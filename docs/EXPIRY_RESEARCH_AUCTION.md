# Expiry day from two new angles: the closing auction, and the seller's side

November 3, 2026. **Research only, in Dev. Nothing in the trading engine changed; nothing is deployed.**
Both angles were frozen in writing before they were scored. Neither produced a strategy.

## Why these two

Two E03.2 searches tried to make a buyer smarter and failed. Two things had never been studied here:

1. **The closing auction.** Since August 3, 2026 expiring options settle at the stock market's closing
   auction. The index freezes at 15:15; options keep trading until 15:40; the settlement prints about
   15:30. Every earlier study used 2024/2025 data, from before this rule. This is the "micro" level.
2. **The seller.** Every buyer result says options are overpriced on expiry day. Someone collects that.

## 1. The closing auction (27 days, August 4 to November 3, 2026)

**What happens:** from 15:20, when auction orders start, option prices move toward where the auction will
close. On October 6 the index stood frozen at 22,717.70; the options moved step by step to 22,773 by
15:29; the settlement printed 22,776.10.

**What the test found:**
- At 15:22 the options' drift points the right way only about 60% of the time, once a data error is fixed
  (below). By 15:27-15:29 it is right 88-100% of the time, too late to earn anything.
- After 15:22 there is no extra move left to catch: the median is slightly against the drift.
- The test trade on the 8 unseen Production days made +Rs 2,657 over 5 trades, but only 2 won and
  without the best day it lost Rs 2,077. Failed.
- **The auction's size is overpriced as well.** Your paper book's B (a strangle bought at 15:13) lost
  Rs 3,007 over five days; BH (the same strangle held through the auction) lost on all four of its days,
  Rs 6,313 in all. (An earlier count showed B positive: legs left to settle had their loss stored in a
  different field. Corrected here.)

**A data error found and fixed:** the ICICI history shows a provisional auction index from 15:20 (it once
jumped 1,780 SENSEX points away from the final), while Kite's index stays frozen. The test had read the
frozen level at 15:20 and so picked up that provisional value on 8 days. Read at 15:15 instead, the result
is the one above. The options were always closer to the final price than that provisional index.

**Plainly:** the market makers who quote these options see the auction's orders and reprice within
minutes. A system checking every 10 seconds cannot get there first, and the other agent's quote study
showed that tiny fast moves are eaten by spread and fees anyway.

## 2. The seller's side (NIFTY 2024 and 2025, 105 expiry afternoons)

The test: sell the at-the-money call and put and buy protection a few strikes away (an "iron butterfly"),
so the worst loss is fixed in advance. 12 versions, fixed before scoring.

| | 2024 | 2025 |
|---|---:|---:|
| Sold at 13:00 (every version) | loses | loses |
| Sold at **14:00**, protection 200 points away, stop at twice the credit | +Rs 20,049 | +Rs 16,723 |
| Same, sold at 13:45 | +Rs 23,728 | **-Rs 6,327** |
| Same, sold at 14:15 | +Rs 25,342 | **-Rs 8,175** |

One version passed, and it also made Rs 7,473 on the 9 recent auction days. But in 2025 it works only
when sold at exactly 14:00; fifteen minutes either way loses thousands. That is luck, not an edge. In
2024 selling paid whenever it was sold between 13:15 and 14:15; in 2025 only at 14:00. It also loses badly under bad fills
(-Rs 14,911 in 2024), and selling needs margin far above Rs 25,000. **Rejected.**

## What we learned

1. **On expiry day the price already contains what the market knows**: the auction's direction within
   minutes, its size richly, the cheap far options more than they pay. The money flows from buyers who
   pay that premium.
2. **Selling is not the easy answer either.** Whether it pays depends on the year's afternoons, and its
   losses are large when they come.
3. **The one buyer's edge found in all this work is still E02/E03's afternoon trend pullback.**
4. **Advice for the partner from the data:** don't buy the strangle or cheap far options into the
   15:15-15:30 auction, and don't hold cheap far options to the close. On average both pay the seller.

About the stories of Rs 20 lakh becoming Rs 10 crore in a day: the auction does produce enormous moves
(SENSEX +346 points on October 15, -357 on September 3), and someone holding the right cheap ticket wins
hugely. On average, those tickets lose, and nobody hears from the people who held the wrong ones.

## What happens next (your decisions)

1. The E03-family exam already frozen for the approved download stays the fair test of the buyer's edge.
2. Forward paper for E03 and E03.1; D keeps measuring the seller's side on paper.
3. No new switch or strategy from this work.

Technical record: [research/simulation/2026-11-03-expiry-auction/README.md](research/simulation/2026-11-03-expiry-auction/README.md).
