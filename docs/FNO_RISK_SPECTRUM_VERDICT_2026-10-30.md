# The risk spectrum and the final verdict on the F&O book

> **Corrected by the 2024 exam (Oct 31, 2026):** see [FNO_2024_EXAM_2026-10-31.md](FNO_2024_EXAM_2026-10-31.md). On a year it had never seen, the pick here (TPB + rule, ₹5,000, no cap, no brakes) lost ₹60,581 with a 38.6% fall. The stretched-entry rule itself passed, and the best candidate is now the four strategies with that rule, at today's limits. This page is kept as written on Oct 30.

**Study O30r, October 30, 2026.** Research only. Nothing in the trading system changed, and Production was not touched. The real-money test from Nov 2 is unchanged.

Companion to [FNO_EARNING_POWER_2026-10-30.md](FNO_EARNING_POWER_2026-10-30.md). Numbers and code: [`research/fno/2026-10-30-risk-spectrum/`](research/fno/2026-10-30-risk-spectrum/README.md).

---

## The verdict

1. **Are we too conservative? No.** With realistic costs the best level over both years is **₹5,000 of risk per trade**, the same risk per trade we use today. More money at risk earned more only up to ₹12,500 a trade, and the fall grew much faster than the profit. From ₹25,000 a trade it stopped paying at all. All-in lost everything.
2. **Is there a book that does reasonably well in both years? Yes, in these replays:** TPB (the trend-day pullback) with one rule, skip entries that are already stretched far from VWAP.
3. **Is the system generally profitable? Today's live book: not proven. TPB with the rule: modestly yes, in replays,** in most months and most three-month periods, but not most weeks. It is about 16–27% a year on ₹2.5 lakh, not a daily income.
4. **Nothing earns reliably on sideways days.** Only 1 of 116 strategies made money on them in both years. The practical answer is to lose less on those days.
5. **None of this is proof.** Both years were already seen, and the rule was found by looking at them. The 2024 exam and real fills decide.

---

## 1. The spectrum: every level, exact

**How it was run.** 692 replays through the shipped code, not the sizing simulator. A level is only settings: the shipped planner sizes it as money × risk share ÷ (premium × 65 × premium stop), within own cash.

The money path includes an extra cost of ₹200 per lot per trade plus ₹5 per lot for each lot in the order. That is an assumption, because no real-fill data exists yet. The account is carried from Jan 2025 to Oct 2026 (22 months), so a wipe-out stays wiped out.

**TPB with the rule, ₹2.5 lakh start:**

| Level | Risk per trade at the start | 2025 alone | 2026 alone | Money after 22 months | Biggest fall | Worst day |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1% | ₹2,500 | +₹12,821 | +₹4,972 | ₹2,69,375 | 11% (₹30,034) | −₹3,899 |
| **Today's limits** (2%, 1–3 lots, all brakes) | ₹5,000 | +₹37,320 | +₹22,413 | **₹3,29,141** | **12% (₹43,065)** | −₹11,570 |
| **2%, no lot cap, no brakes (the pick)** | ₹5,000 | **+₹61,417** | **+₹31,346** | **₹3,49,696** | **21% (₹80,745)** | −₹15,435 |
| 3% | ₹7,500 | +₹67,541 | +₹25,501 | ₹3,72,717 | 32% (₹1,45,121) | −₹24,846 |
| 4% | ₹10,000 | +₹88,863 | +₹48,002 | ₹4,02,811 | 42% (₹2,17,915) | −₹36,711 |
| 5% (the most money) | ₹12,500 | +₹84,885 | +₹59,463 | ₹4,15,516 | 51% (₹3,01,598) | −₹48,401 |
| 8% | ₹20,000 | +₹53,986 | +₹34,890 | ₹3,35,223 | 72% (₹5,08,106) | −₹95,506 |
| 10% | ₹25,000 | +₹1,513 | −₹1,406 | ₹2,55,226 | 80% (₹5,51,120) | −₹1,15,408 |
| 15% | ₹37,500 | −₹1,01,664 | −₹73,118 | ₹1,20,633 | 91% | −₹1,22,159 |
| 25% (all the money, 25% stop) | ₹62,500 | −₹2,24,937 | −₹1,83,085 | ₹31,351 | 99% | −₹1,55,809 |
| All the money, no stops | everything | −₹2,42,458 | −₹2,46,444 | ₹2,361 (wiped out) | 100% | −₹3,41,634 |

**Reading it:**
- **Money rises until 5% and then falls.** Past that point more risk means less money.
- **The pick is exactly half the peak.** The peak was 4% in 2025 and 5% in 2026, so half the smaller one is 2%. Betting at half the peak is the standard margin of safety, because the estimates can be wrong ([MacLean, Thorp and Ziemba](https://www.stat.berkeley.edu/~aldous/157/Papers/Good_Bad_Kelly.pdf)).
- **Today's limits give the best return per rupee of fall:** +₹79,141 for a ₹43,065 fall. The pick adds about ₹20,555 and costs ₹37,680 more fall. Going to 5% adds another ₹65,820 and costs ₹2,20,853 more fall.
- **At 1%, too many trades are refused,** because the option costs too much for that risk budget.
- **The worst day is not ₹5,000 even today.** The −3% day stop blocks new entries; it does not close open ones, and a trade can lose more than planned.
- **Without stops one trade took 61–74% of the account.**

**The frozen answers:**
- **Balanced:** highest worse-year net with both years positive, at most one negative half-year, at least 40 trades a year, a fall of at most 25%, no wipe-out. **TPB + rule at 2%, no brakes.** 12 of 168 pass; today's limits with the rule come second.
- **Most money:** TPB + rule at 5%, ₹4,15,516, with a 51% fall.
- **Lowest risk that still earns:** TPB at 1% with scaled brakes, +₹152 / +₹13,580, 9% fall.
- **Cross-year:**
  - Chosen on 2025: TPB + rule at 3% made +₹67,541, then +₹25,501 on 2026 with a 31% fall.
  - Chosen on 2026: four strategies + rule at 6% made +₹2,28,948, then **−₹1,11,959 on 2025 with a 66% fall**.
  - So a level picked from one good year cannot be trusted. Holding TPB with the rule is the only choice that survived in both directions.

**The four strategies at each level, with the extra cost:**

| Book and level | 2025 | 2026 | Money after 22 months | Biggest fall |
| --- | ---: | ---: | ---: | ---: |
| **Today's live book, today's limits** | **−₹38,681** | +₹61,674 | ₹2,11,319; stops itself in Mar 2025 | 17% |
| Live book + rule, today's limits | +₹4,805 | +₹47,333 | ₹2,99,061 | 12% |
| Live book + rule, 2%, scaled brakes | +₹5,159 | +₹60,022 | ₹3,08,777 | 12% |
| Live book + rule, 4%, scaled brakes | +₹18,041 | +₹1,03,279 | ₹3,00,457 | 23% |
| Live book + TPB on closed days + rule, 2%, scaled brakes | +₹9,886 | +₹59,716 | ₹3,20,720 | 15% |
| Live book, 5%, no brakes | −₹1,81,675 | +₹1,12,682 | ₹88,033 | 80% |

The rule matters more than the level. **At the same limits, the rule moves the live book's 2025 from −₹38,681 to +₹4,805 and keeps it trading,** though 2026 gives up about ₹14,000.

**Brakes:** on the four strategies they cut the fall roughly in half at higher risk (4%: 48% without, 23% with). On TPB in 2025 they cost money (2%: +₹61,417 without, +₹10,359 with).

**The cost is the biggest unknown.** Without the extra cost, TPB + rule at 5% shows ₹13 lakh and at 10% about ₹40 lakh. **Those are not believable:** they assume up to 539 lots fill at the candle's price, while one NIFTY order is limited to 54 lots ([NSE circular, Oct 2026](https://nsearchives.nseindia.com/content/circulars/FAOP76693.pdf)). If real fills show almost no extra cost, the balanced level moves from 2% to about 3% (₹6,70,301, 24% fall, as replayed). Real fills from Nov 2 are what will settle this.

**Other settings, one at a time** (5% risk, with the extra cost; never chosen):
- A 15% premium stop is much too tight (TPB + rule: −₹12,125 / +₹3,173).
- Stops wider than 25% with the same rupee risk simply mean fewer lots.
- On TPB with the rule, fewer trades a day, one position at a time, and wider or narrower underlying stops only move money between the two years. None is better in both.
- On the four strategies plus TPB with the rule, an underlying stop twice as wide is better in both years (−₹26,263 / +₹1,14,699 against −₹40,377 / +₹50,098), but 2025 is still negative and the fall is about 53%, so it is noted and not chosen.

## 2. Which strategy on which kind of day

Per lot, shipped size and brakes, as replayed. Each cell is 2025 / 2026. **These labels are known only after the day**, so no system can choose by them in advance.

| Kind of day (days) | Big trend (78 / 47) | Big swings both ways (45 / 58) | Quiet trend (51 / 34) | Sideways (74 / 64) |
| --- | ---: | ---: | ---: | ---: |
| SHIPPED | +33,618 / +34,859 | −7,433 / +799 | −11,186 / −5,362 | −8,478 / −22,598 |
| OR20 | +44,836 / +51,281 | −20,932 / +5,109 | −13,991 / −12,859 | −15,956 / −50,125 |
| EFF | +50,878 / +29,508 | **+32,552 / +50,069** | −29,017 / −41,954 | −54,794 / −49,807 |
| TPB | **+70,293 / +49,926** | −9,626 / +20,516 | −2,030 / −4,082 | −21,943 / −24,305 |
| Four together, no gate | +77,203 / +42,105 | +30,556 / +55,693 | −33,319 / −50,467 | −47,299 / −50,022 |
| Live book (ADX gate) | +28,412 / +64,588 | +5,591 / +54,701 | −11,613 / −15,162 | −22,119 / −23,215 |
| Live book + rule | +33,066 / +30,725 | +20,685 / +36,921 | −12,152 / −8,350 | **−13,830 / −3,773** |
| TPB + rule | +75,529 / +51,884 | −4,502 / +11,033 | **−1,774 / −1,269** | −17,023 / −15,996 |
| Strategies of 116 positive in both years | 47 | 24 | 5 | **1** |
| Random books of 20 positive in both years | 6 | 5 | 1 | 0 |

- **Big trend days are where the money is,** and nearly everything earns.
- **Big swing days suit the fast breakout, EFF.** It is the exception that earns there, and it gives it all back on quiet days.
- **Quiet trend days:** late-day momentum made a little (+₹4,312 / +₹11,828 at best); everything else lost. TPB with the rule is about flat.
- **Sideways days:** the only strategy positive in both years was one failed-break fade (+₹2,273 / +₹17,986), found by scanning with hindsight. That family loses across whole years (O30). So there is no sideways strategy to deploy. The rule makes those days cost less.

**What can be known before the trade** (yesterday's ADX):

| | ADX ≥ 25 (gate open) | ADX < 25 (gate closed) |
| --- | ---: | ---: |
| Live book + rule | +27,769 / +55,524 | no trades |
| TPB + rule | +24,304 / +46,824 | +27,926 / −1,172 |
| Four together, no gate | +1,755 / +12,771 | +25,385 / −15,462 |

So when the gate is open, the four strategies with the rule and TPB with the rule both work. When it is closed, TPB with the rule is the only one worth considering, and in 2026 it only broke even there. In 2025 the four did well on closed days, which is why the gate gave up 2025 (+₹27,140 to +₹271).

**Which strategy suited which year:**
- **2026 (a falling market, wide daily ranges):** the live book, +₹80,912, of which **+₹47,288 was Budget day**. Almost all its 2026 profit came on days when the daily trend was down (+₹80,977 against −₹64).
- **2025 (rose slowly, narrower ranges):** the opening-drive book that ran until Oct 29 made +₹64,712, then only +₹7,288 in 2026.
- **Both:** TPB with the rule, +₹52,230 / +₹45,652, and the live book plus TPB on closed days with the rule, +₹56,904 / +₹51,885.

## 3. The small changes, measured

Per lot, exact, shipped size and brakes:

| Change | 2025 net | 2026 net | 2025 fall | 2026 fall |
| --- | ---: | ---: | ---: | ---: |
| **ADX gate** on the four | +27,140 → +271 | **−2,691 → +80,912** | 29,091 → 31,482 | **60,166 → 12,519** |
| **Skip stretched**, live book | **+271 → +27,769** | +80,912 → +55,524 | 31,482 → 22,252 | 12,519 → 7,363 |
| **Skip stretched**, TPB | +36,694 → +52,230 | +42,056 → +45,652 | 14,966 → 13,277 | 22,896 → 20,981 |
| **TPB on closed days**, live book | +271 → +34,517 | +80,912 → +80,232 | 31,482 → 20,398 | 12,519 → 33,331 |

- **The ADX gate cut the 2026 fall by 79%, but it did nothing for 2025.** No single change saved the majority of the falls in both years.
- **Skipping stretched entries cuts falls by 8–41%,** with the biggest effect on the four strategies.

## 4. Is it generally profitable?

Per lot, shipped size and brakes, Jan 2025 – Oct 2026, 22 months. Each cell is as replayed / after ₹200 per trade.

| Book | Net | Green months of 22 | Green 3-month windows of 20 | Weekly t-statistic | Without its best day |
| --- | ---: | ---: | ---: | ---: | ---: |
| Live book | +81,183 / +32,383 | 9 / 9 (14 traded) | 11 / 10 | 1.33 / 0.55 | +33,895 / −14,305 |
| Live book + TPB on closed days | +1,14,748 / +38,148 | 13 / 12 | 14 / 8 | 1.61 / 0.54 | +67,460 / −8,540 |
| TPB | +78,750 / +40,350 | 14 / 12 | 16 / 13 | 1.77 / 0.91 | +57,489 / +19,489 |
| Live book + rule | +83,293 / +50,693 | 8 / 7 (13 traded) | 13 / 8 | 1.86 / 1.18 | +60,091 / +27,891 |
| Live book + TPB on closed days + rule | +1,08,789 / +52,389 | 14 / 11 | 14 / 12 | 2.04 / 1.01 | +85,587 / +29,587 |
| **TPB + rule** | **+97,882 / +64,882** | **16 / 14** | **16 / 14** | **2.43 / 1.63** | **+80,093 / +47,493** |
| 20 random books | median −31,502, best +1,222 | | | | |

**In rupees at today's limits (TPB + rule, ₹2.5 lakh):** ₹3,29,141 with the extra cost and ₹3,89,824 without. That is about ₹3,600–6,400 a month, or roughly 16–27% a year, with a fall of 8–12%.

**Plainly:**
- **Yes, modestly, in replays, for TPB with the rule.** It was positive in both years, in 14–16 of 22 months and 14–16 of 20 three-month periods. No random book came close.
- **Not day by day.** It trades on about a quarter of sessions (115 of 451). Weeks are close to a coin flip: 37 up, 34 down, 25 with no trade.
- **Today's live book is not proven.** After the extra cost it lost ₹38,681 in 2025 and stopped itself that March. Its 2026 depended on one day; without that day its two-year total after ₹200 per trade is negative.
- **The evidence is suggestive, not proof.** A t-statistic of 1.63 after costs falls short of the usual bar of 2. More than a thousand combinations have been tried on these two years, and the rule came from looking at them.

## 5. What was checked

- **All 692 replays passed `check_book`:** every trade closed, charges recomputed, trades per day, own cash, and lot size recomputed from the planner's formula (brakes off). Zero problems.
- **The shipped level reproduces the stored rupees exactly:** −7,738 / +68,176, +36,068 / +57,776, +82,124 / +45,796.
- **A sample replayed twice gave identical trades** (three books, both years).
- **Each carried 2026 started from 2025's end balance** (asserted).
- **The earlier simulator was only a cross-check.** It is close at 1–2%. Above that it runs lower for the rule books and differs either way for the live book, because the larger account can buy high-premium options the one-lot run refused, and that compounds. This is why the numbers here come from exact replays.
- **Random books at the same shares:** none positive in 2025 at any level, at most 2 of 20 in 2026. From 8% up, some end under ₹10,000, and at 25%, 19 of 20 did in 2025.

## 6. What was decided, and what is left

- **No change to the system.** Lots are not raised. The risk per trade stays at ₹5,000.
- **Risk to know about:** the Nov 2 real-money test mirrors today's live book, which is the weaker choice under realistic costs. At one lot this cannot do much damage, but the test will measure that book. Whether to change it first is the owner's call, after the exam.
- **The pick is frozen for 2024** (third sheet, `2026-10-30-risk-spectrum/freeze-2024.json`, before any 2024 data exists). The O30f and O30s sheets are scored first. Steps: `exam_r.py run` with `O30F_YEAR=2024`, then `exam_r.py score`, once. The run and score steps have not been run, because no 2024 data exists; the scoring logic is covered by `test_exam_r.py`.
- **Not tested:** other indices, because their options are not fully downloaded. Spreading the same rule across indices is the main route not yet tested for raising profit without raising risk per trade.

## 7. Files

| File | What |
| --- | --- |
| `lab_r.py`, `freeze.json` | Levels, books, the extra cost, the carried account; freeze `8fd8de8` |
| `analyze_r.py`, `results.json` | The proof checks, the frozen answers, every row |
| `verdict_r.py`, `verdict.json` | Kinds of day, consistency, the single changes (written after seeing results) |
| `exam_r.py`, `freeze-2024.json` | The third 2024 sheet |
| `test_lab_r.py`, `test_exam_r.py` | 13 tests |

Run with `python-engine\winvenv\Scripts\python.exe`: `lab_r.py run` per year (`O30C_YEAR`, 2025 first), `analyze_r.py`, `lab_r.py verify` per year, `verdict_r.py`. Method: [FNO_YEAR_DATA_TESTING_METHOD.md](FNO_YEAR_DATA_TESTING_METHOD.md), section 15.
