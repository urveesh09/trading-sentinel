"""Plain-text, safety-first formatters for partner hedge reviews.

The functions in this module only render already-validated advisory plans.
They never place an order and deliberately avoid imperative execution
language.  Dynamic fields are validated before being interpolated so a
malformed/non-advisory object cannot be presented as a live recommendation.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime
from numbers import Real
from typing import Optional

import pytz

from partner_content import DISCLAIMER
from hedge_analytics import VixRegimeReading
from hedge_strategies import (
    BearCallSpreadPlan,
    BullPutSpreadPlan,
    CalendarSpreadPlan,
    CollarPlan,
    CoveredCallPlan,
    DeltaRebalancePlan,
    FuturesHedgeSizePlan,
    HedgePlan,
    IronButterflyPlan,
    IronCondorPlan,
    LegSpec,
    LongVolPlan,
    RatioSpreadPlan,
    ProtectivePutPlan,
)

MAX_TELEGRAM_CHARS = 4096
IST = pytz.timezone("Asia/Kolkata")
_FORBIDDEN = re.compile(r"execute|buy\s+now|sell\s+now|guaranteed", re.IGNORECASE)


def _finite(value: object, label: str, *, allow_inf: bool = False) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if math.isnan(result) or (not allow_inf and not math.isfinite(result)):
        raise ValueError(f"{label} must be finite")
    return result


def _require_numeric_fields(
    value: object, names: tuple[str, ...], *, allow_inf: tuple[str, ...] = (),
) -> None:
    for name in names:
        raw = getattr(value, name)
        if isinstance(raw, bool) or not isinstance(raw, Real):
            raise ValueError(f"{name} must be a real number")
        _finite(raw, name, allow_inf=name in allow_inf)


def _as_of(value: Optional[datetime]) -> str:
    if value is None:
        return "not supplied"
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("as-of timestamp must be timezone-aware")
    return value.isoformat(timespec="seconds")


def _date(value: object, label: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError(f"{label} must be a date")
    return value


def _money(value: object, label: str, *, allow_inf: bool = False) -> str:
    number = _finite(value, label, allow_inf=allow_inf)
    if math.isinf(number):
        return "not bounded by this hedge"
    return f"₹{number:,.2f}"


def _pct(value: object, label: str) -> str:
    number = _finite(value, label)
    return f"{number * 100:.1f}%"


def _reason(value: object) -> str:
    """Keep diagnostic text single-line and prevent language injection."""
    text = re.sub(r"\s+", " ", str(value or "unspecified")).strip()
    text = _FORBIDDEN.sub("[redacted]", text)
    return text[:500]


def _validate_leg(leg: object, expected_expiry: date) -> LegSpec:
    if not isinstance(leg, LegSpec):
        raise ValueError("plan contains a malformed leg")
    if leg.side not in {"BUY", "SELL"} or leg.opt_type not in {"CE", "PE", "FUT"}:
        raise ValueError("plan contains an invalid leg direction/type")
    if not isinstance(leg.quantity, int) or isinstance(leg.quantity, bool) or leg.quantity <= 0:
        raise ValueError("plan contains an invalid leg quantity")
    if not isinstance(leg.lot_size, int) or isinstance(leg.lot_size, bool) or leg.lot_size <= 0:
        raise ValueError("plan contains an invalid leg lot size")
    if (
        not str(leg.tradingsymbol).strip()
        or not isinstance(leg.contract_token, int)
        or isinstance(leg.contract_token, bool)
        or leg.contract_token <= 0
    ):
        raise ValueError("plan leg is missing the live contract identity")
    _require_numeric_fields(
        leg, ("strike", "premium", "bid", "ask", "delta", "gamma", "theta", "vega"),
    )
    if _date(leg.expiry, "leg expiry") != expected_expiry:
        raise ValueError("leg expiry does not match plan expiry")
    bid = _finite(leg.bid, "leg bid")
    ask = _finite(leg.ask, "leg ask")
    premium = _finite(leg.premium, "leg premium")
    for label, value in (("leg strike", leg.strike), ("leg delta", leg.delta),
                         ("leg gamma", leg.gamma), ("leg theta", leg.theta),
                         ("leg vega", leg.vega)):
        _finite(value, label)
    if leg.strike < 0:
        raise ValueError("plan contains a negative leg strike")
    if bid <= 0 or ask <= 0 or ask < bid or premium <= 0:
        raise ValueError("plan leg does not contain a valid two-sided quote")
    expected = ask if leg.side == "BUY" else bid
    if not math.isclose(premium, expected, rel_tol=1e-7, abs_tol=1e-7):
        raise ValueError("plan leg premium is not the executable side of its quote")
    return leg


def _validate_plan(plan: object, expected_type: type, strategy: str) -> HedgePlan:
    # Do not let a structurally similar object slip through: each formatter is
    # paired with one exact constructor and one exact leg topology.
    if type(plan) is not expected_type:
        raise ValueError(f"expected {expected_type.__name__}")
    if not plan.advisory_only:
        raise ValueError("non-advisory plan rejected")
    if plan.strategy != strategy or not str(plan.underlying).strip() or not str(plan.rationale).strip():
        raise ValueError("plan strategy/underlying is malformed")
    _require_numeric_fields(
        plan, ("spot", "net_premium", "max_loss", "max_profit", "hedge_ratio"),
        allow_inf=("max_loss", "max_profit"),
    )
    spot = _finite(plan.spot, "plan spot")
    if spot <= 0:
        raise ValueError("plan spot must be positive")
    expiry = _date(plan.expiry, "plan expiry")
    if not isinstance(plan.taken_at, datetime) or plan.taken_at.tzinfo is None or plan.taken_at.utcoffset() is None:
        raise ValueError("plan live-as-of timestamp must be timezone-aware")
    if not isinstance(plan.legs, tuple) or not plan.legs:
        raise ValueError("plan must contain at least one leg")
    for leg in plan.legs:
        _validate_leg(leg, expiry)
    _finite(plan.net_premium, "net premium")
    _finite(plan.max_loss, "max loss", allow_inf=True)
    _finite(plan.max_profit, "max profit", allow_inf=True)
    return plan


def _dte(plan: HedgePlan) -> int:
    """Return DTE from the plan's own IST as-of date, never wall-clock now."""
    local_date = plan.taken_at.astimezone(IST).date()
    value = (plan.expiry - local_date).days
    if value < 0:
        raise ValueError("plan expiry is before its live-as-of date")
    return value


def _breakeven_line(plan: HedgePlan) -> str:
    values = tuple(_finite(value, "breakeven") for value in plan.breakevens)
    if not values:
        return "Breakeven: not applicable"
    return "Breakeven(s): " + ", ".join(f"{value:,.2f}" for value in values) + " points"


def _credit_points(legs: tuple[LegSpec, ...]) -> float:
    """Cash-credit convention: SELL premium less BUY premium, per unit."""
    value = sum(leg.premium if leg.side == "SELL" else -leg.premium for leg in legs)
    return _finite(value, "premium credit points")


def _validate_option_plan(
    plan: HedgePlan,
    expected_type: type,
    strategy: str,
    expected_legs: tuple[tuple[str, str], ...],
) -> HedgePlan:
    plan = _validate_plan(plan, expected_type, strategy)
    if len(plan.legs) != len(expected_legs):
        raise ValueError("plan leg count does not match strategy")
    for index, (leg, (side, opt_type)) in enumerate(zip(plan.legs, expected_legs)):
        if (leg.side, leg.opt_type) != (side, opt_type):
            raise ValueError(f"plan leg {index + 1} has the wrong side/type or order")
        for label, value in (("leg delta", leg.delta), ("leg gamma", leg.gamma),
                             ("leg theta", leg.theta), ("leg vega", leg.vega)):
            _finite(value, label)
    net_premium = _finite(plan.net_premium, "net premium")
    max_loss = _finite(plan.max_loss, "max loss")
    max_profit = _finite(plan.max_profit, "max profit")
    if net_premium <= 0 or max_loss <= 0:
        raise ValueError("plan must contain a finite positive premium and max loss")
    if max_profit < 0:
        raise ValueError("plan maximum profit must be finite and non-negative")
    for value in plan.breakevens:
        _finite(value, "breakeven")
    return plan


def _context_line(plan: HedgePlan, context: Optional[str]) -> str:
    supplied = context if context is not None and str(context).strip() else plan.rationale
    return f"Context: {_reason(supplied)}"


def _premium_line(points: float, rupees: float, label: str = "Net premium") -> str:
    points = _finite(points, "premium points")
    rupees = _finite(rupees, "premium rupees")
    return f"{label}: {points:,.2f} points | {_money(rupees, 'premium rupees')}"


def _same_leg_size(legs: tuple[LegSpec, ...]) -> bool:
    first = legs[0]
    return all(
        leg.quantity == first.quantity and leg.lot_size == first.lot_size
        for leg in legs
    )


def _option_greeks_line(legs: tuple[LegSpec, ...]) -> str:
    """Aggregate quote-time option Greeks with side and exchange units."""
    totals = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    for leg in legs:
        if leg.opt_type not in {"CE", "PE"}:
            continue
        sign = 1.0 if leg.side == "BUY" else -1.0
        units = leg.quantity * leg.lot_size
        for name in totals:
            totals[name] += sign * _finite(getattr(leg, name), f"leg {name}") * units
    return (
        "Option-leg Greeks (model, snapshot): "
        f"Δ {totals['delta']:+,.2f} underlying units | "
        f"Γ {totals['gamma']:+,.4f} Δ/point | "
        f"Θ ₹{totals['theta']:+,.2f}/day | "
        f"Vega ₹{totals['vega']:+,.2f} per +1.00 vol"
    )


def _finish(lines: list[str]) -> str:
    lines = [str(line).replace("\r", "").replace("\n", " ") for line in lines]
    body = "\n".join(lines)
    if _FORBIDDEN.search(body):
        raise ValueError("formatter output contains forbidden execution language")
    if DISCLAIMER not in body:
        body = f"{body}\n\n{DISCLAIMER}"
    if len(body) <= MAX_TELEGRAM_CHARS:
        return body
    # Keep the disclaimer intact even when a future caller adds long dynamic
    # diagnostics.  The formatter is allowed to lose detail, never safety.
    keep = MAX_TELEGRAM_CHARS - len(DISCLAIMER) - 5
    return body[:keep].rstrip() + " ...\n\n" + DISCLAIMER


def _leg_line(leg: LegSpec) -> str:
    side_label = "BUY side (ask is the cost)" if leg.side == "BUY" else "SELL side (bid is the reference)"
    return (
        f"{leg.side} {leg.tradingsymbol} | {leg.opt_type} {leg.strike:,.2f} | "
        f"{leg.quantity} lot(s) | expiry {leg.expiry.isoformat()} | "
        f"{side_label}: bid {leg.bid:,.2f} points / ask {leg.ask:,.2f} points | "
        f"premium {leg.premium:,.2f} points"
    )


def format_protective_put_alert(plan: ProtectivePutPlan) -> str:
    """Format a protective-put review, including partial/over-coverage."""
    plan = _validate_plan(plan, ProtectivePutPlan, "protective_put_alert")
    if plan.protected_units <= 0 or plan.option_units <= 0:
        raise ValueError("plan has invalid protection coverage")
    ratio = plan.option_units / plan.protected_units
    if ratio < 1:
        coverage = f"PARTIAL COVERAGE — {plan.option_units:,}/{plan.protected_units:,} units ({ratio:.1%})"
    elif ratio > 1:
        coverage = f"OVER-COVERAGE — {plan.option_units:,}/{plan.protected_units:,} units ({ratio:.1%})"
    else:
        coverage = f"FULL COVERAGE — {plan.option_units:,}/{plan.protected_units:,} units"
    return _finish([
        f"🛡 Protective put review — {plan.underlying}",
        f"Live as of: {_as_of(plan.taken_at)} | underlying reference: {plan.spot:,.2f}",
        f"Expiry: {plan.expiry.isoformat()} | strike: {plan.put_strike:,.2f}",
        _leg_line(plan.legs[0]),
        coverage,
        f"Premium at risk: {_money(plan.max_loss, 'premium at risk')} | cost/reference notional: {_pct(plan.cost_as_pct, 'cost percentage')}",
        "Review whether this protection matches the confirmed holding and horizon; no automatic action is implied.",
        DISCLAIMER,
    ])


def format_collar_recommendation(
    plan: CollarPlan,
    *,
    existing_hedge_pct: Optional[float] = None,
    post_hedge_pct: Optional[float] = None,
) -> str:
    """Format a covered collar review and make its trade-offs explicit."""
    plan = _validate_plan(plan, CollarPlan, "collar_recommendation")
    if plan.protected_units <= 0 or plan.option_units <= 0 or len(plan.legs) != 2:
        raise ValueError("plan has invalid collar coverage")
    ratio = plan.option_units / plan.protected_units
    if ratio < 1:
        coverage = f"PARTIAL COVERAGE — {plan.option_units:,}/{plan.protected_units:,} units ({ratio:.1%}); call leg must be reviewed for coverage."
    elif ratio > 1:
        coverage = f"OVER-COVERAGE — {plan.option_units:,}/{plan.protected_units:,} units ({ratio:.1%})."
    else:
        coverage = f"FULL COVERAGE — {plan.option_units:,}/{plan.protected_units:,} units."
    lines = [
        f"🛡 Collar review — {plan.underlying}",
        f"Live as of: {_as_of(plan.taken_at)} | underlying reference: {plan.spot:,.2f}",
        f"Expiry: {plan.expiry.isoformat()} | put floor: {plan.put_strike:,.2f} | call cap: {plan.call_strike:,.2f}",
        _leg_line(plan.legs[0]),
        _leg_line(plan.legs[1]),
        coverage,
        f"Net debit/(credit): {_money(plan.net_debit, 'net debit')} | premium at risk / max loss: {_money(plan.max_loss, 'max loss')}",
        f"Downside floor distance: {plan.floored_downside:,.2f} points | maximum upside after premium: {_money(plan.capped_upside, 'capped upside')}.",
        "Review the protection floor against the confirmed holding; the call leg explicitly limits upside.",
    ]
    if existing_hedge_pct is not None:
        lines.append(f"Existing hedge percentage: {_pct(existing_hedge_pct, 'existing hedge percentage')}")
    if post_hedge_pct is not None:
        lines.append(f"Post-review hedge percentage: {_pct(post_hedge_pct, 'post hedge percentage')}")
    lines.append(DISCLAIMER)
    return _finish(lines)


def format_futures_hedge_size(
    plan: FuturesHedgeSizePlan,
    *,
    existing_hedge_pct: Optional[float] = None,
    post_hedge_pct: Optional[float] = None,
) -> str:
    """Format conservative whole-lot futures sizing and residual exposure."""
    plan = _validate_plan(plan, FuturesHedgeSizePlan, "futures_hedge_size")
    if plan.lots <= 0 or plan.notional <= 0 or plan.exposure <= 0:
        raise ValueError("plan has invalid futures sizing")
    if len(plan.legs) != 1 or plan.legs[0].opt_type != "FUT" or plan.legs[0].side != "SELL":
        raise ValueError("futures hedge plan must contain one short-futures review leg")
    residual_pct = plan.residual_delta / plan.exposure
    lines = [
        f"⚖ Futures hedge-size review — {plan.underlying}",
        f"Live as of: {_as_of(plan.taken_at)} | underlying reference: {plan.spot:,.2f}",
        _leg_line(plan.legs[0]),
        f"Whole-lot sizing: {plan.lots} lot(s) | live lot notional: {_money(plan.notional, 'lot notional')}",
        f"Target exposure reference: {_money(plan.exposure, 'exposure')} | rounded residual: {_money(plan.residual_delta, 'residual exposure')} ({residual_pct:.1%})",
        "Rounding is toward a smaller hedge; residual exposure remains and futures downside is market-dependent.",
        "Review the hedge ratio, liquidity and confirmed portfolio exposure before any human decision.",
    ]
    if existing_hedge_pct is not None:
        lines.append(f"Existing hedge percentage: {_pct(existing_hedge_pct, 'existing hedge percentage')}")
    if post_hedge_pct is not None:
        lines.append(f"Post-review hedge percentage: {_pct(post_hedge_pct, 'post hedge percentage')}")
    lines.append(DISCLAIMER)
    return _finish(lines)


def format_vix_hedge_alert(
    reading: VixRegimeReading,
    *,
    as_of: Optional[datetime] = None,
    observed_at: Optional[datetime] = None,
) -> str:
    """Format an informational volatility posture, never a trade signal."""
    if not isinstance(reading, VixRegimeReading):
        raise ValueError("expected VixRegimeReading")
    if as_of is not None and observed_at is not None and as_of != observed_at:
        raise ValueError("conflicting VIX timestamps")
    stamp = as_of if as_of is not None else observed_at
    if reading.regime not in {"UNAVAILABLE", "LOW", "NORMAL", "ELEVATED", "PANIC"}:
        raise ValueError("unknown VIX regime")
    if reading.automatic_action:
        raise ValueError("automatic VIX action is not renderable")
    if reading.spot is not None:
        _finite(reading.spot, "VIX spot")
    if reading.pct_change is not None:
        _finite(reading.pct_change, "VIX change")
    if reading.z_score is not None:
        _finite(reading.z_score, "VIX z-score")
    lines = [
        f"🌡 Volatility hedge posture — {reading.regime}",
        f"Live as of: {_as_of(stamp)} | data fresh: {'yes' if reading.data_fresh else 'no'}",
    ]
    if reading.spot is not None:
        lines.append(f"India VIX reference: {reading.spot:,.2f}")
    if reading.pct_change is not None:
        lines.append(f"Change versus supplied prior close: {reading.pct_change * 100:.1f}%")
    if reading.z_score is not None:
        lines.append(f"History z-score: {reading.z_score:.2f}")
    lines.append(f"Posture: {_reason(reading.posture)}")
    if reading.should_review_protection:
        lines.append("Review existing protection and hedge cost with a human; this is informational only.")
    else:
        lines.append("Continue monitoring; no hedge recommendation is made from this reading alone.")
    lines.append(DISCLAIMER)
    return _finish(lines)


def format_covered_call_recommendation(
    plan: CoveredCallPlan, *, context: Optional[str] = None,
) -> str:
    """Render a quote-backed covered-call review.

    ``net_premium`` and ``credit`` values produced by the strategy builders
    are rupees.  The leg premium is per-underlying-unit points, so both are
    displayed explicitly instead of silently treating one as the other.
    """
    plan = _validate_option_plan(
        plan, CoveredCallPlan, "covered_call_recommendation", (("SELL", "CE"),)
    )
    _require_numeric_fields(
        plan, ("covered_units", "option_units", "call_strike", "cap_return_pct",
               "yield_pct", "credit_points", "credit_rupees"),
    )
    if (
        plan.covered_units <= 0 or plan.option_units <= 0
        or plan.option_units > plan.covered_units
        or not math.isfinite(plan.call_strike) or plan.call_strike <= plan.spot
        or plan.legs[0].strike != plan.call_strike
        or not math.isclose(
            plan.net_premium, plan.legs[0].premium * plan.option_units,
            rel_tol=1e-7, abs_tol=1e-7,
        )
        or not math.isclose(plan.credit_points, plan.legs[0].premium, rel_tol=1e-7, abs_tol=1e-7)
        or not math.isclose(plan.credit_rupees, plan.net_premium, rel_tol=1e-7, abs_tol=1e-7)
        or not math.isclose(
            plan.max_profit,
            (plan.call_strike - plan.spot) * plan.option_units + plan.net_premium,
            rel_tol=1e-7, abs_tol=1e-7,
        )
        or not math.isclose(
            plan.max_loss, plan.spot * plan.option_units - plan.net_premium,
            rel_tol=1e-7, abs_tol=1e-7,
        )
    ):
        raise ValueError("covered-call coverage or strike is malformed")
    _finite(plan.cap_return_pct, "cap return")
    _finite(plan.yield_pct, "covered-call yield")
    dte = _dte(plan)
    leg = plan.legs[0]
    return _finish([
        f"📈 Covered-call review — {plan.underlying}",
        f"Live as of: {_as_of(plan.taken_at)} | spot reference: {plan.spot:,.2f} | DTE: {dte}",
        f"Call cap: {plan.call_strike:,.2f} | coverage: {plan.option_units:,}/{plan.covered_units:,} units",
        _leg_line(leg),
        _premium_line(leg.premium, plan.net_premium, "Premium received"),
        _option_greeks_line(plan.legs),
        f"Maximum profit to expiry: {_money(plan.max_profit, 'maximum profit')} | downside risk before zero: {_money(plan.max_loss, 'downside risk')}",
        f"Yield on covered notional: {_pct(plan.yield_pct, 'covered-call yield')} | cap return: {_pct(plan.cap_return_pct, 'cap return')}",
        _breakeven_line(plan),
        _context_line(plan, context),
        "Review the confirmed holding, assignment risk and capped upside with a human; no automatic action is implied.",
        DISCLAIMER,
    ])


def format_bull_put_spread(
    plan: BullPutSpreadPlan, *, context: Optional[str] = None,
) -> str:
    """Render a defined-risk bullish put-credit spread review."""
    plan = _validate_option_plan(
        plan, BullPutSpreadPlan, "bull_put_spread", (("SELL", "PE"), ("BUY", "PE"))
    )
    _require_numeric_fields(
        plan, ("short_strike", "long_strike", "width", "credit",
               "credit_points", "credit_rupees"),
    )
    short, long = plan.legs
    units = short.quantity * short.lot_size
    if (
        not _same_leg_size(plan.legs)
        or not plan.long_strike < plan.short_strike < plan.spot
        or short.strike != plan.short_strike or long.strike != plan.long_strike
            or not math.isclose(plan.width, plan.short_strike - plan.long_strike, rel_tol=1e-7, abs_tol=1e-7)
            or not math.isclose(plan.credit, plan.net_premium, rel_tol=1e-7, abs_tol=1e-7)
        or not math.isclose(plan.credit_points, _credit_points(plan.legs), rel_tol=1e-7, abs_tol=1e-7)
        or not math.isclose(plan.credit_rupees, plan.net_premium, rel_tol=1e-7, abs_tol=1e-7)
        or not math.isclose(plan.credit_points * short.quantity * short.lot_size, plan.net_premium, rel_tol=1e-7, abs_tol=1e-7)
        or not (0 < plan.credit_points < plan.width)
        or not math.isclose(plan.max_profit, plan.credit_points * units, rel_tol=1e-7, abs_tol=1e-7)
        or not math.isclose(plan.max_loss, (plan.width - plan.credit_points) * units, rel_tol=1e-7, abs_tol=1e-7)
    ):
        raise ValueError("bull-put leg geometry or risk metrics are malformed")
    dte = _dte(plan)
    return _finish([
        f"🟢 Bull-put spread review — {plan.underlying}",
        f"Live as of: {_as_of(plan.taken_at)} | spot reference: {plan.spot:,.2f} | DTE: {dte}",
        f"Short put: {plan.short_strike:,.2f} | long put: {plan.long_strike:,.2f} | width: {plan.width:,.2f} points",
        _leg_line(short), _leg_line(long),
        _premium_line(_credit_points(plan.legs), plan.credit, "Net credit received"),
        _option_greeks_line(plan.legs),
        f"Defined maximum loss: {_money(plan.max_loss, 'maximum loss')} | maximum profit: {_money(plan.max_profit, 'maximum profit')}",
        _breakeven_line(plan),
        _context_line(plan, context),
        "Review support, margin, liquidity and assignment risk before any human decision; no automatic action is implied.",
        DISCLAIMER,
    ])


def format_bear_call_spread(
    plan: BearCallSpreadPlan, *, context: Optional[str] = None,
) -> str:
    """Render a defined-risk bearish call-credit spread review."""
    plan = _validate_option_plan(
        plan, BearCallSpreadPlan, "bear_call_spread", (("SELL", "CE"), ("BUY", "CE"))
    )
    _require_numeric_fields(
        plan, ("short_strike", "long_strike", "width", "credit",
               "credit_points", "credit_rupees"),
    )
    short, long = plan.legs
    units = short.quantity * short.lot_size
    if (
        not _same_leg_size(plan.legs)
        or not plan.spot < plan.short_strike < plan.long_strike
        or short.strike != plan.short_strike or long.strike != plan.long_strike
            or not math.isclose(plan.width, plan.long_strike - plan.short_strike, rel_tol=1e-7, abs_tol=1e-7)
            or not math.isclose(plan.credit, plan.net_premium, rel_tol=1e-7, abs_tol=1e-7)
            or not math.isclose(plan.credit_points, _credit_points(plan.legs), rel_tol=1e-7, abs_tol=1e-7)
            or not math.isclose(plan.credit_rupees, plan.net_premium, rel_tol=1e-7, abs_tol=1e-7)
        or not math.isclose(plan.credit_points * short.quantity * short.lot_size, plan.net_premium, rel_tol=1e-7, abs_tol=1e-7)
        or not (0 < plan.credit_points < plan.width)
        or not math.isclose(plan.max_profit, plan.credit_points * units, rel_tol=1e-7, abs_tol=1e-7)
        or not math.isclose(plan.max_loss, (plan.width - plan.credit_points) * units, rel_tol=1e-7, abs_tol=1e-7)
    ):
        raise ValueError("bear-call leg geometry or risk metrics are malformed")
    dte = _dte(plan)
    return _finish([
        f"🔴 Bear-call spread review — {plan.underlying}",
        f"Live as of: {_as_of(plan.taken_at)} | spot reference: {plan.spot:,.2f} | DTE: {dte}",
        f"Short call: {plan.short_strike:,.2f} | long call: {plan.long_strike:,.2f} | width: {plan.width:,.2f} points",
        _leg_line(short), _leg_line(long),
        _premium_line(_credit_points(plan.legs), plan.credit, "Net credit received"),
        _option_greeks_line(plan.legs),
        f"Defined maximum loss: {_money(plan.max_loss, 'maximum loss')} | maximum profit: {_money(plan.max_profit, 'maximum profit')}",
        _breakeven_line(plan),
        _context_line(plan, context),
        "Review resistance, margin, liquidity and assignment risk before any human decision; no automatic action is implied.",
        DISCLAIMER,
    ])


def format_iron_condor(
    plan: IronCondorPlan, *, context: Optional[str] = None,
) -> str:
    """Render a four-leg, defined-risk iron-condor review."""
    plan = _validate_option_plan(
        plan, IronCondorPlan, "iron_condor",
        (("SELL", "PE"), ("BUY", "PE"), ("SELL", "CE"), ("BUY", "CE")),
    )
    _require_numeric_fields(
        plan, ("short_put_strike", "long_put_strike", "short_call_strike",
               "long_call_strike", "body_low", "body_high", "put_width",
               "call_width", "credit", "credit_points", "credit_rupees"),
    )
    sp, lp, sc, lc = plan.legs
    units = sp.quantity * sp.lot_size
    if (
        not _same_leg_size(plan.legs)
        or not plan.long_put_strike < plan.short_put_strike < plan.spot < plan.short_call_strike < plan.long_call_strike
        or (sp.strike, lp.strike, sc.strike, lc.strike)
        != (plan.short_put_strike, plan.long_put_strike, plan.short_call_strike, plan.long_call_strike)
        or not math.isclose(plan.put_width, plan.short_put_strike - plan.long_put_strike, rel_tol=1e-7, abs_tol=1e-7)
            or not math.isclose(plan.call_width, plan.long_call_strike - plan.short_call_strike, rel_tol=1e-7, abs_tol=1e-7)
            or not math.isclose(plan.credit, plan.net_premium, rel_tol=1e-7, abs_tol=1e-7)
            or not math.isclose(plan.credit_points, _credit_points(plan.legs), rel_tol=1e-7, abs_tol=1e-7)
            or not math.isclose(plan.credit_rupees, plan.net_premium, rel_tol=1e-7, abs_tol=1e-7)
            or not math.isclose(plan.credit_points * sp.quantity * sp.lot_size, plan.net_premium, rel_tol=1e-7, abs_tol=1e-7)
            or not (0 < plan.credit_points < min(plan.put_width, plan.call_width))
            or not math.isclose(plan.max_profit, plan.credit_points * units, rel_tol=1e-7, abs_tol=1e-7)
            or not math.isclose(plan.max_loss, (max(plan.put_width, plan.call_width) - plan.credit_points) * units, rel_tol=1e-7, abs_tol=1e-7)
    ):
        raise ValueError("iron-condor leg geometry or risk metrics are malformed")
    dte = _dte(plan)
    return _finish([
        f"🟡 Iron-condor review — {plan.underlying}",
        f"Live as of: {_as_of(plan.taken_at)} | spot reference: {plan.spot:,.2f} | DTE: {dte}",
        f"Put body/wings: {plan.short_put_strike:,.2f}/{plan.long_put_strike:,.2f} | Call body/wings: {plan.short_call_strike:,.2f}/{plan.long_call_strike:,.2f}",
        _leg_line(sp), _leg_line(lp), _leg_line(sc), _leg_line(lc),
        _premium_line(_credit_points(plan.legs), plan.credit, "Net credit received"),
        _option_greeks_line(plan.legs),
        f"Defined maximum loss: {_money(plan.max_loss, 'maximum loss')} | maximum profit: {_money(plan.max_profit, 'maximum profit')}",
        _breakeven_line(plan),
        _context_line(plan, context),
        "Review range stability, event risk, margin, liquidity and both wings before any human decision; no automatic action is implied.",
        DISCLAIMER,
    ])


def format_delta_hedge_rebalance(
    plan: DeltaRebalancePlan, *, context: Optional[str] = None,
) -> str:
    """Render a whole-lot futures delta-rebalance review."""
    plan = _validate_plan(plan, DeltaRebalancePlan, "delta_hedge_rebalance")
    _require_numeric_fields(
        plan, ("lots", "current_net_delta", "target_net_delta", "residual_delta"),
    )
    if len(plan.legs) != 1:
        raise ValueError("delta-rebalance plan must contain exactly one leg")
    leg = plan.legs[0]
    if (
        leg.opt_type != "FUT" or leg.side not in {"BUY", "SELL"}
        or plan.side != leg.side or plan.lots <= 0 or plan.lots != leg.quantity
        or not all(math.isfinite(float(value)) for value in (
            plan.current_net_delta, plan.target_net_delta, plan.residual_delta,
        ))
        or abs(plan.residual_delta) >= abs(plan.current_net_delta - plan.target_net_delta)
        or _finite(plan.net_premium, "cash premium") != 0
        or not math.isinf(_finite(plan.max_profit, "maximum profit", allow_inf=True))
        or not math.isinf(_finite(plan.max_loss, "maximum loss", allow_inf=True))
    ):
        raise ValueError("delta-rebalance plan is malformed or does not improve exposure")
    expected_side = "BUY" if plan.target_net_delta > plan.current_net_delta else "SELL"
    if plan.side != expected_side:
        raise ValueError("delta-rebalance side does not move toward target")
    dte = _dte(plan)
    return _finish([
        f"⚖ Delta-rebalance review — {plan.underlying}",
        f"Live as of: {_as_of(plan.taken_at)} | spot reference: {plan.spot:,.2f} | DTE: {dte}",
        _leg_line(leg),
        f"Net delta: {plan.current_net_delta:+,.4f} → target {plan.target_net_delta:+,.4f} | residual: {plan.residual_delta:+,.4f} lot-equivalent",
        f"Whole-lot adjustment: {plan.side} {plan.lots} lot(s) | option premium: n/a (futures) | cash premium: {_money(plan.net_premium, 'cash premium')}",
        "Futures loss is market-dependent and not bounded by this review; whole-lot rounding leaves the stated residual.",
        _context_line(plan, context),
        "Review the reconciled portfolio delta, margin and liquidity before any human decision; no automatic action is implied.",
        DISCLAIMER,
    ])


def format_long_vol_review(plan: LongVolPlan, *, context: Optional[str] = None) -> str:
    """Render a bounded-loss straddle or strangle without promising expansion."""
    if plan.strategy not in {"long_straddle", "long_strangle"}:
        raise ValueError("unsupported long-vol strategy")
    plan = _validate_plan(plan, LongVolPlan, plan.strategy)
    if len(plan.legs) != 2 or any(leg.side != "BUY" for leg in plan.legs):
        raise ValueError("long-vol plan must have two bought legs")
    if {leg.opt_type for leg in plan.legs} != {"CE", "PE"}:
        raise ValueError("long-vol plan requires one put and one call")
    debit = sum(leg.ask * leg.quantity * leg.lot_size for leg in plan.legs)
    if (not math.isclose(plan.max_loss, debit, rel_tol=1e-7)
            or not math.isclose(plan.net_premium, -debit, rel_tol=1e-7)
            or not math.isclose(plan.debit_rupees, debit, rel_tol=1e-7)):
        raise ValueError("long-vol debit or bounded loss is malformed")
    label = "Long-straddle" if plan.strategy == "long_straddle" else "Long-strangle"
    return _finish([
        f"⚡ {label} hedge review — {plan.underlying}",
        f"Live as of: {_as_of(plan.taken_at)} | spot reference: {plan.spot:,.2f} | DTE: {_dte(plan)}",
        *(_leg_line(leg) for leg in plan.legs),
        _premium_line(plan.debit_points, plan.debit_rupees, "Maximum premium at risk"),
        _option_greeks_line(plan.legs), _breakeven_line(plan),
        _context_line(plan, context),
        "Volatility expansion must exceed theta decay and both bid/ask costs; no automatic action is implied.",
        DISCLAIMER,
    ])


def format_iron_butterfly(plan: IronButterflyPlan, *, context: Optional[str] = None) -> str:
    plan = _validate_option_plan(
        plan, IronButterflyPlan, "iron_butterfly",
        (("SELL", "PE"), ("SELL", "CE"), ("BUY", "PE"), ("BUY", "CE")),
    )
    if (len(plan.legs) != 4 or not _same_leg_size(plan.legs)
            or not plan.put_wing < plan.body_strike < plan.call_wing
            or not math.isclose(plan.body_strike-plan.put_wing, plan.width)
            or not math.isclose(plan.call_wing-plan.body_strike, plan.width)):
        raise ValueError("iron-butterfly geometry is malformed")
    return _finish([
        f"🦋 Iron-butterfly hedge review — {plan.underlying}",
        f"Live as of: {_as_of(plan.taken_at)} | spot reference: {plan.spot:,.2f} | DTE: {_dte(plan)}",
        *(_leg_line(leg) for leg in plan.legs),
        _premium_line(plan.credit_points, plan.credit_rupees, "Net credit received"),
        _option_greeks_line(plan.legs),
        f"Defined maximum loss: {_money(plan.max_loss, 'maximum loss')} | maximum profit: {_money(plan.max_profit, 'maximum profit')}",
        _breakeven_line(plan), _context_line(plan, context),
        "High ATM gamma can change this risk quickly; no automatic action is implied.", DISCLAIMER,
    ])


def format_calendar_diary_spread(plan: CalendarSpreadPlan, *, context: Optional[str] = None) -> str:
    if type(plan) is not CalendarSpreadPlan or plan.strategy != "calendar_diary_spread" or not plan.advisory_only:
        raise ValueError("expected advisory CalendarSpreadPlan")
    if len(plan.legs) != 2 or plan.legs[0].side != "SELL" or plan.legs[1].side != "BUY":
        raise ValueError("calendar topology is malformed")
    front, back = plan.legs
    if (front.strike != back.strike or front.expiry != plan.expiry
            or back.expiry != plan.back_expiry or back.expiry <= front.expiry
            or front.opt_type != back.opt_type or front.lot_size != back.lot_size
            or front.quantity != back.quantity):
        raise ValueError("calendar contracts are not the same-strike term pair")
    debit = (back.ask-front.bid)*front.quantity*front.lot_size
    if debit <= 0 or not math.isclose(plan.max_loss, debit, rel_tol=1e-7):
        raise ValueError("calendar debit is malformed")
    return _finish([
        f"📅 Calendar-spread hedge review — {plan.underlying}",
        f"Live as of: {_as_of(plan.taken_at)} | strike: {plan.strike:,.2f}",
        _leg_line(front), _leg_line(back),
        _premium_line(plan.debit_points, plan.debit_rupees, "Maximum debit at risk"),
        _option_greeks_line(plan.legs), _context_line(plan, context),
        "Term-structure and front-expiry gamma can move independently; no automatic action is implied.", DISCLAIMER,
    ])


def format_ratio_spread(plan: RatioSpreadPlan, *, context: Optional[str] = None) -> str:
    plan = _validate_plan(plan, RatioSpreadPlan, "ratio_spread")
    if len(plan.legs) != 2 or plan.tail_risk != "UNBOUNDED" or not math.isinf(plan.max_loss):
        raise ValueError("ratio spread must disclose unbounded tail risk")
    return _finish([
        f"⚠ Ratio-spread research review — {plan.underlying}",
        f"Live as of: {_as_of(plan.taken_at)} | DTE: {_dte(plan)}",
        *(_leg_line(leg) for leg in plan.legs),
        "TAIL RISK: UNBOUNDED beyond the short strike; runtime emission is disabled.",
        _context_line(plan, context), DISCLAIMER,
    ])


def format_gamma_exposure_alert(underlying: str, exposure: float, hours_to_expiry: float, *, as_of: datetime) -> str:
    exposure = _finite(exposure, "gamma exposure")
    hours_to_expiry = _finite(hours_to_expiry, "hours to expiry")
    if hours_to_expiry < 0:
        raise ValueError("hours to expiry cannot be negative")
    return _finish([f"⚠ Gamma-exposure review — {_reason(underlying).upper()}",
        f"Live as of: {_as_of(as_of)} | hours to expiry: {hours_to_expiry:.1f}",
        f"Reconciled-book gamma exposure: ₹{exposure:+,.2f} per 1% underlying move",
        "Review gap and rebalance risk with a human; no automatic action is implied.", DISCLAIMER])


def format_earnings_event_hedge(plan: LongVolPlan, event_label: str, *, context: Optional[str] = None) -> str:
    text = format_long_vol_review(plan, context=context)
    return _finish([f"📈 Earnings-event hedge — {_reason(event_label)}", text])


def format_portfolio_corruption_overlay(plan: FuturesHedgeSizePlan, correlation: float, *, context: Optional[str] = None) -> str:
    correlation = _finite(correlation, "correlation")
    if not -1 <= correlation <= 1:
        raise ValueError("correlation must be within [-1, 1]")
    base = format_futures_hedge_size(plan)
    return _finish([f"🧰 Portfolio-correlation overlay — {plan.underlying}",
                    f"Observed portfolio correlation: {correlation:.2f}",
                    _context_line(plan, context), base])


def format_no_recommendation(
    underlying: str = "",
    reason: str = "data unavailable",
    *,
    as_of: Optional[datetime] = None,
) -> str:
    """Render a safe no-trade/data-unavailable outcome."""
    name = str(underlying).strip().upper() or "UNDERLYING UNAVAILABLE"
    return _finish([
        f"ℹ Hedge review — {name}",
        f"Live as of: {_as_of(as_of)}",
        f"No recommendation: {_reason(reason)}.",
        "No quote-backed hedge plan was produced; wait for reconciled holdings and usable market data.",
        DISCLAIMER,
    ])


format_data_unavailable = format_no_recommendation

__all__ = [
    "MAX_TELEGRAM_CHARS", "DISCLAIMER", "format_protective_put_alert",
    "format_collar_recommendation", "format_futures_hedge_size",
    "format_vix_hedge_alert", "format_no_recommendation",
    "format_data_unavailable", "format_covered_call_recommendation",
    "format_bull_put_spread", "format_bear_call_spread", "format_iron_condor",
    "format_delta_hedge_rebalance",
    "format_long_vol_review", "format_iron_butterfly",
    "format_calendar_diary_spread", "format_ratio_spread",
    "format_gamma_exposure_alert", "format_earnings_event_hedge",
    "format_portfolio_corruption_overlay",
]
