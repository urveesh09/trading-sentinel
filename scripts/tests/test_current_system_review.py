"""Research collection preserves IST boundaries and malformed SQLite evidence."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import run_current_system_review as review


def test_offline_collector_preserves_blob_and_ist_quarter_boundaries(tmp_path):
    for name in ("penny_static.json", "nifty500.json"):
        (tmp_path / name).write_text(json.dumps({"tickers": [{"symbol": "AAA"}]}))
    db_path = tmp_path / "cache.db"
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE intraday_cache (ticker,interval,datetime,open,high,low,close,volume)")
        db.execute("CREATE TABLE ohlcv_cache (ticker,date,open,high,low,close,volume)")
        for table in ("fno_positions", "fno_dr_positions", "bankroll_ledger", "positions"):
            db.execute(f"CREATE TABLE {table} (id,value)")
        db.execute("INSERT INTO positions VALUES (1,?)", (b"\x01\x00\x00\x00",))
        for table, clock, category in (("penny_signals", "scanned_at", "leg"),
                                      ("momentum_signals", "scanned_at", "strategy_version"),
                                      ("fno_signals", "evaluated_at", "leg")):
            db.execute(f"CREATE TABLE {table} ({clock},{category},accepted,reject_reason,ticker,regime)")
            for stamp in ("2026-06-30T20:00:00+00:00", "2026-09-30T20:00:00+00:00"):
                db.execute(f"INSERT INTO {table} VALUES (?,?,?,?,?,?)", (stamp, "MIS", 1, "", "AAA", "CALM"))
        db.execute("CREATE TABLE penny_execution_events (event_type,source,event_ts)")
        db.execute("CREATE TABLE intraday_cache_by_token (instrument_token,interval,datetime)")
    before = review.sha(db_path)
    output = subprocess.check_output([sys.executable, "-B", "-"], input=review.offline_collector(tmp_path).encode())
    collected = json.loads(output, object_hook=review.decode_sqlite_blob)
    assert collected["tables"]["positions"]["rows"][0][1] == b"\x01\x00\x00\x00"
    assert collected["operational"]["penny_signals"][0]["month"] == "2026-07"
    assert collected["operational"]["penny_signals"][0]["n"] == 1
    assert len(collected["operational"]["penny_accepted"]) == 1
    assert collected["operational"]["fno_signals"][0]["n"] == 1  # October 1 IST is inside F&O window
    assert review.sha(db_path) == before


def test_unavailable_full_fno_attempt_has_no_manufactured_pnl(tmp_path):
    local = review.local(tmp_path)
    for family in ("penny", "stock"):
        (tmp_path / f"{family}_universe.json").write_text(json.dumps({"tickers": [{"symbol": "AAA"}]}))
    review.write_snapshot({"request": {"start": review.START, "end": review.FEND, "tickers": ["AAA"]},
                           "intraday": [], "daily": []}, str(local / "q3.sqlite"), source="fixture")
    review.run_job(tmp_path, "fno-full")
    report = json.loads((local / "fno-full-report.json").read_text())
    assert report["state"] == "UNAVAILABLE" and report["metrics"] is None
    assert report["scope"] == "UNAVAILABLE" and report["can_place_orders"] is False
    assert (tmp_path / "fno-full-freeze.json").exists()


def test_compact_funnel_preserves_verdict_counts_without_summing_distinct_tickers():
    source = {"penny_signals": [
        {"month": "2026-08", "category": "MIS", "accepted": 0,
         "reason": "volume 1.2 below 1.8", "n": 3, "tickers": 2},
        {"month": "2026-08", "category": "MIS", "accepted": 0,
         "reason": "volume 1.4 below 1.8", "n": 4, "tickers": 2},
        {"month": "2026-08", "category": "MIS", "accepted": 1,
         "reason": "", "n": 1, "tickers": 1},
    ], "penny_execution_events": [{"event_type": "ENTRY_FILLED", "n": 1}]}
    result = review.compact_operations(source, "sha256:fixture")
    assert {row["accepted"]: row["n"] for row in result["penny_signals"]} == {0: 7, 1: 1}
    assert all("tickers" not in row for row in result["penny_signals"])
    assert result["penny_execution_events"] == source["penny_execution_events"]
    assert source["penny_signals"][0]["reason"] == "volume 1.2 below 1.8"
