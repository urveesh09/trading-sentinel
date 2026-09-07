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
| P7 delivery safety | This path produces `VALIDATED_SHADOW` cards only; `can_send` and `can_place_orders` are always false | No legacy best-effort send is used. |
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

Both advisory switches default to `false`. Setting
`PARTNER_MANUAL_ADVISORY_SHADOW_ENABLED=true` permits an explicitly enabled
no-send observation; `PARTNER_MANUAL_ADVISORY_ENABLED` does not grant
delivery authority.
Neither flag adds a Telegram send or broker-order consumer. The current
delivery lifecycle has not been expanded to live partner market advice in this
change, because that requires separately authorised routing, provider and
authenticated UI evidence. This is intentional: a live send must revalidate
the rendered card and preserve the existing durable ambiguity/recovery guards.

## Validation

Focused regression suite passed:

```
107 passed
python-engine/tests/test_partner_manual_advisory.py
python-engine/tests/test_partner_orchestrator.py
python-engine/tests/test_partner_content.py
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

This Dev change is a complete shadow/preview implementation, not a claim that
the strategies are profitable or ready for live partner delivery. Before a
separate live-delivery decision: collect current-data no-send cards for both
exchanges, validate holiday/rollover and same-day-expiry policies from current
exchange metadata, run the existing durable delivery lifecycle with a safe
fake transport and authenticated UI preview, and obtain an explicit owner
approval for destination and routing. Production was not modified.
