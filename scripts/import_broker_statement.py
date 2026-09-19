#!/usr/bin/env python3
"""[WORKFLOW-F.7 2026-09-17] Broker-statement import CLI.

Per Workstream F in NEXT_AGENT_PLAN.md:
> Investigate each reconciliation warning with retained
> ledger/position records and broker statements when
> supplied. Produce discrepancy IDs and explanations;
> never mutate books merely to make the dashboard agree.

This CLI wraps the existing
``python-engine.broker_reconciliation`` module which
already provides:

  - ``import_broker_statement(...)`` -- atomically imports
    one immutable broker statement; identical retry is
    safe (returns False if the digest matches).
  - ``broker_statement_report(...)`` -- returns the
    newest statement's post-cost reconciliation, with
    MATCH / UNRESOLVED status based on the residual.

The CLI exposes:

  - ``import-statement`` -- imports one statement from a
    JSON file or stdin.
  - ``report`` -- emits the current reconciliation report.
  - ``list-imports`` -- lists all imported statements for
    an account.

Read-only against the strategy books. The CLI only
WRITES to the broker_statement_* tables (the imported
statements). It does NOT mutate the local ledger or
position tables. Per the plan: "never mutate books
merely to make the dashboard agree."

Usage::

    # Import a statement from a JSON file.
    python scripts/import_broker_statement.py \\
        --db-path /data/cache.db \\
        --account-id acct-1 \\
        import-statement \\
        --statement-id stmt-2026-09-17 \\
        --as-of 2026-09-17T16:00:00+05:30 \\
        --statement path/to/statement.json

    # Generate the reconciliation report.
    python scripts/import_broker_statement.py \\
        --db-path /data/cache.db \\
        --account-id acct-1 \\
        report

    # List all imports for an account.
    python scripts/import_broker_statement.py \\
        --db-path /data/cache.db \\
        --account-id acct-1 \\
        list-imports

Statement JSON format (for import-statement)::

    {
      "opening_cash": 100000.0,
      "closing_cash": 101234.56,
      "entries": [
        {"entry_id": "ent-1", "entry_type": "DEPOSIT",
         "amount": 50000.0},
        {"entry_id": "ent-2", "entry_type": "TRADE_REALIZED",
         "amount": -234.56}
      ],
      "fills": [
        {"fill_id": "fill-1", "order_id": "ord-1",
         "status": "FILLED", "quantity": 75, "price": 150.0,
         "fees": 23.45}
      ]
    }

Exit codes:
  0  -- success.
  1  -- business error (UNRESOLVED reconciliation).
  2  -- input invalid.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

# Add python-engine to sys.path so ``broker_reconciliation``
# can be imported when this script runs from /scripts.
_PYTHON_ENGINE = Path(__file__).resolve().parents[1] / "python-engine"
if str(_PYTHON_ENGINE) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ENGINE))


def _load_statement_json(path: Optional[str]) -> dict:
    """Load a statement JSON from a file path or stdin."""
    if path is None or path == "-":
        return json.loads(sys.stdin.read())
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"statement file not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _parse_as_of(value: str) -> datetime:
    """Parse an ISO datetime string, force timezone-aware."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware ISO 8601")
    return dt.astimezone(timezone.utc)


def _format_report(report: dict) -> str:
    """Render a broker_statement_report as human-readable text."""
    lines = [
        "# Broker-statement reconciliation",
        "# ----------------------------",
        f"# account_id:  {report.get('account_id')}",
        f"# status:      {report.get('status')}",
    ]
    if report.get("statement_id"):
        lines.append(f"# statement_id: {report.get('statement_id')}")
        lines.append(f"# as_of:        {report.get('as_of')}")
    if report.get("status") == "UNAVAILABLE":
        lines.append(f"# reason:       {report.get('reason')}")
        lines.append("")
        lines.append("No broker statement on disk. Import one with:")
        lines.append("  python scripts/import_broker_statement.py \\")
        lines.append("    --db-path /data/cache.db \\")
        lines.append("    --account-id <id> import-statement \\")
        lines.append("    --statement <file.json>")
        return "\n".join(lines) + "\n"

    lines.extend([
        f"# opening_cash:    ₹{report.get('opening_cash', 0):,.2f}",
        f"# closing_cash:    ₹{report.get('closing_cash', 0):,.2f}",
        f"# expected:        ₹{report.get('expected_closing_cash', 0):,.2f}",
        f"# residual:        ₹{report.get('residual', 0):,.2f}",
        "",
        f"# net trading P&L: ₹{report.get('net_trading_result', 0):,.2f}",
        f"# deposits:        ₹{report.get('deposits', 0):,.2f}",
        f"# withdrawals:     ₹{report.get('withdrawals', 0):,.2f}",
        f"# charges:         ₹{report.get('charges', 0):,.2f}",
        f"# operating_exp:   ₹{report.get('operating_expenses', 0):,.2f}",
        "",
        "# Fills by status:",
    ])
    fills = report.get("fills", {})
    for status, count in fills.items():
        lines.append(f"#   {status}: {count}")
    lines.append("")

    if report.get("status") == "UNRESOLVED":
        lines.append(
            "** Reconciliation UNRESOLVED. The expected closing "
            "cash does not match the broker-reported closing "
            "cash. Investigate: did the broker record a "
            "transaction we don't have, or did we record one "
            "the broker doesn't have? **"
        )
    else:
        lines.append("Reconciliation MATCH. Books align with broker.")

    return "\n".join(lines) + "\n"


def _format_imports(imports: list[dict]) -> str:
    lines = [
        "# Broker-statement imports",
        "# ----------------------",
        f"# {len(imports)} import(s)",
        "",
    ]
    for imp in imports:
        lines.append(
            f"## {imp['statement_id']} (as_of={imp['as_of']}, "
            f"opening={imp['opening_cash']:.2f}, "
            f"closing={imp['closing_cash']:.2f})"
        )
        lines.append(f"   imported_at: {imp['imported_at']}")
        lines.append(f"   digest:      {imp['payload_sha256']}")
        lines.append("")
    return "\n".join(lines) + "\n"


async def _cmd_import_statement(args: argparse.Namespace) -> int:
    """Import a broker statement from JSON."""
    import aiosqlite
    from broker_reconciliation import import_broker_statement

    if not args.db_path:
        print("--db-path is required", file=sys.stderr)
        return 2
    if not args.account_id:
        print("--account-id is required", file=sys.stderr)
        return 2
    if not args.statement_id:
        print("--statement-id is required", file=sys.stderr)
        return 2
    if not args.as_of:
        print("--as-of is required", file=sys.stderr)
        return 2
    if not args.statement:
        print("--statement <path|-> is required", file=sys.stderr)
        return 2

    statement = _load_statement_json(args.statement)
    as_of = _parse_as_of(args.as_of)

    inserted = await import_broker_statement(
        db_path=args.db_path,
        account_id=args.account_id,
        statement_id=args.statement_id,
        as_of=as_of,
        opening_cash=float(statement.get("opening_cash", 0)),
        closing_cash=float(statement.get("closing_cash", 0)),
        entries=statement.get("entries", []),
        fills=statement.get("fills", []),
    )
    if inserted:
        print(f"Imported statement {args.statement_id} for "
              f"account {args.account_id}.")
        return 0
    else:
        print(f"Statement {args.statement_id} already imported "
              f"with matching digest. Idempotent no-op.")
        return 0


async def _cmd_report(args: argparse.Namespace) -> int:
    """Generate the reconciliation report."""
    import aiosqlite
    from broker_reconciliation import broker_statement_report

    if not args.db_path:
        print("--db-path is required", file=sys.stderr)
        return 2
    if not args.account_id:
        print("--account-id is required", file=sys.stderr)
        return 2

    report = await broker_statement_report(
        db_path=args.db_path, account_id=args.account_id,
    )
    if args.json:
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
    else:
        sys.stdout.write(_format_report(report))
    if report.get("status") == "UNRESOLVED":
        return 1
    return 0


async def _cmd_list_imports(args: argparse.Namespace) -> int:
    """List all imports for an account."""
    import aiosqlite
    from broker_reconciliation import _SCHEMA

    if not args.db_path:
        print("--db-path is required", file=sys.stderr)
        return 2
    if not args.account_id:
        print("--account-id is required", file=sys.stderr)
        return 2

    async with aiosqlite.connect(args.db_path) as db:
        await db.executescript(_SCHEMA)
        cur = await db.execute(
            "SELECT statement_id, as_of, opening_cash, "
            "closing_cash, payload_sha256, imported_at "
            "FROM broker_statement_imports WHERE account_id=? "
            "ORDER BY as_of DESC",
            (args.account_id,),
        )
        rows = await cur.fetchall()
    imports = [
        {
            "statement_id": row[0],
            "as_of": row[1],
            "opening_cash": row[2],
            "closing_cash": row[3],
            "payload_sha256": row[4],
            "imported_at": row[5],
        }
        for row in rows
    ]
    if args.json:
        sys.stdout.write(json.dumps(imports, indent=2) + "\n")
    else:
        sys.stdout.write(_format_imports(imports))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=None,
                        help="path to PROD's cache.db")
    parser.add_argument("--account-id", default=None,
                        help="account identifier")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_imp = sub.add_parser(
        "import-statement",
        help="import one broker statement from JSON",
    )
    p_imp.add_argument("--statement-id", required=True,
                        help="unique statement identifier")
    p_imp.add_argument("--as-of", required=True,
                        help="ISO 8601 timestamp of statement "
                             "(timezone-aware)")
    p_imp.add_argument("--statement", required=True,
                        help="path to statement JSON file "
                             "(or '-' for stdin)")
    p_imp.set_defaults(handler=_cmd_import_statement)

    p_rep = sub.add_parser(
        "report", help="emit the reconciliation report",
    )
    p_rep.add_argument("--json", action="store_true",
                        help="emit JSON output")
    p_rep.set_defaults(handler=_cmd_report)

    p_lst = sub.add_parser(
        "list-imports", help="list all imports for an account",
    )
    p_lst.add_argument("--json", action="store_true",
                        help="emit JSON output")
    p_lst.set_defaults(handler=_cmd_list_imports)

    args = parser.parse_args(argv)
    return asyncio.run(args.handler(args))


__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
