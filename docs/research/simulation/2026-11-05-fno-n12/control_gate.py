"""Point-in-time N11 gate evidence for the shared-wallet control."""

from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime
from math import isfinite

import fno_n11
from fno_exit_rules import IST


@dataclass(frozen=True)
class VolatilityReading:
    recorded_at: datetime
    atr_pct: float
    usual: float


@dataclass(frozen=True)
class ShadowClose:
    id: int
    at: datetime
    net: float


@dataclass(frozen=True)
class GateState:
    stand_aside: bool
    vol_up: bool
    paper_positive: bool
    volatility_recorded_at: datetime | None
    above_line: bool
    paper_count: int
    paper_sum: float


class GateTape:
    """Scoped volatility and complete settled N11 shadow history.

    The caller attests that the close history includes the native opening
    research seeds and all closed shadow results through the declared scope.
    The tape provides observed state or a counterfactual shadow's own state,
    depending on the source. Keep those uses separate in the caller.
    """

    def __init__(self, start: datetime, end: datetime, readings: list[VolatilityReading],
                 closes: list[ShadowClose], *, need: int, stand_ratio: float):
        if any(at.utcoffset() is None for at in (start, end)) or end < start:
            raise ValueError("invalid gate coverage clocks")
        if need < 1 or not isfinite(stand_ratio) or stand_ratio <= 0:
            raise ValueError("invalid native gate policy")
        self._start, self._end = start, end
        self._need, self._stand_ratio = need, stand_ratio
        self._readings = {}
        for reading in readings:
            at = reading.recorded_at
            if at.utcoffset() is None or not start <= at <= end:
                raise ValueError("volatility reading outside gate coverage")
            if (not isfinite(reading.atr_pct) or reading.atr_pct < 0
                    or not isfinite(reading.usual) or reading.usual <= 0):
                raise ValueError("invalid volatility reading")
            day = at.astimezone(IST).date()
            if day in self._readings:
                raise ValueError("duplicate daily volatility reading")
            self._readings[day] = reading
        if any(c.at.utcoffset() is None or c.at > end or not isfinite(c.net) for c in closes):
            raise ValueError("invalid shadow close")
        if len({c.id for c in closes}) != len(closes):
            raise ValueError("duplicate shadow close")
        ordered = sorted(closes, key=lambda c: (c.at, c.id))
        self._times = [close.at for close in ordered]
        self._nets = [close.net for close in ordered]

    def at(self, clock: datetime) -> GateState | None:
        if clock.utcoffset() is None:
            raise ValueError("gate decision clock must be aware")
        if not self._start <= clock <= self._end:
            return None
        reading = self._readings.get(clock.astimezone(IST).date())
        if reading is None:
            return None
        if reading.recorded_at > clock:
            reading = None
        atr, usual = (reading.atr_pct, reading.usual) if reading is not None else (None, None)
        count = bisect_left(self._times, clock)
        nets = self._nets[max(0, count - self._need):count]
        above = fno_n11.vol_up(atr, usual, self._stand_ratio)
        return GateState(
            fno_n11.stand_aside(above, nets, self._need), fno_n11.vol_up(atr, usual),
            fno_n11.paper_positive(nets, self._need), reading.recorded_at if reading else None,
            above, count, sum(nets),
        )
