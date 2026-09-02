# Partner hedge advisory — Phases 1, 2 and 3

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

Phase 2 adds quote-backed covered calls, bull-put spreads, bear-call spreads,
iron condors, and whole-lot futures delta rebalancing. Premium strategies are
defined-risk except the covered call, which is admitted only against a
same-day broker-verified deliverable cash holding. The Phase 2 master switch
ships off until real-chain hand verification is complete.

Phase 3 adds the Greeks/volatility/event layer: expiry-day gamma exposure,
bounded-loss long straddles and strangles, defined-risk iron butterflies,
same-strike calendars, curated earnings/macro-event classification, and a
correlation-triggered futures overlay surface. The 1x2 ratio-spread builder is
research-only: it requires an explicit unbounded-risk opt-in and the scheduled
runtime never supplies one. Missing event, correlation, term-structure, quote,
or position truth suppresses the corresponding review.

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

F&O ledger quantities are broker-native exchange units, not contracts: one
65-unit lot is stored as `65`, never `1`. Open F&O quantities must be divisible
by the instrument-master lot size. Older ambiguous rows remain ineligible
until explicitly reconciled as `UNITS`.

Phase 2 credit structures use the executable bid for every SELL leg and the
executable ask for every BUY leg. They require IV rank history, exact market
mode, and verified support/resistance evidence. `CAUTION` is not treated as a
range; iron condors therefore fail closed until a true `RANGE` classifier is
available. Delta rebalancing uses futures only and declines sub-lot changes.

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
- `PARTNER_HEDGE_DELIVERABLE_MAX_AGE_MIN=5`
- `PARTNER_HEDGE_VIX_MAX_AGE_MIN=15`
- `PARTNER_HEDGE_COLLAR=false`
- `PARTNER_HEDGE_PHASE2_ENABLED=false`
- `PARTNER_HEDGE_PHASE2_MIN_DTE=7`
- `PARTNER_HEDGE_PHASE2_MAX_DTE=45`
- `PARTNER_HEDGE_COVERED_CALL_DELTA=0.30`
- `PARTNER_HEDGE_SPREAD_SHORT_DELTA=0.30`
- `PARTNER_HEDGE_CONDOR_SHORT_DELTA=0.16`
- `PARTNER_HEDGE_MIN_CREDIT_POINTS=10`
- `PARTNER_HEDGE_DELTA_THRESHOLD_LOTS=0.15`
- `PARTNER_HEDGE_PHASE3_ENABLED=false`
- `PARTNER_HEDGE_RATIO_SPREAD=false`
- `PARTNER_HEDGE_EARNINGS_EVENT=false`
- `PARTNER_HEDGE_PORTFOLIO_OVERLAY=false`
- `PARTNER_HEDGE_PHASE3_GAMMA_THRESHOLD=1000`
- `PARTNER_HEDGE_BUTTERFLY_MAX_DTE=3`
- `PARTNER_HEDGE_CALENDAR_MIN_IV_GAP=0.035`

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
call is mandatory. F&O intake/reconciliation must explicitly declare
`quantity_basis=UNITS`. Covered-call eligibility additionally requires
`deliverable_quantity`, `deliverable_as_of`, and `deliverable_source` from the
current trading day. Eligible sources are `kite_holdings` and
`broker_holding_snapshot`; a manual note cannot authorize a short call. Reusing
a broker order id with different position identity is rejected.

## Scheduling and rollout

`partner_hedge_tick` runs off-grid at minutes 07, 22, 37 and 52, second 10,
then self-gates to 09:25–15:15 IST and trading days. A kind/underlying/expiry is
sent at most once per day after successful delivery. Failed Telegram delivery
does not consume the dedup key and can be retried.

`partner_hedge_phase2_tick` runs at minutes 03 and 33, second 20, then
self-gates to 09:30–15:25 IST and trading days. It is zero-cost while the Phase
2 switch is off. Premium kinds have a four-hour per-kind throttle and cap of
four successful messages per day; delta rebalancing has a 30-minute throttle
and cap of eight. Send claims are atomic, so overlapping scheduler runs cannot
double-send; a failed delivery releases its claim for retry.

`partner_hedge_phase3_tick` runs off-grid at minutes 11 and 41, second 50 and
self-gates to 09:20–15:20 IST on trading days. It reads only reconciled
positions, broker instrument expiries, complete ATM term points, the curated
event CSV, and the maintained macro-event calendar. Its master switch ships
off pending paper validation. Phase 3 has a four-hour per-kind/underlying
throttle and four-message daily cap.

Before enabling the master switch, load and reconcile a test portfolio, inspect
`GET /partner/hedge/status`, and manually compare one generated NIFTY plan with
the live broker chain. Production promotion remains GitHub-only.
