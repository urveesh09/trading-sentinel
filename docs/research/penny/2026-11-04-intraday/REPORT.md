# Penny intraday modules - report (November 4, 2026)

Smart (V1, V2), then Classic MIS and Classic CNC. Plan, rounds and every result: `PLAN.md`.

## Result in plain words

1. **Smart V1/V2 cannot be fixed by tuning.** Penny stocks drift down during the day (about -0.5%
   open to close, in every year 2010-2026), and names already up 2% by 10:30 lose another 0.49% by
   15:00. Smart and the Classic breakout buy exactly those names. The other agent's three Smart
   rounds (same day) reduced the loss only by trading less.
2. **The one intraday edge is the opening auction.** A penny stock that opens 2% or more below its
   previous close recovers during the day: +1.1% (gap -2 to -3%) to +2.9% (gap -5 to -10%) from
   the open to the close, positive in every year 2010-2026, confirmed by Kite's official prices.
   Most of it happens between the auction price and the first minutes (open -> 15:15 +1.66%;
   09:16 -> 15:15 +0.71%), so only an order in the pre-open auction (09:00-09:08) earns it.
3. **Smart V3 = buy that stock in the auction, sell at the official close the same day.** One
   ticket on Smart's Rs 2,000 book, deepest gap first, skipping names whose auction is too thin
   for the ticket. **It passed its sealed check** (Jan-Jul 2026 Kite minutes, never scored before):

| Jan-Jul 2026, 89 names, Rs 2,000 | Closes | Net |
|---|---:|---:|
| **Smart V3**, at most 10% of the opening volume, sold at the close | 104 | **+2,936** |
| Smart V3, same, sold at 15:15 | 104 | +2,603 |
| Smart V3, paying 0.5% over the auction price | 103 | +1,899 |
| Smart V1 (same names, same days) | 1,077 | -1,117 |
| Smart V2 (same names, same days) | 1,159 | -802 |

   Positive in 6 of 7 months (January -179); V1 and V2 lost in every month. Without the 7 silver,
   gold and metal ETFs in that universe: +2,328 on 87 closes.
4. **Capacity is the limit, not the idea.** Penny opening auctions are thin (Kite's 09:15 candle on
   gap-down days: median Rs 37k, a quarter of names under Rs 1k). At Rs 2,000 it fits; at Rs 25,000
   the same rule's modelled result shrinks several-fold once capacity is enforced.
5. **Classic MIS and Classic CNC have no edge to improve.** Classic breakouts earned -0.13% and
   +0.09% a trade *before* any spread or charges in the two minute samples. Classic CNC's RSI(2)
   rule fired 60 times in 16 years (-0.25% over three days); without its confirmation, 45,827
   oversold uptrend setups lost -0.27% over three days. One small window (breakouts after 13:00,
   +0.7% in both samples, 29 trades) is now a paper shadow for forward evidence, nothing more.

## Development (seen data)

Daily replays (Yahoo, split cuts, lock rule, intraday charges; Rs 2,000, one slot, `results/round2s-2000.json`):

| Period | All fill | Worst of eight fill models |
|---|---:|---:|
| 2011-2014 | 72,343 | 22,410 |
| 2015-2018 | 50,778 | 11,160 |
| 2019-2022 | 44,345 | 9,515 |
| 2023-2025 | 28,638 | 6,193 |
| Aug - Nov 3 2026 | 3,070 | 1,036 |

The eight models: all fill; a quarter / half of winning tickets not filled (ten-seed means); half
denied on the same day; capacity 0.1% of the 20-day median volume; capacity + half denied; +50 bp
entry and -50 bp exit; +100 bp entry and -50 bp exit. Older periods hold only today's surviving
stocks and look better (win rate 73% in 2011-14, 45% in 2023-25); the recent ones are the honest guide.

Minute replays on Production's own Kite minutes (Aug 10 - Nov 3, Rs 2,000): uncapped +684,
capped 10% of the 09:15 candle +229 (close) / +54 (15:15). Same-dates Smart replays lost.

What was tried: round 1 (rank by gap / liquidity / own history / random, deeper gaps, no crashes,
one/three slots, holding overnight), round 2 (capacity filter, four slots, skipping lower-circuit
opens, own-history filter). Deepest gap first won; liquid-first and overnight holding lost under
stress. Two corrections were made before any selection and are kept: a lower-circuit lock (no
buyers) now carries the sale to the next open, and the capacity model was tightened from 0.5% to
0.1% of daily volume after measuring the 09:15 candle.

## Honest limits

- No historical data shows whether an auction order fills; the auction price is modelled as the
  fill and our order as too small to move it. The capacity models are assumptions.
- Whether Kite's quote shows the indicative auction price at 09:07 is not verified; SV3_PREOPEN
  records it (`preopen.indicative_moved`) and SV3_REF is the after-the-auction reference.
- The minute check covered 89 names (the Oct 5 Penny universe, survivors); 7 were commodity ETFs.
- At the 09:16 settlement the lock rule uses the 15:15 day low; a stock locked again the next day
  is sold at that day's open (the replay used its close).
- Jan-Jul 2026 Kite minutes are now seen. Only the forward record can test anything further.

## Built in Dev (paper only)

- `python-engine/penny_smart_v3.py`: Smart V3 paper book, own store `<DB_PATH>.penny-smart-v3.db`,
  two variants on their own Rs 2,000 books: **SV3_PREOPEN** (decided at 09:07 on the pre-open
  quote, limit 1% above it) and **SV3_REF** (decided at 09:16 on the official open, a reference).
  Jobs `penny_smart_v3_preopen` 09:07, `penny_smart_v3_open` 09:16 (settles the previous session at
  its official close, or a locked one at today's open with delivery charges; records first-minute
  volumes; fills), `penny_smart_v3_bid` 15:15 (best bid, day low, lower circuit: a measured
  MIS-style exit and the lock evidence). Same Penny universe as V1/V2, EQ series only.
  `GET /experiments/penny-smart-v3`. Settings `PENNY_SMART_V3_ENABLED` (default true; rollback
  false) and `PENNY_SMART_V3_BANKROLL` (2000). V1, V2, Classic and the ledger are unchanged.
- `penny_shadow.PEN_AFTERNOON`: Classic breakout shadow from 13:00 (paper, one virtual share).
- Parity: the runtime selection equals the research picks on 198 sessions, 0 mismatches.

## How to judge it forward

After 20+ SV3_PREOPEN closes: its net against Smart V1/V2 on the same sessions
(`/experiments/penny-smart`), `at_1515_bid` (the trade sold at the 15:15 bid), `refusals`
(`open_above_limit`, `auction_capacity`) and `preopen.indicative_moved` (if 0, the 09:07 quote
cannot see the auction and only SV3_REF measures the edge). A real auction order is the only proof
of fills and is the owner's call.

## Reproduce

`scripts/tod.py`, `gap_daily.py`, `gap_minutes.py`, `gap_slices.py`, `rounds.py 1|2|2s [bankroll]`,
`exam.py wire|run` (run refuses a second opening), `parity.py`, `breakout_events.py [kite_jan_jul]`,
`connors_events.py`. Engine Python: `python-engine/winvenv`.
