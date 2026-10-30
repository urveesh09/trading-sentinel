"""O30c Tier 2 checks: the breakout direction case touches only SHIPPED / OR20, and the 10:00-14:00 window."""
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab_c2 as C2  # noqa: E402

C = C2.C


class _Fake:
    def __init__(self, case, sigs, names=("SHIPPED", "TPB")):
        self.book, self.warm, self.notes, self._fired = {"case": case}, False, Counter(), None
        self.members = [C.Y.named(n) for n in names]
        self.table = {"2026-03-02": {"side": {"dmi_dir": "UP", "ema_dir": "UP"}}}
        self._sigs = sigs

    def _signal(self, i, *args):
        return self._sigs[i]


def _sig(direction):
    s = C.G.MomSignal(bar_ts="2026-03-02 10:00:00")
    s.direction = direction
    return s


def _now(clock):
    return C.replay.IST.localize(pd.Timestamp(f"2026-03-02 {clock}").to_pydatetime())


def test_breakouts_follow_the_trend_and_tpb_is_free(monkeypatch):
    monkeypatch.setattr(C.replay, "_last_closed_bar", lambda frame, now: "2026-03-02 10:00:00")
    short = _sig(C.FnoDirection.SHORT)
    passed = _Fake("dmi_breakouts", [short, short])          # SHIPPED short on an up day: passed over; TPB short: kept
    assert C2.route(passed, None, "UNKNOWN", _now("10:06")) is short and passed._fired == 1
    assert passed.notes["case_breakout_against_trend"] == 1


def test_window_10_to_14(monkeypatch):
    long = _sig(C.FnoDirection.LONG)
    for bar, ok in (("09:50:00", False), ("09:55:00", True), ("13:50:00", True), ("13:55:00", False)):
        monkeypatch.setattr(C.replay, "_last_closed_bar", lambda frame, now, bar=bar: f"2026-03-02 {bar}")
        f = _Fake("window_10_14", [long, long])
        assert (C2.route(f, None, "UNKNOWN", _now("12:00")).direction is not None) is ok, bar
