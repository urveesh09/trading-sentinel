# Implementation handoff: Production improvements 2–5

Date: 2026-09-10. Scope: scheduling, accounting reconciliation, production dashboard integration and exact-policy research. Supplements 2026-09-10-dashboard-readiness-and-production-correction-plan.md and 2026-09-10-8115281-review.md. This is a specification, not an implementation claim.

## Objective and working agreement

Deliver a reliably active, measurable system capable of identifying and evaluating net-of-cost opportunities. Do not force trades, manufacture evidence, suppress warnings or imply that additional activity guarantees profit. Owner capital is currently about INR8000; future capital increases are aspirations, not authority to size trades now. Independent partner trades NIFTY/SENSEX intraday manually; no partner order placement or portfolio-feed requirement for generic advice.

Inspect current Dev before editing because another agent may be completing partner corrections. Work in C:/Users/Urveesh/Desktop/trading-sentinel on codex/production-correction-hedge-p0. Inspect Production logs/DB read-only; use consistent exported evidence for tests. Preserve existing untracked audit artifacts. Do not edit Production, send messages, place orders or change runtime permissions. Promotion is through GitHub. Avoid overlapping file edits with the partner-remediation agent; compare branch HEAD before each commit and never reset another agent's changes.

Build on existing modules and APIs; do not create a parallel analytics engine. Deliver independently reviewable commits and a completion matrix of implemented/tested/deployed/observed. Continue all independent implementation even when another stream awaits real observations.

## Partner delivery: prerequisites and tomorrow

The last verified Production state had no explicit profile or research artifacts/qualifications. Therefore no promise of actionable tips tomorrow is justified. Required: reviewed corrections deployed and identity verified; explicit saved default INTRADAY profile; fresh usable per-index inputs; genuine current-policy intraday qualification for the proposed structure/index; enabled and configured Telegram route; valid candidate passing profile, expiry, cost and delivery checks. Saving a profile or toggling delivery alone is insufficient.

Known profile preferences need not be asked again. Capital/risk ceilings are optional in the existing schema. If unset, cards must clearly give per-lot economics and manual sizing, not assumed suitability for a large account. Conditional protection requires its own exposure assumptions. Owner/partner must not be asked to invent research qualifications. An explicitly authorized TEST/no-advice message can verify routing separately, without suggesting trade readiness. No arbitrary collection-day count guarantees qualification.

## Stream 2: scheduling and resource contention

### S2.1 Evidence baseline

Inventory actual scheduler definitions, trigger periods, max_instances, coalescing, timeouts and market calendars for penny, FNO, research quotes, bootstrap, exits and advisory lifecycle. Read main.py, scheduler registration modules, kite_client.py, research_quote_collector.py and research_archive.py. Reconstruct September 10 market-session starts/completions/skips by job and boot epoch. Separate pre-open bootstrap, entry window, exit window and post-close. The post-15:30 penny scan age is expected inactivity, not a freeze.

Record compact structured events: run_id, job_id, boot_id, scheduled/start/end UTC, elapsed monotonic time, result, stage durations, cancellation/timeout and contention reason. Bound retention and output frequency. Distinguish scheduler rejected invocation, missing execution, in-flight work and completed no-op. Measure p50/p95/max provider, limiter, DB, archive and event-loop waits. Aggregate cache counters by daily/intraday path; DEBUG hits versus INFO misses cannot establish hit rate.

Acceptance: saved audit logs produce a reproducible report with explicit unavailable timing fields where old telemetry is insufficient. No fabricated start/end durations. New tests reconstruct skipped/late/non-market/restart states correctly.

### S2.2 Bounded fixes based on findings

Keep stateful trading scans single-instance. Isolate blocking filesystem/CPU work from the event loop; thread offloads do not themselves cancel underlying work, so bound the worker queue and retain locks until real work ends. Introduce bounded provider/request budgets with reserved capacity for exits and expiring advisory updates. Bulk research yields or records a gap under saturation. Reuse snapshots only when exchange/instrument/fields/time/freshness are compatible; never substitute LTP for executable depth.

Bound retries by deadline, avoid simultaneous bootstrap refresh storms and refresh unchanged masters at an appropriate measured cadence. Coalesce obsolete read-only work without deleting evidence of missed coverage. Do not relax quote age thresholds to compensate for a slow collector. Do not increase max_instances to silence warnings. Any interval change needs measured before/after behavior and an explanation of coverage lost or gained.

Acceptance tests: slow provider, held DB lock, archive saturation, provider throttling, cancellation and restart. Exit/lifecycle work must not inherit the deliberately injected bulk-research wait. No duplicate actions or runaway workers. Establish numeric latency/coverage budgets in the first telemetry commit based on current cadence and deadlines; report violations, not only averages. A measured controlled replay must show bounded queues and unchanged deterministic decisions.

### S2.3 Production acceptance, after merge

Read-only next-session timing report including exit-window performance, skip causes and provider freshness. A successful unit suite cannot certify real-session latency. If field measurements fail, leave deployed/observed status explicitly incomplete.

## Stream 3: explain and repair the five reconciliation warnings

### S3.1 Reproducible evidence pack

Use performance_analytics.py, broker_reconciliation.py, existing bankroll/position/outcome stores and the dashboard view model. Export a consistent cutoff snapshot with manifest/hash/schema and query bounds. September 10 12:22 values must not be directly compared with later EOD totals. Source keys: MOMENTUM, EDGE_LIVE, MOMENTUM_PAPER, PENNY_PAPER, EDGE_PAPER. Include unaffected FNO as a control.

For every source produce ledger close count/net, position count/net, difference, covered dates, gross/fees availability and allocation/funding adjustments. Match stable order/trade/close IDs. Model partial exits explicitly; one position and two ledger close events are not inherently a duplicate. Report unmatched, ambiguous, absent-cost and legacy records separately. Never silently infer a unique match from ticker/date alone.

Deliver five finding sheets: specific rows, amount/count delta, demonstrated cause, confidence, proposed correction and whether broker evidence is still needed. Explain cash P&L versus expectancy sample differences. Distinguish booked allocation, internal ledger cash, unrealized equity and actual broker statement balance. Profit factor and drawdown must disclose window, net/gross basis and cash-flow treatment.

### S3.2 Safe implementation

Add stable linkage/provenance going forward. Preserve immutable raw history; any genuine economic correction uses a documented compensating adjustment with unique idempotency key and evidence, not deletion/rewrite to make totals match. Reporting-only classification changes must not alter cash. Handle missing costs as unknown. A count-only mismatch due to partial exits should be classified accurately rather than hidden or presented as lost cash.

Implement drill-down API/UI: reconciled, explained difference, unresolved mismatch, insufficient source coverage, broker statement unavailable. Do not call an explained internal difference broker-reconciled. Reuse account-scoped statement importer; validate format/account/currency, fees and duplicate imports. Ask the owner for a supported broker statement only if required to establish real cash truth; do not request credentials or involve the partner.

Tests: split exits, duplicate event, fee-only event, deposits/withdrawals, missing costs, different time windows, cross-source misclassification, ambiguous matches, repeated imports and idempotent adjustments. Acceptance: every warning has a reproducible explanation; unresolved differences remain visible with quantified uncertainty. No automatic economic repair based on inference.

## Stream 4: connect real Production evidence to the dashboard

### S4.1 Coverage contract and existing sources

Inventory Dashboard.jsx hooks and corresponding routes. Map each card to producer/table/account/mode/policy/window. Add a shared coverage response with source_kind, configured/enabled, attempted_at, last_success_at, observed_at, receipt_at, current_age, state/reason, counts and policy/run identity. Null is unknown, never automatically zero. Distinguish timestamp age from market-calendar eligibility.

Expose existing momentum/penny/FNO shadow tables separately from proactive synthetic results. Adapt real strategy events into the existing proactive activity contract where semantics agree, with namespaced stable IDs and deduplication. Historical backfill needs provenance and bounded scope; do not backdate receipt times or invent missing stages. Unique opportunities, repeated evaluations, rejects, simulated fills and live outcomes must stay distinct.

Acceptance: populated legacy shadow plus unavailable proactive source displays both accurately. Empty, loading, disabled, API failure, unconfigured, stale and healthy-no-setup have different visible states. No card claims all-system inactivity from one empty table.

### S4.2 Production completed-bar producer

Extend proactive_market_data.py and configured workflow to consume actual retained completed-bar observations from existing Kite access. Keep SHADOW-only authority. Explicit production account/run identity replaces the dev-shadow default for this source. Preserve provider, token/master version, bar interval, open/close timestamps, received timestamp, timezone and corporate-action assumptions.

Reject current incomplete bars, future/replayed/out-of-order data and mismatched instruments. Detect gaps and correction revisions. Define reproducible behavior when a previously retained bar is corrected; don't mutate finished research evidence silently. Bound universe, refresh cadence and storage under Stream 2 budgets. Persist through restart and use a frozen policy/config manifest per run.

Acceptance: recorded real observations advance a shadow run chronologically; missing input explains inactivity; fixtures cannot masquerade as Production observations; API/dashboard shows actual run/source identity and evidence clocks. Integration tests include restart, duplicate packet, gaps and a changed bar.

### S4.3 User-facing simplification

Primary operational view: current source readiness, last completed work, unresolved accounting issues, manual advisory blockers and actual collection coverage. Put optional fixture experiments in a secondary research view; enabled broken Production features must remain prominent. Display per-index FNO collection requested/received/usable counts and gap reasons. Receipt count is not usable depth count.

Financial cards display date range and internal-versus-broker evidence. Profile form auto-manages revision and preserves unsaved edits during polling; version conflicts produce an explicit reload/merge choice. Give a plain-language next action for each blocker without creating a trade/send button. UI tests must interact with form while readiness changes, not merely compile JSX.

## Stream 5: strategy research that can improve outcomes

### S5.1 Data inventory and forensic cases

Inspect archives/manifests and dates, both exchanges' masters, bars, option bid/ask/depth/OI/volume, provider/receipt times, gaps and active-leg retention. Build a capability matrix: observed, modelled, unavailable. Preserve raw exports and avoid using the whole sample for tuning.

Reconstruct the five losing ORB trades and selected momentum fast-stop trades, plus matched rejected candidates: contemporaneous indicators, entry eligibility, contract/lot mapping, bid/ask assumptions, fees/slippage, stop/target, duplicate/re-entry behavior, exit clock and MFE/MAE where observable. Separate implementation defects, insufficient evidence and ordinary strategy losses. Do not assume a later recovery means the stop was wrong; compare full downside and alternatives on held-out observations.

### S5.2 Exact two-leg intraday replay

Use the deployed INTRADAY policy/version, true NIFTY/NSE and SENSEX/BSE contracts, current entry cutoff and management deadline from code. Freeze parameter/config/master/cost versions. Pin evaluated and active contracts through exit instead of collecting only rolling ATM. Include rejected and unfilled ideas to avoid survivorship bias.

Replay by information availability (receipt time), never future bars or retrospective knowledge. Entry uses the appropriate bid/ask sides and full-lot depth with synchronization/freshness limits. Model manual reaction delay, no-fill, partial/one-leg execution exposure and both-leg costs; neither instantaneous fill nor capped spread loss may be assumed for an incompletely formed spread. Sparse minute samples cannot prove tick-level fills/stops: report interval ambiguity and conservative bounds/no-fill where required. Model exit using executable observations; expiry payoff is not intraday realized P&L.

Tests: reversed legs, wrong exchange/lot/expiry, one-sided book, stale/unsynchronized quote, missing exit, delayed action, partial legs, same-bar stop and target, overnight carry rejection, future packet leakage, duplicate observations and restart determinism. Require reproducible output hashes under identical inputs.

### S5.3 Small predeclared comparison basket

Baseline: current exact ORB-derived intraday debit-spread policy. Candidate hypotheses: breakout/retest confirmation and trend-pullback continuation; include a no-trade baseline. These are experiments, not claims of profit. Do not multiply parameter variants until replay is credible. Log all variants tried, including failed ones.

Split chronologically by sessions, with holdout and walk-forward rules recorded before evaluation. Separate index/expiry/regime results. Report sample/session counts, unique opportunities, fill/no-fill, net expectancy, drawdown, loss tails, payoff ratio, cost drag, maximum adverse move, time-to-alert and outcome uncertainty. Multiple observations of one trade are not independent samples. Stress costs/slippage/manual delays and feed gaps. Do not annualize a few days into income promises.

### S5.4 Qualification and promotion artifact

Produce a machine-readable artifact plus plain-language report: immutable dataset hash, policy/config/code hash, dates, execution assumptions, excluded observations, all variants, validation split, metrics and limitations. Qualification acceptance criteria must be declared before evaluating the holdout, including evidence coverage, minimum independent sessions/opportunities, uncertainty and risk constraints. There is no defensible universal sample count to invent for every strategy; insufficient evidence must stay insufficient.

Register only genuine reviewed qualifying artifacts through the existing mechanism; separate research report creation from permission to qualify. No AI-created history, self-approval or automatic delivery enablement. A failed strategy result is a valid completed research deliverable, not a reason to relax the gate. Preserve future data collection and prepare next hypotheses when evidence fails.

## Integration and milestone order

M1: baseline telemetry + five accounting evidence packs + data capability inventory (independent reads).
M2: measured contention fixes + accounting drill-down + coverage API.
M3: Production completed-bar adapter + legacy activity integration + real-data dashboard.
M4: deterministic exact-policy replay + active-leg retention + forensic report.
M5: frozen comparison/qualification reports as evidence becomes sufficient; retain an explicit pending-live-observation state if not.

Run focused regression tests for each change, scheduler/API contract checks where affected, dashboard interaction tests/build, and container-compatible gateway tests if native DB paths change. Do not silently count local native-binding failures as a pass. Integrated offline acceptance: slow feed -> explicit stale state -> no unauthorized entry -> active management remains isolated -> restart -> preserved evidence -> consistent report. No external order/message is needed for this test.

## Required final implementation report

For each milestone list commit, changed behavior, tests, before/after evidence, migration/backfill implications, Production activation steps, rollback constraints and remaining dependencies. Link five reconciliation sheets, scheduling report, coverage map and research artifact manifest. Separate completed code from deployed capability and observed performance. Keep existing documents intact; append a new dated implementation record.

User input only where genuinely needed: optional advisory ceilings, broker statement/account scope for real reconciliation, or a risk/promotion decision. Do not block telemetry, diagnostics, UI integration or replay implementation while waiting for those. No promise of profit, daily trade quota, or tomorrow's tips is an acceptance criterion.
