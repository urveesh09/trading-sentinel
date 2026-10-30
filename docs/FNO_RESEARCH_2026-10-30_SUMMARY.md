# F&O research, Oct 29–30, 2026: what was tested, what failed, and why

This is the complete account of the NIFTY F&O strategy research of October 29–30, 2026, written for the owner first and for any agent second.
- **How to repeat or extend the tests:** [FNO_YEAR_DATA_TESTING_METHOD.md](FNO_YEAR_DATA_TESTING_METHOD.md).
- **The data download:** `C:\Users\Urveesh\sentinel-operations\breeze-history-20261029\DOWNLOAD_GUIDE.md` (outside the repo).
- **What came after this summary (O30s, Oct 30 night):** rupees on ₹2.5 lakh, what more size costs, the Budget-day dependence and the stretched-entry rule: [FNO_EARNING_POWER_2026-10-30.md](FNO_EARNING_POWER_2026-10-30.md). The other agent's O30n, O30p and O30q studies are in `docs/research/fno/2026-10-30-micro-adaptation/`, `2026-10-30-option-depth/` and `2026-10-30-loss-day-review/`.

Everything here is research on replays. **Nothing in the trading system was changed on Oct 30.** The live paper book is still `FNO_BOOK=UNION_ADX`, deployed Oct 29 (Production `a461bde`). The real-money test from Nov 2 mirrors that book at one lot and stays off until the owner switches it on.

---

## 1. The short version

1. **The live book is the four strategies, traded only on "trend days"** (yesterday's NIFTY trend strength, ADX, at 25 or more). It was chosen on Jan–Oct 2026 and made **+₹80,912 per lot** there. On **2025**, a year it had never seen, it made **+₹271**: break-even.
2. **The sideways-day idea also failed on 2025.** The failed-breakout fade made +₹30,134 on 2026's sideways days and **−₹14,518** on 2025's.
3. **Why:**
   - **The two years were different markets.** 2026 has mostly been falling (fast moves that pay option buyers); 2025 mostly rose slowly.
   - **One strategy (EFF) flipped** from +₹29,629 to −₹21,796.
   - **The trend gate kept the steadiest strategy (TPB) out of its best 2025 days.**
4. **"Pick the right strategy for each kind of day" was tested properly** (134 strategies, 6 ways of describing a day). It **failed on the year it did not see**: a strategy's result in one year says almost nothing about the next (rank correlation 0.12).
5. **One family held up in both years: the trend pullback (TPB).** The best book found keeps the live book and also lets TPB trade on the days it would otherwise sit out: **+₹1,14,748 per lot over both years** (+₹34,517 in 2025, +₹80,232 in 2026).
6. **That book and 22 others are frozen for a one-time exam on NIFTY 2024,** which the other agent downloads on Oct 31. Whether to add the TPB case to the live book is the owner's call after that exam.

---

## 2. Words used here

| Word | Meaning |
| --- | --- |
| **Per lot** | Profit or loss for one lot of NIFTY options (65 units, today's lot size), after charges. The real-money test trades one lot. |
| **Option buyer** | The book only buys calls (betting up) or puts (betting down). It makes money only when NIFTY moves far enough, fast enough. |
| **The four strategies** | **SHIPPED**: the original 30-minute opening-range breakout. **OR20**: a 20-minute opening-range breakout. **EFF**: the "efficiency break" (a clean, one-way move breaking out). **TPB**: the trend-day VWAP pullback (on a trending morning, buy the dip back to the day's average price). |
| **The book** | The four strategies in a fixed order. The first one that signals takes the trade. One position at a time, with the shipped sizing, stops, exits and costs. |
| **ADX** | Wilder's trend-strength number from daily bars. 25 or more is commonly called a trending market, below 25 sideways. |
| **DMI direction** | Whether yesterday's daily trend points up (+DI above −DI) or down. |
| **Trend gate / "closed days"** | The live rule: trade only when yesterday's ADX ≥ 25. The days below 25 are the "closed days". |
| **In-sample / clean** | In-sample means the rule was chosen by looking at that data, so a good result there proves little. Clean means the rule never saw that data. |
| **Freeze** | Writing down the exact strategies and the pass/fail rule, and committing them to Git, *before* any result is computed. It makes cheating impossible, deliberate or not. |
| **Random-entry books** | 20 books that enter at random. A rule that "works" no better than these is luck. |
| **Max drawdown (DD)** | The biggest fall from a high point of the running total. |
| **One-lot weeks** | The real-money rules played week by week: start each week at ₹15,000, stop below ₹7,000, at most 3 trades a day. |

---

## 3. The data

- **Source:** ICICI Direct's free Breeze API, 1-minute history of expired NIFTY options and futures.
- **What exists:**

  | Year | Sessions | Downloaded | Status |
  | --- | --- | --- | --- |
  | NIFTY Jan 1 – Oct 28, 2026 | 203 | Oct 29 | in-sample (rules were found on it) |
  | NIFTY 2025 | 248 | Oct 30 | now seen too |
  | NIFTY 2024 | — | planned Oct 31 | **unseen: the exam** |

  - The Oct 21, 2025 Diwali Muhurat hour is dropped from the 2025 sessions.
- **Honest caveat:** a 1-minute bar is not a live quote. On the overlap with the recorded quotes, candles came out about **₹100–200 per trade per lot better** than reality (O29f). Books that trade more are flattered more.
- **Download state (Oct 30):** NIFTY 2025 is complete (3,585 option requests, 0 wrong expiries). SENSEX 2026 options are 917 of 4,057, and the remainder runs after NIFTY 2024.

---

## 4. The studies, in order

| Study | Question | Answer | Folder (`docs/research/fno/…`) | Commits |
| --- | --- | --- | --- | --- |
| **O29f** year genome (Oct 29) | Search strategy combinations on the year of data | The search fails when checked forward. The book live then (UNION_DRIVE) lost on the unseen Jan–Sep 2026. TPB alone was positive. | `2026-10-29-year-genome/` | `1b14225`, `0d1f6fa` |
| **O29g** why-study (Oct 29) | Why did the strategies lose, and when did they win? | In 2026 all four won on trend days. Gate "all four, ADX ≥ 25": +₹80,912 (in-sample). | `2026-10-29-why-study/` | `9d450aa` |
| **O29h** (Oct 29) | Put the trend gate live | Deployed as `UNION_ADX` | engine (`fno_book.py`) | `2279a2e`, `cfe83dc` → Prod `a461bde` |
| **O29i** sideways study (Oct 29) | What works on the days the gate sits out? | The failed-breakout fade helped (in-sample). Live + fade: +₹1,11,046. | `2026-10-29-sideways-study/` | `d5b08c9`, `d90919d` |
| **O30** 2025 clean test (Oct 30) | Do the 2026 rules hold on 2025? | **No.** UNION_ADX +₹271, fade −₹14,518. TPB alone positive. | `2026-10-30-nifty-2025-test/` | `7d9eeb3`, `5f49a2d` |
| **O30c** case study (Oct 30) | Why did it fail, and which added "cases" help? | EFF flipped; the gate locked TPB out. Of 15 fixed cases only "TPB on closed days" adds real value. The investigation's own ideas made things worse. | `2026-10-30-case-study/` | `a98b1f5`, `b0defde`, `0111fbf` |
| **O30m** kind-of-day router (Oct 30) | Can we pick the right strategy for each kind of day? | **No.** It fails on the unseen year, all 6 ways. Winners don't repeat. Only the trend pullback is robust. | `2026-10-30-day-router/` | `2bcec04`, `33947f2`, `2a57ede`, `71d1a25` |
| **O30f** 2024 exam (frozen Oct 30) | Will the best books hold on a third year? | Pending the 2024 download | `2026-10-30-day-router/` (`lab_f.py`, `freeze-2024.json`) | `2a57ede` |

Each folder has a `README.md` with the full tables.

---

## 5. Every strategy and rule tested

**Strategies (134 in the O30m library, each replayed on both years):**
- **The four live strategies** with five exit styles each:
  - OWN: the strategy's own exits;
  - LIVE: the shipped exits;
  - LATE: a later profit lock;
  - LOOSE: wider stops;
  - RUN: let winners run;
  - plus a VWAP-lost exit.
- **Lab families (O27f), 8 seeded versions each:**
  - TREND_PULLBACK (buy pullbacks in an intraday trend);
  - PDL_BREAK (break of yesterday's high or low);
  - VWAP_BAND (moves beyond VWAP bands);
  - MOMO_BURST (momentum bursts);
  - plus the O27f TPB genome.
- **Two published ideas:**
  - NOISE_BAND (Zarattini, Aziz & Barbon 2024: trade when price leaves the day's normal noise area);
  - LATE_MOMO (Gao, Han, Li & Zhou 2018: the first half-hour predicts the last half-hour).
- **Range-day ("sideways") families (O29i), 48 versions:**
  - FADE (an opening-range break that fails, traded the other way);
  - VWAP_REVERT (snap back to VWAP);
  - PDL_FADE (rejection at yesterday's high or low);
  - RSI2 (2-period RSI extremes).
- **The four together (UNION)**, and 20 random-entry books.

**Rules ("cases") added on top of the four strategies:**
- **Day gates (from yesterday's daily bars):** ADX ≥ 25 (live), ADX ≥ 20, high 20-day volatility, a large 20-day move, the trend regime (two of ADX, volatility and 20-day move high), and yesterday's range or body.
- **Morning conditions (09:45):** opening drive, opening-range width, gap, narrow previous range.
- **Direction:** trade only with the daily trend (DMI, the 20-day EMA, or both agreeing), or only the breakouts with the trend.
- **Priority:** TPB first when two strategies signal together.
- **TPB on closed days:** on days the gate is closed, TPB alone still trades.
- **Time of day:** entries only between 10:00 and 14:00.
- **Kind-of-day routers:** 6 ways of describing a day (trend strength, + direction, + volatility, trend regime + direction, trend strength + opening drive, + direction + opening drive). Each kind of day gets the best strategy from the library, or sits out.
- **ROBUST_CORE:** the four distinct strategies positive in both years together (TPB, two trend-pullback genomes, SHIPPED).

---

## 6. Results in numbers (₹ per lot)

**The books that matter, both years:**

| Book | 2025 | 2026 (Jan–Oct) | Both | Max DD | Green / red months | Worst one-lot week |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **Live + TPB on closed days (best found)** | **34,517** | 80,232 | **114,748** | 33,331 | 13 / 9 | ends ₹7,826 |
| Live now (UNION_ADX) | 271 | 80,912 | 81,183 | 31,482 | 9 / 5 | ends ₹7,826 |
| TPB alone | 36,694 | 42,056 | 78,750 | **22,896** | 14 / 8 | ends **₹10,265** |
| ROBUST_CORE | 19,200 | 59,630 | 78,830 | 37,483 | 15 / 7 | ends ₹9,167 |
| UNION_DRIVE (live until Oct 29) | 64,712 | 7,288 | 72,000 | 57,189 | 16 / 6 | ends ₹8,379 |
| The four, no gate (UNION) | 27,140 | −2,691 | 24,449 | 60,166 | 11 / 11 | ends ₹7,826 |
| Live + sideways fade | −14,248 | 111,046 | 96,798 | 43,126 | 16 / 6 | ends ₹7,826 |

**What failed the clean test (O30, frozen rules):**
- **The trend book:** +₹271 on 2025. It lost to the four without the gate (+₹27,140) and to UNION_DRIVE (+₹64,712).
- **The fades:** FADE −₹14,518 and PDL_FADE −₹12,775 on 2025's sideways days.
- **TPB at ADX ≥ 20:** +₹24,680. It was positive, but behind TPB always-on (+₹36,694).

**The cases (O30c, fixed before the investigation):**

| Case | Change in 2025 | Change in 2026 | Counts? |
| --- | ---: | ---: | --- |
| TPB on closed days | +34,246 | −680 | missed the strict rule by ₹680; the one real candidate |
| Trade only with the trend (EMA / DMI / both) | −5,839 / −11,532 / −8,113 | +14,057 / −4,967 / +3,578 | no: helps one year, hurts the other |
| Other day gates instead of ADX ≥ 25 | all worse in 2025 | all better in 2026 | no |
| Breakouts only with the trend, entries 10:00–14:00, the 20-day-move gate (ideas from the investigation) | worse even in-sample | | no |

**The kind-of-day router (O30m):**
- **Chosen on 2025 and run on 2026,** all 6 ways of describing a day lost (−₹21,000 to −₹79,000).
- **Chosen on 2026 and run on 2025,** 5 of the 6 lost; the one that made money (+₹2,942) still fell far short of the O30c candidate (+₹34,517).
- **Exact replays:**

  | Router | Year it was built on | The other year |
  | --- | ---: | ---: |
  | Built on 2026 | +₹1,10,602 | −₹34,803 (2025) |
  | Built on 2025 | +₹55,084 | −₹13,787 (2026) |

---

## 7. Why a strategy worked in one year and failed in the other (and the reverse)

1. **The market had a different character.**
   - **Direction:** NIFTY's daily trend pointed **down on 77% of 2026's days** and **up on 55% of 2025's**.
   - **Falls pay option buyers:** falls tend to be fast and violent, which is what an option buyer needs. Slow rises let option prices decay before the move pays.
   - **In the live book,** **puts made money in both years** (+₹27,484 in 2025, +₹63,120 in 2026). **Calls lost in 2025** (−₹27,214).
2. **The live book's 2025 loss came from one strategy.** EFF lost ₹21,796 in 2025 inside the live book, after making ₹29,629 in 2026. SHIPPED, OR20 and TPB were all positive in 2025.
3. **The trend gate was a 2026 fact, not a market law.**
   - **In 2026,** every strategy did better on ADX ≥ 25 days.
   - **In 2025,** TPB made **+₹31,869 on the closed days** (against +₹4,825 on trend days), and EFF also did better on them.
   - **The result:** the gate cut most of what the four would have made.
4. **Strategies that fit one year's rhythm lose in the next.**
   - **2026's biggest winners:**

     | Strategy | 2026 | 2025 |
     | --- | ---: | ---: |
     | VWAP band | +55,925 | −34,247 |
     | Failed-breakout fade | +47,555 | −32,772 |
     | Late momentum | +45,264 | −37,232 |
     | Noise band | +41,178 | −36,596 |

   - **The reverse:** UNION_DRIVE made +₹64,712 in 2025 and +₹7,288 in 2026.
5. **Winners don't repeat, so picking them is the trap.**
   - Ranking the 114 strategies by 2025 result and by 2026 result gives orders that barely match (correlation 0.12, where 1 would be the same order). Inside each kind of day it is −0.36 to 0.18.
   - So choosing "the best strategy for this kind of day" from past results is choosing last year's winners. Two years is not enough to learn a reliable day-by-day switch from what we can see before the session.
6. **What does repeat: the trend-pullback idea.**
   - 14 of the 114 strategies made money in both years, and most are TPB with different exits or other trend-pullback versions. None of the 20 random books did.
   - **Why it is credible:** it holds across many settings, not one lucky setting.
   - **What it does:** it waits for a trend that has already shown itself on the day, then buys the pullback. It doesn't predict the day.

---

## 8. Over-tuning: what it looks like and how it was prevented

- **What it looks like:** the router built on 2026 shows +₹1,10,602 on 2026, and −₹34,803 on the year it never saw. Patterns that look solid in tables ("breakouts with the trend", "no entries after 2 PM") made the book worse once built in. Blocking one strategy's trade just let a weaker strategy take the slot.
- **How it was prevented:**
  1. **Freeze first.** Every study committed its strategies, pass/fail rule and analysis script before any result was computed.
  2. **Fixed cases.** Cases came from standard trading logic, with one textbook setting each and no fine-tuning of numbers.
  3. **Both years separately.** A rule must help in **2025 and 2026 separately** (and in most half-years), not only in the total.
  4. **The unseen year.** A selection method must work on the year it did not see.
  5. **Yardsticks.** The live book and random choices are always beside the candidates.
  6. **Ideas found by looking stay apart.** They are reported as such and never counted as proof.
  7. **One clean exam.** NIFTY 2024 is scored once with the books frozen today and is never tuned on.

---

## 9. Issues found on Oct 30, and how they were handled

| Issue | Handling |
| --- | --- |
| The 08:00 IST download was stopped by Claude Code's memory guard while idle (Oct 29 evening) | Reported. The download was handed to another agent with `DOWNLOAD_GUIDE.md`, and long runs now go in 9-minute foreground pieces. |
| Diwali, Oct 21 2025: a holiday with only a one-hour Muhurat session. Breeze fills the index at one price around it. | `download2025.py` skips it (that week's expiry was Oct 20), and the 2025 dataset drops it. The same rule covers Nov 1, 2024. |
| The downloader writes to the same file the tests read; a long read can block it | Each test copies its data in short read-only pieces into its own sealed file (`mirror.sqlite`). |
| Breeze gaps: Jan 31, 2025 and Jan 30, 2026 have no index bars before about 11:53 | Kept as is in both years (the same treatment), and noted. |
| A binding check in the O30c freeze compared against the wrong file list (it stopped, nothing was scored) | Fixed before the freeze was committed. |
| The live book broke even on 2025 | Explained in section 7. The TPB case is the candidate. |
| Owner's Kite subscription (the owner reported it expiring) | On Oct 30 Production still read data: the trend gate at 09:45 (ADX 34.6), and the option chain every 90 s. **Renew before Nov 2.** Real-money orders go through it. |

---

## 10. What happens next

1. **Oct 31:** the owner logs in to ICICI. The other agent runs `probe2024.py` and then `download2024.py` (DOWNLOAD_GUIDE §0), before the SENSEX remainder.
2. **The 2024 exam:** `lab_f.py` (mirror24 → export24 → run), scored once by `analyze_f.py` against `RULE_2024` in `freeze-2024.json`. The scorer was written on Oct 30, before any 2024 data existed.
   - The TPB case is confirmed if it beats the live book on 2024 and isn't worse in either half.
   - "Positive in both years" carries over if at least 9 of those 14 strategies are positive on 2024.
3. **Owner's call:** whether to add "TPB on closed days" to the live book before the real-money week. It needs a small engine change: Dev → PR → deploy on the owner's go-ahead.
   - **Rollback** is one setting (`FNO_BOOK`).
   - **No engine change until the 2024 run is done,** or the run must use a worktree at `2a57ede`.
4. **The forward panel** (Oct 28 – Nov 27) keeps running; it is the clean check on new days.

---

## 11. Where everything is

| What | Where |
| --- | --- |
| This summary | `docs/FNO_RESEARCH_2026-10-30_SUMMARY.md` |
| How to test a strategy on the year data (for agents) | `docs/FNO_YEAR_DATA_TESTING_METHOD.md` |
| A copy-ready study (example strategy, freeze, run, verdict, causality test) | `docs/research/fno/study_template/` |
| Run long tests in safe 9-minute pieces | `docs/research/fno/run_slice.py` |
| The earlier playbook (archive quotes, grid, evolution, forward panel) | `docs/FNO_STRATEGY_TESTING_PLAYBOOK.md` |
| Research rules and the window ledger | `docs/RESEARCH_TESTING_METHOD.md` |
| 2025 clean test | `docs/research/fno/2026-10-30-nifty-2025-test/README.md` |
| Case study and the investigation | `docs/research/fno/2026-10-30-case-study/README.md` (+ `diagnosis.json`) |
| Kind-of-day router, persistence, 2024 exam | `docs/research/fno/2026-10-30-day-router/README.md` |
| The Oct 29 studies | `docs/research/fno/2026-10-29-year-genome/`, `2026-10-29-why-study/`, `2026-10-29-sideways-study/` (each `README.md`) |
| Data download (tooling, guide, verification) | `C:\Users\Urveesh\sentinel-operations\breeze-history-20261029\` (`DOWNLOAD_GUIDE.md`, `verify_download.py`) |
| Plan and handover | `docs/NEXT_AGENT_PLAN.md`, `docs/HANDOVER_CHECKLIST.md` (the O30, O30c and O30m sections) |
