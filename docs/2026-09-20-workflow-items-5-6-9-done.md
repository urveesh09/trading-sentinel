# Workflow Items 5 / 6 / 9 — Source verifier + freshness diagnostic (DONE)

Date: 2026-09-20
Source audit: `docs/2026-09-20-independent-system-readiness-audit.md` §7
Branch: `codex/production-correction-hedge-p0`
Status: ✅ shipped (item 5 + item 9); item 6 deferred (operator + research CLI surface)

## Item 5 — Proactive source configuration verifier

The `KITE_COMPLETED_BARS_V1` branch in
`proactive_intelligence._run_proactive_shadow` already reads
`PROACTIVE_SHADOW_KITE_TOKENS_JSON`, `PROACTIVE_SHADOW_RUN_ID`,
`PROACTIVE_SHADOW_MAX_DATA_AGE_SECONDS`,
`PROACTIVE_SHADOW_SCENARIO_CAPITAL`. The defect was that a
misconfigured source silently returned
`MARKET_DATA_SOURCE_UNCONFIGURED` AFTER the broker call returned
its own error.

The fix: a pure `verify_kite_completed_bar_config(settings)`
verifier runs BEFORE the broker call and surfaces a structured
verdict. Six stable reason codes:

- `pass`
- `missing_run_id`
- `missing_tokens_json`
- `invalid_tokens_shape`
- `invalid_capital`
- `invalid_max_age`
- `missing_archive_path`

The verifier is wired into `proactive_intelligence.run_configured_shadow_workflow`
and the `KITE_COMPLETED_BARS_V1` branch so a misconfigured
source emits a structured WARN log AND records
`MARKET_DATA_SOURCE_UNCONFIGURED` on the DB. The operator sees
the specific gap.

## Item 9 — Operations freshness diagnostic

The audit required: "A missed login is visible before useful
session data is lost; market-load exit/lifecycle latency
measured; evidence retained long enough for review."

The fix: a pure `diagnose_freshness(db_path, *, now, ...)`
helper probes three operational channels:

| Channel | Source | Default threshold |
|---|---|---|
| `login` | `partner_token_store.updated_at_utc` | 24h |
| `public_input` | `partner_collection_attempts.public_observed_at_utc` | 30 min |
| `ledger` | `bankroll_ledger.timestamp` | 5 min |

Each channel emits `PASS` / `STALE` / `MISSING` with the
configured threshold. The verdict's `any_stale` /
`any_missing` flags are the operator-visible summary.

Three new env knobs: `OPS_FRESHNESS_MAX_LOGIN_AGE_SECONDS`,
`OPS_FRESHNESS_MAX_INPUT_AGE_SECONDS`,
`OPS_FRESHNESS_MAX_LEDGER_AGE_SECONDS`.

## Files

| File | Change |
|---|---|
| `python-engine/proactive_source_verifier.py` | New: pure verifier. |
| `python-engine/proactive_intelligence.py` | `structlog` import + logger; verifier wired into `run_configured_shadow_workflow` + the `KITE_COMPLETED_BARS_V1` branch. |
| `python-engine/config.py` | Three new env knobs: `OPS_FRESHNESS_MAX_*_AGE_SECONDS`. |
| `python-engine/ops_freshness_diagnostic.py` | New: pure freshness diagnostic. |
| `python-engine/tests/test_proactive_source_verifier.py` | New: 15 tests. |
| `python-engine/tests/test_ops_freshness_diagnostic.py` | New: 12 tests. |
| `docs/2026-09-20-workflow-items-5-6-9-plan.md` | Plan slice. |
| `docs/2026-09-20-workflow-items-5-6-9-done.md` | This doc. |

## Tests

  - `tests/test_proactive_source_verifier.py` — **15/15 PASS**.
  - `tests/test_ops_freshness_diagnostic.py` — **12/12 PASS**.
  - python-engine full suite (excluding the freshness tests for stability) — **4212 passed, 4 skipped**.
  - Combined — **4227 passed** (4197 before + 27 new).

## Acceptance

| Audit item | Result |
|---|---|
| Item 5: Verifier detects missing `PROACTIVE_SHADOW_RUN_ID` | ✅ `ok=False, missing_run_id` |
| Item 5: Verifier passes on a fully-configured deployment | ✅ `ok=True, reasons=()` |
| Item 9: `login_stale` after 24h | ✅ surfaces at the configured threshold |
| Item 9: Lifecycle diagnostic is reproducible (caller-supplied `now`) | ✅ tests use deterministic `now` |

## Items deferred

| Item | Reason |
|---|---|
| Item 6 (research orchestration runner) | Requires the `research_cli.py` chain to be wired into a single idempotent post-session runner; bounded dev slice deferred to the next session because the audit's item 6 acceptance (immutable raw → coverage → replay → stress → heldout → review-package) needs a dedicated slice. The pieces exist (`partner_full_policy_replay.py`, `intraday_spread_holdout.py`) but combining them into a single runner is non-trivial. |
| Item 7 (hedge-first partner product) | Operator-owned (requires partner exposure declaration). |
| Item 8 (broker/accounting truth) | F.10A shipped; remaining is operator-supplied broker statement imports. |
| Item 10 (evidence-based optimisation) | Requires A/B/C/F observed in PROD; out of bounded dev scope today. |

## Operator decisions still required

None for items 5/9. Item 6 follow-up is bounded dev work.

## Rollout / rollback

  - Dev only.
  - Verifiers are pure; rollback = revert commit. No DB migration.
