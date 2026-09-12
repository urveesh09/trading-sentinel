# A/B implementation slice — causal decision clocks and collection completeness

Dev-only engineering plan. Production remains read-only and no order or partner-message action is authorized by this slice.

ID / title:
A1+B1+H1 — frozen-cutoff decision clock contract, durable per-attempt collection evidence, and warning-clean scheduler registration.

Problem and user-visible impact:
The manual-advisory tick currently evaluates at its tick-start timestamp even though public bars and option-chain inputs arrive later. Captures honestly retain later receipts, so a live candidate can be constructed with a clock that offline replay correctly rejects. Collection readiness also infers too much from retained files and selected-leg summaries: it cannot distinguish a missed schedule, a failed request, a partial response, stale input, or a complete attempt. These gaps can backdate an idea and can make qualification readiness look healthier than the evidence supports.

Current authoritative evidence:
Dev HEAD is `eb3c752` on `codex/production-correction-hedge-p0`, clean and five commits ahead of its remote at the start of this slice. `fno_signal_scan.observe_underlying` records a post-response public receipt but evaluates with the caller's tick-start `now_ist`; `partner_orchestrator.partner_manual_advisory_tick` later fetches a chain and constructs/validates with that same tick-start value. Candidate capture samples a later receipt, exposing the mismatch. The September 12 read-only Production inventory found no partner public-input captures. On this resumption Production is at `954e25a`; its application containers are exited and nginx is restarting. They were not started or changed.

Files and contracts affected:
Expected source touchpoints are `fno_signal_scan.py`, `partner_orchestrator.py`, `partner_qualification.py`, `partner_research_capture.py`, `partner_full_policy_replay.py`, a small archive-backed attempt journal/readiness module, `routes_hedge.py`, related tests, and documentation. Dashboard changes are required only if the existing readiness contract cannot expose the new typed states without them. Existing immutable capture bytes and replay CLI inputs remain readable.

Implementation steps and dependencies:
1. Define a versioned `FROZEN_COMPLETED_BAR_CUTOFF_V1` contract. Tick start chooses the public request cutoff; public and chain responses retain their actual receipts; signal evaluation uses the frozen cutoff; candidate construction and validation use a genuine post-acquisition decision time. If acquisition crosses the configured entry deadline or session date, suppress the idea. Crossing a five-minute boundary is explicit in the clock manifest and does not relabel newly eligible bars as fetched.
2. Generate a stable run/attempt identity per tick and index. Bind tick start, public request cutoff/receipt/source, chain receipt/source, evaluation cutoff, candidate construction, account/profile and index into public/candidate captures and the frozen full-policy manifest. Preserve legacy v1 capture loading with explicit legacy clock metadata; do not rewrite old artifacts.
3. Add an append-only SQLite attempt journal under the research archive. Record expected cutoff, index, source, requested/received contracts, public and candidate states independently, terminal outcome/error, and immutable artifact references. Exact retries are idempotent; conflicting identities fail.
4. Derive per-index session completeness from market-aware expected intervals plus attempts. Report `NEVER_ATTEMPTED`, `ATTEMPTED_UNAVAILABLE`, `PARTIAL`, `STALE`, or `COMPLETE`, with public, candidate and selected-leg gaps separate. A stopped process therefore remains a visible schedule gap.
5. Expose the report on the authenticated research-readiness route without granting qualification, delivery, or order authority. Preserve independent index failures and keep archive failures isolated from public management.
6. Add regression coverage for NIFTY and SENSEX, UTC/IST inputs, five-minute boundary crossing, entry/session deadline crossing, deterministic identity, no-setup, chain failure, partial/missing legs, archive-budget failure, restart persistence and no operational cash/position mutation.
7. Correct the already-documented scheduler startup-catchup rejection path so registering jobs without a running event loop does not first allocate and leak an unawaited coroutine. Add a RuntimeWarning-sensitive regression.

Acceptance / negative / restart / timing tests:
Focused unit/integration tests must reproduce a delayed public/chain fetch without timestamp fabrication; reject a source received after the entry deadline; preserve provider timestamps; create a new identity when the genuine decision clock or newly eligible cutoff changes; reproduce identical frozen inputs; keep one index's failure independent; classify never-attempted/unavailable/partial/stale/complete sessions; retain gaps after store reopen; and prove the attempt path has no execution, cash, position, qualification or transport imports. Then rerun the handover research/orchestrator suite, scheduler/API contracts, relevant gateway tests and dashboard test/build. Treat warnings as failures where the changed path permits.

Data and configuration migration:
The attempt journal is additive and created lazily under the existing research archive. No operational ledger migration and no environment variable are required. Capture formats are versioned; old content-addressed v1 files remain immutable and load as legacy evidence with weaker clock/coverage capability. No persistent volume deletion is allowed.

Rollout and rollback:
Commit and test in Dev. Rollback is the reviewed code commit plus disabling passive archive collection if operational write latency or saturation threatens management; retain the new journal and captures for forward compatibility and audit. Promotion, container recreation and live-session observation require the GitHub/release runbook and are not implied by Dev tests.

Status and verified commit:
TESTED_DEV in implementation commit `3f627cc`. Focused Python acceptance is 185 passed: 64 pure-path tests are warning-clean and 121 integration tests retain one pre-existing Starlette warning. The scheduler/isolation suite passes 41 tests with RuntimeWarning fatal. The final full Python repository rerun is 2,498 passed, 3 skipped and 17 known out-of-slice failures; its 23-warning summary contains no unawaited-coroutine warning. Dashboard acceptance is 25 passed plus a successful production build; gateway acceptance is 317 passed/4 skipped plus a 15-test focused proxy rerun; agent acceptance is 91 passed. Environment warnings and the full-suite baseline are recorded precisely in `HANDOVER_CHECKLIST.md`.

Documentation updated:
This plan slice was created before source edits. `SYSTEM_GUIDE.md`, `NEXT_AGENT_PLAN.md`, `HANDOVER_CHECKLIST.md` and regenerated `SYSTEM_CODE_ATLAS.md` were updated in implementation commit `3f627cc`.

Unresolved limits and exact next action:
This slice does not qualify a strategy, establish profitability, send advice, place orders, calibrate costs, complete held-out review, reconcile historical losses, or deploy Production. Production load/retention and real schedule behavior remain unobserved. Next action: review the implementation commit, resolve or explicitly baseline the broader suite failures, then implement C's multi-session complete/unresolved archive fixture before promotion.
