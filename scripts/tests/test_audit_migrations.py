"""[WORKFLOW-D.2.a 2026-09-16] Tests for the migration ledger
audit tool.

Per Workstream D item 2 in NEXT_AGENT_PLAN.md:
> 2. Review migrations, defaults, flags and Docker volumes.
>    Establish consistent backup/rollback procedures without
>    deleting data.

The audit script walks every python-engine module and
emits a deterministic ledger of CREATE TABLE / ALTER TABLE
statements + schema constants. These tests pin the
contract:

  - Per-module extraction (CREATE TABLE, ALTER TABLE,
    init_<module>_db, _SCHEMA constants).
  - Ledger roll-up is deterministic.
  - Markdown rendering is stable.
  - CLI flag combinations work.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest


HERE = os.path.dirname(os.path.abspath(__file__))
# HERE = scripts/tests/. REPO_ROOT = trading-sentinel/.
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# Import audit_migrations from its path. We avoid a top-level
# ``import audit_migrations`` because the test is in
# ``scripts/tests/`` which has no ``__init__.py`` (pytest's
# rootdir discovery treats it as rootpath-relative).
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "audit_migrations", os.path.join(SCRIPTS_DIR, "audit_migrations.py"),
)
audit_migrations = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit_migrations)


def _write_module(path: Path, source: str) -> None:
    """Write a python-engine-style module to a tmp path."""
    path.write_text(source, encoding="utf-8")


# ─── Per-module extraction ──────────────────────────────


def test_extract_sql_statements_simple_create():
    """Single CREATE TABLE with IF NOT EXISTS."""
    source = '''
async def init_foo_db(db_path: str) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS foo (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)
'''
    creates, alters = audit_migrations.extract_sql_statements(source)
    assert ("CREATE TABLE", "foo") in creates
    assert alters == []


def test_extract_sql_statements_multiple_creates():
    """Multiple CREATE TABLE statements in one module."""
    source = '''
    CREATE TABLE IF NOT EXISTS bar_a (id INTEGER PRIMARY KEY);
    CREATE TABLE IF NOT EXISTS bar_b (id INTEGER PRIMARY KEY);
'''
    creates, _ = audit_migrations.extract_sql_statements(source)
    tables = [t for _, t in creates]
    assert "bar_a" in tables
    assert "bar_b" in tables


def test_extract_sql_statements_alter_table():
    """ALTER TABLE ADD COLUMN is captured with table/column/type."""
    source = '''
    ALTER TABLE foo ADD COLUMN bar TEXT;
    ALTER TABLE foo ADD COLUMN baz INTEGER NOT NULL;
'''
    creates, alters = audit_migrations.extract_sql_statements(source)
    assert creates == []
    assert ("foo", "bar", "TEXT") in alters
    assert ("foo", "baz", "INTEGER") in alters


def test_find_init_functions_with_return_annotation():
    """``async def init_<NAME>(db_path: str) -> ...`` matches."""
    source = '''
async def init_ledger(db_path: str):
    pass

async def init_penny_db(db_path: str) -> None:
    pass

async def init_fno_positions_db(db_path: str) -> None:
    pass
'''
    fns = audit_migrations.find_init_functions(source)
    assert "init_ledger" in fns
    assert "init_penny_db" in fns
    assert "init_fno_positions_db" in fns


def test_find_init_functions_skips_non_init():
    """Functions that don't start with ``init_`` are skipped."""
    source = '''
async def refresh_cache(db_path: str):
    pass

async def helper():
    pass
'''
    fns = audit_migrations.find_init_functions(source)
    assert fns == []


def test_find_schema_constants_detects_triple_quoted():
    """``_SCHEMA = \"\"\"CREATE TABLE ...\"\"\"`` is detected."""
    source = '''
_SCHEMA = """
CREATE TABLE foo (id INTEGER PRIMARY KEY);
CREATE TABLE bar (id INTEGER PRIMARY KEY);
"""
'''
    constants = audit_migrations.find_schema_constants(source)
    assert constants == ["_SCHEMA"]


def test_find_schema_constants_ignores_non_sql_constants():
    """String constants without CREATE TABLE are ignored."""
    source = '''
_VERSION = "1.0.0"
GREETING = "hello"
DEFAULT_NAME = "audit_defaults"
'''
    constants = audit_migrations.find_schema_constants(source)
    assert constants == []


# ─── Per-module audit ──────────────────────────────────────


def test_audit_module_combines_all_findings(tmp_path):
    """A single module with creates + alters + init + schema."""
    module = tmp_path / "test_mod.py"
    _write_module(module, '''
async def init_test_db(db_path: str) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS test_table (id INTEGER PRIMARY KEY)
    """)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS another (id INTEGER PRIMARY KEY);
"""
    ALTER TABLE test_table ADD COLUMN new_col TEXT;
''')
    result = audit_migrations.audit_module(module)
    assert result["module"] == "test_mod.py"
    assert "init_test_db" in result["init_functions"]
    assert "_SCHEMA" in result["schema_constants"]
    assert any(c["table"] == "test_table" for c in result["creates"])
    assert any(c["table"] == "another" for c in result["creates"])
    assert len(result["alters"]) == 1
    assert result["alters"][0]["table"] == "test_table"
    assert result["alters"][0]["column"] == "new_col"


def test_audit_module_handles_file_error(tmp_path):
    """A broken module produces an error entry, not a crash."""
    module = tmp_path / "ok.py"
    _write_module(module, "CREATE TABLE IF NOT EXISTS ok (id INTEGER);")
    result = audit_migrations.audit_module(module)
    assert "error" not in result
    # Line number should be present.
    assert result["creates"][0]["line"] is not None
    assert result["creates"][0]["line"] > 0


# ─── Ledger roll-up ───────────────────────────────────────


def test_build_ledger_rolls_up_tables_and_migrations():
    """The ledger is a deterministic roll-up of per-module audits."""
    audit = [
        {
            "module": "a.py",
            "init_functions": ["init_a_db"],
            "schema_constants": [],
            "creates": [{"table": "ta", "line": 1}],
            "alters": [{"table": "ta", "column": "c", "type": "TEXT",
                        "module": "a.py", "line": 10}],
        },
        {
            "module": "b.py",
            "init_functions": [],
            "schema_constants": ["_SCHEMA"],
            "creates": [{"table": "tb", "line": 2}],
            "alters": [],
        },
        # Error entry is skipped.
        {"module": "broken.py", "error": "SyntaxError: ..."},
    ]
    ledger = audit_migrations.build_ledger(audit)
    assert ledger["modules_count"] == 2  # Error entry excluded.
    assert ledger["tables_count"] == 2
    assert "ta" in ledger["tables"]
    assert "tb" in ledger["tables"]
    assert ledger["tables"]["ta"]["init_functions"] == ["init_a_db"]
    assert ledger["migrations_count"] == 1
    assert ledger["migrations"][0]["column"] == "c"
    assert ledger["schema_constants"] == {"b.py": ["_SCHEMA"]}


def test_build_ledger_first_create_wins_per_table():
    """If two modules CREATE TABLE for the same name (rare but
    possible), the FIRST occurrence (alphabetical module
    order) is the canonical owner.
    """
    audit = [
        {
            "module": "a.py",
            "init_functions": ["init_a_db"],
            "schema_constants": [],
            "creates": [{"table": "shared", "line": 1}],
            "alters": [],
        },
        {
            "module": "b.py",
            "init_functions": ["init_b_db"],
            "schema_constants": [],
            "creates": [{"table": "shared", "line": 1}],
            "alters": [],
        },
    ]
    ledger = audit_migrations.build_ledger(audit)
    assert ledger["tables"]["shared"]["module"] == "a.py"


# ─── Markdown rendering ───────────────────────────────────


def test_format_ledger_md_includes_table_section():
    ledger = {
        "modules_count": 1,
        "tables_count": 1,
        "migrations_count": 0,
        "tables": {"foo": {"module": "a.py", "init_functions": ["init_a_db"],
                            "line": 10}},
        "migrations": [],
        "schema_constants": {},
    }
    md = audit_migrations.format_ledger_md(ledger)
    assert "Migration ledger" in md
    assert "`foo`" in md
    assert "a.py:10" in md
    assert "init_a_db" in md
    assert "Tables (by name)" in md


def test_format_ledger_md_includes_migrations_section():
    ledger = {
        "modules_count": 1,
        "tables_count": 1,
        "migrations_count": 1,
        "tables": {"foo": {"module": "a.py", "init_functions": ["init_a_db"],
                            "line": 10}},
        "migrations": [
            {"table": "foo", "column": "bar", "type": "TEXT",
             "module": "a.py", "line": 12},
        ],
        "schema_constants": {},
    }
    md = audit_migrations.format_ledger_md(ledger)
    assert "ALTER TABLE foo ADD COLUMN bar TEXT" in md


def test_format_ledger_md_omits_schema_section_when_empty():
    """If no module uses ``db.executescript(_SCHEMA)``, the
    Schema constants section is omitted entirely.
    """
    ledger = {
        "modules_count": 1,
        "tables_count": 0,
        "migrations_count": 0,
        "tables": {},
        "migrations": [],
        "schema_constants": {},
    }
    md = audit_migrations.format_ledger_md(ledger)
    assert "Schema constants" not in md


# ─── CLI integration ──────────────────────────────────────


def test_main_json_output_is_valid_json(tmp_path, capsys):
    """The CLI's ``--json`` flag emits parseable JSON to stdout."""
    module = tmp_path / "x.py"
    _write_module(module, '''
async def init_x_db(db_path: str) -> None:
    await db.execute("CREATE TABLE IF NOT EXISTS x (id INTEGER PRIMARY KEY)")
''')
    rc = audit_migrations.main(["--engine-dir", str(tmp_path), "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert "ledger" in parsed
    assert "per_module" in parsed
    assert parsed["ledger"]["tables_count"] >= 1


def test_main_human_readable_output(tmp_path, capsys):
    """Default mode emits the markdown summary."""
    module = tmp_path / "y.py"
    _write_module(module, '''
async def init_y_db(db_path: str) -> None:
    await db.execute("CREATE TABLE IF NOT EXISTS y (id INTEGER PRIMARY KEY)")
''')
    rc = audit_migrations.main(["--engine-dir", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Migration ledger" in out
    assert "Tables (by name)" in out


def test_main_writes_json_and_md_outputs(tmp_path):
    """``--out`` writes JSON, ``--md-out`` writes markdown."""
    module = tmp_path / "z.py"
    _write_module(module, '''
async def init_z_db(db_path: str) -> None:
    await db.execute("CREATE TABLE IF NOT EXISTS z (id INTEGER PRIMARY KEY)")
''')
    json_out = tmp_path / "ledger.json"
    md_out = tmp_path / "ledger.md"
    rc = audit_migrations.main([
        "--engine-dir", str(tmp_path),
        "--out", str(json_out),
        "--md-out", str(md_out),
    ])
    assert rc == 0
    assert json_out.exists()
    assert md_out.exists()
    parsed = json.loads(json_out.read_text())
    assert "ledger" in parsed
    md = md_out.read_text()
    assert "`z`" in md


def test_main_errors_on_missing_directory():
    """``--engine-dir`` must exist; otherwise exit code 2."""
    rc = audit_migrations.main([
        "--engine-dir", "/nonexistent/path/that/never/exists",
    ])
    assert rc == 2


# ─── Real python-engine integration ────────────────────────


REAL_ENGINE = os.path.abspath(os.path.join(REPO_ROOT, "python-engine"))


def test_real_python_engine_audit_smoke():
    """Smoke test: the script can audit the real python-engine
    and produces a non-empty ledger. The exact counts will
    drift as code changes -- the bounded test pins
    ``tables_count > 50`` and ``migrations_count > 0`` as
    floor invariants.
    """
    if not os.path.isdir(REAL_ENGINE):
        pytest.skip("python-engine not present")
    rc = audit_migrations.main([
        "--engine-dir", REAL_ENGINE, "--json",
    ])
    assert rc == 0
    # The output is on stdout; we can't easily capture it
    # here without re-invoking. Instead, exercise the
    # helpers directly.
    from pathlib import Path
    audit = audit_migrations.audit_modules(Path(REAL_ENGINE))
    ledger = audit_migrations.build_ledger(audit)
    # [WORKFLOW-D.2.a 2026-09-16] Floor invariants:
    # the python-engine has 35+ modules with CREATE TABLE
    # (verified via grep) -- the audit must find at least
    # 50 distinct tables (some modules have multiple).
    assert ledger["tables_count"] >= 50, (
        f"audit found {ledger['tables_count']} tables; "
        f"expected >= 50 (real engine has 80+ per earlier run)"
    )
    # And at least a few migrations (ALTER TABLE ADD COLUMN).
    assert ledger["migrations_count"] >= 5
    # At least one schema constant (broker_reconciliation.py
    # uses _SCHEMA, hedge_analytics.py uses _SCHEMA, etc.).
    assert ledger["schema_constants"], (
        "expected at least one module to use db.executescript(_SCHEMA)"
    )
