# O31b and O31c: the final book at today's lot limits - technical summary

Research only. No runtime change, nothing deployed. Plain write-up: [`docs/FNO_FINAL_STRATEGY_2026-10-31.md`](../../../FNO_FINAL_STRATEGY_2026-10-31.md).

**O31b** (`lab_o.py`, `analyze_o.py`, `freeze.json`, `results.json`; freeze `9977e71`, results `4d7b100`). 48 books per year: BASE (the four strategies + rule at today's limits), BASE|AS, 46 one-change variants. The freeze commit message says 47; the frozen file has 48. 150 replays with the three carried runs.
- `improves`: none. `every_year_better`: none. `safer`: `ADX|30`. `no_effect`: `LOCK|off`, `BRAKES|no_total_stop`.
- Selection luck: the pick on two years lost to BASE on the third, all three times.
- Lots: `BASE` (today's limit) is the best within the 15% fall limit.
- Carried: BASE 3,09,155, fall 11.9%; BASE|AS 3,87,347, fall 9.9%; `SKIP|none` 2,10,834, fall 19.7%, last trade 2025-01-03.

**O31c** (`lab_o2.py`, `analyze_o2.py`, `freeze-c.json`, `results-c.json`; freeze `dca512d`). Found by looking at O31b. 83 books per year: a 6 x 6 surface (ADX x rule limit, one lot, brakes off), exact neighbours at today's limits, ADX 30 without cost, 20 random books at ADX 25 and 30. 253 replays with the carried runs.
- `rule_plateau`: false (limit 0.65 is -24,493 against no rule -23,677).
- `adx_plateau`: false (ADX 28 -2,456 in 2024; ADX 27's fall 38,045 against 32,907).
- `final`: the book as live today; both on paper only.
- Random: real A30|S50 +43,170, random median -32,320, best +11. `market_effect` true: random gains +14,563 from ADX 30, real -903.
- Carried A30: 2,99,454, fall 7.8%; without the cost 3,54,029, fall 6.0%.

**`report_o.py`** (`report.json`) is descriptive and written after scoring: the stretch buckets, the rule against no rule by cell (28 of 30), the candidate books in detail, one lot on the real-money terms.

**Checks:** `check_book` 0 problems in 403 replays; parity asserted against the 2024 exam and O30r figures; tests `test_lab_o.py` (6) and `test_lab_o2.py` (5) pass.

**Caveats:**
- All three years are seen; the candidate was chosen after looking.
- The surface is one lot with brakes off; exact rows use today's limits. They are not the same numbers.
- `BASE`'s `open_at_session_end`: see `results.json`; half-day legs have no rupee result, as in the exam.
- Today's settings were partly chosen on these years, so they are bound to look good against their neighbours.

**Reproduce:** the commands are in `lab_o.py`'s and `lab_o2.py`'s docstrings; run 2024, then 2025, then 2026 (the carried runs read the earlier years). `sources` in each freeze refuses a changed engine; use a worktree at the freeze commit.

**The forward check** is fixed in the write-up's section 6.
