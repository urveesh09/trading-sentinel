# Workflow C.A5 — research artifact drift verification

## What landed

|| File | Type | Purpose |
|---|---|---|---|
| `python-engine/intraday_spread_research_verify.py` | source (new, 220 lines) | `verify_research_artifact` + `ArtifactDriftKind` + `ArtifactVerificationReport` + `_recompute_evidence_fingerprint` helper |
| `python-engine/tests/test_intraday_spread_research_verify.py` | test (new, 17 tests) | Pins the artifact drift contract at 4 layers (helpers, dataclass, internal helper, integration) |
| `docs/2026-09-15-workflow-c-a5-research-artifact-verify-done.md` | doc (new) | This file |

## The shift in defensive posture

The research artifact (`intraday_spread_research_v2`) is the deterministic output of `build_research_artifact`. The artifact's `evidence_sha256` is computed from a `deterministic` dict (excluding `created_at`, `review_state`, etc.). The embedded run manifest has its own `manifest_sha256`.

Before this slice, operators had no read-only drift check. Tampering with the artifact body OR the embedded manifest went undetected unless someone re-ran the build pipeline and compared hashes.

After this slice:

- A pure / total / read-only verifier reads the on-disk artifact and checks TWO independent fingerprints:
  1. The artifact's `evidence_sha256` (recomputed from the deterministic block).
  2. The embedded manifest's `manifest_sha256` (recomputed from the manifest body).
- Drift kinds are distinct: tampering with the body fires `EVIDENCE_FINGERPRINT_MISMATCH`; tampering with the manifest (without updating its hash) fires `MANIFEST_FINGERPRINT_MISMATCH`. Operators can attribute drift to the right scope.

## Key design choices

- **Two-stage verification.** Stage 1: body fingerprint check (recompute from deterministic fields). Stage 2: manifest fingerprint check (recompute from manifest body). Both must pass for `MATCH`.
- **Distinct drift kinds per stage.** A body tampering is `EVIDENCE_FINGERPRINT_MISMATCH` (operator sees "the artifact body changed"); a manifest tampering is `MANIFEST_FINGERPRINT_MISMATCH` (operator sees "the embedded manifest changed but the operator forgot to update its hash"). Different operational responses.
- **Read-only by contract.** Enforced by `test_verify_is_pure_no_writes_to_disk` (mtime + size assertion).
- **Defensive input handling.** Missing file → `ON_DISK_MISSING`. Corrupt JSON / non-UTF-8 / non-dict JSON → `BYTES_UNREADABLE`. Missing `evidence_sha256` field → `EVIDENCE_FINGERPRINT_MISMATCH`.
- **Mirrors existing J.10 patterns.** `ArtifactDriftKind` is a `str, Enum` with `kind.value == kind.name`. `ArtifactVerificationReport` is a frozen dataclass with a `matches` property. Same shape as `ManifestDriftKind` (A4) and `DiffKind` (J.10.SUMMARY_VERIFY) — dashboards use a unified contract.

## Defensive regression

| Test file | Tests | Δ |
|---|---|---|
| `test_intraday_spread_research_verify.py` | 17 | +17 |

Workflow C + research_cli surface (14 test files): **190/190 PASS** in 5.15s (was 117; +73 net for A1+A2+A3+A4+A4-CLI+A5).

0 regressions.

## Operator runbook

```python
from intraday_spread_research_verify import (
    verify_research_artifact,
)
result = verify_research_artifact(Path("research-artifact.json"))
if result.kind == "MATCH":
    print(f"Artifact intact: {result.on_disk_fingerprint[:16]}...")
else:
    print(f"Drift detected: {result.kind}")
    # Take action based on the kind.
```

CLI integration (optional follow-up) could expose this via `research_cli verify-research-artifact` mirroring the A4-CLI pattern. The helper is currently importable but not CLI-exposed.

## Critical invariants preserved

- `build_research_artifact` signature and semantics unchanged.
- `create_research_run_manifest` validation contract unchanged.
- Existing `test_intraday_spread_research.py` tests (2) still pass unchanged.
- No new dependencies (stdlib only).
- The artifact's `evidence_sha256` round-trip through JSON is bit-identical (verified by `test_intact_artifact_round_trip_through_disk_is_match`).

## Workflow C — Category A backlog status

All 5 bounded improvements from the investigation report are now DONE:

| Item | Slice | Status |
|---|---|---|
| A1 | asymmetric-fills diagnostic | DONE (`853d096`) |
| A2 | chronological exit-delay monotonicity | DONE (`cb518dc`) |
| A3 | cost-sensitivity determinism pin | DONE (`4d43773`) |
| A4 | qualification manifest drift verification | DONE (`8be4068`) |
| A4-CLI | operator-facing manifest verification CLI | DONE (`40ffcd1`) |
| A5 | research artifact drift verification | DONE (this commit) |

Workflow C Category A is COMPLETE. Category B (operator-required evidence) and Category C (asymmetric-fills architectural decision) remain operator-blocked per the original investigation.
