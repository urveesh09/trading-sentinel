# Workstreams 2–5 — implementation record

Implemented in Dev on September 10. Production was not edited and no message,
order, feature gate, profile, or qualification was activated.

## Completed code: scheduling and coverage foundation

### Scheduler telemetry

- Added a bounded SQLite telemetry journal for selected latency-sensitive jobs:
  F&O tick, manual advisory tick, advisory lifecycle, quote collection, and
  hedge delivery recovery.
- Captures immutable boot/run/job identities, actual start/end timestamps,
  monotonic elapsed time, result/reason, and available stage durations.
  `scheduled_at` remains null for callback execution because APScheduler does
  not provide it there; it is never fabricated.
- Attached an APScheduler listener for genuine misfires and max-instance
  rejections. These remain distinct from a completed no-op or an in-flight
  invocation.
- Telemetry has a bounded retention tail and a short database busy budget. It
  is recorded only after the underlying work has completed; it does not relax
  freshness, increase concurrent stateful scans, or change exit/advisory
  authority.
- Added the read-only `/analytics/scheduler-timing` endpoint and dashboard
  timing card, including per-job run/rejection counts and p95/max duration.

### Producer coverage

- Added a shared read-only `/analytics/operational-coverage` response and
  dashboard card. It maps manual NIFTY/SENSEX advisory inputs, proactive
  completed-bar observations, archived F&O collection, and scheduler evidence
  separately.
- Reports configured/enabled state, attempt/success/observation/receipt
  clocks, source/run identity, counts, and reason. Missing evidence remains
  `UNAVAILABLE` or `UNCONFIGURED`; it is never represented as zero activity,
  zero opportunities, or zero P&L.
- Dashboard text explicitly identifies these as evidence/readiness views, not
  order, delivery, research qualification, or broker-reconciliation controls.

## Validation

- 101 focused Python tests passed: scheduler telemetry, scheduler registration
  census/closures, main API surface, operational coverage, advisory behavior,
  and hedge routes.
- Dashboard production build passed; gateway proxy syntax check passed.
- `git diff --check` passed.

## Still pending by design

1. **Measured Production contention conclusion:** Dev now records the required
   evidence, but real-session p50/p95/skip evidence must be observed after
   deployment before changing cadence, budgets, or concurrency.
2. **Five-warning reconciliation:** the existing dashboard/accounting and
   immutable statement importer remain in place. Event-level matching cannot
   be honestly completed without retained stable close/order identifiers and,
   where cash truth is needed, an explicitly scoped supported broker statement.
   No historical cash was rewritten.
3. **Production completed-bar adapter:** the coverage view correctly reports
   fixture/unconfigured/recorded states. A real Kite completed-bar adapter
   still needs a configured production account/run identity and observations;
   fixtures must not be relabelled as Production.
4. **Exact intraday two-leg replay and qualification:** no historical option
   depth stream or actual-policy replay result was fabricated. This remains
   contingent on preserved synchronized quote/depth, contract/lot and exit
   evidence. A resulting report may validly conclude insufficient evidence;
   it must not auto-qualify advisory delivery.

## Production prerequisites

Deploy this commit through GitHub, verify deployed revision identity, then
observe a market session. Use the new timing and coverage endpoints to review
real events. Any broker statement import requires the owner’s explicit account
scope and a supported statement export; no credentials should be supplied.
