"""[WORKFLOW-F 2026-09-13] Discrepancy-ID framework + durable records (Phase 4).

Implements plan section 10.2 -- "Investigate each retained
reconciliation warning using actual evidence; build durable
discrepancy records and operator-reviewed explanations without
repairing books to agree." F4 ships:

  * A ``DiscrepancyCategory`` enum that maps every reason string
    already emitted by ``reconciliation_evidence.py`` and every
    state already emitted by ``broker_reconciliation.py`` into a
    stable, namespaced identifier (no free-text categories).
  * A ``DiscrepancyRecord`` dataclass + an append-only
    ``discrepancies`` table with a separate append-only
    ``discrepancy_status_log`` table. State transitions live in the
    log; the record itself is immutable. This is the same shape as
    ``promotion_bridge.py`` (forward-only state machine, immutable
    row, separate audit log).
  * ``record_discrepancy(...)`` is idempotent on
    ``(category, evidence_key)``. Re-recording the same finding is a
    no-op that returns ``False``; the first record wins. This
    matters because ``reconciliation_evidence_report`` is meant to be
    re-runnable.
  * ``update_discrepancy_status(...)`` is forward-only. The valid
    transitions are exactly:

        OPEN           -> INVESTIGATING
        OPEN           -> WITHDRAWN
        INVESTIGATING  -> RESOLVED_EXPLAINED
        INVESTIGATING  -> WITHDRAWN

    Anything else (including ``RESOLVED_EXPLAINED -> OPEN``) is
    rejected with ``DiscrepancyTransitionError``. There is no
    auto-close path. The operator reviews every transition.
  * Two bridge functions -- ``record_from_broker_statement(...)``
    and ``record_from_evidence_report(...)`` -- turn the existing
    reports' structured output into discrepancy records. The bridge
    is *the* place where reason-string -> category mapping lives;
    adding a new reason string in ``reconciliation_evidence.py`` is
    a single-line addition here.
  * ``record_current_state(...)`` runs both existing reports and
    records everything in one call. This is the function F5 (broker
    statement automation) will call from its CLI.

The five DISC-A1..A5 entries in the F audit doc remain
``UNKNOWN / UNVERIFIED``. F4 does NOT retroactively populate them;
the framework *records* findings with stable IDs as evidence arrives.
A future commit can call ``record_from_evidence_report`` with
hand-supplied evidence to back-fill the audit doc's five tentative
references when real screenshots / ledger rows are obtained.

[DESIGN-INVARIANTS 2026-09-13]
  1. NO mutation of ``bankroll_ledger``, ``positions``,
     ``fno_positions``, ``fno_dr_positions``, or any
     ``broker_statement_*`` table. F4 is an *observer*, not a
     rewriter.
  2. The ``discrepancies`` table is append-only at the SQLite level.
     BEFORE UPDATE and BEFORE DELETE triggers raise ``ABORT``.
  3. State transitions live in a separate ``discrepancy_status_log``
     table, also append-only with BEFORE UPDATE/DELETE triggers.
  4. Idempotent on ``(category, evidence_key)`` via UNIQUE INDEX.
  5. Forward-only state machine (no back-transitions, no
     auto-closure).
  6. No invented findings. The five audit-DOC DISC-A1..A5 entries
     remain docs-only placeholders; F4 does not invent evidence to
     close them.
"""
from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping, Optional, Sequence


# ---- enums ------------------------------------------------------------------

class DiscrepancyCategory(str, Enum):
    """Stable identifiers for every reconciliation finding.

    Adding a new category is a breaking change for any downstream
    consumer that enumerates categories; existing categories must
    not be renamed or repurposed. New reasons from upstream reports
    must be added as new categories, not folded into existing ones.
    """

    BROKER_RESIDUAL_NONZERO = "BROKER_RESIDUAL_NONZERO"
    BROKER_STATEMENT_UNAVAILABLE = "BROKER_STATEMENT_UNAVAILABLE"
    ORIGIN_REF_PNL_DIFFERENCE = "ORIGIN_REF_PNL_DIFFERENCE"
    ORIGIN_REF_SOURCE_MISMATCH = "ORIGIN_REF_SOURCE_MISMATCH"
    ORIGIN_REF_HAS_NO_MATCHING_POSITION = "ORIGIN_REF_HAS_NO_MATCHING_POSITION"
    MULTIPLE_LEDGER_ROWS_SHARE_ORIGIN_REF = "MULTIPLE_LEDGER_ROWS_SHARE_ORIGIN_REF"
    ORIGIN_REF_POSITION_NOT_CLOSED_OR_UNVALUED = "ORIGIN_REF_POSITION_NOT_CLOSED_OR_UNVALUED"
    LEDGER_PNL_NONFINITE_OR_MISSING = "LEDGER_PNL_NONFINITE_OR_MISSING"
    INTERNAL_EVIDENCE_INVALID_AMOUNTS = "INTERNAL_EVIDENCE_INVALID_AMOUNTS"


class DiscrepancyStatus(str, Enum):
    """Lifecycle states for a discrepancy record."""

    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED_EXPLAINED = "RESOLVED_EXPLAINED"
    WITHDRAWN = "WITHDRAWN"


_VALID_STATUS_TRANSITIONS = frozenset({
    (DiscrepancyStatus.OPEN, DiscrepancyStatus.INVESTIGATING),
    (DiscrepancyStatus.OPEN, DiscrepancyStatus.WITHDRAWN),
    (DiscrepancyStatus.INVESTIGATING, DiscrepancyStatus.RESOLVED_EXPLAINED),
    (DiscrepancyStatus.INVESTIGATING, DiscrepancyStatus.WITHDRAWN),
})


class DiscrepancyTransitionError(RuntimeError):
    """Raised when a status transition violates the forward-only machine."""


# ---- DDL --------------------------------------------------------------------

_DISCREPANCIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS discrepancies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    evidence_key TEXT NOT NULL,
    account_id TEXT NOT NULL,
    source TEXT NOT NULL,
    severity TEXT NOT NULL,
    amount_inr REAL,
    evidence_refs_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    UNIQUE(category, evidence_key)
);
CREATE INDEX IF NOT EXISTS idx_discrepancies_account
    ON discrepancies(account_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_discrepancies_source
    ON discrepancies(source, recorded_at);
CREATE INDEX IF NOT EXISTS idx_discrepancies_category
    ON discrepancies(category, recorded_at);
"""

_DISCREPANCY_STATUS_LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS discrepancy_status_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discrepancy_id INTEGER NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    actor TEXT NOT NULL,
    note TEXT,
    transitioned_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_discrepancy_status_log_discrepancy
    ON discrepancy_status_log(discrepancy_id, transitioned_at);
"""

_IMMUTABLE_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS discrepancies_no_update
BEFORE UPDATE ON discrepancies
BEGIN
    SELECT RAISE(ABORT, 'discrepancies_immutable');
END;
CREATE TRIGGER IF NOT EXISTS discrepancies_no_delete
BEFORE DELETE ON discrepancies
BEGIN
    SELECT RAISE(ABORT, 'discrepancies_immutable');
END;
CREATE TRIGGER IF NOT EXISTS discrepancy_status_log_no_update
BEFORE UPDATE ON discrepancy_status_log
BEGIN
    SELECT RAISE(ABORT, 'discrepancy_status_log_immutable');
END;
CREATE TRIGGER IF NOT EXISTS discrepancy_status_log_no_delete
BEFORE DELETE ON discrepancy_status_log
BEGIN
    SELECT RAISE(ABORT, 'discrepancy_status_log_immutable');
END;
"""


# ---- dataclasses ------------------------------------------------------------

@dataclass(frozen=True)
class DiscrepancyRecord:
    """One immutable discrepancy row + its current status.

    The ``current_status`` and ``status_updated_at`` fields are
    derived from the latest entry in ``discrepancy_status_log``;
    they are NOT columns of the ``discrepancies`` table itself.
    """

    id: int
    category: DiscrepancyCategory
    evidence_key: str
    account_id: str
    source: str
    severity: str
    amount_inr: Optional[float]
    evidence_refs: Sequence[tuple[str, str]]
    recorded_at: datetime
    current_status: DiscrepancyStatus
    status_updated_at: Optional[datetime]
    status_note: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category.value,
            "evidence_key": self.evidence_key,
            "account_id": self.account_id,
            "source": self.source,
            "severity": self.severity,
            "amount_inr": self.amount_inr,
            "evidence_refs": [
                {"table": t, "key": k} for (t, k) in self.evidence_refs
            ],
            "recorded_at": self.recorded_at.isoformat(),
            "current_status": self.current_status.value,
            "status_updated_at": (
                self.status_updated_at.isoformat()
                if self.status_updated_at else None
            ),
            "status_note": self.status_note,
        }


# ---- internal helpers -------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_dt(value: Any, field_name: str) -> datetime:
    """Parse an ISO-8601 string to a tz-aware datetime, or reject."""
    if isinstance(value, datetime):
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError(f"{field_name} must be timezone-aware")
        return value.astimezone(timezone.utc)
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be ISO-8601 string or datetime")
    cleaned = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError(f"{field_name} is not ISO-8601: {value!r}") from exc
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(f"{field_name} must be timezone-aware: {value!r}")
    return dt.astimezone(timezone.utc)


def _validate_evidence_refs(refs: Iterable[Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for r in refs:
        if not isinstance(r, (tuple, list)) or len(r) != 2:
            raise ValueError(
                f"evidence_ref must be a 2-tuple (table, key), got {r!r}"
            )
        table, key = r
        if not isinstance(table, str) or not table:
            raise ValueError(
                f"evidence_ref[0] must be a non-empty string, got {table!r}"
            )
        if not isinstance(key, str) or not key:
            raise ValueError(
                f"evidence_ref[1] must be a non-empty string, got {key!r}"
            )
        ref = (table, key)
        if ref in seen:
            continue
        seen.add(ref)
        out.append(ref)
    return out


def _finite_amount(value: Any, field_name: str) -> Optional[float]:
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric, got {value!r}") from exc
    if not math.isfinite(n):
        raise ValueError(f"{field_name} must be finite, got {value!r}")
    return n


async def init_discrepancies_db(db_path: str) -> None:
    """Create the discrepancies + status-log tables and their triggers.

    Idempotent: ``CREATE TABLE IF NOT EXISTS`` and
    ``CREATE TRIGGER IF NOT EXISTS``. Safe to call from any
    orchestrator boot path.
    """
    import aiosqlite  # local import keeps the public surface tight
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_DISCREPANCIES_SCHEMA)
        await db.executescript(_DISCREPANCY_STATUS_LOG_SCHEMA)
        await db.executescript(_IMMUTABLE_TRIGGERS)
        await db.commit()


# ---- public API: write ------------------------------------------------------

async def record_discrepancy(
    db_path: str,
    *,
    category: DiscrepancyCategory,
    evidence_key: str,
    account_id: str,
    source: str,
    severity: str,
    amount_inr: Optional[float] = None,
    evidence_refs: Sequence[tuple[str, str]] = (),
    actor: str = "system",
) -> int:
    """Append one discrepancy row.

    Idempotent on ``(category, evidence_key)``: if a row with that
    pair already exists, the call is a no-op and the existing row's
    ID is returned. The first record wins; subsequent calls cannot
    overwrite amount, severity, or evidence refs (those columns are
    immutable).

    Returns the row's ID (>= 1).
    """
    if not isinstance(category, DiscrepancyCategory):
        raise ValueError(f"category must be a DiscrepancyCategory, got {category!r}")
    if not isinstance(evidence_key, str) or not evidence_key:
        raise ValueError(
            f"evidence_key must be a non-empty string, got {evidence_key!r}"
        )
    if not isinstance(account_id, str) or not account_id:
        raise ValueError(
            f"account_id must be a non-empty string, got {account_id!r}"
        )
    if not isinstance(source, str) or not source:
        raise ValueError(
            f"source must be a non-empty string, got {source!r}"
        )
    if severity not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
        raise ValueError(
            f"severity must be LOW/MEDIUM/HIGH/CRITICAL, got {severity!r}"
        )
    amount = _finite_amount(amount_inr, "amount_inr")
    refs = _validate_evidence_refs(evidence_refs)
    refs_json = json.dumps(
        [{"table": t, "key": k} for (t, k) in refs],
        sort_keys=True,
        separators=(",", ":"),
    )
    now = _now_utc()
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        await init_discrepancies_db(db_path)
        await db.execute("BEGIN IMMEDIATE")
        try:
            existing = await (await db.execute(
                "SELECT id FROM discrepancies "
                "WHERE category=? AND evidence_key=?",
                (category.value, evidence_key),
            )).fetchone()
            if existing:
                await db.commit()
                return int(existing[0])
            cursor = await db.execute(
                "INSERT INTO discrepancies "
                "(category, evidence_key, account_id, source, severity, "
                "amount_inr, evidence_refs_json, recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    category.value,
                    evidence_key,
                    account_id,
                    source,
                    severity,
                    amount,
                    refs_json,
                    now.isoformat(),
                ),
            )
            new_id = int(cursor.lastrowid)
            # Initial status entry: from_status == to_status == OPEN.
            await db.execute(
                "INSERT INTO discrepancy_status_log "
                "(discrepancy_id, from_status, to_status, actor, note, transitioned_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    new_id,
                    DiscrepancyStatus.OPEN.value,
                    DiscrepancyStatus.OPEN.value,
                    actor,
                    "initial_record",
                    now.isoformat(),
                ),
            )
            await db.commit()
            return new_id
        except Exception:
            await db.rollback()
            raise


async def update_discrepancy_status(
    db_path: str,
    *,
    discrepancy_id: int,
    new_status: DiscrepancyStatus,
    actor: str,
    note: Optional[str] = None,
) -> None:
    """Apply a forward-only status transition.

    The transitions allowed are exactly:

        OPEN -> INVESTIGATING
        OPEN -> WITHDRAWN
        INVESTIGATING -> RESOLVED_EXPLAINED
        INVESTIGATING -> WITHDRAWN

    Anything else raises ``DiscrepancyTransitionError``. Note that
    ``OPEN -> RESOLVED_EXPLAINED`` is rejected; the operator must
    mark the row as ``INVESTIGATING`` first. There is no
    auto-closure.
    """
    if not isinstance(new_status, DiscrepancyStatus):
        raise ValueError(
            f"new_status must be a DiscrepancyStatus, got {new_status!r}"
        )
    if not isinstance(actor, str) or not actor:
        raise ValueError(
            f"actor must be a non-empty string, got {actor!r}"
        )
    if note is not None and not isinstance(note, str):
        raise ValueError(f"note must be a string or None, got {note!r}")
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        await init_discrepancies_db(db_path)
        await db.execute("BEGIN IMMEDIATE")
        try:
            current_row = await (await db.execute(
                "SELECT to_status FROM discrepancy_status_log "
                "WHERE discrepancy_id=? "
                "ORDER BY id DESC LIMIT 1",
                (discrepancy_id,),
            )).fetchone()
            if current_row is None:
                raise ValueError(
                    f"no discrepancy_status_log row for id={discrepancy_id}"
                )
            current = DiscrepancyStatus(str(current_row[0]))
            if current == new_status:
                # Idempotent no-op: same-state transition writes no log
                # row. The status log is append-only and recording the
                # same status twice would be pollution. Returning
                # without raising is the correct contract for
                # forward-only state machines: the operator's
                # "mark as INVESTIGATING" call is safe to repeat.
                await db.commit()
                return
            if (current, new_status) not in _VALID_STATUS_TRANSITIONS:
                raise DiscrepancyTransitionError(
                    f"invalid transition {current.value} -> {new_status.value} "
                    f"for discrepancy_id={discrepancy_id}"
                )
            now = _now_utc()
            await db.execute(
                "INSERT INTO discrepancy_status_log "
                "(discrepancy_id, from_status, to_status, actor, note, transitioned_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    discrepancy_id,
                    current.value,
                    new_status.value,
                    actor,
                    note,
                    now.isoformat(),
                ),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise


# ---- public API: read -------------------------------------------------------

def _row_to_record(
    row: sqlite3.Row,
    refs: Sequence[tuple[str, str]],
    current_status: DiscrepancyStatus,
    status_updated_at: Optional[datetime],
    status_note: Optional[str],
) -> DiscrepancyRecord:
    return DiscrepancyRecord(
        id=int(row["id"]),
        category=DiscrepancyCategory(str(row["category"])),
        evidence_key=str(row["evidence_key"]),
        account_id=str(row["account_id"]),
        source=str(row["source"]),
        severity=str(row["severity"]),
        amount_inr=row["amount_inr"],
        evidence_refs=list(refs),
        recorded_at=_coerce_dt(row["recorded_at"], "recorded_at"),
        current_status=current_status,
        status_updated_at=status_updated_at,
        status_note=status_note,
    )


async def list_discrepancies(
    db_path: str,
    *,
    account_id: Optional[str] = None,
    source: Optional[str] = None,
    category: Optional[DiscrepancyCategory] = None,
    status: Optional[DiscrepancyStatus] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    limit: int = 200,
) -> list[DiscrepancyRecord]:
    """List discrepancies with optional filters.

    All filters are AND-combined. The ``since``/``until`` bounds are
    inclusive and applied to ``recorded_at`` (NOT ``status_updated_at``
    -- that would conflate the original finding with its status log).
    """
    if not 1 <= limit <= 1000:
        raise ValueError(f"limit must be within 1..1000, got {limit}")
    where: list[str] = []
    params: list[Any] = []
    if account_id is not None:
        where.append("d.account_id=?"); params.append(account_id)
    if source is not None:
        where.append("d.source=?"); params.append(source)
    if category is not None:
        if not isinstance(category, DiscrepancyCategory):
            raise ValueError(
                f"category must be DiscrepancyCategory, got {category!r}"
            )
        where.append("d.category=?"); params.append(category.value)
    if since is not None:
        where.append("d.recorded_at>=?")
        params.append(_coerce_dt(since, "since").isoformat())
    if until is not None:
        where.append("d.recorded_at<=?")
        params.append(_coerce_dt(until, "until").isoformat())
    if status is not None:
        if not isinstance(status, DiscrepancyStatus):
            raise ValueError(
                f"status must be DiscrepancyStatus, got {status!r}"
            )
    sql_where = f"WHERE {' AND '.join(where)}" if where else ""
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        await init_discrepancies_db(db_path)
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"SELECT * FROM discrepancies d {sql_where} "
            f"ORDER BY d.id DESC LIMIT ?",
            (*params, limit),
        )
        rows = await cursor.fetchall()
        if not rows:
            return []
        ids = [int(r["id"]) for r in rows]
        placeholders = ",".join("?" * len(ids))
        status_rows = await (await db.execute(
            f"SELECT discrepancy_id, to_status, note, transitioned_at "
            f"FROM discrepancy_status_log WHERE discrepancy_id IN ({placeholders}) "
            f"ORDER BY id",
            ids,
        )).fetchall()
        latest: dict[int, tuple[DiscrepancyStatus, Optional[datetime], Optional[str]]] = {}
        for sr in status_rows:
            did = int(sr["discrepancy_id"])
            ts = _coerce_dt(sr["transitioned_at"], "transitioned_at")
            latest[did] = (
                DiscrepancyStatus(str(sr["to_status"])),
                ts,
                sr["note"],
            )
        out: list[DiscrepancyRecord] = []
        for r in rows:
            cs, sua, sn = latest.get(
                int(r["id"]),
                (DiscrepancyStatus.OPEN, None, None),
            )
            if status is not None and cs != status:
                continue
            try:
                refs_raw = json.loads(str(r["evidence_refs_json"]))
            except json.JSONDecodeError:
                refs_raw = []
            refs = [
                (str(item.get("table", "")), str(item.get("key", "")))
                for item in refs_raw
                if isinstance(item, dict)
            ]
            out.append(_row_to_record(r, refs, cs, sua, sn))
        return out


# ---- bridges to existing reports -------------------------------------------

_REASON_TO_CATEGORY: dict[str, DiscrepancyCategory] = {
    "origin_ref_pnl_difference": DiscrepancyCategory.ORIGIN_REF_PNL_DIFFERENCE,
    "origin_ref_source_mismatch": DiscrepancyCategory.ORIGIN_REF_SOURCE_MISMATCH,
    "origin_ref_has_no_matching_position": DiscrepancyCategory.ORIGIN_REF_HAS_NO_MATCHING_POSITION,
    "multiple_ledger_rows_share_origin_ref": DiscrepancyCategory.MULTIPLE_LEDGER_ROWS_SHARE_ORIGIN_REF,
    "origin_ref_position_not_closed_or_unvalued": DiscrepancyCategory.ORIGIN_REF_POSITION_NOT_CLOSED_OR_UNVALUED,
    "ledger_pnl_nonfinite_or_missing": DiscrepancyCategory.LEDGER_PNL_NONFINITE_OR_MISSING,
    "stable_origin_ref_and_pnl_match": None,  # not a discrepancy; skipped
}


async def record_from_evidence_report(
    db_path: str,
    *,
    evidence_report: Mapping[str, Any],
    account_id: str,
    actor: str = "system",
) -> list[int]:
    """Translate ``reconciliation_evidence_report`` output into records.

    Only the UNRESOLVED detail rows are recorded; MATCHED_INTERNAL
    rows are skipped. New reasons added to ``reconciliation_evidence.py``
    must be added to ``_REASON_TO_CATEGORY`` here -- otherwise the
    bridge silently drops them. This is the *single* mapping point.

    The ``evidence_report`` has two top-level keys:
      * ``sheets`` -- per-row detail (the rows we record). Each row
        carries ``ledger_id``, ``source``, ``ticker``, ``ledger_pnl``,
        ``origin_ref``, ``state``, ``reason``, ``position``.
      * ``source_sheets`` -- per-source summary (roll-up totals). We
        do NOT iterate these for recording; sheet-level flags (e.g.
        ``INTERNAL_EVIDENCE_HAS_INVALID_AMOUNTS``) are recorded
        separately via ``_INVALID_AMOUNT_SOURCES``.

    Returns the list of new (or pre-existing) row IDs in the order
    they were encountered.
    """
    out: list[int] = []
    # 1) Per-row details (the meat of the report).
    details = evidence_report.get("sheets", []) or []
    seen_evidence_keys: set[str] = set()
    for d in details:
        reason = str(d.get("reason", ""))
        category = _REASON_TO_CATEGORY.get(reason)
        if category is None:
            continue
        if str(d.get("state", "")) == "MATCHED_INTERNAL":
            continue
        ledger_id = int(d.get("ledger_id", 0))
        ticker = str(d.get("ticker", ""))
        source = str(d.get("source", ""))
        evidence_key = f"{category.value}|{source}|ledger:{ledger_id}"
        if evidence_key in seen_evidence_keys:
            continue
        seen_evidence_keys.add(evidence_key)
        position = d.get("position") or {}
        evidence_refs = [
            ("bankroll_ledger", str(ledger_id)),
        ]
        if position.get("source") and position.get("status"):
            evidence_refs.append(
                ("position_status", f"{position['source']}:{position['status']}")
            )
        severity = "HIGH" if category in {
            DiscrepancyCategory.ORIGIN_REF_PNL_DIFFERENCE,
            DiscrepancyCategory.MULTIPLE_LEDGER_ROWS_SHARE_ORIGIN_REF,
        } else "MEDIUM"
        amount = _finite_amount(d.get("ledger_pnl"), "ledger_pnl")
        did = await record_discrepancy(
            db_path,
            category=category,
            evidence_key=evidence_key,
            account_id=account_id,
            source=source,
            severity=severity,
            amount_inr=amount,
            evidence_refs=evidence_refs,
            actor=actor,
        )
        out.append(did)
    # 2) Sheet-level invalid-amounts flag (per-source roll-up).
    for sheet in evidence_report.get("source_sheets", []) or []:
        if sheet.get("status") == "INTERNAL_EVIDENCE_HAS_INVALID_AMOUNTS":
            source = str(sheet.get("source", ""))
            did = await record_discrepancy(
                db_path,
                category=DiscrepancyCategory.INTERNAL_EVIDENCE_INVALID_AMOUNTS,
                evidence_key=(
                    f"{DiscrepancyCategory.INTERNAL_EVIDENCE_INVALID_AMOUNTS.value}"
                    f"|{source}|sheet"
                ),
                account_id=account_id,
                source=source,
                severity="MEDIUM",
                amount_inr=None,
                evidence_refs=[("bankroll_ledger", f"source:{source}")],
                actor=actor,
            )
            out.append(did)
    return out


async def record_from_broker_statement(
    db_path: str,
    *,
    broker_report: Mapping[str, Any],
    account_id: str,
    actor: str = "system",
) -> Optional[int]:
    """Translate a ``broker_statement_report`` into a discrepancy record.

    MATCH -> no record. UNRESOLVED -> ``BROKER_RESIDUAL_NONZERO``
    with the residual amount. UNAVAILABLE ->
    ``BROKER_STATEMENT_UNAVAILABLE``. Returns the recorded ID, or
    ``None`` for MATCH (no record kept).
    """
    status = str(broker_report.get("status", ""))
    statement_id = str(broker_report.get("statement_id", ""))
    if status == "MATCH":
        return None
    if status == "UNAVAILABLE":
        category = DiscrepancyCategory.BROKER_STATEMENT_UNAVAILABLE
        evidence_key = (
            f"{category.value}|{account_id}|{broker_report.get('reason', 'NO_BROKER_STATEMENT')}"
        )
        return await record_discrepancy(
            db_path,
            category=category,
            evidence_key=evidence_key,
            account_id=account_id,
            source="BROKER",
            severity="LOW",
            amount_inr=None,
            evidence_refs=[],
            actor=actor,
        )
    if status == "UNRESOLVED":
        residual = _finite_amount(
            broker_report.get("residual"), "broker_report.residual"
        )
        category = DiscrepancyCategory.BROKER_RESIDUAL_NONZERO
        evidence_key = (
            f"{category.value}|{account_id}|{statement_id or 'no_statement_id'}"
        )
        return await record_discrepancy(
            db_path,
            category=category,
            evidence_key=evidence_key,
            account_id=account_id,
            source="BROKER",
            severity="HIGH",
            amount_inr=residual,
            evidence_refs=[
                ("broker_statement_imports", f"{account_id}:{statement_id}"),
            ],
            actor=actor,
        )
    raise ValueError(f"unknown broker report status: {status!r}")


async def record_current_state(
    db_path: str,
    *,
    account_id: str,
    actor: str = "system",
    broker_report: Optional[Mapping[str, Any]] = None,
    evidence_report: Optional[Mapping[str, Any]] = None,
) -> dict[str, list[int]]:
    """Run both existing reports (or accept pre-fetched payloads) and record.

    When ``broker_report`` / ``evidence_report`` are not supplied,
    the function calls the existing async producers in
    ``broker_reconciliation`` and ``reconciliation_evidence``. Both
    producer functions are read-only; F4 only adds the recording
    layer on top.

    Returns ``{"broker": [id_or_None], "evidence": [id, id, ...]}``
    so callers can log the freshly-recorded IDs.
    """
    broker_payload = broker_report
    if broker_payload is None:
        from broker_reconciliation import broker_statement_report
        broker_payload = await broker_statement_report(
            db_path, account_id=account_id,
        )
    evidence_payload = evidence_report
    if evidence_payload is None:
        from reconciliation_evidence import reconciliation_evidence_report
        evidence_payload = await reconciliation_evidence_report(db_path)
    broker_id = await record_from_broker_statement(
        db_path,
        broker_report=broker_payload,
        account_id=account_id,
        actor=actor,
    )
    evidence_ids = await record_from_evidence_report(
        db_path,
        evidence_report=evidence_payload,
        account_id=account_id,
        actor=actor,
    )
    return {"broker": [broker_id] if broker_id is not None else [], "evidence": evidence_ids}


__all__ = [
    "DISCREPANCY_SCHEMA_VERSION",
    "DiscrepancyCategory",
    "DiscrepancyRecord",
    "DiscrepancyStatus",
    "DiscrepancyTransitionError",
    "init_discrepancies_db",
    "list_discrepancies",
    "record_current_state",
    "record_discrepancy",
    "record_from_broker_statement",
    "record_from_evidence_report",
    "update_discrepancy_status",
]


# A version constant so future migrations can be guarded.
DISCREPANCIES_SCHEMA_VERSION = 1
DISCREPANCY_SCHEMA_VERSION = DISCREPANCIES_SCHEMA_VERSION  # alias kept for compatibility
