# Workflow C.C2.SOURCE — asymmetric quote-source binding

**Status:** IMPLEMENTED_AND_TESTED_DEV in implementation commit `e2212cb`;
push pending. Production is unchanged.

## Problem

The archive adapter proves each asymmetric quote packet, but its diagnostic
retains only depth. `replay_full_policy` therefore prices a modeled missing leg
from the earlier fully executable decision book rather than from the archived
asymmetric packet that caused the modeled-partial outcome. If prices moved
between those receipts, the retained `MODELED_PARTIAL_FILL_V1` P&L is causally
wrong even though its report hash is internally consistent.

## Files and contracts

- `python-engine/intraday_spread_archive_adapter.py`: retain a minimal,
  canonical, source-bound top-of-book projection for both legs in each
  asymmetric diagnostic, including packet hashes and quote clocks.
- `python-engine/partner_full_policy_replay.py`: price each modeled missing leg
  only from that asymmetric batch's projection. Never fall back to the earlier
  decision book. Legacy/incomplete projections fail closed as
  `partial_fill_model_unavailable`.
- Focused adapter, full-policy, held-out and qualification tests pin source
  choice, multiple-batch behavior and tamper rejection.

The output remains a modeled research result, not a broker fill, partner tip,
qualification decision, or order authorization. Existing full-spread replay
semantics and execution paths are unchanged.

## Acceptance checks

1. The pre-change focused baseline remains green: 86 tests with warnings fatal.
2. An asymmetric packet whose price differs from the decision book is priced
   from its own verified packet, with its raw packet hash retained.
3. Multiple asymmetric receipts retain and price their own observations in
   chronological order; no decision-book substitution occurs.
4. Missing/malformed source projections cannot produce a CLOSED result.
5. Rehashed mutation of retained source attribution is rejected by the
   held-out adapter, and normal full-policy/held-out behavior remains green.
6. Broader Workflow C tests, compilation, atlas generation, diff checks and an
   appropriate whole-engine regression pass.

## Rollout and rollback

This is an additive Dev research-report shape change with no database,
configuration, broker, delivery, flag, or Production mutation. Promote only
through the existing GitHub branch/review flow. Roll back the implementation
commit to restore the former diagnostic shape; immutable old reports remain
readable but cannot be newly accepted as source-bound modeled partials.

## Remaining work after this slice

Genuine multi-session captures, adequate predeclared held-out coverage,
operator qualification, real collection/retention observation, and
exchange/broker settlement evidence remain operational work. This correction
does not demonstrate profitability or make partner delivery production-ready.

## Verification receipt

- Pre-change focused baseline: 86 passed with warnings fatal.
- Post-change focused adapter/full-policy/held-out/qualification: 87 passed
  with warnings fatal in 4.03s.
- Broader Workflow C/research surface: 259 passed in 6.64s.
- Whole Python engine: 4,070 passed, four skipped and 42 known deprecation
  warnings in 205.51s. JUnit:
  `C:/Users/Urveesh/AppData/Local/Temp/sentinel-workflow-c-source-binding-20260919.xml`.
- Atlas regenerated at 202 modules; changed-source compilation and
  `git diff --check` passed.
- No database/configuration/data migration and no external or Production-side
  action.
- Implementation commit: `e2212cb` on
  `codex/production-correction-hedge-p0`.
