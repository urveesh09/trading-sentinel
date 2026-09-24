# Trading Sentinel — system guide and engineering handover

## September 24 P1 momentum-paper admission forensics (Dev)

Accepted momentum signals now receive durable, bounded paper-admission
evidence. `momentum_paper_admission_outcomes` retains only an opaque
deterministic signal digest, ticker, enumerated outcome and timestamp—never a
raw signal payload. The result is written in the same transaction as an
opening position: `opened`, `already_held`, or `zero_shares` is therefore not
reported before commit. A rolled-back position mutation is separately retained
as `transaction_failure` when SQLite is available; an unavailable database is
logged, never fabricated as durable evidence.

`main.py` now records repeat accepted signals at the alert-deduplication
boundary as `upstream_deduplicated`, rather than falsely saying the paper book
rejected them. A deliberately disabled paper book similarly records `disabled`.
Outcomes are idempotent, retention-bounded by
`MOMENTUM_PAPER_ADMISSION_RETENTION` (20,000), and reopening an already closed
paper position creates a separate immutable admission attempt. This remains a
paper-only bookkeeping path with no order capability or broker authority.

Focused paper/regime/shadow integration checks cover TATATECH-like repeats,
held and zero-share outcomes, disabled state, rollback receipt, retention and
the real upstream boundary (**159 passed**, with one existing Starlette
deprecation). Dev tests establish explainability, not a trading
edge or live/paper promotion. Production was not edited or deployed.

## September 24 P1 F&O tick-tail containment and exit-safe telemetry (Dev)

Read-only Production evidence across the retained 23–24 September window found
27 `fno_tick_complete` runs at or above the 90-second cadence (12 on the 23rd,
15 on the 24th). Their repeated tail was the defined-risk stage; all had zero
DR opens and exits. This identifies speculative paper DR entry preparation,
not ordinary single-leg exit management, as the demonstrated avoidable work.

`fno_orchestrator.py` now gives only the cancellable quote/history reads used
to prepare a *new* paper defined-risk structure one shared 20-second budget.
`asyncio.wait_for` cancels and joins a late input read. It never wraps existing
DR lifecycle management, hard-flat handling, broker-facing single-leg exits,
or a database admission write. Successful DR reads are still reused by the
directional path exactly as before. The tick now separately records
`defined_risk_snapshot`, `defined_risk_management`,
`defined_risk_entry_inputs`, and `defined_risk_entry_admission`; the scheduler
also logs an explicit `dr_entry_skip_reason`.

The stalled-entry test proves prompt cancellation/join, a named timeout, no
order and no detached request; existing F&O/DR/scheduler tests prove the
ordinary path remains intact. This is Dev-only containment, not a claim that
active-exit latency is solved: after reviewed promotion, collect comparable
session telemetry and inspect those new stage fields before any cadence change.
Production was inspected read-only; it was not edited, restarted or deployed.

## September 24 P1 research quote deadlines and coverage evidence (Dev)

The research scheduler now bounds every NIFTY/SENSEX provider await to the
remaining 48-second collection cap, rather than checking only between
underlyings. `asyncio.wait_for` cancels and joins the actual shared Kite
coroutine; it creates no replacement client or hidden late provider task. A
deadline is retained as evidence: current-index `provider_deadline_exceeded`,
exact active-leg tokens already known as unobserved, and later indices as
explicit skipped/unobserved coverage. Nothing is replaced with a stale quote.

Every scheduler result and persisted collection run carries `runtime_capped`,
`elapsed_sec`, `runtime_cap_sec`, `partial_collected` and `partial_count` for
normal, deadline and error paths. Per-index `collection_state` distinguishes
completed, empty, batch error, provider deadline, storage stop and skipped
deadline outcomes. The 60-second cadence and 48-second cap are unchanged.
The first underlying rotates deterministically by UTC scheduler slot and the
chosen order is retained, preventing repeated capped slots from permanently
favoring one index after a restart.
The scheduler regression proves cancellation of a stalled first operation and
complete NIFTY/SENSEX gap accounting; the normal path proves durable telemetry.
Focused coverage passed 54 tests, all research tests passed 62, the combined
collector/scheduler/Kite-client surface passed 173 with one skip and one
pre-existing Starlette lifespan deprecation, and compilation passed. This is
Dev-only evidence: three real logged-in sessions must still
show fairness/latency coverage before operational claims. See the
[P1 receipt](2026-09-24-three-day-production-audit-plan.md).

## September 24 P0 decision-forensics retention verification (Dev)

Read-only Production evidence showed that `python-engine` already uses
Docker `json-file` logging at `20m × 10` (200 MiB) and retained one 18.13 MiB
file across 35.897 hours, an observed 0.50 MiB/hour. Gateway used the same
configuration and retained 2.07 MiB over that interval. There was no rotation
to correct and the 104.42 GiB C: free-space observation did not justify an
unmeasured retention increase. Dev therefore preserves the existing Compose
values and adds `scripts/verify_compose_logging.py`: it renders Compose JSON,
checks only `python-engine`'s `json-file` driver, `max-size`, `max-file` and
the minimum 200 MiB ceiling, and never prints rendered environment values.
The focused unit suite passed 8 tests; direct rendered verification passed.

This is a configuration-regression guard, not proof of three-session
forensics retention: post-promotion acceptance is a read-only inspect and
opening-to-close retrieval for three logged-in sessions. Docker logging
options apply only after container recreation; no recreation was needed or
performed because no Compose value changed. Production was inspected read-only
and no service/data, order or message changed. Details and rollback criteria
are in [the P0 plan](2026-09-24-three-day-production-audit-plan.md).

## September 24 gateway test-lifecycle correction and Dev acceptance (Dev only)

`node-gateway/server/utils/market-hours.js` still refreshes the canonical
holiday calendar from the Python engine during normal module initialisation.
Only when the Jest worker marker and the test setup's explicit
`MARKET_HOURS_TEST_DISABLE_ENGINE_FETCH=1` flag are both present does it retain
the fail-closed fallback without beginning that background request. This avoids
post-test asynchronous logs while making it impossible for an accidental
production flag alone to disable the refresh. `tests/setup.js` preserves the
development-safe `.env.test` fixture and sets only the test-specific switch;
`market-hours.test.js` verifies the exact initialization result.

Dev receipt: Node 20 gateway 461 passed/4 skipped with exit 0; scripts 226
passed; agent 357 passed; dashboard 46 passed and builds. The full engine
runner remains inconclusive because its aiosqlite worker did not exit, so this
is not stated as a whole-engine pass. The code atlas was regenerated (211
Python modules). No Production file/service/data, Telegram delivery or broker
order changed. See
[the release-acceptance receipt](2026-09-24-dev-release-acceptance-plan.md).

The remaining six high-level gates are classified deliberately: no further
product source change is currently unblocked. The Python runner's retained
aiosqlite worker is test-runtime hygiene, to be fixed only after a minimal
owned-leak reproducer; the other gates depend on promotion, real observations,
broker records, held-out evidence and explicit operator approval. Test success
does not replace any of those requirements.

## September 24 real-research authorization package builder (Dev implementation)

`research_cli.py build-qualification-package` assembles the existing
`partner_advisory_authorization_v1` artifact only from bounded, root-confined
full-policy replay reports, a frozen criteria manifest, a reconstructed
held-out aggregate, and an externally created `APPROVED` human-review identity.
It reconstructs every held-out case and the review package before publishing
canonical immutable bytes; source-report policy identity, criteria identity,
scope, review/validity clocks and the 16 MiB authority limit all fail closed.
The output is then locally checked by the same current authority verifier used
at registration and final dispatch.

The command has no database parameter or side effect: it cannot save a profile,
register a qualification, approve evidence, alter configuration, send Telegram
or place an order.  The review identity and validity period must already exist
as separate operator records; `APPROVED` is an input, never inferred from P&L.
Inputs and output are relative to caller-declared roots to prevent traversal,
and a different existing output cannot be overwritten.  See
[the active package slice](2026-09-24-real-research-package-plan.md) for the
exact input layout and remaining real-market prerequisites.

Verification: the package/replay/held-out/review/authority/CLI acceptance group
passed 64 tests with warnings fatal. The wider research/advisory group passed
235 tests with one pre-existing Starlette async-generator-lifespan deprecation;
that legacy warning fails setup when warnings are deliberately made fatal.
The atlas was regenerated to 211 Python modules. Production was not read for
mutation, edited, deployed, or sent any broker/Telegram action.

## September 24 F&O exit recovery (Dev implementation)

An authenticated operator can list pending live single-leg F&O exit intents at
`GET /ops/fno-exit-intents` and reconcile one at
`POST /ops/fno-exit-intents/{position_id}/resolve`. The resolution requires a
named operator, account/order ID, exact intent timestamp and an explicit
confirmation. It reads the current day's broker order book, that order's trades
and net positions. Account, NFO/MIS symbol, SELL side, source tag, order and
trade quantities, terminal status, clocks and residual net quantity must agree.
An unavailable or ambiguous broker response leaves the intent untouched.

A verified terminal zero fill releases the intent with a retained broker
snapshot. A partial fill posts only realized economics to the ledger, scales
the open quantity/risk, preserves cumulative position P&L and permits only a
fresh later exit evaluation. A full fill closes the position and ledger in one
transaction. Each resolution retains bounded broker evidence and its SHA-256,
operator, account, order, and generation. Prior recovered orders are distinct
from unaccounted same-symbol orders. A tick that began before recovery cannot
immediately claim a replacement exit. The no-quote alert no longer suggests a
direct database status edit. Existing ambiguous exits still block automatically.
Daily/weekly/monthly F&O loss switches use each realized ledger event's IST
date, including partial fills; legacy closes without a tagged ledger entry
remain visible through position history.

The operator first reads the authenticated intent list to obtain the exact
`created_at`, then posts a JSON body containing `source: "FNO_LIVE"`,
`expected_created_at`, `account_id`, `order_id`, `operator`, and
`confirm: "RECONCILE_VERIFIED_BROKER_EXIT"`. Both routes require the existing
`X-Internal-Secret` header. A `409` means the evidence is insufficient or
changed; the intent remains for investigation. The stored snapshot is in
`fno_exit_recoveries`, alongside its digest and the linked ledger ID.

Kite's order/trade API is daily; an older unverified intent cannot be cleared
by this endpoint. It needs external statement-level reconciliation and review.
The internal secret authenticates the route; the operator name is an auditable
claim within that trust boundary. No broker order is sent by recovery itself.
Live single-leg activation still needs a supervised broker rehearsal.

## September 23 independent remediation review (Dev only)

The seven incoming audit-fix commits through `674a6fe` required corrections at
real entry, settlement and qualification boundaries. Owner-entry halts now reach
both gateway and direct Kite paths; unknown CAS fails closed. Single-leg F&O exits
retain durable dispatch intents and acknowledged-fill receipts, then atomically
settle position/ledger with source-scoped positive generations and allocated equity.
Ambiguous exits require reconciliation; they cannot automatically resubmit.

New entry advice requires a current `partner_advisory_authorization_v1` package,
recomputed held-out review, exact current code/config/profile, immutable bytes and
explicit dated human approval. Legacy status-only rows and the old bypass setting
cannot authorize delivery. Collection coverage is slot/account scoped; readiness
WARN is not green. Real token/archive freshness is on-demand observational evidence.

Read [the completion and recovery handover](2026-09-21-independent-remediation-review.md)
for contracts, migrations, rollout/rollback and remaining work. Production has not
been changed or re-certified by this Dev completion. Tests prove software behavior,
not strategy profitability or partner qualification.

## September 20 Workflow I.4.D evidence-provenance correction

The opt-in news classifier now renders and classifies one immutable Yahoo +
Google feed snapshot per signal rather than fetching the feeds twice. Each
frozen classification carries the requested ticker, bounded source name/URL,
an aware UTC publication time and a full source-evidence digest. Missing URLs,
missing/naive publication clocks, future-dated items, sources at or beyond the
declared seven-day freshness boundary, and non-HTTP(S)/hostless URLs fail
closed to `UNKNOWN` without a model call. The classification-context digest binds source,
publication time, category, confidence, rationale and prompt version while
deliberately excluding the completion clock.

Optional-review cache keys include that digest only when classification is
enabled, so the disabled-path key remains byte-compatible and changed
classifications cannot retrieve an older opinion. The queue independently
checks context even if a caller reuses an external key. Typed reviews retain
the classification digest/count and immutable `(source digest, URL,
publication clock)` references plus expiry. Sync late completions become
payload-free `REVIEW_UNAVAILABLE`; async unavailable/exception paths retain
their context and deadline. Async READY/CACHED reviews
expose the earlier of request deadline and cache TTL; a shorter repeat request
tightens, and can never extend, that deadline. This is evidence provenance
only: no strategy, threshold, risk, capital, qualification, delivery, broker or
order authority changed. CLI file input parses aware RFC/ISO clocks without
importing the full agent. Focused warning-fatal acceptance is **185 passed**;
the complete isolated network-disabled agent suite is **357 passed**. The
203-module atlas was regenerated. Production remains untouched. See the
[implementation plan](2026-09-20-i4d-classification-provenance-plan.md).
Implementation commit: **`3495ecb`**.

## September 19 Workflow I usefulness-contract correction

Dev now accepts the complete ten-field usefulness snapshot emitted by the
optional-AI worker. The engine strictly validates finite/non-negative latency,
cache-rate bounds and counter consistency, bounded verdicts, and an aware
completion clock while retaining partial legacy envelope compatibility. The
agent's contract-health allow-lists now match its real status producer, and the
hourly check evaluates leakage/usefulness invariants instead of inspecting only
the top-level authority shape. Real-producer boundary tests replace the former
six-field doubles. The dashboard adds p95 latency and last-completion evidence
and displays missing legacy values as unavailable, not observed zero.

This remains opt-in operational evidence under
`OPTIONAL_AI_REPORT_USEFULNESS`; it cannot alter a signal, qualification,
delivery, capital, risk, or order. No schema or default changes. Focused engine
acceptance is **72 passed** with four known framework deprecations; the complete
agent suite is **340 passed** warning-fatal; dashboard acceptance is **46
passed** plus a successful build. Whole-engine acceptance is **4,117 passed,
four skipped and 46 known framework deprecations in 209.34s**. See the
[implementation plan](2026-09-19-workflow-i-usefulness-contract-plan.md).
Production remains untouched.

## September 19 Workflow G.7 range-comparison causality correction

The dedicated `RANGE_REVERSION_V1` research path now evaluates the first
completed bar after its frozen decision cutoff, requires 14 prior bars, and
starts any modeled execution strictly after that decision bar. Later favorable
bars can no longer validate an earlier hypothetical fill. Missing history,
missing decision bars, malformed/duplicate bars, verifier failures and invalid
range geometry return named fail-closed outcomes rather than falling through to
generic completed-bar confirmation.

The predeclared comparison protocol no longer carries the obsolete statement
that range reversion is a confirmation alias or forces every range profile to
`UNCERTAIN`. Range evidence now faces the same completeness, baseline/stress
economics, drawdown and paired uncertainty gates as every other declared
profile. Protocol and evaluator source hashes remain frozen, so existing
protocols cannot be silently reinterpreted and require a new protocol ID under
the corrected implementation. This is offline research only: no qualification,
approval, order, capital or delivery authority. Production remains untouched.
Focused range/comparison acceptance is **81 passed** warning-fatal; the broader
G surface is **222 passed** warning-fatal; whole-engine acceptance is **4,095
passed/four skipped/46 known framework deprecations in 204.44s**.
See the [G.7 plan](2026-09-19-g7-range-comparison-causality-plan.md).

## September 19 Workflow F.10A broker/internal reference verification

Dev now compares each executed `FILLED`/`PARTIAL` broker order in an imported
statement with the retained live order references in `positions` and
`fno_positions`. The report aggregates fills by order, separates cancelled and
rejected evidence, and fails closed on missing schemas, incomplete table
coverage, account-binding gaps, paper/unsupported sources, duplicate
references, missing references and F&O quantity excess. Findings are persisted
idempotently under three additive discrepancy categories and are returned by
the reconciliation CLI and import route.

A unique reference is only `MATCHED_REFERENCE`: internal books still lack
broker `account_id`, statement period bounds are unavailable, and equity
`shares` is a mutable remaining quantity. Accordingly every report keeps
`account_attribution_verified=false`, `broker_reconciled=false`,
`can_place_orders=false`, `can_grow_live_capital=false` and
`authorization_effect=NONE`. This is a diagnostic bridge, not bidirectional
economic reconciliation, capital permission or evidence of profitability.
Focused reconciliation acceptance is **118 passed** with 21 known framework
deprecations; the final whole-engine run is **4,090 passed/four skipped/46
known deprecations in 204.15s**. Production remains untouched. See the
[F.10A plan and receipt](2026-09-19-f10a-broker-internal-reference-plan.md).

## September 19 Workflow C asymmetric source binding

`MODELED_PARTIAL_FILL_V1` now prices each missing leg from the exact verified
asymmetric archive packet that produced the execution-quality diagnostic. The
packet hash, quote clock, bid/ask and quantity flow into the modeled
attribution; the earlier complete decision book is never substituted. Legacy,
missing or malformed source projections fail closed, and held-out ingestion
recomputes the fill and P&L while cross-checking the retained source. Focused
acceptance is **87 passed** with warnings fatal; the broader C group is **259
passed**; the whole engine is **4,070 passed/four skipped/42 known
deprecations**. This remains modeled research evidence, not a broker fill,
qualification, delivery permission, or profitability claim. See the
[source-binding receipt](2026-09-19-workflow-c-asymmetric-source-binding-plan.md).
Production remains untouched.

## September 19 Workflow C partial-fill review correction

The asymmetric partial-fill path now binds its operator-selected CLOSED result
to a dedicated tamper-evident `MODELED_PARTIAL_FILL_V1` replay. Held-out groups
and qualification packages expose full closes separately from modeled partial
closes. The economic correction records mid-plus-2bps entry slippage as a cost,
never profit; missing/invalid top-of-book or naive receipt clocks cannot create
a modeled close. Because this path has no honest full cost-sensitivity artifact,
it remains outside `VERIFIED_FULL_POLICY_REPORTS` and cannot silently satisfy
that qualification gate. Full engine verification is 4,069 passed/four
skipped/42 known deprecations. See the
[C.C2.HOLDOUT receipt](2026-09-19-workflow-c-partial-holdout-plan.md).
Production remains untouched.

## 1. Read this first

September16 momentum/CAS correction: Dev now transfers exclusive live-momentum exit ownership from the intraday monitor to EOD at 15:13 IST and refuses every new square-off submission at or after 15:14:30, before the 15:15 CAS reference-price window. A shared lock prevents the monitor and EOD job from cancelling or selling the same position concurrently. The EOD path checks its deadline before cancelling a protective stop and immediately before submission; if the deadline or another pre-submit failure occurs after cancellation, it attempts to re-arm and durably persist replacement protection and pages the operator. The scheduler uses `max_instances=1`, coalescing and a bounded 60-second misfire window. Final Python receipt:3730 passed/four skipped/42 existing deprecation warnings in214.84s; agent:338 passed. As in the preceding baseline, aiosqlite workers retained the completed pytest processes after the receipt, so the exact test processes were stopped. This changes scheduling/control flow only: no schema, retained position, ledger, broker or configuration migration.

September16 independent post-commit review: the first J.7 resolver hardening was incomplete. The corrected Dev contract HMAC-binds the eligibility decision to the requested symbol, authoritative source label and configuration fingerprint; malformed responses fail closed before execution. Holiday refresh rejects an entire malformed/empty/out-of-validity payload rather than silently filtering it, and both fallback and engine-loaded calendars expire at declared `valid_through`. The audit also removed intermittent operational-coverage SQLite lock races and made J.10 SUMMARY verification deterministic without altering its public JSON shape. Final Dev Python receipt: 3725 passed/four skipped/42 existing deprecation warnings; native runtime-matching Node: 424 passed/four skipped; dashboard: 43 passed and build; agent: 338 passed. The completed Python run retained aiosqlite worker threads after printing the receipt, so clean interpreter teardown remains an environment/runtime follow-up. This is Dev source/test evidence only; Production remains at merge `967e07a`, and real CAS staging captures remain absent. See [independent correction plan](2026-09-14-independent-correction-plan.md).

September14 independent correction: the offline predeclared G/C comparison now freezes full cost metadata and code identity before holdout, supports identical late retries without backdating new protocols, preserves every session/state, reports actual turnover and opportunity-weighted session-cluster uncertainty, and applies baseline/stress gates to every declared profile. Missing declared coverage blocks support even when a lower minimum is met. Explicit CLI paths have no live DB default or backdating switch. Reports retain the complete frozen manifest and remain diagnostic research only: no winner selection, qualification, approval or order authority. See [protocol plan](2026-09-13-predeclared-strategy-comparison-plan.md). G.7 supersedes the historical RANGE alias limitation with a causal dedicated dispatcher; independent trials still are not shared-book capacity proof.

The [external-work audit](2026-09-14-external-work-independent-audit.md) supersedes F-series/J closure claims: actual F&O quantities, account evidence, capital defaults/failure handling, live CAS eligibility, square-off windows and holiday fallback need corrections. Passing synthetic tests are not acceptance of these contracts. Dev only; no push/deployment or operational data mutation.

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

J.5 ends the Python↔Node holiday drift. The Python `NSE_HOLIDAYS_STATIC` (re-verified against NSE Equity 2026 trading-holiday list) is the canonical source of truth across the whole system. `python-engine/holiday_drift.py` is a pure drift detector that parses the Node source as text and emits `{verdict, drift_count, python_only, node_only, in_both}`. The CLI `python-engine/tools/holiday_drift_check.py` wraps it for CI / operators: exit 0 on `ALIGNED`, exit 1 on `DRIFT`. The Node gateway fetches `GET /holidays` from the engine at boot (5s timeout) and mutates `NSE_HOLIDAYS` in place on success. The Node `NSE_HOLIDAYS_FALLBACK` is now the **exact ISO projection** of `market_calendar.NSE_HOLIDAYS_STATIC` (20 dates) — the pre-J.5 18-date hand-maintained list has been retired by the independent correction plan; the fallback is now safe to use before the asynchronous engine refresh completes, overridable via `MARKET_HOURS_HOLIDAYS_JSON`. The static set has a documented validity period: `NSE_HOLIDAYS_VALID_THROUGH = '2026-12-31'`; once the embedded fallback passes this date, `isHolidayCalendarUsable()` returns `false` and `isMarketOpen()` / `isPreMarket()` fail closed rather than assuming a future weekday is open. `replaceHolidays` records the source validity date so a successful engine refresh can extend the live set's validity. `routes_holidays.py` exposes `valid_through` in the response so consumers can see when the static set expires. J.5 ships 18 new drift tests + 6 new Node holiday tests (the pre-correction drift signature Python=20/Node=18 is documented as historical; the post-correction state Python=20/Node=20/drift=0/verdict=ALIGNED is pinned); the python-engine suite is at 3245/4/0 with the previously-failing surface test resolved by the documented golden-refresh.

J.6 lands the Node session-phase mirror. Before J.6, every Node caller — `routes/health.js`, `services/executor.js`, `index.js` (the telegram callback handler) — could only see a binary `isMarketOpen()`; CAS sub-windows were structurally invisible on the Node side even though the J.1 Python classifier knew about them. J.6 ships `sessionPhase(observation_at, opts)` and `currentSessionPhase()` as Node-side mirrors of `python-engine/market_calendar.classify_session_phase`. The contract is bit-perfect: 10 documented phases (CLOSED, PRE_MARKET, CONTINUOUS_TRADING, CAS_REFERENCE_PRICE_WINDOW, CAS_ORDER_ENTRY, CAS_LIMIT_ENTRY_ONLY, CAS_MATCHING, DERIVATIVES_CAS_ALIGNED, CAS_POST, UNKNOWN), identical boundary semantics, IST-clock-aware via `Intl.DateTimeFormat({Asia/Kolkata})`. `sessionPhase()` accepts Date / millisecond-number / ISO-8601-string inputs; naive timestamps default to UTC (matching Python); invalid inputs return `UNKNOWN` without raising. The Phase-1 CAS eligibility probe is mirrored via `opts.cas_eligible` (caller-supplied override) with fallback to the J.2.1 list when absent. Wiring: `routes/health.js` exposes `session_phase: currentSessionPhase()` in `/` GET; `services/executor.js` logs `execution_phase_at_reject` whenever the `isMarketOpen()` guard fires; `index.js` telegram callback now reports "Market in {phase}. Cannot execute now." The invariant is pinned by a 2,355-vector golden regenerated by `python-engine/tests/fixtures/regenerate_session_phase_golden.py` from the live Python classifier and asserted bit-perfect by `node-gateway/server/tests/unit/sessionPhase.test.js`. The regenerator uses two sweeps: a wide minute-granularity sweep (8 days × 24 hours × 4 minutes × 3 option-combos = 2304 vectors) plus a focused second-granularity boundary pass (17 instants × 3 option-combos = 51 vectors) that hits `CAS_LIMIT_ENTRY_ONLY` (15:29:30 - 15:30 IST, ~30-second-wide sub-window) and `CAS_POST` (derivatives 15:40 - 16:00 IST) — both invisible to a minute-granularity sweep. Net: Node full suite 360/4/0 (was 317/4/0; +43 new tests in `sessionPhase.test.js`); python-engine full suite 3247/4/2 pre-existing failures (both unrelated to J.6 — verified by zero imports of any J.6 file). J.6 ships observability only; CAS-aware execution gating is the J.7 plan slice.

J.7 closes the loop on CAS awareness. J.6 gave the Node side visibility into the bounded phase; J.7 uses it to gate execution. Before J.7, an EXEC at 15:30 IST would be sent to Kite during `CAS_MATCHING` — NSE rejects, broker queues for post-CAS execution, or broker silently drops. Both outcomes are production hazards. J.7 ships `isExecutionAllowed(opts)` in `node-gateway/server/utils/market-hours.js` and `execution_allowed(...)` in `python-engine/market_calendar.py`. Both return `{allowed: bool, phase: str, reason: str|null}`. The translation table: `CONTINUOUS_TRADING` / `DERIVATIVES_CAS_ALIGNED` -> allowed; `PRE_MARKET` -> blocked unless `allow_pre_market=true`; `CLOSED` / all `CAS_*` / `UNKNOWN` -> blocked. NEW `node-gateway/server/utils/errors.js::CasPhaseError(phase, reason)` (status 422, code `cas_phase_blocked`) carries the phase + reason for the operator dashboard / telegram callback. Wiring: `services/executor.js` replaces J.6's `currentSessionPhase()` observability log with the J.7 verdict — throws `CasPhaseError` for CAS-blocked phases (preserves `MarketClosedError` for `CLOSED` so the existing error-code surface stays compatible); `index.js` telegram callback shows `verdict.reason` for CAS-blocked phases. The invariant is pinned by a 3,525-vector golden regenerated by `python-engine/tests/fixtures/regenerate_execution_allowed_golden.py` and asserted bit-perfect by `node-gateway/server/tests/unit/isExecutionAllowed.test.js`. Window boundary correction: J.6's docs listed CAS sub-window widths that did not match the live Python constants — the actual boundaries are `CAS_REFERENCE_PRICE_WINDOW` 15:15-15:20, `CAS_ORDER_ENTRY` 15:20-15:25, `CAS_LIMIT_ENTRY_ONLY` 15:25-15:30, `CAS_MATCHING` 15:30-15:35, `CAS_POST` (cash) 15:35-16:00, `DERIVATIVES_CAS_ALIGNED` 15:30-15:40. Net: Node full suite 380/4/0 (was 360/4/0; +20 new); python-engine full suite 3267/4/1 pre-existing failure (the J.6-documented `test_coverage_vocabulary.py` aiosqlite-threading flake).

J.7-HARDENING (independent correction plan) replaces the Node-carried CAS-eligibility list with an authoritative Python projection. Before this slice, `isExecutionAllowed` ran a pure check that consumed whatever CAS eligibility the Node supplied — in practice the Node carried a hardcoded `CAS_PHASE1_FNO_UNDERLYINGS` env list, creating a second, silently divergent eligibility surface. NEW `python-engine/routes_market_session.py::cas_eligibility` is the **single authoritative projection** of `market_calendar.is_cas_eligible`. The route is authenticated via `X-Internal-Secret` (returns 403 without the secret), returns `{symbol, cas_eligible, source, source_version}`, and the `source_version` is a SHA-256 hash of the configured CSV — the configured symbols are not disclosed over the wire. NEW `node-gateway/server/services/cas-eligibility.js` is the **only** path that fetches CAS eligibility. `resolveCasEligibility(symbol, observationAt)` short-circuits outside `isCashCasEligibilityResolutionWindow` (the 15:15-15:29 IST cash-CAS-affected interval) with `{required: false, resolved: true, casEligible: false}` so we never make an unnecessary HTTP call; inside the window it fetches the Python projection with the configured timeout. Failures return `{required: true, resolved: false, casEligible: null, reason: ...}` — the operator sees the human-readable reason and the system fails closed. NEW `entrySessionVerdict(symbol, observationAt)` chains eligibility resolution with the existing `isExecutionAllowed` verdict: an unresolved eligibility returns `{allowed: false, phase: 'CAS_ELIGIBILITY_UNAVAILABLE', reason: ...}`. Both `services/executor.js` and `index.js` (the telegram callback handler) now call `entrySessionVerdict(signalData.ticker, new Date())` **before** any DB UPDATE / EXECUTING transition / answerCallbackQuery — a `CAS_ELIGIBILITY_UNAVAILABLE` failure short-circuits execution; `executor.executeSignal` is never reached; no `EXECUTING` status is recorded; the operator sees `show_alert: true` with the phase-specific reason. NEW `tests/test_market_session_route.py` (3 tests: 403 without secret; 200 projects the configured CSV onto the supplied symbol; 200 returns `false` for unconfigured symbols). NEW `tests/unit/cas-eligibility.test.js` (3 tests: does not fetch outside the affected window; uses the authenticated Python projection inside the window with the `X-Internal-Secret` header; fails closed when the resolver is unavailable). Updated `tests/unit/executor.test.js` (2 new tests: blocks before broker calls when CAS eligibility cannot be resolved; passes the actual ticker to the authoritative resolver), `tests/integration/telegram-callbacks.test.js` (1 new test: blocks the EXEC callback when authoritative CAS eligibility is unavailable), `tests/integration/approved-snapshot.test.js` (mock added so existing tests reach the executor). `utils/errors.js` now exports `CasPhaseError`. The Node side is no longer a second source of eligibility truth — when the Python projection is unreachable, the Node side blocks entry rather than defaulting to continuous trading.

J.8 surfaces the bounded phase to the operator. J.6 made the bounded phase available via `health.session_phase`; J.8 makes the dashboard render it. NEW `node-gateway/client/src/utils/sessionPhase.js` is the pure single-source-of-truth utility: bounded phase -> colour class + display label + `isExecutionBlockedByPhase`. Fail-closed contract: any non-bounded input (null / undefined / garbage strings / numbers) returns `executionBlocked: true` so a misconfigured health payload never silently allows an order that the server would reject. NEW `SessionPhaseBadge` (compact chip with lock-icon when phase blocks) renders in `StatusBar.jsx` next to the binary "Open/Closed" indicator. NEW `SessionPhaseCard` (full card with phase label, broker-order verdict, and short description) renders on `Dashboard.jsx`. `SignalCard.jsx` gains a new `sessionPhase` prop and disables the EXEC button via `isExecutionBlockedByPhase` — the dashboard mirror matches the J.7 server gate so the operator's view matches what the server accepts. NEW `tests/sessionPhase.test.mjs` (15 tests via Node's built-in `node:test` runner): phase enumeration, label/color completeness (10/10), `coercePhase` null/undefined/garbage handling, `isExecutionBlockedByPhase` (8 blocking + 2 allowed + bad inputs), `describePhase` bundle, colour-bucket assertions (CAS=yellow, allowed=green, CLOSED/UNKNOWN=red). Net: client full unit suite 40/0/0 (was 25/0/0 at J.7 close; +15 new); Node full suite 380/4/0 unchanged (J.8 changed no Node code); python-engine J-slice 209/0 warnings-fatal (no regression). J.8 ships observation only; CAS-aware signal handling is the J.9 plan slice.

J.9 stamps the bounded phase at signal insertion. Before J.9, `received_signals` recorded `signal_time` (when the signal was generated) but not the phase at which it was received. Operators querying "how many signals arrived during `CAS_MATCHING`?" had no way to answer. NEW `received_signals.session_phase TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (session_phase IN (...10 phases...))` column in `node-gateway/server/db/schema.sql`. The `DEFAULT 'UNKNOWN'` covers existing rows (pre-J.9) so the additive migration does not break the production SQLite DB. NEW `stampSessionPhaseForSignal(ticker)` in `node-gateway/server/utils/market-hours.js` returns one of the 10 documented phases (never null, never an unrecognised string); non-string tickers (null, undefined, numbers, objects, arrays) route through `currentSessionPhase()` and the result is bounded by `STAMPABLE_PHASES` (the exported Node-side mirror of the DB CHECK constraint). Drift between `STAMPABLE_PHASES` (Node) and the DB CHECK (SQL) is a category-1 invariant failure. Wired into `routes/signals.js` (OpenClaw webhook insert) and `routes/internal.js` (Python engine callback insert) -- the phase recorded is the LIVE phase at the moment of arrival, not `signal_time`. NEW `tests/unit/sessionPhaseStamping.test.js` (5 tests): schema.sql CHECK constraint cardinality + `STAMPABLE_PHASES` cardinality pinned at 10; helper never throws on bad input; output always in the bounded set. Net: Node full suite 385/4/0 (was 380/4/0 at J.8 close; +5 new); python-engine J-slice 224/0 warnings-fatal (defensive regression only; J.9 made no Python changes).

J.10 ships the CAS-branch reachability gate, NOT an auction strategy. Plan §14 explicitly forbids auction-imbalance research and auction-based strategies: "any auction-based strategy is separate research with auction execution semantics, not an extension of a continuous-market fill model." The J.4 done-doc says "without `docs/j2_captures/YYYY-MM-DD/` receipt files passing `j2_capture_review.py`, the classifier's CAS branches are wired but unverified against real Kite." J.10 ships the **runtime gate** that enforces this boundary. NEW `python-engine/cas_reachability_gate.py`: pure / total module that walks `docs/j2_captures/`, reads each J.3 capture's `classifier.phase`, and emits `{verdict, captured_phases, missing_phases, coverage_pct, captures_scanned, captures_skipped}`. `CAS_BRANCHES_REQUIRING_EVIDENCE` is the 6 branches (5 CAS sub-windows + DERIVATIVES_CAS_ALIGNED). Defensive invariant: `CAS_BRANCHES_REQUIRING_EVIDENCE` is checked against `market_calendar._VALID_SESSION_PHASES` at import time -- drift between the gate's required set and the mirror's bounded set raises `RuntimeError` (category-1 invariant failure). NEW `python-engine/tools/cas_reachability_check.py`: operator-facing CLI with `--captures-dir`, `--json`, `--write`; exit 0 on REACHABLE, 1 on UNREACHABLE, 2 on missing directory. NEW `python-engine/tests/test_cas_reachability_gate.py` (9 tests): empty / partial / full coverage, extra-files tolerated (SUMMARY.md/README.md/review_log.md ignored), corrupt-capture skipped, non-bounded-phase ignored, format_report shape, write_report idempotency.

J.10.CLOSURE lands the operator-facing SUMMARY.md surface. **Critical bug fix discovered during J.10.CLOSURE**: `_safe_phase_from_capture` was reading `doc["classifier"]["phase"]` and `doc["phase"]` -- but the J.3 capture schema (per `tools/j2_cas_probe.py::CAPTURE_JSON_SCHEMA`) stores the bounded phase at `rows[i].classifier_phase`. The gate was silently counting every capture as "skipped". Fixed to iterate `rows[]` and read `rows[0].classifier_phase`. NEW `update_summary(report, summary_path, *, captures_dir=None)` in `cas_reachability_gate.py` renders the gate's verdict into a deterministic markdown SUMMARY.md. NEW `--update-summary` flag on `cas_reachability_check.py` CLI. NEW auto-update hook on `j2_capture_review.py` happy-path: SUMMARY regenerates automatically when a capture review passes; fail-path leaves the SUMMARY untouched (fail-closed). NEW `tests/test_cas_reachability_summary.py` (10 tests pinning the SUMMARY contract: verdict line shows bold REACHABLE/UNREACHABLE, missing-branches section, "Generated at" marker, captures_dir path, review-tool pointer, never raises on missing dir, fail-closed, idempotent). NEW `tests/test_j10_closure_e2e.py` (3 tests: happy-path review auto-updates SUMMARY, failed review does NOT auto-update, in-process `main()` helper path). `tests/test_cas_reachability_gate.py` fixtures updated to the J.3 schema shape. Net: python-engine +22 tests (was 3267/4/1 at J.7 close; now 3289/4/1 pre-baseline at this slice); Node full suite 385/4/0 (no Node changes); client 40/0/0 (no client changes). The SUMMARY.md is the persistent audit surface; the gate currently returns UNREACHABLE because `docs/j2_captures/` has no operator-supplied staging captures -- flipping to REACHABLE is operator work (run probe in staging, review captures), per plan §14. Net: Python `test_cas_reachability_gate.py` 9/9 PASS warnings-fatal; J-slice (16 files) 268/22 (the 22 are the J.6-documented `test_calendar_gates.py` cross-test isolation noise, verified by isolation re-run); Node full suite 385/4/0 unchanged (no Node changes in J.10); client full suite 40/0/0 unchanged. CLI invocation on the empty `docs/j2_captures/`: exit 1, UNREACHABLE, 0.0% coverage -- the **correct** state for J.10 (the operator-supplied captures are still pending; J.10 is the gate that waits for them). Closing this gap is the operator's responsibility, not a J.10 follow-up.

J.10.CLOSURE catalog enhancement: a follow-up slice (`12912b1`) adds a per-branch `captures_by_branch` field to the gate's report dict (per-branch list of relative paths) and renders it in three places: SUMMARY.md gains a `## Captures catalog` section listing each captured branch's captures as relative paths under a markdown sub-heading (branches with zero captures render `(no captures yet)`); the CLI's human-readable output gains a `captures catalog:` block; the CLI's `--json` output now includes the field. The catalog is purely informational -- the gate's verdict remains purely count-driven. NEW `tests/test_cas_reachability_check.py` (9 tests via subprocess) pins the CLI contract end-to-end: exit codes (0 REACHABLE / 1 UNREACHABLE / 2 missing-dir), `--json` shape stability (exactly 7 documented keys), `--update-summary` writes SUMMARY.md, `--summary-path` overrides, `--write` persists JSON report independent of `--update-summary`, human output renders the catalog. Net: python-engine +12 new tests (3 catalog + 9 CLI); 0 regressions; Node 394/4/0 + Client 40/0/0 unchanged.

J.10.CLOSURE runbook fix (`1c35633`): the SUMMARY's "How to add captures" section previously showed a probe command with the legacy `--observation-at 15:22:00 IST` syntax, which `tools/j2_cas_probe.py` does not accept (it takes ISO 8601 timestamps). Replaced with a per-branch IST-window cheat-sheet (CAS_REFERENCE_PRICE_WINDOW 15:15-15:19:59, CAS_ORDER_ENTRY 15:20-15:24:59, CAS_LIMIT_ENTRY_ONLY 15:25-15:29:59, CAS_MATCHING 15:30-15:34:59, CAS_POST 15:35-15:59:59 cash, DERIVATIVES_CAS_ALIGNED 15:30-15:39:59) and two ISO 8601 example commands. The runbook cross-references the "Captures catalog" section so a passing review surfaces in the same neighborhood without re-running the CLI. +3 new tests in `test_cas_reachability_check.py` (CLI subprocess): per-branch IST-window render, legacy-syntax rejection, catalog cross-reference.

J.10.CLOSURE `--status` flag (`2b7a670`): the CLI's multi-line human-readable output is awkward for shell prompts, monitoring agents, and CI summary lines. NEW `--status` flag emits a single-line summary: `J.10: <VERDICT> <coverage_pct>% (<captured>/<total> branches, <scanned> scanned, <skipped> skipped)`. Exit code follows the gate's verdict (0 REACHABLE / 1 UNREACHABLE / 2 missing-dir) so it composes with CI gates exactly like the multi-line mode. `<captured>` counts branches with >=1 capture (the gate's count-driven contract), NOT the total number of capture files. +3 new tests: single-line format on UNREACHABLE, REACHABLE 100.0% on all 6 branches, count-driven branch counting (5 captures on one branch = 1 branch). Net: python-engine +6 new tests since J.10.CLOSURE close (3 catalog + 9 CLI + 3 runbook + 3 status = 18 over two sessions); 380/380 PASS at this point.

The historical 15:30 → 15:40 expiry mismatch for derivatives (`fno_chain.EXPIRY_CUTOFF_HOUR/_MIN` and `hedge_strategies._EXPIRY_CUTOFF`) is documented but explicitly NOT fixed in J.1 through J.10 — plan §14 forbids changing strategy deadlines without operator sign-off.

## 6. Broker execution and accounting

The D release-baseline correction restores legacy test fixtures to the startup-migrated ledger contract without changing runtime accounting. A regression verifies repeated migration preserves old rows and accepts new close provenance (`origin_ref`). Windows source guards now read UTF-8 with closed handles; scheduler wrappers document actual delegated calendar gates and deliberate off-session cleanup/reconciliation exceptions. The existing partner-bot default remains `True`; explicitly disabling it still prevents network-client construction, and credentials/qualification/final dispatch remain separate gates. Full Dev Python acceptance now passes 2,545 tests (three skips, 23 existing deprecations); this is not deployment or strategy qualification. See `2026-09-13-release-baseline-plan.md` for the precise release status and warnings.

Gateway files `services/kite.js`, `executor.js`, `risk-geometry.js`, `halt-switch.js` and `routes/orders.js` deserve focused review before any execution change. `token-store.js`, `token-restore.js`, `routes/token.js`, engine `token_lifecycle.py` and `kite_client.py` handle the authentication/provider bridge. Do not log secrets or infer an authenticated broker session from a process heartbeat.

Token restoration now releases each abort timer in `finally`, including fetch failures, and keeps response-body parsing under the same three-second abort scope. Retries and internal authentication remain unchanged. Filesystem-only dead-letter tests stub Telegram rather than start fake-token polling. The current native gateway suite passes 324 tests (four skips) and exits naturally without forceExit or detected open handles. The Windows instrument-test socket warning was traced to a manual asyncio.run between pytest-managed async tests; that test now uses pytest's lifecycle. Original failing four-file warning-fatal acceptance passes 32 tests; broader resource-warning-fatal research acceptance passes 181 tests. This does not prove all operational resources are leak-free in Production.

`performance.py` owns ledger functions used by the application. `performance_analytics.py` and `performance.py` must be read with the relevant position stores. `broker_reconciliation.py` checks imported statement cash arithmetic, `reconciliation_evidence.py` checks internal ledger/position links, and `broker_internal_reconciliation.py` performs the narrower one-way executed-order reference check described above. None alone proves full broker reconciliation. `order_execution_readiness.py` reports order-path evidence; submitting a real order merely to turn UNVERIFIED green is not a valid test plan.

Five reconciliation warnings were previously observed in the UI. Historical screenshots are not current facts. Investigate by account, module, execution mode, close identity and fee treatment; do not overwrite one store to match another. Broker confirmation, net cash and gross position P&L can have different timing and cost conventions.

### F3/F4/F5/F6 — independent correction plan hardening

The independent correction plan (`docs/2026-09-14-independent-correction-plan.md`) tightens the F-substrate at the writer/account/output contract level. These are **fail-closed** changes — every one of them converts a previous "best-effort" or "fabricated default" behaviour into an explicit refusal, so the system cannot silently grant authority it does not actually possess.

**F3 mark_to_market**: `fno_positions.qty` is now contract units (the writer persists `lots * lot_size`; MTM does NOT multiply `lot_size` again). Legacy fno_dr_book rows without an immutable tradingsymbol/token return `QuoteStatus.UNSUPPORTED` with a dedicated note — the aggregate never guesses a symbol. `OpenMarkToMarket.total_unrealised_pnl` is preserved for backwards compatibility (partial subtotal only); a NEW `complete_unrealised_pnl` returns `None` when any mark is non-FRESH. Consumers must opt into the new field. `run_penny_hourly_report` now uses `complete_unrealised_pnl` and renders 'UNAVAILABLE (incomplete/stale quotes)' instead of a misleading `Rs +0`. NEW `tests/test_mtm_reporting_independent.py` (3 tests) pins the contract: incomplete aggregate returns `complete_unrealised_pnl=None` even when the legacy partial subtotal is zero; fresh flat book returns `complete_unrealised_pnl=0`; the active and no-action hourly reports label UNAVAILABLE rather than `Rs +0`.

**F4 discrepancies**: `record_from_evidence_report` writes internal ledger facts under `INTERNAL_UNSCOPED_ACCOUNT_ID` (one fact, one attribution — the same internal fact cannot be attached to two different broker accounts). `_row_to_record` reads `account_attribution` from the DB: `INTERNAL_UNSCOPED` for the dedicated sentinel, `UNVERIFIED_LEGACY_ACCOUNT_ATTRIBUTION` for pre-existing rows in INTERNAL_EVIDENCE_CATEGORIES, `ACCOUNT_SCOPED` for genuine broker-attributed rows. Pre-existing accountless history is preserved rather than silently rewritten to a broker account. NEW `test_legacy_internal_account_attribution_is_unverified` and `test_same_internal_fact_is_not_attached_to_each_broker_account` pin the contract.

**F5 reconciliation_cli**: `_payload_to_import_kwargs` rejects null/blank `account_id` or `statement_id` (previously they would coerce to `'None'` or `'   '`). The `_import_statement` response no longer carries an `imported` boolean — that was a behavioural claim the operator could not verify against the on-disk artifact. NEW `test_main_retry_writes_identical_immutable_output` pins byte-identical retry: two runs of the same immutable payload produce a byte-identical output file.

**F6 capital_policy**: `CapitalPolicyThresholds.loss_tolerance_pct` is now `Optional[float]` — the previous 25.0 default was a fabricated engineering default for the explicit user input plan §10.5 mandates. The config default flips to `None`. `live_current_inr`, `drawdown_pct`, `consecutive_losses` are now `Optional`; missing facts render as `None` in the human-readable summary rather than zero. The CLI never returns `can_grow_live_capital=True`; an explicit `authorization_effect: NONE` field documents that a completed evaluation is a diagnostic, never an executable promotion grant. NEW `tests/test_capital_policy_independent.py` (5 tests): `requested_delta_inr` strictly-positive-nonboolean, refuses `loss_tolerance_pct` until explicit input, missing execution quality as `INSUFFICIENT_EVIDENCE`, the accountless-wrapper refuses without creating a database, and rejects boolean numeric thresholds.

**Affordability**: `tests/test_affordability_integration.py` converted to `@pytest.mark.asyncio` (no more `asyncio.run` inside pytest's managed loop) — a Windows pytest-asyncio warning surfaced during the D-baseline was traced to this exact pattern.

Net: python-engine +12 new tests (5 F6 + 7 F3/F4/F5), 0 regressions. The F-substrate is now writer-faithful, account-authoritative, and CLI-immutable across retries.

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

The trailing-composition follow-up now honors NEXT at-open, bounded pullback limit and completed-bar-confirmation entry behavior before applying the selected trailing exit. Intrabar limit fills don't ratchet from a possibly pre-fill entry-bar high; confirmation bars cannot fill or ratchet the position. Gap-invalid entries remain no-fill and nonfinite cost assumptions fail closed. Root's ten-file proactive/G suite passes 121 tests with warnings fatal; Terra independently reviewed causality and found no blocker. Existing primary comparison runs retain their implementation fingerprint and reject incompatible reuse. G.7 subsequently makes RANGE_REVERSION a causal dedicated hypothesis and removes the stale alias gate; old reports remain retained and cannot be reinterpreted because implementation hashes differ.

The exit-cache follow-up closes that proposal-clock/implementation identity gap: new `matched-exit-evidence-v3` manifests bind effective full proposal identities/timings, snapshotted bars, costs and both evaluator source hashes. A companion `proactive_exit_research_manifests` table retains canonical JSON without changing the original four-column results table. Legacy reports remain readable but cannot be reused as current-version runs; incompatible reuse fails rather than overwriting history. Atomic final recheck handles concurrent identical/conflicting requests, and duplicate opportunity IDs cannot inflate the sample. Root's current proactive/G suite passes 137 tests with warnings fatal. These are input/implementation integrity checks, not genuine held-out provenance, qualification or live authorization; approval validation/range semantics/F evidence remain open.

Approval-budget validation now requires the relevant retained amount, drawdown cap and integer expiry, rejecting booleans/nonfinite values before SQLite coercion. Approval transitions use budgets predeclared on the original unsigned record and a half-open validity window anchored to its original clock; signing later cannot extend expiry. Reads preserve recorded history and expose budget validity/expiry/version status, while `approval_usable=False` explicitly blocks missing frozen held-out/account/F/D evidence. This is budget validation, not full evidence approval or order authority. The twelve-file F/G suite passes 180 tests with warnings fatal; the previous whole-engine receipt predates this and the cache change.

`proactive_market_data.py`/`market_data_sources.py` address provider observations; `proactive_execution_research.py`, `proactive_exit_research.py` and `proactive_portfolio_research.py` compare choices. `proactive_diagnostics.py` and `operational_coverage.py` explain activity gaps. Demo modules exercise synthetic workflows. These components are useful foundations, not automatically broker-consuming strategy deployments.

Optional AI is represented by `optional_ai_status.py`, agent typed `advisory.py`, and `async_reviews.py`. A disabled or unavailable model should leave deterministic signal/risk/delivery functioning. Review timeout, budget, queue saturation, stale results and process restart before extending model use. The user's preference is assistance without absolute dependency.

I.4.D source-event classification (the only plan-§13 explicit gap that previously had no implementation) lands a bounded 8-category classifier against the J.2 sourced news. `agent/news_classifier.py` is pure / total: a fixed `NewsCategory` enum (`REGULATORY`, `EARNINGS`, `M_AND_A`, `GUIDANCE`, `MACRO`, `RUMOR`, `TECHNICAL`, `UNKNOWN`); a frozen `ClassificationResult` dataclass with `title_hash`, `category`, `confidence ∈ [0,1]`, bounded rationale (≤ 280 chars), `prompt_version`, `classified_at`; `CONFIDENCE_THRESHOLD = 0.6` forces low-confidence results to UNKNOWN (fail-closed); `CLASSIFIER_TIMEOUT_SEC = 1.0` per-item latency budget; never raises (timeout / parse error / disabled / model exception → UNKNOWN + confidence=0.0). The taxonomy is operator-defined — a category the model invents (outside the enum) is forced to UNKNOWN. The classifier never grants authority, never persists state, never executes. `DISABLE_CLASSIFIER` forces every result to UNKNOWN (offline / CI / sandbox). `analyze_with_minimax` accepts an optional `pre_classifications: Optional[List[ClassificationResult]] = None` parameter; when supplied, the prompt renders a "CLASSIFIED SENTIMENT DATA" section (above the existing "MULTI-SOURCE SENTIMENT DATA" section) listing `title_hash + category + confidence + rationale` per headline; when None (the default, every existing caller's path), the prompt renders a placeholder text and is byte-identical to its pre-I.4.D shape. Two env-flagged helpers (`_fetch_news_items_for_ticker`, `_maybe_classify_news`) wire the classifier into the verdict call sites when `ENABLE_NEWS_CLASSIFIER=1`; the helpers never raise. The operator CLI `python -m agent.tools.news_classify_cli --ticker TICKER | --input PATH [--dry-run] [--json]` runs without touching the verdict pipeline (lazy-imports `agent.fetch_news_items` only for `--ticker`); exits 0/1/2/3 with structured diagnostics. Agent suite grew 213 → 253 across the I.4.D commits (zero regressions); 36 module tests + 10 helper tests + 9 verdict-prompt integration tests + 21 CLI tests pin the contract.

I.4.E bounded contract-health self-evaluation (per the I.4 deep-research doc's "guard the guards" pattern) lands a pure self-evaluation module that asserts the bounded contract on the agent's own surfaces. `agent/contract_health.py` exposes five independent checks plus an aggregate `evaluate_contract(...)` that returns a `ContractReport` (`passed`, `checks[]`, `evaluated_at`, `schema_version="i4e-v1"`). The five invariants: (1) `status_envelope_authority` — the bounded health envelope carries no execution authority (rejects `can_place_orders != False`, `authorization_effect != "NONE"`, unknown top-level keys); (2) `no_prompt_leakage` — the bounded snapshot carries no prompt or reviewer content (rejects `prompt`, `rationale`, `pitch`, `risks`, `raw_response`, etc., at the top level and inside any `usefulness` sub-envelope); (3) `usefulness_counters_only` — every `usefulness` key is in the allow-list AND every value is a bounded primitive (`int`/`float`/`str`/`None`), with `verdict_counts` typed as `dict[str, int]` (bool values are rejected explicitly); (4) `classifier_fail_closed` — every `ClassificationResult` below `CONFIDENCE_THRESHOLD=0.6` must map to `UNKNOWN`, every category outside the bounded enum is a violation, every rationale > 280 chars is a violation; (5) `review_non_authoritative` — a `Review` must not carry any of `FORBIDDEN_REVIEW_DELTA_FIELDS` (`can_place_orders`, `authorization_effect`, `live_delta_inr`, `capital_delta`, `qualification`, `approved_live_budget`) — per plan §13 "the typed result must not change capital limits, qualification or order/delivery authority". All inputs are optional (`None` means "not inspected in this run", never a violation), letting the operator run the harness with only one surface available. The pure module imports `agent.news_classifier` lazily inside `check_classifier_fail_closed` so it stays importable in isolation (the `agent.py` import path triggers a Telegram env-var check at module load). The operator CLI `python -m tools.contract_health_check {print-config | check <path> | self-check}` is read-only; exit 0 iff every check passed, exit 1 on any violation, exit 2 on I/O/parse/shape error. Agent suite grew 259 → 312 (+53 net) across this slice. See [I.4.E done-doc](2026-09-14-i4e-contract-health-done.md).



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

## 16. September 20 AI activation and truthful hedge staging

The Compose contract now explicitly enables the bounded optional-AI queue,
source-event classification and usefulness telemetry. Its safe policies remain
`proceed`/`advisory`: AI supplies non-authoritative context and cannot place an
order, change capital or silently become a hard veto. The manual partner
advisory switches are also explicit. `PARTNER_HEDGE_ENABLED=true` permits the
advanced Phase-2/3 shadow jobs to observe real inputs, while both advanced
delivery switches remain explicitly false and both shadow switches remain
true.

Phase-2/3 staging days are no longer expected to arise from elapsed uptime or
manual bookkeeping alone. `record_shadow_staging_day` writes one idempotent
system receipt per phase and IST date only after the shadow cycle processes at
least one reconciled underlying through a fresh option-chain context. Missing
login, missing positions, a closed market, stale/unavailable chains, stopped
services and scheduler invocation alone do not count. This system receipt does
not satisfy manual live-chain verification or per-kind Telegram sample review,
does not enable delivery and does not create qualification.

The read-only Production inspection behind this change found three manual
advisory ideas on 2026-09-17, no advanced hedge shadow evaluations, no hedge
gate evidence and no reconciled partner positions. Core application containers
were stopped with exit 137 and `OOMKilled=false`. Production flags were unset
despite a present MiniMax credential. These facts explain 0/7; they do not show
that the strategy gates rejected seven genuine staging sessions.

The partner-readiness CLI now reads the actual persisted profile, input-status,
idea, strategy-qualification and hardened `partner_hedge_messages` schemas.
The predecessor version used obsolete column/table names and treated advanced
Phase-3 readiness as the final gate for ordinary manual advice. The corrected
seventh check reports the manual-advisory enable/delivery configuration;
advanced 0/7 progress remains nested informational evidence with
`blocks_manual_advisory=false`. Database connections are read-only, and a
quiescent read-only Docker mount may use immutable SQLite mode only when no
non-empty WAL exists.

### Exact release-range notes (2026-09-20)

`scripts/build_release_notes.py --base-ref REF` now resolves `REF` and `HEAD`
to immutable commit SHAs and inventories the complete two-dot range. It no
longer labels a latest-30 snapshot as though it were the requested release
range. The generated header records the requested range, resolved base SHA,
resolved SHA range and ahead count. An invalid base or an uninspectable range
fails with exit code 2 before stdout or `--out` is written. Omitting
`--base-ref` intentionally retains the bounded latest-30 diagnostic view.

The tool never fetches, merges, deploys or edits Git state. Reviewers must
fetch explicitly before generation when they need a fresh remote-tracking
base, then verify the resolved base SHA against the intended PR target.

The broker-statement operator report uses the ASCII currency code `INR`
instead of the rupee glyph. Numeric reconciliation semantics are unchanged;
the representation prevents Windows cp1252 consoles from crashing before a
`MATCH` or `UNRESOLVED` result can be displayed.

### Reproducible session-phase goldens (2026-09-20)

The J.6 regenerator treats `generated_at_utc` as the time the semantic fixture
content last changed. If schema/classifier/vector content is identical, it
preserves that timestamp, emits canonical UTF-8 with a trailing newline and
skips writes whose bytes already match. If any semantic content changes, a new
timestamp is assigned and the exact same payload is dual-written to the Python
and Node consumers. No-op verification therefore leaves a clean checkout while
real phase changes remain visible and attributable.
