# F0-R3 — canonical cash events, observation clock and completed-trade streak (October 3, 2026)

Parent: [independent F0 review](2026-10-03-fno-f0-independent-review.md),
item R3. Builds on [R1](2026-10-03-fno-f0-r1-fee-inclusive-exposure.md) and
[R2](2026-10-03-fno-f0-r2-dispatch-ownership.md).

## Problem (from source)

1. **Partial cash is ignored.** `_read_view` and `_read_entry_policy` read
   only `TRADE_CLOSED`. A generic `TRADE_PARTIAL` cash event (written by
   `performance.record_partial_close` and supported by the auditor and replay
   adapters) is invisible to equity and to the day/week/month brakes.
2. **Future-dated cash can hide today's loss.** The buckets use
   `event_day >= today` with no upper bound. A future-dated positive row
   (for example "tomorrow" +₹10,000) offsets today's −₹3,100 and unlocks
   entry. Nothing rejects cash dated after the moment of observation.
3. **The loss streak counts cash rows, not trades.** Six partial exits of
   one trade count as six losses. Ordering is by row id, not by the cash
   clock.
4. **Unexpected cash is not checked.**
   - Other or unknown event types, duplicate `(origin_ref, generation)`
     rows and settled positions with no cash are not detected.
   - Manual ledger events have no defined meaning for F&O capacity. A
     positive manual deposit would silently become entry capacity, which
     contradicts the owner's "no top-ups" rule.

## Contract

1. **Canonical cash events (one shared reader for the view and the
   policy).** Allowed event types:
   - `TRADE_PARTIAL` and `TRADE_CLOSED` are realised trade cash. Each counts
     once, in both equity and the brakes.
   - `INITIAL` and `TRADE_OPENED` must carry zero P&L; otherwise the reader
     returns `unclassified_cash_event`.
   - Manual events (`MANUAL_DEPOSIT`, `MANUAL_WITHDRAWAL`,
     `MANUAL_ADJUSTMENT`) are conservative and asymmetric:
     - a negative amount reduces equity;
     - a positive amount is **not** capacity and is reported, because a
       top-up needs an explicit owner policy;
     - neither is trading P&L for the brakes.
   - Any other type: `unclassified_cash_event` (fail closed).
2. **Validation.** Every event must have:
   - a finite P&L;
   - a parseable, timezone-aware timestamp;
   - a timestamp no later than the **observation instant** `observed_at`;
   - no duplicate non-null `(origin_ref, settlement_generation)` pair.

   Each failure makes the view and policy unavailable (fail closed). Reason
   codes: `invalid_cash_event`, `future_cash_event`, `duplicate_cash_event`.

   `observed_at` defaults to the real wall clock (UTC) and can be injected.
   It is separate from the policy day `today_ist`, so a replay with a past
   `today_ist` is not confused with future cash.
3. **Buckets have an upper bound.**
   - Day: `event_day == today_ist`.
   - Week: `week_start <= event_day <= today_ist`.
   - Month: `month_start <= event_day <= today_ist`.
   - Days are taken from the IST calendar (midnight boundary exact).
4. **Completed-trade identity.**
   - Trade cash is grouped by `origin_ref`.
     - `fno_position:N` is complete only when that position is `CLOSED`.
     - `fno_dr_structure:N` is complete only when that structure is
       `CLOSED`.
     - Open or unresolved partial cash affects equity and the brakes, but
       not the streak.
     - Any other origin, or one pointing to a row that doesn't exist, is
       treated as one completed trade per origin and reported.
   - Legacy cash with no origin counts as one trade per row (the previous
     behaviour) and is reported as `legacy_unlinked_cash_events`. No lineage
     is guessed.
   - A trade's net is the sum of its cash, and its completion time is its
     latest cash timestamp. Trades are ordered by completion time, then by
     highest id.
   - The existing six-loss pause (any day up to latest loss day + 1) is
     derived from this completed-trade sequence.
5. **Missing settlement cash (fail closed: `missing_settlement_cash`).**
   - A `CLOSED` single-leg row with `settlement_generation = G >= 1` must
     have exactly the generations `1..G` under `fno_position:id` for its
     source.
   - A `CLOSED` DR row with `settlement_state='SETTLED'` must have exactly
     generation 1 under `fno_dr_structure:id`.
   - Legacy closed rows (generation 0, or DR rows not marked `SETTLED`) are
     counted in `legacy_unlinked_closed_positions`, never treated as
     corrupt. Archived Production evidence shows such rows (ids 1–29).
6. **Receipts.** `SharedFnoEntryPolicyDecision` adds `completed_loss_streak`,
   `observed_at` and `legacy_unlinked_cash_events`. `SharedFnoRiskView` adds
   `excluded_positive_manual_cash_rs` and `legacy_unlinked_closed_positions`.
   All additions have defaults.

**Out of scope:**
- the live directional `fno_risk.kill_switch_status` (a separate reader,
  noted);
- R4 (payload binding and cost provenance);
- R5.

Sizing, thresholds and exits are unchanged.

## Acceptance

- Both event types are counted once. A `TRADE_PARTIAL` loss of −₹3,100
  halts.
- The IST midnight boundary, week and month boundaries, an equal-timestamp
  tie, out-of-order ids and an injected `observed_at` each behave as
  specified.
- A future positive row cannot mask today's loss (fail closed). Duplicate
  cash, missing settled cash, unknown and nonzero-opening types each fail
  closed.
- A positive manual deposit adds no capacity; a negative withdrawal reduces
  equity.
- Six partials of one closed trade count as one loss, and do not pause.
  Six completed losses pause. Partial losses of a still-open trade count in
  day P&L but not in the streak.
- Legacy rows with generation 0 and no origin do not block, and are counted.
- Existing F0 tests still pass. Fixtures dated after the real clock inject
  `observed_at`.

## Pre-deployment check (Production read-only, once the stack is up)

Production's `python-engine` stack was found stopped at 2026-10-03 12:22
IST (exit 137 / 0). This task did not touch it. Before promoting R3, confirm
the following count is 0 on Production. If it is not 0, those rows are real
integrity gaps to reconcile, not a reason to weaken R3.

```sql
SELECT COUNT(*) FROM fno_positions p WHERE p.status='CLOSED' AND p.settlement_generation>=1
  AND (SELECT COUNT(*) FROM bankroll_ledger l WHERE l.source=p.source
       AND l.origin_ref='fno_position:'||p.id) <> p.settlement_generation;
```

Also list the F&O event types and confirm there are no naive or future
timestamps.

## Rollout and rollback

- **Rollout.** Dev only, read-path logic. There is no schema or settings
  change. Then local commit, the Production check above, and GitHub
  promotion.
- **Rollback.** Revert the reader. No data is changed.

## Implementation result (Dev only; not pushed, not deployed)

Implemented as contracted in `fno_shared_risk.py`. There is no schema or
settings change.

**New shared reader**
- `_read_cash_ledger` is used by both the view and the policy. It:
  - classifies event types;
  - excludes positive manual cash from equity and keeps negative manual
    cash;
  - rejects non-finite, naive, unparseable or future cash
    (`observed_at` defaults to the wall clock);
  - rejects duplicate exact `(origin, generation ≥ 1)` cash.
- `_settlement_cash_gap` requires generations `1..G` for `CLOSED`
  single-leg rows with `G ≥ 1`, and exactly generation 1 for `SETTLED` DR
  structures. It counts legacy closed rows instead of rejecting them.
- `_completed_trades` groups cash by origin and skips trades still open. It
  treats each legacy row with no origin as one trade, and orders trades by
  completion time, then id.

**Policy changes**
- Day, week and month buckets are bounded by the policy day.
- The six-loss pause uses completed trades only.

**Interface additions (all defaulted, additive)**
- `observed_at` on `shared_fno_risk_view`, `shared_fno_entry_policy`,
  `reserve_shared_fno_risk` and `claim_shared_fno_entry_dispatch`.
- Receipts: `completed_loss_streak`, `observed_at`,
  `legacy_unlinked_cash_events`, `excluded_positive_manual_cash_rs` and
  `legacy_unlinked_closed_positions`.

**Design correction made during implementation.** The ledger's unique index
covers only generation > 0, and archived Production evidence lists legacy
closed positions with missing or duplicate terminal cash. So the duplicate
and missing-cash rules apply only to exact generations (≥ 1); generation-0
rows are reported as legacy, never guessed or rejected.

**Test fixture updates**
- Fixtures dated after the real clock now inject `observed_at`.
- The R1 lifecycle fixture now settles with generation 1, as the real writer
  does.
- One shared-risk assertion uses the renamed reason `invalid_cash_event`
  (partial cash is now validated by the same reader).

### Verification (Dev runtime, Windows, from `python-engine`)

| Command | Result |
| --- | --- |
| `-m pytest tests/test_fno_r3_cash_clock_completion.py -q -W error` | **20 passed** |
| All `tests/test_fno*.py` plus atomic-settlement | **437 passed** |
| F&O, Kite, settlement, performance, broker reconciliation, mark-to-market, halt / owner-halt / order-execution, operator status, NIFTY commands and daily decision quality | **727 passed, 1 skipped, 1 failed** |

The one failure is the pre-existing, unrelated
`TestFnoDrMark::test_actual_dr_writer_row_is_explicitly_unsupported`
(recorded in R1).

**Defect proof.** A real-clock probe ran the pre-R3 `HEAD` module and the R3
module on identical databases:

| Scenario | Before (pre-R3) | After (R3) |
| --- | --- | --- |
| `TRADE_PARTIAL` −₹3,100 today | entry allowed | `daily_loss_halt pnl=-3100` |
| Today −₹3,100 plus tomorrow +₹10,000 | entry allowed | `future_cash_event` |
| Six partial losses of one closed trade | falsely paused (`streak=6`) | allowed (streak 1) |

Covered by tests:
- the IST midnight boundary (18:29:59Z and 18:30:00Z);
- ISO-week and month boundaries;
- out-of-order ids (the cash clock decides);
- equal timestamps (id breaks the tie);
- completed trades after the policy day;
- an open trade's partials (in day P&L, not in the streak);
- missing settled cash for single-leg and DR;
- legacy closed rows that do not block;
- manual deposits and withdrawals;
- unknown and nonzero opening event types;
- a naive observation clock;
- the reader's duplicate guard with the ledger index dropped (the index
  itself already refuses the write).

### Remaining

- Run the Production pre-deployment check above once the stack is running
  again. It was stopped at 12:22 IST and was not touched by this task.
- R4 (broker payload binding and cost provenance).
- R5.
- The live `fno_risk.kill_switch_status` still reads `TRADE_CLOSED` only.
  It is a separate live-path reader and a candidate follow-up.
- Multi-leg DR fee bound.
- F1.
