# Source correction: the first 2023 opening read the wrong daily bars

**What happened.** The first run of the frozen books on NIFTY 2023 (freeze `d534b12`, binding `e8a8d3d`) read 2024's daily-bar file instead of 2023's. Its results are invalid and are kept in `results-first-run-wiring-fault.json`, `first-run-keys-2023.json` and `_local/evals`.

**The fault.** `2026-10-31-fno-complements/lab_gap.py` replaces `features.daily_bars` with a reader of a per-year file chosen when it is imported. My repointing moved `features.DOWNLOAD`, which that reader ignores, so `daily-2024.json` (Jan 3, 2023 to Dec 31, 2024) answered for 2023.

**Its effect.**
- The ADX 30 gate needs 60 earlier daily bars, and that file starts in 2023. So it had no reading before Mar 31, 2023, and no strategy traded from Jan 2 to Mar 30.
- After that the ADX came from a much shorter history than intended.
- The later bars in that file were never read as earlier bars for any 2023 session, so nothing looked ahead.

**Why the control missed it.** The 2025 wiring test wrote to the same results folder as the 2025 parity run. The runner reuses a saved result with the same key, so the test replayed nothing and passed on saved files. That was my error.

**How it was found.** The first scores looked wrong: every book near -Rs 38,000, a 16% win rate, and no trade before Mar 31. Tracing the decisions showed signals firing but no gate open.

**The first run's figures, for the record.** Fresh Rs 2.5 lakh, invalid:

| Book | 2023 net | Largest closed fall |
|---|---:|---:|
| N03 | -39,204 | 15.68% |
| N04 | -39,036 | 15.61% |
| N05 | -37,745 | 15.37% |
| N07 | -38,198 | 15.28% |
| N08 | -37,648 | 15.06% |

**What changed.**
- `n08_lab.py` points lab_gap's own reader at the year's daily file. That file is built from the sealed 2023 mirror, in the format every other year uses.
- `exam_2023.py` refuses to run unless the daily bars end with the year and every session has a trend reading.
- 2023 results go to a new folder, so the first run's files can't be reused.
- The wiring test runs in its own folder, must start empty, and fails if any result wasn't really replayed.

**What did not change.** No book, no rule, no threshold, no sealed 2023 dataset. `freeze-v2.json` asserts that its books and rule equal `freeze.json`'s, and `freeze.json` is kept.

**The cost.** 2023 was opened once with a fault, and the invalid result was seen before this correction. Since no rule changed after seeing it, the rerun still tests what was frozen, but this is disclosed because it isn't the clean single opening the plan promised.

**Proof of the fix.** The wiring test now replays 2025 from an empty folder through the 2023 route and matches N03, N04, N05 and N07 trade for trade (`parity-repoint-test.json`).
