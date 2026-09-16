# Workflow D.2.a-migrations — migration ledger audit tool

## Source

Per Workstream D item 2 in `NEXT_AGENT_PLAN.md`:
> 2. Review migrations, defaults, flags and Docker volumes.
>    Establish consistent backup/rollback procedures without
>    deleting data.

The plan doc explicitly calls out:
> Lazy migrations/retention exist across modules, not one
> migration ledger.

Today (before this slice): 35+ python-engine modules each
have their own `async def init_<module>_db(db_path)`.
There's no single place operators can see "what tables
exist" or "what migrations apply". Reviewing pre-deploy
state requires `grep`-ing every module.

## What landed

| File | Type | Purpose |
|---|---|---|
| `scripts/audit_migrations.py` | script (new) | Static migration-ledger audit tool |
| `scripts/tests/test_audit_migrations.py` | test (new) | 19 tests pinning the audit contract |

## What the audit produces

The script walks every `*.py` in `python-engine/` (181 modules at this SHA) and emits a deterministic ledger:

- **80+ tables** discovered (CREATE TABLE statements across modules).
- **10+ ALTER TABLE ADD COLUMN migrations** (the schema-drift history).
- **15+ schema constants** (modules using `db.executescript(_SCHEMA)` rather than per-table CREATE).

Each entry is annotated with:
- `module:line` (where to find it in source).
- `init_function` (the `init_<module>_db` that owns the table).
- `schema_constant` (the `_SCHEMA` constant for executescript-based modules).

## Usage

```bash
# Human-readable markdown
python scripts/audit_migrations.py

# Machine-readable JSON
python scripts/audit_migrations.py --json

# Write to files
python scripts/audit_migrations.py \
    --out /tmp/migrations.json \
    --md-out /tmp/migrations.md
```

## Key design choices

- **Static analysis only.** The script never executes SQL. It reads `.py` files via regex against `CREATE TABLE` / `ALTER TABLE` / `async def init_<name>_db` / `_SCHEMA = "..."`.
- **Three-tier table discovery**:
  1. `CREATE TABLE foo (...)` inside an `init_<module>_db` function (the dominant pattern, ~80% of tables).
  2. `ALTER TABLE foo ADD COLUMN bar TYPE` inside an `init_<module>_db` function (the migration pattern, ~10 migrations today).
  3. `_SCHEMA = """CREATE TABLE ..."""` module-level constants executed via `db.executescript(_SCHEMA)` (the legacy broker-reconciliation / hedge-analytics pattern, ~15 modules).
- **Defensive line numbers.** The `regex` returns offsets; line numbers are computed by counting newlines up to the match start. Best-effort — non-blocking failures (None) are tolerated in the output.
- **Module-level filtering.** `__init__.py`, `test_*.py`, and dotfiles are skipped. Defensive: a broken module produces an `error` entry instead of crashing the whole audit.
- **First-create-wins** for duplicate `CREATE TABLE` (rare but possible when two modules both claim ownership). The first occurrence (alphabetical module order) is canonical.

## Test discipline

19 tests pin the contract:
- 3 SQL extraction tests (single create, multiple creates, alter table).
- 2 `init_<name>_db` finder tests (with/without return annotation, non-init skipped).
- 2 schema-constant finder tests (triple-quoted detected, non-SQL ignored).
- 2 per-module audit tests (combines all findings; broken module produces error entry).
- 2 ledger roll-up tests (tables + migrations aggregated; first-create-wins).
- 3 markdown rendering tests (table section, migrations section, schema section omitted when empty).
- 4 CLI integration tests (JSON output, human-readable, --out/--md-out, missing directory error code).
- 1 real-python-engine smoke test (floor invariants: tables >= 50, migrations >= 5, schema_constants non-empty).

The smoke test catches the bounded invariant that "the real engine must have at least 50 distinct tables and at least 5 migrations" — if a future refactor accidentally centralizes everything into one module, the audit will see the drop and the test will fail.

## Defensive regression

| Test file | Tests | Δ |
|---|---|---|
| `scripts/tests/test_audit_migrations.py` | 19 | +19 (new file) |

19/19 PASS. Zero regressions in any other surface (audit script never imports the python-engine code; it only reads file contents).

## What this does NOT solve

- **D.2.b (backup/rollback runbooks)** — operator-owned; existing `consistent-data-backup-runbook.md` is current.
- **Docker volume review** — operator-owned.
- **D.3 (PR description)** — separate slice.
- **Production migration verification** — the audit produces a ledger but doesn't execute the migrations on a fresh DB to verify they work. That's a separate concern.

## Critical invariants preserved

- The audit is read-only — never mutates the python-engine.
- No new dependencies (uses `re`, `pathlib`, `json`, `argparse` from stdlib).
- Idempotent: running it twice produces byte-identical output.
- The audit's regex matches the engine's conventions (CREATE TABLE, ALTER TABLE, init_<name>_db, _SCHEMA). If the engine's conventions change, the ledger will surface the gap.

## Operator runbook

After deploy to PROD:

1. **Before any future migration**: run `python scripts/audit_migrations.py --md-out /tmp/pre_migration.md` and review the ledger. If your new schema isn't there, the migration isn't routed through the audit's conventions.
2. **As a release gate**: the audit's output is deterministic — operators can diff two SHAs' ledgers to see exactly what changed.
3. **For incident response**: when a production table has unexpected schema, find its owner via the ledger's `module` field — point to the `init_<module>_db` source.
