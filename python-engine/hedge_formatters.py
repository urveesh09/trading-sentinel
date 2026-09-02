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
from typing import Optional

from partner_content import DISCLAIMER
from hedge_analytics import VixRegimeReading
from hedge_strategies import (
    CollarPlan,
    FuturesHedgeSizePlan,
    HedgePlan,
    LegSpec,
    ProtectivePutPlan,
)

MAX_TELEGRAM_CHARS = 4096
_FORBIDDEN = re.compile(r"execute|buy\s+now|sell\s+now|guaranteed", re.IGNORECASE)


def _finite(value: object, label: str, *, allow_inf: bool = False) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if math.isnan(result) or (not allow_inf and not math.isfinite(result)):
        raise ValueError(f"{label} must be finite")
    return result


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
    if not str(leg.tradingsymbol).strip() or leg.contract_token <= 0:
        raise ValueError("plan leg is missing the live contract identity")
    if _date(leg.expiry, "leg expiry") != expected_expiry:
        raise ValueError("leg expiry does not match plan expiry")
    bid = _finite(leg.bid, "leg bid")
    ask = _finite(leg.ask, "leg ask")
    premium = _finite(leg.premium, "leg premium")
    if bid <= 0 or ask <= 0 or ask < bid or premium <= 0:
        raise ValueError("plan leg does not contain a valid two-sided quote")
    expected = ask if leg.side == "BUY" else bid
    if not math.isclose(premium, expected, rel_tol=1e-7, abs_tol=1e-7):
        raise ValueError("plan leg premium is not the executable side of its quote")
    return leg


def _validate_plan(plan: object, expected_type: type, strategy: str) -> HedgePlan:
    if not isinstance(plan, expected_type):
        raise ValueError(f"expected {expected_type.__name__}")
    if not plan.advisory_only:
        raise ValueError("non-advisory plan rejected")
    if plan.strategy != strategy or not str(plan.underlying).strip():
        raise ValueError("plan strategy/underlying is malformed")
    _finite(plan.spot, "plan spot")
    if plan.spot <= 0:
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
        f"{side_label}: bid ₹{leg.bid:,.2f} / ask ₹{leg.ask:,.2f} | "
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
    "format_data_unavailable",
]
