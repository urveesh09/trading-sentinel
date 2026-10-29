"""O29g checks: regime sides and the new families read only what was known at the time."""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab_g  # noqa: E402


def _frame(days: int, today_moves=(0.0,) * 75, seed_move=0.001) -> pd.DataFrame:
    rows, start = [], date(2026, 3, 2)
    d, made = start, 0
    while made < days:
        if d.weekday() < 5:
            price = 100.0
            for i in range(75):
                ts = datetime.combine(d, datetime.min.time()) + timedelta(hours=9, minutes=15 + 5 * i)
                move = today_moves[i] if made == days - 1 else seed_move * (1 if i % 2 else -1) * (i + 1) / 75
                close = price * (1 + move)
                rows.append((ts, price, max(price, close), min(price, close), close, 100))
            made += 1
        d += timedelta(days=1)
    f = pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close", "volume"]).set_index("datetime")
    return f


def test_noise_band_sigma_uses_only_previous_sessions():
    a = _frame(16)
    today = a.index[-1].date()
    b = a.copy()
    b.loc[b.index.date == today, "close"] *= 1.05          # rewrite today's path
    lab_g._NB.clear()
    ba = lab_g.noise_bands(a, today, 1.0)
    lab_g._NB.clear()
    bb = lab_g.noise_bands(b, today, 1.0)
    for ts in ba:
        assert ba[ts][1:] == bb[ts][1:]                    # bands are unchanged; only the close differs


def test_noise_band_needs_history_and_a_full_open():
    lab_g._NB.clear()
    short = _frame(5)
    assert lab_g.noise_bands(short, short.index[-1].date(), 1.0) is None


def test_regime_sides_are_relative_to_earlier_sessions_only(monkeypatch):
    sessions = [f"2026-01-{d:02d}" for d in range(1, 31)]
    values = {s: {"adx14": float(i), "rv20": 1.0, "ret20_abs": 1.0, "prev_range_rel": 1.0, "prev_body": 1.0}
              for i, s in enumerate(sessions)}
    monkeypatch.setattr(lab_g.F, "day_features", lambda sess, drive, weekly: values)
    rows = lab_g.regime_rows(sessions, {}, [])
    assert rows[sessions[10]]["side"]["adx14"] is None     # under 20 earlier sessions
    assert rows[sessions[25]]["side"]["adx14"] == "HIGH"   # rising: above the earlier median
    assert rows[sessions[25]]["side"]["adx_abs20"] == "HIGH" and rows[sessions[5]]["side"]["adx_abs20"] == "LOW"
    values[sessions[29]]["adx14"] = 0.0                     # a later change never alters an earlier side
    again = lab_g.regime_rows(sessions, {}, [])
    assert again[sessions[25]]["side"] == rows[sessions[25]]["side"]


def test_the_frozen_book_list_is_valid():
    books = lab_g.books()
    assert len(books) == len({lab_g.digest(b) for b in books.values()})
    for b in books.values():
        assert 1 <= len(b["members"]) <= 4
        for m in b["members"]:
            assert m["gate"] in lab_g.GATES or m["gate"] in lab_g.Y.GATES
    assert books["UNION_DRIVE_LIVE"] == lab_g.Y.FIXED["UNION_DRIVE"]
