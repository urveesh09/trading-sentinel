# Trading Sentinel: market intelligence audit and next development plan

Date: 7 September 2026. Reviewed Dev HEAD: `7740452` on the existing correction branch. Previous checkpoint: `463608a`.

## 1. Owner-readable verdict

Substantial development is complete. Sentinel now has a useful persistent research and demonstration system: three strategy hypotheses, watchlists, simulated positions and cash, outcome comparisons, partner lifecycle fixtures, optional asynchronous AI and dashboard evidence. This is considerably beyond the previous checkpoint.

The next assignment must move from fixture demonstrations to **market-data evidence and better capital decisions**. The scheduled proactive workflow still reads a local SHADOW fixture. Its three strategy scores are not comparable, and its allocator can commit almost all available cash to its first selection. Neither the green tests nor the synthetic P&L establish an income-producing edge.

One research isolation defect was independently reproduced. Correct it promptly, then continue the broader work below; do not treat that correction as completion of this assignment. There is substantial Dev-only product work still possible without external credentials. The remediation log's statement that no further Dev-only implementation is deferred is too broad relative to the owner's income objective and the earlier full product specification.

No credible percentage of “passive income system complete” can be given. Software components can be counted; a profitable edge requires market evidence. Section 2 separates those categories rather than inventing a completion percentage.

Owner constraints carried forward:

- Approximately ₹8,000 now; original ₹5,000 funding is not evidence of ₹3,000 trading profit. Later capital stages: ₹20–50k, ₹1 lakh, eventually ₹5 lakh, only as confidence and evidence justify.
- Proactive scanning and useful opportunities matter. A broken or starved pipeline must not remain silently inactive for days. Trade quotas must not manufacture low-quality trades.
- Partner hedging has priority over directional F&O tips.
- AI may help research and explanations, but deterministic signals, risk checks, position protection and operation must continue without it.
- The target is higher sustainable **net** earnings with controlled losses and low operating burden. Fast massive profit with little risk is not an engineering guarantee. Risk tolerance, loss limits and withdrawal target remain owner inputs, not inferred permissions.

## 2. What has been implemented, and what is still left

This table describes the inspected Dev changes, not changes made during this audit and not deployed Production behaviour.

| Earlier workstream | Present implementation | Remaining work |
|---|---|---|
| Clock/run correctness | Durable run steps, input digests, persisted economic assumptions, visible-bar filtering, cost-aware resumed management, repairable/transactional position evidence | Cross-run expiry correction; stronger code/data/policy provenance; comprehensive lifecycle scope tests |
| Watchlists and scanning | Persistent lifecycle, pending expiry, fixture-backed scheduled workflow, invalid/unavailable input distinctions | Real completed-bar provider; existing live-book instrumentation; independent liveness and freshness evidence |
| Synthetic account | Persisted fills/exits/marks, reserved cash, costs, account/run UI distinctions | Stop-risk sizing, comparable ranking, basket exposure limits, realistic execution/cost model and broker reconciliation |
| Research comparisons | Immutable matched trials across three entry profiles and two exit profiles; retains no-fill/open/invalid outcomes; report/UI | Frozen historical folds, baseline comparison, uncertainty, capital-constrained portfolio evaluation, calibration and controlled promotion |
| Partner lifecycle | Atomic fixture snapshot promotion; option fixtures; close/reopen/corporate-action evidence; read-only cards and delivery backlog | Actual source integration and mapping; operational freshness monitoring; quantitative hedge alternatives and authorised delivery evidence |
| Optional AI | Bounded pending queue, TTL cache, daily request counter, circuit breaker, status surface; three queue tests pass | Bound retained state; restart-safe budget; dispatch-time circuit enforcement; independently prove outage isolation; useful late-result attribution |
| Integrated demonstration | Reproducible offline command, cash/position/research/partner evidence, synthetic UI mode | Registered scheduler + authenticated API + UI integration with demo mode disabled; actual provider failure injection; market forward evidence |

Recent development includes `50b52f5`, `474d4ca`, `4609226`, `c3461ef`, `e12c001`, `731ffdf`, `1a89b4b`, `b75765d`, `298c70b`, `68d772f`, `e0dbb5d`, `31d6e4c`, `af8d6ce`, `8ac2ab7`, `f7702e0`, `e8e168d`, and `7740452`. Their themes are reflected above. This is a change-range assessment, not a claim that all commits happened today.

The audit created only this plan and offline evidence/probes. It did not implement those product commits, change Production, send a message or place an order.

## 3. Independent verification and limits

Executed from Dev with its existing Windows Python environment:

1. Python: `tests/test_proactive_intelligence.py`, `test_partner_fixture_adapter.py`, `test_partner_input_refresh.py`, `test_hedge_advisory.py`, `test_hedge_routes.py`, `test_integrated_dev_demo.py`, `test_optional_ai_status.py`, `test_partner_lifecycle_demo.py`: **94 passed**.
2. Agent: `tests/test_async_reviews.py`: **3 passed**, using the same Python interpreter. This is not verification of every agent dependency or full agent startup.
3. Gateway: `tests/unit/executor.test.js` and `tests/integration/experiments-proxy.test.js`: **60 passed**. Full native database-dependent gateway suite was not rerun.
4. Client: `npm run test:unit`: **23 passed**. `npm run build`: passed. Existing dependency/deprecation notices are not blockers to this audit.
5. Integrated offline script: passed, output in [integrated audit evidence](2026-09-07-integrated-audit-evidence.json), isolated databases under `review-2026-09-07-next-plan/`.
6. Additional [audit probe](review-2026-09-07-next-plan/test_review_probes.py): **one reproduction passed**, meaning the undesirable cross-run mutation occurred. This is defect evidence, not a passing product acceptance test.
7. `git diff --check`: passed before document creation; final check required after the plan is written.

The integrated demo explicitly does not start a scheduler or contact external services. Its AI portion writes an `OUTAGE_CIRCUIT_OPEN` status fixture; it does not itself force a real worker/provider failure while measuring downstream latency. Its assertion names must not be interpreted as stronger evidence. Earlier UI evidence mode renders fixtures; it does not prove an authenticated network path. This review did not remeasure current Production P&L or independently re-open the browser. Do not substitute these Dev results for either.

## 4. Corrections and engineering gaps

### C1 — High priority: isolate expiry by account, run and evaluation clock

Location: `python-engine/proactive_intelligence.py`, `_expire_pending_shadow_watchlists` and its `run_shadow_workflow` caller.

Confirmed: the expiry SQL selects every matching pending watchlist in the database, without account/run/mode scope. Running account B at September 2 expired account A's September 1 pending watchlist even though account A's own replay clock had not advanced. This invalidates independent scenario research. It is not evidence of a live order fault.

Required implementation:

- Pass the resolved run storage identity into expiry; scope joins and updates to that identity and intended mode. Use the run's validated evaluation clock.
- Expire every supported unfilled deadline-bearing state. Current SQL covers WATCHING, ARMED, SELECTED, but omits TRIGGERED and DEFERRED; cover them explicitly or document/test why they cannot exist in this workflow.
- Keep watchlist state and EXPIRED event atomic, or persist a recoverable outbox. Current sweep commits states before the caller writes events, so a crash can lose expiry evidence.
- Never expire a genuinely filled position; never advance another run's clock or rewrite another run's reason.

Acceptance: two accounts and two runs of one account sharing a DB; advancing either cannot change the other. Include different origins, every pending state, concurrent processing, and failure between expiry/state evidence writes. Convert the audit probe into a regression asserting that the foreign row remains WATCHING.

### C2 — Required before interpreting basket performance: size by risk, not all remaining cash

Locations: `build_shadow_proposals`, `size_shadow_allocations`.

Code inspection: sizing uses `floor(free_cash / cost_adjusted_entry_price)` for each sorted candidate. `max_loss` is calculated after selection; there is no corresponding stop-risk budget cap in this helper. The first candidate can consume effectively the whole budget. Also, trend score is an MA ratio, range score a fractional distance, and breakout score a volume ratio. Sorting these raw numbers makes scale affect preference rather than comparable expected net returns.

Implement a separate versioned SHADOW allocator with quantity constrained by cash, affordable transaction costs, loss-at-stop including a gap allowance, per-name concentration, total open risk and correlated exposure. Retain the old allocator as a baseline. Do not silently replace existing live sizing.

Acceptance: a wider stop cannot increase quantity; simultaneous risk and cash reservations remain bounded; fees cannot create negative cash; incomparable scores cannot masquerade as calibrated probabilities; low capital may legitimately support only one position. Use owner-approved limits for live operation; experimental limits belong to named research manifests.

### C3 — Operational AI hardening, without making AI a gate

Location: `agent/async_reviews.py`.

Code-inspection findings: `_states` has no eviction, although pending work and cache are bounded; daily request counters are process memory and reset on restart; the worker does not recheck an opened circuit before invoking the reviewer for tasks already queued. These are operational gaps, not failures demonstrated by the three current tests.

Add TTL/maximum retained states, a persisted/reserved daily budget for provider calls, explicit deadline/timeouts and dispatch-time circuit policy. Define whether abandoned reservations consume budget. Ensure a failed provider cannot keep spending through an already queued backlog. Test multiple restarts and queued tasks when the circuit opens. A hung provider must not block core operation or spawn unlimited replacement threads.

### C4 — Research provenance is still incomplete

`_ensure_shadow_run` stores capital, fee/slippage and the fixed label `three-sleeves-v1`. Research manifests retain inputs/profile names but do not freeze the full implementation identity. Reusing labels after code changes can combine different semantics under one run.

Record code SHA, schema version, actual strategy/entry/exit/risk parameters, provider/instrument mapping, dataset hash/version, timestamp convention, calendar, adjustment policy and cost-model version. Reject incompatible reuse. Replaying the same manifest on matching code/data should reproduce results; revised code requires a new run or explicit migration lineage.

### C5 — Evidence coverage is narrower than full product integration

`run_configured_shadow_workflow` consumes a local fixture. References inspected for the proactive event writers are confined to proactive workflow/demo/tests; the existing engine/portfolio live books do not yet populate this new funnel through those writers. `strategy_health.py` and `exit_quality.py` are not integrated into this new research consumer. The matched research runner is called from the demo/tests, not a completed general market research job pipeline.

Implement the integration packages below. Preserve the useful existing modules rather than adding a second competing analytics stack. Describe evidence as component, offline integrated, authenticated integration, forward-shadow or broker-reconciled; never collapse these into one “complete” flag.

## 5. Next development programme: ten improvements tied to earnings

The first delivery wave is W1–W4, with W8 partner integration proceeding independently. W5–W7 build on those results. W9 supports them; W10 is the final operational gate. Missing live credentials must not stop adapter contracts, recorded fixtures, tests or offline integration.

### W1 — A trustworthy market-data path

Reuse the current data/cache/calendar infrastructure. Add a provider interface supplying completed historical and current bars to the same proposal builder. Separate decision data from subsequent outcome bars; make future bars inaccessible to the decision interface. Persist exchange timestamp, received timestamp, instrument ID, provider, adjustment version and missing/stale reason.

Start with liquid instruments the account can actually afford and existing supported timeframes. Refresh watchlists on completed bars; manage open exposure on the existing appropriate risk schedule. Partition scheduled attempt, completed evaluation and data freshness metrics. A healthy scheduler with stale prices is not a healthy scanner.

Acceptance: captured real-format responses and malformed/stale/duplicate/corporate-action cases; session boundary and holiday tests; restart catch-up without duplicate economic events; one read-only market-shadow session when data access is available. Deliver provider contract, implementation, scheduler registration, recorded fixture and health UI. Keep all order consumers disabled for this new stream.

### W2 — Actual net profit and lost-opportunity accounting

Connect existing live-book events observationally to the unified funnel using stable decision/order/fill IDs. Retain original book and mode. Reconcile opening equity + deposits - withdrawals + net trading result - separate operating expenses to closing equity, with consistent treatment of fees to avoid double subtraction. Separate realized, marked unrealized and funding movements; record valuation timestamps and unresolved differences.

Map every risk-approved candidate to submitted, expired, superseded, rejected or unfilled status. Report losses attributable to adverse selection, delay/slippage, costs, gaps, exit policy and infrastructure errors where evidence permits; use UNKNOWN instead of invented attribution. Broker acknowledgements alone cannot establish fills.

Acceptance: deterministic broker statement/order/fill fixture with partial fills, cancels, charges, expenses and funding; replay is idempotent; reconciliation residual is zero within documented currency rounding or explicitly unresolved. UI answers: “What did I earn after costs?”, “What is at risk?”, “Why did a good opportunity not trade?”

### W3 — Risk-sized, comparable strategy basket

Implement C2 and rank strategies using held-out, shrinkage-adjusted net expectancy per unit of risk, with uncertainty and capacity penalties. Until comparable evidence exists, use explicit bounded experimental sleeve weights rather than comparing raw scores. Keep symbol and sector/exposure overlap constraints, and reserve room for position protection before new entries.

Evaluate three existing hypotheses first: trend pullback, range stabilization/reversion and contraction breakout. Use completed-bar regime features to record suitability, then test regime-conditioned allocation against fixed weights. Avoid proliferating indicators or optimising dozens of thresholds. At ₹8k, evaluate both one-position and small-basket feasibility after integer-share sizing and all costs.

Acceptance: common-cash event-time portfolio replay, benchmark against present allocator and fixed weights, no impossible capital reuse, risk/concentration invariants, and a report showing participation versus net return and drawdown. The basket must earn its complexity through evidence.

### W4 — A real historical research and learning pipeline

Connect the matched-trial archive to Backtest Lab, strategy health and exit quality. Freeze train/validation/test boundaries before selection; purge overlapping holding windows at fold boundaries; fit transforms only on past training data. Keep all attempted variants, failed runs and no-fills. Include simple existing-strategy and suitable passive/cash benchmarks with consistent exposure/cost conventions.

Store both matched-opportunity comparisons and capital-constrained portfolio paths. Independent cash-per-trial results cannot be summed into an achievable portfolio return. Include sample counts, net expectancy, drawdown, turnover, exposure, fill rates, loss tails, profit concentration and uncertainty computed with dependence-aware blocks. Twenty closed outcomes is a collection threshold, not proof of edge or a capital-increase gate.

Acceptance: immutable fold manifests; no fold leakage; a rejected/unprofitable challenger is a valid result; chronological holdout remains untouched until rules are frozen. Deliver one end-to-end research job and API/UI result using available historical data, or explicit missing-data status with recorded test evidence. No automatic live promotion.

### W5 — Better entry timing and execution economics

Use the existing three entry profiles as challengers: next executable open, bounded pullback limit and completed-bar confirmation. Measure missed-fill opportunity cost alongside filled-trade profitability; evaluate entry delay, spread, gap and participation limits. Limit orders must not receive optimistic fills just because a candle touched a price; define conservative ordering/queue assumptions and stress them.

Replace generic percentage-only fees with a versioned segment/product/date-aware estimate and broker reconciliation when available. Compare results under normal and stressed spread/slippage/fees. Any proposed execution change must use the existing protected executor and ambiguous-order reconciliation.

Acceptance: same opportunities/clock/cash, retained no-fills, marketable-gap rejection, cost sensitivity and end-to-end submit-to-fill timing. Choose a winner only using the W4 protocol; otherwise retain the incumbent.

### W6 — Better exits before more trade frequency

Connect existing exit-quality analysis to trade paths: maximum favourable/adverse excursion, profit giveback, time spent unproductive and stop/gap loss. Compare the current stop/target/time rules with a small frozen set of time-stop and volatility/trailing challengers. Do not assume tighter stops or earlier break-even moves improve profit.

Record every exit decision with policy version and available data. Preserve deterministic protective management during AI, feed and gateway degradation; stale data must trigger the existing explicit risk policy, not fabricated marks.

Acceptance: matched entries, realistic costs on any partial exits, gap-through-stop handling and same-bar ambiguity handled conservatively. Report additional net profit versus additional drawdown/turnover, not only win rate.

### W7 — Proactive activity with intelligent diagnosis

Extend existing two/five-session diagnostics to real account/policy streams. Each completed-bar interval should explain universe coverage, data availability, setups, net-cost viability, risk decisions, reservations, execution and management. Detect an eligible candidate lost between stages separately from a legitimate no-trade day.

Escalation order: repair broken/stale inputs; repair dropped workflow decisions; improve universe coverage within liquidity constraints; test complementary strategy/regime coverage; only then research threshold changes. Never reduce risk controls to satisfy a trade count.

Acceptance: missed jobs, stale data, starved capital, no viable setup and broker rejection produce distinct findings; offline replay produces a daily owner digest with an actionable reason. Useful activity is measured by healthy coverage and retained positive-value opportunities, with net results and risk alongside frequency.

### W8 — Hedge-first partner intelligence

Finish the actual source adapter contract and recorded-response integration using immutable account binding, complete snapshots and existing delivery safeguards. Add deterministic hedge alternatives with exposure before/after, protection range, premium/transaction cost, expiry/liquidity, known limitations and the event that invalidates the advice. Evaluate reducing exposure and doing nothing alongside permitted option structures; hedge premium is a cost, not guaranteed additional income.

Prioritise material unprotected exposure, expiring protection and stale portfolio data. Suppress repeated/economically unchanged advice and lower-value directional noise. Compare hedge outcomes against the same unhedged portfolio using recorded marks and explicit assumptions; measure drawdown reduction, cost and forgone upside.

Acceptance: create/update/close/reopen/corporate action plus quote staleness; account/destination scope; no duplicated delivery after acknowledgement; existing ambiguous-send recovery preserved. Dev can complete transport/provider fakes and UI now. Actual partner mapping, approved source, messaging destination and live canary remain external inputs/authorization, not reasons to stop independent work.

### W9 — Optional AI that contributes measurable value

Complete C3. Use AI for source-linked event summaries, counterarguments, anomaly explanations and bounded research proposals. Store source timestamps, model/prompt identity, availability and cost. Treat external text as data and prevent it changing risk rules, credentials or order fields. Persist late annotations by decision ID so work is useful after the initial alert rather than dependent on resubmitting the same signal.

Evaluate AI-assisted selection/explanation against the same deterministic baseline on held-out opportunities; count fees, latency and model expense. A helpful narrative is not a validated probability. Numeric confidence needs calibration before use in research ranking and must never become unconditional live authority.

Acceptance: key absent, startup failure, slow provider, malformed answer, queue saturation, restart budget and circuit-open backlog tests. Drive actual fake-provider failure while deterministic scanning/management proceeds; do not merely write a status fixture.

### W10 — Operational reliability and staged capital gates

Build a Dev integration harness that starts registered jobs under a controlled clock, uses authenticated engine/gateway APIs and the real UI with evidence-demo mode disabled. Inject restart, stalled feed, locked database, expired auth, rejected order, partial fill and provider outage through safe fakes. Record request traces, state invariants and UI evidence. Use the supported gateway runtime for native binding checks.

Separate software acceptance, forward-shadow observation and authorised broker canary. A capital increase requires reconciled net results, representative independent market observations, acceptable drawdown/loss concentration, realistic cost sensitivity, functioning protective management and owner review. A short winning streak, synthetic return or elapsed number of days is insufficient.

Keep ₹8k as the current capital assumption. Model ₹20–50k/₹1lakh/₹5lakh scenarios for capacity and affordability, but do not change funding, exposure or execution limits automatically. Define owner-approved daily loss, total drawdown, open-risk and concentration limits before any new live allocation. Pending those inputs, build configuration/validation and SHADOW scenarios rather than guessing authorization.

## 6. Delivery sequence and what “done” means

| Checkpoint | Required deliverables | Completion gate |
|---|---|---|
| A: trustworthy foundation | C1, C3, C4; scope regressions; precise evidence labels | No foreign-run mutation; bounded AI state/budget; reproducible manifests; focused tests |
| B: market/data/account bridge | W1 and W2; existing live-book observational producers; authenticated dashboard data | Recorded-provider integration and reconciled fixture; explicit real-data prerequisites |
| C: capital and research | W3 and W4 | Risk-sized basket, frozen folds and real job/API/UI; truthful accept/reject/insufficient result |
| D: smarter decisions | W5, W6, W7 | Entry/exit comparisons and proactive diagnosis against fixed baselines |
| E: partner and optional intelligence | W8 and W9, independently alongside B–D | Hedge-first cards; source/lifecycle evidence; independently exercised AI outage |
| F: full Dev acceptance | W10 | Real authenticated integration harness, restart/failure evidence, final requirements matrix |
| G: operational evidence | Authorised forward-shadow/data operation, then separately approved live canary | Reconciled external evidence; GitHub promotion; no implied permission to send/trade |

Every checkpoint report must name commits, tests, artifacts, remaining requirements and external inputs. A checkpoint is not permission to silently narrow the entire programme. Continue independent Dev work after each checkpoint until the Dev programme is complete or an actual dependency blocks it.

Acceptance matrix columns: requirement ID; file/function; test or runtime evidence; mode; status (implemented/verified/blocked/deferred); exact dependency. Never mark an item complete solely because a route or screenshot exists. Never carry fixture evidence into live performance totals.

## 7. Copyable assignment for the next developer

> Work only in `C:\Users\Urveesh\Desktop\trading-sentinel`, starting from the current branch after checking HEAD/status and preserving prior audits. Implement this plan's Dev programme, beginning with C1 cross-run expiry and atomic expiry evidence, C3 bounded/restart-aware AI operation, and C4 provenance. Continue into W1–W10 through checkpoints A–F; do not stop after one correctness patch. The commercial objective is higher sustainable net earnings with controlled losses, useful activity and hedge-first partner advice. Reuse the existing engine, risk/executor, Backtest Lab, strategy-health and exit-quality infrastructure. Add real-market-data SHADOW plumbing, observational live-book accounting, comparable risk-sized portfolio selection, historical validation and entry/exit learning before claiming intelligence or edge. Keep AI optional. Build provider/transport fakes and authenticated integration when credentials are absent, and list only the genuinely external remainder. Preserve all delivery ambiguity/claim safeguards. Do not edit Production, activate new live strategies, increase capital, send partner messages or place orders. Deliver commits, exact verification results, immutable research evidence, integrated UI/API proof and a requirements completion matrix. Promotion is through GitHub and requires the separate applicable operational authorization.

## 8. Research principles informing this plan

Searching many strategies and reporting the best backtest creates selection bias; trial accounting and out-of-sample evaluation matter. This is why W4 records all variants and does not treat a small positive sample as promotion evidence. [Bailey and López de Prado, The Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf).

Successful API order placement does not imply execution. W2/W5 therefore require actual fill and reconciliation evidence. [Kite Connect order documentation](https://kite.trade/docs/connect/v3/orders/).

The strategy improvements above are testable engineering/research proposals, not claims that these strategies will produce a particular return. The commercial question at each checkpoint is: did this improve reproducible net results or remove a demonstrated source of loss, at acceptable risk and operating cost?
