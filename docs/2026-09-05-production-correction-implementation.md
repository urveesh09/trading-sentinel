# Production correction implementation — 5 September 2026

## Scope completed in Dev

This implementation addresses the P0 hedge-delivery and advanced-phase rollout
gaps in the supplied 5 September correction plan, followed by the independent
P1/P2 operational-correctness work below. It was made only in the Dev
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

### New-entry capital preflight

`node-gateway/server/services/kite.js` now exposes a broker-margin read, and
`node-gateway/server/services/executor.js` requires fresh usable cash evidence
immediately before a new BUY entry. Unknown margin data fails closed with an
explicit `MARGIN_EVIDENCE_UNAVAILABLE` execution error; insufficient cash
returns the non-retryable `INSUFFICIENT_MARGIN` (HTTP 409) outcome defined in
`node-gateway/server/utils/errors.js`. Collateral is deliberately excluded from
the cash calculation. Existing exit and protective-order paths do not consult
this preflight, so a capital restriction cannot trap an open position.

### P1 coverage and notification corrections

`python-engine/penny_edge_engine.py` now distinguishes `insufficient_history`,
`price_out_of_range`, `invalid_volume`, `invalid_data`, and `stale_data` before
reporting `no_setup`. The ₹5–₹55 policy and strategy logic are unchanged.

`python-engine/penny_universe.py` can return opt-in history diagnostics without
changing its default return type. Skip totals now balance by `unresolved_symbol`,
`empty_response`, `short_history`, `fetch_failure`, or `computation_failure`.
This identifies the reason actually observed; it does not assert that every raw
instrument should be eligible.

`python-engine/fno_orchestrator.py` includes defined-risk paper opens and
closes in the immediate F&O message formatter. `python-engine/scheduler_setup.py`
now sends DR-only activity and requires a successful HTTP acknowledgement from
the operator notification gateway; failures remain visible in the scheduler
log rather than being silently accepted. The F&O tick summary now also emits
major stage durations (futures quote/history, exit management, defined-risk
book and entry evaluation/management), so a cadence change can be evaluated
against measured work rather than inferred from an APScheduler skip.

### P2 liveness semantics

`python-engine/ops_watchdogs.py` writes a per-process scheduler boot id, tick
count and process id to the atomic scheduler heartbeat and logs a distinct
`scheduler_progress_tick`. `python-engine/tools/runtime_audit.py` now reports
process heartbeat and scheduler-loop progress separately, segments scheduler
progress by boot id, and retains raw pre-market/overnight gaps under
`outside_market_gaps`. Only intervals that overlap a weekday 09:15–15:30 IST
market session produce a P0 liveness finding. The persistent `MAX` gap metric
was not changed.

## Remaining deployment inputs and non-code work

The plan correctly requires the partner's actual broker/account mapping before
an automated portfolio-source adapter can be built. That information was not
provided, so no broker feed was guessed and Sentinel paper/operator positions
are not treated as partner holdings. The existing authenticated manual intake
and reconciliation contract remains the supported source-neutral path.

The production-specific September 4 P&L reconciliation fixture, post-promotion
skip-rate measurements, and a scheduler contention profile require retained
Production evidence and a promoted observation window. They were not fabricated
from Dev data. Ledger remains authoritative; no ledger or outcome rows were
rewritten, and no strategy parameters were tuned. A live partner canary still
requires explicit destination/content review and send authorization.

## Validation performed

- `python -m compileall` completed successfully for every changed Python module.
- `node --check` completed successfully for the changed gateway services.
- `git diff --check` completed successfully.
- The Windows project environment (`python-engine/winvenv`) ran 113 focused
  hedge, readiness, scheduler, runtime-audit, Penny and F&O regression tests:
  all passed (one unrelated Starlette deprecation warning).
- `npm test -- --runInBand tests/unit/executor.test.js` ran 44 gateway executor
  tests: all passed, including the insufficient/unavailable-margin cases.

No live Telegram canary was sent; the plan requires explicit destination/content
review and send authorization for that deployment step.
