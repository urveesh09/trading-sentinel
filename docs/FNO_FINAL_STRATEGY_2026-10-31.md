# The final F&O strategy: what the evidence supports

**Studies O31b and O31c, October 31, 2026.** Research only. Nothing in the trading system changed, and Production was not touched.

Written for the owner first and for any agent second. It follows [FNO_2024_EXAM_2026-10-31.md](FNO_2024_EXAM_2026-10-31.md). Numbers and code: [`research/fno/2026-10-31-final-book/`](research/fno/2026-10-31-final-book/). How to run tests like these: [FNO_YEAR_DATA_TESTING_METHOD.md](FNO_YEAR_DATA_TESTING_METHOD.md).

---

## The answer

1. **Keep today's lot limit.** It was the best of the five tested.
2. **Today's design is close to as good as it gets by adjusting it.** None of 46 single changes helped in all three years. Choosing the best change on two years then lost to no change on the third, all three times.
3. **The strategy to aim for is the four strategies + the skip rule + a stricter trend filter (ADX 30) at today's limits.** It is the best balance of consistency and low losses found, and it was positive in all three years after the assumed cost.
4. **It is not proven, and it did not pass the check fixed in advance,** though it missed narrowly. So it goes on paper first.
5. **Monday's real-money test should stay on today's book at one lot.** This reverses the earlier recommendation to add the skip rule before Monday (section 6).
6. **It will not be a daily income.** The candidate trades in about 1 week in 7, and most months nothing happens.

---

## 1. The lot limit

The four strategies + the skip rule, ₹2.5 lakh, each year on its own, with the assumed extra cost in the money path:

| Lot limit | 2024 | 2025 | 2026 | Added up | Worst fall in a year |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 lot | −₹18,343 | +₹12,900 | +₹41,112 | +₹35,669 | 10.6% |
| 2 lots | −₹250 | +₹4,432 | +₹44,658 | +₹48,840 | 12.2% |
| **Today: 2, or 3 once proven** | **−₹219** | **+₹4,805** | **+₹47,333** | **+₹51,919** | **12.1%** |
| 3 lots | −₹22,660 | +₹7,720 | +₹61,527 | +₹46,587 | 13.2% |
| 5 lots | −₹21,186 | −₹1,148 | +₹62,176 | +₹39,842 | 13.9% |

More lots earn more in 2026 and give it back in the other years. **Today's limit stays.**

---

## 2. Everything else tested

Each row changes one thing from the four strategies + rule at today's limits. **+₹51,919 is the number to beat.** No row helped in all three years.

| Area | Change | Added up | What it showed |
| --- | --- | ---: | --- |
| Frequency | One position at a time | +₹73,252 | Most money, but worse in 2025 (t 0.91) |
| | At most 2 / 1 trades a day | +₹55,979 / +₹53,388 | Moves money between years |
| | No entry after 13:30 / 12:30 | +₹42,718 / +₹50,644 | Better in 2026, worse in 2024 |
| Day filter | ADX 30 | +₹52,621 | Same money, much smaller falls (section 3) |
| | ADX 20 | +₹12,574 | Far worse |
| | Only with the daily trend (DMI / EMA) | +₹47,312 / +₹49,702 | Great in 2026, loses in 2024 and 2025 |
| | Skip the day before expiry | +₹34,860 | Better in 2024, much worse in 2026 |
| | Opening drive / wide open | −₹20,921 / −₹16,438 | Worse |
| Strategies | Without EFF / SHIPPED / OR20 | +₹24,157 / +₹24,804 / +₹42,850 | All four earn their place |
| | Without TPB | −₹11,681 | TPB matters most |
| | Add TPB on no-trend days | −₹5,487 | Worse |
| | Add FADE on no-trend days | −₹20,607 | Worse: sideways fades still do not work |
| Exits | Everyone on the shipped exit | −₹39,614 | Each strategy's own exit is much better |
| | LATE / LOOSE / RUN exits | +₹12,081 / +₹12,241 / +₹38,447 | Worse |
| Stops | Premium stop 20% / 35% | +₹37,675 / +₹29,953 | 25% stays |
| | Underlying stop × 0.75 / × 1.25 | −₹23,539 / +₹42,508 | Today's stays |
| Contract | Delta 0.45 / 0.65 | +₹8,505 / +₹32,438 | 0.55 stays |
| Risk | 1% / 1.5% / 2.5% a trade | −₹32,331 / +₹15,157 / +₹46,637 | 2% stays |
| Brakes | All off | +₹16,985 | The brakes earn their place |
| | No two-strike / no size cuts | +₹33,134 / +₹31,738 | Same |

- **The brakes, the exits and all four strategies each help.** This supports keeping the system as designed.
- **One caution:** today's settings were partly chosen on these same years, so they are bound to look good against their neighbours.
- **Not informative:** turning off the total stop changed nothing, because this book never reached it. Turning off the profit-lock setting also changed nothing, because each strategy's exits set their own lock.
- **Selection luck, held-out year:** choosing on two years gave `1 lot` for 2024 (−₹18,343 against −₹219), `one at a time` for 2025 (−₹4,517 against +₹4,805), and `skip expiry-eve` for 2026 (+₹17,527 against +₹47,333). All three lost to no change.

---

## 3. The candidate: why ADX 30 with the rule

| | Today's live book | Four + rule, ADX 25 | **Four + rule, ADX 30** |
| --- | ---: | ---: | ---: |
| **₹2.5 lakh with the cost, each year alone** | | | |
| 2024 | −₹33,726 | −₹219 | **+₹16,371** |
| 2025 | −₹38,681 | +₹4,805 | **+₹5,710** |
| 2026 | +₹61,674 | +₹47,333 | **+₹30,540** |
| Worst fall in a year | 17.6% | 12.1% | **7.5%** |
| **One account, Jan 2024 – Oct 2026, with the cost** | | | |
| End | ₹2,10,834, stopped itself Jan 2025 | ₹3,09,155 | **₹2,99,454** |
| Biggest fall | 19.7% | 11.9% | **7.8%** |
| **Same account, no extra cost** | not run | ₹3,87,347 | ₹3,54,029 |
| **Per lot, after ₹200 a trade** | | | |
| Net, 34 months | +₹31,545 | +₹59,129 | +₹52,682 |
| Biggest fall | ₹53,289 | ₹26,852 | **₹10,457** |
| Worst month | −₹24,971 | −₹19,311 | **−₹3,673** |
| Three-month periods up / down, of 32 | 12 / 13 | 14 / 10 | **14 / 3** |
| Weeks up / down, of 148 | 22 / 29 | 25 / 24 | 13 / 8 |
| Without each year's best day | −₹50,215 | +₹2,043 | **+₹22,169** |
| Weekly t-statistic | 0.50 | 1.19 | 1.99 |
| **One lot from ₹15,000, chance of ending under the ₹7,000 floor** | | | |
| 20 sessions | 7.5% | 0.8% | **0%** |
| 60 sessions | 21.6% | 12.6% | **0.2%** |

**The price:** it trades in only 21 of 148 weeks, about 38 trades a year. In most weeks and months nothing happens.

**What to expect, in replays only:** on ₹2.5 lakh, about ₹1,450 a month with the assumed cost, up to about ₹3,050 without it. That is 7% to 15% a year, averaged over long empty stretches.

---

## 4. Did it pass the checks fixed in advance? No, narrowly

Both tests were fixed before their replays ran (`dca512d`).

**The skip rule.** Test: at ADX 25, limits 0.35, 0.5 and 0.65 must all beat no rule, per lot after ₹200, one lot, brakes off.

| Limit | None | 0.25 | 0.35 | 0.5 | 0.65 | 0.75 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Three years | −₹23,677 | −₹28,293 | +₹17,101 | +₹44,073 | **−₹24,493** | −₹11,571 |

Limit 0.65 missed by ₹816, so by the fixed rule it **failed**.

**ADX 30.** Test: ADX 28, 30 and 32 must each be positive in every year at today's limits, and ADX 27, 30 and 32 must each lower the fall. ADX 28 lost ₹2,456 in 2024, and ADX 27 had a larger fall than ADX 25, so it **failed**.

The fixed rule then says: **keep the book as live today, and put both on paper.** That is what this document recommends for real money.

**What the wider picture adds.** None of this overrides the rule, but it is why the candidate is still worth pursuing:

- **The rule helps almost everywhere.** It beat no rule in **28 of 30** cells of the surface. The only two misses are the ones at ADX 25 above.
- **Entries get worse past the limit, in every bucket.** One lot after ₹200, ADX 25, no rule, all three years:

  | Distance from VWAP, as a share of the first 30 minutes' range | Trades | Net | Per trade |
  | --- | ---: | ---: | ---: |
  | Behind VWAP (below 0) | 60 | −₹29,583 | −₹493 |
  | 0 to 0.25 | 61 | +₹27,741 | +₹455 |
  | 0.25 to 0.35 | 32 | +₹37,325 | +₹1,166 |
  | 0.35 to 0.5 | 84 | +₹19,446 | +₹232 |
  | 0.5 to 0.65 | 74 | −₹35,793 | −₹484 |
  | 0.65 to 0.75 | 37 | −₹6,928 | −₹187 |
  | 0.75 to 1 | 60 | −₹28,594 | −₹477 |
  | Above 1 | 84 | −₹7,291 | −₹87 |

  So 0.5 sits on a real slope. It looked like a spike because the 0.5–0.65 band is the worst one, and a limit of 0.65 lets it back in. Behind-VWAP entries also lose, but that was noticed only here, so it is not tested as a rule.

- **ADX 30 and above is a plateau, even though 27 and 28 are not.** With the rule at today's limits, ADX 30, 32 and 35 are all positive in all three years: +₹52,621, +₹37,506, +₹28,247. Worst falls are 7.5%, 5.9% and 5.0%.
- **The real entries beat random ones.** At ADX 30 with the rule, the four strategies made +₹43,170 per lot. The 20 random-entry books had a median of −₹32,320 and a best of +₹11.
- **Much of the strict filter's benefit is simply trading less.** Random books also lost less at ADX 30 (median −₹32,320 against −₹46,883). So it mainly cuts losing days. It does not add skill.

**Why this is still not proof:** all three years have been seen, the candidate was picked after looking at them, and the 46 changes in section 2 and a 36-cell surface were all tried on the same data. The t of 1.99 ignores that search.

---

## 5. The strategy

| Part | Today's live book | The candidate |
| --- | --- | --- |
| What it trades | NIFTY weekly options, buying only, delta about 0.55 | Same |
| Which days | Yesterday's ADX(14) at least 25; no entry on expiry days | **ADX at least 30**; no entry on expiry days |
| Entries | SHIPPED, OR20, EFF, TPB, in that order, on closed 5-minute bars, 09:45–14:45 | Same |
| Skip rule | None | **Skip an entry already 0.5 of the first 30 minutes' range beyond VWAP** |
| Exits | Each strategy's own | Same |
| Size | 2% risk, ₹6,250 cap, 2 lots (3 once proven), 15% of the money in premium | Same |
| Frequency | 3 trades a day, 2 at once | Same |
| Brakes | Day 3%, week 6%, month 10%, total 15%, two-strike, size cuts | Same |

**It does not** trade most days, earn on sideways days (it sits out), or promise any month's result.

**To switch later:** ADX 30 is one setting (`FNO_BOOK_ADX_MIN=30`). The skip rule needs new engine code, tests and a deploy.

---

## 6. What to do

**Monday, Nov 2–6: today's book, one lot, ₹15,000.**
- **This reverses the earlier recommendation.** The exam write-up said to add the skip rule before Monday. The check fixed in advance then failed, and that check said it stays off real money whatever the exam said.
- **The week's job is to measure real fills and prove the order route.** Today's book trades more, so it gives more fill data, and no new engine code goes live the day before real money.
- **The risk is small for one week:** 0.1% chance of ending under the floor at ₹15,000.
- **The owner can overrule this.** If you want the rule on Monday, it needs code, tests and a deploy by Sunday night.

**After Nov 6:** real fills replace the assumed ₹200. Then decide what any further real money trades. If it continues past a few weeks, this evidence favours moving it to the candidate: today's book had a 21.6% chance of hitting the floor over 60 sessions, against 0.2%.

**Do not raise the size** to ₹1–1.5 lakh yet.

### The forward check, fixed now

Only new sessions can settle this.

- **Books, unchanged, all in `freeze.json`:** `SKIP|none` (today), `BASE` (ADX 25 + rule) and `ADX|30` (the candidate).
- **Data:** NIFTY sessions from Oct 29, 2026, through this same replay, once a month after the owner's ICICI login. Use a worktree at this commit if the engine has changed.
- **Cost:** ₹200 until at least 5 real round trips exist, then the measured figure.
- **The candidate is confirmed when, with at least 20 forward trades:** net above zero after cost, net per rupee of fall above today's book, fall at most 10%, and no single day more than half the net.
- **Pace:** at about 38 trades a year this could take around six months. Busy trending stretches will be faster.

---

## 7. How this was checked

- **403 exact replays** through the shipped code (150 in O31b, 253 in O31c). `check_book` found 0 problems: charges, day cap, own cash, lots, extra cost.
- **Parity:** three reference books reproduced the 2024 exam's and the risk study's figures exactly in every year.
- **No effect flagged:** two changes with identical trades are reported as uninformative, not as passes.
- **Order:** O31b's plan was committed before its replays (`9977e71`), its results before O31c was written (`4d7b100`), and O31c's plan and decisions before its replays (`dca512d`).

**What replays cannot show:** real slippage. The ₹200 per trade is an assumption, and candles flatter fills by about ₹100–200 per lot. Lot 65 is applied in all years so results are comparable.
