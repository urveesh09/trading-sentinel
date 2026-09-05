# Second remediation audit and next-step roadmap

Reviewed on 5 September 2026 in **Dev**, branch `codex/production-correction-hedge-p0`, HEAD `705d23d`. Increment reviewed: `89cb55d..705d23d`, including `30cbaa3` and `705d23d`. The previous audit remains the baseline for requirements; this document records what changed, what is still wrong, and the next development priorities.

## 1. Verdict

**The remediation makes real progress, but this branch should not yet be promoted as a working hedge-advice service.** The most serious new regression prevents valid Phase-1 reviews from reaching the sender. The new snapshot importer also lacks whole-snapshot atomicity, freshness/replay protection and an enforced account-level completeness gate. Those problems affect the truth of the portfolio on which advice depends.

This conclusion is supported by offline reproductions through the actual functions, not just source inspection. It is not a claim that these defects have occurred in live Production: Production was not deployed or modified during this review.

The implementation report is more candid than the earlier report about the unresolved adapter. That is appropriate. However, supplying an adapter URL alone will not repair the code defects below. Fix them before connecting real portfolio data or treating a live canary as the remaining engineering test.

### Independent validation

| Validation | Result |
|---|---|
| Expanded Python selection: hedge, input refresh, partner, scheduler contracts/closures, FNO, EDGE, history, runtime audit and ops | **272 passed**, one Starlette deprecation warning |
| Gateway executor suite | **46 passed** |
| Python AST syntax checks on six changed runtime modules | Passed |
| Node syntax checks on executor and Kite service | Passed |
| `git diff --check 89cb55d HEAD` | Passed |
| Offline adversarial integration probes | Reproduced the defects below |

These are selected tests, not the entire repository suite. The passing scheduler characterization tests confirm that the earlier golden-contract failures were corrected. The test counts do not prove hedge delivery: the expanded tests still do not exercise the valid Phase-1 orchestration path sufficiently to catch its new type error.

### What is corrected or materially improved

- A remotely acknowledged delivery is committed before ancillary service-state updates. The previous status-write-after-ack duplicate scenario is addressed and tested.
- A single transport call makes one Telegram POST, preventing its own retry loop from overwriting an earlier timeout result.
- The Phase-1 status helper detects a known pending row alongside reconciled rows.
- An empty builder result no longer makes the unsupported claim `NO_HEDGE_NEEDED`; it reports generic unavailability.
- Shadow message text and detail are persisted in a separate immutable-record table, instead of only overwriting a latest-state value.
- Live balance is preferred to raw cash for valid numeric responses, and product-margin evidence is consulted.
- Cross-boot market-hours gaps are now coverage findings, separate from same-process freezes.
- Missing/malformed EDGE dates return an invalid-data reason, and scheduler golden files include the intended new jobs.
- There is now an actual scheduled adapter consumer, with an explicit unconfigured state, rather than just manual endpoints.

### What remains partial

Transport ambiguity is preserved **within one POST**, but not treated conservatively across delivery claims. “Material” proposal versioning includes an ordinary refresh timestamp. Snapshot completeness is stored as a diagnostic but does not govern advice. The adapter is an HTTP consumer for pre-existing position IDs, not a complete broker onboarding/discovery system. The margin fallback still accepts some invalid current-funds states. These are material distinctions, not wording preferences.

## 2. Reproduction evidence

New evidence is under `docs/review-2026-09-05-round2/`. Previous review artifacts were not changed.

| Probe | Observed behavior at `705d23d` |
|---|---|
| Valid reconciled portfolio and valid chain through `partner_hedge_tick()` | Builders return **2 reviews**, sender called **0 times**; error: `'str' object has no attribute 'value'` |
| Valid quantity change followed by unknown position ID in same snapshot | Function raises, but first position remains changed from **40,000 to 20,000 units** |
| Day-old complete empty snapshot applied after newer position evidence | Open position is marked closed; **0 open rows** remain |
| Complete empty snapshot with invalid VIX | Function raises for VIX, but position closure has already committed |
| Partial snapshot updating all currently known rows | Portfolio helper returns **`READY_FOR_EVALUATION`** |
| Unchanged quantity refreshed two minutes later | `updated_at` changes; that field is part of the proposal fingerprint |
| Ambiguous timeout then immediate same-key claim | **2 POST-equivalent mocked sender calls** |
| 429 requesting 3,600-second delay then immediate same-key claim | **2 mocked sender calls**, no wait enforced by claim policy |
| Already-expired `valid_until` passed to send helper | Sender still called **once** |
| Delta-only Greeks payload | Missing gamma/theta/vega converted to **0.0** |
| Negative live balance with positive raw cash | Parser selects the positive cash fallback |

Reproduction commands, from Dev:

```powershell
python-engine\winvenv\Scripts\python.exe docs/review-2026-09-05-round2/probe_remediation.py
node docs/review-2026-09-05-round2/probe_margin.js
```

These scripts use synthetic fixtures, mocked senders and temporary SQLite databases. They record current behavior; they are not expected-correctness tests and must not be copied into CI as assertions that these outputs are desirable. Source checks and probe outputs are tied to this reviewed HEAD.

## 3. Corrections required now

P1 means high-priority correction before relying on the affected behavior in deployment. P2 means important follow-up or completeness work. The user-facing delivery priority remains hedging first. No catastrophic live incident is asserted.

### C1 — P1: Repair the valid Phase-1 orchestration path first

**Location:** `python-engine/hedge_advisory.py:1280`.

The new fingerprint accesses `leg.opt_type.value`, but `LegSpec.opt_type` is a string (`PE`, `CE`, `FUT`). The real builders produce that representation. The exception occurs before `_send_claimed_review()` and is caught as a tick failure. A valid portfolio therefore still produces no actionable hedge messages.

**Do:** canonicalize the field according to its actual model, then test the complete path using real builders and formatters. Avoid a mock leg with an enum that accidentally hides the defect. Preserve the existing validated bid/ask, quantity and expiry semantics.

**Acceptance:** a valid complete snapshot, fresh marks and listed chain lead through the scheduled closure, tick, builder, formatter and mocked sender to a durable acknowledgement. Include both protective-put and futures advice, no-hedge input, and invalid chain cases. This is the first necessary regression test; lower-level builder and transport tests alone were insufficient.

### C2 — P1: Make portfolio snapshot application atomic

**Locations:** `python-engine/partner_input_refresh.py:51–119`; `hedge_analytics.py:1487`.

Each call to `reconcile_partner_position()` and `close_partner_position()` opens and commits its own transaction. A later duplicate/unknown/invalid row can fail after earlier changes are visible. VIX is validated after closures, so invalid VIX can make the whole refresh report failure even though its portfolio writes committed.

**Do:** validate all rows and snapshot metadata before mutation, then apply one portfolio version and its reconciliation events in a single DB transaction. The helpers need a transaction-aware internal API, or stage validated rows then atomically promote a snapshot version. Readers must see the old complete version or the new complete version, never a mixed intermediate state. Prevalidation alone does not protect against a mid-write failure or concurrent reader.

Decouple VIX ingestion from portfolio application if it is an independent stream. Either reject the whole combined envelope before writes, or report independent stream outcomes clearly; do not silently half-apply an operation reported as failed.

**Acceptance:** invalid last row, invalid VIX, DB failure on the second write and concurrent advice evaluation leave a consistent visible portfolio. Counts reconcile to the accepted snapshot ID. Repeating the same snapshot is idempotent.

### C3 — P1: Reject stale, future and out-of-order snapshot state

**Location:** `_timestamp()` and `apply_partner_input_snapshot()` in `partner_input_refresh.py`.

Timezone awareness is checked, but snapshot age, ordering and replay are not. A stale complete empty snapshot can close positions whose recorded evidence is newer. A delayed snapshot can also overwrite newer quantity/mark state. Price freshness gates cannot protect a position that the importer has already marked closed.

**Do:** add a versioned envelope with account/source binding, snapshot ID, monotonic sequence or comparable revision, actual broker observation time, received time and completeness scope. Persist the last accepted watermark per account/source. Reject backward revisions, duplicate IDs with changed payloads, excessive future skew and stale snapshots before any reconciliation or inferred closure. Equal-ID identical retries must be no-ops. Differentiate position observation age from market-price age; never change an old observation's timestamp to make it pass.

**Acceptance:** delayed empty snapshot cannot close a newer holding; out-of-order quantities cannot roll back state; future timestamps and conflicting replays are quarantined; valid fresh empty snapshots can close only the correct account/source's positions. Use a controllable clock and precise timezone-boundary tests.

### C4 — P1: Enforce snapshot completeness across every advice phase

**Locations:** `partner_input_refresh.py:119`; `hedge_advisory.py:1117`, `:1203`, `:1335`, `:1432`.

The importer writes `PARTIAL_SNAPSHOT`, but Phase 1 checks only loaded row counts/freshness. A partial snapshot containing all *known* positions passes even though it may omit an unknown holding. Phases 2/3 still load the reconciled subset directly; the new Phase-1 partial-row check is not a shared portfolio gate. `last_input_refresh` is also reused by the Phase-1 tick, so its latest-row diagnostic is not durable completeness evidence.

**Do:** make every whole-portfolio calculation consume one accepted, complete, current account snapshot version. Persist feed state separately from evaluation state. A verified empty portfolio needs a distinct state from “no configured portfolio.” If advice for an isolated exposure group is permitted with an incomplete account, define and validate that narrower scope and label it explicitly; do not imply whole-account coverage.

**Acceptance:** partial envelope with all known rows still blocks whole-account advice; pending/invalid rows block relevant phases consistently; a verified empty account reports empty rather than unconfigured. Enable Phase 2/3 with synthetic valid staging evidence in the integration tests so their portfolio gates are exercised, not bypassed by disabled flags.

### C5 — P1: Version economic changes, not refresh timestamps

**Location:** `hedge_advisory.py:1272–1287`.

The fingerprint includes `p.updated_at`, which reconciliation changes on an unchanged refresh. After C1 is fixed, routine refreshes can generate different proposal versions at each evaluation, resetting same-key delivery limits and creating redundant messages. This defect is currently masked by C1. It is a source-derived consequence corroborated by the probe's changing timestamp, not a claim that live spam has occurred.

**Do:** extract a pure canonical proposal-identity function. Use stable account/snapshot scope, economic exposure, selected contracts, side, lots and explicitly defined materiality/risk-band changes. Keep observed/refreshed times as metadata. Separate the dedup key, proposal version, session digest key and delivery attempt ID. Decide explicitly when an unchanged proposal warrants next-session revalidation; simply removing the timestamp from a forever-dedup key can cause a new silence problem.

**Acceptance:** twenty unchanged refreshes produce one current proposal; row reordering has no effect; a real quantity/contract/risk-band change produces one superseding version; a new session follows the stated policy. Apply per-underlying notification caps across versions, with a defined escalation path for urgent protection changes.

### C6 — P1: Finish delivery recovery beyond the single POST

**Locations:** `hedge_advisory.py:268–317`, `:508–522`; `partner_bot.py:121–132`; proposal deadline at `hedge_advisory.py:1294`.

The transport now returns ambiguity correctly, but `_claim()` does not block or specially handle the nested `delivery.state='ambiguous_timeout'`. A released failed claim can be taken immediately. `retry_after` is stored inside an error string and not enforced. `valid_until` is written but no send path reads it, and it is based on tick time rather than the oldest dependency's expiry. There is still no general scheduled recovery worker for one-shot digests.

**Do:** retain a typed attempt history and terminal/transient/ambiguous outcomes. Add `next_attempt_at`, proposal expiry, last known acknowledgement and manual recovery state where needed. Preserve ambiguity across claims. Compute the earliest expiry across marks, chain/leg quotes and policy, and revalidate before transport. Never resend an old proposed size merely because its retry is due. Keep permanent rejection from consuming repeated requests indefinitely; expired advice should be superseded or retired. Use one queue with priority and a recovery worker rather than multiple retry mechanisms.

**Acceptance:** timeout then next tick cannot silently become a normal resend; 429 respects the requested delay; expired proposals produce no send; unresolved acknowledgement persistence is visible; summaries retry after a recoverable outage without waiting until the next day. Inject transport and DB faults together, including acknowledgement persistence failure. Exactly-once remote/local delivery must not be promised across arbitrary crashes.

### C7 — P1: Do not turn invalid/negative live funds into positive raw-cash evidence

**Location:** `node-gateway/server/services/executor.js:25–31`.

Preferring a valid live balance is fixed. However, `finiteNonNegative(live_balance) ?? finiteNonNegative(cash)` falls back for a *present negative or malformed* live balance. The probe selects ₹100,000 cash when live balance is −₹1,000, null or a malformed string. Zero live balance is correctly preserved.

**Do:** distinguish an absent legacy field from a present invalid/negative value. A documented negative current balance must mean no available entry capacity; malformed current evidence must fail closed rather than reusing a different funds component. Restrict any absent-field fallback to a tested documented schema and label the policy. Continue product-specific margin checks and broker rejection handling. Validate response identity/shape and the chosen buffer policy as part of the same preflight.

Kite distinguishes raw cash from current available balance; a positive raw component is not a reason to discard negative current evidence. [Kite funds and margins](https://www.kite.trade/docs/connect/v3/user/#funds-and-margins).

**Acceptance:** negative, zero, missing, null, malformed and positive current balances all produce deliberate distinct outcomes; stale/raw fallback cannot authorize new entry. Re-run product-margin and unknown-order tests. Broker exits remain independent of entry funds checks. This is a preflight correctness issue; it does not imply the broker would accept an unfunded order.

### C8 — P1/P2: Complete and constrain the adapter contract before calling it production-ready

**Locations:** `partner_input_refresh.py:40`, `:76–93`, `:124–137`; scheduled wrapper in `scheduler_setup.py`.

The report correctly says only known position IDs are supported. The consequences need an operational plan:

- New broker positions cannot be discovered/imported by this worker. Unknown IDs reject the snapshot; closed identities do not automatically represent reopened positions. Provide a supported identity/bootstrap lifecycle and atomic reconciliation with the broker's real instrument/account identity.
- The envelope's `source` is supplied by the adapter. Equality to an existing row's source is useful, but there is no receiver-side configured expected account/source binding in this increment. Bind the approved endpoint to the account/scope and reject mismatches.
- The worker does not forward `deliverable_quantity`, `deliverable_as_of` or `deliverable_source`. Covered-call evidence cannot be renewed through it, and reducing a holding below retained deliverable quantity can fail reconciliation even when refreshed holding evidence is available upstream.
- `_greeks()` fills missing gamma/theta/vega with zero. This matches an older permissive intake default, but carries that limitation into the new feed. Unknown is not a measured zero for gamma/volatility-sensitive strategies. Carry provenance, completeness and age and gate strategies by the fields they need.
- VIX is still coupled to the partner adapter and is optional. A genuine market-data VIX producer remains to be connected; an HTTP consumer does not create that data source.
- The worker runs every two minutes without its own enabled/session check. Define a separate ingestion switch and justified hours, including weekend/after-hours behavior, instead of silently tying an always-running writer to partner job registration.
- It sends Sentinel's shared `INTERNAL_API_SECRET` to the configured adapter URL. Before connecting an external service, use an adapter-specific credential with limited scope and an approved secure endpoint; the service that supplies holdings should not need Sentinel's general internal-service authority.

**Acceptance:** wrong account/source rejected before writes; new/reopened/closed identities handled explicitly; reduced deliverable holdings reconcile safely; incomplete Greeks cannot authorize dependent advice; source-disabled refresh performs no remote work; VIX can refresh independently; internal gateway credentials are not sent to the adapter. No actual source credentials or live account calls were used in this review.

### C9 — P2: Close the remaining evidence and operational gaps explicitly

The new shadow table is a substantial improvement. Its content hash omits `evaluated_at`, so identical content is deduplicated, not necessarily one immutable row per evaluation event. Define that choice; preserve separate per-run evaluation evidence if staging-day counts rely on it. Ensure sample-review references resolve to stored rendered text, input snapshot, code/strategy version and actual observation times. A latest pointer remains only a UI convenience.

The following previous items are not resolved by these two commits: precise builder rejection taxonomy, full hedge exposure/protection summaries, priority scheduling, operator DR delivery acknowledgement beyond HTTP acceptance, history/file coverage repair, remaining chain/limiter/DB/notify timing and the real report regression using the retained P&L fixture. EDGE date syntax is fixed, but chronological/session freshness and full OHLC consistency still need the original acceptance cases. Keep these as explicit backlog items rather than quietly treating the previous review as closed.

**Acceptance:** implementation documentation maps each previous finding to fixed/partial/open and cites its actual test. No outcome labelled “delivered” merely because a gateway returned HTTP 200; no claim that instrumentation has already improved skip rates. Preserve the original archived Production P&L evidence and validate the report against it before declaring reporting complete.

## 4. What to do next, in order

### Release A: restore the demonstrable Phase-1 path

Fix C1 and C5 together, since removing the type error exposes the timestamp-based versioning problem. Add a regression that begins with real-shaped inputs and reaches the mocked sender. Do not merge a type-only fix without unchanged-refresh and changed-exposure tests.

### Release B: establish portfolio truth

Complete C2–C4 and the account/identity/freshness parts of C8. Suggested state flow:

`received → schema validated → account/scope verified → freshness/order checked → staged → atomically accepted → eligible for evaluation`

Rejected input must never become a partly visible active snapshot. Retain the last valid snapshot with its actual age; if it expires, block personalized advice and explain why. Preserve audit history of rejection/acceptance without repeatedly inserting duplicate reconciliation rows.

### Release C: establish delivery truth and funds correctness

Implement C6 and C7, and finish the adapter credential boundary before external connection. Use a fake clock and transport/DB fault injection. Separate proposal generation, send intent, acknowledgement, user acknowledgement and confirmed hedge execution. Each is a different event.

### Acceptance milestone before external deployment

Run a multi-cycle simulation, not just one happy-path call:

1. Approved synthetic account starts empty and is recognized as verified empty.
2. A fresh holding appears, is reconciled, and yields appropriate Phase-1 advice.
3. Multiple unchanged refreshes do not flood the partner.
4. A material quantity change supersedes earlier advice once.
5. A stale or partial snapshot does not close or overwrite current portfolio truth.
6. Rate limiting, timeout and DB faults produce correct recovery states.
7. Expired proposals are never transmitted as current.
8. Actual synthetic hedge fills change protection state; delivered advice alone does not.
9. Restart preserves identity, accepted snapshot watermark, deduplication and recovery state.
10. All tests leave live accounts, Production and Telegram untouched.

Then rerun the expanded 272-test selection, gateway suite, scheduler contracts and new regressions. Record failures by behavior, not only aggregate counts. The purpose of additional tests is to cover the newly identified invariants, not to inflate the test total.

### External rollout prerequisites

The actual approved adapter/account mapping, securely scoped credentials, source coverage, partner risk objective and concrete live-message authorization remain genuine external prerequisites. They cannot replace the engineering work above. Promote through GitHub only, with an additive/versioned DB migration and backup. Verify fresh input and an authorized real partner canary, then observe eligible market-session behavior. Keep advanced phases gated by genuine validation evidence.

For the first deployed sessions, report: accepted/rejected snapshot counts by reason; age and completeness; current exposure/protection; proposals generated/suppressed/superseded; attempts/acknowledgements/ambiguities; quote age at send; scheduler delay; and any operator intervention. Roll back or disable the affected advisory path if incorrect sizing, repeated duplicate advice or corrupted snapshot state appears. Existing trade protection must remain available.

## 5. Ten further innovations to investigate for smoother net performance

These extend the previous ten proposals; they are not claims of novel financial discoveries or guaranteed profit. “Smoothly” should mean better after-cost portfolio performance with controlled drawdowns and dependable operations. A smoother hedge can reduce raw upside. Declare the acceptable cost/protection trade-off before optimizing it. The methods below require shadow validation; no strategy parameters or capital allocations were changed in this review.

### 1. Select hedge proxies by stressed tracking error

**Extension:** go beyond a fixed beta/index mapping when protecting a multi-stock portfolio. Estimate how candidate liquid indices/proxies track the actual portfolio under normal and stressed conditions, with uncertainty around beta and residual exposure. Prefer the simplest proxy that provides sufficient protection; abstain from precise sizing when mapping confidence is low.

**Where:** `hedge_analytics.py`, portfolio history and the proposed snapshot contract. Persist which portfolio version and observations support each mapping. A beta of one must not be silently assumed for every holding.

**Economic hypothesis:** reduce overpayment for a hedge that protects the wrong exposure and reduce unexpected residual losses. It is a portfolio-risk improvement, not a forecast of market direction.

**Validation:** compare fixed mapping with proxy selection on held-out periods at equal hedge cost. Measure portfolio-plus-hedge tracking error, tail loss, turnover and basis risk. Reject selection if its advantage disappears under unstable correlation, sector-specific shocks or modest transaction costs. Daily price history is not a substitute for an accurate current portfolio.

### 2. Test staggered hedge expiries instead of one large roll date

**Extension:** compare one-expiry protection with a small expiry ladder, where supported by current listed contracts and portfolio size. Maintain an explicit remaining protection horizon and roll only the relevant slice when it approaches expiry.

**Where:** proposal lifecycle and hedge comparator. Track each slice's premium, expiry, units and protection contribution; do not exceed whole-lot or capital constraints to force a ladder on a small account.

**Economic hypothesis:** spread renewal timing and reduce dependence on one expensive or illiquid roll window. The countervailing costs are more transactions, complexity and potentially less efficient protection.

**Validation:** replay matched portfolios using actual bid/ask chains across multiple roll cycles. Compare total insurance cost, worst protection gap, turnover and combined drawdown. Reject if fee/spread increases exceed the benefit or if contract availability creates uncovered intervals. Show the partner a single portfolio-level explanation rather than separate uncoordinated tips for each slice.

### 3. Make strike and expiry choice aware of skew and term structure

**Extension:** the prior plan compares structures; this experiment compares actual quoted strikes/expiries within an approved structure. A fixed delta or DTE is a starting policy, not evidence that the selected contract is always efficient.

**Where:** `hedge_strategies.py`, chain snapshot persistence and hedge analytics. Compare cost per unit of downside protection over the user's horizon, including bid/ask, skew, time decay, liquidity and residual risk. Keep the number of candidate policies small.

**Economic hypothesis:** avoid persistently overpaying for a particular wing/expiry and identify when maintaining existing protection is preferable to rolling. Skew changes affect option positions; they do not create free protection. [CME explanation of implied-volatility skew](https://www.cmegroup.com/education/articles-and-reports/implied-volatility).

**Validation:** matched scenarios and historical chain snapshots, with a frozen selection rule and full cost accounting. Reject a model that relies on interpolated prices where executable quotes were unavailable or that trades a cheaper premium for inadequate protection. Do not infer an Indian contract's settlement rules from an overseas educational example.

### 4. Compare adding a hedge with reducing the original exposure

**Extension:** add “reduce a portion of the underlying” as a comparator, where the account mandate permits it, instead of assuming every risk reduction requires another derivative. This remains advisory and requires explicit user preference before any execution feature.

**Where:** risk-budget/hedge comparison layer. Compare transaction costs, foregone upside, remaining beta exposure, margin usage and the user's holding constraints. Tax/account-specific consequences must be supplied or explicitly left unmodelled; do not invent them.

**Economic hypothesis:** in some portfolios, a small exposure reduction can meet the same risk objective with less ongoing premium or margin burden. It may also miss a recovery, so compare total portfolio outcomes.

**Validation:** matched held-out portfolios and equal risk objectives across maintain, reduce exposure and buy hedge. Measure net return, drawdown and capital usage, including rebound periods. Reject any “best” option that violates the partner's mandate or depends on missing account costs. A strategy label is not a reason to prefer complexity.

### 5. Add an economic expiry to directional signals

**Extension:** distinguish a signal's predictive lifetime from the API's quote-freshness limit. A quote can be fresh while the original breakout opportunity has already been consumed by price movement or execution delay.

**Where:** Momentum/FNO signal records, gateway entry preflight and shadow research. Estimate remaining edge as a function of time since signal, distance from intended entry, spread and realized move. Start with a small interpretable rule that refuses late/chased entries; avoid a large model fitted to a few trades.

**Economic hypothesis:** avoid negative expectancy entries caused by delay, without changing the original setup logic. This may improve smoothness by removing expensive late fills rather than generating more signals.

**Validation:** replay the same signals at observed and stressed delays, accounting for skipped winners and missed fills. Compare immediate, delayed and expiry-aware execution at equal risk. Reject if improvement appears only under an optimistic fill model. Keep protective exits outside the entry signal-expiry gate.

### 6. Learn a liquidity-based capacity limit for each strategy

**Extension:** go beyond fixed spread/OI thresholds. Estimate the largest useful trade size before market impact and missed fills consume the strategy's edge. Hedge proposals should similarly distinguish theoretical lots from practically executable size.

**Where:** execution telemetry, `cost_schedules.py`, strategy sizing and hedge advice. Use recorded depth, spread, traded volume, order size and partial-fill behavior. Show a smaller executable alternative or explicit capacity limit; do not silently downsize a required hedge and still call the portfolio fully protected.

**Economic hypothesis:** better capital use and less slippage as size grows. A strategy can be profitable at small size and unattractive at larger size.

**Validation:** paper/shadow fills calibrated against real available execution observations, conservative depth consumption and stress spreads. Plot after-cost expected benefit versus size and report uncertainty. Reject apparent scale benefits derived from mid-price fills or unlimited top-of-book liquidity. Do not live-test capacity by sending unnecessary orders.

### 7. Reserve cash for stressed margin and hedge maintenance

**Extension:** current preflight asks whether an entry is affordable now. Add a portfolio planning calculation for whether it leaves sufficient liquidity to maintain protection after a plausible move or margin change.

**Where:** the capital-readiness view and hedge comparator, with actual account balances, product-margin evidence and a user-approved reserve policy. Separate present broker requirement from scenario requirement and from an optional conservative buffer.

**Economic hypothesis:** avoid forced risk reduction or inability to adjust protection during volatility. Holding reserves can reduce capital deployed and raw returns; measure the trade-off rather than maximizing reserve size.

**Validation:** scenario replay of existing exposure with price/volatility shocks, adverse fills and changing margin. Compare opportunity cost, emergency shortfall incidents and total drawdown under fixed versus scenario-aware reserves. Reject scenarios that claim certainty about future broker margin. Use current broker evidence where available. [Kite margin calculation API](https://kite.trade/docs/connect/v3/margins/).

### 8. Prioritize market-data work by the risk it serves

**Extension:** use separate service objectives for protective execution, current hedge inputs, eligible entry candidates and background universe refresh. A broad historical refresh should not make a current protection review stale.

**Where:** scheduler, shared client limiter, caches and input refresh. Instrument queue wait by purpose, reserve bounded capacity for time-sensitive work, share only compatible fresh snapshots and let background work checkpoint/resume. Preserve the broker request limit and avoid increasing concurrency indiscriminately.

**Economic hypothesis:** reduce missed or stale decisions and unnecessary retries, producing more consistent operations with the same market-data budget. This is an operational advantage to measure, not a prediction advantage.

**Validation:** controlled replay with slow broker responses and overlapping scanners. Measure protective-action latency, hedge age at evaluation/send, dropped entry opportunities and bootstrap completion. Reject scheduling changes that improve advisory messages by delaying real position protection. Establish measured service targets from normal workloads before setting alert thresholds.

### 9. Attribute hedge results against the same unhedged portfolio path

**Extension:** build a counterfactual insurance-efficiency report. Compare the observed portfolio plus its actual hedge with the same underlying holdings over the same interval without the hedge. Separate premiums/spreads/fees, delta protection, volatility effects and residual basis risk where supported by data.

**Where:** immutable portfolio/proposal/fill snapshots and the reporting ledger. A delivered suggestion is not an actual hedge; self-reported fills must remain labelled. Report approximation limits for Greek-based attribution and reconcile to actual cash/mark changes.

**Economic hypothesis:** identify expensive protection that rarely serves its intended purpose and retain structures that meet a declared loss budget efficiently. A hedge losing money in a rising market is not automatically a failure.

**Validation:** verify accounting identities before using the report to change strategy. Compare insurance cost, avoided tail loss and foregone upside across periods. Reject causal claims based only on the subset of suggestions the partner chose to trade. The report should improve decisions, not rank strategies by isolated hedge-leg win rate.

### 10. Use cost- and uncertainty-aware adjustment bands

**Extension:** refine the prior lifecycle/no-trade-band proposal by making the decision threshold depend on both estimated risk reduction and adjustment cost. Larger uncertainty in exposure, hedge mapping or quotes should widen abstention—not be treated as a precise target.

**Where:** delta-rebalance/proposal versioning logic, the cost model and input-quality state. A candidate adjustment must exceed a predeclared net-benefit threshold and remain feasible after whole-lot rounding. Keep a separate urgent-risk escalation policy for situations where inaction itself breaches the mandate.

**Economic hypothesis:** smoother turnover and less “chattering” between neighboring hedge sizes as small mark changes arrive. This directly complements C5: timestamps must not trigger trading advice, and tiny economic changes may not justify it either.

**Validation:** compare fixed, cost-aware and uncertainty-aware bands on matched historical portfolios, including whipsaws and gaps. Measure hedge tracking error, tail loss, fees and update count. Reject a policy that reduces messages simply by ignoring material risk. Freeze alternatives before held-out evaluation and record every tested variant to limit selection bias. [Bailey and López de Prado on Deflated Sharpe and selection bias](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf).

## 6. How to prioritize innovation without delaying reliability

The next engineering investment should be C1–C8, not additional strategy breadth. Once the multi-cycle acceptance milestone passes, establish innovations **8 and 9** as operational/economic measurement foundations. Evaluate **1, 3 and 10** as the first hedge-quality experiments; compare **2, 4 and 7** against the partner's protection/cost mandate. Test **5 and 6** separately for the operator's directional trading. Never mix the partner and operator accounts to make a research result look better.

For each experiment predeclare: baseline, holding period, account/portfolio scope, net-cost model, primary benefit metric, allowed drawdown/cost trade-off, historical coverage, held-out dates and rollback rule. Measure both net returns and risk; do not infer profitability from test coverage or increased messaging. More independent observations and realistic costs matter more than adding complex strategy names.

The expected near-term result of the corrections is a dependable hedge service with truthful inputs and delivery state. Any claim of greater profit or smoother realized returns must follow measured, representative after-cost results. This audit provides a path to that evidence; it does not invent an uplift percentage.

## 7. Review boundaries and artifacts

No Production source, runtime, database, broker order or Telegram destination was changed. Production's previously untracked `migration/` directory remained untouched. No application code was edited; new documentation and offline probe artifacts are uncommitted in Dev. Existing plans/review artifacts were preserved.

The review is tied to HEAD `705d23d` and uses synthetic tests plus the previously established Production audit context. It is not a fresh multi-day Production performance assessment. No external adapter, account identity or live transport was tested. The known-ack ancillary-state correction was verified by the current tests; arbitrary remote/local crash atomicity is still not guaranteed.

New files:

- `docs/2026-09-05-hedge-remediation-round2-audit-and-roadmap.md`
- `docs/review-2026-09-05-round2/probe_remediation.py`
- `docs/review-2026-09-05-round2/probe-results.json`
- `docs/review-2026-09-05-round2/probe_margin.js`
- `docs/review-2026-09-05-round2/margin-results.json`
