"""Frozen causal rules for the November 5 F&O paper comparison."""
from dataclasses import dataclass, field
from datetime import timedelta


@dataclass
class Trend:
    slot: object = None
    last: tuple | None = None
    completed: list = field(default_factory=list)

    def update(self, now, future, direction):
        if future is None or future <= 0:
            return "UNKNOWN"
        slot = now.replace(minute=now.minute // 5 * 5, second=0, microsecond=0)
        if self.slot != slot:
            if self.last and self.slot + timedelta(minutes=5) == slot:
                stamp, close = self.last
                if (slot - stamp).total_seconds() <= 75:
                    self.completed = (self.completed + [(self.slot, close)])[-3:]
                else:
                    self.completed = []
            else:
                self.completed = []
            self.slot = slot
        self.last = (now, future)
        if len(self.completed) != 3:
            return "UNKNOWN"
        prices = [p for _, p in self.completed] + [future]
        sign = 1 if direction == "LONG" else -1
        moves = [sign * (b - a) for a, b in zip(prices, prices[1:])]
        if moves[0] > 0 and moves[1] > 0 and prices[-1] * sign >= prices[-2] * sign:
            return "SUPPORT"
        if moves[0] < 0 and moves[1] < 0 and prices[-1] * sign <= prices[-2] * sign:
            return "ADVERSE"
        return "MIXED"


def trend_params(params, position, trend):
    """Only change the premium lock. Structural stops and hard flat still win."""
    if params["FNO_PROFIT_LOCK_ENABLED"] and trend == "SUPPORT":
        return {**params, "FNO_PROFIT_LOCK_KEEP_FRACTION": .35}
    if params["FNO_PROFIT_LOCK_ENABLED"] and trend == "ADVERSE":
        return {**params, "FNO_PROFIT_LOCK_ARM_R": min(.60, params["FNO_PROFIT_LOCK_ARM_R"]),
                "FNO_PROFIT_LOCK_KEEP_FRACTION": .65}
    if position.trail_active and trend == "ADVERSE":
        return {**params, "FNO_PROFIT_LOCK_ENABLED": True, "FNO_PROFIT_LOCK_ARM_R": 1.,
                "FNO_PROFIT_LOCK_KEEP_FRACTION": .60}
    return params
