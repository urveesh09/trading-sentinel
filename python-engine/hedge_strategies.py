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
``covered_call_recommendation`` / ``bull_put_spread`` /
``bear_call_spread`` / ``iron_condor``
    Quote-backed Phase 2 structures. They require every named contract,
    never substitute a nearby wing, and quote credits in both points and
    rupees.
``delta_hedge_rebalance``
    Reduces a portfolio delta error only with whole, fresh futures lots.

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

    ``premium`` is the executable side of the market (ask for BUY, bid for
    SELL), in **points per underlying unit**.  ``quantity`` is positive and
    expressed in lots; ``lot_size`` makes the conversion to rupees explicit:
    ``premium * quantity * lot_size``.
    """

    side: str
    opt_type: str
    strike: float
    expiry: date
    premium: float
    quantity: int
    lot_size: int = 0
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
        if not isinstance(self.quantity, int) or isinstance(self.quantity, bool) or self.quantity <= 0:
            raise ValueError("quantity must be positive lots")
        if not isinstance(self.lot_size, int) or isinstance(self.lot_size, bool) or self.lot_size <= 0:
            raise ValueError("lot_size must be positive")
        if not all(math.isfinite(float(value)) for value in (self.strike, self.premium, self.bid, self.ask)):
            raise ValueError("leg price fields must be finite")
        if self.strike < 0 or self.premium <= 0:
            raise ValueError("strike must be non-negative and premium positive")
        if self.opt_type in {"CE", "PE"} and self.strike <= 0:
            raise ValueError("option strike must be positive")
        if self.bid <= 0 or self.ask <= 0 or self.ask < self.bid:
            raise ValueError("leg must have a valid two-sided quote")
        expected = self.ask if self.side == "BUY" else self.bid
        if not math.isclose(self.premium, expected, rel_tol=1e-8, abs_tol=1e-8):
            raise ValueError("premium must be executable bid/ask side")
        if self.contract_token <= 0 or not self.tradingsymbol.strip():
            raise ValueError("leg must retain live contract identity")

    @property
    def premium_points(self) -> float:
        """Executable premium in points per underlying unit."""
        return self.premium

    @property
    def premium_rupees_per_lot(self) -> float:
        """Executable premium in rupees for one option/future lot."""
        return self.premium * self.lot_size


@dataclass(frozen=True)
class HedgePlan:
    """Common immutable advisory plan header.

    ``net_premium``, ``max_profit`` and ``max_loss`` are rupee amounts for
    the complete recommendation, never option points.
    """

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
class CoveredCallPlan(HedgePlan):
    covered_units: int = 0
    option_units: int = 0
    call_strike: float = 0.0
    cap_return_pct: float = 0.0
    yield_pct: float = 0.0
    credit_points: float = 0.0
    credit_rupees: float = 0.0


@dataclass(frozen=True)
class BullPutSpreadPlan(HedgePlan):
    short_strike: float = 0.0
    long_strike: float = 0.0
    width: float = 0.0
    # ``credit`` is kept as the rupee amount for compatibility; new callers
    # should consume the explicit fields below.
    credit: float = 0.0
    credit_points: float = 0.0
    credit_rupees: float = 0.0


@dataclass(frozen=True)
class BearCallSpreadPlan(HedgePlan):
    short_strike: float = 0.0
    long_strike: float = 0.0
    width: float = 0.0
    credit: float = 0.0
    credit_points: float = 0.0
    credit_rupees: float = 0.0


@dataclass(frozen=True)
class IronCondorPlan(HedgePlan):
    short_put_strike: float = 0.0
    long_put_strike: float = 0.0
    short_call_strike: float = 0.0
    long_call_strike: float = 0.0
    body_low: float = 0.0
    body_high: float = 0.0
    put_width: float = 0.0
    call_width: float = 0.0
    credit: float = 0.0
    credit_points: float = 0.0
    credit_rupees: float = 0.0


@dataclass(frozen=True)
class FuturesHedgeSizePlan(HedgePlan):
    lots: int = 0
    notional: float = 0.0
    exposure: float = 0.0
    residual_delta: float = 0.0
    beta: float = 1.0


@dataclass(frozen=True)
class DeltaRebalancePlan(HedgePlan):
    """A futures-only rebalance; all delta values are lot-equivalents."""

    side: str = ""
    lots: int = 0
    current_net_delta: float = 0.0
    target_net_delta: float = 0.0
    residual_delta: float = 0.0


@dataclass(frozen=True)
class LongVolPlan(HedgePlan):
    """Defined-loss two-leg long-volatility review."""

    put_strike: float = 0.0
    call_strike: float = 0.0
    debit_points: float = 0.0
    debit_rupees: float = 0.0


@dataclass(frozen=True)
class IronButterflyPlan(HedgePlan):
    """Equal-wing, defined-risk short iron butterfly."""

    body_strike: float = 0.0
    put_wing: float = 0.0
    call_wing: float = 0.0
    width: float = 0.0
    credit_points: float = 0.0
    credit_rupees: float = 0.0


@dataclass(frozen=True)
class CalendarSpreadPlan(HedgePlan):
    strike: float = 0.0
    back_expiry: date = date.min
    debit_points: float = 0.0
    debit_rupees: float = 0.0


@dataclass(frozen=True)
class RatioSpreadPlan(HedgePlan):
    long_strike: float = 0.0
    short_strike: float = 0.0
    ratio: int = 2
    tail_risk: str = "UNBOUNDED"


def _aware_now(now: Optional[datetime]) -> Optional[datetime]:
    if now is None:
        return datetime.now(IST)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        return None
    return now


def _nonnegative_finite(value: object) -> bool:
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool)
        and math.isfinite(float(value)) and float(value) >= 0
    )


def _positive_finite(value: object) -> bool:
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool)
        and math.isfinite(float(value)) and float(value) > 0
    )


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
    if (not _positive_finite(snapshot.forward)
            or not isinstance(snapshot.lot_size, int) or isinstance(snapshot.lot_size, bool)
            or snapshot.lot_size <= 0):
        return False
    if (not isinstance(snapshot.taken_at, datetime)
            or snapshot.taken_at.tzinfo is None or snapshot.taken_at.utcoffset() is None):
        return False
    age = (now - snapshot.taken_at).total_seconds()
    if age < 0 or age > max_age_sec:
        return False
    # A date supplied by the instrument dump is the authority.  No guessed
    # expiry or 0-DTE recommendation is permitted by default.
    expiry = expiry_override or snapshot.expiry
    if not isinstance(expiry, date) or isinstance(expiry, datetime):
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
    if quote is None:
        return False
    if not _positive_finite(quote.bid) or not _positive_finite(quote.ask):
        return False
    if not _nonnegative_finite(quote.oi) or not _nonnegative_finite(quote.volume):
        return False
    if quote.bid <= 0 or quote.ask <= 0 or quote.ask < quote.bid:
        return False
    if quote.spread_pct > max_spread_pct:
        return False
    if quote.oi < min_oi or quote.volume < min_volume:
        return False
    # A depth quote without an exchange timestamp cannot be proven fresh.
    # Do not quietly treat the snapshot timestamp as a substitute.
    if quote.last_trade_time is None:
        return False
    if (not isinstance(quote.last_trade_time, datetime)
            or quote.last_trade_time.tzinfo is None or quote.last_trade_time.utcoffset() is None):
        return False
    age = (now - quote.last_trade_time).total_seconds()
    if age < 0 or age > max_age_sec:
        return False
    return True


def _chain_entry_matches_contract(
    snapshot: ChainSnapshot,
    key: Tuple[float, str],
    quote: ContractQuote,
    expected_type: OptionType,
) -> bool:
    """Reject a quote-map entry whose key and resolved contract disagree."""
    try:
        strike, kind = key
        contract = quote.contract
        return bool(
            math.isfinite(float(strike))
            and kind == expected_type.value
            and contract.instrument_type == expected_type.value
            and math.isclose(float(strike), float(contract.strike), rel_tol=0.0, abs_tol=1e-8)
            and contract.expiry == snapshot.expiry
            and contract.lot_size == snapshot.lot_size
            and contract.token > 0
            and str(contract.tradingsymbol).strip()
            and str(contract.name).strip()
        )
    except (AttributeError, TypeError, ValueError):
        return False


def _same_option_series(*quotes: ContractQuote) -> bool:
    """All spread legs must resolve to the same underlying, expiry and lot."""
    if not quotes:
        return False
    first = quotes[0].contract
    return all(
        quote.contract.name == first.name
        and quote.contract.expiry == first.expiry
        and quote.contract.lot_size == first.lot_size
        and quote.contract.token > 0
        and str(quote.contract.tradingsymbol).strip()
        for quote in quotes
    )


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
    if not _positive_finite(target_abs_delta) or not 0.01 <= float(target_abs_delta) <= 0.95:
        return None
    candidates = []
    for (strike, kind), quote in snapshot.quotes.items():
        if quote is None or not _chain_entry_matches_contract(snapshot, (strike, kind), quote, opt_type):
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


def _exact_quote(
    snapshot: ChainSnapshot,
    now: datetime,
    opt_type: OptionType,
    strike: float,
    *,
    max_spread_pct: float,
    max_age_sec: float,
    min_oi: int,
    min_volume: int,
) -> Optional[Tuple[ContractQuote, float, float]]:
    """Resolve one exact listed strike; never substitute a nearby wing."""
    quote = snapshot.quote(strike, opt_type)
    key = (float(strike), opt_type.value)
    if quote is None or not _chain_entry_matches_contract(snapshot, key, quote, opt_type):
        return None
    if not _liquid_quote(
        quote, snapshot, now, max_spread_pct=max_spread_pct,
        max_age_sec=max_age_sec, min_oi=min_oi, min_volume=min_volume,
    ):
        return None
    result = _quote_iv_delta(snapshot, quote, now, opt_type)
    if result is None:
        return None
    iv, delta = result
    return quote, iv, delta


def _builder_inputs_valid(
    snapshot: ChainSnapshot,
    now: Optional[datetime],
    *,
    allow_0dte: bool,
    max_spread_pct: float,
    max_age_sec: float,
    min_oi: int,
    min_volume: int,
) -> bool:
    return bool(
        now is not None
        and all(_nonnegative_finite(value) for value in (
            max_spread_pct, max_age_sec, min_oi, min_volume,
        ))
        and _valid_snapshot(
            snapshot, now, max_age_sec=max_age_sec, allow_0dte=allow_0dte,
        )
    )


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
        lot_size=c.lot_size,
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


def covered_call_recommendation(
    snapshot: ChainSnapshot,
    covered_units: int,
    now_ist: Optional[datetime] = None,
    short_call_delta: float = 0.30,
    *,
    allow_0dte: bool = False,
    min_dte: int = 7,
    max_spread_pct: float = 0.20,
    max_age_sec: float = 120.0,
    min_oi: int = 1,
    min_volume: int = 1,
) -> Optional[CoveredCallPlan]:
    """Sell only the whole call lots covered by a verified long holding."""
    now = _aware_now(now_ist)
    if (
        not isinstance(covered_units, int) or isinstance(covered_units, bool)
        or covered_units <= 0
        or not isinstance(min_dte, int) or isinstance(min_dte, bool) or min_dte < 1
        or not _builder_inputs_valid(
            snapshot, now, allow_0dte=allow_0dte,
            max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
            min_oi=min_oi, min_volume=min_volume,
        )
    ):
        return None
    dte = (snapshot.expiry - now.astimezone(IST).date()).days
    if dte < min_dte:
        return None
    if covered_units % snapshot.lot_size:
        return None
    lots = covered_units // snapshot.lot_size
    if lots <= 0:
        return None
    selected = _select_quote(
        snapshot, now, OptionType.CE, short_call_delta,
        max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
        min_oi=min_oi, min_volume=min_volume,
    )
    if selected is None:
        return None
    quote, iv, delta = selected
    if quote.contract.strike <= snapshot.forward or not _same_option_series(quote):
        return None
    leg = _leg(quote, "SELL", lots, iv, delta, now, snapshot)
    option_units = lots * snapshot.lot_size
    credit = leg.premium * option_units
    capped_gain = (leg.strike - snapshot.forward) * option_units + credit
    downside_loss = max(0.0, snapshot.forward * option_units - credit)
    breakeven = snapshot.forward - leg.premium
    return CoveredCallPlan(
        strategy="covered_call_recommendation", underlying=quote.contract.name,
        spot=float(snapshot.forward), expiry=snapshot.expiry,
        taken_at=snapshot.taken_at, legs=(leg,), net_premium=credit,
        max_profit=capped_gain, max_loss=downside_loss,
        breakevens=(breakeven,), hedge_ratio=option_units / covered_units,
        rationale=(f"Sell {lots} covered {quote.contract.tradingsymbol} lot(s); "
                   f"coverage {option_units}/{covered_units} units."),
        covered_units=covered_units, option_units=option_units,
        call_strike=leg.strike,
        cap_return_pct=capped_gain / (snapshot.forward * option_units),
        yield_pct=credit / (snapshot.forward * option_units),
        credit_points=leg.premium_points,
        credit_rupees=credit,
    )


def bull_put_spread(
    snapshot: ChainSnapshot,
    now_ist: Optional[datetime] = None,
    short_delta: float = 0.30,
    width: float = 200.0,
    lots: int = 1,
    *,
    allow_0dte: bool = False,
    min_credit: float = 0.0,
    max_spread_pct: float = 0.20,
    max_age_sec: float = 120.0,
    min_oi: int = 1,
    min_volume: int = 1,
) -> Optional[BullPutSpreadPlan]:
    """Build an OTM put credit spread using an exact listed long wing."""
    now = _aware_now(now_ist)
    if (
        not _positive_finite(width) or not isinstance(lots, int) or isinstance(lots, bool)
        or lots <= 0 or not _nonnegative_finite(min_credit)
        or not _builder_inputs_valid(
            snapshot, now, allow_0dte=allow_0dte,
            max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
            min_oi=min_oi, min_volume=min_volume,
        )
    ):
        return None
    short = _select_quote(
        snapshot, now, OptionType.PE, short_delta,
        max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
        min_oi=min_oi, min_volume=min_volume,
    )
    if short is None:
        return None
    short_q, short_iv, short_d = short
    short_strike = short_q.contract.strike
    if short_strike >= snapshot.forward:
        return None
    long = _exact_quote(
        snapshot, now, OptionType.PE, short_strike - width,
        max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
        min_oi=min_oi, min_volume=min_volume,
    )
    if long is None:
        return None
    long_q, long_iv, long_d = long
    actual_width = short_strike - long_q.contract.strike
    if not _same_option_series(short_q, long_q) or not math.isclose(
            actual_width, float(width), rel_tol=0.0, abs_tol=1e-8):
        return None
    credit_points = short_q.bid - long_q.ask
    if credit_points <= min_credit or credit_points >= actual_width:
        return None
    short_leg = _leg(short_q, "SELL", lots, short_iv, short_d, now, snapshot)
    long_leg = _leg(long_q, "BUY", lots, long_iv, long_d, now, snapshot)
    units = lots * snapshot.lot_size
    credit = credit_points * units
    return BullPutSpreadPlan(
        strategy="bull_put_spread", underlying=short_q.contract.name,
        spot=float(snapshot.forward), expiry=snapshot.expiry,
        taken_at=snapshot.taken_at, legs=(short_leg, long_leg),
        net_premium=credit, max_profit=credit,
        max_loss=(actual_width - credit_points) * units,
        breakevens=(short_strike - credit_points,), hedge_ratio=1.0,
        rationale=(f"Sell {short_q.contract.tradingsymbol} and buy exact "
                   f"{long_q.contract.tradingsymbol} protection."),
        short_strike=short_strike, long_strike=long_q.contract.strike,
        width=actual_width, credit=credit, credit_points=credit_points,
        credit_rupees=credit,
    )


def bear_call_spread(
    snapshot: ChainSnapshot,
    now_ist: Optional[datetime] = None,
    short_delta: float = 0.30,
    width: float = 200.0,
    lots: int = 1,
    *,
    allow_0dte: bool = False,
    min_credit: float = 0.0,
    max_spread_pct: float = 0.20,
    max_age_sec: float = 120.0,
    min_oi: int = 1,
    min_volume: int = 1,
) -> Optional[BearCallSpreadPlan]:
    """Build an OTM call credit spread using an exact listed long wing."""
    now = _aware_now(now_ist)
    if (
        not _positive_finite(width) or not isinstance(lots, int) or isinstance(lots, bool)
        or lots <= 0 or not _nonnegative_finite(min_credit)
        or not _builder_inputs_valid(
            snapshot, now, allow_0dte=allow_0dte,
            max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
            min_oi=min_oi, min_volume=min_volume,
        )
    ):
        return None
    short = _select_quote(
        snapshot, now, OptionType.CE, short_delta,
        max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
        min_oi=min_oi, min_volume=min_volume,
    )
    if short is None:
        return None
    short_q, short_iv, short_d = short
    short_strike = short_q.contract.strike
    if short_strike <= snapshot.forward:
        return None
    long = _exact_quote(
        snapshot, now, OptionType.CE, short_strike + width,
        max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
        min_oi=min_oi, min_volume=min_volume,
    )
    if long is None:
        return None
    long_q, long_iv, long_d = long
    actual_width = long_q.contract.strike - short_strike
    if not _same_option_series(short_q, long_q) or not math.isclose(
            actual_width, float(width), rel_tol=0.0, abs_tol=1e-8):
        return None
    credit_points = short_q.bid - long_q.ask
    if credit_points <= min_credit or credit_points >= actual_width:
        return None
    short_leg = _leg(short_q, "SELL", lots, short_iv, short_d, now, snapshot)
    long_leg = _leg(long_q, "BUY", lots, long_iv, long_d, now, snapshot)
    units = lots * snapshot.lot_size
    credit = credit_points * units
    return BearCallSpreadPlan(
        strategy="bear_call_spread", underlying=short_q.contract.name,
        spot=float(snapshot.forward), expiry=snapshot.expiry,
        taken_at=snapshot.taken_at, legs=(short_leg, long_leg),
        net_premium=credit, max_profit=credit,
        max_loss=(actual_width - credit_points) * units,
        breakevens=(short_strike + credit_points,), hedge_ratio=1.0,
        rationale=(f"Sell {short_q.contract.tradingsymbol} and buy exact "
                   f"{long_q.contract.tradingsymbol} protection."),
        short_strike=short_strike, long_strike=long_q.contract.strike,
        width=actual_width, credit=credit, credit_points=credit_points,
        credit_rupees=credit,
    )


def iron_condor(
    snapshot: ChainSnapshot,
    now_ist: Optional[datetime] = None,
    short_put_delta: float = 0.16,
    short_call_delta: float = 0.16,
    wing_width: float = 200.0,
    lots: int = 1,
    *,
    allow_0dte: bool = False,
    min_credit: float = 0.0,
    max_spread_pct: float = 0.20,
    max_age_sec: float = 120.0,
    min_oi: int = 1,
    min_volume: int = 1,
) -> Optional[IronCondorPlan]:
    """Build a four-leg defined-risk condor with exact listed wings."""
    now = _aware_now(now_ist)
    if (
        not _positive_finite(wing_width) or not isinstance(lots, int) or isinstance(lots, bool)
        or lots <= 0 or not _nonnegative_finite(min_credit)
        or not _builder_inputs_valid(
            snapshot, now, allow_0dte=allow_0dte,
            max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
            min_oi=min_oi, min_volume=min_volume,
        )
    ):
        return None
    short_put = _select_quote(
        snapshot, now, OptionType.PE, short_put_delta,
        max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
        min_oi=min_oi, min_volume=min_volume,
    )
    short_call = _select_quote(
        snapshot, now, OptionType.CE, short_call_delta,
        max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
        min_oi=min_oi, min_volume=min_volume,
    )
    if short_put is None or short_call is None:
        return None
    sp_q, sp_iv, sp_d = short_put
    sc_q, sc_iv, sc_d = short_call
    lp = _exact_quote(
        snapshot, now, OptionType.PE, sp_q.contract.strike - wing_width,
        max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
        min_oi=min_oi, min_volume=min_volume,
    )
    lc = _exact_quote(
        snapshot, now, OptionType.CE, sc_q.contract.strike + wing_width,
        max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
        min_oi=min_oi, min_volume=min_volume,
    )
    if lp is None or lc is None:
        return None
    lp_q, lp_iv, lp_d = lp
    lc_q, lc_iv, lc_d = lc
    lp_k, sp_k = lp_q.contract.strike, sp_q.contract.strike
    sc_k, lc_k = sc_q.contract.strike, lc_q.contract.strike
    if (
        not _same_option_series(sp_q, lp_q, sc_q, lc_q)
        or not lp_k < sp_k < snapshot.forward < sc_k < lc_k
        or not math.isclose(sp_k - lp_k, float(wing_width), rel_tol=0.0, abs_tol=1e-8)
        or not math.isclose(lc_k - sc_k, float(wing_width), rel_tol=0.0, abs_tol=1e-8)
    ):
        return None
    put_width, call_width = sp_k - lp_k, lc_k - sc_k
    put_credit = sp_q.bid - lp_q.ask
    call_credit = sc_q.bid - lc_q.ask
    credit_points = put_credit + call_credit
    if (
        put_credit <= 0 or call_credit <= 0 or credit_points <= min_credit
        or credit_points >= min(put_width, call_width)
    ):
        return None
    legs = (
        _leg(sp_q, "SELL", lots, sp_iv, sp_d, now, snapshot),
        _leg(lp_q, "BUY", lots, lp_iv, lp_d, now, snapshot),
        _leg(sc_q, "SELL", lots, sc_iv, sc_d, now, snapshot),
        _leg(lc_q, "BUY", lots, lc_iv, lc_d, now, snapshot),
    )
    units = lots * snapshot.lot_size
    credit = credit_points * units
    return IronCondorPlan(
        strategy="iron_condor", underlying=sp_q.contract.name,
        spot=float(snapshot.forward), expiry=snapshot.expiry,
        taken_at=snapshot.taken_at, legs=legs, net_premium=credit,
        max_profit=credit,
        max_loss=(max(put_width, call_width) - credit_points) * units,
        breakevens=(sp_k - credit_points, sc_k + credit_points),
        hedge_ratio=1.0,
        rationale="Sell both liquid OTM tails with exact listed protective wings.",
        short_put_strike=sp_k, long_put_strike=lp_k,
        short_call_strike=sc_k, long_call_strike=lc_k,
        body_low=sp_k, body_high=sc_k, put_width=put_width,
        call_width=call_width, credit=credit,
        credit_points=credit_points, credit_rupees=credit,
    )


def delta_hedge_rebalance(
    snapshot: ChainSnapshot,
    current_net_delta: float,
    target_net_delta: float = 0.0,
    now_ist: Optional[datetime] = None,
    *,
    delta_threshold: float = 0.15,
    allow_0dte: bool = False,
    max_spread_pct: float = 0.20,
    max_age_sec: float = 120.0,
    min_oi: int = 1,
    min_volume: int = 1,
) -> Optional[DeltaRebalancePlan]:
    """Reduce delta error with conservative whole futures lots only.

    Delta inputs are lot-equivalents.  Lots are rounded down so the hedge
    never crosses the requested target; sub-lot errors deliberately produce
    no recommendation.
    """
    now = _aware_now(now_ist)
    if (
        now is None or not isinstance(current_net_delta, (int, float))
        or isinstance(current_net_delta, bool) or not math.isfinite(current_net_delta)
        or not isinstance(target_net_delta, (int, float))
        or isinstance(target_net_delta, bool) or not math.isfinite(target_net_delta)
        or not _positive_finite(delta_threshold)
        or not all(_nonnegative_finite(value) for value in (
            max_spread_pct, max_age_sec, min_oi, min_volume,
        ))
        or not isinstance(snapshot, ChainSnapshot) or snapshot.fut_quote is None
    ):
        return None
    q = snapshot.fut_quote
    if not _valid_snapshot(
        snapshot, now, max_age_sec=max_age_sec, allow_0dte=allow_0dte,
        expiry_override=q.contract.expiry,
    ):
        return None
    if (
        q.contract.instrument_type != "FUT" or q.contract.lot_size <= 0
        or q.contract.token <= 0 or not str(q.contract.tradingsymbol).strip()
        or not str(q.contract.name).strip()
        or not _liquid_quote(
            q, snapshot, now, max_spread_pct=max_spread_pct,
            max_age_sec=max_age_sec, min_oi=min_oi, min_volume=min_volume,
        )
    ):
        return None
    adjustment = target_net_delta - current_net_delta
    if abs(adjustment) <= delta_threshold:
        return None
    lots = math.floor(abs(adjustment))
    if lots <= 0:
        return None
    side = "BUY" if adjustment > 0 else "SELL"
    signed_adjustment = lots if side == "BUY" else -lots
    residual = round(current_net_delta + signed_adjustment - target_net_delta, 8)
    if abs(residual) >= abs(current_net_delta - target_net_delta):
        return None
    premium = q.ask if side == "BUY" else q.bid
    leg = LegSpec(
        side=side, opt_type="FUT", strike=0.0, expiry=q.contract.expiry,
        premium=float(premium), quantity=lots, lot_size=q.contract.lot_size,
        contract_token=q.contract.token,
        tradingsymbol=q.contract.tradingsymbol, bid=float(q.bid), ask=float(q.ask),
    )
    return DeltaRebalancePlan(
        strategy="delta_hedge_rebalance", underlying=q.contract.name,
        spot=float(snapshot.forward), expiry=q.contract.expiry,
        taken_at=snapshot.taken_at, legs=(leg,), net_premium=0.0,
        max_profit=math.inf, max_loss=math.inf, breakevens=(),
        hedge_ratio=lots / abs(adjustment),
        rationale=(f"{side.title()} {lots} whole future lot(s); residual "
                   f"delta error {residual:+.4f}."),
        side=side, lots=lots, current_net_delta=current_net_delta,
        target_net_delta=target_net_delta, residual_delta=residual,
    )


def _atm_pair(snapshot: ChainSnapshot, now: datetime, **filters):
    strikes = sorted({float(k) for k, kind in snapshot.quotes if kind in {"CE", "PE"}})
    if not strikes:
        return None
    strike = min(strikes, key=lambda value: (abs(value - snapshot.forward), value))
    put = _exact_quote(snapshot, now, OptionType.PE, strike, **filters)
    call = _exact_quote(snapshot, now, OptionType.CE, strike, **filters)
    if put is None or call is None or not _same_option_series(put[0], call[0]):
        return None
    return strike, put, call


def long_straddle(
    snapshot: ChainSnapshot, now_ist: Optional[datetime] = None, lots: int = 1,
    *, allow_0dte: bool = False, max_spread_pct: float = 0.20,
    max_age_sec: float = 120.0, min_oi: int = 1, min_volume: int = 1,
) -> Optional[LongVolPlan]:
    """Buy the nearest listed ATM put and call; loss is capped at the debit."""
    now = _aware_now(now_ist)
    if (not isinstance(lots, int) or isinstance(lots, bool) or lots <= 0
            or not _builder_inputs_valid(snapshot, now, allow_0dte=allow_0dte,
                max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
                min_oi=min_oi, min_volume=min_volume)):
        return None
    filters = dict(max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
                   min_oi=min_oi, min_volume=min_volume)
    pair = _atm_pair(snapshot, now, **filters)
    if pair is None:
        return None
    strike, (pq, piv, pd), (cq, civ, cd) = pair
    debit_points = pq.ask + cq.ask
    units = lots * snapshot.lot_size
    debit = debit_points * units
    legs = (_leg(pq, "BUY", lots, piv, pd, now, snapshot),
            _leg(cq, "BUY", lots, civ, cd, now, snapshot))
    return LongVolPlan(
        strategy="long_straddle", underlying=pq.contract.name,
        spot=float(snapshot.forward), expiry=snapshot.expiry,
        taken_at=snapshot.taken_at, legs=legs, net_premium=-debit,
        max_profit=math.inf, max_loss=debit,
        breakevens=(strike - debit_points, strike + debit_points),
        hedge_ratio=1.0, rationale="Buy the same listed ATM put and call with executable asks.",
        put_strike=strike, call_strike=strike, debit_points=debit_points,
        debit_rupees=debit,
    )


def long_strangle(
    snapshot: ChainSnapshot, now_ist: Optional[datetime] = None,
    target_delta: float = 0.25, lots: int = 1, *, allow_0dte: bool = False,
    max_spread_pct: float = 0.20, max_age_sec: float = 120.0,
    min_oi: int = 1, min_volume: int = 1,
) -> Optional[LongVolPlan]:
    """Buy liquid OTM put/call tails with bounded premium risk."""
    now = _aware_now(now_ist)
    if (not isinstance(lots, int) or isinstance(lots, bool) or lots <= 0
            or not _builder_inputs_valid(snapshot, now, allow_0dte=allow_0dte,
                max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
                min_oi=min_oi, min_volume=min_volume)):
        return None
    filters = dict(max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
                   min_oi=min_oi, min_volume=min_volume)
    put = _select_quote(snapshot, now, OptionType.PE, target_delta, **filters)
    call = _select_quote(snapshot, now, OptionType.CE, target_delta, **filters)
    if put is None or call is None:
        return None
    pq, piv, pd = put; cq, civ, cd = call
    if (not _same_option_series(pq, cq)
            or not pq.contract.strike < snapshot.forward < cq.contract.strike):
        return None
    debit_points = pq.ask + cq.ask
    units = lots * snapshot.lot_size
    debit = debit_points * units
    legs = (_leg(pq, "BUY", lots, piv, pd, now, snapshot),
            _leg(cq, "BUY", lots, civ, cd, now, snapshot))
    return LongVolPlan(
        strategy="long_strangle", underlying=pq.contract.name,
        spot=float(snapshot.forward), expiry=snapshot.expiry,
        taken_at=snapshot.taken_at, legs=legs, net_premium=-debit,
        max_profit=math.inf, max_loss=debit,
        breakevens=(pq.contract.strike - debit_points,
                    cq.contract.strike + debit_points), hedge_ratio=1.0,
        rationale="Buy liquid OTM put and call tails with executable asks.",
        put_strike=pq.contract.strike, call_strike=cq.contract.strike,
        debit_points=debit_points, debit_rupees=debit,
    )


def iron_butterfly(
    snapshot: ChainSnapshot, now_ist: Optional[datetime] = None,
    wing_width: float = 200.0, lots: int = 1, *, allow_0dte: bool = False,
    min_credit: float = 0.0, max_spread_pct: float = 0.20,
    max_age_sec: float = 120.0, min_oi: int = 1, min_volume: int = 1,
) -> Optional[IronButterflyPlan]:
    """Sell an ATM straddle with exact, equal-distance protective wings."""
    now = _aware_now(now_ist)
    if (not _positive_finite(wing_width) or not isinstance(lots, int)
            or isinstance(lots, bool) or lots <= 0 or not _nonnegative_finite(min_credit)
            or not _builder_inputs_valid(snapshot, now, allow_0dte=allow_0dte,
                max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
                min_oi=min_oi, min_volume=min_volume)):
        return None
    filters = dict(max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
                   min_oi=min_oi, min_volume=min_volume)
    pair = _atm_pair(snapshot, now, **filters)
    if pair is None:
        return None
    body, (spq, spiv, spd), (scq, sciv, scd) = pair
    lp = _exact_quote(snapshot, now, OptionType.PE, body-wing_width, **filters)
    lc = _exact_quote(snapshot, now, OptionType.CE, body+wing_width, **filters)
    if lp is None or lc is None:
        return None
    lpq, lpiv, lpd = lp; lcq, lciv, lcd = lc
    if not _same_option_series(spq, scq, lpq, lcq):
        return None
    credit_points = spq.bid + scq.bid - lpq.ask - lcq.ask
    if credit_points <= min_credit or credit_points >= wing_width:
        return None
    legs = (_leg(spq, "SELL", lots, spiv, spd, now, snapshot),
            _leg(scq, "SELL", lots, sciv, scd, now, snapshot),
            _leg(lpq, "BUY", lots, lpiv, lpd, now, snapshot),
            _leg(lcq, "BUY", lots, lciv, lcd, now, snapshot))
    units = lots * snapshot.lot_size
    credit = credit_points * units
    return IronButterflyPlan(
        strategy="iron_butterfly", underlying=spq.contract.name,
        spot=float(snapshot.forward), expiry=snapshot.expiry,
        taken_at=snapshot.taken_at, legs=legs, net_premium=credit,
        max_profit=credit, max_loss=(wing_width-credit_points)*units,
        breakevens=(body-credit_points, body+credit_points), hedge_ratio=1.0,
        rationale="Sell the ATM body with exact equal-distance protective wings.",
        body_strike=body, put_wing=body-wing_width,
        call_wing=body+wing_width, width=wing_width,
        credit_points=credit_points, credit_rupees=credit,
    )


def calendar_diary_spread(
    front: ChainSnapshot, back: ChainSnapshot,
    now_ist: Optional[datetime] = None, lots: int = 1, *,
    opt_type: OptionType = OptionType.CE, allow_0dte: bool = False,
    max_spread_pct: float = 0.20, max_age_sec: float = 120.0,
    min_oi: int = 1, min_volume: int = 1,
) -> Optional[CalendarSpreadPlan]:
    """Sell front expiry and buy the same strike in a later expiry."""
    now = _aware_now(now_ist)
    if (not isinstance(lots, int) or isinstance(lots, bool) or lots <= 0
            or opt_type not in {OptionType.CE, OptionType.PE}
            or not _builder_inputs_valid(front, now, allow_0dte=allow_0dte,
                max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
                min_oi=min_oi, min_volume=min_volume)
            or not _builder_inputs_valid(back, now, allow_0dte=False,
                max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
                min_oi=min_oi, min_volume=min_volume)
            or back.expiry <= front.expiry or back.lot_size != front.lot_size):
        return None
    strikes = sorted({float(k) for k, kind in front.quotes if kind == opt_type.value})
    strike = min(strikes, key=lambda value: (abs(value-front.forward), value)) if strikes else None
    if strike is None:
        return None
    filters = dict(max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
                   min_oi=min_oi, min_volume=min_volume)
    fq = _exact_quote(front, now, opt_type, strike, **filters)
    bq = _exact_quote(back, now, opt_type, strike, **filters)
    if fq is None or bq is None:
        return None
    fquote, fiv, fd = fq; bquote, biv, bd = bq
    if (fquote.contract.name != bquote.contract.name
            or fquote.contract.lot_size != bquote.contract.lot_size):
        return None
    debit_points = bquote.ask - fquote.bid
    if debit_points <= 0:
        return None
    units = lots * front.lot_size
    debit = debit_points * units
    legs = (_leg(fquote, "SELL", lots, fiv, fd, now, front),
            _leg(bquote, "BUY", lots, biv, bd, now, back))
    return CalendarSpreadPlan(
        strategy="calendar_diary_spread", underlying=fquote.contract.name,
        spot=float(front.forward), expiry=front.expiry, taken_at=front.taken_at,
        legs=legs, net_premium=-debit, max_profit=math.inf, max_loss=debit,
        breakevens=(), hedge_ratio=1.0,
        rationale="Sell front and buy later expiry at the identical listed strike.",
        strike=strike, back_expiry=back.expiry, debit_points=debit_points,
        debit_rupees=debit,
    )


def ratio_spread(
    snapshot: ChainSnapshot, now_ist: Optional[datetime] = None,
    long_delta: float = 0.40, short_delta: float = 0.20, lots: int = 1,
    *, allow_unbounded: bool = False, max_spread_pct: float = 0.20,
    max_age_sec: float = 120.0, min_oi: int = 1, min_volume: int = 1,
) -> Optional[RatioSpreadPlan]:
    """Construct a 1x2 call ratio only after an explicit unbounded-risk opt-in.

    The Phase-3 runtime never supplies that opt-in. The builder exists for
    transparent research/paper review without letting the scheduler emit an
    unbounded structure accidentally.
    """
    if not allow_unbounded:
        return None
    now = _aware_now(now_ist)
    if (not isinstance(lots, int) or isinstance(lots, bool) or lots <= 0
            or not _builder_inputs_valid(snapshot, now, allow_0dte=False,
                max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
                min_oi=min_oi, min_volume=min_volume)):
        return None
    filters = dict(max_spread_pct=max_spread_pct, max_age_sec=max_age_sec,
                   min_oi=min_oi, min_volume=min_volume)
    long = _select_quote(snapshot, now, OptionType.CE, long_delta, **filters)
    short = _select_quote(snapshot, now, OptionType.CE, short_delta, **filters)
    if long is None or short is None:
        return None
    lq, liv, ld = long; sq, siv, sd = short
    if not (_same_option_series(lq, sq) and lq.contract.strike < sq.contract.strike):
        return None
    legs = (_leg(lq, "BUY", lots, liv, ld, now, snapshot),
            _leg(sq, "SELL", lots*2, siv, sd, now, snapshot))
    net_points = 2*sq.bid-lq.ask
    units = lots*snapshot.lot_size
    net_rupees = net_points*units
    width = sq.contract.strike-lq.contract.strike
    # At the short strike the bought call realizes the full vertical width;
    # above it the extra naked short call creates unbounded loss.
    max_profit = (width+net_points)*units
    upper_breakeven = sq.contract.strike+width+net_points
    return RatioSpreadPlan(
        strategy="ratio_spread", underlying=lq.contract.name,
        spot=float(snapshot.forward), expiry=snapshot.expiry,
        taken_at=snapshot.taken_at, legs=legs, net_premium=net_rupees,
        max_profit=max_profit, max_loss=math.inf,
        breakevens=(upper_breakeven,), hedge_ratio=0.0,
        rationale="Research-only 1x2 call ratio; upside loss is unbounded.",
        long_strike=lq.contract.strike, short_strike=sq.contract.strike,
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
        premium=float(q.bid), quantity=lots, lot_size=fut.lot_size, contract_token=fut.token,
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
    "CoveredCallPlan", "BullPutSpreadPlan", "BearCallSpreadPlan",
    "IronCondorPlan", "FuturesHedgeSizePlan", "DeltaRebalancePlan",
    "LongVolPlan", "IronButterflyPlan", "CalendarSpreadPlan", "RatioSpreadPlan",
    "protective_put_alert", "collar_recommendation", "covered_call_recommendation",
    "bull_put_spread", "bear_call_spread", "iron_condor",
    "delta_hedge_rebalance", "futures_hedge_size", "long_straddle",
    "long_strangle", "iron_butterfly", "calendar_diary_spread", "ratio_spread",
]
