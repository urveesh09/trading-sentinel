"""N08's rules as pure functions: no market data access, no I/O, nothing about any specific date.

Each one answers a question using only what is known at that moment. The lab applies them; tests/test_n08.py pins their edges.
"""
from __future__ import annotations

import math


def _num(value) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def half_clock_stall(age: float, native_minutes: float, trail_active: bool, bid: float, entry_premium: float, progress_r: float, min_r: float = 0.5) -> float:
    """N07's EFF rule for any strategy: from half the strategy's own time stop, an untrailed trade whose option is no higher than
    what was paid and whose underlying has not made the required progress is on its time stop. Otherwise the native clock stands."""
    if not all(_num(v) for v in (age, native_minutes, bid, entry_premium, progress_r)):
        return native_minutes
    if trail_active or bid <= 0 or entry_premium <= 0:
        return native_minutes
    half = native_minutes / 2
    if half <= age < native_minutes and bid <= entry_premium and progress_r < min_r:
        return half
    return native_minutes


def no_progress_cut(eligible: bool, bid: float, entry_premium: float, progress_r: float) -> bool:
    """N04's early EFF cut is eligible, and either the option is no higher than what was paid (N07) or the underlying has made no
    progress at all, so a small premium gain is not evidence that the trade is working."""
    if not eligible or not _num(bid) or not _num(entry_premium) or bid <= 0 or entry_premium <= 0:
        return False
    if bid <= entry_premium:
        return True
    return _num(progress_r) and progress_r <= 0


def low_day_time_allowed(minute: int, last_minute) -> bool:
    """A low-day TPB trade earns by being held to the close, so one entered too late has too little time left to work."""
    return last_minute is None or minute < last_minute


def low_day_lots(minute: int, two_lots_before) -> int:
    """One lot as always, or two when the entry is early enough to have the whole afternoon. Risk per trade stays capped by the planner."""
    return 2 if two_lots_before is not None and minute < two_lots_before else 1


def low_day_direction_allowed(mode: str, direction: str, di_up) -> bool:
    """Which way the extra low-ADX-day TPB trade may go, from yesterday's daily DI lines.

    PUTS is what N03-N07 do. PUTS_UNLESS_UP keeps a put-only book out of a daily uptrend. WITH_TREND also takes calls in one."""
    if mode == "PUTS":
        return direction == "SHORT"
    if di_up is None:
        return direction == "SHORT" and mode == "WITH_TREND"
    if mode == "PUTS_UNLESS_UP":
        return direction == "SHORT" and not di_up
    if mode == "WITH_TREND":
        return (direction == "LONG") == bool(di_up)
    raise ValueError(f"unknown low-day direction mode {mode}")
