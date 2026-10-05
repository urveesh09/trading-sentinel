"""Classic Penny MIS profit protection (paper), owner-directed 2026-10-05.

The classic book only compared price with its fixed entry stop: it never took
its own +2R target intraday and never raised the stop. On Oct 5 SUTLEJTEX
(entry 37.70, stop 37.24, target 38.95) printed +3.4%/+4.1% at 11:03/11:18 and
was stopped at 36.74 for -Rs9.

Rule (declared before any replay of it):
  1. Price at/above the stored target -> exit at the market (``target_paper``).
  2. Once the best price since entry reaches +1R, the stop never sits below
     the larger of round-trip breakeven and entry + half the best gain
     (``LOCK_SHARE``), so a winner gives back at most half its peak.
  3. The stop only ever rises.

Pure decision code; ``main.run_penny_paper_stop_monitor`` persists the peak
and stop and executes the exits.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional

LOCK_AFTER_R = 1.0
LOCK_SHARE = 0.5
TICK = 0.01


@dataclass(frozen=True)
class LockDecision:
    stop: float
    peak: float
    exit_reason: Optional[str] = None


def _floor_tick(price: float) -> float:
    return math.floor(round(price / TICK, 6)) * TICK


def decide(*, entry: float, initial_stop: float, target: Optional[float], stop: float,
           peak: Optional[float], ltp: float, breakeven_per_share: float = 0.0) -> LockDecision:
    """Next stop/peak for one observed price; ``exit_reason`` set for a target exit."""
    peak = max(float(peak or entry), ltp)
    if target and target > entry and ltp >= target:
        return LockDecision(stop=stop, peak=peak, exit_reason="target_paper")
    risk = entry - initial_stop
    if risk <= 0 or peak < entry + LOCK_AFTER_R * risk:
        return LockDecision(stop=stop, peak=peak)
    lock = max(entry + breakeven_per_share, entry + LOCK_SHARE * (peak - entry))
    return LockDecision(stop=max(stop, round(_floor_tick(lock), 2)), peak=peak)
