"""Independent mechanics, mirrored direction, causality and decision-rule checks."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_gap as X
import analyze_gap as A


def fixture():
    idx = pd.date_range("2026-03-02 09:15", periods=60, freq="5min")
    t = pd.DataFrame({"open": 100., "high": 100.5, "low": 99.5, "close": 100.,
                      "atr": 4., "vwap": 100., "minute": idx.hour * 60 + idx.minute}, index=idx)
    # Deliberate down shock at 10:30; two-bar bounce confirms at 10:40.
    t.iloc[15, t.columns.get_indexer(["open", "high", "low", "close"])] = [100, 100, 96, 96.2]
    t.iloc[16, t.columns.get_indexer(["open", "high", "low", "close"])] = [96.2, 97.5, 96, 97.2]
    t.iloc[17, t.columns.get_indexer(["open", "high", "low", "close"])] = [97.2, 99, 97, 98.8]
    # Upside breakout at 11:20, with a deliberately supplied DMI reading.
    t.iloc[25, t.columns.get_indexer(["open", "high", "low", "close"])] = [100, 103, 99.8, 102.8]
    trend = pd.DataFrame({"pdi": 15., "mdi": 15., "adx": 15.}, index=idx)
    trend.iloc[25] = [35, 10, 30]
    return {"t": t, "stamps": list(idx.strftime("%Y-%m-%d %H:%M:%S"))}, trend


@pytest.mark.parametrize("family", X.FAMILIES)
def test_expected_signal_and_mirrored_direction(family):
    f, trend = fixture()
    hit = X.entries({"family": family}, f, trend)
    i, want = (25, 1) if family == "INTRADAY_DMI" else (17, 1)
    d, stop, target = hit[f["stamps"][i]]
    assert d == want and stop < f["t"]["close"].iloc[i] < target
    mirror = f["t"].copy()
    mirror["open"], mirror["close"] = 200 - mirror["open"], 200 - mirror["close"]
    mirror["high"], mirror["low"] = 200 - f["t"]["low"], 200 - f["t"]["high"]
    mirror["vwap"] = 200 - mirror["vwap"]
    tr = trend.copy()
    tr["pdi"], tr["mdi"] = trend["mdi"], trend["pdi"]
    rev = X.entries({"family": family}, {**f, "t": mirror}, tr)
    rd, rs, rt = rev[f["stamps"][i]]
    assert rd == -d and rs == pytest.approx(200 - stop) and rt == pytest.approx(200 - target)


@pytest.mark.parametrize("family", X.FAMILIES)
def test_every_prefix_matches_and_mutated_future_does_not_change_it(family):
    f, trend = fixture()
    full = X.entries({"family": family}, f, trend)
    for cut in range(13, len(f["t"])):
        upto = {**f, "t": f["t"].iloc[:cut], "stamps": f["stamps"][:cut]}
        expected = {k: v for k, v in full.items() if k in upto["stamps"]}
        assert X.entries({"family": family}, upto, trend.iloc[:cut]) == expected
        changed = f["t"].copy()
        changed.iloc[cut:, :4] *= 3
        again = X.entries({"family": family}, {**f, "t": changed}, trend)
        assert {k: v for k, v in again.items() if k in upto["stamps"]} == expected


def test_dmi_prefix_and_rising_direction():
    idx = pd.date_range("2026-03-02 09:15", periods=100, freq="5min")
    c = pd.Series(100 + np.arange(100) * 0.2, index=idx)
    frame = pd.DataFrame({"high": c + 0.5, "low": c - 0.5, "close": c})
    full = X.dmi(frame)
    assert full["adx"].iloc[-1] == pytest.approx(100)
    assert full["pdi"].iloc[-1] > full["mdi"].iloc[-1]
    pd.testing.assert_frame_equal(X.dmi(frame.iloc[:70]), full.iloc[:70])


@pytest.mark.parametrize("family", X.FAMILIES)
def test_session_gap_and_deadline_prevent_entry(family):
    f, trend = fixture()
    i = 25 if family == "INTRADAY_DMI" else 17
    changed = f["t"].copy()
    changed.iloc[i, changed.columns.get_loc("minute")] += 40
    assert f["stamps"][i] not in X.entries({"family": family}, {**f, "t": changed}, trend)
    changed = f["t"].copy()
    changed.iloc[i, changed.columns.get_loc("minute")] = 810
    assert f["stamps"][i] not in X.entries({"family": family}, {**f, "t": changed}, trend)


def test_unconfirmed_shock_and_large_stop_are_refused():
    f, trend = fixture()
    f["t"].iloc[17, f["t"].columns.get_loc("close")] = 97
    assert f["stamps"][17] not in X.entries({"family": "SHOCK_RECOVERY"}, f, trend)
    f, trend = fixture()
    f["t"]["atr"] = 0.5
    assert f["stamps"][17] not in X.entries({"family": "SHOCK_RECOVERY"}, f, trend)


def test_books_keep_complement_gate_skip_cost_and_shared_brakes():
    books = X.books()
    for fam in X.FAMILIES:
        exact, raw = books[f"EX|{fam}"], books[f"RAW|{fam}"]
        assert exact["cfg"] == {} and exact["cost"] == [200, 5] and exact["skip"] == 0.5
        assert exact["members"][:4] == books["EX|MAIN"]["members"]
        assert exact["members"][-1]["gate"] == "adx_abs30:LOW"
        assert raw["cfg"]["FNO_MAX_LOTS"] == 1 and "cost" not in raw


def test_unknown_daily_gate_does_not_admit_complement():
    assert not X.Y.ROUTER.allowed("adx_abs30:LOW", {"side": {"adx_abs30": None}})
    assert X.Y.ROUTER.allowed("adx_abs30:LOW", {"side": {"adx_abs30": "LOW"}})
    assert not X.Y.ROUTER.allowed("adx_abs30:LOW", {"side": {"adx_abs30": "HIGH"}})


@pytest.mark.parametrize("family", X.FAMILIES)
def test_signal_dispatch_uses_last_completed_bar_and_not_future_tail(family):
    from datetime import datetime
    f, _ = fixture()
    frame = f["t"][["open", "high", "low", "close"]].copy()
    prior = frame.copy()
    prior.index -= pd.Timedelta(days=1)
    frame = pd.concat([prior, frame])
    frame["volume"] = 1000.
    now = X.Y.replay.IST.localize(datetime(2026, 3, 2, 10, 44, 59))
    m = X.member(family)
    X._CACHE.clear()
    X.O27F._FEATURES.clear()
    a = X.signal(m, frame, "UNKNOWN", now)
    assert pd.Timestamp(a.bar_ts) == pd.Timestamp("2026-03-02 10:35")
    changed = frame.copy()
    changed.loc[changed.index >= pd.Timestamp("2026-03-02 10:40"), ["open", "high", "low", "close"]] *= 3
    X._CACHE.clear()
    X.O27F._FEATURES.clear()
    b = X.signal(m, changed, "UNKNOWN", now)
    assert repr(a) == repr(b)


def test_judge_rejects_one_bad_year_and_unresolved():
    raw = {"years": {y: {"net": 100, "trades": 20, "without_best_day": 50} for y in A.YEARS},
           "halves": {y: [50, 50] for y in A.YEARS}, "weekly_t": 3, "total": 300, "unresolved": 0}
    main = {"years": {y: {"net": 10, "fall_pct": .05} for y in A.YEARS}, "weekly": [0] * 20}
    exact = {"years": {y: {"net": 100, "fall_pct": .05} for y in A.YEARS}, "weekly": [10, 11] * 10, "unresolved": 0}
    assert A.judge(raw, exact, main, 0)["passes"]
    raw["years"]["2024"]["net"] = -1
    assert not A.judge(raw, exact, main, 0)["passes"]
    raw["years"]["2024"]["net"] = 100
    exact["unresolved"] = 1
    assert not A.judge(raw, exact, main, 0)["passes"]
