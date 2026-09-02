# Partner hedge advisory — Phase 1

Phase 1 adds advisory-only, protection-first partner messages. It does not
place orders. The advisory switch is enabled, while its reconciliation,
freshness, liquidity and session gates continue to fail closed.

## Shipped scope

- Reconciled partner-position ledger with broker-order idempotency.
- Rupee delta-notional portfolio aggregation and conservative whole-lot
  futures sizing.
- Quote-backed protective-put reviews using an actual 21–60 DTE exchange
  expiry and executable ask.
- Covered-collar constructor and formatter. Automatic collar messages remain
  disabled until the deliverable holding can be proved to cover the short call.
- Timestamped, named-source India-VIX intake and informational posture message.
- Plain-text Telegram formatting with data timestamps, actual contracts,
  coverage, premium risk, residual exposure and an advisory disclaimer.
- Restart-safe delivered-message deduplication.
- On deliberate hedge-pipeline enablement, legacy ORB/momentum tips, raw
  PCR/IV/OI/pin alerts, and legacy morning/EOD summaries are suppressed by
  default. Regime transitions and risk-limit cautions remain available.

## Safety invariants

The advisory produces no message unless every position in the calculation is:

1. open;
2. explicitly reconciled;
3. carrying a fresh current price;
4. complete enough to calculate risk (options require current Greeks and an
   underlying reference price).

Option plans additionally require a fresh chain snapshot, actual instrument
expiry, two-sided quotes, configured OI/volume, acceptable spread, and at least
one day to expiry. Phase 1 selects 21–60 DTE by default. Protective puts round
down to whole lots so the hedge cannot become a speculative over-hedge.

## Configuration

`PARTNER_HEDGE_ENABLED=true` is the master switch. It is independent from
`PARTNER_BOT_ENABLED`; both must be true before messages can be sent.

Important settings:

- `PARTNER_HEDGE_TARGET_RATIO=0.50`
- `PARTNER_HEDGE_MIN_DTE=21`
- `PARTNER_HEDGE_MAX_DTE=60`
- `PARTNER_HEDGE_MAX_SPREAD_PCT=0.15`
- `PARTNER_HEDGE_MAX_QUOTE_AGE_SEC=120`
- `PARTNER_HEDGE_POSITION_MAX_AGE_MIN=5`
- `PARTNER_HEDGE_VIX_MAX_AGE_MIN=15`
- `PARTNER_HEDGE_COLLAR=false`

Lot sizes and expiry dates are always read from the daily broker instrument
master; none are hardcoded in advisory code.

## Authenticated intake

All endpoints require `X-Internal-Secret`.

- `POST /partner/hedge/positions` — create a pending position.
- `POST /partner/hedge/positions/{id}/reconcile` — confirm the observed broker
  quantity and current risk inputs.
- `POST /partner/hedge/positions/{id}/close` — reconcile quantity to zero.
- `GET /partner/hedge/positions` — inspect the ledger.
- `POST /partner/hedge/vix` — record a sourced VIX observation.
- `GET /partner/hedge/status` — readiness and reconciliation counts.

Creating a row never makes it advisory-eligible. The separate reconciliation
call is mandatory. Reusing a broker order id with different position identity
is rejected.

## Scheduling and rollout

`partner_hedge_tick` runs off-grid at minutes 07, 22, 37 and 52, second 10,
then self-gates to 09:25–15:15 IST and trading days. A kind/underlying/expiry is
sent at most once per day after successful delivery. Failed Telegram delivery
does not consume the dedup key and can be retried.

Before enabling the master switch, load and reconcile a test portfolio, inspect
`GET /partner/hedge/status`, and manually compare one generated NIFTY plan with
the live broker chain. Production promotion remains GitHub-only.
