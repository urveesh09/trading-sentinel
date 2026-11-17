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

## EN06–EN10: the owner's five extra slots (Nov 17, late night)

The auditor's brief is `../../../EXPIRY_RESEARCH_EN06_EN15.md`. Plan: [PLAN2.md](PLAN2.md), with EN08–EN10
frozen at `2b586f36` before scoring. Each slot must improve the system or teach something.

| Slot | What | Result | What it teaches |
|---|---|---|---|
| **EN06** | Paper execution contract (engine) | **Done**, `836d0183`; `tests/test_expiry_en06.py` 8, of which 6 fail on the EN01 engine | Depth a paper sale took is saved with the fill. A repeated callback on the same packet, or a newer packet with the same bids, cannot sell it again. Filled, assumed and open are split in the day line. Notices are stored with the fill and drained by key. E02-family reconcile runs before the day summary. CAS 2.0 labels apply, and no settlement is guessed after Dec 7. A 13:00 route fixture covers a late login and a missing minute. |
| **EN07** | 2023 coverage rule repaired, re-scored once (`exam2023b.py`, freeze `9624b542` → results) | **Identical**: every arm to the paisa, the same 2 Jan 25 decisions blocked, all 7 verdicts unchanged; E03.1 below 37 of 40 matched random books | The 2023 failure is not a coverage artefact. The loose check never bound on this data. |
| EN08 | Volatility regime: no entries on calm-morning days (bottom pooled tercile, range < 0.519%) | **Fail**: 2023 −3,645 → −1,776 and 2024 +15,581 → +15,872, but 2025 +5,937 → +2,399 | E03.2's calm-morning tickets lost in 2023 (9 tickets, −1,869) and 2024 (4, −292) but won 5 of 5 in 2025 (+3,538). 2024's money sits on active, high-implied-vol days; 2025's on calm, low-implied ones. **No stable regime explains the edge**, so E03.2's results are year-specific. |
| EN09 | Compression, then index + futures breakout, one a day (a different setup) | **Fail**: alone −2,920 / −4,200 / −4,197 (2023/24/25). That is **below the matched random-side null every year** (−2,293 / −3,281 / −3,900). Added to E03.2: 32 tickets, 5 winners. | Breakouts out of afternoon compression are false breaks on expiry. The direction they pick is worse than a coin. This agrees with E01's breakouts and SN's after-move finding. Extra frequency from breakouts is negative. |
| EN10 | A one-lot ticket banks at one initial-risk unit after fees | **Fail**: 6 tickets changed in 3 years (2023 +600; 2024 −363 with one 2x winner cut; 2025 −84) | Too rare to matter and mixed. The 8-minute clock and 2x rule stay. |

Fills for EN08–EN10 each year (ordinary / adverse):

| Arm | 2023 | 2024 | 2025 |
|---|---:|---:|---:|
| E03.2 | −3,645 / −4,036 | +15,581 / +14,629 | +5,937 / +5,371 |
| EN08 calm gate | −1,776 / −2,074 | +15,872 / +15,171 | +2,399 / +1,937 |
| EN09 add | −4,013 / −4,184 | −966 / −2,476 | −4,192 / −4,293 |
| EN09 alone | −2,920 / −3,362 | −4,200 / −4,311 | −4,197 / −4,404 |
| EN10 one-lot bank | −3,045 / −3,694 | +15,217 / +14,269 | +5,852 / +5,401 |

**The round's conclusion:**
- E03.2 is unchanged, and nothing tested beats it robustly.
- Its 2024 profit is concentrated in one put day (+11,771 of +15,581).
- 2025 is modestly positive, and 2023 loses in every version.
- The engine is now honest and complete for forward paper evidence: EN01, EN02 and EN06.
- The only real tests left are new data and forward tickets. Asks, in this order:
  1. NIFTY 2026 expiry afternoons;
  2. SENSEX expiry afternoons;
  3. forward paper tickets.

## EN11–EN25: the auditor's ten slots plus five of mine (Nov 17–18)

**Inputs and files:**
- **Brief:** `../../../EXPIRY_RESEARCH_EN11_EN20.md`.
- **Plan:** [PLAN3.md](PLAN3.md), frozen at `d2f53af7` (`freeze3.json`) before any score.
- **Scored once:** `python en_score3.py score`, start receipt `results3-started.json`, output `results3.json` + `anatomy3.json`.
- **Write-up:** [ANATOMY3.md](ANATOMY3.md); every table is rendered in [ANATOMY3-tables.md](ANATOMY3-tables.md) by `render3.py`.

**Verification before the freeze:**
- `python en_lab3.py`: CHECK_OK. With every hook off, the lab reproduces E03.2 day by day on 2023–25 at all three fill levels, and every arm runs. Only counts were printed.
- `python rec2026.py`: 19 sealed expiry sessions, every file hash-checked.
- `python en15_breadth.py`: 50 names, 143 sessions.
- `python en11_seconds.py`: 22 contracts.
- `python en_score3.py selftest`: the whole pipeline on 2 days a year, with no rupees printed.

**Data:**
- **NIFTY 2023–25 chains** (seen): EN11–EN14, EN17, EN19–EN25.
- **2026 recorded quotes:** forward-panel export `20261117T103003Z`, 9 NIFTY + 10 SENSEX sealed expiry sessions, Sep 10 – Nov 13, real bid/ask and 5-level depth, both weeklies. Used for EN16 and EN18; now seen for these questions.
- **Kite 15-minute bars, Jan–Jul 2026:** EN15 breadth.
- **NIFTY 1-second trades, Jan–Mar 2026:** EN11's speed measure.
- No download, no `.env`, source or Production change.

| Slot | Result | Lesson |
|---|---|---|
| EN11 fast exit | FAIL: worse every year (−361 / −1,833 / −973) | Intrabar stops cut 9 winners (−5,300) to save 17 losers (+2,133). 1-second data: fast exits are 0.4% of entry worse than the minute cadence, and 16 of 42 stop touches recover within 60 s. Keep the completed-minute stop. |
| EN12 pay for the runner | INCONCLUSIVE (1 ticket) | The full-sale diagnostic shows the runner is a hero lottery: +8,903 on 2024-03-28, −4,104 over the 4 other 2x tickets. |
| EN13 range rotation | FAIL: −2,608 / −2,924 / −4,033 | Midpoint targets win, but range breaks and the clock lose more. Below the random-side null in 2023 and 2025. |
| EN14 second wave | FAIL: +1,768 / −3,203 / −1,064 | Beats the immediate-impulse entry every year (+7,707 in total). Chasing a burst loses about Rs 3,400 a year. |
| EN15 breadth | FAIL | When 80% of names move together the index always agrees (0 disagreements), and the next bar continues 45%. No lead. |
| EN16 next-expiry confirmation | FAIL | Agrees 155 of 162 times (the same index), so it is no filter. The trigger's one-lot trades lose −68 each on real quotes. |
| EN17 burst pair | FAIL: −628 / −1,388 / −1,525 | 10 of 15 pairs fade; below the random-minute null every year. |
| EN18 strike by real cost | FAIL | The further strike is never cheaper per rupee. Round trip: NIFTY 11.0% against 5.7%, SENSEX 7.6% against 5.0%. E03.2's pick is already the efficient one. |
| EN19 late pin release | FAIL: +1,629 / −2,530 / −2,697 | The one-lot runner works when it comes; stops dominate (2025: −5,713). |
| EN20 proven re-entry | INCONCLUSIVE (1 retry) | E03.2's own retries after a stop are positive (blocking them costs 1,740 in 2024). Keep them. |
| EN21 scale in when right | FAIL: −3,042 / +21,293 / +3,922 | Halves wrong multi-lot puts (2023 +604) but halves slow winners (2025 −2,015). The 2024 gain is the hero (+6,658). |
| EN22 no hard stop | FAIL: +884 over three years, worse in 2023 and 2025 | The stop is roughly neutral. Stopped trades were wrong entries. |
| EN23 last-half-hour momentum | FAIL: +2,815 / −3,049 / −1,176 | 4 winners in 25; calls lose every year. Gao et al.'s index effect is too small for 15:00 expiry options. |
| EN24 futures participation | FAIL: −1,271 / +3,595 / +4,634 | It removes the 2024 hero (4 tickets, +11,986). Like EN08: it helps the bad year and removes the good years' winners. |
| EN25 patient entry | FAIL: +286 / −572 / +188 | It fills almost every time and is about neutral in ordinary fills. Far better under severe fills: it keeps the 2024 hero, which a market order loses to its 8% limit. An execution safety to measure forward. |

**Conclusion:**
- E03.2 is unchanged. Its stop level and cadence, retry, strike choice and runner were each challenged, and each held up.
- Its losses come from wrong entries, which no exit or filter here repairs without removing the 2024 hero.
- Fresh data is the only lever left:
  - SENSEX expiry afternoons;
  - NIFTY 2026 chains;
  - forward paper tickets;
  - EN25's resting-bid fill rate on recorded quotes.

**Data held open (Nov 18):** the slots waiting for the owner's data (EN15-R, EN16-R, EN11-R, the NIFTY 2026 exam and the SENSEX test) are listed in [DATA_REQUESTS.md](DATA_REQUESTS.md).
