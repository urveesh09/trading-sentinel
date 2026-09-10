# f9e721f: intraday advisory merge-readiness review

Reviewed 8 September 2026 in Dev. Commit: `f9e721f`.

## Decision

**Partial implementation, not a complete live-advisory sign-off.** The intraday identity, dated deadlines, card wording, numeric thesis requirements, cost-inclusive profile checks and current qualification lookup are meaningful improvements. However, critical-time updates and final timing still have defects.

The owner has supplied all preferences needed for this development increment: intraday only, NIFTY 50/SENSEX, manual decisions, hedge-first. No partner broker credentials, order monitoring, mandatory feedback or additional capital declaration is required for per-structure standalone advice.

For a merge that will activate this advisory release, correct the blockers below first. If the owner wants to merge code for staging/inactive previews sooner, verify the effective delivery gate remains off during that rollout; do not rely on missing profiles or missing qualifications as the only barrier. This review did not change any flags, merge, push, send messages or edit Production.

## Independently verified

- Broader nine-module Python regression suite: **159 passed**, one existing Starlette deprecation warning. Modules: manual advisory, partner orchestrator/content, hedge advisory, chain, instruments, scheduler tick/closures and hedge routes.
- Inspected code and implementation note; passing tests do not cover all release requirements.
- Reproducible safe [session probe](review-2026-09-08-partner/f9e721f_session_probe.py), using an isolated SQLite database and a synthetic published idea:
  - At 15:11, underlying 24,900 below the idea's 24,950 invalidation: only `SESSION_EXIT_REMINDER` is generated.
  - Next-day observation leaves the previous idea `DELIVERED_ACKNOWLEDGED`, not retired.
- Probe contains no transport invocation. No actual partner receipt or Production runtime was assessed this turn.

## Corrections required before active rollout

### M1 — Invalidation must remain visible after 15:10

`queue_management_updates` checks the reminder time before checking invalidation/target. After 15:10 it selects the reminder for every observation. Once that reminder has been inserted, subsequent ticks can produce no message while a newly crossed invalidation is never evaluated.

Evaluate material risk events independently. Give invalidation priority and incorporate the exit deadline into its wording, or create separate correctly deduplicated events. Do not send redundant messages merely because both conditions hold.

Acceptance: invalidation first occurs at 15:11 before any reminder, and at 15:12 after a reminder was acknowledged. Both must produce a clear material invalidation update. Preserve conditional language and no order monitoring.

### M2 — Management/reminders/retirement must not require entry-chain availability

The orchestrator still waits for a successful scan, option snapshot and eligible option expiry before calling management updates. That can suppress an exit reminder because data needed for a new option entry is missing. Retirement is inside this same observation path.

The registered job runs every two minutes at second 50. Around the deadline, a normal sequence is 15:14:50 then 15:16:50; the outer 15:15 gate closes before the latter. Consequently this does not guarantee a same-day retirement pass. Next-day session mismatch skips the old row instead of retiring it, as the probe confirms. The skip prevents those old rows generating updates through this function, but is not the promised durable retirement.

Separate clock-based reminders and retirement from quote-dependent entry scans. Use fresh matching underlying data for numeric price events; send a truthful time reminder without fabricating a current price when market data is unavailable. Run an idempotent post-deadline/startup sweep over elapsed ideas, including previous sessions. Handle session/holiday/special-session calendars rather than only fixed wall-clock replacement.

Acceptance: option-chain outage, no new signal, 15:14:50→15:16:50 schedule, restart after deadline, restart next day, and special-session early close. Never imply that a reminder automatically closed the partner's position.

### M3 — Recheck the clock after asynchronous claim/database waits

The caller obtains `final_now` before `_send_claimed_review`. That helper awaits claims and service-state writes and passes the old timestamp into final authorization. The new qualification query adds another await without refreshing the time. This leaves the previously identified post-wait quote-expiry gap unresolved.

Inject and read actual current time at final authorization/transport-start validation after waits, for entries and updates. Recheck quote validity, entry deadline and management deadline as applicable. Update authorization currently does not explicitly enforce the published management deadline; a fresh update created just before 15:15 could cross it while waiting.

Acceptance: fake-clock delay inside claim acquisition, qualification query and transport-start persistence, crossing 30-second quote TTL, 14:45 entry deadline and 15:15 management deadline. Assert no obsolete actionable transport. Preserve sticky ambiguity and acknowledged deduplication.

### M4 — Qualification needs real evidence; activation is still operational work

The new registry rejects the old horizon/policy and dates far in the future, and dispatch now reads current registry status. Good. But a nonempty `dataset_ref` still suffices: no actual immutable research artifact or review history is enforced. The API permits a five-minute future timestamp tolerance while dispatch rejects any future review; make that contract explicit/consistent.

Developer must supply a genuine reviewed **intraday** research artifact per index/policy/structure, with costs and limitations, before registering qualification. Do not relabel three-session evidence or create a placeholder record. Add artifact binding and review history/expiry as required by the earlier plan, or explicitly identify a documented manual-review mechanism and its limitations rather than claiming automated verification.

Also verify final authorization against current profile rules and use a consistent local revision view; a profile-version check alone does not establish all time-dependent permissions after waits.

## Features that can stay disabled without blocking standalone advice

Conditional protection still uses one profile exposure assumption across both indices. Keep that category out of the initial saved profile until assumptions are typed and scoped per index. This does not require the partner to share holdings for standalone debit-spread ideas.

Frozen intraday edge evaluation, richer preparation briefs and fuller latency/capacity evidence are not proven complete by this commit. Distinguish a functioning policy implementation from a strategy with demonstrated market evidence. Do not call all previous I1–I7 requirements complete solely because intraday strings and deadlines exist.

## What is needed from the owner or partner

**No further required preference input for the first standalone release.** Intraday and both indices are confirmed. Use the previous plan's explicit configurable timing defaults and show them in the handoff. Optional personal risk/capital filtering can be added later; unknown values must not imply unlimited suggested quantity.

The remaining setup belongs to the developer/operator:

1. Finish M1–M3 and qualify M4 with actual evidence.
2. Prepare/save the versioned `default` profile with `holding_period=INTRADAY`, NIFTY/SENSEX and `DIRECTIONAL_DEBIT_SPREAD`. Increment existing version. Leave personal limits null and conditional protection disabled initially.
3. Record matching, justified qualification for each index under `partner-manual-intraday-v1`.
4. Verify effective deployed flags, masked Telegram destination, per-index feed readiness and actual image SHA. Produce current-data no-send previews and a registered-scheduler session-end test with safe transport doubles.
5. Promote through GitHub under the already authorised advisory rollout scope. Do not interpret this review as an additional permission request or ask the owner to invent technical qualification values.

## Copyable developer instruction

> Before active rollout of f9e721f, complete M1–M4 in `docs/2026-09-08-f9e721f-merge-readiness-review.md`. Fix reminder precedence swallowing invalidations, separate management/time-based retirement from entry-chain availability, add restart-safe session retirement and re-read time after claim/DB waits at final transport. Test the actual two-minute schedule and deadline crossings, not only direct helper calls. Preserve intraday policy identity and all existing transport ambiguity/claim safeguards. Prepare the known INTRADAY default profile and genuine intraday qualification evidence; do not ask the owner for preferences already supplied or require partner order monitoring. Keep conditional protection off until per-index assumptions are fixed. Work in Dev, preserve audits, and deliver commits, exact tests, real preview/integration evidence and effective rollout configuration through GitHub.
