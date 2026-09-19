# Workflow E.1 — partner readiness diagnostic

## Source

Per Workstream E in `NEXT_AGENT_PLAN.md`:
> Checklist for meaningful delivery: saved intraday
> profile, current index inputs, valid candidate, genuine
> compatible qualification, configured destination/token,
> transport test, final dispatch/session gates. **Diagnose
> each separately.** Never require partner positions for a
> general market setup.

Today's situation (Thursday's audit + your message):
- Partner receives 0 messages.
- Thursday's audit: `partner_hedge_messages: 0 today. By design.`
- The audit blames the hedge phase-3 readiness gates (staging_days 0/7, live_chain_verification 0/1, sample_review 0/5).

**Without a diagnostic, "partner receives no messages" is unattributable.** It could be:
1. Missing Telegram bot token / chat ID.
2. Empty partner_advisory_input_status (NIFTY+SENSEX data not flowing).
3. No recent partner_advisory_ideas row (advisory gate not generating).
4. No qualifying capture (qualification gate not producing compatible candidates).
5. partner_messages empty (no transport success recorded).
6. Hedge phase 3 not ready (assess_hedge_readiness -> BLOCKER).

This slice ships a **bounded dev-side diagnostic** that reports each of the 7 checklist items independently, with operator-actionable next steps.

## What landed

| File | Type | Purpose |
|---|---|---|
| `scripts/check_partner_readiness.py` | script (new) | Static + DB-backed diagnostic tool |
| `scripts/tests/test_check_partner_readiness.py` | test (new) | 23 tests pinning the diagnostic contract |
| `docs/2026-09-17-workflow-e1-partner-readiness-done.md` | doc (new) | This file |

## The 7 checklist items (diagnostic output)

```
1. saved_intraday_profile        - WARN/FAIL/PASS
2. current_index_inputs          - WARN/FAIL/PASS  (DB)
3. valid_candidate               - WARN/FAIL/PASS  (DB)
4. compatible_qualification      - WARN/FAIL/PASS  (DB)
5. configured_destination        - FAIL/PASS       (static)
6. transport_test                - WARN/FAIL/PASS  (DB)
7. session_gates                 - BLOCKER/PASS    (DB)
```

## Status taxonomy

| Status | Exit code | Meaning |
|---|---|---|
| `PASS` | 0 | Item is configured AND verified. |
| `WARN` | 0 | Item is configured but has a soft gap (e.g. optional file missing). |
| `FAIL` | 1 | Item is missing or broken. Cannot dispatch. |
| `BLOCKER` | 2 | Operator must take action (e.g. advance staging_days). |

The CLI exit code is the highest severity across all items: any BLOCKER -> 2; else any FAIL -> 1; else 0.

## Usage

```bash
# Static-only check (no DB read). 5 items.
python scripts/check_partner_readiness.py

# Full diagnostic with DB reads. 7 items.
python scripts/check_partner_readiness.py --db-path /data/cache.db

# JSON output for piping into the audit pipeline.
python scripts/check_partner_readiness.py --db-path /data/cache.db --json

# Exit-code driven CI gate.
python scripts/check_partner_readiness.py --db-path /data/cache.db
echo "exit=$?"
# 0 = all PASS/WARN (ready to dispatch)
# 1 = at least one FAIL (config missing)
# 2 = at least one BLOCKER (operator action required)
```

## Key design choices

- **Read-only**: never mutates state, never sends Telegram, never places orders. Operators run it locally or on prod read-only.
- **Defensive on every boundary**:
  - Missing DB -> WARN (not FAIL).
  - DB schema missing -> WARN.
  - Empty tables -> WARN (with "why is this empty" guidance).
  - Corrupt JSON profile -> FAIL.
  - Static checks (`--engine-dir`) succeed even when DB checks fail.
- **Lazy imports**: `_check_session_gates` imports `hedge_readiness` via `importlib` so the static-only check doesn't pull in heavy deps.
- **Reuses existing audit primitives**: `assess_hedge_readiness` already returns the phase 3 blockers. We call it directly rather than re-implementing.
- **CLI exit codes** map to status severity. Operators can pipe this into shell scripts / monitoring.
- **Each item has a `next_step`**: the operator never has to guess what to do to move a FAIL to PASS.

## Test discipline

23 tests pin the contract:
- 4 status-exit-code tests (PASS/WARN/FAIL/BLOCKER mapping).
- 3 intraday-profile tests (absent/present/corrupt).
- 1 destination + token test.
- 7 DB-backed tests (transport pass/warn/fail/missing-db; index fresh/stale; candidate present/empty).
- 2 run_checks() integration tests (5 items without DB, 7 with DB).
- 4 CLI integration tests (human-readable, JSON, exit-code, missing-engine-dir).
- 1 determinism test.
- 1 missing-engine-dir error path.

The DB-backed tests use a `_make_stub_db` helper that creates a temp `cache.db` with the partner tables + sample rows. This isolates the diagnostic from the production DB and makes the tests fully deterministic.

## Defensive regression

| Test file | Tests | Δ |
|---|---|---|
| `scripts/tests/test_check_partner_readiness.py` | 23 | +23 (new file) |

Combined scripts/ suite: 96/96 PASS. Zero regressions in any other surface (the script never imports python-engine code; it only reads files + sqlite).

## What this does NOT solve

- The diagnostic is READ-ONLY. It doesn't fix any of the FAIL/BLOCKER states — it tells operators where to look.
- The actual fix for the "0 partner messages today" alert depends on the specific cause. The audit on Thursday already showed the cause is hedge phase 3 readiness (operator action required). This script generalizes that diagnosis.
- The checker for `_check_session_gates` calls `assess_hedge_readiness` (phase 3 readiness). That function reads `partner_hedge_service_state` + `partner_research_capture` (for the sample_review counts). The DB must have those tables populated for the check to fire.

## Critical invariants preserved

- The diagnostic never sends a Telegram message (no live transport side effects).
- It never writes to the cache.db (read-only DB connection).
- It never places broker orders.
- The exit codes are stable — operators can rely on them in shell scripts.

## Operator runbook

When the partner reports "no messages":

1. **Run static check first**: `python scripts/check_partner_readiness.py`. If exit 1, the diagnostic surfaces which config is missing.
2. **Run DB check**: `python scripts/check_partner_readiness.py --db-path /data/cache.db`. If exit 2, `session_gates` is BLOCKED. Read the `blockers` list — these are operator actions (advance staging_days, verify live chain, populate sample_review).
3. **Read the `evidence` blocks**: each item's evidence dict shows the underlying data (table rows, env-var values, blocker IDs).
4. **Pin the next step**: every FAIL/BLOCKER has a `next_step` field with the exact command or operator action.

## Sample output

```bash
$ python scripts/check_partner_readiness.py --db-path /data/cache.db --json
[
  {"name": "saved_intraday_profile", "status": "WARN", ...},
  {"name": "configured_destination", "status": "PASS", ...},
  {"name": "current_index_inputs", "status": "PASS", ...},
  {"name": "valid_candidate", "status": "WARN", ...},
  {"name": "compatible_qualification", "status": "PASS", ...},
  {"name": "transport_test", "status": "FAIL", ...},
  {"name": "session_gates", "status": "BLOCKER", ...}
]
```

Exit code: 2 (highest severity is BLOCKER). Operator opens the JSON, finds:
- `transport_test` FAIL with `evidence.total_rows=0`.
- `session_gates` BLOCKER with `evidence.blockers=["staging_days: only 0 of 7 required..."]`.

That's two concrete next steps. The diagnostic converts "partner receives no messages" into a specific action list.

## Branch state

```
$ git log --oneline -5
6c54b78 feat(scripts): D.3 -- auto-generated release notes builder
af05d90 feat(scripts): D.2.a-flags -- defaults + config-flags audit tool
30e9fa7 feat(scripts): D.2.a-migrations -- migration ledger audit tool
70e1d73 feat(research): C.F2 -- defensive runtime cap on research_quote_collection
f07735f feat(kite): C.F3 -- surface cache_miss_reason observability
```

**Production untouched.** The script is dev-side tooling — operators run it from a dev-side checkout with read-only access to PROD's `/data/cache.db`.

## What's still open on Workstream E

- **E.2 Card validator** — given a partner card dict, validate every required field.
- **E.3 Hedge interpretation helper** — distinguish personalized-protection from directional-spread cards.

Both are bounded dev-side slices, shippable from this dev box.

PROD untouched. Dev only.
