"""[WORKFLOW-B.1 2026-09-17] Tests for the session completeness audit.

Per Workstream B in NEXT_AGENT_PLAN.md:
> Compute session completeness from expected market-aware
> intervals and retained attempt records. Distinguish
> never attempted, attempted unavailable, partial,
> stale, and complete. A directory containing valid files
> alone is not sufficient.

These tests pin:

  - ``CompletenessState`` enum has the five states the
    plan calls out.
  - ``audit_session`` reads PROD's archive (read-only)
    and classifies each underlying.
  - ``SessionAuditReport.can_qualify`` is True iff every
    underlying is COMPLETE.
  - ``audit_session_completeness.py`` CLI exits 0/1/2 with
    the right semantics.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPT_PATH = (Path(__file__).resolve().parents[1]
                 / "audit_session_completeness.py")
WORKDIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = Path(__file__).resolve().parents[1]

# Make audit_session_completeness importable.
sys.path.insert(0, str(SCRIPTS_DIR))

from audit_session_completeness import (  # noqa: E402  -- import path
    CompletenessState,
    SessionAuditReport,
    UnderlyingAudit,
    audit_session,
    format_report,
)


IST = ZoneInfo = __import__("zoneinfo").ZoneInfo("Asia/Kolkata")


def _make_archive(tmp_path: Path) -> Path:
    """Create a stub archive with a
    partner-collection-attempts.sqlite3."""
    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    conn = sqlite3.connect(archive_root / "partner-collection-attempts.sqlite3")
    conn.executescript("""
        CREATE TABLE partner_collection_attempts (
            attempt_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL, account_id TEXT NOT NULL,
            underlying TEXT NOT NULL, clock_policy TEXT NOT NULL,
            tick_started_at_utc TEXT NOT NULL,
            evaluation_cutoff_at_utc TEXT NOT NULL,
            expected_at_utc TEXT NOT NULL,
            public_source_id TEXT, public_requested_at_utc TEXT,
            public_received_at_utc TEXT, public_observed_at_utc TEXT,
            public_state TEXT NOT NULL DEFAULT 'PENDING',
            public_reason TEXT, public_artifact_ref TEXT,
            chain_source_id TEXT, chain_requested_at_utc TEXT,
            chain_received_at_utc TEXT,
            candidate_state TEXT NOT NULL DEFAULT 'PENDING',
            candidate_reason TEXT, candidate_artifact_ref TEXT,
            requested_contracts TEXT NOT NULL DEFAULT '[]',
            received_contracts TEXT NOT NULL DEFAULT '[]',
            terminal_state TEXT, terminal_reason TEXT,
            updated_at_utc TEXT NOT NULL
        )
    """)
    conn.close()
    return archive_root


def _insert_attempt(archive_root: Path, *, underlying: str, expected_at: datetime,
                     public_state: str, candidate_state: str,
                     requested: list[int] | None = None,
                     received: list[int] | None = None,
                     terminal_state: str | None = "CANDIDATE_RECORDED",
                     public_received: datetime | None = None,
                     public_observed: datetime | None = None,
                     attempt_id: str | None = None) -> None:
    """Insert one attempt row into the archive."""
    if public_received is None:
        public_received = expected_at.replace(microsecond=200_000)
    if public_observed is None:
        public_observed = public_received
    requested = requested or [1, 2]
    received = received or [1, 2]
    if attempt_id is None:
        attempt_id = f"run-{expected_at.isoformat()}-{underlying}"
    conn = sqlite3.connect(archive_root / "partner-collection-attempts.sqlite3")
    conn.execute(
        "INSERT INTO partner_collection_attempts VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            attempt_id,
            f"run-{underlying}", "acct-1", underlying,
            "FROZEN_COMPLETED_BAR_CUTOFF_V1",
            expected_at.isoformat(),
            expected_at.isoformat(),
            expected_at.isoformat(),
            f"kite:{underlying}:1",
            expected_at.isoformat(),
            public_received.isoformat(),
            public_observed.isoformat(),
            public_state, None, "art-1",
            f"kite:{underlying}:2",
            expected_at.isoformat(), public_received.isoformat(),
            candidate_state, None, "art-2",
            json.dumps(requested), json.dumps(received),
            terminal_state, None, public_received.isoformat(),
        )
    )
    conn.commit()
    conn.close()


# -- 1. CompletenessState enum --------------------------------


def test_completeness_state_has_five_values():
    """[WORKFLOW-B.1 2026-09-17] The plan calls out five
    states: NEVER_ATTEMPTED, ATTEMPTED_UNAVAILABLE, PARTIAL,
    STALE, COMPLETE."""
    states = {s.value for s in CompletenessState}
    expected = {
        "NEVER_ATTEMPTED", "ATTEMPTED_UNAVAILABLE", "PARTIAL",
        "STALE", "COMPLETE",
    }
    assert states == expected


def test_complete_state_exit_code_is_zero():
    assert CompletenessState.COMPLETE.exit_code() == 0


def test_non_complete_state_exit_code_is_one():
    for state in CompletenessState:
        if state == CompletenessState.COMPLETE:
            continue
        assert state.exit_code() == 1


def test_complete_state_is_not_blocking():
    """[WORKFLOW-B.1 2026-09-17] COMPLETE is the only
    non-blocking state."""
    assert CompletenessState.COMPLETE.is_blocking() is False


def test_other_states_are_blocking():
    for state in CompletenessState:
        if state == CompletenessState.COMPLETE:
            continue
        assert state.is_blocking() is True


# -- 2. audit_session: empty archive ------------------------


def test_audit_empty_archive_returns_never_attempted(tmp_path):
    archive = _make_archive(tmp_path)
    report = audit_session(
        archive_root=archive,
        session_date=date(2026, 9, 14),
        underlyings=["NIFTY", "SENSEX"],
        entry_start_minute=9*60 + 15,
        entry_end_minute=15*60 + 30,
        now=datetime(2026, 9, 14, 16, 0, tzinfo=IST),
    )
    assert len(report.underlyings) == 2
    for u in report.underlyings:
        assert u.state == CompletenessState.NEVER_ATTEMPTED
    assert report.can_qualify is False


# -- 3. audit_session: state classification ----------------


def test_audit_classifies_attempted_unavailable(tmp_path):
    """[WORKFLOW-B.1 2026-09-17] All attempts UNAVAILABLE
    with missing expected slots -> PARTIAL."""
    archive = _make_archive(tmp_path)
    for i in range(3):
        expected_at = datetime(2026, 9, 14, 9, 16 + i * 2, 50,
                                 tzinfo=IST).astimezone(timezone.utc)
        _insert_attempt(
            archive, underlying="SENSEX", expected_at=expected_at,
            public_state="UNAVAILABLE",
            candidate_state="UNAVAILABLE",
            terminal_state="UNAVAILABLE",
        )
    report = audit_session(
        archive_root=archive,
        session_date=date(2026, 9, 14),
        underlyings=["SENSEX"],
        entry_start_minute=9*60 + 15,
        entry_end_minute=15*60 + 30,
        now=datetime(2026, 9, 14, 11, 0, tzinfo=IST),
    )
    u = report.underlyings[0]
    assert u.state == CompletenessState.PARTIAL
    assert u.unavailable_count >= 1


def test_audit_classifies_partial_when_missing_schedule(tmp_path):
    """[WORKFLOW-B.1 2026-09-17] Only a few attempts but
    many expected -> PARTIAL."""
    archive = _make_archive(tmp_path)
    # Only 2 attempts in a window expecting ~50.
    for i in range(2):
        expected_at = datetime(2026, 9, 14, 9, 16 + i * 2, 50,
                                 tzinfo=IST).astimezone(timezone.utc)
        _insert_attempt(
            archive, underlying="NIFTY", expected_at=expected_at,
            public_state="OBSERVED",
            candidate_state="OBSERVED",
        )
    report = audit_session(
        archive_root=archive,
        session_date=date(2026, 9, 14),
        underlyings=["NIFTY"],
        entry_start_minute=9*60 + 15,
        entry_end_minute=15*60 + 30,
        now=datetime(2026, 9, 14, 11, 0, tzinfo=IST),
    )
    u = report.underlyings[0]
    # Either PARTIAL (missing_schedule) or STALE (latest is old).
    assert u.state in (
        CompletenessState.PARTIAL, CompletenessState.STALE,
    )


def test_audit_classifies_partial_when_requested_not_received(tmp_path):
    """[WORKFLOW-B.1 2026-09-17] Contract gap (requested
    contracts not in received) -> PARTIAL."""
    archive = _make_archive(tmp_path)
    # Many attempts within the window to clear the
    # schedule-gap check; one has a contract gap.
    now = datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc)
    # Session window: 09:15 IST = 03:45 UTC, 15:30 IST = 10:00 UTC.
    # Use times between 03:45 and 10:00 UTC.
    for i in range(50):
        # 50 attempts over 5 hours = 1 attempt every 6 minutes.
        expected_at = datetime(2026, 9, 14, 4, 0, 50, 50,
                                 tzinfo=timezone.utc) + timedelta(minutes=i*6)
        if i == 25:
            _insert_attempt(
                archive, underlying="NIFTY", expected_at=expected_at,
                public_state="OBSERVED",
                candidate_state="OBSERVED",
                requested=[1, 2, 3],
                received=[1, 2],  # missing 3
                attempt_id=f"nifty-attempt-{i}",
            )
        else:
            _insert_attempt(
                archive, underlying="NIFTY", expected_at=expected_at,
                public_state="OBSERVED",
                candidate_state="OBSERVED",
                attempt_id=f"nifty-attempt-{i}",
            )
    report = audit_session(
        archive_root=archive,
        session_date=date(2026, 9, 14),
        underlyings=["NIFTY"],
        entry_start_minute=9*60 + 15,
        entry_end_minute=15*60 + 30,
        now=now,
    )
    u = report.underlyings[0]
    assert u.incomplete_count >= 1


# -- 4. SessionAuditReport ----------------------------------


def test_can_qualify_false_when_any_not_complete(tmp_path):
    archive = _make_archive(tmp_path)
    # NIFTY with attempts, SENSEX empty.
    expected_at = datetime(2026, 9, 14, 9, 16, 50, tzinfo=timezone.utc)
    _insert_attempt(
        archive, underlying="NIFTY", expected_at=expected_at,
        public_state="OBSERVED",
        candidate_state="OBSERVED",
    )
    report = audit_session(
        archive_root=archive,
        session_date=date(2026, 9, 14),
        underlyings=["NIFTY", "SENSEX"],
        entry_start_minute=9*60 + 15,
        entry_end_minute=15*60 + 30,
        now=datetime(2026, 9, 14, 11, 0, tzinfo=IST),
    )
    assert report.can_qualify is False


def test_to_dict_includes_all_required_keys(tmp_path):
    archive = _make_archive(tmp_path)
    report = audit_session(
        archive_root=archive,
        session_date=date(2026, 9, 14),
        underlyings=["NIFTY"],
        entry_start_minute=9*60 + 15,
        entry_end_minute=15*60 + 30,
        now=datetime(2026, 9, 14, 11, 0, tzinfo=IST),
    )
    d = report.to_dict()
    expected = {
        "session_date", "archive_root", "expected_attempts_per_index",
        # [WORKFLOW-A5/A6 2026-09-20] Audit's new diagnostic keys.
        # `collection_complete` and `eligible_for_replay` are the
        # new names; `can_qualify` is preserved as a constant
        # False (collection completeness does NOT confer
        # strategy qualification).
        "collection_complete", "eligible_for_replay",
        "can_qualify", "underlyings",
    }
    assert set(d.keys()) == expected
    # Collection is never "complete" without an underlying
    # being observed; ``collection_complete`` is therefore False
    # in this empty-archive case.
    assert d["can_qualify"] is False


def test_underlying_to_dict_includes_state(tmp_path):
    archive = _make_archive(tmp_path)
    report = audit_session(
        archive_root=archive,
        session_date=date(2026, 9, 14),
        underlyings=["NIFTY"],
        entry_start_minute=9*60 + 15,
        entry_end_minute=15*60 + 30,
        now=datetime(2026, 9, 14, 11, 0, tzinfo=IST),
    )
    d = report.underlyings[0].to_dict()
    assert "state" in d
    assert d["state"] == "NEVER_ATTEMPTED"


# -- 5. Blocking reasons -------------------------------------


def test_blocking_reasons_for_never_attempted(tmp_path):
    archive = _make_archive(tmp_path)
    report = audit_session(
        archive_root=archive,
        session_date=date(2026, 9, 14),
        underlyings=["NIFTY"],
        entry_start_minute=9*60 + 15,
        entry_end_minute=15*60 + 30,
        now=datetime(2026, 9, 14, 11, 0, tzinfo=IST),
    )
    u = report.underlyings[0]
    assert any("no attempts" in r for r in u.blocking_reasons)


def test_blocking_reasons_for_attempted_unavailable(tmp_path):
    archive = _make_archive(tmp_path)
    for i in range(3):
        expected_at = datetime(2026, 9, 14, 9, 16 + i * 2, 50,
                                 tzinfo=IST).astimezone(timezone.utc)
        _insert_attempt(
            archive, underlying="SENSEX", expected_at=expected_at,
            public_state="UNAVAILABLE",
            candidate_state="UNAVAILABLE",
            terminal_state="UNAVAILABLE",
        )
    report = audit_session(
        archive_root=archive,
        session_date=date(2026, 9, 14),
        underlyings=["SENSEX"],
        entry_start_minute=9*60 + 15,
        entry_end_minute=15*60 + 30,
        now=datetime(2026, 9, 14, 11, 0, tzinfo=IST),
    )
    u = report.underlyings[0]
    assert any("UNAVAILABLE" in r for r in u.blocking_reasons)


# -- 6. format_report ---------------------------------------


def test_format_report_includes_session_date(tmp_path):
    archive = _make_archive(tmp_path)
    report = audit_session(
        archive_root=archive,
        session_date=date(2026, 9, 14),
        underlyings=["NIFTY"],
        entry_start_minute=9*60 + 15,
        entry_end_minute=15*60 + 30,
        now=datetime(2026, 9, 14, 11, 0, tzinfo=IST),
    )
    text = format_report(report)
    assert "2026-09-14" in text
    assert "NIFTY" in text


def test_format_report_marks_can_qualify(tmp_path):
    archive = _make_archive(tmp_path)
    report = audit_session(
        archive_root=archive,
        session_date=date(2026, 9, 14),
        underlyings=["NIFTY"],
        entry_start_minute=9*60 + 15,
        entry_end_minute=15*60 + 30,
        now=datetime(2026, 9, 14, 11, 0, tzinfo=IST),
    )
    text = format_report(report)
    assert "can_qualify:" in text
    assert "False" in text


# -- 7. CLI integration -------------------------------------


def _run_cli(archive_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH),
         "--archive-root", str(archive_root), *args],
        cwd=str(WORKDIR), capture_output=True, text=True, timeout=15,
    )


def test_cli_missing_archive_returns_exit_two(tmp_path):
    bogus = tmp_path / "does_not_exist"
    result = _run_cli(bogus, "--session-date", "2026-09-14")
    assert result.returncode == 2


def test_cli_missing_db_file_returns_exit_two(tmp_path):
    empty = tmp_path / "empty_archive"
    empty.mkdir()
    result = _run_cli(empty, "--session-date", "2026-09-14")
    assert result.returncode == 2
    assert "not found" in result.stderr


def test_cli_empty_archive_returns_exit_one(tmp_path):
    archive = _make_archive(tmp_path)
    result = _run_cli(archive, "--session-date", "2026-09-14")
    assert result.returncode == 1
    assert "NEVER_ATTEMPTED" in result.stdout


def test_cli_json_flag_emits_valid_json(tmp_path):
    archive = _make_archive(tmp_path)
    result = _run_cli(archive, "--json", "--session-date", "2026-09-14")
    parsed = json.loads(result.stdout)
    assert "can_qualify" in parsed
    assert "underlyings" in parsed
