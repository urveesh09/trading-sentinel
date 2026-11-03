# The other side: a defined-risk premium seller on expiry afternoons — frozen before scoring

Written November 3, 2026, after the auction test, before any seller structure is scored anywhere.

## Why

Every buyer result in this repo points one way. Cheap OTM tickets held to the close lose in both years
(E03 census). Near-the-money tickets lose (E03.2). Production's own auction strangle, re-valued with its
settled legs, lost: B -Rs 3,007 over five days, BH (held through the auction) -Rs 6,313 over four, every day
negative. On expiry day options are priced above what they pay. No study here has scored the seller's side.

This is a different business from the partner's buying: it needs margin, and a gap can reach the full
defined loss. It is studied to learn where the money goes, not as a buy recommendation.

## The structure (one "iron butterfly", one lot of each leg)

At decision time `T`, `K` = the strike nearest the index. **Sell** the `K` call and the `K` put; **buy** the
call `W` points above and the put `W` points below. Most it can lose = `W` minus the credit, times the lot,
plus charges. Strikes within `W <= 200` of the index are always in the history (four steps).

Grid, all reported (12 arms): `T` in {13:00, 14:00}; `W` in {2, 4} strike steps (NIFTY 100 / 200 points,
SENSEX 200 / 400); exit at 15:28 (held), or a stop when
the cost to close reaches the credit plus `S` times the credit, `S` in {0.5, 1.0}. Fills as the labs: next
bar's open with half the frozen spread against us (ordinary); double spread plus max(tick, 1%) (adverse);
next bar's worst high/low (severe). A leg with no price is closed at its intrinsic against the index
(counted). Native NFO / BFO charges per leg. NIFTY 65, SENSEX 20 per lot.

## Data and passes

1. **NIFTY 2024 and 2025 expiry minute chains** (105 days; seen for buyer rules, never for a short structure).
   An arm passes if net is above zero in each year at ordinary AND adverse fills, net without the best
   day is above zero in each year, and the worst day is above -Rs 10,000.
2. **Closing-auction era check** (the 9 Production days, Oct 6 - Nov 3, 10-second bids/asks): the
   passing arms with `T` = 13:00 and 14:00, sold at the next snapshot's bids, bought at its asks; held arms
   close at the first snapshot from 15:31 on the asks/bids, or settle at intrinsic. Reported, not a pass
   test: nine days.

Margin is not modelled: the broker's calculator decides it (expected well above Rs 25,000 for one set).
Nothing here changes the runtime.
