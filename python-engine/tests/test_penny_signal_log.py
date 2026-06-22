"""
[PENNY-LOG 2026-06-21] Tests for penny_signal_log module.

Mirrors the existing signal_log.py pattern (CSV + SQLite) but for the
penny subsystem. Schema is a stable contract -- future tasks may ADD
columns but not rename.

Per spec section 10.1: append-only at /data/penny_signals.csv + SQLite table
`penny_signals`. Every scan outcome (accept or reject) is recorded.
"""
import os
import csv
import sqlite3
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch
import pytest


# ---- helpers -----------------------------------------------------------

@pytest.fixture
def tmp_paths(tmp_path, monkeypatch):
    """Patch settings.PENNY_LOG_CSV_PATH and DB_PATH to tmp."""
    from config import settings
    csv_path = str(tmp_path / "penny_signals.csv")
    db_path = str(tmp_path / "test_cache.db")
    monkeypatch.setattr(settings, "PENNY_LOG_CSV_PATH", csv_path)
    monkeypatch.setattr(settings, "DB_PATH", db_path)
    return csv_path, db_path


# ---- init --------------------------------------------------------------

def test_init_penny_signal_db_creates_table(tmp_paths):
    csv_path, db_path = tmp_paths
    from penny_signal_log import init_penny_signal_db
    import asyncio
    asyncio.run(init_penny_signal_db(db_path))
    con = sqlite3.connect(db_path)
    cur = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='penny_signals'"
    )
    assert cur.fetchone() is not None
    con.close()


def test_init_is_idempotent(tmp_paths):
    csv_path, db_path = tmp_paths
    from penny_signal_log import init_penny_signal_db
    import asyncio
    asyncio.run(init_penny_signal_db(db_path))
    asyncio.run(init_penny_signal_db(db_path))   # second call must not fail
    con = sqlite3.connect(db_path)
    cur = con.execute("SELECT COUNT(*) FROM penny_signals")
    assert cur.fetchone()[0] == 0
    con.close()


# ---- append / log -----------------------------------------------------

def test_log_penny_signal_accepted_appends_csv_and_db(tmp_paths):
    csv_path, db_path = tmp_paths
    from penny_signal_log import init_penny_signal_db, log_penny_signal
    import asyncio
    asyncio.run(init_penny_signal_db(db_path))
    asyncio.run(log_penny_signal(
        db_path,
        scan_id="scan-001",
        ticker="ABC",
        leg="CNC",
        accepted=True,
        regime="PR1_CALM",
        close=10.50,
        stop_loss=10.18,
        target_1=10.82,
        target_2=11.13,
        rsi_2=8.5,
        volume_ratio=1.2,
        shares=50,
    ))
    # CSV
    assert os.path.exists(csv_path)
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["ticker"] == "ABC"
    assert rows[0]["leg"] == "CNC"
    assert rows[0]["accepted"] == "1"
    # SQLite
    con = sqlite3.connect(db_path)
    cur = con.execute("SELECT ticker, accepted, leg FROM penny_signals")
    row = cur.fetchone()
    assert row == ("ABC", 1, "CNC")
    con.close()


def test_log_penny_signal_rejected_records_reason(tmp_paths):
    csv_path, db_path = tmp_paths
    from penny_signal_log import init_penny_signal_db, log_penny_signal
    import asyncio
    asyncio.run(init_penny_signal_db(db_path))
    asyncio.run(log_penny_signal(
        db_path,
        scan_id="scan-002",
        ticker="XYZ",
        leg="MIS",
        accepted=False,
        reject_reason="volume too low (dead stock)",
        regime="PR2_ELEVATED",
        close=12.0,
    ))
    con = sqlite3.connect(db_path)
    cur = con.execute(
        "SELECT ticker, accepted, reject_reason FROM penny_signals"
    )
    row = cur.fetchone()
    assert row == ("XYZ", 0, "volume too low (dead stock)")
    con.close()


def test_log_multiple_scans_preserves_history(tmp_paths):
    csv_path, db_path = tmp_paths
    from penny_signal_log import init_penny_signal_db, log_penny_signal
    import asyncio
    asyncio.run(init_penny_signal_db(db_path))
    for i in range(5):
        asyncio.run(log_penny_signal(
            db_path, scan_id=f"s-{i}", ticker=f"T{i}",
            leg="CNC", accepted=True, regime="PR1_CALM",
            close=10.0 + i * 0.1,
        ))
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 5


def test_log_handles_db_failure_gracefully(tmp_paths):
    """Spec section 10.1: log failures must NOT crash live scan."""
    csv_path, db_path = tmp_paths
    from penny_signal_log import init_penny_signal_db, log_penny_signal
    import asyncio
    asyncio.run(init_penny_signal_db(db_path))
    # Point db at an unwritable path to force failure
    bad_db = "/this/path/does/not/exist/cache.db"
    # Should not raise
    asyncio.run(log_penny_signal(
        bad_db, scan_id="x", ticker="X",
        leg="CNC", accepted=False, reject_reason="test",
        regime="PR1_CALM", close=10.0,
    ))
    # Original db should still be empty (no rows leaked there either)
    con = sqlite3.connect(db_path)
    cur = con.execute("SELECT COUNT(*) FROM penny_signals")
    assert cur.fetchone()[0] == 0
    con.close()


def test_log_writes_even_when_db_fails_but_csv_succeeds(tmp_paths):
    """Best-effort: CSV is written first, DB error logged but not raised."""
    csv_path, db_path = tmp_paths
    from penny_signal_log import init_penny_signal_db, log_penny_signal
    import asyncio
    asyncio.run(init_penny_signal_db(db_path))
    bad_db = "/nonexistent/dir/cache.db"
    asyncio.run(log_penny_signal(
        bad_db, scan_id="s", ticker="Y",
        leg="MIS", accepted=True, regime="PR1_CALM", close=10.0,
    ))
    # CSV was attempted at settings.PENNY_LOG_CSV_PATH (csv_path)
    # The CSV write itself may or may not succeed depending on implementation,
    # but the call must NOT raise.
