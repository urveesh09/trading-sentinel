"""[WORKFLOW-F 2026-09-13] Broker statement automation CLI (Phase 5).

Implements plan section 10 -- F5 sub-slices: a CLI for the
operator to ingest a broker statement, run reconciliation reports,
and list discrepancies. F5 is offline-only: no scheduler, no
daemon, no broker network calls. The operator runs the CLI from
outside the container with a local JSON payload.

The CLI is *the* wiring site for ``discrepancies.record_current_state``:
every successful statement import records discrepancies as a side
effect. Re-running with the same payload is idempotent -- the
existing ``broker_reconciliation.import_broker_statement`` already
rejects conflicting payloads at the SHA-256 boundary, and the
discrepancy framework is idempotent on ``(category, evidence_key)``.

Subcommands:

  * ``import-statement`` -- read a JSON payload from disk and
    ingest it via ``broker_reconciliation.import_broker_statement``.
    On success (or idempotent re-import), the F4 framework's
    ``record_current_state`` runs and the resulting discrepancy IDs
    are returned in the output JSON. The output JSON is written
    atomically with byte-identical retries so re-running with the
    same payload produces the same file.

  * ``run-report`` -- run broker cash, internal evidence and the narrower
    broker/internal order-reference report without importing anything. Useful
    for periodic inspection and CI smoke tests.

  * ``list-discrepancies`` -- filter the ``discrepancies`` table by
    ``--account``, ``--source``, ``--category``, ``--status``,
    ``--since``, ``--until``, ``--limit``.

[DESIGN-INVARIANTS 2026-09-13]
  1. NO network calls. The CLI reads a local JSON payload file
     (``--payload``) the operator supplies. No Kite, no Zerodha API.
  2. NO scheduler / daemon. The CLI exits after each invocation.
  3. NO mutation of ``bankroll_ledger``, ``positions``,
     ``fno_positions``, ``fno_dr_positions``, or any
     ``broker_statement_*`` table. Imports are idempotent and the
     F4 framework is append-only.
  4. The output JSON is written via ``_write_output_atomic`` -- a
     byte-identical retry produces the same file (the F4 framework
     already guarantees record idempotency, so two runs with the
     same payload produce the same discrepancy IDs in the same
     order).
  5. The CLI exits with code 0 on success, 1 on validation error,
     2 on import/DB error. The output JSON is written even on
     failure so the operator can inspect what went wrong.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import settings


# ---- helpers ---------------------------------------------------------------

def _json_file(path: str) -> Any:
    """Read a JSON file; raise ValueError on missing / unparseable."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"unreadable input file: {path}: {exc}") from exc
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"unparseable JSON in {path}: {exc}") from exc
    return value


def _write_output_atomic(path: str, value: dict) -> None:
    """Publish an output JSON atomically; byte-identical retries are allowed.

    Matches the ``research_cli._write_comparison_output`` discipline:
    the same input payload produces the same output bytes, so a
    retry of an idempotent CLI run produces an identical file.
    ``allow_nan=False`` prevents the JSON encoder from emitting
    ``NaN``/``Infinity`` which some downstream consumers refuse.
    """
    target = Path(path)
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".reconciliation-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            existing = target.read_bytes()
            if existing != encoded:
                raise ValueError(
                    f"output already exists with different content: {path}"
                )
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _parse_iso(value: str, field: str) -> datetime:
    """Parse an ISO-8601 string into a tz-aware datetime."""
    cleaned = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError(f"{field} is not ISO-8601: {value!r}") from exc
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(f"{field} must be timezone-aware: {value!r}")
    return dt.astimezone(timezone.utc)


def _payload_to_import_kwargs(payload: Any) -> dict[str, Any]:
    """Translate a JSON payload to ``import_broker_statement`` kwargs.

    The caller-supplied payload must carry every required field. We
    reject anything missing here, BEFORE calling the import function
    -- so the operator sees a clear CLI error rather than a deep
    stack trace.

    The required keys are exactly those of
    ``broker_reconciliation.import_broker_statement``:
        account_id, statement_id, as_of, opening_cash, closing_cash,
        entries, fills.
    """
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    required = (
        "account_id", "statement_id", "as_of",
        "opening_cash", "closing_cash", "entries", "fills",
    )
    missing = [k for k in required if k not in payload]
    if missing:
        raise ValueError(
            f"payload missing required keys: {', '.join(missing)}"
        )
    if not isinstance(payload["entries"], list):
        raise ValueError("payload.entries must be a list")
    if not isinstance(payload["fills"], list):
        raise ValueError("payload.fills must be a list")
    identities: dict[str, str] = {}
    for field in ("account_id", "statement_id"):
        value = payload[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"payload.{field} must be a non-empty string")
        identities[field] = value.strip()
    return {
        "account_id": identities["account_id"],
        "statement_id": identities["statement_id"],
        "as_of": _parse_iso(payload["as_of"], "as_of"),
        "opening_cash": float(payload["opening_cash"]),
        "closing_cash": float(payload["closing_cash"]),
        "entries": payload["entries"],
        "fills": payload["fills"],
    }


# ---- subcommands -----------------------------------------------------------

async def _import_statement(args: argparse.Namespace) -> dict[str, Any]:
    """Import a broker statement payload and record discrepancies.

    Exit JSON shape (always written, even on error):
        {
          "command": "import-statement",
          "ok": <bool>,
          "broker_status": "MATCH" | "UNRESOLVED" | "UNAVAILABLE",
          "broker_internal": <reference report>,
          "discrepancy_ids": {"broker": [...], "evidence": [...],
                              "broker_internal": [...]},
          "account_id": <str>,
          "statement_id": <str>,
          "error": <str | None>,
        }
    """
    from broker_reconciliation import import_broker_statement
    from discrepancies import record_current_state

    account_id_for_record = ""
    statement_id_for_record = ""
    out: dict[str, Any] = {
        "command": "import-statement",
        "ok": False,
        "broker_status": "UNAVAILABLE",
        "broker_internal": None,
        "discrepancy_ids": {"broker": [], "evidence": [], "broker_internal": []},
        "account_id": "",
        "statement_id": "",
        "error": None,
    }
    try:
        payload = _json_file(args.payload)
        kwargs = _payload_to_import_kwargs(payload)
        account_id_for_record = kwargs["account_id"]
        statement_id_for_record = kwargs["statement_id"]
        out["account_id"] = account_id_for_record
        out["statement_id"] = statement_id_for_record
        await import_broker_statement(
            args.db, **kwargs,
        )
        from broker_reconciliation import broker_statement_report
        from broker_internal_reconciliation import broker_internal_reference_report
        report = await broker_statement_report(
            args.db, account_id=account_id_for_record,
        )
        out["broker_internal"] = await broker_internal_reference_report(
            args.db,
            account_id=account_id_for_record,
            configured_account_id=settings.BROKER_RECONCILIATION_ACCOUNT_ID,
            statement_id=statement_id_for_record,
        )
        # Run record_current_state on every successful import
        # (including idempotent re-imports -- the F4 framework is
        # idempotent so the duplicate record call is a no-op).
        rec = await record_current_state(
            args.db, account_id=account_id_for_record, actor="cli",
            broker_report=report,
            broker_internal_report=out["broker_internal"],
        )
        out["discrepancy_ids"] = {
            "broker": list(rec.get("broker", [])),
            "evidence": list(rec.get("evidence", [])),
            "broker_internal": list(rec.get("broker_internal", [])),
        }
        out["broker_status"] = str(report.get("status", "UNAVAILABLE"))
        out["ok"] = True
    except (ValueError, KeyError, TypeError, OSError, OverflowError,
            sqlite3.Error) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


async def _run_report(args: argparse.Namespace) -> dict[str, Any]:
    """Run both existing reports without importing anything."""
    from broker_reconciliation import broker_statement_report
    from reconciliation_evidence import reconciliation_evidence_report
    from discrepancies import record_current_state
    out: dict[str, Any] = {
        "command": "run-report",
        "ok": False,
        "account_id": args.account,
        "broker": None,
        "broker_internal": None,
        "evidence": None,
        "discrepancy_ids": {"broker": [], "evidence": [], "broker_internal": []},
        "error": None,
    }
    try:
        out["broker"] = await broker_statement_report(
            args.db, account_id=args.account,
        )
        out["evidence"] = await reconciliation_evidence_report(
            args.db, source=args.source, limit=args.limit,
        )
        from broker_internal_reconciliation import broker_internal_reference_report
        out["broker_internal"] = await broker_internal_reference_report(
            args.db,
            account_id=args.account,
            configured_account_id=settings.BROKER_RECONCILIATION_ACCOUNT_ID,
        )
        if args.record:
            rec = await record_current_state(
                args.db, account_id=args.account, actor="cli",
                broker_report=out["broker"],
                broker_internal_report=out["broker_internal"],
            )
            out["discrepancy_ids"] = {
                "broker": list(rec.get("broker", [])),
                "evidence": list(rec.get("evidence", [])),
                "broker_internal": list(rec.get("broker_internal", [])),
            }
        out["ok"] = True
    except (ValueError, KeyError, TypeError, OSError, OverflowError,
            sqlite3.Error) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


async def _list_discrepancies(args: argparse.Namespace) -> dict[str, Any]:
    """Filter the discrepancies table and write the result."""
    from discrepancies import (
        DiscrepancyCategory, DiscrepancyStatus, list_discrepancies,
    )
    out: dict[str, Any] = {
        "command": "list-discrepancies",
        "ok": False,
        "rows": [],
        "filters": {},
        "error": None,
    }
    try:
        category = None
        if args.category:
            try:
                category = DiscrepancyCategory(args.category)
            except ValueError as exc:
                raise ValueError(
                    f"--category must be a DiscrepancyCategory value, "
                    f"got {args.category!r}"
                ) from exc
        status = None
        if args.status:
            try:
                status = DiscrepancyStatus(args.status)
            except ValueError as exc:
                raise ValueError(
                    f"--status must be a DiscrepancyStatus value, "
                    f"got {args.status!r}"
                ) from exc
        since = _parse_iso(args.since, "since") if args.since else None
        until = _parse_iso(args.until, "until") if args.until else None
        rows = await list_discrepancies(
            args.db,
            account_id=args.account,
            source=args.source,
            category=category,
            status=status,
            since=since,
            until=until,
            limit=args.limit,
        )
        out["rows"] = [r.to_dict() for r in rows]
        out["filters"] = {
            "account": args.account, "source": args.source,
            "category": args.category, "status": args.status,
            "since": args.since, "until": args.until,
            "limit": args.limit,
        }
        out["ok"] = True
    except (ValueError, KeyError, TypeError, OSError, OverflowError,
            sqlite3.Error) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


# ---- argparse + main -------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Sentinel broker statement automation. Offline CLI; no "
            "scheduler, no broker network calls. Reads a local JSON "
            "payload supplied by the operator."
        ),
    )
    parser.add_argument(
        "--db", default=settings.DB_PATH,
        help="SQLite database path (default: settings.DB_PATH)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # import-statement
    imp = sub.add_parser(
        "import-statement",
        help="import a broker statement JSON payload; records discrepancies",
    )
    imp.add_argument(
        "--payload", required=True,
        help="path to a JSON file matching import_broker_statement kwargs",
    )
    imp.add_argument(
        "--output", required=True,
        help="atomic immutable output JSON path",
    )

    # run-report
    rep = sub.add_parser(
        "run-report",
        help="run both existing reconciliation reports; optionally record",
    )
    rep.add_argument(
        "--account", required=True,
        help="account_id for broker_statement_report",
    )
    rep.add_argument(
        "--source", default=None,
        help="optional source filter for reconciliation_evidence_report",
    )
    rep.add_argument(
        "--limit", type=int, default=200,
        help="pagination limit for reconciliation_evidence_report (1..1000)",
    )
    rep.add_argument(
        "--record", action="store_true",
        help="also call record_current_state; off by default to keep "
             "the report command non-mutating",
    )
    rep.add_argument(
        "--output", required=True,
        help="atomic immutable output JSON path",
    )

    # list-discrepancies
    lst = sub.add_parser(
        "list-discrepancies",
        help="filter and list recorded discrepancies",
    )
    lst.add_argument("--account", default=None)
    lst.add_argument("--source", default=None)
    lst.add_argument(
        "--category", default=None,
        help="DiscrepancyCategory value",
    )
    lst.add_argument(
        "--status", default=None,
        help="DiscrepancyStatus value",
    )
    lst.add_argument("--since", default=None, help="ISO-8601 inclusive")
    lst.add_argument("--until", default=None, help="ISO-8601 inclusive")
    lst.add_argument("--limit", type=int, default=200)
    lst.add_argument(
        "--output", required=True,
        help="atomic immutable output JSON path",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "import-statement":
        out = asyncio.run(_import_statement(args))
    elif args.command == "run-report":
        out = asyncio.run(_run_report(args))
    elif args.command == "list-discrepancies":
        out = asyncio.run(_list_discrepancies(args))
    else:  # pragma: no cover -- argparse required=True blocks this
        print(json.dumps({"ok": False, "error": "unknown command"}))
        return 2
    # Always write the output JSON, even on failure, so the operator
    # can inspect what went wrong.
    try:
        _write_output_atomic(args.output, out)
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {"ok": False, "error": f"output write failed: {exc}"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps({"path": args.output, "ok": out["ok"]}, sort_keys=True))
    return 0 if out["ok"] else 1


__all__ = [
    "_import_statement",
    "_list_discrepancies",
    "_run_report",
    "_write_output_atomic",
    "_payload_to_import_kwargs",
    "_parse_iso",
    "_build_parser",
    "main",
]


if __name__ == "__main__":
    sys.exit(main())
