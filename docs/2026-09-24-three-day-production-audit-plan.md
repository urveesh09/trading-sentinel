# Three-day Production audit reconciliation and implementation plan — 24 September 2026

## Boundary and evidence

This is a read-only assessment of the 22–24 September Production audits and
current Production evidence, checked against Dev source at `4174feb` and
Production source at `782bbb7`. It is a plan, not a change to Production,
deployment approval, broker action, partner message or profitability claim.
Production is the evidence source; all future source/config changes belong in
Dev and must be promoted through GitHub. The audits have partial log coverage,
so absence of a log line is not proof that an event did not occur.

The recorded ledger day totals reconcile: 22 September +₹569.13, 23 September
+₹796.68 and 24 September +₹951.99. The 22 September total includes the
BANDHANBNK partial +₹326.73 and its later close component; adding those again
to the trade's reported +₹689.06 would double-count. These are paper-ledger
outcomes, not an estimate of live net expectancy. Three DR outcomes do not
validate a strategy or its risk-adjusted edge.

## Auditor claims corrected before implementation

| Audit claim | Checked conclusion | Consequence |
| --- | --- | --- |
| 24 Sep research average 9.7s and maximum 94s both exceed 60s | Only the maximum exceeds 60s. Long tails cause overlap; the average does not. 18 research `MAX_INSTANCES` skips occurred on 24 Sep. | Bound the tail and measure coverage before changing cadence. |
| Scheduler skips are intensifying from the 23rd to 24th | Aggregate `MAX_INSTANCES` was 74 then 58; audit log windows differ. On the 24th, 58 includes penny 21, research 18, F&O 15, bootstrap 3 and partner advisory 1. | No single cadence adjustment cures all jobs. Compare same active-session windows. |
| C.F2 research cap solves overlap | The 48s check occurs between NIFTY and SENSEX. The aggregate `provider_quote` stage reached ~93s; an individual quote call has no collector-level deadline. Of 358 active 24 Sep runs, 28 stopped after NIFTY. Normal runs omit `runtime_capped` and `elapsed_sec` because only early-return/error paths use the wrapper that adds them. | Confirmed collector contract bug plus unbounded per-call tail. |
| HIGH-007: classifier timeout default-approves and causes a momentum paper trade, for a third consecutive day | The engine opens the deterministic momentum paper baseline before the agent review. News classification is informational and returns `UNKNOWN` on failure, not `APPROVE`. Current `proceed`/`advisory` policy makes AI non-authoritative by design. The 23 Sep audit reports no visible timeout, so a consecutive-day claim is unsupported. | Do not suppress paper trades or invert AI authority. Investigate only the classifier's apparent 1s versus ~2.5–2.9s wall-time discrepancy. |
| `max-file: 10 → 25` guarantees ~12 days of logs | Effective driver is `json-file`, `20m × 10`. The audits show a morning coverage gap, but the 22 Sep audit contradicts itself (`--tail 10000` has 8,422 same-day lines while a larger tail reportedly has none). Gateway extraction used only `--tail 1000`. At a true 200 MiB/day, 25 files would hold only about 2.5 days, not 12. | Measure retained-file bounds, byte rate, extraction method and disk headroom first. |
| Six newly blocked NIFTY SHORT signals prove a new kill switch and otherwise-ready entries | Production DB shows six evaluations of two bar timestamps, three evaluations per bar. `kill_switches_clear` is an existing gate and only proves an active switch was returned; earlier gates' pass state and switch identity need checking. | Preserve fail-closed behavior; trace switch reasons, avoid treating six rows as six independent opportunities. |
| `fno_tick_overrun` at 93.231s on a 90s cadence needs no action | The warning is useful but records an actual overrun; it does not cap or cancel the job. Fifteen 24 Sep F&O skips require separate diagnosis. | Inspect the stage tail and exit-management latency before changing a risk-management cadence. |
| Pending `fno_exit_recovery.py` is the DR debit-spread recovery DR needs | The Dev recovery route is scoped to `FNO_LIVE` single-leg `fno_positions`; DR uses `fno_dr_positions` and separate execution. It does not repair or validate DR exits. | Promote/rehearse that change for its actual scope only; assess DR reconciliation separately from broker evidence. |
| 23 Sep deploy already makes ambiguous partial F&O fills settle cleanly | The Dev-only recovery increment handles verified terminal partial/zero/full single-leg exit intents. Production still runs `782bbb7`; an ambiguous dispatch remains blocked without operator broker evidence. | Do not infer Production recovery coverage from Dev tests or the earlier intent persistence. |

## Ordered work and acceptance

### P0 — Restore decision-forensics coverage without guessing retention

Problem: all three audits have partial morning Python coverage; the exact loss
mechanism and logging volume are not yet proved. Read-only Production checks:
record `docker inspect` log driver/options/path and retained file count, bytes
and first/last timestamps; compare bounded `docker logs --since/--until` with
large-tail extraction; count health/access versus decision/event lines per hour;
measure host/container disk headroom. Record gateway bounds separately. Never
expose tokens, requests or account data in the evidence bundle.

If rotation is confirmed, make a Dev Compose/logging change sized from measured
bytes per day and desired retention, with disk budget and an explicit rollback.
Consider suppressing only noisy health access lines if proven dominant, while
retaining errors and decision logs. Do not install an ad-hoc archive cron or
raise `max-file` to 25 on an unsupported 12-day estimate. Acceptance: an
independent audit can retrieve opening-to-close decision logs for at least
three consecutive logged-in sessions, with measured disk use and no missing
errors/health alerts. Gateway and Python are verified separately.

**P0 Dev result (24 September):** Read-only Production inspection found
`python-engine` and `node-gateway` each on `json-file`, `max-size=20m`,
`max-file=10`. Python retained one unrotated 18.13 MiB file spanning
35.897 hours (84,397 lines; 0.50 MiB/hour across that observed period), and
gateway retained one unrotated 2.07 MiB file over the same period. The current
per-container ceiling is therefore 200 MiB, about 400 observed Python log
hours; it already comfortably covers one complete market session and does not
justify an unmeasured increase. Host C: had 104.42 GiB free; Docker reported
7.865 GiB images, 4.364 GiB volumes and 30.85 GiB build cache (21.47 GiB
reclaimable). This is a bounded observation, not a peak-rate guarantee or a
three-session operational receipt.

No Compose value changed: rotation was not confirmed and changing a working
200 MiB bound would be guesswork. Dev adds
`scripts/verify_compose_logging.py`, which calls `docker compose config
--format json` and asserts only the rendered `python-engine` driver,
`max-size`, `max-file` and minimum 200 MiB ceiling without printing rendered
environment values. It fails closed on absent/malformed/non-`json-file`
logging. The focused assertion and unit tests are the Dev acceptance; post-
promotion acceptance remains a read-only `docker inspect` plus opening-to-
close retrieval for three logged-in sessions. Docker logging options take
effect only when the container is recreated, so there is nothing to recreate
for this no-value-change result. If a future measured peak proves the bound
insufficient, make a separately reviewed Compose change through GitHub; roll
back that change through GitHub if it causes disk pressure or log loss, without
deleting retained logs or evidence.

Dev verification: `python-engine/winvenv` ran the new focused verifier suite
with **8 passed**; `python scripts/verify_compose_logging.py` and a separate
`docker compose config --format json` inspection both resolved
`python-engine` to `json-file`, `20m × 10`. The host's system Python has no
`pytest`, so the repository virtual environment is required for this test.
No Production file, service, container, data volume, Telegram route, broker
route or Compose runtime was changed.

### P1 — Fix research collection deadline and truthful coverage (Dev code)

Files/contracts: `python-engine/research_quote_collector.py`, the read-only
quote transport in `python-engine/kite_client.py`, relevant collector/transport
tests, `scheduler_setup.py` only if later evidence warrants cadence changes.
First write a failing test through `research_quote_collection_tick` showing a
slow first underlying, omitted cap fields and an unreported second-underlying
gap. Make the final journal and returned result consistently include elapsed,
cap status, partial count and explicit skipped-underlying/active-leg gaps on
normal, timeout and error paths. No fabricated packets or valid-looking stale
receipts. Bound each provider operation to the remaining tick deadline and
verify cancellation, transport cleanup and shared-client safety; a thread that
continues after cancellation is not an acceptable hidden leak. Preserve
NIFTY/SENSEX and selected-leg coverage fairness across capped ticks.

Acceptance: deterministic stalled-quote tests finish within the deadline,
leave no orphan operation, journal the exact gap and do not cause a next-slot
overlap; normal-path tests persist the same telemetry. Run focused collector,
Kite-client, scheduler and research suites, then the full engine suite with a
natural process exit (or label the known aiosqlite test-runtime limit rather
than claiming a pass). Observe at least three real logged-in sessions:
per-underlying requested/received active legs, cap count, p50/p95/max stages,
overruns and skipped slots. Keep 60s collection cadence initially. Only decide
on 120s after measuring whether the lost half of sampling is acceptable to
held-out research and active-leg evidence; update both schedule and declared
interval if authorized.

**P1 Dev result (24 September):** `research_quote_collection_tick` now passes
the remaining 48-second tick budget into every future-reference and selected-
contract provider call. The collector uses `asyncio.wait_for`, which cancels
and joins the provider coroutine before the tick returns; it does not detach a
late request onto the shared Kite client. The existing read-only Kite transport
remains shared and unmodified: its rate-limiter/HTTP await is inside that
cancellation boundary, so no separate client is created, closed, or leaked.

Every scheduler result and its durable `collection_run` now records
`runtime_capped`, `elapsed_sec`, `runtime_cap_sec`, `partial_collected` and
`partial_count` on normal, deadline and error outcomes. Each configured index
has a truthful `collection_state`; a deadline emits
`provider_deadline_exceeded` for the interrupted NIFTY/SENSEX stage,
`underlying_skipped_runtime_deadline` for later underlyings, and either exact
`active_leg_unobserved_runtime_deadline` tokens already read or the explicit
`active_leg_coverage_unobserved_runtime_deadline` unknown. It never labels an
unobserved leg as received or manufactures a replacement packet. Empty/error
batches similarly receive a named state rather than appearing as normal
completion. To prevent a cap from repeatedly favoring NIFTY, the first index
rotates deterministically by UTC scheduler slot and the selected
`underlying_order` is retained in the run; this remains stable across process
restart without a mutable in-memory toggle.

The new scheduler-entry regression stalls NIFTY's first provider operation,
observes cancellation, verifies the bounded return and persisted telemetry,
and verifies explicit NIFTY active-leg and SENSEX skipped coverage. A normal
two-index run verifies the same persisted telemetry. Focused collector/archive/
subscription/scheduler tests passed **54**; the complete `test_research_*`
surface passed **62**; the combined collector/scheduler/Kite-client regression
surface passed **173** with one skip and one pre-existing Starlette
async-generator-lifespan deprecation; `py_compile` passed. The legacy runtime-cap assertions
were updated so a capped index is now explicitly auditable instead of absent.
The 60-second schedule and 48-second cap did not change. Production was not
edited, deployed, restarted, queried for mutation, sent a Telegram message or
allowed to place an order. Operational acceptance still requires three real
logged-in sessions with per-index coverage, cap and stage-latency observations;
this code does not make a research or partner-advice qualification claim.

### P1 — Diagnose F&O tick tail independently (evidence first)

The 24 Sep 93.231s tick and 15 `MAX_INSTANCES` skips justify a targeted
read-only breakdown of `stage_durations_sec`, broker/limiter wait, DR exit and
single-leg exit stages, with one-to-one mapping between skipped slots and
completed runs. The audit's 74 `MAX_INSTANCES` events on 23 Sep are for all
jobs, not 74 proven F&O skips. Investigate the 23 Sep 9.6s average/112s
maximum and any F&O-specific skips using comparable retained windows; do not
attribute latency to the remediation deploy without pre/post stage evidence.
Use existing scheduler telemetry, structured `fno_tick_complete` stage
durations, F&O tests and broker/limiter instrumentation to isolate the slow
stage. Prioritize exit monitoring and risk-boundary latency over entry
frequency. Write a minimal stalled-stage reproducer before changing code, then
implement only the smallest demonstrated Dev mitigation (for example, bounding
an identified noncritical wait) without broad scheduler rewrites.
Acceptance for any fix: exit evaluation remains on time, unknown broker state
fails closed, no duplicate orders/intents appear, and an observed session has
no avoidable 90s overrun. Focused regression tests must cover a stalled stage,
entry and exit cutoffs, missing broker evidence, and the unchanged fail-closed
path; run the F&O/scheduler suites and review the resulting telemetry fields.
Do not increase the 90s interval merely to hide a slow exit path. DR broker
reconciliation, if truly needed, is a separate scoped design/evidence decision,
not covered by single-leg recovery. Roll back through GitHub if exit latency
or unknown-state handling worsens.

**P1 F&O Dev result (24 September):** Read-only retained Production logs were
aggregated by day before source changes. They contain 236 `fno_tick_complete`
records on 23 Sep (maximum 111.480s; 12 at/over the 90s cadence) and 233 on
24 Sep (maximum 93.280s; 15 at/over cadence), plus 27 retained APScheduler
F&O `MAX_INSTANCES` skips. Every at/over-cadence record reported zero DR opens
and exits. The repeatable tail was `defined_risk` (up to 75.799s/76.203s),
with variable quote/history waits; this proves the observed avoidable work was
paper DR entry preparation, not an active DR lifecycle action. The retained
window is evidence for that conclusion only; it does not prove every historic
skip or broader scheduler latency has the same cause.

Dev now sets `FNO_DR_ENTRY_MARKET_DATA_MAX_SEC=20.0` and applies one shared
deadline only to the cancellable chain-snapshot and futures-history reads that
prepare a *new* paper DR structure. A timeout cancels and joins the underlying
coroutine through `asyncio.wait_for`, emits a named `dr_entry_skip_reason`, and
does not continue with an admission. Existing DR management—including an
unpriced hard-flat fallback—single-leg exits, and a database admission write
are explicitly not deadline-cancelled. Successful inputs still flow into the
directional leg as the same tick-local snapshot/bar view, preserving its
one-fetch contract. The tick exposes separate `defined_risk_snapshot`,
`defined_risk_management`, `defined_risk_entry_inputs`, and
`defined_risk_entry_admission` durations so the next operational trace can
distinguish a true risk-management delay from a speculative-entry delay.

The deterministic stalled-input regression verifies cancellation/join, bounded
return, explicit reason and no order; existing F&O/DR/scheduler tests retain
entry/exit, hard-flat and fail-closed coverage. The full F&O and scheduler
regression surface ran 357 tests successfully with two pre-existing
deprecations, plus Python compilation. This is a Dev-only mitigation. After reviewed GitHub
promotion, collect a comparable logged-in session and inspect the new fields;
do not alter the 90-second cadence or infer resolved active-exit latency from
this test result. Production was never edited, restarted, deployed, sent an
order or sent a message.

### P1 — Explain TATATECH acceptance without a paper opening

The 23 Sep audit has two `ACCEPTED` TATATECH momentum-signal rows, fifteen
minutes apart, but no paper opening; the cause is not established. Trace the
two signal identities and timestamps through accepted-signal generation,
same-day alert deduplication in `python-engine/main.py`, and
`open_momentum_paper_positions` in `python-engine/momentum_paper.py`. Compare
the position already held at each attempt, sizing inputs and available paper
capital, feature enablement, relevant entry-halt state, transaction result,
and retained event/log evidence. An owner live-entry halt must not be reported
as a paper-book veto unless the actual call path proves it; the paper baseline
has separate authority. Do not infer success solely from `ACCEPTED`, or infer a
bug solely from the absence of `trade_outcomes`.

Implement a bounded, durable admission outcome keyed to the accepted signal
and paper-book attempt (or an equivalently retained structured event) with a
small enumerated result/reason: opened, already-held, zero-shares, disabled,
upstream-deduplicated, actual halt/gate, or transaction failure as applicable.
Make the outcome truthful after commit/rollback, idempotent across repeated
scans, retention-bounded, and free of credentials or full signal payloads.
Record upstream skips at their actual boundary; do not claim the paper opener
made a decision it never received. Preserve the current paper-only authority,
capital/risk sizing, no-duplicate guarantee and nonfatal screener hook.

Acceptance: focused tests reproduce TATATECH-like duplicate accepted rows,
already-held, zero-shares, disabled/halt only where actually wired, and a
database failure; each accepted signal has an explainable outcome or explicit
upstream deduplication, no extra position/order is created, and a rolled-back
insert is never marked opened. Update the guide/active plan and atlas if source
declarations change. Rollback must leave existing positions and ledger intact.

**P1 TATATECH admission-forensics Dev result (24 September):** The new
`momentum_paper_admission_outcomes` table retains an opaque SHA-256 signal
identity, ticker, enumerated outcome/reason and timestamp—not a full signal
payload. Its allowed outcomes are `opened`, `already_held`, `zero_shares`,
`disabled`, `upstream_deduplicated` and `transaction_failure`. Entries are
idempotent by immutable attempt identity and retention-bounded by
`MOMENTUM_PAPER_ADMISSION_RETENTION=20000`. A fresh attempt after a legitimately
closed paper position gets a separate immutable key; repeated scans of the same
active decision do not create another position or outcome.

`open_momentum_paper_positions` creates/updates the evidence within its same
SQLite transaction as the paper position. It writes `opened` only after its
position insert is pending for commit; an exception rolls every opening back,
returns no opened ticker and records `transaction_failure` in a fresh evidence
transaction when SQLite is still available. If SQLite itself cannot be opened,
the failure is logged rather than manufactured as a durable outcome. The
existing paper-only/no-order module boundary, capital sizing, held-ticker fence
and nonfatal screener hook are unchanged.

`main.py` now gathers repeated accepted signals while it applies the existing
same-day alert deduplication and calls the dedicated writer for
`upstream_deduplicated`. This is intentionally outside the paper opener: it
truthfully says the opener never saw that signal. The focused paper, regime and
real screener-boundary suite covers TATATECH-like repeats, held, zero-share,
disabled, rollback and retention paths, as well as real dedup wiring. No
Production file/service/data, broker action, Telegram message or qualification
state changed. Focused momentum/regime/entry integration validation ran **159
passed** with one existing Starlette deprecation. Post-promotion, compare admission outcomes to retained accepted
signal rows before explaining a real absence; this code does not establish
profitability or authorize partner advice.

### P2 — Tighten classifier latency only, not its authority

Files/contracts: `agent/news_classifier.py`, client construction in
`agent/agent.py`, and classifier/pipeline tests. Reproduce a delayed client
with its configured retry behavior; determine if the shared client's retry or
transport causes a one-second timeout argument to take ~2.5–2.9s. If owned,
use a classifier-specific no-retry client or another genuinely bounded call
that cannot leave work running, without changing the full reviewer retry
policy. Timeout remains `UNKNOWN`; deterministic paper capture and
`proceed`/`advisory` authority stay unchanged. Acceptance: wall-clock-bound
test, provenance/UNKNOWN fallback and unchanged paper/reviewer contracts.

**P2 classifier-latency Dev result (24 September):** Source review reproduced
the owned budget mismatch without calling a provider: `news_classifier` passed
its 1.0-second timeout into `agent.client`, while that client was configured
with `MINIMAX_MAX_RETRIES=1`. A retryable timeout could therefore make a second
transport attempt inside a classifier operation. Dev adds a separate long-lived
`classifier_client` with `CLASSIFIER_MAX_RETRIES=0` and routes both
`_maybe_classify_news` and the classifier's implicit fallback to it. The
existing analyst `client` remains configured with `MINIMAX_MAX_RETRIES`; no
review retry, prompt, policy or authority changes.

The classifier still passes its declared per-item timeout to the SDK and does
not start a thread, task or retry loop of its own. A deterministic timeout
regression verifies one call, bounded wall-clock return and the existing
zero-confidence `UNKNOWN` result; construction/wiring tests pin the zero-retry
client rather than assuming the shared reviewer configuration. The full agent
suite passed **361 tests** and compilation/atlas regeneration passed. This
eliminates the repository-owned retry tail but does not promise external API
latency, establish a trading edge, authorize advice or alter the deterministic
paper/review paths. Production was not edited, restarted, messaged or sent an
order. Post-promotion, inspect real classifier elapsed/error telemetry before
considering any provider-specific timeout adjustment.

### P2 — Audit rows and financial interpretation

Explain the 24 Sep two-bar/six-evaluation F&O pattern, log/inspect the actual
switch name and confirm its threshold/evidence without weakening it. Verify
the prior gate witness before saying a blocked signal would have traded.
Keep partial and close ledger events distinct in audit reports. A financial
review must reconcile per-pool day totals and identify paper versus live
activity, costs and sample size; no positive-expectancy declaration from three
DR trades or a profitable day.

### Release and product gates — distinct from fixes above

Dev HEAD `4174feb` is ahead of deployed Production `782bbb7`; the pending
single-leg recovery, qualification package and test-bootstrap work need
reviewed GitHub promotion, backups/migration rehearsal and stamped running
image verification. Promotion is not authorized by this plan. The current
full-engine natural-exit issue remains test-runtime hygiene: isolate a minimal
aiosqlite leak reproducer before altering application teardown. Real broker
reconciliation, real completed-bar/selected-leg collection, future holdout,
independent review, saved partner profile and an explicitly authorized canary
remain separate evidence/operator gates. The partner is still unqualified for
tips; none of these paper P&L figures supplies a delivery timeline.

## Rollout and rollback for implementation slices

For each Dev slice, preserve existing untracked audits and edited golden
fixtures, write a failing reproducer, update this plan and `SYSTEM_GUIDE.md`
with the actual contract, regenerate the code atlas when source declarations
change, run proportional cross-component checks, then commit and immediately
verify docs/plan consistency. GitHub promotion requires operator review and
retained data backup. A failed observation rolls back through GitHub to the
last stamped image; never delete ledger, research archive, broker evidence or
unresolved F&O exit intents. Record Dev-only, pushed and deployed identities
separately.
