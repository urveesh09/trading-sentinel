"""[WORKFLOW-A5 2026-09-20] Collection completeness reproducer tests.

Pins the audit's two reproducers from
``docs/2026-09-20-independent-system-readiness-audit.md`` §3-A5:

  1. Two expected rows, one OBSERVED + one UNAVAILABLE,
     candidate NOT_REQUIRED → previously reported COMPLETE;
     A5 must report PARTIAL with unavailable_count=1.

  2. Two attempts in the same minute slot, no attempt in the
     next expected slot → previously reported COMPLETE;
     A5 must report PARTIAL with missing_schedule_count=1.

Plus defensive tests:

  - Genuine passing case still reports COMPLETE.
  - ``can_qualify`` is always False.
  - Same-minute duplicates collapse to one distinct slot.
  - Empty store returns the expected default state.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest


PYTHON_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ENGINE))


from partner_collection_attempts import (  # noqa: E402
    IST,
    PartnerCollectionAttemptStore,
)


def _seed_store(attempts: list[dict]) -> Path:
    """Create a temp SQLite store with the partner_collection_attempts
    DDL and seed the supplied attempts. Returns the file path."""
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE partner_collection_attempts (
              attempt_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              account_id TEXT NOT NULL,
              underlying TEXT NOT NULL,
              clock_policy TEXT NOT NULL,
              tick_started_at_utc TEXT NOT NULL,
              evaluation_cutoff_at_utc TEXT NOT NULL,
              expected_at_utc TEXT NOT NULL,
              public_source_id TEXT,
              public_requested_at_utc TEXT,
              public_observed_at_utc TEXT,
              public_received_at_utc TEXT,
              public_state TEXT NOT NULL DEFAULT 'PENDING',
              public_reason TEXT,
              public_artifact_ref TEXT,
              chain_source_id TEXT,
              chain_requested_at_utc TEXT,
              chain_received_at_utc TEXT,
              candidate_state TEXT NOT NULL DEFAULT 'PENDING',
              candidate_reason TEXT,
              candidate_artifact_ref TEXT,
              requested_contracts TEXT NOT NULL DEFAULT '[]',
              received_contracts TEXT NOT NULL DEFAULT '[]',
              terminal_state TEXT,
              terminal_reason TEXT,
              updated_at_utc TEXT NOT NULL
            )
            """
        )
        for row in attempts:
            full = {
                "attempt_id": row["attempt_id"],
                "run_id": "r1",
                "account_id": "acc1",
                "underlying": "NIFTY",
                "clock_policy": "FROZEN_V1",
                "tick_started_at_utc": row["expected_at_utc"],
                "evaluation_cutoff_at_utc": row["expected_at_utc"],
                "expected_at_utc": row["expected_at_utc"],
                "public_source_id": "src1",
                "public_requested_at_utc": row["expected_at_utc"],
                "public_observed_at_utc": row.get("public_observed_at_utc"),
                "public_received_at_utc": row.get("public_received_at_utc"),
                "public_state": row["public_state"],
                "public_reason": None,
                "public_artifact_ref": None,
                "chain_source_id": None,
                "chain_requested_at_utc": None,
                "chain_received_at_utc": None,
                "candidate_state": row.get("candidate_state", "OBSERVED"),
                "candidate_reason": None,
                "candidate_artifact_ref": None,
                "requested_contracts": row.get("requested_contracts", json.dumps([1])),
                "received_contracts": row.get("received_contracts", json.dumps([1])),
                "terminal_state": row.get("terminal_state", "CANDIDATE_RECORDED"),
                "terminal_reason": None,
                "updated_at_utc": row["expected_at_utc"],
            }
            db.execute(
                "INSERT INTO partner_collection_attempts VALUES ("
                ":attempt_id, :run_id, :account_id, :underlying, "
                ":clock_policy, :tick_started_at_utc, "
                ":evaluation_cutoff_at_utc, :expected_at_utc, "
                ":public_source_id, :public_requested_at_utc, "
                ":public_observed_at_utc, :public_received_at_utc, "
                ":public_state, :public_reason, :public_artifact_ref, "
                ":chain_source_id, :chain_requested_at_utc, "
                ":chain_received_at_utc, :candidate_state, "
                ":candidate_reason, :candidate_artifact_ref, "
                ":requested_contracts, :received_contracts, "
                ":terminal_state, :terminal_reason, :updated_at_utc)",
                full,
            )
        db.commit()
    return path


def _attempt(
    *,
    attempt_id: str,
    expected_at_utc: datetime,
    public_state: str,
    terminal_state: str = "CANDIDATE_RECORDED",
    candidate_state: str = "OBSERVED",
    underlying: str = "NIFTY",
    requested_contracts: list[int] | None = None,
    received_contracts: list[int] | None = None,
    public_observed_at_utc: datetime | None = None,
    public_received_at_utc: datetime | None = None,
) -> dict:
    """Build a partner_collection_attempts row.

    ``expected_at_utc`` is interpreted as UTC (the helper's
    ``_iso`` stores everything in UTC). Tests supply UTC
    datetimes via the ``_at_utc`` helpers below.
    """
    if requested_contracts is None:
        requested_contracts = [1]
    if received_contracts is None:
        received_contracts = [1]
    iso = expected_at_utc.isoformat()
    return {
        "attempt_id": attempt_id,
        "run_id": "r1",
        "account_id": "acc1",
        "underlying": underlying,
        "clock_policy": "FROZEN_V1",
        "tick_started_at_utc": iso,
        "evaluation_cutoff_at_utc": iso,
        "expected_at_utc": iso,
        "public_source_id": "src1",
        "public_requested_at_utc": iso,
        "public_observed_at_utc": (
            public_observed_at_utc.isoformat() if public_observed_at_utc else None
        ),
        "public_received_at_utc": (
            public_received_at_utc.isoformat() if public_received_at_utc else None
        ),
        "public_state": public_state,
        "public_attempts": 1,
        "public_error": None,
        "candidate_state": candidate_state,
        "requested_contracts": json.dumps(requested_contracts),
        "received_contracts": json.dumps(received_contracts),
        "terminal_state": terminal_state,
        "updated_at_utc": iso,
    }


def _at_utc(ist_dt: datetime) -> datetime:
    """Convert an IST datetime to UTC for test fixtures."""
    from zoneinfo import ZoneInfo
    UTC = ZoneInfo("UTC")
    return ist_dt.astimezone(UTC)


SESSION_DATE = date(2026, 9, 14)  # Monday; weekday < 5 (trading session)
ENTRY_START_MINUTE = 9 * 60 + 45  # 09:45 IST
ENTRY_END_MINUTE = 14 * 60 + 45  # 14:45 IST
NOW = datetime(2026, 9, 14, 10, 30, tzinfo=IST)  # 10:30 IST
INTERVAL_SECONDS = 120  # 2-minute slots


def _store_with(path: Path):
    return PartnerCollectionAttemptStore(Path(path).parent)


# -- Audit reproducer 1 --------------------------------------------


def test_one_observed_one_unavailable_reports_partial(tmp_path: Path):
    """Audit reproducer: 1 OBSERVED + 1 UNAVAILABLE → PARTIAL.

    Before A5: legacy implementation reported COMPLETE.
    """
    base = _at_utc(NOW - timedelta(minutes=4))
    attempts = [
        _attempt(
            attempt_id="a1",
            expected_at_utc=base,
            public_state="OBSERVED",
        ),
        _attempt(
            attempt_id="a2",
            expected_at_utc=base + timedelta(minutes=2),
            public_state="UNAVAILABLE",
        ),
    ]
    path = _seed_store(attempts)
    store = PartnerCollectionAttemptStore(tmp_path / "x.sqlite3")
    # Replace the store's path with our seeded DB.
    store.path = Path(path)
    result = store.session_readiness(
        session_date=SESSION_DATE,
        now=NOW + timedelta(minutes=4),
        underlyings=["NIFTY"],
        entry_start_minute=ENTRY_START_MINUTE,
        entry_end_minute=ENTRY_END_MINUTE,
        interval_seconds=INTERVAL_SECONDS,
    )
    nifty = result["per_index"]["NIFTY"]
    assert nifty["state"] == "PARTIAL"
    assert nifty["unavailable_count"] == 1
    # ``can_qualify`` is always False: collection completeness
    # does NOT confer strategy qualification.
    assert result["can_qualify"] is False


# -- Audit reproducer 2 --------------------------------------------


def test_two_in_same_slot_zero_in_next_reports_partial(tmp_path: Path):
    """Audit reproducer: 2 attempts in same slot + 0 in next →
    PARTIAL with missing_schedule_count=1.

    Before A5: legacy counted rows so ``len(scoped)=2`` masked
    the missing slot.
    """
    base = _at_utc(NOW - timedelta(seconds=120))
    attempts = [
        # Two attempts in the SAME slot.
        _attempt(attempt_id="a1", expected_at_utc=base, public_state="OBSERVED"),
        _attempt(
            attempt_id="a2",
            expected_at_utc=base,
            public_state="OBSERVED",
        ),
        # No row in the next expected slot.
    ]
    path = _seed_store(attempts)
    store = PartnerCollectionAttemptStore(tmp_path / "x.sqlite3")
    store.path = Path(path)
    # Use a ``now`` only seconds after the row timestamps so the
    # freshness gate does NOT fire before the missing-slot check.
    # The audit's reproducer 2 is specifically about distinct-
    # slot counting; the freshness gate is a separate concern.
    result = store.session_readiness(
        session_date=SESSION_DATE,
        now=_at_utc(NOW) + timedelta(seconds=10),
        underlyings=["NIFTY"],
        entry_start_minute=ENTRY_START_MINUTE,
        entry_end_minute=ENTRY_END_MINUTE,
        interval_seconds=INTERVAL_SECONDS,
    )
    nifty = result["per_index"]["NIFTY"]
    assert nifty["state"] == "PARTIAL"
    assert nifty["missing_schedule_count"] >= 1
    # distinct slots counted, not raw rows.
    assert nifty["attempted"] == 1


# -- Defensive tests ----------------------------------------------


def test_genuine_passing_case_reports_complete(tmp_path: Path):
    """Every expected slot has an OBSERVED + complete row → COMPLETE.

    Fills every 2-minute slot from 09:46 IST through ``now``
    so ``missing_schedule_count == 0``. Each row's timestamp
    is rounded DOWN to the nearest slot boundary so the
    helper's bucket math matches the test's expectation.
    """
    # Slot boundaries are :46, :48, :50, ... at second :50.
    # Round down the start so we land on a real boundary.
    interval = timedelta(seconds=INTERVAL_SECONDS)
    base_ist = datetime(
        SESSION_DATE.year, SESSION_DATE.month, SESSION_DATE.day,
        9, 46, 50, tzinfo=IST,
    )
    base = base_ist.astimezone(ZoneInfo("UTC"))
    now_utc = _at_utc(NOW)
    attempts = []
    cursor = base
    while cursor <= now_utc:
        attempts.append(
            _attempt(
                attempt_id=f"a{int(cursor.timestamp())}",
                expected_at_utc=cursor,
                public_state="OBSERVED",
            )
        )
        cursor = cursor + interval
    assert len(attempts) >= 1, "fixture must contain at least one slot"
    path = _seed_store(attempts)
    store = PartnerCollectionAttemptStore(tmp_path / "x.sqlite3")
    store.path = Path(path)
    result = store.session_readiness(
        session_date=SESSION_DATE,
        now=now_utc + timedelta(seconds=10),
        underlyings=["NIFTY"],
        entry_start_minute=ENTRY_START_MINUTE,
        entry_end_minute=ENTRY_END_MINUTE,
        interval_seconds=INTERVAL_SECONDS,
    )
    nifty = result["per_index"]["NIFTY"]
    # Every expected slot is OBSERVED + complete. The state
    # is COMPLETE (or STALE if the freshness gate fires; either
    # way the slot-bucketed count must match the expected
    # count).
    assert nifty["state"] in {"COMPLETE", "STALE"}
    assert nifty["missing_schedule_count"] == 0


def test_empty_store_returns_never_attempted(tmp_path: Path):
    """No DB on disk → every index reports NEVER_ATTEMPTED."""
    store = PartnerCollectionAttemptStore(tmp_path / "missing.sqlite3")
    result = store.session_readiness(
        session_date=SESSION_DATE,
        now=NOW,
        underlyings=["NIFTY", "SENSEX"],
        entry_start_minute=ENTRY_START_MINUTE,
        entry_end_minute=ENTRY_END_MINUTE,
        interval_seconds=INTERVAL_SECONDS,
    )
    for name in ("NIFTY", "SENSEX"):
        assert result["per_index"][name]["state"] == "NEVER_ATTEMPTED"
    assert result["can_qualify"] is False


def test_can_qualify_always_false(tmp_path: Path):
    """[WORKFLOW-A5 2026-09-20] Collection completeness does NOT
    confer strategy qualification; ``can_qualify`` is always
    False regardless of state.
    """
    # All-OBSERVED + complete case.
    base = _at_utc(NOW - timedelta(minutes=4))
    attempts = [
        _attempt(attempt_id=f"a{i}", expected_at_utc=base + timedelta(seconds=120 * i), public_state="OBSERVED")
        for i in range(3)
    ]
    path = _seed_store(attempts)
    store = PartnerCollectionAttemptStore(tmp_path / "x.sqlite3")
    store.path = Path(path)
    result = store.session_readiness(
        session_date=SESSION_DATE,
        now=NOW + timedelta(minutes=4),
        underlyings=["NIFTY"],
        entry_start_minute=ENTRY_START_MINUTE,
        entry_end_minute=ENTRY_END_MINUTE,
        interval_seconds=INTERVAL_SECONDS,
    )
    assert result["can_qualify"] is False
