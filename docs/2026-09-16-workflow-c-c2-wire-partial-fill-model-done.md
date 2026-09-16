# Workflow C.C2.WIRE — wire the asymmetric partial-fill model into the full-policy replay

## Source

Per the 2026-09-16 operator decisions on C.2:
> Q1: 'Filled at mid + 2bps' (estimate from mid-price)
> Q2: All exchanges same (no per-exchange differentiation)
> Q3: Partial counts as CLOSED with partial P&L (realized partial fill)
> Q4: No new operator-config knobs

The bounded-slice discipline split the C.2 work into two commits:
- `31bf71d` (C.C2) — pure model helpers (`asymmetric_fill_model.py`) + 28 tests.
- This slice (C.C2.WIRE) — wire the model into the full-policy replay, replacing the C.A1 fail-closed path with the model-based path.

## What landed

| File | Type | Purpose |
|---|---|---|
| `python-engine/partner_full_policy_replay.py` | source (extended) | Replaces lines 217-220 (asymmetric fail-closed) with model-based dispatch |
| `python-engine/tests/test_partner_full_policy_replay.py` | test (extended) | 3 tests updated to assert the new model-based behavior |
| `docs/2026-09-16-workflow-c-c2-wire-partial-fill-model-done.md` | doc (new) | This file |

## The behavioral change

Before this slice (C.A1 fail-closed):
```python
if any(_pre_decision_window_hit(item, book_at_decision.received_at, now)
       for item in build.asymmetric_batches or []):
    report.update(state="INSUFFICIENT_EVIDENCE",
                  reason="asymmetric_execution_quality_before_decision")
    return {**report, "evidence_sha256": _sha(report)}
```

After this slice (C.C2.WIRE model-based):
```python
pre_decision_asymmetric_batches = [
    item for item in build.asymmetric_batches or []
    if _pre_decision_window_hit(item, book_at_decision.received_at, now)
]
if pre_decision_asymmetric_batches:
    # For each batch, model the missing leg at mid+2bps.
    # Sum the partial P&L across batches. Set state=CLOSED.
    ...
    report.update(state="CLOSED", reason="partial_fill_modeled",
                  partial_fill_observed=True)
```

## The shift in defensive posture

Before this slice, the system refused to qualify any replay that had an asymmetric batch in the pre-decision window — even when the missing leg had a clear mid-price quote. The diagnostic block (C.C1) surfaced the attribution but no P&L was computed.

After this slice, the system models the missing leg at mid+2bps, computes the partial P&L, and returns `state=CLOSED` with the modelled attribution. The asymmetric_diagnostic block (already in place from C.C1) is extended with:
- `modeled_missing_legs`: list of `{received_at, leg_name, side, modeled_fill_price, modeled_mid_slippage_bps, partial_pnl_rs}` entries.
- `total_modeled_pnl_rs`: sum of all per-leg modelled P&L across the pre-decision window.
- `modeled_slippage_bps`: 2.0 (the Q1 default).

Operators can now query `SELECT * FROM held_out WHERE state='CLOSED' AND reason='partial_fill_modeled'` to find every replay that was qualified via the model.

## Key design choices

- **Exchange-agnostic (Q2)**: no per-exchange switch — the model is applied identically regardless of NSE / NSE F&O / BSE.
- **Slippage hard-coded (Q4)**: `mid_slippage_bps=2.0` is the function default, not a runtime config knob. Changing it requires editing `asymmetric_fill_model.py`.
- **Aggregate across batches**: multiple asymmetric batches in the pre-decision window all contribute to the modelled P&L. Each batch's missing leg is modelled independently.
- **Backwards-compatible diagnostics**: the existing C.C1 fields (`pre_decision_asymmetric_observed`, `asymmetric_batch_count`, etc.) are unchanged. The new fields (`modeled_missing_legs`, etc.) are additive.
- **`partial_fill_observed: True`**: the new flag mirrors `asymmetric_batches[].state == 'ASYMMETRIC_EXECUTION_QUALITY'` so consumers can filter for modelled partials without joining the diagnostic block.

## Tests updated

3 existing tests in `test_partner_full_policy_replay.py` asserted the old fail-closed behavior:
- `test_asymmetric_execution_quality_before_decision_is_insufficient_evidence` → renamed to `test_asymmetric_execution_quality_before_decision_is_partial_fill_modeled` and updated to assert `state=CLOSED, reason=partial_fill_modeled, partial_fill_observed=True`.
- `test_asymmetric_diagnostic_attribution_pre_decision` — the trailing assertion updated to assert the new behavior.
- `test_asymmetric_diagnostic_aggregates_multiple_batches` — the trailing assertion updated; added assertion for two `modeled_missing_legs` entries and `total_modeled_pnl_rs` present.

Other asymmetric-related tests (post-decision, malformed `received_at`, clean run) are unchanged.

## Defensive regression

| Test file | Tests | Δ |
|---|---|---|
| `test_partner_full_policy_replay.py` | 21/21 PASS | 0 (3 updated, 0 added) |
| `test_asymmetric_fill_model.py` | 28/28 PASS | +28 (already shipped in C.C2) |
| Full narrow python-engine regression (40 test files) | 504/504 PASS | 0 |

Zero regressions in any other surface.

## What this does NOT change

- **`partial_book_before_decision` (line 200-203) is unchanged**. The wire-up is only for asymmetric-fills. Partial-book (where ONE batch lacks full two-leg depth) is still fail-closed — that's a different code path (line 200 checks `partial_batches`, not `asymmetric_batches`).
- **`decision_book_stale` (line 221-223) is unchanged**. Stale quotes still trigger INSUFFICIENT_EVIDENCE.
- **`public_lifecycle_coverage_missing` (line 244) is unchanged**. The public-thesis lifecycle check is independent.

## Operator runbook

After deploy to PROD:

1. The full-policy replay will return `state=CLOSED, reason=partial_fill_modeled` for any replay with an asymmetric batch in the pre-decision window, instead of `state=INSUFFICIENT_EVIDENCE, reason=asymmetric_execution_quality_before_decision`.

2. To audit every replay that was qualified via the partial-fill model:
   ```sql
   SELECT * FROM held_out WHERE state='CLOSED' AND reason='partial_fill_modeled';
   ```
   The modelled attribution is in the JSON `asymmetric_diagnostic.modeled_missing_legs` field.

3. To compute the modelled P&L across all held-out replays:
   ```sql
   SELECT SUM(json_extract(asymmetric_diagnostic, '$.total_modeled_pnl_rs'))
   FROM held_out WHERE state='CLOSED' AND reason='partial_fill_modeled';
   ```

4. If you want to disable the model (revert to fail-closed), revert commit `<this-commit>`. The pre-commit fail-closed behavior is preserved in git history.

## Critical invariants preserved

- **`asymmetric_diagnostic` block keys**: `pre_decision_asymmetric_observed`, `asymmetric_batch_count`, `pre_decision_batch_count`, `executable_legs`, `insufficient_legs`, `earliest_received_at`, `latest_received_at` — all unchanged.
- **`asymmetric_batches` list in report**: unchanged.
- **`partial_book_before_decision`**: unchanged (still fail-closed at line 200-203).
- **`decision_book_stale`**: unchanged (still fail-closed at line 221-223).
- **`partial_batches` / `conflicting_batches`**: unchanged.

## What's still open

- **C.2 held-out wiring**: the held-out review path (`intraday_spread_holdout.py`) doesn't yet see `partial_fill_observed: True` partials separately. When the held-out diagnostic block is extended to count partial fills distinctly from full closes, operators can audit how many CLOSED outcomes were qualified via the model vs the historical broker-fill path. Separate slice.

## Audit trail summary

```
49456be feat(c): C.B1 + C.B3 -- held-out adequacy + settlement assumptions
63d46ad fix(penny): C.F8 -- write TRADE_OPENED to bankroll_ledger
e2fe147 feat(cli): C.F5 -- J.10 features inventory CLI
729f7f1 fix(gateway): C.F2 -- add Kite LTP fanout observability
0ba14a9 fix(penny): C.B.3 -- dedup penny_universe stale warning
dfc306a feat(c): C.C1 -- structured asymmetric-fill diagnostic
04aa166 fix(agent): C.B.2 -- agent dedup file observability
7cf87c3 fix(research): C.B.1 -- finalize_prior_days race fix
31bf71d feat(c): C.C2 -- asymmetric partial-fill pricing model
<this-commit> feat(c): C.C2.WIRE -- wire model into full-policy replay
```

PROD untouched. Dev only.
