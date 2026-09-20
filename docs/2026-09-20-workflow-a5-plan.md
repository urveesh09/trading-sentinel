# Plan — A5: Collection completeness accuracy

Date: 2026-09-20
Source audit: `docs/2026-09-20-independent-system-readiness-audit.md` §3-A5

## Problem

`partner_collection_attempts.session_readiness` (partner_collection_attempts.py:186-251) has two defects:

1. Counts rows rather than distinct expected scheduler slots.
   Two attempts in the same minute slot count as 2, so a
   missing attempt in a later slot does not register as missing.

2. Treats public unavailability specially only when ALL rows
   are unavailable. One unavailable + one observed + zero other
   gaps falls through to COMPLETE.

Independent reproducer:
  - Two expected rows, one OBSERVED + one UNAVAILABLE → reports
    COMPLETE with unavailable_count=1.
  - Two attempts in the same minute slot, no attempt in the
    next expected slot → reports COMPLETE with
    missing_schedule_count=0.

The audit:

> Collection completeness does not confer strategy qualification.
> The CLI is observational, so this is misleading output rather
> than a direct delivery bypass.

## Fix

Rewrite the per-index completeness state to:

1. Use **distinct scheduler slots**, not raw rows. Bucket the
   rows by ``expected_at_utc`` (truncated to the interval
   granularity) and use the bucket count for completeness math.

2. Classify each **distinct slot** as:
   - `OBSERVED` (the canonical bucket public_state)
   - `UNAVAILABLE` (the canonical bucket public_state)
   - `MISSING` (no row at all)

3. Compute the **bucket-aware** state:
   - `NEVER_ATTEMPTED`: no slots at all
   - `PARTIAL`: any slot missing OR unavailable OR incomplete
   - `STALE`: latest slot older than 2× interval
   - `COMPLETE`: every expected slot has a row, every row is
     OBSERVED, every row is complete

4. Keep `can_qualify=False` — the audit's intent is clear that
   collection completeness never confers strategy qualification.

## Files affected

  - `python-engine/partner_collection_attempts.py` — extend the
    session_readiness method.
  - `python-engine/scripts/audit_session_completeness.py` —
    rename output keys to `collection_complete` /
    `eligible_for_replay`; preserve `can_qualify=False`.
  - `python-engine/tests/test_collection_completeness_reproducers.py`
    (new) — pin the audit's two reproducers + a passing case.

## Acceptance

| Acceptance check | Expected outcome |
|---|---|
| Audit reproducer 1 (1 observed + 1 unavailable) | `PARTIAL`, `unavailable_count=1` |
| Audit reproducer 2 (2 in same slot + 0 in next) | `PARTIAL`, `missing_schedule_count=1` |
| Genuine passing case (every expected slot OBSERVED + complete) | `COMPLETE` |
| `can_qualify` always False | preserved |

## Data and configuration migration

  - No schema changes.
  - No env knobs.

## Rollout and rollback

  - Dev only.
  - The CLI tool's output schema gains two new keys; existing
    consumers that read the old keys continue to work.

## Status

  - Plan committed before implementation: this doc.

## Documentation updated

  - `docs/2026-09-20-workflow-a5-evidence-accuracy-done.md` (new).
  - `python-engine/partner_collection_attempts.py` docstring:
    enumerate the slot-bucketed state machine.
