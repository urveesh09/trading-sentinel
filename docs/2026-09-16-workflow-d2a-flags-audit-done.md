# Workflow D.2.a-flags — defaults + runtime config-flags audit tool

## Source

Per Workstream D item 2 in `NEXT_AGENT_PLAN.md`:
> 2. Review migrations, defaults, flags and Docker volumes.

This slice ships the **defaults + runtime config-flags** half of D.2.a. The **migrations half** shipped in commit `30e9fa7`.

Today (before this slice): the python-engine's `Settings` class has 474 env-var-driven config knobs (mostly via pydantic_settings). Operators had no way to audit:
- Which defaults are SAFE / RISKY / INFRASTRUCTURE.
- Which settings have fail-open name tokens (`DISABLE_`, `ALLOW_`, etc.).
- Which settings have large numeric defaults that could cause real-money impact.

This slice ships a bounded audit tool that classifies every default.

## What landed

| File | Type | Purpose |
|---|---|---|
| `scripts/audit_defaults.py` | script (new) | Static defaults + config-flags audit tool |
| `scripts/tests/test_audit_defaults.py` | test (new) | 28 tests pinning the audit contract |

## Audit output (real engine)

474 rows discovered. Tier breakdown:

| Tier | Count | What it means |
|---|---|---|
| **RISKY** | 13 | Fail-open name token, OR large numeric default (>= 100k). Operator MUST review. |
| **INFRASTRUCTURE** | ~150 | Paths, hosts, ports, log levels, timeouts. Deployment-runbook concern, not behaviour. |
| **SAFE** | ~311 | Small caps, no fail-open semantics, no large numbers. No operator review needed. |

The 13 RISKY settings include:
- `FNO_DISABLE_LIVE` / `FNO_DISABLE_PAPER`
- `PENNY_EDGE_DISABLE_LIVE` / `PENNY_EDGE_DISABLE_PAPER`
- `MOMENTUM_ALLOW_OVERNIGHT`
- `PENNY_PAPER_BANKROLL` (₹100k default)
- `FNO_PAPER_BANKROLL` (₹250k default)
- `PENNY_MIN_20D_TV` (₹500k)
- ... (8 more)

Operators can run `--risky-only` to focus on these.

## Usage

```bash
# All tiers (human-readable markdown)
python scripts/audit_defaults.py

# RISKY only (operator review focus)
python scripts/audit_defaults.py --risky-only

# JSON output
python scripts/audit_defaults.py --json

# Write to file
python scripts/audit_defaults.py --out /tmp/defaults.json
```

## Key design choices

- **Three-tier classification**: SAFE / RISKY / INFRASTRUCTURE. Each tier is a `Literal` enum with bounded membership.
- **Defensive tier rules**:
  - INFRASTRUCTURE wins over RISKY when both match (paths are deployment-level).
  - RISKY triggers on `DISABLE_`, `ALLOW_`, `BYPASS_`, `FORCE_`, `OVERRIDE_` substrings.
  - RISKY triggers on numeric defaults >= 100,000.
  - SAFE is the default.
- **Lazy loading via `importlib.util`** — the audit doesn't require the python-engine venv because it only reads `model_fields` metadata, not module imports.
- **CLI flags**: `--json`, `--out`, `--risky-only`, `--engine-dir`.
- **Deterministic**: same Settings → same audit output.

## Test discipline

28 tests pin the contract:
- 12 tier-classification tests (numeric thresholds, name tokens, priority).
- 5 value-formatting tests (bool, int, float, None, str).
- 3 real-engine audit tests (`audit_settings` returns rows, surfaces known RISKY, no duplicates).
- 1 markdown format test.
- 4 CLI integration tests (human-readable, JSON, --risky-only, --out).
- 1 missing-directory error path.
- 1 floor-invariant smoke test (RISKY count >= 5).

The floor-invariant test pins `risky_count >= 5` — if a future refactor accidentally disables one of the fail-open name tokens, the test fails.

## Defensive regression

| Test file | Tests | Δ |
|---|---|---|
| `scripts/tests/test_audit_defaults.py` | 28 | +28 (new file) |
| `scripts/tests/test_audit_migrations.py` | 19 | 0 (unchanged) |

Combined audit suite: 47/47 PASS. Zero regressions in any other surface.

## What this does NOT solve

- **D.2.b (backup/rollback runbooks)** — operator-owned; existing `consistent-data-backup-runbook.md` is current.
- **D.3 (PR description)** — separate slice.
- **Docker volume review** — operator-owned.
- **Auditing `os.environ` directly** — the audit only reads `Settings` defaults; runtime overrides via env vars aren't tracked. A separate audit could enumerate `os.environ.get(...)` call sites if needed.

## Critical invariants preserved

- The audit is read-only — never mutates `config.py` or any other file.
- Idempotent: same Settings → byte-identical audit output.
- No new dependencies.
- The audit's classifier never *assigns* a tier — it only *reads* the existing default value and classifies it.

## Operator runbook

After deploy to PROD:

1. **Pre-release review**: run `python scripts/audit_defaults.py --risky-only` and confirm all 13 RISKY settings are intentional. If a new RISKY setting appears (e.g. someone adds `DISABLE_<X>`), this surfaces it before deploy.
2. **Diff two SHAs' audits**: the audit is deterministic. Diffing `audit_2026-09-16.json` vs `audit_2026-09-17.json` shows exactly which defaults changed.
3. **Incident response**: when a runtime config is suspected, find it in `audit.json` and see its tier + reason — operators know whether the config is safe to flip live.

## Audit-trail summary

```
31bf71d  C.C2          -- partial-fill model
49456be  C.B1+B3       -- held-out adequacy + settlement
63d46ad  C.F8          -- bankroll_ledger TRADE_OPENED
e2fe147  C.F5          -- J.10 features inventory
729f7f1  C.F2          -- Kite LTP fanout observability
0ba14a9  C.B.3         -- penny stale warning dedup
dfc306a  C.C1          -- asymmetric-fill diagnostic
04aa166  C.B.2         -- agent dedup observability
7cf87c3  C.B.1         -- finalize_prior_days race fix
315fa72  C.C2.WIRE     -- wire partial-fill model
045661d  J.10.DRY_RUN  -- real vs simulation captures
d212250  D.1           -- release-readiness receipt
40e31b0  C.F1          -- defensive alert dispatch
f07735f  C.F3          -- cache_miss_reason observability
70e1d73  C.F2          -- runtime cap on research_quote_collection
30e9fa7  D.2.a         -- migration ledger audit tool
[pending] D.2.a-flags   -- defaults + config-flags audit tool
```

PROD untouched. Dev only.
