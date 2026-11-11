"""[N13 2026-11-11] The paper N11 book's profit lock on the clock it was researched on: one look a minute.

Every N11 study replays one-minute closes, and the one-lot paper record (``fno_n11.paper_tick``) looks at most every
55 seconds. The live loop looks every 10 seconds, so its lock saw higher peaks and shorter dips than anything it was
researched on. The lock sold 6 of 32 paper trades from Oct 1 to Nov 11, against 16 of 209 in the five researched
NIFTY windows. On Nov 5 it sold an OR20 call at 12:03 on a 10-second dip under a floor set by a 10-second peak, while
the record held the same contract to 14:22 (+Rs 1,029 against +Rs 6,095). docs/research/simulation/2026-11-11-fno-n13.

``FNO_PROFIT_LOCK_LOOK_SEC`` > 0 in a position's exit parameters: the lock reads only looks at least that far apart.
On those looks it keeps its best and checks its floor, and fires on the first look under the floor (the researched
rule; no confirmation). Between them, the lock neither moves its best nor sells. The stops, the trail, the time stop,
the premium backstop and the 15:10 flat still read every look. 0 or absent: ``evaluate_single_leg_exit`` unchanged.
The ladder itself (``fno_exit_rules``) is untouched, and many frozen studies bind it.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any, Mapping, Optional

import fno_exit_rules as _rules
from fno_exit_rules import SingleLegExitDecision, profit_lock_floor

LOOK_KEY = "FNO_PROFIT_LOCK_LOOK_SEC"


def applies(source: str, paper_mode: bool, position: Any) -> bool:
    """On for an N11 paper position (a first lot or an earned lot) while FNO_N13_LOCK_LOOK_SEC > 0; never real money."""
    import fno_n11
    from config import settings
    from fno_models import FnoSource
    return (float(getattr(settings, "FNO_N13_LOCK_LOOK_SEC", 0.0) or 0.0) > 0 and source == FnoSource.FNO_PAPER.value
            and bool(paper_mode) and (fno_n11.is_parent(position) or getattr(position, "strategy", None) == fno_n11.ADD))


def look_sec(params: Mapping[str, Any]) -> float:
    try:
        return max(0.0, float(params.get(LOOK_KEY) or 0.0))
    except (TypeError, ValueError):
        return 0.0


def is_lock_look(params: Mapping[str, Any], now_ist: datetime, lock_look_at: Optional[datetime]) -> bool:
    """True when the lock may read this look: every look when off, else the first look or one >= the gap after the last."""
    gap = look_sec(params)
    if gap <= 0 or lock_look_at is None:
        return True
    elapsed = (now_ist - lock_look_at).total_seconds()
    return elapsed >= gap or elapsed < 0          # a clock that went back starts the minute again


def evaluate(position: Any, *, now_ist: datetime, fut_price: Optional[float], exit_px_basis: float, hard_flat: bool,
             params: Mapping[str, Any], lock_breach_since: Optional[datetime] = None,
             lock_look_at: Optional[datetime] = None) -> tuple[SingleLegExitDecision, Optional[datetime]]:
    """(the ladder's decision, the lock's last look). With the cadence off it is ``evaluate_single_leg_exit`` exactly."""
    if look_sec(params) <= 0:
        return (_rules.evaluate_single_leg_exit(position, now_ist=now_ist, fut_price=fut_price, exit_px_basis=exit_px_basis,
                                         hard_flat=hard_flat, params=params, lock_breach_since=lock_breach_since),
                lock_look_at)
    if is_lock_look(params, now_ist, lock_look_at):
        decision = _rules.evaluate_single_leg_exit(position, now_ist=now_ist, fut_price=fut_price,
                                            exit_px_basis=exit_px_basis, hard_flat=hard_flat,
                                            params={**params, "FNO_PROFIT_LOCK_CONFIRM_SEC": 0.0},
                                            lock_breach_since=None)
        return replace(decision, lock_breach_since=None), now_ist
    prior_best = getattr(position, "best_premium", None)
    decision = _rules.evaluate_single_leg_exit(position, now_ist=now_ist, fut_price=fut_price, exit_px_basis=exit_px_basis,
                                        hard_flat=hard_flat, params={**params, "FNO_PROFIT_LOCK_ENABLED": False},
                                        lock_breach_since=None)
    floor = profit_lock_floor(getattr(position, "entry_premium", 0.0), prior_best, params)
    return replace(decision, best_premium=prior_best, profit_lock_floor=floor, lock_breach_since=None), lock_look_at


__all__ = ["LOOK_KEY", "applies", "evaluate", "is_lock_look", "look_sec"]
