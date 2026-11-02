"""The earned-lot rules. Pure arithmetic: no data access, no forecast, nothing here reads a future bar."""
from __future__ import annotations

import math
from typing import Optional


def _num(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def side_of(direction: str) -> int:
    if direction == "LONG":
        return 1
    if direction == "SHORT":
        return -1
    raise ValueError(direction)


def progress_r(direction: str, entry: float, risk_points: float, price: float) -> Optional[float]:
    """How far the future has moved in the trade's favour, in units of the initial stop distance."""
    if not all(_num(v) for v in (entry, risk_points, price)) or risk_points <= 0 or price <= 0:
        return None
    return side_of(direction) * (price - entry) / risk_points


def level_at(direction: str, entry: float, risk_points: float, level_r: float) -> float:
    """The future's price at level_r from entry, in the trade's favour."""
    return entry + side_of(direction) * level_r * risk_points


def child_risk(ask: float, bid: float, reference_premium: float, stop_pct: float, qty: int) -> float:
    """Planned loss on an earned lot: its 25% backstop, or the premium given back to the previous step plus the spread, whichever is smaller."""
    giveback = max(ask - reference_premium, 0.0) + max(ask - bid, 0.0)
    return min(ask * stop_pct, giveback) * qty


def parent_risk(entry_premium: float, stop_pct: float, qty: int, locked: bool) -> float:
    """The first lot's planned loss, on the planner's own 25% convention. Nothing once its trail stop is beyond entry."""
    return 0.0 if locked else entry_premium * stop_pct * qty


def trail_locked(direction: str, entry: float, trail_active: object, trail_stop: Optional[float]) -> bool:
    return bool(trail_active) and _num(trail_stop) and side_of(direction) * (trail_stop - entry) > 0


def budget(equity: float, risk_pct: float, max_rupees: float, multiplier: float) -> float:
    """The planner's risk budget: the same two limits, the same scale."""
    scale = max(0.0, float(multiplier))
    return min(equity * risk_pct * scale, max_rupees * scale)


def child_out(direction: str, future: float, level: float, bid: float, premium_stop: float) -> Optional[str]:
    """Why an earned lot leaves on its own, if it does. The index level comes first in the name when both are true."""
    if side_of(direction) * (future - level) <= 0:
        return "n10_level"
    if bid <= premium_stop:
        return "n10_backstop"
    return None


def extra_cost(cost: Optional[list], lots: int) -> float:
    a, b = (200.0, 5.0) if cost is None else cost
    return (a + b * lots) * lots
