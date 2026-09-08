# Partner advisory rollout implementation

Date: 8 September 2026.  This note records the Dev implementation of the
release corrections and advisory improvements from
`2026-09-08-partner-rollout-audit-and-edge-improvement-plan.md`.

## Scope and safety boundary

The service remains NIFTY/NSE and SENSEX/BSE advice only.  It does not place
orders, read a partner broker account, infer holdings, or claim realised
partner P&L.  An enabled environment variable is necessary but never
sufficient for delivery: current quotes, profile, recorded qualification and
the durable delivery authorizer must all agree.

## Implemented requirements

| Requirement | Implementation | Evidence |
| --- | --- | --- |
| R1 economics and structure | `python-engine/partner_manual_advisory.py` independently recomputes a two-leg vertical from executable BUY ask/SELL bid, checks direction/expiry/type/ratio/lot and rejects non-positive post-cost expiry reward. Displayed debit/loss/profit must reconcile to the oracle. | `test_full_lot_depth_and_independent_expiry_oracle_cannot_be_bypassed` |
| R2 evidence and profile | A versioned `partner_advisory_strategy_qualifications` registry, strict profile validation and authenticated qualification API govern queue eligibility. Research cards remain visible previews and cannot queue. | `test_research_card_cannot_queue_and_expired_card_never_reaches_transport`; `test_profile_structure_risk_and_window_are_delivery_gates` |
| R3 final freshness | Dispatch obtains an injectable fresh clock at the final boundary and refuses an expired card before transport. Manual authorisation rechecks stored card/profile/evidence. | fake-clock expiry assertion in `test_research_card_cannot_queue_and_expired_card_never_reaches_transport` |
| R4 liquidity and routing | Executable depth is at least lot × ratio for every leg, candidates are validated before overlap ranking, and advice chooses the nearest strictly future option expiry. | full-lot-depth assertion and `resolve_advisory_expiry` |
| R5 generations | Card ID is now an immutable economic generation (not a timestamp); a stable delivery-thesis ID prevents changed economics from becoming duplicate entry notices. Changed previews supersede the prior active generation. | `test_material_economics_create_linked_generation_without_quote_time_churn` |
| R6 operability | `GET /partner/advisory/effective-settings` reports only non-secret effective gates. `POST /partner/advisory/qualifications` records review evidence. | authenticated route implementation in `python-engine/routes_hedge.py` |
| E1 card quality | Cards include numerical trigger, invalidation, target/review level and horizon when the signal supplies them. | rendered-card assertions and manual card renderer |
| E2 protection | Profiles can explicitly supply an exposure assumption and coverage units. Only then can the scheduled scanner build a same-index conditional protective-put card; no holding is inferred. | profile validation and `partner_manual_advisory_tick` |
| E3/E4 updates | Published ideas can create one persistent target-zone or invalidation update from a fresh public underlying observation. Updates use a separate `PARTNER_MANUAL_ADVISORY_UPDATE_DAILY_CAP` and hardened delivery path. | `test_market_condition_management_update_never_reads_partner_orders` |
| E6 diagnostics | `GET /partner/advisory/diagnostics` exposes the per-index lifecycle funnel, delivery blockers and update state without converting delivery into a P&L claim. | `test_diagnostics_are_per_index_and_do_not_claim_partner_pnl` |

## Configuration truth

`PARTNER_MANUAL_ADVISORY_ENABLED` and
`PARTNER_MANUAL_ADVISORY_DELIVERY_ENABLED` must both be true before any
manual advisory card or update can transport. `PARTNER_MANUAL_ADVISORY_SHADOW_ENABLED`
alone only permits preview processing. Existing environment values override
code defaults. A stored profile must name a non-empty holding horizon and
any configured structure/capital/risk/window limits are enforced.

The default profile is deliberately incomplete (`holding_period=None`), so it
cannot authorise an actionable delivery until an operator saves an explicit
profile through the authenticated API. Qualification is also explicit and
requires supported index, structure, horizon, policy version, dataset
reference and review timestamp.

## Remaining operational work

No implementation can establish future profitability. Before relying on this
for meaningful capital, create an explicit profile and qualification from
frozen research, inspect the effective-settings endpoint in the deployed
environment, exercise safe no-send/current-data previews, and monitor the
per-index funnel. The longer-horizon E5 frozen-fold entry/exit comparison and
pre-market preparation brief remain separate product work; they are not
represented as proven edge by this rollout.
