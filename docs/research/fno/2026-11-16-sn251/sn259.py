"""SN259 - the calendar and scheduled events, non-price information (PLAN.md; dates in events.json, written first).
(a) turn of the month (the last session of a month and the first 3 sessions of a month): an ATM call 09:20 -> 15:10;
(b) the session before a weekday market holiday (the next trading day is more than one calendar day later, other than a
    plain Friday -> Monday weekend): an ATM call 09:20 -> 15:10;
(c) RBI policy days: the ATM straddle 09:50 -> 15:10;
(d) Union Budget days: the ATM straddle 09:20 -> 15:10.
Rs 3,000 stop. Null "day": the same trade on as many random sessions."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gl  # noqa: E402
import legs as LG  # noqa: E402
import slot  # noqa: E402

EV = json.loads((HERE / "events.json").read_text(encoding="utf-8"))
RBI, BUDGET = set(EV["RBI"]), set(EV["BUDGET"])


def turn_of_month(smp, d):
    k = smp.cal.index(d)
    nd = smp.cal[k + 1] if k + 1 < len(smp.cal) else None
    if nd is not None and nd[:7] != d[:7]:
        return True
    first = [x for x in smp.cal if x[:7] == d[:7]][:3]
    return d in first


def pre_holiday(smp, d):
    nd = smp.next_day(d)
    if nd is None:
        return False
    g = (dt.date.fromisoformat(nd) - dt.date.fromisoformat(d)).days
    wd = dt.date.fromisoformat(d).weekday()
    return g > 1 and not (wd == 4 and g == 3)


def call_trade(smp, d, side, stress=gl.STRESS, late=0):
    return LG.intraday(smp, d, LG.side_legs(smp, smp.s[d], gl.I["09:20"], 1), gl.I["09:20"], gl.FLAT, stress=stress, late=late)


def straddle_at(i):
    def f(smp, d, side, stress=gl.STRESS, late=0):
        return LG.intraday(smp, d, LG.straddle(smp, smp.s[d], i), i, gl.FLAT, stress=stress, late=late)
    return f


ALL = lambda smp, d: True  # noqa: E731
VARIANTS = [
    {"name": "(a) turn of the month: ATM call 09:20-15:10", "signal": lambda smp, d: True if turn_of_month(smp, d) else None,
     "trade": call_trade, "null": "day", "eligible": ALL},
    {"name": "(b) before a weekday holiday: ATM call 09:20-15:10", "signal": lambda smp, d: True if pre_holiday(smp, d) else None,
     "trade": call_trade, "null": "day", "eligible": ALL},
    {"name": "(c) RBI policy day: ATM straddle 09:50-15:10", "signal": lambda smp, d: True if d in RBI else None,
     "trade": straddle_at(35), "null": "day", "eligible": ALL},
    {"name": "(d) Budget day: ATM straddle 09:20-15:10", "signal": lambda smp, d: True if d in BUDGET else None,
     "trade": straddle_at(gl.I["09:20"]), "null": "day", "eligible": ALL},
]

if __name__ == "__main__":
    res = slot.evaluate("SN259", VARIANTS)
    slot.save(HERE / "results-sn259.json", res)
