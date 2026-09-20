# Workflow A4 — Policy identity completeness (DONE)

Date: 2026-09-20
Source audit: `docs/2026-09-20-independent-system-readiness-audit.md` §3-A4
Branch: `codex/production-correction-hedge-p0`
Status: ✅ shipped

## Problem

`partner_qualification.py:236-249` hashed signal/candidate/chain/instrument/thesis/clock modules but NOT the chronological fill/exit/replay implementation used by full-policy economics. Changing delayed-fill, fee, or exit assumptions could therefore leave the frozen policy identity unchanged.

The audit's words:

> `partner_full_policy_replay.py` uses that policy identity.
> Changing delayed-fill, fee, or exit assumptions can therefore
> leave the frozen policy identity unchanged.

## Fix

1. **Extended module set** — `source_names` now includes
   `intraday_spread_chronological.py`,
   `intraday_spread_replay.py`,
   `intraday_spread_holdout.py`,
   `intraday_spread_research.py`,
   `intraday_spread_research_verify.py`,
   `momentum_exits.py`, `fno_costs.py`,
   `exit_quality.py`, `cost_audit.py`,
   `partner_full_policy_replay.py`. A change to any of these
   modules invalidates old identities.
2. **Extended config subset** — the cost/stress semantic
   settings (`FNO_TICK_SIZE`, `FNO_STOP_PREMIUM_PCT`,
   `FNO_SLIPPAGE_BPS`, `FNO_FEE_RATE`, `MOMENTUM_STOP_PCT`,
   `MOMENTUM_TARGET_R`, `PENNY_STOP_PCT`, `PENNY_FEE_RATE`,
   `PARTNER_VERIFY_RESEARCH_ARTIFACTS`) now participate in the
   identity. The subset comprehension uses `hasattr(settings,
   key)` so a partial deployment never crashes on a missing
   setting.
3. **Economic-model manifest** — a new field
   `economic_model_sha256` in the deterministic manifest binds
   the policy modules + config separately from the policy
   identity. A data-only change (a new bar capture timestamp)
   does NOT create a new economic-model strategy.
4. **Standalone helper `policy_identity.py`** —
   `policy_fingerprint(root)`, `economic_model_fingerprint(root,
   config)`, `module_sha256s(root)`. Pure of I/O. Caller reads
   the modules from disk and supplies the config dict. Used by
   downstream callers that need to recompute the fingerprint at
   runtime.

## Files

| File | Change |
|---|---|
| `python-engine/partner_qualification.py` | Extended `source_names`; extended config subset; new `economic_model` + `economic_model_sha256` fields in the deterministic manifest. |
| `python-engine/policy_identity.py` | New: `policy_fingerprint`, `economic_model_fingerprint`, `module_sha256s` helpers. |
| `python-engine/tests/test_policy_identity_completeness.py` | New: 11 tests pinning every audit-acceptance check. |
| `docs/2026-09-20-workflow-a4-plan.md` | Plan slice. |
| `docs/2026-09-20-workflow-a4-policy-identity-done.md` | This doc. |

## Tests

  - `tests/test_policy_identity_completeness.py` — **11/11 PASS** covering every audit-acceptance check plus defensive tests.
  - python-engine full suite — **4192 passed, 4 skipped** (was 4181 before; +11 new tests).

## Acceptance

| Audit requirement | Result |
|---|---|
| Each material fill/exit/fee-model change invalidates old evidence | ✅ helper's module set includes the A4 modules |
| Irrelevant capture timestamps do not create new strategies | ✅ data-only changes don't affect `economic_model_sha256` |
| Deterministic regeneration remains byte-stable | ✅ 10 repeated calls → 2 distinct fingerprints (policy + economic-model) |

## Operator decisions still required

None for A4. A5 (collection attempt store) and A6 (readiness CLI) are the next slices.

## Rollout / rollback

  - Dev only.
  - The existing `partner_qualification.policy_manifest` is now
    stricter: a missing module from the new set fails the
    integrity check (the helper skips, but the manifest's
    `source_sha256` field has the missing key so a caller can
    detect it).
  - Rollback = revert commit. No DB migration.
