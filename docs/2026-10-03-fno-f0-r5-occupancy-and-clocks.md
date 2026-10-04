# F0-R5 — transactional occupancy caps and post-admission clocks (October 3, 2026)

Parent: [independent F0 review](2026-10-03-fno-f0-independent-review.md),
item R5. Builds on R1–R4 (the R2 dispatch claim is the single last step
before any dispatch).

## Problem (from source)

1. **DR occupancy race.** `maybe_open_dr_structure` enforces "one structure
   at a time" with `open_structures()` *before* reserving. Its reservation
   key contains the call's timestamp, so two callers that both read a flat
   book get distinct keys, reserve, claim and insert. The review reproduced
   two `OPEN` structures (ids 1 and 2).
2. **Single-leg caps are checked too early.** The directional caps are read
   before the reservation and claim, outside any transaction:
   - `concurrency` (`FNO_MAX_CONCURRENT`, default 2);
   - `trades_per_day` (`FNO_MAX_TRADES_PER_DAY`, default 3);
   - the marginal open-premium cap (`FNO_MAX_OPEN_PREMIUM_PCT × pool`);
   - no-pyramid (`already_holding_this_contract`).

   Two different signals that are in flight at once can each pass them.
3. **Stale clocks.** The schema, policy, reservation and claim DB waits
   happen *after* the directional final action-clock recheck, and DR keeps
   its pre-wait action time. An entry delayed across the cutoff, or past
   quote or chain freshness, can still be dispatched.

## Contract

1. **Occupancy is enforced at the claim.**
   - `claim_shared_fno_entry_dispatch` accepts an optional
     `EntryOccupancy`. Inside its `BEGIN IMMEDIATE` transaction it applies
     the **existing** limits only, with no new cross-book policy. The
     counts include in-flight claims (`DISPATCHING`/`UNRESOLVED`, excluding
     its own key) as well as positions.
   - Single-leg:
     - `OPEN` positions plus in-flight claims must be below `max_open`;
     - positions entered today plus in-flight claims for today must be below
       `max_trades_per_day`;
     - open premium plus in-flight planned premium plus this entry must not
       exceed `max_open_premium_rs`;
     - with `no_pyramid`, no open position or in-flight claim may hold the
       same contract.
   - DR: `OPEN`/`UNRESOLVED` structures plus in-flight DR claims must be
     below `max_open` (1).
   - A refused claim releases its never-sent reservation as
     `occupancy_denied_before_dispatch:<reason>`. An in-flight claim with an
     unknown planned premium makes the premium check fail closed.
   - Claims record `tradingsymbol`, `planned_premium_rs` and `entry_day`
     (additive columns, immutable under the claim trigger).
2. **Post-admission clock.** After the claim is granted, the last database
   wait before dispatch, live callers (those with an `action_clock`)
   re-read the real clock and re-check:
   - directional: the entry window, contract quote freshness and chain
     freshness;
   - DR: the entry window, chain freshness and every leg's quote freshness.

   A failure resolves the claim as `no_dispatch` (`NOT_SENT`, with the
   reason in the evidence), so the reservation is released auditably and
   nothing is dispatched. Replay callers keep their supplied clock, as
   before.
3. **Unchanged:** exits and management (still allowed during entry halts),
   sizing, thresholds and signals. The existing pre-reservation gate checks
   stay as cheap early filters; the claim is the authority.

## Acceptance

- Two concurrent DR openings that both read a flat book produce exactly one
  `OPEN` structure. The loser's reservation is released and its claim is
  never written.
- Single-leg claims are refused at the existing caps when in-flight claims
  are counted: concurrency, trades/day, the premium cap with in-flight
  premium, no-pyramid against an in-flight claim of the same contract, and
  an orphaned `UNRESOLVED` claim after a restart. A non-conflicting entry is
  still granted.
- A delay across the cutoff, or past quote or chain freshness, after the
  claim means no dispatch: the executor is not called, and the claim is
  `RELEASED` as `no_dispatch` with its reason. This holds for both books.
- Existing feasible paper admissions still open. Exits still run while
  entries are halted.

## Rollout and rollback

- **Rollout.** Dev only. Additive claim columns, plus an `EntryOccupancy`
  argument that existing callers may omit. Then local commit and GitHub
  promotion.
- **Rollback.** Revert the occupancy check and the clock re-check. Claims
  and reservations are preserved.

## Implementation result (Dev only; not pushed, not deployed)

Implemented as contracted.

**`fno_shared_risk.py`**
- `EntryOccupancy` and `_occupancy_denial` re-apply the existing limits
  inside the claim's `BEGIN IMMEDIATE`, counting `OPEN` positions (DR:
  `OPEN`/`UNRESOLVED`) plus in-flight `DISPATCHING`/`UNRESOLVED` claims.
- A refused claim releases its never-sent reservation as
  `occupancy_denied_before_dispatch:<reason>`.
- Claims record `tradingsymbol`, `planned_premium_rs` and `entry_day`. These
  are additive columns, added in place to existing Dev tables and guarded by
  the claim trigger.

**`fno_orchestrator.py`**
- The single-leg claim passes `FNO_MAX_CONCURRENT`,
  `FNO_MAX_TRADES_PER_DAY`, `FNO_MAX_OPEN_PREMIUM_PCT × pool`, no-pyramid on
  the contract, and planned premium `ask × qty`.
- `post_admission_entry_reject` re-checks the entry window, quote freshness
  and chain freshness on the real clock after the claim. A failure resolves
  the claim as `no_dispatch` without calling the executor.

**`fno_dr_book.py`**
- The DR claim passes `max_open=1`.
- `dr_post_admission_reject` re-checks the entry window, chain freshness and
  every leg's quote freshness after the claim.

The earlier pre-reservation checks are kept as cheap early filters.

**Test fix.** The R4 helper that re-claims an exit intent now uses an
evaluation clock strictly after the latest recovery. On the coarse Windows
clock it was intermittently stamped at the same instant and refused by the
existing re-evaluation rule; it now passes 5 out of 5 runs.

### Verification (Dev runtime, Windows, from `python-engine`)

| Command | Result |
| --- | --- |
| `-m pytest tests/test_fno_r5_occupancy_clocks.py -q -W error` | **12 passed** |
| F&O, Kite, settlement, performance, reconciliation, mark-to-market, halt/order-execution, operator status, NIFTY commands, daily decision quality and scheduler (normal warnings) | **865 passed, 1 skipped, 1 failed** |
| R1–R4 + shared-risk + recovery + DR-book selection, `-W error`, identical files at R4 and at R5 source | **146 passed** both times |

The one failure in the large selection is the pre-existing, unrelated
`TestFnoDrMark::test_actual_dr_writer_row_is_explicitly_unsupported`.

**Harness finding (pre-existing, not R5).** Under `-W error`, any
pytest-asyncio test (including the earlier R1/R2 tests) followed by the
synchronous `asyncio.run` test
`test_fno_dr_book.py::test_live_dr_admission_rechecks_after_database_reads`
can raise an unclosed-socket `ResourceWarning`, depending on garbage
collection timing. It reproduces with the R5 source stashed (an R1 test plus
that DR test fails at baseline). It also passes in isolation and in normal
runs. Recorded as a test-harness follow-up: convert that test to
pytest-asyncio, or close the loop explicitly.

**Defect proof.**
- **DR race.** The review's scenario (two DR openings that both read a flat
  book) produces **2** `OPEN` structures with the R5 source stashed, and
  **1** with R5. The automated test shows the loser's reservation released
  with `dr_structure_occupied`.
- **Single-leg.** Tests show refusals at:
  - concurrency (one open position plus one in-flight claim);
  - no-pyramid against an in-flight claim of the same contract;
  - trades/day (two of today's entries plus one in-flight claim; yesterday
    excluded);
  - the premium cap with in-flight premium (2,501 refused, 2,500 granted);
  - an orphaned `UNRESOLVED` claim;
  - an in-flight claim with no premium evidence (fail closed).
- **Clocks.** Directional and DR delays across freshness or the cutoff
  after the claim release with `no_dispatch` and a recorded reason, and the
  executor is never called.

### F0 status after R5

R1–R5 are implemented in Dev. Still open:
- **Operational:** GitHub promotion; the R3 Production read-only check; paper
  observation of claims, reservations and recoveries.
- **F1:** owner cash-only funding semantics and the broker margin
  preflight, before any live funding.

### Commit receipt

- **Implementation commit.** `6d41192` (`fix(fno): enforce occupancy in the
  dispatch claim and re-check clocks (F0-R5)`) on
  `codex/production-correction-hedge-p0`. It is Dev-local only: not pushed
  and not deployed. Production is unchanged at `044c016`; its stack was
  found stopped at 12:22 IST and was not touched.
- **Post-commit check.**
  - Regenerating the atlas produced no diff.
  - The guide, plan, checklist, review and October 3 plan all link to this
    slice.
  - Re-running the R1–R5 and shared-risk tests from the committed tree,
    warnings-fatal, gave 111 passed.
- **Migrations.** Three additive claim columns, created by
  `init_shared_fno_risk_db`. There is no settings change.
