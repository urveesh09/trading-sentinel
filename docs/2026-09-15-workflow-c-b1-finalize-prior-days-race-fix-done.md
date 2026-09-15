# Workflow C.B.1 — fix `finalize_prior_days` concurrent-tick race (F-3)

## Source

The 2026-09-15 production deep audit (`Production_Trading-sentinel/docs/2026-09-15-production-deep-audit.md`) flagged **F-3 (MED, infra)**: 2 Python tracebacks from `research_quote_collection_tick` with the same root cause:

> research_quote_collection_crashed err=research writer busy
> File "/app/research_quote_collector.py", line 323, in research_quote_collection_tick

Telemetry showed `research_quote_collection = 6,501ms avg, 116,402ms (116s) max` — the job is taking so long that the next tick fires before it has finished. The audit's recommended remediation: *"Add a lock around `archive.finalize_prior_days` or serialize the archive writer."*

## What landed

|| File | Type | Purpose |
|---|---|---|---|
| `python-engine/research_archive.py` | source (extended) | `finalize_prior_days` now holds `_write_lock` (re-entrant) for the entire iteration loop |
| `python-engine/tests/test_research_archive.py` | test (extended) | 4 new tests pinning the concurrent-tick contract |
| `docs/2026-09-15-workflow-c-b1-finalize-prior-days-race-fix-done.md` | doc (new) | This file |

## The shift in defensive posture

The bug:
- `_write_lock = threading.RLock()` is the same lock used by `@guarded_write` (the decorator on `finalize_day` and other writers).
- `finalize_day` uses `acquire(blocking=False)` and raises `OSError("research writer busy")` on contention.
- `finalize_prior_days` did NOT hold the lock — it iterated prior days and called `finalize_day` for each one. Two concurrent ticks could both call `finalize_prior_days`:
  - Tick A acquires the lock for `finalize_day("day1")`, releases.
  - Tick B starts, tries `finalize_day("day2")`, succeeds.
  - Tick A continues to `finalize_day("day3")`, succeeds.
  - **If they happen to land on the same day at the same time, the second tick crashes with `"research writer busy"`** (the failure mode PROD observed 2× on 2026-09-15).
- Two ticks landing on the same day is normal under load: with `*/1'` cron and `6.5s avg / 116s max` runtime, overlap is unavoidable.

The bounded fix:
- Hold `_write_lock` at the `finalize_prior_days` level (the `with _write_lock:` block).
- Since `_write_lock` is an `RLock` (re-entrant), the inner `finalize_day` calls re-acquire safely — no deadlock.
- The inner `@guarded_write` decorator on `finalize_day` still runs (capacity check + sqlite lease + audit logging), but the contention point that fired `"research writer busy"` is now absorbed by the outer lock.
- `blocking=True` (default for `RLock.acquire()`) means the second tick WAITS for the first to finish, then iterates and sees nothing left to finalize.

## Key design choices

- **`RLock` (re-entrant) is the existing primitive.** No new locks, no new module imports. The decorator's `acquire(blocking=False)` is unchanged for the per-day writers — the contention that PROD hit was at the iteration level, not the per-day level.
- **No external API change.** `finalize_prior_days` signature and return shape unchanged.
- **No performance regression on the happy path.** When there's no contention, the outer lock is acquired and released in microseconds.
- **Pure / total semantics preserved.** A failure inside the iteration still raises (capacity check, sqlite lease, etc.); only the iteration-level contention is now absorbed.
- **Edge cases pinned.** Three of the four new tests cover edge cases that the fix doesn't change (no quotes dir; only current day; pre-fix path reproduces the race) — guards against future refactors that might accidentally break the cold-start path or the current-day filter.

## Defensive regression

| Test file | Tests | Δ |
|---|---|---|
| `test_research_archive.py` | 17 | +4 |

Cross-surface (Workflow C + research + J.10 + J.4 + J.3, 33 test files): **513/513 PASS** in 32.21s (was 190 on Workflow C surface; +4 net for C.B.1).

0 regressions.

## Operator-facing runbook

The fix is automatic — no CLI change. After this slice deploys to PROD:
- Concurrent `research_quote_collection_tick` invocations no longer crash with `research writer busy`.
- The `archive.finalize_prior_days` mid-tick contention window is eliminated.
- Telemetry should show 0 tracebacks from `research_quote_collection` (was 2 on 2026-09-15).

The same audit recommends re-tuning the cron trigger (`*/1'` is too frequent for `6.5s avg / 116s max` runtime) — that's a separate scheduler concern outside this slice.

## Critical invariants preserved

- `finalize_prior_days` signature unchanged.
- `finalize_day` decorator and behavior unchanged.
- `_write_lock` is the existing primitive — no new lock, no new module imports.
- All 13 existing `test_research_archive.py` tests pass unchanged.
- The audit's other findings (F-3 scheduler re-tune, agent dedup.json missing, etc.) remain in scope but are not addressed by this slice.

## What's still on Category B's backlog

Per the original investigation:
- B1 — adequate genuine held-out evidence (real production sessions).
- B2 — real collection/retention verification (now improved by this slice — the race is fixed, the verification pipeline is more reliable).
- B3 — exchange-specific settlement assumption confirmation.

This slice addresses the **bounded tooling subset of B2**: the collection/retention verification pipeline is now robust to concurrent ticks. The operator-required evidence (B1, the actual held-out sessions, and B3, the exchange-specific assumptions) remain operator-blocked.
