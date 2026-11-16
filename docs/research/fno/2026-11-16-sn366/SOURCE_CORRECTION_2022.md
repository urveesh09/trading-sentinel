# SN366: the 2022 exam's source correction (Nov 16, 2026)

**The fault.** N09's `vol_table()` (the volatility reading behind size by volatility and N11's stand-aside) reads daily bars from its own two fixed files, `fno-n08/_local/daily-2023.json` and `fno-complements/_local/daily-2026.json`. Those files hold Breeze daily rows for 2019 – Mar 2020 and from 2022 on, and nothing for Apr 2020 – Dec 2021. The exam harness repointed N08's trend-gate bars (`lab_gap.DAILY`) to the 2022 point but did not repoint `n09_lab.DAILY_SOURCES`. So every 2022 reading ran across a 21-month hole:
- only 112 of 242 sessions had a reading at all;
- no day was "volatility up";
- the "usual" level (a 250-session median) was inflated by the 2020 crash.

**How it was found.** The first opening's output (`results-sn366-exam-2022-WIRING-FAULT.json`, committed as recorded) showed three things at odds with the sheet's own expectation that the stand-aside "may barely fire" in high-volatility 2022:
- N11 took 6 of 53 entries;
- five books (CUSHION, N10 one try, N10 retry, NO_STAND, VOL_CLOCK) were identical;
- size by volatility never raised a lot.

**The proof** (`results-sn366-volcheck.json`, market readings only):

| | faulty sources | the point's contiguous 2020–2022 file |
|---|---:|---:|
| sessions with a reading | 112 of 242 | 242 of 242 |
| volatility-up days | 0 | 115 |
| below 0.9 × usual | 105 | 103 |
| median ATR% / usual | 1.15 / 1.60 | 1.41 / 1.44 |

**The correction.**
- For the 2022 and 2021L points, `Z.DAILY_SOURCES` is the point's own daily file (the bars both sheets require: 250 sessions before the first 2022 session), with the cache cleared.
- No rule, book, threshold or exit changes.
- The paper-evidence trades (N08 one lot, brakes off) do not read this table and are not re-run.

**The second opening.** The exam is replayed once more from an empty folder; the faulty replays are kept in `_local/exam-evals-2022-faulty`. This is disclosed as the exam's second opening, as 2023's was after its own wiring fault. Both receipts stay in the record.
