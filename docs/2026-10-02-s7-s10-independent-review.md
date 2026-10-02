# Independent continuation review — October 2, 2026

## Scope and correction plan (before implementation)

Review baseline: Dev `f9dd40af43553036c5fa43d9cdbd558bfeb284db`, including
the other agent's four uncommitted S10 files. The local remote-tracking branch
also points at that commit. Production is read-only and is not restarted.
Existing fixtures, audit evidence and Jev artifacts are unrelated and preserved.

1. **Small S10 correction:** preserve deadline forwarding and signature
   compatibility, but recompute remaining time at provider dispatch and wall
   wait; disable SDK retries on the deadline-bound request only. Files:
   `agent/agent.py`, `agent/async_reviews.py` and their focused tests.
   Acceptance: no call with insufficient budget, prompt-building time deducted,
   request timeout below remaining wall, retry override verified, late answer
   unavailable, legacy no-deadline call unchanged. A socket timeout is not
   proof that an arbitrary stuck transport has been cancelled.
2. **Small S8 correction:** daily cash must include exits of earlier admissions
   and be ordered by event clock, not admission order. Ambiguous ordering must
   not manufacture drawdown. Files: `python-engine/daily_decision_quality.py`
   and its tests. Acceptance: overlapping trades, earlier-day admission,
   equivalent UTC/IST clocks, legacy UTC clocks and equal-clock ambiguity.
   Do not claim policy-version drawdown without recorded version lineage.
3. **Small S7 freeze correction:** bind allocation fees and timing evaluator
   settings/fees to manifests, and reject an unknown timing deadline policy.
   Acceptance: runtime-only fee/exit overrides reject evaluation despite an
   unchanged source fingerprint. Earlier freezes must be replaced before new
   future evidence, never retroactively edited or relabelled HOLDOUT.
4. **Minimal test-runtime correction:** remove the unused current-loop lookup
   in `tests/test_partner_orchestrator.py::wired`. Reproducer: run daily-quality
   tests followed by `test_disabled_is_a_total_noop`; its synchronous fixture
   raises after `asyncio.run` clears the loop. pytest-asyncio owns the real
   test loop. No global event-loop policy or application change is permitted.
5. Review S3/S4 remediation, S6 spread, S7 allocation/timing and S9 source
   changes; document larger evidence-binding/research gaps instead of silently
   expanding this review into a redesign. Run affected suites and update the
   guide, active plan, checklist and regenerated atlas.

Rollout: Dev-only corrections, normal GitHub review/promotion; no broker calls,
messages, credentials, environment or migrations. Rollback: revert the reviewed
correction commit through GitHub; retain existing evidence. Momentum paper
remains autonomous and real-money momentum retains owner EXEC approval.

## Verification and remaining implementation

### Verdict

Substantial development is present, but **not all remaining work is merely
deployment or collecting another run**. The spread replay is a prototype, not
an exact-economics-bound qualified research pipeline. S8 is an initial daily
composer, not the complete learning report specified by S8. Existing source
completion statements are superseded by the status below.

Reviewed: `31badc9..f9dd40a` (40 files, 2,991 insertions), source contracts and
affected tests, plus the four uncommitted S10 files. This is a scoped independent
review, not an exhaustive re-audit of every application path or a fresh
Production financial/performance audit. Production Git HEAD remains `d90c775`;
that is not confirmation of the running image.

Small corrections made in Dev:

- S10: original task expiry forwarding retained; provider-dispatch and join
  recompute remaining time; deadline-bound calls override SDK retries to zero
  without changing the shared client's defaults. Transport timeout also fits
  the configured wall with cleanup margin. Completion at the exact deadline
  remains unavailable. Legacy calls without a deadline retain their behavior.
- S8: exits from earlier admissions count on their cash-event day; overlapping
  events are ordered in UTC, including legacy naive UTC clocks. Equal clocks
  without a ledger tie-breaker return unknown drawdown. `daily_cash_drawdown`
  describes the linked stream; `version_specific_cash_drawdown` is null because
  management-policy version lineage is not yet established. Cash coverage is
  explicitly bounded to linked admissions, not claimed as every ledger row.
- S7: timing manifests bind live evaluator settings and equity fees; allocation
  manifests also bind fees. Runtime-only drift is refused. Unknown timing
  deadline policies are refused. Old manifests lacking these snapshots are
  invalid; freeze new ones before future observations, not by editing old ones.
- Test hygiene: an unused `get_event_loop` in the synchronous partner fixture
  failed after daily reporting's `asyncio.run`. The eight-test reproducer failed
  before removal; 48 daily/partner tests pass afterward. No application loop
  policy was changed. News-source tests now supply genuinely current fixtures
  and model the request-local client, preserving their intended assertions.

### Reproduced larger findings — next implementation contracts

**R1 / P1 — finish S6 research evidence binding before interpreting results.**

`fno_dr_exit_experiment.py::_valid` verifies the hash of arbitrary supplied
bytes, not their contents against `DrEntry` or `DrObservation`. Its existing
fixture uses `b'exact-source'` and a one-leg structure and still returns CLOSED.
The source fingerprint is a constant phrase hash; `build_report` does not
validate it or the giveback parameter. Modifying both still returns CLOSED.
An observation with NaN exit cost returns CLOSED with NaN costs, P&L and R.
These are reproduced code defects, not a claim that a live trade was affected:
the module has no runtime caller.

Implement together in `fno_dr_exit_experiment.py` and focused tests:

1. Define a typed immutable source envelope binding exact structure/admission
   identity, entry clock, leg sides, tokens, expiry, lots/quantities, premiums,
   debit/credit, maximum loss/profit and original risk terms. Re-derive economics
   from those bytes and the retained contract master; a hash alone is integrity,
   not provenance or authentication. No ticker/date guessing.
2. Build observations from same-receipt exact-leg provider packets; verify each
   raw token, executable side, clock/age and finite price/cost. Enforce session,
   gap and hard-flat deadlines; do not trust caller-supplied P&L or a `hard_flat`
   boolean as proof. Missing/foreign/legacy/incomplete data is unavailable.
3. Freeze actual source hashes, runtime target/stop/flat terms, cost schedule
   and candidate parameters; verify every term at evaluation. Duplicate entry
   identities, nonfinite numbers and modified manifests must be rejected.
4. Reconcile baseline economics and cash to exact persisted entry/settlement
   identities before treating paired deltas as usable. Cost-stress comparisons
   and complete/no-entry/unavailable sample counts remain explicit.
5. Tests: correct key with wrong quantity/risk/premium/clock, unrelated packet,
   one-leg debit spread, duplicate/foreign leg, stale side, missing hard-flat,
   source/settings/fee drift, NaN/Infinity, duplicate IDs and baseline cash match.

`fno_exit_experiment.py::build_packet_from_archive_events` is improved, but a
600-second-old futures packet paired with a fresh option still emits one
observation and no exclusion. Only the option's normalized provider-clock
column is checked; that column is not re-derived from its raw packet. Changing
it also permits pairing. Finish this adapter in the same evidence slice:
derive/check clocks and raw token identity for **both** packets, require exact
contract identity, reject conflicting normalized columns, and bind caller
entry economics to immutable position/admission/cash evidence. Hashing archive
prices must not upgrade arbitrary entry quantities to verified economics.

Reproducer building blocks are the existing `_entry` in
`tests/test_fno_dr_exit_experiment.py` and `_event` in
`tests/test_fno_exit_experiment.py` (`provider_lag_sec=600` on token 999).
Rollout: research-only, no live exit change; freeze anew after correction.
Rollback preserves raw evidence and marks incompatible reports unavailable.

**R2 / P1 — S9 reconciliation tooling (still not implemented).**

Build an explicit read-only gateway reconciliation command/report over pending
requests/callbacks, terminal unsynced orders and historical dead letters.
Classify actual session/validity expiry and ambiguous/missing evidence; report
row identity, proposed action, reason and precondition fingerprint. A separate
supported, operator-reviewed idempotent migration should mark expiry/resolution
with an audit receipt, recheck preconditions transactionally, and retain rows.
Cancelled/rejected orders must not fabricate fills. Dead-letter acknowledgement
is not resend; never send historical trade instructions automatically. Test
repeat runs, races/new callbacks, unknown broker state, stale EXEC, crash/restart
and rollback. Applying it to Production requires separate operator approval.

**R3 / P1 — finish S10 observability and completion delivery.**

Add bounded submitted/pending/ready/source-excluded/expiry-stage counters and
classifier-versus-analyst timings to the explicit optional-status allow-list.
Then persist original signal/message identity and consume completions once,
updating only the matching still-valid original alert. Test retry, ambiguous
timeout, duplicate completion, restart, expired message and changed source
context. No new EXEC button, size, price, stop, approval, retroactive veto or
entry alert. The current daemon join is **not transport cancellation**; strict
single-inflight shutdown/cancellation and socket-phase overrun require their
own tests/mitigation before closing S10's no-detached-work acceptance. Paper
continues under the configured proceed/advisory policy.

**R4 / P1 — finish S3 durable retention/performance evidence.**

Rotation crash recovery is implemented and tested. Still implement explicit
CSV archive quota/free-space handling and bounded/off-path writer behavior;
retain durable elapsed distributions and market-hours segmentation before raw
telemetry eviction. Existing daily count/stage total/max summaries are not p95
elapsed distributions. Disk-full, torn-write, rollover, retained session identity
and restart tests must preserve evidence and never block protective management.
Post-promotion, verify real peak session volume and prior-boot retention. Dev
Compose renders 500 MiB; that capacity alone does not prove full-session logs.

**R5 / P2 — finish the S7/S8 research/learning contracts.**

- S7a models the fixed configured notional pool, not a fees/reservations-aware
  realized-equity book. The separate equity-constrained experiment, correlated
  exposure and real-budget capacity analysis remain source work. Keep the
  existing baseline label and compare like-for-like. Define immutable competing
  batch/arrival identities rather than rounding historic clocks after seeing
  outcomes. Add causal tests: outcomes cannot affect admission-time ranking.
- S7b supplies declared continuation/zone/thesis fields; it does not yet bind
  these fields to completed-bar immutable evidence. Re-entry naming a different
  state alone does not prove a new independently evidenced thesis or prior exit.
  Add a typed source adapter and explicit eligibility/no-chase/expired paths
  before interpreting caller-supplied candidates as real execution evidence.
- S8 still needs real per-policy/setup/regime lineage, entry/management delay,
  missed allocation, thesis invalidation, hold/giveback/cost decomposition,
  best-winner-excluded sensitivity and versioned proposals. Count unique
  opportunities, not every shadow variant as an opened trade; shadow accepted
  evaluations are not actual positions. Resolve truncated/unlinked legacy cash
  coverage, expose absent books as unavailable rather than complete zero days,
  and add a ledger row tie-breaker before claiming chronological/version
  drawdown. Current daily facts do not constitute automatic learning.

### Operational gates across the whole plan

| Slice | Source status / remaining gate |
|---|---|
| S1 | Exact-contract/atomic settlement correction implemented; verify deployed migrations, real reconciled keyed cash and unresolved exit recovery without inventing historical settlement |
| S2 | Management deadline/priority/clocks implemented; verify stale-IN_FLIGHT recovery and three representative market sessions, management lag, skips and protective deadlines |
| S3 | Logging/rotation/crash recovery implemented; R4 source gaps plus actual peak-volume/prior-boot/disk verification |
| S4 | Typed envelopes, existing-request fanout, capital-skipped paths and post-close/deadline export implemented; five fresh reconciled lifecycles and saturation/write-failure receipts needed; scheduled writer is not proof of a persisted row |
| S5 | Collection/replay/blocker/package tooling available; freeze real protocol before future data, initial 20 independent trading-session target, adequate closes/coverage, authorized qualification registration and separately authorized delivery canary |
| S6 | Momentum and single-leg experiments implemented with improved costs/archive validation; R1 source binding remains, spread is a prototype, then future paired HOLDOUT review |
| S7 | Initial allocation/timing hypotheses implemented and freeze drift corrected; R5 source contracts and independent future evidence/paper-only reviewed pilot |
| S8 | Initial read-only composer corrected; R5 analytical completeness/versioned proposal work remains |
| S9 | Truthful basic health/IST paper status implemented; R2 backlog tooling and fresh post-promotion degraded/no-trade/slow-provider tests |
| S10 | Source pruning plus corrected deadline forwarding implemented; R3 counters, completion delivery and strict worker lifecycle acceptance remain |

Partner messaging code exists, but ordinary general tips are **not proven ready**
by these tests. Qualification and the delivery canary are separate gates; an
empty portfolio snapshot is not the general-tip blocker. Do not promise tips
after a fixed number of calendar days or lower gates to force a send. No real
provider, Telegram delivery, order, qualification or Production runtime was
exercised in this review. Jev remains deferred.

### Verification receipt

Windows Dev runtime: `python-engine/winvenv/Scripts/python.exe`.

- `python -m pytest agent/tests -q -W error`: **368 passed**.
- Engine focused daily/allocation/timing/spread files, `-q -W error`:
  **28 passed**. These include mechanism tests, not acceptance of R1.
- Engine daily + partner orchestrator: **48 passed**, one existing Starlette
  deprecation; Penny-health wiring **5 passed**, same deprecation.
- Expanded engine selection via `rg --files tests` matching
  `test_(fno|momentum|partner|research_quote|research_leg|session_csv|scheduler|signal_log|penny_signal_log|s5_provider|atomic_settlement|daily_decision|operator_status|s4_path)`:
  **1016 passed, six warnings**. Initial run had 33 fixture errors (983 passed);
  the minimal fixture correction removed them. Remaining warnings: Starlette/
  HTTPX deprecations, an aiosqlite closed-loop worker and coroutine teardown
  warning. This is not a warnings-clean full suite. Diagnose remaining hygiene
  only with minimal reproducers; do not blanket-suppress it.
  After printing the 1016-pass summary, this broad process hung during teardown.
  Its verified Dev pytest PID was stopped; this is **not a clean process-exit
  receipt**. All focused runs exited normally. Closed-loop/coroutine warnings
  suggest teardown hygiene, but the exact hanging thread has not been proven.
- Node `npm test -- --runInBand tests/unit/health-status.test.js`: **2 passed**.
- Compose verifier tests **8 passed** warnings-fatal; rendered Dev configuration
  `json-file`, `20m`, `25`, **500 MiB**. No rendered environment was printed.
- Changed modules compiled with `python -m py_compile`; regenerated atlas
  indexes **227 Python modules**; `git diff --check` passed.

No configuration or schema change in this correction. Research freeze contracts
change as described above. The previously uncommitted S10 source is included in
the reviewed local correction; unrelated user files remain excluded. No push,
PR, Production deployment or external message is performed by this review.
Commit identity is recoverable with `git log -- docs/2026-10-02-s7-s10-independent-review.md`
and is supplied in the final handoff.

## Response — R1 completed (Dev, October 2)

- **Defined-risk experiment rebuilt (`fno_dr_exit_experiment.py`, schema v2).**
  - Entries come from persisted `fno_dr_positions` rows via a canonical envelope. Net premium, max profit/loss (`fno_defined_risk._profile`) and the round-trip entry cost are re-derived from the bound legs. Any mismatch, a single leg, duplicate tokens or a non-finite value is unavailable.
  - Observations require verified same-receipt quotes for every leg.
  - The baseline replays the live `evaluate_dr_exit` on the live mid mark and settles with the live executable formula. An unpriced square-off is `UNRESOLVED`, and square-off is derived from the IST clock.
  - The baseline is reconciled to the row settlement and ledger (`fno_dr_structure:{id}`). Paired deltas use only reconciled entries.
  - The manifest freezes the real module fingerprint, live target/stop/square-off, cost schedule and candidate parameters; drift, duplicates and tampering are refused.
  - The prototype API, caller P&L and `hard_flat` flags are gone.
- **Single-leg adapter.**
  - `verify_archive_event` verifies **both** futures and option packets: digest, raw token, identity, LTP/bid/ask columns, and a provider clock re-derived from raw bytes. A missing, future-dated or stale clock is excluded and counted, so the 600-second-stale futures reproducer is now excluded.
  - `entry_from_position_row` binds an entry to its `fno_positions` row and ledger (`fno_position:{id}`). The CLI builds packets from `--db --position-id`.
  - Caller JSON entries are labelled `CALLER_SUPPLIED_UNVERIFIED` and never counted in `paired_reconciled`.
- Tests: DR 9, single-leg 29 and S5 integration, together 49 passed warnings-fatal. The broad engine selection printed 1074 passed, one skip, six known warnings, then hung in teardown (the reviewer's known issue; stopped, not a clean-exit receipt).
- Any earlier S6 freeze is invalid; freeze again before future data.

## Response — R2 completed (Dev, October 2)

**`services/backlog-reconciliation.js`** and **`scripts/backlog-reconciliation.js`** (gateway).

- **`report`** opens `signals.db` read-only and classifies:
  - PENDING requests, by IST session: `EXPIRE` after the session has closed; `LEAVE` while it is still open; `MANUAL_REVIEW` for an unparseable or future clock.
  - EXECUTING / OUTCOME_UNKNOWN rows and open orders: `BROKER_RECONCILIATION_REQUIRED`.
  - CANCELLED/REJECTED orders not synced: `RESOLVE_NO_SYNC`.
  - COMPLETE orders not synced: `LEAVE` for the existing startup retry.
  - Unacknowledged dead letters: `ACKNOWLEDGE_NO_RESEND`.

  Each item carries a reason and a precondition fingerprint, and the report is fingerprinted. Output is exclusive-create.
- **`apply`** requires an unmodified report, a named operator and `--confirm APPLY_REVIEWED_BACKLOG_PLAN`. In one IMMEDIATE transaction it re-reads every row and skips any whose fingerprint changed (new callback, broker update, race).
  - It sets `status='EXPIRED'`, or `sync_to_b=3` (terminal, nothing to sync). No fill, price, status or row is otherwise changed or deleted.
  - It writes `backlog_resolutions` receipts (unique, so a repeat is a no-op).
  - Dead letters are acknowledged in an append-only `<file>.ack.jsonl`; the original lines stay, and nothing is resent.
- Health's undelivered-alert count now excludes acknowledged lines.
- EXEC callbacks already reject anything older than 5 minutes and any non-PENDING row, independently of this tool.
- Tests: 8 new Jest tests, plus the dead-letter and health suites. The complete gateway suite in an ephemeral Node 20 container (source copied without `.env` or native modules, then `npm ci`): **471 passed, 4 skipped**. The local Node 24 has no better-sqlite3 binary.
- **Production use** is a separate, operator-approved step: run `report`, review the plan, then `apply` with the operator name and confirmation. It was not run against Production here.

## Response — R3 completed (Dev, October 2)

- **Counters.** `AsyncReviewQueue.diagnostics_snapshot()` reports:
  - submission outcomes by state; the expiry stage (before submit, in queue, after the call); completed reviews;
  - excluded stale/unverifiable headlines (`record_source_exclusions`);
  - classifier timing and failures (`record_classifier`), separate from analyst timing;
  - in-flight status, in-flight overruns, late results discarded and submits refused after shutdown.

  The agent adds once-only completion outcomes. All are bounded counts and aggregates with no prompts, sources or review text. The agent publishes them as `diagnostics` only when `OPTIONAL_AI_REPORT_DIAGNOSTICS=true` (default false). The engine's strict `_clean_diagnostics` allow-list and the agent's `contract_health` allow-list must be deployed first; a test pins that agent, engine and contract-health key sets are identical.
- **Completion delivery** (`agent/review_completion.py`). A momentum alert sent while its review is `AI_REVIEW_PENDING` registers the original message (id, exact text, keyboard) with `valid_until` = the earlier of the 300-second EXEC window and the review expiry. Every 15 seconds the agent edits that same message once: it appends a bounded annotation and re-sends the identical keyboard.
  - It adds no new alert or button, and changes no price, quantity, stop, target or EXEC validity. A REJECT is labelled advisory only.
  - "message is not modified" counts as delivered, and a timeout is safely retried.
  - An expired window, an unavailable or expired review, or a state lost to a restart is recorded, never published. Persistence is atomic and bounded in `/tmp`.
- **Worker lifecycle.** `shutdown()` marks queued and in-flight keys `UNAVAILABLE` (`worker_shutdown`), refuses new submissions and discards any later result (counted, never cached). SIGTERM triggers it. Python cannot force-cancel a socket blocked in a thread; the bound remains the per-request transport timeout fitted under the deadline, now surfaced by `inflight_overruns`.
- Tests: agent 383 passed warnings-fatal (15 new, repeated 5 times); engine status-bridge group 74 passed (4 new) with the known Starlette/HTTPX deprecations.

## Response — R4 completed (Dev, October 2)

- **Scheduler daily summaries** now keep a durable elapsed histogram (fixed buckets 0.1–300 s plus open-ended; count, sum and max), split into NSE market hours (09:15–15:30 IST, weekdays) and off-hours.
  - The report gives the mean, max and p50/p95 **bucket upper bounds**. These are stated as bounds, not exact quantiles.
  - The additive `elapsed_hist_json` column upgrades legacy tables in place. Histograms survive eviction of the raw tail.
- **Session CSV capacity**, configured by `SESSION_CSV_RESERVED_FREE_BYTES` (1 GiB) and `SESSION_CSV_ARCHIVE_MAX_BYTES` (2 GiB):
  - Writes that would breach the free-space reserve are refused and counted (`dropped_row_counts`), never raised.
  - An over-quota archive is flagged on rotation and never pruned.
  - A torn final row is newline-isolated.
  - Momentum and penny writers now append off the event loop (`asyncio.to_thread`).
- Tests: session/signal-log/telemetry 29 passed warnings-fatal. Still operational: real peak session volume, prior-boot log retention and a disk check after deployment.

## Response — R5 completed in source (Dev, October 2)

- **S7a.**
  - Paper admissions record an immutable `admission_batch_id` and `arrival_index` in their admission evidence (additive; sizing is unchanged). The allocation reader uses them; legacy rows group by their exact recorded clock, never rounded.
  - The replay reports three separately labelled capital bases: `FIXED_POOL` (the current benchmark); `REALIZED_EQUITY` (pool plus realised net cash, minus deployed notional, minus entry fees reserved at sizing and released at exit); and `REAL_BUDGET` (capacity at `MOMENTUM_REAL_BUDGET_INR`, unavailable until you confirm a budget).
  - Each run reports maximum concurrent positions and the largest single-position share of deployed capital.
  - A causal test shows that changing a candidate's future path cannot change any admission-time size or selection, under any policy or basis.
- **S7b.** `timing_candidates_from_db` builds timing candidates only from opened or capital-skipped admissions with verified passive paths. The thesis is the signal key and the state is the sealed packet hash; re-entry happens only through recorded re-openings, and a repeated state is marked rather than aborting the report. A frozen `ZONE_RULE` (VWAP or −0.5R floor, at least stop + 0.25R; no-chase cap +0.25R; 30-minute pullback window that expires to `PULLBACK_WINDOW_EXPIRED`) is bound into the manifest and its drift is refused.
- **S8.**
  - The audit exposes `ledger_rowid` and the verified packet's `bar_ts`/`received_at`. Equal ledger clocks are ordered by row id; without row ids, drawdown stays unknown.
  - Shadow books count unique ticker/bar opportunities separately from variant evaluations. Shadow acceptances are not positions, and absent books are unavailable rather than zero.
  - Momentum adds a per-trade decomposition (seconds from the signal bar timestamp, hold minutes, exit status, net cash, R; giveback and costs explicitly unavailable), lineage by policy version and regime, missed allocation, and best-winner-excluded net cash.
  - Selection remains human review; no automatic proposal or retuning.
- Tests: allocation 21, timing 10, decision quality 10, audit/review updated. The affected engine selection: 438 passed, with the known Starlette/HTTPX deprecations.
- Old S7 manifests are invalid; freeze again before future data. These are tools: any learning conclusion still needs future holdout evidence and human review.
