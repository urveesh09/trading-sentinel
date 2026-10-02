# Independent system audit and next implementation plan — 20 September 2026

Audit scope: current Production runtime, committed Dev/Production code, effective settings, retained operational/research evidence, execution and advisory paths, and tomorrow's intended session. Production was inspected read-only. No settings, orders, partner messages, qualifications, or deployments were changed. Audit artifacts were written only in Dev.

## 1. Decision

**The engineering foundation is substantially stronger, but this is not yet the profitable, proactive income system envisioned. The latest release is genuinely deployed. It is not fully green for expanding live trading or promising partner tips tomorrow.**

| Question | Evidence-based answer |
|---|---|
| Is the latest code running? | Yes. Production merge `e591bb38cac923c3a882d352fff59ee3a6683724`; application image/health fingerprints agree. |
| Are Dev and Production the same? | Their committed trees contain the same 993 paths and blob hashes. Dev HEAD is `c0dc9bc68beb4596cbc20235a152881a682bf86e`; different commit identities reflect the merge. Dev has two pre-existing modified session golden fixtures, so working directories are not literally identical. |
| Will the strategies make money? | Not established. Retained internal results are mostly negative. New research infrastructure and passing tests do not establish a profitable edge. |
| Is the proactive basket operating on real Production input? | No. Enabled, but source is `LEGACY_FIXTURE_V1`, fixture path empty, account `dev-shadow`; opportunities, events, provider observations and synthetic positions are empty. |
| Are ordinary partner tips ready? | No. A saved intraday profile and destination exist, but registered research artifacts and qualifications both number zero. |
| Does the partner need to submit holdings for ordinary tips? | No. General NIFTY/SENSEX market setups are independent of partner holdings. Personalised portfolio hedges are a different feature and require truthful exposure inputs. |
| Can tomorrow be useful? | Yes: authenticated collection, paper observation, shadow evidence and operational verification. This is conditional on a fresh Kite login and input checks. It is not a profit or tip-delivery guarantee. |
| Is all owner trading disabled? | No. F&O/Penny live switches are disabled, but manual Momentum Telegram execution remains broker-capable. |

## 2. What was independently checked

- Read the system guide, code atlas, active plan and handover; used source/runtime evidence where historical notes conflict.
- Compared both committed Git trees, inspected running containers, and ran `scripts/verify_deployment.py` against the Production SHA. Gateway, engine and agent image identity checks passed; build UTC `2026-09-20T12:28:41Z`.
- Checked effective engine settings and Docker environment values, with credentials redacted. Every key in Production's root `.env` and gateway `.env` was present with matching values in its respective running containers. Shared internal/broker/Telegram credentials matched across applicable services. This verifies consistency, not external credential validity.
- Queried Production SQLite in read-only mode; inspected research archives, attempt journals, retained ledger rows, scheduler telemetry and recent container logs.
- Delegated independent advisory/research review to Terra and owner execution/accounting review to Luna, then inspected important findings and reproduced adverse cases independently.
- Independently ran 131 focused engine tests in a network-disabled disposable container using the Production image, Dev source mounted read-only, and temporary test storage: **131 passed, one existing Starlette deprecation warning**.
- Terra ran four focused advisory/replay/holdout suites: **91 passed**. These are separate selections, not a claim that the full repository was rerun.
- Two adversarial collection probes and a ledger-boundary probe reproduced defects that the selected passing tests do not cover.

The newest documented developer receipt records 4,122 engine tests/four skips and 357 agent tests. Those are prior developer receipts, not independently repeated full-suite results in this audit. No broker order, Telegram send, production qualification, live market session, or full browser interaction was performed.

Evidence files are in `docs/audit-evidence/2026-09-20/`: `runtime.json`, `partner-readiness.json`, `attempt-integrity.json`, `ledger-summary.json`, `probe-results.jsonl`, `accounting-probe.txt`, and the reproducible read-only/offline probes.

## 3. Important code defects and corrections

### A1 — High: unknown CAS eligibility is treated as confirmed non-eligibility

**Observed configuration:** `CAS_PHASE1_FNO_UNDERLYINGS` is empty. `market_calendar.is_cas_eligible()` returns false for every symbol when that list is empty, or when config import fails. The API signs the false result and Node accepts it as resolved evidence.

An independent, read-only clock probe for RELIANCE at 15:20 IST on 21 September returned `allowed=True`, `phase=CONTINUOUS_TRADING`. This is a hypothetical-clock policy probe, not an order submission.

Source: `python-engine/market_calendar.py:403–469`, `python-engine/routes_market_session.py:19–59`, `node-gateway/server/services/cas-eligibility.js:53–70`, `node-gateway/server/services/executor.js:423–454`.

NSE's current specification puts CAS-eligible cash stocks into CAS from 15:15; eligibility covers stocks with derivatives. Source: [NSE CAS specification](https://www.nseindia.com/static/products-services/closing-auction-session). A signed empty-list answer is not proof that a stock is non-CAS.

**Implement:** distinguish `ELIGIBLE`, `NOT_ELIGIBLE`, and `UNKNOWN`; build a dated, exchange-bound membership snapshot from an approved current master. Expose coverage, source hash and as-of time. Block new cash entries in the affected window when membership is missing/stale/unknown. Preserve exit handling; do not turn an entry halt into an exit halt. Recheck the session at final broker dispatch after network/database waits. Correct stale circular/effective-date comments while verifying the authoritative reference.

**Acceptance:** eligible stock blocked at 15:15/15:20; genuinely non-CAS stock handled correctly; empty/stale/partial list fails closed; Python/Node parity and latency-crossing-boundary tests; exit cancellation/square-off remains possible. This blocks a blanket owner-execution green light, not passive collection.

### A2 — High: F&O position close and cash-ledger close are not one durable transaction

`fno_positions.close_position()` updates an OPEN row and commits, but returns no affected-row result. `_manage_exits()` subsequently calls `record_trade_close()` in a separate transaction. Failure between them can leave a closed position without its ledger cash movement; a stale caller can append a ledger close after a no-op position update. `origin_ref` is stored but not uniquely enforced by this writer.

Source: `python-engine/fno_positions.py:216–234`, `python-engine/fno_orchestrator.py:372–388`, `python-engine/performance.py:255–301`.

Offline probe: closing nonexistent position 999 returned normally; two writes using the same `fno_position:999` origin created two ledger rows totalling -20. This proves the local invariants are missing; it does **not** prove Production incurred this exact duplicate. Current F&O position totals and ledger totals matched in the audit.

**Implement:** one idempotent transactional settlement keyed by source + position + settlement generation; require expected OPEN state/revision and affected-row ownership. Position close, cost result and ledger delta commit together. Persist broker fill evidence separately from local settlement so a retry settles an acknowledged fill without resubmitting an order. Surface unsettled fills for recovery. Apply the same invariant to spread and partial-close paths after inspecting their contracts.

**Acceptance:** duplicate close, concurrent workers, crash before/after commit, missing row, ledger fault and partial-fill tests; exactly one economic settlement, no phantom equity, recoverable interruption; explain historical mismatches without deleting or fabricating cash entries.

### A3 — High before partner activation: qualification registration is an operator assertion, not enforced research proof

The authenticated research-artifact API accepts a reference, a syntactically valid SHA-256 string and description; it does not read and verify the referenced report bytes. Qualification registration requires that reference to exist, but does not bind a verified heldout package, frozen criteria, review decision or expiry. Final dispatch rereads qualification status and rejects future review timestamps, but a sufficiently old qualification remains acceptable under the same policy string.

Source: `python-engine/partner_manual_advisory.py:535–601`, `python-engine/routes_hedge.py:341–375`, `python-engine/hedge_advisory.py:1047–1061`.

This is **not an unauthenticated bypass**. An authorized operator is currently trusted to have done the research correctly. That contract is weaker than the envisioned machine-enforced evidence gate, particularly when an AI developer might populate fields merely to unblock delivery. Zero current qualifications prevents this from authorizing present tips.

**Implement:** qualification imports a validated immutable report package. Recompute its content hash; verify index, structure, profile/config, complete policy/economic fingerprints, predeclared criteria, heldout split, outcome availability, costs, review identity/time and explicit validity period. Store the package/decision linkage. Revalidate compatibility at candidate creation and final dispatch. Suspend on incompatible policy/economic changes or expiry. Keep operator approval separate from automated report generation.

**Acceptance:** a made-up hash/reference, absent report, failed/insufficient heldout result, changed configuration/economics, expired review or different index cannot authorize a card. A genuine reviewed passing package can. Revocation blocks a queued card. Do not manufacture a qualification for tomorrow.

### A4 — High before trusting qualification economics: policy identity omits execution-model modules

`partner_qualification.py:236–249` hashes signal/candidate/chain/instrument/thesis/clock modules, but not the chronological fill/exit/replay implementation used by full-policy economics. `partner_full_policy_replay.py` uses that policy identity. Changing delayed-fill, fee, or exit assumptions can therefore leave the frozen policy identity unchanged.

**Implement:** include full-policy replay, chronological execution, spread replay, cost/stress implementation and their semantic settings in a versioned economic-model manifest; bind it through report, qualification and runtime compatibility checks. Separate data identity from policy identity.

**Acceptance:** each material fill/exit/fee-model change invalidates old evidence; irrelevant capture timestamps do not create new strategies; deterministic regeneration remains byte-stable.

### A5 — Medium, qualification prerequisite: completeness can falsely report COMPLETE

`partner_collection_attempts.py:221–250` counts rows rather than distinct expected scheduler slots. It also treats public unavailability specially only when *all* rows are unavailable.

Independent temporary-DB probes reproduced:

1. Two expected rows, one OBSERVED and one UNAVAILABLE, candidate NOT_REQUIRED: **COMPLETE, unavailable_count=1**.
2. Two attempts in the same minute slot, no attempt in the next expected slot: **COMPLETE, missing_schedule_count=0**.

`scripts/audit_session_completeness.py:172` additionally converts all-COMPLETE input status into `can_qualify=True`, although the underlying store deliberately always returns false. Collection completeness does not confer strategy qualification. The CLI is observational, so this is misleading output rather than a direct delivery bypass.

**Implement:** compare observed unique scheduler slots with the expected exchange/session-aware slot set; explicitly classify duplicates, unavailable observations, future/out-of-window rows and incomplete stages. Rename CLI output to `collection_complete`/`eligible_for_replay`; preserve `can_qualify=False`. Add the reproduced regressions.

**Production impact check:** independently inspected all retained September 15–17 attempts: each index/day had 165 unique minute slots, all public states OBSERVED, no duplicate minute slots. The 09:45–14:45 entry-window helper counted 150/150. Thus the identified defects do not invalidate these specific rows; they invalidate trusting the summary unconditionally.

### A6 — Medium: readiness CLI can exit successfully with decisive missing prerequisites

The deployed-schema diagnostic correctly describes no qualifications but assigns WARN. Its exit contract returns success for WARN-only results. An automation could interpret exit 0 as delivery-ready. The profile and config PASS results are useful, but the overall exit is not a partner-delivery certificate.

**Implement:** return explicit `delivery_ready=false` and structured blockers separately from diagnostic execution success. Missing qualification must remain a delivery blocker. Treat off-session stale quotes separately from a broken in-session provider; do not make Sunday look like a failed trading session.

**Acceptance:** no qualifications + valid token/profile yields diagnostic-success but delivery-not-ready; deployment automation cannot confuse them.

## 4. Effective settings and operational readiness

| Setting / evidence | Actual state | Interpretation/action |
|---|---|---|
| Core engine/gateway/agent | Running, healthy; release identity passes | Deployment succeeded. |
| Engine trading health | DEGRADED; Kite disconnected; order route UNVERIFIED | Sunday state is not proof of failure, but fresh login and read-only data checks are mandatory before Monday use. Do not place a trade merely to make a status green. |
| `quant_ngrok` | Exited 0 | Gateway Telegram uses polling, so tunnel absence does not itself prevent outbound Telegram sends. Verify the configured Kite callback route if it depends on this tunnel. |
| `autoheal` | Exited 137 | Automatic unhealthy-container recovery is not operating. Determine stop reason; restore via approved operational procedure if intended. Exit 137 alone does not prove an OOM. |
| Telegram routing | Partner token/chat configured and consistent | Last retained successful partner message is September 9; no recent end-to-end delivery proof. |
| Recent gateway network logs | Telegram DNS errors and polling restart around 12:51 UTC | DNS resolution succeeded when rechecked from engine; verify gateway polling recovery/transport before relying on it. No diagnostic message was sent. |
| F&O live / disable-live | false / true | Correctly disarmed for unproven live use. |
| Penny live / EDGE disable-live | false / true | Correctly disarmed. |
| Owner Momentum | Manual Telegram broker execution remains possible | Other sleeve switches are not a global live halt. Add explicit owner live-entry authority and display it clearly; preserve exits. |
| Momentum R1/R2 risk | 10% / 7% of momentum pool | Approximately ₹250/₹175 modeled stop risk on the configured initial ₹2,500 sleeve, before changing equity/size/affordability constraints. These are aggressive defaults, not 1% portfolio risk. |
| Core `RISK_PCT`, total risk | 0.10 / 0.60 | Reconcile the intended capital/risk policy with actual final dispatch. Gateway has a ₹1,500 per-signal ceiling and margin preflight, not a substitute for atomic aggregate exposure limits. |
| Initial core bankroll | ₹4,500; Momentum share ~55.56% | Core allocations imply ₹2,500 Momentum + ₹2,000 Penny; other sleeve allocations are separate. Do not “fix” this to ₹8,000 without tracing total allocation. |
| Partner manual enabled/shadow/delivery | true / true / true | Delivery becomes possible once all independent gates pass; SHADOW enabled does not globally disable delivery. |
| Partner profile default v2 | INTRADAY; NIFTY/SENSEX; MARKET_SETUP; DIRECTIONAL_DEBIT_SPREAD | Meets index/horizon request, but not hedge-first scope. |
| Partner capital/risk limits | ₹100,000 / ₹50,000 | A permissive maximum, not necessarily actual trade size. Confirm the intended per-idea loss ceiling; do not assume huge-account suitability. |
| Partner limits | Two new ideas/day; four updates/day; entry cutoff14:45; reminder15:10; deadline15:15 | A deliberate low-frequency policy; explain it rather than promising continuous tips. |
| Advanced hedge parent | true; phase2/3 live false, shadow true | No holdings/snapshots/account binding exist, so meaningful personalised hedge processing cannot occur. This is independent of ordinary market setups. |
| Proactive shadow source | LEGACY_FIXTURE_V1; empty fixture; dev-shadow identity | Enabled but nonfunctional for real market evaluation. Needs explicit completed-bar provider configuration. |
| Broker reconciliation account | Unconfigured; no imported broker reconciliation tables observed | Internal ledger equity is not externally verified broker equity. |
| Optional AI | Async true; classifier1; usefulness true; READY; requests0 | Feature is deployed and ready to annotate, not evidence of useful decisions or profitable predictions. Proceed/advisory policies avoid absolute dependency. |

Manual execution risk should be checked from current broker positions, pending orders, reserved cash and proposed fill geometry immediately before entry. Risk caps should be explicit per sleeve and for the whole account. Readiness should not be bypassed by an old Telegram button. A persistent global **entry-only** halt and per-channel controls are preferable to relying on unrelated sleeve flags.

## 5. Research and strategy evidence

Retained archive inventory at audit time:

- 990 public-input files: September 15, 16 and 17, 330/day across the two indices.
- Six candidate-input captures and three candidate-evidence records, September 17.
- Three persisted NIFTY cards, all RESEARCH_ONLY; two superseded, one expired historical VALIDATED_SHADOW.
- Quotes/contract masters retained for September 10, 11, 15, 16 and 17. Quote archive file presence is not proof of continuous active-leg executable coverage.
- September 18: **337 collector attempts returned `no_market_data_token`**; zero partner input attempts for that session. This is an operational evidence gap, not simply a quiet market.
- Zero registered strategy qualifications, research artifacts and partner feedback rows.
- Proactive runs record `FIXTURE_SOURCE_UNCONFIGURED`; opportunities/events/provider observations/synthetic positions are zero.

The September 15–17 public scans largely produced NO_SETUP; September 17 has three candidate-recorded decisions per index. Repeated two-minute scans and multiple snapshots are not independent trades. Current evidence is too sparse to establish an edge, especially for heldout trade economics and market-regime robustness.

The full-policy replay, chronological execution, heldout and strategy-comparison code exists. Collection is scheduled; the complete collect → verify → replay → heldout → review-package → qualification process remains an operator/offline workflow rather than an automatically completed research pipeline. Waiting alone will not run and review that pipeline.

### Internal historical cash results

These are retained ledger totals across multiple releases and dates, not a backtest of only today's code and not broker-confirmed returns. Do not add positions' P&L again.

| Source | Retained observations | Internal P&L |
|---|---:|---:|
| Momentum live-labelled | 24 closes | -₹137.28 |
| EDGE live-labelled | 11 closes | -₹125.31 |
| Momentum paper | 31 closes + 2 partial cash movements | -₹2,675.59 |
| EDGE paper | 18 closes | -₹6,560.80 |
| F&O paper | 52 closes | -₹37,287.32 |
| Penny paper | 19 closes | +₹55.33 |

F&O position stores split into 30 directional closes (-₹29,527.35; 6 wins/24 losses) and 22 DR closes (-₹7,759.97; 6 wins/16 losses). Their combined P&L matches the F&O ledger. This is evidence to investigate, not a reason to increase frequency or risk. Penny's small positive sample is also insufficient to declare a profitable strategy.

**Strategy verdict:** the architecture can evaluate ideas more honestly; the actual edge has not been demonstrated. ORB, trend/momentum, range-reversion and protection variants must compete on matched, cost-aware unseen sessions. Freeze the hypothesis and risk budget before evaluation; include no-trade and simpler baselines, misses/no-fills, delayed manual entry, partial/unresolved executions, drawdown and turnover. Report uncertainty and strategy selection bias. No fixed number of elapsed days guarantees qualification.

## 6. Tomorrow: what should happen and what must not be assumed

21 September is not listed as an NSE F&O holiday in the published [2026 holiday circular](https://nsearchives.nseindia.com/content/circulars/FAOP71777.pdf). Verify exchange-specific operational notices and the application's holiday load as part of the normal preflight.

Before open:

1. Confirm PC/network/Docker availability, the intended tunnel/callback route, and core service health. Resolve the disabled autoheal service if it is part of the operational design.
2. Complete normal Kite login. Confirm engine and gateway token/data readiness, fresh NIFTY and SENSEX observations, dated NFO/BFO masters and quote receipts. Never print tokens.
3. Keep unqualified strategies out of live delivery and F&O/Penny live execution. Until A1 and owner entry authority/risk checks are corrected, do not treat manual owner execution as blanket approved. This report does not change any switches.
4. If partner transport confirmation is required, authorize and send a clearly labelled **connectivity test with no trade advice**, retain acknowledgement, and check the actual destination. A connectivity test needs no strategy qualification. None was sent by this audit.

During session:

5. Check actual expected/received attempts and missing reasons, not just “job ran.” Collect active selected-leg quotes through exits. Distinguish NO_SETUP from token/provider failure.
6. Check completed lifecycle/exits separately from new-entry scans. Current-release in-session p95/p99/max runtime and rejection counts are needed; Sunday's no-op jobs cannot demonstrate contention fixes.
7. Record public observations and bounded research evidence. If a qualified strategy does not exist, partner silence is expected; do not loosen gates to create a message.

After close:

8. Seal/verify archive segments, source/master hashes and unique schedule coverage; preserve unresolved outcomes. Generate a per-index session report and an explicit reason why each strategy was or was not evaluated/qualified.
9. Run the research pipeline over eligible data, separately identify missing active-leg exits or heldout samples, and queue a review package. Log a completed no-setup day as useful observation, not a profitable trade or automatic approval.
10. Reconcile any genuine broker activity against statements/orders/fills/charges; do not call internal cash equity broker-confirmed.

Retained September 17 telemetry still includes maxima of 114.278s for research and 130.289s for F&O, with 18 and 8 scheduler rejections respectively; Penny has 12 rejected invocations. These predate today's release and the capped 5,000-row retention is incomplete. They justify new measurement, not a claim that today's timeout changes failed. An 8-second average on a 60-second schedule does **not** itself exceed the interval; tail latency and shared resource contention matter.

## 7. Next implementation sequence — concrete work packages

| Order | Work package / files and contracts | Acceptance and rollout condition |
|---|---|---|
| 1 | **A1 session eligibility + owner authority.** Calendar, authenticated eligibility route, Node resolver/executor, effective-status UI, explicit entry-only global/per-channel controls. | Missing eligibility cannot grant entry; final dispatch rechecks session; manual live capability visibly reported; pending/open exposure included in risk admission. Isolated failure tests before GitHub promotion. |
| 2 | **A2 atomic settlement.** F&O position/orchestrator/performance writers, then inspect DR and partial-close equivalents. | Crash/duplicate/concurrency tests prove one ledger effect; historical discrepancy report; no destructive “repair” or ledger reset. |
| 3 | **A3/A4 qualification truth.** Artifact/qualification schemas/APIs, policy/economics manifest, final delivery authorization. | Verified report bytes + complete model identity + compatible reviewed evidence + expiry required. Authenticated fabricated references cannot activate delivery. |
| 4 | **A5/A6 evidence/readiness accuracy.** Collection attempt store, session CLI, partner checklist and dashboard summary. | Reproduced adverse probes no longer show COMPLETE; no diagnostic green can mean qualified when registry is empty. Retained sessions re-audited. |
| 5 | **Real proactive source activation.** Existing `KITE_COMPLETED_BARS_V1` branch in `proactive_intelligence.py:2003`, provider module, config/deployment contract. | Explicit current instrument-token mapping, Production research account/run ID and immutable capital/cost assumptions; genuine fresh completed bars produce observations and evaluated opportunities, with no broker consumer. A scan may validly reject all setups. |
| 6 | **Research orchestration.** Extend `research_cli.py`/full-policy/chronological/holdout/comparison integration into an idempotent bounded post-session runner. | Immutable raw → coverage → replay → stress → heldout → review package. Restart resumes; invalid/missing data produces a reason, not an approval; CPU/I/O budget cannot delay trading exits. No automatic qualification merely from elapsed sessions. |
| 7 | **Hedge-first partner product.** Versioned profile + conditional-protection candidates, public triggers/invalidation/management, standalone NIFTY/SENSEX research. | User/partner confirms intended exposure type and per-idea cap. Conditional assumptions are explicit; no assertion that partner owns a portfolio. Qualify protection separately; prioritise protective/invalidation updates. No unrelated stock/BANKNIFTY scope expansion. |
| 8 | **Broker/accounting truth.** Existing internal reconciliation CLI and broker statement importer; account/order/fill identity, charges, partials and cash-flow mapping. | All prior warning categories explained by retained evidence; unresolved rows stay visible; never conflate deposit, paper P&L and broker profit. |
| 9 | **Production operations.** Login/input freshness alerts, scheduler telemetry retention, resource budgets, Telegram recovery, callback and autoheal checks. | A missed login is visible before useful session data is lost; market-load exit/lifecycle latency measured; evidence retained long enough for review. Avoid unbounded parallelisation. |
| 10 | **Evidence-based optimisation and controlled capital ladder.** Matched strategy/regime comparison, entry/exit ablations, costs/manual delay sensitivity, optional-AI usefulness. | Select only on frozen out-of-sample criteria and drawdown constraints. AI remains annotation with measured incremental usefulness. More capital or frequency is a reviewed decision based on attributable net results. |

### Required operator inputs

- Confirm the **maximum rupee loss per partner idea and daily loss budget**. The saved ₹50,000 risk ceiling against ₹100,000 capital must not be mistaken for an agreed prudent limit.
- For hedge-first conditional advice: identify whether they normally protect long index exposure, short option exposure, or another exposure. Ordinary directional tips do not require positions or their proprietary strategy.
- Provide/approve the account mapping and broker statements for external reconciliation. Broker credentials are already present; do not paste secrets into chat.
- Confirm whether owner live execution should remain manual-only and the desired entry kill-switch default. The stated ₹8,000 test capital and eventual staged increases are not permission for a 10% sleeve-risk default forever.

Development should use the existing APIs/providers where sound rather than starting another parallel framework. Each package needs a bounded plan slice, focused failure tests, documentation/atlas updates for source changes, and GitHub-based promotion. Do not change unrelated strategies while repairing evidence.

### Rollout / rollback

Implement in Dev only. Preserve the existing modified golden fixtures and audit evidence. Before merge, record schema/config changes and inspect a database backup/migration dry run. Keep new report generation observational; enable it first in shadow. Any future live/advisory promotion must identify the exact compatible qualification and current limits. Rollback should stop new entries/delivery for the affected feature while preserving position management, delivery claims, raw evidence and accounting history; never erase a claim to resend an ambiguous message.

## 8. Expected partner value and timing

When qualified and operational, cards can provide a concrete NIFTY/SENSEX intraday setup, specific contracts and lot-aware costs, entry trigger, invalidation, payoff/risk estimate, target/time horizon and material updates. Their purpose is more disciplined decisions and faster awareness; they do not know the best possible future entry/exit or guarantee profit.

**Tomorrow:** fresh research/operational evidence can be collected after login. No genuine entry tip can currently pass because there are zero qualifications. The partner need not fill in holdings just to receive general market ideas. A no-advice transport test is independently possible with authorization.

**First real tip:** only after the evidence-gate corrections, a genuinely passing reviewed qualification for that index/structure, a current valid setup and a working destination. It could arrive in the first eligible session after those prerequisites are satisfied; neither one/two runs nor the advanced hedge 5/7-day counters promise it. If research fails, the system should change the strategy hypothesis and test again, not relabel it qualified.

**Final assessment:** the improvements are real—release verification, durable advisory transport, causal research, realistic replay, independent lifecycle updates, source-aware dashboards and optional AI are meaningful foundations. The missing step is connecting them into a correctly enforced, actively configured, evidence-producing operating system with demonstrated net edge. That requires the bounded corrections above plus market and broker evidence; another large number of commits alone will not establish it.
