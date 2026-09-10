# Trading Sentinel: round-four verification and income-system roadmap

Reviewed 6 September 2026, IST. Dev branch `codex/production-correction-hedge-p0`, commit `c19aec65717591b5ab5c5f35d8d028cef97ea91e`.

## Decision

The round-three work is substantial and mostly implements what its report describes. It is not yet a clean release candidate: targeted failure probes found remaining delivery-state and snapshot-consistency defects despite a green regression suite. Correct those before enabling automatic recovery in Production.

Your intended product is a low-maintenance trading business: better entry decisions, better management of open trades, controlled capital allocation, and reliable accounting of money actually earned. That is the right objective for the next development phase. “Best buy and best sell” must mean a better decision using information available at the time, not knowledge of future highs and lows. No implementation or backtest can promise dependable monthly income.

The plan below prioritizes making existing intelligence effective and measurable. It does not recommend increasing leverage, loosening safety filters merely to create activity, or switching on additional F&O strategies to meet a monthly target. Hedging remains the partner's highest-priority message category.

## Scope, evidence and limits

- Inspected the complete application diff from `c96345f` to `c19aec6`, the affected tests, the remediation log, adjacent hedge routes, and selected entry/allocation/research/exit components.
- Independently ran **285 Python tests: all passed**, with one existing Starlette lifespan deprecation warning. This is a broader selected suite, not every test in the repository.
- Independently ran **46 gateway executor tests: all passed**. Gateway code was not changed by this commit.
- Ran five additional deterministic offline failure probes against temporary SQLite storage and mocked transport. Results and reproducible script are in `docs/review-2026-09-06-round4/`.
- Production Git identity remains `89926fb`, with pre-existing untracked `migration/`. No Production mutation, broker order, partner message, deployment or process restart was performed.
- This is a remediation and architecture audit. I did not collect a fresh live trading P&L series or prove that partner delivery has resumed. Historical production findings in earlier audits are not substituted for new performance evidence.
- The earlier untracked `2026-09-06-hedge-round-three-review-and-next-plan.md` is preserved. This round changes only documentation and offline review artifacts, not application code.

Python suite: hedge advisory, analytics, strategies, formatters, Phase 3, readiness, routes, partner bot/input refresh/orchestrator/audit hardening, scheduler closures/surface characterization, F&O orchestrator/hourly scheduler, Penny EDGE/universe refresh, runtime audit, ops metrics and scheduler tick. Use the corresponding `tests/test_*.py` files. Gateway: `npm test -- --runInBand tests/unit/executor.test.js`.

## What is now materially better

| Reported correction | Assessment |
|---|---|
| Immutable single-account binding | Implemented for adapter snapshot acceptance, including transaction-level comparison with a persisted binding. This prevents changing an accepted binding through later adapter settings. Other mutation paths still need version invalidation, below. |
| Read-consistent portfolio input | Envelope and open positions are read in one SQLite transaction. This fixes the common mixed-read path; explicit absence is still mishandled by the gate fallback. |
| Post-dispatch transport ambiguity | Partner transport exceptions are conservatively classified. Abandoned claims become manual recovery when reclaimed after lease expiry. A subsequent ledger-write failure still has an unsafe exception path. |
| Acknowledgement persistence failure | Acknowledged delivery no longer falls into ordinary retry when both acknowledgement persistence paths fail. This is a useful correction. |
| Recovery revalidation | Phase 1 checks current account/snapshot and session/calendar; advanced rendered text is retired. Retirement ownership and proposal lifecycle remain incomplete. |
| Stable decision identity | Routine mark/Greek changes no longer generate new Phase-1 identity. Side, lot size, expiry, contracts and account are included. Distinguishing a decision from a delivery generation is now essential. |
| Mark/VIX timestamps | Adapter normalization rejects supplied stale/future timestamps. Do not generalize this to all manual mutation paths or all underlying data provenance. |

## Remaining corrections

### R1 — P0: preserve ambiguity when the authoritative failure write itself fails

Evidence: `python-engine/hedge_advisory.py:567`, `_send_claimed_review`. A timeout result is passed to `_fail_claim`. If that database operation raises, the outer exception handler invokes `_fail_claim` again with `internal_error`. If the second write succeeds, it schedules a retry and clears the transport claim despite the known ambiguous outcome.

Offline probe: inject one failure in `_fail_claim` after an ambiguous timeout, then invoke the send path two minutes later. **Observed two mocked POST-equivalent calls**, not one. The earlier correction handled ancillary status writes, not this authoritative-write failure.

Correction: retain transport state in the enclosing scope and never downgrade post-dispatch uncertainty. On persistence failure, leave durable in-flight intent intact or persist a manual-recovery marker; a generic handler must distinguish failures before dispatch from failures after dispatch. Prefer one explicit state-transition function over exception branches that invent a new classification.

Acceptance: timeout plus first failure-write exception; disconnect plus failure-write exception; acknowledgement plus both acknowledgement-write failures; cancellation/process death after dispatch. All uncertain cases remain non-retryable automatically. A definitely pre-dispatch failure may retry under policy. Test the actual orchestrated send path, not just `_fail_claim` independently.

### R2 — P0: make retirement terminal and conditional on ledger ownership

Evidence: `_claim` at `hedge_advisory.py:270` blocks manual/expired/permanent states but does not block `retired`. `_retire_pending_delivery` at line 701 updates any undelivered row, clearing `claim_token`, without comparing the state/version that the recovery worker read.

Offline probes: a retired row can acquire a new claim; a retirement call can clear an independently acquired transport-started token, making its later acknowledgement completion fail. The latter proves the unsafe update behavior; actual overlap depends on worker scheduling.

Correction: define terminal states centrally. Retire using compare-and-set on expected row revision/state and only when no other worker owns a live claim. Claim acquisition, retirement and acknowledgement must share a documented transition table. Treat stale worker updates as no-ops with an audit event.

Acceptance: recovery reads a retry row, the regular tick claims it, then recovery tries retirement. The live token must survive and its acknowledgement must complete. Every terminal state rejects reacquisition of that delivery generation.

### R3 — P1: separate economic decision identity from delivery generation

Evidence: `_claim` checks the stored expiry before merging fresh detail. An expired record blocks the same key indefinitely. Stable `_proposal_identity` intentionally produces the same key for an unchanged contract/lot decision across normal refreshes.

Offline probe: create an expired unsent decision, then supply a fresh validity window under the same economic key. The fresh attempt is blocked. This creates silent loss of valid advice after a transient delivery problem. Simply allowing retired/expired rows to be overwritten would undo safety and auditability.

Correction: persist separate `decision_id`, `generation_id`, `exposure_lifecycle_id` and `supersedes_generation_id`. A terminal delivery generation stays immutable. Freshly evaluated advice can create a new generation only when policy permits it. Delivered decisions should not repeat for routine refreshes; manual ambiguity must block equivalent generations until resolved. A genuinely new exposure lifecycle may require new protection even if its contracts look familiar.

Acceptance: unsent expired generation followed by fresh eligible evaluation; delivered decision followed by unchanged refresh; ambiguous generation followed by refresh; close/re-entry; materially resized hedge. Verify desired suppression and desired renewed delivery separately.

### R4 — P1: keep explicit absence inside the consistent-read boundary

Evidence: `_whole_portfolio_input_reason` at line 1359 uses `None` both for “caller did not provide a snapshot” and “the consistent read found no snapshot.” In the latter case it loads the latest envelope on another connection.

Offline probe: provide an explicitly absent snapshot and empty rows, while the fallback loader returns a newly accepted complete snapshot. The gate returns `VERIFIED_EMPTY_PORTFOLIO`, although those rows were not read with that envelope. This is an initial-acceptance/concurrency edge case, not evidence that every evaluation is inconsistent.

Correction: require `PartnerEvaluationInput` as the gate argument, or use a distinct sentinel for omitted arguments. Explicit absence must return `NO_ACCEPTED_PORTFOLIO_SNAPSHOT` without another read.

Acceptance: inject first snapshot acceptance between loader return and gate evaluation; the old input remains unavailable. The next full read sees the accepted version.

### R5 — P0 before unattended use: make every portfolio mutation invalidate or advance its revision

Code-review finding: authenticated manual reconcile/close routes still call `reconcile_partner_position` / `close_partner_position` directly (`hedge_analytics.py:1645`, `routes_hedge.py`). Those writes do not advance the accepted snapshot watermark. Phase-1 recovery compares account and snapshot ID, not a portfolio mutation revision or rebuilt decision.

Consequence: a manual quantity/Greek change can leave the same snapshot ID attached to different current rows. Consistent reads prevent torn reads; they do not prove that the rows still represent that accepted envelope. A still-open, actionable portfolio could therefore pass recovery with stale rendered hedge sizing. Invalid rows are also omitted by `_row_to_position` in the evaluation loader; omission should not be interpreted as proof of completeness.

Correction: introduce a monotonic account portfolio revision advanced by every mutation, or mark the accepted envelope dirty until a fresh complete reconciliation. Bind advice to that revision. Return invalid-row counts/reasons and fail portfolio readiness on invalid open records. At final send eligibility, check that the evaluated revision is still current; define behavior when a refresh occurs during chain acquisition.

Acceptance: accepted complete snapshot, then manual resize; manual close of one of several positions; manual new position; invalid stored open row; refresh during review construction. Old advice must not remain eligible merely because snapshot ID is unchanged. These scenarios need integrated tests; this finding is from code inspection, not one of the five executed probes.

### R6 — P1: finish recovery operations and real input lifecycle

The recovery scan only processes `retry_scheduled` rows. It does not proactively sweep abandoned transport-started rows into an operator queue; conversion currently depends on a later claim attempt. One malformed JSON object shape or row-processing exception can also stop the loop. Status-summary recovery is deliberately retired, so define how a missed daily status becomes visible and how a fresh summary is generated.

Implement a bounded sweep with per-row isolation, typed ledger parsing, abandoned-claim alerts, reason counters and an operator resolution procedure. Add source/account migration documentation. Complete the real adapter's new-position, close/re-entry, corporate-action and external-ID mapping contract. “Provide an adapter URL” is not sufficient for a sustainable producer.

Acceptance: mixed valid/corrupt ledger rows; process restart with an abandoned claim that no future strategy rebuild selects; rejected adapter binding; new/reopened holding; expired quote after 429. Report freshness, last useful decision, last acknowledged delivery and manual-recovery backlog independently.

### Joint acceptance, not another collection of isolated patches

Create one offline integration harness: accepted account inputs → real strategy builder → decision generation → claim → mocked Telegram → injected crash/write failure → input mutation → recovery → next regular tick. Assert broker/transport call counts, immutable attempt history, revision ownership and user-visible reason. Run two workers with barriers for race tests. Retain the currently passing suites and add these missing scenarios.

## What “smartest on this infrastructure” should mean

Existing code already goes beyond a plain screener. `engine.py` assigns scores and cost checks; `portfolio.py` ranks momentum by `net_ev` and swing candidates by score after positive-EV filtering; `penny_edge_engine.py` ranks candidates; `risk_engine.py` sizes positions; `momentum_exits.py` manages exits; `backtest_lab.py` has immutable research runs. The next step is validating their estimates and connecting their decisions to outcomes.

Two promising components appear underused: `strategy_health.py` explicitly says its status is advisory, and the repository searches in this review found no production caller of that health evaluator or `exit_quality.py` beyond tests/comments. Verify integration before implementing another health dashboard or exit analyzer. Comments containing historical performance numbers are leads for research, not freshly verified results.

The proposed operating loop is:

`point-in-time data → feasible candidates → net outcome estimate → portfolio choice → entry policy → broker-confirmed position → exit policy → reconciled net outcome → controlled research update`

Every stage records a decision ID and version. “Wait,” “hold cash,” “reduce risk,” and “do nothing” are valid choices. More indicators, more LLM calls or more trades do not establish an edge.

### Architecture within the desktop stack

Retain Python for deterministic features/research and Node for broker execution. Keep the live path small and restartable. Use the existing database/research archive, with append-only decision events and explicit schema migrations; avoid adding infrastructure before profiling shows a need.

Run bar-based inference on completed candles, not high-frequency prediction. A reasonable research starting point is liquid cash instruments and 15–60-minute/swing decisions whose expected holding period is much longer than measured data-to-order delay. This is a proposed fit to desktop constraints, not a claim that those strategies are profitable. Keep F&O execution constrained by its existing readiness gates; hedge recommendations and directional alpha have different objectives.

Use market hours for data, positions, exits and small inference jobs. Run feature refreshes incrementally and larger experiments after market hours with bounded CPU/memory/concurrency. `docker-compose.yml` already defines resource caps; its historical host comments are not a fresh hardware benchmark. Measure actual p95/p99 job delays, memory and broker latency before setting budgets. Queue exits/protective actions ahead of new-entry research and routine reports.

Use an LLM for explaining recorded decisions, reviewing failures and proposing offline experiments. If later used to extract event/news facts, retain source, publication time, confidence and validation. It must not invent prices, bypass deterministic exposure limits, or edit/promote trading rules autonomously in the live loop. Small calibrated statistical models are cheaper and easier to evaluate for the numerical ranking task.

## Ten prioritized intelligence improvements

### 1. Establish one trustworthy net-outcome and decision ledger

Record candidate time, data version, strategy/policy version, entry/stop/exit intent, quantity, rejected alternatives, estimated costs, broker order/fill IDs and all partial fills. Reconcile realized P&L with the broker and keep mark-to-market separately. Track paper, shadow, live and partner-executed outcomes separately. Log a sampled set of rejected candidates so selection quality can be assessed without retaining every repeated scan.

Reuse `signal_log.py`, `fno_signal_log.py`, `penny_execution_journal.py` and `backtest_lab.py`; first map their IDs rather than create competing P&L truth. Enforce reconciliation tolerance explicitly and explain every residual.

Success: every live outcome traces to its decision and every open risk to broker-confirmed quantity. This unlocks reliable learning; it is not itself an alpha claim. Broker order acceptance is not proof of execution. [Kite order documentation](https://kite.trade/docs/connect/v3/orders/).

### 2. Calibrate candidate value instead of trusting score labels

Estimate net outcome distributions conditioned on strategy, regime and liquidity. Start with simple historical bins and shrink small samples toward a conservative baseline; compare a regularized model only when data supports it. A score of 80 is not automatically an 80% win probability.

Measure both probability and payoff: `expected net value = P(win) × average gross win − P(loss) × average gross loss − expected total costs`, with a more complete distribution for partial exits/timeouts. Separate uncertainty in the estimate from normal trade volatility. Rank only feasible positions and allow no trade when evidence is weak.

Success: chronological held-out calibration and improved net value per deployed rupee versus current ranking. Compare like-for-like risk, not larger position sizes. Do not fit labels using information unavailable at the candidate time.

### 3. Add a bounded entry-timing policy

For the same candidate, compare immediate entry, a defined pullback limit, and a confirmation entry. Each policy has a price ceiling, deadline, spread limit and invalidation condition. Track missed trades and adverse selection as well as fill price improvement; an unfilled winning trade is a real opportunity cost.

Use existing completed-bar data and broker execution controls. Begin in shadow with a small fixed set of alternatives. Record the first realistically executable quote after the decision; never assume fills at a bar's best price.

Success: higher net expectancy after realistic nonfills, slippage and delay. Cancel/replace and ambiguous broker states remain governed by the executor, not by model enthusiasm.

### 4. Make exit decisions depend on the remaining opportunity

Integrate `exit_quality.py` with actual trade paths and compare current exits with a small set of policies: fixed stop/target baseline, volatility trail, thesis invalidation, and time decay. Preserve protective stops. Evaluate “hold versus close” using features available at that point, rather than choosing the best exit retrospectively.

Use MFE/MAE and bounded post-exit paths as diagnostics. MFE is an upper bound, not capturable profit. Optimize net outcome/drawdown, not proximity to the eventual high. Test gap-through stops, same-bar stop/target ambiguity, partial exits and expiry/session constraints.

Success: improved held-out net outcomes at the same initial risk, with no worse unprotected-position behavior. This should be an early research priority because the repository already contains exit-management machinery.

### 5. Select strategy families by evidence and market state

Retain a small baseline set, for example existing trend/momentum and mean-reversion candidates where supported by the current books. Compare their performance conditional on trend, volatility, liquidity and event conditions. Use stable state transitions/hysteresis, and distinguish unavailable data from an unfavorable regime.

Keep strategy selection and risk limits separate. A regime model should not silently expand leverage or unlock an unvalidated options strategy. Freeze policies during a forward evaluation period.

Success: the selector beats a static allocation and a simple baseline across held-out periods after costs. Reject a complex selector if it merely explains historical regimes better.

### 6. Allocate capital across the portfolio, including cash

Extend existing pool/sector limits with marginal portfolio risk, overlapping instruments, correlated exposure and capital consumed by pending orders. Compare candidates in net rupees, risk and expected holding time using conservative estimates. Do not mechanically maximize EV divided by holding time; that can overfavor noisy short trades.

Begin with deterministic capped allocations and a cash reserve. Add uncertainty-aware ranking only after calibrated data exists. Minimum lot sizes and broker margin can make an otherwise attractive F&O idea unsuitable for the available account.

Success: better net portfolio return at matched drawdown/risk, fewer correlated losses and fewer rejected orders. No automatic “recover losses by sizing up” behavior.

### 7. Turn strategy-health evidence into controlled exposure changes

Wire the existing health evaluator into a persisted daily assessment with a clearly owned path to existing risk controls. Distinguish a broken producer, zero eligible opportunities, and actual economic deterioration. Repeated readings of the same trades must not masquerade as new independent evidence.

Use sufficient completed outcomes and uncertainty ranges; initially recommend reductions, then automate bounded demotion after validating behavior. Re-promotion requires forward evidence and the normal versioned release path. Exits remain active when entries are disabled.

Success: less capital exposed to deteriorating strategies without frequent false shutdowns. Test unknown-data and zero-activity periods explicitly.

### 8. Make partner hedging a portfolio-protection service

Prioritize action-required protection changes, then position-specific reviews, then routine context. Each card states exposure covered, proposed action/units, estimated cost, residual risk, validity, reason for acting now and what invalidates the recommendation. Compare a feasible hedge with reducing underlying exposure and taking no action. Track partner confirmation separately from Telegram receipt.

Use an explicit protection budget and stress scenarios. Premium received is not profit while short-option risk remains open. Hedging may reduce drawdown while lowering average return; judge it on the user's portfolio objective, not raw tip count.

Success: fewer duplicate/obsolete instructions, shorter time to communicate material risk, and measured net protection value for confirmed holdings. Adapter lifecycle and delivery corrections are prerequisites.

### 9. Add a controlled research and promotion loop

Use the existing lab to freeze data, code, parameters, assumptions and all attempted variants. Employ chronological walk-forward splits, with separation for overlapping label horizons; keep a final untouched test period. Include survivorship/corporate-action checks, realistic charges, spreads, delay and nonfills. Use block-based uncertainty estimates appropriate to correlated outcomes.

Compare simple baselines, randomized-entry controls where appropriate, and current champion policies. A fixed number of trades is not universal proof: require both enough independent evidence and exposure to relevant regimes. Account for the number of strategies tried; attractive backtests can result from selection bias. [Bailey and López de Prado, Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf).

Success: an auditable decision to promote, reject or continue observing. Start with one challenger at a time. Automatic live self-modification is outside this plan.

### 10. Build an income-readiness and low-maintenance operating layer

Report reconciled net live P&L, maximum drawdown, underwater duration, exposure, costs, reserve requirements, manual incidents and minutes of owner intervention. Include stale-data and unprotected-position alerts, startup reconciliation, tested restore/rollback and missed-job visibility. Confirm broker protective orders survive a desktop outage where supported; they do not guarantee fills through a gap.

Separate living-expense withdrawals from trading decisions. Define withdrawable cash only after realized settlement, obligations, tax provision, capital floor and risk reserves. Do not force a trade to meet a daily/monthly income target. Model adverse sequences and withdrawals together; an average profitable backtest can still run out of usable capital.

Success: consistent accounting and fewer interventions across forward operation, followed by an evidence-based decision about sustainable withdrawals. Income readiness requires a meaningful live record; a month of green tests or paper profits is insufficient.

## Capital and income feasibility — updated with your funding plan

You specified approximately **₹8,000 for current testing**, originally funded with ₹5,000; possible subsequent funding of **₹20,000–₹50,000**, then **₹1 lakh**, and eventually **₹5 lakh** if the evidence convinces you. Your return preference is to earn as much as feasible while mitigating risk. You have not specified a numerical drawdown limit or fixed monthly withdrawal. Those remain open policy inputs; the preference is not authorization for leverage or an assumed loss budget.

The difference between ₹5,000 and ₹8,000 must not be reported as ₹3,000 profit until deposits, withdrawals and net trading results are reconciled. The ledger needs external cash-flow events so funding cannot inflate performance or reset strategy drawdown history.

| Capital stage | Purpose and scope | Evidence required before increasing |
|---|---|---|
| About ₹8,000 now | Operational pilot. Use only affordable cash-equity trades within explicit risk limits; keep derivative strategy research/partner hedging evaluation separate from this tiny live book. Preserve a cash buffer and allow zero trades. | All fills/positions reconcile; no unexplained P&L; protective/exit behavior and restart recovery proven; realized costs measured; no unresolved P0 issue. A profitable handful of trades is not sufficient. |
| ₹20,000–₹50,000 | Gradual increase in the same validated book, not a simultaneous new-strategy launch. Continue tracking the original pilot as its own capital regime. | Positive net forward evidence with uncertainty reported; tolerable peak-to-trough drawdown; stable slippage and owner intervention; no deterioration at the first size increase. |
| ₹1 lakh | Broader portfolio allocation only where diversification is affordable and supported by independent evidence. | Incremental exposure improves portfolio outcomes at matched risk; pending orders and correlated positions fit the account budget; tested capital rollback rules. |
| Up to ₹5 lakh, future | A controlled income-candidate portfolio. Evaluate derivative eligibility separately using current broker margin, lot sizes, tail risk and demonstrated strategy evidence. | Sustained live net performance and cost/withdrawal stress analysis; adequate reserves; user-agreed loss limits; no automatic jump merely because the account balance reaches a threshold. |

Capital additions should be separate owner-approved events. A model may recommend a stage change with evidence, but must not transfer funds, raise its own risk limits or turn on new strategies to meet a growth target.

### Make small-account economics explicit

Size on rupees at risk, not just the number of affordable shares. For an unlevered long cash trade, a starting feasibility calculation is `quantity × (entry − stop) + estimated round-trip costs + slippage allowance ≤ approved trade-risk budget`, also constrained by available cash and portfolio risk. The stop is not a guaranteed loss cap through gaps. Recompute costs after rounding/down-sizing rather than retaining the economics of an unaffordable full-size proposal.

For scale illustration only, a 0.25% trade-risk budget would be ₹20 at ₹8,000 and ₹1,250 at ₹5 lakh. This is **not an activated or agreed risk setting**. At the smaller size, fees/spread and whole-share rounding can consume much of the budget; the correct result may be no trade. Do not increase leverage or lower liquidity standards to manufacture opportunities. Use paper/shadow observations to accumulate research evidence when the live account cannot trade a setup economically.

Before any scale-up, define maximum acceptable account drawdown, daily loss limit, total open risk, cash reserve, and the response to each breach. Report prospective loss in both rupees and percent. Entry suspension must continue managing exits. Conservative defaults can be proposed in a separate risk-policy review, but this document does not infer your numerical tolerance.

Use `required annual withdrawal yield = 12 × monthly withdrawal / deployable capital` as a feasibility check, before tax, reserves and costs. At the future ₹5 lakh balance, ₹5,000 per month implies 12% per year in withdrawals; ₹10,000 implies 24%; ₹20,000 implies 48%. These are arithmetic illustrations, not forecasts, sustainable withdrawal rates or recommended targets. Reserves reduce deployable capital and losses can interrupt withdrawals.

During the pilot, prefer measuring reinvested net results and reliability over imposing monthly income withdrawals. Do not back-solve a risk percentage that forces a desired income. First establish what the strategy earns net at tolerable risk, then assess whether capital and withdrawals are compatible. The system should be able to say “insufficient evidence” and “no affordable trade.”

## Proactive trading requirement — added after your activity clarification

You explicitly do not want a dormant system that trades once in five days because of avoidable restrictions, narrow opportunity discovery or operational defects. You accept some risk and want faster profitable growth. **Proactive opportunity discovery and explainable inactivity are now product requirements**, alongside capital protection. A low trade count is a reason to investigate, not automatic evidence of either prudence or a defect.

The objective is to maximize net growth within an agreed risk budget, with healthy opportunity coverage. There is no credible promise of massive fast profits with little risk. We can improve opportunity capture, reduce execution waste and learn faster; we cannot mandate the market's return. Higher activity must demonstrate incremental value after costs. Research on momentum also documents substantial crash exposure, so a familiar strategy name does not establish low risk. [Chabot, Ghysels and Jagannathan, NBER](https://www.nber.org/papers/w20660).

### A concrete small strategy basket to test

Research these three complementary sleeves together against a single-strategy baseline. Enable live sleeves only as their evidence passes; they share one account risk budget. These are proposed strategy specifications, not newly proven proprietary alpha or a claim that this is already the best basket.

| Sleeve | Opportunity and entry hypothesis | Exit and invalidation | Why include it / main failure |
|---|---|---|---|
| Trend pullback and continuation | In liquid stocks with positive market/sector context, monitor relative strength and an established trend; enter after a controlled pullback stabilizes and price resumes, using completed bars and an explicit limit/deadline. | Structural stop set before entry, no averaging down; compare volatility trail with thesis/time exit in replay. | Captures trending days without depending solely on fresh breakouts. Can suffer repeated whipsaws and trend reversal. Build on existing momentum/regime features. |
| Range reversion after stabilization | In a demonstrably non-trending regime, test liquid stocks stretched from a defined intraday reference, requiring stabilization before an affordable long entry. Exclude known event-driven repricing and failed data. | Exit near the reference or earlier on invalidation/time expiry; strict downside stop. | Adds a different opportunity source on range days. A falling stock is not automatically cheap; a range can break. Existing mean-reversion code is a starting point, not validation of this intraday variant. |
| Volatility-contraction breakout | Identify a predeclared consolidation/contraction with relative strength; enter a confirmed expansion above the range or its retest, subject to volume, spread and no-chase limits. | Exit a failed breakout promptly; compare a runner trail and bounded time stop. | Finds transitions from quiet periods into movement. False breakouts and gaps are central risks; it overlaps with momentum and must be clustered accordingly. |

Keep intraday and overnight versions as separate policy IDs, cost assumptions and tests. No accidental conversion of a failed intraday trade into an overnight holding. At ₹8,000 the basket is a choice among strategies, not an instruction to split cash into three tiny simultaneous positions. Use liquid, affordable cash instruments; a low share price alone is not an advantage. Keep partner hedging as a separate protection objective and do not use F&O leverage to fill an activity shortfall.

Start by reusing `engine.py`, `regime.py`, `penny_edge_engine.py`, `portfolio.py`, existing exit modules and the research lab. Evaluate the proposed sleeves on a suitable liquid universe; do not transplant Penny thresholds into liquid stocks or intraday bars without new tests. Freeze a small parameter set for each sleeve before evaluating an untouched period. Also test the basket excluding each sleeve: a sleeve earns capital only if it contributes net value or useful risk diversification.

### The system must actively work on finding opportunities

1. Build a point-in-time liquid/affordable universe before the session, then maintain an intraday watchlist from fresh data. A research starting range is 50–100 liquid symbols, subject to measured data/API and scheduler capacity; this is not a required blind expansion.
2. Re-evaluate shortlisted candidates on each relevant completed bar, initially testing a 5–15-minute cadence for intraday sleeves. Data freshness, execution latency and costs must support the chosen horizon. Reuse incremental features; do not reload entire histories on every scan.
3. Keep near-ready setups with explicit trigger prices, validity windows and invalidation reasons. Revisit them when their conditions change instead of treating a first rejection as permanent.
4. Revisit previously blocked candidates after genuine changes: freed capital, improved spread, fresh data or a new completed-bar trigger. Persist deduplication and cooldowns to prevent repeated orders or notifications.
5. Rank across sleeves and cluster duplicate underlying/sector exposure before sizing. Select feasible opportunities by net value and confidence. Avoid taking the same momentum exposure three times under three labels.
6. Continue managing open trades proactively. Rotating from an existing holding into a new candidate requires evidence that expected incremental value exceeds exit/re-entry costs and uncertainty; portfolio churn is not productive activity.

### Inactivity diagnostics and acceptance targets

These are proposed operational investigation thresholds, not automatic trade quotas or live settings:

- **Every session:** publish a funnel of universe → fresh data → setups → economically viable → risk-approved → submitted → filled. Count unique opportunities as well as evaluations. Include time spent managing open positions and capital already in use.
- **Two missed scheduled scan intervals:** flag scanner/data health and identify the failing stage. Market closure and deliberate disablement are explicit states.
- **Two eligible sessions with zero viable candidates while data and scans are healthy:** initiate an automatic diagnostic report comparing observed activity with the strategy's validated regime-specific baseline. This must not loosen limits or place trades.
- **A rolling five-session window with one or fewer fills:** require a reasoned activity review, honoring your concern directly. Separate insufficient opportunity, available-capital constraints, existing positions, risk-budget constraints, oversized cost gates, unfilled limits and genuine defects. If validated opportunities existed and were missed, classify the operational loss and correct the cause.
- **For every risk-approved, still-valid opportunity:** retain a submitted/filled outcome or an explicit reason for not submitting. Investigate unexplained dropped opportunities immediately.

Research should compare the current sparse baseline with baskets that produce opportunities on more sessions, and report median trades/week, no-trade-session rate, net expectancy, costs, drawdown and missed-opportunity rate. Determine an achievable activity range from time-separated data and the actual ₹8,000 budget. Do not declare “one trade daily” achievable before that evidence exists. A basket with more fills but worse net growth fails acceptance.

### Distinguish safety constraints from preferences

Hard constraints cover authenticated/bound accounts, valid data, broker state, affordable sizing, approved loss/exposure budgets, tradable instruments and protective-order behavior. Soft preferences cover score thresholds, preferred entry shape and ranking weights. A research variant may test softer preferences within the same hard constraints. This makes the system less rigid without making it reckless.

Record all independent rejection reasons and run offline ablations of the dominant soft gates. Measure whether removing a gate adds positive net trades or merely losses. Fix logically contradictory/impossible gates and data bugs immediately in Dev. Promote a threshold change only with evidence; an inactivity counter must never rewrite strategy parameters in Production.

### Faster progress without paying for every experiment with live money

Run the basket in parallel shadow against the same point-in-time feed, with separate virtual capital and realistic costs/nonfills. Keep live allocation limited to proven policies. This accelerates comparison even when ₹8,000 cannot fund all opportunities. Paper results must remain labeled; they do not demonstrate real fills.

Add a weekly opportunity-loss report: stale-data misses, late-scan misses, unfilled-limit misses, avoidable cost, premature exit and excessive give-back. Use bounded executable counterfactuals rather than future highs/lows. Prioritize the largest measured leak instead of inventing a fourth or fifth strategy immediately. Optimize decision quality per unit of compute as well as net rupees at risk.

The immediate roadmap therefore has two parallel development tracks: **fix the audited safety defects**, and **build the activity funnel plus shadow strategy basket**. Live activation still follows correctness and evidence gates. No extra approval is needed to design, instrument or test this in Dev; capital additions and live deployment remain separate actions.

## Use the existing AI agent as an optional assistant

User direction: use the agent section where it improves the system, but do not make Sentinel absolutely dependent on AI. This extends the proactive strategy plan; it does not authorize new live execution behavior.

### Existing implementation and dependency gaps

Inspected `agent/agent.py` and `agent/advisory.py`. The agent already fetches engine signals, collects RSS headlines, obtains MiniMax reviews, sends operator alerts and monitors engine liveness. Typed review outcomes distinguish approval, concerns, rejection and unavailable review. These are useful starting points, not reasons to build another agent service.

However, AI is not currently fully optional:

- Startup exits if `MINIMAX_API_KEY` is absent alongside the required Telegram credentials. A missing AI key can therefore stop agent-hosted alert/watchdog functions.
- Swing `run_pipeline` calls `review.blocks(...)`; an AI rejection suppresses the alert. Momentum already supports advisory rejection, with a configurable blocking policy. Runtime configuration was not inspected, so this is a code-policy observation, not a claim about today's effective setting.
- Both pipelines request news/model analysis before emitting alerts. A bounded synchronous model call can still delay a time-sensitive signal and other work on the same scheduler.
- Swing deduplicates by ticker for the day and marks rejected signals processed. A morning opinion can therefore suppress a later changed opportunity unless decision lifecycle is redesigned.
- RSS handling currently flattens item titles into text. It discards the publication timestamps and source links needed for strong event provenance. The US-oriented queries also require explicit NSE/company identity resolution before interpreting a matching headline as relevant.

These are additional implementation tasks for optional AI, not fixes performed in this documentation update. Do not silently remove a currently configured veto in Production: make the intended deterministic policy explicit, test it, and promote the change through the existing GitHub path.

### Recommended responsibilities

| Agent role | Useful output | Authority and fallback |
|---|---|---|
| Event/news context | Structured event type, affected instrument, publication time, source link and uncertainty; distinguish a confirmed company event from generic sentiment. | Deterministic checks validate identity, freshness and allowed event rules. Unsupported model statements do not become hard trading vetoes. If a strategy independently requires verified event data and that data is missing, its existing data gate still applies. |
| Candidate second opinion | Concise reasons a setup might fail, competing explanations, references to supplied features. | Initially annotate and shadow only. Any later bounded ranking adjustment must demonstrate net benefit and cannot create eligibility, raise exposure or override stops. |
| Inactivity investigator | Explain which funnel stages are blocking opportunities and propose specific offline tests of soft filters. | Read-only diagnostics and research suggestions. No self-editing thresholds, risk limits or live configuration. |
| Partner hedge explanation | A clear account-specific explanation of a deterministically computed hedge, its costs, residual risk and expiry. | Prices, quantities, sides and contracts are immutable supplied fields. A deterministic template sends when AI is unavailable or changes a protected field. Keep partner/operator destinations separate. |
| Daily/weekly research reviewer | Summarize reconciled outcomes, identify likely execution/exit leaks, propose a small versioned experiment. | Research queue only; evidence review and existing promotion gates decide what becomes live. |

### Independence contract

1. Separate AI client initialization from alerting/watchdog startup. Missing AI credentials enter `AI_DISABLED`; unavailable provider enters `AI_UNAVAILABLE`. Neither condition alone stops the deterministic engine, existing execution controls or essential alerts.
2. Engine signals, risk decisions, protective actions and order reconciliation do not wait for an LLM. Publish a deterministic alert under the existing operator-approval policy; attach a timely optional review by decision ID. This does not turn an operator-button workflow into automatic trading.
3. Use a bounded asynchronous queue, worker count, per-review deadline, cancellation/cleanup and circuit breaker. Late results for expired or superseded decisions are archived rather than shown as current advice. AI failure must not stall watchdog work.
4. Cache on decision version plus relevant event-data version, not ticker alone. Reuse valid context while permitting a changed opportunity to receive a new review. Distinguish review deduplication from acknowledged message delivery.
5. Enforce strict output schemas and immutable numeric fields. Treat fetched text as untrusted input, never executable instructions. No shell, broker-order, secret or configuration-write capability is needed for this advisory role.
6. Set explicit daily request/token/cost limits and process only shortlisted candidates or changed events. Show AI spend separately and include it in net business profitability. At ₹8,000, call costs and delays can outweigh a small trade's expected value; do not review every scan repeatedly.
7. Keep a deterministic fallback for every user-facing output. Review unavailable is neither approval nor rejection. Known risk violations remain blocked by deterministic policy regardless of the model's opinion.

### Prove that AI adds value

Run matched shadow comparisons on the same candidates: deterministic baseline; baseline plus AI annotations; and, only later, a bounded AI-assisted ranking experiment. Track net outcome, missed winners, avoided losses, extra delay, invalid/stale claims, cost and reproducibility. An AI conviction score is not a calibrated probability of profit.

Acceptance tests: missing API key; provider outage; timeout; malformed response; queue saturation; stale cached news; wrong-company headline; attempted numeric alteration; late rejection after the decision expires; and two changed setups for the same ticker on one day. Essential alerts/watchdog and deterministic risk/exit behavior must continue as designed. Never remove an existing non-AI safety requirement as a fallback.

Priority: first decouple startup, scheduling and deterministic alert delivery; then add provenance and research/inactivity explanations. Keep AI influence on numerical ranking in shadow until measured. The system should remain useful with the entire AI provider disabled, and use the agent only where it earns its cost.

## Delivery sequence and release gates

| Stage | Concrete output | Exit gate |
|---|---|---|
| A: correctness | R1–R6 state machine/revision fixes and joint fault harness | No blind uncertain resend, no stolen claim, no mixed-version eligibility, valid new generations can proceed. Existing suites and new integration cases pass. |
| B: measurement | Broker-linked decision/outcome ledger, cost attribution, activity funnel, inactivity diagnostics, baseline scorecard, adapter lifecycle; decoupled optional AI startup/queue | Open quantities and realized outcomes reconcile; paper/live/partner outcomes remain separate; no unexplained accounting residuals or silently dropped opportunities; AI outage does not block deterministic operation. |
| C: first intelligence experiment | Three-sleeve shadow basket versus current policy; bounded entry/exit challengers | Time-separated evidence improves net outcomes and worthwhile opportunity coverage within the same hard risk limits. Track all variants; do not launch all sleeves live together. |
| D: portfolio intelligence | Calibrated estimates, stable regime selection and constrained allocation | Improvement at matched portfolio risk; fail-closed behavior under stale data and model unavailability. |
| E: controlled forward operation | Versioned deployment, approved partner canary, operational monitoring | Fresh approved inputs, intended recipient acknowledgement, functioning protection/reconciliation, rollback drill. Promote through GitHub only. |
| F: income readiness | Live net-outcome history and withdrawal stress analysis | User-defined capital floor/drawdown/reserves satisfied over enough independent evidence; no fixed return promise. |

Stages are evidence-driven, not promised calendar dates. Software may be built faster than market evidence can be collected. Keep historical backtests, forward shadow, paper fills and live fills explicitly labeled.

## Recommended next assignment

Implement R1–R6 together as a delivery/portfolio revision contract, with the joint integration harness. In parallel in Dev, map the existing trade ledgers, add the activity funnel/inactivity diagnostics, and specify the three-sleeve shadow basket. Wire exit-quality/strategy-health evidence into the daily scorecard. Measure both net performance and avoidable inactivity. Promote the best supported sleeve/basket incrementally; defer new live strategies until that evidence can tell us whether they actually help.

This document is an implementation plan. Application corrections, new trading models, Production promotion and live canaries have not been performed in this review.
