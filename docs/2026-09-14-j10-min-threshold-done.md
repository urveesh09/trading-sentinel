# J.10.MIN_THRESHOLD — per-branch minimum-unique-captures threshold

## What landed

|| File | Type | Purpose |
|---|---|---|---|
| `python-engine/cas_reachability_threshold.py` | source (new, 50 lines) | Pure helper `meets_min_unique_threshold(branch_unique, min_unique)` — bounded set-style comparison. |
| `python-engine/cas_reachability_gate.py` | source (extended) | New `min_unique_per_branch: int = 1` kwarg on `cas_reachability_report`. New `min_unique_per_branch` field in the report dict (additive; default 1). The verdict's `missing_phases` is computed from the threshold predicate, not from `count == 0`. |
| `python-engine/tools/cas_reachability_check.py` | CLI (extended) | New `--min-unique-per-branch <N>` flag. Non-positive values rejected with exit 2. `--status` line now respects the threshold when computing `captured/total branches`. |
| `python-engine/tests/test_cas_reachability_threshold.py` | test (new, 16 tests) | Pins the pure helper + the gate integration + the format_report surface. |
| `python-engine/tests/test_cas_reachability_check.py` | test (extended) | JSON-shape test now expects 10 keys (added `min_unique_per_branch`). 4 new CLI tests for `--min-unique-per-branch`. |

## The defensive invariant

A single flaky capture must NOT flip the gate to REACHABLE.
The threshold filter is the third defensive layer (after
J.10.DEDUP uniqueness and J.10.FRESHNESS age-boundedness):
**every branch must have N unique observations**, not just
"at least one file on disk".

The default (`N=1`) preserves the pre-threshold behaviour
(no breaking change). Setting `--min-unique-per-branch 2`
requires corroborating evidence per branch — the senior-dev
right move for operators who want a higher bar for
auction-aware code shipping.

## Why the threshold counts UNIQUE, not files-on-disk

The threshold composes with J.10.DEDUP: it counts UNIQUE
fingerprints per branch, not files-on-disk. Three byte-identical
captures under one branch contribute 1 unique observation; the
threshold of 2 still rejects the branch.

This is the right semantic: a threshold of 2 means "we need
TWO independent observations", not "we need TWO files". The
dedup contract is preserved through the threshold filter.

## Why `--status` was patched

The CLI's `--status` line said "6/6 branches captured" even
when the verdict was UNREACHABLE (because of a high threshold).
This was a confusing diagnostic for shell prompts and monitoring
— the line should reflect the actual verdict. Patched:
the captured count uses the threshold predicate (`count >= N`),
not the pre-threshold `count > 0`.

## Design decisions

- **Default 1, opt-in for higher.** `min_unique_per_branch=1`
  is the pre-threshold behaviour; setting it higher requires
  explicit operator intent via the CLI.
- **CLI rejects `<= 0`.** Values at or below zero would mark
  every branch as captured regardless of evidence — nonsensical.
- **Field always present in report.** Even when the operator
  doesn't set a threshold, `min_unique_per_branch=1` is in the
  JSON. Consumers can rely on the shape.
- **Threshold composes with freshness.** Both filters can apply
  together: `--captures-since 7 --min-unique-per-branch 2` keeps
  only fresh captures AND requires 2 unique per branch.
- **The captured count in `captured_phases` is the unique
  count**, not the thresholded count. The operator sees
  progress (1/2 captured, 2/2 captured) without losing the
  raw number.

## Senior-dev invariants preserved

- **NO deletions.** All pre-threshold behaviour preserved when
  `min_unique_per_branch=1` (the default).
- **NO F/G files touched.** Pure J.10 surface work.
- **NO new dependencies.** Stdlib only.
- **NO new tables, NO new SQL.** In-memory comparison.

## Verification

- Focused `tests/test_cas_reachability_threshold.py`: **16/16 PASS** in 0.57s.
- Wider J.10 surface: **130/130 PASS** in 17.03s (was 110 before; +20 net).
- Python-engine narrow regression surface: **454/454 PASS** in 24.20s (was 434; +20 net), 1 pre-existing Starlette lifespan deprecation warning.
- CLI smoke tests:
  - `--min-unique-per-branch 2` keeps the gate UNREACHABLE with single-capture evidence.
  - `--min-unique-per-branch 0` rejected with exit 2.
  - `--min-unique-per-branch 2 --status` shows `0/6 branches` (not 6/6).

## Branch state

- **Branch:** `codex/production-correction-hedge-p0`
- **Pushed:** yes (this slice's commit lands before push)

## What this enables

Operators can now raise the bar for REACHABLE without
modifying the gate's code:

```bash
python -m tools.cas_reachability_check \
    --captures-since 7 \
    --min-unique-per-branch 2 \
    --status
```

The line reads: `J.10: REACHABLE 100.0% (6/6 branches, ...)`
only when every branch has at least 2 unique captures from
the last 7 days. Otherwise the gate stays UNREACHABLE.

A REACHABLE verdict under all four filters (bounded phase +
unique observation + fresh + threshold) is genuinely
REACHABLE. That is the senior-dev contract.

## What this slice deliberately does NOT include

- **No per-branch threshold budgets.** A single
  `--min-unique-per-branch` applies uniformly. Per-branch
  budgets (CAS_REFERENCE_PRICE_WINDOW: 2, CAS_POST: 1, etc.)
  could be a future slice if the operator wants that
  granularity. Out of scope here.
- **No cron-based auto-threshold.** The CLI is operator-invoked.
- **No F/G cross-workstream.** Pure J.10 surface.

## Status

J.10.MIN_THRESHOLD **DONE**. The J.10 gate now requires N
unique captures per branch (default 1, opt-in higher). Backwards-
compatible.

## J.10 surface trajectory

| Slice | Defence added |
|---|---|
| J.10 (`ba91dcc`+`414207e`) | The gate exists; `captured_phases` count drives verdict. |
| J.10.CLOSURE (`c734e4c`+`b8a490e`) | Schema-bug fix (`rows[]` iteration); SUMMARY.md audit surface. |
| J.10.CLOSURE catalog (`12912b1`) | Per-branch `captures_by_branch` catalog. |
| J.10.CLOSURE runbook (`1c35633`) | Per-branch IST-window cheat-sheet. |
| J.10.CLOSURE status (`2b7a670`) | `--status` single-line flag. |
| J.10.DEDUP (`52bc1f2`) | Unique-observation dedup; `duplicates_by_branch`. |
| J.10.FRESHNESS (`c99f510`) | `--captures-since` filter; `captures_skipped_stale`. |
| **J.10.MIN_THRESHOLD** (this slice) | `--min-unique-per-branch` threshold; `min_unique_per_branch`. |

The gate now defends on FOUR axes:
  - bounded phase,
  - unique observation,
  - fresh evidence,
  - corroborating evidence per branch.

A REACHABLE verdict under all four filters is genuinely
REACHABLE. That is the senior-dev contract.
