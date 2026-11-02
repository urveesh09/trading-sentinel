# N11: plan, written before the frozen run

November 2, 2026. Research only. Dev branch. No application, setting, migration, order, Telegram or Production change. The Rs 12,500-15,000 real-money test isn't touched.

## Where this plan came from

Five development screens (`screen` to `screen5` in `n11_lab.py`, 66 books, all kept and all counted in the overfitting estimate) were run on the four seen years before this was written. So this freeze is discipline, not an exam: every number below was chosen with those years in view. The test that counts is `EXAM_2022_N11.md`, and forward shadow.

**The owner's bar.** Better than N08, N09, N09.1, N10 and N10.1 on profit, with worst day and drawdown as good as the best of them or better.

| Measure | Best of the five | Whose |
|---|---:|---|
| Four-year sum, fresh Rs 2.5 lakh a year | +2,33,275 | N10 retry, N10.1 WATCH_FLAT |
| Worst day | -6,127 | N09, N09.1, N10, N10.1 |
| Biggest fall in a year | 13.13% | N09.1, N10.1 PREMIUM_LOCK |
| Worst trade | -4,559 | N09.1, N10, N10.1 |
| 2023 | -32,684 | N09.1, N10.1 PREMIUM_LOCK |
| Double the assumed cost | +1,68,672 | N10 retry |
| Without own top five winners | +1,06,281 | N10 retry, N10.1 WATCH_FLAT |

## What the screens showed

- **Tried and dropped.** The second lot charged at the stop's expected cost (`true_risk`): about +2,700 and no plateau below k = 1.5, though a rough sum had promised +57,700. Second lot on a good paper record (`evidence`): worst day -7,185 to -9,720. Skip stops closer than 1.25 ATR (`noise_atr`): -10,000 in 2026. Earned lot on one-lot trades (`earn_vol`, `add_any`): loses again. The add only once the trail has locked (`LOCK`): -7,500.
- **Kept.** Four parts, below. The screen's numbers aren't the verdict.
- **The reserve and WATCH go.** Without them the same book earned more and fell less, because the stand-aside does the bad-year work. So the live 15% stop needs no change.

## N11

N08's entries and exits, unchanged, plus:

1. **Size by volatility** (N09.1's VOL_CLOCK, unchanged). Two lots only when yesterday's daily ATR% is at or above its median of the last 250 sessions. N08's morning rule for the low-day TPB stays.
2. **One lot after a loss** (`loss_one`). After a realised loss today, the next trade today takes one lot. It never refuses a trade.
3. **Stand aside** (`stand`, `stand_ratio`). Real entries wait while BOTH hold: yesterday's ATR% is below 0.9 of its usual level, and the last 20 closed one-lot paper trades of N08's own rules, exits strictly before now, sum to zero or less. The paper book keeps trading, so it ends by itself when either reading turns. With fewer than 20 paper trades nothing is known, and nothing waits.
   - 20 is inherited from N09 and N10, not chosen here. 0.9 is the middle of the 0.8-1.0 range, chosen away from the cliff above 1.0: 1.05 costs about Rs 33,000 in 2024. It is not the most profitable point on the map.
4. **The honest earned lot** (`add = HONEST`). On a two-lot trade, at or beyond +1R and before 14:45, one more lot may be bought at the first observation where this fits inside Rs 5,000, scaled down in a drawdown and never up:
   - what the held lots are expected to lose at their current stop: today's bid, less entry delta times the distance to that stop, no lower than their premium backstop, plus fees and stress; plus
   - the new lot's whole 25% backstop, fees and stress.

   The rule is decided afresh at every observation, so the retry that N10's plan left unstated is the written rule here. **The held lots' stops and exits are never touched**, which is where N10.1's PREMIUM_LOCK lost its money. The new lot leaves at the held lots' entry level, at its own 25% backstop, or with them.

Unchanged: lot cap 2 plus the one earned lot, Rs 5,000 per trade, the adaptive stance, two-strike day, the native 15% stop at Rs 2,12,500. No margin, option selling, new strategy, date or side exclusion. The fade on stand-aside days was considered and not tested: nearly all those days are in 2023, so it could only fit one year.

## Checks, fixed before the frozen run

**A. The owner's bar.** All must hold, on the frozen book:

1. Four-year sum above 2,33,275.
2. Worst day no larger than 6,127.
3. Biggest annual fall no larger than 13.13%.
4. Worst trade no larger than 4,559.
5. 2023 no worse than -32,684.

**B. Is it sturdy?** All must hold:

6. Double cost above 1,68,672.
7. Without its own top five above 1,06,281.
8. 2024, 2025 and 2026 all positive, at least two of them at or above N10 retry's.
9. Plateau: ratio 0.85 and 0.95, paper window 15 and 25, add at 0.75R and 1.25R: each above 2,33,275 with worst day no larger than 6,127.
10. One account, no resets, at extra cost 195, 198, 199, 200, 201, 202, 205 (per-lot term 5), 180, 220 and 400: never stuck, each at or above N10 retry at the same cost, and within 5% of each other from 195 to 205.
11. All 256 orderings of whole years at one lot, evidence causal in each ordering: median end at or above WATCH's 3,62,226, and no more ends below the start than WATCH's 13.
12. Parent exits untouched: on any trade in both, the held lots' entry and exit are the same with and without the earned lot.

**C. Honest about overfitting.** Reported whatever they say, and each one is written into the report:

13. The stand-aside placebos, at the frozen settings: same count at random, and the state rotated through time. Check: rotated p at or below 0.10.
14. The fair test the literature asks for: is the paper record persistent at all? Correlation of each 20-trade sum with the next 20, whole stream and without 2023. And does the rule beat simply trading smaller: N10 retry scaled down to N11's fall, by the same arithmetic.
15. Parts by year, each removed in turn.
16. The rule on 50 other strategies' one-lot trades, helped against hurt, with and without 2023, and whether the state marks worse trades than the rest.
17. The overfitting estimate on all books since N08, every N11 screen included, exact duplicates removed. Check: N11's family at or below 0.5.
18. The random-entry control: 10 random books, base against the honest add and against the stand-aside.

**Verdict words.** A and B all true: "meets the owner's bar on the seen years". That is not "proven". Anything false is reported as failed, by name, and the book isn't rescued by changing a check. If C says the edge rests on one year, the report says so in its first lines.

## Files and contracts

Only `docs/research/simulation/2026-11-02-fno-n11/`, `docs/FNO_RESEARCH_N11.md`, the method file, and the ritual sections of `docs/SYSTEM_GUIDE.md`, `docs/NEXT_AGENT_PLAN.md` and `docs/HANDOVER_CHECKLIST.md`. Earlier studies are imported, never edited. No engine file changes, so the atlas stays as it is.

**Identity:** `freeze.json` binds these sources, the frozen books and their keys, and is committed before any frozen phase runs.

**Rollout and rollback.** None: N11 has no engine switch. Going live, or even to forward shadow, is the owner's decision. Rollback is to do nothing.

**Remaining work after this:** `EXAM_2022_N11.md`, the owner's ICICI login for NIFTY 2022, a forward paper shadow.
