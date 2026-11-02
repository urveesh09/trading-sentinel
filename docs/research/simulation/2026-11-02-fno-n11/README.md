# N11: technical summary

Research only. No application, Production, lot-limit or money change. Plain write-up: [`docs/FNO_RESEARCH_N11.md`](../../../FNO_RESEARCH_N11.md). Corrections: [`SOURCE_CORRECTION.md`](SOURCE_CORRECTION.md). The test still to come: [`EXAM_2022_N11.md`](EXAM_2022_N11.md). Outside sources: [`SOURCES.md`](SOURCES.md).

**N11 meets the owner's bar on the seen years: all 12 checks pass. One of the honest checks failed, and its lead over N10 retry is entirely 2023.** All four years are seen and were used to shape it. Frozen at `43fa015`, after five development screens.

## Results

Fresh Rs 2.5 lakh each year, today's brakes, extra cost in the money path.

| Book | 2023 | 2024 | 2025 | 2026 | Four years | Worst day | Worst fall in a year | Double cost | Without top 5 | One account |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| N08 | -37,581 | 76,294 | 58,647 | 1,04,924 | 2,02,284 | -9,720 | 15.08% | 1,63,688 | 1,00,172 | 2,12,419 |
| N09 size by volatility | -37,974 | 70,317 | 50,442 | 1,08,643 | 1,91,428 | -6,127 | 15.24% | 1,43,250 | | 2,12,026; 4,10,542 with its restart |
| N09.1 CUSHION | -32,684 | 76,294 | 46,738 | 99,870 | 1,90,218 | -6,127 | 13.13% | 1,52,165 | 88,107 | 3,84,310, or 2.17 lakh: the cliff |
| N10 retry | -32,898 | 88,805 | 51,583 | 1,25,786 | 2,33,275 | -6,127 | 13.21% | 1,68,672 | 1,06,281 | 4,27,440 |
| N10.1 WATCH_FLAT | -32,898 | 88,805 | 51,583 | 1,25,786 | 2,33,275 | -6,127 | 13.21% | 1,65,934 | 1,06,281 | 4,27,452 |
| N10.1 PREMIUM_LOCK | -32,684 | 80,030 | 54,122 | 1,00,120 | 2,01,588 | -6,127 | 13.13% | 1,28,938 | 62,059 | 4,01,475 |
| **N11** | **-11,537** | **93,256** | **53,095** | **1,20,551** | **2,55,365** | **-5,641** | **6.89%** | **1,99,622** | **1,25,490** | **5,18,305** |

181 trades, 83 winners, worst trade -4,559. Falls by year: 6.89%, 2.13%, 5.48%, 2.91%.

## What N11 is

N08's entries and exits, plus:

1. **Size by volatility:** N09.1's VOL_CLOCK, unchanged.
2. **One lot after a loss:** after a realised loss today, the next trade today takes one lot. Never a refusal.
3. **Stand aside:** real entries wait while yesterday's ATR% is below 0.9 of its 250-session median AND the last 20 closed one-lot paper trades of N08's rules, exits strictly before now, sum to zero or less. It held back 54 paper trades in four years: 52 in 2023, 2 in 2025.
4. **The honest earned lot:** on a two-lot trade at or beyond +1R and before 14:45, one lot at the first observation where the held lots' expected loss at their current stop (delta-valued, no lower than their premium backstop, with fees and stress) plus the new lot's whole 25% backstop, fees and stress, fits inside Rs 5,000 x min(1, stance). The held lots' stops are never touched.

Gone: CUSHION's full-premium reserve and WATCH. The native 15% stop at Rs 2,12,500 stays, so the live stop needs no change.

## What each part adds

| Removed | 2023 | 2024 | 2025 | 2026 | Four years | Worst day without it | Worst fall without it |
|---|---:|---:|---:|---:|---:|---:|---:|
| Stand-aside | +26,253 | 0 | -4,359 | 0 | +21,894 | -5,641 | 15.17% |
| One lot after a loss | 0 | 0 | +1,236 | 0 | +1,236 | -6,127 | 6.89% |
| Earned lot | +415 | +16,962 | +4,495 | +15,627 | +37,499 | -5,641 | 7.06% |
| Size by volatility | +5,842 | 0 | -10,199 | 0 | -4,357 | -9,720 | 9.23% |

**Hide each year in turn (`after-verdict.json`):** the earned lot is chosen every time and earns on every hidden year. **The stand-aside isn't chosen when 2023 is hidden.** Size by volatility costs money and is there for the worst day.

## The checks

| Check | Result |
|---|---|
| 1 Sum above 2,33,275 | Pass, 2,55,365 |
| 2 Worst day no larger than 6,127 | Pass, -5,641 |
| 3 Fall no larger than 13.13% | Pass, 6.89% |
| 4 Worst trade no larger than 4,559 | Pass, -4,559 |
| 5 2023 no worse than -32,684 | Pass, -11,537 |
| 6 Double cost above 1,68,672 | Pass, 1,99,622 |
| 7 Without top five above 1,06,281 | Pass, 1,25,490 |
| 8 2024-26 positive, two at or above N10 retry | Pass: 2024 and 2025 above; 2026 is 5,235 below |
| 9 Plateau | Pass: ratio 0.85 2,55,565, 0.95 2,54,027; window 15 2,53,218, 25 2,53,470; add at 0.75R 2,52,950, 1.25R 2,59,428. Worst day -5,641 in all |
| 10 One account, every cost | Pass: table below |
| 11 Stress | Pass, with a caveat: below |
| 12 Held lots untouched | Pass: same exit on all 178 trades compared (`audit-*.json`) |
| 13 Rotated placebo at most 0.10 | Pass, 0.074 |
| **17 Family overfitting at most 0.5** | **Fail, 0.893** |

14, 15, 16 and 18 are reported below, as the plan says.

## One account, no resets

| Extra cost per lot | 195 | 198 | 199 | 200 | 201 | 202 | 205 | 180 | 220 | 400 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| N10 retry | 4,72,207 | 4,48,743 | 4,27,689 | 4,27,440 | 4,27,191 | 4,27,127 | 4,70,145 | 4,35,812 | 4,33,823 | 4,10,161 |
| **N11** | 5,19,193 | 5,18,827 | 5,18,566 | **5,18,305** | 5,18,044 | 5,17,783 | 5,17,000 | 5,15,071 | 5,12,864 | 4,45,026 |

From 195 to 205 N11 moves 0.42%: there is no cliff. Base by year: -11,537, +99,207, +51,023, +1,29,611. Lowest equity 2,32,908, largest fall 6.89%. It never comes near the stop, so nothing here tests the stop.

## Stress: 256 orderings of whole years, one lot, causal proxy

| Rule | Worst end | Median end | Below start | Stopped for good |
|---|---:|---:|---:|---:|
| Permanent 15% stop | 2,11,290 | 3,67,877 | 67 | 67 |
| N09.1's floor | 2,15,291 | 3,42,954 | 50 | |
| N10's WATCH | 1,90,822 | 3,62,226 | 13 | |
| **N11's stand-aside and the 15% stop** | **2,43,462** | **3,92,273** | **1** | **0** |

Against the plain stop: helps 175, hurts 65, same 16; largest gain +2,21,227, largest cost -17,438. "2023 four times" ends at 2,43,462, with 244 paper trades held back and 96 taken. **The caveat:** this reuses the year the rule was shaped on.

## Is it overfit?

- **Lead by period.** 2024-26: N11 2,66,902, N10 retry 2,66,174, N08 2,39,865. Against N10 retry, the lead is 2023.
- **Paired by week.** Against N10 retry +22,090, t 1.57, bootstrap -5,540 to +53,656, 23 weeks better and 12 worse. Against N08 +53,081, t 2.40, +3,781 to +91,433, 34 and 15. Descriptive, since all of it is seen.
- **Head to head on 12,870 splits (`after-verdict.json`).** N11 wins the half it wasn't chosen on 89.7% of the time against N10 retry, 97.4% against N08. Splits overlap, and 2023's weeks fall in half of them.
- **Placebos on the stand-aside (54 skipped, +24,396 at one lot).** Same count at random: median +1,774, beaten 0.27% of the time. State rotated through time: median -28,847, max +34,965, beaten 7.4% of the time.
- **Persistence (check 14).** All years: correlation of one 20-trade sum with the next, 0.512; next 20 average -592 after a losing 20 and +17,543 after a winning 20. Without 2023: 0.107; +8,917 and +16,711.
- **Trading smaller (check 14).** N10 retry scaled to N11's fall would earn 1,21,704 by arithmetic. N11 beats it, on the strength of 2023.
- **50 other strategies (check 16).** Helps 37, hurts 13; without 2023, 31 and 19. It marks worse trades only in 2023 (`SOURCE_CORRECTION.md`).
- **Random entries (check 18).** The honest add hurts in every year: helped 1, 3, 1 and 3 of 10, median -11,522, -3,957, -8,467, -5,246. So it is only as good as the entries it follows. The stand-aside helps all 10 in 2023 (+44,371 median), which says little, since random books lose anyway.
- **The overfitting estimate.** N11's family, 71 books: **0.893, check 17 failed**; median out-of-sample percentile 26%. With the weeks shuffled jointly it stays at a median of 0.893, so this is the plateau and not time order, but the check failed as written. Everything since N08, 159 books: 0.313, median percentile 59%, N11 6th by total. Pure noise averages 0.51 to 0.55 with a standard deviation of about 0.18, and the books aren't independent.

## Controls and audit

- **Parity:** every N11 path on with nothing changed equals saved N08, saved N09.1 VOL_CLOCK and saved N10 retry, trade for trade, on all four years (`parity-*.json`).
- **Independent audit (`audit_n11.py`, `audit-*.json`):** recomputes money for 364 trade records including every earned lot, checks 794 prices against raw quotes, walks all 33 earned lots' minutes for a missed stop, recomputes the volatility reading and the paper evidence by its own code and finds no real entry in the state, confirms one lot on below-usual days, after a loss and on the morning rule, and confirms the held lots live the same life with and without the add.
- **Tests:** `test_n11.py` 28 passed. No engine file changed, so the engine suite wasn't run. Atlas: 291 modules, no diff.

## Limits

- All four years are seen, and N11's parts were chosen after reading them. Every number here is a seen-year result.
- Candle model, modelled spread, assumed extra cost, lot 65, nearest weekly only, no expiry days. An earned lot's fill at the ask on a fast move may be worse in practice.
- The earned lot's rule still needs paper evidence of its own, and with it N11 holds three lots, past the owner's two for now.
- N11 isn't in the engine. The paper reading needs N08's rules running on paper, which Production doesn't do.
- Rs 2.5 lakh only. The one-lot Rs 12,500-15,000 real-money test isn't affected.

## Reproduce

`N08_YEAR` chooses the year; run through `driver.py`, 2023 first for `carry`. Phases: `screen` to `screen5`, `controls`, `panel`, `carry`, `random`. From saved replays: `screen_view.py <phase>`, `stress.py`, `overfit.py`, `pbo.py`, `after_verdict.py`, `score.py`. Audit: `N08_YEAR=<year> python audit_n11.py`. Files: `PLAN.md`, `freeze.json`, `results.json`, `stress.json`, `overfit.json`, `pbo.json`, `after-verdict.json`.
