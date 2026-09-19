# Workflow I usefulness contract correction plan

Date: 2026-09-19  
Environment: Dev only (`codex/production-correction-hedge-p0`)  
Production impact: none until normal GitHub promotion and deployment

## Problem

`agent/async_reviews.py::usefulness_snapshot()` emits ten bounded fields, but
`python-engine/optional_ai_status.py::_clean_usefulness()` accepts only six.
Consequently, enabling `OPTIONAL_AI_REPORT_USEFULNESS` makes a real agent status
post fail validation even though reduced test doubles pass. The agent's
contract-health allow-list also carries obsolete names (`last_response_seconds`
and `snapshot_at`) and omits real producer fields. The dashboard cannot show the
already-produced p95 latency or last completion clock.

This is an operational evidence defect. It does not authorize AI output to
change strategy, qualification, delivery, capital, risk, or orders.

## Files and contracts

- `agent/async_reviews.py`: authoritative ten-field producer shape; no behavior
  or authority change planned.
- `agent/contract_health.py`: align the usefulness allow-list with the actual
  producer while retaining prompt/review-content rejection.
- `python-engine/optional_ai_status.py`: accept and strictly normalize all ten
  producer fields; continue rejecting unknown keys, booleans, negative/nonfinite
  metrics, invalid rates, invalid timestamps, and unbounded verdict names.
- Agent and engine boundary tests: use the real producer snapshot, not a
  hand-maintained six-field fake, and prove full round-trip persistence.
- `node-gateway/client/src/pages/Dashboard.jsx`: render p95 latency and the last
  completed clock from the bounded envelope; retain the non-authoritative label.
- Canonical handover documents and generated code atlas: describe actual Dev
  behavior and exact verification evidence.

No schema migration is required: usefulness is already stored as bounded JSON
inside `optional_ai_status_reports.detail_json`. No environment default changes.

## Acceptance checks

1. A fresh real `AsyncReviewQueue.usefulness_snapshot()` contains exactly the
   documented ten keys and passes both agent contract health and the engine
   validator.
2. A populated ten-field envelope survives post, persistence, and load without
   losing valid values or changing execution authority.
3. Partial legacy six-field envelopes remain accepted.
4. Unknown/leakage fields, bool-as-number, negative/nonfinite latency, rates
   outside `[0, 1]`, naive/invalid completion clocks, and bad verdict buckets
   fail closed.
5. Dashboard source tests pin p95 and last-completion rendering; client unit
   tests and build pass.
6. Focused agent tests pass warning-fatal; focused engine tests pass; broader
   affected tests and the final whole-engine suite pass with known framework
   warnings recorded rather than hidden.
7. Atlas regeneration, Python compilation, diff review, clean worktree, commit,
   push, and post-push documentation consistency are recorded.

## Rollout and rollback

Roll out through the normal Dev commit/push/PR/merge/deploy path. After deploy,
operators may enable `OPTIONAL_AI_REPORT_USEFULNESS=true` on the agent and verify
that the engine retains current status plus all ten bounded fields. This flag
still requires an agent restart because it is read at module load.

Rollback is code-only: revert this slice through GitHub. Existing status rows
remain JSON-readable; a rollback consumer will reject future ten-field posts
rather than silently accepting unknown fields. If rollback is required before a
compatible consumer is restored, disable the opt-in flag and restart the agent.
Do not restore or delete Production data.

## Remaining work after this slice

- Real Production status/latency evidence and operator usefulness labels remain
  external acceptance work; tests do not prove annotation usefulness.
- Per-ticker usefulness breakdown remains a separately deferred I.4.G slice.
- Typed classification review provenance/expiry and any genuine qualification,
  partner delivery, or trading-performance gaps remain independent workstreams.

## Verification in progress

- Pre-change focused baseline: engine 50 passed with four known framework
  deprecations; agent 75 passed warning-fatal; dashboard 43 passed.
- Corrected focused engine: 72 passed with the same four known deprecations.
- Broader optional-AI engine: 89 passed with five known deprecations.
- Complete isolated agent: 340 passed warning-fatal, networking disabled, Dev
  source mounted read-only.
- Dashboard: 46 passed; Vite build passed with the existing Browserslist-data
  notice.
- Whole engine: 4,117 passed/four skipped/46 known framework deprecations in
  209.34s. JUnit:
  `C:/Users/Urveesh/AppData/Local/Temp/sentinel-workflow-i-usefulness-contract-20260919.xml`.
- Atlas regenerated at 203 modules; changed Python compilation and diff checks
  passed. The implementation commit/push receipt follows this source freeze.
