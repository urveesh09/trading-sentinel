# N09: technical summary

Research only. No application, Production, lot-limit or money change. Plain write-up: [`docs/FNO_RESEARCH_N09.md`](../../../FNO_RESEARCH_N09.md). Corrections: [`SOURCE_CORRECTION.md`](SOURCE_CORRECTION.md).

**No new entry, exit, option choice or added strategy beat N08.** The book the frozen rule composed (N09A) failed its verdict, and N09B (N08's decisions with size by volatility and a restart) narrowly failed its own. The largest finding is at the account level: a restart after the 15% stop took one account from Rs 2,12,419 to Rs 4,36,635. All of it is on seen years.

## Results

### Fresh Rs 2.5 lakh each year, today's brakes, extra cost in the money path

| Book | 2023 | 2024 | 2025 | 2026 | Four years | Falls % | Worst trade | Worst day |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| N08 | -37,581 | 76,294 | 58,647 | 1,04,924 | 2,02,284 | 15.08 / 2.16 / 4.70 / 2.69 | -5,107 | -9,720 |
| N09A: no morning rule | -38,667 | 65,214 | 46,823 | 85,576 | 1,58,946 | 15.52 / 2.16 / 4.39 / 2.38 | -5,107 | -9,720 |
| S_VOL: size by volatility | -37,974 | 70,317 | 50,442 | 1,08,643 | 1,91,428 | 15.24 / 4.10 / 4.73 / 2.97 | -5,039 | -6,127 |

Brakes off: N08 -58,321 / 76,294 / 55,082 / 93,863 = 1,66,918, S_VOL -29,407 / 72,136 / 47,321 / 95,740 = 1,85,790; 2023 falls 27.83% and 17.82%; worst day -9,720 and -6,978; paired weekly t 1.13. Cost none: N08 2,52,980, S_VOL 2,54,760. Double: N08 1,63,688, S_VOL 1,43,250.

S_VOL's two-lot share of sessions: 8.5%, 86.3%, 35.3%, 84.7%. Its 2023 ran to Dec 26, against N08's Oct 3.

### One lot, brakes off: N08 -37,375 / 45,221 / 46,037 / 63,994 = 1,17,877, R 53.5

| Challenger | 2023 | 2024 | 2025 | 2026 | Four years | R | t against N08 | Gates passed of 6 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CONFIRM | -24,737 | 19,191 | 14,185 | 40,679 | 49,318 | 20.3 | -2.06 | 2 |
| STRUCTURE | -36,454 | 45,045 | 46,300 | 62,923 | 1,17,814 | 54.0 | -0.03 | 2 |
| D65 | -40,366 | 24,900 | 43,353 | 54,196 | 82,083 | 18.4 | -1.25 | 0 |
| D75 | -40,650 | 16,706 | 16,423 | 60,852 | 53,331 | 20.1 | -1.71 | 1 |
| NOISE textbook, corrected | -1,00,124 | 53,838 | -1,01,913 | -80,033 | -2,28,232 | -44.7 | -2.81 | 0 |
| NOISE with stretch rule, corrected | -56,135 | 1,598 | -28,106 | -20,566 | -1,03,209 | -21.6 | -2.38 | 0 |
| N08 + NOISE, corrected | -78,378 | 63,489 | 2,675 | -20,048 | -32,262 | 14.2 | -1.75 | 0 |

**What waiting did (CONFIRM against N08):** missed 49 winners worth Rs 1,48,895, avoided 79 losers worth Rs 1,13,921, added 7 winners worth Rs 10,808 and 19 losers worth Rs 26,506, and the 115 trades kept in both got Rs 17,886 worse. Its 2023 fall was 9.89% against 17.22%, so it does cut risk, but at too high a price. Pairing is same day and direction within 11 minutes.

**Delta:** the 0.65 and 0.75 books take 213 and 128 trades against 243, because the higher premium hits the risk cap. So this answers "within today's risk budget", not delta in general.

### One account from January 2023

| Book | No restart | ANNUAL | SHADOW | Fall % with SHADOW | Worst day with SHADOW |
|---|---:|---:|---:|---:|---:|
| N08 | 2,12,419 | 4,41,234 | **4,36,635** | 15.08 | -9,720 |
| S_VOL | 2,12,026 | 4,18,765 | **4,10,542** | 15.24 | -6,240 |
| N09A | 2,11,333 | 3,93,989 | 3,88,692 | 15.52 | -9,720 |

`audit_account.py` recomputes these from raw trade files: N08 stopped for 99 days and restarted Jan 10, 2024 with the last 20 paper trades at +Rs 4,846.

## Verdicts

| Verdict | Result |
|---|---|
| **N09A** against N08, 8 checks | **Fails** 1 (one lot no better), 2 (79% of N08's total), 3 (2023 worse). Passes 4, 5, 6, 7 and 8 |
| **N09B** as lead, 5 checks | **Fails** 1 (Rs 4,10,542, needed 4,14,803) and 2 (fall 15.24% against 15.08%; its worst day passes). Passes 3, 4 and 5 |
| **Restart on N08**, 3 checks | **Passes.** But the reshuffle checks have little power: see below |
| **Complement**, 50 books on 2023 | **None.** 48 of 50 lost in 2023. The two positive (GAP_REPAIR g2 +5,383, g3 +5,339) fail the other tests |

## The restart under stress (`stress_years.py`, added after the results, not a frozen rule)

N08 at one lot. All 256 orderings of four whole years with repeats, so read differences, not levels.

| Rule | Median end | Worst end | Ends below start |
|---|---:|---:|---:|
| No restart | 3,67,877 | 2,11,290 | 67 of 256 |
| ANNUAL | 3,67,877 | 1,28,867 | 13 |
| SHADOW | 3,67,877 | 1,28,558 | 13 |

SHADOW against no restart: helps 55, hurts 11, same 190; largest gain +1,89,591, largest cost -83,578. 2023 twice then two good years: 2,66,458 against 2,12,136. 2023 three times then 2024: 1,93,390 against 2,12,136. 2023 four times: 1,28,558 against 2,12,136. **Waiting for paper evidence protected little:** SHADOW ended about where ANNUAL did in every case that mattered, and restarted three times inside a run of 2023s.

**A limit in this design:** the floor moves only down, to 85% of equity at a restart, and doesn't rise with later profit. A live version would need that decided.

## Overfitting

Bailey et al.'s CSCV on weekly results, 16 blocks, 12,870 splits, 201 weeks. **Corrected PBO 0.487** on 69 books. The in-sample best lands at the 53rd percentile out of sample. N08 ranks 5th of 69 by total. On purely random books this estimator averages 0.51 to 0.55 (standard deviation about 0.18), so **choosing the best book within N08's family can't be told apart from choosing among random books.** The estimate compares cousins. It doesn't say whether the family has an edge: that comes from the random-entry comparison in N08's report.

## Diagnosis (`diagnose.py`, `diagnose_tables.py`, `diagnosis.json`)

N08, one lot, brakes off, 243 trades.

| Year | Winners | Costs took it | Direction right, option didn't pay | Moved 0.5R then failed | Wrong direction | Net |
|---|---:|---:|---:|---:|---:|---:|
| 2023 | 32,850 (20) | -724 (5) | -1,990 (6) | -24,529 (23) | -42,982 (31) | -37,375 |
| 2024 | 64,052 (15) | -144 (2) | -687 (2) | -4,422 (3) | -13,579 (7) | 45,221 |
| 2025 | 1,07,934 (38) | -589 (3) | -4,561 (5) | -14,517 (12) | -42,229 (21) | 46,037 |
| 2026 | 96,658 (26) | -569 (3) | -1,385 (3) | -6,763 (4) | -23,947 (14) | 63,994 |

- 30 readings known at entry, split at terciles from the other three years, with a max-t permutation across all: best adjusted p 0.588. Entry-quality readings all have |t| under 1.
- Option prices don't mark 2023 out: realised/implied 0.53, 0.53, 0.53, 0.60; straddle 09:45-15:10 -2.1%, +1.0%, -3.0%, +1.1%.
- Days with an open-to-close move above 0.6 ATR: 50 of 193, 55 of 196, 61 of 194, 34 of 160. 2023 wasn't short of moves relative to its own range.

## Controls

- Every N09 code path on with nothing changed equals N08, trade for trade, on all four years (`n09_lab.py parity`).
- The same stack reproduced stored N07 and EX|MAIN results exactly earlier the same day (`compare_four.py`, `compare-four.json`, which also holds the plain four strategies: -37,774 / -38,721 / -37,509 / -38,042 = -1,52,046; on ADX 25 days only, -49,065).
- `test_n09.py` (15) and `test_n09_scoring.py` (8) pass. The scoring tests check the estimator on noise and on a real edge.
- `audit_account.py` recomputes the accounts from raw trades.
- Cut data: the four cut sessions hold one N08 trade, +Rs 1,059 on Jan 31, 2025. `repair-ceiling` wasn't run; today's allowance is used and it needs the owner's word.

## Limits

- All four years are seen. Every result here is a seen-year result, and the supplement is post-hoc.
- Candle model, lot 65, modelled spread, assumed extra cost. Adverse fills can't be measured until real fills exist.
- Only the nearest weekly expiry is in the data, so next-week options can't be tested.
- N09B's parts have no engine switch, and N09 isn't in the engine.

## Reproduce

`N08_YEAR` chooses the year. `n09_lab.py`, `n09_supp.py` and `noise_correction.py` hold the commands in their docstrings. `analyze_panel.py`, `stress_years.py` and `audit_account.py` read saved replays. Files: `PLAN.md`, `PLAN_SUPPLEMENT.md`, `freeze.json`, `composition.json`, `results-*.json`, `pbo.json`, `pbo-corrected.json`.
