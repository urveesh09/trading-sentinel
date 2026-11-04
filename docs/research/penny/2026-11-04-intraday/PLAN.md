# Penny intraday modules: Smart, then Classic MIS and Classic CNC (Nov 4, 2026)

Owner (Nov 4): "since penny edge is done are smart module done? If not do them also after that go
ahead with the other 2 modules under penny." Penny's modules are EDGE (overnight work done in
overnight v2/v3), Smart (V1, V2: intraday paper books on Rs 2,000), Classic MIS (breakout,
10:30-14:30, exit 15:00) and Classic CNC (Connors RSI(2), multi-day). Research only, Dev only;
V1/V2 policy files are hashed and stay byte-identical; anything new runs beside them on paper.

## Problem

- Smart V1 Production paper record Oct 5-21: 68 closes, 9 wins, -Rs 163 on Rs 2,000
  (penny_smart_v2.py docstring). The strategy-search study (Nov 4, same day) replayed V1 -117.00,
  V2 -85.31 on Oct 19 - Nov 3; its best Smart variant (-52.17) still loses, by trading less.
- Overnight v2/v3: penny-band stocks drift down by day (about -0.5% open to close) and up overnight.

## Descriptive findings before any rule (development data, seen)

`scripts/tod.py`, `scripts/gap_minutes.py` (Yahoo 1-minute Sep 7 - Nov 3 2026, 118 band names,
3,361 stock-days) and `scripts/gap_daily.py`, `scripts/gap_slices.py` (Yahoo daily 2010 - Nov 3 2026,
**Jan 1 - Jul 31 2026 excluded**):

1. The intraday drift is negative in almost every clock segment; names up > 2% by 10:30 lose
   -0.49% more to 15:00 (Smart/Classic buy exactly these). No intraday window after 09:30 earns a spread.
2. The opening auction overshoots. Open to close by gap bucket is positive for every gap-down bucket
   and negative for every gap-up bucket, in every year 2010-2026 (gap -2..-3%: +1.12%, -3..-5%:
   +1.99%, +2..+5%: -1.92%). Kite's official daily bars agree (+1.60% vs Yahoo +1.71% on 3,379
   overlapping gap-down days). Liquid names too (median value > Rs 1 crore: +1.43%).
3. Most of the recovery is between the auction print and the first minutes: for gap <= -2%,
   open -> 15:15 +1.66% but 09:16 -> 15:15 +0.71% (last trade, before paying a spread).
   Only an order in the pre-open auction (09:00-09:08) earns it.
4. Holding a gap-down name overnight loses (next night -0.68% for gaps -3..-10%).

## Hypothesis H1 (Smart V3, "opening-auction reversal", OAR)

Buy penny names that open at least 2% below the previous close in the pre-open auction; sell the
same day at the official close (post-close session) - an intraday round trip at two auction-type
prices, intraday charges, no stop (a stop sells the recovery). Same-day trades need EQ series
(trade-for-trade BE/BZ names cannot be sold the day they are bought).

## Data windows

- Development: daily Yahoo 2011-2025 and Aug 1 - Nov 3 2026 (panels 1014, 1518, 1922, 2325, 26b);
  minutes Sep 7 - Nov 3 2026. All of it was seen by earlier studies (close -> open), not for this
  open -> close hypothesis.
- **Sealed exam: Jan 1 - Jul 31 2026.** (a) Yahoo daily for all band names; (b) the Kite minute
  archive `docs/research/kite/2026-10-05-penny-h1/_local/validated-kite.sqlite` (89 names, never
  scored: the owner skipped round 3 on Oct 7). The Jan-Jul daily bars were inside the overnight
  development panels (close -> next open); their open -> close was never measured. Opened once by
  `scripts/exam.py run` after `scripts/exam.py freeze` is committed.

## Accounting and fills

Fixed bankroll (Rs 25,000 for comparability with the overnight book; Rs 2,000 = Smart's native
book), profits withheld, losses reduce the next day's capital, K equal slots. Intraday charges
(`calc_penny_costs(..., is_intraday=True)`). Fill models, robust = minimum:
M1 full at the auction price and the official close; M2 / M3 a quarter / half of winning tickets
denied (ten-seed means); M4 half denied, one draw per day; M5 capacity 0.5% of the 20-day median
volume; M6 M5 + M3; M7 +50 bp entry and -50 bp exit (selling at a 15:15 bid instead of the close).
An order that cannot fill still uses its slot (no replacement).

## Round 1 (declared before any OAR score)

Arms, Rs 25,000, two slots unless stated, gap <= -2%, exit at the official close:
OAR_GAP (deepest gap first), OAR_VAL (most liquid first), OAR_HIST (stock's own shrunk past
gap-down reversion first), OAR_RANDOM (null order), OAR_GAP3 (gap <= -3%), OAR_MID
(-10% < gap <= -2%), OAR_GAP_1 / OAR_GAP_3 (one / three slots), OAR_NIGHT (OAR_GAP, held to the next
open, delivery charges). Read: robust net and M1 net per panel; consistency across all five panels
picks round 2. Nothing from round 1 is promoted by itself.
