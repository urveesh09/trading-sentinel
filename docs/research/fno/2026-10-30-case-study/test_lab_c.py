"""O30c checks: the direction sides read only earlier daily bars, the case routing passes over against-trend
signals, and the bases are the books frozen before."""
import json
import math
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab_c as C  # noqa: E402


def _daily(n=120):
    days = [d for d in (date(2025, 1, 1) + timedelta(i) for i in range(int(n * 1.5))) if d.weekday() < 5][:n]
    close = [100 + 10 * math.sin(i / 9.0) + 0.05 * i for i in range(n)]
    frame = pd.DataFrame({"open": close, "high": [c * 1.01 for c in close], "low": [c * 0.99 for c in close],
                          "close": close}, index=pd.to_datetime(days))
    return frame


def test_direction_sides_use_only_earlier_bars():
    daily = _daily()
    days = [d.strftime("%Y-%m-%d") for d in daily.index[70:]]
    full = C.direction_sides(daily, days)
    for cut in (80, 95, 110):
        s = daily.index[cut].strftime("%Y-%m-%d")
        changed = daily.copy()
        changed.iloc[cut:] = changed.iloc[cut:] * 1.2   # rewrite the day itself and everything after it
        assert C.direction_sides(changed, [s])[s] == full[s]
    assert {v["dmi_dir"] for v in full.values()} == {"UP", "DOWN"}


class _Fake:
    def __init__(self, case, sides, sigs):
        self.book, self.warm, self.notes, self._fired = {"case": case}, False, Counter(), None
        self.members = [C.Y.named("SHIPPED"), C.Y.named("TPB")]
        self.table = {"2026-03-02": {"side": sides}}
        self._sigs = sigs

    def _signal(self, i, *args):
        return self._sigs[i]


def _sig(direction):
    s = C.G.MomSignal(bar_ts="2026-03-02 10:00:00")
    s.direction = direction
    return s


def test_case_routing(monkeypatch):
    monkeypatch.setattr(C.replay, "_last_closed_bar", lambda frame, now: "2026-03-02 10:00:00")
    now = C.replay.IST.localize(pd.Timestamp("2026-03-02 10:06:00").to_pydatetime())
    short, long = _sig(C.FnoDirection.SHORT), _sig(C.FnoDirection.LONG)
    up = _Fake("dmi", {"dmi_dir": "UP", "ema_dir": "UP"}, [short, long])
    assert C.route(up, None, "UNKNOWN", now) is long and up._fired == 1 and up.notes["case_against_trend"] == 1
    down = _Fake("dmi", {"dmi_dir": "DOWN", "ema_dir": "UP"}, [short, long])
    assert C.route(down, None, "UNKNOWN", now) is short and down._fired == 0
    split = _Fake("both", {"dmi_dir": "DOWN", "ema_dir": "UP"}, [short, long])
    assert C.route(split, None, "UNKNOWN", now).direction is None and split.notes["case_no_direction"] == 2


def test_bases_are_the_frozen_books():
    b, d = C.books(), C.Y.digest
    side = json.loads((C.SIDE / "freeze.json").read_text(encoding="utf-8"))["books"]
    year = json.loads((C.ROOT / "docs/research/fno/2026-10-29-year-genome/freeze.json").read_text())["fixed_books"]
    assert d(b["BASE|UNION_ADX"]) == d(side["UNION_ADX"]) and d(b["BASE|UNION"]) == d(year["UNION"])
    assert [m["name"] for m in b["UNION|tpb_first"]["members"]] == ["TPB", "SHIPPED", "OR20", "EFF"]
    assert [m["gate"] for m in b["UNION_ADX|tpb_all_days"]["members"]] == [C.ADX, C.ADX, C.ADX, "ALWAYS"]
    assert all(b[n]["case"] == "dmi" for n in b if n.endswith("dir_dmi"))
