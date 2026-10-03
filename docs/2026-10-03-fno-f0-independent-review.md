# Independent F0 review and correction plan — October 3, 2026 (IST)

## Verdict and scope

Reviewed Dev `2b106f7`, including F0-A–E (`7b86d85`, `0ba2d29`,
`bc666fe`, `7b77341`, `a9fef57`). The shared paper policy and atomic
reservation-to-position writes are useful implemented work, but **F0 source
acceptance remains open**. Passing the existing tests does not close the
fee, retry, concurrency and evidence contracts below. This review supersedes
the earlier F0 source-complete receipt, without discarding those commits.

Dev was clean at review start. Its cached upstream reference was six commits
behind HEAD; no fetch/push was performed, so this is not a fresh remote audit.
Production checkout and the engine's declared release remain `044c016`; the
running engine does not contain `/app/fno_shared_risk.py`. Production was
inspected read-only. No Production configuration, schema, service, broker or
message action is part of this task. B1/B2 implementation has not started.

## Before-edit slice: two bounded corrections only

Problem: a successful zero-fill operator recovery retains its entry premium
as context, but the shared validator rejects any non-null entry field on a
zero-fill receipt. Also, the two documented read-only shared helpers use a
normal SQLite connection and create an empty database if the path is absent.

Files/contracts: `fno_shared_risk.py`, `tests/test_fno_shared_risk.py` and
`tests/test_fno_exit_recovery.py`. Permit finite positive entry context on a
zero-fill receipt while still requiring no fill price, gross, fees, P&L or
ledger ID, unchanged generation and full remaining quantity. Open shared
readers with a properly encoded SQLite `mode=ro` URI; do not change mutating
reservation/schema initializers. These corrections grant no new capacity
from a fill or from a missing database.

Acceptance: use the real mocked-broker recovery writer to prove zero fill
retains all exposure and books no cash; both shared readers deny a missing
path without creating it, including a filename containing URI metacharacters;
the existing admission, recovery, DR and orchestrator tests continue to pass.
Rollout: Dev-only source/test/docs commit; regenerate atlas and immediately
check documentation consistency. No schema/configuration migration. Rollback
reverts these reader changes, preserving all settlement evidence. The larger
items below remain planned, rather than being patched during this review.

## Reproduced findings and ordered implementation slices

### F0-R1 — preserve fees throughout open and unresolved exposure (P1)

`fno_shared_risk._read_view` sums only position `max_loss_rupees`/
`max_loss_rs` once a reservation is consumed. Both admissions reserve loss
plus fees, but consumption removes the fee portion from the risk view.
On a fresh isolated DB, reserve a 75-unit long at premium 100 with loss 7,500
and `calc_fno_costs(100, 0, 75)=50.57826385`. With pool
7,551.57826385, reported capacity is 1 before insertion and 51.57826385
after `insert_position_with_risk_reservation`. A second reservation for
50.57826385 is accepted, although joint loss plus charges exceeds the pool.

Files: `fno_shared_risk.py`, `fno_positions.py`, `fno_dr_book.py` and their
admission/settlement tests. Retain versioned fee-inclusive exposure bound to
the consumed position receipt; use frozen economics and actual filled
quantity. Count it once across RESERVED → OPEN/UNRESOLVED → partial → CLOSED,
including fees already realised and those still payable. Reconcile legacy
positions explicitly; an unavailable fee/economics binding is not zero fees.
Acceptance: both books preserve total exposure across consumption, same-time
competing admissions cannot spend the fee reserve, partial/final exits release
only verified amounts, and feasible clean trades remain reachable. Do not
change sizing or add arbitrary strategy thresholds.

### F0-R2 — one dispatch owner and durable ambiguous-entry recovery (P1)

`reserve_shared_fno_risk` returns allowed/`already_reserved` for an identical
RESERVED key before consulting the current entry policy. After reserving
1,000, insert a same-day -3,100 cash event into a 50,000 pool: repeating the
key remains allowed despite the daily halt. `_try_entry_for_leg` interprets
any allowed result as permission to call the executor again. Atomic insertion
protects the position row, but does not serialize external dispatch.

Source inspection also finds that every non-paper/non-filled executor result
releases the reservation. The live executor reports `timeout` after a quiet
cancel, without proving terminal zero fill; cancellation errors are swallowed.
Thus an ambiguous/partial/live fill can lose its reserved exposure. This is
a source-level failure path, not a claim that a live incident occurred.

Files: `fno_shared_risk.py`, `fno_orchestrator.py`, `fno_executor.py`, durable
entry receipt/recovery adapters and tests. Separate an idempotent read receipt
from a one-time execution claim; persist request/order identity and outcomes.
Recheck policy before any genuinely new dispatch. Existing RESERVED/UNKNOWN
requests cannot dispatch again or expire by timer. Release only on a durable
no-dispatch result or independently verified terminal zero fill; partial or
unknown outcomes retain their full unverified exposure pending reconciliation.
Acceptance: a barrier test with two identical callers executes once; loss-halt
retry denies a fresh dispatch; restart, transport error, rejected/partial/late
fill and cancel failure preserve evidence and never imply free cash. Keep live
entries gated by their existing authority and F1; do not create live spreads.

### F0-R3 — authoritative cash types, clock and trade completion (P1)

Both view/policy readers filter only `TRADE_CLOSED`. An exact
`TRADE_PARTIAL=-3,100` in a 50,000 FNO_PAPER pool yields day P&L 0,
equity 50,000 and permission to enter. Current F&O recovery emits partial
cash as `TRADE_CLOSED`, so that actual path is counted; the generic partial
ledger contract supported by the auditor and replay adapter is not counted.
The current test called "DR and partial cash" inserts only TRADE_CLOSED.

The policy also uses `event_day >= today_ist` without an upper observation
bound. Today's -3,100 plus tomorrow's +10,000 yields day P&L +6,900 and an
allowed admission. An invalid future cash row must not mask today's brake.
Consecutive losses currently count settlement rows, including partials,
rather than completed trades, with no terminal-position identity binding.

Files: `fno_shared_risk.py`, `fno_positions.py`, `fno_dr_book.py`, shared
settlement/audit adapters and tests. Define canonical per-source cash events,
exact origin/generation uniqueness and an explicit aware observation clock.
Count partial and terminal cash once; reject future/malformed cash, retain
honest unavailable legacy lineage, and derive the existing six-loss policy
from completed trade outcomes rather than treating six scale-outs as six
loss-making trades. Acceptance covers both event types, IST midnight,
week/month boundaries, duplicate/missing cash, out-of-order/equal clocks,
future positive masking and six partials versus six completed losses.

### F0-R4 — bind broker payload contents and entry economics (P1)

`_recovery_evidence_is_intact` accepts any dict with a matching digest,
including `{}`. `_validate_open_partial_exit_evidence` checks stored scalar
arithmetic but does not compare the payload's order/trades/net position to
the receipt's symbol/account/order, quantities or weighted fill price.
Both new partial-integrity fixtures deliberately use `{}` as accepted proof.
An isolated corruption-injection probe on a genuine partial recovery also
remained available after replacing its payload/digest with `{}`. That probe
dropped the UPDATE trigger only in its temporary DB; it demonstrates missing
semantic validation, not a way to bypass an intact Production trigger.

Files: `fno_shared_risk.py`, `fno_exit_recovery.py`, `fno_positions.py` and
tests. Extract reusable pure validation from the real broker verifier and
re-derive account/symbol/order/terminal state, filled/residual quantities and
weighted execution price from the retained canonical packet. Bind immutable
entry economics to the position; freeze charge provenance for the receipt
rather than trusting any nonnegative cost scalar. Do not call the broker from
the risk reader or reprice old fees with current settings. Acceptance: real
writer output passes; empty/wrong payload, internally consistent wrong price,
cash or costs, changed entry premium, duplicate trade/order identities and
unavailable legacy evidence fail closed. Hash integrity is not authenticity.

### F0-R5 — admission occupancy and final dispatch clocks (P1)

With a barrier forcing two `maybe_open_dr_structure` calls to both read a
flat book, real planning/reservation/insertion at clocks one second apart
creates two OPEN structures (IDs 1 and 2). The existing one-structure cap is
outside the reservation/insert transaction; distinct timestamp keys do not
enforce occupancy. Directional position/premium/daily/no-pyramid checks are
also read before the atomic reservation and should be characterized for races.

New schema/policy/reservation DB waits occur after the directional final
action-clock recheck, and the DR path similarly retains its pre-wait action
time. There is no final freshness/cutoff validation after these new waits.
This clock issue is source inspection; no wall-clock incident was inferred.

Files: `fno_shared_risk.py`, both position writers, `fno_orchestrator.py` and
`fno_dr_book.py`. Apply existing occupancy/premium/count/no-pyramid rules to
OPEN/UNRESOLVED plus in-flight claims in the final atomic admission, without
inventing a new cross-book count policy. After bounded DB waits, recheck the
real dated entry deadline and quote freshness immediately before dispatch;
safe pre-dispatch denial needs an auditable claim resolution. Acceptance:
barrier/restart tests never exceed existing caps; delay fixtures crossing the
cutoff or freshness window cannot enter; exits still run during entry halts.

## Rollout, rollback and B1/B2 dependency

Implement R1/R2 first, then R3/R4/R5 in separately reviewable Dev slices with
negative, concurrent and restart tests. Version/add schema only where needed;
review legacy-data compatibility on copies. Immediately update the guide,
plan and atlas per implementation commit. Promote through GitHub, then
observe real paper admissions, fee/cash conservation and unresolved recovery.
Never turn on live spreads, borrow/top up funds, rewrite cash history or use
test passes as profitability/partner qualification.

Rollback must preserve positions, ledger, reservation and recovery receipts.
An emergency entry-disable is separate from exit authority; reverting a
safety validator must not silently treat unknown old receipts as capacity.
F1 broker cash/margin/legging semantics remain independently open.

B1 immutable interval/clock/session/zero-volume data contracts and B2 exact
classic Penny lifecycle remain the next requested phase. Offline B1 design
can be independent, but F0 must not be declared accepted by passing research
tests or by beginning B1/B2. Reuse shipped functions and preserve all no-trade
and unavailable reports.

## Verification receipt

Runtime: Dev `python-engine/winvenv/Scripts/python.exe`, Windows PowerShell.
From Dev `python-engine`:

```powershell
.\winvenv\Scripts\python.exe -m pytest tests/test_fno_shared_risk.py tests/test_fno_risk_switches.py tests/test_fno_exit_recovery.py tests/test_fno_exit_recovery_boundary.py tests/test_fno_dr_book.py tests/test_fno_orchestrator.py -q
```

Baseline: **111 passed, one existing Starlette async-generator lifespan
deprecation, 11.31 seconds, normal exit**. Separate stdlib/temp-DB probes used
the actual reservation/view/insertion functions, real recovery writer with
mocked broker and existing DR planning fixture. They reproduced fee release,
TRADE_PARTIAL omission, halt-bypassing retry, future cash masking, zero-fill
false unavailability, missing-file creation, unbound payload acceptance and
the two-admission DR race. All temporary DBs were removed on exit; no provider
request/order/message/Production DB access occurred in these probes.

Bounded reader correction verification:

```powershell
.\winvenv\Scripts\python.exe -m pytest tests/test_fno_shared_risk.py tests/test_fno_exit_recovery.py -q -W error -k 'shared_readers or verified_zero_fill'
```

**3 passed, 34 deselected, no warnings, 0.77 seconds, normal exit.** The full
six-file command above then reported **114 passed, one existing Starlette
lifespan deprecation, 11.47 seconds, normal exit**, including the previously
excluded route and clock-precision tests. No broad warnings-clean claim is made.
Compilation of the changed module and two test files passed; atlas regeneration
indexes 229 Python modules and changes only the shared-risk declaration offsets;
`git diff --check` passed. No schema/configuration migration is needed for these
two reader fixes. R1–R5 remain planned, not implemented by this review.
Implementation commit: `a3f082f` (`fix(fno): correct risk readers and reopen F0
acceptance`), Dev-local only. Immediately after that commit, the working tree
was clean, changed-source AST declarations matched the generated atlas, all
five handover/plan documents linked to this review, and its R1–R5/status/test
receipt consistency checks passed. No push or Production deployment occurred.
This subsequent documentation receipt records that verified implementation
identity; it makes no additional source or schema change.
