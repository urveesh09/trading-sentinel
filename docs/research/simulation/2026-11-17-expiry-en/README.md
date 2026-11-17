# EN01–EN05: improvements to E03.2 (November 17, 2026)

Plain report: [EXPIRY_RESEARCH_EN.md](../../../EXPIRY_RESEARCH_EN.md). The plan was frozen before any score
([PLAN.md](PLAN.md), `freeze.json`, commit `08bc55b8`). Starting checkout: `48270fb3`. The run used the
audit of Production `0b645d77`.

**Result:**
- **Two engine fixes in Dev:**
  - EN01, honest exits (the audit's three items);
  - EN02, the 13:00 warm-up, so live E03.2 trades the window it was tested on.
- **The three strategy ideas failed their frozen rules.** E03.2 stays unchanged.
- **The NIFTY 2023 exam was opened on the owner's word, and the whole E03 family loses**: E03.2 −3,645
  ordinary, −4,036 adverse, 4 of 17 tickets winning; puts did not beat calls. See the exam section below.
  - The clearest lesson is EN03: the put tickets just below E03.2's 0.70 trend-strength gate lose
    heavily in both years.
  - EN04's 3x puts beat E03.2 on their own but failed the neighbour rule. They go to the 2023 exam as an
    arm.
- No `.env` or schema change, no download.

## Data census (`census.py` → `census.json`, row counts only)

The census checks expiry-day afternoon option rows (13:00–15:29 on the expiry date itself) in the Breeze
history database. It reads no prices, and NIFTY 2023 is skipped.
- Only NIFTY 2024 (52 of 52 expiries) and 2025 (53 of 53) have them.
- NIFTY 2019–2022, NIFTY 2026 and SENSEX 2024–2026 have **none**. Their option rows come from days before
  expiry, or from opening-strike ten-second sessions.
- So E03.2 can be replayed on full chains only in 2024 and 2025 (seen) and 2023 (protected).

**SENSEX calibration check, descriptive only.** The forward-panel quote archive (one snapshot a minute,
Sep 10 – Nov 12, 2026) was checked for strikes inside E03.2's distance and price limits.
- NIFTY offers a strike inside 4 strikes and Rs 5–20 on 96–100% of 13:00–15:00 minutes, both sides.
- SENSEX offers one inside 4 × 100 points and Rs 16.25–65 on 83–100% for calls, and the same for puts
  except two days (Sep 10 and Oct 1, 0%). On those days the 400-point puts cost more than Rs 65.
- Nearest-OTM premiums relative to the index are similar on both: about 0.12% NIFTY and 0.14% SENSEX.
- No calibration bug was found.

## EN01: honest exits (engine)

`expiry_paper.py`:
- `can_fill`, `last_flat` and `expiring_close` use `market_calendar.expiring_index_close_time`.
- `_try_exit` books no fill at or after the expiring close.
- `manage_position` caps the flat time two minutes before that close.

`expiry_e02.py`:
- One exit per quote snapshot. FLAT_TIME waits when a sale or a latched exit used this tick.
- Every sale gets its own notice.
- `settle()`: a prior-day open leg becomes SETTLED_ASSUMED at intrinsic from our sampled post-auction
  index (before CAS 2.0), otherwise UNRESOLVED at its worst case. The value sits in `assumed_pnl`.
- The cash journal, `day_results` and the summary include assumed values.
- `reconcile()` settles a stuck leg the same evening.

`scheduler_setup.py`: the hourly expiry reconcile calls `expiry_e02.reconcile` for each variant and queues
the main ticket's settlement notice.

Tests (`tests/test_expiry_en01.py`, 8): on the old code 6 of the first 7 fail. The flat-still-fires guard
passes on both versions, as intended.

## EN02: the 13:00 warm-up (engine)

`expiry_paper.TICK_START` is 12:47 (it was 12:59), so `EXPECTED_SLOTS` = 1,038. The test pin moves from
966 to 1,038, and the warm-up test is in `test_expiry_en01.py`.
- In the lab, 2 of E03.2's 39 tickets were decided at 13:00–13:10 (+Rs 1,715): 2024-08-08 put +1,377 and
  2025-07-03 put +338.
- Live E03.2 could not decide before about 13:11.
- A, B and C act only in their own 13:00+ windows.

## EN03–EN05 (`en_lab.py`, `en_score.py` → `results.json`, in-sample)

`en_lab.check()` reproduces E03.2 day by day at all three fill levels (+21,517.55).

| Arm | 2024 | 2025 | Both, ordinary | Adverse | Severe | Worst day | Drawdown | Tickets |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **E032 (control)** | +15,581 | +5,937 | **+21,518** | +20,001 | −2,438 | −647 | 754 | 39 |
| EN03 put gate 0.65 | +14,393 | −4,026 | +10,367 | +7,367 | −4,070 | −1,117 | 4,174 | 36 |
| EN03 put gate 0.60 | +10,973 | −4,137 | +8,227 | −279 | −4,349 | −1,448 | 4,049 | 43 |
| EN03 put gate 0.55 | −4,149 | −1,297 | −4,149 | −4,045 | −4,355 | −1,095 | 4,149 | 12 |
| EN04 puts 2.5x | +15,993 | +7,853 | +23,846 | +22,102 | −3,343 | −1,247 | 1,247 | 40 |
| EN04 puts 3x | +24,802 | +9,363 | +34,165 | +31,341 | −3,277 | −1,247 | 1,247 | 40 |
| EN04 puts 3.5x | +29,665 | +9,575 | +39,240 | +34,933 | −4,232 | −1,847 | 1,847 | 40 |
| EN05 put runner 1.1 | +14,632 | +3,719 | +18,351 | +16,863 | −3,046 | −647 | 1,562 | 39 |
| EN05 put runner 1.2 | +14,632 | +3,719 | +18,351 | +17,166 | −3,046 | −647 | 1,562 | 39 |
| EN05 put runner 1.3 | +14,632 | +4,627 | +19,259 | +17,761 | −3,046 | −647 | 1,257 | 39 |

**Decisions (frozen rules):**
- **EN03 fails** every check. The tickets it adds, each on a fresh day book, are below:

  | Put gate | 2024 tickets | 2024 net | 2024 winners | 2025 tickets | 2025 net | 2025 winners |
  |---|---:|---:|---:|---:|---:|---:|
  | 0.65 | 4 | −1,188 | 1 | 9 | −5,395 | 2 |
  | 0.60 | 16 | −4,183 | 4 | 14 | −7,221 | 3 |
  | 0.55 | 27 | −8,956 | 6 | 19 | −5,544 | 4 |

  The put edge exists only in the strongest trends; looser book totals are cut further by the drawdown
  brakes.
- **EN04 fails as frozen:**
  - 2.5x misses 2024's net without the best day (3,493 against 3,810). Lot rounding gives 8 lots and
    Rs 3,125.
  - 3.5x misses the severe tolerance (−4,232 against the −3,438 limit).
  - 3x passes everything, including `RISK_PLAN.md`: skeptical losing-year 19%, p95 drawdown 4,359.
  - All three sizes pass the risk plan's own limits. It was the EN rule's stricter severe tolerance and
    neighbour clause that stopped it.
- **EN05 fails.** Keeping a put runner at the 8-minute clock lowers both years. The clock sale is worth
  more than the runner.
- No adoption, no combination, no candidate. E03.2 is unchanged.

## 2026 sanity check (`replay2026.py` → `replay2026.json`)

E03.2 ran through the current Dev engine (EN01 + EN02) on the 9 Production recordings with five-level
packets (Oct 8 – Nov 5; Oct 6 has none).
- The result is identical to the Nov 5 receipt (engine `b6b0dbf`): SENSEX Oct 22 put −1,063.75 (stop,
  gapped) and NIFTY Oct 27 put +240.79.
- Net −822.96 on 2 tickets.
- These recordings start at 12:59, so EN02 cannot show here.

## The 2023 exam: scored once, the E03 family FAILS

The owner assigned NIFTY 2023 to the exam on Nov 17 (`OWNER_WORD.md`). Freeze `af484542`; scored once
(`exam2023.py score` → `exam2023-results.json`).
- The loader was proven on 2024 beforehand (`exam2023.py check`).
- 52 expiry days: 49 have full chains. Jan 5, 12 and 19 have no option rows; they are unavailable, never
  zero.
- 5 decisions on Jan 25 were unavailable (strikes missing).
- Index and futures are complete on every day.

| Arm | Ordinary | Adverse | Severe | Without best day | Worst day | Tickets | Winning days |
|---|---:|---:|---:|---:|---:|---:|---:|
| E02 | −2,416 | −2,764 | −3,184 | −2,533 | −439 | 17 | 3 |
| E03 | −3,222 | −3,167 | −3,420 | −3,339 | −604 | 17 | 3 |
| E031 | −3,132 | −3,076 | −3,418 | −3,249 | −604 | 17 | 3 |
| E031_L8 | −3,132 | −3,508 | −3,327 | −3,249 | −604 | 17 | 3 |
| **E032** | **−3,645** | **−4,036** | **−4,173** | **−4,626** | **−1,162** | 17 | 3 |
| EN04 puts 2.5x | −4,061 | −3,584 | −4,172 | −4,178 | −1,348 | 14 | 3 |
| EN04 puts 3x | −4,215 | −4,319 | −4,772 | −4,620 | −1,719 | 14 | 4 |
| EN04 puts 3.5x | −4,522 | −4,970 | −4,076 | −4,571 | −1,905 | 9 | 2 |

Every arm loses in every quarter of 2023.

**Tests:**
- 1, E03.1 stands: **fail.** It is worse than 39 of 40 random-entry books (random median −1,832).
- 2, E03.1 vs E03: pass.
- 3, the 8% limit: fail. Severe is better, adverse worse.
- 5, E03.2 vs E03.1: **fail.**
- 6, the put-over-call asymmetry: **fail.** Per ticket, puts made −212 and calls −165. E03.2's puts:
  7 tickets, −1,982, 2 winners. Its calls: 10 tickets, −1,663, 2 winners.
- 7, E03.2 stands: **fail.**
- 8, puts at 3x: **fail.**

The EN03 lesson did not repeat. In 2023, the put tickets a 0.65 gate adds (10, mean +226) beat E03.2's own
puts (7, mean −283). Neither sample is large.

**Meaning:**
- The E03 family's afternoon pullback edge is a 2024–2025 result. It is not confirmed on a year it never
  saw, and the put premise behind E03.2 fails on 2023.
- 2023 was the year every option-buying book here lost (N08's frozen 2023 test, Nov 1). This is the same
  regime point: low volatility, a grinding market.
- **E03.2 stays a paper strategy:**
  - no size increase;
  - nothing toward real money;
  - the forward count (0 of 20 tickets) is the only remaining evidence.
- Whether E03.2 or A/B/C carries the main paper ticket is the owner's call. Neither has a fresh-year pass:
  E01.1 lost 2024, −9,012.

## Verification

- Focused tests: `tests/test_expiry_en01.py` 8 passed; all `-k expiry` tests 231 passed before EN02, and
  `test_expiry_en01.py` + `test_expiry_paper.py` 71 passed after.
- Full engine suite: see `engine-suite.txt`.
- Research reproduction: `en_lab.check()` and `exam2023.py check`.
- Tests prove the code follows the rule, not that the rule makes money.

## Plan slice

- **Problem:** E03.2 opened no tickets in four live sessions; exit defects; owner asked for five EN
  improvements.
- **Files:** `python-engine/expiry_paper.py`, `expiry_e02.py`, `scheduler_setup.py`, `config.py` (comment),
  `tests/test_expiry_en01.py`, `tests/test_expiry_e02.py`, `tests/test_expiry_paper.py`; this folder.
- **Rollout:** Dev only; Production through the GitHub release when the owner says so.
- **Rollback:**
  - EN02: `TICK_START` back to 12:59;
  - EN01: a revert, since the old behaviour was the defect.
- **Remaining:**
  - the owner's word on NIFTY 2023;
  - the data request below;
  - forward tickets: E03.2 has 0 of the 20 needed.

## Data the next round needs (owner's call; through the breeze-history-download skill only)

Expiry-day afternoon chains, the same shape as 2024/2025: one-minute option candles for the expiring
weekly, 12:45–15:30, about 20 strikes around the 13:00 ATM.
1. **NIFTY 2026 expiries, Jan–Nov (~46).** This is the most valuable: the current regime, including the
   closing-auction era.
2. **SENSEX expiries, Oct 2024 – Nov 2026 (~100).** E03.2 has never been tested on SENSEX history.
3. **NIFTY 2020–2022 expiries (~155).** Older regimes; the index and futures are already there.
