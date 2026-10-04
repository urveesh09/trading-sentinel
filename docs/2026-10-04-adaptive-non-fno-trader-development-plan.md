# Adaptive non-F&O trader development — October 4, 2026

Status: **revised development plan, not implemented or deployed**. The owner
asked for trader-like entry/exit decisions and an improved plan after weak
research results. Dev HEAD is `434c4ccce6cb21894750cb74f01f546b4af1ea84`;
the preceding review's uncommitted corrections and evidence are preserved.
This task adds documentation only. No Production access or edits, broker
actions, strategy/configuration/dependency/schema changes, push or deployment.

This plan supersedes the **design direction and implementation order** of the
[October 3 plan](2026-10-03-non-fno-smart-entry-exit-development-plan.md).
The [R1–R5 review contracts](2026-10-04-non-fno-independent-review-and-repeat-plan.md)
remain acceptance requirements. Their fidelity fixes must accompany actual
strategy development; another disconnected filter/helper is not completion.

## What needs to change

The owner's criticism identifies a real weakness: `penny_context_gate` returns
`baseline_rejected` before examining its new evidence. It can only remove old
accepts. `swing_candidate_gate` has the same subset-only design. Those helpers
cannot recognize a good setup missed by the old policy. `penny_exit_thesis`
has no transition history with which to establish a genuinely fresh reclaim.
Adding conditions is not enough to deliver the requested trader behavior.

Strictness is **a hypothesis, not the whole diagnosis**. In the existing
[comparison](2026-10-04-non-fno-review-and-backtest-results.md), Penny accepted
46 observations and closed 18 trades in five sessions; EDGE selected 167
appearances, Swing gave 171 entry decisions and Range gave 1,097 ENTER verdicts
over Q3. Counts are not unique trades or profit. Penny's +₹15.18 was fragile;
the EDGE independent-trial proxy was adverse. Execution, repeated entries,
stop geometry, costs and exit timing can destroy value after a setup passes.
Quarter intraday history and several complete lifecycles remain unavailable.

The target is a system that remembers an opportunity, waits for an executable
entry, reacts promptly to new evidence, exits a failed thesis, and lets a
healthy trade develop. Measure net return, downside, execution delay and
capital occupied. Faster profitable decisions are useful; faster churn is not.
Daily Swing/EDGE opportunities keep their natural horizons. Neither speed nor
activity establishes consistent profit or superiority to a human trader.

## Decision architecture

### 1. Separate safety constraints from strategy preferences

Create a gate inventory for each module: condition, actual caller/configuration,
reason code, evidence availability, and whether it is an execution constraint,
risk contract, setup definition or quality preference. Inspect effective
settings; comments claiming a refinement improves hit rate are not evidence.

Hard constraints stay hard: authorized cash and reservations, existing
loss/drawdown/concurrency ceilings, valid executable prices and quantities,
instrument/circuit restrictions, fresh execution evidence, protective-stop
placement/recovery, approval boundaries and intraday square-off. Missing
required evidence cannot become a pass. Planned stop risk is not a guarantee
against gaps, illiquidity or outages.

RSI, relative volume, distance from VWAP, time-of-day, relative strength and
similar quality cues are candidates for **context-dependent scoring or setup
transitions**. A separately versioned research policy may replace strategy
conjunctions, including considering observations rejected by the baseline.
It must still satisfy unchanged safety/risk contracts. Existing regime risk
brakes do not become optional merely because they use a market indicator.
No blanket threshold relaxation and no live gate removal in this plan task.

Begin with transparent, bounded scores and a few explicit setup definitions.
A score ranks evidence; it is not a win probability or expected profit estimate.
Optional missing features have an explicit availability flag and declared
degraded policy; required missing inputs make that candidate unavailable.
Never replace missing values with neutral observations or silently activate a
fallback. Record baseline and candidate decisions for the same visible inputs.

### 2. Give opportunities persistent states

`WATCH → ARMED → ENTRY_INTENT → OPEN → EXIT_PENDING → CLOSED`

Before entry, a setup can become `EXPIRED` or `INVALIDATED`. After closing,
`COOLDOWN` can return to `WATCH` only through a recorded new/rearmed thesis.
`ENTRY_INTENT` is not a fill; reservation, order submission, partial fill and
stop confirmation have separate execution states. Unconfirmed exits retain
their exposure and recovery obligations.

Store instrument, module, setup family, persistent thesis ID, state revision,
observed/available/decision times, immutable structure anchor, entry zone,
invalidation, expiry, initial risk, quantity, reason codes and policy version.
State updates must be deterministic, idempotent and restartable. One rolling
date string or a price currently above an anchor cannot establish a new thesis.

An opportunity that is too extended can wait for a bounded retest. A developing
breakout can remain armed rather than disappear on a single low-volume minute.
Expiry, broken structure and loss of executability cancel stale intents. A new
quote must revalidate geometry, cash and risk before an order. Do not reuse an
old signal indefinitely or average into a failed thesis.

### 3. Choose entries and manage the thesis

Define each setup's evidence and competing actions in advance: enter on a
fresh continuation, wait for a pullback/reclaim, or decline. Rank only eligible
opportunities using structure, confirmation, liquidity, chase distance,
volatility, executable net reward and existing stock exposure. Any portfolio
concentration ceiling remains a constraint, not a score to compensate away.

Choose the initial stop from causal structure plus a declared tick/noise
allowance **before entry**, then recalculate shares and all costs under the
same cash/risk ceiling. A wider initial stop means less size; zero affordable
shares means no entry. Once filled, never widen the protective stop or increase
risk to rescue a loser. Distinguish stop trigger, submitted exit and actual fill.

Keep a live thesis record: structure intact/broken, progress, adverse excursion,
liquidity, remaining reward, holding time and approaching hard deadline.
Test context-sensitive discretionary exits against current exits. A fixed
elapsed time need not imply failure while structure is intact, but all hard
deadlines and protection/recovery rules remain. Model partial exits only for
integer quantities actually available; a one-share position cannot have a
fractional runner. Winners need a declared trailing/continuation rule, not an
automatic early cut imposed to improve win rate.

## Module work, in priority order

| Module | Concrete development hypothesis | Reuse and implementation targets | Required comparison |
| --- | --- | --- | --- |
| **Penny MIS** | `PEN_TRADER_V1`: fresh breakout and bounded retest/reclaim states; evaluate volume and RSI in the setup's context instead of requiring every old quality gate first. Freeze the anchor before confirmation. Test a structural initial stop with a noise allowance and resized quantity; a failed thesis cannot repeatedly trigger the same entry. | `penny_engine_breakout.py`, `penny_risk.py`, scanner/executor contracts, `penny_lifecycle_replay.py`, `non_fno_research.py`. Keep the pure Penny import boundary; new context arrives through supplied evidence. | Baseline versus replacement entry at identical exit policy, then one declared thesis-exit variant at fixed entries. Record recovered baseline-rejected setups, false breaks, stop overshoot, cost/R, repeated ticker losses and retained winners. |
| **Adaptive Penny EDGE** | `EDGE_TRADER_V1`: treat MR and MO as different theses. For MR, test stabilizing/reclaim timing; for MO, continuation versus bounded pullback. Rank using subtype/context, executable reward after costs, gap risk and expected holding burden. Existing strength is not a probability. | `penny_edge_engine.py`, live scan/orchestrator contracts, `research_daily_decision_replay.py`, Lab. Reuse regime-aware ranking and sizing; first repair the replay's holding clock and cash book. | One persistent portfolio with open positions and dedupe, next executable fill and resized risk, all costs and marked equity. Attribute results to MR/MO and entry/exit changes. Preserve the losing proxy receipt. |
| **Range Reversion** | Persistent range identity; touch arms a thesis, stabilization/reclaim can trigger entry. Expanding/broken range invalidates it. Test a costed mean exit against a bounded thesis/progress exit, with any target update defined causally in advance. | `range_reversion.py`, `proactive_intelligence.py`, `proactive_exit_research.py`, daily replay/Lab. Reuse actual range semantics; remain SHADOW. | Distinct range episodes and completed trades, not repeated ENTER counts. Include trend-transition losses, failed bounces, time/capital occupied and no-trade/current-profile baselines. No averaging down. |
| **Swing** | Rank trend/pullback opportunities using relative strength and current stock exposure; distinguish a healthy pullback from a deteriorating trend. Wait for a reclaim if the immediate entry is extended. Compare thesis invalidation with the actual existing partial/Chandelier trail. | `engine.evaluate_signal`, `position_tracker.py`, pure daily replay; existing trend/pullback proposals. Shared `engine.py` is a protected integration seam. | Actual completed daily signals, next executable entry, gap losses, costs, full holding lifecycle and marked portfolio drawdown. Current manual execution boundary remains. A daily system is not forced to scalp. |
| **Momentum** | Reuse continuation/pullback and re-entry research. Compare fast/slow clock exits with thesis/progress-conditioned exits once their decision clocks are causal. Preserve the runner where supported; quickly exit genuinely invalidated structures. | `momentum_entry_timing_research.py`, exit/path studies, `momentum_exits.py`, `momentum_replay.py`. No duplicate experiment framework or initial shared runtime edit. | Correct accepted-close availability and next executable entry, partials and admissible intrabar paths. Two trades cannot establish which exit is superior; retain the −₹19.01 diagnostic. |
| **Penny CNC** | Audit the conjunction of 250-bar history, SMA trend, RSI(2), volume and partial-daily evidence. If a valid pullback is repeatedly lost, test an armed pullback/reclaim policy independently of MIS. | `penny_engine_connors.py`, scanner/CNC lifecycle. Preserve Penny isolation and multi-day exits. | Missing in-progress daily evidence versus actual rule inactivity; no invented intraday daily candle. Give it a small diagnostic slice, not a new large framework before Penny MIS/EDGE. |

Partner research remains outside this trading-policy effort. F&O remains outside
development. New candidate names above are **proposed**, not existing selectors.

## Learn from rejected opportunities without hindsight

Emit all condition outcomes, not only the first return reason. Penny's present
funnel has 36,015 volume and 33,190 time-window first rejects, but a first reject
does not prove that condition alone blocked an otherwise good trade. Record
each cue and availability at the original decision boundary. Preserve hard
ineligibility separately from strategy rejection and execution rejection.

Build a bounded shadow ledger of predefined setup families across both accepted
and rejected observations. Simulate their declared next-observable entries and
exits, including losses/no-fill/unresolved paths. A later rally may label a
counterfactual outcome; it cannot determine which past opportunity was selected.
Use the same per-session cash book, risk budget and universe for comparisons.

Measure whether a new policy recognizes, arms and executes eligible setups
more effectively, including delays, chase costs and duplicate churn. Define
opportunity coverage against an explicitly frozen mechanical setup universe;
do not call every profitable future move a missed opportunity. Audit samples
by reason/context, and report winners and losers of recovered entries.

## Execution slices and completion contracts

Each slice must update guide/plan/atlas as required, preserve previous results
and record commands, source identity, environment limits and deployment status.

### T0 — decision evidence and causal comparison foundation

Problem: subset-only helpers and inaccurate execution clocks make strategy
improvement both constrained and hard to measure. Files: Yahoo CLI, Lab,
research data contracts, current replay modules, pure decision/state contracts.

Deliver explicit baseline/candidate selection through the **same one-script
date-argument interface**, plus complete gate evidence and persistent cash/state
replay. Keep the original Q3 and September 24–30 scored windows immutable.
Acquire independently sourced native intraday warm-up before scoring: at least
the five complete prior same-minute profiles needed by the existing candidate,
with declared lookback and exclusion receipts. Check provider retention first;
collect forward archives for future tests, never synthesize expired history.
Additional available profile history can be tested only as a frozen variant.

Implement R2 EDGE holding/entry/cash and R3 Momentum clock/path/partial-equity
counterexamples before qualified economic comparisons. A scheduled open exit
cannot consult that day's later high; a completed bar cannot admit an entry
at its start. OHLC ambiguity requires declared outcome bounds or quote evidence.
Missing partial marks/fills cannot disappear from drawdown or bankroll.

Acceptance: old 16 outcomes still reproducible in their original scope; candidate
selectors never silently fall back; inputs/settings/source hashes and evidence
times bound to each run. Portfolio cash conserves through gaps, partials,
unresolved orders and exits. Deterministic state/clock counterexamples pass.
Rollout/rollback: offline only, default BASELINE, separate data/database/process;
disable candidate selection to return to the previous research path.

**Develop the Penny/EDGE decision prototypes alongside these adapters.** T0 is
not a reason to spend another phase producing only measurement helpers. The
first delivery includes a runnable policy that can recognize a baseline-rejected
setup from evidence available then, and the replay needed to judge it honestly.

### T1 — Penny and EDGE complete trader candidates

Problem/files: implement the first two module rows above, using pure shared
policy functions in research and eventual runtime adapters. No research-only
policy copy that later diverges from the deployed evaluator. Reuse current
VWAP/ATR/rank/exit functions where behavior is retained; version any replacement.

Acceptance: WATCH/ARMED/expiry/new-thesis and order/protection transitions work
under replay/restart; replacement candidates can admit a predeclared setup the
baseline rejects while every safety constraint remains enforced. This establishes
capability, not a trade quota or profitable edge. Report paired economics and
all rejection/availability categories, actual structural sizing and cost stress.
The entry-only comparison precedes the single exit variation, so causes remain
identifiable. One complete candidate per module is the first milestone.

Rollout/rollback: named offline versions, default OFF; prior baseline and original
trial receipts retained. No live EDGE promotion/recovery bypass or automatic
Penny activation. Any unsupported data window remains unavailable.

### T2 — remaining module policies and latency

Problem/files: complete Range/Swing entry-to-exit adapters and states; reuse
Momentum timing/exit research; perform the limited CNC audit above. Wire them
to the same comparison interface instead of standalone disconnected gates.

Acceptance: Range stays SHADOW, approvals remain intact, signal appearances
dedupe to theses/positions, holding/exit clocks and cash reconcile. Report net
economics by setup/context, rejected-opportunity recovery and risk concentration.
Module-specific horizons remain explicit. Any shared-source modification gets
a non-F&O-specific interface and protected F&O regression evidence.

For a future runtime adapter, cache incremental features and maintain a bounded
armed watchlist. Evaluate completed-bar setup evidence when it becomes available;
use fresh quotes for executable timing/risk checks. Do not rescan hundreds of
tickers on every tick. Measure quote age, evidence-to-decision, decision-to-submit
and submit-to-fill at p50/p95/p99 with realistic contention. Freeze numeric
entry freshness/expiry and service budgets from measured baseline before trials.
Broker/exchange latency is not eliminated by a faster Python function.

Rollout/rollback: offline/isolated prototype first. Streaming subscriptions,
scheduler registrations and runtime broker connections require the later
compatibility/rollout slice; this plan creates none.

### T3 — qualify improvements and protect F&O before integration

Problem/files: comparison/trial manifests and reports, replay equity ledger,
F&O compatibility fixtures, future non-F&O runtime adapters and documentation.

Freeze a maximum **two candidate versions per module per development round**,
including its exit variation. Register the earlier PEN_CONTEXT/exit/proxy
studies in the trial ledger. Record all failed/unavailable outcomes. New rounds
need an explicit evidence-based hypothesis and fresh validation; the cap cannot
be evaded by silently changing thresholds under one name.

Run two clearly labelled comparisons: (a) original archived configurations for
regression; (b) a separately frozen owner-allocation stock portfolio: Penny
₹2,000, Momentum ₹3,000, EDGE ₹3,000, Swing ₹1,000, with only already permitted
own-cash transfers. No ₹100,000 EDGE default substituted for authorized funding.
Compare strategies at equal cash/risk, complete costs and realistic fill stress.

Report net expectancy/R, marked peak-to-trough drawdown including partial/open
exposure, tail/gap losses, turnover/cost share, capital-days occupied, winner
concentration, setup/context breakdown and paired outcome uncertainty. Keep
dependent trades together in uncertainty estimates; observations on the same
ticker/session are not independent samples. Track progress/stop overshoot and
winner capture alongside opportunity response. No win-rate or trade-count target.

Choose the policy and freeze numeric economic/risk acceptance **before** a fresh
untouched forward or historical qualification window is opened. A repeated Q3
or five-session sample is development data. A profitable candidate should show
positive after-cost expectancy, risk-adjusted improvement over its matched
baseline and downside within existing ceilings across enough independent
sessions/contexts. Report uncertainty: if superiority is not established,
continue shadow/data collection rather than claim qualification. Specify the
sample/stopping rule in the freeze; do not stop testing at the first good week.

Rollout: broker-free shadow, then a separately authorized GitHub promotion/canary
only after qualification and F&O compatibility. Rollback disables new stock
entries; admitted positions retain their versioned management and exit recovery.
No migration may orphan stops, reservations, thesis IDs or existing positions.

## F&O must not be hindered

Preserve the October 3 noninterference contract in full: F&O policy, sizing,
cash/reservations, loss brakes, admissions, exits, configuration and schedules
are excluded. Stock development must not consume protected F&O cash headroom,
exit request capacity or job/quote deadlines. Entry halts never halt management.

Research uses isolated processes, caches, databases and output directories.
Do not alter shared `regime.py`, `engine.py`, `main.py`, `scheduler_setup.py`,
`kite_client.py`, account reservations, gateway or global defaults without an
explicit non-F&O seam and paired compatibility checks. Initially keep new pure
decision logic outside those runtime seams. No borrowing, top-ups, leverage or
hard-risk increases, and no funding transfers from F&O.

Before integration, freeze F&O decision/exit fixtures and measured resource
budgets. Under stock variants off/on and injected floods, quote/API failures,
worker crashes and SQLite contention: F&O decisions, sizes, reservations and
exit authority must match; no new deadline misses or resource-limit violations.
An already failing baseline must be resolved separately before integration.
Stock workers shed entry load first. Operational compatibility cannot be inferred
from source isolation or paper profit. Shared rate capacity is documented by
[Kite](https://kite.trade/docs/connect/v3/exceptions/).

## Research basis and its limits

Primary sources rechecked October 4. These motivate local hypotheses; none
validates the proposed NSE policies or promises a return.

| Source / evidence inspected | Implication for our design | Limit |
| --- | --- | --- |
| [Gârleanu and Pedersen, Dynamic Trading with Predictable Returns and Transaction Costs](https://archive.nyu.edu/bitstream/2451/28346/2/DynamicTrading.pdf), author/university-hosted 2009 manuscript and indexed NBER abstract; PDF inspected (NBER page fetch returned 403). | Account for signal persistence and turnover costs when choosing timing and holding behavior. | Model assumptions and commodity-futures application do not establish our penny-stock edge or suggest instant trading is always optimal. |
| [Kaminski and Lo, When Do Stop-Loss Rules Stop Losses?](https://dspace.mit.edu/entities/publication/bb69ca4b-0cdc-487f-831d-63b2e84fafee), MIT repository abstract inspected. | Exit policies can add or subtract value; test them against the actual thesis and horizon. | Portfolio/index-futures and longer-frequency evidence is not an NSE intraday stop prescription. We retain mandatory protection. |
| [Lo, Mamaysky and Wang, Foundations of Technical Analysis](https://web.mit.edu/Alo/www/Papers/techanal.html), author-hosted abstract inspected. | Make pattern recognition explicit and reproducible. | Historical conditional information is not net execution profit. |
| [Bailey et al., Statistical Overfitting and Backtest Performance](https://sdm.lbl.gov/oapapers/ssrn-id2507040-bailey.pdf), PDF inspected. | Bound trials, retain failures and use genuinely untouched qualification. | A trial cap or holdout alone does not certify an edge. |
| [Kite orders](https://kite.trade/docs/connect/v3/orders/), official documentation inspected. | Separate decision, order, fill, protection and recovery states. | An order ID does not establish successful execution. |

Do not add an LLM to the order loop as a shortcut to trader intelligence.
Optional AI can explain evidence without changing numeric orders/risk authority.
Once substantial causal outcomes exist, test calibrated, time-split contextual
models with conservative estimates and drift monitoring. Until then, explicit
stateful policies are easier to audit and less likely to learn an 18-trade accident.

## Remaining work and delivery receipt

All T0–T3 strategy implementation, new data acquisition, economic comparison,
qualification, operational compatibility and promotion remain open. Existing
R1–R5 failures stay recorded; this document does not mark them complete.

This revision inspected current Penny entry/Connors/candidate, Momentum timing
and evaluator, EDGE simulator/ranking and Range code plus the prior review
receipts and required handover docs. Delivery verification passed:
`git -c core.safecrlf=false diff --check`; Dev Python checked all three local
plan links, five handover redirects, referenced Python files and scope/slice
assertions. The source diff for `python-engine`, `scripts`, `node-gateway` and
`config` matches its pre-task snapshot exactly. No atlas regeneration was needed
because this task changes no source declarations. The previous
review's 130 test passes remain its historical receipt; no new strategy tests,
backtest or profitability claim is made by this documentation-only task.
No implementation commit was created; HEAD remains `434c4cc`, with prior
uncommitted review changes preserved and these additional Dev-local docs.
