"""Pure, quote-backed advisory hedge constructors.

This module deliberately sits below the scheduler/orchestrator boundary.  It
does not read settings, call a broker, or manufacture a price.  A plan can
only be returned when the supplied :class:`fno_chain.ChainSnapshot` contains
an actual, fresh, two-sided quote for every leg.

The public builders are intentionally conservative:

``protective_put_alert``
    Buys puts against an existing long holding.  Lots are rounded down so a
    hedge can never become a speculative net-long put position.
``collar_recommendation``
    Buys puts and sells calls against a holding.  It refuses a partial lot so
    that the call leg can never be naked.
``futures_hedge_size``
    Sizes a short index-futures hedge from a live future in the snapshot.

All returned dataclasses are frozen.  They are recommendations only;
``advisory_only`` is permanently true and no execution primitive is exposed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional, Tuple

import pytz

import options_math
from fno_chain import ChainSnapshot
from fno_models import ContractQuote, OptionType

IST = pytz.timezone("Asia/Kolkata")
_EXPIRY_CUTOFF = time(15, 30)


@dataclass(frozen=True)
class LegSpec:
    """One executable recommendation leg backed by a resolved contract.

    ``premium`` is the side of the market that would be paid/received
    (ask for BUY, bid for SELL), in index points per unit.  ``quantity`` is
    positive and expressed in lots; side carries the direction.
    """

    side: str
    opt_type: str
    strike: float
    expiry: date
    premium: float
    quantity: int
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    contract_token: int = 0
    tradingsymbol: str = ""
    bid: float = 0.0
    ask: float = 0.0

    def __post_init__(self) -> None:
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if self.opt_type not in {"CE", "PE", "FUT"}:
            raise ValueError("opt_type must be CE, PE, or FUT")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive lots")
        if self.strike < 0 or self.premium < 0:
            raise ValueError("strike and premium must be non-negative")


@dataclass(frozen=True)
class HedgePlan:
    """Common immutable advisory plan header."""

    strategy: str
    underlying: str
    spot: float
    expiry: date
    taken_at: datetime
    legs: Tuple[LegSpec, ...]
    net_premium: float
    max_profit: float
    max_loss: float
    breakevens: Tuple[float, ...]
    hedge_ratio: float
    rationale: str
    advisory_only: bool = True

    def __post_init__(self) -> None:
        if not self.advisory_only:
            raise ValueError("hedge plans are advisory-only")
        if not self.underlying or self.spot <= 0 or self.expiry <= date.min:
            raise ValueError("invalid plan identity")
        if self.net_premium != self.net_premium:
            raise ValueError("net_premium must be finite")
        if not self.taken_at.tzinfo or self.taken_at.utcoffset() is None:
            raise ValueError("taken_at must be timezone-aware")


@dataclass(frozen=True)
class ProtectivePutPlan(HedgePlan):
    protected_units: int = 0
    option_units: int = 0
    cost_as_pct: float = 0.0
    put_strike: float = 0.0


@dataclass(frozen=True)
class CollarPlan(HedgePlan):
    protected_units: int = 0
    option_units: int = 0
    put_strike: float = 0.0
    call_strike: float = 0.0
    net_debit: float = 0.0
    capped_upside: float = 0.0
    floored_downside: float = 0.0


@dataclass(frozen=True)
class FuturesHedgeSizePlan(HedgePlan):
    lots: int = 0
    notional: float = 0.0
    exposure: float = 0.0
    residual_delta: float = 0.0
    beta: float = 1.0


def _aware_now(now: Optional[datetime]) -> Optional[datetime]:
    if now is None:
        return datetime.now(IST)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        return None
    return now


def _valid_snapshot(
    snapshot: ChainSnapshot,
    now: datetime,
    *,
    max_age_sec: float,
    allow_0dte: bool,
    expiry_override: Optional[date] = None,
) -> bool:
    if not isinstance(snapshot, ChainSnapshot):
        return False
    if snapshot.forward <= 0 or snapshot.lot_size <= 0:
        return False
    if snapshot.taken_at.tzinfo is None or snapshot.taken_at.utcoffset() is None:
        return False
    age = (now - snapshot.taken_at).total_seconds()
    if age < 0 or age > max_age_sec:
        return False
    # A date supplied by the instrument dump is the authority.  No guessed
    # expiry or 0-DTE recommendation is permitted by default.
    expiry = expiry_override or snapshot.expiry
    if not isinstance(expiry, date):
        return False
    dte = (expiry - now.astimezone(IST).date()).days
    return dte > 0 if not allow_0dte else dte >= 0


def _years_to_expiry(expiry: date, now: datetime) -> float:
    cutoff = IST.localize(datetime.combine(expiry, _EXPIRY_CUTOFF))
    return max(0.0, (cutoff - now.astimezone(IST)).total_seconds()) / (365 * 86400)


def _liquid_quote(
    quote: Optional[ContractQuote],
    snapshot: ChainSnapshot,
    now: datetime,
    *,
    max_spread_pct: float,
    max_age_sec: float,
    min_oi: int,
    min_volume: int,
) -> bool:
    if quote is None or not quote.two_sided:
        return False
    if quote.bid <= 0 or quote.ask <= 0 or quote.ask < quote.bid:
        return False
    if quote.spread_pct > max_spread_pct:
        return False
    if quote.oi < min_oi or quote.volume < min_volume:
        return False
    if quote.last_trade_time is not None:
        if quote.last_trade_time.tzinfo is None or quote.last_trade_time.utcoffset() is None:
            return False
        age = (now - quote.last_trade_time).total_seconds()
        if age < 0 or age > max_age_sec:
            return False
    return True


def _quote_iv_delta(
    snapshot: ChainSnapshot,
    quote: ContractQuote,
    now: datetime,
    opt_type: OptionType,
) -> Optional[Tuple[float, float]]:
    t = _years_to_expiry(snapshot.expiry, now)
    if t <= 0:
        return None
    iv = options_math.implied_vol(
        quote.mid, snapshot.forward, quote.contract.strike, t, 0.065,
        opt_type == OptionType.CE,
    )
    if iv is None or not math.isfinite(iv) or iv <= 0:
        return None
    d = options_math.delta(
        snapshot.forward, quote.contract.strike, t, iv, 0.065,
        opt_type == OptionType.CE,
    )
    return iv, d


def _select_quote(
    snapshot: ChainSnapshot,
    now: datetime,
    opt_type: OptionType,
    target_abs_delta: float,
    *,
    max_spread_pct: float,
    max_age_sec: float,
    min_oi: int,
    min_volume: int,
) -> Optional[Tuple[ContractQuote, float, float]]:
    if not 0.01 <= target_abs_delta <= 0.95:
        return None
    candidates = []
    for (strike, kind), quote in snapshot.quotes.items():
        if kind != opt_type.value:
            continue
        if quote is None or quote.contract.expiry != snapshot.expiry:
            continue
        if not _liquid_quote(
            quote, snapshot, now, max_spread_pct=max_spread_pct,
            max_age_sec=max_age_sec, min_oi=min_oi, min_volume=min_volume,
        ):
            continue
        # Protective puts and covered calls must be OTM.  An ATM contract is
        # allowed at the boundary, but an ITM call/put would change the hedge
        # objective and is never silently substituted.
        if opt_type == OptionType.PE and strike > snapshot.forward * 1.001:
            continue
        if opt_type == OptionType.CE and strike < snapshot.forward * 0.999:
            continue
        result = _quote_iv_delta(snapshot, quote, now, opt_type)
        if result is None:
            continue
        iv, delta = result
        candidates.append((abs(abs(delta) - target_abs_delta), quote, iv, delta))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], abs(x[1].contract.strike - snapshot.forward)))
    _, quote, iv, delta = candidates[0]
    return quote, iv, delta


def _leg(
    quote: ContractQuote, side: str, quantity: int, iv: float, delta: float,
    now: datetime, snapshot: ChainSnapshot,
) -> LegSpec:
    c = quote.contract
    t = _years_to_expiry(snapshot.expiry, now)
    premium = quote.ask if side == "BUY" else quote.bid
    is_call = c.instrument_type == OptionType.CE.value
    return LegSpec(
        side=side, opt_type=c.instrument_type, strike=c.strike,
        expiry=c.expiry, premium=float(premium), quantity=quantity,
        delta=options_math.delta(snapshot.forward, c.strike, t, iv, 0.065, is_call),
        gamma=options_math.gamma(snapshot.forward, c.strike, t, iv, 0.065),
        theta=options_math.theta(snapshot.forward, c.strike, t, iv, 0.065, is_call),
        vega=options_math.vega(snapshot.forward, c.strike, t, iv, 0.065),
        contract_token=c.token, tradingsymbol=c.tradingsymbol,
        bid=float(quote.bid), ask=float(quote.ask),
    )


def protective_put_alert(
    snapshot: ChainSnapshot,
    protected_units: int,
    now_ist: Optional[datetime] = None,
    put_delta: float = 0.20,
    *,
    allow_0dte: bool = False,
    max_spread_pct: float = 0.20,
    max_age_sec: float = 120.0,
    min_oi: int = 1,
    min_volume: int = 1,
) -> Optional[ProtectivePutPlan]:
    """Build a fully quote-backed long-put hedge, or return ``None``."""
    now = _aware_now(now_ist)
    if (now is None or protected_units <= 0 or max_spread_pct < 0 or
            max_age_sec < 0 or min_oi < 0 or min_volume < 0 or
            not _valid_snapshot(
        snapshot, now, max_age_sec=max_age_sec, allow_0dte=allow_0dte,
    )):
        return None
    # Never round a hedge above the verified holding.  If the holding is
    # smaller than one live lot, an option hedge would create net short-delta
    # exposure below the strike and is therefore declined.
    lots = protected_units // snapshot.lot_size
    if lots <= 0:
        return None
    selected = _select_quote(
        snapshot, now, OptionType.PE, put_delta,
        max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
        min_oi=min_oi, min_volume=min_volume,
    )
    if selected is None:
        return None
    quote, iv, delta = selected
    leg = _leg(quote, "BUY", lots, iv, delta, now, snapshot)
    option_units = lots * snapshot.lot_size
    cost = leg.premium * option_units
    return ProtectivePutPlan(
        strategy="protective_put_alert", underlying=quote.contract.name,
        spot=float(snapshot.forward), expiry=snapshot.expiry,
        taken_at=snapshot.taken_at, legs=(leg,), net_premium=cost,
        max_profit=math.inf, max_loss=cost, breakevens=(),
        hedge_ratio=option_units / protected_units,
        rationale=(f"Buy {lots} lot(s) of the live {quote.contract.tradingsymbol} "
                   f"put; coverage {option_units}/{protected_units} units."),
        protected_units=protected_units, option_units=option_units,
        cost_as_pct=cost / (snapshot.forward * protected_units),
        put_strike=quote.contract.strike,
    )


def collar_recommendation(
    snapshot: ChainSnapshot,
    protected_units: int,
    now_ist: Optional[datetime] = None,
    put_delta: float = 0.20,
    call_delta: float = 0.20,
    *,
    allow_0dte: bool = False,
    max_spread_pct: float = 0.20,
    max_age_sec: float = 120.0,
    min_oi: int = 1,
    min_volume: int = 1,
) -> Optional[CollarPlan]:
    """Build a covered long-put/short-call collar, or return ``None``.

    The held quantity must be an exact whole number of live option lots.  It
    is safer to decline a remainder than to issue a naked call suggestion.
    """
    now = _aware_now(now_ist)
    if (now is None or protected_units <= 0 or max_spread_pct < 0 or
            max_age_sec < 0 or min_oi < 0 or min_volume < 0 or
            not _valid_snapshot(
        snapshot, now, max_age_sec=max_age_sec, allow_0dte=allow_0dte,
    )):
        return None
    if snapshot.lot_size <= 0 or protected_units % snapshot.lot_size:
        return None
    lots = protected_units // snapshot.lot_size
    put = _select_quote(
        snapshot, now, OptionType.PE, put_delta,
        max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
        min_oi=min_oi, min_volume=min_volume,
    )
    call = _select_quote(
        snapshot, now, OptionType.CE, call_delta,
        max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
        min_oi=min_oi, min_volume=min_volume,
    )
    if put is None or call is None:
        return None
    put_q, put_iv, put_d = put
    call_q, call_iv, call_d = call
    # Avoid an inverted or crossing collar caused by bad/stale chain data.
    if put_q.contract.strike >= call_q.contract.strike:
        return None
    put_leg = _leg(put_q, "BUY", lots, put_iv, put_d, now, snapshot)
    call_leg = _leg(call_q, "SELL", lots, call_iv, call_d, now, snapshot)
    units = lots * snapshot.lot_size
    net_debit = (put_leg.premium - call_leg.premium) * units
    # Worst case at S=0 for the held units and option legs.  The exact
    # piecewise payoff is finite because the call is fully covered.
    downside_loss = max(0.0, snapshot.forward * protected_units - put_leg.strike * units + net_debit)
    capped_upside = max(0.0, (call_leg.strike - snapshot.forward) * protected_units - net_debit)
    # Positive point distance from the current forward to the protection
    # floor.  A negative "downside" is not meaningful to callers.
    floored_downside = max(0.0, snapshot.forward - put_leg.strike)
    lower_be = snapshot.forward + net_debit / protected_units
    return CollarPlan(
        strategy="collar_recommendation", underlying=put_q.contract.name,
        spot=float(snapshot.forward), expiry=snapshot.expiry,
        taken_at=snapshot.taken_at, legs=(put_leg, call_leg),
        net_premium=net_debit, max_profit=capped_upside,
        max_loss=downside_loss, breakevens=(lower_be,),
        hedge_ratio=1.0, rationale=(
            f"Buy {lots} put lot(s) and sell {lots} covered call lot(s); "
            "downside floor is funded by the held position."),
        protected_units=protected_units, option_units=units,
        put_strike=put_leg.strike, call_strike=call_leg.strike,
        net_debit=net_debit, capped_upside=capped_upside,
        floored_downside=floored_downside,
    )


def futures_hedge_size(
    snapshot: ChainSnapshot,
    portfolio_value: float,
    beta: float = 1.0,
    hedge_ratio: float = 1.0,
    now_ist: Optional[datetime] = None,
    *,
    allow_0dte: bool = False,
    max_spread_pct: float = 0.20,
    max_age_sec: float = 120.0,
    min_oi: int = 1,
    min_volume: int = 1,
) -> Optional[FuturesHedgeSizePlan]:
    """Size a short live future hedge without rounding into over-hedging.

    ``notional`` is the notional per lot; ``residual_delta`` is the remaining
    rupee exposure after whole-lot sizing.  Zero affordable lots returns
    ``None`` so an orchestrator can explicitly report ``no_trade``.
    """
    now = _aware_now(now_ist)
    if (now is None or portfolio_value <= 0 or beta <= 0 or not 0 < hedge_ratio <= 1 or
            max_spread_pct < 0 or max_age_sec < 0 or min_oi < 0 or min_volume < 0):
        return None
    if not isinstance(snapshot, ChainSnapshot) or snapshot.fut_quote is None:
        return None
    # Futures and options can have different expiries.  Validate freshness
    # against the future's actual instrument-master expiry, not the option
    # expiry carried by the chain ladder.
    if not _valid_snapshot(
        snapshot, now, max_age_sec=max_age_sec, allow_0dte=allow_0dte,
        expiry_override=snapshot.fut_quote.contract.expiry,
    ):
        return None
    q = snapshot.fut_quote
    if not _liquid_quote(
        q, snapshot, now, max_spread_pct=max_spread_pct,
        max_age_sec=max_age_sec, min_oi=min_oi, min_volume=min_volume,
    ) or q is None or q.contract.instrument_type != "FUT":
        return None
    fut = q.contract
    lot_size = fut.lot_size
    if lot_size <= 0:
        return None
    per_lot = snapshot.forward * lot_size
    exposure = portfolio_value * beta * hedge_ratio
    lots = math.floor(exposure / per_lot)
    if lots <= 0:
        return None
    hedged = lots * per_lot
    residual = max(0.0, exposure - hedged)
    leg = LegSpec(
        side="SELL", opt_type="FUT", strike=0.0, expiry=fut.expiry,
        premium=float(q.bid), quantity=lots, contract_token=fut.token,
        tradingsymbol=fut.tradingsymbol, bid=float(q.bid), ask=float(q.ask),
    )
    return FuturesHedgeSizePlan(
        strategy="futures_hedge_size", underlying=fut.name,
        spot=float(snapshot.forward), expiry=fut.expiry,
        taken_at=snapshot.taken_at, legs=(leg,), net_premium=0.0,
        max_profit=math.inf, max_loss=math.inf, breakevens=(),
        hedge_ratio=hedged / (portfolio_value * beta),
        rationale=(f"Short {lots} live {fut.tradingsymbol} lot(s); "
                   f"residual exposure {residual:.2f} rupees."),
        lots=lots, notional=per_lot, exposure=exposure,
        residual_delta=residual, beta=beta,
    )


__all__ = [
    "LegSpec", "HedgePlan", "ProtectivePutPlan", "CollarPlan",
    "FuturesHedgeSizePlan", "protective_put_alert", "collar_recommendation",
    "futures_hedge_size",
]
