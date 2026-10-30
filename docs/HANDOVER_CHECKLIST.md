## October 30 — O30 documentation: the Oct 29–30 research summary, the year-data testing method, a study template and the 2024 scorer (docs + research tooling, Dev; nothing changed in the system)

- [x] Summary, method, template, slice tool and the 2024 scorer committed.
- **Owner (Oct 30):** "what all strategies you have done and everything about the testing and what issues happened in our strategy why it failed in one year and worked in another ... give me the documentation for how you did the testing the methodology for that, so if some other agent does that they can easily do the testing".
- **New:**
  - `docs/FNO_RESEARCH_2026-10-30_SUMMARY.md`: every study and strategy, results, why one year worked and the other failed, the over-tuning guard, the issues, next steps, and where everything is.
  - `docs/FNO_YEAR_DATA_TESTING_METHOD.md`: data, the replay stack, module chain and year selection, how to express and add a strategy, the 12-step protocol, metrics, honesty checks, the window ledger, pitfalls, and the 2024 exam.
  - `docs/research/fno/study_template/` (`lab_x.py`, `analyze_x.py`, `test_lab_x.py`): an example entry wired through the whole chain. Its 2 tests pass, and its January 2025 plumbing run takes 15 trades.
  - `docs/research/fno/run_slice.py`: bounded foreground slices. It was tested on a job that finishes and on a job that gets stopped.
  - `docs/research/fno/2026-10-30-day-router/analyze_f.py`: the `RULE_2024` scorer, committed before any 2024 data exists.
- **Updated:**
  - `docs/FNO_STRATEGY_TESTING_PLAYBOOK.md`: a pointer, and §8's ledger marked superseded.
  - `docs/RESEARCH_TESTING_METHOD.md`: a pointer, and the F&O ledger row.
- **Config and migration:** none. Nothing is deployed.

## October 30 — O30m Kind-of-day router over a 134-strategy library, and the NIFTY 2024 exam freeze (research, Dev: freeze 2bcec04, routers 33947f2, 2024 freeze 2a57ede; the router fails the cross-year check, the trend pullback is the one robust family; nothing changed)

- [x] Library freeze `2bcec04` → library replays → the cross-year check (routers `33947f2`) → exact routers, persistence, and the 2024 freeze `2a57ede`.
- **Results (`docs/research/fno/2026-10-30-day-router/README.md`, per lot):**
  - **No kind-of-day router passes.** Chosen on one year, each of the six partitions loses on the other year (−₹5k to −₹79k), often below random routers.
  - **Exact replays:** the router chosen on 2026 makes +₹1,10,602 there and −₹34,803 on 2025.
  - **Persistence:** the 2025 vs 2026 rank correlation over 114 strategies is 0.12 (−0.36 to 0.18 inside kinds of day). 14 strategies are positive in both years, mostly trend-pullback variants, and 0 of 20 random books are.
  - **ROBUST_CORE** (TPB, two pullback genomes, SHIPPED): +₹78,830 over both years, no better than TPB alone (+₹78,750, max DD ₹22,896).
  - **Best book:** the O30c candidate, live + TPB on closed days, at +₹1,14,748.
- **2024 exam:** frozen in `freeze-2024.json` (23 books, RULE_2024) with `lab_f.py` (mirror24 / export24 / warm24 / run).
  - It runs after `download2024.py`, which is new in `sentinel-operations/breeze-history-20261029` with a 2024 calendar checked offline; DOWNLOAD_GUIDE §0.
  - The engine must be unchanged since O29i, or the run must come from a worktree at `2a57ede`.
- [ ] The 2024 download and exam (Oct 31), then the owner's call on the TPB case before the real-money week.

## October 30 — O30c Why the live book broke even on 2025, and case rules tested on both NIFTY years (research, Dev: freezes a98b1f5 + b0defde, results committed; one case nearly passes: TPB trades on the days the ADX gate is closed; nothing changed)

- [x] Tier 1 freeze `a98b1f5` before any case replay; results, investigation and the Tier 2 freeze `b0defde`; Tier 2 results committed.
- **Why it failed on 2025 (`docs/research/fno/2026-10-30-case-study/README.md`, per lot):**
  - EFF lost −₹21,796 inside the live book, after +₹29,629 in 2026.
  - The ADX gate kept TPB out of its best 2025 days: TPB made +₹31,869 on the closed days.
  - 2026 fell on 77% of days and 2025 rose on 55%. The book's puts paid in both years; its calls lost in 2025 (−₹27,214).
- **Tier 1** (15 cases fixed before the investigation; the rule: beat the base in both years and not be worse in 3 of 4 half-years):
  - **TPB trades on the gate's closed days:** +₹34,246 in 2025 and −₹680 in 2026; both years +₹1,14,748 against +₹81,183. It misses the rule by ₹680 and is the one real candidate.
  - **Trend-direction cases and the other day gates** help one year and hurt the other.
  - **TPB first on the ungated four** passes, but by a small amount.
- **Tier 2** (cases from the investigation; in-sample): breakouts only with the trend, entries only 10:00–14:00, and the 20-day-move gate. None beats the candidate, even in-sample. Slicing patterns did not survive being built into the book.
- **Next clean test:** NIFTY 2024 (unseen; about 4,500 Breeze requests), then the forward panel. The rule (frozen in `freeze-tier2.json`): beat the live book over the year and not be worse in either half.
- [ ] Owner's call on "TPB on the closed days"; the NIFTY 2024 download and clean test.

## October 30 — O30 NIFTY 2025 clean test of the 2026 strategies (research, Dev: freeze 7d9eeb3, results committed; the ADX gate and the sideways fades do not hold on 2025, TPB alone is positive in both years; nothing changed)

- [x] NIFTY 2025 downloaded (another agent, Oct 30 06:12–07:27 IST, 3,949 requests). `verify_download.py` was clean: 3,585 option requests ok, 0 expiry mismatches.
- [x] Freeze `7d9eeb3` committed before any 2025 replay; 76 replays; results committed.
- **Results (per lot of 65; `docs/research/fno/2026-10-30-nifty-2025-test/README.md`):**
  - **The live UNION_ADX made +₹271 on 2025** (138 trades, max DD ₹31,482, 4 green / 4 red months). It loses to UNION without the gate (+₹27,140) and to UNION_DRIVE (+₹64,712), so the trend book does not hold.
  - **The sideways fades lost on 2025's sideways days:** FADE −₹14,518 and PDL_FADE −₹12,775 (the random books' median was −₹22,894). UNION_ADX + FADE made −₹14,248, so the fade is not recommended.
  - **TPB alone was positive in both years:** always on +₹36,694 on 2025 (+₹78,750 with 2026); at ADX ≥ 20 +₹24,680 (+₹79,496 with 2026, max DD ₹14,966, the smallest).
  - **Both years together:** UNION_ADX +₹81,183, all of it from 2026. UNION_DRIVE +₹72,000 (max DD ₹57,189). The ranking flips between years.
  - **Caveat:** candles came out about ₹100–200 per trade per lot better than the recorded quotes (O29f), so books with many trades are flattered most.
- [ ] Owner's call: keep UNION_ADX, return to UNION_DRIVE (environment only), or move to a TPB-only book (engine change) before Nov 2. The fade on sideways days is not recommended.

## October 29 — Rollout receipt O29h (Production a461bde)

- **Merges:** PR #123 (O29f/O29g research, O29h UNION_ADX, O29i freeze) merged at 17:23 IST as a51c791 and deployed. PR #124 (the 09:30 read follow-up, cfe83dc) merged at 17:32 as a461bde.
- **Deploy (on the owner's Oct 29 go-ahead), per the runbook:** the Production checkout was fast-forwarded and stamped with `SENTINEL_RELEASE_SHA` / `SENTINEL_BUILD_UTC`. node-gateway, python-engine and agent were built one at a time and recreated, and nginx was restarted.
- **Verification:** `scripts/verify_deployment.py --expected-sha a461bde…` passed (receipt in `sentinel-operations/release-receipts/`), and local and public `/api/health` both return 200.
- **Engine, read-only:**
  - `FNO_BOOK=UNION_ADX` with ADX minimum 25, on for NIFTY and SENSEX; the gate is read from 09:30.
  - The cached NIFTY 50 daily candles give ADX 35.7 for Oct 30, so the book trades.
  - The real-money switch is off (₹12,500); no open F&O positions; no error lines since the restart.
- **Not done:** the runbook's full consistent data backup. The latest is Sep 11, and recent deploys have not taken one. This change only adds the table `fno_regime_gate`.
- [ ] Oct 30 after 09:30 (read-only): a `fno_regime_gate` row, the owner's `fno_book_adx_gate` Telegram line, and `strategy=` on any book entry.

## October 29 — O29i Sideways-day study (research only) (research, Dev: freeze d5b08c9, results committed; the failed-break fade helps on sideways days (in-sample), VWAP/RSI2 do not; nothing changed)

- [x] `lab_i.py`, `test_lab_i.py` (2 passed: every family causal); freeze committed before scoring.
- [ ] Results: see the study README. Nothing changes on paper or live because of a replay.
- **Results (in-sample, per lot, sideways days only; `docs/research/fno/2026-10-29-sideways-study/README.md`):**
  - **The failed opening-range break (FADE) helps:** 12 of 16 variants positive, H1 pick → H2 +₹6,752, H2 pick → H1 +₹12,533; the random median was −₹891 / −₹4,861. Best variant: +₹30,134, 119 trades, worst day −₹4,315.
  - **PDL_FADE helps, but small:** 8 of 8 positive, +₹553 / +₹2,869.
  - **VWAP_REVERT and RSI2 do not help.**
  - **Joined to UNION_ADX:** +₹111,046 per lot, 9 green / 1 red months, against +₹80,912 for UNION_ADX alone. The fade adds weekly activity (22 / 18 one-lot weeks, against 8 / 5).
- [ ] Owner's call: whether to add the fade on sideways days (at 1 lot). The NIFTY 2025 clean test of UNION_ADX and of the fade comes first.

## October 29 — O29h UNION_ADX trend gate (Dev commits 2279a2e + cfe83dc, pushed; deployed: Production a461bde (Oct 29, 17:34 IST, PR #123 + #124), verify_deployment passed; fno_book 27 + F&O 750 passed, research parity exact on 203 sessions, full suite 5867 passed / 4 skipped plus test_scheduler_closures_invoke 29 passed alone)

- [x] `fno_book` trend gate, orchestrator wiring, default `UNION_ADX`; tests 27 + F&O 750; research parity exact on 203 sessions.
- [ ] After the deploy, from Oct 30: one `fno_book_adx_gate` Telegram line before the first F&O entry window, a `fno_regime_gate` row for the session, and `adx_low`/`adx_unknown` reasons in `fno_signals` when the book sits out (read-only check).
- [ ] The NIFTY 2025 clean test of the gate (download 08:00 IST Oct 30, after the owner's ICICI login) and the owner's queued sideways-day strategy study.

## October 29 — O29g Why-study (research only) (research, Dev: freeze 9d450aa, results committed; in-sample: the ADX gate helps, the published ideas do not transfer; clean 2025 test next; nothing changed)

- [x] `features.py`, `lab_g.py` and `test_lab_g.py` (4 passed); freeze committed before scoring.
- [ ] Results: see the study README. Nothing changes on paper or live because of a replay.
- **Results (in-sample on the year, per lot; `docs/research/fno/2026-10-29-why-study/README.md`):**
  - **The gate:** with yesterday's ADX(14) ≥ 20/25 the strategies trade only in trending regimes and sit out the range-bound May–Aug.
    - TPB at ADX ≥ 20: +₹54,816, 36 trades, worst day −₹4,415, DD ₹7,641, 12 green / 2 red weeks.
    - All four at ADX ≥ 25: +₹80,912, 106 trades, 5 green / 1 red months.
    - For comparison, the live UNION_DRIVE made +₹7,288 (18 / 23 weeks).
  - **Two-fold check:** SHIPPED and OR20 pass both ways; EFF and TPB do not. On random-entry books the gate improved 13 of 20, but they still lose. Profit concentrates in Feb and Oct.
  - **The published ideas do not transfer:** NOISE_BAND at 30 min made −₹33,399, and LATE_MOMO flips sign between halves.
- [ ] Clean test on NIFTY 2025 (frozen books unchanged): download from 00:10 IST Oct 30, after the SENSEX remainder.
- [ ] Owner's call: the forward panel for TPB at ADX ≥ 20 and all four at ADX ≥ 25.

## October 29 — O29f Year genome (research only) (research, Dev: freeze 1b14225, results 0d1f6fa, pushed; verdict: the search fails, the live book loses on the unseen months; not deployed, nothing changed)

- [x] Breeze download tooling outside the repo; NIFTY Dec 2025 – Oct 2026 complete.
- [x] `yeardata.py`, `lab.py`, `test_lab.py` (8 passed); archive parity exact for all six books.
- [ ] SENSEX options: the download continues on Oct 30 after the owner's Breeze login (`login.py`; the session lasts one day).
- [ ] Results: see the study README. Nothing changes on paper or live because of a replay.
- **Results (1,842 replays; 08:36–15:24 IST Oct 29; `results.json`):**
  - **The search fails its frozen rule.** REAL out-of-sample (Apr 1 – Oct 28) made −₹16,870 on 89 trades, positive in only 1 of 4 folds, worst day −₹9,275. The live UNION_DRIVE made −₹17,801 on the same sessions and the NULL search −₹27,546. Every REAL pick made ₹77k–201k on its training months.
  - **The live book on the unseen Jan 1 – Sep 9:** UNION_DRIVE made −₹24,500 (−₹27,156 per lot), with 3 green and 6 red months, and was negative every month from Apr to Aug. At one lot it lost about ₹17–18k in each of May and July.
  - **Under the one-lot real-money rules over 44 weeks:** 17 weeks up and 21 down; the worst week ended at ₹8,379 from ₹15,000. On Sep–Oct it had been 26 of 27 up.
  - **Positive on the unseen months:** TPB alone made +₹14,677 (+₹19,768 per lot) and THEORY_NR +₹42,410 (+₹17,837 per lot). Only 1 of 20 random-entry books beat either. Both are picked after seeing 11 fixed books, so this is evidence, not proof.
  - **The FINAL pick** (TPB plus two momentum bursts, all on `trend5:LOW`) made +₹163,038 in-sample. It is a forward-test candidate only.
  - **Candles against recorded quotes (Sep 10 – Oct 26):** about ₹100–200 per trade per lot optimistic. The sizing differs (fresh pool about 1.8 lots against the archive's live history about 1.1).
  - **Interruptions:** Claude Code stopped the run twice for low memory. Production stayed healthy, and the run resumed from its saved replays.
- [ ] Owner's call: the Nov 2–6 real-money test, in light of the unseen-month result. Any forward panel for TPB, THEORY_NR or the FINAL pick is also the owner's call; nothing is changed.

## October 28 — Rollout receipt O29–O29e (Production 490bd1d)

- PR #121 (O29, O29b research, O29c, O29d) was merged by the owner at 21:07 IST (9233bcf). PR #122 (O29e) was merged at 21:15 (490bd1d).
- **Deploy:** Production fast-forwarded to 490bd1d. Following the runbook, `SENTINEL_RELEASE_SHA` and `SENTINEL_BUILD_UTC` were set, then node-gateway, python-engine and agent were built one at a time and recreated.
- **Verification:**
  - `scripts/verify_deployment.py --expected-sha 490bd1d…` passed. The receipt is in `sentinel-operations/release-receipts/`.
  - The first verification returned 502 because nginx kept the recreated gateway's old address. `docker compose restart nginx` fixed it, and the local and public `/api/health` both return 200.
- **Engine, read-only:**
  - `FNO_BOOK=UNION_DRIVE`, on for NIFTY and SENSEX, with seeds of 38 values each.
  - `fno_positions.strategy` is present, and the cash alert is present.
  - The real-money switch is off (₹12,500, run Nov 2–6). No open F&O positions; no error lines since start.
  - `fno_opening_drive` is created at the first 09:45 read on Oct 29.
- [ ] Oct 29 after 09:45 (read-only): check the `fno_opening_drive` rows for NIFTY and SENSEX, and that F&O entry messages carry `strategy=`.

## October 28 — O29e Book on SENSEX (paper) (Dev commit 95183ff, pushed; deployed: Production 490bd1d (Oct 28, 21:18 IST), verify_deployment passed (PR #122); fno_book + SENSEX tests 24 passed, F&O tests + NIFTY parity 700 passed, SENSEX parity 2 passed (30 trades exact))

- [x] `fno_book` per-underlying drive, SENSEX seed, the volume swap, orchestrator wiring; tests and SENSEX parity.
- [ ] After the deploy, from Oct 29: check that SENSEX rows appear in `fno_opening_drive` after 09:45 (read-only), and that SENSEX entries carry `strategy=`.
- [ ] The SENSEX book has no forward panel (the panels replay NIFTY only). Judge it from the paper book itself.

## October 28 — O29d Cash alert, one-lot and SENSEX checks (Dev commit 454a6d7 (research abfc27a, b9a9352), pushed; fno_live_test 35 passed, full suite 5852 passed / 4 skipped plus test_scheduler_closures_invoke 29 passed alone; deployed: Production 490bd1d (Oct 28, 21:18 IST), verify_deployment passed)

- [x] `fno_live_test` cash-short alert and the morning line; tests.
- [x] SENSEX check, frozen and scored (abfc27a, b9a9352): SENSEX unchanged.
- [ ] Owner: if ₹15,000 is deposited, set `FNO_LIVE_TEST_CAPITAL=15000` before Nov 2.
- [ ] Owner: a fade or mean-reversion book on two-way days is advice only. No change without the owner's call.

## October 28 — O29c Four-strategy NIFTY book (Dev commit 01fa551, pushed; fno_book 12 + F&O 731 passed, research parity 2 passed, full suite 5879 passed / 1 load-sensitive scheduler test (passes alone 3/3); deployed: Production 490bd1d (Oct 28, 21:18 IST), verify_deployment passed)

- [x] `fno_book` and its wiring, tests, and research parity (an exact trade match over 31 sessions).
- [ ] Owner: merge and deploy go-ahead. After the deploy, check that the engine starts and that the `fno_opening_drive` row for the day appears after 09:45 (`SELECT * FROM fno_opening_drive ORDER BY session_date DESC LIMIT 3`, read-only).
- [ ] After the first sessions: compare the paper book with forward panel C's UNION_DRIVE row (same strategy, replayed).
- [ ] Rollback if needed: `FNO_BOOK=SHIPPED` in the root `.env`, then restart the engine.

## October 28 — O29b Chop study and forward panel D (study 903f28f/e8d3ee5, panel D c02a997, pushed; research only, not deployed)

- [x] Study frozen, run and analysed. Panel D built, frozen, pinned and smoke-tested (bound == freeze; launcher exit 0).
- [ ] **Owner:** hook panel D into the 16:00 task (the agent's edit was blocked as persistence). In PowerShell:
  `Add-Content -Path "C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\run_panel.cmd" -Value 'call "C:\Users\Urveesh\sentinel-operations\fno-forward-panel-d-20261029\run_panel_d.cmd"' -Encoding ascii`
- [ ] Each evening: `C:\Users\Urveesh\sentinel-operations\fno-forward-panel-d-20261029\docs\research\fno\2026-10-29-forward-panel-d\_local\REPORT.md`
- [ ] Nov 27: read the frozen rule. Promotion is the owner's call, never in a proving week.

## October 28 — O29 Partner-watch fixes (Dev commit 0dbff8b, pushed; partner tests 159 passed, full engine suite 5868 passed / 4 skipped; deployed: Production 490bd1d (Oct 28, 21:18 IST), verify_deployment passed)

- [x] Cash refresh, first-read refusals plus plain trigger wording, carried sales in DAY and the report, and the next-session expiry close note, all in Dev with tests.
- [ ] Owner: merge and deploy when ready. It is not part of the paper or live F&O rules, so the proving week is unaffected.
- [ ] After deploy, on the first day with a top-up or overnight hold: check `partner_watch_report` and the DAY and REFUSED texts.
- [ ] Owner calls listed in the plan: the paper NIFTY pool floor, ₹12,500 against NIFTY lot costs, and the NIFTY-only panels.

## October 28 — O28b Forward panel C (research, Dev, commit `feaeae4`, pushed; pinned and hooked into the 16:00 task)

- [x] Built, frozen, pinned and hooked after panel B. The end-to-end launcher run passed (0 sessions before the open).
- [ ] Each evening: `C:\Users\Urveesh\sentinel-operations\fno-forward-panel-c-20261028\docs\research\fno\2026-10-28-forward-panel-c\_local\REPORT.md` (watch the extreme-loss alarm line).
- [ ] Nov 27: read the frozen rule. Promotion is the owner's call, never in a proving week.

## October 28 — O28 Regime router study (research, Dev, freeze `728cdf8`, results `d3b9a70`, pushed)

- [x] Frozen before scoring (`728cdf8`); parity exact for all four components; 252 replays; verdict `CONDITIONS_NOT_SHOWN_TO_ADD_VALUE`.
- [ ] Owner: decide whether `UNION` and `THEORY_DRIVE` go into a forward panel (research only; no paper or live change in the proving week).

## October 27 — O27h Trend-day pullback shadow (Dev, commit `faaf366`, pushed, deployed by PR #120 (`104485b`, Oct 27))

- [x] The shadow variant, its replay arm (exactly the lab's 14 trades), the owner message and the tests.
- [ ] Oct 28: the owner sees a message if the pullback signals (from 11:30). Forward panel B scores its full trade after 16:00, once the owner has registered the task.
- [ ] Nothing is promoted on one day; panel B's frozen rule is read after Nov 27.

## October 27 — O27f genome round 3 (done, Dev, freeze `3b8f9ef`, results and panel B freeze `0b529f2`, not pushed)

- [x] O27f lab, tests (7) and freeze committed before scoring (`3b8f9ef`); the frozen run is done (2,217 replays, parity gate passed); results are written up.
- [x] O27g forward panel B frozen before Oct 28, with 3 tests passing; pinned copy made; panel A's launcher calls it.
- [ ] Owner: register the 16:00 Mon–Fri task (`register_task.ps1` in the panel A pinned folder; it now runs both panels).
- [ ] Read both panel reports weekly. The frozen rules are read after Nov 27. Nothing is promoted on seen data or during a proving week.

## October 27 — O27e novel F&O entry families (research completed; Dev only)

- [Learning/results](research/simulation/2026-10-27-fno-novel-families/ANALYSIS.md)
  and [audit notes](research/simulation/2026-10-27-fno-novel-families/COMPLETION.md).
- Pre-score freeze: `3e2bcfe`; 121 genomes / 115 distinct A trade histories across
  three novel entry families. Exact CURRENT parity, 123 effective settings match.
- Efficiency break models +INR 31,063.33 versus shipped +10,801.09, but closed-trade
  drawdown 6,748.74 fails the frozen B risk cap. Neighbour sensitivity is fragile.
  Compression loses; failed auction has no eligible arm. No candidate qualifies.
- All dates seen; 29 archived sessions / 30 expected, September 18 unavailable.
  Eight sessions have recording gaps >180s. No untouched-validation/profit claim.
- Final regression: 57 pass, two existing warnings. Independent audit reconciles
  128 closed trade records and 121 arm metrics; frozen source/data remain intact.
- Generic skill REPORT is INVALID for its pre-freeze HEAD pin after the required
  freeze commit. Failure retained; separate source/input/raw-ledger audit passes.
- Research files and local commits only; no application, Production, settings,
  broker, paper rules, scheduler, pinned O27c panel, push or deployment changes.
- Remaining: separately approved prospective evidence; keep shipped rules.
- Rollback: ordinary Git removal of isolated research; no runtime caller imports it.

# Handover receipt and operator checklist

## October 27 — O27d F&O strategy testing playbook (Dev, commit `ed3b9fa`, not pushed)

- [x] `docs/FNO_STRATEGY_TESTING_PLAYBOOK.md`, reference scripts, and the method doc's pointer and F&O ledger row.
- [ ] Hand the playbook to any agent testing F&O strategies. A new forward panel must be frozen before its start date.

## October 27 — O27c F&O forward panel (Dev, commit `e6af14b`, not pushed)

- [x] Panel and rule frozen before Oct 28 (`docs/research/fno/2026-10-28-forward-panel/freeze.json`).
- [x] Tests: `tests/test_fno_forward_panel.py` (new, 3) with the evolution, grid, shadow and replay suites: 41 passed (2 existing third-party deprecation warnings), 36 s.
- [ ] Pinned copy and 16:00 IST (Monday–Friday) scheduled task: re-pinned for 16:00 by commit `3dc3342`; the pinned copy was rebuilt from it on Oct 27 at 20:20 IST (source and FNO settings hashes equal the freeze; `run_panel.cmd` ran end to end: export, 0 forward sessions, report, exit 0). The 16:00 IST Monday–Friday task is NOT registered yet: the agent's registration was refused by the permission check (persistence). The owner runs `register_task.ps1` from the pinned folder, or the agent runs `run_panel.cmd` on request.
- [ ] Weekly: read `C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\docs\research\fno\2026-10-28-forward-panel\_local\REPORT.md`. Nov 27: apply the frozen rule; the owner decides.

## October 27 — O27b F&O evolution round (Dev, freeze `3f97f2c`, results commit `080330d`, not pushed)

- [x] Web parameters reviewed: the stocks-in-play ORB (5–25 min ranges, RVOL > 1, ATR stop), Crabel's stretch and NR4/NR7, gap and VWAP filters, a time cutoff. Our own variation: an EMA 9/21 trend check.
- [x] What the winning days had in common (window A only) recorded in the study README.
- [x] Genes, GA, fitness, plateau and B check frozen before scoring (`docs/research/fno/2026-10-27-evolution/freeze.json`).
- [x] Tests: focused `tests/test_fno_evolution.py tests/test_fno_consistency_grid.py tests/test_fno_shadow.py tests/test_fno_policy_replay.py tests/test_preregistered_study_runner.py tests/test_fno_orchestrator.py`: 73 passed (2 existing third-party deprecation warnings), 39 s; the full suite runs before the results commit.
- [x] Run: verdict `NONE_PASSED_KEEP_SHIPPED`. The finalists earned +₹15k to +₹21k on A but made 0–1 trades on B (the EMA check refused late-October trends). Details are in the study README and `results.json`.
- [x] Full suite after the gene code, run beside the 10-worker evolution:
  - engine: 5,848 passed, 4 skipped, 1 failed (16 min 6 s); `scripts/tests` 287 passed.
  - The failure, `test_scheduler_closures_invoke.py::test_a_tick_that_waited_for_the_fast_exit_skips_when_another_tick_ran_meanwhile` (await count 2 vs 1), is timing-sensitive under full CPU load. Alone, still under load, it passed 2 of 3.
  - It does not touch `fno_shadow` or the research scripts.
- [ ] Make that scheduler test independent of CPU load (open).
- [ ] Owner decides on a forward-only replay of any passing genome. No paper or live change in the proving week.

## October 27 — O27 F&O consistency grid (Dev, freeze `d4cfb7e`, results commit `32f4271`, not pushed)

- [x] Read-only export of the Production archive, 29 sealed NIFTY sessions Sep 10 – Oct 26 (`_local/dataset/`, not in git).
- [x] Dev and Production `FNO_*` settings compared by per-key hash: all 123 equal (names only printed).
- [x] Grid and selection rule frozen before scoring (`docs/research/fno/2026-10-27-consistency-grid/freeze.json`).
- [x] Tests: focused suites `tests/test_fno_consistency_grid.py tests/test_fno_shadow.py tests/test_fno_policy_replay.py tests/test_preregistered_study_runner.py`: 35 passed (2 existing third-party deprecation warnings), 23 s; the full suite runs before the results commit.
- [x] Grid run (361 arms, 58 min, 6 workers; Production left running). Parity held.
  - Frozen verdict: `SHADOW_CANDIDATE` `OR20|LOCK_LATE|T75|TR1.5`, with 0 trades in B, so its check is empty (rule gap reported).
  - CURRENT ranks 27th of 32 eligible.
  - Details: study README.
- [x] Full suite after the grid code: engine 5,844 passed, 4 skipped, 0 failed (14 min 14 s, run alongside the grid); `scripts/tests` 287 passed.
- [ ] If an arm is recommended: the owner decides on a broker-free live shadow plus a forward replay. No paper or live change in the proving week.

## October 26 — O26e The O26d recheck's two gaps fixed (Dev, commit `1d99c12`, pushed, deployed by PR #119 (`3b945eb`, Oct 26))

- [x] Each research trade's terminal pass uses its own saved execution; legacy records never get the closing-auction model (F1).
- [x] Minute bars replace the stop-first result only when they cover the whole session with no gap over 5 minutes (F2).
- [x] Tests: full suite 6,123 passed, 1 failed, 4 skipped (11 min 26 s). The failure was a second queue-order test in `test_s5_provider_lanes.py` with the same Windows-clock assumption. All five queue-order tests now run at `QUEUE_RATE` 20/s; the file then passed 3 of 3 alone and 12 of 12 run four at a time. No engine code changed after the full run. Focused: tracker and mirror 52, shadow 25. The reviewer's recheck scenarios: 6 passed, and the 2 defect reproductions now fail.
- [x] PR #119 merged as `3b945eb` and deployed Oct 26, 21:35–21:44 IST: backups `quick_check=ok`, rollback images tagged, three images stamped and recreated one at a time, `verify_deployment` passed, switches unchanged (receipt in the plan).
- [ ] Confirm SEBI's December 7 CAS timings before that date.

## October 26 — O26d The independent review of O26–O26c fixed (Dev, commit `4205eef`, pushed, deployed by PR #119 (`3b945eb`, Oct 26))

- [x] Production runs `f9547c5` (PR #118); O26, O26b, O26c and O26d are Dev only.
- [x] Daily paper exits are ordered: open first, T1 before T2, stop before target after the open (the breakeven stop included); entry-day open unused; minute bars on days the daily bar cannot order (R1).
- [x] A partly filled opening order is sized as it fills; buy-time facts stay first known (R4).
- [x] Unknown warning evidence is left out, not counted as "no warning"; the score rule is its own frozen SPEC v2 (R2, R6).
- [x] The closing-auction 15:15 exit needs dated evidence (window 2026-08-03 to 2026-12-06, the stock in that day's archived F&O master) and is reported as modelled (R3).
- [x] Tests cannot reach the network by numeric address or asyncio either, in Python children too (R5).
- [x] The intermittent scheduler test: Windows' 15.6 ms clock; the tick now counts passes.
- [x] DAY's charges are labelled estimated.
- [x] Tests: full suite (`python -m pytest tests ../scripts -q`): 6,110 passed, 4 skipped, exit 0 (11 min 24 s). The first full run had 2 failures, both explained and fixed (HIGHLOW-1's expectation; the lanes test's timing). Focused: tracker and mirror 48, partner watch and score 130, closing auction and replay 50, scheduler 29, network guard 11.
- [ ] Rollout with the next PR (owner's go-ahead): engine only; no setting.
- [ ] Confirm SEBI's December 7 CAS timings before that date.
- [ ] Owner: Oct 26's 22 censored research trades stay censored unless you want a backfill.
- [ ] Next session: SADHNANIQ should close once in each Smart book.

## October 26 — O26c The Oct 26 audit's findings fixed; DAY charges and refusal size (Dev, commit `a848bcb`, pushed, deployed by PR #119 (`3b945eb`, Oct 26))

- [x] Production runs `f9547c5` (PR #118); O26, O26b and O26c are Dev only.
- [x] A halt tripped while a buy's cash is read stops the buy before the POST and gives its hold back (O26-H1).
- [x] A check whose prices went old during its database claim is worked out again, not sent (O26-C1); future read/receipt clocks are INVALID (O26-C2).
- [x] Closing-auction (F&O) stocks get their 15:15 research exit at the 15:00 close (runtime and replay); before, every one was censored (O26-R1).
- [x] The daily paper tracker takes the stop when a bar touches both, and stops the rest after T1 (O26-P1).
- [x] F&O passes run to 15:39 while a position is open (O26-M1).
- [x] The 409s were Dev's test suite polling the real partner bot; tests now have fake tokens and no network (O26-T1).
- [x] DAY shows the charges; a buy refused for funds shows its share of the cash.
- [x] Tests: Dev (Windows venv) full engine + scripts suites: 6,069 passed, 4 skipped, exit 0 (O26b's 6,056 plus 13 new cases). A run that refused every outside lookup passed too (before the last 10 cases): it listed the tests that had reached Telegram and NSE. Each fix's new test fails on the old code (checked with HEAD's file swapped in).
- [ ] Rollout with the next PR (owner's go-ahead): engine only; no setting.
- [ ] Owner: Oct 26's 22 censored research trades stay censored unless you want a backfill.
- [ ] Next session: SADHNANIQ should close once in each Smart book.

## October 26 — O26b A far bigger buy still warns on a quiet day; trades stored during the day; warnings scored by a frozen rule (Dev, commit `cf6befc`, pushed, deployed by PR #119 (`3b945eb`, Oct 26))

- [x] On a quiet day, a buy over 1.5x the partner's usual size, or bigger right after a loss, still gets one short size warning (SIZE). It is dropped if the trade is sold before it goes.
- [x] Every trade is stored as it changes (`partner_watch_trips`); `partner_watch_report <day>` lists them with the exact result after charges.
- [x] `partner_watch_score` scores the check's warnings by a rule frozen today. It decides only on days from Oct 27 and gives no verdict before 20 warned trades.
- [x] A restart no longer wipes a closed trade's buy-time facts (found by the new tests, fixed before the commit).
- [x] The flaky "send cut off part way" test is explained (the PLAN's send was sometimes the one that hung) and fixed: it waits for the PLAN first (35/35 runs).
- [x] Tests: partner files 633 passed. Full Dev (Windows venv) engine + scripts suites: 6,056 passed, 4 skipped, exit 0, 12 min 5 s (O26's 6,045 plus 11 new tests); the first full run had the one flaky test (fixed, above).
- [ ] Rollout with the next PR (owner's go-ahead): engine only; the new table creates itself; no setting.

## October 26 — O26 The trade watch tells the day so far once a step of the partner's cash; run figures agree with the warning (Dev, commit `6ec5ce1`, pushed, deployed by PR #119 (`3b945eb`, Oct 26))

- [x] DAY message: each further 10% of the day's cash lost today, once a step, also on a Quiet day. It gives the numbers (result, won and lost, buys soon after a loss, still open, the check to send) and never blocks.
- [x] The check's and the plan's run figure are rounded down: "20%" always comes with the chased-spike warning.
- [x] Tests: watch 112 passed; partner files 622 passed. Full Dev (Windows venv) engine + scripts suites: 6,045 passed, 4 skipped, exit 0, 11 min 50 s (O25N's 6,040 plus the 5 new tests).
- [ ] Rollout with the next PR (owner's go-ahead): engine only, no setting, no migration.
- Evidence behind it (Production, Oct 26, read-only): 21 buys in under three hours, about −₹5,300 after charges (estimated from the watch's looks), Quiet tapped at 09:28, nothing about the day as a whole. Not changed from one day: no threshold, no rule.

## October 25 — O25N O25M's open items closed; promoted to Production (commit `967c2d6`, pushed)

- [x] The brief, wrap, coach note and review prompt are retried only after a send that provably never left (5, 10, 20 min; 4 sends; within 60 min), from the stored text with "Written at". A possible delivery is never resent. New job `partner_daily_retry`.
- [x] A CHECK work-out cut off by a restart is worked out again (row `refreshing` until replaced).
- [x] Env audit (read-only, names and switches only): no orphan or missing names; no `.env` change needed. The real-money switches are still off and the owner halt is still on.
- [x] Tests: Dev (Windows venv) full engine + scripts suites: 6,039 passed, 4 skipped, 1 failed (the calendar-gate guard wanted the new cron's [CALENDAR-GATE] marker; added, then the guard, scheduler, golden and ledger tests: 40 passed). 6,040 = O25M's 6,031 plus 9 new tests. Tests do not show the partner's results or profitability.
- [x] Rollout done 18:45–18:56 IST:
  - PR #118 merged as `f9547c5`;
  - 8 database snapshots `quick_check=ok`, rollback tags `:7468853-20261025`;
  - Production fast-forwarded, built and recreated one service at a time, nginx restarted;
  - `verify_deployment.py` passed; env audit identical except the release SHA;
  - the new jobs are registered; switches off; owner halt on; no order or message.
- [x] Oct 25, 23:02 IST, config only: the owner put a new partner Kite app's `PARTNER_KITE_API_KEY` and
  `PARTNER_KITE_API_SECRET` in Production's root `.env` (`PARTNER_KITE_USER_ID` unchanged).
  - Only `python-engine` reads them, so only it was recreated (`up -d --no-deps --no-build --force-recreate`):
    same image, release `f9547c5`, healthy; no traceback; `/health` reasons unchanged (no_kite_token,
    instrument_cache_unavailable, order_execution_unverified).
  - Checked without printing values: both set, cleanly written, different from the owner's `KITE_API_KEY`, and
    the running engine has them. Zerodha's login page accepts the new key (a session is opened; a made-up key
    gets 400). The secret is proven only by the partner's first login with the new app.
  - The gateway reads only `PARTNER_KITE_USER_ID` (unchanged, matches); no other file holds these values.
  - Owner: the new app's redirect URL must be `<public URL>/api/partner-kite/callback`.
  - No code change, no deploy, no backup (no data change).

## October 25 — O25M R1–R3 fixed in Dev (commit `07e22da`, pushed)

- [x] R1: a CHECK reply is never sent after its prices' 15 s. It is worked out again once for the same option and expiry, else a no-numbers note to ask again.
- [x] R2: quotes need both clocks, zoned and believable. Missing or unreadable is UNVERIFIED, and a future exchange time is INVALID; neither checks a level. A typed price never makes an old quote current; an old future places no level.
- [x] R3: the partner's reminder is retried only after a send that provably never left (5, 10, 20 min; 4 sends; 07:00–08:30) and never after a possible delivery. New job `partner_login_reminder_retry`.
- [x] Tests: Dev (Windows venv) full engine suite 5,744 passed, 4 skipped (617 s) plus scripts/tests 287 passed: 6,031 in all (O25k's 6,015 plus the 16 new tests); focused partner suites 165 passed; the O25L review's four reproductions now fail against this code. Tests do not show the partner's results or profitability.
- [x] (O25N) Rolled out to Production with O25N as `f9547c5` (see the O25N receipt).
- [x] (O25N) The brief, EOD, coach note and review prompt now use the daily-send ledger.

## October 25 — O25L independent release/partner audit

- [x] Production `7468853` image/HTTP identity and Dev source parity verified; normalized hashes match 342 engine/gateway/agent source/config files. VM tunnel active/enabled and source matches Dev. No Production mutation during review.
- [x] Independent focused checks: 490 passed. Four isolated fake-data reproductions confirmed three gaps; they do not represent fixes.
- [x] (O25M) R1: rebuild or expire CHECK market-dependent text at delivery/retry, preserving exact contract identity and bounded/ambiguous delivery handling.
- [x] (O25M) R2: enforce valid quote clocks and current option/future evidence even when an entry price is supplied; label unavailable inputs honestly.
- [x] (O25M) R3: bounded safe retry for provably unsent morning reminders, without globally changing dedup or repeating ambiguous sends.
- [ ] First live partner session: both logins, account reconciliation, persisted message acknowledgement/latency and quote paths; streaming remains off. No unnecessary real trade for testing.
- [ ] Effective-date CAS/session/settlement maintenance before Dec 7; preserve current/replay rules. Subsequent stream and adaptive entry/exit evaluation follow the [review and concrete plan](2026-10-25-independent-production-partner-review.md).
- No source/schema/configuration/deployment change in this audit. Real-money switches remain off; no outbound message/order. Empty qualifications do not by themselves block owner-authorized NOT CHECKED cards.

## October 25 — O25k 07:00 login reminders with each person's own link; per-channel halt set (commit `1d40091`, pushed)

- [x] Production `.env`: OWNER_LIVE_ENTRY_HALT_CHANNELS=momentum,penny,edge. The global halt is still true.
- [x] 07:00 on trading days:
  - the owner gets the Kite login link (skipped if already logged in);
  - the partner gets their own login button, once a day, unless already logged in.
- [x] Tests: engine + scripts full suite 6,015 passed, 4 skipped, exit 0 (11 min 34 s); tests/test_login_reminder.py 5 passed; scheduler surface/census goldens pass with the 07:00 trigger. Not a profitability result.
- [x] Rolled out: PR #117 `7468853`; backup, rebuild, recreate; `verify_deployment.py` passed; reminders at 07:00, halts as set, tunnel answers.

## October 25 — O25j latest docs to Production, rebuild, tunnel settings applied (commit `0cc0edc`; receipt in the plan's O25j slice)

- [x] Real-money check: every engine entry path is off and the owner halt is on, so the engine's new order route can only carry exits.
- [x] Runbook step 9: lift OWNER_LIVE_ENTRY_HALT for F&O only before the Nov 2 run, or nothing buys.
- [x] Done 14:27–14:59 IST:
  - PR #116 merged as `b6b39e8` (`0aa629a` kept);
  - 8 database snapshots `quick_check=ok`, both `.env` backups, rollback image tags;
  - Production fast-forwarded and rebuilt; the tunnel lines added;
  - engine, gateway and agent recreated, nginx restarted;
  - `verify_deployment.py` passed; both services reach Kite through the tunnel;
  - switch false, entry halt true, no order.
- [ ] Owner:
  - the Kite login Monday before 09:15;
  - the weekend steps 1, 3 and 6–9;
  - step 10 after Nov 2.

## October 25 — O25i Oracle ingress complete; direct public tunnel verified

- [x] Owner-added NSG ingress confirmed: stateful TCP 31528, source `0.0.0.0/0`, all source ports. Existing rules retained.
- [x] Direct public negative checks 407/403, and both deployed-image transports HTTP 200 / verified TLS / fake-token rejection. No real broker credential, order or Production volume used.
- [x] Private canonical settings now select the direct endpoint; separate SSH settings/task retained. Receipt stored privately. Production services remain healthy at `0aa629a`, real-money switch off; no Production configuration edit or restart.
- [ ] Operator step 5 adoption, current login/read-only preflight, later funding/explicit order test/activation. Direct route has no SSH-task dependency. Use the updated [single checklist](runbooks/fno-live-test.md); older blocked-port statements below are historical.

## October 25 — O25h SSH bridge ready; Oracle website not needed for tunnel adoption

- [x] Probed the VM's actual cloud authority with official SDK: instance principal authenticated, VNIC read denied (404 `NotAuthorizedOrNotFound`); no cloud change. Removed temporary SDK.
- [x] Installed owner-level Scheduled Task **Trading Sentinel - Kite SSH Bridge**: strict host keys, loopback-only 31528, existing SSH port 22, keepalives, indefinite retries with duplicate instances ignored. Requires owner Windows login; no stored Windows password.
- [x] Actual client and deployed-image transport tests passed; missing-auth 407 / wrong-target 403 / verified TLS HTTP 200. Forced SSH process loss automatically recovered in 58.8 s. Stop/start left Production healthy. No reboot/physical network-loss test or real order.
- [x] Protected `tunnel-client.env` now selects the SSH route; direct endpoint retained separately. Task XML and verification receipt saved privately. No Production `.env` edit; existing application route unchanged.
- [ ] At operator adoption, follow step 5 in the updated live-test checklist and verify login/route. Keep Windows logged in and both SSH/tunnel healthy during trading. No Oracle website step required for this route; account recovery remains useful separately.
- [SSH bridge operation and rollback](runbooks/kite-ssh-bridge.md). This supersedes older statements that cloud 31528 ingress is required before any client adoption.

## October 25 — O25g Production recovered; PR #115 merged and deployed (`0aa629a`)

- [x] Started the three existing services, then verified dashboard/nginx recovery. Reviewed O25f and independently ran 66 focused tests; no new blocking defect found in that review.
- [x] Merged checked PR #115 through GitHub and fast-forwarded Production. Built sequentially and recreated engine, gateway, agent; all healthy, exact merged SHA verified in images/containers/HTTP. Engine log retention 20m x 25 and all application restart policies `always` are effective.
- [x] New Linux engine image: 74 tests passed. New gateway native SQLite/tunnel module checks passed. Protected rollback image tags and eight checked database backups retained outside both repositories.
- [x] Scheduler 88 jobs, partner registration 18, proving-week Oct 26–30 CLI works, evening report enabled. Real-money test false; live bankroll 0. Telegram read-only authentication passes; outbound delivery not tested. No real order sent. No direct Production source/configuration edit.
- [ ] Owner completes Oracle sign-in; permit cloud TCP 31528 and verify its direct TLS path before applying protected client settings. Old 31527 retained.
- [ ] Owner Kite login Monday before 09:15, partner's separate watch login, then observe the proving week's 15:50 reports. Funding/order test/Nov 2–6 activation remain later owner decisions.
- Full [recovery/release receipt](2026-10-25-production-recovery-and-release.md). Earlier stopped/unmerged descriptions below are historical.

## October 25 — O25f review of O25d/O25e: three gaps fixed; Production is down until the owner starts it (commit `e9645de`, Dev, pushed, in draft PR #115, not deployed, switch off)

- [x] Both order routes set: the engine keeps running and real orders are refused (NOT_SENT). It no longer fails at import.
- [x] A malformed run date: buys are refused, and the 09:25 and 15:50 messages still go out, naming it.
- [x] `restart: always` for the engine, gateway and agent. A Docker Desktop update on Oct 25 11:12–11:15 IST left them down.
- [x] The runbook says the tunnel is installed, the `.env` lines are in `tunnel-client.env`, and only the Oracle rule is left. It also adds a "Production running?" check and no updates in market hours.
- [x] Verified on the VM (read-only): `kite-tunnel` active/enabled, listening on 31528, VM firewall ACCEPT. From outside, 31528 does not answer and 31527 does.
- [x] Tests: engine + scripts full suite 6,010 passed, 4 skipped, exit 0 (11 min 36 s); focused suites 140 passed, 1 skipped; the three new regression tests fail on 94a262a/85b464a (checked in a throwaway worktree) and pass now; gateway code unchanged (O25d's receipt: 97 focused passed). Read-only checks: VM kite-tunnel active/enabled, 31528 listening, VM firewall ACCEPT; external 31528 times out, 31527 answers. Not a profitability result.
- [ ] Owner:
  1. `docker start python-engine`, `node-gateway`, `agent` (Production, now);
  2. the Oracle ingress rule for TCP 31528;
  3. PR #115 ready, merged and deployed;
  4. checklist steps 1, 3, 5–9 at the weekend;
  5. step 10 after Nov 2.

## October 25 — O25e VM installation receipt; cloud ingress pending

- [x] Owner's attached Linux USB searched read-only; recovered SSH access, strict saved-host-key match, authenticated expected Mumbai VM. Key and client settings are protected outside the repositories; no private values printed/committed.
- [x] Installed exact O25d source `94a262a`; matching SHA-256, active/enabled service, persisted VM TCP 31528 rule, settings/logs `0600`. Existing 31527 process retained.
- [x] Actual VM self-test **407 / 403 / verified TLS HTTP 200**. Engine and gateway client transports passed against this service through a temporary SSH forward (gateway in disposable Linux image). Fake tokens only; no order calls. Temporary resources closed/removed.
- [ ] Owner finishes Oracle Console sign-in/password recovery; inspect existing security list / NSG and permit 31528, then verify the direct public path. External TCP still times out.
- [ ] GitHub promotion of PR #115, operator client configuration, actual login/preflight and later funding/order test/Nov 2–6 activation. Production remains `582d7a5`, no tracked diff; no application restart or live-trading enablement.
- [ ] Production engine/gateway already stopped at 11:11:48 / 11:11:51 IST (exit 137, OOMKilled false), before this install. Diagnose/restore through the authorized rollout before Monday's messages are expected. Cause not established.
- Full [installation/rollback receipt](2026-10-25-oracle-tunnel-installation.md). This supersedes the older missing-SSH-key statement below; application deployment remains pending.

## October 25 — O25d remediation receipt (Dev code `94a262a`, pushed; VM access pending)

- [x] Documentation identity receipt `ca189f8` pushed; [draft PR #115](https://github.com/urveesh09/trading-sentinel/pull/115) created/attached for normal GitHub promotion. Not merged or deployed; broader S23–O25 branch changes are included.
- [x] All five review comments implemented: frozen authorized entry window/length, no order after failed preflight, conflicting routes rejected before HTTP clients, AMO maintenance excluded, authenticated loopback installer check with external restrictions retained.
- [x] Tests cover delayed startup, immutable dates/length, legacy run migration, zero order calls on failed checks, zero HTTP clients for conflicting routes, maintenance boundaries, restricted-loopback checks, and continued real exits after entries expire.
- [x] Full engine/scripts validation: **6,008 passed, 4 skipped**, exit 0; affected suite **314 passed, 1 existing skip**. Existing warnings and the separately reproduced injected penny-writer teardown diagnostic are documented in the active plan. A restrictive-allow-list real-Kite TLS self-test passed. No claim of deployment or profitability.
- [ ] Existing Oracle VM install/ingress and real client routes: owner confirmed an Oracle account; SSH key/agent and authenticated Console are still unavailable. Owner sign-in is needed; the page is left available. IP-range metadata indicates Mumbai; confirm instance ownership/identity before installation.
- [ ] Later: funds/current Kite login, explicitly authorized broker test order, and owner activation for Nov 2–6. `FNO_LIVE_TEST_ENABLED` stays false; Production is unchanged.
- Historical audit: [independent review](2026-10-25-independent-live-tunnel-review.md). Current implementation and verification: O25d at the top of the active plan and guide. Existing unrelated changes are excluded from implementation commits.

## October 25 — Independent O25b/O25c audit receipt (Dev documentation only)

- [x] Reviewed pushed `d67caad`; independent checks: 116 focused Python tests,
  97 focused gateway tests, and a real local Kite TLS self-test passed.
- [x] Corrected Dev runbook engine commands to use `--user quantuser`, and
  require deployment before invoking a newly shipped module.
- [x] Production inspected read-only: release `582d7a5`, switch false, proxy
  settings unset, no open FNO_LIVE positions/exit intents. Cached login is
  stale; cash is not verified. Old VM port reachable; new port timed out.
- [ ] Before real money: close the run-bound, failed-preflight and conflicting
  route configuration findings; add maintenance and allow-list tests.
- [ ] VM/Oracle installation and actual routes; current login/cash; GitHub
  promotion; explicitly authorized real-order test and later activation.
- Evidence and full remaining work: [review](2026-10-25-independent-live-tunnel-review.md).
  Audit documentation changes are local/uncommitted, not pushed or deployed.
  No strategy/source/configuration change, migration or atlas regeneration.

## October 25 (3) — O25c the owner's dates (proving Oct 26–30, checklist Oct 31–Nov 1, run Nov 2–6), the free encrypted Kite tunnel, a weekend test order (commit `cff5036`, Dev, pushed, not deployed, switch off)

- [x] `scripts/kite_tunnel.py` for the VM:
  - CONNECT to api.kite.trade:443 only, with a password;
  - `install` runs a self-test and prints both .env lines;
  - verified locally against real Kite on Python 3.8, 3.11 and 3.12; unit verified, exposure 1.5.
- [x] Gateway KITE_PROXY_URL: the SDK and the LTP call over TLS inside the tunnel. Verified with the real SDK against Kite.
- [x] Engine:
  - the route is checked to answer (preflight and 09:25), and the password is never printed;
  - a 3-minute market-hours probe of the order route (`📡 KITE ORDER ROUTE DOWN`).
- [x] The test order also runs at a weekend, as an after-market order cancelled before 09:15.
- [x] The runbook is one dated checklist (`docs/runbooks/fno-live-test.md`, steps 0–10).
- [x] Tests: engine + scripts full suite 5,994 passed, 4 skipped, exit 0 (11 min 26 s); gateway full suite 514 passed, 4 skipped, 18 failed only in db.test.js and backlog-reconciliation.test.js (better-sqlite3 cannot load on this Windows Node 24: environment); new tests: test_kite_tunnel.py 10, kite-tunnel.test.js 8, preflight +7, endpoint probe +3, readiness +1 case; live checks: the tunnel and both clients against the real api.kite.trade (Python 3.8/3.11/3.12, the gateway image's Node 20), systemd-analyze verify OK, exposure 1.5. Not a profitability result.
- [ ] Owner:
  - 0. optional: deploy before Mon Oct 26 09:15 (daily proving-week messages, Friday's verdict);
  - 1. the verdict;
  - 2. deploy;
  - 3. cash;
  - 4. the tunnel on the VM and the Oracle ingress rule for 31528;
  - 5. the two .env lines, then recreate both services;
  - 6. login;
  - 7. the read-only preflight;
  - 8. the test order;
  - 9. the switch;
  - 10. retire 31527 after Monday.

## October 25 (2) — O25b the review's nine gaps in the real-money test fixed; bounded runs, readiness, evidence, encrypted route option (commit `abbe073`, Dev, pushed, not deployed, switch off)

- [x] P1:
  - a gateway cleanup failure no longer stops protection;
  - refused price changes are retried, with the broker-confirmed price kept;
  - the exit's identity is written before the send and its order id before any wait, so a restart follows or recovers it by tag;
  - only an MIS holding on the right exchange may be sold;
  - a filled preflight buy is handed to the engine.
- [x] P2:
  - one-lot P&L from fills with one lot's own charges;
  - an UNAVAILABLE verdict when the drawdown halt is unknown;
  - NIFTY enforced in the buy;
  - the runbook order fixed.
- [x] Added:
  - a bounded run (5 sessions, named);
  - the 09:25 readiness message (the preflight runs once);
  - execution evidence in the 15:50 report;
  - KITE_ORDER_PROXY_URL for an encrypted route.
- [x] Tests: engine full suite (Dev, Windows, 10 min 6 s, after the last edit): 5,698 passed, 4 skipped, exit 0. `test_fno_live_test` has 26 tests; 6 reproduce the review's cases (refused modification, restart while the sell waits, lost reply, never-sent tagged exit, NRML holding, non-NIFTY) and failed before the fixes. `test_fno_proving_week` has 8 and `test_fno_live_preflight` 5. Against the previous modules (a scratch copy with `git show HEAD:` of `fno_proving_week.py` and `fno_live_preflight.py`), the one-lot-charges, unavailable-halt and preflight hand-off tests fail as they should. An earlier full run made during editing had one failure: `test_fno_shadow` reads the orchestrator's source by line number while the file was being edited. It passes 18 of 18 alone, and the final run is clean. Gateway: `executor.test.js` 65 passed (+1: a failed hold release keeps the GTT protection). The full gateway suite: 506 passed, 4 skipped, 18 failed in `db.test.js` and `backlog-reconciliation.test.js` (better-sqlite3 native binding unavailable on this Windows Node 24; the files are untouched). No order was placed anywhere. The relay was probed without credentials: plain HTTP answered 200, CONNECT answered 404.
- [ ] Owner:
  1. the verdict;
  2. deploy;
  3. relay: firewall the port to the home IP now, a CONNECT proxy before the run;
  4. the route in the `.env`, recreate the engine, the read-only preflight, the test order;
  5. the switch.

## October 25 — O25 the ₹12,500 real-money F&O test is ready behind one switch (commit `ca12934`, Dev, pushed, not deployed, switch off)

- [x] FNO_LIVE_TEST_ENABLED: one lot of what the paper book buys. NIFTY only, never on an expiry day, one position, own cash, a ₹7,000 floor. Sizing guardrails are relaxed for this test only.
- [x] Real-money gaps fixed before any real order:
  - a live exit left resting at a stale price (now worked down until it fills and followed up);
  - cash holds never released (the next day every buy would have been refused);
  - orders leaving from an unregistered IP (KITE_ORDER_BASE_URL);
  - an open live position unmanaged when switched off;
  - never selling what the broker no longer holds.
- [x] The proving week Oct 26–30 is pre-registered (`fno_proving_week`); a 15:50 owner message each day and the verdict on Fri Oct 30.
- [x] Preflight `python -m fno_live_preflight --test-order`; runbook `docs/runbooks/fno-live-test.md`.
- [x] Tests: engine full suite (Dev, Windows, 9 min 47 s): 5,684 passed, 4 skipped, 1 collection error -- pytest collected `fno_live_test.py` (its name matches `*_test.py`) and ran its helper `test_equity` as a test; renamed `live_equity`. After that, `pytest fno_live_test.py fno_live_preflight.py fno_proving_week.py --collect-only` collects nothing, and the affected files (`test_fno_live_test` 16, `test_fno_proving_week` 6, `test_fno_live_preflight` 3, `test_fno_orchestrator`, `test_fno_hourly_and_scheduler`, `test_performance`) pass 128 of 128. Gateway: `executor.test.js` 64 passed (1 new test, 1 new assertion). The full gateway suite: 505 passed, 4 skipped, 18 failed in `db.test.js` and `backlog-reconciliation.test.js`, which cannot load better-sqlite3's native binding on this Windows Node 24 (an environment limit; the files are untouched). `releaseFilled` was checked against real SQLite in a throwaway container of the gateway image (Node 20, no network). No order was placed anywhere.
- [ ] Deployed: no. Owner, in order:
  1. the verdict;
  2. deploy (engine, then gateway);
  3. ₹12,500 of free cash in the account;
  4. root `.env`: `KITE_ORDER_BASE_URL=http://161.118.160.180:31527`;
  5. the preflight PASS in market hours;
  6. `FNO_LIVE_TEST_ENABLED=true`, then recreate the engine.

## October 24 (night, 4) — O24i the F&O drawdown halt stays and is no longer silent (commit `0b7d7b9`, Dev, pushed, not deployed)

- [x] Decided (the owner delegated it): the 15% drawdown halt stays as it is. Its July – August losses were made by the same entry rule.
- [x] The owner is told once per change of the paper book's size tier or entry halts (`fno_risk_alert`), with the distance to the 15% line. Today: ₹14,298, about six average stop-outs.
- [x] The partner stays in English (no change needed).
- [x] Tests: engine full suite (Dev, Windows, 9 min 32 s): 5,658 passed, 4 skipped, 1 failed — `test_kite_client.py::TestRateLimiter::test_management_priority_is_bounded_and_normal_work_is_fair`, a 10 ms timing test that fails under suite load (`kite_client.py` is untouched; it passed 8 of 8 runs alone, and `test_kite_client` + `test_fno_risk_alert` + `test_fno_orchestrator` together: 66 passed, 1 skipped). `test_fno_risk_alert` 3 passed. Engine only; no client change.
- [ ] Deployed: no. After deploy, expect one owner message: "F&O paper risk: quarter size (0.25x) … ₹14,298 above the 15% halt line".

## October 24 (night, 3) — O24h F&O variants scored on real paths; exit slippage; "check before you buy" (commit `b8cf7a8`, Dev, pushed, not deployed)

- [x] The F&O shadow outcome was a target-hit scenario. The variants are now traded through the live book in the replay (`FNO_SIG_*`).
- [x] Study `fno-entry-t2` (frozen e37504f, scored once): the shipped entry is the best of five. The trend-day continuation is **not supported** and stays off; the variants keep being recorded.
- [x] The 15% drawdown halt cliff is attributed. The live paper book is ₹14,298 above it: an **owner decision**, nothing changed.
- [x] `python -m fno_exit_report`: 7 of 7 level exits since Sep 1 filled past their level (≈ ₹2,235), all before the 10 s fast exit.
- [x] The partner can send "check 22300 pe" for the plan before a buy; WATCH_ON tells them.
- [x] Tests: engine: the full suite 5,656 passed, 4 skipped, exit 0 (573 s); the partner and exit-report files 225 passed with thread and unraisable warnings as errors; study fno-entry-t2 scored once (10 reports) and the halt attribution run. No live broker or Telegram round trip (Saturday).
- [ ] Deployed: no. Ships with S23-O24g (rebuild the engine, then the gateway).
- [ ] Owner: the drawdown halt; the partner's language.

## October 24 (night, 2) — O24g stops moved together told together; "no stop" only from a GTT list read then; the order stream (off) and delivery measurement (commit `797d69b`, Dev, pushed, not deployed)

- [x] Fifth audit: GTTs moved down together were told for one only. Real, fixed. So were two SL orders modified together, and a move under the plan beside another move.
- [x] A "no stop" claim, or a sell-order claim counting a GTT, is made only from a GTT list read in that tick.
- [x] Order stream built, off (`PARTNER_WATCH_STREAM_ENABLED` false). Kite's order updates wake a tick at once; the 5 s reads go on regardless. New dependency `websockets==12.0` (rebuild the image).
- [x] Delivery measurement: `detected_by` per message, tick statistics per day, and `python -m partner_watch_report` (read-only).
- [x] Tests: engine: the full suite 5,648 passed, 4 skipped, exit 0 (576 s), after one test fix (an earlier run: 5,647 passed, 4 skipped, 1 failed, the refused-stream test reading the log through capsys); the watch, stream, partner and scheduler files 244 passed with thread and unraisable warnings as errors. The new tests against db167ed: 7 of the watch file's 95 fail there (the five issues, the wording, the retry). Client unit 65 passed. No live broker, websocket or Telegram round trip (Saturday).
- [ ] Deployed: no. Ships with S23-O24f (rebuild the engine, then the gateway).
  - On the first live day, run `docker exec -u quantuser python-engine python -m partner_watch_report` (read-only).
- [ ] Owner:
  - switch the stream on after the partner's plan has the websocket, and check one live day in the report;
  - pick the next partner features (O24b list).

## October 24 (night) — O24f "none held" only with evidence; sell orders matched by product; a replacement matched to the stop it replaced; the watch says when it cannot see (commit `320fe20`, Dev, pushed, not deployed)

- [x] Fourth audit of the watch: three issues, all real, all fixed. Each is a test that fails on 764055f's watch.
- [x] An orphan sell is "you hold none" only when Zerodha's positions show it. Otherwise the message says it could not check and does not say "cancel it": the order may protect a holding from an earlier day.
- [x] Sell orders are matched by product: an MIS sell on NRML units is told (PRODUCT, never muted).
- [x] A replacement stop is matched to the stop it replaced. Several changed together are told as one change, not paired. A stop cancelled with nothing new is not a move. A GTT modified down is a move.
- [x] A GTT that fired and sold part is told so, not as "no longer active".
- [x] BLIND and BACK, always sent:
  - BLIND: orders unreadable for 60 s; positions for 120 s while the overnight list is unknown; GTTs for 120 s while a holding's protection is unknown;
  - BACK: when that read works again.
- [x] One option held as MIS and NRML is named with the product; units that look converted say so.
- [x] Tests: engine: watch tests 88 passed (thread and unraisable warnings as errors); the six partner test files 204 passed; scheduler closures 26 passed. Full engine suite: 5,629 passed, 4 skipped, 5 errors (593 s). The 5 errors were all in `test_session_phase_golden.py`, at setup: its child Python failed to start (exit 0xC0000142) when Claude Code stopped the run's shell for low memory, and pytest went on to finish. That file then passed alone (7 passed). Client unit 65 passed. No live broker or Telegram round trip (Saturday).
- [ ] Deployed: no. Ships with S23-O24e (rebuild the engine, then the gateway).
  - On the first live days, read:
    - BLIND / BACK in `partner_watch_messages`, and the PRODUCT / ORPHAN counts;
    - `partner_watch_looks` against the 15 s.
- [ ] Owner:
  - streaming next (a websocket dependency, an image rebuild, the paid plan);
  - pick the next partner features (O24b list: pre-buy check and others).

## October 24 (late) — O24e the watch's last races closed; sell orders that could sell short (commit `79629e5`, Dev, pushed, not deployed)

- [x] Third audit of the watch: four gaps, all real, all fixed. Each is a test that fails on ad6190e's watch.
- [x] A message is sent only if the read it was built from is still the latest after the build and after its row is marked; otherwise it is built again (or dropped).
- [x] A plan version and its PLAN / ADDED message go in one transaction; a failed write leaves neither and is tried again on the next tick.
- [x] A moved stop is told for the units that stop sells, the rest said apart, and only while that same order waits there.
- [x] Without a plan stop (no market data, a swing as big as the price), the stop already in place is named; "place it now" is never said over it.
- [x] Freshness: our read ≤ 15 s old, and the exchange's last quote update ≤ 15 s before we received it (was 60 s).
- [x] New loss alarms, never muted:
  - EXCESS: sell orders for more than is held;
  - ORPHAN: sell orders waiting with nothing held.
- [x] The plan no longer tells the partner to raise a lower stop (a comparison only).
- [x] Tests: engine full suite 5620 passed, 4 skipped, exit 0 (9 m 41 s, `winvenv/Scripts/python -m pytest -q`); `tests/test_partner_watch.py` 74 passed (62 before), 60 repeated runs clean after one unreproduced failure (see Remaining); client unit 65 passed (no client change). The new tick tests were run against ad6190e's watch: the four audit gaps and the two new alarms fail there for their reasons; the cut-off-send test passes there too (O24d was already conservative). No live broker or Telegram round trip (Saturday, market closed).
- [ ] Deployed: no. Ships with S23-O24d (rebuild the engine, then the gateway).
  - On the first live days, read:
    - `partner_watch_looks` received_at − quote_at (the 15 s);
    - `partner_watch_messages` outcomes and the EXCESS / ORPHAN counts.
- [ ] Owner:
  - streaming next (a websocket dependency, an image rebuild, the paid plan);
  - pick the next partner features (O24b list: pre-buy check and others).

## October 24 (night) — O24d the watch's advice stays with the partner's position (commit `677c630`, Dev, pushed, not deployed)

- [x] Audit of O24c: seven gaps, all real, all fixed. Each is a test that fails on 2effb5d's watch.
- [x] Stop advice starts from what protects the units:
  - no second SL when a stop already covers them;
  - a tighter stop is never widened;
  - a part covered gets an SL for the rest only.
- [x] Outbox: each message is built just before it is sent, from the latest book read.
  - A plan for a trade already closed, or a warning no longer true, is `superseded`, not sent.
  - A provably unsent message survives a restart and is sent rebuilt.
- [x] Keys per trade and incident. A later trade in the same option, or a carried position the next day, gets its own warnings.
  - What covered a trade is remembered across a restart.
- [x] One reconciled count (Zerodha's when it differs) for every message and plan version. What was bought and sold is said apart.
- [x] Levels are instructions only against a fresh price (STALE / UNCHECKED: a reference to check). Selling now is priced against the bids' sizes.
- [x] Tick budget: reads and waits share 4 s; optional reads wait a tick; sending goes beside the tick.
- [x] Review: an off-card trade with the partner's own SL is not said to have "no written stop".
- [x] Tests: engine full suite 5608 passed, 4 skipped, exit 0 (9 m 35 s, `winvenv/Scripts/python -m pytest -q`); `tests/test_partner_watch.py` 62 passed (45 before); the partner and backstop test files 240 passed; client unit 65 passed (no client change). The 13 new tick tests were run against 2effb5d's watch: 12 fail for the audit's reasons, the lifecycle test only on the new cover line. No live broker or Telegram round trip (Saturday, market closed).
- [ ] Deployed: no. Ships with S23-O24c (rebuild the engine, then the gateway).
  - On the first live day, read `partner_watch_messages`:
    - the outcomes (acknowledged / superseded / expired / muted);
    - detected_at − event_at and sent_at − detected_at.
- [ ] Owner: streaming once the partner's paid plan is active (a new websocket dependency, an image rebuild, a live check). Pick the next partner features (O24b list).

## October 24 (evening) — O24c the trade watch made trustworthy; a fired backstop recognised; a stable usual size (commit `7d0cb6f`, Dev, pushed, not deployed)

- [x] Audit A-G on 08a95e3 reproduced and fixed.
  - Each reproduction is a test that the old code fails.
  - Before/after probe: A1 130 → 65 held, A2 0 → 65, B "protected" → ABSENT, D "place SL at ₹90" (price ₹20) → "already under the plan stop", F fired backstop found.
- [x] Held: from each fill (GET /trades), per product, a carried position from its overnight quantity, confirmed by Zerodha's positions. A difference uses Zerodha's count, and the message says so.
- [x] Cover: FULL / PARTIAL / ABSENT / UNKNOWN with units, same product only.
  - A fired stop that has not sold → UNFILLED after 10 s.
  - An unreadable GTT list says nothing and is read again.
- [x] Delivery: a provably unsent message (no connection / 429 / 5xx) is sent again, rebuilt; a timeout is not. Event, detection and Telegram-ack times are stored.
- [x] Levels: checked against the price just read; a crossed plan stop is never offered as a stop. Futures levels are named as futures.
- [x] Plans: version 1 immutable; a restart reloads it; a new buy order adds a version and an ADDED message.
- [x] Timing: book reads ≤ 4 s each; the plan runs beside the tick (≤ 1.5 s wait, 25 s deadline).
- [x] Backstop: a fired SL listed as LIMIT with its trigger is recognised.
- [x] Review: the usual size starts from the 45 days before the window; "Rules of 24 Oct 2026" on the page and the PDF.
- [x] Tests: engine full suite 5590 passed, 4 skipped, exit 0 (9 m 31 s, on the final code; an earlier run before the last test: 5589 passed); tests/test_partner_watch.py 45 passed; client unit tests 65 passed; Vite build passed. Before/after probe on 08a95e3 vs the working tree: A1 130 → 65 held, A2 0 → 65, B 'protected' → ABSENT, D 'Place the SL order now: trigger ₹90' (price ₹20) → 'already under the plan stop', F fired backstop False → True. No live broker or Telegram round trip (market closed).
- [ ] Deployed: no. Ships with S23-O24b (rebuild the engine, then the gateway).
  - After deploy, on the first live day, read `partner_watch_messages`: detected_at − event_at, sent_at − detected_at, the outcomes and the PARTIAL count.
- [ ] Owner: streaming once the partner's ₹500 plan is active (new websocket dependency, image rebuild, live check).

## October 24 (afternoon) — O24b partner size vs their habit; system on the 15:40 F&O close (commit `3c6523e`, Dev, pushed, not deployed)

- [x] O24-SZ: no fixed tenth of cash anywhere for the partner.
  - UNUSUAL_SIZE flags more than 1.5 times their usual share; the usual is the median of the last 20 trades, once there are 5.
  - The rule is "Usual size".
  - The watch warns only on a much-bigger-than-usual buy.
- [x] O24-MC2: the F&O session facts are at 15:40:
  - time to expiry, the hedge gamma hours, futures candles (job at 15:45), the analytics gate, the expiry-book capital close;
  - the ops, health and telemetry windows.
  - Cash stays at 15:30, and strategy times are unchanged.
- [x] Tests: engine full suite 5560 passed, 4 skipped, 1 failed (winvenv, Python 3.11.9, 9 min 23 s): the failure was tests/test_oct21_audit_fixes.py's weekday session length, which is now 09:15-15:40 (23,100 s); that test was updated and passes, together with tests/test_partner_insights.py (53 passed). After the run only those two test expectations changed, not code. The modules moved to 15:40 have their tests passing: 346 in the targeted run, then 43 after the updates. The watch 20, insights 34 and PDF 13 tests pass. The Oct 23 review rebuilt on a copy of Production's partner tables gives Usual size 12/12 and score 43/72. The route golden changes only research_future_candles (15:40 -> 15:45)
- [ ] Deployed: no. Ships with O24 (rebuild the engine).
  - After deploy: Oct 23's review shows "Usual size 12/12".
  - `research_future_candles` runs at 15:45.
- [ ] Owner: decide whether any strategy time should move with the close (FNO hard flat 15:10, entries end 14:45, the expiry book's BL late 15:30).

## October 24 — O24 partner: stops as Zerodha shows them, 15:40 close, plain refusals, trade watch (commit `53280d9`, Dev, pushed, not deployed)

- [x] O24-SR the review reads every stop:
  - fired stops (LIMIT/MARKET with a trigger);
  - stops turned into a sale (CONVERTED, from the history);
  - placement times from the history;
  - older days rebuilt from trigger changes;
  - a sale that cannot be told says nothing.
- [x] O24-RF Zerodha's refusals in plain words: margin for a buy, and a sale counted as a new short sale (another sell waiting, more than held, or the products differ).
- [x] O24-MC the partner modules close at 15:40 (`market_calendar.DERIVATIVES_CLOSE_TIME`); the evening wrap moves to 15:50.
- [x] O24-PW the trade watch (`partner_watch.py`), messages only:
  - a 09:00 login button, then "watch on";
  - every 5 s: PLAN, NO_STOP, LOWERED (first, then under the plan or off the buy price), REMOVED, REFUSED, CLOSE;
  - "Quiet today" keeps only LOWERED, REMOVED and REFUSED;
  - a reconnect button after a lost login;
  - shadow looks every 15 s;
  - "Assistant: …" lines in the review.
- [x] Tests: engine full suite 5559 passed, 4 skipped, exit 0 (winvenv, Python 3.11.9, 9 min 29 s); an earlier full run had one timing flake in tests/test_kite_client.py (the rate-limiter fairness test, untouched code), which passed 3 of 3 alone; partner tests 224 passed (new tests/test_partner_stop_reading.py 15 and tests/test_partner_watch.py 19); client unit tests 64 passed and the Vite build passes; a server render of the page shows the assistant line, the plain refusal and the lesson; the Oct 23 review rebuilt with Dev code on a copy of Production's partner tables (read-only export) gives the numbers above; the route goldens add exactly partner_watch_tick and partner_watch_prompt and move partner_eod_wrap and partner_hedge_eod_summary from 15:40 to 15:50
- [ ] Deployed: no.
  - Rebuild the engine, then the gateway.
  - First trading day after deploy:
    - 09:00 login button;
    - after the login, "Trade watch on until 15:40";
    - a PLAN message within about 10 s of a buy;
    - `partner_watch_message kind=… delivered=True` lines;
    - `partner_watch_messages` rows;
    - the review's Oct 23 shows "Moved the stop down · 9 times".
- [ ] The paid Kite plan on the partner's key: no code change needed.
  - If Zerodha issues a new API key or secret, the owner updates the root `.env` and restarts the engine.
  - Log `partner_watch_partner_market_data_unavailable` means the key has no market data, and the owner's quotes are used.
- [ ] Owner decisions open:
  - the system-wide 15:40 close (time to expiry, EOD and attribution times, analytics gates);
  - when to score the shadow exit plans;
  - whether the "more than a tenth of your cash" line should use another share.

## October 23 (evening) — O23 partner review: earlier days, PDF, rule meanings (commit `66cfb7c`, Dev, pushed, not deployed)

- [x] O23-PH earlier days:
  - a day bar steps back and forward and lists 120 days;
  - Progress days open their review;
  - an earlier day reads "that day", and tomorrow's focus shows on the newest day only;
  - Progress stays the last 30 days whichever day is open.
- [x] O23-PD "Download PDF": the open day's review as `trading-review-YYYY-MM-DD.pdf` (engine reportlab + DejaVu; gateway passes only a PDF, 20 a minute, session needed).
- [x] O23-PM every rule says what it means. "Traded a card" = the trade was on a card the system sent on Telegram that day (the same option, bought after the card arrived).
- [x] Tests: engine full suite 5524 passed, 4 skipped, exit 0 (winvenv, Python 3.11.9, 9 min 12 s); the new tests/test_partner_review_pdf.py 12 passed; in the engine image (Debian 13, Python 3.11.17, fonts-dejavu-core, pinned packages) the partner tests 111 passed and the default font path embeds DejaVu with every symbol covered; gateway jest in a throwaway container 522 passed, 4 skipped (40/41 suites, partner-kite 10); client unit tests 63 passed and the Vite build passes; the real Oct 23 review printed to an 11-page PDF in 0.25 s and was checked page by page; the route golden adds exactly the two new GET routes
- [ ] Deployed: no.
  - The engine image needs a rebuild (reportlab, pillow, charset-normalizer, fonts-dejavu-core); then the gateway.
  - After deploy:
    - open `/?view=review` and step to Oct 19;
    - download Oct 23's PDF;
    - in the engine, `python -c "import partner_review_pdf as p; print(p.fonts())"` names `ReviewSans-…` with `embedded=True`.
- [ ] Check on the partner's phone that the download works from the Telegram link; if the in-app browser blocks it, decide whether to add "Send the PDF to my Telegram".

## October 23 — S23 Oct 23 audit fixes (commit `7e2a2b9`, Dev, pushed, not deployed)

- [x] S23-BS1 (P1, live only): a lost backstop receipt is resolved by the order's own tag, quantity, exchange and time, never by shape; doubt holds the exit and pages. The audit's reproducer now proceeds instead of adopting the old stop.
- [x] S23-COST1: one rule for equity charges. CNC sold the session it was bought pays intraday charges; held overnight it pays the full delivery schedule (tracker, EDGE confirmed exit, Momentum closes). DCMSRIND would be ₹48.84, not ₹82.58 (and not the audit's ₹118.31).
- [x] S23-G1: entry gates price full costs (the ₹50k bypass is gone); Momentum acceptance unchanged.
- [x] S23-SG: engine `stop_grace_period: 45s`, uvicorn graceful wait 10 s.
- [x] S23-R1: second Momentum terminal pass at 16:05 for trades still censored.
- [x] S23-U1: ETF iNAV tickers left out of the universe screen.
- [x] S23-H1: gateway health degrades on recent dead letters, recent unsynced orders and any unsynced order that may have filled; older settled backlog is under `stale_backlog`.
- [x] S23-T1: every scheduler run has its id before its marker; completions are written with the growing budgets and replay without duplicates.
- [x] S23-M1/M2: nudge quotes the last measured refresh; 16:00 digest has an all-books block (main, Smart V1, overnight with holdings, subtotal; V2 apart).
- [x] S23-S1: overnight trades record displayed bid/ask and the exit-quote bid; the comparison shows `realism` counterfactuals. S23-Q1: short quote batches name the missing symbols.
- [x] S23-D1: PR #112/#113 slices now say deployed.
- [ ] Oct 6 Momentum allocation holdout is due; evaluate it at `b03afa5` (its fingerprint commit, since S23 changed `engine.py`).
- [x] Tests: engine 5512 passed, 4 skipped (full suite, exit 0); gateway 519 passed, 4 skipped (full jest suite in a throwaway Linux container from the gateway image, no network); the health, dead-letter and backlog suites re-run after comment edits: 19 passed.
- [ ] Deployed: no. After deploy, see the plan's rollout list (clean shutdown receipt, 16:05 retry line, smaller history scope, health `ok` with `stale_backlog`, nudge, digest block, overnight `realism`).
- [ ] Owner decisions pending: old backlog clean-up via the reviewed reconciliation; whether anything about the ₹127.79 historical over-charge is reported beyond the docs (the ledger is not rewritten).

## October 22 (evening) — T22-BG / T22-U (commit `3a9f674`, Dev, pushed, deployed 2026-10-22 19:38 IST by PR #114 (`582d7a5`))

- [x] Suite hang at exit diagnosed: a leaked aiosqlite worker from an unheld startup catch-up. Not caused by A22; A22 itself passed in full (5,451).
- [x] Fourteen fire-and-forget sites are held via `background_tasks.spawn` (ledger write, post-login init, catch-ups, alerts); failures are logged; shutdown drains.
- [x] Tests can no longer hang: per-test drain plus a session-end connection guard.
- [x] `aiosqlite` pinned 0.20.0 → 0.21.0: 0.20 leaked a worker when a connect was cancelled mid-open (proven by a test that fails on 0.20.0). The engine image must be rebuilt to pick it up.
- [x] Universe refresh reads history only for quoted in-band EQ symbols; universe identical over 40 randomised sets; Production estimate 10,235 → ~956 reads.
- [x] Tests: engine 5460 passed, 4 skipped (full suite, Windows winvenv, aiosqlite 0.21.0; exit 0, no leaked worker); client unchanged (60 passed, vite build ok).
- [x] Deployed 2026-10-22 19:38 IST (PR #114, `582d7a5`). Images were built one service at a time (a combined build was stopped for low host memory). `verify_deployment.py` passed for the engine, gateway and agent; the engine image has aiosqlite 0.21.0; no `Task was destroyed` or errors on start; `/health` shows the release and `fno_exit_paths` (recording, 0). `trading_ready=false` is the standing `order_execution_unverified` (no real broker order yet).
- [ ] Next session (2026-10-23): `penny_universe_refresh_done elapsed` in minutes, `penny_universe_history_scope fetch≈900–1,000`, `count=100`, quality audit like today's.
- [x] (done in S23-SG) Engine stop grace: SIGKILL came 3 s after SIGTERM at this redeploy (exit 137, `cause=unclean_stop`); see the plan.

## October 22 — A22 audit follow-up (commit `ffa979c`, Dev, pushed, deployed 2026-10-22 19:38 IST by PR #114 (`582d7a5`))

- [x] P1 broker backstop: intent before send, an unreadable ledger holds the exit, uncertain sends reconciled from the order book (live only).
- [x] P2 Momentum terminal pass: history fetched with no write lock held; one short transaction per ticker.
- [x] P2 exit-path recorder: bounded queue, one guarded writer thread, per-session cap, drops counted (ops `fno_exit_paths`), drained on shutdown; settings bound on each line.
- [x] P2 exit-arm evaluator: scores only bound, same-contract, gap-free evidence whose CURRENT reproduces the live exit; mismatches listed.
- [x] P2 partner login: one 35 s deadline; deeper read and coach note in the background; the review shows progress.
- [x] P2 coaching extrema: whole minutes inside the holding only; buy/sale-minute prices shown apart as uncertain.
- [x] Enrichments: Smart V1/V2 `versus` (opportunities, stop-outs, missed winners, fees, hold, rupee-hours); scope labels; version separation verified.
- [x] Tests: engine 5451 passed, 4 skipped (full suite, Windows winvenv); client 60 node tests passed, vite build ok; gateway partner-kite jest 7 passed.
- [x] Deployed 2026-10-22 19:38 IST (PR #114); `/health` has the `fno_exit_paths` counters.
- [ ] Still to see on live use: `params` on the first exit-path line of an F&O position, the partner login status line, `versus` in `/experiments/penny-smart`.

## October 21 (night, 3) — SX-F1 / SX-P2 owner-delegated calls (commit `ace52ab`, Dev, pushed, deployed: merged by PR #113 (`33065ed`), running in Production at `582d7a5` (Oct 23 audit attestation))

- [x] F&O profit lock needs a second look ≥ 8 s after the first under its floor (rollback `FNO_PROFIT_LOCK_CONFIRM_SEC=0`).
- [x] Every F&O exit look recorded (`fno_exit_paths`), exported, and replayable by arm (`fno_exit_cadence.py`).
- [x] PEN_SMART_V2 (wider noise-aware stop, three-close thesis failure) runs beside unchanged V1; `GET /experiments/penny-smart`.
- [x] Partner cards and expiry promotions: no change, with the reasons in SYSTEM_GUIDE.
- [x] Tests: new 14; full engine suite 5,433 passed, 4 skipped, 0 failed (9 min).
- [ ] Deployed: no. After deploy: exit-path lines on the first F&O position; two Smart state rows after the first Penny scan.
## October 21 (night, 2) — SX-M1 Momentum shadow scoring (commit `27ee87b`, Dev, pushed, deployed: merged by PR #113 (`33065ed`), running in Production at `582d7a5` (Oct 23 audit attestation))

- [x] Gap-exit closes shown apart and never scored; promotion gate counts scored closes. Related tests 58 pass; full suite not rerun.
- [ ] SX-F1 F&O live-cadence exit evidence: designed only (see NEXT_AGENT_PLAN).
## October 21 (night) — O21-PX partner's deeper review (commit `68eec28`, Dev, branch `codex/production-correction-hedge-p0`, pushed, deployed: merged by PR #113 (`33065ed`), running in Production at `582d7a5` (Oct 23 audit attestation))

- [x] One review link every trading day after the brief
  (`ensure_review_message`: the coach note's button, else the prompt).
- [x] Partner's Zerodha read adds order history (numeric id GET), positions
  and equity margins, best effort; new tables `partner_orders`,
  `partner_order_changes`, `partner_broker_positions`,
  `partner_account_days`.
- [x] Traded options' 1-minute candles from the owner's market data (prints
  fallback), `partner_trade_paths`; gateway login wait 45 s.
- [x] Round trips split (re-entries are their own trades); ENTRY_UNDER_STOP;
  new lessons CHASED_SPIKE, GAVE_BACK_PROFIT, STOP_LOWERED,
  PRICE_RAISED_TO_FILL, BIG_RISK, HELD_OVERNIGHT, INSUFFICIENT_FUNDS;
  positives CUT_LOSS_SAVED, STOP_TRAILED.
- [x] Review: rules kept, per-trade chart and "what the option did", day
  numbers, orders, window statistics with plain lines, tomorrow's focus.
- [x] Tests: `tests/test_partner_insights.py` 31 pass; partner suites 120
  pass; full engine suite 5,417 passed, 4 skipped, 0 failed (9 min 24 s); client `node --test` 59 pass;
  `npx vite build` OK; gateway partner jest 10 pass.
- [ ] Deployed: no. Merge the branch, rebuild engine and gateway (no new
  setting; the partner's keys as already listed).
- [ ] After deploy: the 15:40 link; after the partner's login the
  `partner_paths_stored` line and charts on the review.
## October 21 (late) — Oct 21 audit fixes + overnight forward shadows (commit `462d28f`, Dev, branch `codex/oct21-audit-fixes`, pushed, deployed: merged by PR #112 (`046f3ff`), running in Production at `582d7a5` (Oct 23 audit attestation))

- [x] S21-R1 15:32 terminal pass for virtual Momentum trades (receipts
  CLOSED / CENSORED); S21-R2 RS identity binds index, daily bars, rules,
  pool; S21-R3 replay runtime arm admits like the runtime; S21-E1 EDGE
  entry-day event check; S21-L1 restart overlap on trading sessions.
- [x] R21-M1 EDGE rows carry real outcomes, ranking is not a gate, alarm
  wording; R21-M2 hourly allocation and equity; heartbeat slot on
  delivery; T21-X transport kinds.
- [x] O21-ON shadows `ON_TWO_LARGER` and `ON_TIGHT_SPREAD` on the overnight
  book (declared 2026-10-21 from the book's own cost split; research only,
  own cash) and `GET /experiments/edge-overnight`.
- [x] Docs drift: the Oct 19 fix tests are 15 (collected), not 17.
- [x] Tests: new `tests/test_oct21_audit_fixes.py` 18 pass;
  `tests/test_oct15_audit_fixes.py` updated (transport kinds); related
  suites 223 pass; goldens regenerated (one route, one job); full engine
  suite 5,386 passed, 4 skipped, 0 failed (9 min 2 s); `scripts/tests` 276 pass.
- [x] Evidence used (read-only, Production engine container): the overnight
  store's 16 split exits (close→open +₹986.97, entry spread −₹462.11,
  15:20→close −₹108.41, charges ₹677.78 over 20 closes, net −₹991.05).
- [ ] Deployed: no. Merge order: `codex/production-correction-hedge-p0`,
  `codex/partner-coach-standard-capital`, then this branch (it contains
  both); rebuild the engine.
- [ ] After deploy: `momentum_shadow_terminal` at 15:32 with closed/censored
  counts; shadow rows at the 15:20 overnight entry; the 15:45 EDGE alarm
  quiet when the paper leg enters, or naming the real refusal.

## October 21 (night) — the partner's review page + explained lessons (commit `6f882f0`, Dev, branch `codex/partner-coach-standard-capital`, pushed, deployed: merged by PR #112 (`046f3ff`), running in Production at `582d7a5` (Oct 23 audit attestation))

- [x] O21-PL each flag: what happened, why it matters (this trade's
  numbers), the better action and what it would have paid, the rule;
  impact = actual − better, same order count; a profitable rule-break is
  still a lesson.
- [x] Stop discipline from Zerodha (SL orders + GTTs, GET `/gtt/triggers`
  read-only): no stop, stop wider than the card, stop cancelled; only on
  complete days with the GTT list read.
- [x] `partner_lessons.py`: the day review (lesson of the day with the same
  trade's other mistakes folded in, what went well, trade stories, cards not
  taken, data notes), progress (this week against last, clean streak), the
  evening note.
- [x] Partner dashboard `PartnerReview.jsx` (Today / Progress / All
  details); Zerodha login lands on it; owner "Partner's view" button.
- [x] Tests: `tests/test_partner_coach.py` rewritten (21, every figure
  recomputed), new `tests/test_partner_lessons.py` 10,
  `tests/test_partner_broker_sync.py` 32; with
  `tests/test_partner_fill_capture.py` 89 pass; golden regenerated (one
  route); full engine suite 5,368 passed, 4 skipped, 0 failed (9 min 1 s). Gateway
  `tests/integration/partner-kite.test.js` 7 pass; full jest 498 pass, 18 fail in `tests/unit/db.test.js` and `tests/unit/backlog-reconciliation.test.js` (better-sqlite3 has no native binary on this Windows host; environment, as before).
  Client `node --test tests/*.test.mjs` 56 pass (new
  `tests/partnerReview.test.mjs` 4); `vite build` ok; the page was
  server-rendered with a real `/partner/review` payload (no runtime error).
- [x] Environment: Windows `python-engine/winvenv` (pytest 8.0.0); no
  browser in this session (render checked server-side, not on screen).
- [ ] Deployed: no. Same order as below.
- [ ] First Zerodha evening: open the review on a phone; check the lesson
  against the partner's Kite order book.

## October 21 (evening) — the partner's Zerodha fills + coach-only review page (commit `9648f95`, Dev, branch `codex/partner-coach-standard-capital`, pushed, deployed: merged by PR #112 (`046f3ff`), running in Production at `582d7a5` (Oct 23 audit attestation))

- [x] O21-PK `partner_broker_sync.py`: evening "Open today's review" button
  (Kite login for the partner's own Personal app); the callback reads GET
  `/orders` + `/trades` only, refuses any account but
  `PARTNER_KITE_USER_ID`, token in memory until 06:00; one ZERODHA report
  per filled option order, matched to cards; `partner_broker_days`.
- [x] Coach: Zerodha fills replace taps on read days; NOT_TRADED after a
  complete read; the note waits for the read and says "(from Zerodha)".
  Card buttons off while Zerodha is configured.
- [x] Gateway `/api/partner-kite/callback` + `/coach`: coach-only session
  (`partner_view`, never `authenticated`); client "Your trading review".
- [x] Owner `/api/auth/callback` refuses the partner's account (or every
  account but `ZERODHA_USER_ID`). It never checked the account before.
- [x] Tests: new `tests/test_partner_broker_sync.py` 28; with
  `tests/test_partner_coach.py` and `tests/test_partner_fill_capture.py`
  63 pass; golden regenerated (3 route additions); full engine suite
  5,341 passed, 4 skipped, 0 failed (9 min 12 s; collected before the 28th Zerodha test, which passes on its own). Gateway: new `tests/integration/partner-kite.test.js` 6 and
  `tests/unit/auth-account-guard.test.js` 3 pass;
  full jest 497 pass, 18 fail in `tests/unit/db.test.js` and `tests/unit/backlog-reconciliation.test.js` (better-sqlite3 has no native binary on this Windows host; environment, as in the afternoon receipt). Client: `node --test tests/*.test.mjs` 52 pass;
  `vite build` ok.
- [x] Environment: Windows `python-engine/winvenv` (pytest 8.0.0); Kite
  behaviour from Zerodha's docs (Personal plan: order and portfolio APIs, no
  market data; static IP for order endpoints only; token expiry 06:00), not
  yet exercised against the partner's account.
- [ ] Deployed: no. Same order as below (expiry-v3 first, then this branch).
- [ ] Setup: the owner creates a separate app in their developer account
  with the partner's client ID (redirect
  `https://<NGROK_URL>/api/partner-kite/callback`; Personal if offered). The owner
  adds `PARTNER_KITE_API_KEY`, `PARTNER_KITE_API_SECRET` and
  `PARTNER_KITE_USER_ID` to the root `.env`, and `PARTNER_KITE_USER_ID`
  (plus their own `ZERODHA_USER_ID`) to `node-gateway/.env`. Then restart
  the engine and gateway.
- [ ] First evening: the prompt arrives after 15:40; the login lands on the
  review; `partner_zerodha_synced` count matches the partner's order book.

## October 21 (afternoon) — partner fill capture + coach, standard capital, F&O broker backstop (commit `b580af2`, Dev, branch `codex/partner-coach-standard-capital`, pushed, deployed: merged by PR #112 (`046f3ff`), running in Production at `582d7a5` (Oct 23 audit attestation))

- [x] O21-PC cards carry Bought/Skipped buttons, exit updates Sold; replies
  record or correct prices; off-card "b NIFTY 22950 PE 120 x2"; only the
  partner chat is read; card text and gates unchanged.
- [x] Partner Coach page + `GET /partner/coach`: did vs card plan, flags with
  reasons and rupee effect, manual reaction allowance 120 s; evening note
  only on days with reported trades; card price paths frozen at the wrap.
- [x] O21-SC Standard Capital page + `GET /performance/standard-capital`:
  every book on one capital (₹10k / ₹12.5k / ₹2L / ₹5L / custom), `since`
  for the current version; read-only, paper, not a forecast.
- [x] O21-BS live F&O entries rest a broker SL backstop; exits cancel and
  read it first; paper never places one.
- [x] Tests: new `tests/test_partner_fill_capture.py` 26,
  `tests/test_partner_coach.py` 9, `tests/test_standard_capital.py` 8,
  `tests/test_fno_broker_backstop.py` 17; goldens regenerated (additions
  only); full engine suite 5,314 passed, 4 skipped, 0 failed (9 min 15 s). Clean baseline at `561ae70` in a
  scratch worktree: 5,254 passed, 4 skipped (9 min 8 s). Gateway: new
  `tests/integration/partner-coach-proxy.test.js` 4 pass; full jest 488
  pass, 18 fail in `tests/unit/db.test.js` and
  `tests/unit/backlog-reconciliation.test.js` (better-sqlite3 has no native
  binary on this Windows host: "Could not locate the bindings file";
  environment, not code). Client: `node --test` 51 pass; `vite build` ok.
- [x] `tests/test_mark_to_market.py` clock race fixed: one fixed instant per
  module (a quote stamped after `now` had a negative age and read STALE);
  46/46 three runs in a row. The Oct 19 receipt's 5,527 vs Oct 21's 5,253:
  the Oct 19 run also included `scripts/tests` (276 tests, all pass today);
  no engine test disappeared.
- [x] Environment: tests ran with `python-engine/winvenv` (Windows, pytest
  8.0.0); the Production trial ran read-only inside the engine container
  (`-u quantuser`, SQLite `mode=ro`).
- [ ] Deployed: no. Merge `codex/production-correction-hedge-p0` first
  (expiry-v3, before Thursday's SENSEX expiry), then this branch; rebuild
  engine and gateway outside 12:59–15:40 on an expiry day.
- [ ] After deploy: `partner_cron_registered jobs=16`; no getUpdates 409;
  tell the partner about the buttons (only without Zerodha; with it the
  evening "Open today's review" button replaces them, O21-PK above).

## October 21 — expiry-v3 (B takes BP's pair target) and expiry-shadow-v5 (commit `a88da98`, Dev, pushed, deployed: merged by PR #112 (`046f3ff`), running in Production at `582d7a5` (Oct 23 audit attestation))

- [x] B (main) sells both legs once the pair nets 20% after fees (BP's rule).
  BP was never worse than B on any expiry B traded (+₹2,998.74 over four;
  Oct 19 forward +₹722.46).
- [x] BL (shadow) = v2's per-leg B on the same strangle; BP retired, its
  history still prints. BR is BL plus its leg stop.
- [x] CI (new shadow) = C sold once the index is back inside the box
  (in-sample +₹2,429.99 against C); AE tested and not added (−₹167.32).
- [x] A, C, D, budgets, execution and the owner's 10-expiry rule unchanged.
- [x] Oct 19 audit fixes: X-1 settled legs labelled worthless/intrinsic (the
  15:38 sale does fill ITM legs); X-2 still-index counts and RV to 15:15; X-3
  rule-version split in tallies and paired lines; X-4 strangle leg lines name
  the open partner; X-5 failed-break index and line printed.
- [x] Replay of Production Oct 6/8/13/15/19 through Dev: only B (= old BP), BL
  (= old B) and the new CI rows change; main book in-sample +₹8,755.33 (v2
  +₹5,756.59), still 4 losing expiries of 5. In-sample, not evidence of
  profit.
- [x] Tests: `tests/test_expiry_paper.py` 63 pass; full engine suite
  5,253 pass, 4 skip, 1 fail (8 min 40 s). The failure, `test_mark_to_market.py::TestEquityMark::test_zero_shares_position_is_flat`, is a clock race in that test (its quote is stamped after `now`, so the age is negative and reads STALE); it does not touch the expiry module, passes alone, and a different test of the same file failed the same way in an earlier run.
- [ ] Deployed: no (merge, rebuild the engine before the SENSEX expiry on
  Thursday Oct 22, outside the 12:59–15:40 window).

## October 19 — Oct 19 audit fixes (commit `d12bb1d`, Dev, pushed, deployed by PR #111)

- [x] O19-E1 EDGE morning scan scores the last completed session (`before_date`).
- [x] O19-P1 partner update gap per card (45 s), reminder outside the daily cap.
- [x] O19-P2 unsendable QUEUED cards → `EXPIRED_UNSENT`.
- [x] O19-S1/S2 Smart held names quoted in the scan batch; halt reasons named;
  hashed Smart policy files untouched.
- [x] O19-O1 overnight pick ≤ free cash / open slots (replay mirrors it).
- [x] O19-F1 `FNO_LOCK_LATE_ARM` / `FNO_LOCK_LOOSE_KEEP` / `FNO_LOCK_OFF` replay arms.
- [x] O19-M2 `MOM_RS_PULLBACK` shadow + replay variant + `momentum-pullback` job.
- [x] O19-B1 bootstrap order; O19-M1 hourly silent-scan heartbeat.
- [x] Tests: full suite 5,527 passed, 4 skipped (9 min 23 s); new tests/test_oct19_audit_fixes.py 15 (collected; recorded as 17 until Oct 21)
- [x] Deployed by PR #111 (merge `2fc12ee`, Oct 20 22:56 IST; engine image built 22:59 IST; the
  running container has the `before_date` scan fix, checked Oct 21). Was: no.

## October 18 — simulation-report fixes (commit `a0a3fd8`, Dev, pushed, merged by PR #111)

- [x] O18-F1 F&O replay dated expiry calendar; `CURRENT` arm; exporter
  `option_expiries`.
- [x] O18-P1 classic Penny PENNY_PAPER exits fill like the runtime paper
  executor (lifecycle v5; `REFERENCE` for old receipts).
- [x] O18-E1 `EDGE_OVERNIGHT_RUNTIME` replay arm; runtime realism refusal
  split without behaviour change.
- [x] O18-R1..R3 runner: EDGE/Swing/Range lifecycle jobs, bounded daily tail,
  entry-dated windows, `penny-smart`, current Momentum contract + index.
- [x] No strategy threshold, runtime config or schema changed.
- [x] Tests: full suite `pytest tests ../scripts/tests` 5,512 passed, 4 skipped, 0 failed (9 min 10 s); new tests/test_oct18_sim_fidelity.py 8, runner tests 20.
- [ ] Deployed: not needed for the engine (research tooling); merge to keep
  Production's `scripts/` in step.

## October 15 — expiry-v2 (C takes CX's failed-break exit) and expiry-shadow-v4 (commit `5458d2d`, Dev, pushed, deployed by PR #110)

- [x] C (main) sells its ticket on A's failed break. CX's rule was never worse
  than C on any of the 4 expiries (Oct 15 forward +₹2,018.54).
- [x] CH (shadow) = v1's held C on the same entry; CX retired, its history
  still prints.
- [x] A, B, budgets, execution, context and the owner's 10-expiry rule are
  unchanged. AL, BP and BR are not promoted (AL worse; BP/BR no forward
  entry).
- [x] Summary: per-window fresh-index counts (B 0 of 9 on Oct 15); paired
  lines matched per entry; context "window" labels; each day's own rules in
  the header.
- [x] Replay of Production Oct 6/8/13/15 through Dev: only C's rows change,
  exactly to CX's results; main book in-sample +₹7,836.98 (v1 +₹4,648.34),
  still 3 losing expiries of 4. In-sample, not evidence of profit.
- [x] Tests: `tests/test_expiry_paper.py` 60 pass; full engine suite
  5,228 pass, 4 skip, 0 fail (8 min 7 s, on the shared working tree with a6d820d).
- [ ] Deployed: no (merge, rebuild the engine before the next expiry).

## October 15 (evening) — Oct 15 audit fixes (commit `a6d820d`, Dev, pushed, deployed by PR #110)

- [x] O15-N1 no-answer provider calls counted by kind; outages paged at
  start and end through the acknowledged outbox (≥ 120 s market overlap,
  ≥ 5 failures).
- [x] O15-H1 historical sends gated at send time (3 per 1.05 s).
- [x] O15-M1 partner sends that never connected retry within their
  validity; ambiguous failures stay manual.
- [x] O15-R1 a restart with a held/unknown book pages from 60 s; EDGE token
  wait bounded in elapsed time.
- [x] O15-B2 stop samples carry their time (stale ⇒ "no price seen near the
  stop"); wrap paths end at the 15:15 exit.
- [x] O15-D1 deployed status recorded for PR #107/#108/#109 entries below.
- [x] O15-D2 late overnight notices dated in the sent text.
- [x] Tests: new `tests/test_oct15_audit_fixes.py` 28 pass; full engine suite 5,168 pass, 4 skip, 0 fail (5 min 22 s), `tests/test_expiry_paper.py` excluded because the expiry agent's uncommitted work is in the shared tree.
- [ ] Deployed: no (merge, rebuild the engine).

## October 15 — expiry-shadow-v3 and expiry-audit diagnostics (commit `db6e028`, Dev, pushed, deployed by PR #109)

- [x] CX: C plus a sale on A's failed break; same entry as C, one ticket a
  day.
- [x] BR: B plus a 50% per-leg premium stop; same strangle as B.
- [x] Summary: mark denominators with unmarked-leg reasons, context field
  availability, the paired shadow − primary line, and per-play rupees in the
  owner tally.
- [x] Primary `expiry-v1`, `expiry-exec-v2`, Telegram trade lines and the
  owner rule are unchanged.
- [x] Replay of Production Oct 6/8/13 packets through Dev: 0 row mismatches;
  diagnostics equal the audit's independent counts. In-sample only, not
  evidence of profit.
- [x] Tests: `tests/test_expiry_paper.py` 57 pass; full engine suite
  5,197 pass, 4 skip, 0 fail (8 min 22 s, on the shared working tree).
- [x] Deployed by PR #109 (merge `4e5836e`, Oct 15 07:39 IST; recorded Oct 15 from the Production audit). Was: no (merge, rebuild the engine). Scoring starts at the first
  expiry after deploy.

## October 15 — second review R1/R2 (commit `934aa2c`, Dev, pushed, deployed by PR #109)

- [x] R1: EDGE cutoff checked before every candidate admission; an accepted
  fill is kept.
- [x] R2: outbox changes are row-scoped; a page queued mid-send survives
  and is delivered.
- [x] Tests: full engine suite 5,188 pass, 4 skip, 2 fail, 1 known flake deselected (7 min 56 s). Both failures are in `test_expiry_paper.py` and come from the expiry agent's uncommitted shadow-v3 work in progress (with the committed `expiry_paper.py` a v3 test fails instead). None touch R1/R2 code. `test_oct13_audit_fixes.py` 49 pass; EDGE suites pass.
- [x] Deployed by PR #109 (merge `4e5836e`, Oct 15 07:39 IST; recorded Oct 15 from the Production audit). Was: no (merge, rebuild the engine).

## October 15 — review F1–F5 of the Oct 13 fixes (commit `ec1d5a2`, Dev, pushed, deployed by PR #109)

- [x] F1 EDGE catch-up re-checks the 15:15 cutoff after the token wait; the
  scan re-checks it at the entry boundary.
- [x] F2 only a COMPLETED EDGE scan writes the atomic daily receipt; the
  cron and catch-up share one lock.
- [x] F3 the wrap carries the stop time separately from first-event
  scoring.
- [x] F4 the restart page counts every book (unknown is not zero) and is
  delivered through an acknowledged, backed-off, deduplicated outbox.
- [x] F5 the hourly Penny fill is joined by execution-attempt identity;
  otherwise "fill n/a". Checked against Production's Oct 13 UNITEDPOLY rows
  (read-only).
- [x] Tests: full engine suite 5,187 pass, 4 skip, 0 fail (7 min 45 s; known mark-to-market flake deselected); `test_oct13_audit_fixes.py` 46 pass. Expiry code untouched.
- [x] Deployed by PR #109 (merge `4e5836e`, Oct 15 07:39 IST; recorded Oct 15 from the Production audit). Was: no (merge, rebuild the engine).

## October 13 — Oct 13 audit fixes (commit `433a81a`, Dev, pushed, deployed by PR #109)

- [x] O13-B1: a stop closes the buyer idea (`CLOSED_INVALIDATED`); no later
  target, reminder or authorizer pass; the stop itself still sends;
  pre-change rows close on the next pass.
- [x] O13-B1/B4 wrap: the held premium path ends at the stop, then "after
  exit (not held)"; no event reads "no level seen (5-min samples)".
- [x] Buyer fallback is a one-option card (`BUYER_VIEW_FALLBACK_V1`), never
  the SELL-leg spread card.
- [x] O13-B2: failed pulses keep the delivered cap; 5-minute retry; 12
  failures a day at most.
- [x] O13-B3: SENSEX option fees on BFO for exit, admission reserve, fee
  reserve, buyer loss at SL, protection card and shadow. Ledger history
  unchanged.
- [x] O13-Q1: `before_send` gate on every quote attempt; admission waits for
  the last send. O13-Q2: cancelled or failed dispatcher releases queued
  callers.
- [x] O13-R1: `lifecycle_events.jsonl` with host_suspend, thread_stall,
  clean_shutdown and startup receipts; operator page on a market-hours gap
  with open positions.
- [x] Penny: Avg R from the position row ("n/a" if unknown); hourly report
  shows the fill price; paper exit provenance fields.
- [x] Liquidity filter: unlisted names drop in one line.
- [x] EDGE startup catch-up waits for the token (10 min max) and skips a day
  whose scan already completed.
- [x] Tests: full engine suite 5,174 pass, 4 skip, 0 fail (7 min 44 s; known mark-to-market flake deselected); `test_oct13_audit_fixes.py` 33 pass. Expiry code untouched.
- [x] Deployed by PR #109 (merge `4e5836e`, Oct 15 07:39 IST; recorded Oct 15 from the Production audit). Was: no (merge, rebuild the engine).
- [ ] After deploy: no `TARGET_ZONE` or reminder after an `INVALIDATION` for
  the same idea; quote `over_documented_limit` 0; one
  `lifecycle_startup_receipt` line at boot.

## October 12 (night) — O12-PB2 card numbers verified (commit `feed23e`, Dev, pushed, deployed by PR #108)

- [x] Index conversion vs real SENSEX index (Oct 8): median +0.4, mean |16| points.
- [x] Premium model on 41,950 pairs; 60-minute decay; target range 0.85–1.0.
- [x] Loss at SL from the buy limit plus spread and charges; exact stop price; near-stop flag.
- [x] Five real Oct 6–9 cards replayed: levels correct; the premium stop protected every loss.
- [x] Tests: full engine suite 5,141 pass, 4 skip, 0 fail (7 min 24 s); partner, hedge and identity suites 231 pass.
- [x] Deployed by PR #108 (merge `4fd45f3`, Oct 12 21:45 IST; recorded Oct 15 from the Production audit). Was: no (merge, rebuild the engine).

## October 12 (evening) — O12-PB partner messages for an option buyer (commit `304ad70`, Dev, pushed, deployed by PR #108)

- [x] Buyer card (about 300 characters vs 1,670): one option, buy-up-to limit,
  skip time, stop and target on the index plus option premium, risk per lot,
  exit time. Dispatch label and identity unchanged.
- [x] One-line updates (exit / book + SL to cost / square off); a malformed
  view falls back to the old wording.
- [x] Brief and wrap for NIFTY/SENSEX in two lines each; the wrap shows each
  card's option premium path.
- [x] OI flow pulse: one message per index per new fact, 30-minute gap,
  6 a day; crisis-only regime notice; own-book caution notice off.
- [x] Tests: full engine suite 5,139 pass, 4 skip, 0 fail (7 min 22 s).
  `test_partner_buyer.py` 14; orchestrator buyer tests 5; partner, hedge,
  qualification, policy identity, scheduler and goldens: 681 pass.
  Agent and gateway untouched.
- [x] Checked against Production (read-only): Oct 6–12 card and update
  lengths; Oct 9 22550 CE premium path (₹97 at the card, ₹125 at the target
  time, ₹141 peak).
- [ ] After deploy, first session: read the `partner_msg` log lines; check
  the card's `≈` index levels against the real index; count pulses.
- [x] Deployed by PR #108 (merge `4fd45f3`, Oct 12 21:45 IST; recorded Oct 15 from the Production audit). Was: no (merge, rebuild the engine). Rollback
  `PARTNER_BUYER_MESSAGES=false`.

## October 12 — Oct 12 audit fixes (commit `d4a75fc`, Dev, pushed, deployed by PR #108)

- [x] O12-F1 flat fast exit off the lock and out of telemetry; regular tick waits for a fast pass.
- [x] O12-R1 anchored chain (1 request), DR/fired-signal reads in the management lane, per-stage read timing.
- [x] O12-Q1/Q2 shared → quote bucket → send; post-wait batch lane; bounded fairness; cancel-safe; keyed 500 chunks.
- [x] O12-C1/C2 truncated dump retried; usable-only no-op; stale symbols dropped; snapshot clocks validated.
- [x] O12-T1/T2/T3 tilt identity pairing, frozen manifest, open/unavailable, drawdown, hourly offload.
- [x] O12-S1 Smart exit-date total on `/health`; rec 10 overnight ladder receipt; O12-D1 wording.
- [x] Engine suite (all files): 5,118 pass, 4 skip, 2 fail. Both pass when
  re-run:
  - `test_kite_client_methods::test_methods_go_through_rate_limiter`, an
    `inspect.getsource` test: `kite_client.py` was edited during the run.
    Files a–k re-run in order: 2,399 pass.
  - `test_mark_to_market::TestFnoMark::test_actual_fno_writer_qty_is_not_multiplied_twice`,
    the known order/date-dependent mark test; it passes alone.

  `test_oct12_audit_fixes.py`: 25 pass. Quote/lanes/Oct 9 files: 53 pass.
  F&O, chain users, scheduler and goldens: 293 + 88 pass. Agent and gateway
  untouched.
- [x] Tilt checked on a read-only copy of Production F&O rows: same 22
  pairs and nets; drawdown added.
- [x] Deployed by PR #108 (merge `4fd45f3`, Oct 12 21:45 IST; recorded Oct 15 from the Production audit). Was: no (merge, rebuild the engine).

## October 9 (night) — F&O shadow FNO_SPREAD_TILT_V1 (commit `2d658b8`, Dev, pushed, deployed by PR #107)

- [x] Shadow module, hourly report line, `/ops/fno-spread-tilt`; 4 tests.
- [x] Checked read-only on Production data (reconciles to the F&O ledger).
- [x] F&O/routes/ops/surface tests: 607 pass.
- [x] Deployed by PR #107 (merge `df55f80`, Oct 11 23:47 IST; recorded Oct 15 from the Production audit). Was: no.

## October 9 (evening) — open items closed (commit `68e965a`, Dev, pushed, deployed by PR #107)

- [x] F&O fast exit ON by default (10 s management only).
- [x] Gateway notify 64 KB body; best-effort alerts split into parts.
- [x] Ledger/position gaps explained (receipt doc); no ledger rows changed.
- [x] Smart prior-day positions exit at the first executable bid (existing book rule + symbol quotes).
- [x] Engine suite (all files): 5,090 pass, 4 skip, 1 fail —
  `test_mark_to_market::TestFnoDrMark::test_all_legs_fresh` in the full run
  only; it passes 3/3 alone with these changes (known order/date-dependent,
  see the Oct 4 slice). Gateway jest: 484 pass, 18 fail in `db.test.js` /
  `backlog-reconciliation.test.js` (the same pre-existing Windows baseline);
  the new split/limit/notify tests pass.
- [x] Deployed by PR #107 (merge `df55f80`, Oct 11 23:47 IST; recorded Oct 15 from the Production audit). Was: no (merge, rebuild engine + gateway).

## October 9 — Production audit fixes (commit `959392a`, Dev, pushed, deployed by PR #107)

- [x] O9-R1 symbol cache snapshot + 2-min recovery job + `/health` + watchdog.
- [x] O9-S1 Smart held exits quoted by symbol; `smart_penny` on `/health`.
- [x] O9-M1 Momentum skips on unusable cache; heartbeat bounded; non-2xx logged.
- [x] O9-O1 overnight symbol fallback; DATA_UNAVAILABLE receipt after the last retry.
- [x] O9-Q1/Q2/Q3 dispatch gate, instrument-path status counting, 500-key chunks.
- [x] O9-E1 expiry outbox on `notice_outbox`; UTF-16 part lengths.
- [x] Engine suite (expiry file run separately): 5,039 pass, 4 skip, 1 fail —
  `test_s5_provider_lanes::test_without_bulk_waiters_ordering_is_unchanged_from_s2`,
  a 200/s timing test on the unchanged `RateLimiter`; it passed 6/6 re-runs
  alone (load flake). `test_expiry_paper.py`: 51 pass. `test_oct9_audit_fixes.py`: 14 pass.
- [x] Oct 8 expiry replay (925 packets) re-run on this code: identical trades,
  summary parts 3,472 + 826.
- [x] Deployed by PR #107 (merge `df55f80`, Oct 11 23:47 IST; recorded Oct 15 from the Production audit). Was: no (owner merges `codex/production-correction-hedge-p0` and rebuilds the engine).

## October 8 (late night, 2) — follow-up review F1–F3 (commit `1f4321b`, Dev, pushed, not deployed)

- [x] F1 overnight decision clock, cutoff recheck, actual entry time, snapshot TTL.
- [x] F2 gateway 422 for rejected content; `notice_outbox` classification; overnight outbox.
- [x] F3 quote budget enforced with merged batches; counters complete; 429 counted.
- [ ] Expiry outbox adopts `notice_outbox` (expiry agent).
- [x] Engine suite: 5,075 pass, 4 skip, 0 fail. Agent: 390 pass. Gateway jest:
  478 pass, 18 fail in `db.test.js` / `backlog-reconciliation.test.js`, the
  same 18 failing on the unchanged baseline (pre-existing on this Windows host);
  the notify tests (10) pass. Expiry test durations are unchanged by the budget.

## October 8 (late night) — independent review R2–R6 (commit `fc58da3`, Dev, pushed, not deployed)

- [x] R2 research arms explicit; re-run reproduces −₹5,267 / +₹6,968.
- [x] R3 overnight `visible-asks-v2` (re-quote, 30-min last trade, re-walk).
- [x] Overnight outbox parts and step-over (expiry R1 flaw).
- [x] R4 cohort unavailable attribution.
- [x] R5 agent guard release.
- [x] R6 endpoint budget measurement and `/ops/provider-budget`.
- [x] Full engine suite: 5,064 pass, 1 fail (`test_surface_matches_golden`,
  the intended new `/ops/provider-budget` route); golden regenerated with
  `TS_UPDATE_GOLDEN=1`, that file then 4 pass. Agent suite: 390 pass.

## October 8 (night) — review R1: expiry notices split; refused row stepped over

- [x] `notice_parts` (3,500-character parts, at line ends, nothing dropped)
  and per-part outbox rows.
- [x] `flush_notices` steps over a row refused 3 times; it stays pending, and
  two failures in a row stop the flush.
- [x] `test_expiry_paper.py`: 49 pass (3 new).
- [x] Oct 8 replay (read-only copy of the Production store): summary in 2
  parts, 3,472 + 826 characters.
- [ ] Owner: merge and rebuild before October 13. On that day, confirm the
  summary parts arrived on Telegram.

## October 8 (night) — Oct 8 production audit fixes (commit `7f028ed`, Dev, pushed, not deployed)

- [x] O8-F1 peak persistence without futures (`update_best_premium`).
- [x] O8-F2 bought-put sign; `FNO_TIME_STOP_RESPECTS_PREMIUM=False` from replay.
- [x] O8-O1 overnight `visible-asks-v1` entry fill contract.
- [x] O8-P1 scorecard "observed" wording, 30-date window.
- [x] T6 Momentum cohort report outside the frozen fingerprint; freeze verifies.
- [x] O8-A1 agent status publish timeout/overlap/streak.
- [x] Equal-open wording corrected in guide and code comment.
- [x] Full engine suite (`winvenv python -m pytest tests`): 5,054 pass, 4 skip,
  0 fail (process hangs at exit after the summary, known host issue).
  Agent suite: 389 pass.
- [x] Replays: `docs/research/fno/2026-10-08-time-stop-sign/` (18 archived sessions).
- [ ] Merge, rebuild, then verify the first F&O single-leg and overnight entry receipts.

## October 8 (evening) — owner's expiry stop rule

- [x] Rule recorded in the design doc header, the guide and the plan.
- [x] `owner_rule_lines` added to every expiry day summary.
- [x] Test `test_the_owner_stop_rule_is_tallied_in_every_summary`.
  `test_expiry_paper.py`: 46 pass.
- [x] Checked on a read-only copy of the Production store: expiry 2 of 10, lost 2 of 2.
- [ ] At expiry 10: report the verdict and the per-play drop recommendations.

## October 8 — first SENSEX expiry audit follow-up (`expiry-shadow-v2`, `expiry-context-v1.1`)

Commit `b7d3f4d` on `codex/production-correction-hedge-p0` (docs-identity
follow-up recorded below it). Status: Dev, pushed, not deployed.

- [x] T5: 966 slots; no tick at exactly 15:40 (tick and scheduler guards).
- [x] T4: OI context reads fresh quotes only and records `oi_fresh`/`oi_window`.
- [x] The summary shows each snapshot's nominal and actual read time, and a
  whole-trade path line per entry.
- [x] The expiry quote batch waits in the limiter's management lane (rate unchanged).
- [x] New frozen shadows AL and BP; A/B/C thresholds unchanged.
- [x] Tests: `test_expiry_paper.py` 45 pass (7 new).
- [x] Expiry plus scheduler/cron tests: 133 pass.
- [x] Full Python suite (`.\winvenv\Scripts\python.exe -m pytest tests`):
  5,043 pass, 4 skip, 0 fail. The process hung at exit after the summary,
  which is a known host issue.
- [x] Replay of the retained Oct 8 Production packets: a read-only `docker cp`
  of `/data/cache.db.expiry-paper.db` into the scratchpad, run through Dev.
  All A/B/C/BH/C500/D legs and the audit's path marks matched to the paise.
  AL +₹501.63 and BP +₹786.76 are in-sample only.
- [x] Atlas regenerated. No schema, config or migration change. No
  Production edit.
- [ ] Owner: merge and rebuild before the next expiry (Tuesday Oct 13, NIFTY).
- [ ] After that expiry: check that the summary shows 966 slots, OI coverage,
  AL/BP rows, and a lower max decision lag.

## October 7 (evening) — F&O profit lock + re-entry gate; audit T1–T3

- [x] `tests/test_fno_profit_lock_and_reentry.py` (9 tests):
  - lock arming, the half-gain floor, no arm-and-fire on one sample,
    precedence and the no-futures path;
  - the re-entry level and margin, the Oct 7 case blocked and the other
    direction allowed;
  - plan refusal, the levels SQL and `best_premium` persistence.
- [x] `test_edge_overnight_paper.py`: 19 pass, adding:
  - the PRAENG-like same-session retry;
  - LTP retry after the grace and the stop at 15:20;
  - a missed whole session gets no split;
  - `prior_session` skips holidays.
- [x] `test_expiry_paper.py`: 38 pass, including the ±20% D stress, which
  records a breach and is not capped.
- [x] F&O replay grid saved in `docs/research/fno/2026-10-07-exit-and-reentry/`.
- [x] `test_momentum_shadow_integration.py`: 9 pass. The selective entry
  keeps a strong stock in a rising market. It refuses on a falling market,
  low relative strength or a missing index, and the same scan with the gate
  off accepts.
- [x] The 4 long-standing suite failures are fixed (76 pass):
  - `mark_to_market` DR: the code could not read the contract-bound leg
    format that `fno_dr_book` has stored since `9e26e1b` (every real spread
    was UNSUPPORTED), and it subtracted `net_premium_rs` on top of
    per-leg (mark − entry) P&L. Both are fixed. No runtime caller passes DR
    rows (`main.py` uses `fno_dr_rows=[]`), so no live value was wrong.
  - `proactive_demo`: the fixed Sep 1–7 2026 dates aged out of the 30-day
    report window on Oct 1, which broke the 3 demo tests. The demo now
    anchors to a recent week and takes its five sessions from the same NSE
    calendar rule the diagnostic uses (Oct 2 is a holiday).
- [x] Full suite before the overnight guards: 5,030 passed, 4 skipped,
  0 failed (395 s).
- [x] Overnight realistic-entry guards: `test_edge_overnight_paper.py` has 21
  passing tests. They cover every refusal reason, and that a refused pick is
  replaced by the next ranked one (the scan is ranked 10 deep).
- [x] Partner re-entry gate: `test_partner_manual_advisory.py` covers the
  Oct 7 case. 439 tests matching partner, hedge or advisory pass.
- [x] Partner context: 460 partner/hedge/advisory/brief/EOD tests pass,
  including the dormant-hedge decoupling and the EOD card scorecard.
- [ ] Oct 8: the partner receives the 09:50 brief and the 15:40 EOD with
  the card scorecard, and intraday analytics stay silent.
- [ ] Oct 8+: a `reentry_not_confirmed` partner attempt appears only after a
  same-day invalidation in that direction.
- [ ] Oct 8+: the overnight ENTRY `skipped` list shows the realism reasons.
  After 30+ trades, compare the live entry cost with the 25 bps assumption.
  If real slippage is 0.5% or more, the edge is gone; stop the book.
- [ ] Oct 8+: the Momentum funnel shows `selective_*` refusals, and paper
  entries only on up-market days. After 30+ overnight exits, count
  `open_is_prev_close` and compare net with and without those exits.
- [ ] After the rebuild:
  - check the first `profit_lock` or `reentry_not_confirmed` rows in
    `fno_positions` and `fno_signals`;
  - check that any overnight `EXIT_RETRY_*` notice arrives with its reason;
  - on Oct 8 SENSEX, check that the summary has no `RESERVE BREACH` unless
    the move exceeded 5%.
- [ ] After 20 forward F&O single-leg trades, compare against the replay
  baseline. If the lock or the gate costs money forward, set the flags off;
  no code change is needed.

## October 7 — expiry chain context (`expiry-context-v1`, record-only)

Commit: see `git log`, on `codex/production-correction-hedge-p0`.

- [x] Every expiry tick records the ATM straddle and the IV it implies,
  realized volatility so far, OI walls, max pain, PCR, OI change per side,
  and the future's build-up. Every leg records its OI.
- [x] Snapshots are taken in each A/C signal, at 14:30 and at 15:13:30. The
  summary shows them and how the close met them.
- [x] No rule reads the context. A whole day gives identical positions with
  and without OI.
- [x] `test_expiry_paper.py`: 36 pass (4 new, including a context failure that
  still records the tick). Cost and EDGE overnight
  tests pass. Full suite: 5,006 pass, 4 skip, 4 fail (dev_acceptance_harness,
  integrated_dev_demo, mark_to_market DR, proactive_intelligence; all in the
  earlier no-change failure list).
- [x] Pushed; not deployed.
- [ ] Owner rebuilds the engine before October 8 (the first observation).
- [ ] After the expiries, the owner decides which context becomes a frozen
  gate or label.

## October 6 (night) — overnight entry/overnight attribution

- [x] `test_edge_overnight_paper.py`: 15 pass, including the split and the
  delayed exit (which records no split).
- [ ] After rebuild: the first 09:17 message shows the two parts for each
  trade.
- [ ] After 10+ sessions: sum `entry_vs_close_rs` and `overnight_rs`
  separately. Only then consider an entry-clock study, frozen first.

## October 6 (night) — Penny durable brake (C3) and allocation freeze

- [x] `tests/test_penny_daily_brake.py` (3 tests):
  - today's paper partial and close legs trip the brake, and other days,
    books and deposits are excluded;
  - a restart rebuilds the same value;
  - an unreadable ledger blocks live and keeps paper.
- [x] Penny integration and scanner tests: 34 pass. Main-surface and add_job
  goldens: 4 pass.
- [x] Allocation manifest frozen (experiment
  `momentum-allocation-holdout-from-2026-10-07`).
- [ ] After about 10 sessions with capital skips, run `evaluate` on a
  read-only Production DB copy and record holdout per policy, net and
  drawdown, without changing the runtime.

## October 6 (night) — research writer bounded wait (R1)

- [x] `test_research_archive.py`: 19 pass. A 0.3 s holder delays an append
  instead of dropping it, and a holder past the bound is named in the
  refusal. Research, partner and scheduler isolation tests: 211 pass.
- [ ] After rebuild: count `research_storage_stop` and
  `partner_research_input_capture_failed` (Oct 6: 7 and 4). If any remain,
  the `holder=` field names the culprit.

## October 6 (night) — overnight buy charges and partner management retry

- [x] O1: `test_edge_overnight_paper.py`, 13 pass. Includes the Oct 6
  reproduction (reserved Rs 28.93, cash −Rs 7.59 rebuilt), the buy-side and DP
  split, and a cash-bound admission that fits premium plus charges.
- [x] A1: `test_partner_manual_advisory.py` covers a 50 s old target update
  sent after one refused send, an EXPIRED_UNSENT reason past 360 s, and
  acknowledged-claim reconciliation.
- [x] Partner, hedge and overnight suites: 427 pass. Repaired existing tests:
  - the qualification fixture clock expired on Oct 6 (29-day validity from
    Sept 7);
  - the delivery-blocker tests now pin the qualified-only contract
    (`SEND_UNQUALIFIED=False`).
- [ ] After rebuild: the old Oct 6 TARGET_ZONE row closes on the first scan
  as `EXPIRED_UNSENT` (`idea_retired_session_end`). It is not sent.
- [ ] After rebuild: the overnight entry message's `cash_after` is ≥ 0.

## October 6 (evening) — expiry shadow plays (`expiry-shadow-v1`)

Commit `6c2a82f` on `codex/production-correction-hedge-p0`: pushed, not deployed.

- [x] BH (B held, no bank or trail), C500 (C inside ₹500) and D (short iron
  condor, 2 → 1 → 0 steps out, held to settlement) run beside A, B and C. They
  send no Telegram trade lines and have their own summary section.
- [x] D's maximum loss is (gap − credit) × qty + entry charges + STT reserve,
  and must fit ₹2,500. If quotes are lost, D is valued at that maximum.
- [x] Dropped the A fee-filter variant: it could never trade inside ₹2,500.
- [x] `test_expiry_paper.py`: 32 pass (4 new shadow tests).
- [x] Full suite: 4,983 pass, 4 skip, 11 fail (the same 11 that fail without
  these changes; see the section below).
- [ ] Owner rebuilds the engine before October 8; the shadow plays are scored
  after 20 expiries.
- [ ] D stays paper only; selling options needs margin, the owner's decision.

## October 6 — expiry first-day audit remediation (`expiry-exec-v2`)

Commit `db5153d` on `codex/production-correction-hedge-p0`: pushed, not deployed. Production runs `70a2256`.

- [x] Decision clock after quote receipt; start and decision times and limiter
  timing on each tick.
- [x] Full five-level depth and index/future status logged; refusal counters.
- [x] `bank_pending` keeps a partial bank's remainder (survives restart).
- [x] Serialised outbox flush (expiry and EDGE overnight); `sent_at` is the
  acknowledgement time; separate `expiry_paper_flush` job.
- [x] A dark-index expiry is recorded (day, ticks, summary).
- [x] BSE options charge (`FNO_BSE_EXCHANGE_TXN_PCT=0.000325`); schedule
  frozen per position.
- [x] Sell and summary messages show fees, filled net, assumed and whole
  modeled.
- [x] Unchanged: strategy thresholds, ceilings, freshness limits, paper-only.
- [x] Tests (`.\winvenv\Scripts\python.exe -m pytest`):
  - `test_expiry_paper.py`: 28 pass (corrected on October 6 evening; an
    earlier note said 29). Eight are new: the clock probe, window crossing,
    partial bank across a restart, concurrent flush, dark-index day, BFO fee
    freeze, v1 store migration, and the mixed-contract label.
  - Focused expiry, EDGE overnight, cost, golden, scheduler and cron-gating
    tests pass.
  - Full suite: 4,978 pass, 4 skip, 12 fail.
    - 11 of the failures are in the dev-acceptance, integrated-demo,
      mark-to-market DR, partner delivery/advisory, proactive and
      qualification tests. They fail identically with these changes stashed.
    - The 12th, `test_penny_cron_gating`, was this change: the new flush job
      had no `is_trading_day` gate. The gate was added and the test passes.
- [x] Environment limit: on this host, pytest sometimes hangs at interpreter
  exit after all tests report, with and without these changes (3 of 4
  baseline runs). Run with `timeout` and read the summary line.

## October 5 (late night) — expiry book second review

Commit `263dd48` on `codex/production-correction-hedge-p0`: pushed to Dev, not deployed.

- [x] Exit-fee reserve: buy charged once, one sell-order fee per lot reserved.
- [x] `require_delivery` on `/api/internal/notify`, 502 on refusal, used by the
  paper outboxes.
- [x] Settlement labelled as our sampled index; filled and assumed totals on
  separate lines.
- [x] Python: `test_expiry_paper.py` 20 pass; focused expiry, EDGE overnight,
  cost, scheduler and golden selection 134 pass (`.\winvenv\Scripts\python.exe
  -m pytest ...`).
- [x] Gateway: new `internal-notify-ack.test.js` (3) and the `sendAlertOnce`
  case in `alert-dead-letter.test.js` pass. Full jest: 476 pass, 4 skip, 18
  fail; all 18 are in `db.test.js` and `backlog-reconciliation.test.js` and
  fail identically with these changes stashed (native SQLite on this host).
- [x] Full Python suite not rerun for this change.
- [ ] Owner merges and rebuilds both containers (Production runs `acc7181`).

## October 5 (night) — expiry-day book review fixes

- [x] Hard loss ceiling (premium plus charges); A tries ATM, else one strike
  OTM.
- [x] Fresh, depth-walked fills; latched exits; `AUCTION_WINDOW` labels.
- [x] Futures-confirmed breakout with no stale carry-over.
- [x] `reconcile` settles leftovers as assumed or unresolved (hourly job plus
  every tick).
- [x] Durable Telegram outbox.
- [x] Tests: `tests/test_expiry_paper.py` 19 pass. They cover gaps,
  bank-then-gap, one-lot banking, stale and one-unit quotes, missing bids,
  outage settlement, the outbox, and the second-trade ceiling. Goldens were
  updated.
- [x] Full suite: 4,967 pass, 4 skip, 8 fail. None of the failures is in the
  expiry book:
  - `test_partner_delivery_blockers` ×3 already fail at `653560a`;
  - `test_mark_to_market::test_all_legs_fresh` is clock-dependent and passes
    alone;
  - the rest are the known pre-existing failures.
- [ ] Owner merges and rebuilds Production (running `acc7181`).

## October 5 (night) — scheduler telemetry and Penny funnel stages

- [x] `scheduler_telemetry.py`: retried final write, failure log, parked
  replay, and the `inflight_state` split. `test_scheduler_telemetry.py` and the
  H2 tiers tests: 33 pass. The new tests fault-inject a locked database at
  completion.
- [x] `ops_metrics.py`: `stages_json`. `test_ops_metrics.py`: 28 pass,
  including a reconciliation of the Oct 5 shape (2 accept rows, 1 admitted,
  1 not admitted, 1 fill) and a column migration.
- [ ] After rebuild, check `/ops` `funnel[].stages` for the first trading day,
  and check for no `scheduler_telemetry_completion_write_failed` lines or for
  replays.

## October 5 (night) — partner advisory labels

- [x] Unqualified cards are delivered as "PURE ADVICE — NOT CHECKED", qualified
  ones as "PURE ADVICE" (`config.py`, `partner_manual_advisory.py`,
  `hedge_advisory.py`).
- [x] Partner, hedge and qualification-boundary tests: 132 pass. New tests
  cover the label, the authorizer under flag on/off, and the qualified label.
- [ ] After rebuild, confirm the partner's first labelled card (at most 2 per
  day).

## October 5 (night) — Momentum auto-execute

- [x] `node-gateway/server/config.js`: `MOMENTUM_AUTO_EXECUTE` defaults to `true`.
- [x] Production `.env`: `OWNER_LIVE_ENTRY_HALT=true` (verified by key-only grep).
- [x] Gateway `momentum-auto-execute` and `momentum-execution` tests pass.
- [ ] Owner lifts the halt when real automatic Momentum buys are wanted.

## October 5 (night) — EDGE overnight C5/C6

- [x] Notice outbox plus restart catch-up (`edge_overnight_paper.py`,
  `scheduler_setup.py`).
- [x] `test_edge_overnight_paper.py`: 9 pass (outbox retry and send-once; late
  exit at LTP; exit within grace at the open; entry only before the close).
  Scheduler goldens updated with `TS_UPDATE_GOLDEN=1` (one new job); scheduler
  and surface tests pass.

## October 5 (night) — audit remediation slice 3

- [x] C8 whole-trade analytics; Swing heads-up typed signal; heatmap log names;
  DP ₹15.34.
- [x] Tests:
  - `test_performance_analytics.py`: 9 pass, including the new partial-leg
    case.
  - `test_main_breadth_integration.py`: 3 pass; the new heads-up test fails
    without the fix.
  - `test_edge_portfolio_replay.py`: 12 pass; the DP assertion is updated to
    about 1.75%.
- [ ] Deferred: C2 BSE option exchange rate (0.0325% vs NSE 0.03553%, about
  ₹3.6 per ₹1 lakh premium; many call sites plus the entry cost snapshot); C4
  one DP per scrip per day for partial EDGE sells.

## October 5 (night) — Penny paper profit lock

- [x] `penny_profit_lock.py`, monitor wiring in `main.py`, flag
  `PENNY_PROFIT_LOCK_ENABLED=True` (paper MIS only).
- [x] Tests: `tests/test_penny_profit_lock.py` (rule, SUTLEJTEX Oct 5 path,
  monitor raise→bank, target exit, missing quote, flag off) plus
  `test_penny_exit_lifecycle.py`: 27 pass.
- [ ] Forward evidence: count `target_paper` / `profit_lock_paper` closes against
  `protective_stop_paper` over 10+ sessions. This is not qualification.
- [ ] Diagnostic replay arm after round-3 scoring (seen data, labelled).

## October 5 (night) — audit remediation slice 1

- [x] C1: post-dispatch failures keep the Momentum/EXEC lock
  (`executor.js`, `momentum-execution.js`, `index.js`, `routes/orders.js`).
- [x] Partner informational surfaces resume while advisory is unqualified;
  RV refresh datetime fix (`partner_orchestrator.py`).
- [x] Kite acquisition retries transient network failures.
- [x] Verification:
  - Gateway `npx jest`: 472 pass, 4 skip, 18 fail. The 18 failures are
    pre-existing (`db.test.js`, `backlog-reconciliation.test.js`: better-sqlite3
    has no native Windows build); the same 18 fail with these changes stashed.
  - New `tests/unit/momentum-execution.test.js` 3/3 pass; the retry test fails
    without the fix.
  - New executor post-dispatch tests pass.
  - Python partner modules: 116 pass. The new silence tests fail without the
    fix.
- [ ] Owner merges and rebuilds Production; confirm a partner morning brief on
  the next trading day.
- [ ] Penny profit protection (after round-3 scoring).

## October 5 (evening) — expiry-day paper book

- [x] Researched expiry-day dynamics and wrote the
  [design doc](2026-10-05-expiry-day-paper-book.md) covering:
  - the closing auction and the 15:40 close;
  - SEBI's pending settlement review;
  - evidence on retail losses.
- [x] `expiry_paper.py` (plays A/B/C, ₹2,500 per play per expiry, paper only)
  and a 10 s scheduler job. The research archive window was extended to 15:40.
- [x] Tests: `tests/test_expiry_paper.py`, 11 pass (pure exit and entry rules
  plus a simulated expiry afternoon). Scheduler goldens updated. Full suite
  after the fix: 4,942 pass, 4 skip, and only the 4 known pre-existing
  failures.
- [ ] Owner merges and rebuilds Production before the next expiry (NIFTY, Tue
  Oct 6).
- [ ] First expiry: confirm the ticks, the box and the Telegram summary.

## October 4 (late) — gateway uid fix and successor inheritance

- [x] Diagnosed the Production `node-gateway` crash loop (read-only): uid 100
  could not write `cache.db` (uid 1000, 644).
- [x] Both images use uid/gid 1000; entrypoints chown WAL/SHM files.
- [x] Verified locally: both images built; on a scratch volume reproducing
  Production ownership, the gateway and engine entrypoints each led to a
  successful `cache.db` write.
- [x] [Inheritance doc](2026-10-04-successor-inheritance.md) written. The
  in-chat reminder was cancelled; the Windows task remains for Oct 5, 17:07.
- [ ] Owner merges and **rebuilds** Production images; confirm all containers
  are healthy.

## October 5 — EDGE overnight study

- [x] Event study on seen Jan–Sep 2026; 1-minute fill and liquidity checks.
- [x] `EDGE_OVERNIGHT` and `CNC_FULL` costs implemented with tests (4 new; EDGE,
  daily-book and Lab suites: 42 pass).
- [x] Code `2298e77`; freeze `1e5c904` committed and pushed before scoring;
  scored once.
- [x] Verdict `NOT_SUPPORTED_STAYS_OFF` (drawdown vs starting capital);
  the results are recorded in full.
- [x] Windows task `Sentinel-Round3-KiteScoring` registered for Oct 5, 17:07.
- [x] The owner approved E1: `edge_overnight_paper.py` (₹25k) with 15:20 and
  09:17 jobs, a separate store and no order capability (5 tests; scheduler
  goldens add exactly the two jobs).
- [x] E2: runtime delivery costs corrected; the EDGE partial-settlement test now
  asserts the exact cost-inclusive P&L.
- [x] Verification: full engine suite 4,930 pass / 4 skip, with the 4 pre-existing
  failures plus the cron-gating guard. After the gating fix, the gating, golden
  and paper tests give 11 pass.

## October 5 — everything on paper, forward evidence

- [x] Slice doc [2026-10-05-forward-paper-evidence.md](2026-10-05-forward-paper-evidence.md)
  (insights from `penny-smart-t4`; no new thresholds).
- [x] `MOM_SELECTIVE` Momentum shadow variant with one NIFTY 50 fetch per scan;
  the funnel and existing variants are unchanged (tests: 4 selective cases,
  integration on/off parity plus exactly one index call).
- [x] `PENNY_SMART_SHADOW_ENABLED=True` (paper only, separate DB).
- [x] Owner's smart-Penny controller and tick corrections committed as verified.
- [x] Live switches verified OFF by default; the Production `.env` overrides none
  (read-only).
- [x] Verification: full engine suite 4,918 pass / 4 skip / 4 pre-existing failures (dev harness, integrated demo, F&O DR fixture, proactive demo); penny/momentum/ops selection with new defaults 1,348 pass.
- [x] Commit `9c5becb`, pushed to `codex/production-correction-hedge-p0`; not merged or deployed (owner merges to `main` on GitHub).
- [ ] Kite January–July acquisition, then freeze and score of the round-3
  studies (October 5, after the owner's login).

## October 4 — smart Penny paper controller and frozen ablations

- [x] Explicit [implementation slice and receipt](2026-10-04-penny-smart-trader-implementation.md)
  maintained before implementation; prior Dev edits preserved.
- [x] Reused adaptive setup state transitions; persistent strength ranking,
  one-shot quote budgets and confirmed-close management. No automatic
  breakeven/partial, widened stop, averaging down or forced trade quota.
- [x] Durable separate paper store, entry risk/cost/cash checks, daily marked-loss
  latch, cross-day equity carry, restart/concurrent dedup and independent exits.
- [x] Default OFF, no real orders/funding; reuse scanner history, bound optional
  held-symbol quote batch and CPU/time/DB impact. F&O AST and adapter isolation.
- [x] Broad regression: 1,410 pass / one skip / one unchanged F&O fixture failure;
  final policy/scanner/lifecycle 74 pass (28 new-policy), runner two pass.
  Compilation, diff check, final bound/hash verification and stable atlas passed.
- [x] [Frozen five-arm owner-budget diagnostic](research/yahoo/2026-10-04-penny-smart-t4/freeze.json)
  distinguishes ranking, entry/risk, exit and combined policies. Both windows
  are already examined; zero-trade days and losing arms retained.
- [x] T4 complete with stable bound inputs: incumbent +₹91.7169 / 38 versus
  combined −₹47.5019 / 153; every improvement check fails, stays OFF. Other new
  entry/exit arms also trail incumbent. Daily/stress results preserved.
- [ ] Prospective quote/fill evidence, explicit D1–D4 follow-up slices; untouched
  T3 data/freeze/score remains unavailable. No qualifying profitability claim.
- [ ] Actual live settlement/risk contract, broader exit evidence, point-in-time
  universe/regime/portfolio fidelity and GitHub promotion.
- [x] Dev-local/uncommitted at `a674740`, no push/merge/deployment or Production
  edit. The new DB is opt-in and separate; runtime dependencies unchanged.

## October 4 — authorized Penny corrections and researched strategy

- [x] [Correction contracts and receipt](2026-10-04-penny-corrections-and-relative-strength-slice.md):
  explicit exactly-once old/new stop comparison, effective setting/cost/source
  binding, rounded decision-risk arithmetic, current-date instrument ticks.
- [x] Unknown tick metadata refuses new live orders; existing stop/unwind/exit
  recovery remains available with the legacy fallback. Future promotion needs
  a successful normal universe refresh before any live entry.
- [x] 830 selected tests passed (one skip, existing dependency warnings); final
  price/executor/lifecycle 55 passed, source compile/diff checks and stable atlas.
- [x] Stable five-day source/data freeze and baseline parity: old 18 / +₹15.1765,
  corrected noise 15 / +₹36.4486; seen paper-book evidence only. The first drifted
  run is preserved as invalid and untouched Kite scoring remains unavailable.
- [x] [Primary research and R0–R4 development plan](2026-10-04-penny-consistent-returns-strategy.md)
  separates possible 1% days from unproved daily consistency; preserves F&O.
- [ ] Untouched T3 data/freeze/score; proposed selection and exit ablations.
- [ ] Actual-fill/cost/open-risk budget and settlement-fed daily brake before
  live activation or increased admitted risk; qualification and GitHub promotion.
- [x] Dev-local/uncommitted at base `a674740`; no push/merge/deployment, funding
  or live-flag change, broker call or Production edit. No DB/dependency migration.

## October 4 — independent Penny review and further-development discussion

- [x] [Source/evidence review and primary web research](2026-10-04-penny-efficiency-independent-review.md)
  at pushed Dev `a674740`; required docs revalidated. Production Git metadata
  only read (`044c016`); no new operational performance claim.
- [x] 45 focused tests passed; in-memory counterexamples confirm risk-rounding,
  coarse live snapping, capital shrinkage and the contaminated pending baseline.
  Historical suite totals remain historical; not every branch path was audited.
- [x] Saved proposed sequence with files/contracts, acceptance, rollout/rollback,
  owner-budget daily metrics and F&O noninterference. No 1–2% daily guarantee.
- [ ] Explicit exactly-once stop policies/effective-settings freeze, final-price
  risk arithmetic, instrument-aware execution review and untouched Kite study.
- [ ] Further stop/selection/execution experiments, qualification and any
  separately authorized GitHub promotion/paper observation/live decision.
- [x] Documentation only in this task, Dev-local/uncommitted; no source/config,
  schema/dependency change, broker call, new historical scoring, merge/deployment.

## October 4 — Penny noise-floor stop ON (owner selection) and push

- [x] `PENNY_NOISE_STOP_ENABLED=True` in runtime Penny; tests updated (794 Penny, 4873 engine pass; 4 pre-existing failures).
- [x] Pushed branch `codex/production-correction-hedge-p0` on owner instruction; promotion to Production via PR merge.
- Rollback: `PENNY_NOISE_STOP_ENABLED=false`.

## October 4 — Momentum direct trading + round-3 candidates (Dev only)

- [x] Gateway shared Momentum execution path + auto route (default OFF) + agent wiring.
- [x] Momentum `MOM_SELECTIVE` / `RUNNER_EXIT`, Penny `PEN_NOISE_STOP(_BE)`, Kite history tool,
  parallel study runner, [module testing guide](MODULE_TESTING_GUIDE.md).
- [ ] Kite data (owner login) → freeze → score `momentum-smart-t3`, `penny-noise-t3`.
- [ ] Owner: set `MOMENTUM_AUTO_EXECUTE=true` only after promotion and a passing study.
- Commit `a4f1a54`: engine 4872 passed / 4 pre-existing failures; gateway 465 passed / 18 Windows
  better-sqlite3 binding failures (pre-existing); agent 387 passed.
- Not pushed, not deployed.

## October 4 — SENSEX/NIFTY future-candle recording (Dev only)

- [x] `research_future_candles` job (15:40 IST) + exporter includes SENSEX futures.
- [x] Census/surface goldens regenerated (one job added); new tests 3.
- [ ] Promote via GitHub so Production records from the next session.
- Not pushed, not deployed.

## October 4 — F&O growth slice (Dev only)

- [x] Adaptive risk multiplier + two-strike day halt (live tick, capped-loss book, replay).
- [x] Brakes 3/6/10/15%; cap ₹40,000; lots 2 (3 only when proven).
- [x] Capped-loss book multi-lot within ₹10k × multiplier and 40% pool capital; cost fix.
- [x] SENSEX paper single-leg: NIFTY RVOL proxy, correlation guard, per-underlying
  management, exchange routing, traded-book refresh.
- [x] Vehicle-by-IV implemented, OFF.
- [x] Owner window test Sep 17–Oct 1: drawdown-cut silent-halt bug fixed (one-lot floor);
  live test minimum revised ₹1.5L → ₹2L. Flaky under load: `test_s5_provider_lanes` (passes alone 3/3).
- [ ] SENSEX replay export; BFO live exit evidence/recovery; forward scoring.
- [ ] Owner: review and approve promotion via GitHub.
- Commit `e8d93c3`: full suite 4854 passed, 4 skipped, 4 failed (pre-existing, listed in the slice).
- Not pushed, not deployed; Production only read.

## October 4 — F&O replay, candidates and speed (Dev only)

- [x] Read-only export of the Production research archive (14 sessions, 166 MB, local only).
- [x] `fno_entry_plan` / `entry_halts` extracted (behaviour-neutral: 520 → 534 F&O tests pass).
- [x] Full-policy replay; parity 8 of 9 live paper trades.
- [x] `fno-trader-v1` frozen (`d973f05`) then scored: shipped baseline best; candidates OFF.
- [x] Fast exit loop + bar-close trigger implemented, serialised by one lock, default OFF.
- [ ] Owner: decide whether to paper-enable `FNO_FAST_EXIT_ENABLED` after promotion.
- [ ] Production must be running for the archive to grow; re-export weekly.
- Not pushed, not deployed; Production data volume only read.

## October 4 — T2 Range/Swing/Momentum + CNC audit (Dev only)

- [x] Shared own-cash daily book; EDGE refactor reproduces frozen equity/trades.
- [x] Range, Swing portfolio replays; Momentum next-bar entry + thesis exit.
- [x] Generic pre-registration tool; T2 freezes committed (`68e0754`) before scoring.
- [x] [T2 results](2026-10-04-t2-range-swing-momentum-slice.md): all candidates
  NOT_SUPPORTED_STAYS_OFF; CNC conjunction fired 0 times Jan–Sep 2026.
- [x] Removed superseded gates and the EDGE independent-trial proxy.
- [x] [Testing method guide](RESEARCH_TESTING_METHOD.md) and
  [improvement options + F&O review](2026-10-04-improvement-options-and-fno-review.md).
- [ ] Owner: choose next rounds (Swing round 2, EDGE/Range geometry, F&O archive/replay/tick exits).
- Not pushed, not deployed; no Production edit, settings, schema or F&O change.

## October 4 — T1 Penny/EDGE trader candidates (Dev only)

- [x] Review corrections committed separately (`00fd560`).
- [x] Penny trader policy + replay candidates, pre-registered freeze (`22a7ce6`).
- [x] EDGE own-cash portfolio replay + `EDGE_TRADER_V1`, freeze (`684de3d`).
- [x] Untouched windows scored once; [results](2026-10-04-t1-penny-edge-trader-slice.md):
  Penny V2 and EDGE V1 **NOT_SUPPORTED_STAYS_OFF**; shipped Penny baseline
  +₹63.17 untouched; shipped EDGE −40.17% marked (Jan–Jun, own cash).
- [ ] Owner: decide whether to pause EDGE paper; keep EDGE live disabled.
- [ ] EDGE round-2 geometry hypothesis on 2024–2025 untouched data.
- [ ] Weekly Penny minute archive (Yahoo ~30-day retention).
- [ ] T2 Range/Swing/Momentum adapters; R5/T3 F&O noninterference.
- Not pushed, not deployed; no Production access, broker action, settings,
  schema, dependency or F&O change.

## October 4 — revised adaptive trader plan (latest direction)

- [x] [Adaptive non-F&O trader plan](2026-10-04-adaptive-non-fno-trader-development-plan.md)
  supersedes prior design/order while preserving R1–R5 fidelity requirements.
  Current subset-only helpers, mixed activity/economic evidence and source
  limitations reviewed; primary research and transfer limits recorded.
- [x] Complete module candidates, persistent setup/execution states, alternative
  timing, thesis exits, rejected-opportunity evidence and matched-risk tests
  specified with files/contracts, acceptance, rollout/rollback and remaining work.
- [x] F&O excluded and protected through cash, shared resources and exit authority;
  no strategy/funding/risk/approval change authorized by this plan-only revision.
- [x] Required docs reviewed; documentation link/scope and diff checks recorded;
  source diff preserved from prior review. No fresh test/backtest or profit claim.
- [x] Dev-local/uncommitted at HEAD `434c4cc`, prior corrections/results preserved;
  no Production access, broker action, runtime/configuration/dependency/schema
  change, implementation commit, push or deployment in this task.
- [ ] T0–T3 implementation, data, economics, untouched qualification and F&O
  operational compatibility; any separately authorized GitHub promotion/canary.

## October 4 — independent review and identical Yahoo comparison

- [x] Required docs/source/new commits reviewed at Dev `434c4cc`; explicit
  [correction and R1–R5 plan](2026-10-04-non-fno-independent-review-and-repeat-plan.md)
  recorded before edits. Original plan is partial; source-only research is not
  an active-policy improvement or operational F&O compatibility proof.
- [x] Initial repeat reproduces all 16 old states/windows/metrics exactly.
- [x] Minor Penny retest/profile and Momentum ATR/regime/exit-evidence corrections;
  EDGE independent trials downgraded to PROXY with unvalidated clock/cash limits.
- [x] 130 focused tests passed (existing HTTPX warning), compilation/diff and
  atlas regeneration (241 modules) passed; shipped/F&O/shared runtime untouched.
- [x] Final same-data repeat matches all 16 previous outcomes; three candidate/
  measurement studies and raw/report/source integrity receipts retained. See
  [results](2026-10-04-non-fno-review-and-backtest-results.md): no demonstrated
  improvement; losing/unavailable diagnostics remain visible.
- [ ] R1–R5, sufficient native coverage, qualification and any separate rollout.
- [x] Dev-local uncommitted corrections/docs/results; no Production access,
  broker action, funding/configuration/dependency/schema change, push/deployment.

## October 3 — researched non-F&O development plan

- [x] [Smart-entry/exit plan](2026-10-03-non-fno-smart-entry-exit-development-plan.md)
  records module priority, shipped contracts, primary web sources and transfer
  limits, acceptance, rollout/rollback and remaining work.
- [x] F&O excluded; no interference through capital, shared code/configuration,
  scheduler, DB, quote/broker capacity or exit authority is a release contract.
- [x] Required docs/AGENTS and relevant source reviewed at Dev `4be033a`;
  Yahoo counts distinguish verdicts/selections/fills and five-session sensitivity.
- [x] Documentation-only link/scope/diff verification recorded on delivery;
  no new strategy tests/profit claims, source/configuration/schema changes,
  Production access, broker actions, push or deployment. Updates are uncommitted.
- [x] N1–N3 source slice: named Momentum partial/runner exit lifecycle, EDGE
  next-open lifecycle, default-off Penny context candidate and pure Range/Swing
  candidate gates. See [implementation receipt](2026-10-04-n1-n3-implementation-slice.md).
- [x] F&O isolation held: no F&O source/configuration, shared reservation,
  scheduler, database schema, broker action, Production edit, push or deploy.
- [x] Source commit `65e050a`; 109 focused tests passed (one existing HTTPX
  deprecation), affected modules compiled, diff check passed and atlas was
  regenerated to 241 modules. Dev only.
- [ ] N0 operational F&O compatibility baseline; candidate data coverage,
  matched-cash evidence and all-failure trial ledger; N4 untouched
  qualification and separately authorized observation/GitHub rollout.

## October 3 Yahoo non-F&O interface — latest research receipt

- [x] One script with inclusive dates, current shipped Lab paths and all-module
  reports; no Sentinel candle/trade history or F&O/broker/Production access.
- [x] Yahoo native intervals, 900-day daily warm-up, raw/import/validated hashes,
  no fabricated volume/candles, whole-invalid-day exclusion and visible partial
  universes. Explicit current Penny symbol fallback, no live universe change.
- [x] Requested Q3 primaries preserved; recent intraday/sensitivity studies
  labelled separately. EDGE/Swing/Range evaluator scope remains explicit.
- [x] Current Penny activity demonstrated: 18 recent sensitivity closes;
  Momentum two virtual same-day time exits. No qualification/system return.
- [x] 70 focused tests passed; no overwrite, offline tampering, clock/identity,
  session/interval, isolation and drift contracts checked. Final repeated
  results, compilation/diff and deterministic atlas recorded in the receipt.
- [x] [Usage guide](YAHOO_BACKTEST_GUIDE.md), [plan](2026-10-03-yahoo-all-module-backtest-plan.md)
  and [results](2026-10-03-yahoo-backtest-results.md) are consistent. Source commit
  `df0c379`; all 16 repeat outcomes and 1,203 raw hashes agree. Immediate
  documentation/atlas/clean-worktree verification passed.
- [ ] Complete entry/exit/portfolio fidelity and prospective qualification;
  downloading Yahoo daily data does not close these gaps.
- [ ] Owner-controlled promotion. Dev only, no new dependency, runtime schema/
  configuration change, Production edit, broker orders, push or deployment.

## October 3 current-system test receipt — latest Dev research status

- [x] Frozen dates/current universes before scoring; baseline `556209c`.
- [x] Stopped Production `044c016` stable DB/WAL/universe copied into Dev;
  one read-only collection, raw BLOB preservation, immutable data hashes.
- [x] All 19 module jobs finished; 11 delivered runs match current source;
  7 original/final outcomes agree. Failed and unavailable attempts retained.
- [x] Penny MIS/CNC/joint lifecycle, EDGE/Range evaluator and covered-window
  Momentum diagnostic; full-quarter Momentum and Swing unavailability recorded.
- [x] F&O full-policy/exit evidence rejects preserved; exactly linked recorded
  cash explicitly distinguished from a new current-policy backtest.
- [x] EDGE handle-only cleanup; 28 focused tests passed (existing HTTPX warning).
  Source/data/report hashes, raw-to-compact counts, UTC-normalized actual cash
  checks, compile/diff and regenerated atlas verified.
- [x] [Comprehensive results](2026-10-03-current-system-backtest-results.md),
  [plan](2026-10-03-current-system-backtest-plan.md), machine summary and integrity
  receipt retained. Source commit `4929bea`; immediate documentation consistency,
  deterministic atlas and clean-worktree checks passed; see completion receipt.
- [ ] Owner discussion of improvements; no strategy tuning undertaken.
- [ ] Complete historical context/coverage, Momentum real EOD/partial lifecycle,
  Penny mixed-offset clock normalization, other-book lifecycle/portfolio fidelity,
  exact executable F&O input/exit evidence and prospective qualification.
- [ ] Runtime acceptance and owner-controlled GitHub promotion. This task is
  Dev-local, no schema/configuration impact, push, orders or deployment;
  Production engine remains stopped and was not restarted/edited.

## October 3 P1–P4 receipt (Dev only)

- [x] Recursive local dependency hashes and exclusive snapshot/report publication.
- [x] CLI/Lab regression: 26 passed; one existing httpx deprecation warning.
- [x] Owner account/division ceilings approved: Swing ₹1,000, Penny ₹2,000,
  Momentum ₹3,000, EDGE ₹3,000; transfers allowed.
- [x] P1 shared account-cash reservation: full entry value + calculated entry
  charges + 1% fill buffer, durable across Python/gateway and never applied to exits.
- [x] P3 shared-cash Penny joint lifecycle adapter, correctly labelled
  `PORTFOLIO_PARTIAL`; unresolved exposure remains locked.
- [x] P4 append-only future holdout registry; policy/data/config drift and
  retroactive/reused-as-untouched qualification are rejected.
- [ ] Paper observation of the P1 ledger and FULL_PORTFOLIO evidence for any
  actual qualification remain required before owner-controlled promotion.
- [x] Source commit `919e042` is Dev-only; Python 90-test focused regression,
  gateway 59-test executor regression, compile/diff checks and 240-module atlas
  regeneration passed. The gateway's local native SQLite test ABI mismatch is
  documented; container-native protocol validation remains a release gate.

## October 3 independent post-implementation review — current status

- [x] Audited Dev `4481af0` against the original plan and actual contracts;
  baseline checks: 422 Python and 58 gateway tests passed.
- [x] Recorded small-correction scope and larger follow-ups before editing:
  [independent review](2026-10-03-post-implementation-independent-review.md).
- [x] Corrected known-order reconciliation, unresolved single-leg occupancy,
  malformed order evidence, partial report aggregates/winner exclusion and
  unsupported untouched-holdout certification in Dev.
- [x] Final affected regression: 294 passed, two existing deprecations; atlas,
  compile, review links and diff consistency passed.
- [x] Source commit `284bb4a`; immediate guide/plan/checklist/review consistency,
  atlas reproducibility and clean worktree verified. Receipt is Dev-local only.
- [ ] F1-B common account cash reservation, charges/book budgets and catastrophe acceptance.
- [ ] B0/B1 complete dependency/data/context manifests and point-in-time evidence.
- [ ] B2/B3/B4 full historical lifecycle/portfolio scope; CNC real-data run.
- [ ] B6 prospective freeze/reuse audit, marked equity and session uncertainty.
- [ ] Dev release operational acceptance and GitHub promotion. Production
  resumed after the owner's power cut; read-only declared engine identity
  remains `044c016` and healthy. This review did not restart/edit it. B5 stays excluded.

Older receipts below are historical at their commit. Checked evaluator/lifecycle
slices do not close missing full-system requirements; older open F0 R1-R5 and
CNC adapter tasks were subsequently implemented and independently reviewed.

## October 3 B3 Swing/EDGE evaluator receipt (Dev only)

- [x] Added separate shipped-function evaluator adapters; retained the old
  Swing proxy label.
- [x] Bound daily bar visibility and explicit index/universe requirements;
  incomplete evidence does not become a proxy fill.
- [x] Fixed the shared RSI-history out-of-bounds defect found by B3 binding.
- [x] Focused B3/engine tests passed (149); one existing httpx deprecation
  warning remains.
- [x] Source commit `e349b0b` is Dev-only; no configuration, migration, push
  or deployment occurred.
- [x] B4: Momentum baseline is `MOM_BASE`; Range has an independent
  completed-bar evaluator (70 focused tests, one existing httpx deprecation).
- [x] B4 source commit `3e03916` is Dev-only; no configuration, migration,
  push or deployment occurred. Catalogue consistency was verified after commit.
- [x] B6 evidence-only standard reports, deterministic uncertainty and
  non-overlapping holdout declaration/comparison guard (37 focused tests).
- [x] B6 source commit `60bd989` is Dev-only; no configuration, migration,
  push or deployment occurred.
- [ ] Real-data/Production read-only checks only after Production is restored;
  GitHub promotion remains owner-controlled.

## October 3 B2 CNC receipt (Dev only)

- [x] Exact CNC Connors paper lifecycle replay, with tracker and scanner
  parity ([B2 CNC](2026-10-03-b2-penny-cnc-connors-lifecycle.md); 14 + 7 tests).
  This completes the declared paper lifecycle slice, not historical portfolio context.
- [ ] Predeclared CNC real-data run once Production is running again
  (read-only collector).
- [x] B0 and B3; [ ] B4 and B6 (B5 excluded by the owner).

## October 3 F1-A receipt (Dev only)

- [x] Owner's "no extra margin" definition recorded; read-only audit of every live entry path.
- [x] Own-cash entry guard in the gateway and the Python broker client
  ([F1-A](2026-10-03-f1a-own-cash-no-leverage-guard.md)); gateway 58 / Python 16 tests; full Python suite 4733 passed
  (4 pre-existing failures).
- [ ] Owner decisions: Penny live caps (2,500 against 2,000), Swing/Momentum
  book-level allocation, EDGE notional cap.
- [ ] GitHub promotion; the first live EXEC after deployment should show an
  `entry_own_cash_preflight` log line.

## October 3 B1/B2 receipt (Dev only)

- [x] Plan slice before source changes: [2026-10-03-b1-b2-data-contracts-and-penny-lifecycle.md](2026-10-03-b1-b2-data-contracts-and-penny-lifecycle.md).
- [x] B1 bar data contracts (`research_data_contracts.py`): 29 warnings-fatal tests.
- [x] B2 exact classic Penny MIS lifecycle (`penny_lifecycle_replay.py`):
  22 warnings-fatal tests, including live-scanner parity at every minute and
  a mutation check on the clock.
- [x] Lab `penny_breakout_mis_lifecycle_1m` (`LIFECYCLE`) and CLI
  `--strategy lifecycle`: 6 CLI tests; existing baseline path unchanged.
- [x] Broad regression: 809 passed, 1 skipped (known Starlette/HTTPX
  deprecations only).
- [x] Predeclared read-only Production-data runs archived. Primary: 3 trades,
  +₹31.52. Sensitivity: 5 trades, +₹81.12. No profitability claim.
- [ ] Owner decisions: classic Penny kill-switch wiring (currently inert);
  minute capture through 15:00 for open positions.
- [ ] CNC Connors exact adapter; B3–B6; point-in-time universe and regime.
- [ ] F0 R1–R5 (independent review) and F1 remain open; GitHub promotion of
  these Dev commits.

## October 3 independent F0 review (supersedes source-complete receipt)

- [x] Review F0-A–E against actual source and isolated adversarial fixtures:
  baseline 111 passed, one known Starlette deprecation, normal exit.
- [x] Correct missing-DB creation by shared readers and false unavailability
  after verified terminal zero-fill recovery; three new regressions pass
  warnings-fatal, preserving all exposure and existing exit authority.
- [x] Final six-file selection: 114 passed, one known Starlette warning,
  normal exit; compilation/atlas (229 modules)/whitespace checks passed.
- [x] F0-R1: fee-inclusive exposure conservation after reservation consumption
  ([R1 slice](2026-10-03-fno-f0-r1-fee-inclusive-exposure.md); 11 warnings-fatal tests; Dev only).
- [x] F0-R2: single dispatch ownership, halt-safe retries and ambiguous-entry
  recovery retaining capital until verified resolution ([R2 slice](2026-10-03-fno-f0-r2-dispatch-ownership.md); 37 tests).
- [x] F0-R3: partial cash, future-clock rejection and completed-trade loss streak
  ([R3 slice](2026-10-03-fno-f0-r3-cash-clock-completion.md); 20 tests). Run its Production pre-deployment SQL check first.
- [x] F0-R4: broker payload contents and immutable entry/cost evidence binding
  ([R4 slice](2026-10-03-fno-f0-r4-broker-payload-binding.md); 18 tests).
- [x] F0-R5: transactional existing caps and post-admission-wait action clocks
  ([R5 slice](2026-10-03-fno-f0-r5-occupancy-and-clocks.md); 12 tests; DR race 2 -> 1 structure).
- [ ] GitHub promotion and actual paper/recovery observation; Production
  remains `044c016` and has no shared-risk module at inspection.

Full files/contracts/acceptance/rollout/rollback and final verification:
[independent review](2026-10-03-fno-f0-independent-review.md). B1/B2 remains
pending; tests and source commits do not establish profitability or deployment.

## October 3 continuation receipt

- [x] Deep successor inheritance and shipped-module/F&O safety plan.
- [x] Existing Penny baseline executed: zero trades on a valid two-stock sample;
  earlier unavailable samples preserved; no strategy profitability claim.
- [x] Inert offline CLI and research-only SQLite reader closure; 4 CLI + 11
  replay warnings-fatal; combined 82 passed with one HTTPX deprecation warning.
- [x] F0-A Dev foundation: fail-closed cross-book cash/exposure view and
  transactional one-way reservations; 49 focused F&O checks warnings-fatal;
  source commit `7b86d85` (Dev, pushed; Production untouched).
- [x] F0-B paper admission binding: both books reserve fee-inclusive worst-case
  cash, then atomically consume their receipt with the position insert; exits
  remain allowed. Source commit `0ba2d29` (Dev; pushed). Shared
  loss/drawdown and partial-settlement work remains.
- [x] F0-C shared day/week/month/drawdown (and existing consecutive-loss)
  entry decisions for both paper books: all exact F&O terminal/partial cash is
  common, invalid evidence fails closed and exits remain outside entry halts.
  Dev-only verification: 24 warnings-fatal focused; 79 normal wider F&O tests;
  implementation commit `bc666fe` (local only, not pushed or deployed).
- [x] F0-D verified single-leg partial-settlement residual exposure: recovery
  quantity/generation, exact ledger cash and pro-rata max loss are bound by
  the shared view; mismatches fail new entries closed. Dev-only verification:
  10 warnings-fatal shared-risk tests; 32 shared-risk/recovery tests with the
  known warning-producing ASGI route test deselected; 80 broader F&O
  risk/DR/orchestrator tests passed normally. Source commit `7b77341` is
  Dev-local, not pushed or deployed.
- [x] F0-E receipt-backed partial cash integrity: immutable recovery receipts
  retain entry/fill/gross/cost/net economics; the shared view verifies their
  broker-evidence digest, ledger cash/generation and residual exposure before
  release. Missing legacy partial economics fail entry closed, never guessed.
  Dev verification: 32 focused warnings-fatal; 150 broader F&O tests normally;
  the warnings-fatal wider selection surfaced one existing socket warning.
  Source commit `a9fef57`; Dev-only, not pushed or deployed.
- [ ] F0 operational acceptance: observe paper admissions and recovery evidence
  after GitHub promotion. F1 cash-only broker/margin preflight still precedes
  live funding.
- [ ] F1 owner cash-only funding semantics, broker initial/final margin and
  catastrophe acceptance before live allocation; no live spread authorisation.
- [ ] B1/B2 interval/zero-volume/session data contracts and full classic Penny
  lifecycle; remaining B0–B6 adapters/provenance/portfolio/holdout work.
- [ ] R6 deployed evidence and separate partner qualification/canary.

## October 2 F&O profitability assessment

- [x] Dev-only read-only history CLI; 12 focused warnings-fatal tests; executed
  against Production SQLite without edits/restarts/provider/order/message calls.
- [x] Recent linked positive paper and older unreconciled negative results
  reported separately; no current-policy profitability or allocation claim.
- [ ] Obtain licensed historical executable option quotes and contract masters.
- [ ] Full current-policy causal replay, shared capital/cost stress, independent
  holdout and prospective paper acceptance per the profitability assessment.
- [ ] Any live pilot/funding requires separate owner authorization.

## October 2 release checklist

- [x] R1–R5 source completed and pushed (R4 `c118598`, R5 `addf46b`).
- [x] Production `.env`: AI-safe keys appended; backup `.env.bak-2026-10-02`; render verified.
- [ ] Merge the GitHub PR into Production and recreate containers (operator).
- [ ] Post-deployment read-only checks listed in NEXT_AGENT_PLAN.
- [ ] Backlog `apply` only after reviewing `report` (operator approval).
- [ ] When the AI returns: `ENABLE_NEWS_CLASSIFIER=1`; diagnostics opt-in after verification.
- [ ] R6 operational acceptance gates.

## October 2 review priorities R1–R3

- [x] R1: evidence-bound S6 replays (DR v2 and single-leg binding/reconciliation). 49 tests warnings-fatal.
- [x] R2: gateway backlog report/apply with idempotent receipts; dead-letter acknowledgement. Node 20 suite 471 passed.
- [x] R3: S10 diagnostics, once-only completion updates, strict worker shutdown. Agent 383 / engine bridge 74 passed.
- [ ] Operator: review the backlog `report` in Production, then approve `apply` separately.
- [ ] Deploy the engine diagnostics allow-list, then enable `OPTIONAL_AI_REPORT_DIAGNOSTICS`.
- [ ] R4 (S3 retention), R5 (S7/S8 learning), R6 operational acceptance.

## October 2 continuation review — current acceptance

Use [the independent S7–S10 review](2026-10-02-s7-s10-independent-review.md)
and NEXT_AGENT_PLAN.md's top section; older checkboxes are historical receipts.

- [x] Review new commits and four pending S10 files; preserve unrelated user
  fixtures/audits/Jev artifacts and leave Production untouched.
- [x] Small S10 deadline/retry, S8 cash order/day/coverage, S7 freeze and minimal
  reproduced test-loop corrections; no config/schema/order/authority change.
- [x] Agent 368 warnings-fatal; focused research 28 warnings-fatal; expanded
  engine 1016 passed with six recorded warnings; daily/partner 48; Penny five;
  Node health two; Compose eight and rendered 500 MiB.
  Expanded process hung after its pass summary and required stopping its
  verified Dev PID; clean teardown remains open. Focused checks exited normally.
- [ ] R1: full DR typed source/leg/economics/observation/cash and freeze binding;
  both single-leg raw clocks/tokens and position-economics/cash binding.
- [ ] R2: supported S9 read-only reconciliation and separately reviewed
  idempotent expiry/resolution migration, with receipts and race tests.
- [ ] R3: bounded S10 cause/stage status, once-only valid original-message
  annotation update and strict worker/transport lifecycle tests.
- [ ] R4: S3 bounded CSV capacity/off-path writes and durable elapsed/market-
  hours summaries; actual peak-session/prior-boot retention verification.
- [ ] R5: S7 source-bound thesis/bar eligibility and separate constrained equity/
  correlation research; full S8 learning analytics and versioned proposals.
- [ ] S1/S2 deployed keyed cash/schema/recovery and three market sessions;
  S4 five reconciled paths; S6/S7 newly frozen future HOLDOUT review.
- [ ] S5 frozen protocol, initial 20-session target with adequate closes/coverage,
  authorized qualification and separate delivery canary. No guaranteed tips date.
- [ ] Remaining Windows socket/aiosqlite/coroutine hygiene: minimal reproducer
  only; no warnings-clean full suite is claimed. Promote via GitHub only;
  this review does not push/deploy or send messages.

## October 2 independent S1–S6 review receipt

- [x] S7a: capital-skipped candidate economics and passive paths; frozen
  first-arrival / fixed-equal / risk-proportional common-book replay. 11 tests
  warnings-fatal; cross-phase 1114 passed. No sizing or exit change.
- [ ] After promotion: freeze the allocation manifest before the next session;
  evaluate holdout batches only. S7b holdout acceptance remains open.
- [x] S7b: inert frozen completed-bar continuation versus bounded-pullback
  no-chase research; no-fill/path outcomes, gap/deadline validation and
  distinct thesis/state re-entry condition are explicit. Rejected evaluator
  receipts are available through a bounded isolated-shadow near-miss view.
  Focused timing/shadow suite: 18 passed warnings-fatal. No entry/exit/sizing,
  broker, AI, Production or authority change.
- [ ] Freeze S7b before a new session and evaluate only post-freeze HOLDOUT
  observations; do not promote a timing hypothesis from development evidence.
- [x] S8 initial read-only daily decision-quality report: distinct book/mode/
  policy evidence, partial versus terminal cash, rejected-receipt visibility
  and per-version drawdown where supported. Selection remains human review
  only. Focused warnings-fatal tests: 2 passed; no Production change.
- [ ] S6 spread prototype has mechanism tests, not verified packet/economics
  binding. R1 source correction is required before HOLDOUT interpretation,
  followed by independent review; no runtime authority.
- [x] S9 initial truthful operator-state slice: additive Penny attempt/completed
  clocks and bounded outcome; IST per-source ledger facts with paper books
  kept separate; evidence-labelled Telegram status/dead-letter backlog; health
  probe deadline cleanup. Focused Node health (2), operator status (14) and
  Penny health (5) checks passed. Dev-only; no queue, order, broker, database
  migration or Production change. Source commit `5c9834a`, not deployed.
- [ ] S9 operational backlog handling: review a read-only expiry/reconciliation
  report and a supported idempotent migration for stale requests/callbacks,
  unsynced orders and historical dead letters. Preserve audit records; do not
  use ad-hoc Production SQL or resend stale trade instructions.
- [x] S10 first source-validity slice: optional-AI review excludes stale,
  undated and timezone-unverifiable source classifications instead of expiring
  the whole advisory review; rendered context marks the exclusion as
  `NEWS_UNAVAILABLE`. Focused agent/queue suite: 55 warnings-fatal passed.
  Dev-only; no authority, capital, entry, broker or Production change.
- [ ] S10 remaining: bind provider transport/retry to the task's remaining
  deadline, update the original alert when an annotation completes, then
  collect post-promotion evidence under the existing advisory policy.
- [x] S4 runtime wiring: equity paths attached to the existing research request,
  bounded background writer, deadline-close policy, per-entry adapter
  exclusion. End-to-end test plus 1091 selected tests passed. No Production
  environment change needed (defaults apply; `.env` has no override).
- [ ] After promotion: confirm `momentum_paper_paths` writes in collection runs
  and five reconciled fresh lifecycles.
- [x] Review response: S6 one-entry fee allocation and verified archive pairing
  (`ea8695d`); S3 crash-recoverable rotation (`c054bf3`); S4 typed
  byte-bound path envelope (`bfd343d`). Regressions fail on prior source;
  1024 selected tests passed. Dev only, unpushed.

- [x] Revalidate phase commits/contracts and rendered Dev Compose, not just
  prior completion claims. See `2026-10-02-s1-s6-independent-review.md`.
- [x] Small Dev corrections: DR token/finite prices, passive clock/price
  validation, exact-leg paired future receipt, ambient quote lane, fee/source
  freezes and independent candidate parameter copies. No trading authority,
  exit policy, schema, provider request/rate or Production change.
- [x] Expanded affected suite 948 passed; isolated warnings-fatal checks
  54 DR/S6, seven passive S4 and 11 S5 passed. Broad warnings-fatal socket
  hygiene remains explicitly open. Compose verifier eight passed, rendered
  retention 500 MiB; compilation and atlas (222 modules) passed.
- [ ] S3: recover manifest/state failures across rotation, bound/offload
  writers and preserve durable elapsed/session distinctions; prove actual
  full-session and prior-boot retention after promotion.
- [ ] S4: typed provider-byte/quote binding, bounded existing-fanout integration,
  post-close paths, saturation tests and five fresh reconciled lifecycles.
- [ ] S5: frozen protocol, independent future sample, reviewed qualification
  package and separately authorized delivery canary. No guaranteed tips date.
- [ ] S6: strict raw-packet/contract/clock/conflict and economic/cash binding,
  versioned one-entry/multiple-exit candidate fees, DR spread exit experiment
  and future paired holdout review before any paper-policy promotion.

## October 1 consolidated planning receipt

- [x] Read October 1 audit and cross-check it against Production ledger,
  admissions, retained contract master, collection attempts and telemetry.
- [x] Correct penny/momentum balance confusion, bearish-view versus option-sale
  confusion, and market-hours versus post-market scheduler conclusions.
- [x] Record configured DR lot mismatch plus unpriced/non-atomic settlement
  hazards; no historical incident or corrected cash is fabricated.
- [x] Save [the ordered smart-trader plan](2026-10-01-smart-trader-consolidated-plan.md),
  with files/contracts, reproductions, acceptance, rollout/rollback and effort.
- [x] Implement S1 in Dev: exact selected-contract lot/identity, unresolved
  hard-flat state, atomic/idempotent cash settlement and model-versus-cash
  reporting. Focused warnings-fatal tests: 24; affected F&O suite: 84 passed,
  one deselected timing-sensitive recovery test, and one existing Starlette
  deprecation. Additive migration only; Dev-local,
  unpushed/not deployed at this receipt. Review/push via GitHub and inspect
  deployed receipts before considering S1 operationally complete. Source
  commit: `9e26e1b` on `codex/production-correction-hedge-p0`.
- [x] Implement S2 in Dev with focused regression coverage and receipts.
  October 2 initial sub-slice: management provider reads now have explicit
  5-second exit / 10-second DR snapshot caps with cancellation-joined degraded
  paths and bounded read outcomes; 34 focused checks pass. Remaining: action
  clocks, priority, detailed timing and deployed evidence. Dev-only source
  commit `5ae54a8` is unpushed/not deployed; no broker/settlement/admission
  mutation is deadline-wrapped.
- [x] Implement S2 provider-stage timing/attempt evidence,
  quote-age evidence and refreshed real action clocks. Focused validation: 59
  passed; compilation/atlas passed. Earlier full-completion claim is superseded
  by the independent review below; no cadence/rate increase was made. Source commit
  `d2319e2` is local, unpushed and not deployed.
- [x] Independently review S1/S2; correct post-read/final action clocks,
  frozen signal cutoff, timezone/partial quote-age evidence and scheduler
  completion-log retention. See `2026-10-02-s1-s2-independent-review.md` for
  commands/results and limits. Dev only; existing user changes preserved.
- [x] Finish S2 exact-leg DR management reads, shared-provider priority/fairness
  and DB-wait/timeout-stage attribution. Exact retained legs are never rebuilt
  from a nearest chain; bounded three-admission management priority preserves
  normal fairness and original provider capacity; DB elapsed is honestly
  labelled inclusive of lock wait; cancelled deadlines are partial/unknown.
  Focused checks: 105 passed/one known skip; isolated warnings-fatal DR/Kite:
  53 passed/one known skip. Broad warnings-fatal aggregation still exposes two
  unrelated unclosed-socket warnings. Dev only, pending GitHub promotion.
- [x] Implement S3 evidence retention in Dev: rendered Python-engine logging is
  `20m x 25` (500 MiB); momentum/penny CSVs rotate by IST session into
  SHA-256-manifested archives without routine deletion; final scheduler facts
  are retained in daily outcome/stage rollups before raw-tail pruning. S3
  focused: 57 passed; warnings-fatal rotation/summary: 13 passed; Compose
  verifier: 8 passed. No data migration/deletion, broker, AI authority or
  Production recreation. Rollback is GitHub reversion without archive removal.
- [x] Implement S4 admission-capital and passive equity-path evidence in Dev:
  admitted outcomes retain bounded fixed-pool/cash/deployment/risk/fee policy
  facts and a precise `zero_shares` reason; the INR 50,000 configured benchmark
  is explicitly not drawdown-adjusted. Opened keys seal canonical admission
  packet bytes and an audit-recomputed SHA-256 receipt. Exact-key passive path
  subscriptions preserve original quantity through scale-outs. The caller-fed
  collector accepts only already-observed packet bytes and provider/receipt
  clocks, never fetching data itself; the read-only adapter rejects forged
  bytes, wrong ticker/key, invalid gaps/clocks or missing exact deadline data.
  Focused S4 tests: 73 passed; compilation passed. Additive Dev-only SQLite
  evidence; no strategy/sizing/exit, broker, AI, deployment or Production edit.
  Rollback via GitHub reversion/collector disablement retains evidence.
- [x] S5a: partner candidate persistence/protection use the live action clock;
  explicit replay stays frozen; stale quotes still reject. Late-chain
  regression reproduces the September 30 `stale_or_future_leg_quote`
  rejection on the old source. Partner/hedge/scheduler suites: 373 passed.
  Dev only; no threshold, qualification, profile, delivery or message change.
- [x] S5b: owner-approved `bulk` limiter lane for momentum screener fetches
  (normal ahead, at most three normal admissions while bulk waits; management
  unchanged; rate/burst/concurrency unchanged). Research requests the future plus
  exact active legs first, then the ladder, and records per-call timing.
  141 passed/one skip; warnings-fatal subset 24 passed. Pre-existing partner
  fixture ordering errors are reproduced on clean HEAD; follow-up only.
- [x] S6a: frozen read-only exit experiment (`momentum_exit_experiment.py`):
  manifest freeze/verify, DEVELOPMENT/HOLDOUT labels, thesis-confirmed time
  stop/target extension, exposure and cost-stressed paired metrics. 13 tests
  warnings-fatal; momentum suites 125 passed. No runtime caller.
- [x] S6b step 1: extract the live single-leg F&O exit ladder into pure
  `fno_exit_rules.py` (behaviour-preserving; characterization and 20,000-case
  differential tests; F&O/scheduler suites 397 passed).
- [x] S6b step 2: frozen single-leg F&O exit experiment and read-only
  archive packet adapter; shared metrics module; AST-based no-caller guards.
  30 experiment/ladder tests warnings-fatal; related suites 110 passed.
- [ ] After S4 paths are collecting: freeze the S6 candidate before the next
  session and evaluate HOLDOUT entries only; F&O exit experiments separately.
- [x] S5c: read-only `partner-delivery-blockers` report (ordered per-candidate
  blockers, aggregate attempt/idea disagreement, registry facts, labelled
  current-flag projection; `mode=ro`, never creates DBs). 10 passed
  warnings-fatal; CLI/qualification/partner regression 110 passed.
- [ ] Run the blocker report read-only on Production after promotion; then
  freeze the S5 protocol before any fresh holdout session.
- [ ] After promotion, measure screener elapsed (estimate +10–20%), research
  cap count, `provider_timing` and penny skips on three deployed sessions.
- [ ] Configure S4 path caps, connect an existing quote fanout without adding a
  provider request, then collect five fresh reconciled passive lifecycles.
  These are instrumentation acceptance only, not proof of profitability,
  partner qualification, deployment or trading authority.
- [ ] Before deployment, verify host free space, preserve prior-boot logs and
  collect a complete market-session volume/rotation receipt. This does not
  prove profitability, partner qualification or operational deployment.
- [ ] Inspect at least three complete deployed sessions; no tests establish
  profitability, partner qualification or operational deployment.
- [x] Reproduce optional-review expiry from mixed fresh/stale/undated sources;
  inspect queue/deadline/completion visibility without provider/message calls.
- [ ] Implement S10 context/expiry/deadline fixes and bounded completion updates,
  preserving paper autonomy, source truthfulness and owner EXEC authority.
- [ ] Preserve paths/coverage; freeze future exit/allocation/partner studies.
- [ ] Complete compatible partner qualification and authorized delivery canary.
- [x] Production unchanged; this receipt is planning only. No new software
  tests, source changes, deployment or profitability conclusion are claimed.

## September 26 economic-binding correction

- [x] Require original entry economics as well as exact admission identity;
  reject altered replay size/time/price/stop/target/optional exit inputs.
- [x] Retain immutable bounded snapshots atomically with opened admissions;
  keep legacy/corrupt evidence unavailable and preserve trading authority.
- [x] Validate 42 research/audit tests with warnings fatal; 122 affected tests
  pass with one existing Starlette lifespan deprecation warning.
- [ ] Promote through GitHub; collect fresh snapshot-bearing admissions and
  provenance-verified LTP paths, then review a predeclared reconciled sample.
- [ ] Independently qualify partner research and authorize a transport canary.
  Production remains untouched by this correction.

## September 25 adaptive-trader product decision (plan only)

- [x] Preserve autonomous deterministic momentum paper trading and explicit
  owner EXEC approval for every new real-money momentum entry. Reject an
  unrequested default AI veto on classifier timeout.
- [x] Add the [adaptive trader roadmap](2026-09-25-adaptive-trader-vision-plan.md):
  opportunity/thesis lifecycle, paper-only paired exit study, predeclared
  strategy basket, costed allocation research and separate partner authority.
- [x] Implement the first Dev paper-only exit comparison according to
  [the exit-study slice](2026-09-25-adaptive-exit-study-plan.md): source-bound
  chronological LTP evidence, net costs, deadline/gap checks, drawdown and
  explicit unresolved paths.  `momentum_exit_study.py` is no-runtime research
  code; focused acceptance passed 13 warnings-fatal tests and the affected
  momentum surface passed 109 with one existing Starlette lifespan warning.
  Source commit `cbc5fca` is pushed on the Dev branch and not deployed.
- [ ] Preserve actual timestamped quote packets and run the comparison over a
  predeclared bounded momentum-paper sample.  Keep incomplete evidence marked
  `INSUFFICIENT_EVIDENCE`; obtain independent future holdout before any
  owner-reviewed proposal.  No result authorizes live exits, orders or partner
  advice.
- [x] Implement the [Phase 2 momentum-paper decision baseline](2026-09-26-adaptive-decision-baseline-plan.md):
  retain new admission-to-position-to-cash keys, audit them read-only, and
  label all legacy/unlinked lifecycle evidence unavailable. Focused acceptance:
  9 warnings-fatal audit/lifecycle tests; affected momentum surface: 194 passed
  with one existing Starlette lifespan warning. Source commit `94871f2` is
  pushed on `codex/production-correction-hedge-p0`, not deployed. No backfill,
  live/paper strategy change or new authority was added.
- [ ] After reviewed promotion, verify the additive `paper_admission_key`
  migration and run the read-only decision audit against fresh paper entries.
  Preserve old unlinked evidence as unavailable; do not infer a strategy edge,
  partner qualification or live authority from the report.
- [x] Implement the [Phase 3 source-bound evidence review](2026-09-26-adaptive-evidence-binding-plan.md):
  future exit-study packets may carry the exact admission key and the
  read-only composite review rejects all heuristic/ticker joins. Focused
  Phase 1/3 tests: 20 passed warnings-fatal; affected paper/replay suite: 214
  passed with one existing Starlette lifespan warning. Source commit `beb7e78`
  is pushed on `codex/production-correction-hedge-p0`, not deployed. No runtime
  authority, strategy, allocation, exit, broker, EXEC or partner behavior
  changed.
- [ ] After reviewed promotion, retain a predeclared sample of fresh keyed
  admissions and complete LTP paths; run the Phase 3 review and preserve every
  unavailable/unresolved row. Run the frozen strategy-basket comparison only
  on later held-out sessions. No report can qualify advice or change a trade.

## September 25 Production audit response (plan only)

- [x] Reconcile the deployed merge and 25 September paper ledger read-only;
  correct the paper-admission table name and verify TENNIND `opened` plus
  PARADEEP `zero_shares`. No speculative migration is required.
- [x] Separate post-close container replacement from unproved Docker log
  rotation, informational F&O parity warning from entry veto, and expected
  post-close penny health staleness from a proven restart defect.
- [x] Verify a saved general INTRADAY profile, 165 collection attempts per
  index on 25 September, six SENSEX candidate decisions and zero general
  qualifications. The hedge phase's 0/7 staging counter is separate.
- [ ] Execute the ordered [September 25 plan](2026-09-25-production-audit-response-plan.md):
  release-spanning forensic logs, three-session deployed coverage/safety
  observation, packet-level parity diagnosis, next-session penny recovery,
  and predeclared held-out general partner research/review.
- [ ] Any TEST canary, advice, broker action or Production deployment requires
  its separate authority and evidence. This documentation change grants none.

## September 24 P2 F&O audit evidence and financial interpretation (Dev)

- [x] Preserve the first-reject contract and add only the passed-gate prefix
  plus active-switch evidence to future F&O signal rows.  The trace proves
  preceding gates, never hypothetical later sizing/execution/admission.
- [x] Add a strictly read-only daily audit builder/CLI: it refuses to create a
  missing database, groups repeated rows as one decision unit, exposes
  switch-policy thresholds/evidence, and labels legacy evidence unavailable.
- [x] Separate `TRADE_PARTIAL` cash events from `TRADE_CLOSED` outcomes by
  FNO_PAPER/FNO_LIVE, mark costs unavailable where the ledger lacks them, and
  emit no expectancy/qualification verdict.  Focused suite: 84 passed;
  broader F&O/performance/division suite: 376 passed with two pre-existing
  framework deprecation warnings; compilation passed.
- [ ] After reviewed promotion, run `fno_audit_report.py` read-only against a
  retained F&O database for a logged-in session. Compare its decision-unit and
  switch evidence to raw rows; do not call repeated leg rows independent trade
  opportunities or infer an edge from daily paper P&L.

## September 24 P2 classifier latency containment (Dev)

- [x] Identify the owned retry mismatch: the 1-second informational classifier
  reused the analyst client with `MINIMAX_MAX_RETRIES=1`.
- [x] Construct and select an isolated classifier client with
  `CLASSIFIER_MAX_RETRIES=0`; retain the analyst review client's existing
  retry configuration and all review/entry authority semantics.
- [x] Verify direct fallback and agent helper client selection, one bounded
  timeout call returning `UNKNOWN`, unchanged classifier provenance/fallback
  and the complete agent suite: 361 passed. Compilation and atlas regeneration
  passed.
- [ ] After reviewed promotion, observe classifier elapsed/error telemetry on
  real provider calls. Treat a provider service tail as an operational issue;
  do not re-enable retries or change deterministic entry authority without a
  separately reviewed budget and evidence.

## September 24 P1 momentum-paper admission forensics (Dev)

- [x] Record an opaque accepted-signal identity and enumerated immutable
  outcome after the actual paper boundary: opened, already-held, zero-shares,
  disabled, upstream-deduplicated or transaction-failure. No raw signal
  payload, broker route or order capability is added.
- [x] Write normal outcomes with the position transaction; a rolled-back insert
  cannot appear opened. Where the evidence database remains available, retain
  a separate transaction-failure receipt. Bound retained outcomes at 20,000.
- [x] Record repeated accepted signals at the `main.py` alert-dedup boundary,
  not as a decision by the paper opener; preserve a separate immutable attempt
  if a legitimately closed paper position reopens.
- [x] Focused paper/regime/shadow checks cover TATATECH-like repeats, held,
  zero-share, disabled, rollback and retention outcomes plus real boundary
  wiring: 159 passed with one existing Starlette deprecation. This is
  explainability evidence, not strategy qualification.
- [ ] After reviewed promotion, inspect real admission outcomes alongside the
  retained accepted-signal log. Investigate an unexplained missing record; do
  not infer a trade from `opened`, nor a profitable strategy from paper P&L.

## September 24 P1 F&O tick-tail containment and exit-safe telemetry (Dev)

- [x] Read Production logs without mutation and isolate 27 F&O runs at/over
  90 seconds (12 on 23 Sep, 15 on 24 Sep). Their repeatable tail was paper DR
  entry preparation; each showed zero DR opens/exits. Do not infer that all
  broader scheduler skips or any active-exit delay share this cause.
- [x] Bound only the new paper-DR entry's cancellable chain/history reads with
  `FNO_DR_ENTRY_MARKET_DATA_MAX_SEC=20`. Existing DR management, hard-flat,
  single-leg exit handling and the mutation that admits a structure remain
  unbounded by this entry deadline.
- [x] Emit separate DR snapshot/management/entry-input/admission durations and
  `dr_entry_skip_reason`. A stalled-input regression proves cancellation and
  join, named evidence and no order; focused F&O/DR/scheduler checks pass.
- [ ] After reviewed GitHub promotion, compare at least one complete logged-in
  session with the new fields. Keep the 90-second cadence unless evidence
  proves an active risk-management path needs a separate correction. Roll back
  this bounded paper-entry change through GitHub if it worsens exit timing or
  produces unknown-state handling.

## September 24 P1 research quote deadlines and truthful coverage (Dev)

- [x] Replace the between-index-only cap with a per-provider remaining-budget
  boundary that cancels and joins the shared Kite coroutine before return.
- [x] Persist/return cap, elapsed and partial-count fields for normal, deadline
  and error outcomes; expose a named per-index state and exact/unknown active-
  leg coverage gaps without fabricating a quote; rotate first-index ownership
  by deterministic scheduler-slot order across restarts.
- [x] Prove a stalled first NIFTY provider cancels, returns within its cap,
  records the NIFTY active-leg/SENSEX coverage gaps, and leaves no operation
  alive. Prove normal durable telemetry. Focused suite: 54 passed; all
  `test_research_*`: 62 passed; combined collector/scheduler/Kite-client:
  173 passed/one skipped with one pre-existing Starlette lifespan deprecation;
  compilation passed.
- [ ] After reviewed promotion, collect and retain three logged-in session
  receipts showing per-index requested/received active legs, cap count,
  p50/p95/max provider stages, overruns and skipped slots. Do not change the
  60-second cadence or qualify advice from this implementation alone.

## September 24 P0 decision-forensics retention verification (Dev)

- [x] Inspect Production read-only: Python and gateway use `json-file`,
  `max-size=20m`, `max-file=10`; Python's retained 18.13 MiB file spans
  35.897 hours at 0.50 MiB/hour observed, with no rotation confirmed.
- [x] Preserve the existing 200 MiB engine cap rather than enlarge it from an
  unsupported daily-rate estimate; record 104.42 GiB host free space and the
  Docker artifact sizes as bounded evidence, not a peak-rate guarantee.
- [x] Add the rendered-Compose guard and run 8 focused tests plus the live Dev
  `docker compose config --format json` assertion. It exposes no environment
  values and changes no running service.
- [ ] After GitHub promotion, recreate only if a future approved Compose change
  requires it, inspect the effective engine log config read-only, and retain
  opening-to-close logs for three consecutive logged-in sessions. Roll back a
  future retention change through GitHub if disk pressure or log loss occurs;
  do not delete existing evidence.

## September 24 gateway test-lifecycle correction and Dev acceptance

- [x] Stop the Jest-only background holiday refresh from outliving the suite,
  without changing the production engine-refresh default or calendar
  fail-closed fallback.
- [x] Pin the explicit Jest worker/setup contract in the market-hours unit test.
- [x] Compatible Node 20 gateway: 30 suites passed/1 skipped; 461 tests
  passed/4 skipped; natural exit 0. Scripts: 226 passed. Agent: 357 passed.
  Dashboard: 46 passed and production build completed. Atlas regenerated to
  211 Python modules.
- [ ] Obtain a fresh clean full `python-engine/tests` process exit for the
  receipt. This is test-runtime/CI hygiene—not an unimplemented product
  feature. Prior full receipts completed assertions before retained aiosqlite
  workers; diagnose an owned leak with a minimal reproducer before changing
  application teardown or suppressing warnings globally.
- [ ] GitHub promotion, stamped deployment verification, retained-data backup,
  real-session collection/reconciliation, a saved INTRADAY profile, genuine
  held-out qualification and an explicitly authorized Telegram canary remain
  operator/research gates. Nothing here sends an order or a partner message.

## September 24 real-research package-builder implementation (Dev)

- [x] Add a root-confined, size-bounded authorization-package assembly CLI; it
  reads immutable full-policy reports and never uses an operational DB default.
- [x] Reconstruct held-out evidence and review from every source report; reject
  mismatched scope/policy/criteria, altered replay bytes, non-approved review
  identities, invalid clocks and non-identical replacement output.
- [x] Verify assembled bytes through the real current authority verifier without
  registering a qualification or granting any delivery/order authority.
- [x] Focused package/replay/held-out/review/authority/CLI suite: 64 passed
  warning-fatal. Broader research/advisory suite: 235 passed with one existing
  Starlette async-generator-lifespan deprecation; the warning becomes a setup
  error only under warning-fatal mode. Atlas regenerated to 211 Python modules.
- [ ] Collect real completed-bar and selected-leg data, freeze a future holdout,
  obtain an independent human review and explicitly admit only compatible
  evidence through the existing registry. Tests and package assembly do not
  establish profitability or authorize partner tips.

## September 24 F&O exit recovery implementation (Dev)

- [x] Authenticate pending-intent inspection and explicit named resolution.
- [x] Verify same-day broker order, trades and net position; retain the bounded
  snapshot/digest and fail closed on missing, stale, conflicting evidence.
- [x] Atomically account partial/full fills and terminal zero fills, preserve
  cumulative P&L and residual risk, and reject stale/concurrent retry claims.
- [x] Broad Python run: 4,493 passed/four skipped, with the sole intentional
  route-golden mismatch; regenerated diff adds only GET/POST recovery routes.
  Route/F&O acceptance then passed 74 tests. Focused recovery/risk after the
  cross-session kill-switch, migration and read-only inspection fixes passed 65
  broker-client/recovery/risk/surface tests. Existing framework
  deprecations remain. Atlas regenerated to 210 Python modules.
- [x] Implementation commit `30a6b8c` pushed to
  `origin/codex/production-correction-hedge-p0`; post-commit scope and
  canonical documentation checked. Existing unrelated worktree files were not
  staged. This new slice is Dev-only until a GitHub promotion.
- [ ] Promote through GitHub, rehearse with real broker evidence and keep live
  single-leg activation a separate operator decision. Older unknown intents
  need statement-level reconciliation; never delete one to force retry.

## September 23 independent remediation completion

Read the [review, migration and recovery instructions](2026-09-21-independent-remediation-review.md)
before taking over. Dev branch: `codex/production-correction-hedge-p0`; reviewed
incoming HEAD `674a6fe`; correction commit `8f8f39f` (post-commit consistency checked).
Production remains untouched. Earlier audit artifacts and pre-existing golden
fixture edits are not part of the correction commit.

- Verify source/ledger index and additive exit-intent/receipt tables on a backup.
- An acknowledged fill retries accounting only; an ambiguous dispatch needs broker
  reconciliation. Preserve evidence and keep live single-leg execution off until
  the operator recovery workflow is ready.
- Mount real immutable authorization packages and confirm exact profile/code/config
  compatibility. Old qualification rows may now correctly block new advice.
- Run read-only readiness with explicit DB/archive/token paths; absent/WARN evidence
  is not delivery-ready. Current token-file metadata is not a broker auth probe.
- Promote only through GitHub and verify all running image identities. Test success
  never substitutes for real strategy qualification, reconciliation or canary consent.

Verification: **4,476 Python passed / 4 skipped**, **460 gateway passed / 4 skipped**
in compatible Node 20; 46 known Python framework deprecation warnings. Syntax,
staged diff and 209-module regenerated atlas checked. No dashboard source changed.

## September 20 Workflow I.4.D provenance correction (Dev tested)

The classifier no longer refetches news after rendering sentiment: Yahoo and
Google are fetched once each and the same frozen items feed both raw and typed
context. Results retain the requested ticker, bounded source URL/name, aware
publication time and source digest; unreliable source metadata fails closed to
UNKNOWN. That includes stale-at-seven-days, missing/naive/future clocks and
invalid/non-HTTP(S) URLs. Classification context is part of enabled cache
identity, while the disabled legacy key is unchanged; the queue independently
guards direct reused-key collisions. Available/unavailable/exception typed
reviews retain structured immutable source provenance and expiry. Sync late
results are payload-free unavailable; READY/CACHED expiry can tighten but never
extend. CLI file input now parses aware RFC/ISO clocks.

Focused warning-fatal acceptance: **185 passed**. Complete isolated agent:
**357 passed**, warning-fatal, network disabled, Dev mounted read-only. Changed
Python compilation and `git diff --check` passed; the code atlas regenerated at
**203 modules**. No engine/dashboard source changed, so their September 19 full
receipts remain the applicable cross-component baseline and were not rerun.
No schema/config default/broker/partner message/order/Production edit or
authority change. Implementation commit **`3495ecb`** passed its immediate
source/docs/atlas consistency review. Implementation and receipt commits
**`3495ecb` + `a4e189f` are pushed** to
`origin/codex/production-correction-hedge-p0`. Real provider
freshness/latency and operator-labelled usefulness
remain Production evidence, not test claims. See the
[plan](2026-09-20-i4d-classification-provenance-plan.md).

## September 19 Workflow I usefulness contract (Dev tested)

The real ten-field optional-AI usefulness snapshot now crosses the agent/engine
boundary without rejection. Strict validation rejects unknown/leakage keys,
booleans, negative/nonfinite latency, invalid or inconsistent cache rates,
inconsistent review totals, invalid verdict buckets, and naive completion
timestamps. Partial historical envelopes remain readable. The hourly
contract-health job now recognizes the real status envelope and runs both the
leakage and usefulness checks. Dashboard evidence includes p95 latency and last
completion, with unavailable legacy fields shown as `—` rather than zero.

Focused engine acceptance: **72 passed/four known framework deprecations**.
Broader optional-AI engine acceptance: **89 passed/five known deprecations**.
Complete isolated agent acceptance: **340 passed**, warnings fatal, networking
disabled and Dev source mounted read-only. Dashboard: **46 passed** and Vite
build passed with the existing outdated Browserslist notice. Whole engine:
**4,117 passed/four skipped/46 known framework deprecations in 209.34s**;
JUnit: `C:/Users/Urveesh/AppData/Local/Temp/sentinel-workflow-i-usefulness-contract-20260919.xml`.
Atlas regenerated at 203 modules; changed Python compilation and diff checks
passed. Implementation commit `8dd2c41` passed its immediate source/docs/atlas
consistency review with a clean worktree and was pushed to
`origin/codex/production-correction-hedge-p0`. No schema/config
default, broker/network call, partner message, order, Production edit, or
authority change. Real Production status evidence and operator usefulness
labels remain open. See the
[plan](2026-09-19-workflow-i-usefulness-contract-plan.md).

## September 19 Workflow G.7 (Dev tested)

The range-reversion simulator no longer chooses the last bar before the entry
deadline and then backdates a modeled fill to an earlier bar. It evaluates only
the first completed post-cutoff decision bar and begins execution after it.
Insufficient/malformed inputs never fall through to generic confirmation. The
comparison protocol removes its stale alias/forced-uncertain rule while keeping
all ordinary evidence gates and no-authority fields. Existing frozen protocols
remain implementation-hash bound and require a new protocol ID.

Focused range/comparison baseline was **76 passed** warning-fatal; corrected
focused range/comparison is **81 passed** and the broader G surface is **222
passed**, both warning-fatal. Whole engine is **4,095 passed/four skipped/46
known framework deprecations in 204.44s**; JUnit:
`C:/Users/Urveesh/AppData/Local/Temp/sentinel-g7-range-causality-20260919.xml`.
Atlas remains 203 modules; changed-source compilation and diff checks pass.
Implementation commit `fefa5a3` contains source, tests, atlas and documentation;
its immediate consistency review passed with a clean Dev worktree. Verification
receipt `bc79325` also passed its immediate review; both commits were pushed to
`origin/codex/production-correction-hedge-p0`. They are not merged, released or
deployed. No schema/config/default, broker call, order, partner delivery or
Production mutation occurred.

## September 19 Workflow F.10A (Dev tested)

The new read-only broker/internal report checks executed imported broker order
IDs against retained live references in both position books and records
missing, ambiguous and insufficient-scope results without granting any trading
or capital authority. A broker cash `MATCH` can no longer suppress a missing
internal order reference. The HTTP and CLI response changes are additive.

This slice has no table migration, history rewrite, configuration/default
change, broker/network call, order submission or partner delivery. It does add
three discrepancy category strings; rollback removes the producer/bridge, but
already appended rows require code that recognizes those values. Bidirectional
economic reconciliation still needs account-scoped internal books, statement
period bounds, universal order IDs, richer immutable fill data and genuine
broker evidence. Focused reconciliation acceptance: **118 passed/21 known
framework deprecations in 6.95s**. Whole engine: **4,090 passed/four skipped/46
known deprecations in 204.15s**; JUnit:
`C:/Users/Urveesh/AppData/Local/Temp/sentinel-f10a-broker-internal-final2-20260919.xml`.
The first whole run exposed an unrelated microsecond clock race in one MTM test
fixture; binding its quote and report to the same instant made that test
deterministic, and the exact final tree passed. Atlas regenerated at 203 Python
modules; changed Python compilation and diff checks passed. Production remains
unchanged. Implementation commit `1dde067` contains source, tests, atlas and
canonical documentation. Its immediate stat/status/guide/plan/atlas review
passed with a clean Dev worktree. Verification receipt `d2735e9` also passed
its immediate consistency review. Both commits were pushed to
`origin/codex/production-correction-hedge-p0`; they are not merged, released or
deployed.

## September 19 Workflow C.C2.SOURCE (Dev tested)

The modeled asymmetric path no longer borrows prices from the earlier decision
book. Each missing-leg estimate retains and uses its own archive-verified
packet hash, clock, bid/ask and quantity; incomplete legacy evidence fails
closed. Held-out admission cross-checks the source and recomputes the fill/P&L,
including rejection of a rehashed source mutation. Focused acceptance: **87
passed** with warnings fatal; broader C: **259 passed**; whole engine: **4,070
passed/four skipped/42 known deprecations in 205.51s**. JUnit is retained at
`C:/Users/Urveesh/AppData/Local/Temp/sentinel-workflow-c-source-binding-20260919.xml`.
No schema/config/data migration, broker call, delivery authority, flag change,
or Production edit. Implementation commit: `e2212cb` on
`codex/production-correction-hedge-p0`; verification receipt: `1a97932`. Both
were pushed to `origin/codex/production-correction-hedge-p0`. See
[the plan and receipt](2026-09-19-workflow-c-asymmetric-source-binding-plan.md).

## September 19 Workflow C.C2.HOLDOUT (Dev tested)

The modeled partial CLOSED path is now held-out ingestible and separately
counted, with negative adverse-entry slippage, degenerate-book fail-closed
behavior, strict provenance validation, and qualification propagation. It does
not claim verified full economics. Focused: **90 passed**; qualification and
held-out: **134 passed**; broader Workflow C/research/orchestrator: **226
passed**, one known Starlette warning; whole engine: **4,069 passed/four
skipped/42 known deprecations in 214.71s**. Atlas regenerated at 202 modules.
JUnit is retained at
`C:/Users/Urveesh/AppData/Local/Temp/sentinel-workflow-c-partial-holdout-20260919.xml`.
System Python lacked pytest, so validation used the checked-in Windows venv.
No schema/config migration, retained-data rewrite, external call, delivery,
broker action, or Production mutation. Implementation commit: `6348fdb` on
`codex/production-correction-hedge-p0`; immediate post-commit source/guide/plan/
checklist/atlas consistency review passed with a clean Dev worktree. The
read-only Production checkout remained at `fef35e7` with its pre-existing
untracked audit/migration files untouched. Commits `6348fdb` and `070e9c0`
were pushed to `origin/codex/production-correction-hedge-p0`. Merge/PR, real
held-out collection, qualification, deployment, and partner delivery evidence
remain unchecked.
See [the slice receipt](2026-09-19-workflow-c-partial-holdout-plan.md).

## September16 current-state override

Momentum/CAS release candidate: pushed Dev commit `ee0a300` schedules live momentum auto-square at 15:13 IST, transfers exclusive ownership from the monitor under a shared lock and enforces a 15:14:30 hard submission cutoff. The path checks before stop cancellation and immediately before submission; a pre-submit abort after cancellation attempts and persists replacement protection and pages the operator. Focused suites:79 passed; scheduler/calendar subset after restoring direct wrapper gates:25 passed; final Python:3730 passed/four skipped/42 existing deprecation warnings; agent:338 passed. The completed pytest receipt retained aiosqlite worker processes, and the exact processes were stopped. No schema/config migration, retained-data rewrite, broker call or Production mutation. Merge, deployment SHA and market-session observation remain unchecked.

Dev started clean/pushed at `6c54b78`; Production read-only checkout is merge `967e07a` and all six containers are up (three application containers healthy), but trading readiness remains false because broker order execution is unverified. Dev has eight commits after the deployed source parent, including the Production-found contract-health alert fix. Do not call those deployed. The new manual-card path has zero qualified strategies, artifacts, ideas or delivered cards; current saved profile/inputs and destination configuration do not substitute for genuine qualification.

Independent J negative review found resolver/calendar payload-binding defects after `00dffbd`; pushed Dev commit `97e62e7` now requires an HMAC-bound exact symbol/source/version response, rejects malformed holiday payloads atomically and expires engine-loaded as well as fallback calendars. It also fixes deterministic SUMMARY verification and serializes operational-coverage SQLite initialization to remove intermittent locks. Final verification: Python3725 passed/four skipped/42 existing deprecation warnings in213.57s; native runtime-matching Node424 passed/four skipped; dashboard43 passed plus build; agent338 passed. The completed Python run left aiosqlite worker threads alive after its receipt, so the exact test processes were stopped and clean teardown remains a follow-up. Merge/deploy/staging CAS captures remain pending; no Production file, service, partner channel or broker was mutated.

## September14 independently reviewed correction (Dev only)

G/C protocol source plus real-simulator/temp-SQLite acceptance are corrected; exact late freeze/output retries preserve immutable history, full manifest/cost/source identity is retained, all declared sessions and outcome states appear, seeded cluster CI matches the opportunity-weighted estimand, actual-price turnover replaces quantity-as-turnover, and every profile has explicit baseline/stress research gates. CLI tests isolate standalone `asyncio.run` in a worker thread; no runtime suppression or scheduler changes.

Command from Dev `python-engine`: `.\winvenv\Scripts\python.exe -m pytest tests/test_comparison_protocol_acceptance.py tests/test_research_cli_strategy_comparison.py tests/test_research_cli_qualification.py tests/test_proactive_intelligence.py tests/test_proactive_execution_research.py tests/test_proactive_exit_research.py tests/test_proactive_portfolio_research.py tests/test_trailing_stop_profile.py tests/test_promotion_bridge.py tests/test_range_reversion_profile.py -q -W error`:156 passed/no warnings6.84s, exit0. Full `-m pytest tests -q --junitxml=C:/Users/Urveesh/AppData/Local/Temp/sentinel-g-protocol-reviewed-20260914.xml`: receipt3304 cases/zero failures/errors/four skips173.475s; process teardown still active at inspection, exit/warning summary unconfirmed. Do not call this a clean full run yet.

Source commit8561820; immediate nine-file stat/status review confirms guide/plan/checklist/atlas and actual-source tests are included. Only the two preserved external golden generated-at edits remain dirty. Only new offline tables/triggers, no operational ALTER/history rewrite, no flags/order/transport authority. Preserve existing protocols; incompatible source identities require a newly frozen ID, never rewriting an old manifest. No push/deploy. F/J claimed closure is superseded by [independent findings](2026-09-14-external-work-independent-audit.md); I, real coverage/heldout results, risk preferences, account reconciliation and D release/session acceptance remain pending.

## September 14 J.10.CLOSURE + independent correction plan

J.10 CAS-branch reachability gate closed `ba91dcc` + `414207e`. J.10.CLOSURE operator-facing SUMMARY.md surface closed `c734e4c` (source, +820 lines, +13 new tests pinning SUMMARY contract + happy-path auto-update hook + critical schema-bug fix) + `b8a490e` (docs, +184 lines, J.10 done-doc + SUMMARY.md + plan/atlas/guide sweep). Critical bug fix during J.10.CLOSURE: `_safe_phase_from_capture` was reading `doc["classifier"]["phase"]` and `doc["phase"]` (top level); the J.3 capture schema stores the bounded phase at `rows[i].classifier_phase`. The gate was silently counting every capture as "skipped". Fixed to iterate `rows[]` and read `rows[0].classifier_phase`. Five fixtures in `test_cas_reachability_gate.py` and one fixture set in `test_cas_reachability_summary.py` were using the legacy shape; both files now use the J.3 schema shape. `docs/j2_captures/SUMMARY.md` is the persistent audit surface; the gate currently returns UNREACHABLE because `docs/j2_captures/` has no operator-supplied staging captures — flipping to REACHABLE is operator work (run probe in staging, review captures), per plan §14.

Independent correction plan (`docs/2026-09-14-independent-correction-plan.md`) closed in 5 source commits:

- `050e58a` — F6 fail-closed capital evidence: `loss_tolerance_pct` now `Optional[float]` (default flips to `None`; no more 25.0 fabricated engineering default); CLI never returns `can_grow_live_capital=True`; explicit `authorization_effect: NONE` field documents the diagnostic-only nature. +5 independent regressions (`tests/test_capital_policy_independent.py`).
- `2133a3c` — F3/F4/F5 writer/account/output contracts: `mark_to_market` `qty` is contract units (no double-`lot_size`); `complete_unrealised_pnl` returns `None` on non-FRESH; legacy fno_dr_book rows return `UNSUPPORTED`; `record_from_evidence_report` writes internal ledger facts under `INTERNAL_UNSCOPED_ACCOUNT_ID`; `_row_to_record` exposes `account_attribution`; `_payload_to_import_kwargs` rejects null/blank identity; `'imported'` key removed (operator can't verify the behavioural claim); byte-identical retry pinned. +7 independent regressions.
- `fd450a3` — F3 reporting follow-up + J.5 holiday reconciliation: `penny_hourly_report` renders 'UNAVAILABLE (incomplete/stale quotes)' instead of misleading `Rs +0`; `main.py` uses `complete_unrealised_pnl`; `market_calendar.NSE_HOLIDAYS_VALID_THROUGH = '2026-12-31'` is the documented static-set validity; `routes_holidays.py` exposes `valid_through` in the response. The pre-correction drift signature Python=20/Node=18 is documented as historical; the post-correction state Python=20/Node=20/drift=0/verdict=ALIGNED is pinned. `main_surface_golden.json` regenerated to include the new `routes_market_session` route.
- `00dffbd` — J/H live CAS eligibility + degraded calendar: NEW `routes_market_session.py` is the single authoritative Python projection (`/market-session/cas-eligibility`, authenticated, `source_version` is a SHA-256 hash of the configured CSV); NEW `services/cas-eligibility.js` is the only Node fetch path (short-circuits outside the 15:15-15:29 IST cash-CAS-affected interval via `isCashCasEligibilityResolutionWindow`); NEW `entrySessionVerdict` chains eligibility with `isExecutionAllowed` (unresolved eligibility returns `allowed: false, phase: 'CAS_ELIGIBILITY_UNAVAILABLE'`). `services/executor.js` and `index.js` call `entrySessionVerdict(signalData.ticker, new Date())` BEFORE any DB UPDATE / EXECUTING transition / answerCallbackQuery — `executor.executeSignal` is never reached; no `EXECUTING` status is recorded. The Node `NSE_HOLIDAYS_FALLBACK` is now the exact ISO projection of `market_calendar.NSE_HOLIDAYS_STATIC` (20 dates); `isHolidayCalendarUsable()` fails closed after `NSE_HOLIDAYS_VALID_THROUGH`. +9 new tests; updated `tests/integration/approved-snapshot.test.js` with `cas-eligibility` mock to prevent regressions.
- `64e22a9` — docs + chore: imported `docs/2026-09-14-independent-correction-plan.md`; refreshed session_phase golden timestamps.

**Final defensive regression** at the close of this slice:

- Python J + F + I + cas-reachability surface: **362/362 PASS** (was 3267/4/1 at J.7 close; +19 new tests across F6/F3/F4/F5/market-session; 0 regressions)
- Node full (excl. db.test): **394 pass / 4 skip / 0 fail** (was 385/4/0 at J.10.CLOSURE close; +9 new; 0 regressions)
- Client full: **40 pass / 0 fail** (unchanged; no client changes)
- Working tree: clean
- Branch: `codex/production-correction-hedge-p0`, 438 commits ahead of origin at this slice's close

The J series is now operationally closed (J.1 → J.2.1 → J.2.2 → J.3 → J.4 → J.5 → J.6 → J.7 → J.7-HARDENING → J.8 → J.9 → J.10 → J.10.CLOSURE = 13 sub-slices). F3/F4/F5/F6 are hardened. The only J-related follow-up is operator-supplied staging captures (gate-flip UNREACHABLE → REACHABLE); the only F-related follow-up is operator-signed `BridgeDecision` + actual release validation under D.

J.10 follow-up operator-surface enhancements (post-CLOSURE):
- `12912b1` per-branch captures catalog in SUMMARY + CLI; gate report gains `captures_by_branch: dict[str, list[str]]`; SUMMARY renders a `## Captures catalog` section with sub-headings per branch (zero-capture branches render `(no captures yet)`); CLI human output gains a `captures catalog:` block; CLI `--json` includes the field.
- `37f585f` end-to-end CLI test coverage (9 tests via subprocess) — pins exit codes, `--json` shape stability (exactly 7 keys), `--update-summary` writes SUMMARY.md, `--summary-path` overrides, `--write` persists JSON report.
- `1c35633` per-branch IST-window runbook in SUMMARY — fixed the legacy `--observation-at 15:22:00 IST` syntax bug (the probe CLI doesn't accept it); replaced with a per-branch IST-window cheat-sheet + two ISO 8601 example commands.
- `2b7a670` `--status` flag for shell prompts and monitoring — single-line output, exit code follows verdict, count-driven branch counting (5 captures on 1 branch = 1 branch captured).
- `181f6ee`, `4630131` docs sweeps to reflect the J.10.CLOSURE + independent correction plan + these follow-up enhancements.

Net J.10 follow-up slice delta: python-engine +18 new tests across 4 commits (3 catalog + 9 CLI + 3 runbook + 3 status). All defensive regressions clean: Python 380/380 PASS (was 3267/4/1 at J.7 close, +113 net); Node 394 pass / 4 skip / 0 fail (was 380/4/0 at J.7 close, +14 net); Client 40/40 PASS (no client changes).

I.4.D source-event classification (5 commits across two sessions):
- `c80e3fa`  bounded classifier module: fixed 8-category `NewsCategory` taxonomy (`REGULATORY`, `EARNINGS`, `M_AND_A`, `GUIDANCE`, `MACRO`, `RUMOR`, `TECHNICAL`, `UNKNOWN`); frozen `ClassificationResult` dataclass (ticker, title_hash 12 hex chars of SHA-256, category, confidence ∈ [0,1], bounded rationale ≤ 280 chars, prompt_version, classified_at); `CONFIDENCE_THRESHOLD = 0.6` (fail-closed: below threshold → UNKNOWN); `CLASSIFIER_TIMEOUT_SEC = 1.0` per-item latency budget; never raises (timeout / parse error / disabled / model exception → UNKNOWN + confidence=0.0); fixed taxonomy — a category the model invents (outside the enum) is forced to UNKNOWN; `DISABLE_CLASSIFIER` forces every result to UNKNOWN (offline / CI / sandbox); `_extract_json_object` parser tolerates `<think>...</think>` blocks (MiniMax-M3 reasoning), `\`\`\`json\`\`\`` fences, leading prose, malformed input. 36 module tests pin the contract.
- `d60073b`  verdict-prompt rendering: `analyze_with_minimax` gains an OPTIONAL `pre_classifications: Optional[List[ClassificationResult]] = None` parameter. When supplied, the prompt renders a `CLASSIFIED SENTIMENT DATA` section (above the existing `MULTI-SOURCE SENTIMENT DATA` section) listing `title_hash + category + confidence + rationale` per headline; when None (the default, every existing caller's path), the prompt renders a placeholder text and is byte-identical to its pre-I.4.D shape. The verdict pipeline's existing path is unchanged. 9 integration tests pin the contract.
- `bc0a0a6`  env-flagged helpers: `_fetch_news_items_for_ticker(ticker)` and `_maybe_classify_news(ticker)`. The latter returns `None` when `ENABLE_NEWS_CLASSIFIER != '1'` (default), `[]` when the flag is on but the classifier is disabled / no items fetched / exception raised (fail-closed), or a list of `ClassificationResult` otherwise. Both helpers never raise. The verdict pipeline's failure modes are unchanged. 10 helper tests pin the contract.
- `557de73`  operator CLI: `python -m agent.tools.news_classify_cli --ticker TICKER | --input PATH [--dry-run] [--json] [--limit N]`. Runs without touching the verdict pipeline (lazy-imports `agent.fetch_news_items` only for `--ticker`); exits 0/1/2/3 with structured diagnostics. 21 CLI tests pin the contract.
- `099907d`  async-queue extension: `AsyncReviewQueue._Task` gains a frozen `pre_classifications: tuple = ()` field; `submit()` gains a `pre_classifications: Optional[List[ClassificationResult]] = None` kwarg; the worker inspects the reviewer's signature via `inspect.signature` and forwards the kwarg when supported, falling back to the original 3-arg shape when not (backwards-compatible with the existing lambda-reviewer test suite). The call sites at lines 1393/1599 of `agent.py` now compute `pre_classifications = _maybe_classify_news(ticker)` and forward it to both `queue_optional_ai_review` and the synchronous `analyze_with_minimax` fallback. **`ENABLE_NEWS_CLASSIFIER=1` now fires end-to-end through the momentum async path AND the synchronous fallback.** 6 async-queue tests pin the contract.

Net I.4.D slice delta: agent suite 213 → 259 (+46 across 5 commits: 36 module + 9 integration + 10 helper + 21 CLI + 6 async-queue). All defensive regressions clean: Python 380/380 PASS (no Python-engine changes); Node 394 pass / 4 skip / 0 fail (no Node changes); Client 40/40 PASS (no client changes); agent 259/259 PASS.

The I.4.D slice is the only plan-§13 explicit gap that previously had no implementation. With this slice, the I-series bounded-annotation surface is complete for `summarize` (I.2 + I.B) + `identify-missing-evidence` (conviction) + **`classify` (I.4.D)**. Remaining I.4 opportunities (E: periodic self-evaluation; G: per-ticker breakdown) are explicitly deferred per the I.4 deep-research doc and the plan-§13 contract (operator-supplied ground truth).

## Read order

0. **[2026-09-14-inheritance-i4d-handoff.md](2026-09-14-inheritance-i4d-handoff.md)** — the comprehensive handoff binder for the next session. Covers current state, what landed in this session, the user's repeated mantras (verbatim), senior-dev protocols, the vision, files NOT to touch, session-search anchors, and stopping criteria. **READ THIS FIRST.**
0a. **[2026-09-14-i4e-contract-health-done.md](2026-09-14-i4e-contract-health-done.md)** — the I.4.E bounded contract-health self-evaluation done-doc (the slice that closed "guard the guards"; 5 invariants + read-only CLI; agent suite grew 259 → 312).
0b. **[2026-09-14-j10-dedup-done.md](2026-09-14-j10-dedup-done.md)** — the J.10.DEDUP done-doc (capture-fingerprint dedup on the J.10 gate; the gate now counts unique observations per branch; duplicates surfaced for audit but do not inflate the verdict; python-engine narrow regression surface 364 → 404).
0c. **[2026-09-14-j10-freshness-done.md](2026-09-14-j10-freshness-done.md)** — the J.10.FRESHNESS done-doc (`--captures-since <DAYS>` filter + `captures_skipped_stale` report field; the gate now defends on three axes — bounded phase, unique observation, fresh evidence; python-engine narrow regression surface 404 → 434).
0d. **[2026-09-14-j10-min-threshold-done.md](2026-09-14-j10-min-threshold-done.md)** — the J.10.MIN_THRESHOLD done-doc (`--min-unique-per-branch <N>` threshold filter + `min_unique_per_branch` report field; the gate now defends on four axes; python-engine narrow regression surface 434 → 454).
0e. **[2026-09-14-j10-capture-summary-aggregate-done.md](2026-09-14-j10-capture-summary-aggregate-done.md)** — the J.10.CAPTURE_SUMMARY_AGGREGATE done-doc (per-day histogram + `captures_per_day` field + `## Captures per day` SUMMARY section; evidence velocity over time; python-engine narrow regression surface 454 → 474).
0f. **[2026-09-14-j10-write-atomic-done.md](2026-09-14-j10-write-atomic-done.md)** — the J.10.WRITE_ATOMIC done-doc (atomic + byte-identical JSON write for the gate's audit trail; mirrors the F5 `reconciliation_cli._write_output_atomic` discipline; python-engine narrow regression surface 474 → 487).
0g. **[2026-09-14-j10-capture-listing-done.md](2026-09-14-j10-capture-listing-done.md)** — the J.10.CAPTURE_LISTING done-doc (`--list-captures` CLI flag + `list_captures`/`format_listing` helpers + `i10-capture-listing-v1` schema; fast, side-effect-free audit tool; python-engine narrow regression surface 487 → 510).
0h. **[2026-09-14-j10-branch-histogram-done.md](2026-09-14-j10-branch-histogram-done.md)** — the J.10.BRANCH_HISTOGRAM done-doc (per-branch-per-day matrix + `branch_per_day` field + `## Captures per branch per day` SUMMARY section + `--show-branch-histogram` CLI flag; evidence density per branch per day; python-engine narrow regression surface 510 → 527).
0i. **[2026-09-14-i4e-cron-wiring-done.md](2026-09-14-i4e-cron-wiring-done.md)** — the I.4.E.CRON_WIRING done-doc (`contract_health_cron_tick` + hourly `schedule.every(1).hours.do` registration in `agent.py` + double try/except fire-and-forget guard + Telegram alert on violation; the I.4.E harness now self-policing; agent suite 312 → 325).
0j. **[2026-09-14-j10-summary-verify-done.md](2026-09-14-j10-summary-verify-done.md)** — the J.10.SUMMARY_VERIFY done-doc (`--verify-summary` CLI flag + `verify_summary`/`DiffKind`/`VerificationReport` helpers + byte-identical drift detection + `GENERATED_AT_DIFFER` (benign) vs `BYTES_DIFFER` (real) distinction + mutually-exclusive refusal with `--update-summary`; drift detection that never overwrites; J.10 surface 220 → 244).
0k. **[2026-09-14-j10-capture-oldest-newest-done.md](2026-09-14-j10-capture-oldest-newest-done.md)** — the J.10.CAPTURE_OLDEST_NEWEST done-doc (`oldest_newest_per_branch` + `format_recency_table` + `recency_by_branch` field + `## Captures recency per branch` SUMMARY section; per-branch timestamp range for stale-evidence + single-day-cluster + wide-span detection; first-occurrence-paths filter for dedup consistency; J.10 surface 244 → 272).
1. [SYSTEM_GUIDE.md](SYSTEM_GUIDE.md): feature architecture, authority boundaries, before/after improvements and limitations.
2. [SYSTEM_CODE_ATLAS.md](SYSTEM_CODE_ATLAS.md): 171 top-level engine/agent Python modules plus gateway/dashboard source navigation, declarations, dependencies and tables (September14 regeneration; +1 module after the I.4.D slice: `routes_market_session.py` was added in the J.7-HARDENING commit, then `agent/news_classifier.py` in `c80e3fa`).
3. [NEXT_AGENT_PLAN.md](NEXT_AGENT_PLAN.md): implementation workstreams, acceptance checks, expected effects and documentation ritual.
4. [September 12 replay progress](2026-09-12-full-policy-replay-progress.md) and [Production inventory/CAS findings](2026-09-12-production-evidence-and-cas-findings.md).

## What is being handed over

Dev branch: `codex/production-correction-hedge-p0`. This handover adds the final prior-book replay correction and documentation in one new commit; existing commits are preserved, not squashed. Identify the handover commit with `git log -1 --oneline` immediately after it is created, or search the log for `finalize replay and comprehensive system handover` later.

| Commit | Increment |
|---|---|
| `5a565df` | Full-policy inputs, capture and public-thesis replay foundations |
| `e043276` | Archived evidence validation and immutable diagnostics |
| `e4661d7` | Full-policy connector, independent lifecycle and execution risk limits |
| `0b13ed5` | Verified public capture loading |
| `d99ddd9` | Offline full-policy CLI and immutable report output |
| `273fdd4` | Candidate input preservation and capture isolation |
| `3f627cc` | Causal advisory clocks, durable collection coverage and scheduler warning correction |
| `e548d24` | Full-policy held-out integration and conflicting quote rejection |
| `760c086` | Predeclared criteria, source-bound stress economics and close-ordered drawdown |
| `e1c6687` | Master-proven public futures/roll scope and exact delayed-execution boundaries |
| Final handover commit | Fresh prior-book support, regressions, system guide/atlas/plan and AGENTS ritual |

These are Dev changes. This handover does not push, merge, rebuild or deploy them. No partner message or broker order was sent. Production files were not edited. Check remote tracking before pushing: earlier conversational assumptions about remote state may be stale.

## Validation performed for this wrap-up

Final combined rerun: **171 Python tests passed, with the two warnings described below**. Dashboard **23 tests passed**, production build passed, changed Python/generator compilation passed, documentation links resolved, atlas regenerated and diff whitespace checks passed. These are scoped engineering checks, not a Production green light.

131 Python tests passed in the combined research/orchestrator set. Reproduce from Dev `python-engine`:

```powershell
.\winvenv\Scripts\python.exe -m pytest tests/test_partner_full_policy_replay.py tests/test_partner_qualification.py tests/test_partner_qualification_review.py tests/test_partner_research_capture.py tests/test_research_cli_qualification.py tests/test_intraday_spread_signal_artifact.py tests/test_intraday_spread_research.py tests/test_intraday_spread_replay.py tests/test_intraday_spread_holdout.py tests/test_intraday_spread_chronological.py tests/test_intraday_spread_archive_adapter.py tests/test_partner_orchestrator.py -q
```

Dashboard: 23 tests passed with `npm run test:unit`; `npm run build` passed from `node-gateway/client`. Existing warnings: Starlette async-generator lifespan deprecation in Python and an outdated Browserslist database during the build. No dependency updates were made to remove these warnings.

Additional scheduling/isolation suite: 40 tests passed after correcting an outdated test fixture to call the real ledger migration and using explicit UTF-8 source reads. Production accounting code was not changed for these test fixes. Command: `python -m pytest tests/test_scheduler_real_path_isolation.py tests/test_scheduler_telemetry.py tests/test_scheduler_closures_invoke.py tests/test_fno_isolation.py tests/test_paper_ledger_isolation.py -q` in the same environment. This run also emits an unawaited-coroutine warning from the scheduler-closure test path at scheduler_setup.py:594; investigate the fixture/runtime distinction before claiming warning-free scheduler acceptance.

This is not a rerun of the entire repository test suite, gateway/native database suite, broker integration or a live session. Gateway/agent code was not modified by this wrap-up. Full release acceptance remains a task before Production promotion. A successful offline replay test does not prove historical sample sufficiency or profit.

## Current outstanding limits

- Production public input archives were absent at the last read-only inventory; no complete real session replay was produced from that root.
- Dev now implements `FROZEN_COMPLETED_BAR_CUTOFF_V1`: tick/cutoff, public and chain request/receipt, construction and dispatch boundaries are distinct. It is not deployed or observed in Production.
- Dev now retains per-attempt public/candidate outcomes, requested/received chain tokens and conditional-protection inputs, and bounds advisory wait on archive writes. Timeout remains outcome-unknown because an in-flight worker thread cannot be killed; Production latency and retention still need observation.
- Public capture hashes prove supplied-file integrity, not uninterrupted sampling or independent authenticity.
- Full-policy outcomes now enter held-out aggregation through a verified deployed-evaluator report, manifest and same-observation cost artifact. Ordered drawdown and exact declared stress gates are implemented. Real cost calibration, contemporary entry-quality checks and adequate real-session coverage remain unfinished.
- CAS/session-phase correctness needs official-source-backed review across engine, gateway and research.
- Negative earlier performance and accounting discrepancies need forensic/reconciliation work.
- No actionable partner strategy was qualified by this work. No fixed tip-start date can be given.

## First next action

F correction source `e00874b`; immediate eleven-file stat/status review confirms clean Dev, matching source/guide/atlas/plan and independent review incorporated. Local only, not pushed/deployed. Next implementation: genuine G/C predeclared comparison protocol and evidence validation; F forensic/account/statement inputs remain unresolved, not closed by this inventory correction.

Latest whole-engine receipt (F provenance/cache/budget source): `.\winvenv\Scripts\python.exe -m pytest tests -q --junitxml=C:/Users/Urveesh/AppData/Local/Temp/sentinel-fg-provenance-baseline-20260913.xml` from Dev engine returns0: **2,703 passed/four skipped/23 existing deprecations,126.20s**. Supersedes previous whole-engine counts. Runtime/assertions frozen; F explanatory test docstring alone edited during run. Independent F review finds no correctness blocker with existing route-import deprecation visible. Not qualification, real reconciliation, deployment or actual backup compatibility.

F source/provenance correction: unknown equity tariff effective date restored with rates/version/as-of/options untouched; owning schemas/PKs, writers, settings and unsupported A1–A5 closure claims corrected. Eight-file acceptance150 passed with all warnings fatal6.48s; ten-file154 passed7.07s with one existing Starlette deprecation and ResourceWarning/unraisable warnings fatal. Fresh DB fixtures exercise real initializers and broker import; not deployed-data reconciliation. Full engine rerun in progress; source frozen. Independent final review pending. See F/G correction plan; local only, no Production/remote mutation.

Approval-budget source commit `2cbe1a3`; immediate seven-file stat/status review confirms clean Dev and matching guide/atlas/plan. Independent final bridge review passes 65 tests with warnings fatal, no blocker. Local only, not pushed/deployed; required genuine evidence validation remains open.

Approval-budget/validity follow-up: twelve-file F/G suite **180 passed**, no warnings, 6.60s, current Dev winvenv with `-q -W error`. Required predeclared amount/DD/expiry, type/finite bounds, original half-open validity window, stale/legacy reads, exact expiry, whitespace signer and malformed historical signature regressions pass. No schema/default/order/transport changes. `approval_usable=False` remains explicit until genuine frozen held-out/account/F/D evidence is validated. Source commit pending; no push/deployment. Next: actual comparison/evidence validation and bounded F provenance/schema corrections, not a declaration of full G acceptance.

Exit-cache source commit `dd60b0c`; immediate seven-file commit/status review confirms clean Dev and matching documentation. Next correction is approval budget/evidence/expiry validation; F evidence corrections and faithful range comparison remain open. Local only, not pushed/deployed.

Exit-cache integrity follow-up: ten-file proactive/G suite **137 passed**, warnings fatal, 5.99s, current Dev winvenv. Retained v3 companion manifests bind full effective proposal/clock/cost/bar/evaluator identity; the result table retains its previous four columns and all legacy rows. Compatible concurrent retries remain idempotent; conflicting reuse fails. Old four-value writer shape tested on an isolated database, not actual deployed-data compatibility. No Production ops/remote promotion. See F/G correction plan for exact command and remaining approval/range/F evidence work.

Trailing-composition source commit `5bede72`; immediate seven-file stat/status review confirms clean Dev and matching guide/atlas/plan. Local only; no Production or remote promotion. Next implementation: separate exit-cache full proposal/clock/implementation identity, then remaining approval-validation and F evidence corrections.

Trailing-composition follow-up: root ten-file proactive/G command with `-q -W error` passes **121 tests**, no warnings, 5.53s; Terra independently approves causal entry/limit/confirmation/exit dispatch and retained primary-run immutability. Full current engine `.\winvenv\Scripts\python.exe -m pytest tests -q --junitxml=C:/Users/Urveesh/AppData/Local/Temp/sentinel-fg-trailing-baseline-20260913.xml` from Dev `python-engine` returns0: **2,656 passed/four skipped/23 existing Starlette-httpx deprecations**, 124.91s, source frozen during run. This supersedes earlier whole-engine counts and includes the parallel F/G changes plus current fixes; it does not validate unsupported strategy/governance claims. Exact scoped command and remaining exit-cache identity/bridge approval/range/F evidence gaps: `2026-09-13-fg-independent-correction-plan.md`.

Independent-review terminal-state source commit `13fb426`; immediate seven-file stat/status confirms clean Dev and matching documentation, local only. Remaining audit corrections are explicit in the F/G correction plan; terminal-state acceptance does not accept the entire governance bridge or strategy basket.

User-requested independent F/G audit found concrete bridge terminal-state and trailing-dispatch defects plus unsupported F provenance/schema/closure claims. First atomic bridge correction passes **81 tests** in the seven-file F/G group with `-q -W error`, 1.63s, Dev engine winvenv; six new regressions cover terminal amendment, reverse transition, concurrent first decisions and backdated append clocks. Full approval validation/trailing composition/F evidence corrections remain required; see `2026-09-13-fg-independent-correction-plan.md`. No live permission inferred.

Optional annotation validity source commit `59e915a`; immediate seven-file stat/status review confirms clean Dev and matching guide/atlas/plan, local only. Final focused Windows validity tests 14 passed with all warnings fatal in 1.14s.

I validity slice: `2026-09-13-optional-ai-validity-plan.md`; READY/CACHED no longer outlive original/shortened validity or cache TTL, exact-deadline results discarded, nested signal inputs snapshotted. Current isolated agent suite **98 passed**, warnings fatal, 2.10s: `docker run --rm --pull=never --network none --entrypoint python --mount type=bind,source=C:\Users\Urveesh\Desktop\trading-sentinel\agent,target=/app,readonly trading-sentinel-agent-test:latest -m pytest tests -q -p no:cacheprovider -W error`. No credentials/Production mounts, all helpers removed automatically. This is not complete I provenance/news usefulness. F/G are being independently audited at user request; do not overwrite the other agent's implementation.

Refreshed target/default review: [September 13 release target review](2026-09-13-release-target-review.md). Dev merge `7150ac7` non-destructively reconciles target `954e25a`; pre/post tree identical, clean status and target ancestor verified. The historical triple-dot inflation is resolved without source changes or force push. Docker/Compose/ledger migration code match the refreshed target. Partner delivery defaults are enabled in both versions: explicitly verify effective passive rollout switches, never claim disabled-by-default. Local only, not pushed/deployed.

Latest whole-engine receipt on Dev `0f3a2a0`: `.\winvenv\Scripts\python.exe -m pytest tests -q --junitxml=C:/Users/Urveesh/AppData/Local/Temp/sentinel-d-final-baseline-20260913.xml` from `python-engine`: **2,569 passed/four skipped/23 existing deprecations, 121.31s**, exit0. Supersedes earlier whole-engine count; not deployment or strategy qualification.

Review the complete Dev release diff/defaults and prepare the GitHub PR; resolve actual authorized quiescence/backup/restore and previous-code compatibility using the consistent-backup runbook. Production application containers were observed stopped, with no implicit restart; user was asked whether deliberate. C's boundaries and baseline/resource fixes are tested in Dev. Preserve the working CLI and immutable v1/v2/v3 artifacts; do not infer deployment or qualification.

## September 13 backup/rollback safety verification

Source commit `cd92830`; immediate post-commit stat/status review confirms the eight-file tool/runbook slice and clean Dev worktree. Local only, not pushed or deployed.

`2026-09-13-consistent-backup-plan.md` and `consistent-data-backup-runbook.md` define full-tree/WAL capture, explicit exclusive maintenance ownership, no operational deletion and rollback that preserves newer history. Offline `scripts/verify_data_backup.py` verifies exact retained inventory/hash and SQLite integrity in scratch, never claims live consistency. Root reviewed Terra's implementation and corrected directory-only iteration, source-enumeration bounds/errors, parent case aliases and weak/optional test setup. Independent Luna audit inventories stores/retention/migration hazards incorporated in runbook.

Final Windows command from `python-engine`: `.\winvenv\Scripts\python.exe -m pytest tests/test_data_backup_verification.py tests/test_deployment_verification.py tests/test_performance.py tests/test_partner_collection_attempts.py tests/test_research_leg_subscriptions.py tests/test_partner_research_capture.py -q -W error`: **117 passed, one symlink-privilege skip, no warnings**, 5.01s. Backup/deployment subset: 29 passed/one skip. WAL source connection remains open through capture; fixture byte snapshot confirms no source mutation and recovered ledger row. Missing WAL, matching corrupt SQLite, tampering, traversal/Windows aliases, hardlinks/devices, duplicate members/root, bounded expansion/enumeration, changing source/archive and receipt overwrite have negative tests. Receipt overwrite is not hidden by optional symlink skip.

Documented helper commands were checked with dummy data, cached Python3.11-slim and Alpine images, `--pull=never --network none`, no Production volume: inventory → Alpine `tar -C /source -cf /backup/data.tar .` → verifier all return exit0. Retained fixture/receipt: `C:/Users/Urveesh/AppData/Local/Temp/sentinel-d-backup-native-20260913`. This proves CLI/native-tar compatibility, not an actual Production restore. The existing engine image lacks pytest; no dependencies were installed into it, and native command smoke replaced that unavailable cross-platform test environment. Atlas regeneration unchanged at 155 modules, compilation and diff check pass.

Read-only Docker snapshot: actual `/data` volume `production_trading-sentinel_trading_data`; engine/gateway RW, agent RO; all three stopped exit137, OOMKilled=false around 01:01 UTC. Autoheal/nginx/ngrok run. No root stop/restart or Production edit occurred. This state is not a quiescence/maintenance receipt. Actual backup, isolated restore on actual data, old/new complete compatibility, PR/release and real market-session evidence remain outstanding.

## September 13 resource ownership verification

Source commit `93ce675`; post-commit behavior/documentation consistency checked with clean Dev status. Local only, not pushed/deployed.

`2026-09-13-resource-clean-release-plan.md`: native Node 20 Alpine gateway `./node_modules/.bin/jest --runInBand --detectOpenHandles` passes **324 tests/four skipped** (25 suites passed/one skipped) in 16.927s and returns exit 0 naturally, with no detected open handles. Networking was disconnected after npm ci; current Dev source was recopied before acceptance. Focused token/dead-letter tests: 15 passed, natural exit. Original-code negative controls: fetch-rejection cleanup fails with one remaining timer; stalled-body regression fails by timeout. Neither working source nor Production was reverted for these controls; only a scratch container copy was replaced. Logs retained in the user Temp directory as `sentinel-d-resource-gateway-20260913.log`, `sentinel-d-timer-negative-20260913.log`, and `sentinel-d-body-negative-20260913.log`. Scratch container and original-source temp helper were removed; no operational volume was attached/deleted.

Python: Terra isolates `test_option_lookup`'s manual loop; root converts it to pytest-managed async. Original four-file instrument/scanner/full-policy/multisession command with `-W error`: **32 passed**, no warnings, 3.41s. Broader 15-file research/qualification/archive/orchestrator group with `-W error::ResourceWarning -W error::pytest.PytestUnraisableExceptionWarning`: **181 passed**, one existing Starlette deprecation, 7.83s. No warning suppression or global loop fixture added. Earlier full Python baseline remains 2,545 passed/three skips; only the equivalent test loop changes after that whole-suite run. Changed JS syntax checks/Python compilation, atlas regeneration (unchanged 155 modules) and diff check pass. This is TESTED_DEV; D release/real evidence still incomplete.

## September 13 D acceptance baseline

Implementation commit `f7e33cb` restores the full acceptance baseline. Post-commit source/docs diff and clean Dev status were checked. Atlas regeneration remains identical at 155 modules. This is local Dev only, not pushed/released.

Plan/evidence: `2026-09-13-release-baseline-plan.md`. Full Dev engine command: `.\winvenv\Scripts\python.exe -m pytest tests -q --junitxml=C:/Users/Urveesh/AppData/Local/Temp/sentinel-d-baseline-20260913.xml` from `python-engine`: **2,545 passed, three skipped, 23 existing Starlette/httpx deprecations in 126.27 seconds**. This supersedes the earlier 17-failure baseline. No tests were excluded or marked xfail to hide failures.

The corrected fixture/source-guard/default group passes 148 tests (one skip, one existing Starlette warning). Migration regression preserves legacy rows, exercises repeat initialization and retains new close provenance. Momentum's helper mirrors the migrated column because both sync and async tests call it; division/audit fixtures call the real migration. Scheduler/isolation passes 41 tests with RuntimeWarning fatal (one existing Starlette deprecation). Dashboard passes 25 unit tests and Vite build (existing Browserslist warning); agent passes 91 tests in the existing test image with networking disabled and current Dev source mounted read-only. Runtime accounting, flags, clocks and transport authority did not change.

Gateway: **318 passed/four skipped** (25 suites passed/one skipped), 17.739 seconds, temporary Node 20 Alpine native-SQLite environment. Dependency installation uses no repository `.env` or persistent volumes; the acceptance rerun disconnects networking after installation. The existing script uses forceExit and detects two open handles: token-restore timer on fetch rejection and fake-token Telegram polling in alert-dead-letter tests. Log: `C:/Users/Urveesh/AppData/Local/Temp/sentinel-d-gateway-20260913.log`. The temporary container was removed after preserving its log, with no operational volumes involved. No actual partner message or broker order was requested or submitted. The Windows combined all-warning-fatal socket investigation is still pending. No Production edits, push, merge or deployment occurred.

## A/B implementation verification

- Focused Python acceptance: 185 tests passed across decision clocks, collection attempts, chain/scanner, captures, qualification/replay, orchestrator, archive readiness and authenticated hedge routes. The 64 pure-path tests passed with all warnings treated as errors; the integration group retains one pre-existing Starlette lifespan deprecation warning.
- Scheduler/isolation acceptance: 41 tests passed with `RuntimeWarning` treated as an error. The previously documented unawaited `_run_penny_edge_scan_safe` coroutine warning is fixed; registration now checks for a running event loop before constructing the coroutine.
- Dashboard: 25 unit tests passed and the Vite production build passed. The existing outdated Browserslist database warning remains.
- Gateway: all 317 tests passed (4 skipped) in a clean Node 20 Alpine container; the focused updated proxy contract passed 15 tests. Existing forced-exit/open-handle and Telegram-library warnings remain. Agent: 91 tests passed in the existing Production agent image with networking disabled.
- Latest full Python repository rerun after the hardened C economics slice: 2,514 passed, 3 skipped and the same 17 failures, with 23 deprecation warnings and no unawaited-coroutine warning. The failures were outside the changed path: legacy test-created `bankroll_ledger` schemas omit `origin_ref`; the declared `PARTNER_BOT_ENABLED` default is already `True` while an older test expects `False`; several Windows source-inspection tests use CP1252 instead of UTF-8; and affected momentum-paper assertions cascade from the legacy ledger fixture. The 17 failures still prevent `RELEASE_VALIDATED` status even though the focused slices are green.
- Production remained read-only. No container was started, no message/order was sent, and no qualification was registered.

## C replay-fidelity verification

- Source/execution-boundary acceptance: v3 futures scope is independently proven against raw/canonical dated master evidence, including the complete front/roll expiry selection. Legacy/caller-supplied inputs cannot claim verified held-out provenance. The unmocked multi-session fixture now uses retained public captures rather than caller price dictionaries.
- Exact entry/management instants, excluded same-day option expiry, fill-timestamp embedded cancellation, delayed public-age checks, liquidity/quantity/cost-inclusive reward gates, unrelated archive packets and nonnegative gross-notional slippage have focused regressions. Missing, partial and late exits preserve unresolved exposure. Finalized quote segments require manifest integrity.
- The expanded focused group passes 143 tests, including rejection of decision bars not bound to a supplied capture and a forged scope that omits the actual front future. The final broad C/research/orchestrator group passes 185 tests. The combined warning-fatal run exposes an unclosed Windows asyncio socket during test-group transitions; isolated full-policy/multisession warning-fatal acceptance passes 15 tests. This warning is not silently suppressed and requires baseline investigation in D. Follow-up subagent review attempts failed on account usage limits; the earlier read-only findings were incorporated and locally checked.
- Source-final repository comparison: 2,526 passed, 3 skipped, the same 17 documented failures and 23 warnings in 122.40 seconds. The final additional decision-frame negative test passes in the 143/185-test groups. This is no new source-path regression, not release validation; the baseline failures and remaining gateway/dashboard/agent acceptance must be addressed in D.

- The unmocked two-session fixture uses the real deployed evaluator, verified raw/canonical contract master, hashed raw quote packets, archive adapter, chronological replay and held-out aggregator. It produces one finite costed close and one unresolved accepted entry; neither result can grant qualification, delivery or order authority.
- Distinct valid same-leg packets at one receipt are now explicit conflicts independent of input order. Exact duplicate retries remain idempotent, and a relevant conflict produces `decision_book_conflict` rather than a conveniently selected book.
- Verified full-policy reports can enter held-out review through a strict adapter. Report/manifest tampering, simplified evaluators, conflicting states and malformed identities are rejected.
- Changed C acceptance: 28 tests passed warning-free. The broader full-policy/research/qualification/archive/orchestrator group passed 139 tests with one pre-existing Starlette async-generator lifespan deprecation warning.
- Full-policy reports now always retain a fingerprinted baseline plus caller-declared fee/slippage scenarios calculated from identical observations. Held-out aggregation revalidates full nested artifacts/source identities, sorts realised outcomes by timezone-aware close clocks, retains individual economics and computes sequential drawdown. Qualification review requires a policy/profile-bound immutable criteria manifest frozen before holdout, exact stress coordinates, unique outcome identities and matching non-closed states; legacy evidence remains readable but receives blockers. After independent invariant/test audits, the expanded focused group passes 61 tests warning-free and the broader group passes 151 tests with the same Starlette warning.

## User-facing clarity

The system is better at preserving and testing what it actually observed and proposed. It is less likely to manufacture a historical fill or hide a missing exit in research. Those are prerequisites for finding a real edge, not proof that an edge has been found. The partner's saved intraday profile is a setup input, while qualification and Telegram delivery are separate checks.

## Commit ritual

Before the next implementation: update the plan slice. With each commit: update the guide/atlas/plan and verification evidence. After each commit: verify the actual diff and documentation agree. Instructions are also in Dev AGENTS.md so the ritual survives this conversation.

## September 20 AI/readiness deployment checklist

- [x] Production inspected read-only; no Production source/config/database edit.
- [x] Confirm MiniMax, Telegram bot and partner chat credentials are present
  without printing their values.
- [x] Explain 0/7 from persistent evidence: no gate rows, no advanced shadow
  evaluations, no reconciled partner positions; only 2026-09-17 produced manual
  advisory ideas.
- [x] Render Dev Compose and confirm AI flags on, safe AI policies selected,
  manual advisory on, advanced shadow on, advanced delivery off.
- [x] Add idempotent, genuine-input-only system staging receipt.
- [x] Correct E.1 diagnostic schema drift and the false coupling between
  advanced hedge 0/7 and manual-advisory dispatch.
- [x] E.1 diagnostic suite: 27 passed with warnings fatal, 1.37 seconds.
- [x] Full Python engine rerun: 4,122 passed, four skipped, 46 existing
  deprecation warnings, 218.99 seconds. A first run exposed a test-only
  microsecond future-clock race in two F&O quote fixtures; binding the fixture
  quote to the test's declared `now` made the acceptance deterministic without
  changing runtime valuation behavior.
- [x] Agent image suite: 357 passed, 3.82 seconds, network disabled.
- [x] Agent enabled-flag import smoke confirms async review/usefulness true and
  proceed/advisory policies. Python-engine Compose run confirms manual advice,
  hedge parent and shadow flags true with Phase-2/3 live delivery false.
- [x] Dev `agent` and `python-engine` images build successfully. The Python
  Dockerfile retains one existing `FromAsCasing` warning.
- [x] Focused readiness/Phase-2/Phase-3 suite: 59 passed, one existing Starlette
  deprecation warning, 4.39 seconds.
- [x] Implementation/docs commit `1a6e0d9` pushed to
  `origin/codex/production-correction-hedge-p0`. The task diff is committed;
  two pre-existing unstaged generated session-fixture timestamp changes remain
  intentionally untouched.
- [ ] Merge/deploy through GitHub; recreate affected services and verify release
  identity. Never copy or edit Production directly.
- [ ] Confirm `agent`, `node-gateway`, `python-engine`, nginx and autoheal are
  healthy. Current read-only observation has the three application containers
  stopped (exit 137, not OOM-killed) and nginx restarting.
- [ ] During a logged-in trading session, confirm optional-AI status receipts,
  partner input state, advanced shadow evaluations and one staging receipt only
  when a fresh reconciled position and chain were genuinely processed.
- [ ] Record manual live-chain/sample-review evidence separately; do not infer
  it from uptime or automatically enable Phase-2/3 delivery.

## 2026-09-20 exact release-range receipt

- [x] `--base-ref` drives exact `base..HEAD` commit selection rather than only
  changing the rendered label.
- [x] Both endpoints are captured as SHAs; requested/resolved ranges and ahead
  count are visible in the generated notes.
- [x] Invalid or uninspectable bases exit 2 without emitting or writing notes.
- [x] No-base diagnostic behavior remains capped at the latest 30 commits.
- [x] 31 warning-fatal release-note tests pass, including 31 post-base commits
  and the valid base-equals-HEAD case.
- [x] A live Dev generation against `origin/evolve/smart-strategies` matched
  `git rev-list --count` at 31 commits before this correction was committed.
- [x] Release handoff generated from source head `2766b00`: resolved range and
  count include the correction (32 commits). Its final docs-only commit is
  intentionally identified for one last regeneration before PR creation.
- [ ] Reviewer still owns PR approval/merge, backup/restore and deployment.
- [x] Production remained read-only and untouched.
- [x] Broker-statement text output is cp1252-safe (`INR`); reconciliation
  amounts, statuses and exit codes are unchanged.
- [x] Complete scripts suite: 225 passed with warnings fatal (20.63 seconds).

## 2026-09-20 deterministic session-golden receipt

- [x] Unchanged 2,355-vector payload preserves `generated_at_utc` and is
  byte-identical across consecutive generations.
- [x] Semantic payload changes cannot reuse the prior provenance timestamp.
- [x] Python and Node copies are written from one canonical newline-terminated
  UTF-8 string; already-matching files are not rewritten.
- [x] Python focused suite: 7 passed with warnings fatal (1.95 seconds),
  including raw-byte CRLF normalization on Windows.
- [x] Node session mirror: 43 passed with natural exit (1.56 seconds); one
  expected offline holiday-fetch warning was logged.
- [x] Existing timestamp-only local fixture changes remain unstaged. Production
  was not read from, written to or restarted.
