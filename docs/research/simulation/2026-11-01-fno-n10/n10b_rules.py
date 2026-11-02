"""WATCH: how a funded floor may come down, by small bounded slices, on paper evidence. Pure arithmetic."""
from __future__ import annotations

from typing import Optional, Sequence


def evidence_ok(prior_nets: Sequence[float], closed_since_last_slice: int, need: int) -> bool:
    """The last `need` paper trades made money together, and that many have closed since the last slice, so evidence is never spent twice."""
    return len(prior_nets) >= need and closed_since_last_slice >= need and sum(prior_nets[-need:]) > 0


def lowered_floor(floor: float, best_equity: float, slice_share: float, deepest_share: float) -> Optional[float]:
    """The floor after one slice, never under deepest_share of the best closed equity. None when there is nothing left to give."""
    if not 0 < slice_share < 1 or not 0 < deepest_share < 1:
        raise ValueError("invalid shares")
    target = max(floor - slice_share * best_equity, deepest_share * best_equity)
    return target if target < floor - 1e-9 else None
