# J.10.CAPTURE_SUMMARY_AGGREGATE — per-day capture histogram on the SUMMARY

## What landed

|| File | Type | Purpose |
|---|---|---|---|
| `python-engine/cas_reachability_aggregate.py` | source (new, 175 lines) | Pure helpers: `per_day_breakdown(captures_root, *, unique_per_path=None)` (buckets captures by `YYYY-MM-DD/` parent directory) + `format_per_day_table(per_day, *, max_rows=7)` (markdown rendering with collapse). |
| `python-engine/cas_reachability_gate.py` | source (extended) | New `first_occurrence_paths: set[str]` tracking during the loop. New `captures_per_day` field in the report dict (additive; default `{}`). The SUMMARY gains a `## Captures per day` section between the catalog and the duplicates. |
| `python-engine/tests/test_cas_reachability_aggregate.py` | test (new, 20 tests) | Pins the pure helpers + the gate integration + the SUMMARY rendering + the dedup-aware unique counting. |
| `python-engine/tests/test_cas_reachability_check.py` | test (extended) | JSON-shape test now expects 11 keys (added `captures_per_day`). |

## The completeness question

The J.10 SUMMARY surfaces TOTAL counts: `captures_scanned`,
`captures_skipped`, `captured_phases[phase]`. But the operator's
audit picture was incomplete — they couldn't tell *evidence
velocity over time*. A REACHABLE verdict with all evidence
collected on a single day three months ago is operationally
different from one with evidence collected across many recent
days.

The per-day histogram completes the picture: how many captures
per day, when the bulk of evidence was collected, and whether
evidence is concentrated or stale. This is the missing third
axis: not "what do we have" or "how fresh is it" (J.10.FRESHNESS)
but "is evidence distributed over time or stacked in a single
burst".

## Design decisions

- **Bucket by `YYYY-MM-DD/` parent directory.** Per the J.3
  contract (`docs/j2_captures/README.md`), captures live under
  per-day subdirectories. The histogram reads this directly from
  the path. A stray file at the captures_root level (no
  subdirectory) buckets under the literal `"(unfiled)"`
  sentinel — visible in the SUMMARY instead of silently dropped.
- **`scanned` vs `unique` columns.** `scanned` is every JSON
  file under that day regardless of validity. `unique` is the
  count of captures whose fingerprint was the FIRST occurrence
  under its branch (J.10.DEDUP semantics). The two columns
  together let the operator see "we found N files but only M
  contributed as evidence" — the duplicate surface.
- **Sorted ascending; collapse when too many.** Default
  `max_rows=7` keeps the SUMMARY readable. Operators with long
  histories get a `(+ N more days, oldest first)` footer that
  collapses to `max_rows - 1` rows. The most recent days
  remain visible at the bottom (per audit-utility logic:
  recency is what the operator scans first).
- **`"(unfiled)"` rows first.** Lex-sort would put
  `2026-09-XX` before `(unfiled)`. The helper explicitly
  forces `(unfiled)` to the top so the operator sees the
  unexpected first.
- **Dedup-aware unique counting.** When the gate passes the
  `first_occurrence_paths` mapping to `per_day_breakdown`,
  `unique` increments only for paths that contributed to
  coverage. Without the mapping, `unique == scanned` (the
  pre-dedup semantic). The gate always passes the mapping.
- **No new dependencies.** Stdlib only.

## The defensive invariant

```text
The SUMMARY's per-day histogram is honest about dedup: a
single unique observation under one branch contributes 1 to
``unique`` even when there are 5 byte-identical copies on disk.
The operator cannot be misled by file-count.
```

Test `test_dedup_inside_branch_does_not_inflate_unique` exercises
this directly: 3 byte-identical captures under one branch on
the same day → `scanned=3, unique=1`.

## Senior-dev invariants preserved

- **NO deletions.** All existing behaviour preserved.
- **NO F/G files touched.** Pure J.10 surface.
- **NO new dependencies.** Stdlib only (`pathlib`).
- **NO new tables, NO new SQL.** In-memory computation.
- **Backwards-compatible report shape.** The new field is
  ADDITIVE; the previous 10 fields are byte-identical.

## Verification

- Focused `tests/test_cas_reachability_aggregate.py`: **20/20 PASS** in 0.58s.
- Wider J.10 surface: **150/150 PASS** in 18.14s (was 130 before; +20 net).
- Python-engine narrow regression surface: **474/474 PASS** in 24.86s (was 454; +20 net), 1 pre-existing Starlette lifespan deprecation warning.

## Branch state

- **Branch:** `codex/production-correction-hedge-p0`
- **Pushed:** yes (this slice's commit lands before push)

## What this enables

Operators now see the **shape** of evidence collection over
time, not just totals. A SUMMARY that previously showed
"12 captures scanned, REACHABLE" now shows:

```
| Date       | Scanned | Unique |
|---|---|---|
| 2026-09-08 | 2 | 1 |
| 2026-09-09 | 3 | 2 |
| 2026-09-10 | 4 | 3 |
| 2026-09-14 | 3 | 0 |
```

The operator can immediately see: "2026-09-14 shows 3 scanned
but 0 unique — that's duplicate traffic that day; my J.10.DEDUP
filter is doing its job."

Combined with J.10.FRESHNESS (per-capture age) and J.10.MIN_THRESHOLD
(per-branch corroborating evidence), the operator has a
**complete audit picture**: distribution, freshness, and depth.

## What this slice deliberately does NOT include

- **No rolling-window aggregation.** The histogram is
  per-calendar-day, not per-7-day-window. A 7-day-window
  aggregation could be a future slice if the operator wants
  it. Out of scope here.
- **No time-of-day distribution.** The histogram buckets by
  date only; the IST-window cheat-sheet (in the SUMMARY's
  "How to add captures" section) already covers the time
  dimension.
- **No per-branch-per-day crosstab.** The histogram is per-day
  across all branches. A branch-by-day matrix would be useful
  for spotting "is one branch always skipped on Mondays?" but
  is a future slice if the operator wants it.
- **No F/G cross-workstream.** Pure J.10 surface.

## Status

J.10.CAPTURE_SUMMARY_AGGREGATE **DONE**. The J.10 SUMMARY now
surfaces a per-day histogram. Backwards-compatible: every
existing field is unchanged.

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
| **J.10.CAPTURE_SUMMARY_AGGREGATE** (this slice) | Per-day histogram; `captures_per_day` field; `## Captures per day` SUMMARY section. |

The SUMMARY now has:
  - `## Verdict` (overall status)
  - `## Captured per branch` (per-branch coverage)
  - `## Captures catalog` (every file backing each branch)
  - `## Captures per day` (NEW — evidence distribution over time)
  - `## Duplicate captures` (audit of redundancy)
  - `## Missing branches` (when UNREACHABLE)
  - `## How to add captures` (runbook)
  - `## What the gate enforces` (plan §14 reference)

The operator's audit picture is complete. The summary
answers every question the gate can prove.
