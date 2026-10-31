"""O31b checks: the books are what they say, and the rule judges what it says."""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_o as A  # noqa: E402
import lab_o as X  # noqa: E402


def _row(nets, falls=(0.1, 0.1, 0.1), trades=(50, 50, 50), weekly=None):
    return {"years": {y: {"net": n, "fall_pct": f, "trades": t, "worst_day": -1000, "max_lots": 2}
                      for y, n, f, t in zip(A.YEARS, nets, falls, trades)}, "weekly": weekly or [0.0] * 20}


def test_base_is_the_exam_book_and_every_variant_changes_one_thing():
    b = X.books()
    base = b["BASE"]
    live = X.L.base_book("LIVE+rule", X.L.levels()["SHIPPED"], True, "SHIPPED")
    assert base["members"] == live["members"] and base["skip"] == live["skip"] == 0.5 and base["cost"] == live["cost"] and base["cfg"] == {}
    assert "skip" not in b["SKIP|none"] and b["SKIP|none"]["cost"] == base["cost"]
    assert "cost" not in b["BASE|AS"]
    assert b["LOTS|1"]["cfg"] == {"FNO_MAX_LOTS": 1, "FNO_MAX_LOTS_PROVEN": 1} and b["LOTS|1"]["members"] == base["members"]
    assert len(b["DROP|TPB"]["members"]) == 3 and len(b["ADD|fade_closed"]["members"]) == 5
    assert b["ORDER|tpb_first"]["members"][0]["name"] == "TPB"
    assert b["DAY|drive"]["router"] == "o30m" and b["DAY|drive"]["members"][0]["gate"] == "adx_abs25:HIGH&open_drive:HIGH"
    digests = {X.Y.digest(v) for v in b.values()}
    assert len(digests) == len(b), "two variants are the same book"


def test_extra_sides_are_known_before_the_session():
    sessions = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    idx = pd.date_range(end="2023-12-31", periods=100, freq="D")
    adx = pd.Series([20.0] * 99 + [31.0], index=idx)
    rows = {d: {"side": {}} for d in sessions}
    X.extra_sides(rows, sessions, ["2024-01-04"], adx)
    assert [rows[d]["side"]["dte2"] for d in sessions[:4]] == ["HIGH", "HIGH", "LOW", "LOW"]
    assert rows["2024-01-05"]["side"]["dte2"] == "HIGH"     # next expiry unknown to the data
    assert rows["2024-01-01"]["side"]["adx_abs30"] == "HIGH", "reads the last bar before the session"
    later = pd.Series(20.0, index=pd.date_range("2023-09-01", "2024-01-10", freq="D"))
    later.loc[pd.Timestamp("2024-01-01"):] = 90.0
    rows = {"2024-01-01": {"side": {}}}
    X.extra_sides(rows, sessions, ["2024-01-04"], later)
    assert rows["2024-01-01"]["side"]["adx_abs30"] == "LOW", "today's value must not be read"


def test_improves_needs_every_year_falls_trades_and_t():
    base = _row((100, 100, 100), weekly=[0.0] * 20)
    good = [10.0, 12.0, 8.0, 11.0] * 5
    assert A.judge(_row((200, 200, 200), weekly=good), base)["improves"]
    assert not A.judge(_row((200, 200, 99), weekly=good), base)["improves"], "one year worse"
    assert not A.judge(_row((200, 200, 200), falls=(0.1, 0.1, 0.12), weekly=good), base)["improves"], "fall above the room"
    assert not A.judge(_row((200, 200, 200), trades=(50, 39, 50), weekly=good), base)["improves"], "too few trades"
    noisy = [100.0, -99.0] * 10
    assert not A.judge(_row((200, 200, 200), weekly=noisy), base)["improves"], "t below 2"


def test_safer_trades_money_for_a_lower_fall_within_limits():
    base = _row((100, 100, 100), falls=(0.1, 0.2, 0.1))
    assert A.judge(_row((95, 95, 95), falls=(0.1, 0.17, 0.1)), base)["safer"] is False, "worst year below BASE's"
    assert A.judge(_row((100, 90, 95), falls=(0.1, 0.17, 0.1)), base)["safer"] is False, "worst year below BASE's"
    assert A.judge(_row((100, 100, 80), falls=(0.1, 0.17, 0.1)), base)["safer"] is False, "worst year below BASE's"
    assert A.judge(_row((100, 100, 100), falls=(0.1, 0.17, 0.1)), base)["safer"] is True
    assert A.judge(_row((100, 100, 100), falls=(0.1, 0.19, 0.1)), base)["safer"] is False, "fall not lower by 2 points"


def test_selection_luck_scores_on_the_year_it_did_not_choose_on():
    rows = {"BASE": _row((10, 10, 10)), "A": _row((100, 100, -500)), "B": _row((-500, 100, 100))}
    out = A.held_out(rows)
    assert out["2026"]["pick"] == "A" and out["2026"]["beat_base"] is False
    assert out["2024"]["pick"] == "B" and out["2024"]["beat_base"] is False
    assert out["2025"]["pick"] == "BASE"


def test_lots_answer_respects_the_fall_limit():
    rows = {"BASE": _row((10, 10, 10)), "LOTS|1": _row((5, 5, 5), falls=(0.05, 0.05, 0.05)), "LOTS|5": _row((90, 90, 90), falls=(0.3, 0.1, 0.1))}
    assert A.lots_answer(rows)["best"] == "BASE"
