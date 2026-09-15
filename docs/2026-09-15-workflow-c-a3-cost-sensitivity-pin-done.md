# Workflow C.A3 — deterministic cost-sensitivity pin

## What landed

|| File | Type | Purpose |
|---|---|---|---|
| `python-engine/intraday_spread_holdout.py` | source (extended) | New `canonical_cost_sensitivity_fingerprint` helper; new `cost_sensitivity_sha256` field in the bucket's per-artifact cost_sensitivity entry |
| `python-engine/tests/test_intraday_spread_holdout.py` | test (extended) | 8 new tests pinning the scenario-set fingerprint contract |
| `docs/2026-09-15-workflow-c-a3-cost-sensitivity-pin-done.md` | doc (new) | This file |

## The shift in defensive posture

The plan flagged "immutable cost-sensitivity evidence for qualification review" as the next C-workstream slice. Previously:

- A `case.cost_sensitivity` payload was preserved verbatim in the bucket's `cost_sensitivity` list, including the scenarios array in whatever order the upstream code provided.
- The full-policy report's `evidence_sha256` was computed from the WHOLE report dict (including scenarios in their input order). Two qualification windows that used the SAME logical scenario set but in different orders produced DIFFERENT `evidence_sha256` values.
- The qualification review had no way to verify "these two runs used the same scenario set" without diffing the full scenarios list.

After this slice:

- The bucket's per-artifact `cost_sensitivity` entry carries a separate `cost_sensitivity_sha256` pin computed from the scenarios SORTED by `(fee_multiplier, additional_slippage_bps)`.
- The pin is **invariant under input-order permutations**. Two qualification windows that used the SAME logical scenario set produce the same pin regardless of how the upstream code ordered them.
- The pin is **sensitive to actual scenario-set changes**. Adding or removing a scenario changes the pin.

## Key design choices

- **Sort key is `(fee_multiplier, additional_slippage_bps)`.** This is the canonical coordinate of a cost-stress scenario -- the same dimensions the upstream `_validated_cost_sensitivity` already uses for de-duplication. Same fee with different slippage is treated as DISTINCT (they're different cost-stresses).
- **Pin is independent of `evidence_sha256`.** The report's existing `evidence_sha256` is preserved unchanged. The new pin is a parallel diagnostic that operators can use to compare scenario sets across runs without depending on the report's overall byte-comparison.
- **Defensive input handling.** Non-list inputs degrade to the canonical empty-list digest (`None`, `dict`, `str` -- all return `_digest([])`). The helper NEVER raises; a malformed input is detectable by comparing against the empty fingerprint.
- **Computed AFTER validation.** The pin is computed only for cases that survived `_validated_cost_sensitivity` (which raises on malformed scenarios). The pin attaches to buckets for VALIDATED cases only.
- **Pure / total helper.** Same shape as the J.10 / C contract -- never raises, returns deterministic output for any input.

## Operator runbook

After building a qualification report:

```bash
python -m research_cli replay-full-policy ... # writes a heldout report
```

The heldout report's `groups[].cost_sensitivity[].cost_sensitivity_sha256` field carries the pin. Operators verifying "did this run use the same scenario set as the last run" compare the pins directly:

```python
import json
current = json.load(open("latest_heldout.json"))
previous = json.load(open("previous_heldout.json"))
for bucket in current["groups"]:
    for cs in bucket["cost_sensitivity"]:
        # Compare cs["cost_sensitivity_sha256"] to the previous run's pin.
        ...
```

If the pins match, the scenario set is identical (regardless of upstream ordering). If they differ, the operator can diff the `artifact` block to see what changed.

## Defensive regression

Workflow C surface (10 test files): **142/142 PASS** in 4.49s (was 117; +25 net for A1+A3).

| Test file | Tests | Δ (vs 117 baseline) |
|---|---|---|
| `test_intraday_spread_holdout.py` | 15 | +8 |

0 regressions.

## Critical invariants preserved

- `evidence_sha256` of the heldout report unchanged.
- `_validated_cost_sensitivity` validation contract unchanged.
- `case.cost_sensitivity` storage unchanged (the pin is ADDITIVE on top of the existing fields).
- Backward-compatible: existing report consumers that don't read `cost_sensitivity_sha256` are unaffected.

## What's still on the Category A backlog

- A2 — chronological exit-delay monotonicity hardening (smaller polish).
- A4 — qualification manifest drift verification CLI (mirror of J.10.SUMMARY_VERIFY).
- A5 — research summary drift verification (mirror of A4).
