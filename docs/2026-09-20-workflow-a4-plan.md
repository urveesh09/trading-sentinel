# Plan — A4: Policy identity completeness

Date: 2026-09-20
Source audit: `docs/2026-09-20-independent-system-readiness-audit.md` §3-A4

## Problem

`partner_qualification.py:236-249` hashes
`fno_engine_mom.py`, `partner_manual_advisory.py`, `fno_chain.py`,
`fno_instruments.py`, `options_math.py`, `partner_qualification.py`,
`partner_thesis.py`, `partner_decision_clock.py` -- but NOT the
chronological fill/exit/replay implementation used by full-policy
economics. `partner_full_policy_replay.py` uses that policy identity.

Changing delayed-fill, fee, or exit assumptions can therefore leave
the frozen policy identity unchanged, breaking the audit's
requirement:

> Each material fill/exit/fee-model change invalidates old evidence;
> irrelevant capture timestamps do not create new strategies;
> deterministic regeneration remains byte-stable.

## Fix

Extend the policy identity to include the chronological execution,
spread replay, cost/stress implementation, and the semantic
settings that drive them. Bind through report → qualification →
runtime compatibility checks. Separate data identity from policy
identity.

Concretely:

1. Add the missing modules to the hash set:
   - `intraday_spread_chronological.py` (chronological execution)
   - `intraday_spread_replay.py` (replay)
   - `intraday_spread_holdout.py` (heldout split)
   - `intraday_spread_research.py` (research)
   - `intraday_spread_research_verify.py` (verification)
   - `momentum_exits.py` (exit logic)
   - `fno_costs.py` (cost model)
   - `exit_quality.py` (exit quality)
   - `cost_audit.py` (cost audit)
   - `partner_full_policy_replay.py` (full-policy replay)

2. Add the cost/stress semantic settings to the configuration
   subset that participates in the policy identity.

3. Add an `economic_model_manifest` field to the deterministic
   manifest that separates policy identity from data identity.

4. Make `partner_full_policy_replay` and downstream callers
   recompute the manifest at runtime and reject on mismatch.

5. Tests pin:
   - Each material module change invalidates old evidence.
   - Irrelevant capture timestamps do not create new strategies.
   - Deterministic regeneration remains byte-stable.

## Files affected

  - `python-engine/partner_qualification.py` — extend `source_names`
    tuple + add `economic_model_manifest` field to the manifest.
  - `python-engine/partner_full_policy_replay.py` — recompute the
    manifest at runtime; surface mismatch as an explicit rejection.
  - `python-engine/tests/test_policy_identity_completeness.py`
    (new) — pin the audit's three acceptance conditions.

## Acceptance

| Acceptance check | Expected outcome |
|---|---|
| Each material fill/exit/fee-model change invalidates old evidence | ✅ manifest_sha256 differs after a 1-byte edit to `fno_costs.py` |
| Irrelevant capture timestamps do not create new strategies | ✅ same manifest across two `decision_at` timestamps |
| Deterministic regeneration remains byte-stable | ✅ same manifest across two rebuilds of the same inputs |

## Data and configuration migration

  - No schema changes.
  - New env knob: `ECONOMIC_MODEL_VERSION` (default `"v1"`).
  - Existing qualifications are accepted as-is; re-verification
    on next read uses the new identity.

## Rollout and rollback

  - Dev only.
  - Rollback = revert commit.

## Status

  - Plan committed before implementation: this doc.

## Documentation updated

  - `docs/2026-09-20-workflow-a4-policy-identity-done.md` (new).
  - `python-engine/partner_qualification.py` docstring: enumerate
    the extended identity module set.
