"""Pure single-leg F&O exit ladder shared by live management and research (S6b).

Extracted verbatim from ``fno_orchestrator`` so the paper/live manager and the
read-only exit experiments evaluate *the same* rules.  No I/O, logging or
database access happens here: the caller persists trail state, logs the
returned facts and performs any exit.  Ladder order (unchanged):

0. hard flat (caller-supplied flag) -- unconditional;
with a futures quote:
1. underlying stop, 2. trailing stop after the target armed it,
3. premium backstop on the exit basis, 4. time stop (only before the trail is
   armed; optionally deferred while the premium is in profit);
without a futures quote: only the premium backstop can fire.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional

import pytz

IST = pytz.timezone("Asia/Kolkata")


@dataclass(frozen=True)
class SingleLegExitDecision:
    exit_reason: str
    trail_active: bool
    trail_stop: Optional[float]
    best_underlying: Optional[float]
    persist_trail: bool
    trail_newly_armed: bool = False
    entry_time_unparseable: bool = False
    time_stop_deferred: Optional[dict] = None


def live_single_leg_exit_params(settings: Any) -> dict:
    """The configuration values the live ladder reads, as an explicit mapping."""
    return {
        "FNO_TRAIL_ATR_MULT": float(settings.FNO_TRAIL_ATR_MULT),
        "FNO_TIME_STOP_MIN": float(settings.FNO_TIME_STOP_MIN),
        "FNO_TIME_STOP_MIN_R": float(settings.FNO_TIME_STOP_MIN_R),
        "FNO_TIME_STOP_RESPECTS_PREMIUM": bool(settings.FNO_TIME_STOP_RESPECTS_PREMIUM),
    }


def _age_minutes(entry_time: Any, now_ist: datetime) -> tuple[float, bool]:
    try:
        entry_dt = datetime.fromisoformat(entry_time)
        if entry_dt.tzinfo is None:
            entry_dt = IST.localize(entry_dt)
        return (now_ist - entry_dt).total_seconds() / 60.0, False
    except (ValueError, TypeError):
        # The caller logs this loudly: the time stop is defeated for the row.
        return 0.0, True


def evaluate_single_leg_exit(
    position: Any, *, now_ist: datetime, fut_price: Optional[float],
    exit_px_basis: float, hard_flat: bool, params: Mapping[str, Any],
) -> SingleLegExitDecision:
    """Return the exit reason (or ``""``) and the trail state to persist.

    ``position`` exposes the ``fno_positions`` row attributes used by the
    ladder (direction, entry/stop/target underlying, atr_at_entry,
    entry_premium, premium_stop, entry_time and trail fields).
    """
    p = position
    if hard_flat:
        return SingleLegExitDecision("hard_flat_1510", bool(p.trail_active),
                                     p.trail_stop_underlying, p.best_underlying, False)
    if fut_price is None or not fut_price > 0:
        # No futures quote this tick: only the premium backstop can still
        # protect the position.
        reason = "premium_backstop" if exit_px_basis > 0 and exit_px_basis <= p.premium_stop else ""
        return SingleLegExitDecision(reason, bool(p.trail_active),
                                     p.trail_stop_underlying, p.best_underlying, False)

    long_view = p.direction == "LONG"
    best = p.best_underlying or p.entry_underlying
    best = max(best, fut_price) if long_view else min(best, fut_price)
    trail_active = bool(p.trail_active)
    trail_stop = p.trail_stop_underlying
    newly_armed = False

    target_hit = fut_price >= p.target_underlying if long_view else fut_price <= p.target_underlying
    if target_hit and not trail_active:
        trail_active = True
        newly_armed = True
    if trail_active:
        dist = float(params["FNO_TRAIL_ATR_MULT"]) * (p.atr_at_entry or 0.0)
        new_trail = best - dist if long_view else best + dist
        if trail_stop is None:
            trail_stop = new_trail
        else:
            trail_stop = max(trail_stop, new_trail) if long_view else min(trail_stop, new_trail)

    stopped = fut_price <= p.stop_underlying if long_view else fut_price >= p.stop_underlying
    trailed = (trail_active and trail_stop is not None
               and (fut_price <= trail_stop if long_view else fut_price >= trail_stop))
    premium_stopped = exit_px_basis > 0 and exit_px_basis <= p.premium_stop
    timed_out = False
    unparseable = False
    deferred = None
    if not trail_active:
        age_min, unparseable = _age_minutes(p.entry_time, now_ist)
        if age_min >= float(params["FNO_TIME_STOP_MIN"]):
            r_points = abs(p.entry_underlying - p.stop_underlying)
            progress = fut_price - p.entry_underlying if long_view else p.entry_underlying - fut_price
            needed = float(params["FNO_TIME_STOP_MIN_R"]) * r_points
            if progress < needed:
                timed_out = True
            if timed_out and params["FNO_TIME_STOP_RESPECTS_PREMIUM"]:
                premium_pnl_per_lot = exit_px_basis - p.entry_premium
                if p.direction == "SHORT":
                    premium_pnl_per_lot = -premium_pnl_per_lot
                if exit_px_basis > 0 and premium_pnl_per_lot > 0:
                    timed_out = False
                    deferred = {"age_min": age_min, "underlying_progress": progress,
                                "needed": needed, "premium_pnl_per_unit": premium_pnl_per_lot}

    if stopped:
        reason = "underlying_stop"
    elif trailed:
        reason = "trail_stop"
    elif premium_stopped:
        reason = "premium_backstop"
    elif timed_out:
        reason = "time_stop"
    else:
        reason = ""
    return SingleLegExitDecision(
        reason, trail_active, trail_stop, best, persist_trail=not reason,
        trail_newly_armed=newly_armed, entry_time_unparseable=unparseable,
        time_stop_deferred=deferred,
    )


__all__ = ["SingleLegExitDecision", "evaluate_single_leg_exit", "live_single_leg_exit_params"]
