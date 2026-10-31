# The main strategy's weak spots, and what could do better there

**Study O31e, October 31, 2026.** Research only. It follows the owner's instruction: "situations where the strategy didn't perform the best. You identify those situations and in those situations, what better strategy we can put in ... you implement a new test". Numbers and code: [`research/fno/2026-10-31-weak-spots/`](research/fno/2026-10-31-weak-spots/). The earlier steps: [FNO_FINAL_STRATEGY_2026-10-31.md](FNO_FINAL_STRATEGY_2026-10-31.md).

**The main strategy in this document** is what the owner asked for and what is now built in Dev (`eb4930d`, not deployed): the four strategies + the skip rule + ADX 30, at today's lot limits.

---

## The answer

1. **No new idea passed the strict test.** All 15 changes and all 15 sit-out-day strategies fell short, a couple of them narrowly.
2. **The biggest weak spot is calls.** Inside the main strategy, calls lost in all three years and puts earned in all three. Random entries show almost no such gap, so it belongs to these strategies, not to the market.
3. **Three candidates came out ahead on these years.** Each earned more than the main strategy over the three years, with about the same or smaller falls.
4. **All three years are now seen, so this cannot be proved on them.** A fresh exam on NIFTY 2023 is fixed in advance. That year's long calm rise is the worst case for buying puts, and it can run as soon as the data is downloaded.
5. **The main strategy stays as the owner asked until that exam.**
6. **Nothing reliable earns on the days the main strategy sits out, except possibly TPB buying puts.** Sitting out remains a sound default.

---

## 1. Where the main strategy is weak

One lot, brakes off, after ₹200 a trade. 2024 / 2025 / 2026:

| Situation | Result | Three years | Trades | Won |
| --- | ---: | ---: | ---: | ---: |
| **Calls** | −₹3,585 / −₹199 / −₹3,878 | **−₹7,662** | 56 | 39% |
| **Puts** | +₹7,828 / +₹10,501 / +₹32,504 | **+₹50,833** | 64 | 48% |
| **EFF** | −₹6,217 / −₹13,653 / +₹5,914 | **−₹13,956** | 71 | 34% |
| TPB | +₹2,932 / +₹13,651 / +₹14,487 | +₹31,070 | 20 | 70% |
| OR20 | ₹0 / +₹7,027 / +₹7,265 | +₹14,292 | 14 | 43% |
| SHIPPED | +₹7,528 / +₹3,278 / +₹959 | +₹11,765 | 15 | 60% |
| **Entries behind VWAP** | −₹6,051 / +₹2,365 / −₹9,839 | **−₹13,525** | 28 | 29% |
| **Big-gap days** | +₹2,805 / −₹7,846 / −₹548 | **−₹5,590** | 29 | 31% |
| ADX 30–35 | −₹4,514 / +₹515 / +₹15,679 | +₹11,679 | 63 | 38% |
| ADX 35 and above | +₹8,758 / +₹9,787 / +₹12,946 | +₹31,491 | 57 | 51% |

Most of the trades (71 of 120) come from EFF, the one strategy that loses here.

---

## 2. The days it sits out

ADX was under 30 on **609 of 699 sessions (87%)**: 228 of 248, 214 of 248 and 167 of 203.

The same four strategies with the rule, on those days:

| Situation | 2024 | 2025 | 2026 | Three years |
| --- | ---: | ---: | ---: | ---: |
| **Calls** | −₹37,703 | −₹55,772 | −₹30,795 | **−₹1,24,270** |
| Puts | −₹4,786 | −₹15,029 | +₹19,203 | −₹613 |
| **Entries in the gap's direction** | −₹76,468 | −₹23,666 | −₹47,513 | **−₹1,47,646** |
| Entries against the gap | +₹33,979 | −₹47,135 | +₹35,920 | +₹22,764 |
| **ADX falling** | −₹45,288 | −₹52,600 | −₹33,135 | **−₹1,31,023** |
| ADX rising | +₹2,799 | −₹18,201 | +₹21,542 | +₹6,141 |
| **Entries 12:00–13:30** | −₹24,473 | −₹16,631 | −₹16,226 | **−₹57,330** |
| **Entries 13:30–14:45** | −₹42,091 | −₹28,271 | −₹15,290 | **−₹85,653** |
| Entries 10:30–12:00 | +₹32,619 | −₹25,531 | +₹28,216 | +₹35,304 |

- **The days that would pay can't be known in advance.** Big trend days made +₹1,00,957 and quiet days made −₹2,67,791, but those labels are known only after the day.
- **Across all 116 stored strategies on these days:** none earned in all three years, and neither did any of the 20 random books. For calls alone, none did either. For puts alone, 3 did.

---

## 3. What the outside world offered

The search found little rigorous evidence.

- **Narrow CPR, NR7, low-ADX breakouts:** trader commentary and indicator scripts, with no published results. So they were tested here, and they failed.
- **The last half hour:** the first half hour predicting the last half hour is the one peer-reviewed intraday effect found (Gao, Han, Li and Zhou, *Journal of Financial Economics*, 2018). It failed here worse than anything else: **−₹1,18,237** per lot (t −6.31). The study measured an index fund's price, not options. Option buyers pay spread and costs on a move that small, and that may be why, though this test did not isolate the reason.
- **Buying options when implied volatility is low:** one vendor's claim, and no rigorous study of buyers was found. In our own data, entries when volatility was cheap still lost on the days it sits out (−₹75,014), and inside the main strategy they did worse than the rest (−₹3,421 against +₹25,225).

Sources are listed in section 8.

---

## 4. The new test

Fixed before any of these replays (`e6a7c78`). 201 replays, 0 problems, parity with the main strategy exact.

### Changes to the main strategy

Exact, at today's limits, ₹2.5 lakh, each year alone, with the assumed extra cost in the money path. **Strict pass:** better in every year, fall at most 1 point worse, 15+ trades a year, paired t at least 2. **None passed.**

| Setup | 2024 | 2025 | 2026 | Added up | Worst fall | Trades a year | t against main |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **Main** | +₹16,371 | +₹5,710 | +₹30,540 | **+₹52,621** | 7.5% | 25 / 50 / 33 | |
| **Main + TPB buying puts on sit-out days** | +₹15,337 | +₹47,892 | +₹77,233 | **+₹1,40,462** | 8.1% | 44 / 98 / 64 | 1.73 |
| **Puts only, from ADX 25** | +₹24,293 | +₹31,699 | +₹68,432 | **+₹1,24,424** | 7.4% | 37 / 60 / 37 | 1.34 |
| Puts from ADX 25, calls from ADX 30 | +₹20,252 | +₹34,935 | +₹54,227 | +₹1,09,414 | 9.6% | 46 / 80 / 49 | 1.14 |
| Without entries behind VWAP | +₹22,265 | −₹4,190 | +₹58,041 | +₹76,116 | 6.6% | 18 / 42 / 25 | 1.34 |
| **Main without EFF** | +₹12,558 | +₹27,328 | +₹26,136 | **+₹66,022** | **3.7%** | 9 / 24 / 17 | 0.54 |
| Puts only, ADX 30 | +₹19,477 | +₹5,271 | +₹38,437 | +₹63,185 | 5.8% | 16 / 25 / 23 | 0.40 |
| Calls need ADX 35 | +₹13,760 | +₹2,032 | +₹32,025 | +₹47,817 | 5.2% | 20 / 33 / 32 | −0.26 |
| Narrow opening only | +₹15,492 | +₹20,364 | +₹15,895 | +₹51,751 | 3.6% | 11 / 21 / 16 | −0.03 |
| With the gap only | +₹15,041 | −₹13,398 | +₹35,745 | +₹37,388 | 6.5% | 11 / 25 / 21 | −0.53 |
| No big-gap days | −₹8,449 | +₹17,977 | +₹24,438 | +₹33,966 | 7.2% | 18 / 41 / 24 | −0.83 |
| Only when ADX is rising | −₹13,664 | +₹10,926 | +₹34,567 | +₹31,829 | 7.3% | 11 / 34 / 26 | −0.95 |
| Puts only, from ADX 20 | +₹8,384 | −₹8,874 | +₹47,677 | +₹47,187 | 14.0% | 52 / 125 / 57 | −0.09 |
| Puts from ADX 20, calls from ADX 30 | +₹4,497 | −₹10,284 | +₹43,896 | +₹38,109 | 15.4% | 61 / 146 / 69 | −0.27 |
| Puts only, every day | −₹17,075 | −₹27,485 | +₹40,345 | −₹4,215 | 21.9% | 125 / 175 / 127 | −0.88 |
| Puts every day, calls from ADX 30 | −₹38,027 | −₹28,888 | +₹35,593 | −₹31,322 | 20.6% | 115 / 194 / 139 | −1.46 |

- **Better in every year:** puts only from ADX 25, and puts from ADX 25 with calls from 30. Their t is too low for a strict pass.
- **The weaker "better balance" test:** only main + TPB buying puts passed it. It trailed the main strategy by ₹1,034 in 2024.
- **Going lower does not keep helping.** Puts below ADX 25 for all four strategies quickly get worse. Puts every day lose money.
- **Selection check:** choosing on two years and scoring on the third gave +₹15,337 against +₹16,371 (2024), +₹31,699 against +₹5,710 (2025), and +₹68,432 against +₹30,540 (2026). That is positive every time and ahead 2 of 3, far better than the same check earlier today, which lost on all three. The frozen rule asks for all three, so it does not count as shown.

### Strategies for the days it sits out

One lot, brakes off, after ₹200 a trade, judged against sitting out, which earns exactly zero. **Pass:** above zero every year, 8+ trades a year and 40 in all, weekly t at least 2, and above the best of 20 random books (−₹8,372). **None passed.**

| Strategy | 2024 | 2025 | 2026 | Three years | Weekly t |
| --- | ---: | ---: | ---: | ---: | ---: |
| **TPB buying puts** | +₹13,199 | +₹27,831 | +₹23,559 | **+₹64,589** | **1.89** |
| Four, against the gap, 10:30–12:00 | +₹44,037 | −₹11,164 | +₹48,192 | +₹81,065 | 1.65 |
| Four, 10:30–12:00 | +₹46,538 | −₹24,468 | +₹23,072 | +₹45,142 | 0.84 |
| Four, on RBI / Budget / election days | +₹8,535 | −₹3,157 | +₹21,068 | +₹26,446 | 1.07 |
| Supertrend + VWAP | +₹1,872 | −₹15,389 | +₹25,129 | +₹11,612 | 0.31 |
| Four, against the gap | +₹17,904 | −₹41,960 | +₹34,714 | +₹10,658 | 0.17 |
| Gap fade | +₹5,371 | +₹9,918 | −₹9,633 | +₹5,656 | 0.26 |
| Prior-day high/low break | +₹10,231 | −₹3,050 | −₹2,367 | +₹4,814 | 0.47 |
| Four, ADX 25–30 and rising | −₹17,100 | −₹6,939 | +₹27,487 | +₹3,448 | 0.10 |
| Four, once the day's range has expanded | +₹2,729 | −₹32,784 | +₹29,593 | −₹462 | −0.01 |
| First-hour range break | +₹2,922 | −₹5,923 | −₹5,994 | −₹8,995 | −0.89 |
| Four, puts only | −₹19,914 | −₹15,137 | +₹24,190 | −₹10,861 | −0.17 |
| Narrow-CPR break | −₹5,587 | −₹5,351 | −₹2,916 | −₹13,854 | −1.78 |
| Last hour, sit-out days | −₹61,917 | −₹29,007 | −₹6,993 | −₹97,917 | −5.44 |
| Last hour, every day | −₹64,559 | −₹40,856 | −₹12,822 | −₹1,18,237 | −6.31 |

TPB buying puts is the only one that earned in all three years. It missed only the t test, by 0.11.

### Is the put edge a market effect?

**Not on this evidence.** On the same days, random entries lost about the same on puts as on calls: −₹84,856 against −₹81,952 on sit-out days, and −₹14,133 against −₹19,342 on ADX 30 days. The real strategies earned +₹50,833 on puts and lost ₹7,662 on calls. A likely reason is that sell-offs run fast and lift option prices, while rises grind and let them decay. That reason is an interpretation, not something this test measured.

---

## 5. The three candidates in more detail

One lot, brakes off, after ₹200 a trade, 34 months:

| | Main | Main + TPB puts | Puts only from 25 | Main without EFF |
| --- | ---: | ---: | ---: | ---: |
| Net | +₹43,170 | +₹1,07,699 | +₹1,08,800 | +₹59,098 |
| Trades, won | 120, 44% | 222, 45% | 142, 48% | 50, 60% |
| Months up / down | 5 / 5 | **20 / 12** | 11 / 7 | 7 / 2 |
| Three-month periods up / down, of 32 | 9 / 8 | **26 / 6** | 17 / 7 | 14 / 3 |
| Weeks up / down / no trade, of 148 | 11 / 10 / 127 | 39 / 37 / 72 | 24 / 20 / 104 | 11 / 5 / 132 |
| Weekly t | 1.61 | **2.48** | 2.03 | 2.33 |
| Biggest fall | ₹13,142 | ₹16,492 | ₹19,250 | **₹7,441** |
| Worst month | −₹3,720 | −₹6,762 | −₹9,580 | **−₹2,957** |
| Without each year's best day | +₹13,797 | **+₹72,367** | +₹48,689 | +₹26,272 |
| From ₹15,000, chance under ₹7,000 in 60 sessions | 0.2% | 2.5% | 1.1% | **0%** |
| From ₹15,000, a five-session week with no trade | 85% | **54%** | 76% | 90% |

- **Main + TPB buying puts** is the most consistent, and it depends least on big days. It trades in about every other week.
- **Main without EFF** has the smallest losses, but it makes only about 17 trades a year.
- **Puts only from ADX 25** is the simplest change, but it never buys a call.

**A real danger:** these three years may flatter a put buyer. None of them held a long calm rise with few sell-offs. A book that buys only puts could bleed through such a year.

---

## 6. The next step: an exam on NIFTY 2023

NIFTY rose about 20% in 2023, so it is the fairest hard test. **The books and the rule are fixed now in `research/fno/2026-10-31-weak-spots/freeze-2023.json`,** before any 2023 data exists here.

- **Books:** main, main + TPB puts, puts only from 25, puts from 25 with calls from 30, puts only at ADX 30, main without EFF.
- **Rule:** a candidate holds if it nets more than the main strategy on 2023 and its fall is at most 15%. If main + TPB puts or puts only from 25 holds, the higher earner over three years is recommended as the new main. If neither holds, the main strategy stays.
- **Needs:** the owner's ICICI login, about one day's download allowance, and the download agent. ICICI has not been asked whether it serves 2023, so the first step is a small probe.
- **The SENSEX remainder waits** for the following day's allowance.

---

## 7. What this study did not do

- **No new strategy went into the system.** Nothing here changes the engine.
- **It did not use each year's real lot.** Lot 65 is used in all years so results are comparable.
- **It did not prove anything.** The list of ideas was shaped by looking at these three years. The ₹200 a trade is an assumption.
- **The event dates for 2024 and 2025 are from memory** of the published calendars and were not checked against a source. That sample is small and did not pass.

---

## 8. Sources

- [Market intraday momentum, Gao, Han, Li and Zhou, Journal of Financial Economics 2018](https://econpapers.repec.org/RePEc:eee:jfinec:v:129:y:2018:i:2:p:394-414)
- [A summary of that study](https://alphaarchitect.com/2014/08/attention-prop-traders-the-first-half-hour-of-trading-predicts-the-last-half-hour/)
- [Volatility risk premium, a vendor's description](https://flashalpha.com/concepts/vrp)
- [Why option sellers usually earn the premium](https://www.cxoadvisory.com/volatility-effects/the-why-of-the-volatility-risk-premium)
- [An ADX range-breakout code example, with no published results](https://doc.stocksharp.com/en/api-examples/0507_ADX_Range_Breakout)
- [A Nifty CPR commentary, anecdotal](https://it.tradingview.com/chart/NIFTY/EF6QgS7Z-Nifty-Analysis-EOD-August-6-2025-Wednesday)
- [RBI's Monetary Policy Committee calendar for 2026-27](https://www.rbi.org.in/scripts/BS_PressReleaseDisplay.aspx?prid=62422)
- [RBI's February 2026 decision date](https://www.5paisa.com/news/rbi-mpc-february-2026-meet-policy-decision-on-february-6-live-streaming-details-announced)
