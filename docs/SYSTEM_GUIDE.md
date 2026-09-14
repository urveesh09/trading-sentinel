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

Release safety now has an optional offline `scripts/verify_data_backup.py` source inventory/tar verifier and [consistent backup/rollback runbook](consistent-data-backup-runbook.md). It checks exact file hashes, bounded safe extraction and header-identified SQLite integrity with WAL recovery in scratch. Its receipt deliberately says consistency is unproven: independent live quiescence and actual source/mount coverage are operator responsibilities. Code rollback must preserve current post-backup books/evidence and prove previous-code compatibility on copies; it must not restore older cash/trade history over the live volume. Dev fixtures, not a Production backup, validate this tool.

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

### CAS and market-session correctness (workstream J)

`market_calendar.py` is the single source of truth for session clocks. Beyond the historical `is_market_open` / `is_trading_day_sync` it now exposes a bounded session-phase classifier (`classify_session_phase(observation_at, *, symbol, is_derivative, cas_eligible)`) and a CAS-eligibility gate (`is_cas_eligible(symbol)`). The classifier returns exactly one of ten documented phases — `CLOSED`, `PRE_MARKET`, `CONTINUOUS_TRADING`, `CAS_REFERENCE_PRICE_WINDOW`, `CAS_ORDER_ENTRY`, `CAS_LIMIT_ENTRY_ONLY`, `CAS_MATCHING`, `CAS_POST`, `DERIVATIVES_CAS_ALIGNED`, `UNKNOWN` — for every (timestamp, symbol, is_derivative, cas_eligible) input. It never raises and never consults `NSE_HOLIDAYS_STATIC` (a deliberate separation of clock-only phase from holiday awareness).

The CAS-aware phases are gated on `is_cas_eligible`, which consults the operator-supplied list `settings.CAS_PHASE1_FNO_UNDERLYINGS` (env var, plain CSV string) at the moment it is asked. The list is operator-curated per NSE/CMTR/72394 — Dev ships an empty string so the classifier stays in non-CAS mode until the operator opts in. Config typing is deliberately a `str` (CSV at the wire layer) so pydantic-settings v2.2.1 does not JSON-decode the env var. `is_cas_eligible` does a lazy `from config import settings` so `market_calendar` stays importable in isolation, defends against import failures by returning False (the bounded default), and memoises the parsed set with `@functools.lru_cache(maxsize=1)`.

J.3.1 added a `cas_eligible: bool | None = None` keyword to `classify_session_phase` so callers can resolve eligibility upstream and bypass the settings lookup. Default `None` preserves the pre-J.3.1 byte-identity; explicit True/False forces the branch. This is the boundary that J.3's `--eligibility-list` and future staging captures depend on.

The G forward-compat seam `proactive_intelligence.py::stamp_session_phase` is now wired (J.4) to the real classifier. Contract: `observation_at=None` still returns `"UNKNOWN"` (preserves the `_ensure_shadow_run` manifest site); a real datetime returns the bounded phase from `classify_session_phase`. Optional kwargs `symbol` / `is_derivative` / `cas_eligible` mirror the classifier. Lazy import of `market_calendar` inside the function keeps `proactive_intelligence` policy-agnostic at module-import time.

Operator evidence collection during a real CAS window uses `python-engine/tools/j2_cas_probe.py` (staging-only CLI; `--dry-run` for Dev sanity checks). The probe captures the classifier verdict + eligibility verdict + Kite quote (cash fields + circuit limits + broker-side extras), with `--now` or `--observation-at`, `--output` JSON path, `--eligibility-list`, `--require-eligible`, `--validate`, and `--schema-print`. Inline JSON Schema (`SCHEMA_VERSION: 2`) pins the document shape. Strict ISO 8601 parser refuses naive timestamps. It is NOT exercised by pytest — see `docs/2026-09-13-j2-broker-behaviour-probe.md` for the operator procedure and six-point review checklist.

J.3 (this slice's J.3.1 + J.3.0) sharpens the probe (`SCHEMA_VERSION: 2`, inline JSON Schema, `--schema-print`, `--eligibility-list`, `--require-eligible`, `--validate`, strict ISO 8601) and adds the deterministic review tool `python-engine/tools/j2_capture_review.py`. The review tool runs the six-point checklist + an opt-in OHLC-continuity cross-window check against captured JSON and exits 0 only when every check passes. The operator protocol (`docs/2026-09-13-j3-capture-protocol.md`) prescribes a six-window capture grid (15:10 / 15:17 / 15:22 / 15:27 / 15:32 / 15:42 IST); the receipts land in `docs/j2_captures/YYYY-MM-DD/`. Until those receipts arrive, the broker-behaviour question remains open.

J.5 ends the Python↔Node holiday drift. The Python `NSE_HOLIDAYS_STATIC` (re-verified against NSE Equity 2026 trading-holiday list) is the canonical source of truth across the whole system. `python-engine/holiday_drift.py` is a pure drift detector that parses the Node source as text and emits `{verdict, drift_count, python_only, node_only, in_both}`. The CLI `python-engine/tools/holiday_drift_check.py` wraps it for CI / operators: exit 0 on `ALIGNED`, exit 1 on `DRIFT`. The Node gateway fetches `GET /holidays` from the engine at boot (5s timeout) and mutates `NSE_HOLIDAYS` in place on success; the pre-J.5 18-date list becomes `NSE_HOLIDAYS_FALLBACK` (documented degraded-mode for engine-unreachable environments), overridable via `MARKET_HOURS_HOLIDAYS_JSON`. J.5 ships 18 new drift tests + 6 new Node holiday tests; the python-engine suite is at 3245/4/0 with the previously-failing surface test resolved by the documented golden-refresh.

J.6 lands the Node session-phase mirror. Before J.6, every Node caller — `routes/health.js`, `services/executor.js`, `index.js` (the telegram callback handler) — could only see a binary `isMarketOpen()`; CAS sub-windows were structurally invisible on the Node side even though the J.1 Python classifier knew about them. J.6 ships `sessionPhase(observation_at, opts)` and `currentSessionPhase()` as Node-side mirrors of `python-engine/market_calendar.classify_session_phase`. The contract is bit-perfect: 10 documented phases (CLOSED, PRE_MARKET, CONTINUOUS_TRADING, CAS_REFERENCE_PRICE_WINDOW, CAS_ORDER_ENTRY, CAS_LIMIT_ENTRY_ONLY, CAS_MATCHING, DERIVATIVES_CAS_ALIGNED, CAS_POST, UNKNOWN), identical boundary semantics, IST-clock-aware via `Intl.DateTimeFormat({Asia/Kolkata})`. `sessionPhase()` accepts Date / millisecond-number / ISO-8601-string inputs; naive timestamps default to UTC (matching Python); invalid inputs return `UNKNOWN` without raising. The Phase-1 CAS eligibility probe is mirrored via `opts.cas_eligible` (caller-supplied override) with fallback to the J.2.1 list when absent. Wiring: `routes/health.js` exposes `session_phase: currentSessionPhase()` in `/` GET; `services/executor.js` logs `execution_phase_at_reject` whenever the `isMarketOpen()` guard fires; `index.js` telegram callback now reports "Market in {phase}. Cannot execute now." The invariant is pinned by a 2,355-vector golden regenerated by `python-engine/tests/fixtures/regenerate_session_phase_golden.py` from the live Python classifier and asserted bit-perfect by `node-gateway/server/tests/unit/sessionPhase.test.js`. The regenerator uses two sweeps: a wide minute-granularity sweep (8 days × 24 hours × 4 minutes × 3 option-combos = 2304 vectors) plus a focused second-granularity boundary pass (17 instants × 3 option-combos = 51 vectors) that hits `CAS_LIMIT_ENTRY_ONLY` (15:29:30 - 15:30 IST, ~30-second-wide sub-window) and `CAS_POST` (derivatives 15:40 - 16:00 IST) — both invisible to a minute-granularity sweep. Net: Node full suite 360/4/0 (was 317/4/0; +43 new tests in `sessionPhase.test.js`); python-engine full suite 3247/4/2 pre-existing failures (both unrelated to J.6 — verified by zero imports of any J.6 file). J.6 ships observability only; CAS-aware execution gating is the J.7 plan slice.

The historical 15:30 → 15:40 expiry mismatch for derivatives (`fno_chain.EXPIRY_CUTOFF_HOUR/_MIN` and `hedge_strategies._EXPIRY_CUTOFF`) is documented but explicitly NOT fixed in J.1/J.2/J.3/J.4/J.5 — plan §14 forbids changing strategy deadlines without operator sign-off (J.7).

## 6. Broker execution and accounting

The D release-baseline correction restores legacy test fixtures to the startup-migrated ledger contract without changing runtime accounting. A regression verifies repeated migration preserves old rows and accepts new close provenance (`origin_ref`). Windows source guards now read UTF-8 with closed handles; scheduler wrappers document actual delegated calendar gates and deliberate off-session cleanup/reconciliation exceptions. The existing partner-bot default remains `True`; explicitly disabling it still prevents network-client construction, and credentials/qualification/final dispatch remain separate gates. Full Dev Python acceptance now passes 2,545 tests (three skips, 23 existing deprecations); this is not deployment or strategy qualification. See `2026-09-13-release-baseline-plan.md` for the precise release status and warnings.

Gateway files `services/kite.js`, `executor.js`, `risk-geometry.js`, `halt-switch.js` and `routes/orders.js` deserve focused review before any execution change. `token-store.js`, `token-restore.js`, `routes/token.js`, engine `token_lifecycle.py` and `kite_client.py` handle the authentication/provider bridge. Do not log secrets or infer an authenticated broker session from a process heartbeat.

Token restoration now releases each abort timer in `finally`, including fetch failures, and keeps response-body parsing under the same three-second abort scope. Retries and internal authentication remain unchanged. Filesystem-only dead-letter tests stub Telegram rather than start fake-token polling. The current native gateway suite passes 324 tests (four skips) and exits naturally without forceExit or detected open handles. The Windows instrument-test socket warning was traced to a manual asyncio.run between pytest-managed async tests; that test now uses pytest's lifecycle. Original failing four-file warning-fatal acceptance passes 32 tests; broader resource-warning-fatal research acceptance passes 181 tests. This does not prove all operational resources are leak-free in Production.

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

The proactive-ledger stack (`proactive_intelligence.py` plus five sibling modules, total 3,007 LoC; tests under `tests/test_proactive_*.py` total 891 LoC) is the substrate for plan §11's six hypotheses; it is offline-safe by docstring and every report payload returns `can_place_orders=False, authorization_effect=NONE`. An independent audit and the promotion-bridge contract that any future live promotion must obey are at `docs/2026-09-13-workflow-g-state-of-codebase-audit.md` and `docs/2026-09-13-workflow-g-promotion-bridge.md`.

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

Independent F source review corrected materially inferred accounting schemas and unsupported historic closure claims in `2026-09-13-workflow-f-state-of-codebase-audit.md`: positions has no declared PK/id; outcomes has autoincrement id plus UNIQUE(ticker,closed_at); broker entries has the three-column account/statement/entry PK. Ledger has multiple writers and position/outbox lifecycle updates exist. A1–A5 warning identities/closures remain UNKNOWN without original records. Equity snapshot effective date is again null because verification date does not establish tariff effectiveness; numeric costs/version/as-of/options and old snapshots remain unchanged. Fresh isolated schema and funding-not-profit fixtures support these contracts, not actual Production reconciliation or loss reconstruction.

`proactive_intelligence.py` maintains activity stages, watchlists, synthetic capital/positions and outcome evidence by account/mode/run. Watchlist lifecycle includes watching, armed, triggered, selected/deferred/rejected, expiry and invalidation. Persisted assumptions prevent the same research run being reused with different economics.

Independent F/G review identified mislabeled trailing-exit dispatch and incomplete promotion approval validation despite passing focused tests. The first correction makes `promotion_bridge.py` transitions atomic and directed, reads the latest committed append state, and prevents a terminal refusal/approval from being amended. Signature timestamps cannot reorder that state. This preserves both tables and all rows. Its records remain non-authoritative (`can_place_orders=False`); approval budget/evidence/expiry validation and faithful entry/exit composition are still required, so neither a stored approval nor a green focused suite establishes live permission. See `2026-09-13-fg-independent-correction-plan.md`.

The trailing-composition follow-up now honors NEXT at-open, bounded pullback limit and completed-bar-confirmation entry behavior before applying the selected trailing exit. Intrabar limit fills don't ratchet from a possibly pre-fill entry-bar high; confirmation bars cannot fill or ratchet the position. Gap-invalid entries remain no-fill and nonfinite cost assumptions fail closed. Root's ten-file proactive/G suite passes 121 tests with warnings fatal; Terra independently reviewed causality and found no blocker. Existing primary comparison runs retain their implementation fingerprint and reject incompatible reuse. RANGE_REVERSION remains an acknowledged confirmation alias, not a faithful mean-reversion result; the separate exit-policy report cache still needs full proposal-clock/implementation identity, and bridge approval validation remains unfinished. Old reports are retained, not reinterpreted as corrected results.

The exit-cache follow-up closes that proposal-clock/implementation identity gap: new `matched-exit-evidence-v3` manifests bind effective full proposal identities/timings, snapshotted bars, costs and both evaluator source hashes. A companion `proactive_exit_research_manifests` table retains canonical JSON without changing the original four-column results table. Legacy reports remain readable but cannot be reused as current-version runs; incompatible reuse fails rather than overwriting history. Atomic final recheck handles concurrent identical/conflicting requests, and duplicate opportunity IDs cannot inflate the sample. Root's current proactive/G suite passes 137 tests with warnings fatal. These are input/implementation integrity checks, not genuine held-out provenance, qualification or live authorization; approval validation/range semantics/F evidence remain open.

Approval-budget validation now requires the relevant retained amount, drawdown cap and integer expiry, rejecting booleans/nonfinite values before SQLite coercion. Approval transitions use budgets predeclared on the original unsigned record and a half-open validity window anchored to its original clock; signing later cannot extend expiry. Reads preserve recorded history and expose budget validity/expiry/version status, while `approval_usable=False` explicitly blocks missing frozen held-out/account/F/D evidence. This is budget validation, not full evidence approval or order authority. The twelve-file F/G suite passes 180 tests with warnings fatal; the previous whole-engine receipt predates this and the cache change.

`proactive_market_data.py`/`market_data_sources.py` address provider observations; `proactive_execution_research.py`, `proactive_exit_research.py` and `proactive_portfolio_research.py` compare choices. `proactive_diagnostics.py` and `operational_coverage.py` explain activity gaps. Demo modules exercise synthetic workflows. These components are useful foundations, not automatically broker-consuming strategy deployments.

Optional AI is represented by `optional_ai_status.py`, agent typed `advisory.py`, and `async_reviews.py`. A disabled or unavailable model should leave deterministic signal/risk/delivery functioning. Review timeout, budget, queue saturation, stale results and process restart before extending model use. The user's preference is assistance without absolute dependency.

The Dev optional-annotation queue now deep-snapshots nested signal inputs and bounds READY/CACHED validity by the original task deadline and cache TTL. A shorter cached-request deadline tightens validity; a later one cannot extend it. Completion exactly at expiry is discarded, and status returns EXPIRED without a review once validity elapses. This fixes a reproduced stale-cache defect without changing reviewer signatures, budgets or deterministic authority. The full isolated agent suite passes 98 tests with warnings fatal and networking disabled. Model/prompt/source provenance, sourced-news timestamps and annotation usefulness still require I acceptance; this lifecycle slice is not that proof.

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
