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

### Round 1 corrections before any selection

- First run (`results/round1-nolock.json`) sold at the official close even when a stock closed on
  its low below the open (a lower-circuit lock has no buyers). Rule added: such a sale carries to the
  next session (its open, or its close if it opens and stays locked; delivery charges).
- M5 capacity was 0.5% of the 20-day median volume. Kite's 09:15 candle on gap-down days (Production
  feed, 149 stock-days) has a median value of Rs 37k, p25 Rs 1k: the opening auction is thin.
  M5/M6 now use 0.1%, and M8 (+100 bp entry, -50 bp exit) was added. Round 1 was rerun on both fixes.

### Round 1 result (`results/round1.json`, Rs 25,000; panels 1014 / 1518 / 1922 / 2325 / 26b)

| Arm | M1 net | robust (min M1-M8) |
|---|---|---|
| OAR_GAP | 718k / 548k / 521k / 358k / 26.7k | 75.9k / 19.4k / 12.0k / 38.1k / 2.2k |
| OAR_VAL | 536k / 386k / 253k / 199k / 21.4k | 81.2k / -8.2k / -25.0k / -24.9k / -2.7k |
| OAR_HIST | 595k / 473k / 417k / 330k / 31.3k | 48.6k / 3.8k / -6.6k / 6.8k / 4.4k |
| OAR_RANDOM | 544k / 447k / 401k / 216k / 18.9k | 42.8k / -2.7k / -8.6k / -23.6k / -4.9k |
| OAR_GAP3 | 627k / 480k / 496k / 349k / 26.7k | 74.8k / 17.3k / 13.4k / 39.2k / 2.2k |
| OAR_MID | 616k / 521k / 479k / 336k / 23.5k | 48.0k / 16.1k / 2.1k / 25.2k / -1.2k |
| OAR_GAP_1 | 914k / 646k / 565k / 363k / 38.7k | 80.2k / 15.7k / -2.3k / 26.6k / 7.7k |
| OAR_GAP_3 | 602k / 504k / 482k / 358k / 24.0k | 76.4k / 27.3k / 19.5k / 45.0k / -0.3k |
| OAR_NIGHT | 548k / 406k / 159k / -17k / -7.5k | negative from 1518 |

Lessons: deepest gap first is best and the deepest gaps (< -10%) are the best trades; liquid-first
loses under +100 bp; holding overnight loses (confirms the descriptive finding); capacity (M5/M6)
is the binding stress at Rs 25k (only 490 of 1,761 OAR_GAP trades fill under M5 on 1014). Win rate
falls from 73% (2011-14) to 45% (2023-25): older panels hold only today's survivors, so the
recent panels are the honest guide. These are still daily-bar models of auction fills.

## Round 2 (declared before any round-2 score)

Arms (Rs 25,000 unless stated, gap <= -2%, deepest first, exit at the official close):
OAR_CAP (skip names whose 0.1%-of-median-volume capacity cannot take a quarter of the ticket:
a causal filter on the 20-day median volume), OAR_CAP4 (OAR_CAP, four slots), OAR_NOBAND (skip
auction prices on a circuit-band level), OAR_CAP_NOBAND, OAR_HIST_CAP (own-history order with the
capacity filter), OAR_CAP_HISTOK (OAR_CAP, skipping names whose own shrunk history is below zero
after 3+ gap-down days). Smart's native Rs 2,000 book: OAR_GAP at one and two slots (S1, S2).
Read as round 1.

### Round 2 result (`results/round2.json`, `results/round2s-2000.json`)

Rs 25,000: the capacity filter, four slots, skipping circuit-band opens and own-history order
change M1 a lot and the robust net a little; none beats OAR_GAP's robust net in every panel
(OAR_GAP 75.9k / 19.4k / 12.0k / 38.1k / 2.2k; OAR_CAP 94.8k / 3.8k / 5.0k / 17.3k / 1.0k).
Rs 2,000 (Smart's book): S1 (one slot, deepest gap) M1 72.3k / 50.8k / 44.3k / 28.6k / 3.1k,
robust 22.4k / 11.2k / 9.5k / 6.2k / 1.0k, positive under every model in every panel.

### Minute-level development (`minute_oar.py`, `results/minute-dev.json`; seen data)

Production's own Kite minutes (Jul 30 - Nov 3; the 09:15 candle carries the opening match) at
Rs 2,000, one slot: uncapped +1,107 (close exit) / +588 (15:15 last trade -25 bp). With capacity =
10% of that day's 09:15 candle, +229 / +17: on 20 of 53 days the deepest gap was too thin for even
Rs 2,000. Skipping names whose prior-20-session median 09:15 candle x 10% cannot take a quarter of
the ticket (causal) gives +229 / +54 from Aug 10 (S1_THIN). +50 bp entry on top of that capacity
turns it negative (-73): the capped edge is about Rs 7.6 a trade. Same-dates Smart replays on the
Yahoo minutes (Sep 7 - 18, 30 names): V1 -38, V2 +7.

## Sealed exam (frozen in `exam-freeze.json` by `scripts/exam.py freeze`, opened once by `run`)

Primary S1_THIN (one slot, Rs 2,000, gap <= -2% deepest first, EQ only, thin-auction skip, buy at the
official open, sell at the official close, lock rule). Pass = all of:
1. capped close (10% of the 09:15 candle): closes >= 30, net > 0, ex-best > 0;
2. capped 15:15 exit (-25 bp): net > 0;
3. both capped versions beat Smart V1 and V2 replayed by `run_smart` (10 bp spread, same 89 names,
   same dates, Rs 2,000);
4. capped close positive in >= 4 of 7 months; 5. its drawdown <= Rs 500;
6. Jan-Jul daily Yahoo band universe, S1 at Rs 2,000: robust (min M1-M8) > 0.
Reported, not pass: uncapped, 25% capacity, +50 bp entry, two slots, Rs 25,000 daily OAR_GAP/OAR_GAP_3.
Wiring run on seen data (`results/exam-wire.json`, 15 s) replays all arms.
