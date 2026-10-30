# Why the F&O book does not earn lakhs, and what more size really costs

**Study O30s, October 30, 2026.** Research only. Nothing in the trading system changed, and Production is untouched. The real-money test from Nov 2 stays at one lot.

Written for the owner first and for any agent continuing the work. Section 14 shows how to repeat or extend it. The detailed numbers are in [`research/fno/2026-10-30-earning-power/`](research/fno/2026-10-30-earning-power/README.md).

---

## The short version

1. **Yes, the book is conservative.** On ₹2.5 lakh it puts ₹11,000–17,000 into an average trade, which is 4–7% of the money, and trades on 46–105 days a year.
2. **But caution is not what holds it back.** Three times the lots on today's strategies (no brakes) would have lost ₹34,479 in 2025 before any extra costs, and ₹1,25,079 with them. A larger size only multiplies whatever edge is there, and in 2025 the edge was close to zero.
3. **"Lakhs in a day" does exist in our own tests.** The live strategies at 6 lots, adding to winners, made **₹1,38,943 on one day** (Feb 1, 2026) and ₹5.80 lakh that year. The same settings **lost ₹2.12 lakh in 2025, an 85% fall.** That is the trade-off in one line.
4. **One day made most of the "great" 2026.** The Budget-day crash on Feb 1 was ₹47,288 of the live book's ₹80,912 per lot (58%). Without it, TPB alone beat all four strategies together in 2026.
5. **The most useful finding is about where we enter, not how much we buy.** Entries made after price has already run far from its average (VWAP) lose in nearly every test. Passing over them took the four-strategy book's 2025 from +₹271 to +₹27,769 per lot and left it positive in both years even after ₹200 extra cost per trade. It costs about ₹25,000 of 2026, mostly one Budget-day trade.
6. **₹2 lakh a year on ₹2.5 lakh is 80% a year.** With TPB plus that rule it would have taken about 5 lots: +₹2.53 lakh and +₹1.83 lakh as replayed, +₹1.52 lakh and +₹1.12 lakh after extra costs, with a fall of ₹98,000–1,41,000 on the way and a worst day of about −₹37,000. These are in-sample numbers. They are not proof until the 2024 exam and forward data.

**Nothing here is a promise.** Both years were already seen, and the rule in point 5 was found by looking at them. NIFTY 2024 is the one clean check left (section 12).

---

## 1. The question

> "so many people earn literally lakhs in single days and then despite putting almost 2.5 lakhs in paper why can the system not even earn 2 lakhs in any single year? is it because of our conservativeness? is there any way where we can ensure our current minimalistic loss strategy ... the 4 strategies together had done really well in 2026 run though failed in 2025 ... search and make combinations and test it out ... tell me how much tradeoff" (owner, Oct 30)

Every earlier F&O study compared strategies **per lot**. This is the first one measured in **rupees on ₹2.5 lakh**.

## 2. Words used here

| Word | Meaning |
| --- | --- |
| **LIVE** | Today's book: the four strategies (SHIPPED, OR20, EFF, TPB), only on days the daily trend strength ADX was ≥ 25 the day before |
| **BEST** | LIVE, plus TPB on the days the trend gate is closed (the O30c candidate) |
| **TPB** | The trend-day VWAP pullback strategy alone |
| **Stretched entry** | At entry, the last closed 5-minute close is already at least half of the first 30 minutes' range beyond VWAP, in the trade's direction |
| **"As replayed"** | The replay's own prices and real charges |
| **"+₹200"** | The same, with ₹200 more cost per lot per trade. Treat this as the more realistic of the two: earlier checks found the candle data flatters a trade by about ₹100–200 per lot |
| **Fall** | The largest drop from a running peak (with no brakes, the two years joined from ₹2.5 lakh unless stated) |
| **Half-year** | 2025 Jan–Jun, 2025 Jul–Dec, 2026 Jan–May, 2026 Jun–Oct |

## 3. Why others earn lakhs in a day

Three things, and "better strategy" is not the first of them.

**Their capital is far bigger.** ₹2 lakh is 2% of ₹1 crore. On one lot, our own data gives the scale:

| Per lot, with perfect hindsight (buy the better side at 09:45, sell at its best minute) | 2025 | Jan–Oct 2026 |
| --- | ---: | ---: |
| A median day | ₹4,408 | ₹4,783 |
| The best day of the year | ₹18,690 | ₹31,088 |
| The whole year, every day perfect | ₹9,66,746 | ₹9,69,121 |

So ₹2 lakh on a typical day needs about 45 lots, roughly ₹5 lakh of premium, **even with perfect timing that nobody has**.

**You only hear from the winners.** SEBI's studies of individual F&O traders:
- 91% lost money in FY25, with average losses of about ₹1.1 lakh ([Business Standard](https://www.business-standard.com/markets/news/net-losses-of-traders-in-fo-widens-in-fy25-sebi-study-125070701221_1.html), [Value Research](https://www.valueresearchonline.com/stories/225398/average-trader-lost-rs-1-1-lakh-fo-fy25/)). 87.7% still lost in FY26 ([Finnovate](https://www.finnovate.in/learn/blog/sebi-fno-trader-losses-fy26-individual-derivatives)).
- Over FY22–FY24, 93% lost. The biggest 3.5% of loss-makers lost ₹28 lakh on average, and only about 1% made more than ₹1 lakh after costs ([Taxmann](https://www.taxmann.com/post/blog/93-of-1-crore-fo-traders-saw-rs-2l-avg-loss-while-top-3-5-faced-rs-28l-avg-loss-incl-costs-sebi/), [Fortune India](https://fortuneindia-web.quintype.io/investing/9-out-of-10-individual-traders-faced-losses-in-equity-fo-in-fy22-fy24/118513)).
- Proprietary firms and foreign funds earned about ₹61,000 crore gross in FY24, largely by algorithm ([TaxGuru](https://taxguru.in/sebi/sebi-study-shows-93-percent-individual-fo-traders-incur-losses.html)).

**Big size cuts both ways.** Our ₹5.80 lakh example below is the same trader who lost 85% the year before. A screenshot of the first never shows the second.

**80% a year is a very high bar.** A well-known published intraday momentum strategy reports about 19.6% a year on the S&P 500 ETF over 2007–2024, with leverage up to 4× ([Zarattini, Aziz and Barbon](https://concretumgroup.com/beat-the-market-an-effective-intraday-momentum-strategy-for-sp500-etf-spy/)). That is the authors' own figure on a different market, used only for scale.

## 4. How much of the ₹2.5 lakh is actually used

From the exact replays at the shipped size and brakes:

| Book | Year | Trades | Days traded | Average in a trade | Share of the money | Average lots | Rupees made |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| LIVE | 2025 | 138 | 54 | ₹11,108 | 4.4% | 1.17 | −₹7,738 |
| LIVE | 2026 | 106 | 46 | ₹17,036 | 6.8% | 1.41 | +₹68,176 |
| BEST | 2025 | 214 | 105 | ₹11,796 | 4.7% | 1.34 | +₹1,343 |
| BEST | 2026 | 169 | 87 | ₹14,006 | 5.6% | 1.25 | +₹92,002 |
| TPB | 2025 | 107 | 71 | ₹12,395 | 5.0% | 1.50 | +₹34,435 |
| TPB | 2026 | 85 | 57 | ₹11,933 | 4.8% | 1.25 | +₹36,965 |

This is by design (`python-engine/config.py`):
- at most 2 lots, or 3 once the record is proven;
- at most 2% of the money at risk, capped at ₹6,250;
- at most 15% of the money in premium, and 3 trades a day;
- stops at −3% in a day, −6% in a week and −10% in a month, and a full stop at −15%;
- size is cut to half at 4% below the peak and to a quarter at 8%.

So the answer to "is it our conservativeness?" is **yes on the mechanics**, and the next sections show why simply removing it fails.

## 5. What was tested

Everything was frozen and pushed before scoring (commit `045351b`).

- **Size:** fixed 1–15 lots, or 1–10% of the money at risk.
- **Brakes:** none, the shipped ones, a throttle that cuts size in a fall without stopping, and the throttle with a daily stop.
- **Smart size:** half size on a stretched entry.
- **Letting winners pay:** add a lot at +1R with the stop moved to entry (ADD1), also at +2R with the stop at +1R (ADD2), or the engine's own add at target (HOUSE). Hold longer: RUN (120 min, 2 ATR) or HOLD (no time stop, 3 ATR).
- **Running side by side:** the four strategies as separate slots, and LIVE beside TPB.
- **The O30q ideas, one textbook setting each:** RETEST (break, pull back, continue), FAILCONF (failed break confirmed, reverse), SQUEEZE (quiet box, then break).
- **Control:** the same on 20 random-entry books.
- **Information only:** the hindsight ceiling and option selling.

That made **38 books × 136 size and brake settings = 5,168 combinations**. The simulator matched the stored shipped replays within ₹2,416 a year and one trade.

## 6. What size does

The same trades, more lots, with no brakes:

| | 1 lot | 3 lots | 5 lots | 10 lots |
| --- | ---: | ---: | ---: | ---: |
| **LIVE, as replayed:** 2025 / 2026 | −₹11,493 / +₹78,825 | −₹34,479 / +₹2,36,474 | −₹57,125 / +₹3,94,123 | −₹1,07,322 / +₹5,79,422 |
| **LIVE, +₹200:** 2025 / 2026 | −₹41,693 / +₹56,825 | −₹1,25,079 / +₹1,70,474 | −₹2,25,950 / +₹2,84,123 | −₹2,47,472 / +₹4,04,386 |
| LIVE, +₹200: biggest fall | 22% | 61% | 95% | 99% |
| **TPB, as replayed:** 2025 / 2026 | +₹32,525 / +₹37,442 | +₹97,576 / +₹1,12,327 | +₹1,62,627 / +₹1,87,211 | +₹1,34,499 / +₹3,76,271 |
| **TPB, +₹200:** 2025 / 2026 | +₹10,125 / +₹19,642 | +₹30,376 / +₹58,927 | +₹45,040 / +₹98,211 | −₹2,08,331 / +₹1,92,829 |
| TPB, +₹200: biggest fall | 12% | 28% | 42% | 96% |

Look at TPB at 10 lots in 2025. **The trades that made +₹10,125 on one lot lose ₹2,08,331 on ten.** An early losing run takes the money, the account can then only afford fewer lots, and the recovery arrives too small to matter.

**The big-day example, replayed exactly** (LIVE, adding at +1R, 6 lots, half size when stretched):

| | 2025 | 2026 |
| --- | ---: | ---: |
| Net | **−₹2,11,891** | **+₹5,79,750** |
| After +₹200 | −₹2,79,891 | +₹4,47,550 |
| Biggest fall that year | 85% | 21% |
| Best day | ₹14,159 | **₹1,38,943** (Feb 1) |

**How far size can go, by the Kelly formula** (lots at which long-run growth is highest; going past it earns *less* over time, and the literature advises betting well below it because the inputs are estimates, [MacLean, Thorp and Ziemba](https://www.stat.berkeley.edu/~aldous/157/Papers/Good_Bad_Kelly.pdf)):

| Book | As replayed | +₹200 |
| --- | ---: | ---: |
| LIVE | 2.6 | below zero |
| BEST | 3.1 | below zero |
| TPB | 8.1 | 3.4 |
| LIVE with the rule (section 9) | 9.9 | 4.9 |
| BEST with the rule | 8.6 | 3.4 |
| TPB with the rule | 15.4 | 9.3 |

**The frozen verdict.** A combination passes if, after +₹200, it is positive in both years, negative in at most one half-year, falls no more than 25%, makes at least 40 trades a year, and beats the random books under the same size.
- **71 of 5,168 pass, and 67 of those are TPB alone with some size or add.** Four include the live strategies.
- **The frozen pick** is TPB with the engine's add, 3 lots, half size when stretched: +₹61,695 / +₹65,438, fall 23%. Exact replay: +₹60,901 / +₹1,10,166. Plain TPB at the same size is as good and simpler, so the add earns its place only by a whisker.
- **One pass fell over in exact replay.** LIVE with ADD2, at the shipped risk and brakes, was simulated at +₹11,895 in 2025 and came out at −₹41,332. The simulator is reliable for sizes without brakes (usually one trade apart). It is not reliable once brakes decide which trades happen.
- **Picking by one year's best is luck.** The best combination on 2026 alone (+₹5.42 lakh, 21% fall) did −₹2.42 lakh on 2025 with a 97% fall. The best on 2025 alone stayed positive on 2026 (+₹65,195) but below plain TPB and BEST at the same size.

## 7. One day made most of 2026

Feb 1, 2026 was the Sunday Budget session, when NIFTY fell about 2% after the F&O tax rise ([Business Today](https://www.businesstoday.in/union-budget/story/budget-2026-stock-market-sensex-nifty-plunge-2-after-stt-hike-on-fo-trades-513924-2026-02-01)). Our index data shows 25,400 at 11:30 and 24,777 at 12:30.

| Per lot, shipped book | 2026 | From Feb 1 | Without Feb 1 |
| --- | ---: | ---: | ---: |
| LIVE | +₹80,912 | +₹47,288 | +₹33,625 |
| BEST | +₹80,232 | +₹47,288 | +₹32,944 |
| TPB | +₹42,056 | no trade | +₹42,056 |

So "the four together did really well in 2026" is true mostly because they were there on one crash day. That is what option buying is supposed to catch, and it is real money in the replay. But it cannot be planned on, and one such day is not a repeatable edge.

The wider pattern matches. On raw one-lot books (no brakes), BEST made +₹42,866 / +₹1,15,271 on the biggest 10% of days and **lost ₹38,493 / ₹38,059 on all the others**. LIVE lost ₹57,042 / ₹31,943 on the others. TPB earned more evenly: +₹1,786 / +₹24,376 on the biggest days and +₹33,407 / +₹11,174 on the rest.

The books caught little of what was available: LIVE −3.3% / +8.8% of the hindsight ceiling, BEST +0.5% / +8.0%, TPB 3.6% / 3.7%.

## 8. What failed

At one lot, no brakes, 3 trades a day, +₹200:

| Book | 2025 | 2026 | Verdict |
| --- | ---: | ---: | --- |
| TPB (reference) | +₹10,125 | +₹19,642 | the only base positive in both years |
| BEST (reference) | −₹23,948 | +₹37,068 | |
| LIVE (reference) | −₹41,693 | +₹56,825 | |
| RETEST alone | −₹55,225 | −₹4,371 | fails |
| FAILCONF alone | −₹20,614 | −₹10,625 | fails, about zero before the extra cost |
| SQUEEZE alone | −₹71,704 | −₹53,732 | fails; no better than random |
| BEST + RETEST | −₹46,242 | +₹5,724 | worse than BEST |
| BEST + FAILCONF | −₹40,415 | +₹32,883 | worse than BEST |
| BEST + SQUEEZE | −₹68,325 | −₹10,348 | worse than BEST |
| BEST + all three | −₹97,392 | −₹29,388 | worse than BEST |
| LIVE, hold longer (RUN / HOLD) | −₹68,059 / −₹99,785 | +₹59,636 / +₹29,614 | worse in 2025 |
| LIVE + adds (ADD1 / ADD2) | −₹74,294 / −₹62,019 | +₹98,724 / +₹98,890 | bigger both ways |
| TPB + adds (ADD1 / ADD2) | +₹5,849 / +₹11,921 | +₹14,524 / +₹6,252 | fall roughly 1.3–2× |
| TPB, HOLD | +₹17,733 | +₹17,951 | about the same, one more bad half-year |
| The four as separate slots | −₹1,75,383 | −₹94,311 | more trades, far worse |
| Random books (median) | −₹64,714 | −₹46,052 | |

Trading more and holding longer did not help. Adding to winners made good years better and bad years worse: more risk, not more skill.

**Option selling, priced because you asked how others earn (information only; your rule forbids it).** The common retail form, one setting, per lot, no expiry days, 30% stop per leg, after ₹100 per leg per day:

| | 2025 | 2026 | Biggest fall | Worst day |
| --- | ---: | ---: | ---: | ---: |
| 09:20 short straddle | −₹15,955 | −₹52,689 | ₹33,487 / ₹81,249 | −₹8,495 / −₹12,158 |
| Same with wings 200 points away | −₹1,72,916 | −₹94,851 | ₹1,81,240 / ₹1,34,819 | −₹12,226 / −₹11,292 |

Before that extra cost the straddle was about +₹22,645 / −₹20,889. This one setting does not show that selling cannot work, and margin is not modelled. It does show that the popular version is not free money, so the evidence gives no reason to revisit your rule.

## 9. What worked: do not buy a stretched entry

**Where it came from.** The O30q review noticed that stretched entries lost more often on LIVE. In the frozen run, half size when stretched lifted every book. Then, looking closer:

| TPB, one lot, as replayed | 2025 Jan–Jun | 2025 Jul–Dec | 2026 Jan–May | 2026 Jun–Oct | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Stretched entries (40 trades) | −₹7,206 | −₹3,837 | −₹2,959 | −₹1,805 | **−₹15,807** |
| All other entries (163 trades) | +₹10,294 | +₹35,943 | +₹27,455 | +₹12,858 | **+₹86,550** |

**It is also true on random entries,** which is what makes it more than a curve-fit. Pooling 20 random books, 8,250 trades: stretched entries lost ₹282 per trade, the others ₹77 per trade, and stretched was worse in all four half-years. So it looks like a property of buying options after a run, not of one strategy.

**Exact replay, shipped size and brakes, per lot** (Tier 2 freeze `fd8e4c1`; the references reproduce exactly):

| Book | 2025 | 2026 | 2026 without Feb 1 | +₹200: 2025 / 2026 | Trades | Rupees at shipped size: 2025 / 2026 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| LIVE | +271 | +80,912 | +33,625 | −27,329 / +59,712 | 138 / 106 | −7,738 / +68,176 |
| **LIVE, passing over stretched** | **+27,769** | **+55,524** | +32,322 | **+8,369 / +42,324** | 97 / 66 | **+26,230 / +79,247** |
| BEST | +34,517 | +80,232 | +32,944 | −8,283 / +46,432 | 214 / 169 | +1,343 / +92,002 |
| **BEST, passing over stretched** | **+56,904** | **+51,885** | +28,683 | **+23,904 / +28,485** | 165 / 117 | +36,068 / +57,776 |
| TPB | +36,694 | +42,056 | +42,056 | +15,294 / +25,056 | 107 / 85 | +34,435 / +36,965 |
| **TPB, passing over stretched** | **+52,230** | **+45,652** | +45,652 | **+33,230 / +31,652** | 95 / 70 | **+82,124 / +45,796** |
| UNION (no trend gate) | +27,140 | −2,691 | −316 | −54,860 / −66,091 | 410 / 317 | +31,341 / +19,046 |
| UNION, passing over stretched | +36,312 | +54,227 | +31,001 | −25,888 / +8,027 | 311 / 231 | +32,174 / +83,812 |

By half-year (per lot): BEST with the rule is +42,793, +14,111, +36,139, +15,746, and TPB with the rule is +17,945, +34,285, +37,356, +8,296, all positive. LIVE with the rule is +28,380, −611, +32,222, +23,302.

**What the frozen verdict says, plainly.** Only TPB passes the strict test (better in both years). LIVE and BEST fail it because their 2026 falls, which is mostly one stretched entry on Budget day (+₹23,255 at 12:16). UNION improves in all four half-years but stays negative after +₹200 in 2025.

**What it really does.** For the four-strategy books it does **not** add much total money; it evens the years and makes them survive costs:

| Two years, per lot | Without | With | After +₹200, without | After +₹200, with | Trades, without → with |
| --- | ---: | ---: | ---: | ---: | ---: |
| LIVE | +81,183 | +83,293 | +32,383 | +50,693 | 244 → 163 |
| BEST | +1,14,749 | +1,08,789 | +38,149 | +52,389 | 383 → 282 |
| TPB | +78,750 | +97,882 | +40,350 | +64,882 | 192 → 165 |

**The limit is not knife-edge.** At 0.75 instead of 0.5: LIVE +24,691 / +47,409, BEST +53,620 / +49,050, TPB +54,935 / +37,984. At 0.25 it refuses too much and profits shrink: LIVE +14,550 / +10,400. These are shown, never chosen.

**Why it is not a loss-reaction block:** it reads the price at the moment of entry, never earlier results. A later bar can still enter at a better place.

## 10. The trade-off, with the rule in place

**TPB, passing over stretched, ₹2.5 lakh, no brakes.** Simulated. Exact replays came out within about 4% in 2025. They were higher in 2026 by about ₹31,000–55,000: one high-premium winner on Mar 13 that the larger account could afford (+₹24,772 at 3 lots), plus flat brokerage the simulator over-counts. So these are the lower figures.

| Lots | As replayed: 2025 / 2026 | +₹200: 2025 / 2026 | Fall, as replayed | Fall, +₹200 | Worst day | Worst month |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | +₹50,511 / +₹36,555 | +₹30,311 / +₹22,355 | 6% (₹19,515) | 9% (₹28,208) | −₹7,495 | −₹10,650 |
| 2 | +₹1,01,022 / +₹73,111 | +₹60,622 / +₹44,711 | 11% (₹39,030) | 15% (₹56,416) | −₹14,990 | −₹21,299 |
| 3 | +₹1,51,533 / +₹1,09,666 | +₹90,933 / +₹67,066 | 16% (₹58,545) | 19% (₹84,624) | −₹22,485 | −₹31,949 |
| 5 | +₹2,52,554 / +₹1,82,777 | +₹1,51,554 / +₹1,11,777 | 24% (₹97,575) | 29% (₹1,41,040) | −₹37,474 | −₹53,248 |
| 8 | +₹4,04,087 / +₹2,92,443 | +₹2,18,750 / +₹1,78,843 | 34% (₹1,56,120) | 43% (₹2,25,664) | −₹59,959 | −₹85,197 |

**A chance view: 5,000 one-year paths redrawn week by week from both years, as replayed / +₹200.** These come from the same years the rule was found on, so **treat them as the good case. The real chances of a fall are higher.**

| Lots | Typical year | A losing year | Falls 25% at some point | Falls 50% at some point | Reaches ₹2 lakh |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | ₹63,526 / ₹38,506 | 2% / 11% | 0% / 0% | 0% / 0% | 0% / 0% |
| 2 | ₹1,27,052 / ₹77,011 | 2% / 11% | 2% / 10% | 0% / 0% | 13% / 3% |
| 3 | ₹1,90,578 / ₹1,15,517 | 2% / 11% | 9% / 28% | 0% / 2% | 46% / 19% |
| 5 | ₹3,17,630 / ₹1,92,528 | 2% / 11% | 32% / 60% | 3% / 14% | 76% / 48% |
| 8 | ₹5,08,208 / ₹3,08,045 | 2% / 11% | 58% / 80% | 13% / 33% | 89% / 66% |

**The four strategies with the rule, at 3 lots, exact:** LIVE +₹78,726 / +₹1,72,197 (+₹200: +₹11,526 / +₹1,31,997), BEST +₹1,56,122 / +₹1,68,330 (+₹200: +₹45,722 / +₹96,330), with falls of 9–24% by year.

**In plain terms, if the 2024 exam holds up:**
- **2–3 lots** is the sensible range on ₹2.5 lakh. It would have made about ₹45,000–1,50,000 a year, with falls of about ₹40,000–85,000.
- **5 lots** is what ₹2 lakh a year costs: falls of ₹1–1.4 lakh and days of −₹37,000 or worse.
- **8 lots and up** is gambling on this edge.
- **The cleaner way to earn ₹2 lakh is more capital at the same risk**: about ₹5.5–7.5 lakh at the 3-lot share of risk, after the extra cost, once the system has earned it.

**At one lot with ₹12,500–15,000** (96 weeks replayed week by week, as replayed, ₹15,000 start): LIVE 14 up, 18 down, worst week ends ₹7,826. With the rule, 13 up, 18 down, worst ₹10,176. The rule changes the worst week more than the count. A week is mostly noise at this size.

## 11. What was decided

- **Production and the real-money test: unchanged.** Nov 2–6 stays one lot on the deployed rules unless the owner decides otherwise after the exam.
- **Lots are not raised anywhere.** Sizing up today's rules is not supported.
- **The stretched-entry rule is the one candidate.** It goes to the 2024 exam, and adding it to the book is the owner's call afterwards (Dev → PR → deploy).
- **RETEST, FAILCONF, SQUEEZE, holding longer, side-by-side slots and adds on the live book are closed.** They are not to be retried with tuned settings on these two years.
- **The O30s frozen pick is recorded as frozen,** but plain TPB with the rule is simpler and did better, so that is the better next candidate.

## 12. The 2024 exam and what comes next

1. **Owner:** ICICI login on Oct 31 (the download needs it).
2. **Other agent:** NIFTY 2024 download, before the SENSEX remainder, then the negative-volume re-check.
3. **Sheet 1 (unchanged, scored first):** `2026-10-30-day-router/analyze_f.py`.
4. **Sheet 2 (this study, frozen at `ff08fca` before any 2024 data exists):** `exam_s.py run` in both modes, then `exam_s.py score`, once. Its rule:
   - the stretched rule holds if it beats the book on at least 2 of LIVE, BEST and TPB, and lifts the random median;
   - each sized candidate must be positive at 3 lots after +₹200 and fall no more than 25%.
5. **Then the owner decides:** whether to add the rule to the paper book, and from there the real test.
6. **Forward:** panels A–D run to Nov 27. Real fills from Nov 2 will show whether ₹200 is too much or too little, which matters more than any other assumption here.

## 13. Limits

- **Both years are seen.** The stretched rule was found by looking at them. Only 2024 and forward days are clean.
- **Number of tries.** 38 books, 136 settings, one follow-up rule with two sensitivity limits. Luck is a real explanation for any single row. Passing also on random entries is what reduces that worry.
- **Minute candles, not quotes.** The bid and ask are modelled from a spread table, and bigger sizes will pay more. Up to about 10 lots of ATM NIFTY should fill, but that is not measured. No real-fill data exists yet.
- **Fixed 65 lot** for every year, and today's charges (a higher STT than 2025 actually had).
- **Falls are measured on closed trades,** so the moment-to-moment fall is somewhat bigger. The chance table ignores brakes and cash limits.
- **Sizes above 1 lot in the simulator ignore the shipped minimum-pool gate** (premium × 65 × 25% ≤ 2% of the money). In exact replays it refused or admitted a few high-premium trades. It explains the 2026 gaps in section 10, and the big-day example would have been larger without it.
- **Data quality is unresolved.** The sealed 2025 data has 2 negative-volume future rows and 54 option rows (O30p). VWAP uses future volume, so the stretched reading touches this, slightly. Re-check after the re-download.
- **Regimes.** Two years are not many. 2025 rose slowly and 2026 mostly fell. 2024 adds a third kind of year, not certainty.

## 14. How another agent repeats or extends this

All of it is in `docs/research/fno/2026-10-30-earning-power/`. Use `python-engine\winvenv\Scripts\python.exe`, never a bare `python`.

```
python lab_s.py freeze                                    # new studies: your own folder and freeze
python ../run_slice.py --env O30C_YEAR=2025 -- <folder>/lab_s.py run --jobs 3      # repeat until DONE, then 2026
python analyze_s.py                                       # the frozen grid and verdict -> results.json
python reference_s.py                                     # hindsight ceiling and selling -> reference.json
python report_s.py                                        # descriptive views -> report.json
python ../run_slice.py --env O30C_YEAR=2025 --env O30S2_MODE=shipped -- <folder>/lab_s2.py run --jobs 3   # Tier 2
python analyze_s2.py
O30C_YEAR=2025 python exact_s.py --name TPB --lots 3 --skip                        # exact replay at real size
```

**The idea to reuse:** replay a book once as **RAW** (one lot, brakes off, 6 trades a day), then size it many ways in `analyze_s.sim(rows, rule, brakes, stress, half, capital, day_cap, reserve)`. It takes milliseconds per combination. `rule` is `("fixed", lots)`, `("risk", share)` or `("shipped",)`, which reproduces the shipped sizing.

**To size your own strategy:** add its book to a copy of `lab_s.books()`, freeze, run, and call `sim`. Add a size rule by extending `sim`. Add an entry rule as in `FNO_YEAR_DATA_TESTING_METHOD.md` section 7.

**Rules learned here:**
- Always test the size on the random books as well.
- Always replay exactly what you would act on. A combination that passes only in the simulator and depends on brakes is not a result.
- Show every result with and without the extra cost.
- Check every headline for one-day dependence (`without_budget_day`).
- Never choose size from one year.

The full method, ledger and pitfalls are in [FNO_YEAR_DATA_TESTING_METHOD.md](FNO_YEAR_DATA_TESTING_METHOD.md), section 15.

## 15. Files

| File | What |
| --- | --- |
| `lab_s.py`, `freeze.json` | Books, RAW settings, adds, entries; freeze `045351b` |
| `analyze_s.py`, `results.json` | The simulator, grid, frozen verdict, cross-year, trade-off, bootstrap, Kelly |
| `_local/all-combos.json` | All 5,168 rows (ignored by Git) |
| `report_s.py`, `report.json` | Money in use, plans, stretched split, biggest days (written after seeing results) |
| `reference_s.py`, `reference.json` | Hindsight ceiling and option selling |
| `lab_s2.py`, `analyze_s2.py`, `freeze-t2.json`, `results-t2.json`, `report_s2.py`, `report-t2.json` | Tier 2, the stretched rule, freeze `fd8e4c1` |
| `exact_s.py`, `exact.json` | Exact replays at real size |
| `exam_s.py`, `freeze-2024.json` | Sheet 2 for the 2024 exam, frozen `ff08fca` |
| `test_lab_s.py`, `test_lab_s2.py`, `test_exam_s.py` | 25 tests |
| `README.md` | Technical summary |

## Sources

- SEBI study coverage: [Business Standard, FY25](https://www.business-standard.com/markets/news/net-losses-of-traders-in-fo-widens-in-fy25-sebi-study-125070701221_1.html); [Value Research](https://www.valueresearchonline.com/stories/225398/average-trader-lost-rs-1-1-lakh-fo-fy25/); [Finnovate, FY26](https://www.finnovate.in/learn/blog/sebi-fno-trader-losses-fy26-individual-derivatives); [Taxmann, FY22–24](https://www.taxmann.com/post/blog/93-of-1-crore-fo-traders-saw-rs-2l-avg-loss-while-top-3-5-faced-rs-28l-avg-loss-incl-costs-sebi/); [Fortune India](https://fortuneindia-web.quintype.io/investing/9-out-of-10-individual-traders-faced-losses-in-equity-fo-in-fy22-fy24/118513); [TaxGuru](https://taxguru.in/sebi/sebi-study-shows-93-percent-individual-fo-traders-incur-losses.html). These are secondary reports of SEBI's releases.
- Intraday momentum: [Zarattini, Aziz and Barbon](https://concretumgroup.com/beat-the-market-an-effective-intraday-momentum-strategy-for-sp500-etf-spy/); [Gao, Han, Li and Zhou, Market intraday momentum](https://econpapers.repec.org/RePEc:eee:jfinec:v:129:y:2018:i:2:p:394-414).
- Size: [MacLean, Thorp and Ziemba, Good and bad properties of Kelly](https://www.stat.berkeley.edu/~aldous/157/Papers/Good_Bad_Kelly.pdf); [Moreira and Muir, Volatility-managed portfolios](https://www.nber.org/papers/22208).
- Budget day: [Business Today](https://www.businesstoday.in/union-budget/story/budget-2026-stock-market-sensex-nifty-plunge-2-after-stt-hike-on-fo-trades-513924-2026-02-01); [Outlook India](https://www.outlookindia.com/national/budget-2026-higher-stt-no-fpi-boost-drag-markets).
- The three entries came from the O30q review's own sources: [`2026-10-30-loss-day-review/SOURCES.md`](research/fno/2026-10-30-loss-day-review/SOURCES.md).
