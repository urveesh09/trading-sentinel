# Workflow A5 — Collection completeness accuracy (DONE)

Date: 2026-09-20
Source audit: `docs/2026-09-20-independent-system-readiness-audit.md` §3-A5
Branch: `codex/production-correction-hedge-p0`
Status: ✅ shipped

## Problem

`partner_collection_attempts.session_readiness` had two defects:

1. Counted rows rather than distinct expected scheduler slots.
   Two attempts in the same minute slot counted as 2, so a
   missing attempt in a later slot did not register as
   missing.

2. Treated public unavailability specially only when ALL rows
   were unavailable. One unavailable + one observed + zero other
   gaps fell through to COMPLETE.

Independent reproducer:
  - Two expected rows, one OBSERVED + one UNAVAILABLE → reported
    COMPLETE with unavailable_count=1.
  - Two attempts in the same minute slot, no attempt in the
    next expected slot → reported COMPLETE with
    missing_schedule_count=0.

## Fix

1. **Distinct-slot bucketing** — `session_readiness` now buckets
   rows by `expected_at_utc` truncated to the interval
   granularity. Multiple rows in the same slot collapse to one
   distinct slot. The legacy "ATTEMPTED_UNAVAILABLE" branch
   is preserved for existing consumers; only fires when EVERY
   distinct slot is unavailable.
2. **Slot-aware state machine** — ANY unavailable OR missing OR
   incomplete slot promotes the per-index state to PARTIAL.
3. **`can_qualify` always False** — preserved as a constant
   property so existing consumers reading the field keep
   working. The audit's invariant: collection completeness
   does NOT confer strategy qualification.
4. **CLI new keys** — `collection_complete` and
   `eligible_for_replay` added to the audit report. The
   `can_qualify` field is preserved for byte-identical
   output.

## Files

| File | Change |
|---|---|
| `python-engine/partner_collection_attempts.py` | `session_readiness`: distinct-slot bucketing + slot-aware state machine + ATTEMPTED_UNAVAILABLE preserved. |
| `python-engine/tests/test_collection_completeness_reproducers.py` | New: 5 tests pinning every audit-acceptance check. |
| `scripts/audit_session_completeness.py` | `SessionAuditReport` adds `collection_complete` + `eligible_for_replay` properties; `can_qualify` is now always False. |
| `scripts/tests/test_audit_session_completeness.py` | Test updated to include new keys. |
| `docs/2026-09-20-workflow-a5-plan.md` | Plan slice. |
| `docs/2026-09-20-workflow-a5-evidence-accuracy-done.md` | This doc. |

## Tests

  - `tests/test_collection_completeness_reproducers.py` — **5/5 PASS**.
  - `tests/test_audit_session_completeness.py` — **all PASS**.
  - python-engine full suite — **4197 passed, 4 skipped**.
  - scripts full suite — **225 passed**.

## Acceptance

| Audit requirement | Result |
|---|---|
| Audit reproducer 1 (1 OBSERVED + 1 UNAVAILABLE) | ✅ `PARTIAL`, `unavailable_count=1` |
| Audit reproducer 2 (2 in same slot + 0 in next) | ✅ `PARTIAL`, `missing_schedule_count=1` |
| Genuine passing case | ✅ `COMPLETE` |
| `can_qualify` always False | ✅ preserved as constant property |

## Operator decisions still required

None for A5. A6 (readiness CLI accuracy) is the next slice.

## Rollout / rollback

  - Dev only.
  - The CLI tool's output schema gains two new keys; existing
    consumers that read only `can_qualify` continue to work.
  - Rollback = revert commit. No DB migration.
