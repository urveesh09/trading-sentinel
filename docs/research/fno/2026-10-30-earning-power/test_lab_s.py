"""O30s checks: the entries are causal and fire as declared, add-ons never raise the first risk, the simulator's sizing,
cash and brakes behave, and the bootstrap is repeatable."""
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_s as A  # noqa: E402
import lab_s as S  # noqa: E402


def _day(bars: list[tuple]) -> tuple[pd.DataFrame, list[str]]:
    """Bars of (high, low, close) from 09:15, every 5 minutes, ATR 1."""
    idx = [pd.Timestamp("2026-03-02 09:15") + pd.Timedelta(minutes=5 * i) for i in range(len(bars))]
    t = pd.DataFrame(bars, columns=["high", "low", "close"], index=idx)
    t["atr"] = 1.0
    t["minute"] = [555 + 5 * i for i in range(len(bars))]
    return t, [str(i) for i in idx]


FLAT = [(101.0, 100.0, 100.5)] * 6
M = {**S.ENTRY}


def test_retest_long():
    t, st = _day(FLAT + [(102.5, 101.0, 102.0), (102.0, 101.1, 101.5), (102.8, 101.5, 102.6), (103, 102, 102.5)])
    out = S.retest(M, t, st)
    assert list(out) == [st[8]] and out[st[8]][0] == 1
    assert out[st[8]][1] < 101.1, "the stop sits past the retest"


def test_retest_dies_when_it_closes_back_inside():
    t, st = _day(FLAT + [(102.5, 101.0, 102.0), (102.0, 100.0, 100.5), (103, 100.5, 102.6)])
    assert S.retest(M, t, st) == {}


def test_failconf_reverses_toward_the_middle():
    t, st = _day(FLAT + [(102.5, 101.0, 102.0), (101.5, 100.2, 100.5), (100.9, 100.2, 100.4), (100.5, 100.0, 100.2)])
    out = S.failconf(M, t, st)
    assert list(out) == [st[8]]
    d, stop, target = out[st[8]]
    assert d == -1 and stop > 100.9 and target == 100.5


def test_failconf_dies_when_the_level_is_regained():
    t, st = _day(FLAT + [(102.5, 101.0, 102.0), (101.5, 100.2, 100.5), (102.0, 100.5, 101.8), (101.0, 100.2, 100.4)])
    assert S.failconf(M, t, st) == {}


def test_squeeze_needs_a_quiet_box_then_a_break():
    quiet = [(100.3, 100.0, 100.0 + 0.05 * (i % 3)) for i in range(20)]
    t, st = _day(quiet + [(103.0, 100.2, 102.5), (103, 102, 102.5)])
    out = S.squeeze(M, t, st)
    assert list(out) == [st[20]] and out[st[20]][0] == 1


def test_entries_are_causal():
    bars = FLAT + [(102.5, 101.0, 102.0), (102.0, 101.1, 101.5), (102.8, 101.5, 102.6)] + [(103, 102, 102.5)] * 10
    bars2 = FLAT + [(102.5, 101.0, 102.0), (101.5, 100.2, 100.5), (100.9, 100.2, 100.4)] + [(100.5, 100, 100.2)] * 10
    for rule, base in ((S.retest, bars), (S.failconf, bars2), (S.squeeze, [(100.3, 100.0, 100.1)] * 20 + [(103, 100.2, 102.5)])):
        t, st = _day(base)
        full = rule(M, t, st)
        assert full, rule.__name__
        for cut in range(5, len(base)):
            changed = t.copy()
            changed.iloc[cut + 1:, changed.columns.get_indexer(["high", "low", "close"])] *= 1.05
            again = rule(M, changed, st)
            assert {k: v for k, v in full.items() if st.index(k) <= cut} == {k: v for k, v in again.items() if st.index(k) <= cut}


def _leg(direction="LONG"):
    return SimpleNamespace(direction=direction, entry_underlying=100.0, stop_underlying=99.0 if direction == "LONG" else 101.0,
                           entry_premium=50.0, lots=1, lot_size=65, fills=[], o30s_r=1.0, o30s_adds=0)


def test_add_moves_the_stop_so_the_first_risk_does_not_grow():
    leg, q, notes = _leg(), SimpleNamespace(ask=60.0, bid=59.0), Counter()
    assert not S.add_if_due(leg, 100.9, q, S.ADDS["ADD2"], notes)
    assert S.add_if_due(leg, 101.0, q, S.ADDS["ADD2"], notes)
    assert leg.lots == 2 and leg.stop_underlying == 100.0 and leg.entry_premium == 55.0
    assert not S.add_if_due(leg, 101.5, q, S.ADDS["ADD2"], notes)
    assert S.add_if_due(leg, 102.0, q, S.ADDS["ADD2"], notes)
    assert leg.lots == 3 and leg.stop_underlying == 101.0
    assert not S.add_if_due(leg, 110.0, q, S.ADDS["ADD2"], notes), "no more than the plan"


def test_add_short_side():
    leg, q = _leg("SHORT"), SimpleNamespace(ask=60.0, bid=59.0)
    assert S.add_if_due(leg, 99.0, q, S.ADDS["ADD1"], Counter())
    assert leg.stop_underlying == 100.0


def _trade(day, hour, prem, net, stretch=None, lots=1, sleeve=0, minutes=30):
    return (f"{day}T{hour:02d}:00:00+05:30", f"{day}T{hour:02d}:{minutes:02d}:00+05:30", prem, net, lots, stretch, day,
            tuple(pd.Timestamp(day).isocalendar()[:2]), day[:7], sleeve)


def test_sim_scales_and_stress_is_per_lot():
    rows = [_trade("2026-03-02", 10, 100.0, 1000.0), _trade("2026-03-02", 11, 100.0, -500.0)]
    assert A.sim(rows, ("fixed", 3))["net"] == 1500
    assert A.sim(rows, ("fixed", 3), stress=200)["net"] == 1500 - 2 * 3 * 200


def test_sim_own_cash_limits_lots():
    s = A.sim([_trade("2026-03-02", 10, 100.0, 1000.0)], ("fixed", 100), capital=30000.0)
    assert s["max_lots"] == 4, "Rs 30,000 buys four lots at Rs 6,500"


def test_sim_risk_rule_and_half_when_stretched():
    rows = [_trade("2026-03-02", 10, 100.0, 1000.0, stretch=0.9)]
    assert A.sim(rows, ("risk", 0.02))["max_lots"] == 3          # 5000 // 1625
    assert A.sim(rows, ("risk", 0.02), half=True)["max_lots"] == 1


def test_sim_shipped_brakes_stop_the_day_after_two_losses():
    rows = [_trade("2026-03-02", h, 100.0, -100.0) for h in (10, 11, 12)]
    assert A.sim(rows, ("fixed", 1), "SHIPPED")["trades"] == 2
    assert A.sim(rows, ("fixed", 1), "NONE")["trades"] == 3


def test_sim_throttle_cuts_after_a_fall():
    rows = [_trade("2026-03-02", 10, 100.0, -6000.0), _trade("2026-03-03", 10, 100.0, 100.0)]
    s = A.sim(rows, ("fixed", 8), "THROTTLE")                     # -48,000 of 2.5 lakh is 19%: half size next
    assert s["net"] == round(-48000 + 4 * 100)


def test_sim_day_cap_is_per_sleeve():
    rows = sorted([_trade("2026-03-02", h, 100.0, 10.0, sleeve=s) for h in (10, 11, 12, 13) for s in (0, 1)])
    assert A.sim(rows, ("fixed", 1))["trades"] == 6


def test_boot_is_repeatable_and_scales():
    rows = {"2025": [_trade("2025-03-03", 10, 100.0, 300.0), _trade("2025-03-10", 10, 100.0, -100.0)], "2026": []}
    a, b = A.boot(rows, [1, 5], stress=0.0), A.boot(rows, [1, 5], stress=0.0)
    assert a == b
    assert a["5"]["median_net"] == 5 * a["1"]["median_net"]


def test_books():
    b = S.books()
    assert sum(n.startswith("NULL") for n in b) == 20
    assert len(b["BEST+ALL3"]["members"]) == 7
    assert [m["gate"] for m in b["BEST"]["members"]] == [S.C.ADX, S.C.ADX, S.C.ADX, "ALWAYS"]
    assert [m["gate"] for m in b["LIVE"]["members"]] == [S.C.ADX] * 4
    assert b["TPB|ADD2"]["pyr"] == "ADD2" and b["TPB|HOLD"]["members"][0]["exit"] == "HOLD"
    assert all(v["o30s"] == "raw1" for v in b.values())
    assert len({S.Y.digest(v) for v in b.values()}) == len(b)
