# N09 plan: small challengers beside a fixed N08

**Owner's request (Nov 1, 2026):** take the auditor's review of N08, use what is good, contradict what isn't, add your own ideas, and develop and test N09.

**Status of this file:** written after the step 1 diagnosis and before any challenger is scored. Research only: no application, configuration, Production, lot-limit or real-money change. N08 stays unchanged as the benchmark.

## What the diagnosis says (one lot, brakes off, four years, 243 trades)

| Finding | Evidence | Effect on the plan |
|---|---|---|
| Losses are direction and failed moves | Wrong direction -1,22,737; moved 0.5R then failed -50,231; good direction but the option didn't pay -8,624; gross positive but costs took it -2,026 | Option response and cost are small. The auditor's option layer can't be the main fix |
| No entry-quality reading separates winners from losers | Close location, bar size, 2-bar push, option response: every t under 1.0 after thresholds from the other three years | The auditor's first choice has weak odds. It is still tested once, because it is cheap and the question deserves an answer |
| Nothing survives the search | Best adjusted p across 30 readings is 0.588 | No filter is added from this table |
| Volatility readings have the strongest pull | ATR %, RV10, premium and IV lead the table; IV points the same way all four years; 2025 is the exception for ATR % | Not a filter, since 2025's low-ATR trades earned. A size rule that never refuses a trade can use it. The noise-area paper reports the same pattern on VIX |
| The market offered big days in 2023 | Days with an open-to-close move above 0.6 ATR: 50 of 193, about the same as the other years | 2023 wasn't short of moves relative to its own ATR; the entries were on the wrong side |
| Option prices don't mark 2023 out | Realised against implied volatility: 0.53, 0.53, 0.53, 0.60. Straddle held 09:45-15:10: -2.1%, +1.0%, -3.0%, +1.1% | A "cheap options" gate wouldn't have helped: 2023 looks like 2025 |
| The cut data barely reaches N08 | The four cut sessions hold one N08 trade, +Rs 1,059 on Jan 31, 2025 | `repair-ceiling` is not a precondition, and today's allowance is used up anyway |
| One lot survives 2023 slowly | One lot, no brakes, one account: lowest Rs 2,07,070, ends 2026 at Rs 3,67,877 | The account problem is larger than any entry filter. See below |

## Where this agrees with the auditor

- N08 stays fixed; the challengers are frozen before they are scored.
- Equal-size comparisons first, sizing last.
- The two-lot morning rule goes: a time of day alone is no reason for more money, and it failed on 2023.
- Continuous-account results and the permanent halt are measured.
- All four years are development evidence. Untouched history stays closed until the rules are frozen.

## Where this disagrees

1. **No orchestrator or day-state controller.** Four have failed here on these years: the 09:45 router (O28), the kind-of-day router (O30c/O30m), the N06 selector, and the intraday router. Building a fifth from the same years adds overfitting, not evidence. It comes back only if a strategy shows a state-specific edge on unseen data.
2. **"First resolve the truncated data" is not needed first.** It touches one N08 trade. It remains worth doing on the owner's word.
3. **Entry quality isn't the strongest weakness.** It is what the auditor expected, but the diagnosis shows no signal in it. Direction is the loss, and nothing tested predicts direction.
4. **The biggest money is in the account, not the trade.** N08's +Rs 2,02,284 assumes a fresh Rs 2.5 lakh every year. One real account from January 2023 stops in October 2023 and takes no 2024-26 trade. That gap is larger than anything an entry rule has ever added.

## The challengers, all fixed now

Equal-size view: one lot, brakes off, extra cost in the money path, against N08 in the same view.

| Book | The one change | Why |
|---|---|---|
| ONE\|CONFIRM | SHIPPED, OR20, TPB wait for the next bar to close further in the trade's direction, stop untouched, not stretched. Original stop, target recomputed. EFF keeps its retest | The auditor's entry challenger |
| ONE\|STRUCTURE | EFF, OR20, SHIPPED: from 20 minutes, untrailed, under 0.5R progress, two closes on the wrong side of VWAP: exit. TPB excluded, because cutting it cost Rs 46,065 | The auditor's exit challenger, deterioration half. N08 already has the wider trail |
| ONE\|D65, ONE\|D75 | Target option delta 0.65 or 0.75 instead of 0.55 | Mine. Strike choice has never been tested. Less time value at risk per point of move. Next-week expiry can't be tested: the data holds the nearest weekly only |
| ONE\|NOISE_TEXTBOOK | Zarattini, Aziz and Barbon's noise-area momentum alone, with no stretch rule | Mine. A complement with outside evidence, whose boundary adapts to recent moves by itself. Not fitted here |
| ONE\|NOISE_HOUSE | The same, obeying the stretch rule | So it can sit beside the others |
| ONE\|N08+NOISE | N08 with NOISE_HOUSE as the last member | Its contribution in a shared book |

**Noise-area rules, from the paper:** sigma at a time of day is the average of |close / open - 1| at that time over the last 14 sessions (10 accepted, because holidays shorten the replay's window). Upper = max(open, previous close) x (1 + sigma), Lower = min(open, previous close) x (1 - sigma). Decisions at half-hour marks, moved to a 09:15 open: the bars closing 09:45, 10:15 and so on. Long above Upper, short below Lower. Trail at the marks only: long exits below max(Upper, VWAP), short above min(Lower, VWAP). Kept from the house: the opposite boundary as the hard stop, the 25% premium backstop, 15:10 close, entry window, caps. The paper's daily volatility sizing isn't used: one lot.

**Sizing, full cash path, fresh Rs 2.5 lakh a year, today's brakes:**

| Book | Change from N08 |
|---|---|
| CASH\|NO_E | Low-day TPB stays one lot: the two-lot morning rule removed |
| CASH\|S_VOL | Two lots only when yesterday's daily ATR % is at or above its median of the past 250 sessions, one lot otherwise, for every strategy. Never refuses a trade. No morning rule |

**The account, one account from January 2023:** each of N08 and N09, as it is and with two ways to start again after the 15% stop. Floor resets to 85% of equity at the restart.

| Arm | Rule |
|---|---|
| ANNUAL | Start again at the next calendar year |
| SHADOW | The same rules keep trading on paper at one lot; start again when the last 20 paper trades together made money |

## Rules, fixed now

**A challenger joins N09 if, against N08 at one lot, it passes all of:**

1. 2023 net at or above N08's.
2. Four-year net higher, and four-year R higher. R is net divided by delta x stop distance x quantity, so a bigger delta can't win by size alone.
3. Net higher in at least 3 of 4 years.
4. Worst day no more than 10% larger.
5. Net gain still positive after removing its 5 most helpful days.
6. Paired weekly t of at least 1.0. This is a sign, not proof.

The noise member also needs NOISE_HOUSE alone to make money in 2023, since a complement has to earn where N08 struggles. If both deltas pass, the higher four-year R is used.

**Sizing:** N09 never uses the morning rule. S_VOL is used if its 2023 net is at or above N08's, its four-year total is at or above CASH|NO_E's, and its worst fall in 2024-26 is no more than 1 percentage point above N08's. Otherwise CASH|NO_E.

**N09 is N08 without the morning rule, plus whatever passes.** `analyze_panel.py panel` writes `composition.json`, which is committed before N09 is replayed. Nothing is hand-picked.

**Verdict on N09 against N08. It becomes the research lead only if all pass:**

1. One lot: four-year net above N08's, and 2023 at or above N08's.
2. Fresh years: four-year total at least 85% of N08's, so the profit given up is bounded and shown.
3. Fresh years: 2023 net at or above N08's.
4. Worst trade and worst day no larger than N08's.
5. One account from January 2023, by the better account rule that isn't chosen after seeing N09's own path: SHADOW is primary; ends above N08's unchanged account.
6. Four-year total above zero at double the assumed extra cost.
7. Probability of backtest overfitting, Bailey et al.'s CSCV on weekly results, under 0.5 across N08's 81 search books plus the challengers.
8. Four-year total above zero without its five best trades.

**Even a pass changes nothing.** N09 would still be a seen-year lead. Next: NIFTY 2022 on the owner's login as a one-time exam, then a forward shadow beside N04, N05, N07 and N08, then real fills. The owner decides anything else. No profitability claim comes from replays.

## What each result will report

Every challenger: new winners, missed winners, avoided losses and extra costs against N08; net by year; trades; falls. Failures stay in the record.

## Files and contracts

- `diagnose.py`, `diagnose_tables.py`, `diagnosis.json`: step 1.
- `n09_rules.py`: pure rules. `n09_lab.py`: patches on the unchanged replay stack. `test_n09.py`: rule edges.
- `n09_lab.py parity`: every N09 path on with nothing changed equals N08, trade for trade, on all four years.
- `analyze_panel.py`: scoring, composition, verdict, overfitting estimate. Frozen with the rest.
- `freeze.json`: source hashes and book definitions, committed before the panel runs.

## Rollout and rollback

Dev research only, nothing to roll back. N09 is not in the engine. Production stays c97cb8c. PR #126 is untouched. The Nov 2 real-money test isn't affected by any of this.

## Sources

- Zarattini, Aziz, Barbon, Beat the Market: https://concretumgroup.com/beat-the-market-an-effective-intraday-momentum-strategy-for-sp500-etf-spy/
- Bailey, Borwein, Lopez de Prado, Zhu, The Probability of Backtest Overfitting: https://papers.ssrn.com/abstract=2326253
