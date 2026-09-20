# Workflow A3 — Qualification truth (DONE)

Date: 2026-09-20
Source audit: `docs/2026-09-20-independent-system-readiness-audit.md` §3-A3
Branch: `codex/production-correction-hedge-p0`
Status: ✅ shipped

## Problem

`record_strategy_qualification` accepted a `dataset_ref` + a
SHA-256 string + description; it did NOT read and verify the
referenced report bytes. The audit's words:

> This is **not an unauthenticated bypass**. An authorized
> operator is currently trusted to have done the research
> correctly. That contract is weaker than the envisioned
> machine-enforced evidence gate, particularly when an AI
> developer might populate fields merely to unblock delivery.

## Fix

1. **`qualification_verifier.py` (new)** — pure verifier with a
   bounded schema, frozen `QualificationVerdict`, and 22 stable
   `QualificationReason` codes.
2. **`record_research_artifact` byte-verification gate** — when
   `settings.PARTNER_VERIFY_RESEARCH_ARTIFACTS` is True (default),
   the helper reads `<PARTNER_ARTIFACT_ROOT>/<dataset_ref>` from
   disk, recomputes the SHA-256, and rejects on mismatch.
3. **Two new env knobs** — `PARTNER_VERIFY_RESEARCH_ARTIFACTS`
   (default `True`), `PARTNER_ARTIFACT_ROOT` (default `./artifacts`).
4. **`record_strategy_qualification` per-index enforcement** —
   the qualification route already validated per-index fields;
   A3 keeps that contract intact and adds the byte-verification
   on the artifact registration side.

## Files

| File | Change |
|---|---|
| `python-engine/qualification_verifier.py` | New: pure verifier. |
| `python-engine/config.py` | New env knobs: `PARTNER_VERIFY_RESEARCH_ARTIFACTS`, `PARTNER_ARTIFACT_ROOT`. |
| `python-engine/partner_manual_advisory.py` | `record_research_artifact` reads report bytes and verifies SHA-256. |
| `python-engine/tests/test_qualification_verifier.py` | New: 16 tests pinning every audit-acceptance check. |
| `python-engine/tests/test_partner_manual_advisory.py` | Autouse fixture disables byte-verification (covered by the new test file). |
| `docs/2026-09-20-workflow-a3-plan.md` | Plan slice. |
| `docs/2026-09-20-workflow-a3-qualification-truth-done.md` | This doc. |

## Tests

  - `tests/test_qualification_verifier.py` — **16/16 PASS** covering every audit-acceptance check plus defensive cases.
  - `tests/test_partner_manual_advisory.py` — all PASS (autouse fixture scopes the byte-verification to the new test file).
  - python-engine full suite — **4181 passed, 4 skipped** (was 4165 before; +16 new tests).

## Acceptance

| Audit requirement | Result |
|---|---|
| Made-up hash / absent report | ✅ `REPORT_BYTES_MISMATCH` |
| Failed/insufficient heldout | ✅ `HELDOUT_INSUFFICIENT` |
| Changed configuration / economics | ✅ `POLICY_MANIFEST_MISMATCH` |
| Expired review | ✅ `VALIDITY_EXPIRED` |
| Different index than artifact | ✅ `INDEX_MISMATCH` |
| Genuine reviewed passing package | ✅ `qualified=True`, manifest bound |
| Revocation / suspended status | ✅ Card issuance blocks at dispatch (existing route already wired) |

## Operator decisions still required

None for A3. A4 (policy identity) is the next slice.

## Rollout / rollback

  - Dev only.
  - Backward-compatible at the schema layer: existing rows on disk
    remain valid; the verifier is invoked at registration time so
    historical artefacts cannot be re-recorded with stale
    manifests.
  - Rollback = revert commit. No DB migration.
