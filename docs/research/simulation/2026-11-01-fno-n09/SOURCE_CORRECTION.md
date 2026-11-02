# N09 corrections, disclosed

Every first result stays on record. No book or rule was changed to improve a score, and none of these turned a failure into a pass.

## 1. The noise-area books left the house profit lock on

**What the plan said:** the noise member exits only by its own trail, the premium backstop, its hard stop and the 15:10 close.

**What the frozen code did:** it set the time stop and the trail out of the way but left `FNO_PROFIT_LOCK_ENABLED` on, so 526 of the textbook book's 1,039 trades left by the lock.

**How it was caught:** printing exit reasons before writing the report.

**Fix:** `noise_correction.py` reruns the three books with the lock off, in new keys, and leaves the frozen `n09_lab.py` unedited.

| One lot, four years | First run | As the plan describes |
|---|---:|---:|
| Noise-area alone, textbook | -2,44,378 | -2,28,232 |
| Noise-area alone, stretch rule | -1,52,629 | -1,03,209 |
| N08 + noise-area | -68,346 | -32,262 |

All three still fail all six gates. Before the assumed extra cost, the stretch-rule book is +6,261 and N08 + noise-area is +1,02,423, against N08's +1,67,692 on the same basis. So it loses to N08 even with that cost ignored, and it trades so often that the cost then takes the rest.

## 2. The first overfitting estimate included books that aren't strategies

**What happened:** `pbo` searched across N08's 81 books as they stood, and four of them are cost-stress runs. `COST|none` is N08 with no assumed cost, so it won in-sample in 12,201 of 12,870 splits and also ranked high out of sample. That produced 0.031.

**How it was caught:** the score looked too good, and the list of chosen books showed why.

**Fix:** `n09_supp.py` drops the four cost books and 11 exact duplicates: 69 books, same method and blocks. **Corrected: 0.487.** `pbo.json` keeps the first run, and `results-final.json` check 7 was scored on it. It still passes on the corrected figure, but only just, and N09A fails on other checks anyway.

**Reading 0.487:** on purely random books this estimator averages 0.51 to 0.55, with a standard deviation of about 0.18 for one set of books. So 0.487 is what chance produces. See the README.

## 3. The month reshuffle couldn't test the restart much

The frozen reshuffle draws single months at random. That breaks up a bad stretch, so the floor is rarely reached and the restart fired in about 2% of paths. Its checks passed, but they say little. `stress_years.py` was added afterwards and is marked as not frozen: it keeps each year whole and tries all 256 orderings, including 2023 repeated.

## 4. A broken commit before the freeze

`d126ac2` carried a syntax error from my line-ending patch and no `freeze.json`. `af9f0ba` fixed it. No challenger was scored in between: the panel stopped on that error, and the panel keys were still absent when it was rerun.

## 5. A judgement I'm not allowed to act on

S_VOL missed its first check by Rs 393 (2023 -37,974 against -37,581), and N09B missed its account check by Rs 4,261 and its fall check by 0.16 of a percentage point. With the brake on, a 2023 figure mostly shows where the floor stopped the book, so these checks were blunt. I still count them as failed, because I wrote them before seeing the numbers.
