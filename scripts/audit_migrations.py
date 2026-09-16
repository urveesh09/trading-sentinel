#!/usr/bin/env python3
"""[WORKFLOW-D.2.a 2026-09-16] Walk the python-engine and emit
a migration ledger.

Per Workstream D item 2 in NEXT_AGENT_PLAN.md:
> 2. Review migrations, defaults, flags and Docker volumes.
>    Establish consistent backup/rollback procedures without
>    deleting data.

The python-engine has 35+ modules, each with its own
``async def init_<module>_db(db_path)`` that creates tables
on demand. There is **no single migration ledger** --
operators must grep each module to know what tables exist
and what migrations apply.

The plan doc explicitly calls this out:
> Lazy migrations/retention exist across modules, not one
> migration ledger.

This script is the bounded dev-side slice of D.2.a. It:
1. Walks every python-engine module.
2. Extracts CREATE TABLE / ALTER TABLE statements via
   simple regex (no AST dependency -- the SQL is plain
   string literals in the source).
3. Maps each table to its init_<module>_db function.
4. Emits a JSON ledger (``migrations.json``) AND a
   human-readable ``migrations.md`` summary.

It never executes SQL -- this is a static audit tool.

Usage:
    python scripts/audit_migrations.py
    python scripts/audit_migrations.py --json
    python scripts/audit_migrations.py --out /tmp/migrations.json
    python scripts/audit_migrations.py --md-out /tmp/migrations.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ENGINE_DIR_DEFAULT = Path(__file__).resolve().parent.parent / "python-engine"


# Regex patterns for SQL extraction. These are deliberately
# simple -- the python-engine uses single-line CREATE/ALTER
# statements. Multi-line ones (like kite_client._init_db)
# are captured by a multi-line variant.
#
# Capture groups:
#   1: statement verb (CREATE TABLE / ALTER TABLE)
#   2: table name
#   3: body (between parentheses, or ``ADD COLUMN x ...`` for ALTER)
_CREATE_TABLE_RE = re.compile(
    r"""CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"?([A-Za-z_][A-Za-z0-9_]*)"?""",
    re.IGNORECASE,
)
_ALTER_TABLE_RE = re.compile(
    r"""ALTER\s+TABLE\s+([A-Za-z_][A-Za-z0-9_]*)\s+ADD\s+COLUMN\s+
        ([A-Za-z_][A-Za-z0-9_]*)\s+([A-Za-z0-9_]+)""",
    re.IGNORECASE | re.VERBOSE,
)
_INIT_FUNC_RE = re.compile(
    # Match ``async def init<NAME>(<param>: str)``. The return
    # annotation ``-> ...`` is optional -- some legacy helpers
    # like ``init_ledger`` in performance.py omit it.
    r"^\s*async\s+def\s+(init[A-Za-z_][A-Za-z0-9_]*)\s*\(\s*(\w+)\s*:\s*str\s*\)(?:\s*->[^\n]+)?",
    re.MULTILINE,
)

# Match module-level string constants holding CREATE TABLE
# statements. Two patterns are common:
#   1. ``_SCHEMA = \"\"\"CREATE TABLE ... ;\"\"\"`` (triple-quoted)
#   2. ``_SCHEMA = "CREATE TABLE ..." `` (single-line)
# The audit tool records these as ``schema_constants`` so
# operators know which modules run their schema via
# ``db.executescript(_SCHEMA)`` rather than per-table CREATE.
_SCHEMA_CONSTANT_RE = re.compile(
    r'^([A-Z_][A-Z0-9_]*)\s*=\s*("""|\'\'\')(.*?)\2',
    re.MULTILINE | re.DOTALL,
)


def is_init_db_function(name: str) -> bool:
    """Filter init<NAME> helpers to ones that look like DB
    initializers. The convention is ``init_<module>_db``; we
    also accept single-word names like ``init_ledger``.

    Refuses names that don't start with ``init_`` AND aren't
    plausibly a DB initializer (e.g. ``initialize_metrics``
    would not match the regex above; ``initializer`` would).
    """
    return name.startswith("init_")


def extract_sql_statements(source: str) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
    """Return (create_statements, alter_statements) from source.

    create_statements: list of (verb, table_name)
    alter_statements: list of (table_name, column_name, type)
    """
    creates = []
    for match in _CREATE_TABLE_RE.finditer(source):
        verb = "CREATE TABLE"
        table = match.group(1)
        # Filter out a few false-positives: SQL keywords that
        # match the regex but aren't table names.
        if table.upper() in {"IF", "TABLE", "INDEX", "TRIGGER", "VIEW"}:
            continue
        creates.append((verb, table))
    alters = []
    for match in _ALTER_TABLE_RE.finditer(source):
        table, column, col_type = match.groups()
        alters.append((table, column, col_type))
    return creates, alters


def find_init_functions(source: str) -> list[str]:
    """Return the names of init_<module>_db functions defined in source."""
    return [m.group(1) for m in _INIT_FUNC_RE.finditer(source)]


def find_schema_constants(source: str) -> list[str]:
    """Return the names of module-level string constants
    that look like SQL schema blocks (e.g. ``_SCHEMA``).
    Operators use ``db.executescript(_SCHEMA)`` to run
    these, so the audit records them as ``schema_constants``
    rather than per-table init functions.
    """
    names: list[str] = []
    for m in _SCHEMA_CONSTANT_RE.finditer(source):
        # Only flag constants whose body contains CREATE TABLE.
        body = m.group(3)
        if "CREATE TABLE" in body.upper():
            names.append(m.group(1))
    return names


def audit_module(path: Path) -> dict[str, Any]:
    """Audit a single python-engine module.

    Returns a dict with:
      - module: filename
      - init_functions: list of init_<...>_db function names
      - creates: list of {table, line} dicts
      - alters: list of {table, column, type, line} dicts
    """
    source = path.read_text(encoding="utf-8")
    creates, alters = extract_sql_statements(source)
    init_fns = find_init_functions(source)
    schema_constants = find_schema_constants(source)
    # Annotate with line numbers (best-effort -- re-search each match).
    # The re module's match.group(int) accepts int, but we use
    # **kwargs which requires string keys. The re.Match object's
    # groupdict() maps int -> str automatically; we use that.
    def _line_of(pattern, **groups):
        target = {int(k): v for k, v in groups.items()}
        for m in pattern.finditer(source):
            if all(m.group(i) == target[i] for i in target):
                return source[: m.start()].count("\n") + 1
        return None
    return {
        "module": path.name,
        "init_functions": init_fns,
        "schema_constants": schema_constants,
        "creates": [
            {"table": t, "line": _line_of(_CREATE_TABLE_RE, **{"1": t})}
            for verb, t in creates
        ],
        "alters": [
            {
                "table": tab,
                "column": col,
                "type": ctype,
                "line": _line_of(
                    _ALTER_TABLE_RE, **{"1": tab, "2": col, "3": ctype},
                ),
            }
            for tab, col, ctype in alters
        ],
    }


def audit_modules(engine_dir: Path) -> list[dict[str, Any]]:
    """Audit every python module in the python-engine."""
    results = []
    for path in sorted(engine_dir.glob("*.py")):
        if path.name.startswith("test_"):
            continue
        if path.name.startswith("_"):
            continue
        try:
            results.append(audit_module(path))
        except Exception as exc:
            # Defensive: never let one bad file abort the audit.
            results.append({
                "module": path.name,
                "error": f"{type(exc).__name__}: {exc}",
            })
    return results


def build_ledger(audit: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll up the per-module audit into a single ledger.

    The ledger's shape:
      - tables: dict[table_name, {module, init_functions, line}]
      - migrations: list[{table, column, type, module, line}]
      - schema_constants: dict[module, list[str]]
      - modules_count: int
      - tables_count: int
      - migrations_count: int
    """
    tables: dict[str, dict] = {}
    migrations: list[dict] = []
    schema_constants: dict[str, list[str]] = {}
    for entry in audit:
        if "error" in entry:
            continue
        if entry.get("schema_constants"):
            schema_constants[entry["module"]] = entry["schema_constants"]
        for create in entry["creates"]:
            t = create["table"]
            if t not in tables:
                tables[t] = {
                    "module": entry["module"],
                    "init_functions": entry["init_functions"],
                    "line": create["line"],
                }
        for alter in entry["alters"]:
            migrations.append({
                "table": alter["table"],
                "column": alter["column"],
                "type": alter["type"],
                "module": entry["module"],
                "line": alter["line"],
            })
    return {
        "tables": tables,
        "migrations": migrations,
        "schema_constants": schema_constants,
        "modules_count": len([e for e in audit if "error" not in e]),
        "tables_count": len(tables),
        "migrations_count": len(migrations),
    }


def format_ledger_md(ledger: dict[str, Any]) -> str:
    """Render the ledger as a human-readable markdown summary."""
    lines = [
        "# Migration ledger",
        "# ----------------",
        f"# {ledger['modules_count']} modules audited",
        f"# {ledger['tables_count']} tables discovered",
        f"# {ledger['migrations_count']} ALTER TABLE ADD COLUMN migrations",
        "",
        "## Tables (by name)",
        "",
    ]
    for name in sorted(ledger["tables"]):
        info = ledger["tables"][name]
        inits = ", ".join(info["init_functions"]) or "(no init_<>_db found)"
        line = info["line"] if info["line"] is not None else "?"
        lines.append(f"- `{name}` -- {info['module']}:{line} -- init: {inits}")
    lines.append("")
    if ledger.get("schema_constants"):
        lines.append("## Schema constants (modules using `db.executescript(_SCHEMA)`)")
        lines.append("")
        for mod in sorted(ledger["schema_constants"]):
            constants = ledger["schema_constants"][mod]
            lines.append(f"- `{mod}` -- constants: {', '.join(constants)}")
        lines.append("")
    lines.append("## Migrations (ALTER TABLE ADD COLUMN)")
    lines.append("")
    if not ledger["migrations"]:
        lines.append("(none)")
    else:
        for m in ledger["migrations"]:
            line = m["line"] if m["line"] is not None else "?"
            lines.append(
                f"- `{m['module']}:{line}` -- "
                f"`ALTER TABLE {m['table']} ADD COLUMN {m['column']} {m['type']}`"
            )
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-dir", type=Path, default=ENGINE_DIR_DEFAULT,
                        help="Path to the python-engine directory.")
    parser.add_argument("--json", action="store_true",
                        help="Emit machine-readable JSON to stdout.")
    parser.add_argument("--out", type=Path, default=None,
                        help="Write the JSON ledger to this path.")
    parser.add_argument("--md-out", type=Path, default=None,
                        help="Write the markdown summary to this path.")
    args = parser.parse_args(argv)
    if not args.engine_dir.is_dir():
        print(f"audit_migrations: not a directory: {args.engine_dir}",
              file=sys.stderr)
        return 2
    audit = audit_modules(args.engine_dir)
    ledger = build_ledger(audit)
    if args.json:
        sys.stdout.write(json.dumps({
            "ledger": ledger,
            "per_module": audit,
        }, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.write(format_ledger_md(ledger))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps({
                "ledger": ledger,
                "per_module": audit,
            }, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.md_out:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(format_ledger_md(ledger), encoding="utf-8")
    return 0


__all__ = [
    "audit_module",
    "audit_modules",
    "build_ledger",
    "extract_sql_statements",
    "find_init_functions",
    "format_ledger_md",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
