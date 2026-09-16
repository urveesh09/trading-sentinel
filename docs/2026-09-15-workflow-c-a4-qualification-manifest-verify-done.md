# Workflow C.A4 — qualification criteria manifest drift verification

## What landed

|| File | Type | Purpose |
|---|---|---|---|
| `python-engine/partner_qualification_verify.py` | source (new, 280 lines) | `verify_qualification_criteria_manifest` + `ManifestDriftKind` + `ManifestVerificationReport` |
| `python-engine/tests/test_partner_qualification_verify.py` | test (new, 14 tests) | Pins drift contract at 3 layers (helpers, dataclass, integration) |
| `docs/2026-09-15-workflow-c-a4-qualification-manifest-verify-done.md` | doc (new) | This file |

## The shift in defensive posture

The qualification criteria manifest is the frozen predeclared contract that binds a deployed policy to a disjoint training/holdout schedule. Before this slice:

- Operators could only verify a manifest by feeding it to `build_qualification_review_package` and watching for a ValueError. That's a heavy operation -- it requires building the full qualification review, which also requires the heldout report.
- There was no read-only, isolated drift check.

After this slice:

- A pure / total / read-only verifier reads the on-disk manifest, recomputes the body fingerprint, and reconstructs the canonical body via `freeze_qualification_criteria`. Any drift kind is surfaced without writing to disk.
- Two distinct drift kinds: `MANIFEST_FINGERPRINT_MISMATCH` (the body or fingerprint was tampered with) and `CRITERIA_NOT_RECONSTRUCTABLE` (the body has fields that `freeze_qualification_criteria` doesn't produce, OR a validation rule is violated).

## Key design choices

- **Two-stage verification.** Stage 1: body fingerprint check (recompute `_sha(body)`, compare to on-disk `criteria_manifest_sha256`). Stage 2: reconstructability check (re-run `freeze_qualification_criteria` from the manifest's declared fields, compare reconstructed body to on-disk body). Both must pass for `MATCH`.
- **Distinct drift kinds per stage.** Operators can tell the difference between "the file was tampered with" (`MANIFEST_FINGERPRINT_MISMATCH`) and "the body has unsupported fields" (`CRITERIA_NOT_RECONSTRUCTABLE`). This is operationally meaningful: tampering is a security event; an unsupported field is a configuration drift.
- **Read-only by contract.** The verifier NEVER writes to disk (enforced by `test_verify_is_pure_no_writes_to_disk` with mtime + size assertion). The operator commits via `write_qualification_criteria_manifest`.
- **Defensive input handling.** Missing file → `ON_DISK_MISSING`. Corrupt JSON / non-UTF-8 / non-dict JSON → `BYTES_UNREADABLE`. Missing `criteria_manifest_sha256` field → `MANIFEST_FINGERPRINT_MISMATCH` (the on-disk fingerprint is None so they can't match).
- **Mirrors J.10.SUMMARY_VERIFY's enum + dataclass shape.** `ManifestDriftKind` is a `str, Enum` with `kind.value == kind.name`. `ManifestVerificationReport` is a frozen dataclass with a `matches` property. The operator-facing contract is identical, so dashboards that consume drift reports can use a unified shape.

## Defensive regression

Workflow C surface (11 test files): **156/156 PASS** in 4.60s (was 117; +39 net for A1+A3+A4).

| Test file | Tests | Δ (vs 117 baseline) |
|---|---|---|
| `test_partner_qualification_verify.py` | 14 | +14 |

0 regressions.

## Operator runbook

Operators verifying a manifest:

```python
from partner_qualification_verify import (
    verify_qualification_criteria_manifest,
)
result = verify_qualification_criteria_manifest(Path("criteria-manifest.json"))
if result.kind == "MATCH":
    print(f"Manifest intact: {result.on_disk_fingerprint[:16]}...")
else:
    print(f"Drift detected: {result.kind}")
    # Take action based on the kind.
```

CLI integration is the next step (could be added to `research_cli` in a follow-up slice). For now the helper is importable for any consumer.

## Critical invariants preserved

- `freeze_qualification_criteria` signature and semantics unchanged.
- `write_qualification_criteria_manifest` atomic-write discipline unchanged.
- `build_qualification_review_package` validation unchanged.
- The verifier is additive and reads from the same canonical schema.
- No new dependencies (stdlib only).

## What's still on the Category A backlog

- A2 — chronological exit-delay monotonicity hardening (smaller polish).
- A5 — research summary drift verification (mirror of A4).
- CLI integration for A4 in `research_cli` (optional — the helper is importable).
