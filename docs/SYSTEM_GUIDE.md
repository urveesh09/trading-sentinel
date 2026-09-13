# Trading Sentinel — system guide and engineering handover

## 1. Read this first

This is the canonical architecture and feature guide. It is paired with [the code atlas](SYSTEM_CODE_ATLAS.md), [the next-agent plan](NEXT_AGENT_PLAN.md), and [the handover checklist](HANDOVER_CHECKLIST.md). Snapshot date: September 12, 2026. It describes the Dev source, not an assertion that all features are enabled or deployed.

The immediate handover is a bounded engineering deliverable. The broader objective—reliable, cost-aware trading income and valuable intraday partner advice—is not proven achieved. No documentation, test count, model score or green container demonstrates profitability.

**Environment rule:** assess Production at `C:\Users\Urveesh\Desktop\Production_Trading-sentinel`; change Dev at `C:\Users\Urveesh\Desktop\trading-sentinel`; promote through GitHub. Do not copy code directly into Production. Preserve persistent data volumes. Never run `down -v` as part of routine deployment.

Dev branch for this work: `codex/production-correction-hedge-p0`. The release runbook currently names `evolve/smart-strategies`; verify the actual PR target and checkout rather than assuming `main`. See [deployment verification](deployment-verification-runbook.md).

## 2. Product purpose and user constraints

There are two distinct products sharing infrastructure:

1. Sentinel trades/researches the owner's own strategies, with real, paper and shadow modes kept separate.
2. Sentinel provides useful manual intraday advice to an independent partner trading NIFTY and SENSEX. It does not execute that partner's orders.

The owner currently describes approximately INR 8,000 of test capital, originally INR 5,000, with possible progression to INR 20–50k, INR 1 lakh and eventually INR 5 lakh after confidence improves. Deposits are not trading income. No fixed withdrawal target or accepted drawdown percentage was agreed. The owner wants proactive opportunity discovery, not forced trades merely to achieve a daily quota.

The partner trades only intraday, prioritizes hedging, and uses larger capital independently. General market setup advice does not require their personal strategy, broker credentials or a fabricated portfolio. Personalized portfolio protection requires actual exposure evidence; conditional protection requires explicit coverage assumptions. These must not be confused.

An explicit intraday profile was previously observed in Production. The previously observed risk ceiling is configuration evidence, not an endorsement of that risk. Recheck effective settings and the saved profile; do not ask the user to repeat completed setup without evidence it is missing.

## 3. Runtime topology

| Layer | Entry points | Responsibility | Principal boundary |
|---|---|---|---|
| Reverse proxy | `node-gateway/nginx/nginx.conf`, `docker-compose.yml` | HTTP ingress, upstream routing, independent proxy health | Healthy proxy is not healthy trading |
| Gateway | `node-gateway/server/index.js`, `app.js` | Express app, authentication, broker API services, engine proxy | Order endpoints have real side effects |
| Engine | `python-engine/main.py`, `scheduler_setup.py` | FastAPI, scheduler, strategies, persistence and research | Feature flags and risk gates determine authority |
| Dashboard | `node-gateway/client/src/App.jsx`, `pages/Dashboard.jsx` | Operator views, source/readiness explanations, research UI | Display is not independent broker reconciliation |
| Optional agent | `agent/agent.py`, `advisory.py`, `async_reviews.py` | Typed AI review and asynchronous annotation | AI cannot grant order or delivery permission |
| Persistence | Compose named data volume, engine SQLite, gateway DB schema | Durable books, positions, claims, research journals | Account/mode/run scope is mandatory |
| Operations | release stamps, health, telemetry, watchdogs, autoheal | Detect liveness/deployment failures | Restart success is not correctness evidence |

The Compose stack includes the three application services, nginx, ngrok and autoheal. Dependencies start best-effort rather than requiring every service to be healthy first. Read the actual Compose resource limits and healthchecks before changing concurrency.

## 4. Authority and evidence types

| Type | Meaning | Must never be presented as |
|---|---|---|
| LIVE | Broker-facing trading path with its own controls | Guaranteed broker-reconciled profit merely because mode says LIVE |
| PAPER | Simulated execution/accounting | Real income |
| SHADOW | Proposal/evaluation/fixture evidence without execution authority | Actual fills or partner delivery |
| REPLAY | Historical or chronological study using declared assumptions | Live observations or held-out proof when tuned on the same data |
| Operational status | Jobs, heartbeats, retries, readiness | Trading opportunity or edge |
| Strategy qualification | Reviewed evidence for a specific policy/index/profile scope | Permission for every strategy or perpetual profitability |

The safe direction of dependency is market inputs → deterministic strategy → validation/risk → applicable execution/delivery authority. Research and AI annotate this process; neither bypasses it.

## 5. Trading feature map

### Core equity and momentum

`engine.py` supplies signal calculations; `regime.py` and `breadth.py` provide market context; `universe.py` supplies the candidate universe. `portfolio.py` and `risk_engine.py` filter/allocate, with `main.py` composing scheduled application behavior. `position_tracker.py`, `momentum_exits.py` and `chandelier_stop.py` participate in position/exit management. `momentum_paper.py`, `momentum_shadow.py`, `momentum_replay.py`, `backtest.py` and `walk_forward.py` provide separate simulation/research surfaces.

Do not infer live performance from a backtest or change a shared exit helper without checking its live and paper callers. A viable signal still needs executable pricing, sufficient capital, risk approval and current data.

### Penny and EDGE

`penny_scanner.py` and `penny_universe.py` handle scanning/universe preparation. Engines include `penny_engine_breakout.py`, `penny_engine_connors.py` and `penny_edge_engine.py`. `penny_edge_orchestrator.py`/`penny_edge_live.py` compose EDGE behavior. `penny_risk.py`, `penny_executor.py`, `penny_position_reservations.py` and `penny_execution_journal.py` cover risk, submission/reservations and durable execution evidence.

Related modules provide regime/sector filters, health, signal logs, attribution, heatmaps, static company data and backtests. See all `penny_*` entries in the atlas. These are a family of strategies, not one fungible P&L stream. Small expected gains are especially sensitive to costs and thin liquidity.

### F&O

`fno_models.py` defines contracts/quotes/directions. `fno_instruments.py` builds contract indexes, expiries, lots and strike metadata. `fno_underlyings.py` distinguishes index/exchange scope. `fno_chain.py` obtains chain snapshots and strike selection. `options_math.py` supplies options calculations.

`fno_engine_mom.py` evaluates the ORB/momentum policy: opening-range structure, volatility/trend/volume context and thesis levels. `fno_gates.py`, `fno_risk.py`, `fno_executor.py`, `fno_positions.py`, `fno_orchestrator.py` form the separate trading path. `fno_defined_risk.py` and `fno_dr_book.py` provide defined-risk spread logic/bookkeeping. Analytics, OI store, signal log, shadow and report modules retain separate evidence.

Earlier Production audits reported negative F&O performance. A dominance of `no_or_break` is not itself proof that a filter should be loosened. Reproduce losing trades and distinguish data/session defects from genuinely absent setups.

## 6. Broker execution and accounting

Gateway files `services/kite.js`, `executor.js`, `risk-geometry.js`, `halt-switch.js` and `routes/orders.js` deserve focused review before any execution change. `token-store.js`, `token-restore.js`, `routes/token.js`, engine `token_lifecycle.py` and `kite_client.py` handle the authentication/provider bridge. Do not log secrets or infer an authenticated broker session from a process heartbeat.

`performance.py` owns ledger functions used by the application. `performance_analytics.py` and `performance.py` must be read with the relevant position stores. `broker_reconciliation.py` and `reconciliation_evidence.py` distinguish imported external statements from internal ledger/position observations. `order_execution_readiness.py` reports order-path evidence; submitting a real order merely to turn UNVERIFIED green is not a valid test plan.

Five reconciliation warnings were previously observed in the UI. Historical screenshots are not current facts. Investigate by account, module, execution mode, close identity and fee treatment; do not overwrite one store to match another. Broker confirmation, net cash and gross position P&L can have different timing and cost conventions.

## 7. Partner manual-advisory flow

1. `partner_orchestrator.py` selects NIFTY/SENSEX specifications and loads profile/effective settings.
2. `fno_signal_scan.observe_underlying` fetches futures bars and evaluates public conditions without an option-chain dependency.
3. Each completed public management path runs before optional new-entry chain work; this prevents a slow first-index chain from blocking the other index's lifecycle updates.
4. `attach_entry_chain` and expiry resolution obtain candidate inputs only where needed.
5. `partner_manual_advisory.build_directional_debit_spread` constructs a defined-risk directional candidate; conditional protection follows a distinct explicit-assumption path.
6. Candidate validation checks contract/exchange/lot consistency, two-leg economics, freshness, liquidity and profile constraints.
7. Qualification remains separate from input readiness and profile validity.
8. Persisted delivery claims, final authorization and Telegram transport govern an eligible card. Research evidence alone cannot deliver.
9. Public invalidation/target updates and clock-only intraday reminders manage published ideas; they do not claim the partner took or closed a position.

`partner_manual_advisory.py` centralizes profiles, candidates, research artifacts, qualifications, feedback and public updates. Read its schema/declarations in the atlas. `partner_thesis.py` shares pure invalidation/target rules with research. `partner_bot.py`, `partner_content.py` and legacy parts of `partner_orchestrator.py` also exist: do not accidentally re-enable old naked-option/status messages while enabling the new pathway.

Current policy remains INTRADAY, with an entry cutoff, reminder and management deadline represented in candidate data. Historically configured times were 14:45, 15:10 and 15:15 IST. Verify current settings; exchange closing hours are a different concept from Sentinel's deliberately earlier deadline.

## 8. Portfolio hedge pathway is separate

`hedge_advisory.py`, `hedge_strategies.py`, `hedge_analytics.py`, `hedge_formatters.py` and `hedge_readiness.py` provide portfolio-aware phases and evidence. `partner_source_adapter.py`, `partner_input_refresh.py` and `partner_fixture_adapter.py` handle source/snapshot inputs. `routes_hedge.py` exposes authenticated operator/API surfaces.

Prior hardening established single-account binding, complete snapshot acceptance, atomic reconciliation, consistent reads/revisions, stable economic identities and conservative delivery recovery. A missing portfolio adapter does not mean general market-setup tips require partner holdings. Conversely, the manual-advisory profile cannot prove personalized hedge coverage.

Timeout/disconnect after possible dispatch is ambiguous. Automatic resend can duplicate consequential advice. Inspect durable claim/transport evidence and manual-resolution requirements instead of deleting ledger rows or forcing status to queued.

## 9. Research and the improvements made in this work

### Earlier baseline versus present Dev

At takeover of the research pipeline (`de696f9`), a claimed pipeline existed, but code review exposed incomplete causal inputs, weak archive/identity boundaries and missing end-to-end alignment with the deployed strategy. Earlier hedge/delivery corrections were already substantial work by previous implementations; do not attribute all existing features to this increment.

| Earlier gap | Improvement now present | Practical benefit | Remaining limit |
|---|---|---|---|
| Weak complete-policy reproduction | `partner_qualification.py` composes actual evaluator, candidate and profile checks with `FROZEN_COMPLETED_BAR_CUTOFF_V1` clocks | Research asks the same entry question at an explicit frozen cutoff and later genuine construction time | Production session evidence and reviewed qualification remain absent |
| Missing exact public input | `partner_research_capture.py` saves fetched OHLCV and actual receipt | Reproduce inputs without inventing past availability | Latest inspected Production archive had none |
| Missing candidate input archive | Passive full map/chain/profile capture now includes requested/received tokens and conditional-protection inputs | Retain why particular contracts were considered and expose missing response contracts | Production load and retention behavior still require live-session observation |
| Threshold-only or spread-P&L exits | Full-policy connector and shared public thesis | Replay tracks the published invalidation/target | Public collection gaps are not reconstructed |
| Between-book breach lost | Independent public event stream with sticky breach | No optimistic exit omission after recovery | Sparse input still cannot prove uninterrupted coverage |
| Original price reused at delayed entry | Actual-book capital/risk and round-trip cost reserve | Reject fills that violate profile after price changes | Cost model and contemporary quality calibration remain |
| Timestamp equality requirement | Explicit tick/cutoff/request/receipt/construction clocks plus latest proven prior books | Later acquisition remains causal without changing provider timestamps or bar eligibility | Old v1 captures retain weaker legacy timing evidence |
| Mutable or mismapped evidence | Raw/master fingerprints, token/terms validation, immutable reports | Detect altered inputs and accidental result replacement | Hashes are integrity, not independent source authenticity |
| Ad hoc scripts needed | `research_cli replay-full-policy` | Repeatable offline diagnostic | It does not register qualifications |

### Module chain

`research_archive.py` owns preservation, writer admission/lease and storage limits. `research_quote_collector.py` collects quote evidence; `research_leg_subscriptions.py` pins needed contracts. `partner_collection_attempts.py` journals each scheduled NIFTY/SENSEX attempt independently and derives `NEVER_ATTEMPTED`, `ATTEMPTED_UNAVAILABLE`, `PARTIAL`, `STALE` or `COMPLETE` session state. `partner_decision_clock.py` defines the pure causal clock contract. `research_study.py` provides modelled studies. `partner_research_capture.py` retains public, directional and conditional-protection inputs and loads public lifecycle evidence.

The deployed advisory timing policy is `FROZEN_COMPLETED_BAR_CUTOFF_V1`. Tick start freezes completed-bar eligibility. Public and option-chain requests and receipts keep their actual clocks and source IDs; candidate construction/validation uses the genuine post-acquisition time. Crossing the session date or the exact 14:45 IST entry deadline suppresses the idea instead of backdating it. A five-minute boundary crossed during acquisition does not silently admit a bar that was outside the frozen request. The next scheduled tick is a new run and cutoff. Public and candidate v2 captures share the same run/account/index identity, while old v1 captures remain immutable and load as legacy evidence.

Archive persistence is still lower priority than public management and candidate evaluation. A nonblocking writer lease prevents concurrent active writers, and advisory waiting is bounded by `RESEARCH_CAPTURE_WAIT_TIMEOUT_SEC` (default two seconds). Since a Python worker thread cannot be killed safely, timeout is recorded as outcome-unknown and its eventual completion is consumed/logged; it is never automatically retried as a certain failure.

`intraday_spread_archive_adapter.py` checks master/packet evidence and builds paired books, retaining partial batches. `intraday_spread_signal_artifact.py` is a distinct signal-artifact path; its simple evaluator must not be passed off as the complete policy. `intraday_spread_replay.py` prices a bounded one-lot spread. `intraday_spread_chronological.py` chooses causal entry/exit sequences, supports manual delay, public events and cost stresses.

`partner_full_policy_replay.py` binds the actual selected candidate to archived books, profile limits and public lifecycle events. The archive adapter rejects distinct valid packets for the same leg and receipt instead of selecting by input order; exact byte-identical retries are deduplicated. Conflicts remain explicit report evidence and can invalidate the decision book. Each accepted replay retains a fingerprinted baseline plus declared fee/slippage stresses computed from identical chronological observations; a thesis already crossed at decision remains a reviewable no-fill instead of disappearing. `intraday_spread_holdout.heldout_case_from_full_policy_report` verifies and retains the complete deployed-policy report, manifest, stress artifact and source identities before admission. Aggregation orders realised economics by timezone-aware close clocks and calculates sequential drawdown. `partner_qualification_review.py` requires an immutable criteria manifest frozen before holdout, evaluates its exact stress point and baseline/stressed drawdown limits, and rejects missing, duplicate, malformed or state-changing evidence. Legacy reports remain readable but blocked. This integration is not proof of a passing strategy, calibrated real costs or adequate real evidence.

### Important replay semantics

The tested source/execution-boundary slice adds v3 public captures with the exact futures symbol/token, exchange, expiry, lot/tick, dated raw-master digest, full eligible expiry list and next roll contract. Full-policy replay independently proves these identities and the front-contract selection against the retained master. Legacy v1/v2 captures remain readable but unscoped. Caller-supplied public dictionaries remain diagnostic and cannot establish verified held-out evidence. Finalized quote segments must match their retained segment manifest, not merely individual packet self-hashes.

Actual delayed-entry books reapply deployed spread, OI, volume and full-lot depth gates, public-observation age, current quantity, profile capital/risk and positive cost-inclusive expiry reward. Entry and management cutoffs use exact dated IST instants; same-day option expiry is excluded. Invalidation at the delayed fill cancels entry in either public-event representation. Delayed public-thesis exits require a genuine timely later book; recovery does not cancel the latched breach. Missing, partial or late books remain unresolved. Slippage is charged on gross executed leg notional and cannot become negative on a distressed net-debit close. Expiry reward/risk is a structural research bound, not a promised intraday target; asymmetric actual fills and exchange-specific settlement models remain outside this full-lot replay.

- A decision event can refer to a previously received complete book. Its constituent quote timestamps remain unchanged. Stale books or intervening partial observations are rejected.
- A public breach before delayed entry cancels it; after entry it remains pending through later price recovery.
- Exit delay starts at public event receipt, not the next option book. Missing executable exits remain UNRESOLVED.
- Capital and risk checks use execution debit plus declared costs, not original card prices.
- Reports retain insufficient evidence, no setup/no fill and unresolved outcomes. Excluding these creates selection bias.
- `can_qualify`, `can_deliver`, `can_place_orders` remain false in this connector.
- A CLI exit code 0 means diagnostic execution succeeded, including an insufficient-evidence result.

The exact command and policy format are in [replay progress](2026-09-12-full-policy-replay-progress.md). Every experiment needs its own immutable destination. Never reuse a report filename to hide changed assumptions.

## 10. Proactive research and optional AI

`proactive_intelligence.py` maintains activity stages, watchlists, synthetic capital/positions and outcome evidence by account/mode/run. Watchlist lifecycle includes watching, armed, triggered, selected/deferred/rejected, expiry and invalidation. Persisted assumptions prevent the same research run being reused with different economics.

`proactive_market_data.py`/`market_data_sources.py` address provider observations; `proactive_execution_research.py`, `proactive_exit_research.py` and `proactive_portfolio_research.py` compare choices. `proactive_diagnostics.py` and `operational_coverage.py` explain activity gaps. Demo modules exercise synthetic workflows. These components are useful foundations, not automatically broker-consuming strategy deployments.

Optional AI is represented by `optional_ai_status.py`, agent typed `advisory.py`, and `async_reviews.py`. A disabled or unavailable model should leave deterministic signal/risk/delivery functioning. Review timeout, budget, queue saturation, stale results and process restart before extending model use. The user's preference is assistance without absolute dependency.

## 11. Dashboard and API navigation

The gateway mounts routing/authentication in `server/app.js`. Engine routes are split among `routes_ops.py`, `routes_hedge.py`, `routes_portfolio.py`, `routes_promotion_readiness.py`, experiment routes and `main.py`. Use the atlas to find exact local handlers; a route's local path is not necessarily its externally mounted URL.

`pages/Dashboard.jsx` composes operational and performance views. `pages/ResearchCenter.jsx` and `BacktestLab.jsx` show research; `Positions.jsx` shows positions. Hooks include partner setup/cards/backlog and advisory collection readiness, reconciliation, scheduler timing, operational coverage, optional AI, proactive activity and session diagnostics. The advisory evidence card shows per-index expected/attempted/missing/incomplete counts and never turns an unavailable response into zero. Utility modules normalize display contracts.

Blank/zero cards can mean no configured account, no source observation, no evidence for the selected mode/run/window, feature disabled, API failure, or genuinely zero events. They are not interchangeable. Each UI surface should show source, scope, observed timestamp and missing-input reason. Reconciliation warnings must remain visible until explained.

## 12. Scheduler, lifecycle and operations

`scheduler_setup.py` registers trading scans, forced exits, partner entry/lifecycle jobs, research collection, input refresh and hedge recovery. `scheduler_telemetry.py` measures job runs. `ops_metrics.py`, `ops_watchdogs.py`, `memory_metrics.py`, `operator_status.py`, `operator_alert.py` and acceptance watchdogs support operations.

Startup catch-up registration resolves a running event loop before constructing `_run_penny_edge_scan_safe`. Synchronous registration/tests therefore defer the catch-up without leaking an unawaited coroutine; the ordinary async application startup path still schedules it.

Measure duration tails, queue delay, provider latency and lock contention separately. An 8-second average does not exceed a 60-second interval; a 115-second tail can overlap it. Prioritize exits and active-advice updates before optional research. Avoid solving lag merely by unbounded parallelism or deleting observations.

`release_identity.py`, gateway `release-identity.js`, Docker build stamps and `scripts/verify_deployment.py` tie a deployment to an actual source/image identity. A newly merged branch does not imply a rebuilt container. The verifier is a deployment identity check, not a profit verifier.

## 13. Last observed Production evidence, not a current health promise

On September 12 read-only inspection found application containers stopped; nginx was restarting. No application service was started. A disposable network-disabled helper mounted the existing data volume read-only. It found four master manifests, September 10/11 quote journals and zero public-input captures under `/data/research`.

Earlier September 11 assessment inspected 61,335 packets and found insufficient strategy evidence for both indices. Packet count is not trade sample size. That report also identified selected-leg retention gaps. Read [the original assessment](research-assessment-2026-09-11/qualification-readiness-report.md) and [the later inventory](2026-09-12-production-evidence-and-cas-findings.md). Reinspect state before acting; these observations expire.

## 14. Release and test discipline

Use the repository Python environment for tests. Avoid importing engine application modules just to generate docs: imports may initialize runtime resources. The atlas generator uses AST/text only.

For changed research/orchestration code, focused tests plus the combined research/orchestrator suite are required. Full release acceptance additionally includes gateway tests under a compatible Node/native SQLite runtime, dashboard tests/build, agent checks as applicable, scheduler/API contracts, migration review and deployment verification.

The historical Node 24 ABI/better-sqlite3 issue is an environment limitation, not permission to claim gateway green. Use the repository-compatible container/runtime rather than changing production dependencies to suit a test host. No broker order or partner message is required to run offline tests.

See HANDOVER_CHECKLIST.md for wrap-up validation and limits. The final handover commit closes this documentation task; it does not declare strategies qualified or promise tomorrow's tips.

## 15. Source navigation and maintenance

The atlas indexes all top-level engine/agent Python modules, declared symbols/line numbers, engine dependencies, related tests and declared tables, plus gateway/dashboard source dependencies and local routes. It is generated navigation, not a substitute for semantic review.

After every implementation commit, update affected sections here, regenerate the atlas, reconcile the active plan, and record checks/deployment state. Prefer doing those updates in the implementation commit; verify immediately afterwards. The mandatory ritual is specified in AGENTS.md and NEXT_AGENT_PLAN.md.
