"""[WORKFLOW-H H3 2026-09-13] Intraday-cache diagnostic acceptance.

Closes H3 of workstream H per
``docs/2026-09-13-workflow-f-state-of-codebase-audit.md`` section 14
future plan and ``docs/NEXT_AGENT_PLAN.md`` row H.

Acceptance coverage for ``python-engine/intraday_cache_diagnostic.py``.

[WHY-THIS-EXISTS 2026-09-13]
  Pre-fix, the audit doc claimed "zero intraday-cache hit rates"
  without distinguishing true-zero-callers from freshness-gated
  misses from cold cache. The H3 diagnostic surfaces every caller
  (cached vs uncached), classifies the existing rows by freshness,
  and audits the key shape for the section-12 cross-account /
  cross-token invariant. Read-only; no schema changes.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pytest

import intraday_cache_diagnostic
from intraday_cache_diagnostic import (
    CACHED_CALLER_SITES,
    UNCACHED_CALLER_SITES,
    _INTERVAL_MINUTES,
    _render_conclusion,
    audit_key_shape,
    cache_freshness_window,
    cache_interval_breakdown,
    cache_row_counts,
    init_intraday_cache_diag_db,
    main,
    run_diagnostic,
)


# ---- helpers ---------------------------------------------------------------

@pytest.fixture
def cache_db(tmp_path):
    """A fresh cache.db per test with the intraday_cache table."""
    db = str(tmp_path / "cache.db")
    init_intraday_cache_diag_db(db)
    yield db


def _insert_row(
    db: str,
    *,
    ticker: str = "TCS",
    interval: str = "minute",
    dt: datetime = None,
    fetched_at: datetime = None,
):
    """Insert one row into intraday_cache. dt / fetched_at default to now.

    NB: the PRIMARY KEY is (ticker, interval, datetime). Tests that
    insert multiple rows with the same (ticker, datetime) but
    different intervals MUST vary the ticker so the PRIMARY KEY
    is unique.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    if fetched_at is None:
        fetched_at = datetime.now(timezone.utc)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO intraday_cache VALUES (?,?,?,?,?,?,?,?,?)",
            (
                ticker,
                interval,
                dt.strftime("%Y-%m-%d %H:%M:%S"),
                100.0, 101.0, 99.0, 100.5, 1000,
                fetched_at.isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


# ---- init / table_exists ---------------------------------------------------

class TestInit:
    def test_init_creates_table(self, cache_db: str) -> None:
        """init_intraday_cache_diag_db is idempotent and creates
        the table matching kite_client._create_intraday_cache_table.
        """
        conn = sqlite3.connect(cache_db)
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='intraday_cache'"
            ).fetchone()
            assert row is not None
            # Schema matches the kite_client schema.
            cols = [str(r[1]) for r in conn.execute(
                "PRAGMA table_info(intraday_cache)"
            ).fetchall()]
            assert cols == [
                "ticker", "interval", "datetime",
                "open", "high", "low", "close", "volume",
                "fetched_at",
            ]
        finally:
            conn.close()

    def test_init_is_idempotent(self, cache_db: str) -> None:
        init_intraday_cache_diag_db(cache_db)
        init_intraday_cache_diag_db(cache_db)
        # No exception; the table is still there.
        conn = sqlite3.connect(cache_db)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='intraday_cache'"
            ).fetchone()
            assert row[0] == 1
        finally:
            conn.close()


# ---- row counts ------------------------------------------------------------

class TestRowCounts:
    def test_empty_table_returns_zero_counts(self, cache_db: str) -> None:
        out = cache_row_counts(cache_db)
        assert out["table_present"] is True
        assert out["total_rows"] == 0
        assert out["distinct_sessions"] == 0
        assert out["distinct_tickers"] == 0
        assert out["distinct_intervals"] == 0

    def test_after_inserts(self, cache_db: str) -> None:
        _insert_row(cache_db, ticker="TCS")
        _insert_row(cache_db, ticker="INFY")
        _insert_row(cache_db, ticker="HDFC")
        out = cache_row_counts(cache_db)
        assert out["total_rows"] == 3
        assert out["distinct_tickers"] == 3
        assert out["distinct_intervals"] == 1

    def test_distinct_sessions_counted_by_date(self, cache_db: str) -> None:
        today = datetime.now(timezone.utc)
        yesterday = today - timedelta(days=1)
        _insert_row(cache_db, ticker="TCS", dt=today)
        _insert_row(cache_db, ticker="INFY", dt=today)
        _insert_row(cache_db, ticker="HDFC", dt=yesterday)
        out = cache_row_counts(cache_db)
        assert out["distinct_sessions"] == 2

    def test_fresh_db_returns_zero_rows(self, tmp_path) -> None:
        # A path that doesn't exist: the diagnostic self-heals by
        # creating the intraday_cache table on first run (matches
        # kite_client behaviour). The table is present, but with
        # zero rows -- which is the most honest signal: no callers
        # have populated it yet.
        missing = str(tmp_path / "no_such.db")
        out = cache_row_counts(missing)
        assert out["table_present"] is True
        assert out["total_rows"] == 0


# ---- interval breakdown ----------------------------------------------------

class TestIntervalBreakdown:
    def test_single_interval(self, cache_db: str) -> None:
        _insert_row(cache_db, ticker="TCS", interval="minute")
        _insert_row(cache_db, ticker="INFY", interval="minute")
        out = cache_interval_breakdown(cache_db)
        assert out == {"minute": 2}

    def test_multiple_intervals_sorted_desc(self, cache_db: str) -> None:
        # Vary ticker per insertion so the PRIMARY KEY
        # (ticker, interval, datetime) stays unique across rows
        # with the same datetime.
        for i in range(3):
            _insert_row(cache_db, ticker=f"TCS{i}", interval="minute")
        for _ in range(1):
            _insert_row(cache_db, ticker="NIFTY", interval="5minute")
        for i in range(2):
            _insert_row(cache_db, ticker=f"BANKNIFTY{i}", interval="15minute")
        out = cache_interval_breakdown(cache_db)
        # Order is descending by count.
        keys = list(out.keys())
        assert keys == sorted(keys, key=lambda k: -out[k])
        assert out == {"minute": 3, "15minute": 2, "5minute": 1}


# ---- freshness -------------------------------------------------------------

class TestFreshness:
    def test_fresh_row_classified_fresh(self, cache_db: str) -> None:
        now = datetime.now(timezone.utc)
        # Same minute as now_utc => fresh.
        fresh_dt = now - timedelta(seconds=10)
        _insert_row(cache_db, ticker="TCS", dt=fresh_dt, interval="minute")
        out = cache_freshness_window(cache_db, interval="minute", now_utc=now)
        assert out["fresh_count"] == 1
        assert out["completed_count"] == 0

    def test_stale_row_classified_completed(self, cache_db: str) -> None:
        now = datetime.now(timezone.utc)
        stale_dt = now - timedelta(hours=2)
        _insert_row(cache_db, ticker="TCS", dt=stale_dt, interval="minute")
        out = cache_freshness_window(cache_db, interval="minute", now_utc=now)
        assert out["fresh_count"] == 0
        assert out["completed_count"] == 1

    def test_5minute_freshness_uses_5min_window(self, cache_db: str) -> None:
        now = datetime.now(timezone.utc)
        # 3 minutes ago => fresh for 5minute, completed for minute.
        three_min_ago = now - timedelta(minutes=3)
        _insert_row(cache_db, ticker="NIFTY", dt=three_min_ago, interval="5minute")
        _insert_row(cache_db, ticker="TCS", dt=three_min_ago, interval="minute")
        five_out = cache_freshness_window(cache_db, interval="5minute", now_utc=now)
        minute_out = cache_freshness_window(cache_db, interval="minute", now_utc=now)
        assert five_out["fresh_count"] == 1
        assert minute_out["fresh_count"] == 0
        assert minute_out["completed_count"] == 1

    def test_malformed_datetime_counted(self, cache_db: str) -> None:
        now = datetime.now(timezone.utc)
        # Insert directly with a malformed datetime string.
        conn = sqlite3.connect(cache_db)
        try:
            conn.execute(
                "INSERT INTO intraday_cache VALUES (?,?,?,?,?,?,?,?,?)",
                ("TCS", "minute", "garbage", 100, 101, 99, 100.5, 1000, now.isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
        out = cache_freshness_window(cache_db, interval="minute", now_utc=now)
        assert out["malformed_count"] == 1
        assert out["fresh_count"] == 0
        assert out["completed_count"] == 0

    def test_intervals_only_classify_same_interval(self, cache_db: str) -> None:
        now = datetime.now(timezone.utc)
        fresh = now - timedelta(seconds=10)
        _insert_row(cache_db, ticker="TCS", dt=fresh, interval="minute")
        _insert_row(cache_db, ticker="NIFTY", dt=fresh, interval="5minute")
        # Asking for minute returns ONLY minute rows.
        out = cache_freshness_window(cache_db, interval="minute", now_utc=now)
        assert out["total_for_interval"] == 1


# ---- key-shape audit -------------------------------------------------------

class TestKeyAudit:
    def test_compliant_key_shape_no_violations(self, cache_db: str) -> None:
        out = audit_key_shape(cache_db)
        assert out["violations"] == []
        assert out["primary_key_columns"] == ["ticker", "interval", "datetime"]

    def test_violation_detected_for_account_id(self, cache_db: str) -> None:
        # Synthesise a violation by adding a forbidden column. We
        # do this through direct DDL -- the diagnostic must surface
        # it.
        conn = sqlite3.connect(cache_db)
        try:
            conn.execute("ALTER TABLE intraday_cache ADD COLUMN account_id TEXT")
            conn.commit()
        finally:
            conn.close()
        out = audit_key_shape(cache_db)
        assert any("account_id" in v for v in out["violations"])

    def test_violation_detected_for_coin_token(self, cache_db: str) -> None:
        conn = sqlite3.connect(cache_db)
        try:
            conn.execute("ALTER TABLE intraday_cache ADD COLUMN coin_token TEXT")
            conn.commit()
        finally:
            conn.close()
        out = audit_key_shape(cache_db)
        assert any("coin_token" in v for v in out["violations"])


# ---- caller-site inventory -------------------------------------------------

class TestCallerInventory:
    def test_cached_callers_includes_penny_scanner_and_main(self) -> None:
        sites = {c[0] for c in CACHED_CALLER_SITES}
        assert "penny_scanner.py" in sites
        assert "main.py" in sites

    def test_uncached_callers_includes_fno_and_partner(self) -> None:
        sites = {c[0] for c in UNCACHED_CALLER_SITES}
        assert "fno_orchestrator.py" in sites
        assert "fno_signal_scan.py" in sites
        assert "partner_orchestrator.py" in sites

    def test_interval_minutes_covers_documented_set(self) -> None:
        # The freshness gate in kite_client.get_intraday uses these
        # intervals; the diagnostic must understand them.
        assert _INTERVAL_MINUTES["minute"] == 1
        assert _INTERVAL_MINUTES["5minute"] == 5
        assert _INTERVAL_MINUTES["15minute"] == 15
        assert _INTERVAL_MINUTES["30minute"] == 30
        assert _INTERVAL_MINUTES["60minute"] == 60
        assert _INTERVAL_MINUTES["day"] == 1440


# ---- run_diagnostic (end-to-end) -------------------------------------------

class TestRunDiagnostic:
    def test_empty_db(self, cache_db: str) -> None:
        result = run_diagnostic(cache_db, interval="minute")
        assert result["row_counts"]["total_rows"] == 0
        # Conclusion text: COLD (zero rows) + zero-hits explanation.
        assert "COLD" in result["rendered"]
        assert "zero rows" in result["rendered"]
        assert result["key_audit"]["violations"] == []

    def test_partial_warm_db(self, cache_db: str) -> None:
        now = datetime.now(timezone.utc)
        # One fresh, one stale.
        _insert_row(cache_db, ticker="TCS", dt=now - timedelta(seconds=10))
        _insert_row(
            cache_db, ticker="INFY", dt=now - timedelta(hours=2),
        )
        result = run_diagnostic(cache_db, interval="minute", now_utc=now)
        assert "1/2 rows would serve a HIT today" in result["rendered"]
        assert "fresh rows ARE eligible" in result["rendered"]

    def test_full_warm_db(self, cache_db: str) -> None:
        # Vary ticker so the PRIMARY KEY stays unique across the 5 rows.
        now = datetime.now(timezone.utc)
        for i in range(5):
            _insert_row(
                cache_db,
                ticker=f"TCS{i}",
                dt=now - timedelta(seconds=10),
            )
        result = run_diagnostic(cache_db, interval="minute", now_utc=now)
        assert "5/5" in result["rendered"]


# ---- CLI ------------------------------------------------------------------

class TestCli:
    def test_main_runs_and_writes_output(self, cache_db: str) -> None:
        output_path = cache_db + ".out.json"
        rc = main([
            "--db", cache_db, "--interval", "minute", "--output", output_path,
        ])
        assert rc == 0
        with open(output_path) as f:
            data = json.load(f)
        assert data["ok"] is True
        assert data["db_path"] == cache_db
        assert data["interval"] == "minute"
        assert "row_counts" in data
        assert "interval_breakdown" in data
        assert "freshness" in data
        assert "key_audit" in data

    def test_missing_db_self_heals(self, tmp_path) -> None:
        # A path that doesn't exist: the diagnostic creates the table
        # on first run. The diagnostic must NOT crash.
        missing = str(tmp_path / "missing.db")
        output_path = str(tmp_path / "out.json")
        rc = main([
            "--db", missing, "--interval", "minute", "--output", output_path,
        ])
        assert rc == 0
        with open(output_path) as f:
            data = json.load(f)
        # table_present is True because we just created it; the
        # rows are zero because no caller has populated them.
        assert data["row_counts"]["table_present"] is True
        assert data["row_counts"]["total_rows"] == 0
        assert data["freshness"]["table_present"] is True
        assert data["key_audit"]["table_present"] is True

    def test_validation_error_returns_nonzero(self, tmp_path) -> None:
        # --db is required.
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 2


# ---- repro determinism -----------------------------------------------------

class TestReproducibility:
    def test_same_db_same_result(self, cache_db: str) -> None:
        now = datetime.now(timezone.utc)
        _insert_row(cache_db, ticker="TCS", dt=now - timedelta(seconds=10))
        r1 = run_diagnostic(cache_db, interval="minute", now_utc=now)
        r2 = run_diagnostic(cache_db, interval="minute", now_utc=now)
        # The structured parts are byte-identical. The rendered text
        # contains the timestamp which is the same now_utc.
        assert r1["row_counts"] == r2["row_counts"]
        assert r1["interval_breakdown"] == r2["interval_breakdown"]
        assert r1["freshness"]["fresh_count"] == r2["freshness"]["fresh_count"]
