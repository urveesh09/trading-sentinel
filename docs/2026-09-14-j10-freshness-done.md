# J.10.FRESHNESS — capture-freshness filter on the J.10 gate

## What landed

|| File | Type | Purpose |
|---|---|---|---|
| `python-engine/cas_reachability_freshness.py` | source (new, 95 lines) | Pure helpers: `capture_age_days(capture_path, *, now_utc=None)` (reads `generated_at_utc`, returns days-or-None) + `is_within_max_age(age_days, max_age_days)` (bounded comparison). |
| `python-engine/cas_reachability_gate.py` | source (extended) | New `max_age_days` kwarg on `cas_reachability_report`. New `captures_skipped_stale` field in the report (default 0, additive). `format_report` shows the stale line when >0. `update_summary` adds a `stale_clause` to the verdict paragraph when the filter dropped captures. |
| `python-engine/tools/cas_reachability_check.py` | CLI (extended) | New `--captures-since <DAYS>` flag. Non-positive values rejected at exit 2. Composes with `--json` / `--status`. |
| `python-engine/tests/test_cas_reachability_freshness.py` | test (new, 25 tests) | Pins `capture_age_days` (10 cases) + `is_within_max_age` (4) + gate integration (7) + format/SUMMARY (4). |
| `python-engine/tests/test_cas_reachability_check.py` | test (extended) | JSON-shape test now expects 9 keys (added `captures_skipped_stale`). 5 new CLI tests for `--captures-since`. |

## The third dimension of evidence

The J.10 gate's per-branch count is now driven by three filters:

1. **Bounded phase** (existing) — `rows[0].classifier_phase` must be in `_VALID_SESSION_PHASES`.
2. **Unique observation** (J.10.DEDUP) — SHA-256[:16] fingerprint; duplicate captures don't inflate the count.
3. **Freshness** (J.10.FRESHNESS, this slice) — `generated_at_utc` must be within `--captures-since` days.

A capture that fails the freshness check is counted under the
new `captures_skipped_stale` field (distinct from the existing
`captures_skipped` for malformed captures). The two categories
are kept separate so an operator can tell "we couldn't read it"
vs "we read it but it's old" at a glance.

## Design decisions

- **`generated_at_utc` is the freshness source of truth.** The
  J.3 capture schema (per `tools/j2_cas_probe.py::CAPTURE_JSON_SCHEMA`)
  guarantees `generated_at_utc` is an ISO 8601 timestamp with
  timezone info. The freshness helper rejects naive timestamps
  (schema violations) and unparseable values (return `None`).
- **Stale vs malformed are distinct categories.** A capture
  with bad schema → `captures_skipped`. A capture with good
  schema but old age → `captures_skipped_stale`. An operator
  reading the JSON report can tell which filter rejected each
  file.
- **Stale filter runs BEFORE fingerprint work.** A stale capture
  doesn't burn CPU on SHA-256 hashing. The order is: freshness
  → schema-validity → fingerprint-dedup → branch count.
- **Backwards-compatible default.** `max_age_days=None` (the
  CLI default) preserves the pre-freshness behaviour: every
  capture counts regardless of age. The `captures_skipped_stale`
  field is always present (default 0) so consumers can rely on
  the shape.
- **CLI rejects non-positive `--captures-since`.** The gate
  trusts the value when it's a positive float, but `<= 0` would
  be nonsensical (mark every capture as stale). CLI exits 2 with
  a structured diagnostic.
- **No clock injection.** `now_utc` defaults to
  `datetime.now(timezone.utc)`. Tests can override it via the
  keyword argument for deterministic age calculations.

## The defensive invariant

```text
A gate that was REACHABLE on stale evidence MUST flip to
UNREACHABLE when the operator applies a freshness filter.
```

This is the central invariant the slice defends. Test
`test_filter_drops_stale_to_unreachable` exercises it directly:
six 90-day-old captures are REACHABLE with no filter, UNREACHABLE
with `max_age_days=30`. Without the freshness filter, an operator
who hasn't refreshed the captures directory in months sees a
green REACHABLE that's actually based on stale evidence. The
filter exposes this gap.

## Senior-dev invariants preserved

- **NO deletions.** All existing behaviour preserved; the new
  field is additive; the new CLI flag is opt-in.
- **NO verdict-semantics change without consent.** The
  pre-freshness behaviour (no filter) is the default; the
  filter is opt-in via `--captures-since`. The verdict still
  answers "do all 6 branches have >= 1 capture?" -- the filter
  changes WHICH captures count, not the threshold.
- **NO F/G files touched.** Pure J.10 surface work.
- **NO new dependencies.** Stdlib only (`datetime`).
- **NO new tables, NO new SQL.** Freshness is computed
  in-memory during the existing `cas_reachability_report` walk.

## Verification

- Focused `tests/test_cas_reachability_freshness.py`: **25/25 PASS** in 0.56s.
- Wider J.10 surface (`test_cas_reachability_gate.py` +
  `test_cas_reachability_summary.py` + `test_cas_reachability_check.py`
  + `test_cas_reachability_dedup.py` + `test_cas_reachability_freshness.py`
  + `test_j10_closure_e2e.py` + `test_j3_capture_review.py`):
  **110/110 PASS** in 15.02s (was 80 before this slice; +30 net).
- Python-engine narrow regression surface (J + F + I +
  cas-reachability + main surface + holiday drift):
  **434/434 PASS** in 22.82s, 1 pre-existing Starlette
  lifespan deprecation warning (NOT a regression from this slice).
- CLI smoke tests:
  - `python tools/cas_reachability_check.py --captures-since 7`
    → stale captures skipped, `captures_skipped_stale` populated.
  - `python tools/cas_reachability_check.py --captures-since 0`
    → exit 2, "must be > 0 days" diagnostic.
  - `python tools/cas_reachability_check.py --captures-since 7 --json`
    → JSON output includes `captures_skipped_stale`.
  - `python tools/cas_reachability_check.py --captures-since 7 --status`
    → single-line status reflects the filtered verdict.

## Branch state

- **Branch:** `codex/production-correction-hedge-p0`
- **HEAD (this slice):** see `git log -1 --oneline` after commit
- **Working tree:** clean (committed in this slice's commit)
- **Pushed:** yes (this slice)

## What this enables

Operators can now answer "is the gate REACHABLE with **fresh**
evidence?" with one command:

```bash
python -m tools.cas_reachability_check --captures-since 7
```

The gate's verdict is honest about the age of its evidence. A
green REACHABLE under a 7-day filter means all 6 branches have
at least one unique capture collected in the last week. A red
UNREACHABLE under the same filter means at least one branch
needs a fresh capture.

This is the senior-dev right move: a REACHABLE verdict that
hides stale evidence is worse than UNREACHABLE, because it
gives the operator false confidence that auction-aware code
can ship. The freshness filter makes that gap visible.

## What this slice deliberately does NOT include

- **No cron-based auto-freshness.** The CLI is operator-invoked;
  wiring it into a cron is a follow-up if the operator asks.
- **No "stale captures get pruned" behaviour.** The filter
  SKIPS stale captures but never DELETES them. The captures
  directory is the operator's audit trail; the gate never
  touches the source of truth.
- **No freshness per branch.** A single `--captures-since`
  filter applies to all 6 branches uniformly. Per-branch
  freshness budgets (CAS_REFERENCE_PRICE_WINDOW: 30 days,
  CAS_POST: 7 days, etc.) could be a future slice if the
  operator wants that granularity. Out of scope here.
- **No F/G cross-workstream.** Pure J.10 surface.

## Status

J.10.FRESHNESS **DONE**. The J.10 gate now filters captures by
age, with `captures_skipped_stale` surfacing the filter's audit
trail. Backwards-compatible: the pre-freshness behaviour
(no filter) remains the default.

## J.10 surface trajectory

| Slice | Defence added |
|---|---|
| J.10 (`ba91dcc`+`414207e`) | The gate exists; `captured_phases` count drives verdict. |
| J.10.CLOSURE (`c734e4c`+`b8a490e`) | Schema-bug fix (`rows[]` iteration); SUMMARY.md audit surface. |
| J.10.CLOSURE catalog (`12912b1`) | Per-branch `captures_by_branch` catalog. |
| J.10.CLOSURE runbook (`1c35633`) | Per-branch IST-window cheat-sheet. |
| J.10.CLOSURE status (`2b7a670`) | `--status` single-line flag. |
| **J.10.DEDUP** (`52bc1f2`) | Unique-observation dedup; `duplicates_by_branch`. |
| **J.10.FRESHNESS** (this slice) | `--captures-since` filter; `captures_skipped_stale`. |

The gate now defends on three axes:
  - bounded phase,
  - unique observation,
  - fresh evidence.

A REACHABLE verdict under all three filters is genuinely
REACHABLE. That is the senior-dev contract.
