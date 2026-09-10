# Validation of 463608a and next implementation contract

Reviewed 6 September 2026, IST. Dev baseline: `463608a9626b82aa8bca31dfeb8a06f7b763ab9f`, `codex/production-correction-hedge-p0`.

## Verdict in plain language

The commit makes several real corrections, but it is **not yet a reliable replay/research engine**. Future rows are withheld at an earlier evaluation clock, normal account/run identities are separated, economic assumptions are stored, historical bar validation is stronger, and the returned cash is recomputed after committed results.

However, the same scenario can still produce different trades and profits depending on how often it is called. Resumed positions can also use different fees/slippage from those saved in the run. Pending setups do not expire reliably. Correct these before treating simulation results as evidence for a strategy.

This is a focused validation, not a new recommendation to abandon the larger product build. Finish the contract below, then continue the existing adapter, optional-AI, research comparison and integrated-demo milestones. This audit changed only documentation and offline probes, not application code or live behavior.

## Verification and evidence

- **97 selected Python tests passed**: proactive intelligence, partner fixtures/input, hedge advisory/routes, main surface characterization and scheduler closures. One existing Starlette lifespan deprecation warning.
- Frontend `npm run build` passed; existing Browserslist data-age warning. No actual browser visual verification in this audit.
- `git diff --check` passed for tracked changes.
- Reviewed the complete `1d41eb0..463608a` application diff and relevant existing simulation/persistence functions.
- Executed `docs/review-463608a/probe_run_contract.py` against temporary databases. Sanitized results are stored alongside it. No broker, Telegram or AI calls.
- Full gateway/agent suites, live market behavior and profitability were not revalidated. Production was not modified.

## Which reported changes are implemented?

| Claim | Finding |
|---|---|
| Future bars cannot affect an earlier clock | Implemented for the direct workflow's bar filtering. Probe confirms zero positions before future bars become visible. A separate historical-entry timing issue remains below. |
| Chronological replay | Wrapper validates increasing steps within one invocation and calls the workflow. It does not enforce an account/run watermark across invocations or guarantee equivalent economic results. |
| Account/named-run separation | Normal named scenarios are isolated by scoped IDs; existing regression passes. Legacy/default run adoption still needs explicit migration semantics. |
| Immutable economic assumptions | Capital/fee/slippage and a fixed policy-manifest label are persisted and conflicting values rejected. Management does not consistently consume them; policy parameters/code/data provenance are incomplete. |
| Complete historical OHLCV validation | Considerably stronger validation for chronological, finite, well-formed historical bars. Bad/insufficient data still collapses to no-proposal and can be logged as a successful no-setup scan. |
| Post-outcome returned free cash | Implemented. Each call reflects its committed outcomes. Identical reruns can still create additional outcomes, so stable accounting requires the fixes below. |
| Pending/expiry/watchlist consistency | Partial. Initial future-data absence is no longer immediately EXPIRED, but persisted pending expiry and filled/open state semantics remain wrong/incomplete. |
| Dashboard run identities | Implemented in response/UI labels. Build passes. Full reconciliation/valuation/drill-down and browser evidence remain pending. |

## Required corrections, ordered by impact

### N1 — P0 research correctness: do not finance a past entry with later cash

Location: `run_shadow_workflow`, proposal selection/simulation loop; `_shadow_account_state`; simulator entry boundary.

Confirmed probe: with ₹1,000 and zero fees/slippage, the first call at a given clock creates one closed trade and returns ₹980.20. Repeating **the exact same clock and inputs** creates another previously deferred sleeve, entering at the same earlier historical bar, and returns ₹960.40. The first trade's capital was occupied at that historical entry time. Releasing it after a later close must not permit a retroactive simultaneous second entry.

The `as_of` filter prevents seeing bars beyond now; it does not prevent making a new selection now and filling it at a bar before selection. Current code has no durable selected/authorized-at boundary for simulator entry, no atomic run-step completion, and no chronological cash-reservation event stream. Dedup of completed opportunity IDs is insufficient for a previously deferred opportunity.

Implement:

1. Persist an evaluation step key and its input digest/result. Same run, same clock, same inputs returns the prior result without new economic effects. Conflicting input at the same step must reject or create an explicit revised run; do not silently alter established outcomes.
2. Persist selection/reservation time and earliest executable bar boundary for each opportunity. A newly selected candidate cannot fill before selection. A candidate selected earlier may fill on a subsequent eligible bar even if processing resumes later.
3. Process replay in event-time order: update known prices/positions, settle eligible exits, select/reserve capital, then execute only at permitted subsequent events. Define tie-breaking at an identical timestamp and completed-bar/open-time semantics.
4. Persist reservations/position changes with compare-and-set account/run revision, or an equivalent serializable owner. Two overlapping invocations must not allocate the same cash. No database lock across slow external operations.
5. A fresh decision on an old trigger requires an explicitly valid new entry, not replay of a price that has already passed.

Acceptance: exact rerun leaves trades, cash, events and positions unchanged; deferred second sleeve cannot enter during another position's reservation; equivalent replay/incremental schedules yield identical economics; two workers cannot overspend; crash/resume does not repeat a fill. Include several competing opportunities, not just one.

### N2 — P0 research correctness: consume the saved run costs throughout position life

Location: `_advance_open_shadow_positions` calls `simulate_open_shadow_position` with its default `.001` fee and `5` bps slippage, rather than the manifest supplied to `run_shadow_workflow`.

Confirmed probe with fee=0/slippage=0: one-pass close has exit ₹101.80 and net −₹19.80. The equivalent position opened in one step and managed in the next exits at ₹101.7491 and nets −₹21.1738. The manifest did not change; the management path did.

Load cost assumptions from the authoritative persisted run and pass them through every entry, management, exit and fee-persistence path. Store a versioned cost model/reference. Replay must accept/use the same run assumptions rather than exposing only default-cost operation. Do not rely on transient defaults after restart.

Acceptance: nondefault zero-cost and nonzero-cost cases match across uninterrupted, multi-step, restarted and replay runs; ledger entry/exit fees reconcile; changed manifest rejects before any economic mutation. Include open positions surviving a process restart.

### N3 — P1: expire persisted pending setups and define filled state clearly

Confirmed probe: after a scan with no executable entry bars, then a tick after the entry deadline, watchlists remain `ARMED` and `SELECTED`. The builder now omits expired proposals, so the expiry branch inside the newly generated proposal loop is never reached for those old rows. There is no persisted pending-work sweep independent of new proposals.

A separate probe shows `COMPLETED` while the synthetic position is still OPEN because both OPEN and CLOSED simulation results transition the watchlist to COMPLETED. If COMPLETED is intended to mean “setup converted to position,” that must be explicit and distinct from closed-trade completion; current semantics mix the two.

Implement pending lifecycle loading from persistence before/alongside new scan output. Expire or invalidate pending entries even if their instrument disappears from the current universe or the builder returns nothing. Distinguish WATCHING/ARMED/SELECTED_PENDING/FILLED (linked position)/EXPIRED/INVALIDATED; use position CLOSED for the final trading outcome, or document a separate immutable setup-completed concept.

Acceptance: no-bar pending remains pending before deadline and expires afterward; disappearance from universe still expires; a real open position is managed after entry expiry; a closed position/event agree; rejected and unavailable proposals are not falsely marked expired. Keep transition/event writes atomic or repairable.

### N4 — P1: enforce a durable run clock and separate research provenance

Confirmed: a completed run accepts a later invocation with an earlier `now`, exposing future-established positions/cash to an earlier as-of request. `run_shadow_replay` only checks ordering in its local `clock_steps` list.

Persist last committed evaluation clock and sequence per run. Reject backward economic mutations; historical inspection is a read-only as-of projection, not a rerun against current state. Handle equal-clock retries through N1. Add a typed execution origin/mode so replay data is distinguishable from ongoing shadow observation; the wrapper currently records SHADOW for everything.

Expand the manifest beyond fixed string `three-sleeves-v1`: actual policy parameters/version, code identity, bar semantics, cost model, universe/data provenance and initial balance. Incremental input snapshots can append immutable versioned digests; corrections need a declared revision policy. Define migration for legacy positions before creating a manifest that implicitly adopts them. Avoid default-run storage keys sharing an unrestricted namespace with encoded named-run keys.

Acceptance: backward calls reject without mutation; equal retries no-op; new revised run stays separate; old unmanifested evidence is quarantined/labeled rather than certified; source corrections cannot silently alter a previously completed research result.

### N5 — Finish atomic evidence and truthful scan states

Still present from prior review: account cash reads, position writes, watchlist transitions and outcome events use separate transactions; close followed by crash can leave a missing event. Stale writes lack expected-last-bar ownership. Invalid historical input returns `[]`, after which the workflow may record SUCCESS/NO_COMPLETED_SETUP.

Complete one unit of work or durable outbox/repair path for economic state plus evidence. Check write ownership and row counts. Return typed scanner outcomes distinguishing insufficient history, invalid data, stale data and valid no setup. Do not let a mode-level latest successful scan hide another account/policy's failure. Separate scheduled-attempt liveness from deduplicated data evaluations and market-data freshness.

Acceptance: failure injected between state/event writes repairs deterministically; stale worker cannot overwrite newer progress; malformed history surfaces unavailable/invalid without being counted as healthy coverage; never-configured and disabled states are explicit.

## Remaining larger work — continue after/alongside these contracts

The source-of-truth product scope remains `2026-09-06-proactive-intelligence-product-build-spec.md`. This focused correction must not become another reason to leave the rest of that build untouched.

| Workstream | Required next output | Can develop without live credentials? |
|---|---|---|
| Partner fixture atomicity/lifecycle | One transaction covers envelope validation, create/update/close, accepted watermark and revision; preserve source mark times; complete reopen/corporate-action fixtures and deterministic cards. | Yes |
| Optional AI | Bounded asynchronous queue, startup/provider-failure isolation, deterministic alerts/watchdog independent of model latency, provenance/cache/budget tests. | Yes, fake provider |
| Research/learning | Connect corrected outcomes to Backtest Lab, exit-quality and strategy health; run baseline versus bounded entry/exit challengers; retain all trials and insufficient-evidence states. | Yes, fixtures first; historical evidence explicitly pending if absent |
| Account/UI evidence | Post-commit cash, reserved capital, realized versus marked unrealized results, fees and account/run drill-down with clear windows. | Yes |
| Proactive diagnostics | Calendar-aware expected scans and two/five-session inactivity explanations; observational live-book event producers without changing order behavior. | Yes for fixture/Dev wiring |
| Integrated demo | One deterministic multi-session command driving real registered jobs/APIs, account/run isolation, restart, AI outage and partner lifecycle, with browser evidence. | Yes |

## Concrete next assignment and completion gates

1. Implement N1/N2 together: immutable run-step processing, event-time cash authorization and manifest-driven management costs. Convert the probe into economic-invariant tests. Do not solve idempotence by blocking all subsequent useful updates.
2. Complete N3/N4/N5: persisted lifecycle sweep, durable clock, provenance and atomic/repairable evidence. Verify expiry, new data, concurrency, crash recovery and equal-time retry cases.
3. In parallel where independent, finish partner transactional fixtures and optional-AI plumbing. Missing real adapter/key is not a blocker for software/test completion.
4. Connect the trustworthy outcome stream to comparisons/health reports and the UI. Research completion means working machinery and honest evidence, not guaranteed profitable strategies.
5. Deliver the multi-session demo and actual browser evidence. Run relevant Python/agent/client/gateway tests in their supported runtimes; report any environment limitation precisely.

Required end report: exact commits, changes and test commands/counts; which findings N1–N5 are fixed with evidence; P1–P7 product status; runnable demo command; genuinely external prerequisites; explicit statement of any live effect. Preserve previous audit artifacts. All changes in Dev; no Production edits, live strategy activation, orders, messages or funding changes.

## Copyable developer instruction

> Continue from current Dev HEAD using `docs/2026-09-06-463608a-validation-and-next-implementation.md` and the full product build spec. Fix duplicate historical entries on identical reruns, use persisted run costs for resumed positions, enforce a durable clock and pending-expiry lifecycle, and make economic state/evidence atomic or repairable. Then continue through the independent partner fixture, optional-AI, research/UI and integrated-demo workstreams. Preserve audits and delivery safeguards; keep Production and all live effects untouched. Report N1–N5 evidence plus P1–P7 status. A single narrow correction is a checkpoint, not completion of the broader assignment.
