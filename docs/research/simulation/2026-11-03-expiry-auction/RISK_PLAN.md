# How much risk E03.1's edge can carry — the decision rule, frozen before computing it

Written November 3, 2026. The owner allowed more risk "as long as we can make so much money that the
loss that is increased is covered". Every new rule has failed; E03.1's afternoon trend pullback is the only
edge found. This sets its size by calculation, not by taste.

## What is computed (`riskdial.py`)

- **Exact replays** of E03.1 on all 105 NIFTY expiry afternoons (continuous 2024-2025), same Rs 25,000
  cash, at size `k` in {1, 1.5, 2, 2.5, 3, 4}: ticket reserve Rs 1,250k, day reserve Rs 2,500k, lot cap 3k
  (the lab's 10-lot ceiling still applies), drawdown brakes scaled with `k` (half at Rs 1,500k, quarter at
  Rs 3,000k, stop at Rs 4,000k, never above the cash). Ordinary, adverse and severe fills. Lot rounding is real.
- **Skeptical stress** of each adverse replay's daily results: the best day removed, then half the average
  day's result subtracted from every expiry (the edge cut in half, because both years were used to build it).
- **Year bootstrap:** 20,000 years of 52 expiries drawn in blocks of four consecutive expiries from the
  skeptical series: chance of a losing year, 5th-percentile year, 95th-percentile peak-to-trough drawdown,
  and the median log growth of the Rs 25,000.

## The decision (fixed now)

The recommended size is the **largest `k`** that meets all three:

1. skeptical chance of a losing year at most 30%;
2. skeptical 95th-percentile drawdown at most Rs 5,000 (20% of the cash);
3. the exact severe-fill replay loses at most Rs 6,250 (25% of the cash) over the two years.

If no `k` above 1 passes, the size stays at 1. Reported regardless: every `k`'s profit per rupee of worst
day and of drawdown, so lot-rounding cliffs show. A size is a deployment setting for the owner to choose
after forward evidence; nothing here changes the runtime or any real-money limit.
