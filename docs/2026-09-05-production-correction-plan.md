# Production run correction plan — 5 September 2026

Scope: investigation and implementation plan, based on the 4 September Production audit and read-only verification on 5 September. No application code, Production files, runtime configuration, database rows, services, or messages were changed during this investigation. This document is saved in Dev.

## User priority update — hedging first

Revised on 5 September at the user's request: **getting useful, trustworthy hedge messages to the partner is the highest delivery priority.** Keep legacy directional FNO tips and raw analytics suppressed by default. Restoring those messages is optional backlog work and is not the remedy for hedge silence.

The first release should establish a complete path from fresh hedge inputs through evaluation to an acknowledged partner message. Deliver portfolio-specific protection reviews when reconciled exposure is available, and clearly labelled VIX/risk-context updates when only market inputs are available. A status update explains missing inputs; it does not count as delivery of actionable hedge advice.

## 1. Findings that determine the plan

### Partner silence: confirmed upstream suppression and missing replacement inputs

The live Production database contains 77 legacy `partner_messages` rows. The last recorded message is the delivered EOD message at **2026-09-01 15:40:00 IST**. On September 1 it recorded three directional signal messages, a morning brief, an EOD wrap, and analytics events. There are no recorded partner messages from September 2 onward.

Production currently has **zero rows** in each of:

- `partner_positions`
- `partner_position_reconciliations`
- `partner_vix_history`
- `partner_hedge_messages`
- `partner_hedge_gate_evidence`

The running container's effective settings confirm that the partner bot, hedge master switch, Phase 2, Phase 3, and all four legacy suppression switches are true. Both partner credentials are present; this establishes configuration presence, not current Telegram delivery capability.

Commit `443c74b`, dated **September 2, 07:42 IST**, introduced the hedge advisory and suppression behavior. That timing matches the reported start of silence. The latest code still returns early from directional scans and legacy briefs/wraps when hedging is enabled; analytics events are selectively suppressed. Regime/risk cautions remain possible, so this is not literally a blanket transport disablement.

The September 4 log contains **23 Phase-1, 12 Phase-2 and 12 Phase-3 in-session state records**, all with zero reconciled positions. None of those three jobs logged a failure. Phase 1's independent VIX path also returns without a message when its input table is empty. Repository inspection found position/reconciliation and VIX intake APIs, but no scheduled producer populating those inputs.

**Diagnosis:** the legacy service was retired before the replacement had operational input feeds. Successful empty scheduler runs concealed a user-visible service regression. The audit's description of intentional suppression is technically correct but insufficient as a service-health verdict.

The operator's FNO paper activity and successful operator Telegram delivery do not establish partner delivery: `partner_bot.py` uses a separate bot and destination, directly; the operator gateway notify route is a different channel. No test message was sent during this investigation. A simultaneous Telegram problem remains untested, but is not needed to explain the observed silence.

### Audit qualifications

1. **Heartbeat discrepancy reconciled:** the 1,214-second raw gap is from 07:19:18 to 07:39:32 IST. The heartbeat count is `1` on both ends, alongside startup sequences. It is a premarket discontinuity across startup epochs. Subsequent captured heartbeat intervals top out at 60 seconds. A market-hours maximum of 60 seconds is consistent with this evidence. The exact reason for the earlier startup discontinuity remains unverified; it is not evidence of a 20-minute market-hours freeze.
2. **EDGE coverage label is ambiguous:** `compute_features_for_day()` returns `None` for fewer than 21 bars, price outside ₹5–₹55, or nonpositive median volume. All become `insufficient_features`. Therefore the 484/500 count cannot be treated as 484 history failures. Preserve the price rule while separating these reasons.
3. **Penny skip count needs classification:** 6,012/10,107 histories were skipped (59.5%). The code combines fetch failure, empty/short history and computation failure. It does not prove that every skipped symbol should be in the tradable universe.
4. **Outcome reporting has a coverage gap, not demonstrated missing cash:** ₹13.10 of Penny closes exists in the ledger and execution events but not in the six-row outcome query. Do not book that money again.
5. **Returns do not justify immediate tuning:** the +₹2,465.82 combined paper result includes a +₹3,317.82 carryover EDGE close. Excluding that close gives **−₹852.00**. This is a reporting decomposition, not evidence sufficient to optimize strategy parameters.

### Deployment baseline

Production HEAD: `89926fb`; Dev HEAD: `a569444`. Their tracked trees are identical; Production has merge history on top. Dev was clean at inspection. Production's pre-existing untracked `migration/` directory was left alone. Docker's compose working-directory label points to the Production folder. Seven relevant running-container files were SHA-256 matched to Production: configuration, partner orchestration, hedge advisory/readiness, scheduler setup, Penny universe and main entrypoint. No pending Dev correction exists for these findings.

## 2. Recommended work packages

Priority P0 is the hedge delivery critical path. P1 covers remaining operational correctness/coverage, and P2 reporting and optional enhancements. Live-entry capital readiness remains a prerequisite for live-entry availability, but is not a dependency for advisory-only hedge delivery. These are planned changes, not changes already applied.

### A. P0 — Define and deliver the partner's hedge message service

**Files:** `python-engine/config.py`, `partner_orchestrator.py`, `partner_bot.py`, `hedge_advisory.py`, `hedge_formatters.py`, `docs/HEDGE_PIPELINE.md`.

Keep legacy ORB/directional tips, raw analytics and legacy briefs/wraps suppressed. Introduce hedge-specific morning and end-of-day summaries independently of those legacy jobs. The morning summary shows current exposure, existing protection, data freshness and any eligible review; the EOD summary explains reviewed protection, unresolved exposure and unavailable inputs. Use the existing trading-day/session conventions. Do not automatically restore directional tips when a hedge input becomes unavailable.

Prioritize messages in this order:

1. Material deterioration in an existing hedge, stale inputs affecting protection assessment, or a significant change in reconciled exposure. Clearly separate an inability to assess risk from a confirmed risk change.
2. Eligible Phase-1 protective-put and futures-sizing reviews grounded in actual partner exposure. Show the exposure being protected, actual contracts/expiry, units/lots, quote timestamp, premium or relevant margin context where available, coverage and residual exposure. Identify the message as advisory, not an executed order.
3. Validated adjustments and advanced strategies that address the portfolio's demonstrated risk. Standalone premium-generation ideas are secondary and must not be labelled protection merely because they use options.
4. Hedge-specific daily summaries and sourced VIX/risk-context updates. Without portfolio inputs, avoid personalized quantities and explain that portfolio-specific advice is unavailable.

Add a partner service state showing last input refresh, last evaluation, exact no-advice reason, last candidate, last attempted send and last acknowledged delivery. Distinguish `NO_PORTFOLIO_INPUT`, verified empty portfolio, stale data and valid `NO_HEDGE_NEEDED`. Missing-input notices should identify the setup action required, be deduplicated and appear on state change plus a concise daily summary, not every scan.

Use a bounded delivery queue so important protection changes are delivered ahead of routine digests; coalesce superseded updates and revalidate expiring advice before sending. This priority applies to partner notifications and must not delay Sentinel's protective order execution.

**Acceptance:** replay the September 2 hedge-on/empty-input condition: legacy tips stay suppressed, hedge setup status is visible, and no portfolio sizing is fabricated. With fresh eligible inputs, an actual hedge review reaches the mocked partner destination and records an acknowledgement. With no eligible hedge, report the precise reason. Verify priority ordering, superseded messages, closed-market behavior and absent credentials. A heartbeat or VIX-only notice does not satisfy the portfolio-hedge delivery acceptance test.

### B. P0 — Verify hedge delivery end to end

**Files:** `partner_bot.py`, `hedge_advisory.py`, hedge delivery tests; shared delivery support if required.

Retain and verify the existing hedge atomic claim/delivery mechanism: bounded retries, successful-delivery deduplication, expired claim recovery and explicit failure states. Exercise the full hedge evaluation → formatting → partner sender → acknowledgement → persistent delivery-record path. Preserve partner/operator destination isolation.

Record Telegram acknowledgement/message identifiers where available. Treat a timeout after possible remote acceptance as ambiguous: do not promise exactly-once delivery or retry without bounds. Expired hedge quotes must be reevaluated before retrying; critical data-loss status can still be reported. Redact credentials from diagnostics.

**Acceptance:** mocked success, 429, malformed response, network timeout, permanent rejection, restart and concurrent hedge sends. Failed sends remain recoverable; confirmed messages do not repeat; stale proposals are not delivered as current. Include a concrete partner hedge-message canary as the final deployment verification, with the destination/content reviewed and explicit send authorization before transmission. This plan revision does not send messages.

The legacy `_seen()`/`_throttled()` failed-delivery issue remains documented, but fixing that inactive path is P2 optional work if legacy messages are later requested. It must not delay hedge delivery.

### C. P0 — Supply the hedge service with genuine, fresh inputs

**Files:** `hedge_analytics.py`, `hedge_advisory.py`, `routes_hedge.py`, `scheduler_setup.py`; new input adapter module and tests.

The first implementation decision is the partner's actual position source: partner broker feed versus an explicit supported manual intake workflow. Treat this input adapter as the first implementation dependency for personalized hedge reviews; build the VIX feed and delivery verification alongside it. Do not substitute Sentinel paper positions or assume the operator account belongs to the partner. General FNO trade ideas should remain separate from portfolio-specific hedges.

Build an idempotent import/reconciliation path for identity, underlying, units, side, position status, current mark, timestamps and options Greeks. Refresh marks and reconciliation before the configured five-minute freshness limit expires; a one-time import will become ineligible. Reconcile closes, quantity changes and partial positions. Preserve exchange-unit/lot validation and broker-backed deliverable verification for covered calls.

Add a timestamped India-VIX producer using the application's authenticated market-data integration, with source, actual observation time, trading-day freshness and bounded retention. Its refresh must satisfy the 15-minute freshness window. Do not mark a cached value fresh by changing its timestamp.

Add counters for missing portfolio, verified empty portfolio, stale marks, missing Greeks, unavailable expiry, stale chain, wide spread, inadequate liquidity, insufficient IV history and below-one-lot sizing. Retain all those guards; do not fabricate advice to increase message volume.

**Acceptance:** synthetic reconciled portfolio produces expected eligible advice; missing/stale/invalid inputs fail with exact reasons; imports and retries do not duplicate positions; closing an exposure removes it from advice. Verify VIX-only behavior independently of positions. The partner's source/account mapping is required before implementing its actual feed, but does not block packages A/B.

### D. P0 for hedge rollout — Align readiness, enabled phases and documentation

**Files:** `hedge_readiness.py`, `hedge_advisory.py`, `config.py`, `routes_hedge.py`, `docs/HEDGE_PIPELINE.md`.

Readiness currently provides diagnostics; the scheduled Phase-2/3 jobs do not consult `assess_hedge_readiness()`. Both phase defaults are true despite zero recorded gate evidence. Documentation also says Phase 2 ships off in one section and lists it as on elsewhere. Missing readiness evidence is therefore not the demonstrated cause of today's silence, but a separate rollout gap.

Define separate configured, input-ready, validated and sending states. Enforce the existing readiness contract before advanced partner-facing sends, with a shadow evaluation mode that can generate review evidence while sends remain gated. Avoid a circular rule that requires delivered partner samples before any samples can be reviewed.

Use genuine evidence for the existing five Phase-2 staging days, seven Phase-3 staging days, live-chain checks and per-kind sample reviews. Make dormant strategies and strategy-specific blockers visible; do not delay eligible Phase-1 protection reviews or hedge-status messages while advanced phases gather validation evidence. Resolve documentation/configuration contradictions in the same PR.

**Acceptance:** enabled plus missing evidence reports blocked advanced delivery; shadow samples remain reviewable; complete fresh evidence allows only the intended kinds; stale evidence cannot silently pass. Earnings/calendar requirements apply to relevant strategies. No automatic trade execution is introduced.

### E. Separate live-entry prerequisite — Extend execution readiness to capital

**Files:** `python-engine/order_execution_readiness.py` and its consumers; `node-gateway/server/services/executor.js`, `routes/orders.js` and relevant execution handlers.

The audit records ₹567.86 required and ₹0 available for RPOWER. Extend the existing execution-readiness design rather than adding a competing state machine. Separate session validity, broker order permission, usable margin and outcome reconciliation. A successful read-only account request is not proof that the broker will accept an order.

Add short-lived preflight margin evidence for new live entries and a structured `INSUFFICIENT_MARGIN` outcome. Cover dashboard and Telegram execution paths. Preserve broker rejection handling because capital can change after preflight. Do not retry a rejected entry indefinitely or let entry restrictions disable protective exits. Funding is an operator decision, not a code correction.

**Acceptance:** zero/stale/unavailable margin prevents new entry submission; valid evidence permits normal submission; rejection after a successful check is correctly recorded; unknown order outcome is reconciled before resubmission; exits remain available. Validate with broker mocks, not a real-money test order.

### F. P1 — Fix scheduler overruns without slowing protection blindly

**Files:** `scheduler_setup.py`, `fno_orchestrator.py`, shared Kite client/limiter, Penny scanner orchestration.

FNO had 16 overruns/skips at a 90-second interval; Penny had 24 skips. Several sampled FNO overruns finish at 10:32, 10:47 and 11:02 after approximately 93 seconds, consistent with quarter-hour workload contention. That is a hypothesis to measure, not a proven root cause.

Instrument stage durations: limiter queue wait, historical fetch, chain fetch, DB access, entry/exit evaluation and notify. Profile overlapping Momentum/Penny/partner work. Share only fresh compatible snapshots, avoid redundant per-bar history requests, and prioritize position management over candidate scans. Keep `max_instances=1` and idempotency guarantees.

A 120-second FNO scan interval is a candidate mitigation only after confirming its effect on exits, time stops and the hard-flat window. Prefer isolating exit monitoring from slower entry analytics where measurements justify it. Do not merely raise concurrency or increase the broker request rate. Review Penny's interval against measured runtime in the same workload replay.

**Acceptance:** replay slow broker/DB work and concurrent scanner load; no overlapping orders or missed hard-flat actions; chosen cadence has measured headroom (proposed p95 below 80% of interval), and skips are classified. Confirm at least two representative Production sessions after promotion; report actual skip rates and exit latency.

### G. P1 — Repair data provenance, coverage and bootstrap cost

**Files:** `penny_universe.py`, `universe.py`, `daily_bootstrap.py`, bootstrap registration, data manifests and deployment tooling.

Classify each history skip as unresolved symbol, unsupported series, empty response, short history, stale cache, rate limit, fetch failure or computation failure. Define the expected eligible population from instrument identity/segment/series before setting coverage goals. Do not target 100% of 10,107 raw symbols blindly.

Validate and version the company-data input and Nifty 500 file. Include source date, schema, checksum, expected counts and fallback status. Ship a reviewed deployment/migration procedure through GitHub to validate and provision named-volume data atomically with backup/rollback. Copying a new image alone does not guarantee that an existing volume is repaired. Do not manually copy files into Production during development.

Resolve HFCL/JBCHEPHARM against the instrument master and aliases; do not delete them solely because this cache reports them unknown. Reuse valid cached history and fetch required deltas; preserve enough historical depth for metrics. Separate task failure from partial success in bootstrap readiness.

**Acceptance:** skip totals balance; controlled invalid/short/new-listing samples have distinct reasons; every eligible symbol has current sufficient data or an explicit exception. Proposed initial target: at least 95% usable coverage of the validated eligible population, with stricter requirements before an individual symbol can trade. Benchmark bootstrap improvement from the 3,395-second baseline while respecting the limiter. Surface degraded files before the first dependent scan.

### H. P1 — Make EDGE rejection reasons truthful

**Files:** `penny_edge_engine.py`, EDGE scanner/logging callers, `tests/test_penny_edge_engine.py`.

Replace the coarse feature failure with separate `insufficient_history`, `price_out_of_range`, `invalid_volume`, invalid/stale data and `no_setup` reasons. Preserve the ₹5–₹55 price band and existing setup logic. Re-evaluate the September 4 universe from retained input snapshots where available; otherwise state that retrospective reason counts cannot be recovered exactly.

**Acceptance:** known outside-band stock is an eligibility rejection, not a missing-data incident; sufficient clean eligible history computes features; reason counts sum to the evaluated universe. Only consider history repair or universe redesign after this decomposition.

### I. P2 — Correct liveness and financial reporting semantics

**Files:** `ops_metrics.py`, `scheduler_tick.py`, `main.py`, `tools/runtime_audit.py`, report/outcome adapters and tests.

Report process heartbeat, scheduler heartbeat and per-job progress separately. Segment raw logs by boot/run ID and record coverage windows. Show premarket discontinuities separately from in-session gaps; a healthy heartbeat alone does not prove a scan is progressing. The current SQL uses `MAX` to preserve gap maxima, so the audit note suggesting a simple last-writer-wins maximum is not supported by this code.

For finance reports, keep `bankroll_ledger` authoritative. Add a unified read model across outcome sources, or an idempotent Penny outcome adapter if the table is intended to be universal. Reconciliation must prevent duplicate ledger postings. Expose paper/live, division, entry day, exit day and carryover status. Normalize query boundaries using each column's actual timezone/storage convention, including date-only legacy records.

**Acceptance:** the September 4 fixture reproduces ₹2,465.82 ledger P&L, explains the ₹13.10 outcome-table difference, separates ₹3,317.82 carryover and −₹852.00 remainder, and reports the 07:19–07:39 gap outside market hours. Include restart, overlapping capture and UTC/IST boundary cases.

### J. P1/P2 — Improve FNO notification completeness and strategy review

**Files:** `scheduler_setup.py`, `fno_orchestrator.py`, FNO notification tests, analytics/reporting tools.

An additional code gap: immediate FNO notification checks only `entries`/`exits`; its formatter also omits debit-spread opens/closes. DR-only activity can therefore receive no immediate notification through this path. Include structured DR events and their paper/live identity. Check gateway HTTP/application acknowledgement; the current POST does not call `raise_for_status()`. This concerns operator reporting and is separate from the partner-suppression root cause.

Once operational correctness is restored, review multiple sessions by strategy, rejection reason, entry time, regime, costs and exit reason. Examine repeated time-stop losses and signal freshness with a declared sample window and out-of-sample validation. Low acceptance alone is not a defect. Do not relax gates, shorten stops or expand risk solely to improve September 4's result.

**Acceptance:** DR-only open/close emits the intended report; failed acknowledgements are visible/recoverable; historical performance distinguishes carryover from new signals and paper from live. Parameter changes require their own evidence and PR.

## 3. Execution and promotion sequence

| Order | Proposed PR scope | Dependency / completion gate |
|---|---|---|
| 1 | Hedge input intake, recurring reconciliation/marks and VIX feed (C), plus service states (A) | Actual partner source identified; eligible exposure stays fresh; VIX-only context is explicitly non-personalized |
| 2 | Phase-1 protection messages, hedge summaries and reliable delivery (A/B) | End-to-end eligible hedge fixture reaches partner transport and persists acknowledgement; legacy tips remain suppressed |
| 3 | Advanced hedge readiness and protection adjustments (D) | Shadow evidence and required staging complete; independently eligible Phase 1 continues |
| 4 | Hedge-related shared-resource timing work (F), only where needed for input freshness/delivery | Timeliness verified under scanner load; protective order execution remains prioritized |
| 5 | Remaining live readiness, data coverage, EDGE and operator FNO notification corrections (E/G/H/J and remaining F) | Existing operational acceptance gates; capital readiness required before live entries are considered available |
| 6 | Audit/P&L semantics, strategy review and optional legacy messaging repairs (I/J/B legacy follow-up) | September 4 fixture reconciles; no legacy reactivation without a requested preference change |

Steps 1–2 form one initial release milestone: **fresh portfolio input produces a valid Phase-1 hedge review with a recorded delivery outcome**. Do not ship an input-only change and declare hedge messaging restored. VIX context and setup status may be released earlier, but must be described as partial functionality. Steps 3–4 can progress alongside validation; unrelated audit remediation must not become a release dependency for this milestone.

Before personalized advice can go live, confirm the partner's portfolio source/account mapping and supported holdings. The current request establishes hedging as the content priority; it does not establish that Sentinel's account or paper book represents that portfolio. While that information is pending, complete the source-neutral intake contract, market-data producer, formatting, mocked delivery and shadow fixtures.

Work only in `C:\Users\Urveesh\Desktop\trading-sentinel`. Create a `codex/` branch at implementation time after rechecking local changes. Use separate reviewable commits/PRs, test in Dev, and promote through GitHub using the normal daily release process. Record deployed commit/image identity and effective non-secret flags. No direct Production source/configuration edits.

For each PR, run the relevant existing partner/hedge, readiness, scheduler, bootstrap, EDGE, ops and gateway test suites plus new regression cases. Broader integration checks are justified for scheduler/shared-client changes. This planning task did not run the application test suites or claim they pass.

Deployment validation should verify readiness before the first dependent market scan, observe actual partner send acknowledgements on the next eligible events, and reconcile end-of-session books and notifications. Roll back through GitHub/redeploy on lost hedge delivery coverage, stale or incorrectly sized hedge advice, repeated duplicate messages, impaired protective exits or new data corruption. Keep database migrations additive and backups available; never roll back by deleting live trading history.

Advanced-phase validation takes the existing required staging sessions; it should not delay eligible Phase-1 hedge delivery. Legacy directional messaging remains optional and suppressed by default. No wall-clock implementation estimate is asserted before selecting the partner data adapter and profiling contention.

## 4. Evidence and limitations

Primary audit: `C:\Users\Urveesh\AppData\Local\Temp\ts-perf-20260904\production_run_assessment_2026-09-04.md` (the supplied path's underscore-separated directories did not exist; this is the matching actual file).

Supporting archived evidence: `python_xl.log`, `SCHEMA_NOTES.md`, `db_audit.json`, `db_audit2.json`, gateway/agent captures in the same directory. September 5 verification used SQLite `mode=ro` with `PRAGMA query_only=ON`, selected effective non-secret settings, Docker deployment identity and relevant source hashes. Runtime database queries corroborate the message cutoff and empty hedge tables.

Detailed historical log review here focused on September 4; the September 2 onset is corroborated by retained message records, the user's report and commit timing, not a complete independent replay of September 2. The partner's actual Telegram inbox, current transport success, portfolio and preferred input source were not accessed. The 6,012 history skips and 484 EDGE coarse rejections remain unclassified at individual-symbol level. These are explicitly scheduled investigation steps, not asserted root causes.

At implementation time, preserve a sanitized durable evidence bundle with hashes outside Temp; Temp is not guaranteed long-term retention. Do not commit credentials, raw portfolio data or unredacted runtime logs.
