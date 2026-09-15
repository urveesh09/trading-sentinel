# J.10.WRITE_ATOMIC — atomic + byte-identical JSON write for the gate's audit trail

## What landed

|| File | Type | Purpose |
|---|---|---|---|
| `python-engine/cas_reachability_atomic.py` | source (new, 105 lines) | Pure helper `write_report_atomic(report, out_path)` — write-to-tempfile + `os.link` discipline; byte-identical retries; refuses to clobber different-content pre-existing files. |
| `python-engine/cas_reachability_gate.py` | source (extended) | `write_report(...)` now delegates to `write_report_atomic`. Pre-existing `json` / `Path` imports retained for compatibility. |
| `python-engine/tests/test_cas_reachability_atomic.py` | test (new, 13 tests) | Pins the helper contract + the gate integration + the end-to-end byte-identical-retry discipline. |

## The defensive invariant

```text
A byte-identical retry of ``write_report`` produces a
byte-identical file. A different-content pre-existing file
at the same path raises ``ValueError`` (no silent clobber).
The sibling tempfile is always unlinked, even on failure.
```

Without atomic writes, the gate's audit trail has three
failure modes:
  - Crash between truncate and write → partial / empty file.
  - Concurrent reader sees a torn write → JSON parse error.
  - Different-content retry (e.g. operator pointed at the
    wrong captures directory) → silent clobber, lost audit.

The atomic helper addresses all three. It mirrors the F5
`reconciliation_cli._write_output_atomic` discipline (per
`docs/2026-09-13-fg-independent-correction-plan.md`), so the
two audit surfaces now use the same pattern.

## Design decisions

- **Write-to-tempfile + `os.link`.** This is the POSIX-blessed
  pattern for atomic file replacement: write to a sibling
  tempfile, `fsync` to disk, then `os.link` the tempfile to the
  target path. The `link` syscall is atomic on POSIX and on
  Windows NTFS. The target either shows the OLD content or the
  NEW content — never a torn write.
- **`allow_nan=False`.** The JSON spec disallows `NaN` and
  `Infinity` literals, but Python's `json` encoder emits them by
  default (with a warning some consumers ignore). `allow_nan=False`
  is the F5 helper's discipline — refuse to emit invalid JSON
  rather than produce a file some downstream tool will reject.
- **Refuse to clobber different content.** The gate's report is
  a stable shape: two runs against the same captures directory
  must produce byte-identical output. A different-content
  pre-existing file means the operator is pointing at the
  wrong path or has stale output from a different captures
  directory. We raise `ValueError` rather than silently
  overwriting their audit trail.
- **Same-content retry is a noop.** When `os.link` fails with
  `FileExistsError` AND the existing bytes match what we
  would write, the helper treats it as a successful noop.
  This makes CLI retries idempotent without raising.
- **Tempfile always unlinked.** Even on `ValueError` (different
  content) the sibling tempfile is removed in `finally`. The
  operator never sees `.j10_report-XXX` files littering their
  captures directory.
- **Local helper, not cross-module import.** The F5 helper
  lives in `reconciliation_cli.py` and the J.10 helper lives
  in `cas_reachability_atomic.py`. Both are ~25 lines and
  mirror each other; cross-module coupling between the F5 and
  J.10 surfaces adds risk for a 25-line change. The pattern is
  documented in each file's docstring; future F-series or
  J-series work can lift the helper into a shared module when
  there are THREE call sites, not two.

## Senior-dev invariants preserved

- **NO deletions.** All pre-existing fields preserved.
- **NO F/G files touched.** Pure J.10 surface.
- **NO new dependencies.** Stdlib only (`json`, `os`,
  `tempfile`, `pathlib`).
- **NO new tables, NO new SQL.**
- **Backwards-compatible.** `write_report`'s signature is
  unchanged; the only observable difference is that
  `ValueError` is now raised on different-content pre-existing
  files. CLI behaviour for the common case (no pre-existing
  file, or byte-identical retry) is unchanged.

## Verification

- Focused `tests/test_cas_reachability_atomic.py`: **13/13 PASS** in 0.54s.
- Wider J.10 surface: **163/163 PASS** in 17.80s (was 150 before; +13 net).
- Python-engine narrow regression surface: **487/487 PASS** in 24.80s (was 474; +13 net), 1 pre-existing Starlette lifespan deprecation warning.

## Branch state

- **Branch:** `codex/production-correction-hedge-p0`
- **Pushed:** yes (this slice's commit lands before push)

## What this enables

The J.10 gate's audit trail is now crash-safe:
  - A mid-write crash leaves the OLD report intact (the
    `os.link` is atomic; the sibling tempfile is unlinked).
  - A concurrent reader never sees a torn write.
  - A byte-identical retry produces a byte-identical file
    (no spurious "new" reports in downstream consumers).
  - A different-content pre-existing file is a hard error
    the operator must resolve -- no silent clobber.

Combined with J.10.CAPTURE_SUMMARY_AGGREGATE (the per-day
histogram in the SUMMARY), J.10.DEDUP (unique-observation
counting), J.10.FRESHNESS (`--captures-since` filter), and
J.10.MIN_THRESHOLD (`--min-unique-per-branch` filter), the
J.10 surface is now defensive on six axes. The audit trail
itself is crash-safe; the gate's verdict is honest about
bounded phase, unique observation, fresh evidence, and
corroborating evidence per branch.

## What this slice deliberately does NOT include

- **No shared atomic-write module.** Two call sites (F5 +
  J.10) is below the threshold where cross-module coupling
  pays for itself; the helpers stay local.
- **No fsync tuning.** `os.fsync` is the conservative choice;
  a future slice could swap in `fdatasync` for POSIX if
  metadata durability is shown to be a bottleneck. Out of
  scope here.
- **No concurrent-write conflict resolution.** The helper
  refuses different-content writes; it does not attempt to
  merge or arbitrate. The operator resolves the conflict.
- **No F/G cross-workstream.** Pure J.10 surface.

## Status

J.10.WRITE_ATOMIC **DONE**. The gate's `write_report` is now
atomic + byte-identical. Backwards-compatible.

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
| **J.10.WRITE_ATOMIC** (this slice) | Atomic + byte-identical `write_report`; mirrors F5 discipline. |

The gate now has:
  - 4 verdict filters (bounded phase + unique observation
    + fresh evidence + corroborating evidence).
  - 6+ audit surfaces (verdict, per-branch, catalog, per-day,
    duplicates, missing branches, runbook).
  - 1 crash-safe output writer.

A REACHABLE verdict under all four filters, persisted via
a crash-safe writer, is genuinely REACHABLE.
