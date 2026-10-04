# Smarter non-F&O entries and exits — October 3, 2026

**October 4 direction update:** the
[adaptive trader plan](2026-10-04-adaptive-non-fno-trader-development-plan.md)
supersedes this document's design direction and implementation order. Build
complete stateful replacement candidates that can recover baseline-rejected
setups; additional subset-only filters do not satisfy the owner request.
Keep this original rationale/history and its F&O noninterference contract;
R1–R5 fidelity and all adverse research receipts remain applicable.

Status: **researched development plan; no strategy implementation or promotion**.
Source baseline: Dev `4be033acdba81b18b941f28845725dc63fa80897`.
This is the owner's next development direction, superseding earlier notes to
wait for the improvement discussion. It does not reopen F&O development.

## Goal and the evidence we actually have

Improve net profit per unit of risk and capital, reduce avoidable stop-outs and
execution losses, and retain worthwhile winners. Measure consistency across
sessions and market conditions. Faster profit is an aspiration; neither this
plan nor a backtest can promise consistent profits or eliminate loss risk.
Increasing capital or frequency alone is not an improvement in strategy quality.

The **₹15.18 is a five-session Penny research result**, not all-module profit,
live earnings or a full-quarter estimate. It used incomplete-session sensitivity
data. At ₹2,000 starting cash it is approximately 0.76% for that particular
sample; do not annualize it. See [the frozen Yahoo results](2026-10-03-yahoo-backtest-results.md).

| Engineering priority | Current evidence | Meaning and first action |
| --- | --- | --- |
| 1. Classic Penny MIS | Sep 24–30: 46 accepted signals, 18 filled/closed; +₹15.18 net, 5 wins/13 losses | Best available executable lifecycle diagnostic. Explain stop overshoot, costs and repeated entries before tuning. |
| 2. Adaptive Penny EDGE | Q3: 1,142 candidate appearances, 167 selections across 65 scans | Active ranked opportunities; selections are not fills. Bind shipped execution and exits, then test ranking/entry improvements. |
| 3. Range Reversion | Q3: 1,097 ENTER verdicts | Most setup verdicts; repeated opportunities can inflate the count. Remains SHADOW research. Deduplicate and replay complete trades before any promotion proposal. |
| 4. Swing | Q3: 171 entry decisions | Meaningful daily opportunities; complete entry/exit/cash replay and context fidelity remain missing. |
| 5. Intraday Momentum | Sep 24–30: 2 virtual closes, −₹0.83 | Too small to rank its true activity or expectancy. Bind its existing partial/runner exits first; reuse existing entry-timing experiments. |
| Deferred: classic Penny CNC | Recent sample: zero entries | Audit gate overlap and coverage; no automatic threshold relaxation or separate large development effort yet. |
| Excluded: F&O and Partner | Separate money books/advisory boundaries | F&O is protected below. Partner advice/qualification is not authorized by this plan. |

Counts have different meanings and windows; they are not a profitability league
table. This assessment concerns current Dev research, not a new Production
performance assessment. Range remains research even if its count exceeds Penny.

Penny costs reduced ₹24.46 gross to ₹15.18 net. Thirteen exits were paper LTP
stops, four smart-EOD, one time exit. Removing the largest winner leaves
**−₹27.74**; the shipped adverse-fill diagnostic gives **−₹115.83**. Average R
was negative despite positive rupees because trades had different risk amounts
and tiny planned stops were overshot. Investigate each mechanism rather than
concluding that earlier profit-taking, more trades or bigger positions will help.

## Non-negotiable F&O contract

**No matter what we develop for non-F&O modules, F&O must not be hindered.**

F&O strategy, thresholds, risk sizing, capital protections, admission, exit
authority and schedules are excluded from this development. In particular,
entry halts must never disable management or exits of existing positions.
Preserving F&O filenames alone does not satisfy this requirement.

1. Research runs in a separate process with separate data, database and output
   directories. No broker clients, live database writes, runtime scan imports
   with startup side effects, new live subscriptions or scheduler registrations.
   Batch downloads and CPU-heavy scoring stay outside the trading process.
2. New variants default OFF and use non-F&O-specific namespaces. Do not change
   shared regime/configuration defaults, dependency versions or the global
   kill switch. Penny's pure-module import isolation remains mandatory; pass
   validated context through explicit interfaces rather than importing the
   Nifty/F&O engines into Penny evaluators.
3. Keep the existing account own-cash/reservation contract. No transfer from
   F&O, top-up, borrowing, leverage increase, increased book risk ceiling or
   relaxation of shared loss/drawdown checks. Preserve current nominal owner
   allocations: Penny ₹2,000, Momentum ₹3,000, EDGE ₹3,000, Swing ₹1,000;
   existing permitted unused-allocation transfers remain bounded by own cash.
   Research defaults and hypothetical paper bankrolls must be labelled separately.
4. Shared code changes require a separate compatibility slice: inventory
   transitive F&O consumers, freeze old behavior and configuration, show paired
   F&O replay/contract tests, and review resource impact before integration.
   Prefer a stock-specific adapter. Do not silently change F&O by editing
   `engine.py`, `regime.py`, `main.py`, `scheduler_setup.py`, `kite_client.py`,
   `performance.py`, reservation services or the gateway executor.
5. Before any future canary, demonstrate protected F&O cash headroom, unchanged
   admission/exit behavior, subscriptions and broker request capacity under
   concurrent stock load. Stock turnover can starve shared account cash even
   without an F&O code edit. If current contracts cannot demonstrate this,
   remain broker-free/shadow and document a separate compatibility proposal.
6. Inject quote failure, rate limiting, database contention, stock queue floods,
   worker failure and kill-switch events. Compare identical F&O fixtures with
   stock variants off/on: decisions, sizing, halt reasons and exit calls must
   match; no writes to F&O rows or lost exit authority. Profile F&O p95/p99 job
   latency, quote age, missed deadlines, SQLite lock waits and broker requests.
   Freeze numeric service/resource limits from the baseline before trials;
   require no additional deadline misses or limit violations. If a baseline
   deadline already fails, integration stays blocked until separately resolved.

Broker limits are shared and finite; throttling stock entry work must preserve
existing exit capacity. [Kite rate-limit documentation](https://kite.trade/docs/connect/v3/exceptions/)
and [streaming documentation](https://kite.trade/docs/connect/v3/websocket/)
support treating this as an operational contract. A paper replay does not prove
that Production resource isolation has been achieved.

## Research findings and how they inform this plan

Reviewed October 3. These are research directions, not proof of an NSE edge.
Some primary sites returned 403; abstract-only evidence is explicitly marked.
Local candidate rules below are our hypotheses, not prescriptions from papers.

| Primary source | Supported finding | Application and transfer limit |
| --- | --- | --- |
| [Gao, Han, Li and Zhou: Market Intraday Momentum](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2440866) | Abstract describes first-half-hour/last-half-hour predictability in the S&P 500 ETF, 1993–2013. Primary abstract indexed; full page/PDF inaccessible here. | Test time-of-day and market context. Does not validate NSE penny breakouts, a specific VWAP rule or profit after our costs. |
| [Moreira and Muir: Volatility Managed Portfolios](https://conference.nber.org/confer/2016/LTAMs16/Moreira_Muir.pdf) | Monthly factor portfolios use lagged realized variance to vary exposure, with lower exposure at higher volatility. PDF inspected. | Test capped volatility-aware stock exposure. Monthly factor evidence does not establish intraday stop widths; never increase our hard risk caps. |
| [Lo, Mamaysky and Wang: Foundations of Technical Analysis](https://web.mit.edu/Alo/www/Papers/techanal.html) | Systematic pattern definitions can provide incremental conditional information in historical US stocks. Author-hosted abstract inspected. | Use explicit, reproducible setup states and reason codes. Conditional information is not proof of profitable execution in India. |
| [Carr and López de Prado: Determining Optimal Trading Rules without Backtesting](https://arxiv.org/abs/1408.1159) | Trading-rule calibration is studied under a discrete Ornstein–Uhlenbeck process. Abstract inspected. | Treat Range targets, invalidation and holding time as a joint hypothesis. No universal optimal stop/target or proof that our stocks follow that process. |
| [Bailey et al.: Statistical Overfitting and Backtest Performance](https://sdm.lbl.gov/oapapers/ssrn-id2507040-bailey.pdf) | Searching many variants and reporting the best can fit noise; reused holdouts do not fix uncontrolled trial selection. PDF inspected. | Limit variants, retain every trial, freeze prospective holdouts and account for multiple testing. |
| [Kite orders](https://kite.trade/docs/connect/v3/orders/) | Receiving an order ID does not establish execution; true status needs order evidence. Documentation inspected. | Model fills, rejected/unconfirmed protective stops, partial quantities and exit recovery; a signal or bar touch is not an executed trade. |
| [yfinance download documentation](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html) | Intraday history has retention limits; interval/adjustment/date semantics matter. Documentation inspected. | Preserve unavailable dates and native intervals. Our direct Yahoo importer is already implemented; a different Python wrapper cannot recover expired history. |

Time-of-day cumulative relative volume, fresh reclaim/retest logic and
cost-aware selection are **local hypotheses to test**. An 18-trade sample is
insufficient to learn reliable probabilities or deploy an ML policy. Start with
bounded interpretable rules; consider calibrated models only after substantial
clean out-of-sample evidence. Optional AI stays advisory and cannot alter
numeric orders, stops or exit authority.

## Implementation slices, in order

### N0 — freeze the baseline and establish F&O isolation

Problem: evaluator counts, short sensitivity profits and different paper
bankrolls currently obscure where value is gained/lost; shared dependencies can
introduce unintended F&O changes.

Files/contracts: existing Yahoo CLI and Lab, data contracts and policy manifests;
new research-only comparison manifests and F&O compatibility fixtures.
Inventory the shared files named above plus Python/Node account reservations.
Read existing momentum S7, proactive entry/exit research and the atlas before
adding another experiment framework.

Acceptance: reproduce the 16 archived Yahoo outcomes at unchanged policy;
bind universe, warm-up, native interval, adjustment provenance, costs, cash,
clocks and source hashes. Store old results immutably. Classify every module
as evaluator, declared lifecycle, partial portfolio or qualified scope.
Create a module funnel: evaluated → accepted → eligible → reserved → ordered
→ filled → protected → exited, including every rejection and unresolved path.
Separate data absence from rule inactivity. Establish F&O off/on fixtures and
resource budgets before candidate integration. No orders or live DB writes.

Rollout/rollback: offline only; discard a faulty run and retain its failure
receipt. Existing runner and baseline remain usable. Remaining dependency:
complete historical context cannot be created from missing Yahoo bars.

### N1 — complete lifecycle/economic measurement

Files: `backtest_lab.py`, `research_data_contracts.py`,
`penny_lifecycle_replay.py`, `penny_scanner.py`, `penny_executor.py`,
`penny_engine_breakout.py`, `penny_edge_engine.py`,
`penny_edge_orchestrator.py`, `engine.py`, `position_tracker.py`,
`momentum_exits.py`, `momentum_replay.py`, `proactive_intelligence.py`,
`proactive_exit_research.py` and `portfolio_parity.py`. These are integration
targets, not permission to mutate shared runtime functions in this planning task.

Bind the actual shipped entry/exit functions through pure research adapters.
Penny already has a lifecycle: extend diagnostics, not a competing strategy.
EDGE must reconcile signal-close versus executable-entry timing across scanner,
orchestrator and simulator; its stale docstrings disagree. Do not fill at a
close used to discover the signal. Swing uses actual `evaluate_signal` and daily
tracker behavior rather than the old fee-free/proxy backtest. Range keeps its
SHADOW admission/exit semantics. Momentum reuses `evaluate_momentum_exit` with
partial quantities, fees, breakeven, trailing and hard square-off; its current
Yahoo virtual full-quantity T1 adapter is not that lifecycle.

Acceptance: golden scenario parity for each shipped evaluator/exit, same-bar
ambiguity, worse gap fills, fee/tax/tick rounding, partial quantity including
one-share cases, rejected/ambiguous orders, protective-stop failures and
unresolved positions. Only completed/available evidence may influence decisions.
Use next executable observations and bounded limit fills; no zero-volume fills,
future information, silently resolved missing exits or reused target profits.
Daily OHLC cannot prove quote-level timing; report bounds/partial scope when
intrabar order is unknown. Mark open equity and peak/trough drawdown, not only
realized cash. Reconcile joint stock cash and correlations without double counting.
Historical manual approval/broker context stays declared unknown unless evidenced.

Rollout: Penny diagnostics and EDGE lifecycle first; then Range/Swing; Momentum
exit parity can proceed as a small independent research slice. Rollback disables
the new adapter and preserves its report. No runtime policy change.

### N2 — Penny MIS and EDGE candidates

Penny source contracts: `penny_engine_breakout.py`, `penny_shadow.py`,
`penny_risk.py`, `penny_scanner.py`, executor admission and lifecycle replay.
Reuse existing flags/helpers; do not present VWAP/ATR/regime sizing as new features.

| Candidate | Entry hypothesis | Exit/risk hypothesis |
| --- | --- | --- |
| PEN_CONTEXT | Compare current linear elapsed-day volume baseline with cumulative volume at the same minute on prior valid sessions. Require a fresh completed-bar breakout/reclaim or bounded retest, acceptable liquidity and limited distance from its anchor. | Structural stop plus a tick/spread/volatility floor; recompute shares downward under current caps. Reject when conservative move-to-target cannot cover costs. |
| PEN_EXIT | Keep baseline entries to isolate exit effects; record whether failed repeated entries represent the same unexpired thesis. | Compare current paper stop/smart-EOD/time exit against thesis invalidation and one bounded runner policy. Only re-arm after a fresh structure; do not ban all re-entry or force early profit-taking. |

The current MIS lifecycle does **not** take a target exit: the target informs
EOD/risk logic. A partial/runner policy would be a new experimental variant,
never labelled today's baseline. Stops may ratchet tighter, never widen after
entry; no averaging down. Cost-aware breakeven must pay actual exit charges.
Retain existing protective-stop and unconfirmed-exit recovery contracts.
Analyze giveback after favorable excursion and stop-out excursion before choosing
trail or time limits. Yahoo OHLC lacks historical spread/depth; use disclosed
stress bounds, not invented quotes. Missing prior-minute volume profiles block
PEN_CONTEXT; they do not justify a fabricated seasonal curve.

EDGE files: `penny_edge_engine.py`, `penny_edge_live.py`,
`penny_edge_orchestrator.py` and Lab adapters. It already ranks by
regime-adjusted strength and deduplicates per ticker. Test one cost/liquidity/
gap-aware ranking variant against current selections and one subtype-aware exit
variant: mean-reversion exits toward the mean; momentum can retain a bounded
runner. Keep actual holding caps. Evaluate net return on deployed capital and
time occupied, not strength scores alone. Preserve EDGE_LIVE's current entry
recovery block; research results do not authorize bypassing it.

Acceptance: freeze each candidate manifest; isolate entry and exit experiments
before combining only justified survivors. Compare equal starting capital,
per-book caps and account cash. All stop/risk/exit tests and N0 F&O checks pass.
No increase in unresolved exposure or unexplained cash. Lower rejection counts
or more trades alone are not acceptance. Rollout: broker-free variants only;
baseline remains the active runtime choice. Rollback selects baseline.

### N3 — Range, Swing and Momentum candidates

Range: build on `range_reversion_entry` and proactive research, which already
test intact/non-expanding ranges, lower-band touch, mean target and invalidation.
Test rejection of directional expansion using causal market/stock context,
minimum net room to mean, fresh thesis identifiers and a bounded holding time.
Compare against existing Range and no-trade baselines; no averaging down or
martingale. Keep SHADOW status throughout this plan; live promotion needs its
own completed proposal after lifecycle evidence.

Swing: reuse existing EMA/ATR, breadth/context, gap-risk sizing and Chandelier
tracker. Test executable pullback/reclaim versus chasing a stretched entry;
rank relative strength, liquidity, net reward and correlated exposure. Compare
current exits with a bounded structural/volatility trail and thesis/time
invalidation. Missing event/news data cannot be claimed as event avoidance.
Preserve owner approval and gap risk; a stop does not cap overnight gap losses.

Momentum: reuse `momentum_shadow.py`, `momentum_entry_timing_research.py`,
`momentum_exit_study.py` and existing continuation/bounded-pullback S7 variants.
Test timing/limited VWAP distance and relative-volume context, then compare
actual runner/partial exit policies. It already has recency, morphology,
volatility stop floors and regime controls; finish evidence/parity before
inventing more indicators. Preserve real-money owner approval and intraday
square-off. Do not attach later-day prices to an intraday missing exit.

Acceptance: same N2 economic/compatibility checks, plus Range expansion and
duplicate-thesis cases, Swing gap/approval/one-share cases, Momentum partial
accounting and restart/hard-deadline cases. Existing studies contribute trial
history and remain non-HOLDOUT. Rollout/rollback: offline/shadow only; none
of these candidates becomes live simply because its backtest looks better.

### N4 — qualify comparisons, then prepare a separate rollout proposal

Use the existing date-argument Yahoo interface with versioned baseline/candidate
selection, immutable per-run manifests and one side-by-side report. Prices come
from Yahoo for this work, not Sentinel trade history. Actual execution receipts
may later validate fills, but remain distinct from Yahoo price backtesting.
No new scheduler or recurring collector is authorized by this planning task.

Q3 intraday retention is already unavailable. Archive future independently
acquired native Yahoo windows outside the runtime, or submit a separate provider
proposal if retention/coverage remains inadequate. Never aggregate daily bars
into invented minutes. Existing reviewed Q3/Sep 24–30 data is development data,
not an untouched holdout. Daily studies can expand backward with appropriate
warm-up and visible current-universe/survivorship limitations.

Before scoring, freeze a chronological train/validation/untouched-holdout split,
purge overlapping trades around boundaries and declare holding-period embargoes.
Initially allow at most **two candidate policies per module plus baseline**;
parameters/settings and rejected trials count toward the trial ledger. An entry
or exit combination is another trial, not a free unreported optimization. Use
session-block uncertainty estimates and matched portfolios; do not treat
correlated ticker trades as independent observations. Apply multiple-testing
adjustment when making significance claims; do not print impressive Sharpe/PBO
values when data is insufficient.

Proposed evidence floors are **60 covered sessions and 100 closed intraday
trades**, and **12 covered months and 50 closed daily-strategy trades**, with
several market conditions represented. These are governance floors, not proof
or deadlines; low frequency means more observation time, not weakened gates.
Coverage, dependence and uncertainty may require substantially more evidence.
Where historical membership is unavailable, limit the conclusion accordingly.

Freeze acceptance before results: positive net holdout expectancy after costs,
improvement over baseline at matched cash/risk with session-block confidence
intervals, drawdown/tail exposure within existing caps, and acceptable cost/fill
sensitivity. Test 1.5x and 2x assumed slippage plus observed adverse bounds;
charges use the applicable schedule, not arbitrary scaling. Report performance
without the largest one/two winners, across weeks/regimes, and turnover/capital
occupancy. Winner exclusion is a concentration diagnostic, not a requirement
to truncate all winners. If uncertainty includes no improvement, report
INCONCLUSIVE; if the edge disappears at credible execution costs, reject it.

The report must show: coverage/unavailable days, each funnel stage, closed/open
positions, gross/cost/net money, consistent initial-risk R, marked drawdown,
loss tails, favorable/adverse excursions, winner capture/giveback, duration,
capital usage, exposure correlation, holdout/trial identity and F&O checks.
Optimize sustainable expectancy and drawdown, with return per capital-day as a
secondary measure; no fixed rupee-per-day guarantee or trade-count target.

Only a survivor earns a separate rollout proposal: Dev checks → prospective
paper comparison (at least 20 sessions for operational evidence, not a proof of
profit) → reviewed GitHub promotion → separately authorized limited canary.
Keep current operator approvals. Baseline restore/variant disable affects new
non-F&O entries only; positions retain the exact exit policy admitted with them.
Rollback must never orphan protective stops, reset reservations or disable F&O.
Avoid destructive shared schema migrations; any later additive migration needs
an explicit old/new reader compatibility and rollback contract.

## First deliverable and remaining work

Start **N0 and N1**, delivering a frozen Penny failure attribution and a complete
declared EDGE lifecycle before proposing runtime tuning. This provides the
fastest route to a defensible improvement decision. Follow with PEN_CONTEXT /
PEN_EXIT and EDGE variants, then Range/Swing, with Momentum parity as a bounded
supporting slice. Reuse shipped functions and record every changed contract.

Remaining: native intraday coverage, lifecycle adapters and exact context,
stock portfolio marked equity, experiments, genuinely untouched evidence,
operational F&O compatibility, qualification and any authorized rollout.
None is completed by this plan. No strategy, threshold, funding, dependency,
runtime configuration or database migration changed; Production was not read
or altered for this planning task. No broker action, push or deployment.

Verification receipt: required handover docs and applicable AGENTS reviewed;
source contracts above inspected against `4be033a`; research limitations and
prior Yahoo counts reconciled. `git diff --check` passed. A Python documentation
scope/link check passed: exactly four documentation paths changed, 50 local
links and 26 explicitly named Python source targets exist, and the source HEAD
is unchanged. New-plan whitespace/UTF-8 checks also passed. No source declarations
changed, so atlas regeneration was unnecessary. This is documentation-only work;
strategy tests were not rerun, and the existing 70-test Yahoo receipt remains
historical. The plan and documentation updates are Dev-local, uncommitted at
delivery. There is no runtime configuration or migration impact.
