"""Durable per-attempt evidence for partner advisory input collection.

This archive-local journal records observations only.  It deliberately has no
imports from order, cash, position, qualification, or transport modules.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping
from zoneinfo import ZoneInfo

from partner_decision_clock import DecisionClock, aware


IST = ZoneInfo("Asia/Kolkata")
TERMINAL_STATES = {"NO_SETUP", "CANDIDATE_RECORDED", "UNAVAILABLE", "REJECTED", "SUPPRESSED", "ERROR"}


def _iso(value: datetime | None) -> str | None:
    return None if value is None else aware(value, "attempt timestamp").astimezone(timezone.utc).isoformat()


def _tokens(values: Iterable[int]) -> str:
    return json.dumps(sorted({int(value) for value in values}), separators=(",", ":"))


class PartnerCollectionAttemptStore:
    def __init__(self, archive_root: str | Path):
        self.path = Path(archive_root) / "partner-collection-attempts.sqlite3"

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=0.25)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS partner_collection_attempts (
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
          public_received_at_utc TEXT,
          public_observed_at_utc TEXT,
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
        );
        CREATE INDEX IF NOT EXISTS partner_attempt_session_idx
          ON partner_collection_attempts(underlying, expected_at_utc);
        """)
        columns = {row[1] for row in db.execute("PRAGMA table_info(partner_collection_attempts)")}
        if "public_observed_at_utc" not in columns:
            db.execute("ALTER TABLE partner_collection_attempts ADD COLUMN public_observed_at_utc TEXT")
        return db

    def start(self, clock: DecisionClock, *, expected_at: datetime | None = None) -> str:
        attempt_id = clock.run_id
        immutable = (
            attempt_id, clock.run_id, clock.account_id, clock.underlying, clock.policy,
            _iso(clock.tick_started_at), _iso(clock.evaluation_cutoff_at),
            _iso(expected_at or clock.tick_started_at), _iso(clock.tick_started_at),
        )
        with self._connect() as db:
            row = db.execute("""
              SELECT attempt_id,run_id,account_id,underlying,clock_policy,
                     tick_started_at_utc,evaluation_cutoff_at_utc,expected_at_utc
              FROM partner_collection_attempts WHERE attempt_id=?
            """, (attempt_id,)).fetchone()
            if row is not None and tuple(row) != immutable[:8]:
                raise ValueError("collection attempt identity is immutable")
            db.execute("""
              INSERT INTO partner_collection_attempts(
                attempt_id,run_id,account_id,underlying,clock_policy,tick_started_at_utc,
                evaluation_cutoff_at_utc,expected_at_utc,updated_at_utc)
              VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(attempt_id) DO NOTHING
            """, immutable)
        return attempt_id

    def record_public(self, attempt_id: str, *, state: str, requested_at: datetime | None,
                      received_at: datetime | None, source_id: str | None,
                      observed_at: datetime | None = None,
                      artifact_ref: str | None = None, reason: str | None = None,
                      updated_at: datetime) -> None:
        normalized = state.upper()
        if normalized not in {"OBSERVED", "UNAVAILABLE", "ERROR"}:
            raise ValueError("invalid public collection state")
        with self._connect() as db:
            existing = db.execute("""
              SELECT public_source_id,public_requested_at_utc,public_received_at_utc,public_observed_at_utc,
                     public_state,public_reason,public_artifact_ref
              FROM partner_collection_attempts WHERE attempt_id=?
            """, (attempt_id,)).fetchone()
            incoming = (source_id, _iso(requested_at), _iso(received_at), _iso(observed_at),
                        normalized, reason, artifact_ref)
            if existing is None:
                raise ValueError("collection attempt is missing")
            if existing[4] != "PENDING":
                if tuple(existing) != incoming:
                    raise ValueError("public attempt evidence is immutable")
                return
            changed = db.execute("""
              UPDATE partner_collection_attempts SET public_source_id=?,public_requested_at_utc=?,
                public_received_at_utc=?,public_observed_at_utc=?,public_state=?,public_reason=?,
                public_artifact_ref=?,updated_at_utc=?
              WHERE attempt_id=?
            """, (*incoming, _iso(updated_at), attempt_id)).rowcount
            if changed != 1:
                raise ValueError("collection attempt is missing")

    def record_candidate(self, attempt_id: str, *, state: str,
                         requested_at: datetime | None, received_at: datetime | None,
                         source_id: str | None, requested_contracts: Iterable[int] = (),
                         received_contracts: Iterable[int] = (), artifact_ref: str | None = None,
                         reason: str | None = None, updated_at: datetime) -> None:
        normalized = state.upper()
        if normalized not in {"OBSERVED", "NOT_REQUIRED", "UNAVAILABLE", "PARTIAL", "ERROR"}:
            raise ValueError("invalid candidate collection state")
        requested = {int(value) for value in requested_contracts}
        received = {int(value) for value in received_contracts}
        if not received.issubset(requested):
            raise ValueError("received contracts must be a subset of requested contracts")
        if normalized == "OBSERVED" and requested != received:
            raise ValueError("observed candidate collection requires every requested contract")
        with self._connect() as db:
            existing = db.execute("""
              SELECT chain_source_id,chain_requested_at_utc,chain_received_at_utc,candidate_state,
                     candidate_reason,candidate_artifact_ref,requested_contracts,received_contracts
              FROM partner_collection_attempts WHERE attempt_id=?
            """, (attempt_id,)).fetchone()
            incoming = (source_id, _iso(requested_at), _iso(received_at), normalized, reason,
                        artifact_ref, _tokens(requested), _tokens(received))
            if existing is None:
                raise ValueError("collection attempt is missing")
            if existing[3] != "PENDING":
                if tuple(existing) != incoming:
                    raise ValueError("candidate attempt evidence is immutable")
                return
            changed = db.execute("""
              UPDATE partner_collection_attempts SET chain_source_id=?,chain_requested_at_utc=?,
                chain_received_at_utc=?,candidate_state=?,candidate_reason=?,candidate_artifact_ref=?,
                requested_contracts=?,received_contracts=?,updated_at_utc=? WHERE attempt_id=?
            """, (*incoming, _iso(updated_at), attempt_id)).rowcount
            if changed != 1:
                raise ValueError("collection attempt is missing")

    def finish(self, attempt_id: str, *, state: str, reason: str, updated_at: datetime) -> None:
        normalized = state.upper()
        if normalized not in TERMINAL_STATES:
            raise ValueError("invalid terminal attempt state")
        with self._connect() as db:
            existing = db.execute("SELECT terminal_state,terminal_reason FROM partner_collection_attempts WHERE attempt_id=?",
                                  (attempt_id,)).fetchone()
            if existing is None:
                raise ValueError("collection attempt is missing")
            if existing[0] is not None:
                if tuple(existing) != (normalized, reason):
                    raise ValueError("terminal attempt evidence is immutable")
                return
            changed = db.execute("""
              UPDATE partner_collection_attempts SET terminal_state=?,terminal_reason=?,updated_at_utc=?
              WHERE attempt_id=?
            """, (normalized, reason, _iso(updated_at), attempt_id)).rowcount
            if changed != 1:
                raise ValueError("collection attempt is missing")

    def session_readiness(self, *, session_date: date, now: datetime,
                          underlyings: Iterable[str], entry_start_minute: int,
                          entry_end_minute: int, interval_seconds: int = 120,
                          scheduler_second: int = 50,
                          market_open: bool | None = None,
                          max_public_age_seconds: int = 360) -> dict:
        """[WORKFLOW-A5 2026-09-20] Per-index session completeness.

        Uses **distinct scheduler slots** (not raw row counts) so
        duplicate rows in the same minute slot do not mask a
        missing attempt in a later slot. Classifies each
        expected slot independently; the per-index state is
        derived from the slot classifications, not from row
        aggregates.

        The audit's reproducers (both now caught):
          - 1 OBSERVED + 1 UNAVAILABLE → ``PARTIAL``
          - 2 attempts in same slot + 0 in next slot → ``PARTIAL``

        ``can_qualify`` is preserved as ``False``. The audit's
        invariant: collection completeness does NOT confer
        strategy qualification.
        """
        current = aware(now, "readiness now")
        if (interval_seconds <= 0 or interval_seconds % 60 or not 0 <= scheduler_second <= 59
                or max_public_age_seconds <= 0):
            raise ValueError("attempt schedule must use positive whole-minute intervals and a valid second")
        interval_minutes = interval_seconds // 60
        first_minute = ((entry_start_minute + interval_minutes - 1) // interval_minutes) * interval_minutes
        start = (datetime.combine(session_date, datetime.min.time(), IST)
                 + timedelta(minutes=first_minute, seconds=scheduler_second))
        end = datetime.combine(session_date, datetime.min.time(), IST) + timedelta(minutes=entry_end_minute)
        cutoff = min(current, end)
        trading_session = session_date.weekday() < 5 if market_open is None else bool(market_open)
        expected = 0 if not trading_session or cutoff < start else int((cutoff - start).total_seconds() // interval_seconds) + 1
        lower = _iso(datetime.combine(session_date, datetime.min.time(), IST) + timedelta(minutes=entry_start_minute))
        upper = _iso(end + timedelta(minutes=1))
        names = [name.upper() for name in underlyings]
        if not self.path.exists():
            return {"session_date": session_date.isoformat(), "expected_attempts_per_index": expected,
                    "per_index": {name: self._empty_state(expected) for name in names},
                    "can_qualify": False}
        with sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM partner_collection_attempts WHERE expected_at_utc>=? AND expected_at_utc<?",
                              (lower, upper)).fetchall()
        per_index = {}
        for name in names:
            scoped = [row for row in rows if row["underlying"] == name]
            if not scoped:
                per_index[name] = self._empty_state(expected)
                continue
            # [WORKFLOW-A5 2026-09-20] Bucket by distinct slot.
            # ``expected_at_utc`` truncated to the interval
            # granularity is the canonical slot key. Multiple
            # rows in the same slot collapse to one bucket.
            slot_buckets: dict[str, list] = {}
            for row in scoped:
                ts = datetime.fromisoformat(row["expected_at_utc"])
                # Truncate to the interval: the canonical slot
                # boundary is ``start + k * interval_seconds``.
                slot_offset = int((ts - start).total_seconds() // interval_seconds)
                slot_key = (start + timedelta(seconds=slot_offset * interval_seconds)).isoformat()
                slot_buckets.setdefault(slot_key, []).append(row)
            distinct_slots = len(slot_buckets)
            missing_schedule = max(0, expected - distinct_slots)
            unavailable_count = 0
            stale_input_count = 0
            incomplete_count = 0
            latest = None
            for bucket_rows in slot_buckets.values():
                # The canonical row per bucket is the LATEST one
                # by ``updated_at_utc``. Multiple rows in the same
                # bucket (the audit's reproducer 2) are deduped to
                # the latest so the bucket classification is
                # deterministic.
                canonical = max(bucket_rows, key=lambda r: r["updated_at_utc"])
                if latest is None or canonical["updated_at_utc"] > latest.isoformat():
                    latest = datetime.fromisoformat(canonical["updated_at_utc"])
                if canonical["public_state"] != "OBSERVED":
                    unavailable_count += 1
                # Stale input: the public observed → received
                # delta exceeds ``max_public_age_seconds``.
                if canonical["public_observed_at_utc"] and canonical["public_received_at_utc"]:
                    age = (datetime.fromisoformat(canonical["public_received_at_utc"])
                           - datetime.fromisoformat(canonical["public_observed_at_utc"])).total_seconds()
                    if age > max_public_age_seconds or age < 0:
                        stale_input_count += 1
                # Incomplete: terminal missing OR candidate not
                # in the closed set OR contract subset mismatch.
                requested = set(json.loads(canonical["requested_contracts"]))
                received = set(json.loads(canonical["received_contracts"]))
                if (canonical["terminal_state"] is None
                        or canonical["candidate_state"] not in {"OBSERVED", "NOT_REQUIRED"}
                        or not requested.issubset(received)):
                    incomplete_count += 1
            # [WORKFLOW-A5 2026-09-20] Slot-aware state machine.
            # ANY unavailable OR missing OR incomplete slot
            # promotes the per-index state to PARTIAL. The
            # legacy "COMPLETE only when ALL slots are clean"
            # semantics are preserved.
            if latest is not None:
                stale = current.astimezone(timezone.utc) - latest > timedelta(seconds=interval_seconds * 2)
            else:
                stale = False
            if unavailable_count > 0 and unavailable_count == distinct_slots:
                # [WORKFLOW-A5 2026-09-20] Legacy
                # ATTEMPTED_UNAVAILABLE state preserved for
                # existing consumers; only fires when every
                # distinct slot is unavailable.
                state = "ATTEMPTED_UNAVAILABLE"
            elif unavailable_count > 0 or missing_schedule > 0 or incomplete_count > 0:
                state = "PARTIAL"
            elif stale_input_count > 0 or (stale and current <= end):
                state = "STALE"
            else:
                state = "COMPLETE"
            per_index[name] = {
                "state": state,
                "attempted": distinct_slots,
                "expected": expected,
                "missing_schedule_count": missing_schedule,
                "unavailable_count": unavailable_count,
                "incomplete_count": incomplete_count,
                "stale_input_count": stale_input_count,
                "latest_updated_at_utc": latest.isoformat() if latest is not None else None,
            }
        return {"session_date": session_date.isoformat(), "expected_attempts_per_index": expected,
                "per_index": per_index, "can_qualify": False}

    @staticmethod
    def _empty_state(expected: int) -> Mapping[str, object]:
        return {"state": "NEVER_ATTEMPTED", "attempted": 0, "expected": expected,
                "missing_schedule_count": expected, "unavailable_count": 0,
                "incomplete_count": 0, "stale_input_count": 0, "latest_updated_at_utc": None}
