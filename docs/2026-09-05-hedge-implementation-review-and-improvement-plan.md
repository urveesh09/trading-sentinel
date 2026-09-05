# Hedge implementation review, correction plan and ten improvement proposals

Review date: 5 September 2026. Reviewed Dev branch: `codex/production-correction-hedge-p0`, HEAD `89cb55d`. Baseline: `a569444`. Review includes **2c73c6f**, **8822945** and **89cb55d**; the first commit contains the hedge work omitted from the quoted two-commit summary.

## 1. Verdict

**Useful partial implementation, below the agreed hedging-first completion standard, with corrections required before treating the branch as release-ready.** The work adds worthwhile observability, delivery records, advanced-phase gates and execution checks. It does not yet establish the promised fresh-portfolio → valid hedge review → acknowledged delivery service. Several new behaviors also give misleading results under conditions not covered by the focused tests.

This is not a recommendation to discard the work. Retain the sound foundations and finish the missing path. Keep legacy directional FNO messages suppressed, as requested. Increased message count alone is not success: missing-input notices and VIX context do not substitute for eligible personalized hedge advice.

### Assessment against expectations

| Agreed expectation | Observed implementation | Assessment |
|---|---|---|
| Fresh recurring partner inputs and VIX producer | Existing intake endpoints retained; no recurring producer or source-neutral refresh worker added | **Incomplete; not solely deployment work** |
| End-to-end valid Phase-1 hedge delivery | Builder and delivery helper tests exist; no complete recurring-input-to-delivery milestone demonstrated | **Incomplete** |
| Hedge-specific summaries | Two jobs and a status/count formatter added | Useful, but no exposure/protection/day-action recap |
| Exact blocked-state reasons | New service-state table and reason strings | Partial; false ready/no-hedge states remain |
| Reliable acknowledgements/recovery | Message IDs, claims and bounded retries | Useful, but acknowledged messages can be retried after local write failure |
| Critical changes prioritized over digests | No priority queue/coalescing/revalidation worker found | **Not implemented** |
| Advanced readiness with reviewable shadow evidence | Sending gated; shadow candidate overwrites one state key | Gates improved; durable review evidence incomplete |
| Broker capital preflight | New check in gateway `executeSignal()` | Implemented with incorrect balance selection and product assumptions |
| Penny/EDGE reason fidelity | More reason categories | Improvement, not actual coverage repair; malformed-date/staleness gaps remain |
| FNO cadence diagnosis | Stage durations added | Initial instrumentation; no measured cadence correction |
| DR-only notification | Eligibility/formatter updated; HTTP status checked | Useful, but gateway acceptance is not Telegram acknowledgement |
| Liveness audit | Process/scheduler distinction and boot IDs | Improvement; cross-boot market gaps escape findings |
| September 4 P&L regression fixture | Deferred as unavailable | Evidence exists; review fixture now created |

### What was done well

- Production was kept separate; the reviewed implementation is in Dev.
- Phase 2/3 are disabled for delivery by default and checked against readiness before advanced sends. Phase 1 remains independent.
- Existing hedge claim ownership protection and trade protection/exit paths were preserved.
- The partner transport remains separate from the operator bot; acknowledgement IDs are now representable.
- DR-only activity can trigger a notification; missing files/history and price-band rejection are more visible.
- Monotonic stage timing and distinct scheduler/process heartbeat concepts are appropriate foundations.
- No strategy gates were loosened merely to improve one day's P&L.

## 2. Independent validation and evidence

I ran **262 focused Python tests**, including hedge builders/analytics/readiness/routes, partner transport/orchestration, FNO, Penny, runtime audit, scheduler tick and ops metrics: **all passed**. This broader run emitted a Starlette deprecation warning and a test-time unawaited startup-catchup coroutine warning; neither is counted here as a proven new runtime defect.

I then ran `tests/test_main_surface_characterization.py`: **2 passed, 2 failed**. Thus the selected Python review total is **264 passed, 2 failed**, not a clean overall validation result. The failures are:

- `test_surface_matches_golden`
- `test_add_job_census_matches_golden`

Both identify the two new hedge summary jobs missing from their expected snapshots. This is an intentional job addition with an incomplete test-contract update, not proof that a job disappeared.

The **44 gateway executor tests passed** independently. `git diff --check a569444 HEAD` also passed. These are selected suites, not the entire repository test suite. Passing them does not demonstrate current broker acceptance, actual partner delivery, improved trading returns or Production performance.

Offline probes used synthetic portfolios/market inputs, a temporary SQLite database and mocked transport. No broker order or Telegram message was sent. Reproduction scripts and machine-readable outputs are in [review-2026-09-05](C:/Users/Urveesh/Desktop/trading-sentinel/docs/review-2026-09-05/reproduce_review_findings.py):

- `reproduce_review_findings.py` / `python-probe-results.json`
- `reproduce_margin_findings.js` / `margin-probe-results.json`
- `production-pnl-fixture.json`, derived from archived Production query results with source SHA-256 hashes

The fixture reproduces ₹2,465.82 ledger P&L, ₹2,452.72 outcome-table P&L and a ₹13.10 coverage difference. Excluding the ₹3,317.82 EDGE carryover close leaves −₹852.00. It is a scoped, rounded-to-paise reporting fixture, not a full DB backup or complete attribution replay.

The original supplied plan and implementation report were left unchanged. Review artifacts are new, uncommitted Dev files. No application source or Production state was changed by this review.

## 3. Findings and required corrections

Severity P1 here means fix before relying on the affected behavior in deployment; P2 means important correctness, evidence or acceptance work. This review does not assert a demonstrated catastrophic P0 incident. The **delivery priority** remains hedging first regardless of those review severity labels.

### R1 — P1: The main hedge-input implementation is still missing

**Evidence:** repository calls to `record_vix_observation()` and `reconcile_partner_position()` still lead to intake routes and tests, not a scheduled ingestion/refresh service. The implementation report defers the account adapter under “deployment inputs and non-code work.”

**Consequence:** entering positions once does not keep them actionable under the five-minute price freshness gate. An empty VIX table stays empty. Deploying this branch against the observed Production state would add setup/digest messages, not establish personalized hedge reviews.

**Correction:** implement a source-neutral snapshot contract and recurring refresh worker now, plus an independently scheduled sourced VIX producer. The partner's account identity/connector selection is a real external dependency; adapter code, quote refresh, reconciliation events, verified-empty snapshots and synthetic integration tests are not. Keep position truth separate from price refresh: a fresh quote must not imply a broker reconciliation happened. Add timestamped snapshot completeness, account mapping, quantity changes and closes.

**Acceptance:** create/reconcile a synthetic real-shaped position, advance the clock past five minutes while refresh runs, generate an eligible hedge and record mocked acknowledgement. Repeat with stale feed, partial snapshot, verified empty account and changed quantity. Missing inputs must remain explicitly blocked. Test VIX independently of portfolio mapping.

### R2 — P1: Incomplete portfolio can appear ready; failed construction becomes “no hedge needed”

**Locations:** `python-engine/hedge_advisory.py:1026`, `:1034`, `:1171`; existing reconciled-only loader in `hedge_analytics.py:1474`.

**Reproduced:** one reconciled position plus one pending position returns `READY_FOR_EVALUATION`. The pending row is omitted from the grouped review calculation. A high OI requirement suppresses all proposals, but the tick maps any empty review list to `NO_HEDGE_NEEDED`. Empty proposals can also mean missing Greeks, invalid exposure, insufficient lot size or unavailable liquidity.

**Consequence:** the partner can receive advice based on an incomplete exposure set or receive false reassurance when the engine simply cannot construct a valid hedge. The reconciled-only calculation was already present; the new readiness label does not resolve that existing completeness gap and adds misleading status.

**Correction:** validate completeness at the account/snapshot and relevant exposure-group boundary. Identify every excluded open position, including unparsable rows. Use structured builder results with proposals plus reasons. Separate `NO_HEDGE_NEEDED`, `BELOW_MINIMUM_LOT`, `NO_LIQUID_CONTRACT`, `MISSING_GREEKS`, `PARTIAL_RECONCILIATION` and `INPUT_UNAVAILABLE`. Track status per underlying/phase and clear resolved current blockers while retaining historical events.

**Acceptance:** opposing confirmed/pending exposures never produce a whole-portfolio ready label. Missing Greeks and a deliberately illiquid chain produce their own reason, not “no hedge needed.” A genuinely complete portfolio within its target risk band can report that no adjustment is required.

### R3 — P1: Acknowledgement followed by a status-write failure causes duplicate sending

**Location:** `python-engine/hedge_advisory.py:410`. `_send_claimed_review()` writes `last_attempted_send` after remote success but before completing its delivery claim. Its exception path releases the claim as failed.

**Reproduced:** mocked Telegram success, followed by an injected failure of that status write, then a retry of the same key produced **two sender calls**. Telegram had already acknowledged the first call.

**Correction:** make the claim/delivery record authoritative. Record attempt intent before transport; after success, persist acknowledgement before nonessential service-state summaries. A known acknowledgement must never become an ordinary retryable transport failure because an ancillary status write failed. On acknowledgement persistence failure, retain an ambiguous/recovery-required state and reconcile conservatively; no local schema can guarantee exactly once across every remote/local crash boundary.

**Acceptance:** inject failures before send, after remote acknowledgement, during ledger completion and during status refresh. Known acknowledged delivery is not automatically resent. Old claim owners cannot complete newer claims, and the operator can inspect unresolved acknowledgement persistence.

### R4 — P1: Transport retries can send stale advice and lose timeout ambiguity

**Location:** `python-engine/partner_bot.py:124–146`.

**Reproduced:** a first-call timeout followed by 403 responses makes four POST attempts and ends as `rejected`; the earlier possible remote acceptance is no longer visible in the returned state. The same preformatted text is reused across sleeps with no validity deadline or input refresh. Configured three claim attempts can each make four network sends; “three attempts” is not three POSTs.

**Consequence:** a late message can retain old prices/size, and an ambiguous send can be treated as definitely rejected. With rate-limit delays the age can exceed the two-minute quote freshness policy. The claim helper's stored timestamp is the tick's original `now`, not the actual acknowledgement time.

**Correction:** use a delivery state machine with persistent attempt history, sticky ambiguity, a proposal expiry time, actual event timestamps, permanent/transient error classification and scheduled backoff. Recompute current proposals before retrying stale advice. Honor `retry_after` without claiming an early capped retry honored the server delay. Separate status-text retries from price-sensitive proposal retries. After exhaustion, expose a dead-letter/recovery item. One-shot daily summaries need a retry worker too; a retryable row alone does not schedule another attempt.

**Acceptance:** fake-clock tests cross proposal expiry, market close and claim lease boundaries. A previous timeout remains visible through later failures; permanent rejection stops wasteful transport retrying; stale proposals are superseded, not resent. Measure both claim attempts and actual POSTs.

### R5 — P1: Margin parser selects the wrong balance and misstates required margin

**Locations:** `node-gateway/server/services/executor.js:17–28`, `:478`.

**Reproduced:** the official response-shaped sample with cash ₹245,431.60 and live balance ₹99,725.05 selects **₹245,431.60**. Zero cash and live balance ₹5,000 selects zero; `cash:null` is coerced to zero rather than falling back or being rejected as malformed.

Kite documents raw cash and current available balance as different fields. Its order-margin API also calculates requirements for a specified order/product; full purchase notional is not universally the broker's MIS margin requirement. [Kite funds and margins](https://kite.trade/docs/connect/v3/user/#funds-and-margins), [Kite margin calculation](https://kite.trade/docs/connect/v3/margins/).

**Consequence:** the new preflight can overstate available funds or block a legitimate entry. A deliberate full-cash policy could be valid, but must be explicitly configured and labelled a policy, not presented as broker-required margin. Broker rejection still limits the overstatement; this review does not claim the check can force an unfunded fill.

**Correction:** strictly parse documented numeric fields, segment availability and current usable funds. Use broker product/order margin evidence where supported; model any additional conservative buffer separately. Exclude null/booleans/empty strings from numeric evidence. Review every entry path, including direct Python/gateway order paths, instead of assuming the `executeSignal()` hook is global. Keep broker rejection and ambiguous-placement reconciliation intact; exits remain exempt.

**Acceptance:** fixture tests for cash/live divergence, pay-in, unavailable/disabled segment, collateral policy, null/string/negative values, CNC/MIS differences and changed funds after preflight. Verify dashboard and Telegram responses carry a structured no-submission reason.

### R6 — P1 for the requested service: Material hedge changes are still suppressed by daily keys

**Location:** `python-engine/hedge_advisory.py:1174`; existing key is underlying + expiry + date, with kind in the table key. This is an existing limitation the new plan required addressing, not a newly introduced defect.

**Trigger:** an acknowledged morning futures-sizing review is followed by a material exposure increase or a closed/replaced hedge for the same underlying and expiry. The daily delivered key prevents a revised Phase-1 message. No explicit priority/coalescing queue was added. Phase 1 also awaits the informational VIX path before inspecting portfolio inputs.

**Correction:** version proposals by material exposure/hedge changes and risk-band transitions. Track the advice lifecycle separately from daily digests, coalesce superseded proposals, cap repetitive noise and prioritize meaningful protection changes. A broker-confirmed hedge holding is necessary to call protection active; a sent message is not a fill. Do not let delivery queue work delay actual protective trading operations.

**Acceptance:** unchanged exposures dedupe; a meaningful same-day change sends one updated review referencing the previous proposal; a later stale proposal is dropped; a pending digest cannot indefinitely delay an urgent risk-state change.

### R7 — P2: Shadow mode does not retain the evidence needed to graduate

**Locations:** `python-engine/hedge_advisory.py:1273`, `:1406`.

Each candidate overwrites the same `last_shadow_candidate` state key across phases and kinds. The formatted `text` is computed but not stored. The result is a latest-value diagnostic, not a history of reviewable Telegram samples. Existing readiness requires dated staging and per-kind sample evidence.

**Correction:** append shadow evaluations with immutable evaluation IDs, full rendered message, sanitized inputs, pricing/expiry timestamps, strategy version and reason. Associate human sample-review evidence with those IDs. Keep the existing latest state as a UI convenience, not the evidence ledger.

**Acceptance:** multiple kinds and days remain queryable after restart; every reviewed sample resolves to its actual rendered text and input snapshot; repeated evidence IDs cannot inflate counts. Phase-1 delivery should not wait for advanced-phase history.

### R8 — P2 / validation gate: Scheduler golden contracts fail

**Locations:** `tests/test_main_surface_characterization.py:147`, `:249`; associated `main_surface_golden.json` and `add_job_census_golden.json`.

**Correction:** deliberately update both snapshots to accept only the two intended hedge summary jobs, review the diff and add invocation tests for the summary closures. Do not update snapshots blindly to hide unrelated removals. Run these contracts in the mandatory test selection for scheduler changes.

**Acceptance:** the two failing tests pass with exactly the intended job additions and unchanged existing routes/jobs. Correct the implementation report's validation scope rather than presenting focused passing tests as full readiness.

### R9 — P2: Market-hours outages across boots are recorded but not flagged

**Location:** `python-engine/tools/runtime_audit.py:285–292`.

**Reproduced:** scheduler ticks at 10:00 and 11:00 on a weekday with different boot IDs produce `restart_gap_seconds=3600` and **no findings**. The same-epoch gap branch applies the market-hours check; the new-epoch branch does not. Process liveness has a similar cross-epoch reporting boundary.

**Correction:** assess cross-epoch elapsed coverage gaps independently of the cause. Classify as market-hours downtime/coverage unknown rather than necessarily “scheduler freeze.” Include missing first/last expected coverage and stalled counters within the same authoritative boot ID. Preserve the correct exclusion of the audit's 07:19–07:39 premarket gap.

**Acceptance:** same-boot freeze, cross-boot market outage, premarket restart and truncated capture produce distinct correct states. Do not claim continuous coverage from a final tick alone.

### R10 — P2: DR notification acknowledgement remains only HTTP acceptance

**Locations:** `python-engine/scheduler_setup.py:155`, `node-gateway/server/routes/internal.js:31`, `services/telegram.js:402`.

The gateway route ignores `sendAlert()` returning false and still replies `{success:true}`. That sender can defer retries in the background. `raise_for_status()` therefore detects HTTP failures, not successful Telegram delivery. This is a pre-existing gateway contract gap exposed by the new acknowledgement claim.

**Correction:** represent gateway acceptance, pending delivery, actual acknowledgement and failed/dead-letter outcomes separately with an event ID. Avoid duplicate submissions while gateway retries are active. Include DR structure identity, legs/expiry, exit reason and P&L in a usable message; the present close count alone is not a lifecycle recap.

**Acceptance:** gateway 200 with deferred send is recorded pending, not delivered; eventual acknowledgement/dead-letter reconciles; a DR-only close yields an identifiable report. Partner delivery remains independent of this operator channel.

### R11 — P2: EDGE validation still throws for a missing date and does not establish staleness

**Location:** `python-engine/penny_edge_engine.py:451`.

**Reproduced:** otherwise valid bars with the evaluation bar's `date` missing raise `KeyError`, despite listing `date` among required fields. The conversion excludes that field and later accesses it outside the guard. The new `stale_data` result only checks a supplied Boolean flag; it does not establish date/session freshness itself. Impossible OHLC relationships are not fully checked either.

**Correction:** validate required date and chronological/session semantics at the data boundary and pass an explicit as-of/session contract. Check low/high/open/close consistency. Preserve valid feature outputs and price-band strategy policy; keep policy rejection separate from data invalidity. Update documentation: the actual no-setup label remains `no_mr_or_mo_setup`, not `no_setup` as claimed.

**Acceptance:** missing/invalid date returns a structured reason, repeated/stale sessions fail appropriately, valid eligible bars preserve numerical outputs, and skip totals reconcile. This corrects the new diagnostic contract; it is not proof malformed bars occurred in Production.

### R12 — P2: Instrumentation and data/report remediation remain partial

**Locations:** `fno_orchestrator.py:688–863`, `penny_universe.py:460–647`, implementation report's remaining-work section.

The new durations do not separately time chain acquisition, limiter wait, DB wait or notify. A futures-quote exception occurs before its timing field is stored; if the orchestrator raises, the wrapper may have no returned summary. Histories fetched inside the DR block are counted under DR rather than a distinct history stage. These limits matter when diagnosing the 93-second overruns.

History diagnostics are improved but generic exception-text matching is not structured symbol resolution, and no data-file provisioning/cache repair or eligible-universe coverage improvement was implemented. There is also no unified outcome/report adapter. The archived P&L files are present, so the fixture work can start now; only post-promotion observations inherently need a future run.

**Correction:** emit stage outcomes in `finally` blocks, include failure/timeout timing, separate measured dependencies and retain overall elapsed time without pretending nested stage times are additive. Use broker/cache typed reasons and versioned data provisioning. Turn the new retained P&L subset into a real report regression, then extend its timestamp/attribution cases. Do not change cadence until timing evidence supports it.

**Acceptance:** slow/failed quote, history, chain, limiter and DB fixtures identify the bottleneck; September 4 report totals match; coverage changes show a measured before/after denominator. “Instrumented” must remain distinct from “optimized.”

## 4. Correction delivery plan

| Sequence | Scope | Evidence required to finish |
|---|---|---|
| 1 | R1/R2: complete input contract, recurring refresh, VIX producer and truthful exposure readiness | Synthetic multi-cycle feed → valid hedge proposal; partial/stale feeds fail accurately |
| 2 | R3/R4/R6: authoritative delivery state, expiry-aware recovery, lifecycle updates and priority | Fault-injection matrix; no known-ack duplicate; changed exposure supersedes old advice |
| 3 | R7/R8: durable shadow samples and scheduler contract completion | Reviewable sample history; scheduler contracts pass |
| 4 | R5: capital evidence correction, reviewed alongside the first releases | Real response-shaped broker fixtures; all applicable entry routes assessed; exits unaffected |
| 5 | R9/R10/R11/R12: remaining audit, notification, data and timing correctness | Reproduction cases fixed; report fixture and instrumentation assertions pass |
| 6 | Controlled GitHub promotion and actual service verification | Correct account mapping, verified input refresh and authorized canary; next eligible session reviewed |

R5 remains a release condition for calling the new margin check correct even if developed in parallel with the hedge path. The selected Python tests, gateway tests, scheduler contracts and new regression probes should be rerun after corrections. Convert probes into expected-correctness assertions; do not encode the defective outputs as desired behavior.

External decisions: the partner's actual account/source, permission to connect that source, portfolio/hedging objectives, and authorization for a concrete live canary. Engineering can proceed with source-neutral interfaces and synthetic fixtures while those remain unresolved. Do not populate Production with invented holdings, fake reviewed samples or paper trades posing as partner positions.

Release success is a current, valid, correctly sized Phase-1 review with an auditable delivery outcome, plus clear no-advice explanations when appropriate. Status-only messages are a partial release. Keep advanced sends gated until their genuine evidence requirements are met. Promote and roll back through GitHub; never edit Production directly.

## 5. Ten improvements aimed at better net returns and more useful hedge advice

These are **testable proposals, not promises of profit**. The code review and one-day audit cannot establish incremental returns. Hedging often buys downside protection at the cost of premium, upside or margin; evaluate the combined portfolio, not the hedge leg's P&L alone. Suggestions below build on existing modules rather than claiming that every underlying capability is absent.

### 1. Rank hedge alternatives by protection gained per rupee of cost

**Why it matters here:** the system can build puts, futures and several advanced structures, but emitting every eligible structure is not the same as choosing the most useful protection. The partner wants hedging to be the product's primary value.

**Build:** extend `hedge_strategies.py`/`hedge_analytics.py` with a comparison layer for no additional hedge, a protective put, a bounded put spread, an eligible collar and a futures reduction. Use the same reconciled portfolio, horizon and executable quotes. Report the combined portfolio under downward/upward price moves, IV changes and time passage. Include premium, round-trip costs, futures margin headroom, basis risk and residual exposure. Rank against an explicit user-selected loss/protection objective; do not rank solely by premium received.

**Economic hypothesis:** selecting the least costly candidate that meets the required risk reduction can reduce unnecessary hedge drag. Collars trade upside for protection; a put spread protects only over its bounded range. Those payoff trade-offs are well established, but Sentinel's ranking needs local validation. [OIC collar explanation](https://www.optionseducation.org/strategies/all-strategies/collar-protective-collar).

**Test / reject:** matched historical portfolios and quote snapshots, including stress and rally periods. Compare after-cost portfolio return, maximum drawdown, expected shortfall and protection cost. Reject a ranker that merely improves hedge-leg returns while worsening the user's chosen portfolio risk/return objective. Never describe an index hedge as a guaranteed floor on a mismatched stock portfolio.

### 2. Manage the hedge lifecycle with exposure-based adjustment bands

**Why:** the same-day deduplication limitation can leave yesterday's or this morning's advice stale after exposure changes. More frequent repeated advice is not the solution.

**Build:** extend the existing delta-rebalance logic with proposal IDs, broker-confirmed hedge holdings, target coverage bands, minimum material change and a no-trade band. Evaluate portfolio changes, expiry proximity, delta/gamma changes and depleted margin headroom. Send “maintain,” “adjust,” “replace” or “review protection” only when the risk state materially changes. Link each update to the prior proposal and explicitly distinguish advice from executed holdings.

**Economic hypothesis:** timely adjustment can reduce unintended under/over-hedging while a no-trade band limits turnover. Avoid a fixed “rebalance every N minutes” transaction rule; cadence is for observation, not compulsory trading.

**Test / reject:** replay gap days, sharp reversals, added/closed holdings and quote interruptions. Compare fixed daily hedging, frequent mechanical rebalancing and band-based changes at equal risk targets, including transaction costs. Track residual exposure, turnover and duplicate/superseded tips. Reject if costs rise without a material improvement in protection. Implement only after R1–R6 establish trustworthy inputs and messaging.

### 3. Turn partner messages into concise, versioned decision records

**Why:** status counts and isolated contract suggestions do not tell the partner why a hedge matters or whether it remains current. A better tip can prevent an obsolete or misunderstood action even without a better prediction model.

**Build:** each advice card should state the exposure being protected, why now, preferred structure, an alternative when suitable, units/lots, expiry, executable quote time, estimated cost, coverage/residual risk and what invalidates it. Include a valid-until time, change-from-previous explanation and a link/reference to the calculation. Label scenarios as scenarios and probabilities only when calibrated. Keep “no liquid hedge available” distinct from “no hedge necessary.”

**Economic hypothesis:** improved clarity and timeliness can reduce duplicate, late and wrong-size decisions. Acknowledgement by Telegram proves delivery, not reading or acting; actual execution feedback must come from a reliable source or be marked self-reported.

**Test / reject:** blind review of rendered samples across eligible, stale and no-action cases; measure comprehension, stale-action incidence, duplicate proposals and cost difference between quote-at-generation and acknowledged execution. Report any observed benefit separately from selection bias in who acts. Reject extra message fields that increase confusion without improving decisions. Extend `hedge_formatters.py` and the durable advice/evidence ledger.

### 4. Make execution quality and total costs first-class strategy inputs

**Why:** September 4's Penny gross advantage was tiny and Momentum/FNO lost money. A strategy that looks profitable at a mid-price can lose after spread, fees and delay. The repository already has `fno_costs.py`, `cost_schedules.py` and executable-side hedge quotes; extend and calibrate those mechanisms.

**Build:** record signal timestamp, quote age, spread/depth, order intent, broker acknowledgement, fill/partial-fill prices, cancellations and total fees by product. Estimate slippage by liquidity, order size, time of day and volatility. Use an effective-dated fee schedule and contract metadata. Compare limit placement alternatives in shadow; do not assume unfilled limits have zero opportunity cost or favorable selection.

**Economic hypothesis:** avoid trades where realistic trading friction consumes the estimated edge, and reduce avoidable implementation shortfall on those retained. Better fills are measurable without claiming a new predictive signal.

**Test / reject:** apply conservative BUY-at-ask/SELL-at-bid baselines, cost stress and actual available fill data. Compare net expectancy at matched trade opportunities, fill rate and adverse selection after fills. Reject filters that look better only because difficult missing fills were excluded. Broker margin calculations should support affordability, not be mistaken for transaction profit. [Kite order/basket margin API](https://kite.trade/docs/connect/v3/margins/).

### 5. Evaluate a regime-conditioned strategy selector with a genuine abstain option

**Why:** Momentum, mean reversion and range-oriented option structures have different premises. Sentinel already has regime and shadow modules; adding another classifier without checking current behavior risks duplication and overfitting.

**Build:** first audit existing dispatch. Define a small, predeclared set of states using only information available at decision time: directional persistence, realized volatility, breadth and liquidity. Compare continuation, mean-reversion and existing defined-risk candidate families within their intended regimes. Permit no new entry when classification confidence or data quality is inadequate. Keep portfolio hedges governed by exposure, not by a speculative directional score alone.

**Economic hypothesis:** avoid paying for a strategy in conditions where its historical net expectancy is weak. This is a hypothesis to test, not a reason to loosen the low-acceptance gates seen in the audit.

**Test / reject:** chronological walk-forward blocks across multiple conditions; freeze features/thresholds before each test block. Compare to current dispatch and a simpler fixed allocation at equal risk. Require stable improvement across multiple held-out blocks after costs, not one profitable regime slice. Retain all failed variants in the experiment registry. Use `regime.py`, Momentum/FNO shadow modules and existing backtest infrastructure.

### 6. Test time-stop and exit policies using the full price path

**Why:** the audited Momentum positions and single-leg FNO trade exited via time stops. That supports investigation, not a conclusion that time stops are wrong or should simply be extended.

**Build:** collect maximum favorable/adverse excursion, time to excursion, quote quality and continuation after the current exit. Compare the existing rule against a small declared set: unchanged hard stop plus a progress-based time stop, volatility-adjusted holding window, and conservative trailing behavior. Maintain hard-flat and protective-stop constraints. Use intrabar ordering conservatively when both stop and target could have occurred.

**Economic hypothesis:** exit losing/no-progress trades earlier when supported by evidence, while allowing demonstrably persistent winners room. Any longer hold must account for increased exposure and turnover capacity.

**Test / reject:** paired replay on identical entry opportunities, not separately cherry-picked trades. Measure net R expectancy, tail loss, turnover, holding time and missed next opportunities. Use held-out dates and cost stress. Reject an apparent gain explained by a few carryover outliers or an optimistic intrabar fill assumption. Build on the existing momentum/FNO backtests and outcomes; do not fit a new exit to the three September 4 Momentum trades.

### 7. Allocate risk across correlated divisions and positions, not isolated signal counts

**Why:** a Momentum long, FNO long and Penny/EDGE long may all share market downside even if they use separate bookkeeping pools. Separate pool labels do not establish independent risk.

**Build:** add an account-aware aggregate exposure/risk-budget view over the existing division risk controls. Track market/sector concentration, directional delta, estimated gap loss, liquidity constraints and common underlying exposure. Keep paper simulations separate from funded live books, and the partner's portfolio separate from the operator's account. Treat a hedge as reducing risk only to the extent supported by its actual holdings and stressed payoff, not because its strategy name contains “hedge.”

**Economic hypothesis:** reduce avoidable correlated drawdowns and allocate scarce capital to stronger validated opportunities. Start with simple concentration/volatility caps before attempting optimized covariance weights or aggressive Kelly sizing.

**Test / reject:** compare fixed existing pools and capped allocation on the same opportunity stream, with time-varying correlations and stress shocks. Measure portfolio net return, drawdown, expected shortfall and opportunity loss. Reject allocations that depend on unstable correlations or recent winners. Require improvements at a comparable risk level; merely taking more leverage is not a better strategy.

### 8. Add event- and liquidity-aware eligibility with historical calendars

**Why:** scheduled events, expiry transitions and thin quotes can change whether an otherwise valid strategy is executable. Existing event/macro calendars are a useful starting point, but their absence must not be converted into certainty that no event exists.

**Build:** version known-at-the-time results/macro/corporate-action calendars and contract metadata. Define strategy-specific treatment: reduce or abstain from new unvalidated event exposure, tighten stale-quote requirements, and review existing protection near expiry or planned events. Record calendar completeness. Do not automatically buy volatility because an event is near or sell it because IV looks high; market prices may already reflect the event.

**Economic hypothesis:** avoid trades whose gap/slippage risk is not represented by the normal stop model and avoid obsolete contracts. Keep event hedges separate from speculative straddle ideas.

**Test / reject:** replay event and matched non-event windows using only then-known calendar entries, bid/ask prices and actual instrument expiries. Report missed winners as well as avoided losses and premium drag. Reject blanket filters that only improve results through hindsight. Apply local instrument settlement/lot metadata; US options education supports payoff intuition, not Indian settlement assumptions.

### 9. Build a point-in-time, quality-controlled research and tradable universe

**Why:** 6,012 history skips and 484 coarse EDGE rejections leave uncertainty about opportunity coverage. Better labels alone cannot recover missed opportunities or establish trustworthy backtests.

**Build:** store daily eligible-universe snapshots, source dates, instrument-token/series mappings, delistings/renames, corporate actions and per-symbol data-quality reasons. Separate strategy price eligibility from invalid data. Preserve synchronized option-chain bid/ask/OI/expiry snapshots for future hedge and FNO testing. Extend the current history/cache work; do not simply expand to all raw symbols.

**Economic hypothesis:** recover valid opportunities lost to avoidable data errors and reduce selection bias when judging strategies. Do not equate a bigger universe with higher profitability.

**Test / reject:** compare before/after eligible coverage, freshness, false candidates, runtime and after-cost shadow outcomes. Keep historical membership point-in-time so delisted losers are not silently removed. Do not assume continuous futures data supplies a historical options order book: Kite's continuous history support is scoped, and expired instrument mappings need preservation. [Kite historical-data documentation](https://kite.trade/docs/connect/v3/historical/).

### 10. Introduce a challenger promotion process that measures net economic benefit

**Why:** the system already contains many strategy, shadow and backtest components. Trying more combinations increases the chance of selecting a lucky result. Operational fixes and research improvements need different acceptance criteria.

**Build:** register every experiment before evaluation: hypothesis, versions, data period, cost model, benchmark, risk budget, primary metric and rejection rule. Use chronological development/validation/untouched test periods, with separation around overlapping trade-label windows. Count tested variants. Compare a challenger against the current implementation on matched opportunities; retain negative experiments. Use uncertainty estimates with dependence-aware resampling and a multiple-testing adjustment such as Deflated Sharpe where appropriate. Its purpose is to reduce selection bias, not certify future profit. [Bailey and López de Prado, Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf).

**Economic hypothesis:** stop promoting lucky backtests and spend development/capital on effects that survive realistic testing. For alpha use after-cost expectancy and portfolio return at matched risk; for hedges use combined-portfolio drawdown/tail reduction subject to a predeclared cost budget; for partner tips use timely valid advice and actual outcome feedback.

**Test / reject:** promotion requires adequate independent observations, multiple held-out conditions, cost stress, stable parameters and no material operational regression. Low sample size means insufficient evidence, not an invented minimum win rate. Follow successful shadow validation with a separately authorized limited rollout and predefined rollback criteria. No fixed return uplift is claimed for any of these ten proposals.

## 6. Recommended investment order and reporting

First complete the hedge corrections and improvements **1–3**: they directly serve the partner's stated priority. Develop **4** and **9** as measurement/data foundations, because unreliable costs or history invalidate strategy research. Then evaluate **5–8** under the experiment discipline in **10**, which should be established before running the comparisons.

For every proposal, publish an evidence card: baseline/version, sample coverage, excluded/missing cases, net result with uncertainty, risk/drawdown change, extra costs and deployment status. Distinguish **code implemented**, **synthetic tests passed**, **shadow validated**, **broker/transport verified** and **measured Production benefit**. None of those labels should be substituted for another.

The most defensible current expectation is improved reliability and more actionable hedge information after corrections. Whether that becomes greater net profit or lower losses must be measured from the combined portfolio over an adequate, representative period.
