# J.10.CAPTURE_LISTING — fast, side-effect-free audit tool for the captures directory

## What landed

|| File | Type | Purpose |
|---|---|---|---|
| `python-engine/cas_reachability_listing.py` | source (new, 130 lines) | Pure helpers: `list_captures(captures_root)` (walks the directory, groups by `rows[0].classifier_phase`) + `format_listing(listing)` (deterministic human-readable rendering). |
| `python-engine/tools/cas_reachability_check.py` | CLI (extended) | New `--list-captures` flag. Short-circuits the verdict walk; tolerates missing directories; mutually exclusive with `--status` / `--update-summary` / `--write` / `--captures-since` / `--min-unique-per-branch`. |
| `python-engine/tests/test_cas_reachability_listing.py` | test (new, 23 tests) | Pins the helper contract + format_listing + CLI surface + mutual-exclusion enforcement. |

## The audit-tool gap

The full `cas_reachability_report` walk does fingerprinting,
freshness checks, dedup logic, per-day aggregation, and threshold
verification. An operator asking "what captures exist on disk?"
doesn't need any of that — they want a fast, side-effect-free
listing that prints the captures grouped by branch.

Without this slice, the operator had two options:
  1. Run the full gate (slow, returns a verdict, prints verdict
     machinery they don't want).
  2. Use `find docs/j2_captures/` (works but doesn't group by
     branch; the operator has to mentally re-key each file's
     `rows[0].classifier_phase`).

`--list-captures` gives them the third option they actually
want: a structured listing that runs in milliseconds, doesn't
compute a verdict, and groups captures by branch.

## Design decisions

- **Pure helper, no verdict logic.** `list_captures` only
  reads `rows[0].classifier_phase` per file (the J.3 schema's
  bounded phase). No fingerprinting, no freshness check, no
  dedup, no per-day aggregation. The listing is FAST: O(N) on
  file reads, no SHA-256 hashing, no JSON parsing beyond
  `rows[0].classifier_phase`.
- **Tolerates missing directories.** Unlike the gate (which
  exits 2 on a missing captures dir), the listing returns an
  empty listing. The operator gets a clean "0 captures" report
  instead of an error. The audit tool never fails.
- **Always exits 0.** The listing is informational only. A
  missing captures dir is not an error for an audit tool —
  it's just an empty listing. The operator can't accidentally
  fail their shell pipeline with `--list-captures`.
- **Cross-platform path normalisation.** Python's
  `Path.relative_to` returns paths with the OS separator
  (`\` on Windows); downstream consumers expect the JSON-
  canonical forward slash. The listing normalises to
  forward slashes (`str(rel).replace(os.sep, "/")`). The gate's
  `cas_reachability_report` does NOT normalise today — this is
  a fresh audit-tool contract; changing the gate is a separate
  concern (out of scope; would be an unrequested behaviour
  change for existing consumers).
- **Mutually exclusive with verdict-output flags.** The listing
  is an audit tool, not a verdict invocation. `--list-captures`
  with `--status` / `--update-summary` / `--write` is rejected
  with exit 2 because the combination has no useful semantics:
  the listing produces no verdict, so `update_summary` has
  nothing to write.
- **Mutually exclusive with verdict filters.** `--list-captures`
  with `--captures-since` or `--min-unique-per-branch` is also
  rejected: those are verdict filters, not listing filters.
  The listing is a fast walk that ignores them; the operator
  gets a confusing result if they're set. Better to refuse.
- **`schema_version` pinned.** `"i10-capture-listing-v1"` so
  consumers can detect shape drift. The gate uses
  `schema_version: 2` for the J.3 capture schema; this is a
  separate versioning axis (the listing shape, not the capture
  shape).
- **Reuses `_safe_phase_from_capture`** from the gate. The J.3
  schema-bug fix (iterate `rows[]`, read `rows[0].classifier_phase`)
  is preserved: a malformed capture (e.g. non-bounded phase) is
  counted as `skipped_captures` and excluded from the listing,
  matching the gate's `captures_skipped` discipline.

## Senior-dev invariants preserved

- **NO deletions.** All existing fields preserved.
- **NO F/G files touched.** Pure J.10 surface.
- **NO new dependencies.** Stdlib only (`json`, `os`,
  `pathlib`).
- **NO new tables, NO new SQL.**
- **Backwards-compatible.** The gate's CLI behaviour is
  unchanged; the listing is a strictly additive flag.

## Verification

- Focused `tests/test_cas_reachability_listing.py`: **23/23 PASS** in 4.44s.
- Wider J.10 surface: **186/186 PASS** in 22.01s (was 163 before; +23 net).
- Python-engine narrow regression surface: **510/510 PASS** in 28.96s (was 487; +23 net), 1 pre-existing Starlette lifespan deprecation warning.

## CLI surface

```
$ python -m tools.cas_reachability_check --list-captures
J.10 CAS capture listing -- <captures_root>
  total JSON files:   12
  listed (valid):     12
  skipped (invalid):  0
  branches with captures: 4/6

Captures per branch:
  [ ] CAS_REFERENCE_PRICE_WINDOW (no captures yet)
  [ ] CAS_ORDER_ENTRY (no captures yet)
  [+] CAS_LIMIT_ENTRY_ONLY (2 capture(s)):
      - 2026-09-10/RELIANCE_15_27.json
      - 2026-09-14/RELIANCE_15_27.json
  [+] CAS_MATCHING (3 capture(s)):
      - 2026-09-10/RELIANCE_15_32.json
      - 2026-09-12/TCS_15_32.json
      - 2026-09-14/RELIANCE_15_32.json
  [+] CAS_POST (1 capture(s)):
      - 2026-09-14/HDFCBANK_15_42.json
  [+] DERIVATIVES_CAS_ALIGNED (1 capture(s)):
      - 2026-09-14/RELIANCE_15_35.json
```

## Branch state

- **Branch:** `codex/production-correction-hedge-p0`
- **Pushed:** yes (this slice's commit lands before push)

## What this enables

Operators can now answer "what captures exist on disk?" with one
command, no verdict machinery:

```bash
# Fast listing — no fingerprinting, no freshness check
python -m tools.cas_reachability_check --list-captures

# Machine-readable for downstream tooling
python -m tools.cas_reachability_check --list-captures --json | jq

# Custom captures dir (e.g., staging)
python -m tools.cas_reachability_check \
    --captures-dir /path/to/staging/j2_captures \
    --list-captures
```

The audit tool complements the gate: the gate answers "is the
J.10 gate REACHABLE?" (with all four filters + per-day
histogram), the listing answers "what's on disk?" — a
necessary pair for operators triaging evidence.

## What this slice deliberately does NOT include

- **No freshness filter.** The listing is a fast walk; freshness
  requires reading `generated_at_utc` and computing now_utc -
  timestamp, which costs a datetime parse per file. Out of scope
  for a listing tool.
- **No fingerprint / dedup count.** The listing shows every
  file on disk, including duplicates. The gate already surfaces
  duplicates via `duplicates_by_branch`; the listing is the
  raw filesystem view.
- **No `--write` of the listing to a file.** The listing is
  pure stdout; if an operator wants a file they pipe it
  through `tee`. The gate's `--write` is for the gate's
  verdict, not the listing.
- **No F/G cross-workstream.** Pure J.10 surface.

## Status

J.10.CAPTURE_LISTING **DONE**. The `--list-captures` CLI flag is
a fast, side-effect-free audit tool. Backwards-compatible:
existing gate behaviour is unchanged.

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
| **J.10.CAPTURE_LISTING** (this slice) | `--list-captures` audit tool; `list_captures` + `format_listing` helpers; `i10-capture-listing-v1` schema version. |

The gate + audit-tool pair is now complete:
  - The gate answers "is the J.10 gate REACHABLE?" with
    defensive filters + per-day histogram + atomic output.
  - The listing answers "what's on disk?" without computing a
    verdict.
  - Together: operator can audit the captures, run the gate,
    inspect the gate's report, and read the SUMMARY — without
    any of the four operations interfering with the others.
