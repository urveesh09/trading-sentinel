# N11 corrections and disclosures

Every first result stays on record. No frozen file was edited after the freeze at `43fa015`: the panel, carry and random phases refuse to run if one is.

## 1. One check failed: the family's overfitting estimate

**Check 17** said N11's own family should score at or below 0.5. It scored **0.893**. By the plan, that stands as failed.

After the verdict I tested why (`after_verdict.py`). The same books with the weeks shuffled jointly, which destroys time order and keeps the books, score a median of 0.893 (0.815 to 0.946). So time order isn't producing it. These books have close totals, and when totals are close, whatever does best on one half must do worse on the other. The plain meaning stays: **among N11's close variants, history can't say which is best.** Treat them as one book. N11 itself ranks 6th of 68 in its family by total, and it wasn't chosen for ranking first.

## 2. The stand-aside rests on one year

- **Hide 2023 and it wouldn't be chosen:** it adds +26,253 in 2023, nothing in 2024 and 2026, and -4,359 in 2025.
- **Outside 2023 a losing paper record doesn't predict losses:** after a losing 20 the next 20 trades still averaged +8,917, against +16,711 after a winning 20.
- **On 50 other strategies it marks worse trades only in 2023.** Mean per skipped trade against mean per kept trade: 2023 -74 against -12; 2024 +128 against -42; 2025 -121 against -187; 2026 +957 against -23. It helps 37 and hurts 13 of them, but most of them lose, so standing aside saves money on them whatever the state means.
- **Placebos are mixed:** the same count skipped at random beats it 0.27% of the time, but the state rotated through time beats it 7.4% of the time. That passes the 0.10 line, not by a wide margin.
- **The literature agrees it's a risk tool.** Published practitioner descriptions call this kind of rule risk-shaping and not a source of edge, and I found no peer-reviewed test of it. The size-by-volatility half has better support: Gao et al. (2018) find intraday momentum stronger on more volatile days. `SOURCES.md` has the links.

So this is **insurance**, with one claim paid in four years. It can't be proven on these years, and it may not even fire on NIFTY 2022 (`EXAM_2022_N11.md` says "not tested" if it fires on fewer than 10 real entries).

## 3. N11's whole lead is 2023

2024-26 together: N11 2,66,902, N10 retry 2,66,174. The lead over N10 retry is Rs 728 outside 2023. Paired by week, the gain over N10 retry has t 1.57 and a bootstrap interval of -5,540 to +53,656, which includes zero.

N11 isn't better every year: N10 retry earns Rs 5,235 more in 2026, and N08 earns Rs 5,552 more in 2025.

## 4. The stress test flatters the stand-aside

256 orderings of whole years is check 11, and it passes by a wide margin: worst end 2,43,462, median 3,92,273, one ending below the start. But it reuses 2023, the year the rule was shaped on, and at one lot with fixed admissions. "2023 four times" ending at 2,43,462 means the rule knows 2023, not that it would know the next bad year. A bad stretch with volatility above the line wouldn't stand aside at all.

## 5. Everything was chosen with the four years in view

- 67 screen books and 12 panel books. `PLAN.md` says 66: the real count is 67, because the `NOOP` control counts as a book in the first screen. No verdict depends on it.
- **The stand-aside's line of 0.9** was read off the map, moved away from a cliff: at 1.05 it costs about Rs 33,000 in 2024, because the rule would have missed the start of that year. 0.9 is the middle of the range that holds, not its best point, but the cliff is real, and a future recovery could start below the line.
- **Dropping the reserve and WATCH** was decided after seeing that the same book earned more and fell less without them.
- **The honest add** was the fifth screen's result, so it isn't independent of the others.

## 6. What dropping the reserve gives up

N09.1's full-premium reserve protected the floor even if every stop failed. N11 has only the native 15% stop, the same as live today, and open premium can reach 15% of the account. A failed stop could go through it. No trade in these years did.

**The native stop is a fixed Rs 2,12,500.** After an account grows it protects less: at Rs 5 lakh it is more than 50% away. The adaptive stance cuts size at falls of 4% and 8%. The account's largest fall here is 6.89%, but this floor doesn't rise with profit. Any change to it is the owner's decision.

## 7. Ideas that failed, kept on record

| Idea | Rough or screen result | Exact result |
|---|---|---|
| Second lot charged by the stop's expected cost | rough sum +57,701 | about +2,700, no plateau below k = 1.5, worst trade -5,863 at k = 1.0 |
| Second lot on a good paper record | | 2025 only, worst day -7,185 to -9,720 |
| Skip stops under 1.25 ATR | looked clean | -10,112 in 2026 |
| Earned lot on one-lot trades | | -19,210 at +1R, -1,672 only after the trail locks |
| Add only after the trail locks | | -7,479 against the honest add |

The rough-sum gap repeats the N10 lesson: **a sum from saved trades only chooses what to test.** Path effects (the stance cut after one bigger loss, reserve refusals) were larger than the raised lots' own +6,914.

## 8. Limits on two of the rules

- **One lot after a loss, and the stand-aside, react to losses.** The owner has rejected rules that stop or ban after a loss. The first only cuts size and never refuses a trade. The second does hold real entries back, though it ends by itself and isn't triggered by any one loss. It needs the owner's judgement before anything beyond paper.
- **The paper reading needs a paper record.** N08's rules aren't running on paper in Production, and the stream here starts in January 2023, so the first 20 trades of 2023 had no reading. They lost about Rs 10,000.
- **Cost stress doesn't change the paper reading.** The double-cost book reads the paper stream at base cost, an assumption inherited from N10.1. Its worst day is -6,266, past -6,127. That isn't a check, and it is stated here.

## 9. Small faults, no effect on results

- The first audit run failed on import: N09.1 also has a `stress.py`, and it was found first. Fixed the import order.
- The first carry run reached 2024 before 2023 had finished. It stopped safely, as it should, and reran in order.
- `pbo.py` first asked for a rank using a name that duplicate removal had dropped, so the rank came back empty. The estimates didn't change.
