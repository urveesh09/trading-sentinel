# Trading Sentinel development handover

Date: 8 September 2026

## Purpose

This document is the continuity brief for the next development session. It
describes the role to assume, the current Dev state, the non-negotiable safety
boundary, work already completed, remaining work, and the delivery standard.

The objective is to improve useful, evidence-based intraday advisory quality
and risk control. It is **not** to increase trade count, imply guaranteed
profit, invent partner holdings, or enable unrelated trading capability.

## Role to assume

Act as the principal implementation and verification engineer for Trading
Sentinel. Your responsibilities are to:

1. Read the current plan/audit fully before editing.
2. Translate every finding into an observable contract: code location,
   acceptance test, and operational evidence.
3. Implement in small coherent increments, preserving existing durable
   delivery, acknowledgement, ambiguity, deduplication and rate-limit
   protections.
4. Independently inspect the result rather than trusting an earlier claim.
5. Run proportionate tests, compile checks and diff checks before committing.
6. Write/update implementation documentation describing what changed, why,
   verification performed, configuration implications, and remaining work.
7. Commit only intended implementation files and push the working branch.
8. Be explicit about anything that cannot be honestly verified from available
   evidence. Do not substitute a placeholder, fixture, configuration flag, or
   optimistic claim for real research or operational proof.

When a plan asks for research-backed qualifications, distinguish code that can
support them from actual market evidence. Synthetic fixtures prove software
behaviour only; they do not prove edge, liquidity capacity, or future returns.

## Immutable workspace boundary

There are two separate working copies:

| Purpose | Location | Rule |
| --- | --- | --- |
| Production | `C:\Users\Urveesh\Desktop\Production_Trading-sentinel` | Inspect runtime/log evidence only. Do not edit code, config, environment or data directly. |
| Development | `C:\Users\Urveesh\Desktop\trading-sentinel` | Make all requested code, test and documentation changes here. |

Promotion occurs via GitHub. Never copy files into Production or modify its
environment as a shortcut. Current work is on branch
`codex/production-correction-hedge-p0`.

## Current committed state

Latest pushed commit: `a077d54` — `fix: complete intraday advisory lifecycle gates`.

Important preceding commits:

| Commit | Meaning |
| --- | --- |
| `c6afd2f` | Initial scoped NIFTY/SENSEX manual-advisory foundation. |
| `e930968` | Manual advisory delivery rollout wiring. |
| `a734562` | Independent economics, profile/qualification gates, generation and management improvements. |
| `f9e721f` | Intraday-only policy, dated deadlines and cards. |
| `a077d54` | Audit corrections for invalidation precedence, scan-independent lifecycle, post-wait freshness and artifact-bound qualification. |

All commits above were pushed to `origin/codex/production-correction-hedge-p0`.

## Product boundary now implemented

The partner advisory service is deliberately constrained to:

- NIFTY/NSE/NFO and SENSEX/BSE/BFO only.
- Manual, advisory-only decisions; no partner order placement.
- Intraday-only `DIRECTIONAL_DEBIT_SPREAD` ideas under
  `partner-manual-intraday-v1`.
- Defined-risk structures with conservative executable-side economics.
- Conditional public-market follow-ups using “If you took idea X…” wording.
- No partner broker access, fill inference, mandatory feedback, position
  monitoring, or partner P&L attribution.

Conditional protection exists only as an optional, explicit-assumption path.
It must remain absent from the initial profile until assumptions are typed and
scoped independently for each index. Never infer an exposure from cash,
capital, another index, or a message recipient.

## Implemented advisory controls

### Economics and liquidity

`python-engine/partner_manual_advisory.py` independently validates each
directional debit spread from the two executable legs. It verifies leg count,
BUY/SELL pairing, direction, strikes, expiry, type, ratio, lot size, finite
values, displayed economics and positive reward after stated round-trip cost.
Depth must cover at least one full lot times ratio on the executable side.

An expiry maximum payoff is structural information, not an intraday profit
forecast. Cards must keep this distinction clear.

### Intraday policy and timing

Only horizon `INTRADAY` and policy `partner-manual-intraday-v1` are accepted.
Candidates persist session date, signal time, entry deadline, management
deadline, quote observation/receipt facts, and quote validity. Current IST
defaults are configurable in `python-engine/config.py`:

- entry window: 09:45–14:45;
- exit reminder: 15:10;
- management/retirement deadline: 15:15.

Cards explicitly state that they are intraday only, must not be carried
overnight, and require manual action. The system never claims it closed a
partner position.

### Delivery safety

The existing `hedge_advisory` delivery ledger provides durable claims,
transport-start persistence, acknowledgement handling, ambiguity preservation,
destination backoff and deduplication. Do not weaken these controls.

Manual dispatch now rechecks at the authority boundary:

- enabled flags;
- exact persisted card and profile identity/version;
- intraday policy, current session and entry deadline;
- unexpired quote;
- current qualification registry status;
- fresh clock after claim/database waits and immediately before transport
  intent.

Never reuse a scan-start timestamp as proof that a quote remains valid.

### Lifecycle and follow-ups

`partner_manual_advisory_lifecycle_tick` is registered every minute and is
independent of option-chain scan success. It can issue an honest time-only
exit reminder and retires elapsed ideas after downtime, missed boundaries or a
next-day restart. Invalidation has precedence over routine reminder events;
each event has its own immutable deduplication key.

Price-triggered follow-ups require fresh public underlying data. A reminder
must not invent a current price. Management updates expire at the same-day
management deadline.

### Profiles and qualifications

Profiles are persisted by ID and monotonic version. A profile update retires
only that profile’s outstanding cards. Limits include stated round-trip costs.
The default scheduler profile is `default`, but it is intentionally not an
active authority until a saved `INTRADAY` profile exists.

Qualification requires:

- matching underlying, structure, `INTRADAY` horizon and policy version;
- non-future review timestamp;
- current `QUALIFIED_FOR_ADVISORY` state; and
- a registered research artifact reference with SHA-256 content fingerprint.

The artifact registry proves that a particular reviewed artifact was bound to
the qualification. It does **not** itself prove that the strategy is
profitable. Do not create dummy artifacts or qualifications merely to allow
messages to send.

## Relevant files

| File | Responsibility |
| --- | --- |
| `python-engine/partner_manual_advisory.py` | Advisory types, profile/qualification/artifact persistence, candidate validation, card rendering, lifecycle/reminder generation. |
| `python-engine/partner_orchestrator.py` | NIFTY/SENSEX scan consumer and scan-independent lifecycle tick. |
| `python-engine/hedge_advisory.py` | Hardened delivery claim/authorization/transport/recovery boundary. |
| `python-engine/routes_hedge.py` | Authenticated profile, artifact, qualification, cards, diagnostics and effective-settings APIs. |
| `python-engine/scheduler_setup.py` | Registered scheduler closures/jobs. |
| `python-engine/config.py` | Advisory gates, caps, quote limits and intraday timing settings. |
| `python-engine/tests/test_partner_manual_advisory.py` | Primary acceptance/regression tests. |
| `python-engine/tests/test_scheduler_closures_invoke.py` | Scheduler closure invocation contract. |
| `python-engine/tests/main_surface_golden.json` | Reviewed API/scheduler surface contract. |
| `python-engine/tests/add_job_census_golden.json` | Reviewed registered-job census. |

## APIs and safe operator workflow

All partner advisory routes require the existing internal authentication
mechanism. Important read-only routes are:

- `GET /partner/advisory/profile?profile_id=default`
- `GET /partner/advisory/effective-settings?profile_id=default`
- `GET /partner/advisory/cards`
- `GET /partner/advisory/diagnostics`

Write routes exist for a profile, research artifact and qualification. Do not
use them as exploratory live tests: when both delivery flags are enabled, a
valid profile and qualification can allow a subsequent live tick to dispatch.

Initial standalone profile target (save at the next monotonic version returned
by the GET endpoint; do not assume version `1` if one already exists):

```json
{
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

Leave conditional protection disabled in this initial profile. The profile is
not a personal sizing instruction: null limits do not mean unlimited risk or
liquidity.

## Release status and remaining gates

The source-code blockers from the intraday merge-readiness review are
implemented. **This is not yet a truthful active-production green light.**
Before activating delivery, the operator/developer must:

1. Create and preserve genuine frozen intraday research artifacts for NIFTY
   and SENSEX separately. They must include realistic entry delay, bid/ask
   execution, fees, no-fills, time exit, losses/drawdowns and limitations.
2. Register those immutable artifacts with their SHA-256 fingerprints.
3. Record matching, justified intraday qualifications for each index and
   structure. A synthetic fixture is not acceptable evidence.
4. Save the explicit `default` intraday profile at the next valid version.
5. Verify deployed effective settings, masked destination, current image SHA,
   feed readiness, scheduler registration and no-send/current-data previews.
6. Run a safe transport-double session test around entry cutoff, exit reminder,
   management deadline, restart and ambiguity/recovery cases.

The production environment and its switches have not been edited by this
development work.

## Verification protocol for every next increment

Before commit:

1. Inspect `git status --short`; preserve user-owned audit documents and
   unrelated changes.
2. Run the focused tests affected by the change. For advisory work, minimum
   baseline includes:

   ```powershell
   C:\Users\Urveesh\Desktop\trading-sentinel\python-engine\winvenv\Scripts\python.exe -m pytest `
     tests\test_partner_manual_advisory.py tests\test_partner_orchestrator.py `
     tests\test_hedge_advisory.py tests\test_hedge_routes.py `
     tests\test_scheduler_closures_invoke.py tests\test_main_surface_characterization.py -q
   ```

3. Compile edited Python modules with `python -m py_compile`.
4. Run `git diff --check`.
5. If a route or scheduler job intentionally changes, regenerate and review
   the surface/census golden files; never silently bypass their tests.
6. Add only intended files explicitly. Do not stage untracked audit plans,
   probes or review directories unless the user specifically asks.
7. Commit with an accurate message and push the existing branch.

If a full suite exceeds the tool timeout, report that fact accurately and run
the complete focused risk surface instead. Never report a full-suite pass that
did not finish.

## Existing planning and audit artifacts

Read the relevant current plan before new work. Important documents include:

- `docs/2026-09-08-intraday-partner-advisory-implementation-plan.md`
- `docs/2026-09-08-f9e721f-merge-readiness-review.md`
- `docs/2026-09-08-intraday-partner-advisory-implementation.md`
- `docs/2026-09-08-partner-rollout-audit-and-edge-improvement-plan.md`
- `docs/2026-09-08-partner-setup-guide-and-a734562-review.md`

These review documents and associated `docs/review-*` material are presently
untracked user artifacts. Preserve them; do not delete, rewrite or stage them
accidentally.

## Copyable instruction for the next session

> Work only in `C:\Users\Urveesh\Desktop\trading-sentinel` on branch
> `codex/production-correction-hedge-p0`. First read
> `docs/2026-09-08-development-handover.md` and the applicable latest plan or
> audit in `docs/`. Treat Production as read-only. Continue as the principal
> implementation and verification engineer: convert findings into code,
> acceptance tests, operational evidence and documentation; preserve delivery
> ambiguity/dedup/rate-limit safeguards; do not invent partner holdings,
> orders, fills, P&L, research evidence or future profitability. The partner
> scope is NIFTY/SENSEX, manual, intraday-only, defined-risk advisory. Inspect
> git status, keep user audit artifacts out of commits, run focused tests plus
> compile/diff checks, update reviewed route/scheduler golden contracts when
> intentional, commit/push the existing branch, and report precisely what is
> proven versus what remains an operational/research release gate.
