# EN26–EN40 and the first fresh exam of E03.2 (NIFTY 2026, SENSEX): where each slot won and lost

Scored once on Nov 18, 2026 by `en_score4.py` under `PLAN4.md`, frozen at `12f828d1` before any score:
- results: `results4.json`, `anatomy4.json`, `results4-started.json`;
- tables: `ANATOMY4-tables.md`, rendered by `render4.py` from the scored files.

The rupee figures below come from those files. Each figure is the net after fees of one Rs 25,000 book at ordinary fills, unless the text says otherwise.

**Books:**
- **Development (seen):** NIFTY 2023, 2024 and 2025, one book per year.
- **Exam (untouched until today):**
  - **N-X1:** NIFTY Jan 6 – Sep 8, 2026, 36 expiry afternoons.
  - **S-X1:** SENSEX Jul 29, 2025 – Sep 3, 2026, 58 expiry afternoons.
- **X2 (partly seen):** NIFTY 7 days and SENSEX 5 days, Sep–Oct 2026. Reported apart; each had one E03.2 ticket (−33 and −95).

## 1. E03.2 on fresh data: its edge is not confirmed

| Book | Ordinary | Adverse | Severe | Without best day | Worst day | Tickets (winners) | Random entries, median |
|---|---:|---:|---:|---:|---:|---:|---:|
| NIFTY Jan–Sep 2026 | **−3,847** | −4,129 | −3,819 | −3,917 | −1,281 | 9 (2) | −961 |
| SENSEX Jul 2025 – Sep 2026 | **+2,082** | +1,637 | −4,151 | **−3,173** | −1,125 | 11 (3) | −105 |

- **NIFTY 2026: it lost, and lost more than random entries did.**
  - 5 tickets hit the stop for −3,514 of the −3,847.
  - The 14:30–15:00 window: 3 tickets, no winners, −2,536.
  - Puts: 5 tickets, 1 winner, −2,924. Calls: 4 tickets, 1 winner, −923.
  - Worst days: Apr 21 put −1,025, May 26 put −889, Feb 17 put −622.
  - Best day: Aug 4 put, +71.
- **SENSEX: positive only through one ticket.**
  - The Nov 13, 2025 put sold half at 2x and trailed the rest: **+5,255**. The other 10 tickets lost −3,173.
  - 6 stops: −4,071.
  - 14:30–15:00: 5 tickets, no winners, −3,490.
  - Calls: 4 tickets, no winners, −2,320.
- **The E03-family tests, unchanged from the frozen exam:**
  - **Test 7 (E03.2 stands): fails on both books.** NIFTY fails every check. SENSEX fails "without the best day".
  - **Test 1 (E03.1 stands):** fails on both.
  - **Test 5 (E03.2 over E03.1):** fails on both. On NIFTY, E03.1 lost less (−2,650). On SENSEX, E03.2 was ahead except without its best day.
  - **Test 6 (puts earn more per ticket than calls):** holds on SENSEX (+276 against −580). Fails on NIFTY 2026 (−345 against −231).
- **The whole record:** 248 expiry afternoons across NIFTY 2023–25, NIFTY 2026 and SENSEX.
  - E03.2 made +16,107.
  - Two tickets made all of it and more: Mar 28, 2024 (NIFTY put, +11,771) and Nov 13, 2025 (SENSEX put, +5,255).
  - **Every other ticket together lost −918.**
  - It trades about one ticket every three expiries (76 tickets in 248 afternoons).
- **Coverage:** the strike-coverage rule refused 0 NIFTY 2026 decisions and 1 SENSEX decision. The download's ± 10 strikes around the opening at-the-money strike covered E03.2's choices.

### Size (risk dial K1, RISK_PLAN.md's frozen limits): stays at 1
- No size from 1x to 3x passes either record.
- Even at 1x, the skeptical chance of a losing year is 63% (NIFTY 2023–25 + 2026) and 80% (SENSEX). The limit is 30%.

### A fact about the brakes (post-score diagnostic)
One continuous E03.2 book started in January 2023:
- hits the Rs 4,000 drawdown stop on **Jan 18, 2024**;
- stays halted for 139 of the next 190 expiries, because the brake never resets;
- ends at Rs 20,877, so it never traded the 2024 hero.

The yearly books in these tables each start fresh at Rs 25,000.

## 2. The auditor's ten

### EN26: confirm damage before exiting faster (INCONCLUSIVE)
**How it did:** the confirmation fired **once in 248 afternoons**, in 2023, saving +117. The catastrophe diagnostic (a wick to 40% of the entry) never fired.

**Why:** at minute cadence a wick through the stop is followed by one of two things:
- a completed minute below the stop, so the ordinary stop sells; or
- a recovery.

The in-between state, "near the stop with the index half an ATR against", almost never lasts a minute.

**Learned:**
- The completed-minute stop already catches lasting damage.
- The faster-exit question needs real sub-minute bids. That means the TR01 recorder, forward.

**Comparison: EN11, the blind fast touch, on the same tickets.**
- Across the five books it saved 29 tickets (+4,712), cut 13 (−6,052) and turned 2 winners into losers.
- On the fresh books alone it did better than E03.2: −3,339 on NIFTY, +3,401 on SENSEX. It is a diagnostic, not a candidate.

### EN27: give the scout time to earn an add (FAIL)
**The rule:** buy half first; add once in minutes 2–6 if the trade is confirmed; the stop never moves down.

**Gains:**
- 25 tickets stayed half-size. They lost −2,132, against −5,925 for E03.2 on the same tickets: **+3,793 saved on wrong tickets**.
- On fresh NIFTY, the three biggest stops were halved: Apr 21 −1,025 → −536, May 26 −889 → −468, Feb 17 −622 → −335.

**Costs:**
- 14 adds (10 winners) made +19,634, against +24,423 for E03.2: **−4,789 on winners that started slowly**.
- Development lost −2,337 in 2024 and −888 in 2025.
- SENSEX adverse fell to +224, against +1,637.

**Result:**

| Book | EN27 | E03.2 |
|---|---:|---:|
| NIFTY 2026 | −2,650 | −3,847 |
| SENSEX | +2,294 | +2,082 |

**Against EN21:** better in 2025 and on both fresh books, worse in 2024. EN21's 20%-jump add bought the hero bigger.

**Learned:** probing with half shrinks the losers in every book. The price is the size of the slow winners.

### EN28: patient entry with a bounded fallback (ONE-INDEX: SENSEX PASS, NIFTY FAIL)
- **Fills:** the same tickets, bought **0.49% cheaper**.
  - 75 of 76 filled passively under the conservative bound.
  - The minute after a decision traded a median of 19 ticks below the decision bid.
  - 1 ticket used the fallback; none was missed.
  - The optimistic diagnostic gave identical results, so the bound does not matter here.
- **Ordinary fills:** about the same as E03.2.

  | Book | EN28 against E03.2 |
  |---|---:|
  | 2023 | −114 |
  | 2024 | −572 (an extra ticket lost −922) |
  | 2025 | +136 |
  | NIFTY 2026 | +266 |
  | SENSEX | +178 |

- **Severe fills:** much better, for example 2024 +10,530 against −2,582 and SENSEX −955 against −4,151. Most of that gap is the model, not a market fact: the severe scenario buys at the bar's high, while a resting bid keeps its fixed price. This is the auditor's warning.
- **Why NIFTY fails:** only the "adverse net > 0" check, because nothing is profitable on NIFTY 2026. On every relative check it beat E03.2 on both fresh books.
- **Learned:**
  - On these options a resting bid almost always fills within the minute.
  - The real saving is about the spread.
  - Whether real queues fill it needs TR01's depth data.

### EN29: a runner that must keep earning its hold (INCONCLUSIVE: 6 tickets)
**How it did:** the stall exit improved 3 runners (+2,079) and worsened 2 (−435).

| Book | EN29 | E03.2 |
|---|---:|---:|
| 2024 | +16,482 (kept the hero's tail) | +15,581 |
| 2025 | +6,712 | +5,937 |
| SENSEX (hero sold earlier) | +4,972 | +5,255 |

**Against selling everything at 2x:** a full sale saved 4 tickets (+4,104) but cut the 2024 hero by −8,970.

**Learned:** the best runner rule so far. It needs many more 2x tickets to judge.

### EN30: second wave at a held base (FAIL)
- **Development:**

  | Year | EN30 |
  |---|---:|
  | 2023 | −1,888 |
  | 2024 | −266 |
  | 2025 | +4,987 |

  It beat EN14's breakout entry by +5,332 over three years, and the immediate chase by much more.
- **Fresh data:** −2,816 on NIFTY and −1,757 on SENSEX. That is about its random-side null (−2,733 and −2,004), so it shows **no direction skill**. EN14 on the same books: −2,378 and −375.
- **Learned:** a held retrace is a better entry than a breakout. But after a 2.5-ATR burst, the next direction is a coin toss on fresh data.

### EN31: reverse only after the opposite move is accepted (INCONCLUSIVE)
**How it did:** the accepted-reversal condition happened **once** in 248 afternoons, on NIFTY 2026: −441.

**The diagnostic flip** (buy the other side immediately after every stop):
- 16 flips, 8 winners, −727;
- 2024 lost about −3,000 against E03.2, because flips crowded out E03.2's profitable re-entries (+1,740 removed);
- NIFTY 2026 was +1,784 better.

**Learned:** after a failed E03.2 ticket the market rarely proves the other side within 10 minutes. Flipping blindly is a coin toss.

### EN32: a different contract for the range trade (FAIL)
**How it did:** buying one lot at the money or one strike in the money, instead of EN13's cheap out-of-the-money option, **cut the range trade's losses by 20–99%** (66% in 2023, 30% in 2024, 20% in 2025, 99% on NIFTY 2026, 65% on SENSEX). It still lost everywhere.

| Book | EN32 | EN13 |
|---|---:|---:|
| 2023 | −885 | −2,608 |
| 2024 | −2,046 | −2,924 |
| 2025 | −3,238 | −4,033 |
| NIFTY 2026 | −13 | −2,311 |
| SENSEX | −764 | −2,169 |

**Funding:** one lot fit the Rs 1,250 reserve on only 8 of 109 NIFTY 2026 signals and 6 of 85 SENSEX signals.

**Learned:** for small targets the cheap OTM option is the wrong instrument; decay and spread eat the move. The range signal has no edge either way.

### EN33: measured cross-index lag (FAIL, minute adaptation)
**The lead is real:** NIFTY's front future leads the SENSEX index by a minute, measured over 6,960 minutes:
- lag correlation 0.077;
- partial correlation 0.226 once SENSEX's own minute is removed;
- same-minute correlation 0.65.

**It does not pay:** the 29 tradable events lost −74.5 per one-lot trade, about the same as random minutes (−76.6).

**Learned:** usable as an input, not as a trade at minute resolution. The 30-second and BANKNIFTY versions are DATA_UNAVAILABLE.

### EN34: the later expiry (NOT FEASIBLE)
**The numbers:** one lot of next week's at-the-money or first OTM option costs a median Rs 8,909 (NIFTY put) to Rs 11,910 (SENSEX call). The reserves are Rs 1,250 and Rs 2,500. **0 of 4,276 minute-sides fit.** The slot stops here, as the plan said.

### EN35: the combination (NOT READY; interaction diagnostic only)
**Status:** EN27 and EN28 failed development and EN29 is inconclusive, so the combination is not eligible.

**The diagnostic, for learning:**

| Book | EN35 | E03.2 |
|---|---:|---:|
| NIFTY 2026 | **−2,355** (the best E03.2 variant there) | −3,847 |
| SENSEX | +2,470 | +2,082 |

- Development: −2,947 / +13,205 / +5,334.
- Severe fills much better.

**The pieces do not fight each other:**
- 15 adds still happen behind the patient entry;
- the hero's tail is kept.

**Learned:** this is the combination worth testing forward if its pieces earn eligibility.

## 3. My five

### EN36: buy gamma only when it is cheap (FAIL)
**The rule:** buy only when the at-the-money straddle is at most 0.6924 × the expected move.

**How it did:** it removed 37 tickets. 16 were winners, and the removed tickets were worth +14,758 net, mostly the 2024 hero.

**Gains:** bad-year losses cut by 73–93%.

| Book | EN36 | E03.2 |
|---|---:|---:|
| 2023 | −240 | −3,645 |
| NIFTY 2026 | −1,036 | −3,847 |

**Costs:**

| Book | EN36 | E03.2 |
|---|---:|---:|
| 2024 | +2,025 | +15,581 |

**Learned:** E03.2's heroes were bought while options were *expensive* against recent movement, because the big move was already under way. Cheap options mean quiet days and small losses. Valuation runs against the hero.

### EN37: the chain's flow agrees (INCONCLUSIVE)
**How it did:** it removed 2 tickets in 248 afternoons.

**Learned:** out-of-the-money turnover rises and falls with price itself. It carries no separate information at minute level.

### EN38: the futures lead the cash (ONE-INDEX: SENSEX PASS, NIFTY FAIL)
**The rule:** keep a signal only when the futures basis widened in the trade's direction.

**How it did:** it removed 36 tickets, 14 of them winners, worth +14,198 net. Again that was mostly the 2024 hero.

| Book | EN38 | E03.2 |
|---|---:|---:|
| 2023 | −393 | −3,645 |
| 2024 | +3,551 | +15,581 |
| 2025 | +2,764 | +5,937 |
| NIFTY 2026 | −2,442 | −3,847 |
| SENSEX | +2,819 | +2,082 |
| Total | +6,299 | +16,107 |

Three of five books are positive. The worst year is −2,442 against E03.2's −3,847.

**Learned:** futures leading the cash marks better tickets on average. It is the steadiest profile here, but it still loses on NIFTY 2026 and gives up the hero.

### EN39: trade only 14:00–14:30 (ONE-INDEX, exam-only)
**The test:** the window was chosen on 2023–25, where it was +1,315 / +1,741 / +2,847.

**Fresh data:** NIFTY −705 (2 tickets, no winners); SENSEX +3,358 (3 tickets, all winners).

**Learned:** the steady window stayed positive on SENSEX and lost a little on NIFTY. At 18 tickets in 248 afternoons, it is too rare to be a strategy.

### EN40: no put double (FAIL, exam-only)
**How it did:**

| Book | EN40 | E03.2 |
|---|---:|---:|
| NIFTY 2026 (puts lost, so half-size puts lost less) | −2,650 | −3,847 |
| SENSEX (the hero put was half size: +1,698 instead of +5,255) | −664 | +2,082 |

**Learned:** the put double is a bet on the put hero. It paid on SENSEX and cost on NIFTY 2026.

## 4. Round 3's held parts on fresh data
| Part | NIFTY 2026 | SENSEX | Status |
|---|---:|---:|---|
| EN21 scale-in | −3,240 | +606 (the hero bought half, then added smaller: +3,510) | FAIL |
| EN25 resting bid | −3,581 | +1,975 | FAIL |
| EN14 second wave (own book) | −2,378 | −375 | FAIL |
| EN12 cover the cost at 2x | −3,847 (no change) | +2,172 | INCONCLUSIVE (one ticket each) |

## 5. Harness repair R1 (the auditor's quote-harness faults)
The fixes: forward-only clock exits, decision-time sizing, a dated front future and quote age ≤ 10 s.

**EN16-R1: FAIL, unchanged.**
- Confirmed 155 of 162 triggers; hit 47.1%.
- 80 booked one-lot trades, mean −17.5.
- 62 refusals: 27 for the reserve, 25 for the limit, 10 for a stale or missing quote.

**EN18-R1: FAIL, unchanged.** The alternative strike was never chosen.

**Conclusion:** the repaired harness confirms both verdicts.

## 6. What this round taught

1. **E03.2 is a lottery on rare put heroes, not a consistent earner.** Two tickets carry its whole record. On fresh NIFTY it lost more than random entries.
2. **Filters that remove losing tickets also remove the hero:** EN36, EN38, EN39, and EN24 before them. Nothing here tells a hero in advance: not valuation, flow, the futures basis, the time window or the volume.
3. **What does work, mechanically:**
   - **probing with half** (EN21 and EN27) shrinks the losers in every book;
   - **the stall runner** (EN29) keeps the hero's tail;
   - **a resting bid** (EN28) saves about the spread.

   None of these turns a losing year positive.
4. **Contract choice matters for small targets** (EN32): at-the-money instead of cheap out-of-the-money cut losses by 20–99%.
5. **NIFTY futures lead SENSEX by a minute** (EN33): real, but not tradable through options at that speed.
6. **Size stays at 1.** The brakes halt a bad-year book for good.

**Nothing is promoted or deployed.**
- E03.2 stays the paper main, unchanged.
- Whether to keep it as the main on NIFTY after this failed exam is the owner's call.
