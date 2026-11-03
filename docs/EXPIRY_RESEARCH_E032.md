# E03.2 — no rule beats E03.1; what the search taught us

November 3, 2026. **Research only, in Dev. Nothing in the trading engine changed, nothing is deployed.**
E03.1 stays the best expiry candidate (disabled paper variant, not deployed).

## The short answer

I tried nine new directions and about 1,000 settings. None beats E03.1 in both years. Two of the
tests used parts of the day that no expiry rule had ever been scored on, so they are close to fair
exams, and both failed. One change helps, and only when fills are bad.

The honest way to earn much more is not a cleverer rule on these two years. It is (1) a fresh test on
expiries nobody has looked at, (2) forward paper tickets, and then (3) more money at the same
percentage risk, if the forward tickets hold up.

## What was tested

| Idea | Fair test? | Result |
|---|---|---|
| E02/E03's entry in the **morning**, 09:30-13:00 | yes, frozen before scoring | Loses in both years: E03 -3,221 (2024), -3,505 (2025). Worse than random entries. |
| The **last slice**, 15:00-15:15 | yes, frozen before scoring | Three tickets in 2024, none in 2025. Not enough to trade. |
| **Roll the profit**: at 2x, spend part of the gain on a cheaper option further out | no (seen years) | Usually loses: the 2x is mostly the end of the move, not the start of a hero. |
| **Grow the ticket with profits** | no | Results jump around with lot rounding; no steady gain. |
| **Same signal, near-the-money option** | no | Loses in every setting (-2,546 to -4,576). |
| **Cheaper strike so two or three lots fit** | no | Lower in every setting. |
| **Genome**: fit on one year, test on the other, 677 settings | half fair | Its picks earn less than E03.1 on the year they did not see. |
| **Buy limit**: never pay more than 7-8% above the price seen at the decision (now 10%) | no | Same profit in normal and worse fills; the severe-fill loss falls from Rs 3,234 to Rs 2,486. |
| **Bigger book**, same rule, same percentage risk | no | Up to Rs 1,00,000 the profit per rupee holds (+Rs 49,591 over two years, worst day -Rs 2,166). |

## What we learned

1. **The edge lives only between 13:00 and 15:00 on expiry day.** Before 13:00 a cheap option does not
   move enough in eight minutes; after 15:00 there is almost nothing in the price band. Advice for a
   buyer: a trend pullback on a cheap expiry option is an afternoon trade, not a morning one.
2. **The money comes from cheap options moving fast in the right direction.** Reverse the direction
   and it loses; use a near-the-money option and it loses. Both parts matter.
3. **Cheaper is not better.** Going further out to buy more lots, or rolling profit into a far option,
   loses. Very cheap options are overpriced, as the E03 study found.
4. **Searching harder does not help.** A broad genome finds settings that look better on one year and
   then earn less on the other. The good news: 85% (fit on 2024) and 99.7% (fit on 2025) of the
   settings it tried are positive on the unseen year, so the E02/E03 idea is not one lucky point.
5. **Bad fills are the real risk.** A 7-8% buy limit costs nothing in the model's normal fills and cuts
   the worst-fill loss by about a quarter. It does not make bad fills profitable.

## Why I did not ship an E03.2 variant

The buy limit differs from E03.1 only when the price jumps between the decision and the fill. A third
paper book that behaves the same in normal fills would not teach us anything forward. It should be
part of whichever variant you promote. Every E03.1 paper ticket already shows whether the limit would
have refused it.

## What happens next (your decisions)

1. **A fresh test.** The database has no 2026 expiry-day option chains, for NIFTY or SENSEX. A new
   download (about 31 requests per expiry, as for 2024/2025) would give an untouched exam for E03 and
   E03.1. It needs your word. NIFTY 2023 stays the protected exam.
2. **Forward paper.** Merge, rebuild, and switch on E03 and E03.1 to collect real paper tickets.
3. **Size.** Only after forward evidence, and at the same percentage risk.

Technical record: [research/simulation/2026-11-03-expiry-e032/README.md](research/simulation/2026-11-03-expiry-e032/README.md).
