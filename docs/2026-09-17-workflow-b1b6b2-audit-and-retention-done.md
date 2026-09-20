# Workflow B.1 + B.6 + B.2 — collection coverage + retention + gap audit

## Source

Per Workstream B in `NEXT_AGENT_PLAN.md`:
> Complete collection coverage, not just valid files.

The plan's relevant items:

1. Per-attempt records with expected schedule/cutoff
   (already shipped via `partner-collection-attempts.sqlite3`).
2. Public and candidate capture outcomes independently
   (already shipped).
3. Preserve all selected legs through the advice lifecycle
   (operator-verified).
4. Compute session completeness from expected market-aware
   intervals and retained attempt records. Distinguish
   never attempted, attempted unavailable, partial, stale,
   and complete.
5. Track quote and public-event gaps independently. Avoid
   pretending a stop between unobserved samples has a known
   fill.
7. Bound disk work (diagnostic — operator-owned queue
   decision).

## What shipped

### B.1 — Session Completeness Audit (`scripts/audit_session_completeness.py`)

- `CompletenessState` enum: `NEVER_ATTEMPTED` /
  `ATTEMPTED_UNAVAILABLE` / `PARTIAL` / `STALE` /
  `COMPLETE`.
- `UnderlyingAudit` + `SessionAuditReport` dataclasses
  with `can_qualify` aggregate.
- `audit_session(...)` wraps
  `PartnerCollectionAttemptStore.session_readiness()` and
  emits the report.
- CLI emits human-readable (default) or JSON
  (`--json`) report.
- 20 tests pinning the classification rules.

### B.6 — Archive Retention Audit (`scripts/audit_archive_retention.py`)

- `RetentionClass` enum: `REFERENCED` /
  `OLD_AND_UNREFERENCED` / `OLD_AND_REFERENCED` /
  `RECENT_AND_UNREFERENCED` / `MISSING`.
- `audit_retention(...)` walks the archive directory and
  classifies each file:
  - Old + unreferenced = `OLD_AND_UNREFERENCED`
    (cleanable).
  - Old + referenced = `OLD_AND_REFERENCED`
    (KEEP -- reference wins).
  - Recent + unreferenced = `RECENT_AND_UNREFERENCED`
    (wait).
  - DB-only artifact_refs that don't resolve to a file =
    `MISSING`.
- Lazy-loads `partner_collection_attempts` to avoid
  polluting `sys.modules` for other audit scripts.
- Skips `.sqlite3` files (always referenced by the
  system).
- 23 tests pinning the classification rules + DB-reference
  matching (absolute / relative / basename).

### B.2 — Gap Detector (`python-engine/gap_detector.py`)

- `Gap` + `GapSummary` + `GapSeverity` dataclasses.
- `detect_gaps(timestamps, max_acceptable_gap)` returns
  one `Gap` per pair of consecutive observations.
- `gap_crosses_entry_cutoff(gap, entry_cutoff_minute)`
  surfaces gaps that span the cutoff.
- `gap_could_hide_fill(gap, max_acceptable_gap)` enforces
  the plan's rule: gaps wider than the threshold
  represent unknown between-sample state.
- `audit_gaps(...)` end-to-end report with summary +
  fill_uncertain_gaps + crosses_entry_cutoff.
- Pure function. No I/O. No clock injection.
- 23 tests pinning the gap detection + classification.

## Tests

- `scripts/tests/test_audit_session_completeness.py`: 20/20 PASS.
- `scripts/tests/test_audit_archive_retention.py`: 23/23 PASS.
- `python-engine/tests/test_gap_detector.py`: 23/23 PASS.
- Combined scripts/: 200/201 PASS (1 pre-existing flaky
  test, NOT caused by B.6/B.2).
- Combined python-engine narrow regression + A-suite + B.2:
  283/283 PASS.
- Agent regression: 338/338 PASS.

## Production untouched

No edits to `Production_Trading-sentinel/`. The audit
scripts read PROD's archive + cache.db read-only.

## Acceptance (from plan)

- ✅ Per-attempt records with expected schedule/cutoff
  (B.1 + existing `partner-collection-attempts.sqlite3`).
- ✅ Public and candidate capture outcomes recorded
  independently (B.1 + existing tables).
- ✅ Session completeness classifies into the 5 states
  the plan calls out (NEVER_ATTEMPTED /
  ATTEMPTED_UNAVAILABLE / PARTIAL / STALE / COMPLETE).
- ✅ Quote and public-event gaps detected independently;
  "could hide a fill" rule enforced (B.2).
- ✅ Capture files referenced by qualification records
  out-live review (B.6).

## Operator-owned follow-ups

- B.3 (selected-leg persistence verification).
- B.4 (conditional-protection capture documentation).
- B.5 (saturation evidence diagnostic).

## What's left of Workstream B

The bounded dev work I haven't shipped yet:

| Slice | Description | Effort |
|---|---|---|
| B.3 | Selected-leg persistence verification | ~80 LoC + 8 tests |
| B.4 | Conditional-protection capture docs | ~50 LoC + 4 tests |
| B.5 | Saturation evidence diagnostic | ~120 LoC + 10 tests |

All bounded dev work. None operator-blocked.
