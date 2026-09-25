# Adaptive trader roadmap — owner paper autonomy, owner-approved real money

## Product decision and non-negotiable authority

The owner wants Sentinel to become a proactive, flexible trader that discovers
opportunities, forms a thesis, manages the whole position, captures larger
valid moves, and learns from outcomes—not a collection of ever-tighter entry
filters. More net profit is the objective, not a promised outcome or a reason
to conceal risk. This roadmap builds on the existing momentum, penny, F&O,
proactive and replay modules rather than restarting the architecture.

**Owner momentum paper:** automatically take every eligible deterministic
strategy signal in the isolated paper book, as the current code does. A news
classifier timeout remains `UNKNOWN` information; it is **not** a default veto
or a hidden approval. Optional AI may annotate a thesis, but does not decide
paper admission, numeric risk or exits. The system may use its existing
deterministic paper sizing and management without asking the owner each time.

**Owner real money:** each new momentum entry still needs the owner's explicit
EXEC approval plus the current broker, session, capital, risk and execution
checks. Approval of one entry does not authorize autonomous new orders,
capital increases, overnight conversion or altered risk limits. Existing
protective exit obligations remain active after an approved fill; any proposed
new live authority requires its own design and authorization.

**Partner:** receives manual intraday NIFTY/SENSEX ideas only after compatible
strategy qualification and delivery authorization. Sentinel does not place
partner orders. General market setups do not need partner holdings; personalized
hedges do. The partner's intraday horizon is not silently extended to overnight.

## What the smarter system should do

Model each opportunity as a versioned, explainable *trade thesis* rather than a
binary pass/fail signal. At a genuine decision clock it should record: market
regime and competing opportunities; directional/range rationale and invalidation;
entry and no-chase price; expected gross and cost-stressed reward versus defined
loss; capital, liquidity and correlation budget; intended management horizon;
and the data/source age. If evidence is unavailable, the thesis can abstain
with a reason; it must not fabricate confidence or an executable price.

The lifecycle is discovery → candidate ranking → paper admission → active
management → closed/unresolved result → research feedback. Active management
is the main “flexible and greedy” work: seek a larger share of *confirmed*
trends through predeclared trailing/scale-out or time-extension variants, while
reacting to thesis invalidation, deteriorating liquidity and session deadlines.
It must distinguish a profitable move worth holding from a losing position
merely being given more time. Protective stops, defined maximum loss, hard-flat
rules and broker ambiguity controls are constraints, not performance filters
to disable.

## Ordered development slices

### A. Establish a decision-quality baseline before optimizing

Use the existing `momentum_paper_admission_outcomes`, paper positions/ledger,
`momentum_shadow`, `penny_shadow`, F&O decision units and proactive opportunity
ledger to trace accepted, skipped, opened, managed, expired and closed ideas.
Reconcile each strategy/mode/account separately. Report **net** R and cash P&L,
fees/slippage, drawdown, turnover, time in trade, unused risk budget,
opportunities missed by capital or scheduling, and the fraction of positive
excursion actually captured. Estimate capacity at the owner's approximately
₹8k *real* capital, not a ₹50k/₹100k paper pool. Do not rank one day's penny
losses or three DR outcomes as a strategy verdict.

Acceptance: repeatable per-opportunity audit from immutable inputs through
paper result, no double-counted partials, separate live/paper numbers, and
explicit unavailable/unresolved outcomes. This slice is diagnostic only.

### B. Research a small strategy basket, not a wider filter maze

Predeclare a few distinct hypotheses and compare them on the same independent
opportunities: trend continuation after bounded pullback; completed-bar
breakout confirmation; stable-range mean reversion; and cost-aware abstention.
For owner penny/momentum, first investigate whether the observed fast STOPs
represent entry timing, spread, regime or normal variance. Do not tune a new
threshold to the September 25 losing set. For the partner, compare only
defined-risk, intraday NIFTY/SENSEX structures under its own economics and
manual execution delay; stock-paper wins do not transfer to index options.

Acceptance: frozen manifest, causal input clocks, realistic bid/ask and fee
stress, no-fill/unresolved cases, independent opportunity count, future held-out
sessions and uncertainty/drawdown. A comparison may reject every variant. No
model is promoted because it has the highest in-sample P&L.

### C. Make trade management adaptive, then allocation adaptive

On the *same accepted entries*, compare existing fixed target/time stop with
bounded trailing, scale-out, and thesis-based hold/exit variants using only
information observable at each decision. Measure upside capture *and* added
tail loss, gaps, transaction cost, missed exits and late-session exposure.
Separate paper and live exit consumers: a paper experiment cannot silently
change an owner-approved real position's management contract. For an optional
longer owner horizon, first research a **separate** swing/CNC product and
overnight risk/financing/stop behavior; never let an MIS or partner intraday
position roll overnight by accident.

Then compare flat per-trade sizing with a versioned allocation policy that
considers cash actually available, concurrent exposure, correlation, regime,
liquidity and costed edge. Do not compound paper profits into real buying
power or automatically grow live limits. Keep a small explicit loss/drawdown
budget and prevent a “greedy” policy from averaging down or doubling after a
loss unless that behavior is separately researched and authorized.

Acceptance: paired, source-bound exit and allocation reports with negative
controls; no future-data leakage; realistic costs and gap risk; invariant
maximum loss and deadline tests; no additional broker order authority.

### D. Build an honest feedback loop

After each paper close or no-fill, compare the predicted thesis with actual
path, costs, adverse/favorable excursion and invalidation timing. Group by
regime and setup rather than chasing the latest ticker. Show what changed in
the strategy's *hypothesis*, not only its win rate. Candidate ranking can
adapt only through a versioned, predeclared evaluation and future holdout;
online parameter drift must not rewrite an active trade or silently inherit a
prior qualification. AI can summarize sourced evidence and propose research
questions; deterministic evaluators and human-reviewed release decisions own
strategy changes.

Acceptance: reproducible version/policy lineage, prior decisions still
replayable, a rejected hypothesis visible, and no automatic promotion from a
backtest or paper streak.

### E. Promote only what earns authority

Start shadow, then paper, then a reviewed proposal with reconciled economics,
cost stress, drawdown and operational stability. For owner live momentum,
retain per-entry approval and existing account/risk/order gates; capital
increases need an explicit owner decision. For partner general tips, use the
separate held-out qualification and authorized TEST/canary process in the
[September 25 audit plan](2026-09-25-production-audit-response-plan.md).
Delivery quality includes timely actionable terms and honest invalidation,
not a daily message quota.

Acceptance: no paper/research component can place a real order or send an
unqualified partner tip; permission is narrow, revocable and tested under
timeouts, restarts, stale data and ambiguous broker/transport results.

## First executable slice, rollout and rollback

Start with A plus a **paper-only paired exit study** from C: choose a bounded
set of existing momentum entries and compare current exits with one
predeclared trailing/hold variant on the same chronological quote/public
evidence. Do not alter production exits to run the experiment. Identify the
exact current callers (`momentum_paper.py`, `momentum_exits.py`,
`position_tracker.py`, replay/shadow helpers), freeze entry and cost identities,
add leakage/deadline/gap tests, and produce an immutable report with net P&L,
capture ratio, drawdown and unresolved exposure. If the archive lacks faithful
path evidence, report `INSUFFICIENT_EVIDENCE` and improve collection first.
Run the partner general-index qualification evidence track in parallel; owner
strategy research does not replace or postpone its separate held-out review.

Implementation occurs in Dev with a failing reproducer, updated system guide
and active plan, focused plus affected cross-component tests, atlas regeneration
for declaration changes and immediate post-commit consistency check. Promote
only through reviewed GitHub flow. Roll back a losing or operationally unsafe
variant to the prior version while retaining all paper, ledger and research
evidence. The current task only records this roadmap; no trading behavior,
configuration, Production service or authority changed.

## Active Dev implementation slice

The first paper-only paired study is specified in
[the adaptive exit-study plan](2026-09-25-adaptive-exit-study-plan.md).  It
uses an immutable timestamped-LTP input packet rather than treating sparse OHLC
as a faithful monitor history.  Any missing, gapped, ambiguous or late-session
path is explicitly unresolved.  No runtime exit policy, broker authority,
EXEC approval, partner message or Production configuration is changed by this
research instrumentation.
