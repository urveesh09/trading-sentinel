"""[WORKFLOW-E.6 2026-09-17] Tests for the partner advisory audit.

The audit reads ``partner_advisory_ideas`` from PROD's
cache.db (read-only) and verifies each advisory has a
valid rendered card body. The audit catches:

  - advisories with empty rendered_card
  - advisories whose rendered_card fails the renderer
    contract from E.4 (missing required pieces)
  - advisories with rendered_card > MAX_TELEGRAM_CHARS
  - advisories with status=DELIVERED but no card

Read-only. No DB writes, no Telegram.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = (Path(__file__).resolve().parents[1]
                 / "audit_partner_advisories.py")
WORKDIR = Path(__file__).resolve().parents[2]


def _build_db(path: Path, rows: list[dict]) -> None:
    """Create a stub cache.db with the given rows."""
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE partner_advisory_ideas (
            advisory_id TEXT PRIMARY KEY,
            scope TEXT, underlying TEXT, exchange TEXT,
            status TEXT, evidence TEXT,
            quote_time TEXT, valid_until TEXT,
            rendered_card TEXT, payload TEXT,
            supersedes_id TEXT,
            created_at TEXT, updated_at TEXT
        )""")
    for r in rows:
        conn.execute(
            "INSERT INTO partner_advisory_ideas VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r["advisory_id"], r["scope"], r["underlying"], r["exchange"],
             r["status"], r["evidence"], r["quote_time"],
             r["valid_until"], r["rendered_card"], r["payload"],
             r.get("supersedes_id"), r["created_at"], r["updated_at"])
        )
    conn.commit()
    conn.close()


def _good_card() -> str:
    """A complete rendered card body."""
    return (
        "[MARKET SETUP] • NIFTY (NSE)\n"
        "Idea abc/v1 • Data 2026-09-17T09:30:00+05:30 • "
        "Valid until 2026-09-17T15:30:00+05:30\n"
        "INTRADAY ONLY — do not carry overnight. Manual action only; "
        "the system cannot close any position for you.\n"
        "Why now: ORB broke above opening range\n"
        "Structure:\n"
        "BUY 1× NIFTY24100CE | 2026-09-26 24100CE | lot 75 | "
        "bid/ask 100/105\n"
        "Act only if: combined debit ≤ ₹150.00 before fees\n"
        "Risk: theoretical maximum loss ₹150.00 if all intended legs "
        "fill and remain paired\n"
        "Invalidation: below opening low\n"
        "Management: exit at target\n"
        "Uncertainty: liquidity uncertain\n"
        "Evidence: QUALIFIED_FOR_ADVISORY. Per-structure economics only; "
        "no personal quantity is supplied.\n"
        "Manual decision. Recheck current executable quotes and broker "
        "requirements before acting.\n"
    )


def _good_payload() -> str:
    return json.dumps({
        "legs": [{"side": "BUY", "ratio": 1, "tradingsymbol":
                   "NIFTY24100CE", "lot_size": 75, "expiry":
                   "2026-09-26", "option_type": "CE", "strike":
                   24100}],
        "why_now": ["ORB broke above opening range"],
        "invalidation": "below opening low",
        "management": "exit at target",
        "uncertainty": "liquidity uncertain",
        "net_debit_rs": 150.0,
        "max_loss_rs": 150.0,
    })


def _make_row(advisory_id: str, **overrides) -> dict:
    base = {
        "advisory_id": advisory_id,
        "scope": "MARKET_SETUP",
        "underlying": "NIFTY",
        "exchange": "NSE",
        "status": "QUEUED",
        "evidence": "QUALIFIED_FOR_ADVISORY",
        "quote_time": "2026-09-17T09:30:00+05:30",
        "valid_until": "2026-09-17T15:30:00+05:30",
        "rendered_card": _good_card(),
        "payload": _good_payload(),
        "supersedes_id": None,
        "created_at": "2026-09-17T09:30:00",
        "updated_at": "2026-09-17T09:30:00",
    }
    base.update(overrides)
    return base


# -- 1. Happy path ----------------------------------------------


def test_valid_advisory_passes(tmp_path):
    db = tmp_path / "cache.db"
    _build_db(db, [_make_row("a1")])
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--db-path", str(db)],
        cwd=str(WORKDIR), capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0
    assert "[PASS]" in result.stdout
    assert "(1)" in result.stdout


def test_multiple_valid_advisories_all_pass(tmp_path):
    db = tmp_path / "cache.db"
    _build_db(db, [_make_row(f"a{i}") for i in range(5)])
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--db-path", str(db)],
        cwd=str(WORKDIR), capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0
    assert "5 advisory(ies)" in result.stdout


# -- 2. Failure cases ------------------------------------------


def test_empty_rendered_card_is_a_fail(tmp_path):
    db = tmp_path / "cache.db"
    _build_db(db, [_make_row("a1", rendered_card="")])
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--db-path", str(db)],
        cwd=str(WORKDIR), capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 1
    assert "[FAIL]" in result.stdout
    assert "rendered_len=0" in result.stdout


def test_card_missing_required_pieces_is_a_fail(tmp_path):
    db = tmp_path / "cache.db"
    _build_db(db, [_make_row("a1", rendered_card="short text")])
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--db-path", str(db)],
        cwd=str(WORKDIR), capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 1
    assert "missing required piece" in result.stdout


def test_card_exceeding_telegram_limit_is_a_fail(tmp_path):
    db = tmp_path / "cache.db"
    huge = "x" * 5000
    _build_db(db, [_make_row("a1", rendered_card=huge)])
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--db-path", str(db)],
        cwd=str(WORKDIR), capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 1
    assert "rendered_len=5000" in result.stdout


# -- 3. CLI flags ---------------------------------------------


def test_limit_flag_caps_results(tmp_path):
    db = tmp_path / "cache.db"
    _build_db(db, [_make_row(f"a{i}") for i in range(10)])
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--db-path", str(db), "--limit", "3"],
        cwd=str(WORKDIR), capture_output=True, text=True, timeout=15,
    )
    assert "3 advisory(ies)" in result.stdout


def test_status_filter_only_includes_matching(tmp_path):
    db = tmp_path / "cache.db"
    _build_db(db, [
        _make_row("a1", status="QUEUED"),
        _make_row("a2", status="DELIVERED"),
    ])
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--db-path", str(db),
         "--status", "QUEUED"],
        cwd=str(WORKDIR), capture_output=True, text=True, timeout=15,
    )
    assert "1 advisory(ies)" in result.stdout
    assert "a1" in result.stdout
    assert "a2" not in result.stdout


def test_json_flag_emits_valid_json(tmp_path):
    db = tmp_path / "cache.db"
    _build_db(db, [_make_row("a1")])
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--db-path", str(db), "--json"],
        cwd=str(WORKDIR), capture_output=True, text=True, timeout=15,
    )
    parsed = json.loads(result.stdout)
    assert isinstance(parsed, list)
    assert len(parsed) == 1
    assert parsed[0]["advisory_id"] == "a1"
    assert parsed[0]["audit_status"] == "PASS"


# -- 4. Error handling -----------------------------------------


def test_missing_db_returns_exit_two(tmp_path):
    bogus = tmp_path / "does_not_exist.db"
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--db-path", str(bogus)],
        cwd=str(WORKDIR), capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 2
    assert "db file not found" in result.stderr


def test_db_without_table_returns_exit_two(tmp_path):
    db = tmp_path / "empty.db"
    sqlite3.connect(str(db)).close()
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--db-path", str(db)],
        cwd=str(WORKDIR), capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 2
    assert "table not found" in result.stderr
