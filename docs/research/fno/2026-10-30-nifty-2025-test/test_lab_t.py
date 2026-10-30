"""O30 checks: the 2025 books are exactly the books frozen on 2026, and the sealed 2025 copy keeps only 2025."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab_t as T  # noqa: E402


def _frozen(name: str) -> dict:
    return json.loads(T.FREEZES[name].read_text(encoding="utf-8"))


def test_books_are_the_ones_frozen_on_2026():
    books, d = T.books(), T.Y.digest
    side, why, year = _frozen("o29i")["books"], _frozen("o29g")["books"], _frozen("o29f")["fixed_books"]
    assert d(books["UNION_ADX"]) == d(side["UNION_ADX"]) == d(why["UNION_ALL|adx_abs25:HIGH"])
    for name in T.SIDE_PICKS.values():
        assert d(books[name]) == d(side[name])
    for name in ("TPB|adx_abs20:HIGH", *(f"{c}|{g}" for c in T.Y.NAMED for g in ("ALWAYS", "adx_abs25:HIGH"))):
        assert d(books[name]) == d(why[name])
    assert d(books["UNION"]) == d(year["UNION"]) and d(books["UNION_DRIVE"]) == d(year["UNION_DRIVE"])
    for i in range(20):
        assert d(books[f"NULL{i:02d}|sideways"]) == d(side[f"NULL{i:02d}|sideways"])
        assert d(books[f"NULL{i:02d}|ALWAYS"]) == d(why[f"NULL{i:02d}|ALWAYS"])
        assert [m["gate"] for m in books[f"NULL{i:02d}|adx_abs25:HIGH"]["members"]] == \
            ["adx_abs25:HIGH"] * len(books[f"NULL{i:02d}|ALWAYS"]["members"])


def test_sealed_copy_holds_2025_only():
    if not T.MIRROR.is_file():
        pytest.skip("the sealed 2025 copy is local (_local/) and not built here")
    con = sqlite3.connect(f"file:{T.MIRROR.as_posix()}?mode=ro", uri=True)
    assert con.execute("SELECT COUNT(*) FROM candles WHERE datetime >= ?", (T.END,)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM candles WHERE kind != 'daily' AND datetime LIKE ?",
                       (T.MUHURAT + "%",)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(DISTINCT underlying) FROM candles WHERE kind != 'daily'").fetchone()[0] == 1
