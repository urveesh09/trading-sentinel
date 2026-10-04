# F0-R2 — one dispatch owner and evidence-backed entry outcomes (October 3, 2026)

Parent: [independent F0 review](2026-10-03-fno-f0-independent-review.md),
item R2. Builds on [R1](2026-10-03-fno-f0-r1-fee-inclusive-exposure.md).

## Problem (reproduced from source)

1. **A reservation reply is treated as permission to send.**
   `reserve_shared_fno_risk` returns allowed/`already_reserved` for an
   identical `RESERVED` key before it consults the entry policy, and
   `_try_entry_for_leg` treats any allowed result as permission to call the
   executor. Two identical callers, or a retry after a same-day loss halt,
   can therefore send the order more than once. The position insert is
   atomic, but sending the order to the broker is not serialised.
2. **Every non-fill result releases the reservation.** Several of those
   results do not prove a zero fill:
   - The live `execute_entry` reports `timeout` after `_cancel_quietly`,
     which swallows cancel errors and never re-reads the final order state.
     A partial fill, or a fill that races the cancel, is released as free
     capital.
   - `_place_limit` turns *any* exception into `order_id=None` → `rejected`.
     A read timeout after the broker accepted the order is released.
   - A `COMPLETE` order without a price is treated as "no fill" (cancel, then
     release), although it filled.
   - The DR paper path also relies on the identical-key reply and has no
     claim.

These are source-level failure paths. No live incident is claimed;
`FNO_LIVE` entries remain gated by their existing authority, and F1 is still
required.

## Contract

1. **Separate the read receipt from the right to send.**
   - `reserve_shared_fno_risk` keeps its idempotent read receipt, but it is
     no longer authority to send.
   - A new `claim_shared_fno_entry_dispatch` takes `BEGIN IMMEDIATE`.
   - It requires the matching `RESERVED` reservation and no existing claim,
     re-reads the current entry policy (the same scope that admission used),
     and inserts exactly one `DISPATCHING` row in a new
     `fno_entry_dispatches` table. The table's primary key is the
     reservation key and each row carries a random owner token.
   - Only the claim winner may call the executor or insert the position.
   - If the policy now denies entry, nothing was sent, so the reservation is
     released as `policy_denied_before_dispatch`. Durable `RESERVED` or
     `UNRESOLVED` evidence can never be claimed again, and nothing expires
     by timer.
2. **Outcomes are typed and need evidence.**
   `resolve_shared_fno_entry_dispatch` (owner token required, applied once)
   changes the claim and the reservation together.

   **Release capacity** only with verified evidence:
   - `no_dispatch`: `dispatch_certainty=NOT_SENT`, meaning a halt or
     validation refusal before sending, a connection failure before sending,
     or paper with nothing external;
   - `rejected`: `BROKER_REJECTED`, an explicit HTTP 4xx with no order
     created;
   - `zero_fill_verified`: the final order state, re-read after the cancel,
     is `CANCELLED` or `REJECTED` with `filled_quantity == 0` and an order id.

   **Retain the full reservation** (claim becomes `UNRESOLVED`, the
   reservation stays `RESERVED`, with no release):
   - `partial`, `unknown`, `filled_unrecorded`.

   A successful position insert consumes the reservation and marks the claim
   `FILLED` in the same transaction. Consumption now **requires** a
   `DISPATCHING` or `UNRESOLVED` claim, so no reservation-backed position can
   exist without exactly one claim. Releasing a claimed reservation through
   the generic resolver is refused.
3. **Operator reconciliation.** `reconcile_shared_fno_entry_dispatch`
   releases an orphaned `DISPATCHING` claim (for example after a restart) or
   an `UNRESOLVED` one, but only with a named operator and verified evidence:
   - `zero_fill_verified` with an order id, terminal status and zero fill;
   - or `no_order_verified` with an account id, the check time and an empty
     list of matching orders.

   A discovered fill is recorded by inserting the position through the
   normal writer, which consumes the claim. Terminal claims (`FILLED`,
   `RELEASED`) and their evidence are immutable and cannot be deleted
   (triggers).
4. **Broker and executor evidence (additive).**
   - `KiteClient.place_order` returns `dispatch_certainty`:
     - `NOT_SENT`: halt or validation refusal, `ConnectError` or
       `ConnectTimeout`;
     - `BROKER_REJECTED`: HTTP 4xx;
     - `AMBIGUOUS`: 5xx, other request errors, or an accepted response
       without an order id;
     - `ACCEPTED`.
   - Live `FnoExecutor.execute_entry`:
     - after a non-`COMPLETE` wait, it cancels, keeps any cancel error, and
       **re-reads the final order state**;
     - it returns `filled` (including a fill that races the cancel),
       `zero_fill_verified`, `partial`, `rejected`, `no_dispatch` or
       `unknown`, with an `evidence` dict;
     - a missing `dispatch_certainty`, an exception or an unreadable final
       state is `unknown`.
   - Paper is unchanged.
5. **Orchestrator and DR.** Both books follow reserve → claim → act →
   resolve. A paper insert failure resolves as `no_dispatch` (nothing
   external exists). A live fill whose insert fails resolves as
   `filled_unrecorded` (retained). `partial` and `unknown` log a critical
   line telling the operator to reconcile.

**Unchanged:** sizing, thresholds, signals, exits and the separate R5
occupancy race (the one-DR-structure cap) and R3/R4. Live entries keep
their existing authority gates.

## Acceptance

- Barrier test: two identical concurrent claims grant exactly one. At the
  orchestrator level, a second identical entry attempt never calls the
  executor.
- Loss-halt retry: a `RESERVED` key whose policy is now halted is denied at
  the claim and released as `policy_denied_before_dispatch`, with no
  executor call.
- Restart: an orphaned `DISPATCHING` claim cannot be re-claimed, keeps its
  exposure, and is released only by verified operator reconciliation.
- Executor:
  - a transport exception, 5xx, cancel failure, unreadable final state, or
    `COMPLETE` without a price gives `unknown` (retained);
  - a partial fill gives `partial` (retained);
  - a verified cancel with zero fill releases;
  - an explicit 4xx and a pre-send halt release;
  - a fill that races the cancel gives `filled`.
- Consumption without a claim is refused. Terminal claims are immutable.
  Existing feasible paper admissions still open, and both reservations
  still end `CONSUMED`.

## Rollout and rollback

- **Rollout.** Dev only. An additive table and triggers are created by
  `init_shared_fno_risk_db`, and the `place_order` field is additive. Then
  local commit, GitHub promotion, and paper observation of claims. Watch
  for `UNRESOLVED` claims after any live entry.
- **Rollback.** Revert the module, executor and orchestrator changes. The
  dispatch table is preserved as evidence. Reverting must not convert
  `UNRESOLVED` claims into free capacity, so an operator must reconcile them
  first.

## Implementation result (Dev only; not pushed, not deployed)

Implemented as contracted.

**`fno_shared_risk.py`**
- New `fno_entry_dispatches` table with a transition-guard trigger (no
  change after `FILLED`/`RELEASED`, no return to `DISPATCHING`, no identity
  change) and a no-delete trigger. Both are created by
  `init_shared_fno_risk_db`.
- New functions: `claim_shared_fno_entry_dispatch`,
  `resolve_shared_fno_entry_dispatch` (an unverifiable release is applied as
  `unknown`) and `reconcile_shared_fno_entry_dispatch`.
- `consume_shared_fno_risk_reservation_in_transaction` now requires and
  completes the claim. The generic `resolve_shared_fno_risk_reservation`
  refuses claimed reservations.
- `SharedFnoRiskView.unresolved_entry_dispatch_count` is added, and the
  dispatch table is a required table of the view.

**`kite_client.py`.** Additive `dispatch_certainty` on every `place_order`
return.

**`fno_executor.py`**
- After a non-`COMPLETE` wait, it cancels, keeps any cancel error, and
  re-reads the final order state up to 3 times.
- New outcomes: `zero_fill_verified`, `partial`, `rejected`, `no_dispatch`,
  `unknown`, plus `filled` when an order fills during the cancel. Each comes
  with `evidence`.
- `_place_limit` exceptions are `AMBIGUOUS`. Paper behaviour is unchanged.

**`fno_orchestrator.py` and `fno_dr_book.py`.** Reserve → claim → act →
resolve. A paper insert failure resolves as `no_dispatch`; a live fill whose
insert fails resolves as `filled_unrecorded`. Retained outcomes log
`fno_entry_outcome_unresolved` at critical level.

Existing R1 tests now claim before inserting, as real callers must.

### Verification (Dev runtime, Windows, from `python-engine`)

| Command | Result |
| --- | --- |
| `-m pytest tests/test_fno_r2_dispatch_ownership.py -q -W error` | **37 passed** |
| `-m pytest tests/test_fno_r1_fee_exposure.py -q -W error` | **11 passed** |
| All `tests/test_fno*.py` plus `test_kite*`, atomic-settlement, performance, broker-reconciliation, mark-to-market and halt/owner-halt/order-execution | **666 passed, 1 skipped, 1 failed** |
| Penny executor/exit/journal/main-integration and momentum-paper order paths | **118 passed** |

The single failure in the large selection is the pre-existing, unrelated
`test_mark_to_market.py::TestFnoDrMark::test_actual_dr_writer_row_is_explicitly_unsupported`,
recorded in R1 (stale `PlannedStructure` call).

The R2 tests cover:
- **One owner.** Four concurrent identical claims produce exactly one grant.
  An orchestrator tick repeated at the same signal bar after an ambiguous
  result calls the executor **once** and leaves the claim `UNRESOLVED` with
  its reservation retained.
- **Halted retry.** A `RESERVED` retry after a same-day −₹3,100 loss is
  denied at the claim and released as `policy_denied_before_dispatch`, with
  no claim row.
- **Restart.** An orphaned `DISPATCHING` claim cannot be re-claimed, cannot
  be released by the generic resolver, and is refused reconciliation without
  an operator, with matching orders, or with a naive timestamp. It is
  released only with verified `no_order_verified` evidence.
- **Release rules.** Only a broker-rejected, not-sent or verified zero-fill
  outcome releases. A missing filled quantity, an `OPEN` final state, an
  ambiguous rejection or empty evidence is applied as `unknown` and
  retained.
- **Executor matrix.** A transport exception, cancel failure, unreadable
  history, `COMPLETE` without a price, or a cancel without a filled quantity
  each give `unknown`. A partial gives `partial`; a verified cancel or
  rejection with zero fill gives `zero_fill_verified`; a fill during the
  cancel gives `filled`.
- **Executor-to-release contract.** Real executor zero-fill evidence passes
  the release check, and partial evidence does not.
- **Broker client.** Accepted gives `ACCEPTED`; accepted without an id,
  HTTP 503 and read timeout give `AMBIGUOUS`; HTTP 400 gives
  `BROKER_REJECTED`; a connect error, halt or validation refusal gives
  `NOT_SENT`, with no request sent.

Mutation check: disabling the claim's already-claimed guard fails the
concurrency and restart tests. The orchestrator test still holds because the
table's primary key independently refuses a second claim. The module was
restored.

### Remaining

- R3 (canonical cash events, observation clock, completed-trade loss
  streak).
- R4 (broker payload binding).
- R5 (transactional occupancy caps and post-wait clocks, including the
  one-DR-structure race).
- Multi-leg DR fee bound.
- F1.

Live entries keep their existing authority gates.

### Commit receipt

- **Implementation commit.** `54c500e` (`fix(fno): single dispatch owner and
  evidence-backed entry outcomes (F0-R2)`) on
  `codex/production-correction-hedge-p0`. It is Dev-local only: not pushed
  and not deployed. Production is unchanged at `044c016`.
- **Post-commit check.**
  - Regenerating the atlas produced no diff.
  - The guide, plan, checklist and review all link to this slice.
  - Re-running the R2, R1 and shared-risk tests from the committed tree,
    warnings-fatal, gave 61 passed.
- **Migrations.** An additive table and two triggers are created by the
  existing `init_shared_fno_risk_db`. There is no settings change.
