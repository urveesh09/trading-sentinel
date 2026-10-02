# Consolidated smart-trader implementation plan — October 1, 2026

Status: **PLAN_ONLY**, saved in Dev. No application implementation, migration,
Production edit/restart, broker action or partner message is authorized by this
document. Jev work is deferred. Assess Production; implement in Dev; promote
through the reviewed GitHub workflow.

## 1. Objective and authority

Sentinel should discover worthwhile opportunities, choose how and when to
enter, allocate finite capital, manage a valid thesis, capture continuing
trends and exit when invalidated or required by the session. Optimize net
returns and capital use subject to explicit downside and operational budgets.
Acceptance rate, more trades, more filters and more messages are not objectives.

Momentum paper remains autonomous. An optional AI timeout remains an UNKNOWN
annotation, not a new default veto. Every new real-money momentum entry retains
owner EXEC approval and existing execution/risk checks. Protective management
of an approved position remains active. Partner tips are manual intraday advice;
qualified advice does not grant partner order authority. Personalized portfolio
hedging is a separate product requiring genuine accepted portfolio inputs.

Reuse existing research, replay, shadow, qualification and comparison tools.
Do not rebuild completed evidence instrumentation or infer a missing feature
from an empty table. A software failure may require a correction immediately;
a strategy hypothesis requires measured comparisons and future evidence.

## 2. Evidence reviewed and corrected baseline

Production checkout/image: `d90c7759af22fc60b4f5e19c742ebec9b7193fa1`, build
`2026-09-27T18:00:08Z`. Dev at planning start: `35ee54a` on
`codex/production-correction-hedge-p0`. Source is effectively the same for the
inspected paths; Dev's additional Jev change is documentation only.

Reviewed Production audits dated September 29, September 30 and October 1.
September 29 includes September 28; no separate September 28 file was found.
Cross-checks used SQLite `mode=ro`, retained instrument/quote/collection files,
Docker inspect/health and source reads. Current logs do not reconstruct deleted
old-container logs. Scheduler's 5,000-row retention prevents a full historical
September 28–29 scheduler comparison; do not call that absence healthy.

| Verified observation | Implication |
|---|---|
| September 28 +INR 5,902.10, September 29 no ledger trades, September 30 -INR 178.71, October 1 +INR 8,702.97; all paper | Recent gains are real ledger observations, not a qualification result |
| September 17–October 1: single-leg F&O +INR 10,755.67 over 9 closes; DR +INR 3,187.60 over 7 closes; momentum +INR 24.14 including partial cash; penny -INR 98.82 over 10 closes; EDGE_PAPER +INR 378.78 | Always include partial cash and separate books; audit totals/counts need correction |
| Retained full histories: single-leg F&O -INR 18,367.22 over 38 closes; DR -INR 3,721.71 over 28 closes; penny -INR 41.03 over 28 closes | Different policy periods and legacy evidence cannot be pooled into a claim about current edge |
| INR 47,647.44 is the latest MOMENTUM_PAPER ledger balance | The audit's alleged 52% penny drawdown is book misidentification |
| October 1 BRIGADE: 87 shares at INR 573.10; IDFCFIRSTB: 1 share; BANDHANBNK: zero_shares | Paper capital was dominated by the first position, not necessarily by the best opportunity |
| September 30 GABRIEL used INR 49,469 of the fixed INR 50,000 pool; SAPPHIRE received 2 shares | Capital opportunity cost needs paired allocation research |
| October 1 F&O tick market-hours average 10.076s, maximum 116.425s, 4 MAX_INSTANCES; penny 18 MAX_INSTANCES; manual advisory maximum 111.511s | Last-30 post-market samples and COMPLETED alone are misleading |
| Slowest October 1 F&O tick: futures_quote 39.602s, exit_management 19.179s, defined_risk_snapshot 57.530s | Management reads, retries and shared request admission need bounded timing and observability |
| Research runtime-capped runs: 55/376, 59/376, 56/376, 58/376 for September 28–October 1 | Provider deadlines can leave index/selected-leg evidence incomplete even when jobs return normally |
| September 28–29 finalized quote hashes and event counts verified; September 30 finalized by next session | Integrity works; completeness and prompt post-session availability remain separate |
| Four September 30/October 1 momentum closes match admission keys and ledger cash; old/unopened cases remain unavailable/unresolved | Existing binding tools work, but no completed equity LTP comparison was established |
| Each index retained 165 partner attempts each day across these four sessions; profile default v2 exists; research/qualification registries empty | Collection is active; general advisory qualification has not been completed |
| General advisory/delivery flags true; personalized snapshot refresh false; F&O live disabled | An empty portfolio snapshot does not explain general-tip qualification; do not revive legacy tips |
| Actual log policy 20m x 10; gateway backlog 5 pending, 4 unsynced terminal orders, 8 undelivered alerts | Retention/reconciliation work remains; do not erase evidence or silently resend stale advice |

### New code findings requiring reproduction before the fix

1. `fno_dr_book.plan_structure` uses `_lot_size()` from configuration, falling
   back to 75. The retained October 6 contracts at strikes 22600/22500/22650
   have lot size 65. The October 1 spread records 75 while single-leg uses 65.
   This is a paper-economic contract mismatch. Preserve historical ledger cash;
   produce a separately labelled correction analysis rather than rewriting it.
2. DR legs retain option type/strike/ratio/premium but not exact expiry/token
   identity. Management values them against a current chain. Test an expiry
   rollover/foreign-contract snapshot; exact-contract marking must replace
   strike-only assumptions for future positions.
3. `manage_dr_structures` uses zero gross P&L when square-off is due but quotes
   are unavailable. That is an invented settlement, not an observed close.
4. DR position closure and `record_trade_close` are separate transactions;
   the DR caller does not supply the positive settlement generation required
   for the ledger's unique idempotency constraint. Reproduce crash-between-
   writes and concurrent-management cases; establish whether missing/duplicate
   cash is possible. No such incident was established for today's closes.
5. Chain snapshots use the tick's supplied `now_ist` as `taken_at` after slow
   network reads. Entry/management also reuse the scan-start clock. Reproduce
   the distinction between frozen signal cutoff, quote receipt and final
   admission/deadline clocks. Do not invalidate causal replay by simply
   replacing every timestamp with the latest wall clock.

The bearish `SHORT` direction is an underlying view; the single-leg executor
buys puts. October 1's put-premium increase is consistent with positive P&L.
Do not add a re-entry ban, automatic token refresh every eight hours, larger
live allocation, arbitrary gate relaxation or historical row deletion based
on the auditors' recommendations. None is supported by the reviewed evidence.

## 3. Ordered implementation slices

### S1 — P0: exact defined-risk economics and truthful settlement

October 2 cross-phase acceptance is superseded by
[the independent S1–S6 review](2026-10-02-s1-s6-independent-review.md): small
Dev corrections and passing suites do not close S3 crash faults, S4 runtime
capture/provider-byte binding, S5 qualification or S6 archive/economic/cost
binding and the missing DR experiment. Complete these reviewed slices before
calling the end-to-end roadmap operationally ready.

Problem: 75-versus-65 lot mismatch, incomplete contract identity and potentially
invented/nonatomic closes undermine learning from DR results.

Files/contracts: `fno_dr_book.py`, `fno_chain.py`, `fno_models.py`,
`fno_defined_risk.py`, `fno_instruments.py`, `performance.py`,
`fno_audit_report.py`; new DR-focused regression tests. Use contract metadata
in snapshots rather than a global lot fallback. Persist bounded immutable
underlying/expiry/exchange/token/symbol/lot/ratio and pricing-policy identity.

Steps:

1. Create offline reproductions for each finding, including a 65-unit master.
2. Derive lot/quantity from the exact selected legs; reject inconsistent or
   missing identities for new admission with a precise outcome. Keep existing
   structure-selection and risk thresholds unchanged in this correction.
3. Mark only the stored contracts. Missing prices produce an explicit
   unresolved settlement state. At hard-flat, record deadline breach and
   unresolved valuation; do not claim an observed fill or fabricate zero cash.
   No extra entry may treat unresolved exposure as available capital.
4. Make terminal position/cash settlement atomic and idempotent, or use a
   durable pending receipt with deterministic recovery if a single transaction
   cannot preserve current contracts. Keep ledger as cash truth.
5. Separate modelled mid valuation from executable bid/ask cash in reporting.
   Version any change to the existing paper fill model; do not silently change
   the baseline while fixing contract metadata.

Acceptance: mixed/changed lot sizes, expiry rollover, missing/foreign leg,
missing price at hard-flat, repeat calls, concurrent closes and injected
write failure cannot create wrong quantity, invented cash or duplicate cash.
Every new priced close reconciles to one exact lifecycle. Legacy positions
remain readable, explicitly unverified, and are not reconstructed by guessing.

Rollout/rollback: additive nullable provenance/state migration tested against
old schemas and repeat startup. Dev/offline first, GitHub deployment after
review. Retain old economic records and any unresolved exposure on rollback;
prove old-code handling before promotion. Do not drop additive evidence.

Implementation receipt (Dev, October 1): S1 contract/settlement correction is
implemented locally and remains unpushed/not deployed. New paper structures
bind every selected option leg to bounded NFO underlying/expiry/token/symbol/
lot/ratio identity, derive the lot from those legs (including a 65-unit master)
and reject missing, inconsistent or later non-matching contracts. Legacy rows
remain readable but unverified; no identity was guessed. A hard-flat with a
missing exact-leg price now becomes `UNRESOLVED` with no ledger cash and blocks
another structure through the existing one-open-structure guard. A priced close
uses `ENTRY_MID_EXIT_BID_ASK_V1`: model-mid and executable bid/ask values are
separate, and the terminal DR row plus one generated ledger close commit in one
SQLite transaction. Focused warnings-fatal tests passed 24: selected lots,
missing identity, rollover mismatch protection, hard-flat, repeat/concurrent
close, injected ledger failure rollback and daily report separation. The
broader affected F&O suite passed 84 with one intentionally deselected,
timing-sensitive exit-recovery test and one pre-existing Starlette lifespan
deprecation warning; that recovery test passes alone but fails only in its
grouped run and is outside this slice. Migration is additive columns only;
there is no configuration, broker, scheduler, entry-threshold or Production
change. Remaining S1 rollout: review/push through GitHub, verify deployed
schema and inspect real unresolved/settled receipts before interpreting cash.
Source commit `9e26e1b` is local on `codex/production-correction-hedge-p0`;
it is not pushed or deployed.

### S2 — P0: timely management and honest final decision clocks

Problem: market-data reads can block management and consume entry validity.

Files/contracts: `fno_orchestrator.py`, `fno_chain.py`, `kite_client.py`,
`partner_orchestrator.py`, `scheduler_telemetry.py`, `scheduler_setup.py`;
existing orchestrator, scheduler-isolation and collection-deadline tests.

Steps:

1. Measure limiter queue wait, transport duration, attempt/retry count, parsing,
   DB wait, management lag and final quote age separately with bounded fields.
2. Introduce explicit per-operation total read budgets and cancellation that
   leaves no detached retries. Preserve existing entry budgets. Start with a
   5-second exit-quote read budget and 10-second DR-management read budget in
   Dev fault tests; validate against quote cadence before freezing defaults.
   A budget failure invokes explicit degraded/unpriced handling, not fake cash.
3. Use fresh, exact-leg observations where eligible instead of rebuilding the
   entire chain for every open structure. Give due management requests priority
   over speculative/research work, with bounded fairness; never increase the
   provider request rate to solve queueing.
4. Refresh real action time before admission, TTL checks and hard-flat checks;
   retain the frozen completed-bar cutoff independently for signal causality.
5. Report COMPLETED, no-setup, unavailable, deadline-exceeded and partial
   coverage separately. Recover/label old IN_FLIGHT receipts after process
   death; they do not prove unfinished broker actions.

Acceptance: delayed provider/limiter/retry negative tests demonstrate that
optional research cannot postpone management beyond its configured budget;
stale reads never authorize entry. Boundary tests cross entry cutoff and
hard-flat during a request; clock jumps and cancellation preserve safety.
Do not put order submission/settlement mutations inside generic `wait_for`.
Inspect at least three complete deployed market sessions for management lag,
p95/max duration, skip counts and unresolved exposure; observed failures stay
visible and are investigated rather than averaged with off-session no-ops.

Rollout/rollback: small independent commits for instrumentation, read budgets
and request prioritization. No global concurrency/rate increase. Reverse each
slice through GitHub while retaining receipts and active position obligations.

Initial implementation receipt (Dev, October 2): S2 provider-read containment
is underway, locally only. `FNO_EXIT_QUOTE_READ_MAX_SEC=5` bounds the futures
and open single-leg exit quote reads; `FNO_DR_MANAGEMENT_READ_MAX_SEC=10`
bounds the existing DR snapshot read. Each reports bounded `COMPLETED`,
`DEADLINE_EXCEEDED` or `FAILED` state, elapsed seconds and cap seconds in the
tick result. Timeouts cancel and join the read, then preserve the existing
unpriced/hard-flat handling; broker dispatch, terminal settlement, admission
and database writes are outside every `wait_for`. The new DR timeout regression
proves cancellation/join plus management invocation with no snapshot. Focused
orchestrator/recovery/audit checks passed 34. Warnings-fatal mode exposed an
existing unclosed-socket ResourceWarning in an unrelated stage-duration test,
so it is not represented as a clean warnings-fatal suite. No schema/config-file
migration, provider-rate increase, broker, entry-policy, Production or AI
runtime change occurred. Remaining S2 work: due-management priority, fresh
action-time admission checks, limiter/transport/parse/DB timing breakdown and
deployed-session observations. Source commit `5ae54a8` is local on
`codex/production-correction-hedge-p0`; it is not pushed or deployed.

Historical partial-slice receipt (Dev, October 2): S2 timing/action-clock
work is implemented locally. The real Kite quote client exposes bounded
limiter wait, transport, parse, attempt and retry metrics; management retains
them where available and explicitly labels fixture/adapter timing unavailable
rather than inventing values. Exact open-leg quote observations retain a
conservative oldest quote age. Real scheduler ticks refresh action time after
provider waits and again before entry-window admission, while explicit
replay/test clocks stay frozen for causality. Exits still run before optional
DR entry work; no rate limit/concurrency increase was made. Focused
orchestrator/Kite/recovery/audit validation passed 59 and compilation passed.
Independent review supersedes the full-completion claim: source work remains
for exact-held-leg DR reads, shared-provider management priority/fairness and
DB-wait/timeout-stage attribution. Small post-read/final-admission clock,
frozen signal cutoff, quote-age and completion-log corrections are documented
in [the review](2026-10-02-s1-s2-independent-review.md). GitHub
promotion must also be followed by three complete session receipts for lag, p95/max,
deadline, skip and unresolved-exposure review. Source commit `d2319e2` is
local on `codex/production-correction-hedge-p0`; it is not pushed or deployed.

S2 completion receipt (Dev, October 2): DR management now requests only the
persisted, validated leg tokens and constructs its valuation snapshot from
those identities. It never rebuilds a nearest-expiry/ATM chain for a legacy,
missing or inconsistent retained identity; that lifecycle remains
unpriced/unresolved and creates no invented cash. `KiteClient` now shares a
single token bucket with a bounded management lane: management receives up to
three consecutive admissions while normal work waits, then a queued normal
request is admitted. This changes ordering only, not the 3/s rate, burst-one
capacity or concurrency; cancelled waiters remove themselves. Completed quote
timing includes limiter, transport, parsing and retry-backoff time. Timeout
records explicitly say that the cancelled provider stage is partial/unknown.
Management SQLite stage elapsed time is retained separately and honestly
labelled as operation elapsed including any lock wait, rather than a fabricated
lock-only measurement. Focused DR/orchestrator/Kite checks: 105 passed, one
known skipped test; the isolated DR/Kite warnings-fatal command: 53 passed,
one known skip. The larger warnings-fatal aggregate still has two unrelated
unclosed-socket ResourceWarnings, so it is not claimed clean. No migration,
provider-rate/concurrency, broker, entry policy, AI, Production or deployment
change. Remaining S2 acceptance is stale-IN_FLIGHT recovery review and three
complete deployed-session receipts; neither tests nor promotion prove
profitability or qualification.

### S3 — P1: preserve the evidence required to learn

Files/contracts: `docker-compose.yml`, `scripts/verify_compose_logging.py`,
`logging_setup.py`, `signal_log.py`, `penny_signal_log.py`,
`scheduler_telemetry.py`, `research_archive.py`, operational runbooks.

Steps: provision engine logging at 20m x 25 (500 MiB) initially, verify rendered
Compose without exposing env values, and measure actual peak session bytes.
Preserve old-container logs by release/boot before replacement. Add bounded
daily market-hours scheduler summaries before raw telemetry eviction. Rotate
CSV evidence by session without losing header, identity or rows; keep manifests
and a retained bounded archive. Monitor disk/free-space and writer failures.
Finalize closed-session research segments after the session with bounded
off-path work, keeping restart recovery and partial-tail handling intact.

Acceptance: rendered/actual log policy matches; representative peak-volume
checks retain a full session with documented margin. Replacement retains the
previous boot's evidence. Rotation/restart tests show no lost/duplicated
records. Summaries retain market-hour stage/skip/outcome measures after raw
retention. Backups/restore tests precede material retention/migration changes.

Rollout: Dev config and tests first; effective Production recreation is an
operator deployment step. Rollback restores config/writers without deleting
archives. A 500 MiB capacity check alone is not proof of a full session.

S3 completion receipt (Dev, October 2): `python-engine` now renders Docker
`json-file` retention at `20m x 25` (500 MiB); the verifier fails closed below
that floor and never prints rendered environment values. Momentum and penny
signal CSV writers keep their configured current-session path, then atomically
move the prior IST-session file into a sibling archive on rollover. Each
archive retains its original header/rows and gets an append-only SHA-256
manifest entry; unlabelled pre-S3 files are preserved as `legacy-*`, never
silently assigned to a new session. No automatic archive deletion was added.
Scheduler telemetry now folds final events into durable IST-day/job/kind
summaries (outcome counts and finite stage count/total/max) before the raw
tail can be pruned. Crash `IN_FLIGHT` markers are intentionally excluded from
the final summary and remain explicit in raw recovery evidence. Existing
research archive free-space reserve, writer lease and daily write budget remain
the passive-collection capacity controls. S3 focused suite: 57 passed;
warnings-fatal rotation/summary suite: 13 passed; Compose verifier: 8 passed
and rendered 500 MiB. The only schema effect is additive
`scheduler_daily_summaries` telemetry; no trading-data migration, archive
deletion, broker, AI authority, Production recreation or deployment occurred. A deployed
free-space check, prior-boot log preservation and complete-session volume
measurement remain operational acceptance, not test or profitability claims.

### S4 — P1: complete equity paths and explain capital-skipped admissions

Files/contracts: `momentum_paper.py`, `main.py`, `momentum_paper_audit.py`,
`momentum_exit_study.py`, `momentum_paper_evidence_review.py`,
`momentum_shadow.py`; a scoped new equity-path collector/adapter if required.

Steps: first inventory whether faithful equity observations already exist.
If absent, attach a bounded passive collector to accepted paper opportunities
and relevant existing quote fanout, without a provider call on admission/exit.
Retain key, exact instrument, immutable entry economics, source packet hash,
provider observation/receipt clocks, gaps and deadline observation. Follow paths
through the study horizon even after the baseline exits, including scale-outs;
a post-close counterfactual needs post-close prices. Preserve existing strict
study deadline/gap rules. Source hash verification must inspect packet bytes.

Extend bounded admission evidence with configured benchmark pool, realized
paper cash basis, deployed/reserved capital, fees, available notional, risk
budget and allocation-policy version. Keep `zero_shares` compatibility while
adding a precise reason (capital exhaustion versus risk/price/invalid input).
Label the current fixed INR 50,000 sizing benchmark; do not present it as
drawdown-adjusted spendable equity. Do not change sizing in this evidence slice.

Acceptance: original quantity survives scale-outs; two same-ticker admissions
never mix; writer saturation cannot block trading; gaps remain unavailable;
forged/mismatched packet identity is rejected. Reproduce the GABRIEL/SAPPHIRE
and BRIGADE/BANDHANBNK/IDFCFIRSTB capital decisions without altering old records.
New full paths allow the existing paired review to complete, or report the
exact missing evidence. At least five fresh reconciled lifecycles are an
instrumentation smoke milestone, not a profitability criterion.

Rollout/rollback: additive bounded evidence, existing collectors reused where
possible; collector disabled on rollback, historical paths retained. Configure
storage caps before enabling it. No silent strategy or AI-authority change.

S4 completion receipt (Dev, October 2): accepted paper admissions now seal a
bounded canonical decision packet and SHA-256 receipt, plus a separate bounded
capital snapshot containing the fixed configured pool label, realised cash
basis, deployed/reserved/available notional, risk budget, fee basis and policy
version. `zero_shares` remains the historical outcome while its reason is now
specific. A new exact-admission-key subscription table captures immutable
original quantity and the intraday deadline. The new caller-fed path collector
stores only supplied provider packet bytes with provider/receipt clocks; it has
no HTTP or LTP callback, so it cannot add a provider request on admission or
exit. Its read-only adapter recomputes each source hash from stored bytes and
fails closed on identity, ticker/key, order, gap or exact-deadline faults before
emitting a study packet. S4 focused tests: 73 passed; compilation passed.
This is additive Dev-only instrumentation, not an automatic quote-fanout
deployment. Configure caps, connect an existing fanout and collect five fresh
reconciled paths before an operational evidence claim. No sizing, exit, broker,
AI authority, historical record or Production behavior changed; rollback uses a
GitHub reversion/collector disablement and retains historical evidence.

### S5 — P1: complete general partner research and delivery readiness

Files/contracts: `partner_collection_attempts.py`, `research_quote_collector.py`,
`research_leg_subscriptions.py`, `partner_research_capture.py`,
`partner_full_policy_replay.py`, `intraday_spread_holdout.py`,
`partner_qualification_review.py`, `partner_qualification_package.py`,
`partner_qualification_authority.py`, `partner_manual_advisory.py`,
`research_cli.py`, `hedge_advisory.py`; existing qualification/delivery tests.

Steps:

1. Verify public inputs, contract master, selected-leg quotes and lifecycle
   coverage per candidate/index, including all no-fill/unavailable cases.
   Prioritize exact subscribed legs over optional ladder breadth. Diagnose the
   recurring 48-second collection caps without relaxing freshness rules.
2. Use September 28–October 1 as development/diagnostic data. They cannot be
   called fresh holdout after reviewing their outcomes. Freeze policy/profile,
   fees, manual-entry delay, slippage, coverage and review criteria before new
   holdout; retain each manifest and actual creation time.
3. Run the already implemented full-policy replay and holdout review. Plan an
   initial 20 independent trading-session observation window; keep collecting
   if the frozen minimum independent closes/coverage criteria are unmet.
   Session count is a scheduling target, not a new permission gate. Existing
   qualification requirements take precedence and cannot be lowered afterward
   to obtain a passing result. Variants of one idea are not independent trades.
4. Build the immutable authorization package only from verified evidence and
   a compatible reviewed outcome. Register qualification through the existing
   authorized interface; never manufacture rows or auto-promote a backtest.
5. Run a separately authorized transport canary. Verify receipt/dedup/expiry,
   ambiguous timeout recovery, invalidation, target and session reminders.
   Delivery success is evidence of transport, not strategy profitability.

Acceptance: a diagnostic can explain every candidate's delivery blocker;
wrong profile/policy/hash, incomplete evidence, stale qualification and expired
cards cannot send. A qualified fresh card has exact terms and acknowledgement;
restarts/timeouts cannot duplicate it. Partner still decides whether to trade.

Rollout/rollback: per-index qualified pilot, existing message cap retained,
revocable qualification/delivery flags. No legacy broadcaster restoration.
Personalized hedge activation is a separate track requiring source/account
binding, complete snapshots, real reconciliation and its own staging evidence.

S5 implementation slice (Dev, October 2). Read-only Production inspection
(engine image, data volume mounted read-only, no network; stack was already
stopped for the NSE holiday) established the following before any edit:

- Research collection is bimodal: p50 elapsed about 1.5 s, while 55/56/58
  runs per session reach the 48 s cap. Each capped run falls 1–4 minutes after
  :00/:15/:30/:45 IST, and even the one-token future-reference request stalls.
  No provider timeout/retry was logged. The September 30 engine log shows
  `run_momentum_screener` fetching 497 tickers for about 243 s, with up to 50
  concurrent waiters on the shared 3/s, burst-one limiter. Research completes
  in about 1 s immediately after the screener finishes. The same window shows F&O
  `chain_snapshot_deadline` and a skipped penny scan. Root cause: shared
  normal-lane queue contention, not request size or transport.
- Partner coverage, September 28–October 1: 1,295 attempts were NO_SETUP;
  22 candidates had complete requested/received contracts. All 22 persisted
  ideas are `RESEARCH_ONLY` with no qualification registry match, so
  `strategy_not_qualified_for_delivery` is the universal delivery blocker.
- Seven September 30 ideas were stored `REJECTED` for
  `stale_or_future_leg_quote` while the attempt journal recorded the same
  ticks as `candidate_validated`. `persist_candidate` re-validates at the
  frozen tick-start clock; a chain received more than 5 seconds after tick
  start therefore looks like a future quote. This is the S2 frozen-clock
  defect in the partner path, not a market-quality rejection.

S5a — partner action clock. Files: `partner_orchestrator.py`, its tests.
Persistence and conditional-protection construction/precheck use the tick's
live `stage_now()` action clock; explicit replay/test clocks remain frozen.
No validation threshold, qualification, delivery or profile rule changes.
Acceptance: a chain received after the 5-second future tolerance persists as
VALIDATED_SHADOW; explicit replay clocks remain byte-for-byte frozen; an
actually stale quote still rejects.

S5b — owner-approved bulk provider lane. Files: `kite_client.py`, `main.py`
(momentum screener per-ticker fetches only), `research_quote_collector.py`,
tests. Add a `bulk` lane to the shared `RateLimiter`: queued normal requests
are admitted ahead of bulk, but at most three consecutive normal admissions
occur while bulk waits (bounded fairness, no starvation). Management priority
from S2 is unchanged and above both. Rate 3/s, burst one and concurrency stay
unchanged. Research requests the future reference plus exact active legs
first, then the optional ATM ladder, and retains limiter/transport timing
for every provider call. Acceptance: bulk cannot starve; normal work is not
queued behind a 50-waiter bulk backlog; management still preempts both;
cancellation removes waiters; exact legs survive a ladder deadline.
Expected effect: the bucket is work-conserving, so the screener's ~243 s scan
becomes roughly 10–20% longer (estimate 270–285 s). Penny scans and F&O
snapshots that previously stretched, timed out or were skipped now complete
first. Signal logic is unchanged. This estimate must be measured after deployment.

S5c — read-only candidate delivery-blocker diagnostic. Join attempt journal,
persisted ideas, qualification registry and delivery flags; report every
candidate's ordered blockers and attempt/idea disagreements. No writes,
qualification, registration or messages.

Steps 2–5 (frozen protocol, 20-session holdout, package, canary) reuse the
existing tooling and need fresh post-promotion sessions; they are not
represented as complete by S5a–S5c. Rollback: GitHub reversion of each
sub-slice; no data migration or evidence deletion.

S5a completion receipt (Dev, October 2): `partner_manual_advisory_tick` now
persists candidates with `stage_now()` and builds/prechecks conditional
protection at the same live action clock; explicit replay calls keep the frozen
tick clock. New end-to-end regressions (real candidate, validation and
persistence) cover a 20-second-late chain (`VALIDATED_SHADOW`), frozen replay
and a genuinely stale chain (still rejected). The late-chain test fails on the
previous source with `stale_or_future_leg_quote`. Partner/hedge/scheduler
suites: 373 passed with the known Starlette deprecation. No validation
threshold, qualification, profile, delivery, schema or Production change.
Source commit `f45ce43`.

S5b completion receipt (Dev, October 2): `RateLimiter` gained the `bulk` lane
(`normal_burst=3`) and `provider_lane()` context; `_run_momentum_screener_impl`
creates its per-ticker tasks inside the bulk lane. `get_quote_by_instruments`
now delegates to `get_quote_by_instruments_with_timing` (identical single
attempt/failure semantics). Research collection requests future plus exact
active legs first, then the remaining ladder, and retains `provider_timing`.
Regressions: normal not queued behind a 30-waiter bulk backlog; bulk admitted
within three normals; management still preempts both and yields to bulk;
unchanged S2 ordering without bulk; cancellation; context scope/reset;
timed lookup; an exact leg surviving a ladder deadline (fails on the previous
collector). 141 affected tests passed with one known skip; warnings-fatal
subset 24 passed. A pre-existing partner fixture event-loop ordering error
in combined runs is reproduced on clean HEAD (30 errors) and is unrelated.
No schema, configuration, rate, concurrency, broker or Production change.

S5c completion receipt (Dev, October 2): new `partner_delivery_blockers.py`
and the `partner-delivery-blockers` CLI command. Read-only (`mode=ro`), missing
databases are reported, output is immutable. Tests cover ordered blockers for a
real research-only shadow card and a validation rejection, aggregate attempt
disagreement, status classification, malformed payloads, unchanged DB digest
and refused different overwrite (10 passed warnings-fatal); related CLI,
qualification, collection and advisory suites passed 110. No schema,
configuration, qualification, delivery or Production change. S5 steps 2–5
remain operational and need fresh promoted sessions. S5b commit: `18c7f2a`.

### S6 — P2: smarter exits on the same opportunities

Files/contracts: existing `momentum_exit_study.py`,
`momentum_paper_evidence_review.py`, `momentum_exits.py`,
`proactive_exit_research.py`, F&O management research adapters.

Steps: first run the existing baseline versus `target_hold_trail_v1` comparison
on complete source-bound paths. Then, only as a separately frozen experiment,
compare thesis-confirmed time extension/scale-out against the original exits.
Confirmation uses information available at that moment (price/VWAP/structure,
progress, volume and regime); failure/invalidation exits promptly. Initial risk
does not grow, stops do not move against the trade, and intraday deadlines stay.
Do not overwrite the live monitor to conduct a research comparison.

Measure net cash/R, favorable/adverse excursion, upside captured, giveback,
tail loss, costs, time exposed and unresolved outcomes. Keep F&O single-leg,
defined-risk spreads and equity studies distinct; their R denominators differ.
October 1's +2.29R put is a useful successful hold/trail case, not a reason to
replace all time stops. Include bad continuations and gap scenarios too.

Acceptance: paired same-entry/economics reports, no future-price leakage,
cost-stressed comparisons and negative cases. Freeze selection before future
holdout. A small positive sample does not authorize a new runtime exit policy.
Promote a reviewed winner to versioned paper-only management first; retain
baseline shadow comparison and rollback trigger. Live changes need their own
explicit scope review and preserve owner-approved entry authority.

S6 implementation slice (Dev, October 2). Inventory: `momentum_exit_study.py`
(v1) pairs the live pure evaluator with `target_hold_trail_v1` and is consumed
by `momentum_paper_evidence_review.py`; it stays byte-for-byte unchanged. No
complete source-bound equity path exists yet (S4 collection is not deployed),
so step 1 cannot produce a result today. Do not use backfilled or synthetic
paths as evidence. The live evaluator already banks half at +1R and defers
the fast time stop while LTP holds above VWAP-at-entry; the remaining hard
exits are the slow time stop and the final target.

S6a — frozen equity exit experiment. New `momentum_exit_experiment.py`
reuses the v1 loader, path validation, evaluator replay, costs and legs.
- `freeze` writes an immutable manifest: candidate policy, all parameters,
  evaluator settings, code fingerprint (study, experiment and evaluator
  source) and freeze time. `evaluate` refuses any mismatch.
- Entries at or before the freeze time are labelled `DEVELOPMENT`; only later
  entries count as `HOLDOUT`.
- Candidate registry: `target_hold_trail_v1` (identical to v1's alternative)
  and `thesis_confirmed_extension_v1`. The latter applies only where the
  baseline would exit on the slow/fast time stop or the target. It extends
  only when confirmation known at that quote holds: LTP above VWAP-at-entry,
  not below entry, within 0.5R of the running high since entry, and a regime
  not containing REGIME_3/CRISIS. While extended, losing confirmation exits
  at that observation. The stop only ratchets up (running high minus 1.0R),
  never below the current stop, and 15:15 IST remains forced. Volume is not
  in the packet and is declared unused.
- Metrics per policy: net cash, R, MFE/MAE in R over the exposure window,
  giveback (peak minus realised R), minutes exposed, worst R, and net at
  cost multipliers 1.0/1.5/2.0. Paired deltas: counts of wins/losses/ties,
  mean/median/worst, sum excluding the best delta, and per-cost sums.
- Acceptance: no future leakage (later quotes cannot change earlier
  decisions); bad continuation, gap-through-stop, missing VWAP, crisis
  regime and deadline cases; manifest tamper refusal; candidate
  `target_hold_trail_v1` reproduces the v1 alternative. Qualification stays
  `NOT_ASSESSED`; no runtime import.

F&O single-leg and defined-risk exit experiments are separate future slices
(different R denominators and path sources). Promotion to versioned
paper-only management requires a reviewed holdout result and is not part of
S6a. Rollback: delete the inert module via GitHub; no state to migrate.

S6a completion receipt (Dev, October 2): implemented as planned in
`momentum_exit_experiment.py` plus 13 warnings-fatal tests; momentum
exit/paper/review suites passed 125. v1 study bytes unchanged. Spot check
on a synthetic path: the baseline cuts at 90 minutes (+0.05R net); the
candidate defers it, the live +1R scale-out still fires, and the remainder
exits at 15:15 (+1.32R, giveback 0.375R). This is a mechanism check, not
evidence. No real result exists until S4 paths are collected after the
freeze.

S6b slice (Dev, October 2): F&O single-leg exit research. Step 1 extracts the
live inline ladder into pure `fno_exit_rules.py` (called by the orchestrator)
so research cannot drift from live rules; `fno_backtest.py` already diverges
(bar-close arming, different order) and is not the reference. Acceptance:
characterization tests on the inline code before and after, a frozen-oracle
differential test, and unchanged F&O suites. Step 1 receipt: 3 new
orchestrator characterization tests, 20,000-case differential match, 397
suite tests passed; no configuration or behaviour change. Step 2: a frozen
single-leg experiment on archived futures and exact-option paths, reusing
the S6a manifest/holdout discipline.

Step 2 contract: new inert `fno_exit_experiment.py`.
- Packet schema `fno_single_leg_exit_study_input_v1`: one entry per position
  (token/symbol, direction, quantity, entry premium/underlying,
  stop/target/premium stop, ATR, entry time) plus paired observations
  (futures LTP and option exit basis at the same receipt).
- A read-only archive adapter builds packets from research-archive quote
  events only where the front future and the exact option share one
  collection receipt. The exit basis is the best bid, or LTP when no bid
  exists, exactly as live. Provenance hashes the archived raw-packet
  digests. Gaps above the declared maximum, a late first observation or a
  missing observation at/after 15:10 are `INSUFFICIENT_EVIDENCE`.
- Baseline replays `evaluate_single_leg_exit` with paper bid fills,
  `calc_fno_costs` and live R (net / entry premium x FNO_STOP_PREMIUM_PCT x
  quantity). An exit with no positive basis is `UNRESOLVED`, never priced.
- Candidates are frozen in a manifest (parameters, live ladder settings,
  hard-flat minute, backstop percentage, source fingerprint):
  - `fno_partial_at_target_v1`: bank floor(lots/2) lots at the bid when the
    target arms the trail; the rest follows the live ladder. Fewer than two
    lots means identical to baseline.
  - `fno_confirmed_time_extension_v1`: defer a live time stop only while
    underlying progress is non-adverse, the underlying is within 0.5R of
    its best and the basis is at least 10% above the premium stop. All other
    exits are unchanged, and hard flat stays.
- Development/holdout labelling, exposure metrics and cost-stressed paired
  deltas as in S6a.
- Acceptance: baseline parity with the live ladder decisions, no future
  leakage, partial-lot arithmetic, unresolved basis, insufficient paths,
  manifest tamper refusal and adapter pairing/provenance.

Step 2 receipt (Dev, October 2): implemented as contracted. The S6a no-caller
guard caught cross-experiment helper reuse, so the summary arithmetic moved
to shared `exit_experiment_metrics.py` (included in both fingerprints), and
the guards were tightened to AST import checks. Tests: 15 new; 30
experiment/ladder tests warnings-fatal; 110 related suites. Remaining S6:
defined-risk spread exits (separate R and two-leg pricing), and every
operational holdout run.

### S7 — P2: opportunity-aware allocation and entry timing

Files/contracts: `proactive_intelligence.py`, `proactive_portfolio_research.py`,
`proactive_comparison_protocol.py`, `proactive_execution_research.py`,
`momentum_shadow.py`, `momentum_replay.py`, `momentum_paper.py`,
`engine.py`, `penny_engine_breakout.py`, `penny_engine_connors.py`;
locate actual consumers before editing.

Steps: use existing common-cash research to compare the current first-arrival
allocation with FIXED_EQUAL_V1 and RISK_BUDGET_V1 on chronological competing
opportunities. Record independent thesis identity, entry zone/no-chase limit,
invalidation, time horizon, costs, available capital and expected net reward.
Add at most two initial entry hypotheses: completed-bar continuation and
bounded pullback entry. Research stable-range mean reversion later as a
distinct strategy. Re-entry requires a newly evidenced thesis/state, not a
blanket four-hour ban. Track rejected/near-miss setups in isolated shadow so
research can distinguish bad timing from spread costs or absent opportunities.

Compare fixed benchmark capital and cash-constrained realized paper equity
as separately labelled experiments. Account for fees/reservations and concurrent
or correlated exposure. Rank available candidates using a frozen transparent
policy; do not claim calibrated probabilities without calibration evidence.
Use the operator-confirmed real budget for capacity analysis, not the large
paper pool. Do not reduce a losing strategy's reported loss by changing size
and then call that improved expectancy.

Acceptance: simultaneous candidates, input-order permutations, no cash,
fees, partial exits, capital release, correlated positions and restart cannot
overspend or duplicate admission. Report NOT_SELECTED/CAPITAL_UNAVAILABLE as
opportunity outcomes. Compare net return, drawdown, turnover, cost burden and
capital use on independent future sessions. Paper-only pilot of a reviewed
winner, with immutable allocation version and baseline fallback.

### S8 — P2: daily learning and strategy selection

Files/contracts: proactive comparison/research modules, `fno_audit_report.py`,
`momentum_paper_audit.py`, `penny_shadow.py`, `momentum_shadow.py`,
`strategy_health.py`, research/dashboard views.

Steps: produce a daily decision-quality report per book/mode/policy/setup/regime.
Join exact opportunities through admission, management and cash; keep legacy
unknowns explicit. Explain entry delay, missed allocation, thesis failure,
successful hold, exit giveback and execution cost. Label best-winner-excluded
sensitivity and version-specific drawdown instead of conflating win rate with
edge. Freeze one subsequent experiment at a time; retain rejected hypotheses.

Acceptance: independent opportunity counts, correct partial/final cash,
repeatable source lineage, no mixed R sum presented as portfolio return,
no hindsight-optimal exits. At least one rejected hypothesis remains visible.
Learning proposes versioned changes; it cannot silently retune active trades,
increase live capital or inherit an old partner qualification.

### S9 — P1 alongside research: accurate operator state and backlog handling

Files/contracts: `penny_health.py`, `main.py`, `operator_status.py`,
`node-gateway/server/routes/health.js`, signal/callback/executor routes,
gateway Telegram/dead-letter services and dashboard consumers.

Steps: expose attempted/completed scan clocks, data age, login/market phase,
management lag, cash by book and qualification blockers. Separate live request,
paper admission and advisory clocks while retaining old API fields for clients.
Investigate stale penny completion versus partial/failing scans with a minimal
reproducer before declaring a metric bug. Telegram's hard-coded connected field
must be labelled diagnostic or backed by real transport evidence.

Expire intraday requests at their actual validity/session boundary with an
audit trail; callbacks independently reject stale EXEC. For the five existing
pending records, use a reviewed dry-run reconciliation report and supported
expiry migration, not ad-hoc Production SQL. Resolve the three cancelled and
one rejected unsynced order idempotently without fabricating fills. Historical
dead letters receive explicit acknowledgement/resolution; never silently
delete them or resend stale trade instructions. Refresh/validate holiday data
through the existing official-source workflow; do not infer labels from audits.
Use existing daily-login/token validation; investigate authentication failures
instead of an invented automatic eight-hour token-refresh schedule.

Acceptance: no-trade healthy session, missing token, slow provider, old failed
alert, expired callback and qualification blocker render accurately. Existing
clients still work; read-only health cannot place orders or alter queues.
No broker order is needed to test readiness reporting. No diagnosis conflates
the momentum paper balance with penny cash again.

Rollout/rollback: additive API/UI fields; explicit backlog actions have dry-run
and receipts. Preserve old records on rollback and use GitHub promotion only.

### S10 — P1: useful optional AI reviews without immediate source expiry

Added after the owner reported frequent `AI review UNAVAILABLE
(AI_REVIEW_EXPIRED) - unreviewed` alerts. This is a planning addition, not an
implemented fix or a reason to block autonomous paper entries.

Availability boundary: an unavailable, timed-out, quota-limited or otherwise
failed optional AI/API review must remain non-blocking when the configured
policy is `proceed`/`advisory`. The deterministic paper lifecycle and the
separate owner-EXEC path continue with an explicit `UNAVAILABLE`/`UNKNOWN`
annotation; neither may be silently converted into an AI approval. Only an
already explicit, deliberately configured blocking policy may block on review
state, and its operator-visible reason must identify that policy rather than
misrepresent a provider outage as a market or risk decision.

Investigation evidence:

- Production has `MINIMAX_ASYNC_REVIEW_ENABLED=true`, news classification on,
  unavailable policy `proceed` and momentum rejection policy `advisory`.
- `queue_optional_ai_review` maps a submission state EXPIRED to the exact
  owner-visible AI_REVIEW_EXPIRED text. `_effective_classification_expiry`
  and `async_reviews._bound_expiry` take the minimum expiry across every
  classification. An undated item's missing source validity falls back to
  its already-past classification timestamp; a stale source has a past expiry.
- An isolated, read-only reproduction of the actual deployed expiry function
  gave 90 seconds for fresh evidence, -1 second for fresh plus undated evidence,
  and -86,400 seconds for fresh plus stale evidence. The last two reject the
  review before queue admission/provider execution. This is a reproduced
  code defect affecting optional annotation availability.
- October 1 logs show classifier APITimeoutError around BRIGADE, BANDHANBNK
  and IDFCFIRSTB alert creation. The retained AI status reports zero analyst
  requests, zero completions and zero cache misses. That is consistent with
  pre-submission expiry, not evidence that the analyst provider took 90 seconds.
  Exact per-alert source clocks were not retained, so the specific offending
  headline in each historical alert is not proven.
- A second path can expire reviews: the default request deadline is 90 seconds,
  but analyst wall timeout is 100 seconds with 45-second transport attempts and
  one retry. A single worker can queue 16 tasks. The worker does not forward
  task `expires_at` to `analyze_with_minimax`, so it can spend time on a request
  whose remaining budget is much shorter. This is a code-path hazard, not the
  established explanation for today's zero-request status.
- The initial alert can say PENDING and then mark the signal processed.
  The pipeline skips it on subsequent polls; no completed-review update to
  that original Telegram message was found. A successful worker review can
  therefore remain invisible to the operator.

Files/contracts: `agent/agent.py`, `agent/async_reviews.py`,
`agent/news_classifier.py`, `agent/advisory.py`, `agent/tests/test_async_reviews.py`,
`agent/tests/test_agent_pipeline.py`, classifier/provenance/contract tests;
`python-engine/optional_ai_status.py` and its validator tests if bounded status
fields change. Use current MiniMax; Jev remains deferred.

Steps:

1. Add minimal regressions for mixed fresh/stale/undated sources. Separate
   unavailable source evidence from review lifetime: expired/unverifiable
   headlines cannot support current catalyst claims, but must not poison a
   fresh market-signal review. Retain explicit exclusion counts/reasons.
2. Construct one sanitized review context used consistently by prompt text,
   classifications, source references, expiry and cache digest. Pruning only
   classifications while keeping stale text in raw sentiment is insufficient.
   An all-unusable-news case may review deterministic market facts with
   explicit NEWS_UNAVAILABLE; it must not invent a catalyst. Preserve the
   legacy explicit blocking policy when deliberately configured.
3. Keep genuine signal/source TTLs. For valid included evidence, review expiry
   is bounded by signal validity, included source validity and the configured
   annotation deadline. Do not extend source lifetime to eliminate the banner.
   Keep UNKNOWN classifications distinct from invented APPROVE results.
4. Forward the exact task deadline to reviewers that accept it. Account for
   queue wait; bound transport/retry/wall time by remaining budget with cleanup
   margin. Skip already-expired work before spending quota/provider time, and
   prevent detached timed-out calls or stale worker completion from exhausting
   the worker. Preserve compatible test/custom reviewer signatures.
5. Separate submitted/pending/ready/expired-before-submit/expired-in-queue/
   expired-after-call and source-unavailable counters. Include bounded stage
   timing and expiry cause, without source text, prompt, credentials or private
   review content crossing the status bridge. READY service capability must
   not imply a signal was reviewed. Distinguish classifier latency/failure
   from analyst latency/failure; diagnose the one-second classifier timeouts
   separately before changing their budget.
6. Make completed annotations visible through a bounded, idempotent update
   linked to the original signal/message if still valid. Retain message identity
   and completion state; use a tested completion consumer rather than removing
   signal dedup or resending an entry alert. The update cannot change price,
   quantity, stop, EXEC validity or approval authority; it cannot retroactively
   veto an open trade. If the signal expired, retain a diagnostic instead of
   publishing a fresh actionable button/card.

Acceptance: mixed-source reproduction now permits a bounded honest review;
only stale news cannot be represented as current evidence; fresh-source expiry
still applies. Tests cover no-news, classifier timeout, shortened cache expiry,
source-context changes, slow first task/two queued signals, completion at the
exact deadline, provider retry, worker shutdown and late result. A completed
review reaches its one matching valid alert once, while expired/restarted
signals cannot create duplicate alerts or new authority. Paper admission and
owner EXEC tests remain unchanged. Add source-exclusion/expiry counters to the
bounded allow-list and contract tests explicitly, never accept arbitrary keys.

Rollout/rollback: first correct source/context expiry and deadline propagation
with offline tests; then independently add observability and completion
delivery. Deploy through GitHub and inspect genuine fresh-signal receipts.
Rollback restores the previous annotation path, preserves diagnostic evidence
and message identity, and leaves paper/real-order authority intact. Proposed
effort 2–4 engineering days including completion delivery; run alongside S3/S4
after S1/S2. No provider request, new message or configuration change was made
to investigate this report.

## 4. Delivery sequence and estimated effort

These are engineering estimates, contingent on reproductions, not promised
completion dates or profitable trading dates.

| Batch | Work | Indicative effort | Completion evidence |
|---|---|---|---|
| A | S1 exact DR economics/settlement; S2 management clock/read containment | 3–5 engineering days | Negative controls, migration/recovery tests, no invented settlement, bounded management |
| B | S3 retention; S4 equity paths/admission capital evidence; S5 collection coverage | 3–5 engineering days, partly parallel | Full preserved session and exact replay inputs; candidate-level coverage report |
| C | S9 operator state/backlogs; S5 frozen research protocol | 2–4 engineering days | Correct book/health display, tested expiry/reconciliation, immutable protocol |
| C-AI | S10 source/context expiry, remaining deadline, visible completion | 2–4 engineering days, partly parallel | Useful current annotations; explicit expiry cause; no stale claims or trading-authority change |
| D | S6 exit comparison; S7 allocation/entry comparisons; S8 daily learning | 4–8 engineering days for tooling/integration plus future observations | Costed, paired reports and a versioned paper pilot only if review supports it |
| E | S5 qualification review and authorized message canary | At least the planned 20 trading-session observation window; longer if too few complete closes or review fails | Compatible qualification package and acknowledged timely message lifecycle |

Start S1 immediately when implementation is requested. S3 can proceed after
its own plan/reproducer without waiting for strategy research. Freeze future
study criteria as soon as coverage permits; partner research is not delayed
until all owner allocation research finishes. Existing evidence supports
diagnostics now, not backdated holdout. Do not promise tips on a fixed calendar
date: authorization, qualification and a fresh qualifying setup all matter.

## 5. Verification and release ritual

Each slice starts with a minimal failing reproduction, explicit affected
contracts and dependency inventory. Verify the source differs from the control
only within that slice. Run focused tests and affected integration suites;
broaden to full release tests for migrations, shared market-data admission or
runtime behavior. Tests use temporary databases/archives, simulated providers
and network-disabled broker/Telegram boundaries, never Production mounts.

Examples from `python-engine` using the existing Windows environment:

```powershell
.\winvenv\Scripts\python.exe -m pytest tests/test_fno_defined_risk.py tests/test_fno_orchestrator.py tests/test_fno_exit_recovery.py tests/test_fno_exit_recovery_boundary.py tests/test_scheduler_real_path_isolation.py -q
.\winvenv\Scripts\python.exe -m pytest tests/test_research_archive.py tests/test_research_quote_collection_deadline_p1.py tests/test_research_leg_subscriptions.py tests/test_partner_research_capture.py -q
.\winvenv\Scripts\python.exe -m pytest tests/test_momentum_paper.py tests/test_momentum_paper_audit.py tests/test_momentum_paper_evidence_review.py tests/test_momentum_exit_study.py tests/test_momentum_square_off_deadline.py -q
.\winvenv\Scripts\python.exe -m pytest tests/test_partner_qualification_review.py tests/test_partner_qualification_package.py tests/test_partner_qualification_verify.py tests/test_research_cli_qualification.py -q
```

Add the new slice-specific reproductions to these commands; the existing suites
alone do not prove new behavior. Use warnings-fatal runs for pure modules and
record framework/runtime warnings separately; do not suppress a leak. For
gateway changes use the supported Node/native-SQLite runtime and callback,
executor, signal, health and dead-letter tests. Run dashboard tests/build after
changing public response fields. Verify Compose through the existing logging
verifier; print only approved diagnostic fields, never rendered secrets.

Update guide, active plan, checklist and verification receipts with each source
commit; regenerate the atlas after source/declaration changes. Verify the actual
commit and docs immediately. Record SHA, commands/results, environment limits,
config/migration effects and local/pushed/deployed status. Before rollout use
the existing consistent-backup/restore and deployment-identity procedures.
Rollback through GitHub; retain new evidence, newer cash and unresolved exposure.

## 6. Planning receipt and remaining uncertainties

This turn only created this plan and linked it from Dev handover documents.
No source/config changed; atlas regeneration and software test runs are not
applicable. Planning documents remain local/uncommitted unless subsequently
recorded otherwise. Existing dirty fixture/audit/artifact files were preserved.
Documentation verification: `git diff --check` passed; the new plan has no
trailing whitespace; named focused test files and the existing Windows Python
runtime were checked for existence. Four Dev documentation files changed.

Read-only checks: `docker ps`/targeted `docker inspect`; `docker exec ... python
-c` with SQLite URI `mode=ro`; source `rg`/`Get-Content`; retained master lookup;
collection-run gap aggregation; `build_momentum_paper_decision_audit` read-only.
Prior-turn archive verification confirmed September 28–29 raw hash/event count.
The default root Python in the engine lacks user-installed dependencies;
configuration probes use `docker exec --user quantuser` rather than installing
packages. No new software correctness or profitability test result is claimed.

Still to establish: exact DR entry packet/expiry binding for historical rows;
whether a DR write failure actually occurred (only code hazard established);
whether equity paths exist in another retained source; latency root cause
split between provider/limiter/DB; true penny completion failure versus metric
state; future-held-out strategy results and separately authorized transport.
An IN_FLIGHT telemetry row is not evidence of an open position. A successful
paper close is not evidence of broker readiness. Empty quarantine/feedback
tables can be normal and are not development requirements by themselves.
