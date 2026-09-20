# Workflow A6 — Readiness CLI accuracy (DONE)

Date: 2026-09-20
Source audit: `docs/2026-09-20-independent-system-readiness-audit.md` §3-A6
Branch: `codex/production-correction-hedge-p0`
Status: ✅ shipped

## Problem

The deployed-schema diagnostic correctly described no qualifications
but assigned WARN. Its exit contract returned success for WARN-only
results. An automation could interpret exit 0 as delivery-ready.

The audit's words:

> The profile and config PASS results are useful, but the overall
> exit is not a partner-delivery certificate.

Additionally, the audit required separating off-session stale
quotes from a broken in-session provider so a Sunday does not look
like a failed trading session.

## Fix

1. **`compatible_qualification` returns BLOCKER, not WARN** when
   no compatible row exists (the audit's required semantics). The
   diagnostic still describes what is wrong; the exit code
   separates "diagnostic ran" from "delivery is ready".

2. **New top-level `delivery_ready` boolean** in the JSON
   payload. `True` iff there are no BLOCKERs and no FAILs. The
   human-readable output also surfaces it on the first line.

3. **New CLI flag `--delivery-ready-only`** that exits 1 when
   the diagnostic ran cleanly but `delivery_ready=False`. This
   is the operator-friendly surface for automation.

4. **New `provider_freshness` check** that distinguishes three
   operational states:
   - `IN_SESSION` (market hours + last public quote fresh) → PASS
   - `OFF_SESSION` (Sunday / outside market hours + last quote
     older than 1h) → PASS (intentional quiet state)
   - `STALE_IN_SESSION` (market hours + last quote older than
     6m) → BLOCKER (real provider failure)
   - `NO_PROVIDER_INPUT` (no quote ever) → BLOCKER

5. **Updated exit codes**:
   - `2` any BLOCKER (delivery-blocking condition)
   - `1` any FAIL OR `delivery_ready` is False with `--delivery-ready-only`
   - `0` diagnostic ran, no FAIL/BLOCKER, delivery ready

## Files

| File | Change |
|---|---|
| `scripts/check_partner_readiness.py` | `compatible_qualification` BLOCKER; new `_check_provider_freshness`; new `--delivery-ready-only` flag; new `delivery_ready` boolean in JSON + human output. |
| `scripts/tests/test_check_partner_readiness.py` | New `test_delivery_ready_false_when_no_qualification`; updated `test_main_json_is_valid` for the new schema. |
| `docs/2026-09-20-workflow-a6-plan.md` | Plan slice. |
| `docs/2026-09-20-workflow-a6-readiness-cli-accuracy-done.md` | This doc. |

## Tests

  - `tests/test_check_partner_readiness.py` — **28/28 PASS** (was 26).
  - scripts full suite — **226 passed** (was 225).
  - python-engine full suite — **4197 passed, 4 skipped** (no regressions).

## Acceptance

| Audit requirement | Result |
|---|---|
| No qualifications + valid token/profile | ✅ `delivery_ready=False`, exit 2 |
| All PASS but no qualification | ✅ `delivery_ready=False`, exit 2 |
| All PASS including a qualification | ✅ `delivery_ready=True`, exit 0 |
| Off-session Sunday with stale last quote | ✅ `provider_freshness=PASS` |
| In-session with stale public quote | ✅ `provider_freshness=BLOCKER` |
| `--delivery-ready-only` flag | ✅ exit 1 when not delivery-ready |

## Operator decisions still required

None for A6. The audit's six defects A1-A6 are now fully closed.

## Rollout / rollback

  - Dev only.
  - Backward-compatible: existing consumers reading the
    per-check items continue to work; `delivery_ready` is an
    additional key. Exit codes for BLOCKER (2) and FAIL (1)
    unchanged; exit 0 now requires `delivery_ready=True` AND
    no FAIL/BLOCKER.
  - Rollback = revert commit. No DB migration.
