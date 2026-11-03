# The closing-auction drift — plan, frozen before scoring (November 3, 2026)

Owner request (November 3, after two E03.2 searches found nothing): look for what the system is missing,
at the micro level, with full freedom. Not another threshold search.

## What is new here

Every expiry study in this repo used 2024/2025 minute chains, when NIFTY's close was a 30-minute average.
**Since August 3, 2026 the market works differently** (`docs/2026-10-05-expiry-day-paper-book.md`,
`docs/2026-09-13-workflow-j-deep-research.md`): F&O stocks stop continuous trading at 15:15, a closing
auction sets their close (order entry 15:20-15:30, matching 15:30-15:35), the index value freezes from 15:15
to about 15:29, and **expiring options keep trading until 15:40 and settle at the auction close.** No study
here has scored what options do inside that window.

The one day looked at before this plan (October 6, NIFTY, Production recording) shows the mechanism:
the index froze at 22,717.70; the settlement level implied by call-minus-put prices (the "synthetic") rose
from 22,718 at 15:16 to 22,739 (15:20), 22,750 (15:22), 22,767 (15:28) and 22,773 (15:29); the index then
printed the auction close, 22,776.10 (+58.4), and every option sat at intrinsic. The options market found
the auction price gradually, and at 15:22 it had priced only about half of the move.

## Hypotheses (fixed now)

Notation per expiry day: `S0` the frozen index value (index at 15:20); `F` the settlement (the published
index close); `M = F - S0`; `Y(t)` the synthetic at time `t`; `D(t) = Y(t) - S0`, the drift priced so far;
`R(t) = (F - Y(t)) x sign(D(t))`, the move still to come in the drift's direction. Decision time
`t* = 15:22:00`; a day is **signalled** when `|D(t*)| >= 0.04%` of `S0` (about 9 NIFTY / 30 SENSEX points).

- **H1, direction:** `sign(D(t*)) = sign(M)` on at least 70% of signalled days.
- **H2, under-reaction:** mean and median `R(t*)` above zero, and `R(t*) > 0` on at least 60% of
  signalled days. H2 is what a buyer can trade: the option is priced at `Y`, the money is paid at `F`.

## Data (fixed now; no download)

| Source | Days (closing-auction era) | What it has |
|---|---|---|
| Production paper-book recordings (`expiry_paper_ticks`, read-only copies in `2026-11-02-expiry-e01/_local/export` and `2026-11-03-expiry-e03/_local`) | NIFTY Oct 6, 13, 19, 27, Nov 3; SENSEX Oct 8, 15, 22, 29 | every 10 s: index, future, 34 strikes' best bid/ask and depth |
| Breeze ten-second export (`breeze-history-20261029/data/expiry-10second-20261103`) | NIFTY Aug 4 - Sep 29 (9); SENSEX Aug 6 - Oct 1 (9, the full Sep 24 file) | last trades of the opening-ATM call and put, to 15:29:50 |
| Breeze history database, read-only | the export days | index minutes (frozen value, published close) |

`Y(t)`: Production = median over the three strikes nearest `S0` of strike + call mid - put mid, quotes at
most 20 s old; export = opening-ATM strike + call last - put last, both 10-second bars at most 30 s old.
`F`: Production = index at the first snapshot from 15:31; export = index minute close at 15:35.
**October 6 is excluded from every pass count** (it suggested the hypothesis) and reported apart, leaving
26 unseen days: 9 NIFTY and 9 SENSEX export days, 4 NIFTY and 4 SENSEX Production days.
Unavailable values (missing legs, stale quotes) are counted, never zero.

## The trade (Production days only: they have bids, asks and depth)

At the first snapshot from 15:22:00, on a signalled day: buy one lot of the call (drift up) at the
highest strike at or below `Y`, or the put (drift down) at the lowest strike at or above `Y`: in or at the
money relative to the synthetic, so most of the premium is value, not hope. Buy at the next snapshot,
walking the asks, limit 8% above the decision ask. Sell at the first snapshot from 15:31:00 walking the bids
(the settlement is printed by then); unsold by 15:39:50, value at intrinsic at `F` less 0.15% exercise
STT. Native NFO/BFO charges; NIFTY 65 / SENSEX 20 per lot. Controls on the same days and snapshots:
the opposite side, and holding to settlement.

**Trade passes** if, on the eight unseen Production days, total net is above zero, mean net per signalled
day is above zero, and total net without the best day is above zero.

## What each outcome means

- H1, H2 and the trade pass: build a **disabled** paper shadow for forward expiries (NIFTY Tuesdays,
  SENSEX Thursdays), with the owner's decision to switch it on. Not real money: 26 days are not proof.
- H1 passes, H2 fails: the options price the drift as fast as it is visible. A learning, nothing to trade.
- H2 clearly negative: the options overshoot; a fade becomes a forward hypothesis only.

Diagnostics, reported but never pass criteria: the same measures at 15:16-15:29, the future's drift
(future minus its 15:00-15:14 basis), auction-move sizes, and per-day detail.
