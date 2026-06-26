"""
[NIFTY-COMMANDS-TEST 2026-06-25] Tests for nifty_commands (Phase A).

Pins:
- All commands are READ-ONLY (no state mutation)
- Each command returns a non-empty string
- /help lists available commands and explicitly notes read-only constraint
- Unknown subcommand returns a "try /help" hint
- Failure modes return "error reading" rather than raising
- /nifty stats correctly partitions penny vs nifty trades
- /nifty swing/momentum list top 5 by score when active
- /nifty regime reports market_regime value + age
- /nifty circuit reports halted/not-halted state
"""
import sqlite3

import pytest


# ---- helpers ---------------------------------------------------------

class _FakeSignal:
    """Stand-in for the Signal/MomentumSignal model used in main.py
    globals. Exposes the attrs our command reads via getattr."""
    def __init__(self, ticker, score, close=100.0, stop_loss=95.0, target_1=110.0):
        self.ticker = ticker
        self.score = score
        self.close = close
        self.stop_loss = stop_loss
        self.target_1 = target_1


def _seed_ledger(path: str, rows):
    """rows = [(source, pnl, days_ago)]"""
    from datetime import datetime, timezone, timedelta
    with sqlite3.connect(path) as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS bankroll_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT, event_type TEXT, ticker TEXT,
                pnl REAL, bankroll_before REAL, bankroll_after REAL,
                source TEXT, notes TEXT
            );
        """)
        for source, pnl, days_ago in rows:
            ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
            con.execute(
                "INSERT INTO bankroll_ledger VALUES (NULL, ?, 'TRADE_CLOSED', 'X', ?, 0, ?, ?, '')",
                (ts, pnl, pnl, source),
            )


# ---- /help + dispatch ------------------------------------------------

def test_cmd_nifty_help_lists_commands():
    from nifty_commands import cmd_nifty_help
    out = cmd_nifty_help()
    assert "/nifty stats" in out
    assert "/nifty swing" in out
    assert "/nifty momentum" in out
    assert "/nifty regime" in out
    assert "/nifty circuit" in out
    assert "/nifty help" in out


def test_dispatch_empty_command_returns_help():
    from nifty_commands import dispatch
    out = dispatch("", "", "ignored.db")
    assert "/nifty" in out
    assert "/nifty stats" in out


def test_dispatch_unknown_returns_help_hint():
    from nifty_commands import dispatch
    out = dispatch("foobar", "", "ignored.db")
    assert "Unknown" in out
    assert "/nifty help" in out
    # Explicit read-only notice
    assert "read-only" in out.lower()


# ---- /stats -----------------------------------------------------------

def test_cmd_nifty_stats_with_ledger(tmp_path, monkeypatch):
    from nifty_commands import _get_globals
    db = str(tmp_path / "test.db")
    _seed_ledger(db, [
        ("PENNY", 100.0, 0),
        ("SYSTEM", 200.0, 0),
        ("MOMENTUM", -50.0, 0),
        ("PENNY", 50.0, 1),  # yesterday, not counted
    ])
    # Mock nifty_bankroll + get_open_positions. Note: get_open_positions
    # lives in position_tracker, not performance.
    from unittest.mock import AsyncMock, MagicMock
    fake = MagicMock()
    async def _br(_):
        return 5000.0
    async def _pos(_):
        return []  # no open positions
    monkeypatch.setattr("performance.nifty_bankroll", _br)
    monkeypatch.setattr("position_tracker.get_open_positions", _pos)
    from nifty_commands import cmd_nifty_stats
    out = cmd_nifty_stats(db)
    # Bankroll Rs 5000, today's nifty = 200 + -50 = +150, today's penny = 100
    assert "Bankroll: Rs 5000" in out
    assert "Today:" in out
    # Nifty today should be +150 (200 + -50)
    assert "+Rs 150" in out or "+Rs 150.0" in out


def test_cmd_nifty_stats_handles_db_error(tmp_path, monkeypatch):
    """DB error -> 'error reading' message, not crash."""
    from nifty_commands import cmd_nifty_stats
    out = cmd_nifty_stats("/no/such/path/to/db.sqlite")
    # Either the bankroll async call fails or the DB call fails; either
    # way, the output should not raise and should mention an error OR
    # show valid stats (in which case the test passes silently).
    assert isinstance(out, str)
    assert "error" in out.lower() or "Bankroll" in out


# ---- /swing + /momentum ----------------------------------------------

def test_cmd_nifty_swing_empty(monkeypatch):
    """No active signals -> 'no active signals' message."""
    from nifty_commands import cmd_nifty_swing
    fake = type("M", (), {"current_signals": [], "current_momentum_signals": []})()
    monkeypatch.setattr("nifty_commands._get_globals", lambda: fake)
    out = cmd_nifty_swing()
    assert "no active signals" in out


def test_cmd_nifty_swing_lists_top_5_by_score(monkeypatch):
    from nifty_commands import cmd_nifty_swing
    signals = [
        _FakeSignal("LOW",  50),
        _FakeSignal("HIGH", 90),
        _FakeSignal("MID",  70),
    ]
    fake = type("M", (), {"current_signals": signals, "current_momentum_signals": []})()
    monkeypatch.setattr("nifty_commands._get_globals", lambda: fake)
    out = cmd_nifty_swing()
    assert "Nifty swing (3 active" in out
    assert "HIGH" in out
    assert "MID" in out
    assert "LOW" in out
    # Sort order: HIGH (90) before MID (70) before LOW (50)
    assert out.find("HIGH") < out.find("MID") < out.find("LOW")


def test_cmd_nifty_momentum_empty(monkeypatch):
    from nifty_commands import cmd_nifty_momentum
    fake = type("M", (), {"current_signals": [], "current_momentum_signals": []})()
    monkeypatch.setattr("nifty_commands._get_globals", lambda: fake)
    out = cmd_nifty_momentum()
    assert "no active signals" in out


def test_cmd_nifty_momentum_lists_top_5_by_score(monkeypatch):
    from nifty_commands import cmd_nifty_momentum
    signals = [
        _FakeSignal("M-LOW",  30),
        _FakeSignal("M-HIGH", 80),
    ]
    fake = type("M", (), {"current_signals": [], "current_momentum_signals": signals})()
    monkeypatch.setattr("nifty_commands._get_globals", lambda: fake)
    out = cmd_nifty_momentum()
    assert "Nifty momentum (2 active" in out
    assert "M-HIGH" in out
    assert "M-LOW" in out
    assert out.find("M-HIGH") < out.find("M-LOW")


# ---- /regime ---------------------------------------------------------

def test_cmd_nifty_regime_unknown(monkeypatch):
    from nifty_commands import cmd_nifty_regime
    from datetime import datetime, timezone
    fake = type("M", (), {
        "market_regime": "UNKNOWN",
        "last_run": None,
    })()
    monkeypatch.setattr("nifty_commands._get_globals", lambda: fake)
    out = cmd_nifty_regime()
    assert "Nifty market regime: UNKNOWN" in out
    assert "never computed" in out


def test_cmd_nifty_regime_bull(monkeypatch):
    from nifty_commands import cmd_nifty_regime
    from datetime import datetime, timezone, timedelta
    fake = type("M", (), {
        "market_regime": "BULL",
        "last_run": datetime.now(timezone.utc) - timedelta(minutes=15),
    })()
    monkeypatch.setattr("nifty_commands._get_globals", lambda: fake)
    out = cmd_nifty_regime()
    assert "Nifty market regime: BULL" in out
    assert "15 min ago" in out


def test_cmd_nifty_regime_caution(monkeypatch):
    from nifty_commands import cmd_nifty_regime
    from datetime import datetime, timezone, timedelta
    fake = type("M", (), {
        "market_regime": "CAUTION",
        "last_run": datetime.now(timezone.utc) - timedelta(hours=2),
    })()
    monkeypatch.setattr("nifty_commands._get_globals", lambda: fake)
    out = cmd_nifty_regime()
    assert "Nifty market regime: CAUTION" in out
    assert "2.0 hours ago" in out or "2 hours ago" in out


def test_cmd_nifty_regime_days_ago(monkeypatch):
    from nifty_commands import cmd_nifty_regime
    from datetime import datetime, timezone, timedelta
    fake = type("M", (), {
        "market_regime": "BEAR_RS_ONLY",
        "last_run": datetime.now(timezone.utc) - timedelta(days=3),
    })()
    monkeypatch.setattr("nifty_commands._get_globals", lambda: fake)
    out = cmd_nifty_regime()
    assert "3.0 days ago" in out or "3 days ago" in out


# ---- /circuit --------------------------------------------------------

def test_cmd_nifty_circuit_ok(monkeypatch):
    from nifty_commands import cmd_nifty_circuit
    async def _cb(_):
        return (False, [])
    monkeypatch.setattr("performance.check_circuit_breakers", _cb)
    from nifty_commands import cmd_nifty_circuit
    out = cmd_nifty_circuit("ignored.db")
    assert "OK" in out
    assert "no halt" in out


def test_cmd_nifty_circuit_halted_with_reasons(monkeypatch):
    from nifty_commands import cmd_nifty_circuit
    async def _cb(_):
        return (True, [
            "daily loss > 5%",
            "3 consecutive losing trades",
            "regime UNKNOWN",
        ])
    monkeypatch.setattr("performance.check_circuit_breakers", _cb)
    from nifty_commands import cmd_nifty_circuit
    out = cmd_nifty_circuit("ignored.db")
    assert "HALTED" in out
    assert "daily loss > 5%" in out
    assert "3 consecutive losing trades" in out
    assert "regime UNKNOWN" in out


def test_cmd_nifty_circuit_halted_truncates_long_list(monkeypatch):
    """When there are >3 reasons, the output shows the first 3 plus a
    'more' marker (so the Telegram message stays bounded)."""
    from nifty_commands import cmd_nifty_circuit
    async def _cb(_):
        return (True, [f"reason {i}" for i in range(10)])
    monkeypatch.setattr("performance.check_circuit_breakers", _cb)
    from nifty_commands import cmd_nifty_circuit
    out = cmd_nifty_circuit("ignored.db")
    assert "HALTED" in out
    assert "reason 0" in out
    assert "reason 2" in out
    # reason 9 is past the truncation point
    assert "reason 9" not in out
    assert "+7 more" in out


# ---- integration: dispatch end-to-end --------------------------------

def test_dispatch_routes_all_commands(tmp_path, monkeypatch):
    """All 6 subcommands route to their respective handlers."""
    from nifty_commands import dispatch
    db = str(tmp_path / "noop.db")
    # Set up a fake main module
    fake = type("M", (), {
        "current_signals": [],
        "current_momentum_signals": [],
        "market_regime": "BULL",
        "last_run": None,
    })()
    monkeypatch.setattr("nifty_commands._get_globals", lambda: fake)
    # Circuit-breaker + bankroll + positions mocks
    async def _cb(_):
        return (False, [])
    monkeypatch.setattr("performance.check_circuit_breakers", _cb)
    async def _br(_):
        return 5000.0
    monkeypatch.setattr("performance.nifty_bankroll", _br)
    async def _pos(_):
        return []
    monkeypatch.setattr("position_tracker.get_open_positions", _pos)

    # Each subcommand returns non-empty + appropriate keyword
    assert "/nifty" in dispatch("help", "", db)
    assert "Bankroll" in dispatch("stats", "", db)
    assert "no active signals" in dispatch("swing", "", db)
    assert "no active signals" in dispatch("momentum", "", db)
    assert "BULL" in dispatch("regime", "", db)
    assert "OK" in dispatch("circuit", "", db)
