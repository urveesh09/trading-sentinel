# Partner input corrections — implementation record

Implemented in Dev on September 10. Production was not edited.

## Delivered

- Corrected the scanner/orchestrator contract: a valid scanner result with no
  ORB direction and no option-chain snapshot is now recorded as
  `NO_ENTRY_SETUP`, preserving its explicit rejection reason. It is no longer
  reported as an unavailable input.
- Kept actual input failures distinct: explicit scanner errors,
  missing signals, missing advisory expiry, fired signals without a chain,
  fresh-chain failures, candidate construction failures and validation
  failures each have a separate stage.
- Added durable, per-index (`NIFTY` and `SENSEX`) input-status evidence:
  attempt, observed and receipt clocks; calculated freshness; last successful
  observation; profile state; and strategy-qualification state. A market
  observation is diagnostic evidence only and never means an advice card is
  qualified, deliverable, or executed.
- Decoupled active-card public-condition management from creation of a new
  ORB entry. Fresh just-closed futures bars can trigger invalidation/target
  management checks without a new direction or an unnecessary full-chain
  request. Malformed, future, stale, or unusable bars do not become market
  conditions.
- Added an authenticated setup/readiness API and Dashboard panel. It makes
  saved-versus-missing profiles and independent NIFTY/SENSEX state visible,
  and can save a versioned intraday profile with optional positive capital and
  risk ceilings. It cannot create research evidence, qualify a strategy, send
  advice, or place orders.

## Deliberate limits

This correction does not manufacture research evidence or activate delivery.
An operator still needs genuine strategy qualification before any advisory can
be delivery-eligible. The system remains manual-advisory only: it does not
monitor partner orders or place orders.

## Validation

- 129 focused Python tests passed, covering advisory persistence, orchestrator
  classifications, active-condition management, authenticated routes,
  scheduler contracts, and API surface characterization.
- Dashboard production build passed.
- Gateway proxy syntax check passed.
- `git diff --check` passed.

The full Python suite was started twice but did not complete within the local
tool execution window; both self-started test processes were stopped. The
focused suite above completed successfully and covers every changed Python
surface.
