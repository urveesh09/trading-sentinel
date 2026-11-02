"""N09's rules as pure functions: no market data access, no I/O, nothing about any specific date.

Each one answers a question using only what is known at that moment. n09_lab.py applies them; test_n09.py pins their edges.
"""
from __future__ import annotations

import math
from statistics import mean, median
from typing import Optional, Sequence


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def confirmed(direction: str, signal_close: float, next_close: float, next_low: float, next_high: float, stop: float, stretch: Optional[float], stretch_limit: float = 0.5) -> bool:
    """The entry challenger: the next completed bar closes further in the trade's direction, never touched the stop, and the move has not
    become a stretched entry. One rule, no setting chosen from results."""
    if not all(_num(v) for v in (signal_close, next_close, next_low, next_high, stop)):
        return False
    if _num(stretch) and stretch >= stretch_limit:
        return False
    if direction == "LONG":
        return next_close > signal_close and next_low > stop
    if direction == "SHORT":
        return next_close < signal_close and next_high < stop
    raise ValueError(f"unknown direction {direction}")


def target_from(direction: str, close: float, stop: float, reward_r: float = 1.8) -> float:
    """The 1.8R target every strategy uses, measured from the confirmed price, with the original stop."""
    side = 1 if direction == "LONG" else -1
    return close + side * reward_r * abs(close - stop)


def structure_broken(direction: str, closes: Sequence[float], vwaps: Sequence[float], age_minutes: float, trail_active: bool, progress_r: float, min_age: float = 20.0, min_r: float = 0.5) -> bool:
    """The exit challenger: an untrailed trade at least 20 minutes old with under half a stop's progress, whose last two closed bars both
    closed on the wrong side of VWAP. A trade that is working, or a trade too young to judge, keeps its recorded plan."""
    if trail_active or len(closes) < 2 or len(vwaps) < 2 or not _num(age_minutes) or not _num(progress_r):
        return False
    if age_minutes < min_age or progress_r >= min_r:
        return False
    pairs = list(zip(closes[-2:], vwaps[-2:]))
    if not all(_num(c) and _num(v) for c, v in pairs):
        return False
    if direction == "LONG":
        return all(c < v for c, v in pairs)
    return all(c > v for c, v in pairs)


def noise_sigma(moves: Sequence[float], need: int = 10) -> Optional[float]:
    """Zarattini, Aziz and Barbon: the average absolute move from the open at this time of day over the last 14 days.
    Ten is the least accepted, because holidays leave fewer than 14 sessions in the replay's 21-calendar-day window."""
    good = [m for m in moves if _num(m)]
    return mean(good) if len(good) >= need else None


def noise_bounds(open_today: float, prev_close: float, sigma: float) -> tuple[float, float]:
    """The paper's gap-adjusted boundaries: Upper = max(open, previous close) x (1 + sigma); Lower = min(open, previous close) x (1 - sigma)."""
    return max(open_today, prev_close) * (1 + sigma), min(open_today, prev_close) * (1 - sigma)


def noise_mark(bar_start_minute: int) -> bool:
    """Decisions only at 30-minute multiples after the open, the paper's HH:00 and HH:30 moved to a 09:15 open: the bar that closes at 09:45, 10:15..."""
    return (bar_start_minute + 5 - 555) % 30 == 0


def noise_direction(close: float, upper: float, lower: float) -> Optional[str]:
    if close > upper:
        return "LONG"
    if close < lower:
        return "SHORT"
    return None


def noise_trail_hit(direction: str, close: float, upper: float, lower: float, vwap: Optional[float]) -> bool:
    """The paper's stop: long max(upper, VWAP), short min(lower, VWAP), checked only at the half-hour marks."""
    if direction == "LONG":
        return close < (max(upper, vwap) if _num(vwap) else upper)
    return close > (min(lower, vwap) if _num(vwap) else lower)


def trailing_median(values: Sequence[float], window: int = 250, need: int = 120) -> Optional[float]:
    """The median of the last 250 sessions' readings, none of them today's."""
    good = [v for v in values if _num(v)][-window:]
    return median(good) if len(good) >= need else None


def vol_lots(atr_pct: Optional[float], usual: Optional[float]) -> int:
    """The size challenger: two lots only when yesterday's daily range measure is at or above its own usual level of the past year.
    It never refuses a trade. With no reading, one lot."""
    if not _num(atr_pct) or not _num(usual):
        return 1
    return 2 if atr_pct >= usual else 1


def rearm_annual(halted_year: int, this_year: int) -> bool:
    """The account challenger, plain form: a stopped book may start again at the next calendar year."""
    return this_year > halted_year


def rearm_shadow(recent_nets: Sequence[float], need: int = 20) -> bool:
    """The account challenger, evidence form: the book keeps trading on paper while stopped, and real trading starts again only when its
    last 20 paper trades together made money. It reads paper results of the same rules, one lot, and no real position depends on it."""
    if len(recent_nets) < need:
        return False
    return sum(recent_nets[-need:]) > 0
