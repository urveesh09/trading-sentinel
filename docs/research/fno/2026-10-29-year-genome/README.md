# O29f: the year genome. Strategy books searched and tested on almost a year of NIFTY data

**Verdict: the search does not work on this data, and the live book does not hold up on the months it was never tested on.**
- The frozen walk-forward rule fails 3 of its 5 checks.
- On Jan 1 – Sep 9 the live UNION_DRIVE lost ₹24,500 (−₹27,156 per lot).
- Nothing is promoted. Every candidate here is a forward-test candidate at most.

- Freeze `1b14225` was committed before any scoring.
- 1,842 replays ran on 2–4 workers between 08:36 and 15:24 IST on Oct 29.
- Research only: Production was only read, and no paper, live or proving-week rule changed.

## Results

### 1. The live book and its parts on the eight unseen months (Jan 1 – Sep 9; frozen fixed books)

*Book sizing is the shipped planner's: about 1.8 lots on average from a fresh ₹2.5 lakh pool. "Per lot" is the same trades at one lot.*

| Book | Trades | Net ₹ | Net per lot ₹ | Without best day ₹ | Max DD ₹ | Worst day ₹ | Green / red weeks | Green / red months |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **UNION_DRIVE (live paper book)** | 173 | **−24,500** | **−27,156** | −42,984 | 60,811 | −6,557 | 11 / 24 | 3 / 6 |
| UNION (all four always) | 262 | −842 | −22,579 | −18,914 | 57,596 | −8,779 | 12 / 25 | 3 / 6 |
| THEORY_IB | 171 | 11,688 | −6,908 | −10,705 | 50,871 | −8,622 | 11 / 25 | 4 / 5 |
| THEORY_NR (breakouts after a narrow previous day, plus TPB) | 159 | 42,410 | 17,837 | −4,878 | 60,191 | −8,622 | 11 / 24 | 4 / 5 |
| SHIPPED | 91 | −4,654 | −2,061 | −24,701 | 25,625 | −4,135 | 12 / 21 | 3 / 6 |
| OR20 | 112 | −25,560 | −18,623 | −45,608 | 29,270 | −6,019 | 12 / 23 | 3 / 6 |
| EFF | 221 | −2,304 | −39,397 | −30,790 | 106,696 | −9,268 | 11 / 26 | 2 / 7 |
| **TPB (trend-day pullback)** | 72 | **14,677** | **19,768** | −3,806 | 31,857 | −6,557 | 12 / 15 | 3 / 6 |
| 20 random-entry books | — | median −13,053 | — | — | — | — | — | 5 of 20 positive; best +57,541, worst −38,784 |

- **Per lot, month by month (the whole year, Jan 1 – Oct 28):**

  | ₹ per lot | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct |
  | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
  | UNION_DRIVE | 5,705 | 1,286 | 14,308 | 849 | **−17,943** | −5,851 | **−17,196** | −3,889 | 3,870 | 26,150 |
  | TPB | 3,933 | 6,604 | 29,782 | 882 | −10,402 | −278 | −1,660 | −7,346 | 8,270 | 12,271 |
  | THEORY_NR | 11,456 | 48,303 | 1,977 | −6,100 | −14,446 | −6,429 | −11,284 | 1,288 | −5,496 | 16,528 |

- **Regime dependence:** the breakout family pays in trending months (Feb–Mar and Sep–Oct, when NIFTY fell from about 26,250 to 24,000 and from 24,750 to 22,500) and loses in the range-bound Apr–Aug. Every earlier F&O study saw only Sep–Oct.
- **The one-lot real-money rules** (the O29d method over all 44 weeks of the year: 1 lot, one position at a time, at most 3 a day, only lots the money can pay for, the ₹7,000 floor):

  | Book | From ₹15,000: up / down weeks | Worst week end ₹ | From ₹12,500: up / down weeks | Worst week end ₹ | Weeks under the floor |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | UNION_DRIVE | 17 / 21 | 8,379 | 15 / 21 | 6,950 | 1 (from ₹12,500) |
  | TPB | 15 / 13 | 10,265 | 12 / 15 | 9,146 | 0 |
  | THEORY_NR | 15 / 23 | 10,328 | 14 / 20 | 8,706 | 0 |

  On Sep–Oct alone (O29d), 26 of 27 weeks ended up.

### 2. The search's walk-forward (frozen rule: fails)

| Fold | REAL pick (training only) | Training net ₹ | Test | **Test net ₹** | Live UNION_DRIVE, same test ₹ | NULL pick, test ₹ |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| F1 | EFF [gap LOW] + VWAP band [narrow IB] + TPB | 201,285 | Apr–May | **−33,313** | −21,052 | −13,473 |
| F2 | two prior-day breaks + momentum burst [chop] + TPB | 77,167 | Jun–Jul | **−5,681** | −23,047 | −27,767 |
| F3 | VWAP band [weak drive] + trend pullback [narrow IB] | 96,286 | Aug–Sep | **−19,909** | +148 | +7,409 |
| F4 | VWAP band + TPB [wide IB] + VWAP band [narrow IB] | 189,465 | Oct | **+42,033** | +26,150 | +6,285 |
| **Out-of-sample (Apr 1 – Oct 28)** | | | 89 trades | **−16,870** (worst day −9,275) | −17,801 | −27,546 |

| Frozen check | Result |
| --- | --- |
| Out-of-sample net above 0 | ✗ −16,870 |
| Beats UNION_DRIVE | ✓ −16,870 against −17,801 |
| Beats NULL | ✓ against −27,546 |
| At least 3 of 4 folds above 0 | ✗ 1 of 4 |
| Out-of-sample worst day at or above −5,000 | ✗ −9,275 |

- **Training numbers mean nothing on this data.**
  - Every REAL pick made ₹77k–201k on its training months, then lost on three of its four test blocks.
  - The NULL search found random-entry books worth up to +₹147,024 on training (F4).
- **The FINAL pick** is trained on all of Jan 1 – Oct 28. It is a forward-test candidate only:
  - Members: TPB, plus two momentum bursts, all gated on `trend5:LOW` (after a choppy week).
  - In-sample: 96 trades, +₹163,038, max DD ₹23,188, worst day −₹9,004, 8 green and 2 red months.
  - The walk-forward above is the evidence that this kind of in-sample result does not carry over.
- **Members the search used most** (count over every book it evaluated): VWAP band 518, TPB 516, momentum burst 504, trend pullback 343, prior-day break 275, EFF 158, SHIPPED 113, OR20 87.

### 3. Data-model checks

- **Archive parity is exact** in the run: SHIPPED 13 / ₹10,801.09, OR20 20 / ₹30,566.80, EFF 38 / ₹31,063.32, TPB 14 / ₹17,347.49, UNION_DRIVE 33 / ₹44,169.53, LAB_TPB 14 / ₹17,347.49.
- **Candles against recorded quotes** (the same 11 books on Sep 10 – Oct 26):
  - The trade counts are the same within ±4, and 60–90% of entries fall on the same bar.
  - The rupee totals differ mainly because of sizing. The archive replay starts with the live paper book's real loss history, so it held about 1.1 lots; the candle replay starts fresh at about 1.8.
  - Per lot, UNION_DRIVE made ₹40,339 on quotes and ₹35,081 on candles.
  - Matched trades differ by a median of ₹71 per lot (mean ₹182), so **candles are slightly optimistic, by about ₹100–200 per trade per lot**. Read every year figure as a little better than reality.
- **The regime rebuild** (a description only, not used) agreed with the live label on 26 of 69 logged days (38%), and called 123 of 203 sessions a crisis. That is why the live logged label is used, and UNKNOWN where none was logged.

### Learning

1. **The live book is a trend-month strategy.** It made its money in Feb–Mar and Sep–Oct and lost from April to August. All of the earlier evidence (O27–O29e) came from two trending months.
2. **A search on the past does not pick the future here**, now shown on a year rather than six weeks. The walk-forward lost in 3 of 4 blocks, and random entries searched the same way reach six-figure training profits.
3. **TPB is the most robust single piece.** It was frozen since O27f and is positive on the unseen months: +₹19,768 per lot, 12 green and 15 red weeks, and the fewest down weeks under the one-lot rules. Only 1 of the 20 random-entry books beat its book net (+₹14,677), and the same one beat THEORY_NR. But TPB is the best of 11 fixed books picked after seeing them, and it made most of its money in March, Sep and Oct. That is evidence, not proof.
4. **Range-bound months punish every breakout variant.** Gating did not rescue them out-of-sample: the drive gate, the narrow-IB gate and the narrow-range gate all lost in Apr–Aug.
5. **One lot does not remove the regime risk.** At one lot, the live book lost about ₹17–18k in each of two months, more than the whole real-money test.

### What this means for the proving week and the real-money test (owner's call)

- Nothing changes on paper or live because of this study.
- The Nov 2–6 real-money test would start on a book that, on this year's evidence, has had more down weeks (21) than up weeks (17) at one lot. Its good weeks cluster in trending months.
- The study supports two next steps. Both are proposals, and both are the owner's call:
  - keep the real money off until a forward panel shows a book that wins outside trending months;
  - if it goes ahead, expect the outcome to depend on whether the week trends.

### Disclosures

- **Interruptions:** Claude Code stopped the run twice for low memory, at 09:15 and 10:38 IST. Production stayed healthy throughout. The run resumed from its saved replays, and the results are the same whatever the number of workers.
  - From 10:50 it ran in foreground 9-minute slices: 3 workers in market hours, at least 4 GB free.
  - The memory guard never had to pause a replay.
- **Interim recompute:** at about 13:15 IST an interim, read-only recompute of the REAL picks from saved replays was shown to the owner. It changed nothing.
- **Fixed-book figures:** the fixed books' unseen results were shown to the owner during the run. They were frozen before it, and the GA never reads them.

## Why this study

Every earlier F&O study (O27 to O29e) replayed the same 29–31 sessions of Sep 10 – Oct 28, because the system's own quote archive starts on Sep 10. The owner's ICICI Direct account comes with the free Breeze API, which serves 1-minute candles of **expired** NIFTY and SENSEX options and futures. That gives NIFTY sessions from Jan 1 2026, and **Jan 1 – Sep 9 has never been used by any F&O study**.

The owner asked for two things:
- a new genome search on this year, mixing the best components of the winners, sometimes with a little randomness and sometimes without;
- the best winner, without hindering Production's RAM.

## Data: a declared candle model (`yeardata.py`)

A candle is not a quote, so the model is fixed before anything is scored:

| Part | Rule |
| --- | --- |
| Observation | one per minute, stamped at the minute's last second, priced at the minute's close. The archive also samples about once a minute (median gap 59 s). |
| Bid / ask | close ∓ half the archive's **75th-percentile** spread for that premium. The archive recorded ₹0.10 under ₹50, ₹0.30 at ₹100–150 and ₹0.80 under ₹450, on NIFTY near strikes, 09:30–15:15, Sep 10 – Oct 28. |
| No trade in a minute | the contract keeps its last price and last trade time, so the planner's 120-second quote-age gate ages it as live would. |
| Futures | the front monthly future carries the price. Its 5-minute bars come from its own 1-minute bars, including the 21 days before it became the front contract, as live reads them. |
| Regime (only a crisis blocks F&O) | the label the live engine logged for the bar (Jul 14 – Oct 28), else UNKNOWN, which leaves the gate open. A rebuild with the live RegimeEngine from daily bars called 30 of 32 Sep–Oct sessions a crisis where live logged 1, so it is kept in the manifest as a description only. |
| Lot | 65 (today's contract), so every session is sized as the book would size it now. |
| Options downloaded | the nearest weekly expiry each non-expiry day: calls from 4 strikes below the day's low to 4 above its high, puts up to 7 above (the live chain centres on the futures price, which carries basis). Expiry days have no options; the book makes no entries then. |

## The search (`lab.py`)

- **A genome is a book.** It has 1–4 members in priority order, the shape of the live UNION_DRIVE book.
  - Each member is either a named component exactly as studied (SHIPPED, OR20, EFF, TPB) or an O27f lab family (trend pullback, prior-day level, VWAP band, momentum burst) with its genes.
  - Each member has its own day gate: ALWAYS, or one O28 09:45 condition such as `open_drive:HIGH`.
  - Each member has its own exits: OWN/LIVE/LATE/LOOSE/RUN, and the VWAP-lost exit.
- **The book itself is unchanged.** Every book runs through the shipped single-leg book: planner, sizing, brakes, exit ladder, costs, buying at the ask and selling at the bid. Each book is replayed once over Jan 1 – Oct 28, and windows are slices of that one path.
- **Recombination:**
  - Children take members slot by slot from both parents, and two same-family lab members mix their genes.
  - **40% of children get no mutation at all.** The rest get gene mutations and structural changes: add, drop or reorder a member.
  - Elites carry over unchanged, and two random immigrants join each generation.
- **Walk-forward of the whole search (anchored):**

  | Fold | Train | Test |
  | --- | --- | --- |
  | F1 | Jan 1 – Mar 31 | Apr 1 – May 31 |
  | F2 | Jan 1 – May 31 | Jun 1 – Jul 31 |
  | F3 | Jan 1 – Jul 31 | Aug 1 – Sep 30 |
  | F4 | Jan 1 – Sep 30 | Oct 1 – Oct 28 |
  | FINAL | Jan 1 – Oct 28 | (forward test only) |

- **The NULL track** runs random-entry books with the same budget, gates and exits.
- **The fixed books are frozen here:** the live UNION_DRIVE, its parts, UNION and the O28 theories. They are scored on the unseen Jan 1 – Sep 9, with 20 random-entry books as the luck yardstick.
- **The frozen rule (`lab.RULE`).** The search works only if all of these hold for REAL out-of-sample (Apr 1 – Oct 28):
  - net above 0;
  - beats UNION_DRIVE on the same sessions;
  - beats NULL;
  - at least 3 of 4 folds above 0;
  - worst day at or above −₹5,000.

  The FINAL pick is a forward-test candidate only.
- **Production's RAM:** at most 4 replays run during market hours (09:00–15:45 IST), and no new replay starts while free RAM is under 2 GB (1.5 GB after hours).

## Pre-freeze checks (disclosed)

- **Archive parity is exact** for six books: each named component alone, the live UNION_DRIVE (33 trades, ₹44,169.53) and the O27f trend pullback as a lab member (14 trades, ₹17,347.49). The replay code is the same code.
- **Timing smoke on a partial Sep export:** about 0.1 s per session once the named signals are warmed. The September comparison showed the same setups on both data sets, with per-trade rupees differing by a few hundred, because a candle's close can sit up to a minute from the recorded quote. The full fidelity table (archive against candles on the same 29 sessions) is part of the run.
- `test_lab.py`: 8 passed.

## Files

- `yeardata.py` (export and the replay dataset), `lab.py` (the search), `analyze.py` (`results.json`) and `test_lab.py`.
- `freeze.json` is committed before the run.
- The data and raw replays live in the ignored `_local/`: `dataset-nifty/` is the sealed export, and `evals/` holds one JSON per replay.
- To reproduce: `python yeardata.py export`, then `lab.py run --jobs 8`, then `analyze.py`. The run refuses if any bound source, setting or dataset file changed.
