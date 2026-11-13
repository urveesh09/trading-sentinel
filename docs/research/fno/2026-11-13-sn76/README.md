# SN76: why SN Gold v5 wins, loses, or sits out (Nov 13, 2026)

Descriptive, on the four seen years. `sn76.py` → `results.json`; per day in `_local/days.json`.

**742 sessions at ₹15k:** 58 won, 64 lost, 620 no trade.

**Why no trade:** 609 of the 620 had **no N11 or R0.85 entry at all**; 11 had entries Gold couldn't take (busy or unaffordable).

**The main cause:** with yesterday's ADX < 30, N11 has only one member, trend-pullback **puts**. On low-ADX days:

| Day type | Won / lost / none |
|---|---|
| Up days | 0 / 2 / 179 |
| Flat days | 2 / 12 / 208 |
| Down days | 28 / 21 / 130 |

With ADX ≥ 30, Gold trades on about 35–40% of days.

**Where Gold's money is:**

| Days | Count | Win / loss | Net |
|---|---:|---|---:|
| Range ≥ 1.3% | 128 | 18% / 5% | +₹1,24,723 |
| Down > 0.7% | 92 | 24% / 7% | +₹1,13,629 |
| Range < 0.6% | 185 | – | −₹12,248 |
| Flat days | 275 | – | −₹881 |

By strategy: TPB 91 trade days, +₹97,339; EFF 23, +₹63,768; OR20 14, +₹41,015; SHIPPED 13, +₹13,607.

**Clusters (k-means on the day's range, move, efficiency, first hour, gap, close position):**
- The no-trade mass is a 192-day cluster of slow up-grinds (range 0.76%, close near the high, efficiency 0.06): 174 no trade.
- The best cluster is down days (move −0.62%, close near the low): 22 won, 16 lost, +₹51,354.

**What it teaches:** Gold's empty days are mostly slow or up-grinding low-ADX days, where an option buyer pays time value for little movement. That is why SN04/06/08/09's buying on those days lost.
