# N08: technical summary

Research only. No application, Production, lot-limit or money change. Plain write-up: [`docs/FNO_RESEARCH_N08.md`](../../../FNO_RESEARCH_N08.md).

**Verdict by the frozen rule: N08 fails.** It lost on 2023, so it stays a seen-year lead and does not become the lead research candidate. Its four-year total is above N03, N04, N05 and N07.

## N08

N07 (`NORMAL|PREMIUM_STALL`) plus four changes:

- EFF and OR20 trail at 2 ATR.
- A low-day TPB entered before 12:00 may take up to 2 lots.
- No low-day TPB entry from 14:00.
- `FNO_MAX_LOTS = FNO_MAX_LOTS_PROVEN = 2`.

The book is `n08_book()` in `n08_lab.py`. Rules are in `n08_rules.py`.

## Results

Fresh Rs 2.5 lakh each year, today's brakes, extra cost in the money path. 2026 to Oct 28.

| Book | 2023 | 2024 | 2025 | 2026 | Four years | 2023 brakes off |
|---|---:|---:|---:|---:|---:|---:|
| N03 | -37,802 | 56,192 | 50,090 | 54,153 | 1,22,633 | -57,144 |
| N04 | -38,195 | 51,303 | 54,051 | 77,135 | 1,44,294 | -61,283 |
| N05 | -37,726 | 57,243 | 50,726 | 61,496 | 1,31,739 | -60,709 |
| N07 | -37,719 | 57,982 | 52,023 | 77,135 | 1,49,421 | -60,167 |
| **N08** | **-37,581** | **76,294** | **58,647** | **1,04,924** | **2,02,284** | **-58,321** |

Falls of N08 by year: 15.08%, 2.16%, 4.70%, 2.69%. Worst trade -5,107 (N07 -6,910), worst day -9,720 (N07 -9,482). Paired weekly t against N07: 2023 alone 0.01, four years 1.88.

## Frozen checks

| Check | Result |
|---|---|
| 2023 net above zero | **Fail** |
| 2023 net at or above N07's | Pass, by Rs 138 |
| 2023 fall no larger than N07's | Pass, 15.08% against 15.18% |
| Positive every year | **Fail** |
| Four-year total above N03, N04, N05, N07 | Pass |

## O31e exam (`freeze-2023.json`), same opening

| Book | 2023 net | Fall | Three-year net | Holds? |
|---|---:|---:|---:|---|
| EX\|MAIN | -37,810 | 15.12% | 52,621 | No: net below zero |
| EX\|D\|only_puts_from_25 | -37,553 | 15.28% | 1,24,424 | No: fall above 15% |
| EX\|D\|tpb_puts_closed | -38,133 | 15.47% | 1,40,462 | No |
| EX\|D\|puts_from_25 | -38,490 | 15.66% | 1,09,414 | No |
| EX\|C\|puts_only | -31,921 | 12.77% | 63,185 | Yes by the letter: lost less than main |
| EX\|C\|no_eff | -28,339 | 11.34% | 66,022 | Yes by the letter: lost less than main |

The rule's recommendation concerns only the two named put books, and neither holds: **the main book stays.** Its own "holds" test fails too.

## Why 2023 went this way (`explain_2023.py`, `explain-2023.json`, after the verdict)

| Year | NIFTY | Median daily ATR | N07 trades, brakes off | Win % | Gross-positive % | Net | Random entries, median of 20 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | +19.4% | 0.82% | 94 | 23 | 29 | -60,167 | -67,534 |
| 2024 | +9.0% | 1.05% | 34 | 50 | 56 | 52,153 | -57,820 |
| 2025 | +10.1% | 0.93% | 87 | 47 | 51 | 43,303 | -81,353 |
| 2026 | -13.2% | 1.23% | 56 | 50 | 55 | 59,899 | -40,059 |

- **The year was not unusually hard for random entries, and N07 was barely better than them.** In 2024-26 N07 beats the random median by about Rs 1,00,000 or more (Rs 99,958 in 2026). In 2023 it beats it by Rs 7,367. Random books run at one lot and N07 at its own sizes, so this is a rough yardstick, but the entries had no visible edge.
- **Both directions lost.** Low-day puts: 19 trades, 5 wins, -14,395 for N07. EFF, TPB and OR20 calls in the main book also lost. It isn't only the put bias.
- **No simple volatility guard explains it.** At ATR 0.7-0.85%, N07 made -33,439 in 2023 and +15,295 in 2025. Only ATR above 1.25% is positive in 2023, on 9 trades.
- **Smaller moves make costs weigh more.** Median cost was 16% of a stop's worth in 2023 against 9-10% in 2024-26. That is one cause, not the whole: only 29% of trades were positive even before costs.

**The 15% halt** is a fixed floor at Rs 2,12,500 and never lifts by itself. It saved 2023 from a 28% fall. But one account started in January 2023 stops for good: N07 after Jul 12, 2023 and N08 after Oct 3, 2023, ending near Rs 2,12,000 and taking no 2024-26 trade (`one_account` in `explain-2023.json`).

## What the search found on 2024-26

81 books. All are in `screen-1..4.json`.

- **Giving back profit is small.** 66 of 85 losers never reached 0.5R and lost Rs 1,25,199; the other 19 lost Rs 19,899.
- **Profit locks:** best +4,214, and worse in 2025.
- **Half-clock stall on TPB:** -46,065.
- **Adding lots to winners:** -12,549.
- **Low-day trades with the daily trend:** -47,545 and -83,700.
- **Moving the 15:10 close:** every other time worse.
- **Event days:** 7 trades, +4,078. No rule.
- **The first low-day TPB of the day, 11:30-12:00:** 27 trades, +48,261, positive every year. On 2023 N08's morning low-day trades made 15 trades, 3 wins, -16,316: **this edge failed out of sample.**
- **Nearby settings** all beat N07 by Rs 33,099-57,345. N08 also beats N07 at no extra cost (2,82,446 against 2,22,418) and double (2,01,677 against 1,25,952), on 2024-26.
- **Concentration:** five trades supply 44,312 of N08's 52,724 gain on 2024-26.

## Controls

- N03, N04, N05 and N07 reproduced trade for trade on 2024-26 (`parity-*.json`).
- Every N08 code path on with nothing changed equals N07.
- The 2023 route, aimed at sealed 2025 data from an empty results folder, equals the stored 2025 results (`parity-repoint-test.json`).
- `test_n08.py`: 42 tests.
- `data-binding-2023.json`: 245 sessions, no bad rows, no ceiling hit; hashes committed before replay.
- Trend readings on every 2023 session, from 248 earlier daily bars (`exam-inputs-2023.json`).

## Limits

- **2023 was opened twice.** The first run read the wrong daily bars and is invalid (`SOURCE_CORRECTION.md`). No book or rule changed between the runs.
- All four years are now seen. N08's parts were shaped on 2024-26, so its gain there proves nothing by itself.
- Candle model, lot 65, assumed extra cost. These replays used the cut data from the 1,000-candle ceiling (52 requests, none in 2023).
- N08 is not in the engine. E and L have no engine switch yet.
- Mar 1, 2023 has no option data, so the book can't enter that session.

## Reproduce

`N08_YEAR` chooses the year; `n08_lab.py`, `exam_2023.py` and `after_exam.py` hold the commands in their docstrings. `score_exam.py` and `explain_2023.py` read saved replays. Windows workers re-import the main script, so patches stay at module level.
