# Current-system retrospective test — October 3

## Authorized scope and frozen design, before replay

The owner requests testing first, then discussion of module improvements.
Use current Dev source `556209c` (P1-P4 changes), retained Production evidence
read-only, and all shipped money/research families. Do not tune thresholds,
alter entry/exit policy, purchase data, restart/promote services, place orders
or send messages. This request authorizes F&O research for this slice despite
the older B5 implementation exclusion; it does not authorize a new live path.

Dates: F&O September 17-October 1, 2026 inclusive, IST; stocks July 1-September
30, 2026 (Q3) inclusive. Missing July/minute evidence must remain unavailable.
These are retrospective exploratory windows, never untouched holdouts.

Universe: freeze Production's current `/data/penny_static.json` (100 names)
and `/app/data/nifty500.json` (500 names) before replay outcomes. This is
explicit current membership, not reconstructed historical membership. Include
NIFTY 50/NIFTY BANK/NIFTYBEES only as required market inputs. Record historical
signal funnels separately across the actual recorded universe: an accepted
signal is not a filled trade. Additional coverage-selected Penny minute names
may be a separately labelled diagnostic, never substituted into the primary.

## Files/contracts and execution

Inert Dev orchestration under `scripts/`; dated report and raw JSON under
`docs/research/2026-10-03-current-system/`. Local immutable snapshots may be
large and stay locally retained rather than committed. Use existing Lab/CLI,
B1 validation, Penny MIS/CNC/joint lifecycle, Swing/EDGE/Range evaluator and
MOM_BASE replay functions. Preserve their real costs/defaults and declared
regime/fill assumptions; state EVALUATOR/LIFECYCLE/PORTFOLIO_PARTIAL scope.
Freeze strategy/config/transitive source manifests before scoring.

Collect selected OHLCV rows and small relevant ledger/position tables inside
one read-only Production SQLite transaction; stream bytes to Dev, never copy
a live SQLite main file without its WAL or write a backup in Production.
Read/copy only the requested finalized quote journals/manifest bytes and the
past October 1 journal into Dev. Bind raw file and data hashes. No provider calls.

Resume environment: the engine is stopped. The initial live collector failed
before producing data. Read its stable database plus WAL/SHM and universe files
into Dev with `docker cp`, verify it remains stopped across the copy, and run
the same mode=ro transaction locally. Preserve the failed attempt; do not restart
Production. A standalone main-file copy of an active database is still forbidden.

F&O: attempt the registered current-policy runner and report its explicit
unavailable contract. Reuse current single-leg/DR exit kernels only where exact
stored entry identity and retained executable quotes support them. Otherwise
keep missing paths and legacy DR leg identities unavailable. Separately refresh
exactly linked recorded paper cash for the requested dates; never relabel that
as a fresh full-policy backtest or synthesize options from constant IV.

## Acceptance and report

Every module has an attempted run, scope, coverage, activity/reject funnel,
closed/unresolved/open counts and evidenced cash/cost/exits where supported.
Report missing sessions, warm-up/adjustment/context and shared-capital limits.
Penny diagnosis distinguishes lack of signals, strict gates, inactive scheduling,
unavailable data and cash/fill/exit constraints. Primary complete-session policy
is unchanged; predeclared allow-gaps sensitivity may illustrate the effect of
retained coverage, with unresolved exits retained and never counted as zero P&L.
No parameter search or “smartness” changes until the owner reviews this evidence.

Execution corrections: EDGE's SQLite transaction context does not close its
handle and prevents temporary-cache deletion on Windows. Correct only handle
cleanup in `penny_edge_live.py`, verify both return/exception paths and rerun
with a new manifest; retain the first failed run. F&O's full-day archive packet
contains pre-entry observations, which correctly fail exit-path validation.
Preserve that attempt and retry using only post-entry receipts (the declared
exit-path contract); do not remove gaps/stale prices or relax reconciliation.

The transitive manifests also bind EDGE in otherwise unrelated adapters.
Retain original runs, then rerun completed primary jobs with `-final` identities
after the cleanup correction so delivered current-source manifests agree.
Verify deterministic metrics against their originals; no numeric policy changes.

Momentum's requested quarter fails its existing provenance contract because
July/August 10 include legacy_unknown intervals. Keep that primary unavailable
run. Before any Momentum scoring, also declare a separate August 11-September
30 covered-window diagnostic (same MOM_BASE/default policy and fixed 500-name
universe), because verified 15minute labels begin August 11. Never represent
this shorter window as a complete quarter. Run the already declared Penny
allow-gaps sensitivity separately from complete-session results.
Also apply the same declared gap sensitivity to the existing joint Penny cash
adapter at its unchanged ₹2,000 default. This distinguishes lifecycle candidate
results from cash-lock/rejection effects; no new selection or sizing policy.

Verify snapshot integrity, source fingerprints, source-to-result scope and
recorded cash reconciliation. Run focused tests if orchestration introduces
new accounting/collection behavior. Archive all failures/unavailable attempts.

## Rollout, rollback and remaining work

Dev research only. Rollback removes inert orchestration without deleting raw
evidence/archived runs; no runtime schema or configuration migration. Update
guide/active plan/checklist and regenerate the atlas if source changes; record
commands, results, environment, commit identity and immediate consistency checks.
Deliver a comprehensive module comparison and a discussion agenda, not tuned
strategies or qualification. Production checkout/release is `044c016`, but the
engine is currently stopped; runtime observation is separate from Dev backtests.

## Findings requiring later work, not silently changed during testing

Momentum's existing virtual adapter settles missing intraday exits at a later
day's opening bar. Sixteen of this diagnostic's 18 closes follow that fallback;
the negative result is not an estimate of the live MIS exit policy. A later
slice must bind real partial-T1/trail/time exits, retain unavailable EOD as
unresolved and test gaps without invented settlement.

The partial Penny cash adapter sorts mixed-offset timestamp strings. Normalize
aware clocks to UTC before ledger ordering, retain conservative CNC date-only
release, and test ties/partial events before expanding its scope. Independent
UTC-normalized replay of both actual Penny cash streams agrees exactly on
admission, rejection, free/locked cash, unresolved count and realized P&L.
No changed ledger or strategy result is substituted into this study.

This task's real-data attempts are complete; full historical portfolio parity,
verified F&O input/exit evidence and prospective qualification remain open.
See [the results](2026-10-03-current-system-backtest-results.md).
