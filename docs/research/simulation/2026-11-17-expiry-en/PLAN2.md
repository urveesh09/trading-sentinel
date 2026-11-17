# EN06–EN10: the owner's five extra slots (plan frozen before EN08–EN10 are scored)

Written November 17, 2026, late night, after the auditor's brief (`docs/EXPIRY_RESEARCH_EN06_EN15.md`) and
the 2023 exam. The owner's order: each slot must either improve the system or teach something.
E03.2 stays the benchmark.

| Slot | Kind | State at this freeze |
|---|---|---|
| EN06 | Engine: the paper execution contract (brief EN06) | Done in Dev, `836d0183`; tests 8 |
| EN07 | Exam: repair the 2023 coverage rule and re-score once (brief EN15) | Done, `9624b542`: identical result |
| EN08 | Learning: when does E03.2's edge exist? A volatility-regime decomposition with one frozen gate | This plan |
| EN09 | New opportunity: one compression-to-breakout setup (brief EN09) | This plan |
| EN10 | Exit: bank a one-lot gain before it fades (brief EN11) | This plan |

## Data

NIFTY 2023, 2024 and 2025 expiry chains, 49 + 52 + 53 days:
- 2024 and 2025 are seen (E03.2 was fitted there).
- 2023 has now been opened by the exam.
- **No unseen full-chain expiry data is left.**

So these are learning experiments on seen data. A survivor can only go to a forward paper shadow, and the
new download is its real test. The bar is set high on purpose: a mechanism has to hold in **all three
years**, including 2023, where every E03 arm lost.

`en_lab2.py` reproduces E03.2 day by day on all three years at all three fill levels (`check()`). The
exam's decision-minute coverage rule (`exam2023b.available_at`) applies to every arm; in 2023 it removes
two Jan 25 decisions.

## Common rule R: "beats E03.2 robustly"

Each year runs as its own Rs 25,000 book, against the E03.2 control from the same run. R holds when all of
these hold:
1. In 2023, 2024 and 2025 separately, net ≥ E03.2's at ordinary AND at adverse fills.
2. In each year, net without that year's best day (ordinary) ≥ E03.2's.
3. The sum of the three years' severe nets ≥ E03.2's sum − Rs 1,000.
4. No day in any year (ordinary) worse than −Rs 2,500.

## EN08: the volatility regime

**Metric:** fixed at 13:00, from 09:15–13:00 bars only. The morning index range, (max high − min low) /
13:00 close, in percent. Terciles come from the pooled distribution over every expiry day of the three
years. This uses no outcome, and the scorer computes it.

**Mechanism tested:**
- Volatility clusters within a session, so a calm morning predicts a calm afternoon.
- On calm afternoons cheap OTM options decay faster than any trend moves them, and 2023 was a calm year.
- If this is E03.2's weakness, its tickets on calm-tercile days lose in every year.

**Candidate:** `regime_min` = the pooled lower tercile; no new entry on calm days.

**Passes** if R holds AND E03.2's own calm-tercile tickets total ≤ 0 in each of the three years.

**Reported regardless:** E03.2's tickets and net by tercile and year, and the 13:00 ATM-straddle ratio as
a secondary diagnostic (no decision).

## EN09: compression, then breakout (a different setup, not a looser E03.2)

Frozen in `en_lab2.py`:
- The 20-bar index range ending at the previous bar is ≤ 0.6 × the median 20-bar range of that session's
  bars ending 09:45 onward (up to 20 bars before).
- Then the index closes beyond the previous 20 bars' high/low, AND the front future closes beyond its own.
- The decision bar ends in 13:00–14:45.
- One breakout per day, the first, taken or not.
- It uses the same strike choice, size, put multiple, fill model and exits as E03.2.
- `add` arm: E03.2's book plus these signals on minutes where E03.2 has none, under the same cash, day
  ceiling and two-ticket limit.
- `only` arm: the breakout signals alone.

**Passes** if all of these hold:
- R holds for `add`;
- `only` is positive at ordinary fills in at least 2 of 3 years;
- `only` is above the median of 40 matched nulls in every year. A null keeps the same days and minutes and
  draws the side at random.

**Reported:** signal count, days shared with E03.2, `only` per year at all fills, and the null.

## EN10: one-lot bank

- A ticket of exactly one lot cannot sell half at 2x.
- Before its 8-minute clock, it is sold whole when the bid reaches entry × (1 + 1.0 × 35%) plus its
  round-trip charges per unit, i.e. one initial-risk unit after fees.
- Multi-lot tickets, the 2x rule, the stops and the clock are unchanged.

**Passes** if R holds.

**Reported:** one-lot tickets changed; how many ended better, worse or the same; 2x winners truncated; by
side.

## What a pass or a fail means

- **Pass:** a disabled-by-default paper shadow candidate for forward comparison. Never a replacement of
  E03.2 on seen data, and never a size step.
- **Fail:** recorded with what it teaches.

No threshold or parameter is searched; each slot has one frozen setting.
