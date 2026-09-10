# Partner setup guide and review of a734562

Date: 8 September 2026. Reviewed Dev HEAD: `a734562`.
Scope: explain activation prerequisites, independently review implementation and identify next corrections. No Production state, profile, qualification, switches, messages or orders were changed.

## What the last line means

The switches enable an advisory service. Two additional pieces determine what it is allowed to recommend:

1. **Saved profile = the partner's trading preferences.** Markets, allowed strategy types, holding period, alert window and optional risk/capital limits. The current scheduler loads profile ID `default`.
2. **Strategy qualification = a recorded, evidence-supported decision that a particular strategy is suitable for advisory use.** It is keyed by index, structure, holding horizon and policy version. NIFTY and SENSEX need separate matching records.

The profile is a preference, not an order instruction. Qualification is the developer/research reviewer's responsibility; it is not something the owner should invent to unblock a switch. Neither requires partner broker credentials, order monitoring or mandatory feedback.

At present, the default profile has no holding period, so it cannot authorise delivery. Both builders use the literal horizon `INTRADAY_TO_3_SESSIONS`. A profile set to `INTRADAY` will not match that candidate. This is a current implementation limitation, not a reason to choose an unsuitable horizon. The developer must add the actual requested horizon if different.

## What is needed from the owner

| Input | Why it matters | Required now? |
|---|---|---|
| Same-day trades, overnight up to three sessions, or both | Determines setup, expiry, management and qualification scope | Yes, confirm actual preference; no silent overnight assumption |
| Desired alert hours | Avoids advice when the partner cannot act | Confirm preferred hours; developer must reconcile them with scanner hours |
| Standalone defined-risk ideas versus conditional protection too | A protection idea must state what exposure it assumes | Standalone ideas need no holdings; protection assumptions are only needed if enabling that category |
| Optional maximum acceptable loss/capital for one suggested structure | Filters per-structure affordability; not an instruction to allocate all partner capital | May remain unspecified with no personal quantity; if supplied, include fees and stress assumptions |

Already known: **NIFTY 50 and SENSEX; hedge-first; manual execution; no partner order monitoring.** Do not ask for these again. A large account balance is not a substitute for a maximum loss preference.

The owner does not need to provide test datasets, manufacture approval evidence, reveal credentials in chat or fill in internal API fields. The implementing developer can save the profile after preferences are confirmed and use the existing securely configured internal authentication.

## How the developer should configure it

These are authenticated engine APIs, not currently demonstrated as an owner-friendly onboarding screen. Do not assume they are exposed on a public browser URL or gateway route.

1. `GET /partner/advisory/profile?profile_id=default`: inspect existing version. Use its next version for an update; version 1 is only for the first saved record.
2. `PUT /partner/advisory/profile?profile_id=default`: save the agreed profile using `X-Internal-Secret` through the established internal path. Keep the credential out of command output, documentation and chat.
3. Developer produces/reviews frozen strategy research with costs and limitations; registers a qualification only for a supported, justified index/structure/horizon/policy combination using `POST /partner/advisory/qualifications`.
4. Inspect `GET /partner/advisory/effective-settings`, `GET /partner/advisory/diagnostics` and `GET /partner/advisory/cards` in the deployed environment. Validate actual environment precedence and destination configuration without exposing secrets. Code defaults alone do not establish runtime state.
5. Verify current-data previews for each index and the corrected dispatch gates. Follow the already authorised GitHub rollout path; no direct Production-file edits. Saving a qualifying profile while delivery is enabled can make the next scheduled tick eligible to send, so perform configuration in the intended reviewed deployment step, not as an exploratory API test.

Example profile payload **only if the owner confirms overnight holding up to three sessions is acceptable**; this is not applied by this audit:

```json
{
  "version": 1,
  "enabled_scopes": ["MARKET_SETUP"],
  "instruments": ["NIFTY", "SENSEX"],
  "holding_period": "INTRADAY_TO_3_SESSIONS",
  "timezone": "Asia/Kolkata",
  "delivery_start_minute": 585,
  "delivery_end_minute": 905,
  "permitted_structures": ["DIRECTIONAL_DEBIT_SPREAD"],
  "preference": "ACTIONABLE",
  "capital_limit_rs": null,
  "risk_limit_rs": null
}
```

585/905 are 09:45/15:05 IST, matching the inspected scanner's current outer gate. They are a concrete configuration example, not a newly approved partner preference. Profile windows broader than this do not cause scans outside the scheduler's gate. Unknown personal limits remain null; quantities must not be inferred. Do not enable conditional protection until its per-index assumption defect below is fixed.

Qualification fields currently required: `underlying`, `structure_kind`, `horizon`, `policy_version`, `dataset_ref`, `reviewed_at`, `status`. For the present directional builder, matching values are NIFTY or SENSEX, `DIRECTIONAL_DEBIT_SPREAD`, `INTRADAY_TO_3_SESSIONS`, `partner-manual-v1`. The dataset and timestamp must refer to an actual completed review. No ready-to-post fake qualification is supplied here because passing a database gate does not establish strategy quality.

## Independent implementation assessment

**157 tests passed** in the broader nine-module suite: partner manual advisory, orchestrator, content, hedge advisory, chain, instruments, scheduler tick, scheduler closures and hedge routes. This is broader than the implementation note's reported 113 relevant tests. One existing Starlette deprecation warning remains.

The independent vertical oracle, cost-positive reward rejection, full-lot depth, research-only queue gate, profile restrictions, future-expiry resolver and explicit public-condition follow-ups are meaningful improvements. They address important defects from the previous review. The profile no longer needs a fabricated portfolio.

However, this is **partial completion of the earlier release plan**, not a clean final sign-off. The following findings come from code inspection except where a probe is explicitly stated.

### A1 — Qualification is still a weak approval record, not verified research

`record_strategy_qualification` accepts nonempty dataset/horizon strings and stores status; `is_strategy_qualified` checks only the matching status. An offline temporary-database probe with `dataset_ref='nonexistent-audit-evidence'` and a review date one year in the future returned `True` for qualification.

Required: bind to an immutable existing research artifact ID/hash and matching code/policy/index/horizon, record reviewer and actual review time, reject future timestamps, preserve an append-only review/suspension history and define review validity/expiry. Require documented evaluation criteria; do not invent a profit threshold after seeing the results. Missing or insufficient evidence remains research-only. The developer's note explicitly leaves frozen-fold research separate, so qualifying records must not be presented as already justified by that unfinished work.

### A2 — Recheck current qualification and profile at the final transport boundary

The manual `_authorize_dispatch` checks `strategy_qualified` and evidence in the stored payload, not the registry's current state. Suspending a strategy after queueing therefore is not re-evaluated there. It reads current profile version but not the full current time-dependent profile rules.

Required: fresh registry status and profile validation under a consistent local revision/claim check immediately before transport; test qualification suspension, profile window closure and configuration changes while a card waits. Do not rely on the cached approval boolean as authority.

### A3 — Fresh-clock improvement still precedes claim/database waits

`dispatch_queued_advisory` obtains a fresh clock before `_send_claimed_review`, which then awaits claim/DB/service-state work and passes that same timestamp into authorization. Delay inside that sequence can still consume the TTL. Update dispatch has the same shape. The quote parser also still falls back from last-trade time to caller-stamped snapshot time; quote-depth provenance is not fixed by a fresh dispatch clock.

Required: inject/read fresh time within final authorisation/transport-start validation, after waits; represent provider quote and receive timestamps separately. Add fake-clock tests with delays inside claim acquisition and final DB work, not only before calling dispatch. No stale actionable card should reach transport.

### A4 — Follow-ups need an actual idea lifetime and independent risk-observation path

`queue_management_updates` selects all `DELIVERED_ACKNOWLEDGED` ideas without filtering the holding horizon or contract expiry. `INTRADAY_TO_3_SESSIONS` is a string, not a persisted session-aware management deadline. Old ideas can generate later updates when their numeric levels are crossed. The scanner also requires a usable option snapshot and a future eligible expiry before observing old ideas, even though a public underlying observation may suffice.

Required: persist an exact session/calendar-aware management deadline and explicit retirement state; never follow an expired idea as active. Run underlying-condition monitoring independently of new-entry/chain readiness. Keep it independent of partner trades. A failed/stale queued update must be revalidated/regenerated with an auditable lifecycle rather than becoming a permanently stranded once-inserted row.

### A5 — Conditional protection assumptions are shared across both indices

The profile supplies one `conditional_exposure_assumption` and one coverage quantity. The orchestrator reuses them for both NIFTY and SENSEX. A NIFTY-specific assumption must not appear on a SENSEX protection card. Capital is not exposure, and identical unit counts do not make different indices equivalent.

Required: per-index typed exposure assumptions including reference instrument, direction, units, expiry/reference basis and protection horizon. Confirm cross-index mismatch rejection and lot/coverage rounding; no claimed exact coverage without the corresponding calculation. Until corrected, keep this category out of the saved profile. Standalone debit-spread profiles can be developed independently.

### A6 — Risk/capital limits omit costs

`validate_profile` compares the risk limit to gross maximum loss and capital limit to gross debit. Offline probe: maximum loss ₹3,375 plus estimated costs ₹118.41 passes a ₹3,375 risk limit. This exceeds an all-in interpretation of that limit.

Required: define and enforce all-in limits, including estimated relevant charges and documented stress allowance. Label assumptions clearly. Keep per-structure economics separate from suggested total partner quantity.

### A7 — Horizon/profile onboarding and useful diagnostics are unfinished

Profiles accept free-form horizon strings, while the builders use one fixed horizon. Qualification must match that exact string, creating an easy silent misconfiguration. Effective-settings lists abstract requirements but does not itself report a complete per-index qualification decision or whether the profile is actually saved versus returned implicitly.

Required: typed supported horizons, builder support for the selected horizon and exact deadlines. Add an owner-friendly form or command returning concrete states: profile absent, unsupported horizon, qualification absent/suspended/expired, feed unavailable, no valid setup, expired quote, destination unavailable and delivery ready. Include per-index strategy review links and preserve secret masking.

## What improves for the partner

- Payoff checks prevent mathematically bad or inconsistent spread recommendations; they do not prove positive expected return.
- A real profile aligns alerts and management with the partner's holding period rather than assuming they can hold overnight.
- Evidence-backed qualification separates tested strategy families from experimental previews.
- Fresh quotes and full-lot feasibility make displayed economics more credible; large-size execution still requires independent capacity assessment.
- Numeric trigger/invalidation/target information and timely conditional follow-ups make the advice more actionable without monitoring orders.
- Per-index diagnostics explain silence instead of requiring the owner to guess which switch is blocking delivery.

## Next developer assignment

> Use `docs/2026-09-08-partner-setup-guide-and-a734562-review.md`. Preserve the improvements in a734562 and fix A1–A7 in Dev. Prioritise live qualification revocation, post-wait freshness, bounded follow-up lifetime, per-index protection assumptions and all-in limits. Add a typed horizon/profile setup path; ask the owner only for actual trading preferences, not research/database implementation details. Produce real frozen research evidence and record qualification only if its documented criteria are met. Never register a placeholder dataset or merely change an enum to activate sends. Test both indices with claim delays, suspension, old ideas, mismatched assumptions and fees at the limit. Keep partner order monitoring and feedback unnecessary. Deliver corrected code, exact tests, a preferences-ready profile payload and verifiable qualification artifacts, with an effective-settings report and current-data no-send card examples. Continue under the existing GitHub advisory rollout authorization; do not edit Production directly or introduce unrelated live trading.
