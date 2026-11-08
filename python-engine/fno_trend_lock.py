"""[N012-A] The trend-aware profit lock on the paper F&O main book.

The N012 research's strongest priced change (Round 30 ``TREND_ONLY``, docs/research/simulation/2026-11-05-fno-n12):
while an N11 paper position is held, the front future's last three completed 5-minute buckets and its current price
say whether the trend SUPPORTS the trade (two bucket moves with it, the price not back under the last bucket close),
opposes it (ADVERSE, the mirror) or neither (MIXED; UNKNOWN until three buckets are complete). Only the premium
profit lock changes; structural stops, the trail, time stops and the hard flat are untouched:

  * SUPPORT, lock on: keep ``FNO_TREND_LOCK_SUPPORT_KEEP`` of the best gain (default 0.35, wider than the
    native 0.50, so a trend in the trade's favour is given room);
  * ADVERSE, lock on: keep ``FNO_TREND_LOCK_ADVERSE_KEEP`` (default 0.65, tighter), the arm capped at 0.60 R
    (a cap the native 0.40 R arm never reaches; kept so the rule is the research's exactly);
  * ADVERSE, lock off, trail active: the lock is switched on at 1.0 R keeping ``FNO_TREND_LOCK_TRAIL_KEEP``
    (default 0.60; 0 or less leaves it off).

The numbers and the decision to keep them: docs/research/simulation/2026-11-08-fno-n012-a2 (N012-A2). Paper only
(``FNO_PAPER``): a real-money position and the one-lot paper reference (fno_n11.manage_paper) keep the native
lock. The bucket state lives in memory per position; after a restart a position reads UNKNOWN (native lock) until
three buckets complete again, at most 15 minutes. Pure apart from that state; no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Mapping, Optional

from config import settings

SUPPORT, ADVERSE, MIXED, UNKNOWN = "SUPPORT", "ADVERSE", "MIXED", "UNKNOWN"
BUCKET_GAP_SEC = 75          # the last look in a bucket must be this close to its end for its close to count


@dataclass
class Trend:
    """The research's ``regular_rules.Trend``, line for line: completed 5-minute buckets of the front future."""
    slot: Optional[datetime] = None
    last: Optional[tuple] = None
    completed: list = field(default_factory=list)

    def update(self, now: datetime, future: Optional[float], direction: str) -> str:
        if future is None or future <= 0:
            return UNKNOWN
        slot = now.replace(minute=now.minute // 5 * 5, second=0, microsecond=0)
        if self.slot != slot:
            if self.last and self.slot + timedelta(minutes=5) == slot:
                stamp, close = self.last
                if (slot - stamp).total_seconds() <= BUCKET_GAP_SEC:
                    self.completed = (self.completed + [(self.slot, close)])[-3:]
                else:
                    self.completed = []
            else:
                self.completed = []
            self.slot = slot
        self.last = (now, future)
        if len(self.completed) != 3:
            return UNKNOWN
        prices = [p for _, p in self.completed] + [future]
        sign = 1 if direction == "LONG" else -1
        moves = [sign * (b - a) for a, b in zip(prices, prices[1:])]
        if moves[0] > 0 and moves[1] > 0 and prices[-1] * sign >= prices[-2] * sign:
            return SUPPORT
        if moves[0] < 0 and moves[1] < 0 and prices[-1] * sign <= prices[-2] * sign:
            return ADVERSE
        return MIXED


def trend_params(params: Mapping[str, Any], position: Any, trend: str, *, support_keep: float,
                 adverse_keep: float, trail_keep: Optional[float]) -> dict:
    """The exit parameters for one look: only the premium lock changes (the research's ``trend_params``)."""
    if params["FNO_PROFIT_LOCK_ENABLED"] and trend == SUPPORT:
        return {**params, "FNO_PROFIT_LOCK_KEEP_FRACTION": support_keep}
    if params["FNO_PROFIT_LOCK_ENABLED"] and trend == ADVERSE:
        return {**params, "FNO_PROFIT_LOCK_ARM_R": min(.60, params["FNO_PROFIT_LOCK_ARM_R"]),
                "FNO_PROFIT_LOCK_KEEP_FRACTION": adverse_keep}
    if trail_keep is not None and getattr(position, "trail_active", False) and trend == ADVERSE:
        return {**params, "FNO_PROFIT_LOCK_ENABLED": True, "FNO_PROFIT_LOCK_ARM_R": 1.,
                "FNO_PROFIT_LOCK_KEEP_FRACTION": trail_keep}
    return dict(params)


_TRENDS: dict = {}


def applies(source: str, paper_mode: bool, position: Any) -> bool:
    """On for an N11 paper position (a first lot or an earned lot) while the switch is on; never for real money."""
    import fno_n11
    from fno_models import FnoSource
    return (bool(settings.FNO_TREND_LOCK_ENABLED) and source == FnoSource.FNO_PAPER.value and bool(paper_mode)
            and (fno_n11.is_parent(position) or getattr(position, "strategy", None) == fno_n11.ADD))


def params_for(key: Any, position: Any, params: Mapping[str, Any], now: datetime,
               future: Optional[float]) -> tuple:
    """(parameters, trend) for one management look at ``position``: its trend updated with this look's future."""
    trend = _TRENDS.setdefault(key, Trend()).update(now, future, position.direction)
    trail = float(settings.FNO_TREND_LOCK_TRAIL_KEEP)
    return trend_params(params, position, trend, support_keep=float(settings.FNO_TREND_LOCK_SUPPORT_KEEP),
                        adverse_keep=float(settings.FNO_TREND_LOCK_ADVERSE_KEEP),
                        trail_keep=trail if trail > 0 else None), trend


def forget(key: Any) -> None:
    """A position left: its buckets go with it."""
    _TRENDS.pop(key, None)


def forget_all_but(source: str, keys: set) -> None:
    """Drop ``source``'s buckets for positions no longer open (one call per management pass of that source)."""
    for key in [k for k in _TRENDS if k[0] == source and k not in keys]:
        _TRENDS.pop(key, None)


__all__ = ["Trend", "trend_params", "applies", "params_for", "forget", "forget_all_but",
           "SUPPORT", "ADVERSE", "MIXED", "UNKNOWN"]
