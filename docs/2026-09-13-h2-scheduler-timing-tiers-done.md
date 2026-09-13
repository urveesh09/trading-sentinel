# H2 (scheduler timing priority-tier breakdown) — done and committed

## What landed (commit `52f625e`)

**Branch**: `codex/production-correction-hedge-p0`
**Files changed**: 5 (1 new, 4 modified), +735 / -3 lines
**Tests**: +22 net passing
**Whole-engine**: 2,952 passed / 4 skipped / 39 warnings in 131.89s
**Status**: H2 done; remaining H3/H5 deferred.

## The gap we closed

Pre-fix, `scheduler_timing_report` grouped by literal `job_id` but **not by the §12 priority tier**. The operator could not see "the slowest stage across all exit-tier jobs" vs "the slowest scan-tier job"; tail-latency signals were buried under a flat per-job roll-up.

§12 specifies: *"Prioritize order exits and public advice management, then candidate scans, then research."* H2 ships the four priority tiers + a system meta-tier.

## Code surface

### `python-engine/scheduler_telemetry.py` (+207 lines)

- `JOB_TIER_MAP` — every registered `penny_*`, `fno_*`, `partner_*`, and system job_id classified into one of the four §12 priority tiers (`exit`, `advice`, `scan`, `research`) plus a `system` meta-tier for bootstrap/login/circuit-breaker jobs.
- `TIER_ORDER` — the priority sequence in §12 spec order.
- `_tier_for(job_id)` — returns `"other"` for unrecognised ids so the roll-up never silently drops a job.
- `_aggregate_by_tier(jobs)` — per-tier `runs`, `executed_runs`, `rejected`, `in_flight`, `results`, `elapsed_seconds` (p50/p95/max across the **union of samples**, not the median of per-job medians), and per-stage `stage_durations` percentiles.
- `scheduler_timing_report` extended with a top-level `by_tier` key. **Existing keys (`boot_id`, `events`, `jobs`, `inflight`, `note`) remain byte-identical.**
- A tier with zero jobs returns `None` (not `0`) for all numeric fields, per §12 acceptance: *"UI fixture covers unavailable and zero distinctly."*

### `python-engine/operational_coverage.py` (+37 lines)

- One `scheduler_tier:{tier_name}` entry per tier so `/analytics/operational-coverage` surfaces tier-level coverage. Empty tiers emit `state="UNCONFIGURED"`, `reason="no_jobs_in_tier"`.

### `python-engine/tests/test_scheduler_h2_timing_tiers.py` (NEW, 22 tests)

- `JOB_TIER_MAP` completeness: every registered penny/fno/partner/system job is classified.
- `TIER_ORDER` priority sequence.
- `unrecognised → "other"`.
- All six tiers present in `by_tier` regardless of data.
- Empty-tier returns `None` (with explanatory note).
- Single-sample returns that sample unchanged.
- Per-tier percentile math (multiple samples, multiple jobs).
- Stage-duration aggregation across jobs.
- `results` merge across jobs.
- `rejected` counter semantics (incremented on `event_kind=SCHEDULER_REJECTED`, NOT on `result=REJECTED`).
- Inf-sample filtering at the roll-up layer.
- `operational_coverage_report` tier-entry integration.

## Senior-dev design choices

1. **Defence at the roll-up layer, NOT at `_percentiles`.** Adding a `ValueError`-on-Inf guard to `_percentiles` would change behaviour for any caller passing Inf. The per-tier roll-up filters Inf at its own boundary instead. Existing callers unaffected.
2. **Per-tier `elapsed_seconds` is the UNION of samples**, NOT the median of per-job medians. The operator wants "the slowest stage across this priority bucket", not "the average of medians" which can hide a tail.
3. **Unrecognised jobs land in `"other"`, not silently dropped.** A future agent who adds a job must add it to `JOB_TIER_MAP`; the test `test_every_registered_*_job_maps_to_a_known_tier` catches the silent drop.
4. **Empty-tier returns `None` for all numeric fields**, with an explanatory note. This honours §12's *"UI fixture covers unavailable and zero distinctly"* — the dashboard can distinguish "no data" from "instant" without a second probe.
5. **`system` meta-tier for bootstrap/login/circuit-breaker.** Honest accounting; the cron itself is the operator signal that the system is alive. Folded into one of the four §12 buckets would distort the priority accounting.

## Senior-dev self-corrections in this slice

1. **First aggregation had `elapsed_samples` declared but never populated.** The smoke test caught it: each tier had correct job_count but `p50=None, p95=None, max=None`. Fixed by iterating the per-job `elapsed_samples` and adding `math.isfinite` filtering.
2. **`_percentiles` doesn't reject Inf by itself.** I wrote a test asserting `ValueError`; that was wrong (it would be a behaviour change for existing callers). Fixed the test to assert the *roll-up layer* filters Inf — that's where the actual defence lives.
3. **`rejected` counter is on `event_kind`, not `result`.** I wrote a test using `result="REJECTED"`; the source only increments `rejected` on `event_kind="SCHEDULER_REJECTED"` (set by `attach_scheduler_listener`). Fixed the test to insert the row directly with the correct `event_kind`.

## Verification

| | Before H2 | After H2 |
|---|---|---|
| **Python suite** | 2,930 pass | **2,952 pass** (+22) |
| **Time** | 129.02s | 131.89s |
| **Skipped** | 4 | 4 |
| **Warnings** | 39 | 39 (no new) |

Stable across 2 full-suite reruns (131.89s, 130.78s).

## What was explicitly NOT done in this slice

- **No H3 (intraday-cache diagnostic)** — deferred to the next H slice.
- **No H4 (cache-add)** — explicitly deferred per §12; requires operator sign-off after H3's diagnostic conclusion.
- **No H5 (dashboard readiness)** — deferred.
- **No modification of `_percentiles` itself** — the roll-up layer filters Inf; the helper is unchanged.
- **No golden regeneration** — the route surface is unchanged; the only new keys are inside the existing `scheduler_timing_report` JSON shape (which is consumed but not pinned by a golden).

## Reference paths

- `docs/2026-09-13-workflow-f-state-of-codebase-audit.md` section 13 (new this commit) — full description, invariants, verification numbers.
- `docs/NEXT_AGENT_PLAN.md` requirement matrix row H — updated to "IMPLEMENTING (H1 closed and PROD-ready; H2 priority-tier breakdown closed; remaining H3/H5 deferred)".

## Operator-facing usage

```python
from scheduler_telemetry import scheduler_timing_report

rep = await scheduler_timing_report(db_path, limit=500)

# Old: per-job roll-up still works exactly as before.
rep["jobs"]["penny_edge_exit"]["elapsed_seconds"]  # {"p50": ..., "p95": ..., "max": ...}

# New: per-tier roll-up.
rep["by_tier"]["exit"]["elapsed_seconds"]     # p50/p95/max across ALL exit-tier jobs
rep["by_tier"]["exit"]["stage_durations"]     # per-stage aggregation
rep["by_tier"]["scan"]["elapsed_seconds"]      # None if no scan-tier jobs ran
rep["by_tier"]["other"]                        # catches unrecognised job_ids

# Tier-level coverage:
from operational_coverage import operational_coverage_report
rep = await operational_coverage_report(db_path)
rep["producers"]["scheduler_tier:exit"]        # OBSERVED + counts
rep["producers"]["scheduler_tier:scan"]        # UNCONFIGURED + "no_jobs_in_tier"
```

## Next H phases (deferred)

- **H3** (Phase 3): Intraday-cache caller/key/window diagnostic — pure read-only enumeration of `intraday_cache` read sites + freshness classification.
- **H4** (Phase 4): Cache-add — DEFERRED until operator sign-off after H3.
- **H5** (Phase 5): Dashboard readiness reasons — `operational_coverage_report` extended with §12 vocabulary (`disabled`, `unconfigured`, `no_session`, `no_setup`, `no_evidence`, `stale`, `error`).
