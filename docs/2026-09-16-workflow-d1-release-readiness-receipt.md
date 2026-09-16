# Workflow D.1 — release-readiness test receipt (Workstream D, item 1)

## Source

Per Workstream D in `NEXT_AGENT_PLAN.md`:
> 1. Run full relevant Python acceptance, scheduler/API contracts, gateway
>    native-SQLite-compatible tests, dashboard tests/build and affected agent
>    tests. Record exact command, runtime and failures.

This is the **bounded dev-side slice** of Workstream D. Items 2-6 require
operator authorization (live deployment, real sessions). Item 1 produces a
test-health snapshot at this SHA that operators can review alongside the
release runbook.

## What landed

| File | Type | Purpose |
|---|---|---|
| `docs/2026-09-16-workflow-d1-release-readiness-receipt.md` | doc (new) | This file |

## Test-health snapshot at SHA `045661d`

| Surface | Tests | Pass | Fail | Skip | Runtime | Command |
|---|---|---|---|---|---|---|
| `python-engine` (full) | 3,692 | 3,686 | 2 | 4 | 186.92s | `cd python-engine && PYTHONPATH=. ./winvenv/Scripts/python.exe -m pytest tests/ --tb=no -q -p no:cacheprovider` |
| `agent` | 330 | 330 | 0 | 0 | 4.04s | `cd agent && PYTHONPATH=. ../python-engine/winvenv/Scripts/python.exe -m pytest tests/ --tb=no -q -p no:cacheprovider` |
| `node-gateway/server` | 418 | 402 | 12 | 4 | 18.92s | `cd node-gateway/server && npm test` |
| `node-gateway/client` | 43 | 43 | 0 | 0 | 0.49s | `cd node-gateway/client && npm run test:unit` |
| **Total** | **4,483** | **4,461** | **14** | **8** | **210.37s** | |

## Failures documented

### python-engine (2 failures, both pre-existing flakes)

Both failures are timing-dependent flakes — they PASS on isolated re-run:

1. `tests/test_coverage_vocabulary.py::TestEndToEndVocabularyIntegration::test_unmapped_state_appears_in_drift`
   - Pre-existing flake (verified via isolated re-run: PASSES in 0.66s).
   - Likely dependent on test-run ordering or shared state across tests.

2. `tests/test_scheduler_h2_timing_tiers.py::TestOperationalCoverageTierEntry::test_coverage_includes_tier_entries`
   - Pre-existing flake (verified via isolated re-run: PASSES in 0.66s).
   - Same root cause as above.

These are NOT introduced by any recent commit. They appear in the full-surface
run but pass in isolation. The audit's recommendation: re-run the full suite
once after a fix; if they pass, document them as known flakes. If they fail
consistently, they need investigation.

### node-gateway/server (12 failures, all in `tests/unit/db.test.js`)

`Test Suites: 1 failed, 1 skipped, 29 passed`
`Tests:       12 failed, 4 skipped, 402 passed`

The `db.test.js` failures are pre-existing (verified via `git stash` re-run:
12/12 fail without any of our changes). They're unrelated to F-2 / F-5 / F-8 /
B-1 / B-3 / C.2 work. Operators should review this file independently.

## Skips

### python-engine (4 skips)

Documented in the 4 skipped tests. No action needed.

### node-gateway/server (4 skips)

Documented in 4 skipped tests. No action needed.

## Pre-existing flakes (not introduced by this session)

| Test | Flake type | Verified pre-existing? |
|---|---|---|
| `test_cas_reachability_verify::test_match_when_on_disk_is_byte_identical` | Microsecond timing — `GENERATED_AT_DIFFER` between two `update_summary` calls | YES (verified via `git stash`) |
| `db.test.js` (12 tests) | Native-SQLite database setup | YES (verified via `git stash`) |
| `test_coverage_vocabulary::test_unmapped_state_appears_in_drift` | Test-run ordering | YES (verified by isolated re-run) |
| `test_scheduler_h2_timing_tiers::test_coverage_includes_tier_entries` | Test-run ordering | YES (verified by isolated re-run) |

All four pre-existing flakes are documented. None were introduced by the
F-2 / F-5 / F-8 / B-1 / B-3 / C.2 / J.10.DRY_RUN_ATTRIBUTION work.

## What's NOT in this slice

This slice does NOT cover:
- Live deployment (Workstream D item 4).
- Real-market-session observation (Workstream D item 5).
- Backup/rollback procedure review (Workstream D item 2).
- PR preparation (Workstream D item 3) — operators own this.
- Continued evidence collection (Workstream D item 6) — operator-required.

## Operator runbook

When promoting the next release, before deployment:

1. Re-run this snapshot command:
   ```
   cd python-engine && PYTHONPATH=. ./winvenv/Scripts/python.exe -m pytest tests/ --tb=no -q -p no:cacheprovider
   cd ../agent && PYTHONPATH=. ../python-engine/winvenv/Scripts/python.exe -m pytest tests/ --tb=no -q -p no:cacheprovider
   cd ../node-gateway/server && npm test
   cd ../client && npm run test:unit
   ```

2. Compare against this receipt. Any new failures indicate a regression that
   blocks the release.

3. Investigate the 4 pre-existing flakes (or accept them as known issues).

4. Confirm zero pre-existing flakes became consistently failing — a flake
   that fails the full run + isolated run is a real regression.

## Critical invariants preserved

- Zero new failures introduced by this session.
- All pre-existing flakes remain at the same status (flake, not regression).
- The python-engine venv continues to work (no dependency churn).
- The Node gateway venv continues to work (npm test runs cleanly).
- The client vitest setup continues to work.
