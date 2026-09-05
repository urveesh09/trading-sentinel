# Production correction implementation — 5 September 2026

## Scope completed in Dev

This implementation addresses the P0 hedge-delivery and advanced-phase rollout
gaps in the supplied 5 September correction plan. It was made only in the Dev
working copy on branch `codex/production-correction-hedge-p0`; Production source,
configuration, databases and partner messaging were not changed.

### Partner hedge service state and input status

`python-engine/hedge_advisory.py` now creates `partner_hedge_service_state`.
The Phase-1 tick records the last input refresh, last evaluation, exact
no-advice reason, last candidate, last attempted send and last acknowledged
delivery. Input status distinguishes:

- `NO_PORTFOLIO_INPUT`
- `UNRECONCILED_PORTFOLIO_INPUT`
- `STALE_PORTFOLIO_INPUT`
- `UNAVAILABLE_EXPIRY`
- `STALE_OR_UNAVAILABLE_CHAIN`
- `NO_HEDGE_NEEDED`

The first three conditions produce a daily deduplicated setup-status notice,
not a fabricated personalized hedge quantity. The existing VIX flow remains
separate and informational.

`python-engine/routes_hedge.py` exposes that sanitized state through the
authenticated `GET /partner/hedge/status` endpoint. No credentials are returned.

### Delivery acknowledgement and bounded recovery

`python-engine/partner_bot.py` now provides `PartnerSendResult` and
`send_partner_result()`. Telegram acknowledgement message identifiers are
captured when returned by the API. HTTP rejection, rate limiting, network
failure and timeout ambiguity are represented distinctly. The legacy boolean
`send_partner()` API remains for existing non-hedge partner jobs.

`python-engine/hedge_advisory.py` stores the delivery state and acknowledgement
on each hedge record. Failed sends no longer disappear from the delivery table;
they remain recoverable up to `PARTNER_HEDGE_DELIVERY_MAX_ATTEMPTS` (default 3).
An in-flight claim remains leased until recovery, while an expired claim is still
safe against completion by an older owner. A timeout is not represented as proof
of non-delivery, so exactly-once Telegram delivery is not claimed.

### Hedge-specific summaries and advanced-phase gating

`python-engine/hedge_formatters.py` adds a hedge-only morning/EOD summary that
states reconciliation coverage and input status without personalizing advice.
`python-engine/scheduler_setup.py` schedules those summaries independently of
the suppressed legacy directional brief/wrap jobs.

`python-engine/config.py` changes Phase 2 and Phase 3 defaults to disabled and
adds shadow-mode switches, both enabled by default. `python-engine/hedge_advisory.py`
now evaluates advanced candidates in shadow mode but permits partner-facing
sends only when the phase is explicitly configured on **and**
`assess_phase_readiness()` returns `READY`. Status exposes configured, shadow,
validated and sending states. This keeps Phase-1 protective reviews and setup
messages available while advanced strategies accumulate real evidence.

`docs/HEDGE_PIPELINE.md` was updated to remove the former contradictory Phase-2
default and to document service state, acknowledgements, summaries, retry
semantics and readiness-gated shadow delivery.

## Intentionally not implemented

The plan correctly requires the partner's actual broker/account mapping before
an automated portfolio-source adapter can be built. That information was not
provided, so no broker feed was guessed and Sentinel paper/operator positions
are not treated as partner holdings. The existing authenticated manual intake
and reconciliation contract remains the supported source-neutral path.

The P1/P2 execution-capital, scheduler-performance, universe/bootstrap, EDGE,
financial-reporting and operator FNO-notification packages are deliberately
separate follow-on scopes. They do not block this P0 advisory delivery path.

## Validation performed

- `python -m compileall` completed successfully for each changed Python module.
- `git diff --check` completed successfully.
- Added regression coverage for acknowledged hedge delivery, bounded failed
  delivery, default advanced-phase status, and non-personalized daily summaries.

The repository's checked-in `python-engine/.venv` is a Linux virtual environment
and cannot run on this Windows host. The host Python also lacks the project test
dependencies; installing the pinned requirements cannot complete because the
pinned pandas build is not compatible with the available host interpreter.
Therefore the full pytest suite must be run in the project Linux/CI environment
before merge. No live Telegram canary was sent; the plan requires explicit
destination/content review and send authorization for that deployment step.
