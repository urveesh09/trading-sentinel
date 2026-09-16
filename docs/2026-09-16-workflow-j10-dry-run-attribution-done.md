# Workflow J.10.DRY_RUN_ATTRIBUTION — surface real vs simulation captures in the gate

## Source

Per the 2026-09-15 production audit F-5:
> 🟡 F-5 (MED, infra): New PR #89-#92 features deployed but invisible in production runtime. Need to verify they're wired correctly.

The audit identified that the J.10 capture gate's REACHABLE verdict could be satisfied by simulation captures (`dry_run: true`) without operators being able to confirm how much of the verdict came from real broker behaviour vs simulation.

## What landed

| File | Type | Purpose |
|---|---|---|
| `python-engine/cas_reachability_gate.py` | source (extended) | New `_read_dry_run` helper + `dry_run_attribution` field on the gate report |
| `python-engine/tests/test_cas_reachability_check.py` | test (extended) | JSON shape updated to include the new field |
| `python-engine/tests/test_cas_reachability_dry_run_attribution.py` | test (new) | 13 tests pinning the dry_run attribution contract |
| `docs/2026-09-16-workflow-j10-dry-run-attribution-done.md` | doc (new) | This file |

## The shift in defensive posture

Before this slice, the J.10 gate's REACHABLE verdict gave no indication of whether the underlying captures were real broker observations or simulated. Operators had to inspect each capture's `dry_run` field manually.

After this slice, the gate report carries a `dry_run_attribution` block:
```json
"dry_run_attribution": {
  "real": 4,
  "dry_run": 2,
  "unknown": 0,
  "total_unique": 6
}
```

Operators can now answer the F-5 question: "Is the REACHABLE verdict grounded in real broker behaviour?" — by looking at `real` vs `dry_run` counts. A REACHABLE verdict with `real=0, dry_run=N` is purely simulated (a diagnostic red flag, not a fail-closed trigger).

## Key design choices

- **Verdict logic unchanged**: real and dry_run captures both count toward REACHABLE. The attribution is purely diagnostic — operators can audit, but the gate doesn't refuse a dry_run-only REACHABLE verdict.
- **`unknown` bucket for schema drift**: a capture with a missing or non-boolean `dry_run` field lands in `unknown`, NOT silently bucketed as real or dry_run. This surfaces upstream schema drift in the audit.
- **Dedup discipline applies**: duplicates (per the J.10.DEDUP fingerprint) don't inflate the attribution. Only UNIQUE first-occurrence captures are counted.
- **Defensive reader**: `_read_dry_run` returns `None` for missing file, malformed JSON, non-dict document, missing field, or non-boolean value. The caller buckets `None` into `unknown`.
- **`total_unique` invariant**: `total_unique == real + dry_run + unknown` always holds.

## Defensive regression

| Test file | Tests | Δ |
|---|---|---|
| `test_cas_reachability_dry_run_attribution.py` | 13 | +13 (new file) |
| `test_cas_reachability_check.py` | 26 (was 26 — JSON-shape key added) | 0 (1 assertion updated) |
| `test_cas_reachability_gate.py` | 9 | 0 |
| `test_cas_reachability_features.py` | 13 | 0 |
| All other cas_reachability tests | unchanged | 0 |

Full cas_reachability surface: 224/224 PASS. Zero regressions in any other surface.

## Test discipline

13 tests pin the contract:
- 6 helper tests (`_read_dry_run` for real, dry_run, missing field, non-boolean, unreadable, empty doc).
- 7 report-level tests:
  - Empty dir → all-zero attribution with `total_unique=0`.
  - Real-only → `real=N, dry_run=0, unknown=0, total_unique=N`.
  - Mixed → both buckets populated.
  - Unknown bucket correctly populated for schema-drift captures.
  - Dedup doesn't inflate attribution.
  - Verdict unchanged by dry_run attribution (purely diagnostic).
  - `total_unique` invariant holds.

## What this does NOT change

- **`cas_reachability_report`'s verdict logic**: unchanged. Both real and dry_run captures count toward REACHABLE.
- **J.10.FRESHNESS / DEDUP / MIN_THRESHOLD**: unchanged. The dry_run attribution is purely additive.
- **Existing JSON shape**: extended with one new top-level key (`dry_run_attribution`). All other keys unchanged.

## Operator runbook

After deploy to PROD, operators can audit the dry_run attribution via:

```bash
python tools/cas_reachability_check.py --json | jq '.dry_run_attribution'
```

Output shape:
```json
{
  "real": 4,
  "dry_run": 2,
  "unknown": 0,
  "total_unique": 6
}
```

A `REACHABLE` verdict with `real=0` is a diagnostic red flag — the gate is being satisfied purely by simulation. The verdict itself is not flipped (per the slice design); operators must decide whether to require real captures.

## What's still open

- **SUMMARY.md rendering of dry_run_attribution**: the field is in the JSON output but not yet in the human-readable SUMMARY.md. A separate slice could surface it in the SUMMARY when `--show-dry-run-attribution` is set.
- **Audit-on-write**: the gate could refuse to write the SUMMARY.md when `real=0, dry_run>0` (a "you must run a real capture before publishing a REACHABLE verdict" policy). Operator decision required.
- **J.10.CAPTURE_FINGERPRINT_TOOL**: per-capture source-tool attribution (not just dry_run). Today's `tool` field is a const "j2_cas_probe" — a future slice could differentiate by probe configuration.

## Critical invariants preserved

- The 12 documented JSON keys (now 13 with `dry_run_attribution`).
- `verdict` field semantics: REACHABLE iff all 6 branches have ≥1 unique capture (regardless of dry_run).
- All existing CLI flags (`--json`, `--write`, `--status`, `--update-summary`, `--summary-path`, `--captures-since`, `--min-unique-per-branch`, `--list-captures`, `--show-branch-histogram`, `--verify-summary`, `--features-inventory`).
- The J.10 schema-bug fix (rows[0].classifier_phase, not top-level).
- Atomic write discipline (J.10.WRITE_ATOMIC).
