# Workflow C.C2 — asymmetric partial-fill pricing model (Q1-Q4 from operator decisions)

## Source

Per the 2026-09-16 operator decisions on C.2:
> Q1: 'Filled at mid + 2bps' (estimate from mid-price)
> Q2: All exchanges same (no per-exchange differentiation)
> Q3: Partial counts as CLOSED with partial P&L (realized partial fill)
> Q4: No new operator-config knobs

This slice implements the **bounded partial-fill pricing model**. The model helpers (mid+2bps estimator + partial-fill P&L aggregator) are pure / total / side-effect-free. The full-policy replay still uses fail-closed for `partial_book_before_decision` (line 200-203) but the asymmetric-fail-closed path (line 217-220) is **kept** — the model helpers are exposed for future use when the operator opts to model partials at the full-policy-replay layer.

## What landed (this slice)

| File | Type | Purpose |
|---|---|---|
| `python-engine/asymmetric_fill_model.py` | module (new) | `mid_price`, `estimate_missing_leg_price`, `compute_partial_fill_pnl` |
| `python-engine/tests/test_asymmetric_fill_model.py` | test (new) | 28 tests pinning the model contract |
| `docs/2026-09-15-workflow-c-c2-asymmetric-fill-model-done.md` | doc (new) | This file |

## The shift in defensive posture

Before this slice:
- The asymmetric-fill helpers did NOT exist as a reusable, pure module.
- The mid+2bps model was a verbal decision in the workflow investigation; nothing in the code matched it.

After this slice:
- `asymmetric_fill_model.py` is the **canonical reference implementation** of the Q1-Q4 decisions.
- The helpers are pure / total / side-effect-free — every input boundary has a defensive check (negative slippage, missing bid/ask, inverted book, non-numeric inputs, missing side, zero qty).
- The model is **exchange-agnostic** by design (Q2): no per-exchange switch.
- The model accepts the Q4 decision (no config knobs): slippage is a hard-coded default at the function signature, not a runtime config.

## What's still on C.2's backlog (NOT in this slice)

The full-policy replay in `partner_full_policy_replay.py` lines 217-220 still returns `INSUFFICIENT_EVIDENCE, reason=asymmetric_execution_quality_before_decision` when an asymmetric batch is detected in the pre-decision window. **This slice does NOT change that path** — the model helpers are the bounded reference implementation, but the dispatch to the model at the replay layer is a separate slice.

Reason: changing the fail-closed path is a behavioral change to a load-bearing function with 6 existing tests asserting `INSUFFICIENT_EVIDENCE`. The bounded-slice discipline is to ship the model first (this slice), let operators review the model contract, and then in a follow-up slice wire it into the replay path. The two slices are independent: the model can ship without the dispatch.

## Q3 implication for future wiring

When the operator decides to wire the model into the replay path, the dispatch will look like:
- Detect asymmetric batch in pre-decision window.
- For each leg, if it has a real broker fill → use the actual fill price; if it's missing → call `estimate_missing_leg_price(bid, ask, side)` with `mid_slippage_bps=2.0`.
- Call `compute_partial_fill_pnl(qty, filled_legs, missing_legs)` to get the partial P&L.
- Set `state=CLOSED, reason=partial_fill_modeled, partial_fill_observed=True`.

The existing `asymmetric_diagnostic` block (C.C1) remains in the report so operators can audit which legs were filled vs insufficient and when — that's the per-leg attribution the diagnostic already provides.

## Key design choices

- **Pure helpers only — no I/O.** `mid_price`, `estimate_missing_leg_price`, `compute_partial_fill_pnl` are total functions. No DB calls, no Kite calls, no logging.
- **Defensive everywhere.** Every input boundary has a check: negative slippage raises `ValueError`; missing bid/ask returns `None`; inverted book returns `None`; non-numeric inputs return `None`; missing side raises `ValueError`; zero qty raises `ValueError`.
- **Exchange-agnostic by design (Q2).** No `exchange` parameter anywhere. Two calls with identical inputs return identical P&L regardless of the caller's exchange label.
- **Slippage is a function default, not a config knob (Q4).** `mid_slippage_bps=2.0` is the default at the function signature. Changing it requires editing `asymmetric_fill_model.py` — that's the desired behavior per Q4.
- **Missing leg with degenerate quote → zero P&L contribution.** Rather than crashing the replay, the model degrades gracefully when the top-of-book is missing. The diagnostic block surfaces the leg name and the missing bid/ask so operators can audit.
- **`Side` is a `Literal["BUY", "SELL"]`** — type-safe enum, accepts lowercase via `.upper()`.

## Defensive regression

| Test file | Tests | Δ |
|---|---|---|
| `test_asymmetric_fill_model.py` | 28 | +28 (new file) |

All 28 tests PASS. Zero regressions in any other surface (the full-policy replay path is unchanged).

## What this does NOT solve

- The full-policy replay still returns `INSUFFICIENT_EVIDENCE` on asymmetric batches — wiring the model is a follow-up slice.
- The held-out qualification path doesn't yet see partial-fill P&L — that's also a follow-up.
- Historical partial-fill data (none in PROD per the audit) is unaffected.

## Critical invariants preserved

- `asymmetric_diagnostic` block in the report — unchanged.
- Fail-closed behavior on `partial_book_before_decision` (line 200-203) — unchanged.
- Fail-closed behavior on `asymmetric_execution_quality_before_decision` (line 217-220) — unchanged.
- All existing tests pass.

## Operator runbook

After deploy to PROD, the model helpers are available but not auto-wired:
- `from asymmetric_fill_model import mid_price, estimate_missing_leg_price, compute_partial_fill_pnl`.
- Callers can experiment with the model in held-out review without changing the replay path.
- When the operator is ready to switch the replay to the model, a follow-up slice will:
  - Replace lines 217-220 with a model-based path.
  - Update the 6 existing `asymmetric_execution_quality_before_decision` tests to assert `state=CLOSED, reason=partial_fill_modeled, partial_fill_observed=True` instead.
  - Add the partial P&L to the report.

## What's still open on the audit

- **C.2** (asymmetric partial-fill model) — model helpers DONE in this slice; replay-path wiring remains.
- **B-1** / **B-3** — DONE in `49456be`.
- **F-2** / **F-5** / **F-8** — DONE.
- **C.2 wiring** — separate slice.
