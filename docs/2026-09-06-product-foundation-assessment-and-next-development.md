# Product foundation assessment and next development assignment

Reviewed 6 September 2026. Baseline: `768741c`, Dev branch `codex/production-correction-hedge-p0`. Reviewed seven commits from `39ed947` through `768741c`, against `e03991a`.

## Assessment

There is useful progress: evidence tables and read APIs, a dashboard card, three proposal hypotheses, a small simulator, watchlist persistence, a funding ledger, fixture ingestion and optional AI initialization now exist. The reported remaining work is broadly honest.

However, these are **partial foundations, not completed product milestones**. The new opportunity writer, proposal builder, allocator/simulator and watchlist mutator have no application consumers outside tests in the searched Python tree. The dashboard can read the new tables, but scheduled scans do not populate them. The simulator and reporting defects below would make research/operational evidence misleading if connected unchanged.

Do not activate these strategies live or use their current simulated returns as proof of an edge. Continue product development, correcting the foundations while wiring an end-to-end shadow workflow. Do not respond to this review by completing only isolated fixes and stopping the product build.

The full scope remains `2026-09-06-proactive-intelligence-product-build-spec.md`. This document specifies the immediate correction/integration sequence and updates milestone status.

## Verification performed

- Selected Python run: **86 passed, 1 failed**, one existing Starlette warning. Included proactive/fixture tests, partner input/advisory/routes, scheduler closures and main surface characterization.
- Failure: `tests/test_main_surface_characterization.py::test_surface_matches_golden`. Four routes exceed the stored golden contract; the first difference is `/analytics/proactive-activity`. Review all intended additions, including earlier route changes, rather than attributing all four to the latest commit or blindly regenerating the fixture.
- Frontend `npm run build`: passed, 1,513 modules transformed. Existing Browserslist freshness warning. Compilation is not browser verification or proof that real evidence reaches the card.
- Ran deterministic offline probes using temporary SQLite storage. Script and output: `docs/review-2026-09-06-product-foundation/`.
- No full gateway suite, independent agent runtime suite, new live-run P&L assessment or browser UI interaction was performed in this review. Do not reuse older test counts as fresh validation.
- Application code was not changed in this review. Only this document and offline probes/results were added. No Production operation, broker order or Telegram send was performed.

## Current milestone status

| Product milestone | Current evidence | Status |
|---|---|---|
| P1 activity/profitability | Event/funding tables, two read APIs and dashboard count card. No production event producers, broker-linked outcomes, accounting waterfall or session-aware diagnostics. | PARTIAL; reporting defects present |
| P2 proactive watchlist/three sleeves | Pure proposal function and persisted state helper. No scheduled universe/watchlist consumer; tests do not individually prove all three sleeves. | PARTIAL |
| P3 allocation/simulation | Cash-based selection and single-bar simulator. No common portfolio reservation/position lifecycle. Simulator can violate cash/timing. | PARTIAL; not research-valid |
| P4 outcome learning/entry-exit comparison | No new implementation in the reviewed diff. | NOT_STARTED for this product build |
| P5 optional AI | Missing key no longer exits solely because AI is absent. News/review still occur synchronously; unavailable-policy blocking remains configurable. | PARTIAL |
| P6 partner lifecycle/cards | Creates known fixtures and closes absent rows. Reopening fails; row creation is outside accepted-snapshot transaction; cards/UI/corporate actions missing. | PARTIAL |
| P7 integrated demo/UI evidence | Build succeeds; no multi-session end-to-end demo or browser evidence. | NOT_STARTED |

## Correctness work to include in the next development increment

### C1 — Simulator must respect time, cash and position lifetime

Location: `python-engine/proactive_intelligence.py:128`, `simulate_shadow_trade`.

Confirmed by probe: a ₹100 proposal with a subsequent ₹200 open uses quantity calculated from ₹100, producing approximately **₹1,800.90 entry notional on ₹1,000 cash**, before entry fees. A bar from the previous day can be used as an executable entry because the proposal contains no signal/cutoff timestamp and the simulator checks only the upper expiry bound.

Code findings: it returns after the first usable bar and labels its close a time exit. There is no retained multi-bar position lifecycle. It can open beyond the stop/target geometry; `max_quantity=0` becomes unlimited through `or math.inf`. It does not validate finite prices, integral positive caps or OHLC consistency. Gap-stop behavior cannot be evaluated realistically by this one-bar shortcut.

Correction contract:

1. Proposal carries `signal_at`, `data_cutoff`, entry deadline and independent holding/session deadline. Accept bars strictly after the eligible decision boundary, in defined order, with explicit open/close timestamp semantics.
2. Determine executable price before sizing. Include entry fees, rounding, cash reservation and explicit maximum quantity; zero means zero, not unlimited. Require valid long geometry or invalidate/rebuild the candidate after a gap.
3. Maintain position state across bars until stop/target/thesis/time/session exit, or return `OPEN` with a valuation when data ends. Entry expiry does not close an already filled position.
4. Treat gaps through stops conservatively using available executable price. Preserve stop-first handling for genuinely ambiguous OHLC ordering and report the assumption.
5. Use finite-number/OHLC/chronology validation and immutable simulation assumptions. Flat percentage fees may be a disclosed fixture assumption; they are not a complete broker fee model.

Acceptance: ₹1,000 gap-up case never overspends; pre-signal bar rejected; no entry after deadline; position held across multiple bars; later gap through stop; zero cap; NaN/infinite/inconsistent bars; open-at-data-end; costs reconciled per fill. These cases are prerequisites for using simulated performance in P4.

### C2 — Shared allocation must size actual positions

Locations: `ShadowProposal`, `allocate_shadow_proposals` at line 111.

`required_capital` is currently just one share's price. The allocator reserves that value, but the simulator can size each selected candidate using a whole cash argument. There is no durable quantity/reservation contract tying the two together. Scores also use incompatible scales: trend ratios, range distances and volume ratios are sorted directly against one another.

Return sized allocations with quantity, executable-price assumption, fees, initial risk and reserved capital. Pass exactly that allocation to simulation. Maintain one shared account balance/open positions/pending reservations. Use an explicitly uncalibrated but comparable ranking baseline, or documented normalized ranks within sleeves, until calibrated estimates exist. Never imply raw cross-sleeve scores are comparable win probabilities.

Acceptance: two affordable candidates cannot both spend the same free cash; duplicates across sleeves are clustered; costs after downsizing remain valid; remaining balance and all rejection reasons reconcile. Simulate the requested capital stages as research scenarios only.

### C3 — Validate proposal hypotheses and data boundaries

Location: `build_shadow_proposals`, line 65.

Only the last timestamp is checked. Earlier bars can be unordered/future/incomplete; finite OHLCV validation is missing. A timestamp before `now` does not prove that an open-timestamped bar has completed. Range reversion can emit a target at/below entry after an excessive rebound. Trend logic uses rising close rather than the specified prior-high confirmation and lacks the specified relative-strength input; these differences must be an explicit versioned hypothesis, not described as the full original specification.

Specify/validate bar interval and completed cutoff, chronological uniqueness, OHLC geometry, finite positive prices and nonnegative volume. Prevent zero-volume division and stale/expired proposal output. Enforce target/entry/stop geometry and disclose parameter versions. Keep incomplete-data reasons observable rather than reducing all failures to an empty list.

Test each sleeve separately with a positive case and meaningful negative cases. The present test name mentions three sleeves but asserts only that some proposal exists. Also test future-data perturbations cannot change earlier decisions.

### C4 — Make activity counts and workflow diagnostics truthful

Locations: `proactive_activity_report` line 313, `proactive_inactivity_diagnostics` line 294.

Confirmed: two distinct opportunity IDs in different stages are reported as one opportunity because the report takes the maximum per-stage distinct count. Every stage transition is labeled a scan evaluation. Confirmed: an unrelated filled opportunity masks a different dropped risk-approved opportunity because diagnostics aggregate all history by mode. An empty database produces no diagnostics.

Other gaps: any event can appear to prove scanner liveness; no trading-calendar/session boundary or per-policy expected scan schedule is used. A weekend can look like a scan outage. The two-session/five-session requirements are not implemented. Funding totals cover all history even when activity has a `days` window, without clearly labeling the different period.

Implement separate scan-run evidence and opportunity-stage evidence. Count distinct opportunities across the whole filter scope; count evaluations from actual scan/candidate evaluation IDs. Detect dropped workflows by decision/opportunity using an expected transition deadline and accounting for deliberate rejections, expiry and reservations. Use per-policy expected jobs, the exchange calendar and account/mode filters. Represent unconfigured/no-evidence distinctly from healthy inactivity.

Acceptance: two IDs yield two; one setup with five lifecycle events is not five scans; old unrelated fill cannot hide a new dropped decision; fresh lifecycle event cannot hide a failed scanner; weekends do not trigger expected-scan failures; never-configured and never-ran states are visible; five-session sparse activity is diagnosed without forcing a trade.

### C5 — Enforce immutable event identity and scoped accounting

Locations: `record_opportunity_event` line 206 and `record_cash_flow` line 273.

Existing opportunity identity is not checked when a new event reuses its ID. An event in a different mode/account/policy can be appended while the opportunity retains its original identity. Older events can overwrite current-state projection. Idempotency conflicts silently ignore changed payloads rather than distinguishing an exact replay from conflicting evidence. Funding has a mode but no account identity and is not integrated with broker outcome reconciliation.

Define immutable identity tuple and conflict behavior. Require exact replay equality for an idempotency key; reject conflicting reuse without mutation. Preserve event time separately from observed setup time and session identity. Reject stale projection writes or derive current state from ordered revisions. Scope funding by account/mode and distinguish expenses from external funding when presenting returns. Use a common window/as-of contract or label differing windows explicitly.

Acceptance: same ID with different mode/account is rejected; exact replay no-ops; changed amount under the same flow key is a conflict; stale event cannot regress state; deposits do not increase profit; broker fills/outcomes can trace to decisions. Preserve historical events in migrations.

### C6 — Fixture lifecycle must be atomic and preserve source truth

Location: `python-engine/partner_fixture_adapter.py:16`.

Confirmed: create → complete empty close → same external ID reopen raises `broker_order_id already belongs to a different partner position`. The adapter attempts to reuse a globally unique broker-order field for an external position lifecycle. Confirmed: a valid new row followed by a malformed row leaves **one new open position committed** after the fixture is rejected. Preexisting snapshot closure is atomic, but the adapter as a whole is not.

The adapter also stamps marks with `received_at` instead of retaining source mark observation time. It coerces quantities through `int(...)`; external identity lacks source/account namespacing. Options/Greeks and corporate-action semantics are not implemented. A docstring saying Dev-only is not an enforced runtime/data-source boundary.

Validate the complete envelope and rows before any writes, then create/update/close/bind/revise in one transaction shared with accepted-snapshot promotion. Add explicit source/account/external-position/lifecycle mapping, not synthetic broker-order evidence. A reopening starts a new lifecycle. Preserve mark timestamps and required derivatives fields. Keep fixture use behind an explicit Dev/demo mode and isolated database selection; never let fixture data impersonate broker evidence.

Acceptance: invalid second row/account/sequence produces no position or revision mutation; correct close/reopen; external ID collision in another account rejected/scoped correctly; fractional quantity invalid where units require integers; stale marks stay stale; corporate action fixture; unknown option inputs blocked with reasons; real hedge builder reads the accepted fixture.

### C7 — Persist the whole watchlist lifecycle, not just its latest label

Location: `transition_watchlist`, line 249.

Good: repeat WATCHING does not reset the existing row or expiry. Missing: append-only transition history, account/policy linkage, observation revisions and scheduled expiry processing. Older `now` can move state backward in time. Once entry validity has passed, even a selected item's completion is rejected; SELECTED also has no EXPIRED transition. Entry opportunity expiry must be distinct from a filled position's exit lifecycle.

Integrate transitions with opportunity evidence in the same transaction, use optimistic revisions, preserve original entry deadline, and define pending-order versus filled-position states. A scheduler must expire unfilled opportunities while continuing to manage filled positions. Test restart, stale concurrent transition, entry expiry, fill-before-expiry then later completion, invalidation and replay.

### C8 — Optional AI is only a startup improvement so far

`0b9f7d6` usefully makes the API key optional. However, configured model-client construction can still fail at import, per-signal news/review is synchronous, and `MINIMAX_UNAVAILABLE_POLICY=block` can still block the pipeline when the model is absent. `AI_AVAILABLE` currently reflects client construction, not a successful provider response.

Finish P5: isolated initialization failure handling, real disabled/unavailable status, asynchronous bounded review queue, independent deterministic alert/watchdog execution, expiry-aware caching, circuit breaker and cost budget. Do not change a configured live veto silently. Test no key, initialization exception, timeout, queue saturation and provider outage with mocked transport. Keep numerical trade authority deterministic.

### C9 — Restore integration contracts

Review the actual route inventory against the golden fixture, justify the intended additions and update it deliberately. Add API validation for report windows and tests of the dashboard response shape/empty/error states. Regenerating goldens alone does not validate reporting semantics. Run client unit tests/browser evidence when UI behavior changes. Keep the native-binding gateway limitation explicit until tested in the supported runtime.

## Immediate next assignment: one corrected end-to-end shadow system

Implement the following sequence as one continuing assignment in Dev. Commit by checkpoint, but do not stop after a helper/test-only increment. All tests/demos must use isolated data and mocked external effects.

### Checkpoint 1 — Correct evidence and trade semantics

Implement C1–C7/C9 regression cases and contracts. Retain existing working code where possible. Split `proactive_intelligence.py` into focused modules only if useful for ownership/testing; avoid a rewrite that discards evidence or existing interfaces. Save the failing probe scenarios as regression tests asserting corrected behavior.

Deliverable: valid proposal → sized allocation → multi-bar simulation → persisted fills/outcome, with invariant checks for cash, timing, identity and funding. Fixture lifecycle is all-or-nothing. Route contracts pass. This checkpoint is groundwork for the next, not completion of the assignment.

### Checkpoint 2 — Wire the scheduled producer and persistent consumer

Add a SHADOW-only orchestrator to existing scheduler conventions. It obtains a bounded liquid/affordable fixture or real read-only data universe, computes incremental completed-bar features, records a scan-run outcome even with no candidates, advances watchlists, allocates, simulates/manages open shadow positions and persists decisions/outcomes. Resume after restart without duplicating opportunities/fills or resetting validity.

Instrument representative existing live books observationally without changing their orders. Keep account/mode separation. Exits/protection remain higher priority than scanning/research. Register explicit feature flags and update scheduler contracts. No broker executor consumer is needed for new shadow strategies.

Acceptance: invoke the registered scheduled job, not just its builder; observe rows through the real API; restart and rerun identical data without duplicates; simulate scanner outage; show an empty-but-successful scan separately from failed data. Profile bounded query/history work.

### Checkpoint 3 — Finish user-visible activity and profitability

Extend the current dashboard card to show actual scan health, unique setups, selection/fill reasons, account/capital use, funding, gross/fees/net outcomes, reconciliation status and missing evidence. Display the new diagnostics; the current count card alone does not explain why a trade was missed. Provide drill-down from a count to decisions/reasons. Clearly mark synthetic/shadow performance.

Acceptance: browser-verified examples for active, no-affordable-trade, no-opportunity, feed failure, five-session sparse activity, deposited funds and completed shadow trade. Save screenshots from the functioning application, not design mockups.

### Checkpoint 4 — Connect comparisons, health and optional AI

Consume the corrected outcome stream in existing Backtest Lab/exit-quality/strategy-health components. Compare one baseline with bounded entry/exit challengers on frozen time-separated data; report costs/nonfills/uncertainty and retained failures. No arbitrary profit claim from synthetic fixtures.

Finish C8 and make AI annotations independently observable. Complete P6 partner cards/corporate-action/reopen fixtures. Lack of real credentials blocks a real canary only, not this software. Do not let research/statistical evidence requirements become an excuse to leave the evaluation machinery unimplemented.

### Checkpoint 5 — Integrated multi-session demonstration

Provide one documented command or demo route using an isolated database. It must run registered jobs across several simulated eligible sessions, demonstrate all three sleeve triggers, constrained capital choice, expiry, a multi-bar completed trade, net outcome/funding separation, correct inactivity diagnosis, restart idempotency, an AI outage and a partner close/reopen lifecycle. Include machine-readable manifest/results and real UI evidence.

Report each P1–P7 milestone as implemented/tested, partial, not started or blocked by a named external input. Attach actual test commands/counts and pending work. No milestone is complete merely because a small focused test file passes.

## Suggested instruction to send the developer

> Assess and implement `docs/2026-09-06-product-foundation-assessment-and-next-development.md` alongside the full proactive-intelligence product spec. Start from current Dev HEAD. Correct the confirmed simulator, reporting and fixture-atomicity defects, then continue through the scheduled SHADOW orchestrator, persistent outcomes, dashboard drill-down, research/AI integration and multi-session demo. Do not stop after another helper-only checkpoint. Preserve audits and existing delivery safeguards. Keep all live behavior and Production untouched. Finish with P1–P7 status, exact verification evidence and the runnable demo.

The objective remains proactive, measurable decision quality on the current infrastructure. Correct economics and integration must precede using more activity or attractive simulated returns as evidence of better profit.
