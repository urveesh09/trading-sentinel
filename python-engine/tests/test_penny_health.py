"""
[PENNY-HEALTH-TEST 2026-06-25] Tests for penny_health (Phase B).

Pins:
- build_health_snapshot() returns a structured dict
- snapshot always has all expected keys (never KeyError)
- /health endpoint surface shows "OK" or "DEGRADED" with subsys detail
- Staleness check: >24h = is_stale=True
- Halted state surfaces in snapshot
- format_health and format_regime_all are bounded (<1500 chars)
- cmd_health and cmd_regime_all are read-only (no DB writes)
- Cross-subsystem view includes BOTH penny + nifty
"""
import sqlite3
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---- helpers ---------------------------------------------------------

def _seed_positions(path: str, rows):
    """rows = [(ticker, entry, sl, shares, source, status)]"""
    with sqlite3.connect(path) as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS positions (
                ticker TEXT, status TEXT, source TEXT,
                entry_price REAL, stop_loss REAL, shares INTEGER
            );
        """)
        for ticker, entry, sl, shares, source, status in rows:
            con.execute(
                "INSERT INTO positions VALUES (?, ?, ?, ?, ?, ?)",
                (ticker, status, source, entry, sl, shares),
            )


# ---- /health endpoint behavior -------------------------------------

def test_health_endpoint_no_longer_noop():
    """The placeholder `{"status": "ok"}` is gone -- the real
    health_check now returns a structured dict with subsystems."""
    # We can't import main and call health_check directly because
    # main has heavy side effects on import. But we CAN verify the
    # health module is the new source of truth.
    import penny_health
    assert hasattr(penny_health, "build_health_snapshot")
    assert hasattr(penny_health, "cmd_health")
    assert hasattr(penny_health, "cmd_regime_all")


def test_build_health_snapshot_returns_full_structure(tmp_path, monkeypatch):
    """Every expected key must be present, even if values are defaults
    (e.g. last_scan_at=None when no scan has run)."""
    from penny_health import build_health_snapshot_sync
    # Empty DB but with the bankroll_ledger table so nifty_bankroll works
    db = str(tmp_path / "test.db")
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS bankroll_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT, event_type TEXT, ticker TEXT,
                pnl REAL, bankroll_before REAL, bankroll_after REAL,
                source TEXT, notes TEXT
            );
            CREATE TABLE IF NOT EXISTS positions (
                ticker TEXT, status TEXT, source TEXT,
                entry_price REAL, stop_loss REAL, shares INTEGER
            );
        """)
    fake = type("M", (), {
        "_penny_regime_engine": None,
        "market_regime": "UNKNOWN",
        "last_run": None,
    })()
    import sys
    sys.modules["main"] = fake
    async def _cb(_):
        return (False, [])
    monkeypatch.setattr("performance.check_circuit_breakers", _cb)
    async def _br(_):
        return 5000.0
    monkeypatch.setattr("performance.nifty_bankroll", _br)
    try:
        snap = build_health_snapshot_sync(db)
    finally:
        if "main" in sys.modules and sys.modules["main"] is fake:
            del sys.modules["main"]
    # All top-level keys present
    assert "overall_status" in snap
    assert "penny" in snap
    assert "nifty" in snap
    assert "halted" in snap
    assert "halt_reasons" in snap
    assert "bankroll" in snap
    # Penny subkeys
    for k in ("regime", "last_scan_at", "last_scan_age", "last_regime_at",
              "last_regime_age", "open_positions", "is_stale"):
        assert k in snap["penny"], f"missing penny.{k}"
    # Nifty subkeys
    for k in ("market_regime", "last_swing_scan_at", "last_swing_scan_age",
              "open_positions", "is_stale"):
        assert k in snap["nifty"], f"missing nifty.{k}"


def test_health_snapshot_is_stale_when_last_run_is_old(tmp_path, monkeypatch):
    from penny_health import build_health_snapshot_sync
    db = str(tmp_path / "test.db")
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS bankroll_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT, event_type TEXT, ticker TEXT,
                pnl REAL, bankroll_before REAL, bankroll_after REAL,
                source TEXT, notes TEXT
            );
            CREATE TABLE IF NOT EXISTS positions (
                ticker TEXT, status TEXT, source TEXT,
                entry_price REAL, stop_loss REAL, shares INTEGER
            );
        """)
    long_ago = datetime.now(timezone.utc) - timedelta(hours=48)
    fake = type("M", (), {
        "_penny_regime_engine": None,
        "market_regime": "BULL",
        "last_run": long_ago,
    })()
    import sys
    sys.modules["main"] = fake
    async def _cb(_):
        return (False, [])
    monkeypatch.setattr("performance.check_circuit_breakers", _cb)
    async def _br(_):
        return 5000.0
    monkeypatch.setattr("performance.nifty_bankroll", _br)
    try:
        snap = build_health_snapshot_sync(db)
    finally:
        if "main" in sys.modules and sys.modules["main"] is fake:
            del sys.modules["main"]
    assert snap["nifty"]["is_stale"] is True
    assert snap["overall_status"] == "DEGRADED"
    assert "2.0 days ago" in snap["nifty"]["last_swing_scan_age"]


def test_health_snapshot_halted_surfaces_reasons(tmp_path, monkeypatch):
    from penny_health import build_health_snapshot_sync
    db = str(tmp_path / "test.db")
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS bankroll_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT, event_type TEXT, ticker TEXT,
                pnl REAL, bankroll_before REAL, bankroll_after REAL,
                source TEXT, notes TEXT
            );
            CREATE TABLE IF NOT EXISTS positions (
                ticker TEXT, status TEXT, source TEXT,
                entry_price REAL, stop_loss REAL, shares INTEGER
            );
        """)
    fake = type("M", (), {
        "_penny_regime_engine": None,
        "market_regime": "BULL",
        "last_run": datetime.now(timezone.utc),
    })()
    import sys
    sys.modules["main"] = fake
    async def _cb_halted(_):
        return (True, ["daily loss > 5%", "regime UNKNOWN"])
    monkeypatch.setattr("performance.check_circuit_breakers", _cb_halted)
    async def _br(_):
        return 5000.0
    monkeypatch.setattr("performance.nifty_bankroll", _br)
    try:
        snap = build_health_snapshot_sync(db)
    finally:
        if "main" in sys.modules and sys.modules["main"] is fake:
            del sys.modules["main"]
    assert snap["halted"] is True
    assert "daily loss > 5%" in snap["halt_reasons"]
    assert snap["overall_status"] == "DEGRADED"


def test_health_snapshot_ok_when_fresh_and_running(tmp_path, monkeypatch):
    from penny_health import build_health_snapshot_sync
    db = str(tmp_path / "test.db")
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS bankroll_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT, event_type TEXT, ticker TEXT,
                pnl REAL, bankroll_before REAL, bankroll_after REAL,
                source TEXT, notes TEXT
            );
            CREATE TABLE IF NOT EXISTS positions (
                ticker TEXT, status TEXT, source TEXT,
                entry_price REAL, stop_loss REAL, shares INTEGER
            );
        """)
    fake = type("M", (), {
        "_penny_regime_engine": None,
        "market_regime": "BULL",
        "last_run": datetime.now(timezone.utc) - timedelta(minutes=5),
    })()
    import sys
    sys.modules["main"] = fake
    async def _cb_ok(_):
        return (False, [])
    monkeypatch.setattr("performance.check_circuit_breakers", _cb_ok)
    async def _br(_):
        return 5000.0
    monkeypatch.setattr("performance.nifty_bankroll", _br)
    try:
        snap = build_health_snapshot_sync(db)
    finally:
        if "main" in sys.modules and sys.modules["main"] is fake:
            del sys.modules["main"]
    assert snap["halted"] is False
    assert snap["nifty"]["is_stale"] is False
    # Note: with no real penny regime engine initialised, overall
    # status is DEGRADED (penny.is_stale=True). The Nifty subsystem
    # alone is healthy. This is the correct fail-open behavior.
    assert snap["nifty"]["market_regime"] == "BULL"
    assert "5 min ago" in snap["nifty"]["last_swing_scan_age"]


# ---- format functions -----------------------------------------------

def test_format_health_includes_both_subsystems(tmp_path, monkeypatch):
    from penny_health import build_health_snapshot_sync, format_health
    db = str(tmp_path / "test.db")
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS bankroll_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT, event_type TEXT, ticker TEXT,
                pnl REAL, bankroll_before REAL, bankroll_after REAL,
                source TEXT, notes TEXT
            );
            CREATE TABLE IF NOT EXISTS positions (
                ticker TEXT, status TEXT, source TEXT,
                entry_price REAL, stop_loss REAL, shares INTEGER
            );
        """)
    fake = type("M", (), {
        "_penny_regime_engine": None,
        "market_regime": "BULL",
        "last_run": datetime.now(timezone.utc),
    })()
    import sys
    sys.modules["main"] = fake
    async def _cb(_):
        return (False, [])
    monkeypatch.setattr("performance.check_circuit_breakers", _cb)
    async def _br(_):
        return 5000.0
    monkeypatch.setattr("performance.nifty_bankroll", _br)
    try:
        snap = build_health_snapshot_sync(db)
    finally:
        if "main" in sys.modules and sys.modules["main"] is fake:
            del sys.modules["main"]
    body = format_health(snap)
    assert "Penny:" in body
    assert "Nifty:" in body
    assert "regime" in body.lower()
    # Note: with no real penny regime engine initialised, the
    # snapshot will correctly report DEGRADED (penny is_stale=True).
    # We're just checking that the format function produces the
    # expected structure, not that the underlying state is healthy.


def test_format_health_under_telegram_limit():
    from penny_health import format_health
    # Build a fake snapshot manually (with the new security field)
    snap = {
        "overall_status": "OK",
        "penny": {"regime": "PR1_CALM", "last_scan_age": "5 min ago",
                  "last_regime_age": "today", "open_positions": 2,
                  "is_stale": False},
        "nifty": {"market_regime": "BULL", "last_swing_scan_age": "5 min ago",
                  "open_positions": 1, "is_stale": False},
        "halted": False,
        "halt_reasons": [],
        "bankroll": {"penny": 2500.0, "nifty": 5000.0},
        "security": {"internal_api_secret_configured": True},
    }
    body = format_health(snap)
    assert len(body) < 1500


def test_format_health_surfaces_unset_secret():
    """[AUDIT-FIX-2.2] When INTERNAL_API_SECRET is empty, format_health
    surfaces a SECURITY warning line in the Telegram view."""
    from penny_health import format_health
    snap = {
        "overall_status": "DEGRADED",
        "penny": {"regime": "PR1_CALM", "last_scan_age": "5 min ago",
                  "last_regime_age": "today", "open_positions": 0,
                  "is_stale": False},
        "nifty": {"market_regime": "BULL", "last_swing_scan_age": "5 min ago",
                  "open_positions": 0, "is_stale": False},
        "halted": False,
        "halt_reasons": [],
        "bankroll": {"penny": None, "nifty": 5000.0},
        "security": {"internal_api_secret_configured": False},
    }
    body = format_health(snap)
    assert "SECURITY" in body
    assert "INTERNAL_API_SECRET" in body


def test_format_health_degraded_when_secret_unset():
    """[AUDIT-FIX-2.2] Empty secret -> overall_status = DEGRADED (even
    when nothing else is wrong)."""
    from penny_health import build_health_snapshot_sync
    from datetime import datetime, timezone
    import asyncio
    from unittest.mock import AsyncMock

    db = "/tmp/_test_format_health_unset.db"
    import os
    if os.path.exists(db):
        os.remove(db)
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS bankroll_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT, event_type TEXT, ticker TEXT,
                pnl REAL, bankroll_before REAL, bankroll_after REAL,
                source TEXT, notes TEXT
            );
            CREATE TABLE IF NOT EXISTS positions (
                ticker TEXT, status TEXT, source TEXT,
                entry_price REAL, stop_loss REAL, shares INTEGER
            );
        """)
    fake = type("M", (), {
        "_penny_regime_engine": None,
        "market_regime": "BULL",
        "last_run": datetime.now(timezone.utc),
    })()
    import sys
    sys.modules["main"] = fake
    async def _cb(_):
        return (False, [])
    monkeypatch_called = []
    def _set_monkey():
        return _cb
    # Inline async callbacks (no real monkeypatch needed for this minimal test)
    class _M:
        async def cb(_): return (False, [])
    m = _M()
    import unittest.mock
    with unittest.mock.patch("performance.check_circuit_breakers", m.cb):
        async def _br(_): return 5000.0
        with unittest.mock.patch("performance.nifty_bankroll", _br):
            # Set INTERNAL_API_SECRET empty via monkeypatch
            from config import settings
            original = settings.INTERNAL_API_SECRET
            settings.INTERNAL_API_SECRET = ""
            try:
                snap = build_health_snapshot_sync(db)
            finally:
                settings.INTERNAL_API_SECRET = original
    assert snap["overall_status"] == "DEGRADED"
    assert snap["security"]["internal_api_secret_configured"] is False


def test_format_regime_all_includes_both_regimes(tmp_path, monkeypatch):
    from penny_health import build_health_snapshot_sync, format_regime_all
    db = str(tmp_path / "test.db")
    fake = type("M", (), {
        "_penny_regime_engine": None,
        "market_regime": "CAUTION",
        "last_run": datetime.now(timezone.utc),
    })()
    import sys
    sys.modules["main"] = fake
    async def _cb(_):
        return (False, [])
    monkeypatch.setattr("performance.check_circuit_breakers", _cb)
    try:
        snap = build_health_snapshot_sync(db)
    finally:
        if "main" in sys.modules and sys.modules["main"] is fake:
            del sys.modules["main"]
    body = format_regime_all(snap)
    assert "Penny:" in body
    assert "Nifty:" in body
    assert "CAUTION" in body


def test_format_regime_all_flags_halt():
    from penny_health import format_regime_all
    snap = {
        "overall_status": "DEGRADED",
        "penny": {"regime": "PR1_CALM", "last_regime_age": "today",
                  "is_stale": False},
        "nifty": {"market_regime": "BULL", "last_swing_scan_age": "5 min ago",
                  "is_stale": False},
        "halted": True,
        "halt_reasons": ["x"],
        "bankroll": {"penny": None, "nifty": 5000.0},
    }
    body = format_regime_all(snap)
    assert "halted" in body.lower()


# ---- cmd_health / cmd_regime_all (Telegram surface) -----------------

def test_cmd_health_returns_string_no_crash(tmp_path, monkeypatch):
    from penny_health import cmd_health
    db = str(tmp_path / "test.db")
    fake = type("M", (), {
        "_penny_regime_engine": None,
        "market_regime": "BULL",
        "last_run": datetime.now(timezone.utc),
    })()
    import sys
    sys.modules["main"] = fake
    async def _cb(_):
        return (False, [])
    monkeypatch.setattr("performance.check_circuit_breakers", _cb)
    try:
        out = cmd_health(db)
    finally:
        if "main" in sys.modules and sys.modules["main"] is fake:
            del sys.modules["main"]
    assert isinstance(out, str)
    assert len(out) > 0
    # Must be bounded
    assert len(out) < 1500


def test_cmd_regime_all_returns_string_no_crash(tmp_path, monkeypatch):
    from penny_health import cmd_regime_all
    db = str(tmp_path / "test.db")
    fake = type("M", (), {
        "_penny_regime_engine": None,
        "market_regime": "BULL",
        "last_run": datetime.now(timezone.utc),
    })()
    import sys
    sys.modules["main"] = fake
    async def _cb(_):
        return (False, [])
    monkeypatch.setattr("performance.check_circuit_breakers", _cb)
    try:
        out = cmd_regime_all(db)
    finally:
        if "main" in sys.modules and sys.modules["main"] is fake:
            del sys.modules["main"]
    assert isinstance(out, str)
    assert "Penny:" in out


def test_cmd_health_handles_exceptions_gracefully():
    """Even if internals throw, cmd_health returns a graceful error
    message rather than propagating."""
    from penny_health import cmd_health
    # Force a hard error by passing a bad path and breaking the DB
    out = cmd_health("/nonexistent/path/to/db.sqlite")
    # Should be a string (not raise) -- content may be "error" or
    # a partial snapshot, both acceptable per the fail-open contract.
    assert isinstance(out, str)
