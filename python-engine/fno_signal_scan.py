"""
[PARTNER-TIPS 2026-07-18] Read-only ORB signal scan per underlying (WS2).

Thin composition of the already-pure F&O pieces -- bars fetch ->
evaluate_fno_mom -> (on a fired direction) chain snapshot + 0.55-delta
strike pick -- with ZERO executor/positions imports. This is the partner
tips bot's signal source for NIFTY/BANKNIFTY/SENSEX; the NIFTY
paper-trading path in fno_orchestrator is untouched and unaware of it.

The liquidity check here is deliberately NOT the fno_gates §7 ladder
(that needs pool/positions context): a tip on a thin chain is still a
tip -- it ships with a "thin market" tag instead of being suppressed,
because the partner may be looking at a different strike anyway.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import pytz
import structlog

from config import settings
from fno_chain import ChainSnapshot, select_strike_by_delta, take_chain_snapshot
from fno_engine_mom import MomSignal, evaluate_fno_mom
from fno_models import ContractQuote, FnoDirection, OptionType
from fno_underlyings import UnderlyingSpec, get_instruments_for

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

# Same frame the orchestrator uses (~14 sessions of 5-min bars for
# EMA(50) + the per-slot RVOL baseline). Duplicated from
# fno_orchestrator.RVOL_FETCH_CALENDAR_DAYS on purpose: importing the
# orchestrator here would drag the executor module graph into a
# read-only scan (and trip test_fno_isolation's spirit if not its letter).
BARS_FETCH_CALENDAR_DAYS = 21


@dataclass
class UnderlyingScan:
    """One underlying's scan outcome. sig always carries the OR/ATR/EMA
    levels when computable (evaluate_fno_mom fills them even on reject),
    which is what the morning brief reads. snap/pick are only fetched
    when a direction actually fired."""
    name: str
    sig: Optional[MomSignal] = None
    snap: Optional[ChainSnapshot] = None
    pick: Optional[Tuple[ContractQuote, float, float]] = None  # (quote, iv, delta)
    thin_chain: bool = False
    thin_reasons: List[str] = field(default_factory=list)
    # Public futures-bar acquisition and optional entry-chain acquisition are
    # separate facts. A chain outage must not erase an otherwise usable public
    # condition for active-advice management.
    entry_error: str = ""
    error: str = ""


def _liquidity_reasons(q: ContractQuote, iv: float) -> List[str]:
    """Light sanity on the picked strike, reusing the §7 thresholds as
    plain numbers. Returns human-short reasons, empty == healthy."""
    reasons: List[str] = []
    if q.oi < settings.FNO_MIN_OI:
        reasons.append(f"OI {q.oi} < {settings.FNO_MIN_OI}")
    if q.volume < settings.FNO_MIN_VOL:
        reasons.append(f"volume {q.volume} < {settings.FNO_MIN_VOL}")
    spread = q.spread_pct
    if spread == float("inf"):
        reasons.append("one-sided book")
    elif spread > settings.FNO_MAX_SPREAD_PCT:
        reasons.append(f"spread {spread * 100:.1f}% > {settings.FNO_MAX_SPREAD_PCT * 100:.1f}%")
    if not (settings.FNO_IV_SANITY_MIN <= iv <= settings.FNO_IV_SANITY_MAX):
        reasons.append(f"IV {iv:.2f} outside sanity band")
    return reasons


async def observe_underlying(
    kite,
    spec: UnderlyingSpec,
    regime: str,
    now_ist: Optional[datetime] = None,
) -> UnderlyingScan:
    """Fetch and evaluate the public futures-bar condition only.

    This deliberately does *not* request an option chain.  Published advice
    is managed from this public observation, so a slow or unavailable entry
    chain cannot delay an invalidation, target, or retirement update.
    """
    now_ist = now_ist or datetime.now(IST)
    out = UnderlyingScan(name=spec.name)
    try:
        book = get_instruments_for(spec.name)
        today = now_ist.date()
        if not book.ready(today):
            out.error = "instruments_not_ready"
            return out
        fut = book.front_future(today)
        if fut is None:
            out.error = "no_front_future"
            return out

        frm = (now_ist - timedelta(days=BARS_FETCH_CALENDAR_DAYS)).strftime(
            "%Y-%m-%d 09:15:00"
        )
        to = now_ist.strftime("%Y-%m-%d %H:%M:%S")
        bars = await kite.get_intraday_by_token(
            fut.token, frm, to, interval="5minute"
        )
        out.sig = evaluate_fno_mom(bars, regime, now_ist)

        return out
    except Exception as exc:
        logger.error(
            "fno_signal_public_observation_failed underlying=%s err=%s",
            spec.name, str(exc), exc_info=True,
        )
        out.error = str(exc)
        return out


async def attach_entry_chain(
    kite,
    scan: UnderlyingScan,
    now_ist: Optional[datetime] = None,
) -> UnderlyingScan:
    """Attach optional-chain evidence to an already observed signal.

    Entry-chain failure is represented by ``entry_error`` rather than the
    public-observation ``error`` field.  Callers can therefore manage an
    active idea even while suppressing a new entry safely.
    """
    if scan.error or scan.sig is None or scan.sig.direction is None:
        return scan
    now_ist = now_ist or datetime.now(IST)
    try:
        book = get_instruments_for(scan.name)
        if not book.ready(now_ist.date()):
            scan.entry_error = "instruments_not_ready"
            return scan
        snap = await take_chain_snapshot(kite, book, now_ist)
        if snap is None:
            scan.entry_error = "chain_unavailable"
            return scan
        scan.snap = snap

        opt_type = (
            OptionType.CE if scan.sig.direction == FnoDirection.LONG else OptionType.PE
        )
        pick = select_strike_by_delta(snap, opt_type, now_ist)
        if pick is None:
            scan.thin_chain = True
            scan.thin_reasons = ["no strike solves for IV/delta"]
            return scan
        scan.pick = pick
        q, iv, _delta = pick
        scan.thin_reasons = _liquidity_reasons(q, iv)
        scan.thin_chain = bool(scan.thin_reasons)
        return scan
    except Exception as exc:
        logger.error(
            "fno_signal_entry_chain_failed underlying=%s err=%s",
            scan.name, str(exc), exc_info=True,
        )
        scan.entry_error = str(exc)
        return scan


async def scan_underlying(
    kite,
    spec: UnderlyingSpec,
    regime: str,
    now_ist: Optional[datetime] = None,
) -> UnderlyingScan:
    """Evaluate one complete entry scan, preserving the legacy API.

    New-entry consumers use this convenience composition.  The partner
    management loop calls the two phases separately so delivery lifecycle
    work is never held behind optional-chain I/O.
    """
    out = await observe_underlying(kite, spec, regime, now_ist)
    return await attach_entry_chain(kite, out, now_ist)
