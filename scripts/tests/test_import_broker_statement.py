"""[WORKFLOW-F.7 2026-09-17] Tests for the broker-statement
import CLI.

Per Workstream F in NEXT_AGENT_PLAN.md:
> Investigate each reconciliation warning with retained
> ledger/position records and broker statements when
> supplied. Produce discrepancy IDs and explanations;
> never mutate books merely to make the dashboard agree.

These tests pin the CLI's three subcommands:

  - ``import-statement`` -- atomic import + idempotent retry.
  - ``report`` -- reconciliation with MATCH / UNRESOLVED.
  - ``list-imports`` -- list all imports for an account.

The CLI wraps ``python-engine.broker_reconciliation``
which provides the underlying logic. The tests stub out
the database by using a fresh tmp_path each time.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPT_PATH = (Path(__file__).resolve().parents[1]
                 / "import_broker_statement.py")
WORKDIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))


def _good_statement(
    *,
    opening_cash: float = 100000.0,
    closing_cash: float = 101234.56,
    entries: list[dict] | None = None,
    fills: list[dict] | None = None,
) -> dict:
    if entries is None:
        entries = [
            {"entry_id": "ent-1", "entry_type": "DEPOSIT",
             "amount": 50000.0},
            {"entry_id": "ent-2", "entry_type": "TRADE_REALIZED",
             "amount": 1000.0},
            {"entry_id": "ent-3", "entry_type": "CHARGE",
             "amount": 31.0},
        ]
    if fills is None:
        fills = [
            {"fill_id": "fill-1", "order_id": "ord-1",
             "status": "FILLED", "quantity": 75,
             "price": 150.0, "fees": 23.45},
        ]
    return {
        "opening_cash": opening_cash,
        "closing_cash": closing_cash,
        "entries": entries,
        "fills": fills,
    }


def _write_statement(path: Path, statement: dict) -> None:
    path.write_text(json.dumps(statement), encoding="utf-8")


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=str(WORKDIR), capture_output=True, text=True, timeout=30,
    )


# -- 1. import-statement subcommand ---------------------------


def test_import_statement_creates_record(tmp_path):
    """[WORKFLOW-F.7 2026-09-17] Import creates a record in
    broker_statement_imports."""
    db = tmp_path / "cache.db"
    stmt_path = tmp_path / "stmt.json"
    _write_statement(stmt_path, _good_statement())
    result = _run_cli(
        "--db-path", str(db),
        "--account-id", "acct-1",
        "import-statement",
        "--statement-id", "stmt-1",
        "--as-of", "2026-09-17T16:00:00+05:30",
        "--statement", str(stmt_path),
    )
    assert result.returncode == 0, (
        f"unexpected exit; stderr: {result.stderr}"
    )
    assert "Imported statement" in result.stdout
    # Verify the row exists.
    conn = sqlite3.connect(str(db))
    cur = conn.execute(
        "SELECT statement_id FROM broker_statement_imports "
        "WHERE account_id=?",
        ("acct-1",),
    )
    assert cur.fetchone()[0] == "stmt-1"
    conn.close()


def test_import_statement_is_idempotent(tmp_path):
    """[WORKFLOW-F.7 2026-09-17] Identical retry returns
    False (no insert)."""
    db = tmp_path / "cache.db"
    stmt_path = tmp_path / "stmt.json"
    _write_statement(stmt_path, _good_statement())
    args = [
        "--db-path", str(db),
        "--account-id", "acct-1",
        "import-statement",
        "--statement-id", "stmt-1",
        "--as-of", "2026-09-17T16:00:00+05:30",
        "--statement", str(stmt_path),
    ]
    first = _run_cli(*args)
    assert first.returncode == 0
    second = _run_cli(*args)
    assert second.returncode == 0
    assert "Idempotent no-op" in second.stdout
    # Still only one row.
    conn = sqlite3.connect(str(db))
    cur = conn.execute(
        "SELECT COUNT(*) FROM broker_statement_imports"
    )
    assert cur.fetchone()[0] == 1
    conn.close()


def test_import_statement_rejects_naive_datetime(tmp_path):
    db = tmp_path / "cache.db"
    stmt_path = tmp_path / "stmt.json"
    _write_statement(stmt_path, _good_statement())
    result = _run_cli(
        "--db-path", str(db),
        "--account-id", "acct-1",
        "import-statement",
        "--statement-id", "stmt-1",
        "--as-of", "2026-09-17T16:00:00",  # naive.
        "--statement", str(stmt_path),
    )
    # The script calls _parse_as_of which raises ValueError
    # for naive datetimes. The exit code should be 2 (input
    # invalid via uncaught exception -> non-zero).
    assert result.returncode != 0


def test_import_statement_requires_arguments(tmp_path):
    """[WORKFLOW-F.7 2026-09-17] Missing required arguments
    fail with non-zero exit."""
    db = tmp_path / "cache.db"
    result = _run_cli(
        "--db-path", str(db),
        "--account-id", "acct-1",
        "import-statement",
        # Missing --statement-id, --as-of, --statement.
    )
    assert result.returncode != 0


# -- 2. report subcommand -----------------------------------


def test_report_for_account_with_no_imports(tmp_path):
    db = tmp_path / "cache.db"
    result = _run_cli(
        "--db-path", str(db),
        "--account-id", "acct-1",
        "report",
    )
    assert result.returncode == 0
    assert "UNAVAILABLE" in result.stdout
    assert "No broker statement on disk" in result.stdout


def test_report_when_statement_reconciles(tmp_path):
    """[WORKFLOW-F.7 2026-09-17] When opening + entries
    = closing, status is MATCH."""
    db = tmp_path / "cache.db"
    stmt_path = tmp_path / "stmt.json"
    # opening 100000, deposit 1000, charge 31 -> closing 100969.
    statement = _good_statement(
        opening_cash=100000.0,
        closing_cash=100969.0,
        entries=[
            {"entry_id": "ent-1", "entry_type": "DEPOSIT",
             "amount": 1000.0},
            {"entry_id": "ent-2", "entry_type": "CHARGE",
             "amount": 31.0},
        ],
    )
    _write_statement(stmt_path, statement)
    _run_cli(
        "--db-path", str(db),
        "--account-id", "acct-1",
        "import-statement",
        "--statement-id", "stmt-1",
        "--as-of", "2026-09-17T16:00:00+05:30",
        "--statement", str(stmt_path),
    )
    result = _run_cli(
        "--db-path", str(db),
        "--account-id", "acct-1",
        "report",
    )
    assert result.returncode == 0
    assert "MATCH" in result.stdout


def test_report_when_statement_unresolved(tmp_path):
    """[WORKFLOW-F.7 2026-09-17] When opening + entries
    != closing, status is UNRESOLVED, exit 1."""
    db = tmp_path / "cache.db"
    stmt_path = tmp_path / "stmt.json"
    # Use a positive CHARGE so the residual is meaningful.
    # opening 100000, charge 100 -> expected 99900, but
    # broker reports 99800 (off by 100). UNRESOLVED.
    statement = _good_statement(
        opening_cash=100000.0,
        closing_cash=99800.0,
        entries=[
            {"entry_id": "ent-1", "entry_type": "CHARGE",
             "amount": 100.0},
        ],
    )
    _write_statement(stmt_path, statement)
    _run_cli(
        "--db-path", str(db),
        "--account-id", "acct-1",
        "import-statement",
        "--statement-id", "stmt-1",
        "--as-of", "2026-09-17T16:00:00+05:30",
        "--statement", str(stmt_path),
    )
    result = _run_cli(
        "--db-path", str(db),
        "--account-id", "acct-1",
        "report",
    )
    assert result.returncode == 1
    assert "UNRESOLVED" in result.stdout
    assert "residual" in result.stdout


def test_report_json_emits_valid_json(tmp_path):
    db = tmp_path / "cache.db"
    stmt_path = tmp_path / "stmt.json"
    statement = _good_statement(
        opening_cash=100000.0,
        closing_cash=100000.0,
        entries=[
            {"entry_id": "ent-1", "entry_type": "CHARGE",
             "amount": 100.0},
            {"entry_id": "ent-2", "entry_type": "DEPOSIT",
             "amount": 100.0},
        ],
    )
    _write_statement(stmt_path, statement)
    _run_cli(
        "--db-path", str(db),
        "--account-id", "acct-1",
        "import-statement",
        "--statement-id", "stmt-1",
        "--as-of", "2026-09-17T16:00:00+05:30",
        "--statement", str(stmt_path),
    )
    result = _run_cli(
        "--db-path", str(db),
        "--account-id", "acct-1",
        "report", "--json",
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["account_id"] == "acct-1"
    assert parsed["status"] == "MATCH"


# -- 3. list-imports subcommand -------------------------------


def test_list_imports_empty_account(tmp_path):
    db = tmp_path / "cache.db"
    result = _run_cli(
        "--db-path", str(db),
        "--account-id", "acct-1",
        "list-imports",
    )
    assert result.returncode == 0
    assert "0 import(s)" in result.stdout


def test_list_imports_shows_one_record(tmp_path):
    db = tmp_path / "cache.db"
    stmt_path = tmp_path / "stmt.json"
    _write_statement(stmt_path, _good_statement())
    _run_cli(
        "--db-path", str(db),
        "--account-id", "acct-1",
        "import-statement",
        "--statement-id", "stmt-1",
        "--as-of", "2026-09-17T16:00:00+05:30",
        "--statement", str(stmt_path),
    )
    result = _run_cli(
        "--db-path", str(db),
        "--account-id", "acct-1",
        "list-imports",
    )
    assert result.returncode == 0
    assert "1 import(s)" in result.stdout
    assert "stmt-1" in result.stdout


def test_list_imports_filters_by_account(tmp_path):
    """[WORKFLOW-F.7 2026-09-17] list-imports filters by
    account_id -- other accounts don't appear."""
    db = tmp_path / "cache.db"
    stmt_path = tmp_path / "stmt.json"
    _write_statement(stmt_path, _good_statement())
    for stmt_id, acct in [("stmt-a", "acct-1"), ("stmt-b", "acct-2")]:
        _run_cli(
            "--db-path", str(db),
            "--account-id", acct,
            "import-statement",
            "--statement-id", stmt_id,
            "--as-of", "2026-09-17T16:00:00+05:30",
            "--statement", str(stmt_path),
        )
    result = _run_cli(
        "--db-path", str(db),
        "--account-id", "acct-1",
        "list-imports",
    )
    assert "stmt-a" in result.stdout
    assert "stmt-b" not in result.stdout


def test_list_imports_json_emits_valid_json(tmp_path):
    db = tmp_path / "cache.db"
    stmt_path = tmp_path / "stmt.json"
    _write_statement(stmt_path, _good_statement())
    _run_cli(
        "--db-path", str(db),
        "--account-id", "acct-1",
        "import-statement",
        "--statement-id", "stmt-1",
        "--as-of", "2026-09-17T16:00:00+05:30",
        "--statement", str(stmt_path),
    )
    result = _run_cli(
        "--db-path", str(db),
        "--account-id", "acct-1",
        "list-imports", "--json",
    )
    parsed = json.loads(result.stdout)
    assert isinstance(parsed, list)
    assert len(parsed) == 1
    assert parsed[0]["statement_id"] == "stmt-1"


# -- 4. CLI argument validation -----------------------------


def test_cli_requires_subcommand():
    result = _run_cli("--db-path", "/tmp/x.db", "--account-id", "acct-1")
    # argparse exits 2 when subcommand missing.
    assert result.returncode == 2


def test_cli_requires_db_path():
    """[WORKFLOW-F.7 2026-09-17] Without --db-path, the
    handler exits 2."""
    result = _run_cli(
        "--account-id", "acct-1",
        "list-imports",
    )
    assert result.returncode == 2


def test_cli_requires_account_id():
    """[WORKFLOW-F.7 2026-09-17] Without --account-id, the
    handler exits 2."""
    db_path = "/tmp/test.db"
    result = _run_cli(
        "--db-path", db_path,
        "list-imports",
    )
    assert result.returncode == 2
