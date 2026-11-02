# N11: better than all five on the years we have, and how far to trust it

**November 2, 2026. Research only.** Nothing in the trading system changed, and Production was not touched. The real-money test stays at one lot.

**N11 earned more than N08, N09, N09.1, N10 and N10.1, with a smaller worst day and about half the fall. All 12 of the checks I set for it pass.** But three things limit how far to trust it:

- **Its lead over N10 retry is entirely 2023.** In 2024-26 the two are level: ₹2,66,902 against ₹2,66,174.
- **The rule that saves 2023 has only that one year behind it.** Hide 2023 and I wouldn't have chosen it.
- **One overfitting check I set in advance failed.**

All four years were studied before and during its design, so none of this is proven. Technical summary: [research/simulation/2026-11-02-fno-n11/README.md](research/simulation/2026-11-02-fno-n11/README.md).

## 1. The results

Fresh ₹2.5 lakh each year, four years, costs included:

| | N08 | N09 | N09.1 | N10 retry | N10.1 | **N11** |
|---|---:|---:|---:|---:|---:|---:|
| 2023 | −₹37,581 | −₹37,974 | −₹32,684 | −₹32,898 | −₹32,898 | **−₹11,537** |
| 2024 | +₹76,294 | +₹70,317 | +₹76,294 | +₹88,805 | +₹88,805 | **+₹93,256** |
| 2025 | +₹58,647 | +₹50,442 | +₹46,738 | +₹51,583 | +₹51,583 | **+₹53,095** |
| 2026 (to Oct 28) | +₹1,04,924 | +₹1,08,643 | +₹99,870 | +₹1,25,786 | +₹1,25,786 | **+₹1,20,551** |
| **Four years** | **+₹2,02,284** | **+₹1,91,428** | **+₹1,90,218** | **+₹2,33,275** | **+₹2,33,275** | **+₹2,55,365** |
| Worst day | −₹9,720 | −₹6,127 | −₹6,127 | −₹6,127 | −₹6,127 | **−₹5,641** |
| Biggest fall in a year | 15.08% | 15.24% | 13.13% | 13.21% | 13.21% | **6.89%** |
| At double the assumed cost | +₹1,63,688 | +₹1,43,250 | +₹1,52,165 | +₹1,68,672 | +₹1,65,934 | **+₹1,99,622** |
| One account from Jan 2023 | ₹2,12,419 | ₹2,12,026 | ₹3,84,310, or about ₹2.17 lakh | ₹4,27,440 | ₹4,27,452 | **₹5,18,305** |

The N10.1 column is its WATCH_FLAT version. N11 isn't best in every year: N10 retry earns ₹5,235 more in 2026, and N08 earns ₹5,552 more in 2025.

## 2. What N11 is

N08's entries and exits stay exactly as they were. Four rules go on top:

**Stand aside when both readings say no.** Real trades wait while yesterday's volatility is clearly below its usual level (under 0.9 of it) **and** the last 20 paper trades together made nothing or lost. The paper book keeps trading, so this ends by itself as soon as either reading turns. It held back 54 paper trades in four years: 52 in 2023 and 2 in 2025.

**One lot after a loss.** After a losing trade today, the next trade today takes one lot. It never refuses a trade. It adds ₹1,236, and takes the worst day from −₹6,127 to −₹5,641.

**Two lots only when volatility is at or above usual.** This is N09.1's rule, unchanged. It costs ₹4,357 over four years, and it is why the worst day isn't −₹9,720.

**An honest third lot.** It may be added to a two-lot trade past +1R (a gain equal to the amount risked), at the first moment when the whole planned loss fits inside your ₹5,000: what the held lots are expected to lose at their current stop, plus everything the new lot could lose at its stop. **The held lots' stops are never touched.**

That last rule fixes both of N10's weaknesses. The retry N10's plan never stated is now the written rule, and the risk N10.1 found understated is now fully charged. It earned ₹2,55,365 against the unproven version's ₹2,54,621. N10.1 lost money here because it tightened the original trade's stop. This version doesn't.

**What came out:** the reserve and the floor that steps down. With the stand-aside doing the bad-year work, the same book earned more and fell less without them. So **your live 15% stop wouldn't need to change.**

## 3. What each rule earned

| Rule | 2023 | 2024 | 2025 | 2026 | Four years |
|---|---:|---:|---:|---:|---:|
| Stand-aside | +₹26,253 | 0 | −₹4,359 | 0 | +₹21,894 |
| Third lot | +₹415 | +₹16,962 | +₹4,495 | +₹15,627 | +₹37,499 |
| One lot after a loss | 0 | 0 | +₹1,236 | 0 | +₹1,236 |
| Two lots by volatility | +₹5,842 | 0 | −₹10,199 | 0 | −₹4,357 |

The numbers are what N11 gains from having each rule.

## 4. The account has no hidden trap

N09.1's one-account figure turned on ₹18.45. So I reran N11's account at ten different cost levels:

| Assumed extra cost per lot | ₹195 | ₹199 | ₹200 | ₹202 | ₹205 | ₹400 |
|---|---:|---:|---:|---:|---:|---:|
| N10 retry | ₹4.72L | ₹4.28L | ₹4.27L | ₹4.27L | ₹4.70L | ₹4.10L |
| **N11** | ₹5.19L | ₹5.19L | ₹5.18L | ₹5.18L | ₹5.17L | ₹4.45L |

It moves 0.42% across the rupee-sized changes. Its lowest point is ₹2,32,908, well above the ₹2,12,500 stop. Nearby settings hold as well: all six earn between ₹2,52,950 and ₹2,59,428, with the same worst day.

## 5. Is it overfit? Partly, and here is where

**The third lot looks the sturdiest.** Hide any one year and I would still have chosen it, and it made money in every hidden year. It has no edge of its own, though: on random entries it hurts in every year. It is only as good as the trades it follows.

**The stand-aside is insurance, and one claim doesn't prove insurance.**

- Hide 2023 and I wouldn't have chosen it: it costs ₹4,359 across the other three years.
- Outside 2023, a losing paper record doesn't predict more losses. The next 20 trades still averaged +₹8,917, against +₹16,711 after a winning record.
- On 50 other strategies it picks out worse trades only in 2023.
- Skipping the same number of trades at random beats it 0.27% of the time. Moving its waiting periods to other dates beats it 7.4% of the time. That passes my line of 10%, but not by a wide margin.
- It sits close to a cliff. Raise the volatility line from 0.9 to 1.05 and 2024 loses about ₹33,000, because the rule misses the start of that year. A future recovery could start below the line. I chose 0.9 as the middle of the range that holds, not its best point.
- Its strongest test, 256 orderings of whole years, reuses 2023. So the worst ending of ₹2,43,462 says less than it seems to.

**Outside research points the same way.** A published study (Gao and colleagues, 2018) supports the volatility half: intraday momentum is stronger on more volatile days. For pausing on your own results I found no solid study, and practitioners describe it as cutting risk, not adding edge.

**The check that failed.** I set a limit of 0.5 on the overfitting estimate within N11's own close variants. It came out at **0.893**. Shuffling the weeks gives the same figure, so the cause is that these variants earn almost the same, not time order. It stays failed either way, and it means history can't say which variant is best. So treat them as one book, and don't tune further. Across all 159 books since N08 the estimate is 0.313, where pure chance averages about 0.53.

**Against N10 retry, week by week,** the gain could still be zero: the likely range runs from −₹5,540 to +₹53,656. Against N08 it stays above zero: +₹3,781 to +₹91,433.

## 6. What failed along the way

- **My biggest hope.** Second lots on expensive options looked worth +₹57,700 in a rough sum. Exact replay gave about +₹2,700, so I dropped it. Rough sums only choose what to test.
- **A second lot on a good paper record:** worst day −₹7,185 or worse.
- **Skipping very tight stops:** −₹10,112 in 2026.
- **An earned lot on one-lot trades:** −₹19,210.
- **Adding only once the trail has locked:** −₹7,479 against the honest rule.

In all, 79 books were tried, and every one is kept and counted.

## 7. Two things that are your decision

**The stand-aside holds real trades back after poor results.** You have rejected rules that stop or ban after a loss. This one isn't triggered by any one loss, and it ends by itself, but it is close to that line. So I would keep it on paper until you have decided.

**The 15% stop is a fixed ₹2,12,500.** N11 relies on it and on nothing stronger. It protects less as an account grows: at ₹5 lakh it is more than 50% away. N09.1's reserve is gone too, so a stop that fails has nothing behind it. No stop in these years failed that way.

## 8. What is left

- **NIFTY 2022, the fair test.** [The sheet](research/simulation/2026-11-02-fno-n11/EXAM_2022_N11.md) is written before the data exists. It needs your ICICI login. 2022 was more volatile than 2023, so the stand-aside may barely fire, and the sheet then says "not tested", not "passed".
- **A forward paper shadow of N08, N10 retry and N11,** on market days nobody has seen. It isn't built, and you would register the scheduled task. It also gives N11 the paper record its stand-aside needs.
- **No more rounds on these four years.** N11 improves on them, and more searching would only make the results less trustworthy.

Errors and judgement calls: [SOURCE_CORRECTION.md](research/simulation/2026-11-02-fno-n11/SOURCE_CORRECTION.md). Outside sources: [SOURCES.md](research/simulation/2026-11-02-fno-n11/SOURCES.md).
