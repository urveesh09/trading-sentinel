# F0-R4 — bind retained broker payloads and entry/cost economics (October 3, 2026)

Parent: [independent F0 review](2026-10-03-fno-f0-independent-review.md),
item R4. Builds on R1–R3.

## Problem (from source)

1. **The digest check accepts any packet.** `_recovery_evidence_is_intact`
   accepts any JSON object whose SHA-256 matches, including `{}`. The F0-D
   and F0-E partial-integrity fixtures deliberately use `{}` as accepted
   proof.
2. **The packet is never compared with the receipt.**
   `_validate_open_partial_exit_evidence` checks the receipt's own scalar
   arithmetic, but never compares the retained broker order, trades and
   net position against the receipt's:
   - account, symbol and order;
   - terminal status and quantities;
   - weighted fill price.

   A receipt whose price, cash and costs were all altered consistently
   still grants capacity.
3. **Entry premium can drift.** The receipt's `entry_premium` is not bound
   to the position's entry premium, and the position's entry premium,
   symbol and source are not immutable.
4. **Charges have no provenance.** Any non-negative cost scalar is accepted.
   Nothing records which cost schedule produced the charge, and the reader
   cannot re-derive it without repricing at today's settings.

## Contract

1. **One packet interpretation.**
   - A new pure module, `fno_exit_evidence.py`, holds `derive_exit_facts`:
     the order, trade and net-position checks moved verbatim from
     `verify_broker_exit` (field identity, terminal status, timing,
     quantities, unique trade ids, trade/order agreement, weighted price,
     net residual).
   - The live verifier keeps its order-book checks (unique match,
     unreconciled same-symbol orders), then calls this function.
   - The shared risk reader calls the same function on the **retained**
     packet. It never calls the broker.
   - `RecoveryConflict` moves to that module and is re-exported.
2. **Receipt binding (`validate_retained_exit_receipt`).** For each
   recovery of an open single-leg position:
   - the packet parses, its digest matches, and it carries the receipt's
     `account_id`, an `order`, `trades`, `net_position` and a
     timezone-aware `observed_at`;
   - the derived facts must equal the receipt's terminal status, filled
     quantity, remaining quantity and fill price, with the intent quantity
     equal to filled plus remaining;
   - trade ids must be unique across all recoveries of the position;
   - the receipt's entry premium must equal the position's;
   - filled receipts must carry a valid frozen cost snapshot, and
     `costs == calc_fno_costs_from_snapshot(entry, fill, filled, snapshot)`.

   Each failure denies new entry:
   - `recovery_payload_mismatch`;
   - `recovery_entry_economics_mismatch`;
   - `recovery_cost_provenance_unavailable`;
   - `recovery_cost_mismatch`.

   Pre-R4 receipts on open positions have no cost provenance and fail
   closed. Nothing is backfilled or repriced.
3. **Writer.** `resolve_exit_intent` computes costs from
   `options_cost_snapshot()`, an arithmetic identical to `calc_fno_costs`.
   It persists the snapshot in an additive `cost_snapshot_json` column; the
   existing immutable-receipt triggers already protect it.
4. **Immutability.** An additive `fno_positions_identity_immutable` trigger
   protects populated `entry_premium`, `tradingsymbol` and `source`. No
   writer updates them.

**Limitation (stated, not hidden).** Hash integrity is not authenticity.
Someone able to rewrite the receipt, the packet and the digest together, and
to bypass the triggers, defeats any local check. R4 removes the
inconsistent-edit and empty-payload paths. Broker-signed or
statement-level evidence would be F1 or later.

Sizing, thresholds, signals and exits are unchanged. Live recovery stays
operator-authorised.

## Acceptance

- The real writer's output, from the mocked broker, passes the binding and
  releases only the residual.
- Each of these fails closed:
  - an empty payload;
  - a packet with the wrong symbol, account, order or tag;
  - a consistent wrong price (receipt, cash and costs all edited);
  - wrong costs, or missing or invalid cost provenance;
  - a changed entry premium;
  - duplicate trade ids within a packet or across recoveries;
  - a packet whose net residual disagrees with the receipt;
  - a pre-R4 receipt without cost provenance.
- The triggers block entry-identity rewrites.
- The live verifier keeps its existing rejections, now through the shared
  function, and the existing recovery tests pass.

## Rollout and rollback

- **Rollout.** Dev only, with an additive column and trigger. Then local
  commit and GitHub promotion.
- **Rollback.** Revert the reader and writer. The column and triggers are
  harmless and the receipts are preserved.

## Implementation result (Dev only; not pushed, not deployed)

Implemented as contracted.

- **New `python-engine/fno_exit_evidence.py`.**
  - `derive_exit_facts`: the packet checks moved verbatim from
    `verify_broker_exit`, plus explicit order-id and net-position identity
    checks.
  - `validate_retained_exit_receipt`, `encode_evidence` and
    `valid_cost_snapshot`.
  - `RecoveryConflict`, re-exported by `fno_exit_recovery`.
- **`fno_exit_recovery.py`.**
  - The live verifier keeps its order-book checks, then derives the facts
    through the shared function.
  - `resolve_exit_intent` computes costs with
    `calc_fno_costs_from_snapshot(options_cost_snapshot())`, identical
    arithmetic to `calc_fno_costs`, and stores `cost_snapshot_json`.
- **`fno_positions.py`.**
  - Additive `fno_exit_recoveries.cost_snapshot_json` column.
  - Additive `fno_positions_identity_immutable` trigger for `entry_premium`,
    `tradingsymbol` and `source`.
- **`fno_shared_risk.py`.**
  - Every recovery of an open position is re-derived from its packet and
    bound to the position's entry premium and symbol.
  - Its charges are recomputed from the frozen snapshot.
  - Trade ids must be unique across the position's recoveries.
- **Test fixtures.** The two F0-D/E fixtures that accepted `{}` as proof
  now carry genuine packets and cost snapshots.

### Verification (Dev runtime, Windows, from `python-engine`)

| Command | Result |
| --- | --- |
| `-m pytest tests/test_fno_r4_payload_binding.py -q -W error` | **18 passed** |
| R1–R4, shared-risk and recovery tests (`-W error`, known deprecated ASGI route test deselected) | **122 passed** |
| F&O, Kite, settlement, performance, reconciliation, mark-to-market, halt / owner-halt / order-execution, operator status, NIFTY commands and daily decision quality | **781 passed, 1 skipped, 1 failed** |

The one failure is the pre-existing, unrelated
`TestFnoDrMark::test_actual_dr_writer_row_is_explicitly_unsupported`.

**Defect proof.** With the pre-R4 `fno_shared_risk.py` from `HEAD` swapped
in, all **15** corruption tests failed: the old reader granted capacity on
forged evidence. With R4 restored, all 18 pass. Covered:
- an empty payload;
- wrong symbol, account, `placed_by`, order or tag;
- a price edited only in the packet;
- a duplicate trade within a packet, and a reused trade id across
  recoveries;
- a disagreeing net residual;
- a non-terminal status;
- a naive packet clock;
- a consistent wrong price (receipt, cash and costs all edited);
- costs off by ₹1 with consistent cash;
- missing or invalid cost provenance;
- a changed entry premium (also trigger-protected).

The existing 31 recovery and boundary tests pass through the shared
function.

### Remaining

- R5 (transactional occupancy caps and post-wait clocks, including the
  one-DR-structure race).
- Optionally, reject reused trade ids at write time in
  `resolve_exit_intent` (the reader already fails closed).
- Multi-leg DR fee bound.
- The live `fno_risk.kill_switch_status` reader.
- F1. Broker authenticity, as opposed to local integrity, remains an F1 or
  statement-evidence concern.

### Commit receipt

- **Implementation commit.** `0bc8fa4` (`fix(fno): bind retained broker
  payloads and entry/cost economics (F0-R4)`) on
  `codex/production-correction-hedge-p0`. It is Dev-local only: not pushed
  and not deployed. Production is unchanged at `044c016`.
- **Post-commit check.**
  - Regenerating the atlas produced no diff (232 modules, now including
    `fno_exit_evidence.py`).
  - The guide, plan, checklist and review all link to this slice.
  - Re-running the R4, shared-risk and recovery tests from the committed
    tree, warnings-fatal, gave 54 passed. The one deselected test is the
    known ASGI route test.
- **Migrations.** One additive column and one trigger, created by the
  existing `init_fno_positions_db`. There is no settings change.
