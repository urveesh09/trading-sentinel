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


def test_lifecycle_collection_bounds_and_coverage_only_rule(tmp_path):
    path = tmp_path / "test.db"
    seed(path)
    before = path.read_bytes()
    result = module.collect(str(path), "2026-08-11", "2026-08-20", [], 2, "lifecycle")
    assert result["tickers"] == ["AAA", "BBB"] and result["strategy"] == "lifecycle"
    assert result["selection_rule"].startswith("ALPHABETICAL_AT_LEAST_ONE_COMPLETE_375_BAR")
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match="40 tickers"):
        module.collect(str(path), "2026-08-11", "2026-08-20", [], 41, "lifecycle")
    with pytest.raises(ValueError, match="20 tickers"):
        module.collect(str(path), "2026-08-11", "2026-08-20", [], 21)


def test_lifecycle_replay_validates_rows_and_reports_lifecycle_scope(tmp_path):
    path = tmp_path / "test.db"
    seed(path)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO intraday_cache VALUES('AAA','15minute','2026-08-11 09:15:00',10,11,9,10,100)")
    rejected = module.replay_lifecycle(module.collect(str(path), "2026-08-11", "2026-08-11", ["AAA"], 1, "lifecycle"))
    assert rejected["status"] == "UNAVAILABLE"  # seed has weekend daily rows inside the warm-up
    assert rejected["result"]["coverage"]["exclusions"][0]["reason"] == "off_calendar_daily_row_in_warmup"
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM ohlcv_cache WHERE strftime('%w',date) IN ('0','6')")
    report = module.replay_lifecycle(module.collect(str(path), "2026-08-11", "2026-08-11", ["AAA"], 1, "lifecycle"))
    assert report["strategy_id"] == "penny_breakout_mis_lifecycle_1m"
    assert report["result"]["scope"] == "LIFECYCLE"
    coverage = report["result"]["datasets"]["intraday"]
    assert coverage["row_counts"]["by_label"] == {"15minute": 1, "minute": 375}
    assert report["status"] == "COMPLETE" and report["summary"]["net_pnl"] is None  # no trades: no P&L
    assert report["result"]["funnel"]["evaluations"] > 0
    assert set(report["source_sha256"]) >= {"penny_lifecycle_replay.py", "research_data_contracts.py"}
    assert report["can_place_orders"] is False and report["can_qualify"] is False


def test_cnc_collector_reads_only_the_morning_slice_and_validates_end_to_end(tmp_path):
    path = tmp_path / "cnc.db"
    seed(path)
    with sqlite3.connect(path) as db:   # add >= 250 prior daily rows for AAA (weekdays only)
        day, added = datetime(2026, 8, 10), 0
        while added < 260:
            day -= timedelta(days=1)
            if day.weekday() < 5:
                db.execute("INSERT INTO ohlcv_cache VALUES(?,?,?,?,?,?,?)",
                           ("AAA", day.date().isoformat(), 10, 11, 9, 10, 1000))
                added += 1
    snapshot = module.collect(str(path), "2026-08-11", "2026-08-11", [], 1, "cnc")
    assert snapshot["tickers"] == ["AAA"] and snapshot["strategy"] == "cnc"
    assert {row[2][11:16] for row in snapshot["intraday"]} <= {f"09:{m:02d}" for m in range(15, 31)}
    report = module.replay_cnc(snapshot)
    assert report["strategy_id"] == "penny_cnc_connors_lifecycle_1d"
    assert report["result"]["scope"] == "LIFECYCLE" and report["can_place_orders"] is False
    assert report["result"]["funnel"]["evaluations"] == 1
