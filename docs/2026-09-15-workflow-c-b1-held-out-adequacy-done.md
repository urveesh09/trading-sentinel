# Workflow C.B1 — held-out evidence adequacy diagnostic (B-1 from prod audit)

## Source

Per the 2026-09-15 production deep audit and workflow investigation:
> 6. **Adequate genuine held-out evidence.** Need real production sessions with non-tampered captures. Per inheritance doc §11 and AGENTS.md: this requires the operator to run the J.3 capture review happy-path under live conditions.

> C — replay fidelity/review integration | TESTED_DEV | [8 sub-slices complete] | Obtain adequate genuine held-out evidence

The plan doc's acceptance criterion for held-out evidence is:
> "two unmocked archived sessions containing one finite costed close and one unresolved outcome"

So a held-out sample is "ADEQUATE" iff it contains AT LEAST:
- 1 CLOSED case (finite costed close with measurable P&L).
- 1 UNRESOLVED case (no fill, ambiguous exit, or non-closed).
- At least one case with verified full-policy cost evidence (`cost_sensitivity` non-empty).

## What landed

| File | Type | Purpose |
|---|---|---|
| `python-engine/intraday_spread_holdout_adequacy.py` | module (new) | `evaluate_heldout_adequacy` + `AdequacyThresholds` + `HeldOutAdequacy` |
| `python-engine/tests/test_intraday_spread_holdout_adequacy.py` | test (new) | 13 tests pinning the diagnostic contract |
| `docs/2026-09-15-workflow-c-b1-held-out-adequacy-done.md` | doc (new) | This file |

## The shift in defensive posture

Before this slice, the held-out qualification pipeline emitted a `build_heldout_comparison` report but had no built-in answer to "is this enough?". Operators had to manually inspect the per-group counts and reason about adequacy.

After this slice:
- `evaluate_heldout_adequacy(report)` returns a structured verdict (ADEQUATE / INADEQUATE) with the per-group breakdown and the list of unmet thresholds.
- `format_adequacy(adequacy)` renders a human-readable summary suitable for operator runbooks.
- Operators can override `AdequacyThresholds` (e.g. require 5 closed + 3 unresolved for stricter qualification gates).

The diagnostic does NOT collect sessions or run live Kite calls — that remains operator-owned (the audit's B-1 explicitly says: "this requires the operator to run the J.3 capture review happy-path under live conditions"). The diagnostic ONLY inspects an existing held-out report.

## Key design choices

- **Default thresholds match the plan doc**: 1 CLOSED + 1 UNRESOLVED + at least one cost_sensitivity row.
- **`require_full_policy_evidence` defaults to True** — a held-out report without verified cost evidence is INADEQUATE for qualification review.
- **Fail-closed on malformed input** — `evaluate_heldout_adequacy({})` raises `ValueError("report must have a 'groups' field")` rather than silently returning INADEQUATE.
- **Defensive bucket iteration** — non-mapping buckets are skipped, not raised. This makes the diagnostic resilient to legacy or partial reports.
- **`evaluated=0` always flags INADEQUATE** — even if all other thresholds are relaxed, an empty held-out set is never ADEQUATE (cannot have a verdict with no opportunities).
- **Per-group breakdown preserved** — operators can see which underlying/policy contributed each count, not just the aggregate.

## Defensive regression

| Test file | Tests | Δ |
|---|---|---|
| `test_intraday_spread_holdout_adequacy.py` | 13 | +13 (new file) |
| `test_intraday_spread_holdout.py` | 15 | 0 (no changes) |

Full narrow regression surface (incl. B-3): 27 PASS. Zero regressions.

## Test discipline

- 13 tests pin the contract:
  1-4. Adequate case: 1 CLOSED + 1 UNRESOLVED + cost_sensitivity → ADEQUATE.
  5-7. Inadequate cases: no CLOSED / no UNRESOLVED / no evaluated → INADEQUATE with right unmet reasons.
  8. No cost_sensitivity → INADEQUATE ("no verified full-policy cost evidence").
  9-10. Threshold overrides: tighter thresholds flip ADEQUATE→INADEQUATE; relaxed thresholds allow NO_FILL-only runs.
  11-13. Malformed input: missing `groups`, non-list `groups`, non-mapping buckets.

The fixture builds `_cost_sensitivity` with the canonical `intraday_spread_cost_sensitivity_v1` schema — `format`, `expiry`, `policy_id`, `scenarios` (with matching `state` / `reason` / `net_pnl_rs` / `evidence_sha256` baseline), `can_qualify=False`, `can_place_orders=False`, and a valid `evidence_sha256` fingerprint.

## What this does NOT solve

- The actual held-out evidence collection — operator must run the J.3 capture review happy-path under live conditions.
- The auto-qualification decision — the diagnostic is informational; the existing `automatic_qualification: False` flag in the held-out report remains the source of truth.
- Historical GRAVISSHO / BALRAMCHIN evidence — not retroactively applied.

## Critical invariants preserved

- No change to `build_heldout_comparison` semantics.
- No change to `HeldOutCase` dataclass.
- The diagnostic is purely additive — reads the existing report, returns a verdict.

## Operator runbook

After deploy to PROD, the operator can run:

```python
from intraday_spread_holdout import build_heldout_comparison
from intraday_spread_holdout_adequacy import evaluate_heldout_adequacy, format_adequacy

report = build_heldout_comparison(...)
adequacy = evaluate_heldout_adequacy(report)
print(format_adequacy(adequacy))
```

The output is:

```
# Held-out evidence adequacy diagnostic
# -------------------------------------
# Verdict: ADEQUATE
# Total closed:    1
# Total unresolved:1
# ...
```

If the verdict is INADEQUATE, the diagnostic lists every unmet threshold so the operator knows exactly what's missing.

## What's still open on the audit

- **B-1** (held-out adequacy diagnostic) — DONE in this slice (`<next-commit>`).
- **B-3** (settlement assumptions) — DONE in same commit (`<next-commit>`).
- **C.2** (partial-fill P&L model) — OPEN, operator design input required (next slice).
