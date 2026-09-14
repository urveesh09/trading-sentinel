# J.10 — CAS-branch reachability gate: done and committed

## What landed

| File | Type | Purpose |
|---|---|---|
| `python-engine/cas_reachability_gate.py` | source (new) | Pure / total gate module. Walks `docs/j2_captures/`, emits `{verdict, captured_phases, missing_phases, coverage_pct, captures_scanned, captures_skipped}`. `CAS_BRANCHES_REQUIRING_EVIDENCE` is the 6 branches (5 CAS sub-windows + DERIVATIVES_CAS_ALIGNED). Defensive invariant: `CAS_BRANCHES_REQUIRING_EVIDENCE` is checked against `market_calendar._VALID_SESSION_PHASES` at import time -- if a future slice removes a CAS phase from the bounded set, the gate raises `RuntimeError` (category-1 invariant failure). |
| `python-engine/tools/cas_reachability_check.py` | CLI (new) | Operator-facing tool. `--captures-dir` (defaults to `<repo>/docs/j2_captures`), `--json` (machine-readable), `--write` (persist to a path). Exit 0 on REACHABLE, exit 1 on UNREACHABLE, exit 2 on missing directory. Resolves repo root by walking up from the script path looking for the canonical `docs/j2_captures/` directory. |
| `python-engine/tests/test_cas_reachability_gate.py` | test (new) | 9 tests across 9 describe-blocks: documented-set assertion, empty / partial / full coverage, extra-files tolerated (SUMMARY.md/README.md/review_log.md ignored), corrupt-capture skipped, non-bounded-phase ignored, format_report shape, write_report idempotency. |

## Verification snapshot

| Check | Result |
|---|---|
| **Python `test_cas_reachability_gate.py`** | **9/9 PASS warnings-fatal** |
| Python J-slice (16 files, includes J.10 + all earlier slices) | **268 pass / 22 pre-existing failures unrelated to J.10** (verified by isolation re-run of `test_calendar_gates.py` which passes 18/18 when run alone; the 22 are the J.6-documented cross-test isolation noise) |
| Node full suite (defensive, no Node changes in J.10) | **385 pass / 4 skip / 0 fail** (no regression) |
| Client full suite (defensive) | **40 pass / 0 fail** (no regression) |
| CLI invocation: `python tools/cas_reachability_check.py` | **Exit 1, UNREACHABLE, 0.0% coverage** (correct: the operator-supplied captures are still pending) |
| Required-branches subset of `_VALID_SESSION_PHASES` invariant | **Verified at import time** (`_REQUIRED_PHASES_SUBSET_OF_VALID` assertion) |

## J.10 design

### Why this slice

The plan §14 explicitly forbids auction-imbalance research and auction-based strategies: "any auction-based strategy is separate research with auction execution semantics, not an extension of a continuous-market fill model." The J.4 done-doc says "without `docs/j2_captures/YYYY-MM-DD/` receipt files passing `j2_capture_review.py`, the classifier's CAS branches are wired but unverified against real Kite."

J.10 is the **gate** that enforces this boundary. It does NOT ship an auction strategy; it ships the runtime check that future auction-aware code must pass.

### What J.10 does

1. **Walk the J.3 receipt directory** (`docs/j2_captures/`) — the directory the J.3 capture protocol populates.
2. **Read each JSON capture**, extract `classifier.phase`, and count.
3. **Emit a verdict**: REACHABLE if every branch in `CAS_BRANCHES_REQUIRING_EVIDENCE` has >=1 capture; UNREACHABLE otherwise.
4. **Surface missing branches** so the operator can see what's still needed.
5. **Tolerate** malformed captures (skipped, not fatal) and extra files (SUMMARY.md, README.md, review_log.md — all ignored).

### What J.10 does NOT do (out of scope, by design)

- It does not implement an auction-based trading strategy (forbidden by plan §14).
- It does not capture broker data itself — it walks captures that the J.3 operator protocol produces.
- It does not change the J.3 capture protocol — it consumes its output.
- It does not write captures to the receipt directory (that's `tools/j2_cas_probe.py`'s job).

### The invariant

`CAS_BRANCHES_REQUIRING_EVIDENCE` must always be a subset of `market_calendar._VALID_SESSION_PHASES`. This is enforced at import time:

```python
_REQUIRED_PHASES_SUBSET_OF_VALID: bool = all(
    phase in _VALID_SESSION_PHASES
    for phase in CAS_BRANCHES_REQUIRING_EVIDENCE
)
if not _REQUIRED_PHASES_SUBSET_OF_VALID:
    raise RuntimeError(...)
```

If a future slice removes a CAS phase from the bounded set without updating the gate, the gate raises at module load. This is a category-1 invariant failure: a phase-set change must update both the mirror's bounded set AND the gate's required set in lockstep.

### Operator runbook

```bash
# Run the gate (default location: docs/j2_captures/):
cd python-engine && PYTHONPATH=. ./winvenv/Scripts/python.exe tools/cas_reachability_check.py

# Machine-readable JSON:
PYTHONPATH=. ./winvenv/Scripts/python.exe tools/cas_reachability_check.py --json

# Persist next to the captures:
PYTHONPATH=. ./winvenv/Scripts/python.exe tools/cas_reachability_check.py --write docs/j2_captures/reachability.json

# Custom captures directory:
PYTHONPATH=. ./winvenv/Scripts/python.exe tools/cas_reachability_check.py --captures-dir /path/to/j2_captures
```

Exit codes:
- **0**: REACHABLE (every CAS branch has >=1 capture)
- **1**: UNREACHABLE (one or more branches missing)
- **2**: missing captures directory

### The current state (honest accounting)

The gate currently returns UNREACHABLE with 0.0% coverage. This is the **correct** state for J.10:
- The J.3 capture protocol and review tool are shipped.
- The `docs/j2_captures/` directory exists with a `README.md` (no operator-supplied captures yet).
- J.10 is the gate that waits for the operator to supply real broker evidence.

Closing this gap is the operator's responsibility, not a J.10 follow-up. J.10's deliverable is the gate itself, not the receipts.

## Files modified (final list)

```
python-engine/cas_reachability_gate.py                NEW  +200 lines
python-engine/tools/cas_reachability_check.py          NEW  +95 lines
python-engine/tests/test_cas_reachability_gate.py      NEW  +175 lines
```

## What this enables (per the J.4 done-doc table)

| Future slice | What J.10 enables |
|---|---|
| Any auction-aware Node caller | Must pass `tools/cas_reachability_check.py --write` as a CI gate before merging |
| Operator dashboard surfacing CAS sub-window counts | Reads from `docs/j2_captures/SUMMARY.md` + `reachability.json` (a future slice, not J.10) |
| Plan §14 audit (auction-strategy review) | The gate is the auditable surface -- "REACHABLE" means evidence exists, "UNREACHABLE" means the slice is gated |
