# N08: built on three years, tested on 2023, and it failed that test

**November 1, 2026. Research only.** Nothing in the trading system changed, and Production was not touched.

**N08 earned the most over four years, and did it with a smaller worst trade. But it lost money in 2023, the one year it had never seen, and there it was no better than N07. So by the rule fixed in advance it is not the new lead.** The bigger finding is about all of these strategies: in 2023 they had no visible edge, and did little better than random entries.

Technical summary: [research/simulation/2026-11-01-fno-n08/README.md](research/simulation/2026-11-01-fno-n08/README.md).

## 1. The result

Fresh ₹2.5 lakh each year, today's brakes, costs and assumed extra costs included. 2026 runs to Oct 28.

| | 2023 (the test) | 2024 | 2025 | 2026 | Four years |
|---|---:|---:|---:|---:|---:|
| N03 | −₹37,802 | +₹56,192 | +₹50,090 | +₹54,153 | +₹1,22,633 |
| N04 | −₹38,195 | +₹51,303 | +₹54,051 | +₹77,135 | +₹1,44,294 |
| N05 | −₹37,726 | +₹57,243 | +₹50,726 | +₹61,496 | +₹1,31,739 |
| N07 | −₹37,719 | +₹57,982 | +₹52,023 | +₹77,135 | +₹1,49,421 |
| **N08** | **−₹37,581** | **+₹76,294** | **+₹58,647** | **+₹1,04,924** | **+₹2,02,284** |

- **All of them stop near −₹37,500 in 2023 because of the 15% brake,** which halts trading at ₹2,12,500. With brakes off, N07 lost ₹60,167 and N08 lost ₹58,321.
- **N08's biggest fall by year:** 15.08%, 2.16%, 4.70%, 2.69%.
- **N08's worst trade is smaller:** −₹5,107 against N07's −₹6,910. Its worst day is ₹238 larger: −₹9,720 against −₹9,482.

**The rule fixed before 2023 was opened:**

| Check | Result |
|---|---|
| 2023 net above zero | **Failed** |
| 2023 at least as good as N07 | Passed, by ₹138 |
| 2023's fall no larger than N07's | Passed |
| Positive every year | **Failed** |
| Four-year total above N03, N04, N05, N07 | Passed |

## 2. What N08 is

N07 with four changes, each from a weakness found on 2024-26:

| Change | Weakness it answers | Alone on 2024-26, against N07 |
|---|---:|---:|
| EFF and OR20 trail at 2 ATR, as TPB already does | Winners were sold too soon | +₹20,369 |
| A low-day TPB before 12:00 may take 2 lots | The first low-day pullback earned far more than later ones | +₹39,984 |
| No low-day TPB from 14:00 | Too little time left for a trade that earns by being held to the close | +₹1,801, smaller falls |
| Nothing above 2 lots | The largest losses were all 3-lot trades | −₹16,206, smaller worst trade |

Together on 2024-26: +₹52,724 against N07. On 2023: +₹138. **So the improvement didn't carry to the unseen year.** The morning low-day edge failed outright there: 15 trades, 3 wins, −₹16,316.

## 3. What the other agent wanted to look at

- **Keeping profits from winners that turned to losers:** a small prize. 66 of the 85 losers never reached half a stop's worth of gain, and they lost ₹1,25,199. The 19 that did lost ₹19,899. "51 of 86 losers were once profitable" is mostly tiny gains. Locks made almost nothing; the best added ₹4,214 and was worse in 2025.
- **Event days:** 7 trades in three years, +₹4,078. There's nothing to act on, so no rule was added.
- **Cost model affecting exits:** N07's rule doesn't depend on the assumed extra cost. It behaves the same with or without it. N04's does.
- **Fresh shadow comparison and real costs:** not done. They need sessions that haven't happened yet, and real fills.

**Other things tried, all worse than N07:**

| Tried | Against N07 |
|---|---:|
| Cutting stalled TPB trades at half their clock | −₹46,065 |
| Adding lots to winners | −₹12,549 |
| Low-day trades with the daily trend, calls too | −₹83,700 |
| Skipping low-day puts in a daily uptrend | −₹47,545 |
| Closing at 15:00, 15:15, 15:20 or 15:25 instead of 15:10 | −₹17,545 to −₹26,868 |

## 4. Why 2023 failed

| Year | NIFTY | Typical daily range | N07 win rate, brakes off | N07 net, brakes off | Random entries (median of 20) |
|---|---:|---:|---:|---:|---:|
| 2023 | +19.4% | 0.71% | 23% | −₹60,167 | −₹67,534 |
| 2024 | +9.0% | 0.85% | 50% | +₹52,153 | −₹57,820 |
| 2025 | +10.1% | 0.80% | 47% | +₹43,303 | −₹81,353 |
| 2026 | −13.2% | 1.06% | 50% | +₹59,899 | −₹40,059 |

- **The entries had no visible edge in 2023.** N07 beat random entries by ₹7,367, against about ₹1,00,000 or more in the other three years. Random books run at one lot and N07 at its own sizes, so this is a rough yardstick. Only 29% of N07's trades were positive even before costs.
- **It wasn't only the put bias.** Calls in the main book lost as well.
- **Smaller daily moves made costs weigh more,** but that isn't the whole story.
- **A simple volatility rule wouldn't have fixed it.** On the same low-volatility readings, N07 lost ₹33,439 in 2023 and made ₹15,295 in 2025.

**So the honest reading of "consistent":** three good years with falls under 6%, and one bad year stopped by the brake at about 15%. Good years were far larger than the bad one, but nothing here says which kind of year comes next, or that 2024-26's edge will last.

## 5. What this means for real money

- **The brake works, and it stops for good.** It held the 2023 loss near 15% instead of 28%, but it is a fixed floor at ₹2,12,500. One account started in January 2023 would have stopped trading in 2023 and missed all of 2024-26 until someone reset it.
- **A 2023-style start at one lot reaches the floor fast.** From ₹15,000, N07 at one lot fell below the ₹7,000 floor on Feb 13, 2023, after 10 trades. From ₹12,500, on Feb 6, after 8 trades.
- **The put-based switch is off.** The O31e exam's rule says the main book stays, because neither put-based candidate held. The main book itself also lost 15% in 2023.

## 6. An error in this study, disclosed

The first 2023 run read 2024's daily bars because of a wiring fault of mine, so the trend gate had no reading before Mar 31, 2023. My wiring test had also passed falsely, on saved results. I caught it because the first scores looked wrong, kept those scores on record, fixed the wiring, proved the fix on 2025 by a real replay, and reran with the same books and rule.

So 2023 was opened twice, not once. No book or rule changed in between. Details: [SOURCE_CORRECTION.md](research/simulation/2026-11-01-fno-n08/SOURCE_CORRECTION.md).

## 7. What is left

- **Forward shadow of N04, N05, N07 and N08,** because 2024-26 and 2023 are now all seen.
- **Real fills from the real-money test,** to replace the assumed extra cost.
- **NIFTY 2022,** if a next rule needs an unseen year. The probe shows ICICI serves Dec 2022; earlier months aren't probed.
- **A way to recognise a 2023-type stretch early,** which nothing tested here does.
- **`repair-ceiling`** (52 requests, the owner's word): the 2024-26 replays used the cut data. 2023 has none.
- **N08 in the engine,** only if the owner chooses it. The two low-day rules have no engine switch yet.
