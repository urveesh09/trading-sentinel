from datetime import datetime, timedelta
import importlib.util
from pathlib import Path
import sqlite3

import pytest

SPEC = importlib.util.spec_from_file_location("penny_research_cli", Path(__file__).parents[1] / "run_penny_research.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def seed(path):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE intraday_cache(ticker TEXT,interval TEXT,datetime TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
        db.execute("CREATE TABLE ohlcv_cache(ticker TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
        for ticker in ("BBB", "AAA"):
            for minute in range(375):
                at = datetime(2026, 8, 11, 9, 15) + timedelta(minutes=minute)
                db.execute("INSERT INTO intraday_cache VALUES(?,?,?,?,?,?,?,?)", (ticker, "minute", at.isoformat(sep=" "), 10, 11, 9, 10, 100))
            for offset in range(1, 22):
                at = datetime(2026, 8, 11) - timedelta(days=offset)
                db.execute("INSERT INTO ohlcv_cache VALUES(?,?,?,?,?,?,?)", (ticker, at.date().isoformat(), 10, 11, 9, 10, 1000))


def test_alphabetical_metadata_selection_and_read_only(tmp_path):
    path = tmp_path / "test.db"
    seed(path)
    before = path.read_bytes()
    result = module.collect(str(path), "2026-08-11", "2026-08-20", [], 1)
    assert result["tickers"] == ["AAA"]
    assert len(result["intraday"]) == 375
    assert path.read_bytes() == before


def test_mixed_rows_are_not_hidden_by_collector(tmp_path):
    path = tmp_path / "test.db"
    seed(path)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO intraday_cache VALUES('AAA','15minute','2026-08-11 09:15:00',10,11,9,10,100)")
    result = module.collect(str(path), "2026-08-11", "2026-08-20", ["AAA"], 1)
    assert {row[1] for row in result["intraday"]} == {"minute", "15minute"}


def test_missing_database_not_created_and_range_bounded(tmp_path):
    path = tmp_path / "absent.db"
    with pytest.raises(sqlite3.OperationalError):
        module.collect(str(path), "2026-08-11", "2026-08-20", [], 1)
    assert not path.exists()
    with pytest.raises(ValueError):
        module.collect(str(path), "2026-08-20", "2026-08-11", [], 1)
    with pytest.raises(ValueError):
        module.collect(str(path), "2026-08-11", "2026-08-20", [], 21)


def test_current_registered_baseline_runs_without_capital_return_claim(tmp_path):
    path = tmp_path / "test.db"
    seed(path)
    report = module.replay(module.collect(str(path), "2026-08-11", "2026-08-20", ["AAA"], 1))
    assert report["strategy_id"] == "penny_breakout_intraday_1m_replay"
    assert report["request"]["config"]["variants"] == ["PEN_BASE"]
    assert report["result"]["status"] == "complete"
    assert report["metrics"]["net_return_pct"] is None
    assert report["can_place_orders"] is False
    assert report["can_qualify"] is False
