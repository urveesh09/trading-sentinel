# Trading Sentinel — proactive intelligence product build

Implementation brief for the next Dev assignment, 6 September 2026.
Baseline inspected: `e03991a` on `codex/production-correction-hedge-p0`.

## The assignment: build the broader product

**Implement a working, integrated Dev version of the proactive trading-intelligence roadmap. Do not scope this assignment down to another hedge-delivery correctness increment.** The required deliverables are milestones P1–P7 below, including scheduled consumers, existing UI integration, deterministic demonstrations and tests. This is an implementation assignment, not another planning exercise.

The prior handoff contained the broader roadmap but its safety-first sequence allowed an implementation limited to delivery safeguards. That narrow interpretation is explicitly superseded for the next assignment. Retain existing safeguards, fix genuine blockers where necessary, and continue building the rest. A missing live adapter, AI key, production authorization or statistically proven trading edge does not block fixture adapters, shadow operation, instrumentation, UI, research tools or offline acceptance.

This document follows inspection of the latest commit identity/remediation log and relevant product surfaces. It is **not an independent full audit of `e03991a`** and does not certify its release readiness. Reported delivery safeguards remain a baseline to preserve and validate when touched. The outstanding gateway native-binding problem is a development-environment task, not evidence that all product development must stop.

### User requirements that must survive implementation

- Current testing capital is approximately ₹8,000; future owner-funded stages are ₹20,000–₹50,000, ₹1 lakh and eventually ₹5 lakh. Funding increases are not trading profits.
- Find opportunities proactively. Unexplained inactivity, including one or fewer fills across five eligible sessions, must be visible and investigated. This is not an instruction to force a daily trade.
- Research a complementary strategy basket, improve entries/exits and allocate scarce capital intelligently. Prove improvements after costs and at comparable risk.
- Keep partner hedging highest priority. Separate the partner's portfolio/protection service from the user's small live trading account.
- Use the existing AI agent where it helps, but essential trading, risk, exits, alerts and watchdog behavior must work without an AI provider.
- Capital additions, numerical loss budgets, strategy live activation and withdrawal targets are separate owner decisions. Do not infer them from a wish for fast growth.
- Software completion and evidence of profitability are different. Build the complete evaluation/decision system now; do not fabricate an edge or promise a return.

### Environment and authorization boundary

All changes belong in `C:/Users/Urveesh/Desktop/trading-sentinel`. Read the repository's AGENTS instructions. Preserve existing audit artifacts and unrelated files. Do not directly edit `Production_Trading-sentinel`, restart its services, send Telegram messages, place orders, enable a new live strategy or change its risk settings. Production promotion remains through GitHub. Use synthetic adapters and mocked transports for demonstrations.

The user has asked for the next product development plan. This brief prepares that assignment; this document itself does not change application behavior or start implementation.

## Reuse map — inspect before adding modules

| Capability | Existing surface to extend |
|---|---|
| Candidate scoring and momentum features | `python-engine/engine.py`, `regime.py`, `penny_edge_engine.py` |
| Allocation and sizing | `python-engine/portfolio.py`, `risk_engine.py`; retain book-specific risk controls |
| Exit management | `python-engine/momentum_exits.py`, `position_tracker.py`, book-specific exit code |
| Exit/health diagnostics | `python-engine/exit_quality.py`, `strategy_health.py` |
| Signal/execution evidence | `signal_log.py`, `fno_signal_log.py`, `penny_execution_journal.py`, existing ledger/order stores |
| Existing reports | `routes_commands.py`: `/strategy/funnel`, `/analytics/funnel`, `/analytics/outcomes`, `/analytics/edge`, `/analytics/suggestions` |
| Research and replay | `backtest_lab.py`, `routes_backtest.py`, immutable run archive and existing replay adapters |
| Scheduling | `scheduler_setup.py`, existing runtime/ops instrumentation and scheduler contracts |
| Dashboard | `node-gateway/client/src/pages/Dashboard.jsx`, `ResearchCenter.jsx`, `BacktestLab.jsx`, `Positions.jsx` |
| Gateway | Existing authenticated proxy/report routes and executor; follow current authorization conventions |
| Optional AI | `agent/agent.py`, `agent/advisory.py`, agent tests |
| Partner inputs and delivery | `partner_input_refresh.py`, `hedge_analytics.py`, `hedge_advisory.py`, `routes_hedge.py` |

First create a short implementation map of which existing stores/functions cover each contract. Extend compatible tables/endpoints with migrations; use a new module/table only where semantics require it. Do not create another independent P&L total, another competing halt switch or a standalone dashboard disconnected from current operations.

## Target operating flow and modes

`fresh completed data → candidate/watchlist → strategy proposal → cost/risk eligibility → portfolio selection → entry policy → confirmed execution or shadow simulation → exit policy → net outcome → research/health report`

All records carry an explicit mode: `LIVE`, `PAPER`, `SHADOW` or `REPLAY`. Partner recommendations and partner-confirmed executions use a separate account/domain and are never counted as this account's fills. A deterministic comparison run can simulate execution but cannot be labeled live.

New strategy sleeves start in SHADOW/REPLAY. Existing live policies remain unchanged unless a separately reviewed change is explicitly promoted. Use configuration switches following existing conventions; expose effective mode and policy version in the UI. New functionality must be runnable in Dev using documented commands and fixtures without editing Production environment files.

## P0 — Brief baseline/environment preparation, then proceed

1. Record baseline commit/status and preserve untracked review documents.
2. Use the existing Python virtual environment. Inspect the gateway runtime contract: the Dockerfile uses Node 20 while the reported host run used ABI 137. Validate in a supported matching Node environment or an isolated Dev test container with correctly built native dependencies. Keep lockfiles unless an intentional dependency change is required. Do not borrow a different-ABI binary or change Production containers to repair local tests.
3. Run focused baseline checks once. If a relevant test fails, distinguish environment failure from application failure and fix/document it. Work on independent milestones while a specific environment issue is being resolved.
4. Preserve the latest delivery authorization/guard/backoff/manual-resolution behavior. Add integration coverage if P6 touches it. Avoid restarting a broad audit loop as a substitute for product work.

P0 is not the assignment's final deliverable.

## Shared contracts

Use current repository naming where compatible. These are required semantics, not an instruction to duplicate existing schemas.

### Opportunity and proposal

- `opportunity_id`: stable across repeated scans of the same setup; new setup lifecycle creates a new ID.
- `decision_id`, `parent_decision_id`, `policy_id`, `policy_version`, `account_id`, `mode`, instrument identity and exchange.
- `observed_at`, `data_cutoff`, `evaluated_at`, `valid_until`, trading session and dataset/evidence version.
- Setup state, trigger/invalidation, entry policy, side, proposed units, initial stop, exit policy and capital required.
- Estimated round-trip charges, slippage allowance, estimated net outcome and uncertainty **when available**. Missing/unvalidated estimates remain null with a reason; an indicator score is not a win probability.
- Hard eligibility reasons, soft ranking features, portfolio constraints and final selected/deferred/rejected reason.

### Event and outcome

Append-only stage events include opportunity/decision IDs, mode, session, policy version, event time, deterministic reason code and idempotency key. Current status may be a derived projection; do not overwrite the only historical evidence.

Outcome links decision to submitted order IDs, fill IDs, partial quantities, average prices, entry/exit timestamps, gross P&L, actual/estimated cost status, net P&L and initial-risk denominator. Guard repeated fill callbacks with unique execution keys. Missing broker linkage is explicit, not guessed.

### Cash flows and account value

Persist deposits/withdrawals separately from trading returns. Reconcile `opening equity + net external flows + trading P&L − other expenses = closing equity`, with realized/unrealized components clearly separated and no double-counted fees. Deposits must not erase drawdown history. Record broker reconciliation residual and as-of time.

### Research run

Record frozen data hash, date split, policy/code version, all parameter values, execution/cost assumptions, universe membership, capital constraints, random seed if used, trial family, result and failure/unavailable reason. Re-running identical deterministic input produces identical decisions/outcomes.

## P1 — Visible activity and honest profitability

### Build

Instrument the existing candidate/allocation/execution paths with these conceptual stages: universe, data-ready, setup, cost-viable, risk-approved, selected, submitted, filled, managed, closed. Support explicit unavailable/rejected/deferred/expired outcomes at the relevant stage. Existing LIVE books should emit observational events without changing their trading decisions; new sleeves emit SHADOW events.

Extend the existing funnel/outcome APIs. Every response must include mode, session range, as-of time, counts of unique opportunities versus scan evaluations, sample size and unavailable reasons. Paginate event lists and avoid reading unbounded JSON histories on every scan.

Add scheduled inactivity diagnostics:

- Two missed expected scan intervals: operational-health finding.
- Two healthy eligible sessions with no viable candidates: inspect universe/data/soft-filter bottlenecks.
- Five eligible sessions with one or fewer fills: explain opportunity supply, costs, free cash, open positions, limits, nonfills and faults.
- A still-valid risk-approved/selected opportunity without a terminal order/non-submission result: flag the dropped workflow.

Use the exchange calendar and configured strategy sessions, not calendar-day arithmetic. Deduplicate unchanged findings; dashboard visibility is required, external message dispatch is not required for the offline milestone. No diagnostic may lower thresholds or create orders.

### UI deliverable

Extend Dashboard/Research Center with a readable activity funnel and “Why did we trade or not trade?” view. Show live, paper, shadow and replay separately. Show net realized P&L, unrealized P&L, funding flows, fees, capital in use and reconciliation state. Unknown data must not appear as zero healthy activity or zero loss.

### Acceptance

Provide fixtures for: active trading session; valid no-opportunity session; broken feed; capital tied in positions; cost-infeasible proposals; unfilled orders; missed scheduler run; deposit without profit; repeated fill callback; partial fill and final exit. Each must be visible through the real API/UI. A repeated candidate counts once as an opportunity. No production order behavior changes.

## P2 — Working proactive watchlist and three shadow sleeves

### Build common scanner/registry

Register `trend_pullback_v1`, `range_reversion_v1`, `contraction_breakout_v1` as proposed policy IDs (adapt naming to the registry). Implement the shared proposal interface and a watchlist lifecycle:

`WATCHING → ARMED → TRIGGERED → SELECTED/DEFERRED/REJECTED → EXPIRED/INVALIDATED/COMPLETED`.

Define allowed transitions; repeated scans do not reset expiry or create another execution. Revisit a deferred setup only when relevant data/capital/spread changes. Record the previous and new reason. Use completed bars and explicit feature cutoffs. Missing warm-up/history returns a diagnostic rather than a fabricated signal.

Implement configurable universe selection based on point-in-time liquidity, instrument validity, affordability and data coverage. A development starting capacity is 50–100 symbols only if profiling supports it; not an automatic mandate. Test 5–15-minute completed-bar scheduling for intraday variants, with exits/protection higher priority. New scanning must not add a full-history reload per symbol every tick.

### First deterministic research hypotheses

These starter rules are reproducible experiments, not optimized strategies or live recommendations. Reuse equivalent established feature functions when possible. Freeze each parameter set in the run manifest.

| Sleeve | Initial hypothesis to implement | Mandatory invalidation/exit behavior |
|---|---|---|
| Trend pullback | On completed 15-minute bars, positive fast/slow trend and relative strength; a recent pullback toward the fast trend followed by a close above the previous completed bar high. Parameterize trend windows and pullback tolerance. | Stop below observed pullback structure with existing minimum-distance/volatility safeguards; time expiry for entry; compare current baseline exit and trail. No entry assumed at an earlier bar's price. |
| Range reversion | A low-trend/range classifier, stretch below an observed reference such as session VWAP, followed by a completed-bar stabilization/reclaim. Parameterize deviation and stabilization window. | Long cash variant only for the small pilot; stop below observed stabilization structure, target toward reference, bounded holding period, invalidate when range premise fails. No averaging down. |
| Contraction breakout | Prior completed-bar range width contracts relative to a longer observed range; current completed close breaks the prior range with relative-volume confirmation. Parameterize range windows and contraction/volume thresholds. | Range failure stop, price ceiling/no-chase entry, bounded trigger validity; trail/time-exit alternatives. Calculate the prior range excluding the trigger bar. |

Select a small fixed set of initial parameter values based on available granularity, record them, and label results exploratory. Do not perform an undisclosed parameter sweep. Intraday and overnight policies are separate registry entries. Cluster trend/breakout overlap rather than assuming these are independent risks.

### Acceptance

For each sleeve: a synthetic positive case, negative case, missing data, incomplete bar, expired trigger, gap, repeated scan and regime invalidation. Demonstrate all three producing real proposal objects and flowing into P1 reports and the shadow allocator. A registry entry that always returns unavailable is not implementation completion.

## P3 — Portfolio choice and realistic shadow execution

### Build

Extend existing allocation with one shared capital/risk view for the new basket. At ₹8,000 choose among feasible sleeves, rather than reserving three tiny pools by default. Include capital tied in positions and pending orders; aggregate repeated ticker/sector exposure; recompute costs after share/lot rounding and downsizing. Cash and deferral are valid outputs.

When calibrated expected outcomes are unavailable, use a documented deterministic baseline ranking and label it uncalibrated. Preserve hard account/data/exposure controls. Shadow risk budgets are explicit research scenario inputs, not modifications to live settings or inferred user drawdown tolerance.

Implement/reuse a fill simulator driven by events after signal time. Support bounded marketable/limit policies, no-fill expiry, gap-through stops, partial fills if supported by source detail, fees, spread/slippage assumptions and session cutoffs. If bars cannot determine stop-versus-target ordering, apply a disclosed conservative policy or mark ambiguity. Never take the favorable path by default.

### UI deliverable

Show selected proposal, rejected alternatives, capital use, estimated costs, reason and current mode. Shadow trades need a visible SHADOW label on every relevant card/table/export. Show why the winning candidate was feasible and why another was not.

### Acceptance

Replay with ₹8k, ₹20k, ₹50k, ₹1 lakh and ₹5 lakh **scenario capital**; no real funding action. Fixtures cover unaffordable whole shares/lots, competing same-ticker sleeves, insufficient cash after fees, pending reservation and a no-trade result. Assertions include no negative cash/reserve breach and complete allocation reasons. Larger capital is not itself a promotion signal.

## P4 — Entry/exit research and a measured learning loop

### Build

Register comparable entry policies: baseline immediate-at-next-executable-event, bounded pullback limit, and completed-bar confirmation. Compare on the same opportunities, including missed trades and delay. Never silently drop unfilled candidates from performance comparison.

Connect `exit_quality.py` and `strategy_health.py` to actual scheduled outcome processing. Compare existing exit policy with a volatility trail, thesis invalidation and bounded time exit. Preserve broker-protection behavior. Record MFE/MAE and bounded post-exit excursion as diagnostics; do not present maximum excursion as achievable profit.

Extend Backtest Lab with chronological train/validation/final-test splits, frozen manifests and trial accounting. Display basket, each sleeve and basket-minus-each-sleeve. Metrics: net P&L/expectancy, costs, drawdown, underwater duration, opportunity/fill frequency, nonfills, turnover, capital utilization, uncertainty and data coverage. Compare at matched risk and capital. Reuse `/analytics/edge` where appropriate rather than creating a second contradictory edge verdict.

Build a simple calibration artifact from completed training outcomes, e.g. conservative grouped estimates with shrinkage. It must support `INSUFFICIENT_EVIDENCE`, versioning and deterministic fallback. No live parameter self-modification. Health/drift observations can recommend changes; automated exposure demotion must be separately tested and use existing control ownership.

### Acceptance

Provide a runnable research job and rendered UI results from deterministic fixtures. If real history exists, evaluate a frozen retained dataset and label limitations. If it does not, complete the machinery using fixtures and report real-data evidence pending. No claim of successful strategy validation from synthetic prices.

Tests: future-data perturbation cannot change earlier decisions; final-test data not used to train; repeated outcomes do not become new health evidence; negative/unavailable challenger retained in archive; incumbent remains unchanged when challenger fails. A report must identify every attempted variant, not just the winner.

## P5 — Optional AI that cannot stall essential operation

### Build

Separate AI initialization from agent startup. Missing model key/provider yields `AI_DISABLED`/`AI_UNAVAILABLE`, while deterministic alerts/watchdog continue. Essential risk/exit/order reconciliation is independent of AI.

Move reviews off the synchronous signal/alert path into a bounded worker queue. Define worker/concurrency limits, deadline, cleanup, cache key of decision+event version, circuit breaker and daily request/cost budget. Follow existing operator approval rules; sending a deterministic alert does not authorize automatic execution.

Return schema-validated annotations only: explanation, concerns, cited events, confidence label and unavailable reason. Immutable numeric fields, account, recipient and trade eligibility come from the deterministic proposal. A model may not override stops or hard rules. Preserve news source/publication time and instrument/company identity; discard stale/wrong-company context. Treat news text as data, not instructions.

Use AI first for inactivity explanation, partner-card wording, candidate second opinion and research summaries. AI ranking influence remains shadow-only pending measured benefit. Make the current swing AI veto an explicit reviewed policy change; no silent Production switch.

### UI and acceptance

Show review status, as-of time, sources, cost where known and late/expired status. Test absent key, provider outage, timeout, malformed response, full queue, late result, changed same-ticker decision and attempted numeric alteration. Core alert/watchdog behavior must remain demonstrably active with the provider completely disabled. Use fake providers/transports in tests; no paid API calls needed to complete P5.

## P6 — Partner portfolio lifecycle and usable hedge cards

### Build

Complete the source-neutral fixture adapter and lifecycle interface: external position/instrument identity, account/source, observation time, sequence, covered books, completeness, units/lots and market-field timestamps. Support new position, update, full close, reopen and corporate-action adjustment, not just reconciliation of pre-existing internal IDs.

Ensure lifecycle transitions invalidate/supersede advice through the existing revision/guard contract. Preserve immutable evidence. Upgrade historical rows conservatively; unresolved delivered/ambiguous history must not become permission to resend.

Expose deterministic hedge cards and delivery backlog/manual-resolution status in existing views. Cards show action, units, protected exposure, estimated cost, remaining risk, expiry and invalidation. Fresh complete fixtures must reach the real builders; model output cannot supply missing holdings/Greeks. Keep partner confirmation separate from Telegram acknowledgement.

### Acceptance

Offline end-to-end: fixture complete account → proposal → deterministic card → mocked delivery → mutation → supersession → fresh evaluation. Cover partial snapshot, missing marks/Greeks, corporate action, close/re-entry, adapter unavailable and ambiguous delivery. No live message required. The real adapter URL/account/credentials and partner canary may remain named external prerequisites; fixture lifecycle implementation may not.

## P7 — Integration, user-visible demonstration and operational readiness

### Required demonstration

Provide one documented command or task entry that seeds an isolated demo database and runs a deterministic multi-session scenario through the real services/handlers. Use clearly synthetic instrument/account names. Demonstrate:

1. Three sleeves generate and rank distinct opportunities.
2. One opportunity expires, one is unaffordable, one is selected and simulated through exit.
3. Costs, net outcome and funding appear correctly in the dashboard.
4. A five-eligible-session sparse-activity case produces the right diagnosis without a forced order.
5. An AI outage leaves deterministic processing functional.
6. A partner position lifecycle change invalidates old hedge advice and produces a new eligible review.
7. Research Center/Backtest Lab show comparable policies and explicit insufficient-evidence states.

Capture actual UI screenshots or equivalent verified browser evidence for the implemented views. Document fixture provenance; do not use a fabricated screenshot/mockup as proof of integration. Include run manifest, JSON output and relevant test logs in a dedicated implementation-evidence directory, separate from preserved audits.

### Runtime requirements

Measure job durations and resource usage on the available Dev environment. Bound scan concurrency, queue lengths and report queries. New research must not block position management. Use incremental features, current service limits and after-hours research jobs; do not add a cluster or GPU dependency. Document startup/restart recovery and schema rollback/forward compatibility. Do not silently drop outcomes under overload.

## Implementation order and continuation rule

| Sequence | Work | Required outcome before considering it finished |
|---|---|---|
| 0 | P0 | Reproducible Dev environment/baseline, named blockers; continue independent work. |
| 1 | P1 plus shared contracts | Real events, reports and UI for activity/outcomes. |
| 2 | P2 + P3 | Three working shadow sleeves, proactive watchlist, allocator and simulated lifecycle. |
| 3, parallel where independent | P5 and P6 | Optional AI and complete fixture partner lifecycle. |
| 4 | P4 | Working comparison/calibration/health pipeline consuming outcomes. |
| 5 | P7 | Integrated demonstration, verification, docs and release checklist. |

Use small commits and keep a progress table in an implementation log. **Finishing one milestone is a checkpoint, not completion of this assignment. Continue through all independent milestones without asking whether to do the already-specified next package.** If interrupted, leave exact next steps and resume from them. Do not infer that a context reset cancels the remaining scope.

A genuine blocker must name the missing input, the specific dependent feature and what was completed with fixtures. Do not describe “no production approval,” “no AI key,” “no proven edge” or “no real partner adapter” as blocking all product implementation.

## Definition of done

- P1–P7 implemented with real consumers and existing UI integration; not only stubs, pure helpers or unused tables.
- Representative existing strategies emit observational events, new sleeves run SHADOW/REPLAY, and modes never mix in P&L.
- Inactivity diagnostics explain both legitimate inactivity and broken workflows.
- New strategy/AI/adapter fixtures exercise actual interfaces without external effects.
- Entry/exit comparisons and uncertainty-aware evidence reports are runnable and visible.
- Relevant Python, agent, gateway and client tests pass in their supported runtimes; scheduler contracts and migration checks pass where changed. Report exact commands/counts. A native-binding failure remains a test limitation until corrected; do not call a partial gateway run fully green.
- Documentation includes setup, flags/modes, schema/API changes, demo command, results, rollback and remaining real-world prerequisites.
- No new live activation, Production mutation, broker order, partner message, funding transfer or fabricated profit claim.

### Required final completion table

List P0–P7 with one of: `IMPLEMENTED_AND_TESTED`, `PARTIAL`, `BLOCKED_SPECIFIC_DEPENDENCY`, `NOT_STARTED`. For each include commit, API/UI consumer, test/demo evidence and remaining work. Separately list strategy status (`RESEARCH_IMPLEMENTED`, `SHADOW_OBSERVING`, `EDGE_NOT_DEMONSTRATED`, or evidence-backed later states). “Research implemented but no proven edge” can be a completed software milestone; “only delivery safety implemented” cannot be a completed product build.

## Copyable instruction for the next developer

> Implement `docs/2026-09-06-proactive-intelligence-product-build-spec.md` in the Dev checkout, starting from the current branch. This is the full P1–P7 product build, not another safety-only increment. Preserve existing delivery safeguards and audit artifacts. Build the activity/profitability views, three working shadow strategies, portfolio simulation, entry/exit research, optional asynchronous AI, partner fixture lifecycle and integrated demonstration. Continue through every independent milestone; external credentials or live approval must not block fixture/shadow work. Keep Production and all live sends/orders untouched. Deliver small commits, updated progress documentation, tests and the required P0–P7 completion table. Do not claim completion after a subset of milestones.
