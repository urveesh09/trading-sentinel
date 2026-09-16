# J.10.CAPTURE_OLDEST_NEWEST — per-branch timestamp range

## What landed

|| File | Type | Purpose |
|---|---|---|---|
| `python-engine/cas_reachability_recency.py` | source (new, 270 lines) | `oldest_newest_per_branch` + `format_recency_table` + internal helpers (`_safe_observation_at_utc`, `_safe_phase_from_recency`, `_span_days`) |
| `python-engine/cas_reachability_gate.py` | source (extended) | New `recency_by_branch` report field; new `## Captures recency per branch` SUMMARY section; new import |
| `python-engine/tests/test_cas_reachability_recency.py` | test (new, 28 tests) | Pins the recency contract at four layers: internal helpers, `oldest_newest_per_branch`, `format_recency_table`, gate + SUMMARY integration |
| `python-engine/tests/test_cas_reachability_check.py` | test (extended) | `recency_by_branch` added to the documented JSON shape keys |
| `docs/2026-09-14-j10-capture-oldest-newest-done.md` | doc (new) | This file |

## The shift in defensive posture

The J.10 SUMMARY surfaces counts (per branch, per day, per branch-per-day) but not the **timestamp range** of evidence. A branch with 4 captures all on the same day looks identical to a branch with 4 captures spread across 4 days — but those are different risk profiles:

- **Single-day cluster**: a span of 0 means all evidence is from one CAS observation — suspicious for CAS branches that should be refreshed across market conditions.
- **Stale evidence**: a `Newest` timestamp from >7 days ago suggests the probe hasn't been re-run; the broker behaviour may have shifted.
- **Wide-spanning branch**: a large span means the broker behaviour has been observed across many sessions — the operator can be confident.

After this slice, the SUMMARY surfaces all three.

## The recency section

```
## Captures recency per branch

| Branch | Oldest | Newest | Span (days) | Oldest path | Newest path |
|---|---|---|---|---|---|
| CAS_LIMIT_ENTRY_ONLY | 2026-09-10T09:47:00+00:00 | 2026-09-14T09:47:00+00:00 | 4 | 2026-09-10/RELIANCE_15_27.json | 2026-09-14/TCS_15_27.json |
| CAS_MATCHING | 2026-09-14T09:47:00+00:00 | 2026-09-14T09:47:00+00:00 | 0 | 2026-09-14/RELIANCE_15_32.json | 2026-09-14/RELIANCE_15_32.json |
| CAS_ORDER_ENTRY | (no evidence) | - | - | - | - |
...
```

Each row gives operators a complete breadcrumb — the timestamp AND the file that backed it.

## Key design choices

- **Restrict to first-occurrence paths.** The recency reflects the dedup discipline. Redundant duplicates (per J.10.DEDUP) don't extend the apparent recency; only the first occurrence under each branch counts.
- **Pure / total helper.** Never raises. A missing captures_root, unreadable file, schema deviation, or missing `observation_at_utc` all degrade gracefully:
  - Missing root → `{}`.
  - Unreadable file → skipped.
  - Missing `observation_at_utc` → skipped (can't compute position on the timeline).
  - Schema bug (`rows` missing) → phase unreadable, skipped.
- **`_span_days` clamps negatives to 0.** `span_days` is a coverage-velocity signal, not a duration invariant. A negative span (newest < oldest) means malformed data and is clamped rather than returned as a negative.
- **Schema-bug fix preserved.** `_safe_phase_from_recency` reads `rows[0].classifier_phase` (the J.3 v2 schema), NOT the top-level `classifier.phase` (which doesn't exist in v2). Mirrors the gate's existing fix.
- **OS-native path separators.** `relative_to(captures_root)` returns OS-native separators (Windows: `\`, POSIX: `/`). The SUMMARY is portable because markdown doesn't care about path separators, but tests normalize both sides to forward-slash for cross-platform stability.

## Recency contract

```python
def oldest_newest_per_branch(
    captures_root: Path,
    *,
    first_occurrence_paths: set[str] | None = None,
) -> dict[str, dict[str, str | int]]:
```

Returns `{branch: {"oldest": iso, "newest": iso, "oldest_path": str, "newest_path": str, "span_days": int}}`.

- `span_days` is `(newest - oldest)` rounded to whole days (>=0; 0 when both timestamps fall on the same day).
- Branches with no first-occurrence evidence appear in the dict with `{}` (so the SUMMARY can render a consistent row count).
- An empty captures root returns `{}`.

## Defensive regression

J.10 surface (15 test files): **272/272 PASS** in 25.75s (was 244; +28 net for CAPTURE_OLDEST_NEWEST).

0 regressions.

## Operator runbook

The recency section appears in `docs/j2_captures/SUMMARY.md` automatically after each `--update-summary` or after a successful `tools/j2_capture_review.py` run. Operators read it directly — no new CLI flag.

To surface recency in the JSON CLI output:

```bash
python -m tools.cas_reachability_check \
    --captures-dir docs/j2_captures/ \
    --json
```

The output JSON now includes the `recency_by_branch` field.

## Composition with other J.10 surface flags

| Flag | Composes? | Notes |
|---|---|---|
| `--captures-since` | ✓ | Restricts the captures the gate scans; the recency reflects the filtered set |
| `--min-unique-per-branch` | ✓ | Same |
| `--show-branch-histogram` | ✓ | Same |
| `--list-captures` | ✗ | Mutually exclusive (short-circuits) |
| `--write <path>` | ✓ | Gate JSON includes `recency_by_branch` |
| `--update-summary` | ✓ | SUMMARY includes the recency section |
| `--verify-summary` | ✓ | Verify JSON includes the recency field; the SUMMARY template is identical for the same report, so MATCH still works |

## Critical invariants preserved

- `update_summary` signature and semantics unchanged.
- All prior J.10 surface flags still work.
- No F-series or G-series files touched.
- `_safe_phase_from_capture` schema-bug fix preserved (mirrored in `_safe_phase_from_recency`).
- `tests/main_surface_golden.json` not touched.
- The recency helper is consistent with the dedup discipline (first-occurrence-only).
