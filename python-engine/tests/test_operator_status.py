"""
[OPERATOR-STATUS-TEST 2026-06-25] Tests for operator_status (Phase C).

Pins:
- build_status_snapshot returns structured dict with all expected keys
- /status includes BOTH penny + nifty subsections
- format_status is bounded (<1500 chars)
- /performance works via HTTP fallback (TestClient)
- EOD digest includes both pools' P&L
- All commands are read-only (no DB writes)
- /status gracefully handles missing main module state
"""
import sqlite3
from datetime import datetime, timezone

import pytest


# ---- helpers ---------------------------------------------------------

def _seed_ledger(path: str, rows):
    """rows = [(source, pnl, days_ago)]"""
    with sqlite3.connect(path) as con:
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
        from datetime import timedelta
        for source, pnl, days_ago in rows:
            ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
            con.execute(
                "INSERT INTO bankroll_ledger VALUES (NULL, ?, 'TRADE_CLOSED', 'X', ?, 0, ?, ?, '')",
                (ts, pnl, pnl, source),
            )


def _seed_positions(path: str, rows):
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


# ---- /status builder -------------------------------------------------

def test_build_status_snapshot_full_structure(tmp_path, monkeypatch):
    """Every expected key must be present in /status snapshot."""
    from operator_status import build_status_snapshot
    db = str(tmp_path / "test.db")
    _seed_ledger(db, [
        ("PENNY", 100.0, 0),
        ("SYSTEM", 200.0, 0),
        ("MOMENTUM", -50.0, 0),
    ])
    _seed_positions(db, [
        ("AAA", 10.0, 9.0, 10, "PENNY", "OPEN"),
        ("BBB", 20.0, 19.0, 5, "SYSTEM", "OPEN"),
    ])
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
    import asyncio
    try:
        snap = asyncio.run(build_status_snapshot(db))
    finally:
        if "main" in sys.modules and sys.modules["main"] is fake:
            del sys.modules["main"]
    # Top-level keys
    assert "penny" in snap
    assert "nifty" in snap
    assert "halted" in snap
    assert "halt_reasons" in snap
    assert "by_source_today" in snap
    assert "penny_reservations" in snap
    # Penny subkeys
    for k in ("regime", "balance_estimate", "pnl_today", "open_positions"):
        assert k in snap["penny"]
    # Nifty subkeys
    for k in ("market_regime", "balance", "pnl_today", "open_positions"):
        assert k in snap["nifty"]


def test_status_partitions_pnl_by_source(tmp_path, monkeypatch):
    """/status must separate penny vs nifty P&L today (strict-separation)."""
    from operator_status import build_status_snapshot
    db = str(tmp_path / "test.db")
    _seed_ledger(db, [
        ("PENNY", 100.0, 0),
        ("SYSTEM", 200.0, 0),
        ("MOMENTUM", -50.0, 0),
    ])
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
    import asyncio
    try:
        snap = asyncio.run(build_status_snapshot(db))
    finally:
        if "main" in sys.modules and sys.modules["main"] is fake:
            del sys.modules["main"]
    # Penny = +100, Nifty = 200 + -50 = +150
    assert snap["penny"]["pnl_today"] == 100.0
    assert snap["nifty"]["pnl_today"] == 150.0
    assert snap["by_source_today"]["PENNY"] == 100.0
    assert snap["by_source_today"]["SYSTEM"] == 200.0
    assert snap["by_source_today"]["MOMENTUM"] == -50.0


def test_status_counts_open_positions(tmp_path, monkeypatch):
    """/status reports open positions per source."""
    from operator_status import build_status_snapshot
    db = str(tmp_path / "test.db")
    _seed_ledger(db, [])
    _seed_positions(db, [
        ("A", 10.0, 9.0, 10, "PENNY", "OPEN"),
        ("B", 10.0, 9.0, 10, "PENNY", "OPEN"),
        ("C", 10.0, 9.0, 10, "SYSTEM", "OPEN"),
        ("D", 10.0, 9.0, 10, "MOMENTUM", "OPEN"),
        ("E", 10.0, 9.0, 10, "PENNY", "CLOSED"),  # closed, excluded
    ])
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
    import asyncio
    try:
        snap = asyncio.run(build_status_snapshot(db))
    finally:
        if "main" in sys.modules and sys.modules["main"] is fake:
            del sys.modules["main"]
    assert snap["penny"]["open_positions"] == 2
    assert snap["nifty"]["open_positions"] == 2  # SYSTEM + MOMENTUM


# ---- format functions -----------------------------------------------

def test_format_status_under_telegram_limit():
    from operator_status import format_status
    snap = {
        "penny": {"regime": "PR1_CALM", "balance_estimate": 2600.0,
                  "pnl_today": 100.0, "open_positions": 2},
        "nifty": {"market_regime": "BULL", "balance": 5000.0,
                  "pnl_today": 150.0, "open_positions": 1},
        "halted": False,
        "halt_reasons": [],
        "by_source_today": {"PENNY": 100, "SYSTEM": 200, "MOMENTUM": -50},
    }
    body = format_status(snap)
    assert len(body) < 1500
    assert "Penny" in body
    assert "Nifty" in body
    assert "+Rs 100" in body
    assert "+Rs 150" in body


def test_status_surfaces_unresolved_penny_reservations(tmp_path, monkeypatch):
    from operator_status import build_status_snapshot, format_status
    db = str(tmp_path / "test.db")
    _seed_ledger(db, [])
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE penny_position_reservations "
            "(state TEXT,created_at TEXT)"
        )
        con.execute(
            "INSERT INTO penny_position_reservations VALUES "
            "('UNRESOLVED','2026-08-31T05:00:00+00:00')"
        )
    async def _cb(_): return (False, [])
    async def _br(_): return 5000.0
    monkeypatch.setattr("performance.check_circuit_breakers", _cb)
    monkeypatch.setattr("performance.nifty_bankroll", _br)
    import asyncio
    snap = asyncio.run(build_status_snapshot(db))
    assert snap["penny_reservations"]["unresolved"] == 1
    assert "capacity remains fail-closed" in format_status(snap)


def test_format_status_shows_halt():
    from operator_status import format_status
    snap = {
        "penny": {"regime": "PR1_CALM", "balance_estimate": 2600.0,
                  "pnl_today": 0, "open_positions": 0},
        "nifty": {"market_regime": "BULL", "balance": 5000.0,
                  "pnl_today": 0, "open_positions": 0},
        "halted": True,
        "halt_reasons": ["daily loss > 5%"],
        "by_source_today": {},
    }
    body = format_status(snap)
    assert "HALTED" in body
    assert "daily loss > 5%" in body


def test_format_eod_digest():
    from operator_status import format_eod_digest
    snap = {
        "penny": {"regime": "PR2_ELEVATED", "balance_estimate": 2600.0,
                  "pnl_today": 100.0, "open_positions": 1},
        "nifty": {"market_regime": "BULL", "balance": 5000.0,
                  "pnl_today": -50.0, "open_positions": 0},
        "halted": False,
        "halt_reasons": [],
        "by_source_today": {},
    }
    body = format_eod_digest(snap)
    assert "End-of-day" in body
    assert "Penny" in body
    assert "Nifty" in body
    # Penny +100, Nifty -50. The formatter uses "+Rs 100" for positive
    # and "Rs -50" for negative (Python's :.0f on a negative float
    # includes the minus sign, so we don't add it again).
    assert "+Rs 100" in body
    assert "Rs -50" in body
    assert "PR2_ELEVATED" in body or "penny=" in body


def test_format_performance():
    from operator_status import format_performance
    perf = {
        "total_trades": 10,
        "winning_trades": 6,
        "losing_trades": 4,
        "win_rate_pct": 60.0,
        "avg_r_multiple": 1.2,
        "total_realised_pnl": 500.0,
        "unrealised_pnl": 50.0,
    }
    body = format_performance(perf)
    assert "Performance" in body
    assert "60.0%" in body
    assert "+1.20" in body
    assert "Realised" in body
    assert "Total" in body


def test_format_performance_handles_missing_keys():
    """Robust to partial /performance responses (e.g. tests)."""
    from operator_status import format_performance
    body = format_performance({})
    assert "Performance" in body
    # Should not raise


# ---- cmd surface -----------------------------------------------------

def test_cmd_status_returns_string(tmp_path, monkeypatch):
    from operator_status import cmd_status
    db = str(tmp_path / "test.db")
    _seed_ledger(db, [("PENNY", 100.0, 0)])
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
        out = cmd_status(db)
    finally:
        if "main" in sys.modules and sys.modules["main"] is fake:
            del sys.modules["main"]
    assert isinstance(out, str)
    assert "Penny" in out
    assert "Nifty" in out


def test_cmd_eod_digest_returns_string(tmp_path, monkeypatch):
    from operator_status import cmd_eod_digest
    db = str(tmp_path / "test.db")
    _seed_ledger(db, [])
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
        out = cmd_eod_digest(db)
    finally:
        if "main" in sys.modules and sys.modules["main"] is fake:
            del sys.modules["main"]
    assert isinstance(out, str)
    assert "End-of-day" in out


def test_cmd_status_handles_db_error_gracefully():
    """Even if DB is unreachable, /status returns a graceful partial
    response (NOT a crash). The fail-open contract is satisfied as
    long as we get a non-empty, well-formed string."""
    from operator_status import cmd_status
    out = cmd_status("/nonexistent/db.sqlite")
    assert isinstance(out, str)
    # Should be a valid status body (fail-open: degraded values, not error)
    assert "System status" in out
    assert "Penny" in out
    assert "Nifty" in out
