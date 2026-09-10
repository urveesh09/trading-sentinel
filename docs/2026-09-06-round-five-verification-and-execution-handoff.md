# Verification of 7b19ffc and precise implementation handoff

Date: 6 September 2026, IST. Baseline: `7b19ffc959a30073ca67ab45bb297f29dbf9fbe7`, Dev branch `codex/production-correction-hedge-p0`.

## Answer: is everything implemented?

**No.** Most of the reported round-four correctness changes are present and useful. The new generation model still permits equivalent in-flight claims and bypasses rate-limit delays across generations. Final pre-dispatch revision validation also remains incomplete. The broader proactive trading, strategy basket, accounting/learning and optional-AI roadmap has not been implemented by this commit.

This document is the next implementation brief. Use it for execution order and acceptance requirements; use `2026-09-06-round-four-audit-and-income-system-roadmap.md` for the detailed product rationale and strategy hypotheses. Preserve both earlier audits and their probes as evidence. Do not reinterpret this document as proof of profitable trading or authority to send a live canary.

## Independently verified

- **289 selected Python tests passed**, one existing Starlette lifespan deprecation warning.
- **46 gateway executor tests passed**.
- Inspected the full commit diff and new regression coverage. Only hedge application files, their tests and the remediation log changed; no strategy basket or AI code changed.
- Added and executed `docs/review-2026-09-06-round5/probe_generations.py`. It uses temporary SQLite storage and no network. Recorded output is alongside it.
- Production was read-only; its pre-existing untracked `migration/` remains. No new Production performance assessment, live Telegram send, broker order, configuration change or deployment was performed.
- This review adds documentation/offline probes only. No application fix is implemented in this turn.

| Earlier requirement | Status at this commit |
|---|---|
| Preserve ambiguous transport after failure-write exception | Implemented for the same generation: durable in-flight state is retained. Equivalent new generations can still bypass it: S1 below. |
| Terminal retirement and conditional ownership | Implemented: terminal-state set includes retired; retirement requires matching detail and no live token. |
| Explicit missing snapshot | Implemented and independently probed: returns `NO_ACCEPTED_PORTFOLIO_SNAPSHOT`. |
| Portfolio revision on create/manual reconcile/close/snapshot | Implemented transactionally; recovery compares the revision. Initial dispatch and accepted-envelope integrity still need S3. |
| Invalid-open-row readiness | Implemented through consistent input and readiness call sites. |
| Economic decision versus delivery generation | Implemented; independently confirmed an expired unsent generation permits a fresh one and persisted manual recovery blocks an equivalent generation. Cross-generation ownership/backoff is incomplete. |
| Malformed recovery isolation and abandoned sweep | Implemented for the recovery loop. Full typed handling in claim lookup and the operator resolution lifecycle remain incomplete. |
| Real producer for new/reopened/corporate-action holdings | Still outstanding; existing importer reconciles known internal IDs. |
| Proactive activity funnel and strategy basket | Not implemented by this change. |
| Net-outcome learning, calibrated ranking, exit experiments | Not implemented by this change; existing components should be reused. |
| AI fully optional and asynchronous | Not implemented by this change. |

## Operating instructions for the implementer

Work only in `C:/Users/Urveesh/Desktop/trading-sentinel`. Read its AGENTS instructions and preserve unrelated/untracked files. Continue on the existing Dev branch unless worktree isolation is needed. Do not edit Production, read secrets into logs, place broker orders, send partner messages, or increase capital. Promote through GitHub under the existing release process.

Implement in small reviewable commits by work package. Update the remediation log with exact behavior, tests run, and open prerequisites. Never mark a package complete because only its helper functions or unit tests exist: scheduler/API consumers and offline integration behavior must work. Do not stop after safety fixes and claim the broader roadmap is done.

Current capital is approximately ₹8,000, with future owner-funded stages ₹20–50k, ₹1 lakh and ultimately ₹5 lakh. Max drawdown/withdrawal policy is not numerically specified. Keep risk settings explicit and unchanged until agreed; “earn as much as possible” does not define a loss budget. Development, instrumentation and shadow research can continue without those missing live settings.

## S — Complete the delivery contract first

### S1 / P0 — Serialize equivalent decisions across all generations

Location: `python-engine/hedge_advisory.py:275`, `_claim`.

Observed: generation g1 acquires a claim and records transport started; g2 for the same `decision_id` successfully acquires another claim one second later. Cross-generation lookup blocks delivered/manual states, but not an owned/transport-started claim. Thus the failure-write fix can leave g1 safely in-flight while a newly generated g2 still sends a duplicate before the abandonment sweep.

Implement a durable decision-level owner/guard, keyed by account, message kind, economic decision and exposure lifecycle. Acquire/update it in the same `BEGIN IMMEDIATE` transaction as the generation claim. Store normalized indexed identity/state fields rather than depending entirely on repeated scans of JSON history. While any equivalent generation is owned or transport-started, no other generation may dispatch. After lease expiry, unresolved dispatch becomes manual recovery at decision scope; do not release it to another generation automatically.

Minimum tests: two workers claim distinct generations of the same decision concurrently; g1 timeout plus failed ledger write then g2; process restart before sweep; independent decisions remain able to proceed; acknowledged g1 suppresses equivalent fresh g2. Assert **at most one transport start** across equivalent unresolved generations.

### S2 / P0 — Enforce backoff beyond one generation

Location: same `_claim` cross-generation lookup and rate-limit persistence.

Observed: g1 receives `retry_after_3600`; g2 with the same decision can claim one second later. Fresh generation identity currently bypasses the stored retry deadline.

Persist transport backoff at the appropriate bot/destination scope, plus decision attempt policy. A 429 deadline must apply to initial ticks and recovery, including different generations; do not rely on a local generation row. Preserve immutable attempts across generation replacement. When the delay exceeds quote validity, retire the generation and require new evaluation after the backoff, not an earlier fresh-key send.

Minimum tests: g2 before and after g1's retry deadline; another decision sharing the rate-limited destination; expiry before retry deadline; simultaneous regular/recovery worker; restart with deadline preserved. No POST before the applicable deadline. Do not accidentally share partner transport limits with the separate operator destination.

### S3 / P0 — Validate the evaluated portfolio at dispatch authorization

Locations: `_send_claimed_review` line 589, `_mark_transport_started` line 484, Phase-1 tick, Phase-2/3 tick and recovery.

Code finding: revision comparison currently lives in recovery. Initial ticks load inputs, await market context/chain acquisition and later send without checking whether that revision is still current. Recovery itself checks before a separate claim operation. A manual mutation/refresh can intervene. Also, advancing current revision does not record which revision was accepted as a complete envelope: a later manual mutation may still use the older envelope as completeness evidence during a fresh evaluation.

Implement one final dispatch-authorization transaction shared by initial/recovery paths. Require account binding, current portfolio revision, no invalid rows, valid generation, allowed phase and policy, and compatible complete input. Persist `accepted_portfolio_revision` (or equivalent dirty flag) with snapshot acceptance; manual mutation invalidates completeness until explicitly reconciled under the chosen contract. Include source/account/revision on advanced proposals too.

Use the actual authorization clock for expiry checks, not only the tick's start time. Define the transaction commit as the dispatch authorization boundary; do not hold a SQLite write lock over HTTP or claim to eliminate changes occurring after dispatch. A mutation before authorization must prevent that send. A change after dispatch requires supersession/updated advice policy.

Minimum tests: resize/close/new position during awaited chain construction; revision change between recovery evaluation and dispatch authorization; quote expires while queued; Phase-2 readiness or enablement changes before dispatch; manual mutation after complete snapshot requires fresh completeness proof. Zero stale transport starts before the authorization boundary.

### S4 / P1 — Typed ledger, migration, lifecycle and manual resolution

Handle JSON arrays/null/corrupt fields in `_claim` as well as recovery. Cross-generation lookup currently assumes decoded history is a dictionary. A bad historical row must not crash all subsequent claims of a kind. Quarantine/report corrupt rows; do not silently discard an uncertainty record and proceed as if no prior dispatch occurred.

Define upgrade handling for pre-generation rows that have `proposal_version` or old keys but no `decision_id`. New keys must not blindly duplicate prior delivered/ambiguous advice. If safe identity reconstruction is impossible, surface an explicit migration hold for affected records. Never backfill delivered status without evidence.

Define exposure lifecycle for actual close/re-entry, hedge removal and later reinstatement. Decision suppression must not last forever merely because the same contracts can be recommended again. Ambiguity resolution needs an authenticated operator action, reason/evidence, timestamp and immutable resolution event. Telegram acknowledgement is not partner trade execution.

Minimum tests: old delivered/ambiguous rows upgrade; corrupt same-kind history; true close/re-entry; operator resolution replay; invalid or unauthorized resolution. Provide a read-only backlog view even when sending is disabled.

### S completion gate

One integrated, barrier-controlled harness must exercise input acceptance → real builder → g1 → transport failure → concurrent g2 → mutation → recovery → later fresh evaluation. Tests should cover **both duplicate suppression and valid renewed delivery**, rather than making every path return false. Retain the broad selected suites. Keep these tests offline.

## I — Real partner input and useful hedging

Dependencies: S for live use; contract/fixtures can be built in parallel.

I1. Implement a source-neutral adapter interface with `external_position_id`, lifecycle identity, source/account binding, sequence, observed/received times, explicit covered books, completeness and per-field market timestamps. Resolve instruments and quantities deterministically. Support create, update, close, reopen and corporate-action transitions transactionally. Do not infer account completeness from an empty response to a failed request.

I2. Supply a deterministic fixture adapter plus contract tests without real credentials. Keep production adapter selection unconfigured until the approved source/account is supplied. Missing external integration must not prevent completion of schema, fixture ingestion and end-to-end shadow work.

I3. Generate partner cards from deterministic values: action, side, instrument, units/lots, exposure covered, estimated cost, remaining downside, validity and invalidation. Priority is actionable protection changes, then portfolio review, then routine context. AI may explain but not alter these numbers.

I4. Report input freshness, completeness, decision freshness, last acknowledged delivery and manual-recovery queue separately. Canary success requires the intended mapped recipient and one recorded acknowledgement; do not perform it without explicit authorization.

Acceptance fixtures: full holdings plus derivatives coverage, new position, duplicate source row, partial coverage, unknown instrument, missing Greeks, close/re-entry, corporate action, future timestamp, adapter outage. Each yields an explicit accepted/blocked reason and stable revision/lifecycle behavior.

## M — Measurement and proactive activity (start alongside S)

M1. Map existing signal/order/fill/ledger IDs before adding tables. Reuse `signal_log.py`, `fno_signal_log.py`, `penny_execution_journal.py` and existing accounting. Introduce one canonical `decision_id` linking candidate, policy version, data version, account/mode, order attempts, fills and final net outcome. Capture deposits/withdrawals separately. ₹5,000 becoming ₹8,000 is not automatically profit.

M2. Add append-only stage events: `UNIVERSE`, `DATA_READY`, `SETUP`, `COST_VIABLE`, `RISK_APPROVED`, `SUBMITTED`, `FILLED`, plus terminal reasons. Persist event time, session, strategy/version, unique opportunity ID and source. One opportunity repeated over scans must not inflate frequency. Partial fills and pending orders remain explicit.

M3. Wire scheduled diagnostics and a user-visible report/API into the existing reporting surfaces. Proposed investigation thresholds: two missed scan intervals; two healthy eligible sessions without a viable candidate; rolling five sessions with one or fewer fills. Treat these as diagnostic triggers, not compulsory orders. Explain affordability, tied-up capital, regime, costs, unfilled limits, missing data and defects separately.

M4. Every valid risk-approved opportunity must end in an order result or explicit non-submission reason. Add a sampled rejected-candidate ledger and a weekly bounded missed-opportunity report. Exclude holidays from trading-session windows. Broker fills, paper fills and partner confirmations must never be combined as live performance.

Acceptance: missed scheduler execution triggers visibility; stale data is not called market inactivity; repeated scans remain one opportunity; an operationally dropped eligible candidate is detectable; a legitimate no-trade day does not lower thresholds or create an order. Reconciliation reports identify every unexplained residual.

## A — Optional AI, never a required trading dependency

Files: `agent/agent.py`, `agent/advisory.py`, agent tests; preserve existing operator execution authorization.

A1. Decouple missing AI key/provider from agent alert/watchdog startup. Use explicit `AI_DISABLED`/`AI_UNAVAILABLE`. Do not require model initialization for deterministic operation.

A2. Emit valid deterministic alerts without waiting for LLM analysis. Add a bounded asynchronous review queue keyed by decision/event version, with deadline, cancellation/cleanup, circuit breaker and daily usage budget. No AI result may mutate prices, sizes, stops, account or recipient. Late results are archived as stale.

A3. Retain source links/publication times and resolve company identity for news context. Treat external text as data. AI initially explains, diagnoses inactivity and proposes experiments; no model-driven live risk/config changes or order authority. Review the current swing hard-veto policy explicitly when changing it; absence of AI does not bypass any non-AI safety gate.

A4. Compare deterministic baseline with optional AI in shadow, including delay and API cost. AI influence on rankings stays disabled until measurable incremental value is established. Keep partner and operator message routes distinct.

Acceptance: missing key, timeout, outage, malformed reply, queue saturation, stale/wrong-company headline, changed same-ticker opportunity, altered numeric field. Core exits/risk/alerts/watchdog continue; existing operator approval stays required where it was required.

## B — Proactive three-sleeve research basket

Dependencies: M; use the detailed hypotheses in the round-four roadmap. This is research, not a declaration that a best strategy has been discovered.

B1. Register three explicit policy IDs: trend pullback/continuation, stabilized range reversion, contraction breakout. Keep intraday/overnight variants separate. Reuse existing engine/regime/EDGE features but validate transferred parameters. At ₹8,000 the live allocator selects among sleeves rather than splitting cash into three uneconomic positions.

B2. Build a liquid/affordable point-in-time universe, incremental completed-bar features and a watchlist with trigger, expiry and invalidation. Profile before expanding the universe. Test the proposed 5–15-minute intraday cadence against measured latency/costs; keep exit/protection work ahead of scans/research. Re-evaluate after genuine changes in data, spreads, capital or setup state.

B3. Implement a common proposal contract: strategy/version, decision ID, signal time, evidence/data version, action, entry policy, expiry, initial stop, exit policy, expected cost/net outcome and uncertainty, required capital, portfolio exposure and rejection reasons. Deterministic eligibility/limits precede ranking. Collapse duplicate underlying/sector exposures across sleeves.

B4. Replay frozen datasets with actual tick/lot rounding, realistic costs, slippage, gaps, nonfills and partial-fill assumptions. Report basket plus each sleeve and basket-minus-each-sleeve; compare current policy at matched risk. Use time-separated train/validation/test periods and record all trials. Freeze the winning candidate before forward shadow evaluation.

Acceptance: no lookahead; no fills at a future bar extreme; no forced trade to meet activity quota; empty/partial data explained; declined candidates retained; opportunity frequency improves only if net portfolio evidence also supports it. Keep zero live activation as the default for new sleeves.

## E — Entry, exit and allocation intelligence

E1. Wire existing `exit_quality.py` and `strategy_health.py` into outcome collection/reporting, with tests proving scheduled consumption. Their existence as pure functions is insufficient. Repeated evaluation of the same outcomes is not fresh statistical evidence.

E2. Compare immediate, bounded pullback and confirmation entries using the same candidate set; include nonfills/delay. Compare existing exits with volatility trail, thesis invalidation and bounded time exit. Retain protective order controls. MFE is a diagnostic upper bound, not attainable profit.

E3. Calibrate net outcome estimates from time-separated results; start with conservative bins/shrinkage before complex models. Extend `portfolio.py` and risk sizing to compare feasible opportunities across sleeves with shared capital, pending-order reserves and correlated exposure. Recalculate costs after downsizing. Allow no affordable trade without hiding inactivity diagnostics.

E4. Persist health/drift state and bounded risk responses through existing control ownership. Entry suspension continues managing exits. No autonomous re-promotion, leverage increase or parameter rewriting based on a few wins/losses.

Acceptance: incremental held-out improvement after costs at matched risk; explicit uncertainty; deterministic fallback when models are absent; robust gaps/partial exits; no accounting leakage between training and evaluation. If a challenger fails, record the rejection and continue the champion—do not silently keep tuning against the same final test set.

## Release order, evidence and completion contract

| Order | Deliverable | May proceed now in Dev? | Live dependency |
|---|---|---|---|
| 1 | S1–S4 and integrated harness | Yes | Required before delivery release |
| 2, parallel | M activity/accounting and A optional-AI foundations | Yes | Safe integration tests and existing release workflow |
| 3 | I fixture adapter, lifecycle and deterministic cards | Yes | Approved real adapter/account and explicit partner canary |
| 4 | B shadow basket and E calibrated entry/exit experiments | Yes | Evidence, agreed risk limits, separate strategy promotion |
| 5 | Controlled release and owner-funded capital stages | Preparation only | GitHub promotion; owner authorization and verified live performance |

For every work package, deliver: implementation/migration, scheduler/API wiring, focused and integrated test evidence, example offline output, rollback behavior, and an updated completion table. Run broader tests once integration changes justify them. Do not repeatedly rerun unchanged suites instead of completing missing functionality.

Required end report must explicitly distinguish: **implemented and tested**, **shadow/research only**, **blocked by named external input**, and **not started**. Include exact commits and validation commands/counts. State separately whether Production changed, whether any live message/order occurred and whether any profit claim is supported by live reconciled evidence.

Immediate success is a safe, active, observable system that finds and evaluates opportunities reliably. Neither more trades nor passing tests establishes massive profit or sustainable withdrawals. Preserve the user's goal of proactive growth while making every claimed improvement measurable.
