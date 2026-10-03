# F0-R1 — fee-inclusive exposure conservation (October 3, 2026)

Parent: [independent F0 review](2026-10-03-fno-f0-independent-review.md), item R1.

## Problem

Both paper admissions reserve the structural loss plus a fee reserve:
- single-leg reserves `ml + calc_fno_costs(ask, 0, qty)`;
- defined-risk (DR) reserves `max_loss_rs + structure_round_trip_cost`.

When the position row is inserted, the reservation is consumed. From then
on, `fno_shared_risk._read_view` counts only `max_loss_rupees` /
`max_loss_rs`, so the fee portion becomes free capacity.

Review reproduction:
1. Pool ₹7,551.57826385.
2. Reserve a 75-unit long at premium 100: loss 7,500 plus fee 50.57826385.
3. Capacity is 1 before the insert, but 51.58 after it.
4. A second reservation of 50.58 is then accepted, although joint loss plus
   charges now exceeds the pool.

## Contract

1. **Single-leg.**
   - `fno_positions` gains an additive column `risk_fee_reserve_rupees`.
   - Both insert writers default it to `calc_fno_costs(entry_premium, 0.0,
     qty)`, using the **actual fill and filled quantity**.
   - For a bought option, cash loss plus fees is largest when the premium
     falls to zero. So `entry × qty + fees(entry, 0, qty)` is the exact
     worst-case cash, and the reserve is never computed from a guess.
   - The live entry is a BUY LIMIT at ask, so the fill is at most ask. The
     post-insert exposure is therefore no larger than the consumed
     reservation, and the difference is a verified release.
2. **DR.** The existing frozen `entry_cost_rs` (written at insert) is the
   fee reserve.
3. **Immutability.** Once populated, the single-leg fee reserve and DR
   `max_loss_rs` / `entry_cost_rs` are protected by additive `BEFORE UPDATE`
   triggers.
4. **Counted once, through every state.**
   - Exposure per `OPEN`/`UNRESOLVED` row is loss plus fee reserve.
   - Reserved, then open or unresolved, it is counted exactly once.
   - After a verified partial exit, the residual keeps the **full** frozen fee
     reserve. Fees rise with quantity, so this is an upper bound. The partial
     fill's own charges are already in the exact ledger cash.
   - A terminal close removes the row from exposure; its ledger cash carries
     the actual fees.
5. **Fail closed.**
   - An `OPEN`/`UNRESOLVED` row with a missing, negative or non-finite fee
     reserve makes the view unavailable (`*_fee_reserve_unbound`).
   - So does a single-leg row whose structural loss is below its paid premium
     at risk (`entry_premium × qty`): `structural_loss_below_premium_at_risk`.
   - Unavailable economics are never treated as zero fees, and no legacy row
     is backfilled.

   Production currently has no open or unresolved F&O rows (38 single-leg
   and 28 DR, all closed), so this causes no deployment stall.
6. **Reporting.** `SharedFnoRiskView` gains an additive field
   `open_fee_reserve_rs`. `open_worst_case_cash_rs` now includes fees.

**Out of scope, recorded:** the DR fee estimate uses the existing flat
round-trip model. For credit structures, a catastrophe exit can trade at
higher premiums than entry, so this is an estimate rather than a proven
upper bound. Improving the multi-leg fee model is a separate fee-model item.
R1 makes whatever was reserved conserved rather than silently released.
Sizing, thresholds, signals, broker calls and exit authority are unchanged.

## Acceptance

- The review reproduction passes for both books: after consumption,
  capacity stays at the pre-insert value (minus any verified fill
  difference), and a competing reservation for the fee amount is refused.
- A reserved → open → unresolved → partial → closed walk counts exposure
  once. A partial keeps the residual loss plus the full fee. A close moves to
  exact ledger cash.
- Missing, negative or non-finite fee reserves and under-bound structural
  loss each fail closed. The triggers block rewrites.
- Existing feasible paper admissions (orchestrator and DR fixtures) still
  open.

## Rollout and rollback

- **Rollout.** Dev only, with an additive column and triggers created by the
  existing init functions. Then local commit, GitHub promotion and paper
  observation.
- **Rollback.** Revert the view and writer change. The additive column and
  triggers are harmless if left in place, and positions, ledger and
  reservations are preserved.

## Implementation result (Dev only; not pushed, not deployed)

Implemented as contracted, in three files:
- **`fno_positions.py`**
  - additive column `risk_fee_reserve_rupees`;
  - a shared `_with_entry_baselines` used by both insert writers. It freezes
    `calc_fno_costs(entry_premium, 0, qty)` from the actual fill;
  - a `fno_positions_fee_reserve_immutable` trigger.
- **`fno_dr_book.py`.** A `fno_dr_positions_risk_evidence_immutable`
  trigger protects `max_loss_rs` and `entry_cost_rs`.
- **`fno_shared_risk.py`.**
  - the view counts loss plus fee reserve for every `OPEN`/`UNRESOLVED` row;
  - it fails closed with `single_leg_fee_reserve_unbound`,
    `defined_risk_fee_reserve_unbound` or
    `structural_loss_below_premium_at_risk`;
  - `SharedFnoRiskView.open_fee_reserve_rs` is added.

No change to sizing, thresholds, signals, broker calls, settlement or exit
authority.

Test fixture corrections:
- The shared atomic-settlement helper modelled a 75-unit long at premium 100
  with `max_loss_rupees=1500`, which understates its ₹7,500 premium at risk.
  It now accepts `max_loss_rupees` (default unchanged), and the recovery
  tests use the honest 100 × qty.
- The shared-risk fixtures now include entry economics and fee reserves.
  Their expected totals are fee-inclusive.

### Verification (Dev runtime, Windows)

| Command (from `python-engine`) | Result |
| --- | --- |
| `-m pytest tests/test_fno_r1_fee_exposure.py -q -W error` | **11 passed** |
| The review's six-file selection plus `tests/test_atomic_settlement.py` | **126 passed**, 1 known Starlette deprecation |
| All `tests/test_fno*.py` plus atomic-settlement, performance, broker-reconciliation and mark-to-market | **530 passed, 1 failed** |

The single failure is pre-existing and unrelated:
`test_mark_to_market.py::TestFnoDrMark::test_actual_dr_writer_row_is_explicitly_unsupported`
constructs `PlannedStructure` without the required `contract_legs`. It fails
identically on the untouched baseline (`git stash` check).

- **Defect proof.** Both review-reproduction tests (single-leg and DR) fail
  against the pre-R1 `fno_shared_risk.py` from `HEAD` and pass with R1.
- **Conservation.** The lifecycle test shows available capacity is identical
  in the open, unresolved and catastrophe-closed states. At the close, the
  exposure becomes exact ledger cash.
- **Fill difference.** A fill below ask releases only the verified fee
  difference.

### Remaining

- R2 (single dispatch owner and ambiguous-entry recovery), R3, R4 and R5.
- The multi-leg fee bound for DR credit structures (fee-model item above).
- F1.

### Commit receipt

- **Implementation commit.** `d4fd298` (`fix(fno): keep fee reserve in shared
  exposure after reservation (F0-R1)`) on
  `codex/production-correction-hedge-p0`. It is Dev-local only: not pushed
  and not deployed. Production is unchanged at `044c016`.
- **Post-commit check.**
  - Regenerating the atlas produced no diff.
  - The guide, plan, checklist and review all link to this slice.
  - Re-running the R1, shared-risk and recovery tests from the committed
    tree, warnings-fatal, gave 47 passed. The one deselected test is the
    known ASGI route test, which emits an existing deprecation warning.
- **Migrations.** An additive column and two triggers are created by the
  existing init functions. There is no settings change.
