"""O29i checks: every sideways entry reads only bars up to its own, and the book list is valid."""
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab_i  # noqa: E402


def _frame(days=8, swing=0.004) -> pd.DataFrame:
    rows, d, made = [], date(2026, 3, 2), 0
    price = 100.0
    while made < days:
        if d.weekday() < 5:
            for i in range(75):
                ts = datetime.combine(d, datetime.min.time()) + timedelta(hours=9, minutes=15 + 5 * i)
                close = 100 * (1 + swing * math.sin(i / 3.0 + made))
                rows.append((ts, price, max(price, close) * 1.0005, min(price, close) * 0.9995, close, 100 + i))
                price = close
            made += 1
        d += timedelta(days=1)
    return pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close", "volume"]).set_index("datetime")


def test_each_family_is_causal():
    frame = _frame()
    day = frame.index[-1].date()
    members = [lab_i.side_member(fam, **{k: v[0] for k, v in genes.items()}) for fam, genes in lab_i.GRID.items()]
    for m in members:
        lab_i._TABLES.clear()
        lab_i.O27F._FEATURES.clear()
        full = lab_i.side_table(m, lab_i.O27F.day_features(frame, day))
        cut = frame.index[-30]
        changed = frame.copy()
        later = changed.index > cut
        changed.loc[later, ["open", "high", "low", "close"]] *= 1.03
        lab_i._TABLES.clear()
        lab_i.O27F._FEATURES.clear()
        again = lab_i.side_table(m, lab_i.O27F.day_features(changed, day))
        early = {k: v for k, v in full.items() if pd.Timestamp(k) < cut}
        assert early == {k: v for k, v in again.items() if pd.Timestamp(k) < cut}, m["family"]


def test_the_frozen_book_list_is_sideways_only():
    books = lab_i.books()
    for name, b in books.items():
        if name == "UNION_ADX":
            assert all(m["gate"] == "adx_abs25:HIGH" for m in b["members"])
        else:
            assert all(m["gate"] == lab_i.SIDEWAYS for m in b["members"]), name
    assert sum(n.startswith("NULL") for n in books) == 20
