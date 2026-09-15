# J.10.BRANCH_HISTOGRAM — per-branch-per-day capture matrix

## What landed

|| File | Type | Purpose |
|---|---|---|---|
| `python-engine/cas_reachability_branch_histogram.py` | source (new, 200 lines) | Pure helpers: `branch_per_day_breakdown(captures_root, *, first_occurrence_per_path=None)` (walks the directory, buckets by branch AND date) + `format_branch_per_day_table(matrix, *, max_dates=7, show_unique=True)` (markdown rendering with column collapse). |
| `python-engine/cas_reachability_gate.py` | source (extended) | New `branch_per_day` field in the report dict (additive; default empty matrix on missing dir). New `## Captures per branch per day` SUMMARY section between per-day and duplicates. |
| `python-engine/tools/cas_reachability_check.py` | CLI (extended) | New `--show-branch-histogram` flag. When set, the human-readable report appends the matrix as a follow-up section. JSON output already includes the matrix as `branch_per_day` regardless of the flag. |
| `python-engine/tests/test_cas_reachability_branch_histogram.py` | test (new, 15 tests) | Pins the pure helpers + the format + the gate integration. |
| `python-engine/tests/test_cas_reachability_check.py` | test (extended) | JSON-shape test now expects 12 keys (added `branch_per_day`). 2 new CLI tests for `--show-branch-histogram`. |

## The matrix — the natural complement to the per-day histogram

The per-day histogram (J.10.CAPTURE_SUMMARY_AGGREGATE) tells
the operator "evidence is concentrated on 2026-09-10". The
matrix tells them "evidence is concentrated on 2026-09-10
for CAS_MATCHING, but CAS_REFERENCE_PRICE_WINDOW never got
refreshed".

The matrix is a 2D view: rows are the 6 required branches in
canonical order, columns are dates ascending, cells are the
unique count under that branch on that day. Empty cells render
as `-` so the operator can see at a glance which branches have
zero coverage and which branches are concentrated on a single
day.

## Design decisions

- **Lazy import to break the circular dependency.**
  `cas_reachability_branch_histogram` needs
  `CAS_BRANCHES_REQUIRING_EVIDENCE` and `_safe_phase_from_capture`
  from `cas_reachability_gate`, but `cas_reachability_gate`
  imports from `cas_reachability_branch_histogram` at module
  load. Lazy import inside the function body resolves the
  cycle without restructuring the modules. Documented at the
  top of the helper.
- **Dedup-aware unique count.** Same semantics as the per-day
  histogram (J.10.CAPTURE_SUMMARY_AGGREGATE): when the gate
  passes a `first_occurrence_per_path` mapping, only
  verdict-contributing paths increment `unique`. Three
  byte-identical captures under one branch on one day
  contribute `scanned=3, unique=1`.
- **`show_unique=False` switch.** Cells default to the
  post-dedup unique count. Operators can flip to raw scanned
  count when investigating "did the operator retry the probe?"
  (every retry is a new file, scanned counts them; unique
  counts only the first).
- **`max_dates=7` default.** Keeps the SUMMARY readable.
  Operators with long histories get a `(+ N more dates, oldest
  first)` footer.
- **Canonical branch order.** Rows are always in
  `CAS_BRANCHES_REQUIRING_EVIDENCE` order regardless of dict
  iteration order. Operators can pattern-match against the
  gate's other surfaces.
- **`(unfiled)` bucket for strays.** A capture at the captures
  root level (no `YYYY-MM-DD/` parent) lands in the `(unfiled)`
  column. Mirrors the per-day histogram.
- **`--show-branch-histogram` is additive to JSON output.**
  The matrix is ALWAYS in the JSON payload under `branch_per_day`
  (computed regardless of the flag). The flag only affects the
  human-readable output. Operators using `--json` for
  downstream tooling never need to set it.

## Senior-dev invariants preserved

- **NO deletions.** All previous fields preserved.
- **NO F/G files touched.** Pure J.10 surface.
- **NO new dependencies.** Stdlib only (`pathlib`).
- **NO new tables, NO new SQL.**
- **Backwards-compatible.** New field is additive; new CLI
  flag is opt-in.

## Verification

- Focused `tests/test_cas_reachability_branch_histogram.py`: **15/15 PASS** in 0.52s.
- Wider J.10 surface: **203/203 PASS** in 22.74s (was 186 before; +17 net).
- Python-engine narrow regression surface: **527/527 PASS** in 29.93s (was 510; +17 net), 1 pre-existing Starlette lifespan deprecation warning.

## Sample matrix output

```
| Branch                       | 2026-09-08 | 2026-09-09 | 2026-09-10 | 2026-09-11 | 2026-09-12 | 2026-09-13 | 2026-09-14 |
|---|---|---|---|---|---|---|---|
| CAS_REFERENCE_PRICE_WINDOW   | -          | -          | 1          | -          | -          | -          | -          |
| CAS_ORDER_ENTRY              | -          | -          | 1          | -          | -          | -          | -          |
| CAS_LIMIT_ENTRY_ONLY         | -          | -          | -          | -          | -          | -          | 1          |
| CAS_MATCHING                 | 1          | 1          | 1          | -          | 1          | -          | 1          |
| CAS_POST                     | -          | -          | -          | -          | -          | -          | 1          |
| DERIVATIVES_CAS_ALIGNED     | -          | -          | -          | -          | -          | -          | -          |
```

The operator reads this and immediately sees:
- CAS_REFERENCE_PRICE_WINDOW has 1 capture from 2026-09-10 (potentially stale).
- CAS_LIMIT_ENTRY_ONLY and CAS_POST both have only one capture each.
- CAS_MATCHING is the only branch with multi-day coverage.
- DERIVATIVES_CAS_ALIGNED has zero coverage (REACHABLE blocker).

## Branch state

- **Branch:** `codex/production-correction-hedge-p0`
- **Pushed:** yes (this slice's commit lands before push)

## What this enables

Operators can now answer "which branches need fresh evidence
on which days?" with a single matrix view:

```bash
python -m tools.cas_reachability_check --show-branch-histogram
python -m tools.cas_reachability_check --show-branch-histogram --json | jq '.branch_per_day'
```

The matrix completes the operator's audit picture alongside
the per-day histogram:
- Per-day histogram: "evidence is concentrated on day X"
- Per-branch matrix: "evidence is concentrated on day X for
  branch Y but not for branch Z"

Together: a complete audit of WHERE the evidence is and
WHICH BRANCHES are missing it.

## What this slice deliberately does NOT include

- **Per-day-per-branch-per-time-window matrix.** The current
  granularity is one day per column. A future slice could add
  time-of-day granularity (IST sub-windows) if operators want
  finer density charts. Out of scope here.
- **No cron wiring.** The matrix is computed on every CLI
  invocation; not wired into a periodic report. A future slice
  could add a cron that emails the matrix weekly.
- **No F/G cross-workstream.** Pure J.10 surface.

## Status

J.10.BRANCH_HISTOGRAM **DONE**. The per-branch-per-day matrix
completes the operator's audit picture alongside the per-day
histogram. Backwards-compatible: every existing field is
unchanged.

## J.10 surface trajectory

| Slice | Defence added |
|---|---|
| J.10 (`ba91dcc`+`414207e`) | The gate exists; `captured_phases` count drives verdict. |
| J.10.CLOSURE (`c734e4c`+`b8a490e`) | Schema-bug fix; SUMMARY.md audit surface. |
| J.10.CLOSURE catalog (`12912b1`) | Per-branch `captures_by_branch` catalog. |
| J.10.CLOSURE runbook (`1c35633`) | Per-branch IST-window cheat-sheet. |
| J.10.CLOSURE status (`2b7a670`) | `--status` single-line flag. |
| J.10.DEDUP (`52bc1f2`) | Unique-observation dedup; `duplicates_by_branch`. |
| J.10.FRESHNESS (`c99f510`) | `--captures-since` filter; `captures_skipped_stale`. |
| J.10.MIN_THRESHOLD (`5a5b3f1`) | `--min-unique-per-branch` threshold; `min_unique_per_branch`. |
| J.10.CAPTURE_SUMMARY_AGGREGATE (`2974bec`) | Per-day histogram; `captures_per_day`. |
| J.10.WRITE_ATOMIC (`66da1b0`) | Atomic + byte-identical JSON write. |
| J.10.CAPTURE_LISTING (`f2ce9db`) | `--list-captures` audit tool. |
| **J.10.BRANCH_HISTOGRAM** (this slice) | Per-branch-per-day matrix; `branch_per_day` field; `## Captures per branch per day` SUMMARY section. |

The gate + audit-tool pair is now complete:
  - The gate answers "is the J.10 gate REACHABLE?" with
    defensive filters + per-day histogram + per-branch matrix
    + atomic output.
  - The listing answers "what's on disk?" without computing a
    verdict.
  - Together: operator can audit the captures (listing), run
    the gate (verdict), inspect the per-day velocity, drill
    into the per-branch matrix, and read the SUMMARY — without
    any of these operations interfering with the others.
