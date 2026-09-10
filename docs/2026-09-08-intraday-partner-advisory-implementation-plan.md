# Intraday-only NIFTY/SENSEX partner advisory: implementation plan

Date: 8 September 2026. Baseline Dev HEAD: `a734562`.

## Binding owner requirement

The partner trades **intraday only**, in **NIFTY 50 and SENSEX**, manually. This supersedes every earlier suggestion or example of `INTRADAY_TO_3_SESSIONS` for this partner. Do not ask again about overnight holding or require the partner to adopt it to match the code.

Build a hedge-first intraday advisory service: clear entry conditions, defined-risk structures, useful protection ideas where assumptions are explicit, timely invalidation and same-day exit reminders. No partner broker access, order execution, position monitoring or mandatory Taken/Skipped feedback. Observe published ideas and public market conditions; never infer that a delivered message was traded.

Implementation is in `C:\Users\Urveesh\Desktop\trading-sentinel` only. Preserve earlier audit artifacts. Promotion is through GitHub under the existing advisory rollout scope. This planning task does not itself change configuration or send messages.

## Outcome required

An explicitly saved `INTRADAY` profile can receive qualified NIFTY/SENSEX ideas with exact contracts, fresh executable economics, concrete price conditions and a same-session management deadline. Every idea expires within its session. Neither overnight advice nor yesterday's management updates can leak into this channel.

The current code cannot achieve this by changing one profile string: both builders currently default to `INTRADAY_TO_3_SESSIONS`, qualification matches that literal horizon, and the same-day management lifecycle is incomplete. Implement the contracts below first.

## I1 — Typed intraday profile and policy identity

Locations: `partner_manual_advisory.py`, `routes_hedge.py`, `partner_orchestrator.py`, configuration and persistence migrations.

1. Add a validated `INTRADAY` horizon shared by profile, candidate, qualification and renderer. Pass it explicitly into both market-setup and conditional-protection builders. Reject unsupported free-form horizons.
2. Use a new immutable policy version, such as `partner-manual-intraday-v1`. Do not relabel the old three-session policy or its qualifications as intraday evidence.
3. Persist `session_date`, `signal_at`, `entry_deadline`, `management_deadline`, `quote_observed_at`, `quote_received_at` and `quote_valid_until`. Keep executable quote TTL separate from the idea's holding horizon.
4. Scope profile ID/version, thesis identity, economic version and delivery generation correctly. Retire legacy unacknowledged generations for this profile with an explicit reason; never replay them as fresh intraday advice. Preserve delivery and ambiguity audit history.
5. `default` remains the scheduler's intended profile ID unless that selection is explicitly made configurable and tested. Increment an existing profile version; never overwrite version history silently.

Acceptance: profile/candidate/qualification all match `INTRADAY`; a three-session candidate cannot queue; old qualification cannot authorise new policy; midnight/restart cannot extend a deadline.

## I2 — Explicit same-day timing, independent of entry eligibility

Proposed normal-session application defaults in IST below are engineering defaults, not exchange rules, guaranteed fills or owner risk limits:

| Activity | Proposed default | Required behaviour |
|---|---|---|
| New qualified entry ideas | 09:45–14:45 | Only on a valid trigger and sufficient remaining management time |
| Management/invalidation observation | Through 15:15 | Continue after the entry window closes; do not depend on a new signal or usable new-entry option chain |
| Intraday exit reminder | 15:10 | Conditional wording referencing still-active published ideas |
| Idea management deadline | 15:15 | Advise same-day exit/reassessment; retire observation after the deadline |

Implement these as separate, configurable policy settings. Resolve exchange session/holiday/special-session information for both venues; suppress trading-day advice when there is no eligible session. Clip deadlines earlier where an applicable broker cutoff is known. Missing broker information must be labelled as such; these times do not guarantee that a broker will allow an order until then. Do not require broker credentials to support the advisory service.

The current common `_gates_open` entry window must not suppress an exit reminder or invalidation. A price-triggered update remains useful after new entries are disallowed. Conversely, no recovery worker may send a new entry after its entry deadline even if the transport claim is recoverable.

Every trade card must say **intraday only; do not carry overnight**, include the actual dated IST exit deadline, and explain that the partner must act manually. Never say the system closed their position.

Acceptance: 14:46 new-entry denial with valid management update; 15:10 reminder; 15:15 retirement; holiday/short-session handling; delayed/restarted jobs do not replay obsolete alerts. Test both exchanges and exact boundary semantics.

## I3 — Intraday payoff, entry and exit information

Retain the corrected independent vertical oracle, finite-value checks, positive post-cost expiry reward and full-lot depth gates. Add intraday evaluation:

- A positive maximum expiry payoff is only a structural check, not evidence of profit before today's exit. Compare realistic same-day exit bid/ask, time decay, volatility changes, fees and slippage in the research policy.
- Carry the source trigger, invalidation, target/review zone, timeframe and timestamp into the candidate. Distinguish spot versus futures reference; use the same reference instrument for follow-ups, including around futures rollover.
- Show the maximum combined entry debit, per-structure costs and conservative risk assumptions. Show expiry payoff separately from intraday target/exit scenarios; do not present expiry maximum profit as today's likely profit.
- Define an intraday thesis invalidation and time exit. If a numeric level is missing, do not present a generic instruction as a complete actionable setup.
- Select an eligible option expiry with adequate liquidity and remaining life even though the position is intended to close today. **Intraday does not mean same-day expiry.** Preserve the existing exclusion of same-day-expiry setups until separately qualified; no automatic 0DTE enablement.
- Validate eligible candidates before overlap ranking. Compare NIFTY and SENSEX as potentially overlapping expressions of a thesis, including already published active ideas. Do not promise diversification from two index names.

Acceptance: exact card rendering for both indices and directions, same-day exit economics under adverse volatility/slippage, valid future-expiry contracts with intraday deadlines, and rejection of missing/mismatched reference prices.

## I4 — Complete the remaining release correctness work

These are required alongside intraday support, not optional cleanup. Detailed evidence is in `2026-09-08-partner-setup-guide-and-a734562-review.md`.

1. **Research qualification:** bind to an actual immutable research artifact, index, structure, horizon, policy/code version and review. Reject nonexistent evidence, future review dates and expired/suspended approval. Preserve review history. Do not create dummy qualifications to unblock messages.
2. **Final authority:** recheck current qualification, profile, session deadlines and all relevant switches at final dispatch/recovery. Cached `strategy_qualified=True` is not current authority.
3. **Time after waits:** use an injectable fresh clock after claim/database waits, at final authorization/transport-start validation. Reject expired quotes and ideas. Provider quote time, receive time and last-trade time are different facts; do not fabricate freshness from scan-start time.
4. **All-in limits:** profile limits must include applicable costs and explicitly defined stress allowance. Current gross-debit/gross-loss comparisons can exceed the intended budget after fees.
5. **Immutable delivery:** preserve acknowledged deduplication, durable transport start, sticky ambiguity and destination-wide backoff. Maintain stable thesis versus economic generation identity. Return the actual committed record, not a newly rendered record that was never saved.
6. **Quota reservations:** separate new-idea capacity from critical updates; reserve concurrent/in-flight attempts transactionally. Define how ambiguous delivery consumes quota. Urgent updates do not bypass Telegram rate limits, but must not be silently displaced by ordinary new tips.

Acceptance: qualification suspension while queued; profile window closure; artificial delays inside claim/DB writes; concurrent quota claims; exact-cost boundary; 429/timeout/crash/recovery; no expired or duplicate entry transport calls.

## I5 — Intraday protection without inventing partner holdings

Keep standalone defined-risk index ideas independent of holdings. Conditional protection is a separate optional scope with typed, **per-index** assumptions: reference exposure, direction, units, expiry/reference basis and protection end time. Do not reuse a NIFTY exposure string or unit quantity for SENSEX.

Protection proposals need a stated market reason and a cost/benefit comparison, not a put card merely because a profile includes an exposure assumption. Explain what is protected, what is not, protection cost, residual risk and the same-day exit/unwind consideration. Never advise removing protection while assuming the unknown protected exposure has already been closed.

Complete and test the conditional-protection path in Dev, but leave it absent from the initial saved profile until appropriate assumptions are available. This must not block qualified standalone ideas. Personalised quantities remain absent without the inputs supporting them. Large capital does not imply unlimited liquidity or risk tolerance.

Acceptance: correct NIFTY and SENSEX assumptions independently; mismatched underlying/coverage rejected; no fabricated portfolio; same-day expiry of the idea even when the option contract expires later.

## I6 — Public-condition follow-ups and session retirement

Observe only active published ideas with matching session/reference instrument and an unelapsed management deadline. Create separate immutable event types for invalidation, target/review zone and session-exit reminder. “If you took idea X…” is sufficient; no order monitoring is required.

Persist event generation, delivery state, original observation and expiry. Regenerate/revalidate a failed or stale event where appropriate rather than stranding a once-inserted row forever. An expired entry quote must not erase the longer-lived valid management thesis; an elapsed management deadline must retire it.

At session end, record `RETIRED_SESSION_END` or equivalent with explicit reason. Do not generate tomorrow's update against today's invalidation level. An optional review may summarise observed ideas as model evidence, never realised partner profit.

Acceptance: no feedback needed; invalidation on an otherwise no-setup scan; option-chain failure with a fresh usable underlying; stale underlying suppresses price claims; restart before/after reminder; no next-day replay.

## I7 — Profile setup, research and operator handoff

Add an authenticated setup view or command that returns concrete per-index states: profile missing, horizon mismatch, qualification absent/suspended/expired, stale/unavailable feed, no valid setup, quote expired, deadline elapsed, destination unavailable, queued/acknowledged/ambiguous. Distinguish an implicit default profile from a saved one. Mask destination and never return secrets.

The developer should prepare this initial profile after implementing the horizon support:

```json
{
  "version": 1,
  "enabled_scopes": ["MARKET_SETUP"],
  "instruments": ["NIFTY", "SENSEX"],
  "holding_period": "INTRADAY",
  "timezone": "Asia/Kolkata",
  "delivery_start_minute": 585,
  "delivery_end_minute": 885,
  "permitted_structures": ["DIRECTIONAL_DEBIT_SPREAD"],
  "preference": "ACTIONABLE",
  "capital_limit_rs": null,
  "risk_limit_rs": null
}
```

Use `GET /partner/advisory/profile?profile_id=default` and choose the next version if a saved profile exists. Save through the authenticated `PUT` endpoint in the reviewed rollout step. In this specification the profile entry window applies to new entries; management uses the separate intraday management deadline. Do not let the old shared window block exit updates.

Null limits mean no personal quantity recommendation, not permission for unlimited size. No further owner input is necessary to implement this plan; exact risk preferences can be supplied later if personal filtering is desired. The proposed hours are explicit configurable defaults and should be shown in the final handoff.

Run frozen chronological **intraday** research separately for NIFTY and SENSEX, including costs, realistic manual entry delay, no-fills, exit deadline, losses, drawdown and uncertainty. Register only justified qualifications with matching `INTRADAY` and the new policy version. Synthetic tests demonstrate code correctness, not trading edge. If research is insufficient, deliver the working preview service and name the actual evidence blocker; do not hide it behind generic “needs profile.”

Check `/partner/advisory/effective-settings`, `/partner/advisory/diagnostics` and `/partner/advisory/cards` against the deployed configuration. Environment overrides must be visible. Saving profile plus qualification while live flags are enabled can make the next tick send; do not exercise configuration writes as exploratory live tests.

## Delivery checkpoints

| Checkpoint | Required output | Completion evidence |
|---|---|---|
| A | I1/I2 and I4 correctness | Typed horizon, real dated deadlines, profile/qualification and post-wait freshness regressions |
| B | I3/I5/I6 product behaviour | Complete entry/protection/update cards and both-index session replays without orders or feedback |
| C | I7 integration and research | Authenticated setup, registered scheduler with controlled clock, safe fake transport, per-index research and no-send current-data previews |
| D | GitHub rollout candidate | Exact commits/tests, configuration/profile migration, evidence-backed qualifications or specific missing evidence, rollback and effective-settings report |

Preserve existing tests and run focused partner, hedge transport, F&O payoff, chain, instrument, route and scheduler suites appropriate to the changes. Add independent payoff tests and fake-clock/concurrency scenarios; do not merely assert that a field was renamed. No unconditional profit or “best possible timing” claims.

## Copyable developer assignment

> Implement `docs/2026-09-08-intraday-partner-advisory-implementation-plan.md` in Dev, starting from the current branch after inspecting status. The owner has confirmed **intraday only**: NIFTY 50/SENSEX, hedge-first, manual decisions, no overnight recommendations or partner order monitoring. Complete I1–I7 through checkpoints A–D. Replace the partner's three-session assumption with a genuinely typed intraday policy, dated same-session entry/management deadlines, evidence-backed matching qualifications and a usable profile setup path. Fix current-registry dispatch checks, post-wait quote freshness, all-in limits, per-index protection assumptions and bounded follow-up retirement. Preserve hardened transport ambiguity/dedup safeguards and separate critical updates from new-idea quotas. Prepare the explicit default profile using the next version, exact preview cards for both indices and real intraday research artifacts; do not manufacture qualifications. Keep unknown personal limits unspecified and quantities non-personalised. Do not stop at a string/default change. Deliver commits, exact tests, requirements matrix, safe integration evidence and a GitHub rollout handoff under the existing advisory authorization. Never edit Production directly or enable unrelated live trading.
