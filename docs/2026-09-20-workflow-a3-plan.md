# Plan — A3: Qualification truth

Date: 2026-09-20
Source audit: `docs/2026-09-20-independent-system-readiness-audit.md` §3-A3

## Problem

`record_strategy_qualification` (partner_manual_advisory.py:535) accepts
a `dataset_ref` + a content SHA-256 string + description. It does NOT
read and verify the referenced report bytes. The qualification
registration requires the dataset_ref to exist in
`partner_advisory_research_artifacts` (good), but does NOT bind:

  - Verified heldout package (the report bytes match the SHA-256)
  - Frozen criteria (the report's policy fingerprint)
  - Review decision (operator identity + timestamp + outcome)
  - Expiry (the report is still valid)
  - Compatibility at candidate creation / final dispatch

The audit's words:

> This is **not an unauthenticated bypass**. An authorized operator
> is currently trusted to have done the research correctly. That
> contract is weaker than the envisioned machine-enforced evidence
> gate, particularly when an AI developer might populate fields
> merely to unblock delivery.

## Fix

A pure verifier `qualify_research_package` that:

1. Reads the referenced report bytes from a known root (filesystem
   or operator-supplied path).
2. Recomputes the SHA-256 and rejects mismatch.
3. Parses the report as JSON with a required schema:
   - `index` (NIFTY/SENSEX)
   - `structure_kind`
   - `horizon`
   - `policy_version`
   - `predeclared_criteria` (frozen list)
   - `heldout_split` (train/test dates)
   - `outcome_availability` (per-period realised vs unresolved)
   - `costs` (fee model + slippage assumptions)
   - `review_identity` (operator + timestamp)
   - `validity_period` (start + end, both timezone-aware)
4. Computes the policy identity fingerprint from the report's
   `policy_manifest` field and rejects if it doesn't match the
   current deployed code's fingerprint.
5. Returns a `QualificationVerdict` with:
   - `qualified` (bool)
   - `reason_codes` (stable enum strings)
   - `manifest_sha256` (canonical hash for binding)
   - `validity` (start, end, now → active/expired)
6. Wires the verifier into `record_strategy_qualification` so a
   qualification can only be recorded when:
   - The referenced artifact's bytes match its registered SHA-256
   - The artifact's `validity_period.end` is in the future
   - The artifact's policy manifest matches the deployed code
   - The review identity / timestamp is present and within bounds

## Files affected

  - `python-engine/qualification_verifier.py` (new) — pure verifier.
  - `python-engine/partner_manual_advisory.py` — `record_research_artifact`
    + `record_strategy_qualification` call the verifier.
  - `python-engine/routes_hedge.py` — POST routes surface
    `qualified`/`reason_codes` in the response so operators can see
    *why* a registration was rejected.
  - `python-engine/tests/test_qualification_verifier.py` (new) — unit tests.
  - `docs/2026-09-20-workflow-a3-qualification-truth-done.md`.

## Acceptance

| Acceptance check | Expected outcome |
|---|---|
| Made-up hash, valid shape | Reject at byte-verification step |
| Absent report (path missing) | Reject with reason `report_unreadable` |
| Failed/insufficient heldout result | Reject with reason `heldout_insufficient` |
| Changed configuration/economics | Reject with reason `policy_manifest_mismatch` |
| Expired review | Reject with reason `validity_expired` |
| Different index than artifact | Reject with reason `index_mismatch` |
| Genuine reviewed passing package | Qualifies; manifest_sha256 bound |
| Revocation (suspended status) | Card issuance blocks at dispatch |

## Data and configuration migration

  - No schema changes; existing `partner_advisory_research_artifacts`
    rows are accepted when re-verified.
  - Operators must supply an artifact root (env var
    `PARTNER_ARTIFACT_ROOT`, default `./artifacts/`).
  - A future migration may add a `verified_at` column on
    qualifications; deferred to a follow-up slice.

## Rollout and rollback

  - Dev only.
  - Backward-compatible at the schema layer: existing
    qualifications remain on disk; the verifier is invoked at
    registration time so historical artefacts cannot be
    re-recorded with stale manifests.
  - Rollback = revert commit. No DB migration.

## Status

  - Plan committed before implementation: this doc.

## Documentation updated

  - `docs/2026-09-20-workflow-a3-qualification-truth-done.md` (new).
  - `python-engine/qualification_verifier.py` docstring (new).
