# September 10: dashboard explanation and implementation plan

## Assessment and scope

Production audit, supplied midday dashboard, Production source and read-only running /data/cache.db and /data/research were inspected. These observations have different timestamps: do not reconcile the 12:22 dashboard directly against the 16:14 day-close report. No Production changes, orders or messages were made. This is a Dev implementation handoff, not a claim of completed fixes.

The release is present, but deployment is not product completion. Several panels expose separate research systems whose producers are unconfigured. The largest product gap is failure to turn unavailable states into clear, actionable readiness information. The largest operational concern is in-session scheduling/resource contention. The largest financial evidence concern is unresolved ledger/position reconciliation and persistently negative reported performance.

## Why the dashboard is blank

| Panel | Actual meaning / evidence | Required action |
|---|---|---|
| Why we traded / all modes zero | Reads proactive events/opportunities; not the per-strategy momentum/penny/FNO shadow tables. Those tables can be busy while this panel is empty. | Bridge existing production strategy events with provenance, or display separate coverage explicitly. Zero cannot imply no system activity. |
| Five-session dev-shadow | Running DB records UNAVAILABLE / FIXTURE_SOURCE_UNCONFIGURED. Source is a Dev fixture workflow, not a connected market feed. | Implement a production completed-bar source; show source-unconfigured as primary status. Do not populate Production with demo fixtures to make the panel green. |
| Completed bars | This card reports its own recorded completed-bar provider, not general Kite connectivity. | Connect validated completed-bar observations to the production shadow workflow. |
| Synthetic positions | Dedicated proactive simulator has no source/run/outcomes. Legacy shadow trades do not belong in this card. | Keep separate and explain prerequisite; show actual legacy shadow activity elsewhere. |
| Broker statement | ACCOUNT_NOT_CONFIGURED comes from missing BROKER_RECONCILIATION_ACCOUNT_ID; this feature is imported-statement evidence. | Configure the owner's explicit account scope and import a real supported statement. Kite login alone does not populate it. |
| Partner hedge review | Portfolio hedge-review evidence, not the independent manual advisory product. Portfolio feature was intentionally suppressed. | Replace primary partner dashboard with NIFTY/SENSEX manual advisory readiness/cards; keep portfolio features secondary. |
| Partner advice | Actual profile table is empty. Logs delivery_enabled=True, unavailable=2. Code increments unavailable on scan/snapshot/expiry problems or exceptions; exact reason is not present in summary. | Diagnose per-index input failures AND save explicit profile AND produce genuine qualifications. A profile alone will not repair scan inputs. |
| Delivery recovery zero | No unresolved deliveries; does not establish that any useful message was sent. | Show last acknowledged advice separately from backlog. |
| Optional AI disabled | Annotation feature is deliberately disabled, separate from the older agent and deterministic scanners. | Optional later activation with budget/outage controls; not a prerequisite for market data or advice. |
| Reconciliation warnings | Aggregate ledger close count/P&L differs from position close observations. | Build event-level reconciliation; do not erase warnings or assume broker balances match internal ledgers. |

## Corrections to the supplied audit

1. Penny last scan at 15:30 followed by silence at 16:14 is expected market-close gating: main.run_penny_scanner_once explicitly returns outside 09:15–15:30. This is not evidence of a 46-minute trading-session freeze. In-session max-instance skips remain real evidence requiring duration analysis.
2. Do not increase concurrent scanner instances or lengthen intervals blindly. Max-instance rejection is not a queued second scan. Re-entrant trading scans could duplicate work/orders; slower cadence could hide missed opportunities.
3. unavailable=2 is not two excluded setups or healthy no-setup. Code distinguishes healthy_no_setup, which was zero. Diagnose NIFTY/SENSEX data failures individually.
4. Manual directional advisory does not require partner portfolio ingestion. hedge_enabled=False is separate from manual delivery_enabled=True. Do not re-enable unwanted portfolio summaries to repair this product.
5. A paper simulation cannot validate broker order acceptance. order_execution_readiness uses UNVERIFIED/AUTHORIZED/BLOCKED, not the audit's VERIFIED label. Do not place an unnecessary order to make health green. Read-only checks establish connectivity; actual authorized trading establishes order evidence when it legitimately occurs.
6. Cache hit-rate claim remains invalid: INFO misses and DEBUG hits cannot yield a hit percentage. Daily data_fetch must not be confused with intraday cache behavior.
7. 56k evaluation rows are repeated observations, not unique opportunities, qualifications, or profits. Existing per-strategy shadow tables are separate from new proactive workflow tables. Do not attribute all rows or their creation to PR #86 without historical comparison.
8. The report acknowledges wrong query columns and estimated momentum rejection counts. Re-run those using actual schema and IST session bounds before strategy conclusions. 51/63 no_or_break does not prove a broken opening-range strategy.
9. Zero non-2xx contradicts listed 302/304; say no observed 4xx/5xx where supported. No errors does not prove end-to-end readiness. Release verification establishes identity, not Kite/scheduler functionality.

## What actually is working

Production /data/research contains preserved operational FNO export, NFO/BFO contract masters, quote observations and collection journals. At inspection there were 519 journal records, including 341 without a top-level skip reason and 178 outside-session records. The last in-session record requested and received 90 tokens (45 per index) with no listed gaps. This proves collection activity for that observation, not all-session completeness or executable quality of every quote. Qualification still needs synchronized, fresh, usable books and realistic replay.

The existing paper/strategy systems and new release metadata are active. Their activity is poorly represented by the new dashboard, whose newer research sections remain largely unconfigured.

## Workstream 1 — P0 operational latency diagnosis and bounded correction

Capture market-session job start/end, queue/limiter wait, provider request duration, DB lock/write duration, archive duration and event-loop lag. Separate bootstrap/pre-open load from 09:15–15:30 operation. Report p50/p95/max duration and actual missed eligible runs for research, penny, FNO and bootstrap. Preserve enough logs to reproduce the 87 reported warnings and identify concurrent stages.

Investigate synchronous archive work and shared write lease contention; move blocking I/O off the event loop where demonstrated, cap provider waits and keep a bounded request budget. Reuse compatible quote snapshots with explicit freshness requirements rather than fetching identical data independently. Prioritize exit monitoring and expiring advisory lifecycle over bulk research. Preserve max_instances=1 for stateful scans; bounded concurrency belongs only in safe independent read-only fetches.

Acceptance: injected slow provider/archive cannot hang exit/lifecycle work; no duplicate scan actions; market-time gap and stale-input reasons are explicit; measured timing justifies any cadence changes. Test shutdown/cancellation and timeout paths. Show MARKET_CLOSED after close instead of an alarming age alone.

## Workstream 2 — P0 manual partner readiness diagnosis

Extend each index's scan summary with stage, reason code, observed timestamp, source, current expiry resolution and sanitized error category. Persist latest readiness independently of candidate generation so failures remain visible even with no ideas. Trace scan_underlying error/snap, instrument availability, resolve_advisory_expiry and quote refresh. Compare the successfully collecting research path against this advisory path; collector success is not evidence that their differing input requirements are met.

Expose per-index readiness on dashboard: source ready -> profile saved -> policy qualified -> candidate valid -> delivery enabled -> last acknowledged message. Show exact blockers. Default primary view is independent INTRADAY NIFTY/SENSEX advisory, not portfolio review.

Provide explicit profile setup using the existing authenticated API and INTRADAY policy. Required economic limits must be supplied/approved; do not invent risk tolerance from the partner's large capital. Partner broker credentials, personal strategy and portfolio feed are not required for generic directional advice. Conditional protection still requires declared exposure assumptions. Keep genuine qualification gates.

Acceptance: missing scan, missing expiry, missing profile and missing qualification each produce distinct actionable states. Healthy-no-setup is emitted only after valid inputs were evaluated. A permitted TEST/no-advice diagnostic can test routing independently; no automatic test messages.

## Workstream 3 — P1 reconcile accounting before interpreting performance

Export read-consistent ledger/position evidence per source with immutable IDs, dates, gross, fees, net, partial-close quantities and funding/adjustment events. Match by stable trade/close identity; do not compare one position with several partial-close events as equivalent counts. Explain each of the five displayed warnings with amount/count deltas and reason (costs, partial closes, legacy coverage, source mapping or actual duplicate/missing record).

The supplied live aggregate is internal allocated capital 8000 minus ledger P&L 262.59, not automatically current broker equity. Historical cumulative paper loss 47262.47 is not today's loss. Show date window and accounting basis beside values. Explain why momentum paper cash P&L / closed trades differs from expectancy if adjustment events or differing samples cause it. Do not rewrite historical cash to make reports agree; any proven repair must be auditable and idempotent.

Acceptance: evidence-backed mismatch classifications; separate funding and P&L; supported statement import with account binding and duplicate rejection; internal-ledger versus broker-reconciled status visible. Unavailable costs/risk remain unknown rather than zero.

## Workstream 4 — P1 connect Production evidence to a usable dashboard

Create a coverage response listing each producer, data source, account, mode, policy, reporting interval, last attempt, last success, reason and counts. Connect existing strategy telemetry to the activity display through adapters with stable IDs and deduplication. Distinguish unique candidates from repeated evaluations and completed scans from unavailable ticks.

Implement a production completed-bar recorder using existing Kite access, instrument/timezone mapping and completed-bar cutoff. Preserve provenance, bar-close time, receipt time, gaps and adjustment assumptions. Connect it to the shadow research workflow without broker execution authority. Use an explicit Production research identity, not dev-shadow. Existing fixture/replay data remain separately labelled.

UI states: not configured, unavailable, stale, active/no setup, active/with results, disabled and API error. Every blank primary panel should explain its source and next action. Hide optional Dev fixtures in a secondary research view without concealing faults in enabled Production features. Give FNO quote collection its own per-index readiness/coverage card.

Acceptance: integration test with both populated legacy shadow and unavailable proactive data shows both accurately; no mode mixing; one recorded session produces chronological, attributable research results; visible source timestamps and filters.

## Workstream 5 — P1 strategy quality, using real retained evidence

Produce the five-ORB-trade forensic case pack already planned: contemporaneous bars/options, entry/stop timing, lot sizes, costs, duplicate/re-entry checks, MFE/MAE and ordinary-loss versus implementation-defect classification. Do the same for the repeated momentum fast-stop exits. Do not tune solely to these losing examples or tighten stops assuming it improves expectancy.

Implement exact INTRADAY two-leg spread replay for NIFTY and SENSEX, active-leg collection through exit, chronological quote matching, cost/depth/no-fill modeling, deadline exits and missing-data rejection. Compare a small predeclared strategy basket against a baseline with held-out sessions; report net expectancy, drawdown, cost sensitivity, no-fills and sample limitations separately by index and policy. Only genuine reviewed artifacts qualify partner messages.

Do not increase capital based on scan volume or one winning spread. The current negative reported expectancy makes reconciliation and validated improvements more valuable than forcing additional trades. Activity should increase by repairing latency/data gaps and expanding tested opportunity coverage, not relaxing safeguards to achieve a quota.

## Delivery order and handoff evidence

1. Correct misleading operational states and add per-index advisory failure evidence.
2. Measure and repair demonstrated market-session contention; publish before/after timings.
3. Resolve accounting deltas and make production/dashboard coverage explicit.
4. Connect completed bars and exact-policy replay while forward quote collection continues.
5. Save explicit partner profile, complete genuine qualifications and then evaluate useful delivery outcomes.
6. Optional AI annotation and advanced basket expansion follow reliable deterministic evidence.

Each milestone needs code/tests, a reproducible fixture for its failure, a documented Production smoke check and evidence of the resulting status. Do not claim all systems smart/ready because containers run. Preserve today's audit as evidence; use this document to correct its unsupported interpretations. Implementation happens in Dev and promotion through GitHub only.
