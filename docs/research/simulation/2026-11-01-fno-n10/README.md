# N10: technical summary

Research only. No application, Production, lot-limit or money change. Plain write-up: [`docs/FNO_RESEARCH_N10.md`](../../../FNO_RESEARCH_N10.md). Corrections: [`SOURCE_CORRECTION.md`](SOURCE_CORRECTION.md). The test still to come: [`EXAM_2022.md`](EXAM_2022.md).

**N10 is better than N09.1 on the same seen years, and the largest gain is a fix to the account.** Whether N10 also beats N08's profit depends on one rule that the plan didn't state: with it +2,33,275, without it +1,98,484, against N08's +2,02,284. Round one failed its verdict. All four years are seen, and round two was designed after reading round one.

## Results

Fresh Rs 2.5 lakh each year, today's brakes, extra cost in the money path.

| Book | 2023 | 2024 | 2025 | 2026 | Four years | Worst day | Worst trade | Worst annual fall | Double cost | Without top 5 | One account |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| N08 | -37,581 | 76,294 | 58,647 | 1,04,924 | 2,02,284 | -9,720 | -5,107 | 15.08% | 1,63,688 | | 2,12,419 |
| N09.1 CUSHION | -32,684 | 76,294 | 46,738 | 99,870 | 1,90,218 | -6,127 | -4,559 | 13.13% | 1,52,165 | 88,107 | 3,84,310, or 2.17 lakh: see the cliff |
| N09.1 + WATCH | -32,684 | 76,294 | 46,738 | 99,870 | 1,90,218 | -6,127 | -4,559 | 13.13% | | | 4,17,175 |
| N10, one try (the plan's wording) | -32,898 | 79,334 | 46,738 | 1,05,311 | 1,98,484 | -6,127 | -4,559 | 13.21% | 1,61,990 | 95,194 | 4,18,151 |
| **N10, retry (the frozen code)** | **-32,898** | **88,805** | **51,583** | **1,25,786** | **2,33,275** | **-6,127** | **-4,559** | **13.21%** | **1,68,672** | **1,06,281** | **4,27,440** |

## The cliff in N09.1

A floor that never lowers plus a full-premium reserve means that near the floor no lot can be funded, and with no trades nothing can ever change. Free cash above the floor at the end of 2023 decided the rest of the account:

| Book | Free cash, end of 2023 | Jan 1, 2024, the option that won about Rs 3,900 | Trades in 2024 | One account |
|---|---:|---|---:|---:|
| EARN_WC | 5,284 | taken | 25 | 4,05,525 |
| HYBRID_C | 4,941 | taken | 22 | 4,37,141 |
| N09.1 CUSHION | 4,688 | refused at 12:36 (needs 4,731.54); at 12:37 ask 95 paise lower, needs 4,669.65: taken, by **Rs 18.45** | 17 | 3,84,310 |
| LADDER_WC | 4,668.98 | refused by **67 paise** | 3 | 2,16,481 |
| EARN_WVC | 4,594 | refused | 3 | 2,16,922 |

**The same book as the assumed extra cost moves** (`cliff-map.json`, added after the verdict; one account):

| Extra cost per lot | 195 | 198 | 199 | 200 | 201 | 202 | 205 |
|---|---:|---:|---:|---:|---:|---:|---:|
| N09.1 CUSHION | 4,21,148 | 3,84,661 | **2,16,582** | 3,84,310 | 3,84,141 | **2,16,736** | 4,51,055 |
| N10 retry, no WATCH | 4,72,952 | 4,48,743 | **2,16,873** | **2,16,802** | **2,16,747** | **2,17,105** | 4,70,901 |
| N10 retry, WATCH | 4,72,207 | 4,48,743 | 4,27,689 | 4,27,440 | 4,27,191 | 4,27,127 | 4,70,145 |

At +-10% (180 and 220): N09.1 CUSHION 4,34,509 and 4,17,045, N10 retry with WATCH 4,35,812 and 4,33,823. **So N09.1's Rs 3,84,310 isn't a measurement. It is one draw from a range of Rs 2.17 to 4.51 lakh, and it can stick at a Rs 1 change in an assumption.**

## Round one (frozen 6ab7a85): fails

N08's signals and exits, one lot at entry, a second lot earned at +1R with its own stop at the entry level.

| Book | Four years | Worst day | Worst annual fall | One account | Checks passed of 9 |
|---|---:|---:|---:|---:|---:|
| EARN_N | 1,54,352 | -5,342 | 15.37% | | not a CUSHION book |
| EARN_W | 1,44,953 | -5,342 | 15.67% | | not a CUSHION book |
| EARN_WV | 1,38,945 | -5,342 | 15.06% | | not a CUSHION book |
| EARN_WC | 1,51,406 | -5,342 | 12.89% | 4,05,525 | 4 |
| EARN_WVC | 1,38,915 | -5,342 | 13.16% | 2,16,922 | 1 |
| LADDER_WC | 1,63,097 | -5,342 | 13.22% | 2,16,481 | 1 |
| HYBRID_C | 2,14,484 | -6,405 | 13.02% | 4,37,141 | 6: fails worst day, double cost (1,48,691), top five (86,216) |

- **The earned lot doesn't replace the entry lot.** N08's entry-time second lots made +76,704; earned lots about +30,000 to +41,000. Most of the money is in the first leg, and waiting gives it up.
- **Brakes off:** EARN_W -42,878 / 61,005 / 51,926 / 71,974 = 1,42,027, against N08 1,66,918 and one lot 1,17,877.
- **Random-entry control:** the add hurts in every year: helped 1, 2, 2 and 3 of 10 books, median change -10,483, -4,446, -6,383, -3,628. As the plan said beforehand, this means the add is only as good as the entries it follows.

## Round two (frozen 75d8c70)

**WATCH.** When an entry is refused because no lot can be funded above the floor, the floor may drop by a slice of 5% of the best closed equity, only if the last 20 paper trades (exits strictly before now) made money and at least 20 have closed since the last slice, and never below 75% of the best closed equity. The high-water mark restarts at a slice, and the floor rises again with new highs. For these books alone, this replaces the native 15% halt.

**THIRD.** N09.1's entry, plus one earned lot at +1R only when the first entry holds two lots, with planned risk at most Rs 5,000, never scaled up. In HYBRID_C, lots on two-lot trades made +25,411 and on one-lot trades -6,879.

| PLAN2's check | Frozen code (retry) | One try |
|---|---|---|
| 1 Four-year sum above N08's 2,02,284 | Pass, 2,33,275 | **Fail, 1,98,484** |
| 2 Worst day no larger than 6,127 | Pass | Pass |
| 3 Worst annual fall no larger than N08's 15.08% | Pass, 13.21% | Pass |
| 4 2023 no worse than N08's -37,581 | Pass, -32,898 | Pass |
| 5 2024-26 positive, two at or above N09.1's | Pass | Pass (2025 equal) |
| 6 One account at or above 3,84,310, base and both cost shifts | Pass: 4,27,440; 4,35,812; 4,33,823 | Base 4,18,151; shifts not run |
| 7 Double cost at or above 1,52,165 | Pass, 1,68,672 | Pass, 1,61,990 |
| 8 Plateau | Pass: X 0.75 2,32,656, X 1.25 2,32,541; need 10 4,34,349, need 30 4,33,078, slice 2.5% 4,26,119, slice 10% 4,27,440 | Not run |
| 9 Without top five at or above 88,107 | Pass, 1,06,281 | Pass, 95,194 |
| 10 Stress | Pass | Same WATCH, same stress |

**Verdict.** The frozen code passes all ten. The written plan says "first reaches", which is one try, and by N09's precedent the written plan governs: read that way, **N10 fails check 1 by Rs 3,800.** So the retry can't be called a clean pass. It is now a stated rule and a candidate for unseen data (`EXAM_2022.md`). N09.1 + WATCH passes its own question: its account stays within 4.2% across the cost shifts where N09.1's moves 13.1%.

**Where the gain over N09.1 comes from, retry version:** 15 earned lots, 10 winners, +30,440 (-1,437 / 12,511 / 5,441 / 13,925). Knock-on +12,617: more cash means fewer reserve refusals (Jun 1, 2026 enters two lots instead of one, +5,054; Mar 25, 2026 takes a +3,300 trade in place of a -3,120 one). Top three lots +16,737; without them +13,703. **One try earns 7 lots, +7,043; the 8 retried lots earn +23,397.** A retry passes mostly because the first lots' trail has locked, so their planned risk drops to nothing. So the money is largely in adding once the first lots can't lose.

**WATCH's slices in N10's one account:** Jan 12, 2024, equity 2,19,737, floor 2,12,628 to 2,00,120, last 20 paper +5,758. Jan 10, 2025, equity 2,46,583, floor 2,14,029 to 2,01,439, last 20 paper +25,750. The second came with Rs 32,554 free: it fired on an expensive option, not a real trap. The rule as written allows that. A live version should be narrower (`SOURCE_CORRECTION.md`).

**Paired weekly, retry version:** against N09.1 t 2.84, bootstrap +14,668 to +77,278; against N08 t 1.59, -3,958 to +70,035. Descriptive, since all of it is seen.

## Stress: all 256 whole-year orderings, one lot, causal proxy

| Rule | Worst end | Median end | Ends below start |
|---|---:|---:|---:|
| Permanent 15% stop | 2,11,290 | 3,67,877 | 67 |
| Plain funded floor (N09.1) | 2,15,291 | 3,42,954 | 50 |
| WATCH | 1,90,822 | 3,62,226 | 13 |
| Restart on paper evidence (N09.1's corrected figure) | 1,30,136 | 3,67,877 | |

WATCH against the plain floor: helps 113, hurts 25, same 118; largest gain +1,69,338, largest cost -30,320. Against the permanent stop: helps 80, hurts 98, same 78; +1,75,229, -41,257. Lowest equity 1,90,648; at most 4 slices.

| Years in order | Permanent stop | Plain floor | WATCH |
|---|---:|---:|---:|
| 2023, 2024, 2025, 2026 | 2,12,136 | 3,45,363 | 3,63,534 |
| 2023 twice, 2024, 2025 | 2,12,136 | 2,16,788 | 2,86,883 |
| 2023 three times, 2024 | 2,12,136 | 2,18,842 | 2,16,310 |
| 2023 four times | 2,12,136 | 2,16,393 | 1,91,836 |

**WATCH's real cost:** if bad years keep coming it ends about Rs 25,000 lower than never coming back, and that is what it pays for the rest.

## Overfitting (`pbo-after.json`)

CSCV on weekly results, 16 blocks, 12,870 splits, exact duplicates removed. N10's own panel, 21 books: **0.106**, median out-of-sample percentile 82%. Everything since N08, 89 books: **0.381**, median percentile 63%; N10 retry ranks 1st by total. Pure noise averages 0.51 to 0.55 with a standard deviation of about 0.18, so 0.381 is within one standard deviation. The low panel figure isn't independent evidence: round two's books were built after reading round one. Score2's own printed 0.107 included two duplicate pairs.

## Controls and audit

- **Parity:** every N10 path on with nothing changed equals saved N08 and saved N09.1 CUSHION, trade for trade, on all four years; the add out of reach equals one lot (`parity-*.json`). The first lot lives the same life wherever a trade is in both books (`first_lot_same` in `results.json`).
- **Independent audit (`audit_n10b.py`, `audit-n10b-*.json`):** recomputes money for 421 trade records, checks 886 prices against raw quotes, walks every earned lot's minutes for a missed stop, checks two-lot parents, planned risk within 5,000, the reserve at every entry, and recomputes WATCH's evidence from paper trades closed strictly before each slice.
- **Tests:** `test_n10.py` 28, `test_n10b.py` 21: 49 passed. No full engine suite: no engine file changed.
- **Reference figures** are asserted against saved trades before anything is scored.

## Limits

- All four years are seen, and N10's parts were chosen after reading them. Every number here is a seen-year result.
- Candle model, modelled spread, assumed extra cost, lot 65. An earned lot's fill at the ask on a fast move may be worse in practice. The add is a second order on a moving option.
- Only nearest-weekly options are in the data.
- The reserve design assumes Rs 2.5 lakh. It can't work on the real-money Rs 12,500-15,000: one lot's premium is most of the account, so N10 doesn't apply there.
- N10 isn't in the engine. WATCH touches the live stop's logic, which is the owner's decision.

## Reproduce

`N08_YEAR` chooses the year; run through `driver.py` and `driver2.py`. Commands are in the docstrings of `n10_lab.py`, `n10b_lab.py`, `cliff_map.py`, `no_retry.py` and `audit_n10b.py`. `score.py`, `score2.py` and `after_verdict.py` read saved replays. Files: `PLAN.md`, `PLAN2.md`, `freeze.json`, `freeze-2.json`, `results.json`, `results-2.json`, `results-strict.json`, `cliff-map.json`, `stress-watch.json`, `pbo-after.json`.
