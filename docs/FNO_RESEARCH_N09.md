# N09: what the auditor's ideas and mine did against N08

**November 1, 2026. Research only.** Nothing in the trading system changed, and Production was not touched.

**No new entry, exit, option choice or added strategy beat N08. The biggest finding is about the account: one account started in January 2023 ends at ₹2,12,419 as N08 stands, because the 15% stop never lifts, and at ₹4,36,635 with a restart.** That restart also has a real downside if bad years repeat. All of this is on years already seen, so none of it is proven.

Technical summary: [research/simulation/2026-11-01-fno-n09/README.md](research/simulation/2026-11-01-fno-n09/README.md).

## 1. Why N08 loses

N08 at one lot with brakes off, 243 trades over four years, so size and the stop can't hide anything:

| Why the trade lost | Trades | Net |
|---|---:|---:|
| Wrong direction | 73 | −₹1,22,737 |
| Moved half a stop's worth, then failed | 42 | −₹50,231 |
| Direction right, but the option didn't pay | 16 | −₹8,624 |
| Made money before costs, not after | 13 | −₹2,026 |

Most of the loss is wrong direction, and nothing tested predicts direction. Of 30 readings known at entry, none survives a fair check for how many were tried. Readings of entry quality show nothing at all.

## 2. What was tested

Each was fixed in writing before it was scored.

| Idea | Whose | One lot, four years (N08: +₹1,17,877) | Result |
|---|---|---:|---|
| Wait one bar for confirmation | Auditor | +₹49,318 | Fails. Missed ₹1,48,895 of winners to avoid ₹1,13,921 of losers |
| Exit when the trade's structure weakens | Auditor | +₹1,17,814 | Fails. Almost no effect |
| Choose a stronger strike, delta 0.65 | Mine | +₹82,083 | Fails |
| Choose a stronger strike, delta 0.75 | Mine | +₹53,331 | Fails |
| Add noise-area momentum, a published strategy | Mine | −₹32,262 | Fails. Worse than N08 even before the assumed extra cost, and it trades so often that the cost takes the rest |
| 50 older strategies, tested on 2023 for the first time | Mine | | None qualifies. 48 of the 50 lost in 2023 |

**So 2023 was hard for everything tried here,** not only N08.

## 3. What did help

**Sizing by volatility.** Two lots only when yesterday's daily range is at or above its usual level of the past year, one lot otherwise. It never refuses a trade.

| Fresh ₹2.5 lakh each year | N08 | Size by volatility |
|---|---:|---:|
| Four-year total | +₹2,02,284 | +₹1,91,428 |
| Worst day | −₹9,720 | −₹6,127 |
| 2023 with brakes off | −₹58,321 | −₹29,407 |
| Four-year total with brakes off | +₹1,66,918 | +₹1,85,790 |
| Four-year total at double the assumed cost | +₹1,63,688 | +₹1,43,250 |

It gives up about 5% of the profit for a worst day about a third smaller. In 2023 it took one lot almost all year, so it lost half as much with brakes off.

**Restarting after the 15% stop.** Today the stop is permanent. One account from January 2023:

| How it restarts | N08 | Size by volatility |
|---|---:|---:|
| Never | ₹2,12,419 | ₹2,12,026 |
| Next calendar year | ₹4,41,234 | ₹4,18,765 |
| When the last 20 paper trades made money | ₹4,36,635 | ₹4,10,542 |

## 4. The results by the rules written in advance

| Candidate | Result |
|---|---|
| **N09A:** N08 without the morning two-lot rule, which is what the first rule produced | **Fails.** +₹1,58,946 against +₹2,02,284 |
| **N09B:** N08's trades, size by volatility, restart on paper evidence | **Narrowly fails.** Ends at ₹4,10,542 and needed ₹4,14,803; its largest fall is 15.24% against 15.08%. Its worst day is better |
| **Restart on N08** | **Passes its three checks,** though those checks turned out to be weak (section 5) |

N09A and N09B stay on record as failed. N09B is a close call, and it is the lower-risk way to run the same trades.

## 5. The risk in a restart

A restart can lose again. The first check, which shuffles single months, broke up bad stretches and hardly ever used the restart, so it says little. A harder test added afterwards keeps each year whole and tries all 256 orderings at one lot:

| Years in order | Never restart | Restart on paper evidence |
|---|---:|---:|
| 2023, 2024, 2025, 2026 | ₹2,12,136 | ₹3,63,270 |
| 2023 twice, then 2024, 2025 | ₹2,12,136 | ₹2,66,458 |
| 2023 three times, then 2024 | ₹2,12,136 | ₹1,93,390 |
| 2023 four times | ₹2,12,136 | ₹1,28,558 |

Across all 256 it helped in 55, hurt in 11 and changed nothing in 190. **Waiting for paper evidence protected little** compared with simply restarting the next year. The largest cost was ₹83,578, and the largest gain ₹1,89,591.

## 6. Is N08 overfit?

A standard estimate (Bailey and colleagues) checks how often the best book on half the data does badly on the other half. N08's family scores **0.487**. Random books score about 0.53 on average. **So picking the best among N08's close variants can't be told apart from picking at random,** which fits what 2023 showed. This doesn't say the whole family has no edge: in 2024-26 it beat random entries by about ₹1,00,000 or more a year, on seen data.

## 7. Where this agrees and disagrees with the auditor

**Agreed:** keep N08 fixed, compare at equal size first, size last, measure the account and the stop, remove the morning two-lot rule from anything new, and keep unseen history closed.

**Disagreed, with evidence:**

- **No controller that switches strategies by market state.** Four have failed here on these same years. A fifth adds overfitting.
- **Fixing the cut data isn't a first step.** It touches one N08 trade, +₹1,059. It is still worth doing on the owner's word.
- **Entry quality isn't the strongest weakness.** It was the auditor's first choice, and it did worst of the auditor's two challengers.
- **The option layer is small:** ₹10,650 of ₹1,83,618 lost.

The auditor's warning about repeated searching is right, and this study is more evidence for it.

## 8. Errors in this study, disclosed

- **The noise-area test first left the house profit lock on,** which the plan said it wouldn't. Rerun as the plan describes; it still fails.
- **The first overfitting score, 0.031, was wrong.** Cost-stress runs that aren't strategies were counted. Corrected to 0.487.
- **A broken commit before the freeze,** fixed before anything was scored.

Details: [SOURCE_CORRECTION.md](research/simulation/2026-11-01-fno-n09/SOURCE_CORRECTION.md).

## 9. What is left

- **NIFTY 2022,** the only unseen history. It is the one fair test for size by volatility and the restart. It needs the owner's ICICI login, and only Dec 2022 is confirmed available.
- **A forward shadow of N08 and N09B,** because history is used up. Not built.
- **Real fills from the real-money test,** to replace the assumed extra cost.
- **Any change to the live 15% stop is the owner's decision.** If it is ever changed, the floor also has to rise with profit, which this test's version doesn't do.

This doesn't change the Nov 2 real-money test, which stays at one lot.
