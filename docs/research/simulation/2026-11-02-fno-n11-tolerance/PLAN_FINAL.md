# N11T final: the amount, and the rule the engine will follow. Plan, written before its run

November 2, 2026. Dev only. The owner: "you can put the tolerance on paper if you want, and you can even change the amount of tolerance to any optimal amount ... do that in development right now, and after the day end, I will instruct you what to do."

All four years are seen and this choice was made after reading the map below, so this is discipline, not an exam.

## The amount: Rs 6,250, not Rs 7,500

The fifth screen's map, four-year totals, before the plan-wording fix. N11 earns 2,55,365.

| Limit | k 1.5 | k 1.75 | k 2.0 |
|---|---:|---:|---:|
| 5,500 | 2,69,503 | 2,57,663 | 2,53,749 |
| 6,250 | 2,68,749 | **2,74,745** | 2,63,741 |
| 7,000 | 2,71,674 | 2,74,853 | 2,78,787 |
| 7,500 | 2,69,709 | 2,72,123 | 2,75,036 |

**Why Rs 6,250 at k 1.75:**

1. **The limit is the one thing here that is a hard fact about risk.** Which trades fall inside the map is hindsight, but a smaller limit plans to lose less on every raised trade, whatever the market does.
2. **It gives up nothing for that.** Rs 6,250 earns the same as Rs 7,000 and more than Rs 7,500.
3. **It is not a number off the map.** It is the book's existing rupee limit, `FNO_MAX_LOSS_PER_TRADE`, and it was a neighbour fixed in the first freeze.
4. **Its worst day and worst trade match N11's** (-5,641 and -4,559). That part is partly luck: it leaves out losing second lots of -2,062, -2,913 and -1,021, and also a +6,105 winner.

**Why not the highest cell, Rs 7,000 at k 2.0 (2,78,787):** it adds Rs 750 of planned loss per raised trade for a Rs 4,042 lead that comes from which of about 15 trades fall inside. It is also at the edge of the tested range of k. That is choosing the peak.

**What this choice is weak on:** the row is bumpier than Rs 7,000's. k 2.0 at this limit earns 2,63,741, so the good result depends on which trades qualify. The check below reports this.

## The rule, in the words the code must follow

N11, unchanged, plus one thing. A NIFTY paper trade that N11 already takes at one lot may take a second lot when all of these hold, each known at entry:

1. N11 allows two lots on this trade: volatility at or above usual, no realised loss today, the low-day morning clock.
2. The last 20 closed paper trades, exits strictly before now, made money.
3. **Either** two lots at the normal 25% backstop fit the budget, **or** 1.75 x |delta| x the stop's distance fits inside the premium points the limit allows.
4. The 15% open-premium cap and the structural cap still pass at two lots.

**The budget in point 3** is the larger of the limit and what the stance already allows (`min(pool x 2% x stance, Rs 6,250 x stance)`). **The limit** is Rs 6,250 x min(1, stance): a drawdown shrinks it and a winning streak never lifts it.

**The backstop** then sits where the whole trade, fees and declared stress included, is inside the limit, and never lower than the normal 25% backstop. The underlying stop, target, trail and clocks don't change. The earned lot keeps its own Rs 5,000 charge.

**A gap I found in my earlier plan, on top of the fees gap already disclosed:** `PLAN.md` says every second lot needs the stop-distance check. The tested code only asks it when two lots at 25% don't already fit. A cheap option with an ordinary backstop needs no such check, so the words above now say what was tested. `n11t_strict.py` (the fees fix) stays in force.

## Checks, fixed before this run

The book is `FINAL` in `n11t_final.py`: plan wording, Rs 6,250, k 1.75.

**A. Is it better, and inside the bar?** All must hold:

1. Four-year sum above N11's 2,55,365.
2. Worst day no larger than 6,127, the bar set for N11.
3. Biggest yearly fall no larger than N11's 6.89%.
4. Worst trade no larger than 6,250.
5. Every year at or above N11's, within Rs 500.

**B. Is it sturdy?** All must hold:

6. Double cost above N11's 1,99,622.
7. Without its own top five above N11's 1,25,490.
8. Neighbours: k 1.5, k 2.0, limit 5,500, limit 7,000, all on plan wording. Each above 2,55,365, worst day no larger than 6,127.
9. One account at extra cost 195, 198, 199, 200, 201, 202, 205, 180, 220 and 400: each at or above N11 at the same cost, within 5% of each other from 195 to 205, never near the stop.
10. The audit: on every raised trade, volatility at or above usual, the paper record positive, no realised loss earlier today, planned loss at most Rs 6,250 with fees and stress, and the backstop where the rule puts it.
11. Engine parity: at every planned entry in all four years, the engine's second-lot decision, limit and backstop match this book's, with zero mismatches.

**C. Honest about overfitting.** Reported whatever they say: the placebo, hiding each year, without and with the reversed paper reading, the top three trades' share, and the overfitting estimate over this study's books.

**If a check in A or B fails:** the failure is reported by name. The fallback is Rs 7,000 at k 1.75, then the frozen Rs 7,500 book. A check is never changed to rescue a book.

**Verdict words.** A and B all true: "meets the bar on the seen years". That isn't "proven": the placebo failed for the Rs 7,500 book and I expect no better here.

## Files and contracts

- **Research:** `n11t_final.py`, `driver_final.py`, `test_n11t_final.py`, `parity_final.py`, `audit_final.py`, `score_final.py`, in this folder. The first freeze's files aren't edited.
- **Engine:** `fno_n11.py` (`second_lot`, `second_lot_stop`, `tolerance_limit`, `record_second_lot`, table `fno_n11_second_lot`, a line in the daily report), `fno_orchestrator.py` (paper, NIFTY only), `config.py` (`FNO_N11_TOLERANCE_ENABLED`, `FNO_N11_TOLERANCE_RUPEES`, `FNO_N11_TOLERANCE_STOP_FACTOR`), `tests/test_fno_n11_second_lot.py`.
- **A second lot never costs the trade its first:** if the shared reservation refuses two lots, the entry asks again for one.
- **Real money:** `fno_live_test` reads only the contract from the paper entry, buys one lot and sets its own 25% stop, so neither the second lot nor the tighter backstop reaches it. A second lot uses paper's open-premium room, so a later paper entry can be refused that day, and then the real test wouldn't mirror it. The replay's figures already carry that effect on the paper side.

## Rollout and rollback

Dev and pushed only. Nothing is merged or deployed: the owner decides after the day ends. If deployed, the switch is on by default, as the owner asked for it on paper. Off without a release of code: `FNO_N11_TOLERANCE_ENABLED=false` and an engine restart. It adds one table and no other migration.
