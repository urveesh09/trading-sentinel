# EN11–EN25: where each slot won and lost (scored once, Nov 17–18)

Frozen in `d2f53af7` (`PLAN3.md`), scored once by `en_score3.py`. The receipts are `results3.json`, `anatomy3.json` and `results3-started.json`. `ANATOMY3-tables.md` renders every table straight from those files (`render3.py`).

All rupees below are copied from them. They are ordinary-fill net after fees on one Rs 25,000 book per year, unless the text says adverse or severe; "t" means tickets and "w" means winners. NIFTY 2023–25 are seen development years, so none of this is an exam.

**Result:**
- **No slot passed.**
  - Thirteen failed their frozen rules.
  - **EN12** and **EN20** are INCONCLUSIVE: they moved fewer than 6 tickets in three years.
- **E03.2 stays exactly as it is**, and nothing changes in Production.
- The useful output is the anatomy below:
  - most of the ideas lose in the same few ways;
  - several failed slots contain a part worth keeping.

E03.2 (control): **2023 −3,645 · 2024 +15,581 · 2025 +5,937** (17, 19 and 20 tickets).

## Overview

| Slot | Idea | 2023 | 2024 | 2025 | Verdict |
|---|---|---:|---:|---:|---|
| EN11 | Fast (intrabar) stop and structure exit | −4,006 | +13,748 | +4,964 | FAIL |
| EN12 | Sell just enough at 2x to pay for the ticket | −3,645 | +15,581 | +6,882 | INCONCLUSIVE (1 ticket changed) |
| EN13 | Range rotation (own book) | −2,608 | −2,924 | −4,033 | FAIL |
| EN14 | Second wave of an impulse (own book) | +1,768 | −3,203 | −1,064 | FAIL |
| EN15 | Constituent breadth leads the index (15-min signal) | hit 45.4% | | | FAIL |
| EN16 | Next-expiry confirmation (2026 real quotes) | confirmed 155 of 162 | | | FAIL |
| EN17 | Call + put on a volatility burst (own book) | −628 | −1,388 | −1,525 | FAIL |
| EN18 | Strike by real executable cost (2026 real quotes) | alternative never chosen | | | FAIL |
| EN19 | One small late shot from a pinned strike (own book) | +1,629 | −2,530 | −2,697 | FAIL |
| EN20 | Re-enter only after the failed signal proves itself | −3,645 | +15,216 | +5,937 | INCONCLUSIVE (1 retry) |
| EN21 | Scale in only when right | −3,042 | +21,293 | +3,922 | FAIL |
| EN22 | No hard premium stop | −4,069 | +16,924 | +5,901 | FAIL |
| EN23 | Last-half-hour intraday momentum (own book) | +2,815 | −3,049 | −1,176 | FAIL |
| EN24 | Futures volume must back the resume | −1,271 | +3,595 | +4,634 | FAIL |
| EN25 | Patient entry (resting bid) | −3,359 | +15,009 | +6,124 | FAIL |

## Changes to E03.2's own tickets

### EN11 · fast exit: FAIL (worse in every year)
- **Where it won:** 17 tickets lost less, +2,133 in total.
  - 2023-06-15 put: −1,162 → −831.
  - 2023-12-07 put: −830 → −390.
- **Where it lost:** 9 tickets were cut, −5,300 in total.
  - 2024-02-22 call: a 2x winner, +1,313 → −380.
  - 2023-06-22 put: +1,104 → +196.
  - 2024-08-22 put: +953 → +174.
  - Two of the cut tickets would have recovered to winners (+1,714 in the control) but EN11 sold them for −796.
- **The 1-second data agrees** (`en11_seconds.py`, 42 stop touches, NIFTY Jan–Mar 2026):
  - Price relative to entry, with the stop at 0.65: 1 second after the touch 0.637, 3 seconds 0.635, 10 seconds 0.635.
  - The minute cadence gets 0.637 on average (median 0.607).
  - The fastest exit averaged 0.4% of entry worse than the minute cadence.
  - 16 of 42 touches traded back above the stop within 60 seconds.
  - In 8 of 42, no minute closed below the stop at all.
- **Good part:** fast exits do cut real losers on multi-lot puts.
- **Bad part:** cheap expiry options wick through stops and come back. The minute close filters that noise, and that filter is worth more than the seconds saved.
- **Lesson:** keep E03.2's completed-minute stop. Speed is not where the stop money leaks.

### EN12 · pay for the runner: INCONCLUSIVE
- **What changed:** one ticket. On 2025-09-02 (put) a 2-lot ticket could not be paid back by selling 1 lot, so it sold both: +1,047 → +1,992.
  - Everywhere else, the cover sale equalled E03.2's half sale.
  - E03.2 made 5 partial sales; 4 of them covered the whole debit. The fifth (2025-09-02) is the one EN12 sold whole.
- **The full-sale-at-2x diagnostic shows what the runner is worth:**
  - the 2024-03-28 hero runner is worth **+8,903** (+11,771 against +2,868 sold whole);
  - the other four runners each **cost** money, −4,104 together: 2024-05-09 −1,487, 2024-08-08 −1,204, 2024-07-18 −468 and 2025-09-02 −945.
- **Good part:** the 2x half sale already pays for the ticket.
- **Bad part:** the runner is a lottery ticket. It costs about Rs 1,000 on each ordinary 2x winner (−4,104 over 4) to keep the chance of one big day.
- **Keep in mind:** this is the one place where a simpler rule (sell everything at 2x) would have made more money, on all 4 non-hero 2x tickets. Judging it needs more 2x tickets than history holds.

### EN20 · proven re-entry: INCONCLUSIVE
- **What happened:** only 1 retry in three years. On 2024-07-18 (call) a 1-lot cap turned the split into a whole sale, so +1,150 → +785.
- **The no-retry diagnostic** (a block the owner rejects, used only to measure): E03.2's own second tickets after a losing stop are worth **+1,740 in 2024** and +362 in 2023.
- **Lesson:** E03.2's simple 5-minute cooldown retry is positive. A stricter gate has almost nothing to act on.

### EN21 · scale in only when right: FAIL
- **Where it won:**
  - Losing multi-lot puts lost half as much in 2023: 06-15 −1,162 → −604, 03-16 −889 → −468. 2023 as a whole: −3,645 → −3,042.
  - The 2024 hero grew from +11,771 to +18,429.
  - 9 tickets were added to: 6 winners, +19,797 against +16,016 in the control.
- **Where it lost:**
  - Ordinary winners that took longer than 3 bars to reach 1.2x only ever had half their size.
  - 2025: 8 of 11 changed tickets worse, −2,015. Examples: 08-07 +1,253 → +603, 06-12 +966 → +459.
  - Without the 2024 hero, its three-year net is about −2,360 against E03.2.
- **Good part:** it halves the 2023-style stop losses. That is the one idea here that shrank the bad year without a filter.
- **Bad part:** most of the gain is the hero, and it shrinks slow, normal winners.
- **Worth examining on new data:** a longer add window. That is a hypothesis only; nothing is re-tuned on these years.

### EN22 · no hard premium stop: FAIL
- **Effect:** +884 over three years, mostly from one ticket. On 2024-09-12 (call) a stop-out became a 2x target: −325 → +1,463.
- **Without the stop, the tickets that would have stopped mostly exited by structure or the clock at similar or worse losses:**
  - 2023: −424 overall;
  - 2025: −36;
  - 7 tickets worse (−1,551), 4 better (+2,366).
- **Lesson:** the 35% stop is roughly neutral. The money in stop exits is lost on genuinely wrong entries, not on bad stop placement.
- **Together with EN11:** both faster and no stops fail, so the stop level and cadence are not the problem. The entries are.

### EN24 · futures volume behind the resume: FAIL
- **Where it won:** it removed 7 tickets in 2023 worth −2,649 (2023: −3,645 → −1,271).
- **Where it lost:**
  - it removed the 2024 hero and three other 2024 winners: 4 tickets worth **+11,986**;
  - in 2025 it removed 4 tickets worth +1,303.
- **Lesson:** like EN08's calm-morning gate, it helps the losing year and removes the good years' winners. E03.2's best resumes happen on ordinary volume. Volume is not a quality signal for this setup.

### EN25 · patient entry (resting bid, 2 bars): FAIL by a small margin
- **What it did:**
  - Filled on almost every signal: 3 missed in three years, and the only one E03.2 also took was a −361 loser.
  - Changed 51 tickets by small amounts: 2023 +286, 2024 −572, 2025 +188, so about −100 net.
  - It failed only on 2024.
- **Severe fills:** under the severe-fill scenario it is far better: 2024 +10,530 against −2,582, 2025 +2,585 against +145.
  - That is mostly because a market order at the bar's worst price breaks E03.2's 8% buy limit on the 2024 hero, while the resting bid gets in.
- **Good part:** a resting bid fills about as often as paying the ask, saves half the spread, and caps the entry price when fills are bad.
- **Bad part:** a slightly different entry minute moves outcomes both ways. In ordinary fills it is a wash.
- **Worth measuring forward:** the resting-bid fill rate on real 2026 quotes. This is an execution safety idea, not a profit idea.

## New setups (each in its own Rs 25,000 book, symmetric Rs 1,250 tickets)

### EN13 · range rotation: FAIL (loses every year, 102 tickets)
- **Where it won:** midpoint targets: 8t 7w +1,671 (2023), 8t 7w +1,719 (2024), 4t 3w +525 (2025).
- **Where it lost:**
  - range breaks: −2,392, −2,635, −1,151;
  - the 8-minute clock: −1,023, −1,453, −1,582;
  - stops.
- **Against chance:** it was below its random-side null in 2023 and 2025. The range edge carries no direction.
- **Lesson:** on expiry afternoons, a rotation to the midpoint is too small to pay for the spread and the decay on a cheap option. Breaks are frequent: 10 of 32 tickets in 2023. It traded mostly on E03.2's empty days (64 of 102 tickets) and lost there too.

### EN14 · second wave: FAIL, with one clear lesson
- **Results:** +1,768 / −3,203 / −1,064 (64 tickets).
- **Against the immediate entry:** buying the impulse immediately lost −3,307 / −3,803 / −3,097.
  - **Waiting for the pause and second push beat chasing the first impulse in all three years** (+5,075, +600, +2,032).
  - It beat its null in 2023 and 2025.
- **Where it lost:** stops: 2024 7t −2,903, 2025 9t −4,152.
- **Good parts:**
  - puts in 2025: 14t 8w +1,263;
  - 2023 as a whole, E03.2's losing year: +1,768, of which +2,585 came on days E03.2 also traded.
- **Lesson:** never chase a 2.5-ATR 3-minute burst. If a burst is ever traded, the second wave is the less bad entry. It is still negative in 2 of 3 years.

### EN17 · call + put on a burst: FAIL (15 pairs, 2 winners)
- **Where it lost:** most pairs fade (FADE 10 of 15). Its 2024 and 2025 results were below its random-minute null.
- **Bad part:** two spreads and two sets of fees against a burst that usually does not continue.
- **Good part:** none. The one +946 target (2025-08-07) is the only winner of size.

### EN19 · late release from a pinned strike: FAIL
- **Results:** +1,629 / −2,530 / −2,697 (44 one-lot tickets).
- **Good part:** the one-lot runner from 2x works when it happens: runner exits +2,749, +381 and +3,056.
- **Bad part:** stops: 2025 14t −5,713. The 14:00–14:30 window flipped from +2,376 (2023) to −2,176 (2024).
- **Lesson:** a pin release is a coin flip after costs. The "small late hero" route only pays through its rare runners.

### EN23 · last-half-hour momentum (Gao, Han, Li & Zhou 2018): FAIL
- **Results:** +2,815 / −3,049 / −1,176 (25 tickets, 4 winners).
- **Where 2023 came from:** two puts, 2023-02-23 +3,715 and 05-18 +1,220. Without its best day, every year is negative.
- **By side:** calls lost every year (−1,409, −883, −1,607); stops cost −1,802, −2,740 and −3,291.
- **Lesson:** the index-level effect (R² about 2% in the paper) is far too small to pay for buying a 15:00 expiry option. It turns into a gamma lottery.
- **Deployability:** it would only have been possible after Dec 7 anyway (NSE CAS 2.0).

## Signal and cost studies

### EN15 · constituent breadth (Kite 15-minute bars, Jan–Jul 2026): FAIL
- **Data:** 280 events with |breadth| ≥ 0.6 in 143 sessions.
- **No lead:** whenever 80% or more of the 50 names moved together, the index moved the same way. There were no disagreement events, so breadth adds nothing the index does not already show.
- **Next bar:** it continued only 45.4% of the time (expiry days: 39.3%), a mild reversal.
- **Lesson:** not worth buying minute-level constituent data for this purpose.

### EN16 · next-expiry confirmation (19 real 2026 expiry sessions): FAIL
- **Confirmation is almost always present:** the next expiry's synthetic forward agreed with the front future on 155 of 162 triggers. Both price the same index, so the "confirmation" is near-tautological.
- **The trigger itself:** a 0.04% futures move over 3 minutes continued 47.1% of the time over the next 8 minutes (NIFTY 50.0%, SENSEX 44.2%). A one-lot E03.2-band buy on it lost −68 a trade on real bid/ask (131 trades, −8,888).

### EN18 · strike by real executable cost (same 19 sessions): FAIL
- **What happened:** the rule never chose the further strike.
- **Why** (descriptive follow-up from `rec2026.py`'s own functions):
  - The adjacent further-OTM strike existed 79% of the time.
  - Its one-lot round trip was always a larger share of the premium: NIFTY 11.0% against 5.7%, SENSEX 7.6% against 5.0%.
  - Its 8-minute one-lot return per rupee was worse: NIFTY −12.2% against −6.0%, SENSEX −11.1% against −7.7%.
- **Lesson:** E03.2's nearest-OTM pick inside the band is already the cost-efficient strike. The fixed Rs 47 of order charges dominates cheaper options.

## What carries forward

- **E03.2 unchanged.** Its stop level, its stop cadence, its retry rule and its strike choice were each challenged here, and each held up.
- **Where E03.2 actually loses:** wrong entries, not exits. Every exit variant (EN11, EN12, EN22) and every entry filter (EN24, and EN08 before it) either moves money between years or removes the 2024 hero.
- **Parts worth keeping as hypotheses** (none is a result):
  - EN21's halving of stop losses on wrong multi-lot puts;
  - EN25's resting bid as an execution safety;
  - EN14's lesson that a second wave beats chasing an impulse;
  - EN12's finding that the runner is a hero lottery costing about Rs 1,000 per ordinary 2x winner.
- **What is needed next:** only fresh data can move this forward.
  - SENSEX expiry afternoons;
  - NIFTY 2026 chains;
  - forward paper tickets, 0 of 20 so far.
