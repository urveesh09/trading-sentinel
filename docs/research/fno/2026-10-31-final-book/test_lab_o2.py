"""O31c checks: the books are what they say, the sides read only earlier bars, and the frozen decisions follow their rules."""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_o2 as A  # noqa: E402
import lab_o2 as X  # noqa: E402


def test_books():
    b = X.books()
    assert b["SURFACE|A30|S50"]["members"][0]["gate"] == "adx_abs30:HIGH" and b["SURFACE|A30|S50"]["skip"] == 0.5
    assert "skip" not in b["SURFACE|A25|Snone"] and "cost" not in b["SURFACE|A25|Snone"]
    assert b["SURFACE|A25|S50"]["cfg"]["FNO_MAX_LOTS"] == 1 and b["SURFACE|A25|S50"]["cfg"]["FNO_TWO_STRIKE_LOSSES"] == 1_000_000
    assert b["EXACT|A27"]["cost"] == [200.0, 5.0] and b["EXACT|A27"]["cfg"] == {} and b["EXACT|A27"]["skip"] == 0.5
    assert "cost" not in b["EXACT|A30|AS"]
    assert sum(n.startswith("RANDOM|") for n in b) == 40 and sum(n.startswith("SURFACE|") for n in b) == 36
    r = b["RANDOM|03|A30"]
    assert r["skip"] == 0.5 and all(m["gate"] == "adx_abs30:HIGH" for m in r["members"]) and r["members"] != b["RANDOM|04|A30"]["members"]


def test_adx_sides_read_only_earlier_bars():
    adx = pd.Series(20.0, index=pd.date_range("2023-09-01", "2024-01-10", freq="D"))
    adx.loc[pd.Timestamp("2024-01-01"):] = 90.0
    rows = {"2024-01-01": {"side": {}}, "2024-01-02": {"side": {}}}
    X.adx_sides(rows, adx)
    assert rows["2024-01-01"]["side"]["adx_abs35"] == "LOW" and rows["2024-01-02"]["side"]["adx_abs35"] == "HIGH"


def _s(total, fall=1000):
    return {"total": total, "fall": fall}


def test_rule_plateau_needs_all_three_limits_above_no_rule():
    s = {"A25|Snone": _s(0), "A25|S25": _s(-5), "A25|S35": _s(5), "A25|S50": _s(9), "A25|S65": _s(2), "A25|S75": _s(-3)}
    assert A.rule_plateau(s)["on_plateau"]
    s["A25|S65"] = _s(-1)
    assert not A.rule_plateau(s)["on_plateau"]


def test_adx_plateau_needs_money_every_year_and_lower_falls():
    good = {"years": {"2024": 1, "2025": 1, "2026": 1}}
    exact = {"A28": good, "A30": good, "A32": good}
    s = {"A25|S50": _s(0, 1000), "A27|S50": _s(0, 900), "A30|S50": _s(0, 800), "A32|S50": _s(0, 700)}
    assert A.adx_plateau(exact, s)["on_plateau"]
    assert not A.adx_plateau({**exact, "A32": {"years": {"2024": -1, "2025": 1, "2026": 1}}}, s)["on_plateau"]
    assert not A.adx_plateau(exact, {**s, "A27|S50": _s(0, 1000)})["on_plateau"]


def test_final_call_follows_the_rule():
    assert "ADX 30" in A.final_call(True, True) and "rule" in A.final_call(True, True)
    assert "ADX 25" in A.final_call(True, False)
    assert "paper only" in A.final_call(False, True)
    assert "live today" in A.final_call(False, False)
