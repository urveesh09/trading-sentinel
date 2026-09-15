# Workflow C.A4-CLI — operator-facing manifest drift verification

## What landed

|| File | Type | Purpose |
|---|---|---|---|
| `python-engine/research_cli.py` | source (extended) | New `verify-criteria-manifest` subcommand with `--manifest-path` and `--json` flags |
| `python-engine/tests/test_research_cli_qualification.py` | test (extended) | 7 new CLI tests pinning exit codes, output shape, and the read-only contract |
| `docs/2026-09-15-workflow-c-a4-cli-manifest-verify-done.md` | doc (new) | This file |

## The shift in defensive posture

Before this slice, the A4 helper `verify_qualification_criteria_manifest` was importable but not exposed via CLI. Operators wanting to verify a manifest had to:

1. Either import the helper into a Python script and write their own wrapper, or
2. Re-run the full `build_qualification_review_package` flow just to detect drift (heavy operation that requires the heldout report too).

After this slice, operators have a one-line CLI:

```bash
python -m research_cli verify-criteria-manifest \
    --manifest-path path/to/manifest.json \
    --json
```

Exit code semantics mirror J.10.SUMMARY_VERIFY so monitoring tools can use a unified drift-handling pattern:

- `0` = MATCH (intact, body matches fingerprint, criteria reconstructable)
- `1` = real drift (MANIFEST_FINGERPRINT_MISMATCH or CRITERIA_NOT_RECONSTRUCTABLE)
- `2` = ON_DISK_MISSING or BYTES_UNREADABLE

## Key design choices

- **Read-only by contract.** The CLI never writes to the manifest. `test_cli_does_not_overwrite_manifest` enforces this via mtime + size assertion.
- **JSON output by default optional.** The `--json` flag emits structured JSON (parseable by monitoring); without it, human-readable text is emitted. Both forms surface the same drift kind.
- **Exit codes match J.10.SUMMARY_VERIFY.** This is the senior-dev discipline: when a CLI family has multiple drift checks (manifest verification, J.10 summary verification, eventually research summary verification), the exit codes are aligned so monitoring can use a single drift-handling pattern.
- **Lazy import of the verifier.** The CLI imports `partner_qualification_verify` lazily inside the dispatch branch, keeping the module's import time clean.
- **No new dependencies.** Stdlib only (`json`, `pathlib`, `sys`).

## Defensive regression

| Test file | Tests | Δ |
|---|---|---|
| `test_research_cli_qualification.py` | 8 | +7 |

Workflow C + research_cli surface (13 test files): **173/173 PASS** in 5.04s (was 117; +56 net for A1+A2+A3+A4+A4-CLI).

0 regressions.

## Operator runbook

Verify a manifest:

```bash
python -m research_cli verify-criteria-manifest \
    --manifest-path path/to/criteria-manifest.json
```

Output (human-readable):

```
qualification manifest drift: MATCH
  on-disk:       path/to/criteria-manifest.json
  on-disk fingerprint: abc123def456...
  reconstructed: abc123def456...
  on-disk size:  1024 bytes
```

Output (JSON, `--json` flag):

```json
{
  "kind": "MATCH",
  "matches": true,
  "on_disk_path": "path/to/criteria-manifest.json",
  "on_disk_fingerprint": "abc123def456...",
  "reconstructed_fingerprint": "abc123def456...",
  "on_disk_size": 1024
}
```

Drift detected (exit 1):

```
qualification manifest drift: CRITERIA_NOT_RECONSTRUCTABLE
  on-disk:       path/to/manifest.json
  on-disk fingerprint: abc123def456...
  reconstructed: 789xyz012345...
  on-disk size:  1024 bytes
```

Missing file (exit 2):

```
qualification manifest drift: ON_DISK_MISSING
  on-disk:       (missing)
```

## Critical invariants preserved

- `partner_qualification_verify` helper signature unchanged.
- All other `research_cli` subcommands unchanged.
- `partner_qualification_review.write_qualification_criteria_manifest` atomic-write discipline unchanged.
- No new dependencies.

## What's still on the Category A backlog

- A5 — research summary drift verification (mirror of A4 for `render_research_summary`).
