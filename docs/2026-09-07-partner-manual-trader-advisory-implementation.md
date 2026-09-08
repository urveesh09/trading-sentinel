# NIFTY 50 / SENSEX partner manual-advisory implementation

Date: 7 September 2026

## Delivered in Dev

The manual-trader product now has a distinct, non-executing advisory path in
`python-engine/partner_manual_advisory.py`. It does not use Sentinel cash,
paper fills, broker execution access or a fabricated partner portfolio.

| Requirement | Implementation | Evidence |
| --- | --- | --- |
| P1 scoped advice | Versioned profiles and explicit `MARKET_SETUP`, `CONDITIONAL_PROTECTION`, and `PERSONALISED_HEDGE` scopes | Market setups validate without holdings; personalised scope fails closed without reconciled portfolio authority. |
| P2 hedge-first selection | Same-direction NIFTY/SENSEX market candidates are ranked by bounded payoff after costs and executable spread; the lower-ranked overlap is suppressed | `select_preferred_market_candidates` tests. |
| P3 small strategy family | Same-index, same-expiry directional debit spreads; a conditional index protective-put card requires a stated exposure assumption | No naked legacy option card is reused by the new path. |
| P4 precision gate | Exchange/segment/contract/lot/tick metadata, all-leg bid/ask/depth/OI/volume/spread, quote age, expiry/lot consistency and structural payoff bounds | `test_partner_manual_advisory.py`. |
| P5 lifecycle | Stable advisory/economic IDs, persisted card status, profile supersession, explicit manual `NOT_REPORTED`/`TAKEN`/`SKIPPED`/`CLOSED` feedback | Delivery is never interpreted as a fill. |
| P6 observability | Separate two-minute `partner_manual_advisory_tick`; per-index unavailable/rejected/validated/overlap metrics | It runs after the legacy scan slot. |
| P7 delivery safety | Shadow cards are retained when delivery is off; owner-authorised queued cards use the durable claim/acknowledgement ledger | No legacy best-effort send is used, and `can_place_orders` is always false. |
| P8 optional AI | No AI is on the numeric/card authority path | Deterministic card rendering remains available. |

## NIFTY 50 and SENSEX controls

- NIFTY is bound to NSE/NFO; SENSEX is bound to BSE/BFO.
- Instrument IDs, expiries, strike steps, lot sizes and tick sizes are read
  from each current instrument book. The implementation rejects a wrong
  exchange/segment instead of translating a symbol or strike.
- The scheduled shadow loop explicitly evaluates both indices even if a
  legacy BFO signal flag is off. A missing SENSEX feed increments its own
  unavailable metric and does not prevent a qualified NIFTY preview.
- Simultaneous same-direction NIFTY/SENSEX cards are treated as overlapping,
  not diversification. The preferred candidate is chosen on conservative
  risk-adjusted economics and executable spread.

## New operator surfaces

- `GET` / `PUT` `/partner/advisory/profile`
- `GET` `/partner/advisory/cards`
- `POST` `/partner/advisory/cards/{advisory_id}/feedback`

All require the existing internal authentication. They never create an order
or send a message. A profile change supersedes old still-active cards, forcing
any future delivery path to revalidate current market/profile facts.

## Configuration and rollout boundary

The owner-approved Dev merge candidate enables `PARTNER_BOT_ENABLED`,
`PARTNER_MANUAL_ADVISORY_ENABLED`,
`PARTNER_MANUAL_ADVISORY_SHADOW_ENABLED` and
`PARTNER_MANUAL_ADVISORY_DELIVERY_ENABLED`. Delivery is still advisory-only:
it goes through the durable claim/acknowledgement ledger, is capped at two
ideas per day, and cannot place an order. The legacy naked-option, analytics,
portfolio-status and personalised-hedge sender paths remain suppressed while
the manual channel is active.

`PARTNER_HEDGE_ENABLED` is explicitly disabled in this rollout: it is the
separate reconciled-holdings monitor that produced operational status updates,
and is not needed for an independent manual trader. Existing F&O/proactive
research shadows remain enabled as read-only evidence collectors. Their
fixture/provider paths are intentionally not promoted to live trading or
partner delivery, and broker/order switches remain off.
Neither flag adds a Telegram send or broker-order consumer. The current
delivery lifecycle has not been expanded to live partner market advice in this
change, because that requires separately authorised routing, provider and
authenticated UI evidence. This is intentional: a live send must revalidate
the rendered card and preserve the existing durable ambiguity/recovery guards.

## Validation

Focused regression suite passed:

```
131 passed
python-engine/tests/test_partner_manual_advisory.py
python-engine/tests/test_partner_orchestrator.py
python-engine/tests/test_partner_content.py
python-engine/tests/test_hedge_advisory.py
python-engine/tests/test_fno_chain.py
python-engine/tests/test_fno_instruments.py
python-engine/tests/test_scheduler_tick.py
python-engine/tests/test_scheduler_closures_invoke.py
python-engine/tests/test_hedge_routes.py
```

The tests cover independent valid NIFTY and SENSEX candidates, stale/depth
rejections, wrong exchange rejection, no-holdings market previews, conditional
coverage wording, personalised fail-closed handling, same-direction overlap
suppression, profile supersession, feedback without inferred fills, scheduler
registration, and authenticated non-executing APIs.

## Remaining release evidence

This is not a claim that the strategies are profitable. Same-day expiry is
rejected, and holiday/rollover behaviour remains driven by the current
exchange instrument book. The owner has separately approved advisory delivery
for this merge candidate; it remains necessary to confirm the Production
Telegram credentials/destination and inspect early delivered cards. Production
was not modified by this work.
