"""O31e checks: every new reading and entry is causal, the filters do what they say, and the frozen rules judge what they say."""
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_w as A  # noqa: E402
import lab_w as X  # noqa: E402
import sides_w as W  # noqa: E402


def _frame(days=8, swing=0.006) -> pd.DataFrame:
    rows, d, made, price = [], date(2026, 3, 2), 0, 100.0
    while made < days:
        if d.weekday() < 5:
            for i in range(75):
                ts = datetime.combine(d, datetime.min.time()) + timedelta(hours=9, minutes=15 + 5 * i)
                close = 100 * (1 + swing * math.sin(i / 3.0 + made) + 0.0004 * i * (-1) ** made)
                rows.append((ts, price, max(price, close) * 1.0005, min(price, close) * 0.9995, close, 100 + i))
                price = close
            made += 1
        d += timedelta(days=1)
    return pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close", "volume"]).set_index("datetime")


def _members():
    return [X.member("GAP_FADE", "ALWAYS"), X.member("LAST_HOUR", "ALWAYS"), X.member("CPR_BREAK", "ALWAYS"), X.member("IB_BREAK", "ALWAYS"),
            X.member("SUPERTREND_VWAP", "ALWAYS")]


def test_every_new_entry_is_causal_and_each_fires_somewhere():
    frame = _frame()
    fired = set()
    for day in sorted(set(frame.index.date))[-4:]:
        for m in _members():
            X._TABLE.clear()
            X.O27F._FEATURES.clear()
            full = X.entries(m, X.O27F.day_features(frame, day))
            if full:
                fired.add(m["family"])
            today = frame[frame.index.date == day]
            for cut in (today.index[20], today.index[40], today.index[60]):
                changed = frame.copy()
                changed.loc[changed.index > cut, ["open", "high", "low", "close"]] *= 1.03
                X._TABLE.clear()
                X.O27F._FEATURES.clear()
                again = X.entries(m, X.O27F.day_features(changed, day))
                assert {k: v for k, v in full.items() if pd.Timestamp(k) <= cut} == {k: v for k, v in again.items() if pd.Timestamp(k) <= cut}, m["family"]
    assert fired >= {"LAST_HOUR", "IB_BREAK", "SUPERTREND_VWAP"}, fired


def _daily(n=120):
    idx = pd.bdate_range(end="2026-07-09", periods=n)
    rows = []
    for i in range(n):
        c = 24000 + 200 * math.sin(i / 6.0)
        rows.append((c - 30, c + 60 + 20 * math.sin(i), c - 60, c))
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def test_daily_sides_read_only_earlier_bars_except_todays_open():
    daily = _daily()
    day = "2026-07-02"
    base = W.daily_sides(daily, [day])[day]
    later = daily.copy()
    later.loc[later.index >= pd.Timestamp(day), ["high", "low", "close"]] *= 1.05
    same = W.daily_sides(later, [day])[day]
    assert same == base, "today's high, low and close must not be read"
    opened = daily.copy()
    opened.loc[pd.Timestamp(day), "open"] += 500
    changed = W.daily_sides(opened, [day])[day]
    assert changed["gap_big"] == "HIGH" and {k: v for k, v in changed.items() if not k.startswith("gap")} == {k: v for k, v in base.items() if not k.startswith("gap")}


def test_events_and_expiry_counts():
    assert W.daily_sides(_daily(), ["2026-06-05"])["2026-06-05"]["event"] == "HIGH"
    assert W.daily_sides(_daily(), ["2026-06-04"])["2026-06-04"]["event"] == "LOW"
    sides = W.dte_sides(["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"], ["2026-01-07"])
    assert [sides[d]["dte_band"] for d in sorted(sides)] == ["2", "1", "0", "3P"]


def test_filters():
    now = datetime(2026, 7, 10, 11, 0)
    f = X.filter_reason
    side = {"adx_value": 28.0, "gap_dir": "UP"}
    assert f({"only_dir": "SHORT"}, side, "LONG", None, now) == "only_dir" and f({"only_dir": "SHORT"}, side, "SHORT", None, now) is None
    assert f({"calls_min_adx": 30}, side, "LONG", None, now) == "calls_min_adx" and f({"calls_min_adx": 30}, side, "SHORT", None, now) is None
    assert f({"calls_min_adx": 30}, {"adx_value": 30.0}, "LONG", None, now) is None
    assert f({"gap": "with"}, side, "LONG", None, now) is None and f({"gap": "with"}, side, "SHORT", None, now) == "gap"
    assert f({"gap": "against"}, side, "LONG", None, now) == "gap" and f({"gap": "against"}, side, "SHORT", None, now) is None
    assert f({"gap": "with"}, {}, "LONG", None, now) == "gap", "no gap reading: no entry"
    assert f({"clock": [630, 720]}, side, "LONG", None, now) is None
    assert f({"clock": [630, 720]}, side, "LONG", None, datetime(2026, 7, 10, 12, 0)) == "clock"


def test_books_change_one_thing_and_the_rule_stays_on():
    b = X.books()
    assert b["EX|MAIN"]["skip"] == 0.5 and b["EX|MAIN"]["cost"] == [200.0, 5.0] and b["EX|MAIN"]["cfg"] == {} and "o31e" not in b["EX|MAIN"]
    assert all(m["gate"] == "adx_abs30:HIGH" for m in b["EX|MAIN"]["members"])
    assert b["EX|C|puts_only"]["only_dir"] == "SHORT" and b["EX|C|puts_only"]["skip"] == 0.5 and b["EX|C|puts_only"]["o31e"] == 1
    assert b["RAW|C|puts_only"]["cfg"]["FNO_MAX_LOTS"] == 1 and "cost" not in b["RAW|C|puts_only"]
    assert all(m["gate"] == "adx_abs25:HIGH" for m in b["EX|D|puts_from_25"]["members"]) and b["EX|D|puts_from_25"]["calls_min_adx"] == 30
    assert [m.get("name") for m in b["EX|C|no_eff"]["members"]] == ["SHIPPED", "OR20", "TPB"]
    assert b["RAW|E|last_hour_every_day"]["cfg"]["FNO_HARD_FLAT_MIN"] == 925 and "skip" not in b["RAW|E|last_hour_every_day"]
    assert sum(n.startswith("RANDOM|") for n in b) == 20 and "o31e" not in b["RANDOM|03|closed"]
    assert len({X.Y.digest(v) for v in b.values()}) == len(b)


def _exact(nets, falls=(0.05, 0.05, 0.05), trades=(30, 30, 30), weekly=None):
    return {"years": {y: {"net": n, "fall_pct": f, "trades": t} for y, n, f, t in zip(A.YEARS, nets, falls, trades)}, "weekly": weekly or [0.0] * 20}


def test_change_rules():
    base = _exact((100, 100, 100))
    good = [10.0, 12.0, 8.0, 11.0] * 5
    assert A.judge_change(_exact((200, 200, 200), weekly=good), base)["improves"]
    assert not A.judge_change(_exact((200, 200, 99), weekly=good), base)["improves"]
    assert not A.judge_change(_exact((200, 200, 200), falls=(0.05, 0.05, 0.07), weekly=good), base)["improves"]
    assert not A.judge_change(_exact((200, 200, 200), trades=(30, 14, 30), weekly=good), base)["improves"]
    assert not A.judge_change(_exact((200, 200, 200), weekly=[100.0, -99.0] * 10), base)["improves"]
    assert A.judge_change(_exact((500, 1, 1), weekly=good), base)["better_balance"], "may move money between years"
    assert not A.judge_change(_exact((500, -1, 1), weekly=good), base)["better_balance"], "positive every year"
    assert not A.judge_change(_exact((500, 1, 1), falls=(0.13, 0.05, 0.05), weekly=good), base)["better_balance"], "fall limit"


def _lot(nets, trades=(20, 20, 20), weekly=None):
    return {"years": {y: {"net": n, "trades": t} for y, n, t in zip(A.YEARS, nets, trades)}, "total": sum(nets), "worst_year": min(nets), "weekly": weekly or [10.0, 12.0, 8.0, 11.0] * 5}


def test_specialist_rules_are_against_sitting_out_and_the_random_books():
    assert A.judge_specialist(_lot((10, 10, 10)), -50)["passes"]
    assert not A.judge_specialist(_lot((10, 10, -1)), -50)["passes"]
    assert not A.judge_specialist(_lot((10, 10, 10)), 50)["passes"], "must beat the best random book"
    assert not A.judge_specialist(_lot((10, 10, 10), trades=(7, 20, 20)), -50)["passes"]
    assert not A.judge_specialist(_lot((10, 10, 10), trades=(13, 13, 13)), -50)["passes"], "40 in all"
    assert not A.judge_specialist(_lot((10, 10, 10), weekly=[100.0, -99.0] * 10), -50)["passes"]


def test_selection_luck_scores_the_year_it_did_not_choose_on():
    rows = {"MAIN": _exact((10, 10, 10)), "A": _exact((100, 100, -500)), "B": _exact((-500, 100, 100))}
    out = A.held_out_changes(rows)
    assert out["2026"]["pick"] == "A" and not out["2026"]["beat_main"]
    assert out["2024"]["pick"] == "B" and not out["2024"]["beat_main"]
    lots = {"A": _lot((100, 100, -5)), "B": _lot((-5, 100, 100))}
    assert A.held_out_specialists(lots)["2026"] == {"pick": "A", "net_on_held_out": -5, "earned": False}
