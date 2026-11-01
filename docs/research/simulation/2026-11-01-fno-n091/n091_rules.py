"""Cash-budget rules for long-option research; no data access or direction forecast."""
from __future__ import annotations

import math
from dataclasses import dataclass


def finite_nonnegative(value: object) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0)


@dataclass(frozen=True)
class Budget:
    anchor: float
    peak: float
    floor: float


def advance(state: Budget, equity: float, open_reserve: float, drawdown: float) -> Budget:
    """Raise a floor only when it is backed by cash, including already-open risk."""
    if not all(finite_nonnegative(v) for v in (*state.__dict__.values(), equity, open_reserve, drawdown)) or drawdown >= 1:
        raise ValueError("invalid budget inputs")
    if state.floor > equity - open_reserve + 1e-7:
        raise ValueError("previous funded floor was breached")
    peak = max(state.peak, equity)
    floor = max(state.floor, min((1 - drawdown) * peak, equity - open_reserve))
    return Budget(state.anchor, peak, floor)


def affordable(native_lots: int, equity: float, floor: float, open_reserve: float,
               reserves: dict[int, float]) -> int:
    """Largest whole native-sized lot count supported by a full-loss cash reserve."""
    if isinstance(native_lots, bool) or not isinstance(native_lots, int) or native_lots < 0:
        raise ValueError("invalid native lot count")
    if not all(finite_nonnegative(v) for v in (equity, floor, open_reserve)):
        return 0
    for lots in range(native_lots, 0, -1):
        risk = reserves.get(lots)
        if finite_nonnegative(risk) and floor + open_reserve + risk <= equity + 1e-8:
            return lots
    return 0
