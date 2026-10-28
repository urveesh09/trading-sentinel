# O28 regime router: under what conditions did the best F&O strategies win, and does switching them by condition help?

Research only. No runtime module imports this folder, and nothing here can place an order. All 29 sessions (Sep 10 – Oct 26) were already seen by earlier studies.

## The owner's question (Oct 28)

> "The strategy of trend day vwap pullback and the other agents efficiency break and the other most successful strategies that we had. Can you identify under what kind of market condition or market trend or other parameter? Was it that was there when the strategy specifically won? Is there any way for us to identify that? Maybe if that is so then we can make a conditional thing where if that condition is met, then the specific strategy for that condition be deployed … test one time for how like you did earlier for the 20ish days … ensure correctness"

## Answer

1. **When did they win? On trend days.** A trend day here means the session closed at least half its range away from its open. 18 of the 29 sessions were trend days.
   - TPB made ₹16,808 of its ₹17,347 on them.
   - EFF made ₹27,596 of ₹31,063.
   - OR20 made ₹21,141 of ₹30,567.
   - The shipped break split about evenly (₹5,955 against ₹4,846).
2. **Can it be seen early? Only partly, and not with proof.**
   - The best sign at 09:45 is an **opening drive**: the first 30 minutes move efficiently one way.
     - 11 of the 14 drive mornings became trend days, against 7 of the 15 other mornings.
     - On drive mornings, EFF made ₹34,398 against −₹3,335 on the rest, and OR20 made ₹23,246 against ₹7,321.
     - For those two, the gap points the same way in both halves of the period.
   - After correcting for the 20 condition/strategy pairs tested, even the best one is not statistically reliable (EFF on drive mornings: p = 0.008 raw, 0.15 corrected).
   - The other four signs pointed different ways in different weeks. These were the opening-range width, a narrow previous day, the gap and the 5-day trend.
   - The system's own regime label was "elevated" on 25 of the 29 days, so it cannot separate days.
3. **Did deploying each strategy only under its condition help? No, not on this test.**
   - The walk-forward router learned its conditions from earlier sessions only. On the 16 sessions it had not seen, it made **+₹20,896**.
   - Running the four strategies together, always on, made **+₹33,662** on the same sessions.
   - The router lost to that in all 3 folds. It also scored below 59% of 200 routers whose conditions were picked at random.
   - The literature-based opening-drive router, fixed in advance, made +₹33,828: the same money with 18 trades instead of 24.
   - Verdict under the frozen rule: **`CONDITIONS_NOT_SHOWN_TO_ADD_VALUE`**.
4. **What did help on these days was diversification, not switching.**
   - The four strategies win on different days. Their daily results correlate between −0.22 and +0.32.
   - So running them together beat each one alone on the held-out sessions: OR20 alone +₹29,287, EFF +₹20,831, shipped +₹9,528, TPB +₹8,530.
   - This is optimistic too, because each strategy was chosen on some of these sessions (TPB on all 29). It is a forward-test candidate, not a finding.
5. **The size of the prize.** Picking the best strategy for each day with hindsight would have made about +₹49,793 on the held-out sessions (approximate, from each strategy's own day results), against +₹33,662 for running all four. None of the morning signs captures that gap.

## What was tested

**Components.** Each runs exactly as it was studied, and the run aborts unless each one, routed alone, reproduces its own stored trades:

| Component | What it is | Its own exits |
| --- | --- | --- |
| `SHIPPED` | the shipped 30-minute opening-range break (CURRENT) | live: profit lock, 45-minute time stop, 1.0-ATR trail |
| `OR20` | O27 grid OR20 break without the EMA check | late lock (0.8R), 75-minute time stop, 1.5-ATR trail |
| `EFF` | the O27e efficiency-break finalist (`ed0d136bdd80ee89`) | no lock, 60-minute time stop, 1.5-ATR trail |
| `TPB` | the O27f trend-day VWAP pullback (the live shadow `FNO_TREND_PULLBACK`) | no lock, 120-minute time stop, 2-ATR trail |

**Conditions.** Each is known at 09:45, from today's 09:15–09:40 bars and earlier sessions only. Each is split HIGH/LOW at the median of the previous 20 sessions' values:

| Feature | Meaning | Source of the idea |
| --- | --- | --- |
| `or_width` | 09:15–09:45 range / mean range of the previous 5 sessions | narrow initial balance → trend-day potential (Market Profile) |
| `open_drive` | \|09:40 close − 09:15 open\| / path of the six bars | open-drive conviction (Market Profile open types) |
| `nr` | previous session's range / mean of the 5 before it | Crabel NR4/NR7: contraction → expansion |
| `gap` | \|open − previous close\| / mean range of the previous 5 sessions | gap-and-go versus gap-fill |
| `trend5` | 5-session efficiency of daily closes | multi-day trend versus chop (Kaufman efficiency ratio) |

**Routers.** A router gives each component one option: ALWAYS, NEVER, or one condition (12 options).
- Every router is replayed once over all 29 sessions through the shipped single-leg book. That means one pool, one set of brakes, 3 trades a day and the premium cap, with each leg keeping its own component's exits.
- A window's result is a slice of that one path.
- **Walk-forward:** in each fold, for each component separately, it picks the option whose routed-alone path earned the most on that fold's training sessions after removing the best day.
  - Ties go to ALWAYS, then NEVER, then the conditions in declared order.
  - The folds are the anchored O27f ones: F1 trains Sep 10–30 and tests Oct 1–9; F2 trains to Oct 9 and tests Oct 12–16; F3 trains to Oct 16 and tests Oct 19–26.
- **Literature routers, fixed in advance:** the three breakouts are on only when the opening range is narrow (`THEORY_IB`), the opening drive is strong (`THEORY_DRIVE`), or the previous day was narrow (`THEORY_NR`). TPB stays always on, because it already waits for a trend day.
- **Controls:**
  - running all four always (`UNION`) and each component alone;
  - 200 random routers (each component's option drawn uniformly, seeded);
  - the hindsight best per day, which is approximate and not a book replay.

## Results

### Held-out sessions (F1 + F2 + F3 tests, 16 sessions)

| Router | Trades | Net ₹ | F1 (6) | F2 (5) | F3 (5) |
| --- | ---: | ---: | ---: | ---: | ---: |
| **Walk-forward router** | 16 | **+20,896** | +4,325 | −831 | +17,402 |
| UNION: all four, always on | 24 | +33,662 | +9,727 | +2,973 | +20,962 |
| THEORY_DRIVE | 18 | +33,828 | +9,192 | +2,973 | +21,664 |
| THEORY_NR | 16 | +33,169 | +7,438 | +4,068 | +21,664 |
| THEORY_IB | 20 | +28,688 | +3,658 | +4,068 | +20,962 |
| OR20 alone | 10 | +29,287 | +9,985 | −831 | +20,132 |
| EFF alone | 19 | +20,831 | +1,960 | +13,375 | +5,495 |
| SHIPPED alone | 4 | +9,528 | +6,013 | +3,515 | 0 |
| TPB alone | 7 | +8,530 | +2,798 | 0 | +5,732 |
| 200 random routers | — | median +23,590; 90th percentile +36,248; 93% positive; range −5,829 to +86,194 | | | |
| Hindsight best per day (approx.) | — | +49,793 | | | |

**The walk-forward picks changed from fold to fold**, which is a sign of noise:

| Fold | SHIPPED | OR20 | EFF | TPB |
| --- | --- | --- | --- | --- |
| F1 | nr:HIGH | trend5:HIGH | gap:HIGH | open_drive:HIGH |
| F2 | nr:HIGH | ALWAYS | gap:HIGH | open_drive:HIGH |
| F3 | ALWAYS | trend5:HIGH | open_drive:HIGH | open_drive:HIGH |
| FINAL (all 29) | ALWAYS | ALWAYS | open_drive:HIGH | ALWAYS |

**Frozen verdict:** `CONDITIONS_NOT_SHOWN_TO_ADD_VALUE`. The router did beat zero and SHIPPED. It failed three checks:
- it did not beat UNION (+₹20,896 against +₹33,662);
- it did not match UNION in 2 of the 3 folds (it lost all three);
- it did not reach the random routers' 90th percentile (it beat only 41% of them).

### All 29 sessions (in-sample; every component was chosen on some of these days)

| Router | Trades | Net ₹ | Net without best day | Max DD | Green / red days | Green / red weeks |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| UNION | 49 | +40,405 | +30,448 | 5,941 | 11 / 9 | 6 / 2 |
| THEORY_DRIVE | 32 | +44,170 | +33,642 | 8,007 | 9 / 4 | 7 / 0 |
| THEORY_NR | 32 | +41,137 | +30,610 | 8,007 | 9 / 5 | 6 / 2 |
| THEORY_IB | 32 | +39,432 | +29,607 | 5,941 | 11 / 4 | 7 / 0 |
| FINAL router (chosen on these same days) | 42 | +46,299 | +34,685 | 4,153 | 11 / 8 | 7 / 1 |
| SHIPPED alone | 13 | +10,801 | +3,693 | 1,991 | 6 / 4 | 3 / 3 |
| OR20 alone | 19 | +30,567 | +21,117 | 3,423 | 10 / 5 | 5 / 2 |
| EFF alone | 38 | +31,063 | +22,656 | 6,749 | 12 / 7 | 4 / 4 |
| TPB alone | 14 | +17,347 | +11,627 | 3,418 | 8 / 1 | 6 / 0 |

### Under which morning condition each strategy made its money (29 sessions, each strategy alone)

Each cell is net ₹ on HIGH days / LOW days, then the permutation p-value of the mean daily difference. Every Holm-corrected p is 1.0 except EFF × open_drive (0.15).

| Strategy | or_width | open_drive | nr | gap | trend5 |
| --- | --- | --- | --- | --- | --- |
| SHIPPED | 1,619 / 9,182 (0.42) | 5,352 / 5,449 (0.97) | 9,624 / 1,177 (0.47) | 7,484 / 3,318 (0.54) | 6,307 / 4,494 (0.62) |
| OR20 | 6,989 / 23,578 (0.26) | **23,246 / 7,321** (0.27) | 11,635 / 18,932 (0.49) | 13,181 / 17,386 (0.95) | 13,710 / 16,857 (0.68) |
| EFF | 10,488 / 20,575 (0.48) | **34,398 / −3,335** (0.008) | 5,270 / 25,793 (0.12) | 22,195 / 8,868 (0.22) | 6,072 / 24,991 (0.54) |
| TPB | 8,056 / 9,292 (0.83) | 14,349 / 2,998 (0.18) | 4,994 / 12,353 (0.30) | 10,606 / 6,742 (0.47) | 8,082 / 9,266 (0.67) |

**Same direction in both halves** (post hoc, added after the verdict; HIGH−LOW mean day, Sep 10 – Oct 9 | Oct 12 – 26):
- open_drive: OR20 (+792 | +1,804) and EFF (+1,666 | +4,519) agree in both halves; TPB (+1,754 | −931) and SHIPPED (−341 | +703) flip.
- narrow opening range was better in both halves for SHIPPED and EFF (small amounts).
- a narrow previous day was better for EFF in both halves.
- a trending previous week was better for OR20 in both halves.
- Everything else flips between halves.

**Did 09:45 foresee the trend day?** This counts hindsight trend days among each side's mornings:

| Feature | HIGH side | LOW side |
| --- | --- | --- |
| open_drive | 11 of 14 | 7 of 15 |
| or_width | 10 of 15 | 8 of 14 (opposite to the Market Profile idea) |
| nr | 9 of 16 | 9 of 13 |
| gap | 6 of 12 | 12 of 17 |
| trend5 | 4 of 10 | 14 of 19 |

**The system's regime label at 09:40** was REGIME_2_ELEVATED on 25 days, NORMAL on 3 and CRISIS on 1. It is not a usable separator on this period.

**How differently the strategies' days go** (Spearman correlation of daily net):

| Pair | Correlation |
| --- | ---: |
| SHIPPED ~ OR20 | 0.23 |
| SHIPPED ~ EFF | −0.08 |
| SHIPPED ~ TPB | 0.32 |
| OR20 ~ EFF | 0.23 |
| OR20 ~ TPB | 0.10 |
| EFF ~ TPB | −0.22 |

## Correctness

- **Parity gate (in the run):** each component routed alone reproduced its own stored study path exactly, on bar, contract, entry and exit times and prices, exit reason and net:
  - SHIPPED 13 trades, ₹10,801.09;
  - OR20 20 records including one unresolved, ₹30,566.80;
  - EFF 38, ₹31,063.32;
  - TPB 14, ₹17,347.49.
- **The router uses the shipped book unchanged.** The router only answers the book's own signal-variant call. The shipped `_entry` and `_manage` run unmodified, and each leg is managed alone with its component's exit overrides. A test proves two legs from different components get different exits.
- **Causality:** a test recomputes the 09:45 conditions on 6 dates with every later bar deleted, and gets identical values, thresholds and sides. The router code never reads the hindsight table.
- **Signal cache:** every component's signal was precomputed at every entry tick (all 29 sessions), and 0 bars gave a different answer at a later tick. All 252 replays found every signal in the cache (0 misses).
- **The contract** behind the conditions is the book's own front future on all 29 sessions (a test).
- **The design was frozen and pushed before scoring** (`728cdf8`). `run` refuses to start unless the freeze is committed and every bound input (engine sources, both earlier labs, the component reference files, the dataset and the F&O settings) is unchanged.
- **Tests:** `test_router.py` passes 15. Run from `python-engine`:

  ```
  winvenv/Scripts/python.exe -m pytest ../docs/research/fno/2026-10-28-regime-router/test_router.py -q -p no:cacheprovider
  ```

## Limits

- 29 sessions, and very few trades per condition (often 5–20). Only a large, consistent effect could show up, and none did.
- All sessions were seen, and every component was itself chosen on some of them (TPB on all 29; OR20 and EFF on Sep 10 – Oct 9). That flatters UNION and every router alike. What this test isolates is what routing adds on top, and that is nothing measurable here.
- The conditions are day-level, read once at 09:45. Intraday regime changes are not routed (TPB already reads its own trend condition at 11:30).
- NIFTY expiry days have no entries in the book, so they count as flat days on both sides of every split.
- India VIX is not in the archive, so it could not be tested.
- The hindsight-best figure is approximate. It sums each strategy's own day results, which were not replayed as one book.

## What this means

- **No regime switch goes into the system.** On this evidence it would have lowered profit.
- The one sign worth watching is the **opening drive** for the two breakout strategies (EFF and OR20). It is not proven.
- **The forward candidates are `UNION` and `THEORY_DRIVE`** (all four strategies, with the breakouts gated by the opening drive). They are written in this commit before the Oct 28 open, so any forward test can count Oct 28 as unseen.
- Adding them to a forward panel needs the owner's go-ahead. It would be research only: the proving-week paper and live rules stay unchanged.

## Reproduce

From `python-engine` (the study refuses to run if any bound input changed; reproduce from commit `728cdf8`):

```
winvenv/Scripts/python.exe ../docs/research/fno/2026-10-28-regime-router/router.py run --jobs 8   # ~8 minutes
winvenv/Scripts/python.exe ../docs/research/fno/2026-10-28-regime-router/analyze.py              # results.json
```

Sources consulted for the conditions:
- [LuxAlgo day-type taxonomy](https://www.luxalgo.com/library/concept/day-type-taxonomy/)
- [LuxAlgo open types](https://www.luxalgo.com/library/concept/open-types.md)
- [LuxAlgo NR4/NR7](https://www.luxalgo.com/library/concept/nr4-nr7-narrow-range-bars.md)
- [Oxford Strategy on Crabel's opening range breakout](https://oxfordstrat.com/?p=3707)
- [TradingView efficiency-ratio regime detector](https://es.tradingview.com/scripts/trend-strength/)

These are practitioner sources. No result here relies on their claims.
