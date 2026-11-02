"""TEMPLATE checks: the entry reads only bars up to its own (change later bars, earlier answers stay), and the books."""
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab_x as X  # noqa: E402


def _frame(days=8, swing=0.004) -> pd.DataFrame:
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


def test_entry_is_causal():
    frame = _frame()
    day = frame.index[-1].date()
    m = X.member()
    X._TABLE.clear()
    X.O27F._FEATURES.clear()
    full = X.entries(m, X.O27F.day_features(frame, day))
    assert full, "the example should fire on the synthetic day; adjust the frame if the strategy changes"
    for cut in (frame.index[-50], frame.index[-30], frame.index[-10]):
        changed = frame.copy()
        changed.loc[changed.index > cut, ["open", "high", "low", "close"]] *= 1.03
        X._TABLE.clear()
        X.O27F._FEATURES.clear()
        again = X.entries(m, X.O27F.day_features(changed, day))
        assert {k: v for k, v in full.items() if pd.Timestamp(k) <= cut} == \
            {k: v for k, v in again.items() if pd.Timestamp(k) <= cut}


def test_books():
    b = X.books()
    assert sum(n.startswith("NULL") for n in b) == 20
    assert [m.get("name") or m["family"] for m in b["CAND|added_to_live"]["members"]] == \
        ["SHIPPED", "OR20", "EFF", "TPB", X.FAMILY]
    assert X.Y.digest(b["REF|LIVE"]) == X.Y.digest(X.C.books()["BASE|UNION_ADX"])
