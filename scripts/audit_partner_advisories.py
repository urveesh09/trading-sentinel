#!/usr/bin/env python3
"""[WORKFLOW-E.6 2026-09-17] Partner advisory audit.

Reads ``partner_advisory_ideas`` from PROD's cache.db
(read-only) and reports which advisories have a valid
rendered card body, which are queued vs delivered, and
which have a card that fails the renderer contract from
E.4.

Per Workstream E in NEXT_AGENT_PLAN.md:
> Improve cards around decisions a manual trader can take:
> ... Explain uncertainty and liquidity limits without
> overwhelming the message.

This audit verifies the cards the system produces, not
what Telegram actually receives (that requires Telegram's
delivery log, which is operator-owned).

Usage::

    # Audit the live PROD database.
    python scripts/audit_partner_advisories.py --db-path /data/cache.db

    # JSON output.
    python scripts/audit_partner_advisories.py --db-path /data/cache.db --json

    # Limit to recent advisories (default: all).
    python scripts/audit_partner_advisories.py --db-path /data/cache.db --limit 50

Exit codes:
  0  -- all advisories have valid rendered cards.
  1  -- at least one advisory failed a contract check.
  2  -- input invalid (missing DB, missing table).
"""
from __future__ import annotations

import argparse
import dataclasses
import enum
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional


class AuditStatus(str, enum.Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    BLOCKER = "BLOCKER"

    def exit_code(self) -> int:
        if self == AuditStatus.BLOCKER:
            return 2
        if self == AuditStatus.FAIL:
            return 1
        return 0


@dataclasses.dataclass(frozen=True)
class AdvisoryAuditRow:
    """One row per advisory in the audit report.

    Attributes:
        advisory_id: the advisory's primary key.
        scope: the advisory's scope (MARKET_SETUP /
            CONDITIONAL_PROTECTION).
        underlying: the underlying symbol.
        status: the advisory's status in the DB.
        evidence: the evidence value.
        quote_time: the quote_time from the DB (ISO string).
        valid_until: the valid_until from the DB.
        created_at: when the advisory was created.
        rendered_card_length: length of the rendered_card text
            in chars.
        rendered_card_validation: tuple of validation
            failures (empty = passes).
        audit_status: PASS / WARN / FAIL for this row.
    """
    advisory_id: str
    scope: str
    underlying: str
    status: str
    evidence: str
    quote_time: str
    valid_until: str
    created_at: str
    rendered_card_length: int
    rendered_card_validation: tuple[str, ...]
    audit_status: AuditStatus


# Use the renderer module's validator.
# Add the parent directory to sys.path so the import works.
_RENDERER_PATH = Path(__file__).resolve().parents[1] / "python-engine"
sys.path.insert(0, str(_RENDERER_PATH))

try:
    from partner_card_renderer import (  # type: ignore[import-not-found]
        MAX_TELEGRAM_CHARS,
        validate_rendered_card,
    )
    _RENDERER_AVAILABLE = True
except ImportError:
    _RENDERER_AVAILABLE = False


def _audit_one_row(row: dict) -> AdvisoryAuditRow:
    """Audit a single partner_advisory_ideas row."""
    rendered = row.get("rendered_card", "") or ""
    # Parse the payload back to a dict so we can validate
    # the rendered text against the structured data.
    payload_raw = row.get("payload", "") or ""
    payload: dict = {}
    if payload_raw:
        try:
            payload = json.loads(payload_raw)
        except (ValueError, TypeError):
            pass

    validation_failures: tuple[str, ...] = ()
    if _RENDERER_AVAILABLE and rendered:
        # Reconstruct a card-dict that validate_rendered_card
        # expects. The persisted payload uses the same shape
        # as ``_candidate_payload`` -- scope, evidence, etc.
        card = {
            "scope": row.get("scope", ""),
            "underlying": row.get("underlying", ""),
            "exchange": row.get("exchange", ""),
            "evidence": row.get("evidence", ""),
            "legs": payload.get("legs", []),
            "why_now": payload.get("why_now", []),
            "invalidation": payload.get("invalidation", ""),
            "management": payload.get("management", ""),
            "uncertainty": payload.get("uncertainty", ""),
            "net_debit_rs": payload.get("net_debit_rs"),
            "net_credit_rs": payload.get("net_credit_rs"),
            "max_loss_rs": payload.get("max_loss_rs"),
        }
        failures = validate_rendered_card(rendered, card)
        validation_failures = tuple(failures)

    audit_status = AuditStatus.PASS
    if not rendered:
        audit_status = AuditStatus.FAIL
    elif len(rendered) > MAX_TELEGRAM_CHARS:
        audit_status = AuditStatus.FAIL
    elif validation_failures:
        audit_status = AuditStatus.FAIL
    elif row.get("status") == "QUEUED" and not rendered.strip():
        audit_status = AuditStatus.WARN
    return AdvisoryAuditRow(
        advisory_id=row.get("advisory_id", "?"),
        scope=row.get("scope", "?"),
        underlying=row.get("underlying", "?"),
        status=row.get("status", "?"),
        evidence=row.get("evidence", "?"),
        quote_time=row.get("quote_time", "?"),
        valid_until=row.get("valid_until", "?"),
        created_at=row.get("created_at", "?"),
        rendered_card_length=len(rendered),
        rendered_card_validation=validation_failures,
        audit_status=audit_status,
    )


def audit_partner_advisories(db_path: str,
                               limit: Optional[int] = None,
                               status_filter: Optional[str] = None,
                               ) -> list[AdvisoryAuditRow]:
    """Read ``partner_advisory_ideas`` and audit each row.

    Args:
        db_path: path to the SQLite cache.db file.
        limit: optional max number of rows to audit (newest
            first).
        status_filter: optional advisory status to filter on
            (e.g. ``QUEUED``).

    Returns:
        A list of ``AdvisoryAuditRow``, newest first.
    """
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(f"db file not found: {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        # Check the table exists; if not, raise BLOCKER.
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='partner_advisory_ideas'"
        )
        if cur.fetchone() is None:
            raise RuntimeError(
                "partner_advisory_ideas table not found in this DB"
            )
        sql = (
            "SELECT advisory_id, scope, underlying, exchange, status, "
            "evidence, quote_time, valid_until, rendered_card, payload, "
            "created_at "
            "FROM partner_advisory_ideas"
        )
        params: tuple = ()
        if status_filter:
            sql += " WHERE status = ?"
            params = (status_filter,)
        sql += " ORDER BY created_at DESC"
        if limit:
            sql += " LIMIT ?"
            params = params + (limit,)
        cur.execute(sql, params)
        rows = cur.fetchall()
    finally:
        conn.close()
    columns = [
        "advisory_id", "scope", "underlying", "exchange", "status",
        "evidence", "quote_time", "valid_until", "rendered_card",
        "payload", "created_at",
    ]
    out: list[AdvisoryAuditRow] = []
    for row in rows:
        rec = dict(zip(columns, row))
        out.append(_audit_one_row(rec))
    return out


def rows_as_dicts(rows: list[AdvisoryAuditRow]) -> list[dict]:
    """Serialize audit rows to JSON."""
    return [
        {
            "advisory_id": r.advisory_id,
            "scope": r.scope,
            "underlying": r.underlying,
            "status": r.status,
            "evidence": r.evidence,
            "quote_time": r.quote_time,
            "valid_until": r.valid_until,
            "created_at": r.created_at,
            "rendered_card_length": r.rendered_card_length,
            "rendered_card_validation": list(r.rendered_card_validation),
            "audit_status": r.audit_status.value,
        }
        for r in rows
    ]


def format_report(rows: list[AdvisoryAuditRow]) -> str:
    """Render the audit as a human-readable report."""
    lines = [
        "# Partner advisory audit",
        "# ----------------------",
        f"# {len(rows)} advisory(ies) audited",
        "",
    ]
    if not rows:
        lines.append("No advisories found.")
        return "\n".join(lines) + "\n"
    by_status: dict[str, list[AdvisoryAuditRow]] = {}
    for r in rows:
        by_status.setdefault(r.audit_status.value, []).append(r)
    for status in ("BLOCKER", "FAIL", "WARN", "PASS"):
        items = by_status.get(status, [])
        if not items:
            continue
        lines.append(f"## [{status}] ({len(items)})")
        for r in items:
            lines.append(
                f"- `{r.advisory_id}` {r.scope}/{r.underlying} "
                f"status={r.status} rendered_len={r.rendered_card_length}"
            )
            if r.rendered_card_validation:
                for v in r.rendered_card_validation:
                    lines.append(f"  - {v}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", required=True,
                        help="path to PROD's cache.db")
    parser.add_argument("--limit", type=int, default=None,
                        help="audit only the N most-recent advisories")
    parser.add_argument("--status", default=None,
                        help="filter to advisories with this status")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON")
    args = parser.parse_args(argv)
    try:
        rows = audit_partner_advisories(
            args.db_path, limit=args.limit, status_filter=args.status,
        )
    except FileNotFoundError as exc:
        print(f"audit_partner_advisories: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"audit_partner_advisories: {exc}", file=sys.stderr)
        return 2

    if args.json:
        sys.stdout.write(json.dumps(rows_as_dicts(rows), indent=2) + "\n")
    else:
        sys.stdout.write(format_report(rows))
    has_blocker = any(r.audit_status == AuditStatus.BLOCKER for r in rows)
    has_fail = any(r.audit_status == AuditStatus.FAIL for r in rows)
    if has_blocker:
        return 2
    if has_fail:
        return 1
    return 0


__all__ = [
    "AuditStatus",
    "AdvisoryAuditRow",
    "audit_partner_advisories",
    "rows_as_dicts",
    "format_report",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
