# J.10 CAS-branch reachability gate — closure and operator-facing surfaces

## What landed

| File | Type | Purpose |
|---|---|---|
| `python-engine/cas_reachability_gate.py` | source (extended) | NEW `update_summary(report, summary_path, *, captures_dir=None)` renders the gate's verdict into a deterministic markdown SUMMARY. NEW `_format_missing_section(missing_phases)` helper. **Critical bug fix**: `_safe_phase_from_capture` was reading `doc["classifier"]["phase"]` and `doc["phase"]` -- the J.3 schema actually stores the bounded phase at `rows[i].classifier_phase`. Every capture was previously counted as "skipped" (the gate was 0/0/6/6/6/6 by construction). |
| `python-engine/tools/cas_reachability_check.py` | CLI (extended) | NEW `--update-summary` and `--summary-path` CLI flags. Operator runs `python tools/cas_reachability_check.py --update-summary` to regenerate the SUMMARY.md. |
| `python-engine/tools/j2_capture_review.py` | source (extended) | NEW auto-update hook: on happy-path review (`overall_passed=True`), the SUMMARY is regenerated automatically. On fail-path, no auto-update (fail-closed). Captures directory resolved by walking up from the capture file; absolute path resolves rglob's cwd-dependence. |
| `python-engine/tests/test_cas_reachability_summary.py` | test (new) | 10 tests pinning the SUMMARY.md contract: verdict line shows bold REACHABLE/UNREACHABLE, missing-branches section present when UNREACHABLE, "Generated at" marker, captures_dir path, review-tool pointer, never raises on missing dir, fail-closed, idempotent. |
| `python-engine/tests/test_j10_closure_e2e.py` | test (new) | 3 end-to-end tests: happy-path review auto-updates SUMMARY, failed review does NOT auto-update, in-process `main()` helper path. |
| `python-engine/tests/test_cas_reachability_gate.py` | test (modified) | Updated 5 fixtures from the legacy `{"classifier": {"phase": X}}` shape to the J.3 `{"rows": [{"classifier_phase": X}]}` shape (the same shape that the gate now reads). All 9 gate tests still pass. |
| `docs/j2_captures/SUMMARY.md` | doc (new, generated) | The persistent operator-facing audit surface. Currently shows `UNREACHABLE -- coverage 0.0%` with the missing-branches checklist and "How to add captures" instructions. |

## Verification snapshot

| Check | Result |
|---|---|
| `test_cas_reachability_gate.py` | **9/9 PASS** |
| `test_cas_reachability_summary.py` | **10/10 PASS** |
| `test_j10_closure_e2e.py` | **3/3 PASS** |
| `test_j3_capture_review.py` (defensive) | **17/17 PASS** (no regression) |
| Wider defensive regression (J + I + J4 + J10 + J3 + I.A/B/C/F test surfaces) | **263/263 PASS** |
| Node full suite (defensive) | **385 pass / 4 skip / 0 fail** (no regression) |
| Client full suite (defensive) | **40 pass / 0 fail** (no regression) |
| CLI invocation: `python tools/cas_reachability_check.py --update-summary` | Exit 1, UNREACHABLE, 0.0% coverage, `docs/j2_captures/SUMMARY.md` written ✓ |
| CLI invocation: `python tools/cas_reachability_check.py --json` | Exit 1, JSON `{verdict, captured_phases, missing_phases, coverage_pct, captures_scanned, captures_skipped}` ✓ |

## Critical bug discovery

The `_safe_phase_from_capture` function in `cas_reachability_gate.py` was reading `doc["classifier"]["phase"]` and `doc["phase"]` at the **top level** of the capture document. The actual J.3 capture schema (per `tools/j2_cas_probe.py::CAPTURE_JSON_SCHEMA` and `CAPTURE_JSON_SCHEMA["$defs"]["row"]["properties"]["classifier_phase"]`) stores the bounded phase at `rows[i].classifier_phase` for each row.

The consequence: every capture was silently counted as "skipped" (the gate returned `captures_scanned=N, captures_skipped=N`), and the per-branch counter never incremented. The gate effectively always reported `coverage_pct=0.0%` regardless of how many valid captures existed in `docs/j2_captures/`.

The bug was caught by `test_j10_closure_e2e.py::test_happy_path_review_auto_updates_summary`: the synthetic capture was written with the J.3 schema shape, but the auto-update SUMMARY showed `coverage **0.0%**` because the gate was reading the wrong field. After the fix, the test passes — `coverage **16.7%**` for one captured branch out of six.

The fix: rewrite `_safe_phase_from_capture` to iterate `rows[]` and read `rows[0].classifier_phase`. Documented in the docstring. The legacy `doc["classifier"]` / `doc["phase"]` lookups were removed (they were never documented in the J.3 schema; they were a guess from the predecessor's J.10 implementation).

Five test fixtures in `test_cas_reachability_gate.py` and `test_cas_reachability_summary.py` were using the legacy `{"classifier": {"phase": X}}` shape; those were updated to `{"rows": [{"classifier_phase": X}]}` to match the J.3 schema and the new gate contract.

## J.10 closure: operator runbook

### Manual refresh

```bash
cd python-engine && PYTHONPATH=. ./winvenv/Scripts/python.exe tools/cas_reachability_check.py --update-summary
```

This rewrites `docs/j2_captures/SUMMARY.md` with the latest verdict.

### Auto-refresh

Run `python tools/j2_capture_review.py <capture>` against any valid capture. On happy-path, the SUMMARY auto-flips. No operator memory load.

### What the operator sees

The SUMMARY shows:
- The captures directory
- The verdict (REACHABLE / UNREACHABLE)
- The coverage percentage
- The captured-per-branch table (count + yes/no marker)
- The missing-branches checklist (when UNREACHABLE)
- Step-by-step instructions for adding captures
- The plan §14 enforcement context

### What the operator does NOT see

Per plan §14, "auction-imbalance research is excluded" and "any auction-based strategy is separate research with auction execution semantics, not an extension of a continuous-market fill model". J.10 ships the gate, not a strategy. The SUMMARY explicitly states this in its "What the gate enforces" section.

## Files modified (final list)

```
python-engine/cas_reachability_gate.py            +140 lines (update_summary + schema bug fix)
python-engine/tools/cas_reachability_check.py      +20 lines (--update-summary flag)
python-engine/tools/j2_capture_review.py          +35 lines (auto-update hook)
python-engine/tests/test_cas_reachability_summary.py  +210 lines (new)
python-engine/tests/test_j10_closure_e2e.py      +250 lines (new)
python-engine/tests/test_cas_reachability_gate.py  ~20 lines (fixture updates)
docs/j2_captures/SUMMARY.md                       (auto-generated; not committed -- regenerable)
```

## What this enables

After this slice, the J.10 gate is **operationally complete**:
- A bounded CLI (`--update-summary`) for manual refresh.
- An auto-refresh hook (review happy-path) that the operator doesn't need to remember.
- A persistent SUMMARY.md as the audit surface.
- A correct schema-aware read of the J.3 capture format.

The only thing missing is **operator-supplied staging captures** (plan §14 explicit gate-flip requirement). The gate currently returns UNREACHABLE because `docs/j2_captures/` has no operator-supplied evidence. Once the operator runs `tools/j2_cas_probe.py` against a real Kite session in staging and validates via `j2_capture_review.py`, the gate flips to REACHABLE.
