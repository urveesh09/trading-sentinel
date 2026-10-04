# October 3 post-implementation independent review

## Scope and evidence

Review baseline: Dev `4481af0`, following the original October 3 safety/backtest
plan and the independent F0 R1-R5 review. This receipt supersedes blanket
"B0-B6 complete" claims in earlier receipts; it preserves their actual work.
The owner authorizes small corrections now and a plan for larger changes.
Only Dev may change. No push, promotion, orders, messages or restart is in scope.

Read the system guide, atlas, active plan, checklist, successor inheritance,
original safety/backtest plan and new implementation slices. Compared source,
commit history, contracts and tests, rather than treating commit titles as acceptance.

Baseline verification: the 18-file F&O/data/Penny/Lab/engine/Momentum selection
passed **422 tests** (39.15s; existing Starlette/HTTPX deprecations). Gateway
`node node_modules/jest/bin/jest.js tests/unit/executor.test.js --runInBand`
passed **58 tests**. These are engineering checks, not profitability evidence.
Read-only Production check: checkout `044c016`; `docker ps` found no running
containers and the release-identity read failed because the engine is stopped.
After the owner's power-cut/resume message, containers were observed running
(engine/gateway/agent healthy). A read-only
`docker exec python-engine python -B -c "import json; from release_identity import release_identity; print(json.dumps(release_identity()))"`
returned declared revision `044c016584118fd5c5b515fc6d03909dbcaa8c4b`, build
`2026-10-02T18:36:36Z`. This confirms the older Production engine identity,
not deployment/operational acceptance of the reviewed Dev changes. No new CNC
dataset was collected; the earlier stopped-container limitation has cleared.

## Correction slice recorded before implementation

**Problem/contracts/files.**

1. `fno_shared_risk.reconcile_shared_fno_entry_dispatch` accepts zero-fill proof
   for an unrelated order even when the unresolved claim already records an
   order ID. A temporary-DB probe released KNOWN using UNRELATED. Bind proof
   to the existing order inside the transaction; a known order cannot be cleared
   using an empty order-search list. Include UNRESOLVED single-leg positions in
   the existing concurrency/no-pyramid/premium occupancy checks.
2. `KiteClient.orders_snapshot` converts missing/non-list broker data to `[]`.
   Preserve unavailable evidence as `None`, including invalid JSON/envelopes,
   so own-cash admission and retry recovery cannot infer an empty book.
3. `backtest_reporting` labels a date-only declaration DECLARED_UNTOUCHED.
   Use DECLARED_UNVERIFIED and an explicit explanation, including read-only
   clarification of legacy labels through `backtest_cli report`. Its winner exclusion
   drops the smallest loss in an all-loss sample ([-2,-1] became -2); subtract
   only positive winners. Derived metrics must not silently summarize incomplete
   closed-trade fields, and absent trade evidence must not become zero trades.
   Expose field coverage and null unsupported aggregates.
4. The first resumed regression returned 293 passed/1 failed in
   `test_recovered_intent_requires_new_exit_evaluation`: it assumes a fresh
   wall-clock read is strictly later than recovery. Make its stale/equal/new
   evaluation timestamps explicit relative to the persisted recovery receipt;
   preserve the runtime's strict later-than requirement, without a sleep or
   weaker assertion. File: `tests/test_fno_exit_recovery.py`.

**Acceptance.** Wrong-order/no-order reconciliation retains capital; matching
terminal zero-fill proof releases it; unresolved positions enforce all three
occupancy limits. Malformed order responses block entry without any POST;
successful empty books remain usable and exits remain exempt. Reports distinguish
missing/empty/partial data, preserve all-loss totals and never certify untouched
holdouts. Run affected F0, broker, reporting/CLI and shipped-adapter regressions;
regenerate the atlas and verify documentation/diff consistency.

**Rollout/rollback.** Local Dev commit only. No schema/configuration/threshold
change, no historical artifact rewrite. New holdout declarations have a corrected
status and new reports add coverage metadata; archived reports remain unchanged.
Revert the correction commit through normal Git if necessary; do not release
retained unresolved exposure to make an entry succeed. GitHub promotion remains
separate. Record final commands/results and commit identity below.

## Status against the original plan

| Slice | Verified delivery | Still required |
| --- | --- | --- |
| F0 R1-R5 | Fee exposure, one dispatch owner, cash/completion clocks, payload binding, atomic occupancy and final clocks are implemented (`d4fd298` through `6d41192`), with passing regressions. | The bounded corrections above; later broker/operator reconciliation provenance and paper operational acceptance. |
| F1 | `333b9c1` adds own-cash notional checks at Python/gateway boundaries. | Account-wide atomic reservations, assigned book budgets, charge/contingency coverage and catastrophe acceptance. F1-A snapshot checks alone do not prove no leverage. |
| B0 | `82976d4` catalogue, offline snapshot/run/coverage/report/compare CLI. | Freeze all transitive strategy dependencies and effective assumptions; publish artifacts without an overwrite race. |
| B1 | `9a18445` validates explicit bar intervals, clocks, OHLCV, calendar coverage and unavailable/partial sessions. | Point-in-time membership/listings/delistings, verified corporate actions/adjustment and calendar/provider provenance. Unknown cached adjustment is honestly declared, not validated history. |
| B2 | `9a18445` MIS and `60a5b3e` CNC paper lifecycle adapters bind shipped decisions/tracker behavior under declared assumptions. | Historical scanner/regime/sector/event/universe and joint MIS/CNC allocation before FULL_PORTFOLIO claims; CNC real-data collection/run remains pending (Production has resumed). |
| B3 | `e349b0b` Swing/EDGE shipped daily evaluator adapters, separate proxy labels and RSI fix. | Exact fills, exits, fees, historical market context and portfolio lifecycle; current scope is EVALUATOR. |
| B4 | `3e03916` shipped Momentum baseline and explicit Range evaluator. | Exact manual/paper admission, reservations, correlated allocation and live partial-runner/trail exits. Range verdicts have no return-producing lifecycle. |
| B5 | Excluded in the current recorded owner plan. | Do not implement or claim completion; F&O/partner full replay remains unavailable outside this scope. |
| B6 | `60bd989` evidence-based reports, compatible date/scope/snapshot checks and deterministic IID trade bootstrap. | Prospective locked holdout protocol, reuse/selection audit, complete manifests/comparability, reconciled marked equity and session-block uncertainty. Dates alone prove neither predeclaration nor untouched data. |

The bounded implementation slices have useful acceptance evidence. The full
original safety and full-system backtest plan is **not finished**.

## Larger follow-up plan, in order

### P1 — F1-B common account cash admission (required before live acceptance)

**Problem.** An offline mock of `_own_cash_refusal` admitted two concurrent
700 entries against the same 1,000 cash snapshot. Python and gateway have no
common durable account reservation around snapshot/read/send. This is a source
contract failure, not a live trade or an observed broker balance.

**Contracts/files.** `kite_client.py`, gateway `executor.js`, shared durable
account admission service/store and reconciliation, plus book allocators.
One account identity and own-cash basis; atomically reserve pending and ambiguous
dispatches across both callers, retain them through restart, consume against
verified fills and release only verified zero exposure. Include bounded charges
and contingency; assigned division/book limits must prevent cross-division
funding. Avoid double-subtracting broker-reported commitments.

**Acceptance.** Simultaneous Python/gateway entries whose sum exceeds available
own cash cannot both dispatch; stale snapshots, unknown orders, restart and
partial fills retain commitments; insufficient charges/budget deny entry;
exits remain operational during halts. Resolve the existing Penny 2,500-vs-2,000,
Swing/Momentum allocation and EDGE cap decisions. Complete the original F1
premium-zero/gap/outage/expiry/correlation and broker-disagreement matrix.

**Rollout/rollback.** New explicit plan and additive migration/compatibility
review, isolated mocks first, paper observation then owner-controlled GitHub
promotion. No live spreads or new funding authority from this review. Rollback
must preserve unresolved reservations and keep entry closed if evidence is lost.

### P2 — B0/B1 reproducibility and point-in-time evidence

**Contracts/files.** `backtest_cli.py`, `research_data_contracts.py`, catalogue
and adapter input manifests. Bind every transitive shipped strategy/risk/exit/
cost dependency, effective settings and overrides, data/corporate-action/calendar/
universe versions. Publish reports/snapshots with exclusive, atomic creation:
`exists()` followed by `write_text()` currently permits overwrite races.

**Acceptance.** A dependency or universe/context change invalidates compatibility;
missing evidence yields PARTIAL/UNAVAILABLE; concurrent writers never overwrite
archived bytes; explicit hypothesis differences are shown during comparison.
Keep old manifests readable with a declared version and weaker evidence scope.
Rollback new collection/adapters without rewriting existing snapshots.

### P3 — B2/B3/B4 remaining lifecycle and portfolio parity

**Contracts/files.** Penny lifecycle modules, daily replay helpers, Momentum
replay, Range dispatcher, runtime admission/position trackers and Lab adapters.
Extract/reuse pure shipped kernels and archive actual prior-known contexts;
do not substitute current news, invented historical decisions or neutral
context. Model shared cash, fees, fills, partial exits, illiquidity/gaps and
simultaneous admissions. Preserve evaluator adapters as useful diagnostics.

**Acceptance.** Differential entry/admission/exit/cash fixtures against runtime,
no future bar/context access, joint portfolio reconciliation and declared
unavailable dates. Fetch CNC evidence only via read-only collection once
Production is available; restore decisions/restart belong to the operator.
Penny kill-switch wiring, minute capture through 15:00, CNC live exit management
and partial-day volume semantics require separate runtime slices; no silent
research policy change. Rollback adapters without deleting baseline runs.

### P4 — B6 held-out qualification and uncertainty

**Contracts/files.** Reporting/CLI plus a versioned hypothesis/holdout registry.
Lock policy, transitive code, settings, universe, data and development window
before test observation; record creation time and prior use. A held-out run
references the frozen protocol and records evaluation/reuse/selection history.
Enforce comparability while explicitly exposing allowed hypothesis differences.
Provide session-block uncertainty and marked shared-capital drawdown only
where supported; otherwise null with coverage reasons.

**Acceptance.** Reject retroactive freezes, reused holdouts represented as
untouched, post-freeze policy changes and mismatched context/universe; test
correlated sessions, partial metrics and exact cash accounting. Keep IID
bootstrap labelled as descriptive. Rollback tooling without rewriting the
registry or claiming old date declarations were untouched evidence.

## Final verification receipt

Correction regression (Dev `python-engine`, after the power-cut restart):

```powershell
.\winvenv\Scripts\python.exe -m pytest tests/test_fno_shared_risk.py tests/test_fno_r1_fee_exposure.py tests/test_fno_r2_dispatch_ownership.py tests/test_fno_r3_cash_clock_completion.py tests/test_fno_r4_payload_binding.py tests/test_fno_r5_occupancy_clocks.py tests/test_fno_exit_recovery.py tests/test_fno_exit_recovery_boundary.py tests/test_fno_dr_book.py tests/test_fno_orchestrator.py tests/test_f1a_own_cash.py tests/test_kite_client_methods.py tests/test_backtest_reporting.py tests/test_backtest_cli.py tests/test_backtest_lab.py tests/test_momentum_replay.py -q
```

**294 passed, 2 existing Starlette/HTTPX warnings, 35.96s.** The earlier
293-pass/1-failure result is retained above; the deterministic strict recovery
clock fixture corrected its real-time assumption. The pre-cut test process
was lost and is not counted as completed verification.

`python-engine/winvenv/Scripts/python.exe scripts/build_system_code_atlas.py`
indexed 237 Python modules. `py_compile` passed for corrected source/report
tests; `git diff --check` passed. Review links, active-doc pointers and atlas
declarations were checked against current source. Baseline 422 Python and 58
gateway checks are separate from this final affected-selection result.
No configuration, schema migration, archived-run rewrite or strategy-threshold
change. Production is running the older declared `044c016` engine and untouched
by this review. Changes remain Dev-local, not pushed or deployed.
Source/correction commit: **`284bb4a`** on
`codex/production-correction-hedge-p0`, Dev-local. Immediately after commit,
verified guide/plan/checklist/review pointers and recorded test/environment
results, regenerated the atlas with identical bytes and confirmed a clean
worktree. This documentation-only receipt follows that verified source commit.
No remaining work in the authorized review/correction slice; P1-P4 and the
separate operational acceptance above remain open in the original plan.
