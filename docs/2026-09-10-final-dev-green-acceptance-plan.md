# Final Dev acceptance plan — Trading Sentinel

Baseline: b824da1, 2026-09-10. Consolidated completion contract for the current audited release. This supersedes the ordering of earlier plans, preserves their evidence and includes every unresolved finding from the two-commit and partner reviews. It is not a new implementation or profitability approval.

## 1. Definition of green

DEV GREEN means every gate D1–D9 below is implemented and independently verified at one exact commit, all release-critical regressions pass, unresolved limitations are accurately surfaced, and no known release-blocking correctness defect remains in this scope. It permits a monitored GitHub deployment of the reviewed capabilities. Unconfigured optional functionality may remain off with an explicit state; a defect in enabled functionality may not be hidden behind that distinction.

OPERATIONAL GREEN additionally requires deployed image identities, persistent storage/migrations, valid inputs, appropriate configuration and observed market-session timing/coverage. ADVISORY GREEN additionally requires a saved intraday profile, genuine current-policy/index research qualification, routing and final dispatch readiness, and a valid opportunity. These are separate states. Dev completion cannot promise profits or manufacture future observations. No arbitrary number of data days is a qualification guarantee.

Do not keep expanding the requirements without evidence. Any new blocker discovered during implementation must include a reproducible failure, impact, severity and specific acceptance test. Enhancements without demonstrated blocking impact go into a separate backlog. Positive tests alone do not override an unresolved reproduced failure.

## 2. Execution scope

All code, tests and documents in C:/Users/Urveesh/Desktop/trading-sentinel on codex/production-correction-hedge-p0. Inspect current HEAD and other agents' work first; do not reset or overwrite it. Production remains read-only; promotion through GitHub. Preserve audit documents and retained data. No live orders, partner messages, automatic qualification or Production configuration mutations as part of implementation. Use mocked transports and offline evidence for acceptance.

Implement all independently feasible work; do not stop at adding another status card. Reuse existing modules. Separate implementation commits by gate; record dependencies and exact test evidence. Preserve APIs or document and test compatible migrations.

## D1 — Entry acceptance and chronological execution correctness (P0)

Files: intraday_spread_replay.py, intraday_spread_chronological.py and tests.

Move all entry contract, quantity, side, debit positivity, width, cost and session checks before any active-entry/missing-exit result. Return explicit accepted-entry economics independently from exit availability. The chronological runner must not infer acceptance from a generic unresolved state. Invalid first entry must not block a later valid opportunity; accepted exposure must not disappear when exits are absent.

Use exchange-time comparisons throughout. Validate single-session input semantics; reject mixed-session streams or split them explicitly before execution. Enforce instrument/expiry/policy identity and receipt ordering. An entry deadline and an exit deadline are different constraints: a late or missing exit remains unresolved exposure with its reason, not a discarded rejected trade.

For nonzero manual execution delay, select the first subsequent eligible quote observation at/after the decision's execution time, within a declared maximum wait. Do not reuse the decision-time book as proof of delayed execution. Define deterministic signal expiry/cancellation during that wait. Preserve no-fill, stale-book and partial-leg uncertainty. A simultaneous two-leg fill remains a labelled research assumption unless evidence supports actual fills.

Acceptance: nonpositive/over-width entry with no exit; invalid then valid entry; UTC/IST equivalents; delay changes available book; cancelled signal before execution; missing/late exit; same-interval conflicting stop/target; duplicate packets; partial book; restart-equivalent replay. Every accepted exposure retains risk even without realized P&L.

## D2 — Verifiable deterministic signal artifact (P0 research integrity)

Files: intraday_spread_archive_adapter.py, research manifest/artifact modules; reuse existing strategy evaluator where appropriate.

Implement a real artifact writer/loader, not a free-form score dictionary guarded by a digest length check. Freeze schema, evaluator/code/config/policy identity, session/index, source manifest references and hashes, per-signal decision cutoff and source receipt bounds. Verify file contents against the digest and propagate the identity into replay and report outputs. Hash identity does not prove the evaluator is sound: verify causal source selection and reproduce scores from the declared evaluator.

Use only information available by each decision clock. Future outcomes cannot influence contract selection or signal scores. Make index/futures basis explicit and compatible with advisory thresholds. Unknown provenance is rejected or remains research-insufficient, never silently repaired.

Acceptance: tampered artifact, arbitrary digest, wrong index/policy/config, reordered packets, future source data, missing source file, contract-master mismatch and reproducibility across restart. Same input/config yields the same decision content identity. Report creation timestamps may differ outside deterministic evidence hashes.

## D3 — Holdout/report identity and coverage (P0 research integrity)

Files: intraday_spread_holdout.py, intraday_spread_research.py and typed replay results.

Bind underlying, policy/config, source/signal artifact, session and stable opportunity identity into replay output. Validate supplied labels against these fields. Parse dates and enforce chronological training-before-holdout. Freeze declared policies, sessions and evaluation thresholds before producing results; do not claim predeclaration merely because a constructor accepts parameters.

Require a coverage matrix for each declared index/policy/session: observed, no setup, no fill, unresolved, or unavailable. Missing cases must not vanish from the denominator. Deduplicate opportunities independently of formatting/report hashes. Reject missing/non-finite CLOSED P&L rather than converting it to zero. Keep rejected outcomes and unresolved risk in reports. Show per-group sample size, cost sensitivity, net expectancy, drawdown, coverage and uncertainty; insufficient data is a successful truthful report.

Acceptance: relabelled training case in holdout; wrong policy/index/session; duplicated trade with altered report hash; omitted losing/unresolved session; invalid P&L; empty group; out-of-order sessions; deterministic output. No report registers a qualification or chooses a winning strategy automatically.

## D4 — Partner condition management independent of entry generation (P0 advisory)

Files: partner_orchestrator.py, fno_signal_scan.py, partner_manual_advisory.py and relevant tests.

Separate public-condition observation acquisition from entry-chain construction. Active advice can be evaluated when there is no new ORB direction or the entry chain fails. Validate threshold basis: futures-derived levels cannot be compared to spot or another contract without a declared transformation. Preserve expiry, account/profile and immutable idea identity.

Conditional protection uses its own explicit exposure/coverage branch, independent of successful directional debit-spread construction. Do not infer partner holdings, enable protection by default or generate orders. An unavailable protective input is explicit even when another branch succeeds.

Keep invalidation priority over clock reminders, transport ambiguity protection, durable claims and final dispatch checks. Make the cadence limitation explicit: completed-bar monitoring does not prove tick-level stop protection. Scheduling/transport failure must not fabricate a successful update.

Acceptance: active invalidation with no entry signal; entry chain failure but valid public observation; stale public data; basis mismatch; protection-only permitted profile; one index fails while other progresses; concurrent recovery; delayed dispatch crossing deadline; restart and ambiguity. Mock all delivery transports; zero real sends.

## D5 — Current readiness and usable setup (P1)

Files: partner_manual_advisory.py, routes_hedge.py, operational_coverage.py, Dashboard/hooks.

Capture real attempt, completion/receipt and source clocks. Compute current age at API read time with an injected clock. Distinguish stale, future, unavailable, disabled, market closed and healthy no-setup. Older in-flight completions cannot overwrite newer status; preserve last successful observation separately. Qualification/profile readiness is computed independently from candidate creation and scoped to current policy/index/profile.

Form must distinguish saved/default profile, preserve unsaved edits during polling, handle revision conflicts, and explain optional per-lot ceilings. Existing user choices are INTRADAY, NIFTY/SENSEX, independent manual execution. Do not require their personal strategy or broker/portfolio integration for generic advice. Profile save success is not delivery success. Show last acknowledged advice separately from an empty backlog.

Acceptance: time advances without a new scan -> status ages; out-of-order completion; future clock; quiet qualified session; profile changes; 30-second polling while typing; failed save; version conflict; API outage. Include interaction tests, not only dashboard compilation.

## D6 — Scheduling isolation and evidence (P1, P0 if exit starvation reproduced)

Files: scheduler_telemetry.py, scheduler_setup.py, main.py, provider/DB/archive boundaries.

Instrument penny/bootstrap as well as FNO/research/lifecycle where missing. Capture start/in-flight/end, boot ID, monotonic duration and separate provider/limiter/DB/archive waits. Count skipped invocations separately from executed runs and market-close no-ops. Bound telemetry writes/retention; telemetry failure must not block exits.

Implement bounded independent read-only worker/request queues and budget controls appropriate to measured code paths. Stateful scans remain single-instance. Bulk research must yield/drop obsolete work with gap evidence instead of starving exits/time-sensitive updates. Thread offloads require bounded work and cancellation semantics; timed-out calls still running may not free a concurrency slot prematurely. Do not blindly increase instances or relax freshness/cadence.

Acceptance: injected slow provider, DB lock, archive contention, cancellation, restart and telemetry failure. Controlled tests demonstrate exit/lifecycle work does not inherit the injected bulk delay, queues remain bounded and actions do not duplicate. Define explicit latency budgets in test/config based on existing deadlines and report measured values; real Production budgets remain operational validation, not a fabricated code benchmark.

## D7 — Five reconciliation findings, not only a reporting API (P1)

Files: reconciliation_evidence.py, performance_analytics.py, broker_reconciliation.py, forward close writers.

Create consistent retained-data sheets for MOMENTUM, EDGE_LIVE, MOMENTUM_PAPER, PENNY_PAPER and EDGE_PAPER. Each needs actual amount/count deltas, time ranges, partial closes, costs coverage, funding/adjustments and specific linked/unlinked rows. Distinguish confirmed cause from ambiguous mapping. Missing broker statements block external reconciliation, not these internal investigations.

Detect duplicates sharing an origin, position-to-ledger missing closes, cross-source errors and non-finite amounts. Declare pagination and scope. Future linkage must cover relevant sources; do not pretend future FNO links resolve historical momentum/penny mismatches. No blind ticker/date matching or cash rewrite. Proven corrections require auditable idempotent adjustment records; unresolved differences stay visible.

Acceptance: five actual finding sheets with reproducible queries and snapshot hashes, plus duplicate/partial/fee/funding/missing-link fixtures. Internal matches never claim broker reconciliation. No unapproved economic mutation. If retained history is genuinely absent, sheet specifies exactly which source/date is missing and what remains unquantifiable.

## D8 — Real data integration, collection and forensic research (P1)

Complete the real Kite -> completed bars -> explicit Production research run -> activity/coverage UI path. Validate archived master identity and declared spot/futures basis, actual receipt time, current-bar exclusion and per-index failure isolation. Test volume semantics against downstream policies: zero-volume spot index bars must not be forced through volume-based equity strategies as if they were tradable shares.

Implement bounded active-leg subscriptions/retention through exit plus evaluated/rejected candidate coverage. Persist reasoned gaps and full contract provenance; do not collect only rolling ATM. Connect existing legacy strategy activity with deduplication and provenance or show it separately so new empty proactive tables cannot imply total inactivity.

Produce ORB and momentum forensic case packs from retained evidence: available decision inputs, contract/cost/timing/risk, duplicate/re-entry and exit facts; unavailable facts explicitly labelled. Implement archive-to-signal-to-chronological replay CLI/run path with frozen small strategy comparison and capability report. It must run now and honestly return insufficient evidence if archives lack required observations. Do not block implementation waiting for future data.

Acceptance: real-client-shaped offline session plus restart yields traceable observations, source status and deterministic research results; missing one index remains visible; no fabricated fills or P&L; no paper/live/replay mixing. Actual market outcomes are not required to pass software-contract tests.

## D9 — Release integration and independent sign-off (P0 release)

At one exact final SHA, run changed-module regressions and connected partner/scheduler/archive/accounting/route suites; run all required repository contracts. Run dashboard build and interaction tests. Gateway database tests must run in the compatible container/runtime where needed; do not call native-binding failures passing. Record any unrelated pre-existing failure with evidence and impact rather than silently waiving it.

Use an isolated Dev integration environment with copied/sanitized evidence and no live transport/order authority. Verify migrations on pre-change schema, idempotent startup/restart, bounded background work, HTTP/auth contracts and release identity from baked image metadata. Startup/API error paths must not expose secrets. Preserve named Production volumes; no deployment commands executed as part of Dev acceptance.

Run an end-to-end scenario: missing profile -> explicit blocker; saved test profile -> inputs; genuine test-only artifact in isolated DB -> candidate; independent active management under entry failure; simulated transport timeout -> manual recovery; clock advance -> stale/deadline handling; restart -> retained evidence; UI/API agree. Test artifacts must never enter Production qualification storage.

Publish one acceptance manifest listing D1–D9, commits, commands/results, evidence files, known limitations, enabled/disabled behavior and pending operational checks. A reviewer must be able to reproduce every blocker regression without trusting an implementation summary.

## Delivery order and finish line

First D1/D4 correctness, then D2/D3 evidence integrity. D5/D6/D7 can proceed independently with file ownership coordination. D8 integrates the results. D9 verifies the combined final SHA. Do not stop after helper APIs if the gate requires an actual evidence sheet or integrated path.

DEV GREEN is reached when D1–D9 pass and no reproduced blocking defect remains. Failed/insufficient strategy evidence is not a software failure if faithfully represented and qualification stays blocked. Missing profile/statement configuration may remain explicit pending operator input; it must not prevent completing independent development.

## Post-Dev operational checklist (not additional speculative coding)

1. Merge reviewed branch through GitHub; build/recreate and verify all application image identities with the existing runbook.
2. Confirm persistence, migrations, disk/write-budget headroom and per-index market data.
3. Observe at least a complete relevant market session for timing/exit-window coverage; more if failures or insufficient coverage warrant it. This validates operation, not trading edge.
4. Save the operator's explicit INTRADAY profile; test routing only with explicit authorization.
5. Collect sufficient causal active-leg observations and unseen sessions for the predeclared research review. Record negative results; no threshold weakening to force approval.
6. Import scoped owner broker statements if external cash reconciliation is desired.
7. Only then assess ADVISORY GREEN per index/policy and current opportunity. Neither Dev green nor routing success promises tips every day or profit.

## Instruction for implementing agent

Implement this plan in Dev on the existing branch, preserving other agents' work. Complete D1–D9 as concrete deliverables. Fix demonstrated problems rather than hiding states. Do not invent live evidence or request partner credentials. At completion provide the acceptance manifest and exact remaining operational prerequisites. Any newly discovered blocker must come with a reproducer; unrelated enhancements go to backlog.
