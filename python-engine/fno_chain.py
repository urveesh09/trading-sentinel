"""
[FNO-CHAIN 2026-07-10] Option-chain snapshot for the F&O subsystem (spec §6.2).

ATM +/- FNO_STRIKE_WINDOW strikes, both CE and PE (22 contracts), plus the
front-month future = 23 tokens in ONE batched /quote call -- well inside
Kite's 500-instrument batch limit (VERIFY-7). The penny scanner's
per-ticker /quote pattern is a known production bug (BUG-2); do not
repeat it.

Pricing basis: the synthetic forward. We use the front-month futures LTP
directly as F (spec §6.2 sanctions this alternative to put-call parity),
and ALSO back a parity forward out of the ATM straddle as a cross-check;
a >0.5% disagreement is logged loudly because it usually means a stale
leg. Using spot for index options would quietly bias every IV and delta
the module computes, corrupting the §8.4 stop conversion.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import pytz
import structlog

import options_math
from config import settings
from fno_instruments import FnoInstruments
from fno_models import Contract, ContractQuote, OptionType

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

# Risk-free rate for discounting / parity. Only moves premiums by basis
# points at weekly tenors; not worth a live feed.
RISK_FREE_RATE = 0.065

# NSE options settle to the 15:30 close on expiry day.
EXPIRY_CUTOFF_HOUR, EXPIRY_CUTOFF_MIN = 15, 30


def years_to_expiry(expiry: date, now_ist: datetime) -> float:
    cutoff = IST.localize(
        datetime(expiry.year, expiry.month, expiry.day,
                 EXPIRY_CUTOFF_HOUR, EXPIRY_CUTOFF_MIN)
    )
    seconds = (cutoff - now_ist).total_seconds()
    return max(seconds, 0.0) / (365.0 * 24 * 3600)


@dataclass
class ChainSnapshot:
    taken_at: datetime                    # IST
    expiry: date
    forward: float                        # futures LTP (pricing basis)
    parity_forward: Optional[float]       # cross-check; None if not computable
    lot_size: int
    fut_quote: Optional[ContractQuote]
    quotes: Dict[Tuple[float, str], ContractQuote] = field(default_factory=dict)

    def age_sec(self, now_ist: datetime) -> float:
        return (now_ist - self.taken_at).total_seconds()

    def quote(self, strike: float, opt_type: OptionType) -> Optional[ContractQuote]:
        return self.quotes.get((float(strike), opt_type.value))


def _parse_quote_entry(contract: Contract, q: dict) -> ContractQuote:
    depth = q.get("depth") or {}
    buys = depth.get("buy") or []
    sells = depth.get("sell") or []
    bid = float(buys[0]["price"]) if buys and buys[0].get("price") else 0.0
    ask = float(sells[0]["price"]) if sells and sells[0].get("price") else 0.0
    ltt = None
    raw_ltt = q.get("last_trade_time")
    if raw_ltt:
        try:
            ltt = IST.localize(datetime.strptime(str(raw_ltt)[:19], "%Y-%m-%d %H:%M:%S"))
        except (ValueError, TypeError):
            ltt = None
    return ContractQuote(
        contract=contract,
        bid=bid,
        ask=ask,
        ltp=float(q.get("last_price") or 0.0),
        oi=int(q.get("oi") or 0),
        volume=int(q.get("volume") or 0),
        last_trade_time=ltt,
    )


def _parity_forward(
    snapshot_quotes: Dict[Tuple[float, str], ContractQuote],
    atm: float, T: float,
) -> Optional[float]:
    """F = K_atm + (C_atm - P_atm) * e^(rT), from mid prices."""
    ce = snapshot_quotes.get((atm, "CE"))
    pe = snapshot_quotes.get((atm, "PE"))
    if not ce or not pe or not ce.two_sided or not pe.two_sided:
        return None
    return atm + (ce.mid - pe.mid) * math.exp(RISK_FREE_RATE * T)


async def take_chain_snapshot(
    kite, instruments: FnoInstruments, now_ist: Optional[datetime] = None,
) -> Optional[ChainSnapshot]:
    """One batched /quote for the front future + ATM+/-N CE/PE ladder.

    Returns None (loudly) when the prerequisites are missing -- callers
    treat None as "no new entries this tick" (staleness kill switch)."""
    now_ist = now_ist or datetime.now(IST)
    today = now_ist.date()

    fut = instruments.front_future(today)
    expiry = instruments.nearest_option_expiry(today)
    if fut is None or expiry is None:
        logger.warning(
            "fno_chain_unavailable reason=%s",
            "no_front_future" if fut is None else "no_option_expiry",
        )
        return None

    # First pass: futures LTP anchors the strike window.
    fut_data = await kite.get_quote([fut.token])
    fut_q = fut_data.get(fut.token)
    if not fut_q or not fut_q.get("last_price"):
        logger.warning("fno_chain_unavailable reason=fut_quote_empty token=%d", fut.token)
        return None
    forward = float(fut_q["last_price"])

    strikes = instruments.strikes_window(forward, settings.FNO_STRIKE_WINDOW)
    contracts: List[Contract] = []
    for k in strikes:
        for ot in (OptionType.CE, OptionType.PE):
            c = instruments.option(expiry, k, ot)
            if c is not None:
                contracts.append(c)
    if not contracts:
        logger.warning(
            "fno_chain_unavailable reason=no_contracts_in_window forward=%.1f "
            "step=%.0f expiry=%s", forward, instruments.strike_step, expiry,
        )
        return None

    # Single batched call for the whole ladder + the future (refreshed
    # together so the parity cross-check compares same-instant quotes).
    tokens = [c.token for c in contracts] + [fut.token]
    data = await kite.get_quote(tokens)
    if not data:
        logger.warning("fno_chain_unavailable reason=quote_batch_empty tokens=%d", len(tokens))
        return None

    quotes: Dict[Tuple[float, str], ContractQuote] = {}
    for c in contracts:
        q = data.get(c.token)
        if q:
            quotes[(c.strike, c.instrument_type)] = _parse_quote_entry(c, q)

    fut_quote = _parse_quote_entry(fut, data[fut.token]) if fut.token in data else None
    if fut_quote and fut_quote.ltp > 0:
        forward = fut_quote.ltp

    T = years_to_expiry(expiry, now_ist)
    atm = instruments.atm_strike(forward)
    parity_f = _parity_forward(quotes, atm, T)
    if parity_f is not None and forward > 0:
        drift = abs(parity_f - forward) / forward
        if drift > 0.005:
            logger.warning(
                "fno_forward_basis_disagreement fut=%.1f parity=%.1f drift_pct=%.2f "
                "-- one leg is probably stale", forward, parity_f, drift * 100,
            )

    snap = ChainSnapshot(
        taken_at=now_ist, expiry=expiry, forward=forward,
        parity_forward=parity_f, lot_size=instruments.lot_size,
        fut_quote=fut_quote, quotes=quotes,
    )
    logger.info(
        "fno_chain_snapshot expiry=%s forward=%.1f atm=%.0f contracts=%d/%d",
        expiry, forward, atm, len(quotes), len(contracts),
    )
    return snap


def select_strike_by_delta(
    snapshot: ChainSnapshot,
    opt_type: OptionType,
    now_ist: datetime,
    target_delta: Optional[float] = None,
) -> Optional[Tuple[ContractQuote, float, float]]:
    """Pick the strike whose |delta| is closest to FNO_TARGET_DELTA (0.55),
    restricted to ATM-or-ITM -- never OTM (spec §8.3: cheap OTM options are
    how a risk-controlled system quietly becomes a lottery-ticket machine).

    Returns (quote, iv, delta) or None when no candidate solves.
    """
    target = target_delta if target_delta is not None else settings.FNO_TARGET_DELTA
    T = years_to_expiry(snapshot.expiry, now_ist)
    F = snapshot.forward
    best: Optional[Tuple[ContractQuote, float, float]] = None
    best_dist = float("inf")
    for (strike, ot), q in snapshot.quotes.items():
        if ot != opt_type.value:
            continue
        # ATM-or-ITM only: CE strikes at/below the forward, PE at/above,
        # with 0.1% tolerance so the true ATM strike is admitted from
        # either side of F.
        if opt_type == OptionType.CE and strike > F * 1.001:
            continue
        if opt_type == OptionType.PE and strike < F * 0.999:
            continue
        mid = q.mid
        if mid <= 0:
            continue
        iv = options_math.implied_vol(
            mid, F, strike, T, RISK_FREE_RATE, opt_type == OptionType.CE
        )
        if iv is None:
            continue
        d = options_math.delta(F, strike, T, iv, RISK_FREE_RATE, opt_type == OptionType.CE)
        dist = abs(abs(d) - target)
        if dist < best_dist:
            best, best_dist = (q, iv, d), dist
    return best
