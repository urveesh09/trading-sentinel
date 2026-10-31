"""O30m checks: the router's kind-of-day gates and direction modes, and how a router book is built."""
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab_m as M  # noqa: E402

C = M.C


class _Fake:
    def __init__(self, gates, sigs, sides):
        self.book, self.warm, self.notes, self._fired = {"router": "o30m"}, False, Counter(), None
        self.members = [C.Y.named(n, g) for n, g in zip(("SHIPPED", "TPB", "EFF"), gates)]
        self.table = {"2026-03-02": {"side": sides}}
        self._sigs = sigs

    def _signal(self, i, *args):
        return self._sigs[i]


def _sig(direction):
    s = C.G.MomSignal(bar_ts="2026-03-02 10:00:00")
    s.direction = direction
    return s


def test_router_gates_and_direction(monkeypatch):
    monkeypatch.setattr(C.replay, "_last_closed_bar", lambda frame, now: "2026-03-02 10:00:00")
    now = C.replay.IST.localize(pd.Timestamp("2026-03-02 10:06:00").to_pydatetime())
    L, S = C.FnoDirection.LONG, C.FnoDirection.SHORT
    sides = {"adx_abs25": "HIGH", "dmi_dir": "DOWN", "open_drive": "LOW"}
    f = _Fake(["adx_abs25:LOW", "adx_abs25:HIGH&dir=with", "adx_abs25:HIGH&open_drive:LOW&dir=against"],
              [_sig(S), _sig(L), _sig(L)], sides)
    got = M.route(f, None, "UNKNOWN", now)
    assert got is f._sigs[2] and f._fired == 2            # 1st: wrong kind of day; 2nd: long against a down trend
    assert f.notes["router_direction_pass"] == 1


def test_router_book():
    lib = M.library()
    cells = [{"cell": {"adx_abs25": "HIGH", "dmi_dir": "UP"}, "pick": "B|UNION", "mode": "with"},
             {"cell": {"adx_abs25": "LOW", "dmi_dir": "UP"}, "pick": "N|TPB|RUN", "mode": "any"}]
    b = M.router_book(cells, lib)
    assert b["router"] == "o30m" and len(b["members"]) == 5
    assert [m["gate"] for m in b["members"]] == ["adx_abs25:HIGH&dmi_dir:UP&dir=with"] * 4 + ["adx_abs25:LOW&dmi_dir:UP"]
    assert b["members"][4]["name"] == "TPB" and b["members"][4]["exit"] == "RUN"
    assert len(lib) == len(set(C.Y.digest(v) for v in lib.values()))   # no duplicate library books
