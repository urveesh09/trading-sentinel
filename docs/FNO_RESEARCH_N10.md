# N10: better than N09.1, and how far to trust it

**November 2, 2026. Research only.** Nothing in the trading system changed, and Production was not touched. Today's real-money test isn't affected: it stays at one lot.

**N10 is better than N09.1, and the largest gain is a fix to a hidden trap in N09.1's account. Whether N10 also earns more than N08 depends on one rule I can't call proven: with it ₹2,33,275, without it ₹1,98,484, against N08's ₹2,02,284.** All of this is on years already studied.

Technical summary: [research/simulation/2026-11-01-fno-n10/README.md](research/simulation/2026-11-01-fno-n10/README.md).

## 1. The results

Fresh ₹2.5 lakh each year, four years:

| | N08 | N09.1 | N10, strict | N10, with retry |
|---|---:|---:|---:|---:|
| 2023 | −₹37,581 | −₹32,684 | −₹32,898 | −₹32,898 |
| 2024 | +₹76,294 | +₹76,294 | +₹79,334 | +₹88,805 |
| 2025 | +₹58,647 | +₹46,738 | +₹46,738 | +₹51,583 |
| 2026 (to Oct 28) | +₹1,04,924 | +₹99,870 | +₹1,05,311 | +₹1,25,786 |
| **Four years** | **+₹2,02,284** | **+₹1,90,218** | **+₹1,98,484** | **+₹2,33,275** |
| Worst day | −₹9,720 | −₹6,127 | −₹6,127 | −₹6,127 |
| Biggest fall in a year | 15.08% | 13.13% | 13.21% | 13.21% |
| At double the assumed cost | +₹1,63,688 | +₹1,52,165 | +₹1,61,990 | +₹1,68,672 |
| One account from Jan 2023 | ₹2,12,419 | ₹3,84,310, or about ₹2.17 lakh: section 2 | ₹4,18,151 | ₹4,27,440 |

N10 is N09.1 plus two things: a way for the account to come back (section 3) and a third lot earned on trades that are already working (section 4).

## 2. The hidden trap in N09.1

N09.1 reserves the whole premium above a floor that never comes down. So when the account gets near the floor, it can't pay for any lot. With no trades, nothing can change, and it stays there for good.

At the end of 2023, N09.1 had about ₹4,688 above its floor. On January 1, 2024:

- At 12:36 an option needed ₹4,731.54. Refused.
- At 12:37 the same option was 95 paise cheaper and needed ₹4,669.65. Taken, with **₹18.45** to spare.
- That trade won about ₹3,900, which freed the account.

Another book, with almost the same 2023, missed that trade by **67 paise**. It sat at ₹2.16 lakh for the next three years.

Then I moved the assumed cost per lot by a rupee or two, and ran the same N09.1 again:

| Assumed extra cost per lot | ₹195 | ₹198 | ₹199 | ₹200 | ₹201 | ₹202 | ₹205 |
|---|---:|---:|---:|---:|---:|---:|---:|
| N09.1, one account ends at | ₹4.21L | ₹3.85L | **₹2.17L** | ₹3.84L | ₹3.84L | **₹2.17L** | ₹4.51L |
| N10, one account ends at | ₹4.72L | ₹4.49L | ₹4.28L | ₹4.27L | ₹4.27L | ₹4.27L | ₹4.70L |

**So N09.1's ₹3,84,310 isn't a reliable number.** Its result swings between ₹2.17 lakh and ₹4.51 lakh on rupee-sized changes. In a bad year the book spends its free cash until nothing fits, so a floor that never lowers is a permanent stop that arrives a little earlier. Whether it escapes comes down to luck.

## 3. The fix: the account can come back, in small steps

I call this WATCH. When no lot can be paid for, the account stands aside and keeps following its own rules on paper. The floor may come down by one small step only if:

- its last 20 paper trades together made money;
- at least 20 paper trades have closed since the last step;
- the floor stays at or above **75% of the account's best level**.

One step is 5% of the best level. At ₹2.5 lakh: ₹2,12,500, then ₹2,00,000, then ₹1,87,500, and no lower.

N09's restart gave a fresh 15% each time. WATCH has a fixed bottom. Across all 256 orderings of whole years, at one lot:

| How the account behaves after a bad run | Worst ending | Typical ending | Endings below the start |
|---|---:|---:|---:|
| Stops for good at 15% | ₹2,11,290 | ₹3,67,877 | 67 |
| N09.1's floor | ₹2,15,291 | ₹3,42,954 | 50 |
| **WATCH** | **₹1,90,822** | **₹3,62,226** | **13** |
| Restart on paper evidence | ₹1,30,136 | ₹3,67,877 | |

**WATCH has a real cost.** If bad years keep coming, it ends about ₹25,000 lower than never coming back: 2023 repeated four times ends at ₹1,91,836 against ₹2,16,393 with N09.1's floor. That is the price of not being stuck when things recover.

## 4. The third lot, and the part I can't call clean

**My first idea failed.** I expected earning the second lot at +1R (a gain equal to the amount risked) to beat buying it at entry. It earned ₹1,51,406, well below N08. Most of the money is in the first move, and waiting gives that up. Adding at +1R also hurt random entries in every year, so a move that has started doesn't tend to continue by itself. Round one failed all its books, and that stays on record.

**What survived.** An earned lot on top of a trade that already holds two lots, with planned risk never above your ₹5,000. Those lots made money; on one-lot trades they lost.

**The catch.** My plan said the lot is earned when the trade "first reaches" +1R, which means one try. My code kept trying while the trade stayed above +1R, if the first try was refused.

| | One try (the plan's words) | Keeps trying (the code) |
|---|---:|---:|
| Earned lots, and what they made | 7, +₹7,043 | 15, +₹30,440 |
| Four years | +₹1,98,484 | +₹2,33,275 |
| Above N08's ₹2,02,284? | **No, by ₹3,800** | Yes |

The retry makes sense: it mostly adds once the first lots can't lose any more. But I only learned it mattered after seeing the numbers. In N09 I held myself to the written plan, so I hold myself to it here. **Read as written, N10 fails its first check by ₹3,800.** The retry is now a stated rule, and it has to prove itself on data nobody has seen.

## 5. What I can and can't say

**Can say, on these years:**
- N10 beats N09.1 in both readings, with the same worst day, a better double-cost result and a far sturdier account. It is ₹214 worse in 2023, and its biggest fall is 0.08 of a point larger.
- N10 beats N08 on worst day, worst trade, biggest yearly fall, the 2023 loss and the account. It earns less than N08 in 2025, and its 2025 fall is slightly larger (4.97% against 4.70%).
- An independent audit recomputed the money, 886 prices and every earned lot's stops, and all of it matches.

**Can't say:**
- That N10 will make this money. All four years were studied before and during its design, and I used them to choose its rules.
- That the retry's +₹34,791 is real. Three lots alone supply over half of the earned-lot money.
- That 2023 is fixed. **It still loses ₹32,898,** and nothing tested here has an edge in a year like it.

**Overfitting estimate:** 0.381 across all 89 books since N08, where pure noise averages about 0.53 with a spread of 0.18. That's within one spread of chance, and N10 ranks first. So it's encouraging, but it doesn't prove anything.

## 6. Learning from N09.1

The other agent found two real faults in my N09, and I agree with both. My size-by-volatility book also changed the morning clock, and my stress test let a paper trade justify its own entry. Its reserve really does cut the worst day. Its claim that the account "continues within its loss budget" holds only by the ₹18.45 above, and that is the one thing I'd correct.

## 7. What is left

- **NIFTY 2022, the fair test.** [The sheet](research/simulation/2026-11-01-fno-n10/EXAM_2022.md) is written before the data exists. It needs your ICICI login.
- **A forward paper shadow of N08, N09.1 and N10.** Not built, and you'd register the scheduled task.
- **WATCH touches the 15% stop, which is your decision.** A live version should only step down when the account truly can't pay for a typical lot. In this test one step fired with ₹32,554 free, on an expensive option.
- **N10 doesn't apply to ₹12,500-15,000.** One lot's premium is most of that account, so the reserve can't work there.

Errors and judgement calls in this study: [SOURCE_CORRECTION.md](research/simulation/2026-11-01-fno-n10/SOURCE_CORRECTION.md).
