# Plan — Audit items 5, 6, 9 (research orchestration + ops)

Date: 2026-09-20
Source audit: `docs/2026-09-20-independent-system-readiness-audit.md` §7

## Items covered in this slice

| # | Item | Why this slice |
|---|---|---|
| 5 | Real proactive source activation (`KITE_COMPLETED_BARS_V1`) | The branch exists but lacks a configuration verifier. A misconfigured source silently returns `MARKET_DATA_SOURCE_UNCONFIGURED`; a verifier surfaces the gap before the broker call. |
| 6 | Research orchestration (extend `research_cli.py`) | Add an idempotent post-session runner that chains raw → coverage → replay → stress → heldout → review-package. |
| 9 | Production operations — login/input freshness alerts | A diagnostic that surfaces missed logins / stale inputs BEFORE useful session data is lost. |

These three are bounded dev work; they fit in one slice because they
all build on the same shadow-config and provenance surfaces.

## Items deferred

| # | Item | Reason |
|---|---|---|
| 7 | Hedge-first partner product | Operator-owned: requires the partner's exposure declaration (`general tips do not require positions`). No bounded dev slice without that input. |
| 8 | Broker/accounting truth | F.10A (`broker_internal_reconciliation.py`) already shipped; remaining work is operator-supplied broker statement imports. |
| 10 | Evidence-based optimisation | Requires A/B/C/F to be observed in PROD; out of scope for a bounded dev slice today. |

## Item 5 — Proactive source activation verifier

The `KITE_COMPLETED_BARS_V1` branch in `proactive_intelligence.py:2004`
already reads `PROACTIVE_SHADOW_KITE_TOKENS_JSON`,
`PROACTIVE_SHADOW_RUN_ID`, `PROACTIVE_SHADOW_MAX_DATA_AGE_SECONDS`,
`PROACTIVE_SHADOW_SCENARIO_CAPITAL`. A configuration verifier runs
BEFORE the broker call and surfaces a structured error if any
required field is missing or invalid.

1. New module `proactive_source_verifier.py` (pure).
2. Function `verify_kite_completed_bar_config(settings) ->
   ConfigVerdict` returns:
   - `ok: bool`
   - `reasons: tuple[str, ...]` — stable codes for each failure
   - `evidence: dict` — current values for each field
3. Wired into `proactive_intelligence._run_proactive_shadow` so the
   verifier runs first; failures map to the existing
   `MARKET_DATA_SOURCE_UNCONFIGURED` reason.

Stable reason codes:

- `missing_run_id`
- `missing_tokens_json`
- `invalid_tokens_shape` (not a dict)
- `invalid_capital` (≤ 0 or non-finite)
- `invalid_max_age` (≤ 0 or > 86400)
- `missing_archive_path`

## Item 6 — Research orchestration runner

The plan calls for an "idempotent bounded post-session runner" that
chains raw → coverage → replay → stress → heldout → review-package.
The pieces exist (`research_cli.py`, `partner_full_policy_replay.py`,
`intraday_spread_holdout.py`). The slice adds:

1. New module `research_pipeline.py` with
   `run_research_pipeline(db_path, session_date, ...) -> PipelineResult`.
   Each stage is gated by the previous stage's success.
2. Stages produce immutable `*_id` strings so a restart resumes
   from the last successful stage.
3. Idempotency: re-running the same session_date with the same
   input identity returns the same `*_id`s.
4. No broker call. No automatic qualification. The result is a
   review package the operator submits.

## Item 9 — Production operations alerts

The audit requires "missed login / input freshness alerts".
A diagnostic that surfaces these BEFORE useful session data is lost.

1. New module `ops_freshness_diagnostic.py` with
   `diagnose_freshness(db_path, *, now) -> Diagnostic` returning
   a structured verdict.
2. Surfaces:
   - Last successful Kite login
   - Last public-input observation
   - Last candidate capture
   - Last ledger write
   - Per-channel age in seconds vs a per-channel threshold
3. Wired into the existing `partner_orchestrator` lifecycle so a
   missed login is logged at WARN at session open and at BLOCKER
   at session close.

Stable diagnostic codes:

- `login_missing` — no successful Kite login ever recorded
- `login_stale` — last login older than `MAX_LOGIN_AGE_SECONDS` (default 24h)
- `input_stale` — last public observation older than
  `MAX_INPUT_AGE_SECONDS` (default 30m)
- `candidate_missing` — no candidate captured today
- `ledger_stale` — last ledger write older than
  `MAX_LEDGER_AGE_SECONDS` (default 5m)

## Files affected

- `python-engine/proactive_source_verifier.py` (new)
- `python-engine/proactive_intelligence.py` (verify before broker)
- `python-engine/research_pipeline.py` (new)
- `python-engine/ops_freshness_diagnostic.py` (new)
- `python-engine/partner_orchestrator.py` (lifecycle integration)
- `python-engine/config.py` (new thresholds)
- New tests in `python-engine/tests/`
- Done-docs

## Acceptance

| Item | Check | Expected |
|---|---|---|
| 5 | Verifier detects missing `PROACTIVE_SHADOW_RUN_ID` | `ok=False, reasons[0]='missing_run_id'` |
| 5 | Verifier passes on a fully-configured deployment | `ok=True, reasons=()` |
| 6 | Pipeline stages return stable IDs across two runs | IDs match |
| 6 | Pipeline aborts on a failed stage | next-stage not attempted |
| 9 | Diagnostic surfaces `login_stale` after 24h | `code='login_stale'` |
| 9 | Lifecycle logs WARN at session open, BLOCKER at close | surfaced |

## Rollout and rollback

  - Dev only.
  - Each verifier is pure; rollback = revert commit. No DB migration.
