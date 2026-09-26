import ast
import asyncio
from datetime import datetime
import inspect
import json
import sqlite3

import pytest

import momentum_paper_audit as audit
from config import settings
from momentum_paper import (
    SOURCE,
    momentum_paper_monitor,
    momentum_paper_square_off,
    open_momentum_paper_positions,
)
from position_tracker import init_positions_db


def _schema(path, *, identity=True, ledger_identity=True):
    con = sqlite3.connect(path)
    con.execute("""
        CREATE TABLE momentum_paper_admission_outcomes (
            admission_key TEXT, signal_key TEXT, ticker TEXT,
            outcome TEXT, recorded_at TEXT
        )
    """)
    identity_column = ", paper_admission_key TEXT" if identity else ""
    con.execute(f"""
        CREATE TABLE positions (
            ticker TEXT, entry_date TEXT, exit_date TEXT, status TEXT,
            entry_price REAL, shares INTEGER, initial_capital_at_risk REAL,
            realised_pnl REAL, r_multiple REAL, source TEXT{identity_column}
        )
    """)
    origin_column = ", origin_ref TEXT" if ledger_identity else ""
    con.execute(f"""
        CREATE TABLE bankroll_ledger (
            timestamp TEXT, event_type TEXT, pnl REAL, source TEXT{origin_column}
        )
    """)
    con.commit()
    return con


def _complete_db(tmp_path):
    path = str(tmp_path / "audit.db")
    con = _schema(path)
    key = "entry:opaque-a"
    con.execute(
        "INSERT INTO momentum_paper_admission_outcomes VALUES (?,?,?,?,?)",
        (key, "signal-a", "ACME", "opened", "2026-09-26T10:00:00+05:30"),
    )
    con.execute(
        "INSERT INTO positions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("ACME", "2026-09-26T10:00:00+05:30", "2026-09-26T15:15:00+05:30",
         "CLOSED_TIME", 100.0, 5, 20.0, 30.0, 1.5, SOURCE, key),
    )
    con.executemany(
        "INSERT INTO bankroll_ledger VALUES (?,?,?,?,?)",
        [
            ("2026-09-26T11:00:00+05:30", "TRADE_PARTIAL", 10.0, SOURCE, key),
            ("2026-09-26T15:15:00+05:30", "TRADE_CLOSED", 20.0, SOURCE, key),
            # Same ticker but another/non-admission origin must never join.
            ("2026-09-26T15:15:01+05:30", "TRADE_CLOSED", 999.0, SOURCE, "other-key"),
        ],
    )
    con.commit()
    con.close()
    return path, key


def test_audit_exactly_reconciles_partial_and_terminal_cash_without_double_count(tmp_path):
    path, key = _complete_db(tmp_path)
    report = audit.build_momentum_paper_decision_audit(path)

    assert report["status"] == "COMPLETE"
    assert report["cash_truth"] == "bankroll_ledger"
    assert report["qualification"] == "NOT_ASSESSED"
    assert report["unlinked_legacy_cash_event_count"] == 1
    row = report["opportunities"][0]
    assert row["admission_key"] == key
    assert row["lifecycle"] == "CLOSED"
    assert row["cash"] == {
        "state": "MATCH", "partial_count": 1, "terminal_count": 1,
        "other_event_count": 0, "partial_pnl": 10.0, "terminal_pnl": 20.0,
        "net_pnl": 30.0, "position_pnl_delta": 0.0,
        "events": [
            {"event_type": "TRADE_PARTIAL", "timestamp": "2026-09-26T11:00:00+05:30", "pnl": 10.0},
            {"event_type": "TRADE_CLOSED", "timestamp": "2026-09-26T15:15:00+05:30", "pnl": 20.0},
        ],
    }
    assert report["summary"]["matched_closed_count"] == 1
    assert report["summary"]["matched_closed_net_pnl"] == 30.0


def test_audit_does_not_join_same_ticker_cash_without_the_exact_admission_key(tmp_path):
    path, key = _complete_db(tmp_path)
    con = sqlite3.connect(path)
    con.execute("DELETE FROM bankroll_ledger WHERE origin_ref=?", (key,))
    con.commit()
    con.close()

    row = audit.build_momentum_paper_decision_audit(path)["opportunities"][0]
    assert row["cash"]["net_pnl"] is None
    assert row["cash"]["state"] == "UNRESOLVED_TERMINAL_CASH"


def test_missing_database_is_read_only_and_does_not_create_a_file(tmp_path):
    missing = tmp_path / "not-created.db"
    report = audit.build_momentum_paper_decision_audit(str(missing))
    assert report["status"] == "UNAVAILABLE"
    assert report["reason"] == "database_unavailable_or_missing"
    assert not missing.exists()


def test_cli_prints_the_read_only_audit(tmp_path, capsys):
    path, _key = _complete_db(tmp_path)
    assert audit._main(["--db", path]) == 0
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["schema"] == audit.SCHEMA
    assert rendered["qualification"] == "NOT_ASSESSED"


def test_legacy_identity_schema_is_explicitly_unavailable_not_matched(tmp_path):
    path = str(tmp_path / "legacy.db")
    con = _schema(path, identity=False, ledger_identity=False)
    con.execute(
        "INSERT INTO momentum_paper_admission_outcomes VALUES (?,?,?,?,?)",
        ("entry:a", "signal", "ACME", "opened", "2026-09-26T10:00:00+05:30"),
    )
    con.commit()
    con.close()

    report = audit.build_momentum_paper_decision_audit(path)
    row = report["opportunities"][0]
    assert report["status"] == "PARTIAL"
    assert report["schema_availability"] == {
        "positions_admission_identity": False, "ledger_origin_identity": False,
    }
    assert row["lifecycle"] == "UNAVAILABLE_POSITION_LINK_SCHEMA"
    assert row["cash"]["state"] == "UNAVAILABLE_LEDGER_LINK_SCHEMA"


def test_duplicate_position_key_and_truncation_stay_explicit(tmp_path):
    path, key = _complete_db(tmp_path)
    con = sqlite3.connect(path)
    con.execute(
        "INSERT INTO positions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("ACME", "2026-09-26T10:01:00+05:30", None, "OPEN", 100, 1, 2, None, None, SOURCE, key),
    )
    con.execute(
        "INSERT INTO momentum_paper_admission_outcomes VALUES (?,?,?,?,?)",
        ("entry:second", "signal-b", "BETA", "zero_shares", "2026-09-26T10:01:00+05:30"),
    )
    con.commit()
    con.close()

    report = audit.build_momentum_paper_decision_audit(path, limit=1)
    assert report["status"] == "PARTIAL"
    assert report["truncated"] is True
    assert report["opportunities"][0]["lifecycle"] == "UNRESOLVED_DUPLICATE_POSITION_KEY"


def _paper_db(path):
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE bankroll_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, event_type TEXT,
            ticker TEXT, pnl REAL, bankroll_before REAL, bankroll_after REAL,
            notes TEXT, source TEXT, origin_ref TEXT
        );
    """)
    con.commit()
    con.close()


def _signal():
    return {
        "ticker": "ACME", "close": 100.0, "stop_loss": 90.0,
        "target_1": 130.0, "target_2": 140.0, "atr_at_entry": 1.0,
        "vwap": 99.0, "regime": "REGIME_1_NORMAL",
        "bar_ts": "2026-09-26T10:00:00+05:30",
    }


@pytest.mark.asyncio
async def test_runtime_paper_lifecycle_keeps_one_admission_key_through_partial_and_close(tmp_path, monkeypatch):
    path = str(tmp_path / "runtime.db")
    _paper_db(path)
    await init_positions_db(path)
    monkeypatch.setattr(settings, "MOMENTUM_PAPER_BANKROLL", 10_000.0)
    monkeypatch.setattr(settings, "MOMENTUM_RISK_PCT", 0.1)
    monkeypatch.setattr(settings, "MOMENTUM_USE_SCALE_OUT", True)
    monkeypatch.setattr(settings, "MOMENTUM_SCALE_OUT_R", 1.0)
    monkeypatch.setattr(settings, "MOMENTUM_SCALE_OUT_FRAC", 0.5)
    await open_momentum_paper_positions(path, [_signal()], datetime(2026, 9, 26, 4, 30))

    async def at_one_r(_ticker):
        return 110.0

    await momentum_paper_monitor(path, at_one_r, datetime(2026, 9, 26, 10, 30))

    async def at_close(_ticker):
        return 105.0

    await momentum_paper_square_off(path, at_close, datetime(2026, 9, 26, 15, 15))
    con = sqlite3.connect(path)
    key = con.execute("SELECT paper_admission_key FROM positions WHERE source=?", (SOURCE,)).fetchone()[0]
    origins = con.execute(
        "SELECT origin_ref FROM bankroll_ledger WHERE source=? ORDER BY id", (SOURCE,)
    ).fetchall()
    con.close()
    assert key and all(row[0] == key for row in origins)


@pytest.mark.asyncio
async def test_reopened_paper_lifecycle_receives_a_new_immutable_admission_key(tmp_path, monkeypatch):
    path = str(tmp_path / "reopen.db")
    _paper_db(path)
    await init_positions_db(path)
    monkeypatch.setattr(settings, "MOMENTUM_PAPER_BANKROLL", 10_000.0)
    monkeypatch.setattr(settings, "MOMENTUM_RISK_PCT", 0.1)
    now = datetime(2026, 9, 26, 4, 30)
    assert await open_momentum_paper_positions(path, [_signal()], now) == ["ACME"]

    async def close_quote(_ticker):
        return 100.0

    await momentum_paper_square_off(path, close_quote, datetime(2026, 9, 26, 15, 15))
    assert await open_momentum_paper_positions(path, [_signal()], now) == ["ACME"]
    con = sqlite3.connect(path)
    keys = [row[0] for row in con.execute(
        "SELECT paper_admission_key FROM positions WHERE source=? ORDER BY entry_date,rowid", (SOURCE,)
    )]
    con.close()
    assert len(keys) == 2 and keys[0] != keys[1]


def test_audit_module_has_no_order_network_or_message_dependencies():
    tree = ast.parse(inspect.getsource(audit))
    imports, names = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    assert not (imports & {"httpx", "requests", "aiosqlite", "kite", "telegram"})
    assert not (names & {"place_order", "modify_order", "cancel_order", "post", "put", "delete"})
