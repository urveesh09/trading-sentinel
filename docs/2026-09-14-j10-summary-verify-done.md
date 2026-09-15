# J.10.SUMMARY_VERIFY — SUMMARY.md drift detection

## What landed

|| File | Type | Purpose |
|---|---|---|---|
| `python-engine/cas_reachability_verify.py` | source (new, 261 lines) | `verify_summary` + `VerificationReport` + `DiffKind` enum + `_extract_generated_at` / `_strip_generated_at` helpers |
| `python-engine/tools/cas_reachability_check.py` | source (extended) | New `--verify-summary` flag with structured text + JSON output, mutually exclusive with `--update-summary` |
| `python-engine/tests/test_cas_reachability_verify.py` | test (new, 24 tests) | Pins the drift contract at four layers: dataclass invariants, internal helpers, `verify_summary` integration, CLI surface |
| `docs/2026-09-14-j10-summary-verify-done.md` | doc (new) | This file |

## The shift in defensive posture

The J.10 SUMMARY.md is the persistent operator-facing audit surface for the CAS reachability gate. Before this slice, the SUMMARY was a one-way write — `update_summary` overwrote whatever was on disk. If something (manual edit, partial write, disk error, race with a stale process) desynchronized the on-disk file from the gate's render, the only way to detect it was to spot a discrepancy manually.

After this slice, operators have a read-only drift check:

```bash
# Render a fresh SUMMARY and diff it byte-for-byte against the on-disk file.
# Exit 0 = match OR benign timestamp-only drift.
# Exit 1 = real body drift (manual edit / partial write).
# Exit 2 = missing on-disk file.
python -m tools.cas_reachability_check \
    --captures-dir docs/j2_captures/ \
    --verify-summary
```

## Drift kinds

| Kind | Meaning | Exit |
|---|---|---|
| `MATCH` | Byte-identical render | 0 |
| `GENERATED_AT_DIFFER` | Body byte-identical after stripping the `Generated at:` line; only the timestamp differs (benign re-render) | 0 (warning to stderr) |
| `BYTES_DIFFER` | Body changed (manual edit, partial write, schema drift) | 1 |
| `ON_DISK_MISSING` | The on-disk file does not exist | 2 |

The `GENERATED_AT_DIFFER` distinction matters: a re-render 30 seconds apart from the previous render naturally has a different `Generated at` timestamp. Without this distinction, every re-run of the gate would flag a "drift" and operators would stop trusting the check. The kind tells the operator *what* drifted, not just *whether*.

## Key design choices

- **Read-only by contract.** `--verify-summary` NEVER overwrites the on-disk file. The CLI rejects `--verify-summary --update-summary` with exit 2 (the combination is a tautology — the update overwrites the file, then the verify sees its own write). Use `--update-summary` to commit a fresh render.
- **Stdlib-only.** The module imports nothing from `cas_reachability_gate` except the `update_summary` symbol it needs to render the canonical SUMMARY. No new dependencies.
- **`tempfile` for the fresh render.** The fresh SUMMARY is rendered into a `tempfile.NamedTemporaryFile` and immediately deleted after bytes are read. The on-disk file is NEVER touched.
- **Bytes-level comparison.** The check is `actual_bytes == expected_bytes`. A single byte of drift triggers `BYTES_DIFFER`. The timestamp-only exception is computed AFTER bytes differ, by stripping the `Generated at:` line and comparing the result.
- **Trailing-newline preservation.** The `_strip_generated_at` helper preserves the trailing newline so the stripped-text comparison is byte-correct.

## Defensive regression

J.10 surface (14 test files): **244/244 PASS** in 25.20s (was 220; +24 net for SUMMARY_VERIFY).

`cas_reachability_check.py` CLI tests: **26/26 PASS**.

0 regressions.

## Operator runbook

```bash
# Verify the SUMMARY matches the current gate state.
python -m tools.cas_reachability_check \
    --captures-dir docs/j2_captures/ \
    --verify-summary

# Verify + JSON output (for monitoring).
python -m tools.cas_reachability_check \
    --captures-dir docs/j2_captures/ \
    --verify-summary \
    --json

# Commit a fresh render after a benign drift.
python -m tools.cas_reachability_check \
    --captures-dir docs/j2_captures/ \
    --update-summary
```

## Composition with other J.10 surface flags

| Flag | Composes? | Notes |
|---|---|---|
| `--captures-since` | ✓ | Filters the captures the gate scans; the fresh render reflects the filtered set |
| `--min-unique-per-branch` | ✓ | The fresh render reflects the threshold |
| `--show-branch-histogram` | ✓ | The fresh render embeds `branch_per_day` |
| `--list-captures` | ✗ | Mutually exclusive with `--verify-summary` because `--list-captures` short-circuits |
| `--write <path>` | ✓ | Gate JSON still written; verify runs on SUMMARY only |
| `--update-summary` | ✗ | See "Read-only by contract" above |
| `--json` | ✓ | Suppresses gate JSON, emits verify-summary JSON only |

## Critical invariants preserved

- `update_summary` signature and semantics unchanged.
- All prior J.10 surface flags still work (no signature changes to other paths).
- No F-series or G-series files touched.
- `_safe_phase_from_capture` schema-bug fix preserved.
- `tests/main_surface_golden.json` not touched (regenerated via `TS_UPDATE_GOLDEN=1`, not hand-edited).
