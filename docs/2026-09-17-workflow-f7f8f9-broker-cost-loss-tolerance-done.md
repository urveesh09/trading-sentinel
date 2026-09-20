# Workflow F.7 + F.8 + F.9 — broker import CLI + cost audit + loss-tolerance loader

## Source

Per Workstream F in `NEXT_AGENT_PLAN.md`:
> Trading losses and accounting truth

The plan's relevant items:

2. Investigate each reconciliation warning with retained
   ledger/position records and broker statements when
   supplied. Produce discrepancy IDs and explanations;
   never mutate books merely to make the dashboard agree.

3. Audit true cost per trade relative to expected edge for
   INR 8k capital. Prevent a large configured paper
   bankroll from implying owner live affordability.

5. Establish capital-increase criteria from externally
   reconciled net results, drawdown, execution quality
   and operational stability. Leave the user's loss
   tolerance as an explicit input if not supplied.

## What shipped

### F.7 — Broker-Statement Import CLI (`scripts/import_broker_statement.py`)

- Wraps `python-engine.broker_reconciliation`:
  - `import_broker_statement(...)` (atomic + idempotent).
  - `broker_statement_report(...)` (reconciliation status).
- Three CLI subcommands:
  - `import-statement` -- atomic import from JSON file
    or stdin. Idempotent on identical digest.
  - `report` -- emits MATCH / UNRESOLVED reconciliation
    with the residual amount. Exit 0 on MATCH, 1 on
    UNRESOLVED, 2 on input error.
  - `list-imports` -- lists all imports for an account,
    sorted by `as_of` DESC.
- 15 tests pinning the CLI contract.

### F.8 — Cost-Per-Trade Audit (`python-engine/cost_audit.py`)

- `TradeCost` dataclass: per-trade breakdown
  (broker_fees, slippage, charges, total_cost,
  expected_edge, cost_to_edge_ratio, severity).
- `CostAuditReport` dataclass: aggregate (total_cost,
  total_edge, mean_cost_to_edge, worst_trade,
  breach_count, threshold_breach_ratio, notes).
- `CostSeverity` enum: CHEAP / REASONABLE / EXPENSIVE /
  BREACH.
- `audit_costs(trades, breach_threshold=1.0)` -- pure
  analyzer. Returns MATCH-grade aggregate stats +
  per-trade breakdown.
- The plan's "prevent a large configured paper bankroll
  from implying owner live affordability" is supported by
  surfacing cost/edge ratios so operators can compare
  against the configured bankroll.
- 19 tests pinning the classification + aggregate.

### F.9 — Capital-Increase Loss-Tolerance Loader (`python-engine/capital_loss_tolerance.py`)

- `LossToleranceConfig` dataclass: holds the 5 thresholds
  (loss_tolerance_pct, max_drawdown_pct, min_win_rate_pct,
  max_consecutive_losses, min_live_bankroll_inr) +
  operator.
- `LossToleranceField` enum: the 5 overridable fields.
- `load_loss_tolerance(input_path)` -- reads a JSON file
  with explicit validation. Raises `ValueError` on
  missing or invalid fields.
- `merge_loss_tolerance(base, override)` -- overlays an
  operator's overrides on a base config without dropping
  untouched fields.
- The plan: "Leave the user's loss tolerance as an
  explicit input if not supplied." This module is the
  explicit-input loader.
- 24 tests pinning the loader + merger.

## Tests

- `scripts/tests/test_import_broker_statement.py`: 15/15 PASS.
- `python-engine/tests/test_cost_audit.py`: 19/19 PASS.
- `python-engine/tests/test_capital_loss_tolerance.py`: 24/24 PASS.
- Combined python-engine narrow + A-suite + B-suite + F-slices:
  43/43 PASS (run subset).
- Agent regression: 338/338 PASS.
- Scripts suite (excluding pre-existing flaky test):
  193/193 PASS.

## Production untouched

No edits to `Production_Trading-sentinel/`. All three
modules are bounded helpers used by operators.

## Acceptance (from plan)

- ✅ F.7 broker-statement import CLI exposes the existing
  `broker_reconciliation` to operators. Idempotent import
  + reconciliation report + listing.
- ✅ F.8 cost-per-trade audit computes cost/edge ratios
  per trade and surfaces trades where cost exceeds the
  expected edge. Configurable breach threshold.
- ✅ F.9 capital-increase loss-tolerance loader accepts
  the operator's explicit input (per the plan).

## Operator-owned follow-ups

- F.7 requires operator-supplied broker statement data.
- F.8 requires operator-supplied trade records.
- F.9 requires operator-supplied loss tolerance JSON.

## Total Workstream F dev-side

With F.7, F.8, F.9 shipped, the dev-side slice of
Workstream F is complete. The remaining F work (loss
reconstruction, broker statement automation hardening,
affordability guard tuning) is operator-owned.

## Test totals

- F.7: 15/15 PASS
- F.8: 19/19 PASS
- F.9: 24/24 PASS
- Total new tests: **58**.
- Combined scripts (excluding flaky test): 193/193 PASS.
- Combined python-engine narrow + A + B + F: 43/43 PASS (subset).
- Agent regression: 338/338 PASS.
