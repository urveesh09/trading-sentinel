"""Pure single-leg F&O exit ladder shared by live management and research (S6b).

Extracted verbatim from ``fno_orchestrator`` so the paper/live manager and the
read-only exit experiments evaluate *the same* rules.  No I/O, logging or
database access happens here: the caller persists trail state, logs the
returned facts and performs any exit.  Ladder order (unchanged):

0. hard flat (caller-supplied flag) -- unconditional;
with a futures quote:
1. underlying stop, 2. trailing stop after the target armed it,
3. premium backstop on the exit basis, 4. profit lock (when enabled),
5. time stop (only before the trail is armed; optionally deferred while the
   premium is in profit);
without a futures quote: the premium backstop and the profit lock can fire.

Profit lock [FNO-PROFIT-LOCK 2026-10-07]: once the option's best exit basis
(bid, else LTP) has been ``FNO_PROFIT_LOCK_ARM_R`` premium-R above entry
(premium-R = entry premium x FNO_STOP_PREMIUM_PCT), the position may not fall
back below a floor of entry + ``FNO_PROFIT_LOCK_FLOOR_R`` premium-R. With
``FNO_PROFIT_LOCK_KEEP_FRACTION`` > 0 the floor also ratchets to keep that
fraction of the best gain. Archived sessions showed 5 of 9 trades that were
+Rs 700-1,560 in profit before giving it all back on the time stop.
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
    best_premium: Optional[float] = None
    profit_lock_floor: Optional[float] = None
    entry_time_unparseable: bool = False
    time_stop_deferred: Optional[dict] = None


def live_single_leg_exit_params(settings: Any) -> dict:
    """The configuration values the live ladder reads, as an explicit mapping."""
    return {
        "FNO_TRAIL_ATR_MULT": float(settings.FNO_TRAIL_ATR_MULT),
        "FNO_TIME_STOP_MIN": float(settings.FNO_TIME_STOP_MIN),
        "FNO_TIME_STOP_MIN_R": float(settings.FNO_TIME_STOP_MIN_R),
        "FNO_TIME_STOP_RESPECTS_PREMIUM": bool(settings.FNO_TIME_STOP_RESPECTS_PREMIUM),
        "FNO_STOP_PREMIUM_PCT": float(settings.FNO_STOP_PREMIUM_PCT),
        "FNO_PROFIT_LOCK_ENABLED": bool(settings.FNO_PROFIT_LOCK_ENABLED),
        "FNO_PROFIT_LOCK_ARM_R": float(settings.FNO_PROFIT_LOCK_ARM_R),
        "FNO_PROFIT_LOCK_FLOOR_R": float(settings.FNO_PROFIT_LOCK_FLOOR_R),
        "FNO_PROFIT_LOCK_KEEP_FRACTION": float(settings.FNO_PROFIT_LOCK_KEEP_FRACTION),
    }


def profit_lock_floor(entry_premium: float, best_premium: Optional[float],
                      params: Mapping[str, Any]) -> Optional[float]:
    """The premium floor once the lock is armed, else ``None`` (pure)."""
    if not params.get("FNO_PROFIT_LOCK_ENABLED") or not entry_premium or entry_premium <= 0:
        return None
    if best_premium is None:
        return None
    risk_unit = entry_premium * float(params.get("FNO_STOP_PREMIUM_PCT", 0.25))
    if risk_unit <= 0:
        return None
    gain = best_premium - entry_premium
    if gain < float(params.get("FNO_PROFIT_LOCK_ARM_R", 0.25)) * risk_unit:
        return None
    floor = entry_premium + float(params.get("FNO_PROFIT_LOCK_FLOOR_R", 0.1)) * risk_unit
    keep = float(params.get("FNO_PROFIT_LOCK_KEEP_FRACTION", 0.0))
    if keep > 0:
        floor = max(floor, entry_premium + keep * gain)
    return floor


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
    prior_best_premium = getattr(p, "best_premium", None)
    best_premium = prior_best_premium
    if exit_px_basis > 0:
        best_premium = exit_px_basis if best_premium is None else max(best_premium, exit_px_basis)
    # The floor comes from the best seen BEFORE this sample, so one sample
    # cannot both arm the lock and fire it.
    floor = profit_lock_floor(p.entry_premium, prior_best_premium, params)
    locked = floor is not None and 0 < exit_px_basis <= floor
    if hard_flat:
        return SingleLegExitDecision("hard_flat_1510", bool(p.trail_active),
                                     p.trail_stop_underlying, p.best_underlying, False,
                                     best_premium=best_premium, profit_lock_floor=floor)
    if fut_price is None or not fut_price > 0:
        # No futures quote this tick: only the premium backstop and the
        # premium-based profit lock can still protect the position.
        reason = ("premium_backstop" if exit_px_basis > 0 and exit_px_basis <= p.premium_stop
                  else "profit_lock" if locked else "")
        return SingleLegExitDecision(reason, bool(p.trail_active),
                                     p.trail_stop_underlying, p.best_underlying, False,
                                     best_premium=best_premium, profit_lock_floor=floor)

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
    elif locked:
        reason = "profit_lock"
    elif timed_out:
        reason = "time_stop"
    else:
        reason = ""
    return SingleLegExitDecision(
        reason, trail_active, trail_stop, best, persist_trail=not reason,
        trail_newly_armed=newly_armed, entry_time_unparseable=unparseable,
        time_stop_deferred=deferred, best_premium=best_premium, profit_lock_floor=floor,
    )


__all__ = ["SingleLegExitDecision", "evaluate_single_leg_exit", "live_single_leg_exit_params",
           "profit_lock_floor"]
