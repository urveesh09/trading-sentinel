## October 27 — O27f genome round 3: new entry families, option-contract genes, a walk-forward of the search itself and a random-entry null (done, Dev, freeze `3b8f9ef`, results and panel B freeze `0b529f2`, not pushed)

- Owner ask (Oct 27, 21:30, after reading O27e): "if you have learnt anything from that then go ahead and try new combinations or new things … assess the results if they were better … test new strategies".
- **Study:** `docs/research/fno/2026-10-27-genome-round3/` (`lab.py`, `test_lab.py`, `freeze.json`, `analyze.py`, `results.json`, `README.md`). Freeze `3b8f9ef` was committed before scoring.
- **What ran:**
  - 2,217 full replays through the shipped single-leg book. The run-time parity gate passed (13 trades, ₹10,801.09).
  - Five new entry families (TREND_PULLBACK, PDL_BREAK, VWAP_BAND, MOMO_BURST, ENSEMBLE) and new genes (SENSEX confirmation, multi-day trend, AM/PM, VWAP-lost exit, delta 0.55/0.65, nearest/next expiry), with cross-family crossover.
  - An anchored walk-forward of the whole search (F1/F2/F3 test blocks, 16 sessions).
  - A random-entry NULL family with the same budget.
- **Verdict (frozen rule): the search fails.**
  - Over the 16 test sessions, the REAL walk-forward made +₹1,011 on 6 trades (1 of 3 folds positive).
  - NULL made +₹3,682 on 9; SHIPPED made +₹9,528 on 4.
  - Keep the shipped book.
- **Learning:**
  - Past rank does not predict future rank: A against B Spearman −0.23; week to week +0.08.
  - Random entries with good exits made money (66% of NULL genomes were positive; the best made +₹28,265).
  - The let-winners-run exit genes (3R, LOOSE, holding trend days) are the most stable.
  - Delta 0.65 and next-week expiry mostly lose trades to the risk cap; filters mostly remove trades.
  - Evolution barely improved on the first random draw.
  - The fitness favoured sparse traders.
- **Most consistent on seen data:** TREND_PULLBACK (FINAL pick). 14 trades, +₹17,347, max DD ₹3,418, 8 green / 1 red days, 6 / 0 weeks, all 23 neighbours profitable, direction-flip −₹11,761. It is a forward-test candidate only.
- **O27g forward panel B:** `docs/research/fno/2026-10-28-forward-panel-b/` (`panel_b.py`, `test_panel_b.py` with 3 passing tests, `freeze.json`, `README.md`). It was frozen before Oct 28. Arms:
  - SHIPPED;
  - O27F_TREND_PULLBACK;
  - O27F_ENSEMBLE_EFF_MOMO;
  - O27E_EFFICIENCY_BREAK;
  - NULL_CONTROL.

  It uses panel A's rule, and a candidate must also beat the random-entry control. A pinned copy is called by panel A's 16:00 launcher.
- Tests: 7 lab tests and 3 panel B tests passed. No runtime, setting, paper, live or panel A change; nothing is promoted.
- Remaining:
  - the owner registers the 16:00 task (panel A's `register_task.ps1`, which covers both panels);
  - read both reports weekly;
  - decide after Nov 27;
  - a future search needs a per-trade or frequency-aware fitness.

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

# Trading Sentinel — next-agent execution plan

## October 27 — O27d The F&O strategy testing playbook: how the Oct 27 tests ran, where the Production data comes from, every strategy tried, how another agent tests their own, and the daily forward test (done, Dev, commit `ed3b9fa`, not pushed)

- Owner ask (Oct 27, 20:20): "create a comprehensive documentation as to how did you run the test … where did you access the data for production … so that … another agent … can also do it. What all strategies have been used … everything about the daily recurring test".
- Files:
  - `docs/FNO_STRATEGY_TESTING_PLAYBOOK.md` (new);
  - `docs/research/fno/2026-10-27-consistency-grid/reference-scripts/` (the exploration and analysis scripts with a README; seen data, not evidence);
  - `docs/RESEARCH_TESTING_METHOD.md` (pointer, and the F&O window ledger row updated: everything to Oct 26 seen for entries and exits; Oct 28 – Nov 27 held by the forward panel).
- No code, setting or runtime change. Tests: not applicable (documentation only).
- Remaining: as O27c; the owner registers the 16:00 task.

## October 27 — O27c Forward panel: the best O27/O27b candidates replayed beside the shipped book on every new session, Oct 28 – Nov 27, from a pinned copy run daily (done, Dev, commit `e6af14b`, branch `codex/production-correction-hedge-p0`, not pushed)

- Owner ask (Oct 27, 20:00): "integrate the best and then let's do this run tomorrow and ahead to test this in upcoming month".
- Decision:
  - Integrated as a forward test, not into the paper or live book. No candidate passed a held-out check.
  - The proving week (Oct 26–30) freezes the paper single-leg rules, and the Nov 2–6 real-money test mirrors the paper book.
- Panel (frozen in `docs/research/fno/2026-10-28-forward-panel/freeze.json` before Oct 28 existed):
  - control: SHIPPED;
  - evolution: EVO_PLATEAU_1, EVO_BEST_FITNESS and EVO_OR20_LET_RUN;
  - O27: O27_PICK and O27_OR20_NOEMA.
- Rule: promising = forward trades ≥ 5, net > 0, net without the best day > 0, net > SHIPPED, DD ≤ max(1.5 × SHIPPED, ₹5,000). Read on Nov 27; interim reports are provisional.
- Files:
  - `scripts/run_fno_forward_panel.py` (freeze/run: read-only export, replay, REPORT.md, latest.json, history.jsonl);
  - `tests/test_fno_forward_panel.py` (provenance of every arm, rule, run outputs);
  - the study README; atlas.
- Daily operation:
  - A byte-for-byte pinned copy of this commit's files sits in `C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\`. Byte copies are used because Git converts line endings and the run checks source hashes.
  - A Windows scheduled task, "Sentinel F&O forward panel", runs it at 16:00 IST Monday to Friday (StartWhenAvailable). The owner moved it from 06:30 on Oct 27 evening because the PC is usually off then. The export now includes the day's own finished session (`--include-finished-today`, from 15:50 IST; the quote collector's last tick is 15:40).
  - Reports land in that copy's `docs\research\fno\2026-10-28-forward-panel\_local\REPORT.md`.
  - Status: re-pinned for 16:00 by commit `3dc3342`; the pinned copy was rebuilt from it on Oct 27 at 20:20 IST (source and FNO settings hashes equal the freeze; `run_panel.cmd` ran end to end: export, 0 forward sessions, report, exit 0). The 16:00 IST Monday–Friday task is NOT registered yet: the agent's registration was refused by the permission check (persistence). The owner runs `register_task.ps1` from the pinned folder, or the agent runs `run_panel.cmd` on request.
- Tests: `tests/test_fno_forward_panel.py` (new, 3) with the evolution, grid, shadow and replay suites: 41 passed (2 existing third-party deprecation warnings), 36 s. Tests do not show profitability.
- Config impact: none in Dev or Production. Production is only read, via a read-only throwaway container at 16:00 IST, after the 15:40 close.
- Rollback: `Unregister-ScheduledTask -TaskName "Sentinel F&O forward panel"`, then delete the pinned folder.
- 16:00 change:
  - `scripts/export_fno_replay_dataset.py` gained `--include-finished-today` (`FINISHED_AFTER_IST_MIN` 15:50); without the flag its behavior is unchanged.
  - The panel passes the flag.
  - The panel was re-frozen before any forward session (first freeze `e6af14b`). Tests: `test_fno_forward_panel.py` (5, two new), `test_oct18_sim_fidelity.py`, evolution and grid suites: 22 passed (27 s).
- Remaining:
  - Read the report weekly and decide on Nov 27.
  - Fix the load-sensitive scheduler test.

## October 27 — O27b The F&O evolution round: 17-gene genomes bred from the O27 grid's good arms plus literature genes, evolved on window A only, finalists checked once on B (done, Dev, freeze `3f97f2c`, results commit `080330d`, branch `codex/production-correction-hedge-p0`, not pushed)

- Owner ask (Oct 27, evening): "do something like how the human gene works … see which parameters … on the winning days were working … make a good combination … add a little bit of more new thing … search the web for some parameters that you are not using … the combinations that did the worst … you do not even consider". The owner allowed stopping Production for RAM; not needed (6 cores are the limit; Production idles under 1% CPU).
- Descriptive look at what the winning days had in common (window A only, 43 distinct grid entries):
  - A few afternoon trend-day breakdowns, in the gap's direction, made most of the money.
  - Breaks against the opening range's own drift did better.
  - Going with the gap was better; a narrower range than usual was mildly better; a previous-session NR4 was worse.
  - VWAP side never differed.
- Plan (frozen in `docs/research/fno/2026-10-27-evolution/freeze.json` before scoring):
  - 13 entry genes and 4 exit genes; seeds from the 31 eligible O27 arms (30-minute time stop and continuation dropped).
  - Population 40, 10 generations, tournament 3, uniform crossover, 12% one-step mutation, 4 elites, 4 immigrants, seed 20261027.
  - Fitness on A: (net − best day) ÷ max(DD, ₹1,000) − 0.5 per losing half; fewer than 8 trades is infeasible.
  - 5 finalists ranked by the median fitness of the genome and its one-step neighbours.
  - B check: ≥ 3 trades, net ≥ 0, DD ≤ max(1.5 × shipped, ₹5,000); "B without Oct 21/23/26" shown for information.
  - The shipped genome must equal CURRENT on A.
- Files and contracts:
  - `python-engine/fno_shadow.py`: the research genes on `FnoShadowVariant`, all defaulting to the base behavior:
    - `ema_spans`, `buffer_atr`, `stretch_buffer`, `min_rvol`;
    - `vwap_side`, `or_bias` (with/against), `gap_align`;
    - `max_or_width_ratio`, `narrow_prior_days`, `latest_entry_min`;
    - `stop_atr_mult`, `target_r`.
  - New helpers in `fno_shadow.py`: `_prior_sessions` (cached per frame window) and `_gene_reject`.
  - `scripts/run_fno_evolution.py`: freeze/run, the GA, plateau, holdout, allele effects.
  - Tests: `tests/test_fno_evolution.py` (new), and one gene test in `test_fno_shadow.py`.
- Tests: focused `tests/test_fno_evolution.py tests/test_fno_consistency_grid.py tests/test_fno_shadow.py tests/test_fno_policy_replay.py tests/test_preregistered_study_runner.py tests/test_fno_orchestrator.py`: 73 passed (2 existing third-party deprecation warnings), 39 s; the full suite runs before the results commit. Tests do not show profitability.
- Config impact: none. No live shadow sets a gene, and no setting, table, paper or live rule changes. Proving week untouched.
- Rollout: research only. A pass becomes, on the owner's word, a forward-only replay from Oct 28. Rollback: revert (no runtime caller sets a gene).
- [x] Run Oct 27, 18:42–19:40 IST (10 workers; Production left up): 400 bred plus 117 neighbour evaluations. Parity held.
  - Verdict: `NONE_PASSED_KEEP_SHIPPED`.
  - The finalists (EMA 21/50 kept; OR20/OR30, width ≤ 1.25×, lock off/late, T75, trail 1.5) earned +₹15k to +₹21k on A, against the shipped +₹7,286. On B every one made 0–1 trades: the EMA check refused the late-October trends, so all failed "≥ 3 trades".
  - Allele lessons: first confirmation, NR4/NR7, tight range caps, a 12:00 cutoff, stretch, RVOL 1.5 and both opening-range bias filters mostly killed trading. The shipped RVOL, target, stop, buffer and cutoff sit at or near the best alleles.
  - Genes interact: "let it run" exits on the shipped entry lowered A to +₹2,917.
- Remaining (owner's call):
  - A forward-only panel from Oct 28: shipped, evolved finalist 1, and `OR20_NOEMA|LOCK_LATE|T75|TR1.5`. Dev replay after each sealed session; no Production change.
  - The load-sensitive scheduler test (see the handover).

## October 27 — O27 The F&O consistency grid: 360 entry × exit combinations of the single-leg book, ranked for consistency, frozen before scoring (done, Dev, freeze `d4cfb7e`, results commit `32f4271`, branch `codex/production-correction-hedge-p0`, not pushed)

- Owner ask (Oct 27, after the close): "test multiple strategies mix and match … I don't want the most earning one. I want the one that is most consistent", using the archived F&O days. Earlier the same day: make the book able to take small profits instead of only filtering.
- Problem:
  - The single-leg book made one trade in six sessions (Oct 19–26).
  - On Oct 21, 23 and 26 the shipped break fired on the right bar. The lagging multi-day EMA(21/50) check rejected it, and "fresh break only" then lost the whole trend day.
  - Quick-scalp designs explored on seen data: 12 single-leg designs all lost after charges (−₹427 to −₹8,932). Of 6 spread versions, one made +₹962 over 22 trades (noise). Scratchpad only, not part of the frozen grid.
- Plan (frozen in `docs/research/fno/2026-10-27-consistency-grid/freeze.json` before any arm was scored):
  - 10 entries (OR30 shipped, OR20, OR45, CONFIRM1, CONT, each with and without the EMA check) × 36 exits (lock TIGHT/LIVE/LATE/OFF × time stop 30/45/75 × trail 0.6/1.0/1.5) = 360 arms, plus a parity arm.
  - The full live book is replayed for each arm over 29 sealed sessions (Sep 10 – Oct 26).
  - Ranking uses the median consistency score of the arm and its one-step exit neighbours on A (Sep 10 – Oct 9), then a do-no-harm check on B (Oct 12 – Oct 26).
  - Rule and caveats are in the study README. All data is seen; B is partly circular for the no-EMA arms.
- Files and contracts:
  - `python-engine/fno_shadow.py`: `FnoShadowVariant.ema_filter` (default True; the live shadows are unchanged).
  - `python-engine/fno_policy_replay.py`: `ReplayPolicy.signal_variant` takes a name or a variant object; `run_replay(policy=str | ReplayPolicy, data=None)`.
  - `scripts/run_fno_consistency_grid.py`: freeze/run, a per-session parse cache under `_local/`, the frozen rule.
  - Tests: `tests/test_fno_consistency_grid.py` (new), plus one each in `test_fno_shadow.py` and `test_fno_policy_replay.py`.
- Acceptance:
  - The parity arm trades exactly as CURRENT.
  - `run` refuses changed inputs and scores each arm once.
  - Results are reported with A/B/full-window figures, CURRENT's rank and the contamination caveat.
- Tests: focused suites `tests/test_fno_consistency_grid.py tests/test_fno_shadow.py tests/test_fno_policy_replay.py tests/test_preregistered_study_runner.py`: 35 passed (2 existing third-party deprecation warnings), 23 s; the full suite runs before the results commit. Tests do not show profitability.
- Config impact: none. No setting, table, live shadow, paper or live rule changes. Proving-week rules untouched.
- Rollout: research only; nothing to deploy. A recommendation becomes, on the owner's word, a broker-free live shadow plus a nightly replay forward from Oct 28. Rollback: revert the commit (no runtime caller).
- [x] Grid run Oct 27, 16:39–17:37 IST (6 workers, Production left running); results are in the study README and `results.json`.
  - Parity held.
  - Verdict under the frozen rule: `SHADOW_CANDIDATE`, `OR20|LOCK_LATE|T75|TR1.5`.
    - All windows: 11 trades, +₹12,916, max DD ₹2,877.
    - It made **0 trades in B** (Oct 12–26), so its check tested nothing. The rule's gap (zero trades pass "net ≥ 0") was found after scoring; it is reported, not repaired.
  - CURRENT ranks 27th of the 32 eligible arms (83rd percentile of all 360 on full-window CS).
  - Post hoc, if at least one B trade had been required: `OR20_NOEMA|LOCK_LATE|T75|TR1.5` (all windows: 19 trades, +₹30,567, DD ₹3,423). Its B trades fall on the days that motivated the idea.
  - Robust across arms:
    - The 20-minute range is the most robust entry family.
    - A 30-minute time stop is worst.
    - Lock and trail settings barely matter.
    - CONT with the EMA check loses (1 of 36 exits profitable).
    - The EMA check depends on the regime: removing it raised net in only 1–4 of 36 exits on A but in 36/36 on B.
    - No arm earns daily.
  - 32 no-EMA arms hold one Oct 21 put that cannot be priced (deeper in the money than the archived strikes).
- Remaining (owner's call):
  - Forward-only evidence: re-export after each sealed session and replay the frozen pick, the post-hoc no-EMA arm and CURRENT on sessions from Oct 28. No Production change; proving-week and Nov 2 plans untouched.
  - A smarter, regime-aware trend check is a new hypothesis, to be frozen before forward scoring.
  - Decide after about 10 forward sessions.

## October 26 — O26e The O26d recheck's two gaps fixed: each research trade resolved under its own saved execution, minute bars used only when they are the whole session (done, Dev, commit `1d99c12`, branch `codex/production-correction-hedge-p0`, pushed, deployed by PR #119 (`3b945eb`, Oct 26))

- Owner ask (Oct 26, 21:00): the recheck (`docs/2026-10-26-o26d-independent-recheck.md`, committed with this slice): "Fix if you think it's an issue … Merge and deploy in prod and rebuild and restart. The 22 let it be". Both findings were agreed.
- [x] **F1 (P2): per-trade execution in the terminal pass.**
  - `momentum_shadow.resolve_momentum_shadow_day` reads each open trade's `execution_json`. `_terminal_bars` gives each trade its own bars: up to its declared time exit; the derived 15:15 bar only when that execution declares `cas_time_exit` and the dated evidence holds.
  - A legacy trade with no model stays censored, `no_terminal_bar:cas_no_model`; a rerun changes nothing.
  - `cas_time_exit_evidence` is NO_MODEL unless the declared exit is 15:15.
  - `_exit_for_bar` takes the trade's own saved slippage and time exit, as its costs already were. All stored records declare 15:15 and 5 bps, so their results do not change.
- [x] **F2 (P2): minute-path completeness.**
  - `position_tracker.minute_path` returns `(path, coverage)`. The whole session must be there, entry day included, checked before the entry-day cut:
    - one date (and the entry's date);
    - coherent finite bars, with no conflicting duplicate minute;
    - the first bar at or before 09:16 and the last at or after 15:25;
    - at most 5 minutes between bars;
    - the day's own high and low within 0.1%.
  - Otherwise the stop-first or entry-day daily result stands, and `coverage` names the reason (`LATE_START`, `GAP_61M` …).
  - A gap is not taken as a quiet stretch: Kite leaves out minutes without trades, but nothing tells that apart from a provider loss. Production's cache holds only partial minute windows, so there was no data to calibrate a volume check.
  - A closing-auction stock (no continuous trading after 15:15) never qualifies.
  - `DAY_EXITS_RULE` = `day_exits_v2_minute_path_complete` is in every result and log line. The research mirror is `penny_cnc_connors_lifecycle_v3` and declares the rule. `usable_minutes` remains as a wrapper.
- The reviewer's recheck scenarios on this code: the six corrected cases still pass, and the two defect reproductions now fail.
- Files:
  - `python-engine/momentum_shadow.py`, `position_tracker.py`, `research_penny_cnc_lifecycle.py`.
  - Tests: `test_oct21_audit_fixes.py` (+2), `test_research_penny_cnc_lifecycle.py` (+12 cases).
  - `docs/SYSTEM_CODE_ATLAS.md`; the recheck document.
- Tests: full suite 6,123 passed, 1 failed, 4 skipped (11 min 26 s). The failure was a second queue-order test in `test_s5_provider_lanes.py` with the same Windows-clock assumption. All five queue-order tests now run at `QUEUE_RATE` 20/s; the file then passed 3 of 3 alone and 12 of 12 run four at a time. No engine code changed after the full run. Focused: tracker and mirror 52, shadow 25. The reviewer's recheck scenarios: 6 passed, and the 2 defect reproductions now fail. Tests do not show profitability.
- Config impact: no setting, no table. Paper tracker: minute bars are used on fewer days (more stop-first results).
- Rollout: PR #119 to `evolve/smart-strategies` with O26–O26e, merged and deployed on the owner's instruction (receipt below). Rollback: the previous images tagged `sentinel-rollback/<service>:f9547c5-20261026`; the additive `partner_watch_trips` table stays.
- **Rollout receipt (done Oct 26, 21:35–21:44 IST):**
  - PR #119 merged as a merge commit, `3b945eb` on `evolve/smart-strategies`, carrying O26 to O26e (`f9547c5` kept; the release branch had no commit of its own beyond its merges).
  - Backups, outside the repositories, in `C:\Users\Urveesh\sentinel-operations\production-rollout-20261026-o26\`:
    - 8 SQLite databases as single-step online snapshots from a read-only, network-less sidecar, every one `quick_check=ok` (cache.db 3.20 GB in 43 s);
    - the previous images tagged `sentinel-rollback/<service>:f9547c5-20261026`.
  - Production: on `evolve/smart-strategies` with no tracked change, `git merge --ff-only` to `3b945eb`.
  - Build: gateway, engine and agent built one at a time, stamped `3b945eb` / `2026-10-26T16:10:09Z`; each image's stamp checked.
  - Engine, gateway and agent recreated one at a time (`--no-deps --no-build --force-recreate`), each healthy before the next; nginx restarted and healthy.
  - `scripts/verify_deployment.py --expected-sha 3b945eb…` passed (exit 0, verified 16:13:58 UTC); the receipt is in `%USERPROFILE%\sentinel-operations\release-receipts\`.
  - Env audit, read-only, before and after (switches, times and presence only): identical except the release SHA. `FNO_LIVE_TEST_ENABLED` False, the owner halt on (`momentum,penny,edge`). No `.env` change.
  - After: no traceback in the engine, gateway or agent logs; the scheduler jobs registered; `partner_watch_trips` created (26 columns).
  - The 22 censored research trades of Oct 26 stay as they are (owner, Oct 26).
- Remaining:
  - The chandelier look-ahead (unchanged).
  - SEBI's December 7 CAS timings: confirm before that date.
  - Oct 26's 22 censored research trades: the owner said leave them.
  - Check SADHNANIQ's next-session close.

## October 26 — O26d The independent review of O26–O26c fixed: the daily tracker orders a day's exits, unknown warning evidence kept apart from "no warning", a partly filled order sized as it fills, the frozen score really frozen, the closing-auction exit only with dated evidence, no network from tests, the one flaky scheduler test (done, Dev, commit `4205eef`, branch `codex/production-correction-hedge-p0`, pushed, deployed by PR #119 (`3b945eb`, Oct 26))

- Owner ask (Oct 26 evening), on the independent review (`docs/2026-10-26-independent-development-review.md`, committed with this slice): "Please fix this make the system better".
- Current state: Production runs `f9547c5` (PR #118). O26, O26b, O26c and O26d are Dev only.
- Each finding was checked against the code, then fixed with tests. The reviewer's six reproductions (outside the repo, run on the result):
  - R2, R3 and R6 now fail: the defects are gone.
  - R1 and R4 fail on the changed API; their scenarios are tests here.
  - R5's reproduction replaces `socket.connect` itself, so it cannot fail; a real connect is tested instead.
- Fixed:
  - [x] **R1 (P2): the daily tracker's exit order.**
    - `position_tracker.day_exits` (with `bar_exits` and `usable_minutes`) is shared by `update_daily_positions` and the research mirror `research_penny_cnc_lifecycle.tracker_step`.
    - The open settles only what it reaches: through the stop, all out at the open; at T2, all out at the open; at T1, the T1 half at the open and the stop to breakeven.
    - After the open, a stop in reach comes before a target, including the breakeven stop a T1 half made active in the same bar.
    - Rising from under T1, the price passes T1 before T2: a day reaching T2 takes the T1 half first. It used to close everything at T2.
    - The entry day's open came before the entry, so it is not used (the entry price stands in).
    - A day the daily bar cannot order (stop-first chose, or any touch on the entry day) is walked through its minute bars (`get_intraday(..., "minute")`, those days only) when they cover it: from 09:16 to 15:14, reaching the day's high and low within 0.1%, from the entry minute on the entry day. Otherwise the stop-first result stands. Logged as `daily_bar_exit_order basis=...`.
    - A T1 half and a close on one day are the two writes the next day's pass would have made (same keys).
    - The mirror is `penny_cnc_connors_lifecycle_v2` (v1 results are not comparable); `tracker_step` returns a list of events.
    - The review's example (open at T1 10.3, high 10.7, low 9.5): the T1 half at 10.3 and the rest at 10.0. It closed all 40 at 10.6.
    - `test_position_tracker_highlow` HIGHLOW-1 changed: its day (T1 = entry 100, high 101, close 98) closed under the breakeven stop, so the price crossed it after T1. The rest is now stopped at 100 the same day; it used to ride overnight under its own stop.
  - [x] **R4 (P2): a partly filled opening order.**
    - `partner_watch_trips` keeps the buy-time facts (`run_pct`, `usual`, `cash`: first known) apart from the opening order's fills (`opening_order`, `opening_qty`, `opening_value`, `opening_final`, `opening_exact`: written again as they grow).
    - `paid_share` is the opening value over the first-known cash, so a restart's later cash read is not used. Later add orders are not in it.
    - `prior_exit` (the trade closed last before the buy; only trades closed by then) replaces `after_loss`.
    - The table is Dev only (O26b): no Production migration. Older Dev tables get the columns added.
  - [x] **R2 (P2): unknown evidence.**
    - `partner_watch_score.evidence_of`: each warning is POSITIVE, NEGATIVE or UNKNOWN (no run, no usual or cash, an opening order that can still fill).
    - POSITIVE is compared against NEGATIVE only; UNKNOWN is counted and shown. ANY is NEGATIVE only when all four are.
    - Each side says how many trades came from the orders rather than the trade book.
  - [x] **R6: the frozen rule.**
    - `SPEC` v2 holds its own thresholds (20% run, 30-minute window, 1.5x usual, 20 warned, 15-minute check look-back) and its cohort and comparison rules.
    - `SPEC_ID` `v2-a3150fcf5a68` is in every result and the report header. A test pins it and shows that moving the live thresholds changes nothing.
    - Frozen before Oct 27, the first decision day.
  - [x] **R3 (P2): the closing-auction exit.**
    - `momentum_shadow.cas_time_exit_evidence` is ELIGIBLE only when all hold: the execution declares `cas_time_exit` (`cas_phase1_last_continuous_close_v1`, new in `EXECUTION`); the session is in `market_calendar.cas_phase1_in_force` (2026-08-03 to before 2026-12-07); the ticker had stock futures in that day's archived NFO master (`research_archive.contract_master_underlyings`; Production has one per day since 2026-09-10).
    - Otherwise the trade stays censored, detail `no_terminal_bar:cas_<reason>`.
    - The derived bar is marked `modelled`; `momentum_shadow_comparison` counts `modelled_time_exit_closes` apart. Bars are sorted first.
    - `momentum_replay._with_last_continuous` uses the same evidence.
    - Found while checking: Zerodha's CAS page gives 2026-08-03 as the start (the code's comments said 2026-01-19, not borne out), and SEBI's revised framework from 2026-12-07 (new timings not confirmed). The window ends there until they are.
  - [x] **R5: the test network guard.**
    - `tests/netguard/sitecustomize.py` refuses lookups, `connect`/`connect_ex`/`sendto` and asyncio `sock_connect` to non-local addresses, numeric and named.
    - `conftest` installs it and puts its folder first on `PYTHONPATH`, so Python child processes that inherit the environment get it.
    - Not covered: a child given its own `PYTHONPATH`, and non-Python programs. `SENTINEL_TEST_NETWORK=1` is the explicit opt-in.
    - `tests/test_network_guard.py` (11 tests).
  - [x] **The one failed scheduler test (cause found).** The tick skipped when `tick_started >= waiting_since` (two `monotonic()` readings). Windows' clock moves every 15.6 ms, so a pass right after another was skipped. It is now a pass counter (`fno_pass["ticks"]`). Production's Linux clock is fine-grained: little live effect. A frozen-clock test fails on the old code.
  - [x] The same clock made `test_s5_provider_lanes::test_without_bulk_waiters_ordering_is_unchanged_from_s2` fail once in this slice's first full run (it passed alone): at 200/s a 15.6 ms step refilled a token while its waiters queued. The test now runs at 20/s; the limiter is unchanged.
- Partner enrichment: DAY says "about ₹X of charges (estimated)": they are worked out from the fills, not the contract note.
- Files:
  - `python-engine/position_tracker.py`, `research_penny_cnc_lifecycle.py`, `partner_watch.py`, `partner_watch_score.py`, `partner_watch_report.py`, `momentum_shadow.py`, `momentum_replay.py`, `market_calendar.py`, `research_archive.py`, `scheduler_setup.py`.
  - Tests: `tests/conftest.py`, `tests/netguard/sitecustomize.py` (new), `test_network_guard.py` (new), `test_research_penny_cnc_lifecycle.py`, `test_partner_watch.py`, `test_partner_watch_score.py`, `test_oct21_audit_fixes.py`, `test_momentum_replay.py`, `test_scheduler_closures_invoke.py`, `test_position_tracker_highlow.py`, `test_s5_provider_lanes.py`.
  - `docs/SYSTEM_CODE_ATLAS.md`; the review document.
- Tests: full suite (`python -m pytest tests ../scripts -q`): 6,110 passed, 4 skipped, exit 0 (11 min 24 s). The first full run had 2 failures, both explained and fixed (HIGHLOW-1's expectation; the lanes test's timing). Focused: tracker and mirror 48, partner watch and score 130, closing auction and replay 50, scheduler 29, network guard 11. Tests do not show profitability or the partner's results.
- Config impact: no setting.
  - Paper books: the daily tracker's results change; they are more conservative where a day cannot be ordered, and minute bars are fetched on those days only.
  - `partner_watch_trips` columns (a Dev table).
  - Momentum shadow: new trades carry the new execution field; an F&O stock's time exit needs that day's archived master.
- Rollout: with the next PR to `evolve/smart-strategies` on the owner's go-ahead; the engine image only. Rollback: revert the commit.
- Remaining:
  - The chandelier trail is still raised with the day's close before that day's low is checked (more stops, not fewer; unchanged).
  - SEBI's December 7 timings: confirm them from the circular, then add the next window (a new execution version).
  - Oct 26's 22 censored research trades: the owner's call (Production has the dated master for Oct 26).
  - Check SADHNANIQ's next-session close.

## October 26 — O26c The Oct 26 audit's findings fixed: no buy sent after a halt, no check sent past its prices, closing-auction stocks scored, the daily tracker takes the stop first, the test suite never reaches the network; two partner messages say more (done, Dev, commit `a848bcb`, branch `codex/production-correction-hedge-p0`, pushed, deployed by PR #119 (`3b945eb`, Oct 26))

- Owner ask (Oct 26): the day's audit (`docs/2026-10-26-production-deep-audit.md` in Production): "if you have any improvement for the partner system or for the trading, go ahead with the working and the enrichment".
- Current state (the audit's O26-D1):
  - Production runs `f9547c5` (PR #118, deployed Oct 25 18:56 IST). The Oct 26 audit verified it from the image, `/health` and 325 source hashes.
  - O26, O26b and O26c are Dev only.
  - The partner's new Kite app secret was proven by their 07:05:56 login.
- Agreed and fixed. Each was reproduced first by a test that fails on the old code.
  - [x] **O26-H1 (P1 before live): a halt tripped while a buy's cash is read.**
    - `kite_client.place_order` checked both halts before and after the rate limiter, then awaited the own-cash read and the reservation. One fake order POST went out with the global halt on.
    - Both halts are now checked again after those reads, immediately before the POST. A refusal gives the hold back as `halted_before_dispatch` (nothing was sent). Exits are unchanged.
    - The gateway already rechecked right before its `placeOrder` (`executor.js`).
  - [x] **O26-C1: a check whose prices go old while its row is claimed.**
    - `_deliver` tested `valid_until` only at its start; a 2 s database claim sent "the ask now" 17 s after the read.
    - It now reads the clock again after the build and the claim. A check past `valid_until` is put back, marked refreshing and worked out again from prices read then.
  - [x] **O26-C2: future clocks.** `quote_freshness` is INVALID when our read or receipt is more than QUOTE_FRESH after `now` (a clock that went back); all three clocks ten minutes ahead passed as FRESH.
  - [x] **O26-R1: 22 of 75 RS_PULLBACK trades censored.**
    - Cause found: NSE's closing auction. Cash stocks with derivatives trade continuously only to 15:15, so they have no 15:15 bar.
    - Production's cache for the day: the 23 tickers without a 15:15 bar are all F&O stocks; the 38 with one are mostly not.
    - The terminal pass therefore censored every F&O stock: the cohort was scored on the smaller stocks only.
    - Now a session with its 15:00 bar and no 15:15 bar takes the 15:15 exit at the 15:00 bar's close (the last continuous price). The 15:00 bar's own stop and target still come first. Receipt detail `time_exit_last_continuous`.
    - `momentum_replay._simulate` does the same, so replays keep runtime parity; it took such trades at the next session's open.
    - Oct 26's 22 receipts stay censored: a pass resolves only the day it runs. A backfill would be a Production data write, the owner's call.
  - [x] **O26-P1: the daily tracker's stop/target order.**
    - `position_tracker`'s comment said stop first; its branch booked the target when one bar touched both. A daily bar cannot order the touches.
    - The stop is now taken, unless the day opened at a target (that fill came first) or at/under the stop (the stop at the open).
    - Found while there: T1 counted after the T1 half was taken. A later day touching T1 and the breakeven stop held the rest. T1 now counts only while the position is OPEN.
    - The research mirror `research_penny_cnc_lifecycle.tracker_step` changed identically (the parity test covers both).
    - Oct 26's VGL target close is not affected: it closed at its high (₹56) and never neared its stop.
  - [x] **O26-M1: F&O management after 15:25.** `_run_fno_tick_safe` and `_run_fno_fast_exit_safe` stopped at 15:25 while derivatives trade to 15:40. They now run 15:26–15:39 only while a single leg (paper or live) or a paper structure is open, so an exit not yet filled is worked and a broker's own 15:25 MIS square-off is read back the same day.
  - [x] **O26-T1: the competing Telegram poller was this Dev test suite.**
    - The three 409s (13:46:48, 14:22:19, 14:37:19 IST) fell inside the three full test runs of O26 and O26b.
    - `test_every_scheduled_job_resolves_its_globals` runs every job, including `partner_inbox_tick`. During market hours that polled the real partner bot with the token in Dev's `.env`.
    - Production backs off 10 minutes after a 409: the partner's inbox (checks, buttons) was paused about 30 minutes in the afternoon.
    - A run that refused every outside name lookup listed the rest:
      - `test_penny_hourly_report…accepts_universe_as_of_kwargs` called Telegram too (with Dev's owner token: it may have sent penny hourly reports to the owner during test runs);
      - seven tests looked up www.nseindia.com.
    - `tests/conftest.py` now gives every test fake bot tokens, a fake chat id and fake partner Kite keys, and refuses a lookup of any non-local host.
- Partner enrichment (from the day's numbers):
  - [x] DAY adds "That includes ₹X of charges on N orders." (`Trip.charges`, the charges `realised` takes off). On Oct 26, charges were ₹1,669 on 55 orders, a quarter of the loss.
  - [x] A buy refused for funds adds "That is more than all of your ₹X cash in one trade" (or its share), and the usual share when known (`refused_text`, `_usual_share(before=)`). On Oct 26, five buys were refused; one needed ₹17,244 on ₹17,218.
- Not changed, and why:
  - O26-F2 (SADHNANIQ open in both Smart books): the penny_smart files are hashed (owner rule). Check read-only that the next session closes it once per policy.
  - O26-S1 (two telemetry write locks, replayed) and O26-Q1 (degraded corporate inputs): observed, recovered or data-side; no code change.
  - BLUECOAST's 11.9% spread admitted by ON_TIGHT_SPREAD: that shadow's rule is frozen while it is scored; its API already says it caps the fill premium, not the spread.
- Files:
  - `python-engine/kite_client.py`, `partner_watch.py`, `momentum_shadow.py`, `momentum_replay.py`, `position_tracker.py`, `research_penny_cnc_lifecycle.py`, `scheduler_setup.py`.
  - Tests: `tests/conftest.py`, `test_f1a_own_cash.py` (+2), `test_partner_watch.py` (+2, 3 extended), `test_oct21_audit_fixes.py` (+1, 1 changed), `test_momentum_replay.py` (+1), `test_research_penny_cnc_lifecycle.py` (+4 cases, 2 renamed), `test_scheduler_closures_invoke.py` (+1).
  - `docs/SYSTEM_CODE_ATLAS.md`.
- Tests: Dev (Windows venv) full engine + scripts suites: 6,069 passed, 4 skipped, exit 0 (O26b's 6,056 plus 13 new cases). A run that refused every outside lookup passed too (before the last 10 cases): it listed the tests that had reached Telegram and NSE. Each fix's new test fails on the old code (checked with HEAD's file swapped in). Tests do not show profitability or the partner's results.
- Config impact: no setting, no table. New receipt detail value; F&O ticks may run 15:26–15:39 when something is open.
- Rollout: with the next PR to `evolve/smart-strategies` on the owner's go-ahead; the engine image only. Rollback: revert the commit.
- Remaining:
  - On the entry day a daily bar also holds prices from before the entry. Ordering by minute bars after the entry needs the tracker and its mirror changed together.
  - Oct 26's 22 censored identities: the owner's call.
  - Check SADHNANIQ's next-session close.

## October 26 — O26b O26's open items, on the owner's go-ahead: a far bigger buy still warns on a quiet day; every trade stored during the day; the check's warnings scored by a frozen rule (done, Dev, commit `cf6befc`, branch `codex/production-correction-hedge-p0`, pushed, deployed by PR #119 (`3b945eb`, Oct 26))

- Owner ask (Oct 26): "Go ahead do it ensure quality of development". This covers O26's three open items: Quiet lets the size warning through, each trade is saved during the day, and the warnings are checked later for whether they predict losses.
- Done:
  - [x] **SIZE (`partner_watch.size_reasons`, `_size_through_quiet`, `size_text`, `_b_size`).**
    - When "Quiet today" mutes a PLAN or ADDED, the same warning the PLAN would carry still goes as SIZE, in two cases:
      - the money in the trade is over 1.5x the partner's usual share of cash (for ADDED, what is held after the add);
      - a buy bigger than the losing trade just before it (the PLAN's "bigger").
    - It says the size, the loss just before, and the plan in one line (`plan_summary`: never a stop to place against an old or crossed price), then "🔕 Quiet is on: this one is sent because of the size."
    - Rare by construction. Built from the latest read: `superseded` once the trade is sold. QUIET_KEEPS, PRIORITY 2, LIFETIME 180 s. Without Quiet the PLAN carries it and no SIZE goes.
  - [x] **Trades stored during the day (`partner_watch_trips`, `trip_row`, `_store_trips`).**
    - Each tick writes the trades that changed (a buy, a sale, a later trade-book fill, the plan's run, the day's cash), all of them after a restart.
    - Stored: fills, the result after charges, `exact` (every fill from Zerodha's trade book), carried.
    - Also stored, from the buy: what a check would have warned about — the plan's 15-minute run, a losing exit within 30 minutes (with "bigger"), the usual share and this buy's share.
    - Those buy-time facts are kept as first known (an upsert with COALESCE).
  - [x] **`partner_watch_report`** adds "Trades <day>": closed, won, lost, the result after charges ("from the orders" when a fill was not in the trade book yet), open, carried, and each trade with its buy-time warnings.
  - [x] **`partner_watch_score`** (new; read-only), frozen before the days it decides on.
    - Closed, not-carried trades from FROZEN_FROM (2026-10-27). Oct 26, the day these were designed on, is never scored.
    - Warnings: CHASED_SPIKE (run ≥ 20%), AFTER_LOSS, BIGGER_AFTER_LOSS, UNUSUAL_SIZE (> 1.5x usual), ANY.
    - SUPPORTED only when all four hold: at least 20 warned trades; the warned mean is below the unwarned mean; the warned total is negative; and it is still negative without the single worst warned loss. Otherwise TOO_FEW or NOT_SUPPORTED.
    - Checked trades (a check reply for the same option in the 15 minutes before the buy) are reported apart from unchecked ones.
    - A verdict informs the owner and changes nothing.
- Found by the new tests and fixed before the commit: after a restart, a closed trade's row was written again before its plan was read back (the watch does not reload plans for closed trades), so its run went to unknown. The buy-time facts are now kept as first known.
- The flaky `test_a_send_cut_off_part_way_is_not_sent_twice` (Oct 24, and again in this change's first full run) is explained and fixed:
  - Under the full suite's load the buy's PLAN was sometimes still unsent when the test made sends hang. The PLAN's send hung, and NO_STOP stayed queued and went after the restart. The log had no PLAN acknowledgement.
  - The test now waits for the PLAN, then checks that the send that hung is NO_STOP: 35 of 35 runs, 10 of them under CPU load.
  - The watch's code was right; the test assumed an order.
- Files: `python-engine/partner_watch.py`, `partner_watch_report.py`, new `partner_watch_score.py`; tests `tests/test_partner_watch.py` (+6; the cut-off send test made deterministic) and new `tests/test_partner_watch_score.py` (5); `docs/SYSTEM_CODE_ATLAS.md` (289 modules).
- Tests: every partner test file 633 passed. Full Dev (Windows venv) engine + scripts suites: 6,056 passed, 4 skipped, exit 0, 12 min 5 s (O26's 6,045 plus 11 new tests); the first full run had the one flaky test (fixed, above). Tests do not show the partner's results or profitability.
- Config impact: no setting.
  - New table `partner_watch_trips`, created by `init_partner_watch_db` (IF NOT EXISTS; no migration step).
  - New `partner_watch_messages` kind SIZE; ADDED's context also keeps `held_value` and `usual`.
- Operator, once deployed:
  - `docker exec -u quantuser python-engine python -m partner_watch_report <day>` gives the day's trades, exact during the day.
  - `docker exec -u quantuser python-engine python -m partner_watch_score` gives the frozen scoring; it says TOO_FEW until there are 20 warned trades.
- Rollout: with the next PR to `evolve/smart-strategies` on the owner's go-ahead; the engine image only. Rollback: revert the commit. The table can stay; nothing reads it then.
- Remaining:
  - The first verdict needs at least 20 warned closed trades on days from Oct 27, and the code must be running in Production to store them.
  - Oct 26's trades reach `partner_orders` with the 15:50 sync, not `partner_watch_trips` (this code was not deployed); it is the design day anyway.

## October 26 — O26 The partner's first watched day: the day so far told once a step of their cash, through "Quiet today"; a run figure that agrees with its warning (done, Dev, commit `6ec5ce1`, branch `codex/production-correction-hedge-p0`, pushed, deployed by PR #119 (`3b945eb`, Oct 26))

- Owner ask (Oct 26), after the first watched day: make the system flexible and smarter for most cases, not trained on one day, always towards better profit; improvements in Dev only.
- Production evidence, Oct 26 (read-only, Production `f9547c5`):
  - The partner logged in at 07:05 with the new Kite app (its secret proven). 21 buys of NIFTY weekly options from 09:17 to 11:56; 19 closed by 13:08.
  - Result about −₹5,300 after charges. This is an estimate: the sells are stored only by the 15:50 sync, so each exit was taken from the watch's looks (a fired stop at its trigger). It matches the watch's own figure for the 09:38 trade (−₹723 against −₹725). That is about 30% of the day's cash (about ₹16,700).
  - "Quiet today" was tapped at 09:28. After it, 19 PLAN, 2 NO_STOP and 1 ADDED were muted. What went: 6 LOWERED, 3 REFUSED (buys bigger than the cash), 3 CHECK replies.
  - Nothing told the partner about the day as a whole.
  - The check was used 3 times, 09:36–09:46. Both of its warnings were right, and the partner held back each time. At 09:38 a 19.7% run read "up 20%" with no chased-spike warning; they bought 17 s later and lost about ₹725.
  - What-if (estimate): skipping every buy that a check would have warned about gives about ₹3,900 less loss. But 20 of 21 buys were warned, both big winners among them. On this one day, neither warning alone separated winners from losers.
- Decisions, and why:
  - A buy's own warnings stay muted under Quiet: 20 of 21 would have gone, and noise gets the bot muted. One DAY message a step tells the pattern instead.
  - No threshold or rule is changed from one day's results (freeze, then score). DAY_STEP is a messaging cadence on the partner's own cash, not a value fitted to Oct 26.
  - The trend line stays. It is the F&O engine's own 5-minute EMA reading, a fact; the 09:38 miss was the run figure.
  - Never a block: DAY gives the numbers and ends "whether to trade on is your call".
- Done:
  - [x] **DAY (`partner_watch.day_so_far`, `day_text`, `_b_day`).**
    - Each time the day's loss (today's closed trades after charges, carried ones left out) passes another DAY_STEP (10%) of the day's cash (opening balance plus money added).
    - It says: the result and its share of the cash; the trades closed, won and lost; how many were bought within 30 minutes of a losing exit and what they made together; what is still open; and the check to send before the next buy (the latest trade's option, e.g. `check 22300 pe`).
    - One message a step a day (key `day:<day>:<step>`); only the step reached now, so a jump past two steps is one message; a restart repeats none.
    - Built from the latest read at send time: a day back above the step, or past the next one (whose own message tells it), is `superseded`.
    - In QUIET_KEEPS; PRIORITY 2; LIFETIME 600 s. Without the day's cash it is never sent.
  - [x] **Run figures rounded down (`_pct_down`)** in the check and the PLAN message: "20%" now always comes with the chased-spike warning (SPIKE_RUN_PCT 0.20), and 19.7% reads 19%.
  - [x] The watch-on text and the Quiet answer name the DAY step. The answer is 164 characters, under the 190 that `partner_fill_capture._answer` keeps.
- Files: `python-engine/partner_watch.py`; `tests/test_partner_watch.py` (+5: Oct 26's first six trades, the 19.7%/20% run, the Quiet answer's length, a step told once through Quiet and after a restart, a step no longer true and no cash); `docs/SYSTEM_CODE_ATLAS.md`.
- Tests: the watch's file 112 passed (107 before); every partner test file 622 passed. Full Dev (Windows venv) engine + scripts suites: 6,045 passed, 4 skipped, exit 0, 11 min 50 s (O25N's 6,040 plus the 5 new tests). Tests do not show the partner's results or profitability.
- Config impact: no new setting, no schema change, no migration. New `partner_watch_messages` kind `DAY`.
- Rollout: with the next PR to `evolve/smart-strategies` on the owner's go-ahead; the engine image only. Rollback: revert the commit.
- Remaining: all three were taken up by O26b (above): a frozen scoring of the warnings (`partner_watch_score`), the trades stored during the day, and the size warning on a quiet day (the owner's go-ahead).

## October 25 — O25N The O25M open items closed: once-a-day partner messages retried safely, the CHECK work-out survives a restart; promoted to Production (done, commit `967c2d6`, branch `codex/production-correction-hedge-p0`, pushed)

- Owner ask (Oct 25): "yes all the open you close then commit push merge and deploy and restart and rebuild the prod while ensuring all the env are in line".
- Done:
  - [x] **Shared daily-send ledger (`partner_orchestrator.send_daily` / `retry_daily` / `daily_retry_tick`).**
    - Used by the brief (09:50), the wrap (15:50), the coach note, the review prompt (`zerodha_prompt`) and the 07:00 login reminder.
    - Each send is a `<kind>_try` row (`<day>:<n>`). It is claimed with its text and button before it goes, and settled with Telegram's answer after.
    - Only a provably unsent send is sent again: 5, 10 and 20 minutes later, at most DAILY_ATTEMPTS (4) sends, and within DAILY_RETRY_WINDOW (60 min) of the first.
    - The retry reuses the first send's stored text with "⏱ Written at HH:MM; it could not be sent then."
    - Never resent: a timeout after the request left, a send a restart cut off, or a 4xx.
    - The day's (kind, day) row, which `_seen` reads, is written only when nothing more will be sent: sent, uncertain, refused or undelivered. `_seen` and `_record` are unchanged; signals, pins, cue and flow events keep their own record (time-sensitive, never resent).
    - New job `partner_daily_retry` (cron */5 at :40 seconds), gated on the partner bot.
    - The reminder keeps its own tick (rebuilt text, also sent when the 07:00 run was missed). Its private copy of the ledger was removed.
    - `_send_prompt`: a second ask while its retry is due says `retry_later`, not a second send.
  - [x] **CHECK work-out durable (`partner_watch`).** The outdated row stays due as `refreshing` until its replacement is in the outbox, and only then is it closed `outdated`.
    - In-process work-outs are listed in `_refreshing`, so a row being worked out waits.
    - After a restart the row is worked out again; the replacement's fixed key means no doubles.
  - [x] **Env alignment (read-only audit, no values printed).**
    - Production's root `.env` has 23 names; every one is used by the engine settings, the agent, ngrok or `os.getenv`.
    - The gateway validates its required env at startup.
    - O25M and O25N add no setting and need no `.env` change.
    - Effective switches before the rollout:
      - FNO_LIVE_TEST_ENABLED, FNO_LIVE_TRADING and PENNY_LIVE_TRADING false;
      - FNO_DISABLE_LIVE and PENNY_EDGE_DISABLE_LIVE true;
      - OWNER_LIVE_ENTRY_HALT true; channels momentum,penny,edge;
      - run window Nov 2–6;
      - reminders 07:00;
      - partner bot, sync, watch and fill capture on; watch stream off;
      - both Kite routes set.
- Files:
  - `python-engine/partner_orchestrator.py`, `partner_broker_sync.py`, `partner_coach.py`, `partner_watch.py`, `scheduler_setup.py`;
  - tests: new `tests/test_partner_daily_delivery.py` (8); `test_partner_watch.py` (+1, the restart during a work-out); `test_partner_orchestrator.py` (its fixture patches `partner_bot.send_partner_result`: the brief and wrap had reached the real sender with a fake token); `test_partner_insights.py`, `test_login_reminder.py` (the ledger's names); the two goldens (the new job only);
  - `docs/SYSTEM_CODE_ATLAS.md`.
- Tests: Dev (Windows venv) full engine + scripts suites: 6,039 passed, 4 skipped, 1 failed (the calendar-gate guard wanted the new cron's [CALENDAR-GATE] marker; added, then the guard, scheduler, golden and ledger tests: 40 passed). 6,040 = O25M's 6,031 plus 9 new tests. Tests do not show the partner's results or profitability.
- Config impact: no new setting; one new scheduler job; new partner_messages kinds `brief_try`, `eod_try`, `coach_try` and `zerodha_prompt_try` (no schema change); partner_watch_messages outcome `refreshing`.
- Rollout: PR to `evolve/smart-strategies`, merged with the owner's go-ahead. Production procedure: database backup, rollback tags, fast-forward, stamped build of the three images one at a time, recreate one at a time, nginx restart, `verify_deployment.py`, then the env audit again. The rollout receipt follows in the next docs commit.
- Rollback: the `sentinel-rollback/<svc>:7468853-20261025` images, or revert the merge; no migration.
- **Receipt (done Oct 25, 18:45–18:56 IST):**
  - PR #118 merged as a merge commit, `f9547c5` on `evolve/smart-strategies`, carrying O25M (`07e22da`) and O25N (`967c2d6`). The Production branch had no commit of its own beyond its merges.
  - Backups, outside the repositories, in `C:\Users\Urveesh\sentinel-operations\production-rollout-20261025-o25n\`:
    - 8 SQLite databases as single-step online snapshots from a read-only, network-less sidecar, every one `quick_check=ok` (cache.db 3.15 GB in 57 s);
    - the previous images tagged `sentinel-rollback/<service>:7468853-20261025`.
  - Production: on `evolve/smart-strategies` with no tracked change, `git merge --ff-only` to `f9547c5`.
  - Build: engine, gateway and agent built one at a time, stamped `f9547c5` / `2026-10-25T13:19:55Z`; each image's baked stamp checked.
  - Engine, gateway and agent recreated one at a time (`--no-deps --no-build --force-recreate`), each healthy before the next; then nginx restarted.
  - `scripts/verify_deployment.py --expected-sha f9547c5…` passed with health checked; the receipt is in `%USERPROFILE%\sentinel-operations\release-receipts\`.
  - Env audit, read-only, run before and after (switches, times and presence only): identical except the release SHA. No `.env` was edited.
  - Engine startup:
    - `premarket_login_nudge`, `login_reminder_retry_tick` and `partner_daily_retry` registered, with the brief and the wrap;
    - no traceback or error;
    - `/health` DEGRADED only for no_kite_token, instrument_cache_unavailable and order_execution_unverified (expected until Monday's login).
  - Gateway: `kite_route` still encrypted through the tunnel; the order-route probe job ran successfully. Dashboard HTTP 200. All four services healthy, restart `always`.
  - No real order placed and no Telegram message sent by the rollout.
- Remaining (not code): live evidence from the first real partner session (O25L item 2) and O25L items 3–8.

## October 25 — O25M Fixes for R1–R3 from the O25L review: CHECK prices current when sent, quote clocks enforced, the morning reminder retried safely (done, Dev, commit `07e22da`, branch `codex/production-correction-hedge-p0`, pushed)

- Owner ask (Oct 25): the three O25L findings, "Fix them".
- Done:
  - [x] **R1, CHECK replies (`partner_watch`).**
    - `answer_check` keeps the reply's evidence with its outbox row: the parsed request, the exact option and expiry (`contract`), `read_at`, and `valid_until` (QUOTE_FRESH, 15 s, after the prices were read).
    - `_deliver` never sends a CHECK past `valid_until`. This covers a retry after no connection, a 429 or a 5xx; a slow first send; and a restart. The row is closed `outdated`.
    - `_refresh_check` then runs beside the sender, so urgent alarms never wait on its market reads. It works the check out again from prices read then, for the same option and expiry (`pin`), CHECK_REFRESHES (1) times. The reply says when the prices were read again.
    - After that, or when the work-out fails, the reply is a note with no numbers that names the option and the words to ask again (`check_late_text`).
    - Replies without prices are sent unchanged: help, not found, price unreadable.
    - A CHECK row without `base` (not written by `answer_check`) counts as priced when its row was written.
  - [x] **R2, quote freshness (`quote_freshness`).**
    - FRESH, STALE, UNVERIFIED (a clock missing, unreadable or without a zone), INVALID (the exchange time more than QUOTE_CLOCK_SKEW, 5 s, after receipt), MISSING.
    - `level_state` returns UNVERIFIED (not VALID) for both bad cases. The texts say "could not be verified", and never show a future time.
    - `_market_plan` uses the option's mid and the future's price only when FRESH, whether or not a price was typed. A typed price with an old quote gives the same plan as no quote: the levels are worked from the typed price, and the reply says why there is no live price.
    - `check_text` itself drops a quote whose clocks do not hold, so it never says "the ask now" from one.
    - An old future quote places no level. The plan takes the last closed 5-minute bar, as before when the future was unread, and the check says so.
    - `unfilled_text` says the bid only from a current quote.
  - [x] **R3, the partner's morning reminder (`partner_broker_sync`).**
    - Each send is a `login_reminder_try` row, claimed before the send (INSERT OR IGNORE) and settled after it.
    - Provably unsent sends are retried: `partner_bot.provably_unsent`, shared with the watch's `_retryable`. The waits are 5, 10 and 20 minutes, LOGIN_REMINDER_ATTEMPTS (4) sends in all, only inside 07:00–08:30 (`reminder_window`).
    - Never repeated: a timeout after the request left, a send a restart cut off (`attempting` older than 60 s), a Telegram 4xx, or after a login.
    - The day's `login_reminder` row is written only when nothing more will be sent. It records reminded, uncertain, refused or undelivered.
    - New job `partner_login_reminder_retry` (`daily_bootstrap.login_reminder_retry_tick`) runs every 5 minutes, hours 7–9, checking the window first and the trading day second. It also sends a reminder the 07:00 run missed (a restart). It never repeats the owner's nudge.
    - `_seen` is unchanged for every other kind.
  - [x] **Owner alerts, observability.** `operator_alert.notify_operator` logs the gateway's `delivered` flag: `operator_alert_queued` (warning) when Telegram did not take it on the first try and the gateway is retrying. Acceptance is still not reported as receipt.
- Evidence behind the strict clock rule: Production's research archive, Oct 21–22. Of 69,480 Kite REST quotes (NIFTY/SENSEX CE, PE and FUT), the exchange time was never missing and never more than 0.5 s after receipt. Receipt minus exchange time: median 1.1 s, p99 2.3 s, max 28.1 s. The check was a read-only script in the engine container, removed afterwards.
- Files:
  - `python-engine/partner_watch.py`, `partner_bot.py`, `partner_broker_sync.py`, `daily_bootstrap.py`, `scheduler_setup.py`, `operator_alert.py`;
  - `tests/test_partner_watch.py`: FakeMarket stamps both clocks as Market.quote does; hand-built quotes use `_clocked`; 8 new tests;
  - `tests/test_login_reminder.py`: 8 new tests;
  - `tests/main_surface_golden.json` and `tests/add_job_census_golden.json`: the new job only;
  - `tests/test_fno_audit_phase1_fixes.py`: its `operator_alert` stand-in now goes through `monkeypatch.setitem`. It had stayed in `sys.modules` for every later test; the full suite found this through the new alert test;
  - `docs/SYSTEM_CODE_ATLAS.md` regenerated.
- Tests: Dev (Windows venv) full engine suite 5,744 passed, 4 skipped (617 s) plus scripts/tests 287 passed: 6,031 in all (O25k's 6,015 plus the 16 new tests); focused partner suites 165 passed; the O25L review's four reproductions now fail against this code. Tests do not show the partner's results or profitability.
- Config and schema impact:
  - no new setting;
  - one new scheduler job;
  - new partner_messages kind `login_reminder_try` (no schema change);
  - partner_watch_messages: new outcome `outdated` and new CHECK context keys (no schema change).
- Rollout: PR to `evolve/smart-strategies`, then the Production runbook (backup, fast-forward, rebuild the engine, recreate, verify). Not deployed: Production stays `7468853` until the owner promotes it.
- Rollback: revert the commit; no migration.
- Remaining:
  - (Closed by O25N, above.) The brief, EOD and coach messages used the same attempted-versus-delivered `_record` pattern.
  - Live evidence from the first real partner session (O25L plan item 2) and O25L items 3–8.
  - (Closed by O25N, above.) A CHECK work-out cut off by a restart was lost.

## October 25 — O25L independent Production/partner review (audit complete; R1–R3 fixed in Dev by O25M, above)

- Production images/HTTP identity verified at `7468853`; Dev application tree matches. Independent normalized hashes match 293 engine, 38 gateway and 11 agent files. Mumbai VM tunnel source matches Dev and is active/enabled; the full application runs on the owner's PC. No Production edit/restart/order/message or switch change during this review.
- New O25k reminder happy paths are deployed, but three fake-data findings remain: R1 queued CHECK financial text can retry unchanged beyond quote freshness; R2 missing/future timestamps pass freshness and typed entry price bypasses a known stale quote; R3 failed morning reminder is still treated as already reminded. Do not mark these fixed from the existing passing suites.
- Implementation order: R1 delivery-time CHECK evidence/contract binding; R2 explicit option/future freshness independent of typed entry; R3 bounded reminder retry retaining ambiguity. Each slice needs adversarial regression tests, guide/plan update, atlas regeneration if declarations change and separate GitHub rollout/rollback. No new partner order authority or blanket paper veto.
- Acceptance, affected contracts, rollout limits, partner feature inventory and the subsequent streaming/entry-exit research plan: [independent review](2026-10-25-independent-production-partner-review.md). First live watch verification is still pending: Production has zero watch messages/quote paths, stream off, and owner token/instrument/order-execution prerequisites unavailable on Sunday.
- Qualification registry is empty, but owner-authorized `PARTNER_MANUAL_ADVISORY_SEND_UNQUALIFIED=true` allows correctly labelled NOT CHECKED cards subject to the other gates; do not describe qualification as the sole blocker or promise daily tips. Latest saved input statuses are NO_ENTRY_SETUP/not_fresh_break on Oct 23.
- New dated maintenance item: implement effective-date/contract-aware CAS/session/settlement changes before Dec 7, retaining current October/November rules and historical replay semantics. Official broker bulletin and SEBI circular are linked in the review.
- Independent checks: 183 + 307 = 490 focused tests passed; four separate reproductions confirmed the three findings. No source/schema/config change; atlas unchanged. Review changes are Dev documentation only; Production stays `7468853`. Remaining: implement R1–R3, obtain first-session evidence, then staged stream/decision improvements. This audit makes no profitability claim.

## October 25 — O25k A 07:00 login reminder for the owner and the partner, each with their own link; F&O the only channel to open (done, Dev, commit `1d40091`, branch `codex/production-correction-hedge-p0`, pushed)

- Owner ask (Oct 25):
  - "OWNER_LIVE_ENTRY_HALT_CHANNELS=momentum,penny,edge, this you add right now";
  - "like you send a message to me at 7:50 am to remind me of login, just send me a message every day at 7:00 am and to my partner to login with our respective links";
  - "commit, push and merge, then pull and restart and rebuild".
- Done:
  - [x] **Production root `.env`:** `OWNER_LIVE_ENTRY_HALT_CHANNELS=momentum,penny,edge` added (backup `env-backup\root.env.before-o25k`).
    - `OWNER_LIVE_ENTRY_HALT=true` is unchanged, so every channel stays halted until the owner lifts the global halt (runbook step 9). F&O is then the only channel that opens.
  - [x] **`daily_bootstrap.premarket_login_nudge`.** It runs at LOGIN_REMINDER_HOUR:MINUTE (new settings, 07:00) on trading days, with `misfire_grace_time` 30 min. It was 07:50, owner only, no link.
    - **Owner:** the plain-text alert now carries the owner's own Kite login link (`owner_login_url`: ZERODHA_API_KEY, which redirects to the gateway's ngrok callback, so it works from the phone). It is skipped when today's token is already fresh.
    - **Partner:** `partner_broker_sync.morning_login_reminder` sends their app's Kite login button (`review_keyboard("🔑 Log in to Zerodha")`), once a day (`partner_messages` kind `login_reminder`). Not when already logged in, not when the partner bot or the app is unconfigured. Its failure never stops the owner's.
    - English only, messages only; the login is read-only.
  - [x] "Every day" is implemented as every NSE trading day, the same gate as before: no login is needed on a closed day.
- Files:
  - `python-engine/config.py`, `daily_bootstrap.py`, `partner_broker_sync.py`, `scheduler_setup.py`;
  - `tests/test_login_reminder.py` (5), `tests/main_surface_golden.json` (the trigger is now cron 07:00).
- Tests: engine + scripts full suite 6,015 passed, 4 skipped, exit 0 (11 min 34 s); tests/test_login_reminder.py 5 passed; scheduler surface/census goldens pass with the 07:00 trigger. Not a profitability result.
- Config impact: new settings LOGIN_REMINDER_HOUR (7) and LOGIN_REMINDER_MINUTE (0); the job `premarket_login_nudge` is now at 07:00. No schema change.
- Rollout: PR to `evolve/smart-strategies`; Production backup, fast-forward, rebuild all three images, recreate them, restart nginx, `verify_deployment.py`.
- **Rollout receipt (Oct 25, 15:30–15:48 IST):**
  - PR #117 merged as `7468853` (`b6b39e8` kept).
  - 8 database snapshots `quick_check=ok` in `C:\Users\Urveesh\sentinel-operations\production-rollout-20261025-o25k\`; previous images tagged `sentinel-rollback/<service>:b6b39e8-20261025`.
  - Production fast-forwarded; the three images built one at a time stamped `7468853`; engine, gateway and agent recreated separately; nginx restarted.
  - `verify_deployment.py` passed with health checked. No startup traceback.
  - Effective settings:
    - the reminder at 07:00, the owner's and the partner's links on kite.zerodha.com, the partner bot and app configured;
    - OWNER_LIVE_ENTRY_HALT true with CHANNELS momentum,penny,edge; the entry gate refuses fno and momentum alike today (global halt);
    - FNO_LIVE_TEST_ENABLED false.
  - The order tunnel probe answers; the gateway's `kite_route` is encrypted. No message or order was sent.
- Rollback: LOGIN_REMINDER_HOUR=7 / LOGIN_REMINDER_MINUTE=50 in `.env` restores the time; or revert.

## October 25 — O25j Latest docs to the Production branch, Production rebuilt, tunnel settings applied (step 5) with the owner's one-time permission (done; docs `0cc0edc`, release `b6b39e8`)

- Owner ask (Oct 25): "push the latest code all in the prod branch, something was pushed in it so that should also be maintained, and resolve any issues in the way. Then run the script to get the latest code in prod. I allow you this once to put the needed variables in the prod env, and then restart prod. In short, make it fully ready for tomorrow's run."
- State found:
  - PR #115 is already merged (`0aa629a` on `evolve/smart-strategies`). Production is at `0aa629a`, deployed 13:42 IST by O25g, and healthy.
  - `hedge-p0` has three docs-only commits (`2e4529f`, `1bcc98e`, `228547b`) not on the Production branch.
  - The Production branch has nothing our branch lacks, apart from its merge commits.
  - Oracle ingress for 31528 has been added by the owner; it answers from this PC.
  - The protected `tunnel-client.env` matches `tunnel-client-direct.env` (2 lines: http://kite:<48>@161.118.160.180:31528).
- Real-money check before giving the engine a working order route. Production's effective settings:
  - PENNY_LIVE_TRADING false, PENNY_EDGE_DISABLE_LIVE true, FNO_LIVE_TRADING false, FNO_DISABLE_LIVE true, FNO_LIVE_TEST_ENABLED false, OWNER_LIVE_ENTRY_HALT true.
  - So no engine entry can be sent. The engine orders the tunnel newly lets through are only exits: momentum residual SLs and F&O exits for real positions, of which there are none.
- Found: `OWNER_LIVE_ENTRY_HALT=true` would refuse every Nov 2 test buy and the step 8 test order. The runbook's step 9 now sets OWNER_LIVE_ENTRY_HALT=false with OWNER_LIVE_ENTRY_HALT_CHANNELS=momentum,penny,edge first. The owner's call at the weekend.
- Rollout:
  1. These docs → PR to `evolve/smart-strategies`, merged as a merge commit (keeps `0aa629a`).
  2. Production: fresh SQLite online backups; `git merge --ff-only`.
  3. Build engine, gateway and agent one at a time, stamped with the merge SHA.
  4. Back up both `.env` files outside the repositories, then add `KITE_PROXY_URL` (`node-gateway/.env`) and `KITE_ORDER_PROXY_URL` (root `.env`) from `tunnel-client.env`; no other setting changes and no value printed.
  5. Recreate engine, gateway and agent separately (`--no-deps --no-build --force-recreate`), restart nginx, run `verify_deployment.py`.
- Acceptance:
  - identities equal the merge SHA; all healthy; restart policies `always`; the switch false;
  - the gateway logs `kite_route` encrypted with no password;
  - the engine's order client goes through the tunnel and Kite's root answers through it;
  - no conflicting route settings; no real order.
- Rollback:
  - delete the two lines (or restore the `.env` backups) and recreate;
  - the images tagged `sentinel-rollback/*:0aa629a-20261025`;
  - the database backups.
- **Receipt (done Oct 25, 14:27–14:59 IST):**
  - PR #116 merged as a merge commit, `b6b39e8` on `evolve/smart-strategies`; `0aa629a` is kept in its history.
  - Backups, outside the repositories in `C:\Users\Urveesh\sentinel-operations\production-rollout-20261025-o25j\`:
    - 8 SQLite databases as single-step online snapshots, every one `quick_check=ok` (cache.db 3.15 GB in 62 s). A first, stepwise attempt restarted on every engine write and was stopped.
    - both `.env` files (`env-backup\`);
    - the previous images tagged `sentinel-rollback/<service>:0aa629a-20261025`.
  - Production: `git merge --ff-only` to `b6b39e8`, no tracked change. Engine, gateway and agent built one at a time, stamped `b6b39e8` / `2026-10-25T09:12:31Z`.
  - `.env`:
    - `KITE_ORDER_PROXY_URL` added to the root file and `KITE_PROXY_URL` to `node-gateway/.env`, from `tunnel-client.env`; no value printed.
    - No KITE_ORDER_BASE_URL. FNO_LIVE_TEST_ENABLED unset (false). OWNER_LIVE_ENTRY_HALT=true unchanged.
  - Engine, gateway and agent recreated separately (`--no-deps --no-build --force-recreate`), then nginx restarted. All healthy, restart policy `always`.
  - `scripts/verify_deployment.py --expected-sha b6b39e8…` passed with health checked (receipt in `%USERPROFILE%\sentinel-operations\release-receipts\`).
  - Engine:
    - its order-route probe (`_kite_probe_get` through the tunnel) answers; quotes stay direct; no startup traceback;
    - `/health` trading_ready false only for no_kite_token, instrument_cache_unavailable and order_execution_unverified (expected until Monday's login); scheduler running;
    - `fno_proving_week` reads 26–30 Oct, no trade yet.
  - Gateway:
    - `kite_route` encrypted true through 161.118.160.180:31528 (password hidden), and `kite_base_url_ignored` for the relay;
    - Kite's root answers HTTP 200 through the tunnel from inside the container, certificate verified; no password in its logs.
  - Dashboard HTTP 200; gateway health ok (Kite token expired). No real order placed, no Telegram message sent.
- Remaining (owner):
  - Monday before 09:15: the Kite login (and the partner's);
  - watch the 15:50 reports Oct 26–30 and Friday's verdict;
  - at the weekend: steps 1, 3 and 6–9, including the entry-halt change;
  - after Nov 2: step 10.

## October 25 — O25i owner-added Oracle ingress; direct route verified (completed; client adoption pending)

- Owner added the requested rule. Read-only Console verification: attached `ig-quick-action-NSG` has stateful ingress TCP 31528 from `0.0.0.0/0`, all source ports, description `Kite authenticated CONNECT tunnel`; original egress retained. Direct TCP and negative policy checks now pass (missing password 407, wrong target 403).
- Contract/acceptance: test both already-deployed application image transports directly against VM public 31528, verified TLS to Kite, fake-token rejection, no real orders/Production volume. Keep SSH bridge and old relay available; no Production source/config/restart or trading activation.
- If both pass, select the direct endpoint in protected operator settings, retain the separate SSH settings for deliberate fallback, and correct the checklist/guide. Operator client adoption, current broker login/funds, actual preflight and later explicitly authorized order test remain separate. Rollback here only restores the protected settings choice; do not delete the owner's rule or disable working services.
- Completed: both deployed images (`0aa629a`) reached Kite root HTTP 200 directly through public 31528 with certificate verification enabled; gateway explicitly reported verified TLS. Both rejected fake broker tokens as expected. No real broker credential, order call, Production volume or SSH forward was used by these disposable test containers.
- `tunnel-client.env` now equals the verified `tunnel-client-direct.env`; `tunnel-client-ssh.env` and its running task remain available for deliberate fallback. Receipts in the protected directory: `direct-tunnel-verification.json`; no secret printed/committed. All four Production services remain healthy; real-money test still off. No Production file, route, image or running service changed in this slice.
- Direct adoption no longer depends on the Windows SSH task. Step 4 is complete; step 5 adoption/current broker login/read-only preflight and later funded/explicit order test remain. The main checklist now has one current status block and the direct endpoint; SSH instructions are a separate fallback. No application source/schema change or atlas regeneration; integration verification covers the operational change.

## October 25 — O25h SSH bridge installed and verified; Console no longer required for this route

- Owner asks whether SSH can recover the Console password or finish the port setup. SSH key access cannot reveal a website password. The VM has no user OCI config/CLI/SDK; that alone does not establish whether instance-principal IAM permissions exist.
- First check: use the official OCI SDK in an isolated temporary VM directory and attempt read-only network-resource discovery with the VM's existing identity. Never print identity keys/tokens or change IAM. If permitted, inspect actual ingress and plan an additive, concurrency-checked TCP 31528 rule; otherwise record the denial rather than infer authority from root access.
- Alternative to assess if cloud administration is unavailable: an existing permitted network path (31527 or a supervised SSH forward). Preserve the running gateway/legacy route; do not silently replace its port, add a fragile persistent session, or edit Production configuration. Any new helper must be implemented/tested in Dev with bounded resources and explicit rollback before VM installation.
- Acceptance: exact observed cloud authority/result, current Production health retained, no secrets in output/Git, no real orders/live activation. Website recovery remains the owner's authentication action if no suitable alternative is completed.
- Read-only result: official OCI SDK 2.189.0 authenticated the instance principal, but `get_vnic` for the metadata-provided VNIC returned HTTP 404 `NotAuthorizedOrNotFound`. No cloud rule/IAM modification attempted. Use the already-authorized SSH path instead: a dedicated Windows Scheduled Task runs the installed OpenSSH client, strict saved host keys, loopback-only 31528 forwarding to the existing VM tunnel, 15-second keepalives/three missed replies, retry on failure and a one-minute recurring trigger with overlapping instances ignored. No application `.env` edits or new paid service.
- Bridge acceptance before adoption: authenticated TLS to Kite through localhost and from a disposable gateway image via `host.docker.internal`; unauthorized request denied and other destinations denied; a stopped bridge is unavailable; task stop/start and forced SSH loss recover with no duplicate listener. Persist protected client settings separately, keep the direct-route copy, and document the additional Windows-session/SSH dependency. Production client adoption remains the later operator step.
- Completed: Windows task **Trading Sentinel - Kite SSH Bridge** is running the installed OpenSSH client under the current owner's Interactive token, limited privileges, no stored Windows password and no visible SSH window observed. Logon plus indefinite one-minute trigger, `IgnoreNew`, unlimited execution, one-minute failure retry. It binds **127.0.0.1:31528 only** and forwards through strict-host-key SSH to VM localhost:31528. S4U task registration was denied; the Interactive task registered without elevation and requires the owner to remain logged in. Do not log off during trading.
- Verification: missing password 407, wrong target 403, actual local engine and disposable gateway transports root HTTP 200 with fake tokens rejected. Stopping/disabling this task removed its endpoint while Production health stayed HTTP 200. After forcibly terminating only its verified SSH PID, scheduled recovery created a new listener/process in **58.8 s**; both deployed image transports then passed, gateway TLS certificate verified. This is process-loss recovery, not a physical network-loss, reboot or unattended-boot test. No real order or outbound test message.
- Protected settings: `tunnel-client.env` and `tunnel-client-ssh.env` now select `host.docker.internal:31528`; `tunnel-client-direct.env` retains the old public endpoint. No secret printed/committed. Task export and verification JSON retained beside them. Temporary OCI SDK removed; metadata-only permission receipt retained root-only on the VM. No cloud rule, VM service source, Production `.env`, application image or trading switch changed.
- Rollback: while clients are still on the old relay, disable then stop only this named task. If adopted later, first deliberately restore/verify the prior client route through the operator rollout; never disable an in-use order route first. Do not overwrite another task or SSH process. Direct public 31528 remains blocked; the old relay is still active.
- Remaining: step 5 operator adoption of the protected SSH settings, restart/recreate clients through the approved process, actual broker login/read-only preflight and later explicitly authorized order test. Cloud Console recovery is optional for this route, still useful for account administration. See [the SSH bridge runbook](runbooks/kite-ssh-bridge.md). Source unchanged; actual integration checks replace an unnecessary new unit-test suite/atlas regeneration.

## October 25 — O25g independent review, Production recovery and GitHub rollout (completed; Production `0aa629a`)

- Owner request: start the stopped Production services, review O25f, and complete the remaining authorized setup where possible. Production is recovered on `582d7a5`: engine, gateway, agent and nginx healthy; public dashboard and health endpoint return HTTP 200. Broker token is expired and Telegram polling is running; a successful outbound message has not been tested.
- Reviewed O25f `e9645de` / documentation `ecd1a18`: all order mutations refuse conflicting routes before HTTP, reporting handles malformed dates, and rendered Compose gives all three application services `restart: always`. Independent focused run: 66 passed (one existing Starlette deprecation warning). No new source defect established in this slice; previous full-suite result is the other agent's 6,010 passed / 4 skipped receipt.
- Files/contracts: PR #115, GitHub target `evolve/smart-strategies`, existing Production Compose project/data volume, baked image release identity, real-money switch off. Do not copy Dev files into Production or add tunnel credentials before its public route passes.
- Rollout: preserve previous image IDs and a protected database backup; mark PR #115 ready and merge its checked head through GitHub, fast-forward the clean tracked Production checkout, build one image at a time, then recreate engine, gateway and agent separately. Preserve untracked audit files and all unrelated Dev edits.
- Acceptance: all application images and HTTP health report the exact merged SHA; containers healthy, restart policies `always`, engine log retention 20m x 25, scheduler running, dashboard reachable, no new startup traceback, and live-test switch false. Confirm proving-week dates/jobs from the deployed code; no real order or profitability claim.
- Rollback: retain the prior three images and pre-rollout database snapshots outside the repositories. If startup fails, restore the previous GitHub release/configuration and tagged images; preserve the failed database for diagnosis rather than blindly overwriting a migrated live database.
- Remaining access blocker: Oracle Chrome tab is still at owner password recovery. The owner must finish sign-in before cloud ingress can be inspected; installed VM service and protected client settings are already present. Funding, actual broker login, real-order preflight and Nov 2–6 activation remain later operator steps.
- Completed rollout: PR #115 marked ready and merged at checked head `ecd1a18`, merge `0aa629a32f1ee714eb898fb790cf50e4ca06fc43`. Production updated by `git pull --ff-only`; no ad-hoc source/configuration copy. Built one image at a time, then recreated engine, gateway and agent separately with `--no-deps --no-build`. All three and nginx are healthy. `verify_deployment.py` passed container/image identities and HTTP release checks at 13:42:35 IST; public dashboard and health HTTP 200. All application restart policies are `always`, engine logging 20m x 25; scheduler startup attests 88 jobs, partner registration 18.
- Additional validation: new Linux engine image **74 passed**, including proving-week tests; new gateway image native SQLite `quick_check=ok` and tunnel module load passed. Deployed proving-week CLI reads Oct 26–30 and no trades yet. Effective settings: real-money test false, live bankroll 0, evening report true, five proving sessions and Nov 2–6 entry window. No new startup traceback observed. Telegram `getMe` authenticated the bot (read only); no test message or real order was sent. Historical stale delivery backlog remains visible; current health is `ok`, broker token expired.
- Readiness distinction: gateway health `ok` and healthy containers do not mean broker readiness. Engine `/health` is `DEGRADED`, `trading_ready=false`, with `no_kite_token`, `instrument_cache_unavailable`, `order_execution_unverified`; scheduler is running. Owner login/instrument refresh and later authorized order-path verification remain required.
- Rollback/evidence retained in the protected `C:\Users\Urveesh\sentinel-operations\production-rollout-20261025` folder: previous image IDs/tags, **eight SQLite online backups with quick_check=ok**, build logs and the release verification receipt. Old images tagged `sentinel-rollback/<service>:582d7a5-20261025`. No source change/atlas regeneration in O25g. Detailed receipt: [Production recovery and release](2026-10-25-production-recovery-and-release.md).
- Remaining: owner completes Oracle sign-in, then cloud TCP 31528 ingress/direct TLS tests and later client adoption; owner logs in to Kite **Monday morning before 09:15**, and partner separately logs in for the watch. Observe 15:50 reports Oct 26–30 and Friday's verdict. Funding, explicit real-order preflight and owner activation remain Oct 31–Nov 1 decisions; retain 31527 until the replacement has a clean real session. Do not enable the stream or trading switch as part of this recovery.

## October 25 — O25f Review of O25d/O25e: a route conflict no longer stops the engine, a bad run date never silences the reports, Production survives a Docker restart (done, Dev, commit `e9645de`, branch `codex/production-correction-hedge-p0`, pushed, in draft PR #115, not deployed, switch off)

- Owner ask (Oct 25): forwarded the O25d/O25e agent's summary: "now you check if there is any issue then fix it and tell me if anything is left or to enhance or what?"
- Checked:
  - the O25d code (`94a262a`) and its review document;
  - the O25e installation receipt;
  - draft PR #115 (open, mergeable, head `85b464a`);
  - the VM, by a read-only SSH check: `kite-tunnel` active and enabled, listening on 31528, VM iptables ACCEPT; the old relay still on 31527;
  - external TCP from this PC: 31527 answers, 31528 does not (Oracle ingress missing);
  - Production containers.
- O25d's six fixes hold: the frozen run record, Nov 2–6 enforced, no test order after a failed preflight, the AMO maintenance window, the allow list's loopback self-test, `--user quantuser`.
- Found and fixed:
  - [x] **P1: a route conflict stopped the whole engine.** O25d raised `ValueError` in `KiteClient.__init__` when KITE_ORDER_PROXY_URL and KITE_ORDER_BASE_URL were both set. `main.py` builds that client at import, so one leftover `.env` line (the runbook's own fallback swaps one for the other) stopped every paper book, every exit's management and every alert, with no message.
    - Now the client is built with `order_route_error` set and no order client.
    - `place_order` (entries and exits), `modify_order` and `cancel_order` return NOT_SENT / ERROR with `order_route_invalid` before any HTTP. `probe_order_route` returns the reason.
    - The 3-minute probe treats the pair as a failure without fetching through it, so it pages `📡 KITE ORDER ROUTE DOWN`.
    - The preflight already refused (O25d).
  - [x] **P2: a malformed run authorization silenced the reports.** O25d's `current_run` raised `ValueError` on an unreadable or disordered FNO_LIVE_TEST_START_DATE/END_DATE/SESSIONS.
    - The 09:25 job then sent no message. `day_report` raised outside its try, so the whole 15:50 message was lost, the proving-week verdict with it.
    - Now `current_run` returns `window_available=False` with `invalid` (nothing written), and `mirror_entry` refuses (`live_test_run_window_unavailable`).
    - The 09:25 check says NOT ready with the reason; `day_report` heads "run … cannot buy: …".
    - A database failure in either report is caught and reported.
  - [x] **P1 operations: Production stayed down after a Docker Desktop update.**
    - The updater ran 05:42–05:45 UTC (11:12–11:15 IST, `Docker Desktop Updater` log). All containers stopped at 05:41:45–51; the engine and gateway exited 137 (no stop grace in 582d7a5).
    - Only the `restart: always` services (nginx, ngrok, autoheal) came back. `python-engine`, `node-gateway` and `agent` (`unless-stopped`) stayed down, with no Telegram (the gateway sends it). nginx crash-loops on the missing upstream.
    - `docker-compose.yml` now gives those three `restart: always`, effective on the next deploy.
    - The runbook gets a "Before anything" check with the `docker start` order, and the rule: no Docker/Windows updates in market hours, above all Nov 2–6.
  - [x] **Runbook steps 4–5:** the tunnel is installed; its `.env` lines are in the protected `tunnel-client.env`; only the Oracle ingress rule is left.
- Not done here (blocked or the owner's):
  - **Restarting Production now:** this agent's `docker start` was refused by the session's permission classifier ("Production Deploy"); the owner runs it.
  - The Oracle console sign-in and the ingress rule.
- Files:
  - `python-engine/kite_client.py`, `fno_live_test.py`, `ops_watchdogs.py`;
  - `tests/test_fno_live_test.py` (the O25d constructor test is replaced; +1 malformed-run test), `tests/test_kite_endpoint_probe.py` (+1);
  - `docker-compose.yml`; `docs/runbooks/fno-live-test.md`.
- Tests: engine + scripts full suite 6,010 passed, 4 skipped, exit 0 (11 min 36 s); focused suites 140 passed, 1 skipped; the three new regression tests fail on 94a262a/85b464a (checked in a throwaway worktree) and pass now; gateway code unchanged (O25d's receipt: 97 focused passed). Read-only checks: VM kite-tunnel active/enabled, 31528 listening, VM firewall ACCEPT; external 31528 times out, 31527 answers. Not a profitability result.
- Config and migration impact:
  - restart policy `always` for three services (applies at their next recreate);
  - no schema, setting default or scheduler change.
  - The route conflict is no longer fatal at start-up: real orders are refused instead.
- Rollout: with PR #115 (engine, then gateway, then agent). Rollback: revert; `restart: unless-stopped` comes back with it.
- Remaining (owner), in order:
  1. Start Production now (`docker start python-engine`, then `node-gateway`, then `agent`).
  2. Oracle sign-in and the TCP 31528 ingress rule, then recheck 407 / 403 / TLS from outside.
  3. Mark PR #115 ready, merge and deploy (before Mon Oct 26 09:15 if the proving week should run on this code and send the daily 15:50 messages).
  4. The weekend checklist (steps 1, 3, 5–9); step 10 after Nov 2.

## October 25 — O25e VM tunnel installed; cloud ingress and application rollout remain

- Installation/documentation receipt **`c062b65`**, pushed on the existing branch and included in draft PR #115. Post-commit documentation/scope checks passed; the only remaining tracked working-tree edits are the original unrelated `.gitignore` and bottom-of-document changes. No application source changed or atlas regeneration required in O25e.
- Problem/access: the owner's attached 128 GB Linux USB held `/home/urveesh/.ssh/id_ed25519`; its saved host keys match `161.118.160.180`. Recovered to an explicitly protected local directory outside both repositories, without printing private material. Strict-host-key SSH authenticated as `ubuntu` on `trading-sentinel`, Ubuntu 22.04.5 LTS, with passwordless sudo. The earlier missing-key blocker is resolved.
- Authorized scope: install the already pushed O25d tunnel on this existing VM, retain port 31527 and its service, verify actual TLS and both client transports without broker credentials or orders. Keep live trading off and the unfunded account untouched. No paid resource, Production working-copy edit, restart or application deployment.
- Files/contracts: committed `scripts/kite_tunnel.py` (`94a262a`); VM `/opt/kite-tunnel`, root-only `/etc/kite-tunnel.env`, `kite-tunnel.service`, additive TCP 31528 firewall rule. Secrets remain in protected storage and are never included in documentation/output. Cloud ingress may require authenticated Oracle Console access if the current rules do not already permit this port.
- Acceptance: confirm VM identity and old relay before changes; capture rollback state; deployed source hash matches Dev; service active/enabled; persistent VM firewall; unauthenticated request 407, other destination 403, verified TLS to Kite from the actual service; external reachability and both real client libraries checked independently. No claim that these tests prove static-IP order acceptance or profitability.
- Rollout/rollback: install only the verified committed program; preserve existing services/configuration; if verification fails, stop the new service and restore only its changes using the captured state. Retire the old relay only after the replacement application routes have been promoted through GitHub and verified. Application promotion remains draft PR #115, not an ad-hoc Production copy.
- Completed: installed the exact pushed `94a262a` script; installed hash matches committed/local hash. The service is active/enabled, its VM firewall rule is persisted, root-only settings/logs are `0600`, and the old relay remains under PID 4053. Actual VM self-test: **407 / 403 / verified TLS HTTP 200**. Both real client transports also passed against this service through a temporary SSH forward (gateway in a disposable existing Linux image); only fake broker tokens, no order calls. Forward closed and disposable container removed. Detailed receipt and rollback: [O25e installation](2026-10-25-oracle-tunnel-installation.md).
- Remaining: direct external 31528 times out; owner must complete the Oracle sign-in/password recovery already open in Chrome before the existing security list / NSG can be checked. No OCI configuration is present on the VM. Then verify direct public client routes, promote PR #115 through GitHub, apply protected client settings via the agreed operator path, and verify current broker login/cash before an explicitly authorized order test and Nov 2–6 activation. No secret values belong in Git/chat.
- Operational observation: Production checkout is still `582d7a5`, no tracked diff. Engine/gateway containers were already stopped (exit 137, OOMKilled false) at 11:11:48 / 11:11:51 IST, before this installation; no cause inferred and no restart performed. Investigate/restore them through the authorized rollout before relying on Monday's proving-week messages. Proxy settings remain unset and the live-test switch defaults off.

## October 25 — O25d remediation verified; Oracle sign-in needed for VM setup

- Code and owned documentation committed/pushed as **`94a262a`** on `codex/production-correction-hedge-p0`. Post-commit source/doc checks pass and atlas regeneration is byte-stable. The original unrelated `.gitignore` and bottom-of-document changes remain uncommitted and excluded. Production remains `582d7a5`; no VM installation, runtime configuration change or real order has occurred.
- Documentation identity receipt: `ca189f8`, pushed. GitHub rollout is prepared as [draft PR #115](https://github.com/urveesh09/trading-sentinel/pull/115), targeting `evolve/smart-strategies`. It includes the accumulated S23–O25 branch work, not only O25d, and is not merged. The GitHub connector needed reauthentication; the existing local `gh` login created the PR successfully and it is attached to this task. Oracle sign-in remains the outstanding access step; no further permission request is needed for the already authorized setup.
- Owner explicitly authorized fixing all five review comments and setting up the existing Oracle VM today. No extra paid service; real-money switch stays false and no test order while the account is unfunded. Production source/configuration still follows GitHub promotion, not direct edits.
- Implementation: freeze each run's persisted length and enforce the authorized Nov 2–6 entry window independently of startup; reject failed preflight before order calls; reject conflicting order route settings before constructing authenticated clients; block AMO maintenance; permit authenticated loopback self-tests with an external allow-list. Preserve all open-position exit behavior.
- Files/contracts: `fno_live_test.py`, `config.py`, `fno_live_preflight.py`, `kite_client.py`, `scripts/kite_tunnel.py`, their focused tests, runbook, guide, checklist and regenerated atlas. New run end-date column/settings require fail-closed handling of legacy run rows without an authorized end date.
- Acceptance: frozen session limit, early/late/delayed startup, no dispatch outside Nov 2–6, legacy rows unavailable, no order calls on failed checks, no HTTP client creation for conflicting routes, maintenance boundaries on weekdays/weekends, authenticated loopback allowed with unrelated clients denied, focused exit/restart coverage, local real-Kite TLS self-test.
- Implemented all five comments. Run dates/length are frozen per name, legacy rows without `ends_on` refuse entries, and exits remain independent. The application switch is unchanged (off). Code and documentation are verified in Dev; no VM or Production deployment has occurred.
- Verification: full engine + scripts `winvenv/Scripts/python.exe -m pytest tests ../scripts/tests -q -p no:cacheprovider -W error::pytest.PytestUnhandledThreadExceptionWarning -W error::pytest.PytestUnraisableExceptionWarning`: **6,008 passed, 4 skipped**, exit 0, 702.68 s, 52 existing deprecation warnings. Affected suite: **314 passed, 1 existing INDICES-plan skip**. Full-suite shutdown also logged the deliberately injected `penny_ledger_write` failure from `test_penny_risk.py`; that unchanged test independently passes 1/1 and reproduces the diagnostic. This is retained as separate test/runtime hygiene, not hidden as a clean shutdown or counted as a failed assertion. The tunnel test-owned loop's pending-handler cleanup was corrected and its tests pass.
- Fresh real-Kite TLS self-test with the corrected script and a restrictive external allow-list: missing password 407; other destination 403; verified TLS to Kite HTTP 200. No broker credentials/order were used. Atlas regenerated (288 modules), `git diff --check` passes. The module's CLI help examples were subsequently corrected to `--user quantuser` (documentation-only source edit).
- Access: owner confirmed an Oracle Cloud account, but Console remains at sign-in and no SSH key/agent/OCI configuration is available. The relay integration dates to commit `176f1d8` (June 14); Oracle's published IP ranges place it in `ap-mumbai-1`. Ownership/instance identity still need confirmation in the account. Oracle's original private key cannot be downloaded again; use documented console recovery if it is lost. No paid resource was created.
- Configuration/migration: new `FNO_LIVE_TEST_START_DATE` / `_END_DATE`, default Nov 2–6, 2026; additive nullable `fno_live_test_runs.ends_on`. Migration and authorization occur only when the test run is queried while armed. Prior rows are never silently granted an end date. Future runs require a new name and explicit dates. Capital/floor/release are metadata, not newly frozen settings.
- Rollout: test in Dev, commit/push only owned slices, verify documentation after commits, promote via GitHub with trading off. Install the verified tunnel on the existing VM only after usable SSH/console access is available; retain old relay until both clients' replacement routes are verified. Never print real tunnel credentials in tool output.
- Rollback: disable new entries while keeping open positions managed; revert through GitHub if necessary. Restore the prior VM service/configuration if installation verification fails. Remaining operations and verification receipts will be updated before handoff.

## October 25 — Independent O25b/O25c validation (review only; execution fixes pending)

- Reviewed `abbe073` / `cff5036` through pushed HEAD `d67caad`. Full evidence and checklist status: [independent review](2026-10-25-independent-live-tunnel-review.md).
- Scope: audit and safe read-only operational checks. Production remains at release `582d7a5`; no service, VM, firewall, secret, order or trading switch was changed. This review's documentation edits are local in Dev, uncommitted and not pushed.
- Problem: the tunnel works locally, but the run's dates/length and failed-preflight/configuration boundaries do not yet justify enabling real money. Port 31528 is not reachable from this PC; no SSH/OCI configuration is available to complete VM installation here.
- Implementation contracts/files:
  1. **P1 — run bounds:** `python-engine/fno_live_test.py`, `config.py`, tests. Use the persisted session limit for an existing run; enforce the explicitly authorized Nov 2–6 window independently of first observation. An outage or environment change must not silently extend it. Keep open-position exits active outside the entry window.
  2. **P1 — failed preflight:** `python-engine/fno_live_preflight.py`, tests. A failed route/cash/evidence check must return failure before invoking the real test-order function. A test-order PASS must not obscure a failed overall preflight.
  3. **P1 — encrypted route configuration:** `python-engine/kite_client.py`, config/preflight tests. Reject conflicting proxy/base settings before any authenticated request. With a proxy configured, an HTTP base must never cause credentials to travel in an ordinary plaintext proxy request.
  4. **P2 — AMO maintenance:** `fno_live_preflight.py`, tests. Refuse 01:00–05:30 IST on trading and closed days; retain the existing open/close buffers and verified cancellation requirement.
  5. **P2 — allow-list installation:** `scripts/kite_tunnel.py`, `scripts/tests/test_kite_tunnel.py`. An installation restricted to the home IP must still be able to run its loopback self-test, without granting other external clients access.
- Acceptance checks: frozen 5-session run stays ended after changing the environment to 10; no entry before Nov 2 or after Nov 6 (including delayed first startup); failed preflight makes zero order calls; conflicting HTTP-base/proxy configuration sends zero authenticated bytes; maintenance-window boundaries on weekdays/weekends; real local tunnel self-test with a restrictive allow-list. Existing exit/restart/protection tests must remain green.
- Small documentation corrections completed in Dev: engine CLI commands use `docker exec --user quantuser` (the image installs dependencies for that user); step 1 now requires deployment before invoking a newly shipped module; the checklist warns about AMO maintenance and outstanding blockers. No strategy/source change, schema migration or atlas regeneration is involved in these documentation edits.
- Verification: 116 focused Python tests passed; 97 focused gateway tests passed. The two native SQLite gateway files reproduce the Windows binding limit (18 failed, 2 passed); both pass in a disposable Linux verification (20 passed, exit 0, Dev source, no network/Production volume). Local real-Kite tunnel self-test: 407 without credentials, 403 for another target, verified TLS/HTTP 200 to Kite. These checks do not place orders or establish profitability.
- Rollout/rollback: resolve the P1 items and review the diff before GitHub promotion; keep `FNO_LIVE_TEST_ENABLED=false`. Install/configure the VM tunnel only with operator access, then verify actual reachability and both client routes. Apply Production changes through the repository's GitHub promotion process. Do not remove the old relay before the replacement is verified; do not send a real test order or arm trading as part of this audit. If later armed, turning entries off must retain open-position exit management.
- Remaining: implementation above; paper evidence for Oct 26–30 (future at review time); a current Kite login and cash check; an open PR/promotion (none was open for this branch when checked); VM/Oracle setup; explicit real-order test and owner activation at the intended time. Never label the VM secured or the run ready based only on these local checks.

## October 25 (3) — O25c The owner's dates, an encrypted Kite tunnel on the free VM for both services, a weekend test order (done, Dev, commit `cff5036`, branch `codex/production-correction-hedge-p0`, pushed, not deployed, switch off)

- Owner ask (Oct 25): "the real money will start next monday not this coming one, after one more week of observing the fno I will start it the steps you put in one doc i will follow and do it next weekend, also the relay do all you can what you need me to do you tell me, remember I wont pay anything extra for that".
- Dates:
  - the proving week stays Oct 26–30, paper only;
  - the owner does the checklist on Sat Oct 31 – Sun Nov 1;
  - the run is Nov 2–6 (FNO_LIVE_TEST_SESSIONS 5).
  - No default changed: FNO_PROVING_START stays 2026-10-26.
- Problems:
  1. The gateway sends all its Kite traffic through the plain-HTTP relay, including the login exchange and the access token. The review asked for it to be secured, and the owner pays nothing extra.
  2. The preflight test order needed market hours, but the owner does the steps at a weekend.
  3. Nothing probed the gateway's route: the engine's probe watches its own KITE_BASE_URL, which is direct.
  4. The preflight printed KITE_ORDER_PROXY_URL as set, so a tunnel password would have been shown.
- Done:
  - [x] **`scripts/kite_tunnel.py`** for the VM (Python 3.8+ standard library only):
    - serves only CONNECT to api.kite.trade:443;
    - checks the password first (constant time, 1 s delay on a wrong one); optional client allow list;
    - limits: request head 8 KiB within 10 s, Kite reached within 10 s, idle close after 300 s, 128 connections;
    - one log line per connection, with no secrets.
    - `install`:
      - a systemd service with sandboxing (DynamicUser, ProtectSystem=strict, a syscall filter and more);
      - the VM's iptables rule placed before Oracle's REJECT, saved by netfilter-persistent;
      - a self-test (no password → 407, another host → 403, verified TLS to Kite);
      - prints both .env lines; a re-run keeps the password.
    - Also `status` (including what listens on 31527), `print-env` and `uninstall`.
  - [x] **Gateway `services/kite-tunnel.js`.** KITE_PROXY_URL gives a `ConnectTunnelAgent`: CONNECT, then TLS with servername api.kite.trade and the certificate verified.
    - It is used by the Kite SDK (lent through the SDK's axios defaults during its constructor only) and by the direct LTP call.
    - The root is https://api.kite.trade. KITE_BASE_URL is ignored, with a warning.
    - The route is logged without the password. Unset, nothing changes.
  - [x] **Engine.**
    - `KiteClient.probe_order_route`: GET /user/profile through the order client.
    - `redact_url_credentials`.
    - The preflight shows the route redacted and checks that it answers.
    - The 09:25 check says NOT ready when the route does not answer.
  - [x] **Weekend test order.** `fno_live_preflight.variety_for` picks the order type:
    - regular from 09:15 to 15:25 on a trading day;
    - AMO after 15:45, before 09:00 and on closed days;
    - none from 09:00 to 09:15 and from 15:25 to 15:45.
    - The AMO is 20% under the last price, never under the lower circuit, and is cancelled as an AMO (`FnoExecutor.cancel_and_read(order_id, variety)`).
    - "CANCELLED AMO" reads as cancelled. UNCLEAR tells the owner to cancel before 09:11.
    - When the engine's book is not today's, instruments are fetched into a temporary file; the engine's snapshot is never written.
  - [x] **Order-route probe.** `_kite_endpoint_probe_tick` also probes a separate order route (the tunnel, or a relay distinct from KITE_BASE_URL) every 3 minutes in market hours.
    - After 2 failures it pages `📡 KITE ORDER ROUTE DOWN`, deduped for 30 minutes, then `✅ … RECOVERED`.
    - The password is redacted.
  - [x] **Runbook** rewritten as one dated checklist (steps 0–10): the relay table, the fallback, and retiring 31527.
- Verified beyond the unit tests:
  - The tunnel, run locally against the real api.kite.trade, gave 407 / 403 / TLS 200. Run on Windows Python 3.11, and in python:3.8-slim and python:3.12-slim containers.
  - The systemd unit: `systemd-analyze verify` OK; `systemd-analyze security` exposure 1.5 OK (systemd 257).
  - The gateway agent (real TLS) and the real kiteconnect SDK, through the local tunnel to Kite: HTTP 200 on `/`, and TokenException for a fake key, as expected.
  - The engine order client (httpx, password in the URL), through the local tunnel: HTTP 403 for a fake token, so Kite was reached. A wrong tunnel password gave ProxyError 407 with no password in the text.
  - Not verified (the owner's steps 4–8): the service under systemd on the real VM, the Oracle security-list rule, and a real order through the tunnel.
- Files:
  - `scripts/kite_tunnel.py`, `scripts/tests/test_kite_tunnel.py` (10);
  - `node-gateway/server/services/kite-tunnel.js`, `kite.js`, `tests/unit/kite-tunnel.test.js` (8);
  - `python-engine/kite_client.py`, `fno_executor.py`, `fno_live_preflight.py`, `fno_live_test.py`, `ops_watchdogs.py`, `config.py` (comment);
  - tests: `test_fno_live_preflight.py` (+7), `test_fno_live_test.py` (readiness), `test_kite_endpoint_probe.py` (+3);
  - `docs/runbooks/fno-live-test.md`, `docs/runbooks/relay-failover.md`;
  - `.gitattributes` (new): the VM script keeps LF line endings in every checkout.
- Tests: engine + scripts full suite 5,994 passed, 4 skipped, exit 0 (11 min 26 s); gateway full suite 514 passed, 4 skipped, 18 failed only in db.test.js and backlog-reconciliation.test.js (better-sqlite3 cannot load on this Windows Node 24: environment); new tests: test_kite_tunnel.py 10, kite-tunnel.test.js 8, preflight +7, endpoint probe +3, readiness +1 case; live checks: the tunnel and both clients against the real api.kite.trade (Python 3.8/3.11/3.12, the gateway image's Node 20), systemd-analyze verify OK, exposure 1.5. Not a profitability result.
- Config and migration impact:
  - a new optional gateway setting, KITE_PROXY_URL (`node-gateway/.env`);
  - the engine's KITE_ORDER_PROXY_URL now documented with the tunnel's password form;
  - no schema change and no new scheduler job (the existing 3-minute probe also covers the order route); no default changed.
  - Unset: no behavior change beyond the preflight's read-only route lines.
- Rollout: the owner's runbook steps 0–10.
- Rollback:
  - delete KITE_PROXY_URL (the gateway returns to the relay);
  - set the engine's KITE_ORDER_BASE_URL to the relay;
  - `sudo python3 kite_tunnel.py uninstall`.
- Remaining (owner):
  - steps 0–10 of `docs/runbooks/fno-live-test.md`;
  - retire 31527 after Monday's clean session.

## October 25 (2) — O25b The review's gaps in the real-money test are fixed; bounded runs, a daily readiness message, execution evidence and an encrypted order route are added (done, Dev, commit `abbe073`, branch `codex/production-correction-hedge-p0`, pushed, not deployed, switch off)

- Owner ask (Oct 25):
  - the audit-agent review of `ca12934`..`b414383`: 5 P1 and 4 P2 findings, each reproduced by the reviewer;
  - "secure the relay … the one you can improve at your end, tell me";
  - "should I run the script every day or only once?"
- Verdict: agreed with all nine findings. Each was reproduced as a failing test first, then fixed:
  - [x] P1 gateway: `releaseFilled` could throw after a confirmed buy and stop its protection. It is now cleanup only: a failure is logged, the hold is kept (errs safe) and protection continues (`executor.js`).
  - [x] P1 a refused price change stalled the exit: the result reported ₹90 while the order rested at ₹99.50. Now `_reprice` returns whether Kite accepted it. The ladder and `follow_exit` keep the broker-shown resting price (`_resting_price`, Kite's `price`), so a refused change is tried again next pass.
  - [x] P1 a restart during the sell's wait lost its order. Now:
    - the exit's tag and reason are written before the send (`record_exit_tag`, `fno_exit_intents.broker_tag`);
    - the order id is recorded on `placed`, before any wait (`on_event`, `_exit_event_recorder`);
    - a claimed exit with a tag but no id is resolved from Kite's order book (`_recover_tagged_exit`):
      - found by tag, symbol, SELL and quantity → adopted and followed;
      - absent after 30 s → freed and sent again;
      - unreadable or ambiguous → held and paged.
    - a claim with neither a tag nor an id (the engine stopped between the claim and its name, or the broker no longer holds the position) is held for exit recovery and paged; nothing is sold from it.
  - [x] P1 MIS and NRML were mixed in the holding check. `_broker_mis_held` counts MIS on the contract's exchange only, against the quantity to sell. If it holds less, nothing is sold, the claim stays and the owner is paged (`not_held` / `partly_held`).
  - [x] P1 a filled preflight buy could be left unmanaged. The tool never sells now: `hand_off_preflight_fill` records it as a FNO_LIVE position (bar `PREFLIGHT-<order>`). The engine sells it at once (`preflight_flatten`) through the full exit path, and the owner is paged.
  - [x] P2 one-lot P&L understated charges (fixed brokerage per order). `one_lot_pnl` now uses the two fills and one lot's full charges, in the proving week and the evening report. Example: 100 → 100.4 is −₹36.66 at one lot, not the halved two-lot −₹13.06.
    - The pre-registration was amended on Sun Oct 25, before the first session; the window has no trades yet.
  - [x] P2 an unreadable drawdown state could pass: the verdict is now UNAVAILABLE.
  - [x] P2 NIFTY-only was not enforced (an NFO segment is not NIFTY). `mirror_entry` refuses any other underlying (`live_test_not_nifty`).
  - [x] P2 runbook order: the route goes in with the switch off; recreate the engine; check the effective route with the read-only preflight; then the test order; then the switch.
- Recommendations taken:
  - [x] **Bounded run.**
    - FNO_LIVE_TEST_RUN (a name, default "1") and FNO_LIVE_TEST_SESSIONS (5): `fno_live_test_runs` keeps each run's start day, capital, floor and release.
    - After its sessions: no new entry (`live_test_run_ended`), one owner notice. A new run needs a new name.
  - [x] **Execution evidence.** Every real step goes to `fno_live_execution_events`: entry filled with delay and slippage, backstop armed, exit placed, modified, refused, filled or not held, adopted.
    - The 15:50 report shows per trade: the decision-to-fill delay, entry and exit slippage against the paper twin, price moves and refusals, the broker stop's state.
    - It also shows the paper trades not bought for real with their reasons, and the outstanding work: open positions, claimed exits (working), held reservations.
  - [x] **Daily readiness** (`fno_live_readiness`, 09:25, while the test is on: `morning_check`). It reports:
    - the route and today's login;
    - free cash against a typical lot (`typical_lot_cost`, the median of the last 20 paper buys);
    - F&O positions held at the broker;
    - the run's session, equity against the floor, and leftovers.
    - So the preflight is run once, and again only when the order path changes (route, relay, IP, API key or app).
  - [x] **Encrypted route option:** KITE_ORDER_PROXY_URL sends orders by HTTP CONNECT through the VM to https://api.kite.trade, TLS end to end. On Oct 25 the relay answered plain HTTP (200) but refused CONNECT (404), probed without credentials. It needs a CONNECT proxy on the VM (owner).
- Relay options (owner):
  1. firewall port 31527 to the home IP;
  2. a CONNECT proxy (`tinyproxy`) plus KITE_ORDER_PROXY_URL;
  3. a WireGuard/Tailscale tunnel.
  - The gateway still sends all its Kite traffic through the plain-HTTP relay (`node-gateway/.env` KITE_BASE_URL): a separate change.
- Files:
  - `python-engine/fno_executor.py`, `fno_orchestrator.py`, `fno_positions.py`, `fno_live_test.py`, `fno_proving_week.py`, `fno_live_preflight.py`, `kite_client.py`, `config.py`, `scheduler_setup.py`;
  - `node-gateway/server/services/executor.js`;
  - `docs/runbooks/fno-live-test.md`;
  - tests: `test_fno_live_test.py` (25), `test_fno_proving_week.py` (8), `test_fno_live_preflight.py` (5), `executor.test.js` (+1), the census goldens.
- Tests: engine full suite (Dev, Windows, 10 min 6 s, after the last edit): 5,698 passed, 4 skipped, exit 0. `test_fno_live_test` has 26 tests; 6 reproduce the review's cases (refused modification, restart while the sell waits, lost reply, never-sent tagged exit, NRML holding, non-NIFTY) and failed before the fixes. `test_fno_proving_week` has 8 and `test_fno_live_preflight` 5. Against the previous modules (a scratch copy with `git show HEAD:` of `fno_proving_week.py` and `fno_live_preflight.py`), the one-lot-charges, unavailable-halt and preflight hand-off tests fail as they should. An earlier full run made during editing had one failure: `test_fno_shadow` reads the orchestrator's source by line number while the file was being edited. It passes 18 of 18 alone, and the final run is clean. Gateway: `executor.test.js` 65 passed (+1: a failed hold release keeps the GTT protection). The full gateway suite: 506 passed, 4 skipped, 18 failed in `db.test.js` and `backlog-reconciliation.test.js` (better-sqlite3 native binding unavailable on this Windows Node 24; the files are untouched). No order was placed anywhere. The relay was probed without credentials: plain HTTP answered 200, CONNECT answered 404.
- Config and migration impact:
  - new settings: FNO_LIVE_TEST_RUN, FNO_LIVE_TEST_SESSIONS, KITE_ORDER_PROXY_URL;
  - a new column `fno_exit_intents.broker_tag`;
  - new tables `fno_live_execution_events`, `fno_live_test_runs`;
  - a new scheduler job `fno_live_readiness` at 09:25 (it acts only while the test is on);
  - `fno_positions.working_exit` is replaced by `exit_intent`.
  - With the switch off there is no trading change.
- Rollout: as O25. Rollback: FNO_LIVE_TEST_ENABLED=false, then revert.
- Remaining (owner):
  - the Oct 30 verdict;
  - deploy;
  - the relay (option 1 now, option 2 before the run);
  - the route in the `.env`, recreate the engine, the read-only preflight, then the preflight test order;
  - the switch.

## October 25 — O25 The ₹12,500 real-money F&O test is ready behind one switch, after a pre-registered proving week (done, Dev, commit `ca12934`, branch `codex/production-correction-hedge-p0`, pushed, not deployed)

- Owner ask (Oct 25):
  - give the paper F&O book "5 more days to prove itself", then put ₹12.5k of real money on it for a week with the investment and risk guardrails relaxed;
  - "make an env variable that if set true, it will start trading this much amount, real money";
  - "will the entry and exit calculation still work?";
  - pure intraday F&O only, no expiry;
  - "this is important and critical, so do it wisely".
- Answer to the question: yes. The real test runs the same signal, strike, gates and exit ladder (`fno_entry_plan`, `fno_exit_rules`, the same `_manage_open_positions`). Only the lot count changes (always one), plus real fills and timing.
- Decisions (the system's, inside the owner's mandate):
  - **Mirror.** The test never decides a trade. It buys one lot of the contract the paper book just bought on the same bar, so the paper book's tiers, loss brakes and 15% halt decide for both.
  - **Scope.** NIFTY only: live exit evidence and recovery accept NFO only. Never on its expiry day, even if paper expiry entries are ever enabled. One open position; at most FNO_MAX_TRADES_PER_DAY entries.
  - **Buy.** A LIMIT at the fresh ask plus 2 ticks. Skipped when that ask is over 2% above the paper price, the quote is stale or one-sided, or the spread is over 1.5%. Cancelled after 30 s, never chased.
  - **Floor.** FNO_LIVE_TEST_FLOOR ₹7,000 (env): no new entries under it; the owner is told once a day.
  - **Relaxed, for the test only:** the 2% risk per trade, the pool gates and the go-live bar. Kept: own cash only (kite_client), the shared ledger reservation, LIMIT and MIS, the hard flat and the broker backstop.
- Found while preparing it: real-money gaps that never surfaced because no live F&O order has ever been placed. Production has 0 FNO_LIVE rows and an empty `account_cash_reservations`. All are fixed:
  - [x] O25-EX: a live exit that does not fill now completes.
    - Before: it waited 15 s at the bid, then left the order resting at a stale price with the exit claim held. No later pass acted, and its broker stop had already been cancelled.
    - Now (`fno_executor`): one SELL LIMIT, modified lower (0.5%, then 3%, then 10% or ₹5 under the bid). If still unfilled, it is kept on the claim (`fno_exit_intents.order_id`) and re-priced every pass, also after a restart (`follow_exit`, `_follow_working_exit`). Never a second SELL.
    - An exit proven never sent, or ended with nothing filled, frees its claim and is retried (`release_exit_intent`).
    - Before any real sell the broker's positions are read. If it holds none (sold in Kite, or squared off), nothing is sold and the claim stays for exit recovery (`_broker_holds_none`).
  - [x] O25-CASH: a filled buy's own-cash hold (`account_cash_reservations`) was never released. The day after a trade, every buy on the account would have been refused (the order had left the day's book, so the hold counted again). The engine's cancelled F&O buys were never released either.
    - Now `KiteClient.settle_entry_reservation` (via `FnoExecutor`) and the gateway's `releaseFilled` release a hold on a proven fill or zero fill. Anything unproven keeps it.
  - [x] O25-ROUTE: the Production engine sends orders straight from this host (KITE_BASE_URL is direct), while Kite accepts orders only from the registered static IPs. New KITE_ORDER_BASE_URL: only place, modify and cancel use it, so the relay can carry orders and quotes stay direct.
  - [x] O25-MGMT: turning a switch off stopped managing an open live position. Now an open FNO_LIVE position is always managed. Each position is exited the way it was entered (a PAPER-... row never by a real order; `_executor_for_position`).
- [x] O25-LT `fno_live_test.py`: FNO_LIVE_TEST_ENABLED / _CAPITAL 12500 / _FLOOR 7000 / _MAX_CHASE_PCT 0.02 / _ENTRY_BUFFER_TICKS 2.
  - `mirror_entry` is called by `fno_orchestrator._single_leg_entries` after a paper entry. It uses the same reservation, single-dispatch claim and outcome protocol as the other legs, arms the broker backstop, and logs every refusal as a FNO_LIVE signal row.
  - `live_pool` feeds the live leg, `performance` and the hourly report.
  - Owner lines read `💰 REAL MONEY ENTRY/EXIT` with the paper price beside them.
- [x] O25-PW `fno_proving_week.py`: the pre-registered proving week, rules fixed on Sunday Oct 25 before the first session.
  - Window: Oct 26–30, the paper single-leg book at one lot.
  - Verdict:
    - PROVED: at least one trade, one-lot net ≥ ₹0, clean operation, no drawdown halt;
    - NOT_PROVED: otherwise;
    - NO_EVIDENCE: no trade.
  - Shown beside it: what ₹12,500 would have done.
  - A 15:50 job (`fno_evening_report`) sends one owner message a day: the week on its days, and the real trades beside their paper twins.
  - CLI: `python -m fno_proving_week`.
- [x] O25-PF `fno_live_preflight.py`, run by the owner. It reads the route, own free cash and open F&O positions. `--test-order` adds one real BUY 20% under the bid, cancelled and read back.
- [x] Runbook: `docs/runbooks/fno-live-test.md`.
- Proving-week discipline: the paper single-leg entry and exit rules stay unchanged Oct 26–30, so the week scores one thing. Fixes to safety or plumbing are fine.
  - Deploying S23–O24i mid-week also moves the expiry cutoff in the delta/IV clock from 15:30 to 15:40 (`fno_chain`, O24-MC), a ten-minute change to time-to-expiry.
  - Best deployed before Monday's open, or after Friday's close.
- Files:
  - new: `python-engine/fno_live_test.py`, `fno_proving_week.py`, `fno_live_preflight.py`, `docs/runbooks/fno-live-test.md`;
  - changed: `python-engine/fno_executor.py`, `fno_orchestrator.py`, `fno_positions.py`, `kite_client.py`, `account_cash_reservations.py`, `performance.py`, `fno_hourly_report.py`, `scheduler_setup.py`, `config.py`;
  - gateway: `node-gateway/server/services/account-cash-reservations.js`, `executor.js`;
  - tests: new `python-engine/tests/test_fno_live_test.py` (16), `test_fno_proving_week.py` (6), `test_fno_live_preflight.py` (3); `test_fno_exit_recovery_boundary.py` (ladder); the census goldens; `node-gateway/server/tests/unit/executor.test.js` (+1).
- Tests: engine full suite (Dev, Windows, 9 min 47 s): 5,684 passed, 4 skipped, 1 collection error -- pytest collected `fno_live_test.py` (its name matches `*_test.py`) and ran its helper `test_equity` as a test; renamed `live_equity`. After that, `pytest fno_live_test.py fno_live_preflight.py fno_proving_week.py --collect-only` collects nothing, and the affected files (`test_fno_live_test` 16, `test_fno_proving_week` 6, `test_fno_live_preflight` 3, `test_fno_orchestrator`, `test_fno_hourly_and_scheduler`, `test_performance`) pass 128 of 128. Gateway: `executor.test.js` 64 passed (1 new test, 1 new assertion). The full gateway suite: 505 passed, 4 skipped, 18 failed in `db.test.js` and `backlog-reconciliation.test.js`, which cannot load better-sqlite3's native binding on this Windows Node 24 (an environment limit; the files are untouched). `releaseFilled` was checked against real SQLite in a throwaway container of the gateway image (Node 20, no network). No order was placed anywhere.
- Config and migration impact:
  - new settings: FNO_LIVE_TEST_*, FNO_PROVING_START / _SESSIONS, FNO_EVENING_REPORT_ENABLED, KITE_ORDER_BASE_URL;
  - new columns `fno_exit_intents.order_id`, `working_limit`, `exit_reason`, and `fno_positions.entry_order_id` read into `FnoPosition`;
  - new table `fno_evening_report_told`; new scheduler job `fno_evening_report` at 15:50.
  - With the switch off there is no trading change: the new exit ladder and position handling act only on FNO_LIVE positions, and none exist. The owner gets the 15:50 proving-week message Oct 26–30 once deployed.
- Rollout: with S23–O24i.
  - The switch goes on only after the verdict, the root `.env` route (`KITE_ORDER_BASE_URL=http://161.118.160.180:31527`), the preflight PASS and ₹12,500 of free cash.
  - Rollback: FNO_LIVE_TEST_ENABLED=false (entries stop; an open position is still managed), then revert.
- Remaining (owner):
  - the Oct 30 verdict and the decision;
  - deploy; the `.env` lines; run the preflight;
  - restricting the relay port 31527 to this host (plain HTTP on an open port).

## October 24 (night, 4) — O24i The F&O drawdown halt stays as it is and is no longer silent; the partner stays in English (done, Dev, commit `0b7d7b9`, branch `codex/production-correction-hedge-p0`, pushed, not deployed)

- Owner ask (Oct 24):
  - On the 15% drawdown halt: "this you decide with the vision in mind" (keep it, base it on a recent peak, or reset the paper starting point).
  - "The partner is in English language only": the partner's messages already are; nothing changes.
- Decision: **the halt stays as it is**: paper equity against the ₹2.5L allocation since inception, 15%, line ₹2,12,500.
  - The July – August losses were made by the same entry rule as today: 27 single-leg trades, 6 winners, about −₹26.8k; the defined-risk book −₹7.4k. The NIFTY opening-range signal has been unchanged since the Jul 22 RVOL fix (`fno_engine_mom`; the Oct 4 edit only added SENSEX's volume source). Later changes were sizing, exits and a re-entry confirmation after a stop (Oct 7).
  - So re-anchoring would hide a real record and loosen the one hard capital limit.
  - A recent-peak base is the same number today: equity has never been above the allocation.
  - For real money, a capital floor that a losing strategy cannot reset is the point of having one.
  - Since Sep 1 the books are positive (single-leg +₹3,764, defined-risk +₹7,238), so the floor is not in the way of a working strategy.
- Facts (Production, read-only, Oct 24):
  - equity ₹2,26,798, ₹14,298 above the line;
  - at one lot the Sep – Oct stop-outs averaged ₹2,321, so about six of them, net of any wins, would reach it.
  - Correction: O24h's README first said "two or three ordinary losses". Fixed there.
- [x] O24i-RA the halt is no longer silent (`fno_risk_alert.py`; `fno_orchestrator.run_fno_tick` after the exits are managed, unless FNO_DISABLE_PAPER).
  - Each F&O tick compares the paper book's risk state with the last one told: the adaptive size tier, and the entry halts (the drawdown halt, the daily, weekly and monthly brakes, the consecutive-loss pause, the two-strike day halt).
  - On a change, one owner message (`operator_alert.notify_operator`, event `fno_paper_risk_state`), with the equity and its distance to the 15% line. A drawdown halt adds: "Keeping, re-anchoring or ending the halt is your decision."
  - The state is kept in `fno_risk_alert_state`; a restart does not repeat it; a send that failed is tried again next tick.
  - The first look at a calm book (normal size, no halt) is only remembered. After deploy the owner gets one message: today the size is quarter (0.25x), equity ₹14,298 above the line.
  - It never raises into the tick.
- Files: new `python-engine/fno_risk_alert.py`; `python-engine/fno_orchestrator.py`; tests: new `python-engine/tests/test_fno_risk_alert.py` (3); `docs/research/fno/2026-10-24-entry-arms/README.md` (correction and decision).
- Tests: engine full suite (Dev, Windows, 9 min 32 s): 5,658 passed, 4 skipped, 1 failed — `test_kite_client.py::TestRateLimiter::test_management_priority_is_bounded_and_normal_work_is_fair`, a 10 ms timing test that fails under suite load (`kite_client.py` is untouched; it passed 8 of 8 runs alone, and `test_kite_client` + `test_fno_risk_alert` + `test_fno_orchestrator` together: 66 passed, 1 skipped). `test_fno_risk_alert` 3 passed. Engine only; no client change.
- Config and migration impact: no setting change. A new table `fno_risk_alert_state` (created on first use). One owner Telegram message per risk-state change.
- Rollout: with S23-O24h. Rollback: revert (the halt rules were never changed).

## October 24 (night, 3) — O24h The F&O shadow variants scored on real paths (the shipped entry stays best; the continuation is not supported); exit slippage measured; "check before you buy" for the partner (done, Dev, commit `b8cf7a8`, branch `codex/production-correction-hedge-p0`, pushed, not deployed)

- Owner ask (Oct 24): improve the system for more profit and smaller losses, flexible, never fitted to one thing. The owner agreed to four items:
  - (1) score the F&O shadow variants on real price paths;
  - (2) a trend-day participation variant, in shadow first;
  - (3) measure exit slippage;
  - (4) "ask before you buy" for the partner.
  - Momentum and Penny stay as they are (they cost nothing, rarely trade, and keep gathering evidence); no development time goes to them.
- Found (Production, read-only):
  - `fno_shadow` recorded only a target-hit scenario: FNO_BASE 43 of 43 "wins", +₹85,689, with no stop, trail or forced close replayed.
  - The F&O single-leg book since Sep 1: 18 trades, +₹3,765 after ₹1,345 of charges. Trail exits +₹13,767, every other exit −₹10,002. 5 of 8 weeks were negative.
- [x] O24h-SA entry-signal arms in the full-policy replay (`ReplayPolicy.signal_variant`; FNO_SIG_CONFIRM_1, _OR_20, _OR_45, _CONTINUATION at the live fast-exit cadence).
- [x] O24h-CT `FNO_CONTINUATION` (`fno_shadow`, `pullback_resumed`, `pullback_atr` 0.25), frozen in e37504f before any replay of it. It is recorded live in shadow from deploy.
- [x] O24h-ST study `fno-entry-t2`, frozen (e37504f, pushed) and scored once (`docs/research/fno/2026-10-24-entry-arms/`: README.md, study/results.json).
  - Data: 28 archived NIFTY sessions (Sep 10 – Oct 23).
  - Development, Sep 10 – Oct 9: BASELINE +₹7,286 (12 trades); CONTINUATION −₹4,846; OR_20 +₹4,597; OR_45 +₹5,655; CONFIRM_1 +₹3,921 (3 trades).
  - Decision, Oct 12 – Oct 23: BASELINE and CONTINUATION each 1 trade, +₹3,515; OR_45 3 trades, +₹3,449; OR_20 and CONFIRM_1 none.
  - Verdict: **NOT SUPPORTED, the continuation stays off.** It fails "net without the best winner > 0" and "beats BASELINE". No variant beats the shipped entry.
  - Parity: the development baseline matches 9 of 12 live NIFTY trades.
  - The decision window is thin: one NIFTY trade, and 3 of its 4 live trades were SENSEX, which is not replayed.
- [x] O24h-HL the drawdown halt cliff, attributed (`halt_attribution.py` / `.json`, not the decision).
  - The continuation's early extra losses put paper equity under the 15% drawdown halt (₹2.125L on ₹2.5L). The halt then blocked the three trend-day winners the baseline took (Sep 28, Sep 30, Oct 1: +₹11,516).
  - With the halt removed (development): BASELINE +₹6,922 (13 trades), CONTINUATION −₹93 (20 trades; −₹7,201 without its best winner). The rule itself loses about ₹7,000; the halt made it worse.
  - The live paper book (Production, read-only, Oct 24): ₹2,26,798, i.e. ₹14,298 above that halt. The halt counts every loss since inception, July included (single-leg −₹23,012 over 45 trades).
  - Changing the halt is the owner's decision; this slice reports it and changes nothing.
- [x] O24h-XS `fno_exit_report.py` (read-only CLI): how far each paper exit with a level (underlying stop, trail, premium stop) filled past it, with a rupee estimate at the entry delta.
  - On Production's data: all 7 such exits since Sep 1 filled past their level, about ₹2,235 in all. The worst was Oct 7: 26 points past the stop, ≈ ₹956.
  - All 7 were before the 10 s fast exit (on since Oct 9; until then exits were checked every 90 s). No stop or trail exit has happened since, so the 10 s pass is not yet measured. Tick exits only if it shows real slippage.
- [x] O24h-PB "check before you buy" (`partner_watch.parse_check`, `check_message`, `check_text`, `answer_check`; `partner_fill_capture.handle_update`; kind CHECK).
  - The partner sends "check 22300 pe" (with a price and lots if they like). The reply is the plan for that option bought now, at their price or the ask just read (fresh only), from the same `build_plan` as the after-buy PLAN:
    - the plan stop and the loss there, the target zone;
    - the normal 5-min swing, the move in the last 15 min, the future's trend, the bid-ask gap;
    - only the warnings that apply: a run ≥ 20% in 15 min (the review's chased spike), the last trade a loss within 30 min, a size much bigger than usual, the day's trade count, expiry today;
    - "A check, not a tip".
  - Without a fresh price and none given, no rupee figure is made up.
  - It is never recorded as a trade, goes through the outbox even when quiet (they asked), and WATCH_ON tells them about it.
- Disagreed or deferred, with reasons:
  - The 45-minute opening range is the closest variant (positive in both windows). It loses without its best winner on development and is not promoted. Every variant keeps being recorded for forward scoring.
  - The partner's language (Hindi, Gujarati) is waiting for the owner.
  - Judgment shadows (protect a profit, trail, idea broken) are scored after about 20 live trades.
- Files:
  - `python-engine/fno_shadow.py`, `python-engine/fno_policy_replay.py`;
  - new: `python-engine/fno_exit_report.py`;
  - `python-engine/partner_watch.py`, `python-engine/partner_fill_capture.py`, `scripts/run_preregistered_study.py`;
  - `docs/research/fno/2026-10-24-entry-arms/` (README.md, study/freeze.json, study/results.json, halt_attribution.py and .json);
  - tests: `test_fno_shadow.py` (+2), `test_fno_policy_replay.py` (+1), new `test_fno_exit_report.py` (2), `test_partner_watch.py` (95 → 98).
- Tests: engine: the full suite 5,656 passed, 4 skipped, exit 0 (573 s); the partner and exit-report files 225 passed with thread and unraisable warnings as errors; study fno-entry-t2 scored once (10 reports) and the halt attribution run. No live broker or Telegram round trip (Saturday).
- Config and migration impact: none. A new message kind CHECK in `partner_watch_messages`, and one more shadow row per F&O tick.
- Rollout: with S23-O24g. Rollback: revert.
- Remaining:
  - the owner's call on the drawdown halt;
  - forward scoring of the entry variants on new sessions (a new freeze);
  - the fast-exit slippage once stop or trail exits happen;
  - the partner's language.

## October 24 (night, 2) — O24g Stops moved together told together; "no stop" claimed only from a GTT list read then; the order stream (off) and delivery measurement (done, Dev, commit `797d69b`, branch `codex/production-correction-hedge-p0`, pushed, not deployed)

- Owner ask (Oct 24): the audit agent's fifth review (on db167ed) reproduced one remaining edge case: GTTs moved down together were told for one of them only. Fix it with regression cover. Then prioritise streaming and live delivery measurements: faster, reliable account awareness over more restrictive filters.
- Verdict: real. Writing the tests found two more of the same family, and a stale-list gap. All are fixed.
- [x] O24g-MV every stop moved down in one read is one LOWERED message, judged together (`moves_reason`, `moved_text`, `_moves_why`, `_held_moves`, `_lowered(moves)`, `_changed`, `_replacement`, `_b_lowered`, `_guard(moves)`, `_rest_note(ids)`).
  - Audit: when several GTTs moved down in one read, only `moved[0]` was looked at; the others were lost, and the bigger move could be the one dropped. Test: ₹70 → ₹69 and ₹68 → ₹60; only the first was told.
  - Found:
    - two SL orders modified down in one read. Whichever came first in the order book counted as "the first move"; the other (₹68 → ₹60) was dropped as within the plan.
    - after a trade's first move, a small move and one under the plan stop in the same read. The one under the plan was never looked at.
  - Now step 1 collects the SL orders modified down for each holding. The guard adds the GTTs modified down and a single replacement. All go in one message for the read: "you moved 2 stops down: ₹70 → ₹69 for 65 and ₹68 → ₹60 for 65. If they are hit, on your 130: …".
  - The reason is the most serious of the read's moves (GUARD, then BELOW_PLAN, then FIRST), and it names the moves it is about ("₹55 is under your plan stop ₹59.4").
  - At send time, only the moves whose stop still waits at its new level are told, and the reason is judged again on them.
  - An SL moved down while the GTT list cannot be read is still told.
  - Several stops cancelled and replaced (O24f, never paired) stay one `changed_text` message.
- [x] O24g-FR a claim of no stop (NO_STOP, PARTIAL, REMOVED), or a sell-order claim that counts a GTT (EXCESS, ORPHAN, PRODUCT), is made only from a GTT list read in that tick, the first time it is due (`_cover_claim`, `_counts_gtt`).
  - Why: the list is reused for 20 s (60 s for the sell-order check). A GTT placed after the last read got "no stop order yet"; one deleted after it still counted in "sell orders add up to 130". Both reproduced.
  - Cost: one GTT read on the tick a claim first comes due. Without that read (it failed, or no budget is left), the claim waits a tick.
- [x] O24g-ST the order stream, a doorbell, off by default (`partner_watch_stream.py`; `partner_watch.wake`, `_woken`, `_tick_lock`; `PARTNER_WATCH_STREAM_ENABLED` false, `PARTNER_KITE_WS_URL`; `websockets==12.0`).
  - Kite pushes the partner's order updates on its websocket. On one, the watch reads the book at once instead of at the next 5 s tick. The stream is never trusted for state: a missed, repeated or out-of-order update changes only when the next read happens, and the 5 s reads go on.
  - Behaviour:
    - one tick at a time: a scheduled tick skips while another runs, and a woken one waits for it;
    - woken ticks are at least 1 s apart;
    - a refusal (HTTP 401 or 403: a plan without the websocket), or no library, is REFUSED, retried every 30 min;
    - any other failure reconnects after a backoff of 1 s, doubling to 60 s;
    - with no frame for 10 s, it reconnects;
    - a new login reconnects with the new token;
    - it stops when the login is gone or at 15:40.
  - The access token is in the URL, so it is never logged (errors by type or HTTP status only).
  - Tested offline: a fake socket (drops, backoff, refusal, missing library, a new login, the close) and a real local websocket server for the whole path (an order update in, LOWERED out, found by the woken tick).
- [x] O24g-DM delivery measurement (`detected_by`, `_TickStats`, `partner_watch_report.py`).
  - Each outbox row records whether a 5 s tick (poll) or a woken tick (stream) found it.
  - Each process saves its day's tick statistics every 60 s as `ticks:<day>:<process start>`: how ticks ended, tick and order-read milliseconds, and the stream's state, connections, updates, errors and exchange-to-receipt lag.
  - `python -m partner_watch_report [FIRST [LAST]]` opens the database read-only and prints, per kind, the outcomes and two timings (p50 / p95 / max):
    - seen: the event to the tick that found it;
    - sent: that tick to Telegram's acknowledgement.
  - `watch_status()["stream"]` gives the stream's state.
- Disagreed or deferred, with reasons:
  - Switching the stream on is the owner's call, once the partner's key has a plan with the websocket and one live day shows it LIVE in the report, with stream-found messages seen sooner.
  - What streaming can change: it shortens "seen" for messages told at once (PLAN, LOWERED, REFUSED: up to 5 s, about 2.5 s on average, today). It does not change the deliberate waits (UNFILLED 10 s, the 20 s grace, NO_STOP 120 s). The report will show which matters.
  - Streaming option prices (quotes for the held options) is not built. It needs the paid plan's market data and a subscription; the doorbell comes first.
  - No new trading filters (the audit's point, agreed).
- The intermittent failures:
  - `test_a_send_cut_off_part_way_is_not_sent_twice` (O24f) has not come back. Every run this round kept its full output.
  - `test_the_ticks_reads_share_one_budget` failed once, on db167ed's code, while the full suite ran beside it. Its bound is 0.9 s on a 0.6 s budget, so it is load-sensitive. With nothing else running it passed 5 of 5 on that code and 5 of 5 on this one.
  - The first full run's only failure was this round's new `test_a_refused_stream_waits_long_and_never_logs_the_token`. It read the log through capsys, which other tests' logging set-up bypasses: empty in the suite, full alone. It now records the stream module's own log lines. It passes alone, and after the main-surface tests (11 passed).
- Files:
  - `python-engine/partner_watch.py`;
  - new: `python-engine/partner_watch_stream.py`, `python-engine/partner_watch_report.py`;
  - `python-engine/config.py`, `python-engine/requirements.txt`;
  - tests: `python-engine/tests/test_partner_watch.py` (88 → 95), new `python-engine/tests/test_partner_watch_stream.py` (7).
- Acceptance: each issue is a tick test that fails on db167ed:
  - `test_gtts_moved_down_together_are_all_told`;
  - `test_a_move_under_the_plan_is_told_when_another_stop_moved_in_the_same_read`;
  - `test_sl_orders_moved_down_together_are_one_message`;
  - `test_a_no_stop_alarm_is_never_built_on_a_gtt_list_read_before_the_gtt_was_placed`;
  - `test_a_sell_order_alarm_is_never_built_on_a_gtt_list_read_before_the_gtt_went`;
  - plus the wording and retry tests.
- Tests: engine: the full suite 5,648 passed, 4 skipped, exit 0 (576 s), after one test fix (an earlier run: 5,647 passed, 4 skipped, 1 failed, the refused-stream test reading the log through capsys); the watch, stream, partner and scheduler files 244 passed with thread and unraisable warnings as errors. The new tests against db167ed: 7 of the watch file's 95 fail there (the five issues, the wording, the retry). Client unit 65 passed. No live broker, websocket or Telegram round trip (Saturday).
- Config and migration impact:
  - new settings `PARTNER_WATCH_STREAM_ENABLED` (false) and `PARTNER_KITE_WS_URL`;
  - a new dependency, `websockets==12.0`: the engine image must be rebuilt. The engine imports it only when the stream connects;
  - a new column `partner_watch_messages.detected_by`, added by `init_partner_watch_db`;
  - new state keys `ticks:*`: one write a minute while the watch runs.
- Rollout: with S23-O24f (rebuild the engine, then the gateway); the stream stays off.
- Switching the stream on:
  - the partner's plan has the websocket;
  - `PARTNER_WATCH_STREAM_ENABLED=true` in the root `.env`;
  - restart the engine;
  - `watch_status` shows the stream LIVE, and the report's Stream line has connections and order updates.
- Rollback: the flag off, or revert the commit.
- Remaining:
  - the first live days, through `partner_watch_report`;
  - the stream's live check (owner, with the plan);
  - quote streaming;
  - judgment messages stay shadow until scored.

## October 24 (night) — O24f The watch's sell-order and replacement boundaries: "none held" only with evidence, sell orders matched by product, a replacement matched to the stop it replaced; the watch says when it cannot see (done, Dev, commit `320fe20`, branch `codex/production-correction-hedge-p0`, pushed, not deployed)

- Owner ask (Oct 24): the audit agent's fourth review (through 764055f) found three remaining issues, two in the new sell-order alarms and one in replacement-stop reporting. It also suggested enrichments. Fix bugs that are real, enrich where it is worth it, disagree where right.
- Verdict: all three were real. Each is now a tick test that fails on 764055f's `partner_watch.py`. Writing the tests found three more of the same family; those are fixed too (O24f-RP, O24f-GF).
- [x] O24f-NH "you hold none" only with evidence (`none_held`, `orphan_text(basis)`, `_b_orphan`, `View.positions` / `View.carried_known`).
  - Audit 1: with Zerodha's positions never read today, an SL protecting a holding from an earlier day was called an orphan: "you hold none now … Cancel it if the trade is over."
  - The bases:
    - ZERODHA: the positions, read within POSITIONS_MAX_AGE, show none. Said as fact.
    - ORDERS: they cannot be read now, but today's overnight list was read.
    - UNREAD: they were not read today.
  - Without ZERODHA the message says the holding could not be checked, and that the order is the holding's protection if it is held: keep it. It is never "cancel it".
- [x] O24f-PR sell orders matched by exchange, option and product throughout (`_sell_products`, `_exits`, `product_text`, `_b_product`, PRODUCT; each exit carries its product).
  - Audit 2: 65 held as NRML with an SL for 65 as MIS gave no alarm. The excess check went by product, but the orphan check skipped any option held in any product.
  - Now a sell of a product not held, on an option held as another, is PRODUCT: "It would not sell them: if it triggers, it opens a new MIS short of 65 … A stop for them has to be NRML."
  - An option held in no product is still one ORPHAN for all its sells. PRODUCT is a loss alarm, never muted.
  - Broker margin checks may refuse such an order; the mismatch is said either way.
- [x] O24f-RP a replacement matched to the stop it replaced (`_track_stops`, `_all_stops`, `_replaced_lower`, `changed_text`, `_Guard.seen/withdrawn/fresh/tracked`, `REPLACE_WINDOW` 120 s).
  - Audit 3: stops for 65 at ₹95 and 65 at ₹90. The ₹95 one was cancelled and replaced at ₹70. It was told as ₹95 → ₹90: the matcher took the highest stop left, not the new one.
  - Also found: cancelling one of two stops, with nothing new, was already told as a move ₹95 → ₹90. So was an SL cancelled beside an older, lower GTT. And a replacement for more units than the old stop sold was costed on all of them.
  - Now stops taken away and stops placed are kept for 120 s, whether seen in one read or several and in either order:
    - one taken away and one placed lower is that stop moved, for the units both sell (`_b_lowered` caps them at the context's);
    - several are told as one change at their average triggers, without pairing them;
    - a stop taken away with nothing placed is not a move (REMOVED and PARTIAL tell it).
  - "Placed" means new to every stop the holding had (its SL orders and the GTT list), not new to what `cover_of` needed to read.
  - A GTT modified down (Kite keeps its id) is now a move too.
  - A restart's first read only remembers. The memory is kept in `partner_watch_state`.
- [x] O24f-GF a fired GTT is told by its order's fate (`_lost_why(gtts=)`, `removed_text` SOLD via GTT and FIRED_CANCELLED). A GTT that fired, sold 30 and had the rest cancelled was told as "your GTT at ₹60 is no longer active". Now: "your GTT at ₹60 fired and sold 30; the other 35 have no stop now."
- [x] O24f-HL watch health: BLIND and BACK (audit enrichment 2). Code: `_health`, `_read_failed`, `_State.unread/blind`, `BLIND_AFTER`, `watch_status()["unread"]`, the page's `watchNote`.
  - BLIND is told once a read the watch needs keeps failing:
    - the orders, for 60 s;
    - the positions, for 120 s while the overnight list is unknown;
    - the GTTs, for 120 s while a holding's protection is unknown.
  - BACK is told when that read works again, only if its BLIND was sent.
  - Both are fixed texts that are always sent, quiet or not.
  - A failure shorter than that, a read skipped for the budget, and a lost login (RECONNECT) are not told.
  - A GTT read skipped for the budget now keeps the last list instead of dropping it.
- [x] O24f-UN uncertainty said where it decides the advice (enrichment 1).
  - EXCESS adds where the count comes from (`_count_note`).
  - One option held as MIS and NRML is two holdings, named with the product ("NIFTY 22300 PE MIS"; `Holding.twin`, `_name`).
  - Units Zerodha shows in a product today's orders did not buy, while the orders' own product shows fewer, are said to look converted (`Holding.converted`).
  - WATCH_ON, the quiet toast and the page note list the sell-order alarms and BLIND.
- [x] O24f-LC lifecycle tests (enrichment 3), one sequence each:
  - failed position reads with an overnight holding;
  - MIS and NRML in one option;
  - several stops, replacements and part quantities;
  - a product conversion;
  - a GTT that fires, sells in part and has the rest cancelled;
  - a GTT modified down;
  - an orders outage with a stop moved during it.
- Disagreed or deferred, with reasons:
  - Trading judgement (enrichment 4: keep strong winners through normal pullbacks, a thesis that fails, reduce vs exit, a tip entered late). Agreed it comes next after streaming. It needs recorded live days (`partner_watch_looks`), and the watch is not deployed yet. It will be scored on winners cut short as well as losses avoided, after charges, before anything is sent.
  - The page shows what cannot be read only while the watch is on. The partner reads the page in the evening, so Telegram BLIND is the partner's signal; the page line is for the owner.
  - No SHORT alarm for a position already short: for this account Zerodha refuses the margin (Oct 23).
- The intermittent failure, still unexplained:
  - Its test is now named: `test_a_send_cut_off_part_way_is_not_sent_twice`. It failed once in a run of the six partner test files, with thread and unraisable warnings as errors; that run's output was not kept.
  - Every repeat since keeps each failing run's full output (scratchpad `flaky/loop.sh`, `loop2.sh`). All were clean:
    - 40 runs of the watch file on 764055f;
    - 80 runs of that test alone;
    - 15 runs of the six files.
  - A probe showed only the outbox task pending at its simulated shutdown in 8 of 8 runs, so a cancelled shadow-looks write is ruled out as the cause.
  - Clean repeats do not show it fixed. Keep `-rA` and the full output on every repeat.
- Files:
  - `python-engine/partner_watch.py`;
  - `node-gateway/client/src/utils/partnerReview.js`;
  - tests: `python-engine/tests/test_partner_watch.py` (74 → 88), `node-gateway/client/tests/partnerReview.test.mjs`.
- Acceptance:
  - each audit issue has a tick test that fails on 764055f:
    - 1: `test_a_sell_order_is_not_called_an_orphan_when_the_positions_could_not_be_read`;
    - 2: `test_a_sell_order_of_another_product_than_the_one_held_is_told`;
    - 3: `test_a_replacement_stop_is_matched_to_the_stop_it_replaced` (one read, and two);
  - the found ones:
    - `test_several_stops_replaced_together_are_one_change`;
    - `test_a_stop_cancelled_with_an_older_gtt_left_is_not_a_stop_moved_down`;
    - `test_a_gtt_moved_down_is_a_stop_moved_down`;
    - `test_a_gtt_that_fires_fills_in_part_and_is_cancelled`;
    - `test_a_replacement_for_more_units_is_told_for_the_units_the_old_stop_sold`.
  - The new test file against 764055f: 17 of 88 fail there, 71 pass.
- Tests: engine: watch tests 88 passed (thread and unraisable warnings as errors); the six partner test files 204 passed; scheduler closures 26 passed. Full engine suite: 5,629 passed, 4 skipped, 5 errors (593 s). The 5 errors were all in `test_session_phase_golden.py`, at setup: its child Python failed to start (exit 0xC0000142) when Claude Code stopped the run's shell for low memory, and pytest went on to finish. That file then passed alone (7 passed). Client unit 65 passed. No live broker or Telegram round trip (Saturday).
- Config and migration impact: no setting, schema or scheduler change. New message kinds PRODUCT, BLIND and BACK in `partner_watch_messages`. The guard memory in `partner_watch_state` gains `seen`, `withdrawn`, `fresh` and `tracked`; an older memory without them starts a fresh look.
- Rollout: with S23-O24e (rebuild the engine, then the gateway). Rollback: revert the commit.
- Remaining:
  - streaming (next slice, offline tests for reconnects, duplicates and ordering first);
  - the first live days:
    - BLIND / BACK counts and how long reads fail;
    - PRODUCT / ORPHAN bases;
    - `partner_watch_looks` against the 15 s;
  - judgment messages stay shadow until scored.

## October 24 (late) — O24e The watch's last races closed: a message is sent only from the latest read, a plan never without its message, a moved stop for its own units, protection named without a level; sell orders that could sell short (done, Dev, commit `79629e5`, branch `codex/production-correction-hedge-p0`, pushed, not deployed)

- Owner ask (Oct 24): the audit agent's third review of the watch (on ad6190e) reproduced four remaining gaps. It also corrected a freshness statement and suggested next enrichments. Fix what is real, enrich where it is worth it, disagree where right.
- Verdict: all four gaps were real. Each is now a test that fails on ad6190e's `partner_watch.py`. The freshness wording was imprecise and the threshold was not deliberate: both corrected.
- [x] O24e-RV the view a message is built from must still be the latest when it is sent (`_deliver`, `_still`, `_mark`, `_unmark`, `_build(view)`, `BUILD_TRIES` 3).
  - Audit 1: the sender checked the view before building. The build then awaited the database and prices, a newer read showed the trade closed, and the old text still went out.
  - Now the view is checked again after the build, and again after the row is marked "attempting". If a newer read came, the row goes back as it was and the message is built again from it (and dropped if no longer true). After 3 tries it waits for the next tick.
  - Changes after dispatch has started cannot be undone. Changes already seen are respected.
- [x] O24e-AT a plan version and the message it owes in one transaction (`_store_plan(announce=)`, `_insert_outbox`, `_noted`).
  - Audit 2: version 1 was stored and its PLAN written separately. One failed write left a plan that never got its message, and nothing repaired it. The same applied to an ADDED version.
  - Now PLAN and ADDED go into the same transaction as their version. A failed write leaves neither, and the plan (or the size change) is seen again on the next tick.
  - A database error in one trade's plan read or revision no longer stops the tick (`partner_watch_plan_read_failed`, `partner_watch_revise_failed`).
- [x] O24e-LU a moved stop is told for its own units, bound to its own order (`lowered_text(units=, cover=, stop_id=)`, `_rest_note`, `_result_for`, `_b_lowered`).
  - Audit 3: 130 held, two stops of 65 each, one moved from ₹95 to ₹70. That adds 25 × 65 = ₹1,625 of gross loss if hit; the message modelled 130 units.
  - Now: "you moved your stop for 65 of your 130 down … on those 65: … The other 65 keep their stop at ₹90."
  - The retry is valid only while that same order (`stop_id`) waits at the new level, not any stop at that price.
- [x] O24e-NL protection named when there is no plan stop (`_no_level_line`, `plan_summary`, `added_text`).
  - Audit 4: with all 65 covered by an SL at ₹95, a plan without market data said "At risk: the whole ₹6,500 you paid. Decide your stop and place it now."
  - Now: "Your SL at ₹95 covers all 65. I could not work out a fresh reference level (no market data). If it sells there: about −₹… with charges; in a fast fall an SL order can trigger and still not fill."
  - A part covered gets the units without a stop and what is at risk on them. Unread GTTs: "unless a GTT covers it". The swing-as-big-as-the-price case is handled the same way.
- [x] O24e-FR freshness made deliberate. `QUOTE_MAX_AGE` 60 s → 15 s, the same as our own read (`QUOTE_FRESH`).
  - The rule is both of these:
    - our quote read is at most 15 s old;
    - the exchange's last quote update is at most 15 s before we received it.
  - Reason: the partner's index options are quoted many times a second. A quote unchanged for 15 s is a stalled feed, or a contract too thin to place a level against. It then gets the reference wording, not an instruction.
  - `partner_watch_looks` keeps both clocks, so the threshold is checked on the first live days.
- [x] O24e-EX sell orders that could sell short (`exits_of`, `_exits`, `excess_text`, `orphan_text`, EXCESS / ORPHAN; GTTs refreshed every 60 s, `GTT_REFRESH`).
  - EXCESS: SL, limit and GTT sells (an OCO counted once) add up to more than is held, for 20 s.
  - ORPHAN: sells still waiting on an option no longer held, e.g. a stop left after selling at market, or an old GTT.
  - Both are loss alarms, never muted.
  - Evidence: on Oct 23 Zerodha refused a second sell order from the partner for exactly this, because their cash could not margin the extra as a short. So for this account the alarm matters mostly for GTTs (nothing is reserved until they fire) and for a larger account.
- [x] O24e-TS the FULL-but-lower stop is compared with the plan stop, no longer followed by "Raising its trigger to ₹X keeps the loss to the plan": a tighter stop is not a better one until it is scored (audit enrichment 5).
- Disagreed or deferred, with reasons:
  - Plans for carried positions (audit enrichment 3): Production has one day of the partner's positions (Oct 23). All 9 were NRML and all were closed that day; none were carried. Deferred until a carried position is seen.
  - "What changed since my last message" (enrichment 1): every live message already leads with the partner's latest action ("You added…", "you moved your stop…", "your stop at … is cancelled", "N still held: you sold…"). A partial sale stays silent unless it changes protection, so that is not more alerts.
  - Pre-buy check (enrichment 4) waits for the owner's pick (the O24b list).
  - Streaming (enrichment 6): agree it is next, with offline tests for reconnects, duplicates and ordering first. It needs a new websocket dependency, an image rebuild and the partner's paid plan; proposed as the next slice.
  - Stop changes as decisions (enrichment 5): the shadow scoring must count winners stopped early as well as losses avoided before any tighter stop is called better.
- Files:
  - `python-engine/partner_watch.py`;
  - tests: `python-engine/tests/test_partner_watch.py` (62 → 74).
- Acceptance:
  - each audit gap has a tick test that fails on ad6190e:
    - 1: `test_a_message_whose_trade_closed_while_it_was_built_is_not_sent`;
    - 2: `test_a_plan_is_never_stored_without_its_message`;
    - 3: `test_a_stop_moved_for_part_of_a_holding_is_told_for_that_stop`;
    - 4: `test_a_plan_without_market_data_names_the_stop_already_there`;
  - plus pure tests for each text;
  - interruption tests:
    - a newer read while the row is marked;
    - a send cut off part way (stays "attempting", not repeated after a restart).
- Tests: engine full suite 5620 passed, 4 skipped, exit 0 (9 m 41 s, `winvenv/Scripts/python -m pytest -q`); `tests/test_partner_watch.py` 74 passed (62 before), 60 repeated runs clean after one unreproduced failure (see Remaining); client unit 65 passed (no client change). The new tick tests were run against ad6190e's watch: the four audit gaps and the two new alarms fail there for their reasons; the cut-off-send test passes there too (O24d was already conservative). No live broker or Telegram round trip (Saturday, market closed).
- Config and migration impact: no setting, schema or scheduler change. One more GTT read a minute while logged in. New message kinds EXCESS and ORPHAN in `partner_watch_messages`.
- Rollout: with S23-O24d (rebuild the engine, then the gateway). Rollback: revert the commit.
- Remaining:
  - streaming (next slice);
  - the first live days:
    - `partner_watch_looks` received_at − quote_at against the 15 s;
    - `partner_watch_messages` outcomes (superseded, expired) and the EXCESS / ORPHAN counts;
  - judgment messages stay shadow until scored.
  - one run of `tests/test_partner_watch.py` (of about 66 that day) failed once, and 60 repeats did not reproduce it; its traceback was not kept. Repeat it with `-W error::pytest.PytestUnhandledThreadExceptionWarning`, and fix the cause if it returns.

## October 24 (night) — O24d The watch's advice stays with the partner's position: what already protects it, what is still held, a fresh price, its own trade (done, Dev, commit `677c630`, branch `codex/production-correction-hedge-p0`, pushed, not deployed)

- Owner ask (Oct 24): the audit agent reviewed O24c (7d0cb6f, 2effb5d) and found seven more gaps before the watch is production-ready. Fix those that are real, enrich where it is worth it, disagree where right.
- Verdict: all seven were real. Each is now a test that fails on 2effb5d's `partner_watch.py` (probe: 12 new tick tests fail there for the audit's reasons; the lifecycle test is a regression guard and fails there only on the new cover line).
- [x] O24d-SA stop advice that starts from what protects the units (`stop_advice`, `plan_text(cover=)`, `plan_summary`).
  - Audit 1: a trade fully covered by an SL at ₹95 was told "Place an SL sell now: trigger ₹80".
  - FULL with a stop at or above the plan stop: "already covers all 65 … no second SL is needed".
  - FULL with a lower stop: the result at it against the plan stop. With a fresh price, raising it is named.
  - PARTIAL: an SL for the units left only.
  - UNKNOWN (GTTs unread): "if you have no stop yet".
  - ABSENT: "Place an SL sell now" against a fresh price only.
- [x] O24d-OB the outbox (`partner_watch_messages`: `context`, `episode`, `priority`; `_enqueue_many`, `_drain`, `_deliver`, `_build`, `_BUILDERS`, `View`).
  - Audit 2: a plan computed beside the tick was sent after the partner had sold. Audit 6: a retry lived only in memory, so a restart lost it.
  - The tick finds what to say and stores the key and context. The text is built just before sending, from the latest tick's view.
  - Not true any more (the trade closed, a stop is back, the size changed): `superseded`, not sent.
  - No fresh view (`VIEW_FRESH` 15 s, and not the read before the current tick's): it waits.
  - One sender, most urgent first. A provably unsent message is rebuilt and sent again after RETRY_GAP, within LIFETIME_SEC and MAX_ATTEMPTS. This survives `reset()` or a restart.
  - The sender, the plans and the looks go through `background_tasks.spawn` (T22-BG).
- [x] O24d-EP one trade, its own warnings (`_episode`, `_Guard` per episode, `guard:<episode>` in `partner_watch_state`).
  - Audit 3: a removal key was the option plus an in-memory counter, so a later trade in the same option (or a carried position the next day) lost its warning.
  - Keys name the day and the trade (the opening buy's order id, or the carried position) and the incident:
    - NO_STOP: the size;
    - PARTIAL: the size and what covers it, or the stops lost since it was full;
    - REMOVED: the stops lost.
  - What covered each trade is kept in `partner_watch_state`. A stop cancelled while the watch was down is REMOVED after the restart. Before, a no-stop warning already sent for the trade hid it.
- [x] O24d-RC one reconciled count (`_start_plan(holding)`, `_plan_of(size=)`, `_revise`, `_current`, `_held_line`).
  - Audit 4: Zerodha showed 65 and the orders 130. The plan and its loss used 130.
  - Plan versions take the quantity and average of what is held (Zerodha's when it differs). `bought`/`sold` stay the orders'.
  - Every message uses the held count. The PLAN says what was bought apart from what is held: "65 still held: you sold 65 at ₹80, +₹… with charges", or Zerodha's count note.
- [x] O24d-FR a level is an instruction only against a fresh price (`stale`, `level_state(..., now)` → STALE, `_unchecked`, `exit_fill`, `_sell_now`).
  - Audit 5: with no quote, or an hour-old exchange quote checked as VALID, the plan still said "Place an SL sell now".
  - STALE when:
    - our read is older than QUOTE_FRESH (15 s); or
    - the exchange's quote time is more than QUOTE_MAX_AGE (60 s) before its receipt.
  - An unchecked level is "the plan stop ₹X is from HH:MM:SS … check the option is still above ₹X before placing an SL there".
  - Quotes keep the bids shown (`_top` `bids`). Selling now is priced against their sizes:
    - "into the bids (₹A down to ₹B)";
    - or "the bids shown take only N of your Q … or worse".
- [x] O24d-TB one budget per tick (`_book(path, deadline)`, `MIN_READ_SEC`, `TICK_BUDGET_SEC` 4 s, `DELIVERY_INLINE_SEC`, `_wait_within`, `_flush`).
  - Audit 7: each read had its own 4 s, and the tick awaited every Telegram send.
  - Reads and waits share the budget. An optional read with less than 0.5 s left waits for the next tick and keeps the last result: trades, positions, GTTs, cash.
    - A failed trade-book read keeps the last book (it only grows), so it no longer drops to order-level fills.
    - Positions older than 2 min confirm nothing.
    - Cash is tried 3 times while unknown.
  - Sending and the shadow looks go beside the tick.
- [x] O24d-AD after an add, how much of the new size a stop covers ("A stop covers 65 of the 130 now held").
- [x] O24d-OC (`partner_coach._off_card_plan`): an off-card trade with the partner's own SL is no longer said to have "no written stop".
  - The review says what Zerodha shows: own stop and when, none placed, or not known.
  - The card rule stays the owner's, kept apart from whether that stop was good.
- Disagreed or deferred, with reasons:
  - Streaming: agree it is next, and that reconnects, duplicates and out-of-order updates can be tested offline. Not in this slice:
    - it needs a new dependency (no websocket client is installed) and an image rebuild;
    - Kite's websocket comes with the partner's paid plan.
    - The outbox and view are where a stream plugs in: an order update can wake a tick, and REST stays the truth.
  - Origin labels (self-directed / tip) cannot be known without asking the partner. The review now states the partner's own plan as Zerodha shows it. Decision-quality scoring is deferred.
  - Hold / reduce / exit judgement: still shadow until scored on fresh, declared days. Scoring must count winners cut short as well as losses avoided.
  - "Check before buying" (the owner's O24b list, item 4) waits for the owner's pick.
  - Critical alarms stay new messages, not edits.
- Files:
  - `python-engine/partner_watch.py`, `python-engine/partner_coach.py`;
  - tests: `python-engine/tests/test_partner_watch.py` (45 → 62), `python-engine/tests/test_partner_coach.py`.
- Acceptance: each audit point has a test that fails on 2effb5d and passes now:
  - 1: `test_the_plan_never_asks_for_a_second_sl…`, `test_a_trade_already_protected…`;
  - 2: `test_a_plan_ready_after_the_trade_closed…`, `…after_a_partial_sale…`;
  - 3: `test_a_second_trade_in_the_same_option…`, `…carried_over_two_days…`;
  - 4: `test_zerodhas_count_is_the_plans_count`;
  - 5: `test_a_level_is_an_instruction_only…`, `test_selling_now_is_priced…`, `test_a_plan_without_a_price…`;
  - 6: `test_a_message_that_never_left_is_sent_after_a_restart_rebuilt`, `test_a_warning_no_longer_true…`, `test_a_stop_cancelled_while_the_watch_was_down…`;
  - 7: `test_a_slow_send_does_not_hold_up_the_check` (old: 1.08 s for two sends), `test_the_ticks_reads_share_one_budget`;
  - lifecycle: `test_one_option_through_a_day_open_trim_add_close_reopen_restart`.
- Tests: engine full suite 5608 passed, 4 skipped, exit 0 (9 m 35 s, `winvenv/Scripts/python -m pytest -q`); `tests/test_partner_watch.py` 62 passed (45 before); the partner and backstop test files 240 passed; client unit 65 passed (no client change). The 13 new tick tests were run against 2effb5d's watch: 12 fail for the audit's reasons, the lifecycle test only on the new cover line. No live broker or Telegram round trip (Saturday, market closed).
- Config and migration impact:
  - no setting or scheduler change;
  - columns added in place to `partner_watch_messages` (`context`, `episode`, `priority`), plus the index `ix_partner_watch_messages_outbox`;
  - `partner_watch_state` holds `guard:<episode>` rows;
  - message keys now carry the day and trade. O24c's keys were never deployed.
- Rollout: with S23-O24c (rebuild the engine, then the gateway). Rollback: revert the commit; the added columns and rows are harmless.
- Remaining:
  - streaming (next slice, once the paid plan is active);
  - the first live day's `partner_watch_messages`: outcome counts (superseded, expired), detected_at − event_at and sent_at − detected_at;
  - judgment messages stay shadow until scored;
  - a buy added to a position carried in from yesterday gets no plan.

## October 24 (evening) — O24c The trade watch made trustworthy before it is switched on; a fired backstop recognised; a stable usual size (done, Dev, commit `7d0cb6f`, branch `codex/production-correction-hedge-p0`, pushed, not deployed)

- Owner ask (Oct 24): the audit agent reviewed O23-O24b ("correctness gaps that should be fixed before enabling the new trade watch unchanged"). Agree or disagree, fix what is right, and enrich.
- Verdict: A-G were all reproduced on 08a95e3 and are fixed below. The fake-provider reproductions (old code vs new) are in each test's docstring.
- [x] O24c-HD what is held (`partner_watch.fills_of`, `trips_from_fills`, `holdings_of`).
  - A partly filled buy with a sale between its fills counted 130 instead of 65: the order's total was stamped at its last update. Now:
    - each fill comes from GET /trades (read when a fill is new, or while the trade book lags the orders);
    - trips are per exchange, option and product;
    - a trip reopened by the same order's later fill is `<id>#2`.
  - A carried position sold in part before the login counted 0 instead of 65 (the remainder was seeded, then the sale taken off again). Now it starts at the overnight quantity.
  - Zerodha's positions confirm each count. They are read after a new fill, every 30 s, and every tick while they differ.
    - A difference older than POSITIONS_LAG (10 s) uses Zerodha's count, and the message says whose count it is (`_count_note`).
    - With no positions read, the message says the count is from the orders.
- [x] O24c-CV what protects it (`cover_of`, `gtt_legs`): FULL / PARTIAL / ABSENT / UNKNOWN with the units covered.
  - What counts:
    - only stops of the holding's product, for their pending units;
    - SL orders waiting, a modify or AMO in flight included;
    - active GTT stop legs, with their product.
  - A stop of another product is named ("Your stop for 65 is MIS and these are NRML").
  - A fired stop (OPEN with its trigger, or a triggered GTT's order) is "exiting". After 10 s unsold it gets UNFILLED: trigger, limit, bid, and what selling at the bid gives.
  - An unreadable GTT list is UNKNOWN: nothing is said and the list is read again. Before, it was marked checked forever.
  - Messages come from one state machine per holding:
    - NO_STOP (never covered, 120 s after the newest buy order);
    - PARTIAL;
    - REMOVED: covered, then not, for 20 s, with the reason (CANCELLED / SOLD part / GTT gone);
    - LOWERED on a modify, or on a replacement by a lower stop. A stop that fired is not a replacement.
- [x] O24c-DL delivery (`_send`, `_retry_pending`, `_send_until_done`).
  - Telegram's own outcome is stored. A provably unsent message is sent again from the book read then:
    - which: no connection, the 429 rate limit, or a Telegram 5xx;
    - when: 10 s apart, at most 4 times, within LIFETIME_SEC by kind.
  - A timeout after the request left is not repeated. A row left "attempting" by a crash is not repeated.
  - Per message: `event_at` (broker), `detected_at` (tick), `sent_at` (Telegram ack), `message_id`, `attempts`, `outcome`, `error`.
- [x] O24c-LV levels checked against the price just read (`level_state`, `plan_stop_line`).
  - A plan stop at or above the LTP is never offered as a stop to place. The message says the price is already under it, and what selling at the bid gives with charges.
  - A target already passed is said as passed.
  - A level not checked says when it was set.
  - Wording:
    - futures levels read "NIFTY future 22,601", not "index";
    - "If it sells there";
    - "In a fast fall an SL order can trigger and still not fill".
- [x] O24c-PV immutable plans (`partner_watch_plan_versions`).
  - Version 1 is never replaced. A restart loads the stored plan instead of recomputing.
  - A new buy order adds version 2 (ADDED) and an ADDED message: the new size and average, and the loss at the plan stop now and before ("Buying more of a falling option makes the loss at the stop bigger").
  - More fills (FILLED) or a partial sale (TRIMMED) add silent versions.
- [x] O24c-TL timing.
  - The tick reads and sends protection alarms first. Each book read is bounded by READ_TIMEOUT_SEC (4 s).
  - The plan's candles and quotes run as a task; the tick waits at most PLAN_INLINE_SEC (1.5 s).
  - A plan slower than PLAN_DEADLINE_SEC (25 s) says only the premium at risk.
  - A plan task that failed (a database error, say) is started again on the next tick, up to PLAN_TRIES (3).
  - A tick over TICK_BUDGET_SEC (4 s) is logged.
  - Quotes keep bid/ask quantities, the exchange's quote and last-trade times, and our receipt time; `partner_watch_looks` stores them.
- [x] O24-BS (`fno_broker_backstop._sl_shape`): a fired SL listed as LIMIT with its trigger is still the backstop's order. Identity stays strict, and a LIMIT without a trigger still holds.
- [x] O24-SB the review's usual size (`partner_coach.size_history`, `partner_insights.trade_share`).
  - The usual starts from the trades in the 45 days before the window, as the review counts them. A day's UNUSUAL_SIZE no longer depends on the window it is read in.
  - The watch uses the same history.
  - "Usual size" says "Your usual is your own habit, not a safe size".
  - The score carries `rules_version` (2026-10-24), and the page and the PDF say "Rules of 24 Oct 2026".
- Disagreed or deferred, with reasons:
  - Streaming (Kite websocket order updates and ticks): deferred until the partner's ₹500 plan is active. The engine has no websocket library (a new dependency and an image rebuild), and it cannot be verified before a live session.
    - The tick is already split, so a stream can wake the same reconciliation; REST stays the source of truth.
  - Editing an earlier message in place: not for alarms, because Telegram does not notify an edit.
  - OFF_CARD wording: kept. It is the owner's card rule, and it already says what was missing (no written stop or exit), not that the trade was bad.
  - Snapshotting each day's review: not done. The rules date shows when a rule change re-scored a day.
- Files:
  - `python-engine/`: `partner_watch.py`, `fno_broker_backstop.py`, `partner_coach.py`, `partner_insights.py`, `partner_lessons.py`, `partner_review_pdf.py`;
  - client: `node-gateway/client/src/utils/partnerReview.js`, `pages/PartnerReview.jsx`;
  - tests: `test_partner_watch.py`, `test_fno_broker_backstop.py`, `test_partner_insights.py`, `test_partner_review_pdf.py`, `client/tests/partnerReview.test.mjs`.
- Acceptance:
  - each audit counterexample (A1, A2, B, C, D, E, F, G) is a test that the old code fails;
  - the before/after probe on 08a95e3: A1 130 → 65, A2 0 → 65, B "protected" → ABSENT, D "Place the SL order now: trigger ₹90" (price ₹20) → "already under the plan stop", F False → True.
- Tests: engine full suite 5590 passed, 4 skipped, exit 0 (9 m 31 s, on the final code; an earlier run before the last test: 5589 passed); tests/test_partner_watch.py 45 passed; client unit tests 65 passed; Vite build passed. Before/after probe on 08a95e3 vs the working tree: A1 130 → 65 held, A2 0 → 65, B 'protected' → ABSENT, D 'Place the SL order now: trigger ₹90' (price ₹20) → 'already under the plan stop', F fired backstop False → True. No live broker or Telegram round trip (market closed).
- Config and migration impact:
  - no setting or scheduler change;
  - new table `partner_watch_plan_versions` (O24's `partner_watch_plans` is no longer written; it was never deployed);
  - columns added in place to `partner_watch_messages` (attempts, outcome, error, event_at, detected_at, last_attempt_at, sent_at, message_id) and `partner_watch_looks` (bid_qty, ask_qty, quote_at, trade_at, received_at).
- Rollout: with S23-O24b (rebuild the engine, then the gateway). Rollback: revert the commit; the added columns and table are harmless.
- Remaining:
  - streaming after the plan is bought;
  - the first live day's latency and PARTIAL volume, read from `partner_watch_messages`;
  - a buy added to a position carried in from yesterday gets no plan;
  - the judgment messages stay shadow until scored.

## October 24 (afternoon) — O24b Partner size against their own habit; the system on the 15:40 F&O close (done, Dev, commit `3c6523e`, branch `codex/production-correction-hedge-p0`, pushed, not deployed)

- Owner asks (Oct 24):
  - "The partner does not follow the 10% rule; they use the amount they have in the proportion they like." Do not judge their size by a fixed tenth of their cash.
  - Move the rest of the system to the 15:40 close as well.
- [x] O24-SZ size against the partner's own habit.
  - BIG_RISK (more than a tenth of the day's cash at risk) is replaced by UNUSUAL_SIZE (`partner_insights.usual_size_flags`, called from `partner_coach.analyse`):
    - the money put into a trade, as a share of the day's cash, is compared with the median share of the partner's last 20 trades;
    - from the 5th earlier trade on, more than 1.5 times that is flagged;
    - the better line sizes the trade to the usual lots.
  - The rule is now "Usual size" (`partner_lessons.CHECKS` and `RULE_MEANINGS`).
  - The money at risk and its share of cash stay on each trade as facts.
  - The watch's PLAN drops "more than a tenth". It warns only when the buy is much bigger than the usual (`partner_watch._usual_share`: earlier days' Zerodha buys against that day's cash, then today's trips).
  - Oct 23, rebuilt: "Usual size" 12/12 (the partner sized consistently; the one 2-lot trade is already "Bigger size after a loss"). Score 43/72.
- [x] O24-MC2 the system on the 15:40 F&O close. The cash segment still closes at 15:30, so penny, momentum, EDGE and the gateway's stock-signal backlog stay at 15:30. Moved to 15:40:
  - time to expiry: `fno_chain.EXPIRY_CUTOFF` and `hedge_strategies._EXPIRY_CUTOFF`, from `market_calendar.DERIVATIVES_CLOSE_TIME`;
  - the hedge gamma alert's hours left;
  - `research_future_candles`: the candles run to 15:40, and the job moves from 15:40 to 15:45;
  - the partner analytics (OI) gate to 15:40;
  - `standard_capital`: expiry-book exits close at 15:40;
  - the system-activity windows: `lifecycle_receipts`, `ops_metrics`, `ops_watchdogs` (Kite probe), `token_lifecycle`, `daily_bootstrap`, `scheduler_telemetry`, `tools/runtime_audit`.
  - Unchanged, by design:
    - strategy times: FNO entries end 14:45, the hard flat and the DR square-off are at 15:10, the partner card management ends 15:15;
    - the expiry book: A flat 15:13, FINAL_FLAT 15:38 (already set for 15:40), the BL "late" 15:30;
    - the 15:15 operator-alert window.
- Files:
  - `python-engine/`:
    - partner: `partner_insights.py`, `partner_coach.py`, `partner_lessons.py`, `partner_watch.py`;
    - close: `fno_chain.py`, `hedge_strategies.py`, `hedge_advisory.py`, `research_future_candles.py`, `partner_orchestrator.py`, `standard_capital.py`, `lifecycle_receipts.py`, `ops_metrics.py`, `ops_watchdogs.py`, `token_lifecycle.py`, `daily_bootstrap.py`, `scheduler_telemetry.py`, `tools/runtime_audit.py`, `scheduler_setup.py`.
  - Tests: `test_partner_insights.py`, `test_partner_review_pdf.py`, `test_partner_watch.py`, `test_fno_chain.py`, `test_ops_metrics.py`, `test_research_future_candles.py`, and the route goldens.
- Acceptance:
  - No partner message or review line names a tenth of the cash. A trade much bigger than the partner's usual is named, with the usual and the size it implies.
  - Every F&O session boundary reads 15:40; the cash ones read 15:30.
- Tests: engine full suite 5560 passed, 4 skipped, 1 failed (winvenv, Python 3.11.9, 9 min 23 s): the failure was tests/test_oct21_audit_fixes.py's weekday session length, which is now 09:15-15:40 (23,100 s); that test was updated and passes, together with tests/test_partner_insights.py (53 passed). After the run only those two test expectations changed, not code. The modules moved to 15:40 have their tests passing: 346 in the targeted run, then 43 after the updates. The watch 20, insights 34 and PDF 13 tests pass. The Oct 23 review rebuilt on a copy of Production's partner tables gives Usual size 12/12 and score 43/72. The route golden changes only research_future_candles (15:40 -> 15:45)
- Config and migration impact:
  - No setting or schema change.
  - Scheduler: `research_future_candles` 15:40 → 15:45.
  - Time to expiry is 10 minutes longer, so IV and greeks move slightly, most near expiry. Replays of days before Oct 6 use the 15:40 cutoff too, a 10-minute difference.
- Rollout: with O24 (rebuild the engine). Rollback: revert the commit.
- Remaining:
  - The owner's call on any strategy times (hard flat, entry ends, the expiry book's BL late).
  - The partner suggestions offered on Oct 24; see the owner's reply.

## October 24 — O24 Partner: stops read as Zerodha shows them, the 15:40 close, refusals in plain words, and the trade watch (done, Dev, commit `53280d9`, branch `codex/production-correction-hedge-p0`, pushed, not deployed)

- Owner asks (Oct 24):
  - the partner logs in in the morning, and a companion watches their trades and sends messages at the critical moments;
  - messages only, never orders;
  - first goal: cut their losses as much as possible;
  - the rules computed per trade, not static.
- Evidence (Production, read-only, Oct 23 partner book; the research quote archive):
  - The review said "Stop placed and kept 1/12" and "No stop-loss order" on 10 trades. Zerodha's book and histories show a stop on at least 10 of 12 trades, and a stop moved down on 9 of them.
    - A fired stop is LIMIT (SL) or MARKET (SL-M) with its trigger kept: SELL 22950 CE, trigger 33, never modified, filled 13:53.
    - A stop turned into a sale keeps its trigger only in its history: 22300 PE, 68 → … → 75 → 60, then MARKET 62.6.
    - Kite's `order_timestamp` moves on a modify or a fire.
  - The 13:54 "insufficient funds" sell refusal was a second stop on a lot that already had one.
  - F&O now trades until 15:40. The archive's last NIFTY and SENSEX futures trades are 15:30:2x until Oct 5 and 15:39:5x from Oct 6. NSE moved the equity-derivatives close to 15:40; `market_calendar.DERIVATIVES_CLOSE_TIME` already held it. The partner sold at 15:39:53 on Oct 23.
  - Applying the paper book's exit ladder (`fno_exit_rules`) unchanged to the 12 trades (approximate replay) gave about −₹3,558 against the partner's −₹319.
    - The +10% profit lock sold the 22400 PE at +₹285; the partner trailed it to +₹6,135.
    - The partner's options swing 5–36% in a normal 5 minutes (median 16%).
    - So the watch computes each trade's levels from that option's own swing, the index and the cash, not from the system's fixed percentages.
- [x] O24-SR stops as Zerodha shows them.
  - A stop is any option SELL that carried a trigger (`partner_broker_sync.order_stop`, `book_stops`, `merge_stops`).
  - Histories are read for every stop and modified order. They give `stop_trigger` and `stop_since`, stored in new `partner_orders` columns (added in place).
  - Days stored before this are rebuilt from their trigger changes. A modified sale with no trigger seen is UNKNOWN, so nothing is claimed about that trade's stop.
  - CONVERTED (a stop turned into a sale) protected the trade.
  - A trailed stop is praised after a small trim when it ended higher and its last move was up.
  - The PDF prints a lesson's repeated "why" once.
- [x] O24-RF refusals in plain words (`partner_insights.refusal_plain`), on the timeline, in the orders list (page and PDF, with Zerodha's own words under them) and in the watch.
- [x] O24-MC the partner modules close at 15:40 (`DERIVATIVES_CLOSE_TIME`): the day's completeness, the trade paths, taps and the 13:30–15:40 time bucket. The evening wrap moves 15:40 → 15:50 (`PARTNER_EOD_MIN`, with the hedge EOD summary).
- [x] O24-PW the trade watch (`partner_watch.py`).
  - A 09:00 login button; "watch on" after a login before the close.
  - Every 5 s it reads the partner's order book (read-only key) and sends:
    - PLAN: the index stop priced by Black-76, floored by the option's swing, the loss with charges against the cash, the target, and the facts;
    - NO_STOP after 120 s, unless an SL or a GTT is resting;
    - LOWERED: the first move down in a trade, then only below the plan or off the buy price;
    - REMOVED: after 20 s with no replacement;
    - REFUSED;
    - CLOSE at 15:20.
  - "Quiet today" mutes PLAN, NO_STOP and CLOSE.
  - Reconnect after a lost login.
  - The partner's own key reads quotes and candles when its plan has market data, else the owner's (management lane).
  - Shadow looks every 15 s go to `partner_watch_looks`, for scoring the judgment messages later.
  - The review timeline shows "Assistant: …" lines; the page shows "Trade watch on".
- Files:
  - `python-engine/`: `partner_broker_sync.py`, `partner_coach.py`, `partner_insights.py`, `partner_lessons.py`, `partner_trade_paths.py`, `partner_fill_capture.py`, `partner_review_pdf.py`, `partner_orchestrator.py` (doc line), `routes_partner_coach.py`, `scheduler_setup.py`, `config.py`, and the new `partner_watch.py`.
  - Tests: `tests/test_partner_stop_reading.py`, `tests/test_partner_watch.py`, existing partner tests, and the route golden.
  - `node-gateway/client/src/`: `pages/PartnerReview.jsx`, `utils/partnerReview.js`, plus its test.
- Acceptance:
  - The Oct 23 review rebuilt on a copy of Production's partner tables:
    - "Moved the stop down 9 times" is the lesson (−₹1,706), and no "No stop-loss order" is claimed where a stop existed;
    - the 2 trades that cannot be told say nothing;
    - stop rule 1/10, size 6/12, score 37/72 (was 31/74);
    - the refusal reads plainly.
  - The watch never calls a non-read endpoint (allowlist test). It sends nothing for events before its first read, and one message per key (restart-safe).
- Tests: engine full suite 5559 passed, 4 skipped, exit 0 (winvenv, Python 3.11.9, 9 min 29 s); an earlier full run had one timing flake in tests/test_kite_client.py (the rate-limiter fairness test, untouched code), which passed 3 of 3 alone; partner tests 224 passed (new tests/test_partner_stop_reading.py 15 and tests/test_partner_watch.py 19); client unit tests 64 passed and the Vite build passes; a server render of the page shows the assistant line, the plain refusal and the lesson; the Oct 23 review rebuilt with Dev code on a copy of Production's partner tables (read-only export) gives the numbers above; the route goldens add exactly partner_watch_tick and partner_watch_prompt and move partner_eod_wrap and partner_hedge_eod_summary from 15:40 to 15:50
- Config and migration impact:
  - New settings: `PARTNER_WATCH_ENABLED` (True), `PARTNER_WATCH_POLL_SEC` 5, `PARTNER_WATCH_PROMPT_HOUR`/`_MIN` 09:00.
  - `PARTNER_EOD_MIN` 40 → 50.
  - New tables: `partner_watch_messages`, `partner_watch_plans`, `partner_watch_looks`, `partner_watch_state`.
  - Three nullable or defaulted columns on `partner_orders` (ALTER in place).
  - Two scheduler jobs: `partner_watch_tick` (interval 5 s) and `partner_watch_prompt` (cron 09:00).
  - No new package and no env change. If the partner's API key changes with the paid plan, the owner updates the root `.env`.
- Rollout:
  - Merge, then rebuild the engine (and the gateway for the page).
  - Check at 09:00 on a trading day:
    - the login button arrives;
    - after the login, "Trade watch on until 15:40" arrives;
    - after a buy, a PLAN message within about 10 s.
  - In the engine: `partner_watch_message` log lines, and rows in `partner_watch_messages`.
  - Rollback: `PARTNER_WATCH_ENABLED=false` stops the watch alone; revert the commit for the rest.
- Remaining:
  - Score the shadow judgment messages on recorded days and show "what the assistant would have said" in the review. Fixed arms: B the plan (break-even at P + max(W, P−S), trail best − W), C B + index trail after the target, D B + 45-minute no-progress exit, E the system ladder with its lock armed at the option's swing.
  - Then card follow-ups in the partner's numbers, and "ask before you buy".
  - System-wide close at 15:40 (not changed here, the owner's call):
    - `fno_chain.EXPIRY_CUTOFF` 15:30 (time to expiry);
    - `main.py` market-open checks and the EOD close at 15:30;
    - `partner_orchestrator` analytics gate to 15:30;
    - `PENNY_DAILY_ATTRIBUTION_TIME` 15:30;
    - expiry_paper's late window;
    - ops watchdogs and telemetry windows;
    - the cash segment's closing auction (15:15–15:35) for EDGE and Penny close prices.
  - Production stores days with the old reading until this deploys; those days are rebuilt from trigger changes.

## October 23 (evening) — O23 Partner review: earlier days, a PDF of the day, what each rule means (done, Dev, commit `66cfb7c`, branch `codex/production-correction-hedge-p0`, pushed, not deployed)

- Owner ask (Oct 23 evening): the partner loved the review. Let them open
  earlier days' reviews, add a button that downloads the day's review as a
  PDF, and explain "Trade a Card" (the "Traded a card" rule).
- Evidence (Production, read-only, Oct 23):
  - The review already had a small day `<select>` over the last 30 days with
    a card or a trade (Oct 13, 15, 19, 23).
  - Oct 23 is the first Zerodha day: 12 trades, all without a card, so
    "Traded a card 0/12".
  - Kite Connect returns only the current day's orders. A day has Zerodha
    trades only if Zerodha was read that day (the evening login, or the 15:40
    wrap with a held login); nothing before the first login can be fetched.
  - Card price paths are frozen at the 15:40 wrap
    (`partner_coach_card_paths`) and the traded options' 1-minute paths are
    stored (`partner_trade_paths`), so an older review stays as it was after
    the 7-day OI purge.
- [x] O23-PH earlier days.
  - A day bar (◀ Earlier · the day list · Later ▶) replaces the small select.
    The list covers 120 days (`GET /partner/review/days`, read once per page,
    never polled), and Progress "Day by day" rows open their day.
  - On an earlier day the page and the engine say "that day", not "today"
    (headline, clean-day line, cash at risk, the day's charges, refusals,
    expiry, the read-before-close note). The "Today" tab shows the date, and
    "Tomorrow, focus on one thing" shows only on the newest day.
  - Progress always covers the last `days` (30) days. Before, opening an old
    day widened Progress to reach it.
- [x] O23-PD PDF.
  - `GET /partner/review/pdf?day=` (engine) prints the same day review with
    reportlab, with vector text and charts. DejaVu Sans covers ₹ − ✓ ✗; a
    missing glyph is replaced, never dropped.
  - `GET /api/partner-kite/review/pdf` (gateway, partner or owner session,
    20 a minute) passes on only a PDF, as `trading-review-YYYY-MM-DD.pdf`.
  - "Download PDF" waits while today's Zerodha read is still running.
- [x] O23-PM rule meanings. Every rule under "Rules kept" carries a plain
  `means` line on the page and in the PDF. "Traded a card": the trade was on
  a card the system sent on Telegram that day (the same option, bought after
  the card arrived); a trade on any other option counts as a trade without a
  card.
- Files:
  - `python-engine/`: `partner_lessons.py`, `partner_insights.py`,
    `partner_coach.py` (wording only), `routes_partner_coach.py`, new
    `partner_review_pdf.py`, `requirements.txt` (reportlab 4.4.10, pillow
    12.3.0, charset-normalizer 3.5.2), `Dockerfile` (fonts-dejavu-core).
  - `node-gateway/server/`: `routes/partner-kite.js`,
    `middleware/security.js` (the `reviewPdf` limiter).
  - `node-gateway/client/src/`: `pages/PartnerReview.jsx`,
    `utils/partnerReview.js`.
  - Tests.
- Acceptance:
  - Today's review reads exactly as before; an earlier day reads "that day".
  - Progress does not change with the open day; the day list reaches 120
    days.
  - The PDF holds:
    - the headline, and the focus (newest day only);
    - the lesson, what went well, and every lesson in full;
    - the rules with their meanings;
    - every trade with its checks, chart, option lines, timeline and result;
    - the orders, the cards not taken and the notes.
  - No glyph is lost.
  - The gateway passes only a PDF, under a fixed file name, and needs a
    session.
- Tests: engine full suite 5524 passed, 4 skipped, exit 0 (winvenv, Python 3.11.9, 9 min 12 s); the new tests/test_partner_review_pdf.py 12 passed; in the engine image (Debian 13, Python 3.11.17, fonts-dejavu-core, pinned packages) the partner tests 111 passed and the default font path embeds DejaVu with every symbol covered; gateway jest in a throwaway container 522 passed, 4 skipped (40/41 suites, partner-kite 10); client unit tests 63 passed and the Vite build passes; the real Oct 23 review printed to an 11-page PDF in 0.25 s and was checked page by page; the route golden adds exactly the two new GET routes
- Config and migration impact:
  - New Python packages and the Debian font package, so the engine image
    must be rebuilt.
  - No schema, setting or env change.
- Rollout:
  - Rebuild the engine, then the gateway, one at a time.
  - Check: open the review, step to an earlier day, download the PDF on the
    phone that opens the Telegram link.
  - Rollback: revert the commit.
- Remaining:
  - Whether the PDF downloads inside Telegram's in-app browser depends on the
    phone. Android Custom Tabs download it; an in-app browser that blocks
    downloads needs "Open in browser", and then a fresh login.
  - Days before the first Zerodha login have no Zerodha trades (Kite keeps no
    order history). A Console tradebook import would be a separate piece.

## October 23 — S23 Oct 23 audit fixes: broker-stop identity, one equity charge contract, clean shutdown, terminal retry, iNAV screen, health backlog, telemetry identity, honest reporting (done, Dev, commit `7e2a2b9`, branch `codex/production-correction-hedge-p0`, pushed, not deployed)

- Problem: the Oct 23 Production audit of PR #114 (`582d7a5`,
  `docs/2026-10-23-production-deep-audit.md` in Production) and our own
  checks found:
  - S23-BS1 (P1, live F&O only): a lost backstop receipt was resolved from the
    order book by shape (symbol, SELL, SL, trigger). An earlier position's
    COMPLETE stop with the same trigger was adopted, and the still-held long
    was booked flat. Exchange, quantity and order time were not checked
    either. Reproduced in Dev: `before_exit` returned `filled` with
    `OLD-POSITION-SL`.
  - S23-COST1 (P2): the daily tracker settled EDGE/Penny paper with the
    engine's old CNC branch (intraday brokerage and stamp, sell-only STT, no
    DP); the confirmed EDGE exit used the delivery schedule. We disagree with
    the audit's proposed direction: DCMSRIND (Oct 22) was bought and sold the
    same day, which Zerodha charges as intraday (support.zerodha.com,
    "brokerage charged for partial delivery"), so its real cost was about
    ₹48.84. The tracker booked ₹82.58; the delivery schedule would have
    booked ₹118.31.
  - S23-SG: a redeploy SIGKILLed the engine 3 s after SIGTERM (Oct 22 19:38,
    `cause=unclean_stop`), so no drain or clean-shutdown receipt.
  - S23-R1: two of six Momentum research trades had no 15:15 bar at the
    15:32 pass and stayed CENSORED; there was no later pass.
  - S23-U1 (ours): 251 of 259 skipped universe histories were empty
    responses. The sampled ones were ETF iNAV tickers (351 in the instrument
    list) that pass the EQ screen.
  - S23-H1: gateway `/api/health` stayed `degraded` all day for old backlog
    (8 dead letters, 10 PENDING signals from 29 Jun–7 Oct, 4
    CANCELLED/REJECTED orders never synced).
  - S23-T1: a scheduler completion hit `database is locked` with
    `run_id=None`. A lost start marker left the completion without identity;
    its fallback insert ignored the growing retry budgets, and a replay could
    not be matched.
  - S23-M1: the 07:50 nudge said "~55 min"; the refresh took 5.6 min.
  - S23-M2: the 16:00 digest read only classic Penny and Nifty ("+Rs 0")
    on a −₹478.53 closed day.
  - S23-S1: ON_TIGHT_SPREAD measures fill over LTP, not the displayed
    spread (GLOTTIS/HEADSUP passed with ~3% spreads). The overnight exit is
    modelled at the open less 5 bp, although it runs at 09:17.
  - S23-Q1: a short quote batch (`requested=15 returned=0`) did not name
    the missing symbols.
  - S23-G1 (ours): entry gates still zeroed brokerage, STT and GST
    "until the bankroll reaches ₹50,000". The main book holds ₹91k and
    testing is standardised on ₹2L/₹5L.
- Files:
  - `fno_broker_backstop.py`: `broker_tag` column (ALTER on first write),
    `new_tag()` (`BSL` + 17 hex), `_same_order`, identity matcher.
  - `fno_executor.py`: `place_stop_limit(tag=)`.
  - New `equity_charges.py`: `session_date`, `charged_as_intraday`.
  - `engine.py`: true delivery branch, no `for_gate`; `momentum_exits.py`
    drops its `for_gate=False` argument (the full suite caught the
    TypeError).
  - `config.py`: `ZERODHA_CNC_STAMP_DUTY_PCT`, `ZERODHA_CNC_DP_CHARGE`.
  - `position_tracker.py`: `settlement_costs`.
  - `penny_edge_orchestrator.py`: same rule on the confirmed exit.
  - `main.py`: `_charged_as_intraday` on Momentum closes; 16:05 terminal
    retry job; shutdown comment; records the refresh time.
  - `routes_portfolio.py`, `research_penny_cnc_lifecycle.py`.
  - `docker-compose.yml`: engine `stop_grace_period: 45s`.
  - `python-engine/Dockerfile`: `--timeout-graceful-shutdown 10`.
  - `penny_universe.py`: `INAV` suffix.
  - Gateway `routes/health.js`, `services/telegram.js`:
    `undeliveredAlertSummary`, `stale_backlog`.
  - `scheduler_telemetry.py`: run id before the marker, idempotent fallback
    insert.
  - `daily_bootstrap.py`: `record_universe_refresh`,
    `last_universe_refresh`, `login_nudge_text`.
  - New `day_books.py`; `operator_status.py`: the all-books block,
    "Classic Penny".
  - `edge_overnight_paper.py`: `entry_bid`, `entry_ask`, `exit_bid` and
    `exit_bid_net` columns; `_realism`.
  - `kite_client.py`: names the missing quote keys.
  - Tests: `test_fno_broker_backstop.py` (+13 cases in 7 tests; fixtures carry
    real order fields), new `test_s23_cost_contract.py` (19), new
    `test_s23_runtime_fixes.py` (17), `test_scheduler_telemetry.py` (+2),
    `test_penny_universe_refresh.py` (iNAV rows), updated
    `test_engine.py`/`test_audit_fix.py` (old cost shape),
    `add_job_census_golden.json` (+1 job), gateway `health-status.test.js`
    (+2), `alert-dead-letter.test.js` (+1).
- Acceptance (Dev):
  - Every reproducer fails on the previous code and passes now:
    - the audit's old-stop adoption (old code `filled`, new `proceed`);
    - the second probe (changed exchange or quantity);
    - two unattributable candidates hold the exit and page;
    - the escalated-budget completion and the idempotent replay;
    - the tracker settling by holding.
  - DCMSRIND same day → ₹48.8374; held overnight → ₹118.3074. Engine and
    Penny schedules are equal on both branches.
  - On a read of Production data (2026-10-23, read-only), the all-books
    block reproduces the audit: main ₹0, Smart V1 +₹16.40, overnight
    −₹494.93 holding 3 at ₹18,366.60, subtotal −₹478.53, V2 +₹11.02 apart.
  - Gateway: 19 health, dead-letter and backlog tests pass in a throwaway
    Linux container from the gateway image (no network). better-sqlite3 has
    no Windows binary for Node 24 here.
  - The Oct 6 allocation freeze verifies at `b03afa5`, and its intraday
    costs equal the new engine's on 500 random trades.
  - Full engine suite: 5512 passed, 4 skipped (Windows winvenv, 9 min 23 s, exit 0; the process exits on its own). The first run caught `momentum_exits.py` still passing `for_gate` (fixed) and the Oct 6 freeze test (now pinned, above).
- Configuration and migration:
  - Settings: `ZERODHA_CNC_STAMP_DUTY_PCT=0.00015`,
    `ZERODHA_CNC_DP_CHARGE=15.34`; gateway env `HEALTH_BACKLOG_RECENT_HOURS`
    (default 24).
  - Additive columns: `fno_broker_backstops.broker_tag`, and
    `entry_bid`/`entry_ask`/`exit_bid`/`exit_bid_net` on both overnight trade
    tables. Each is created on first write; the read-only comparison selects
    NULL until then.
  - New file `/data/daily_bootstrap_timing.json`; new job
    `momentum_shadow_terminal_retry` (16:05 Mon–Fri).
  - Behavior changes:
    - CNC sold the session it was bought pays intraday charges, held
      overnight the full delivery schedule (tracker, EDGE confirmed exit,
      Momentum closes);
    - entry gates price full costs. Momentum acceptance is unchanged: its
      cost-per-R gate (≤ 0.12 R at full cost) already binds. The daily swing
      screener (`evaluate_signal`) now needs targets that cover delivery
      costs;
    - `/api/health` is `ok` with only stale, settled backlog;
    - live backstop stops carry their own tag instead of `FNO_LIVE`.
- Rollout: merge; rebuild the engine, then the gateway, one at a time;
  recreate both (compose applies the stop grace). After deploy:
  - the next engine stop or redeploy is followed by a startup without
    `cause=unclean_stop`;
  - 16:05 logs `momentum_shadow_terminal pass_name=retry`;
  - `penny_universe_history_scope fetch` drops by the iNAV count;
  - gateway `/api/health` is `ok` with `stale_backlog`;
  - the 07:50 nudge quotes the last refresh;
  - the 16:00 digest has the all-books block;
  - new overnight rows carry the bid/ask fields, and the overnight
    comparison has `realism`.
- Rollback: a code revert of this commit; compose and Dockerfile go back with
  it. The new columns and the timing file are additive and harmless. The
  old cost branch must not be restored silently: it over-charged same-day
  paper trades.
- Remaining:
  - [ ] Owner decision: resolve the old gateway backlog with the reviewed
    reconciliation (`server/scripts/backlog-reconciliation.js`). Health no
    longer depends on it.
  - [ ] Historical cost difference, read-only on Production 2026-10-23: 21
    fully closed EDGE/Penny paper positions (18 same-day, 3 overnight; 19
    partial rows not restated). The stored costs were ₹778.00; under this
    contract they are ₹650.22, so the old tracker over-charged by ₹127.79
    (EDGE_PAPER ₹123.79, PENNY_PAPER ₹4.02). The ledger is not rewritten.
  - [ ] Four Aug 2026 `positions` rows store `exit_price` as a numpy int64
    blob. Current code casts to float; this is history only, and the ledger
    is the authority.
  - [ ] Score the overnight `realism` counterfactuals after ≥ 20 nights
    before any change to the exit or entry timing.
  - [ ] Host or VM shutdowns (nightly ~22:00–23:30) still skip the engine's
    shutdown; the stop grace covers compose stops only.
  - [ ] The Oct 6 Momentum allocation freeze fingerprints `engine.py` and
    `momentum_exits.py`, which changed here. Evaluate its holdout at
    `b03afa5`, the last commit whose fingerprint matches; the freeze test
    now verifies the manifest there. The study prices only intraday round
    trips, and a test shows the new engine gives the pinned values exactly,
    so the holdout is unaffected. Its evaluation ("after about 10
    sessions") is due. No other frozen manifest covers a changed file.
  - [ ] Live F&O stays off. The backstop fix is a precondition, not a go-live
    decision.

## October 22 (evening) — T22-BG held background work, T22-U universe history scope (done, Dev, commit `3a9f674`, branch `codex/production-correction-hedge-p0`, pushed, deployed 2026-10-22 19:38 IST by PR #114 (`582d7a5`))

- Problem:
  - T22-BG: verifying A22, the full suite passed and then hung at exit for
    3.5 h. A startup catch-up spawned by `register_penny_scheduler_jobs` was
    destroyed inside `aiosqlite.connect()`, whose non-daemon worker thread
    then waited forever. The hang depends on the time of day, which is why
    some runs exited. Fourteen engine sites used bare `create_task`, which
    asyncio holds only weakly. Among them are the Penny ledger write and
    `post_login_initialization`.
  - T22-U: the T21-B universe refresh took 60 min on Production because it
    read daily history for all 10,235 NSE instruments; 6,085 were unusable.
- Files:
  - New `background_tasks.py` (`spawn`, `pending`, `drain`).
  - Spawn sites in `scheduler_setup.py` (3 startup catch-ups), `main.py`
    (4, plus `drain` at shutdown), `routes_ops.py` (3), `engine_auth.py`,
    `kite_client.py`, `market_calendar.py`, `penny_risk.py` (ledger write)
    and `scheduler_telemetry.py`.
  - `tests/conftest.py`: per-test drain hook and session-end connection
    guard.
  - `requirements.txt`: `aiosqlite==0.21.0`. 0.20 leaked a worker thread
    when a connect was cancelled mid-open; 0.21.0 fixes it (#317).
  - `penny_universe.py`: `_quote_screen`, history scope, and the candidate
    loop on the same screen.
  - Tests: new `test_background_tasks.py` (8) and
    `test_penny_universe_refresh.py` (+1).
- Acceptance (Dev):
  - A bare task parked on its own future is collected by `gc.collect()`; a
    spawned one is held.
  - `drain` unwinds a task inside an open aiosqlite connection, and its
    worker thread stops.
  - A finishing write gets its grace period.
  - A failed task is logged.
  - No running loop closes the coroutine.
  - The Penny ledger write and every scheduler catch-up are held. These two
    tests fail on the previous code.
  - A connect cancelled mid-open leaves no worker. This fails on aiosqlite
    0.20.0 and passes on 0.21.0.
  - The history-scope test fails on the previous code, which fetched bonds,
    ETFs and unquoted symbols.
  - Old and new refresh write identical universes over 40 randomised sets
    (history calls 16,000 → 3,872).
  - Full suite: 5460 passed, 4 skipped (full suite, Windows winvenv, aiosqlite 0.21.0; exit 0, no leaked worker); the process exits on its own (exit code
    recorded).
- Configuration and migration: no settings and no schema change. One
  dependency pin, `aiosqlite` 0.20.0 → 0.21.0; the engine image rebuild
  picks it up. New log lines are
  `penny_universe_history_scope`, `background_task_failed` and
  `background_tasks_cancelled`.
- Rollout: merge and rebuild the engine. After deploy:
  - the next `penny_universe_refresh_done` shows elapsed in minutes, with
    `penny_universe_history_scope fetch≈900–1,000`;
  - `penny_universe_refreshed count=100` and the quality audit are
    unchanged;
  - an engine restart logs no `Task was destroyed`.
- Rollback: a code revert of this commit, including the pin. Nothing
  persistent changes.
- Remaining:
  - [ ] Compare the first post-deploy refresh's ranked universe and quality
    audit with the day before. They should differ only by market moves.
  - [x] (done in S23-SG, Oct 23 slice) Engine stop grace. On this Docker host `docker stop` kills after
    about 3 s (a throwaway container measured 3.4 s), and compose sets no
    `stop_grace_period`. At the 19:38 redeploy the engine got SIGTERM and
    then SIGKILL 3 s later (exit 137), while the gateway and agent exited 0.
    So the engine's shutdown did not run: no clean-shutdown receipt
    (startup logged `cause=unclean_stop`), no exit-path drain, no
    background drain. Of the 10 startups since 2026-10-17, only 2 followed
    a recorded `clean_shutdown`; some others followed host shutdowns.
    Next: set `stop_grace_period` for python-engine and
    bound uvicorn's own graceful wait, then check `clean_shutdown` on the
    following redeploy.

## October 22 — A22 audit follow-up (done, Dev, commit `ffa979c`, branch `codex/production-correction-hedge-p0`, pushed, deployed 2026-10-22 19:38 IST by PR #114 (`582d7a5`))

- Problem: the Oct 22 audit of PRs #112–113 found two order-safety defects
  in the live broker backstop and five follow-ups. The follow-ups are the
  Momentum terminal pass's write lock, an unbounded exit-path recorder,
  exit-arm research that scored baseline mismatches, the partner login
  exceeding the 45 s gateway deadline, and coaching extrema taken from
  outside the holding. The audit also asked for opportunity-level V1/V2
  comparison, explicit research scopes and version separation. All six
  defects reproduced in Dev; we agreed with every finding.
- Files:
  - `fno_broker_backstop.py`: intent before send, `BackstopUnreadable`,
    in-flight grace, order-book adoption.
  - `momentum_shadow.py`: fetch outside the transaction.
  - `fno_exit_paths.py`: bounded writer, guarded writes, counters, settings
    binding, `close`.
  - `fno_orchestrator.py`: passes the exit settings to the recorder.
  - `main.py`: drains the writer on shutdown.
  - `routes_ops.py`: `fno_exit_paths` stats.
  - `fno_exit_cadence.py`: binding, identity, gap and reconciliation gates;
    `LOCK_CONFIRMED`; paired deltas; coverage.
  - `partner_broker_sync.py`: login deadline, background read,
    `review_sync`.
  - `routes_partner_coach.py`: `sync` in the review.
  - `partner_insights.py` and `partner_lessons.py`: contained extrema,
    `edge` line.
  - `penny_smart_shadow.py`: round trips, `versus`.
  - `standard_capital.py`: `method.scope`.
  - Gateway `routes/partner-kite.js`: comment and log field.
  - Client `PartnerReview.jsx` and `utils/partnerReview.js`: status line,
    auto refresh.
  - Tests: `test_fno_broker_backstop.py` (+4),
    `test_oct21_audit_fixes.py` (+1), `test_fno_exit_cadence.py` (rewritten,
    17), `test_partner_broker_sync.py` (+3, login tests updated),
    `test_partner_insights.py` (+2), `test_penny_smart_v2.py` (comparison
    tests rewritten, +1), `client/tests/partnerReview.test.mjs` (+1) and the
    gateway partner-kite mock.
- Acceptance (Dev):
  - Every audit reproducer is a test that fails on the previous code and
    passes now:
    - a lost receipt never lets an exit sell blind;
    - no intent means no send, and never two sends;
    - an unreadable ledger holds;
    - another writer is never locked out by a history fetch;
    - 100 looks against a stuck disk return in < 1 s, with every drop
      counted;
    - a ₹0 underlying_stop never scores as CURRENT's profit lock;
    - a slow deeper read never delays the login;
    - a 10-second hold gets no best/worst.
  - Expected changed text: the spike test's best is now 10:31, the first
    whole minute after a 10:30:20 buy.
- Configuration and migration: no new settings and no schema change. The
  backstop `state` column gains values `PLACING` and `ALREADY_RECORDED`
  (return only). Exit-path lines gain `params_sha` and `params`. The ops
  snapshot gains `fno_exit_paths`; the review payload gains `sync`.
- Rollout: merge, rebuild engine and gateway. After deploy:
  - `fno_exit_paths` in the ops snapshot shows `written` growing with no
    drops on the first F&O position;
  - the first exit-path line of each position carries `params`;
  - a partner login answers at once and the review shows "Adding your
    order changes…" until done;
  - `GET /experiments/penny-smart` has `versus`.
- Rollback: `FNO_EXIT_PATH_RECORDING=false` stops recording. Everything else
  is a code revert of this commit. The backstop acts only when live F&O is
  enabled.
- Remaining:
  - [ ] Score `fno_exit_cadence` once ≥ 20 positions are scored (not merely
    recorded) after deploy; read `skipped` and `mismatches` first.
  - [ ] Score V2 against V1 from 2026-10-22 with `versus` (≥ 30 V2 closes).
  - [ ] Live F&O stays off. The backstop changes are a precondition for it,
    not a go-live decision.

## October 21 (night, 3) — SX-F1 confirmed lock + exit evidence, SX-P2 PEN_SMART_V2 (done, Dev, commit `ace52ab`, branch `codex/production-correction-hedge-p0`, pushed, deployed: merged by PR #113 (`33065ed`), running in Production at `582d7a5` (Oct 23 audit attestation))

- Problem: owner delegated the open calls (profit lock, Smart Penny, partner
  cards) with "make it smart, not a blocking and filtering system".
- Files: `fno_exit_rules.py` (`FNO_PROFIT_LOCK_CONFIRM_SEC`,
  `lock_breach_since`), `fno_orchestrator.py` (breach state, recorder call,
  ask), `fno_policy_replay.py`, `fno_exit_experiment.py` (state threaded),
  `fno_exit_paths.py` (new), `fno_exit_cadence.py` (new),
  `scripts/export_fno_replay_dataset.py` (copies exit paths),
  `penny_smart_v2.py` (new), `penny_smart_shadow.py` (policy parameter,
  comparison), `penny_scanner.py`, `main.py`, `routes_ops.py`,
  `routes_penny_experiments.py`, `config.py`; tests
  `tests/test_fno_exit_cadence.py` (9), `tests/test_penny_smart_v2.py` (5),
  `tests/test_penny_smart_policy.py`, `tests/test_penny_scanner.py` (one
  call per book); golden adds `/experiments/penny-smart`.
- Acceptance (Dev): one look under the floor waits, a second ≥ 8 s later
  sells, a recovery clears it, protective stops never wait; the recorder
  writes one line per look off the exit path; the evaluator reproduces the
  old lock on the flicker and the confirmed one holding to a later exit
  from verified archive quotes; unresolved never filled; V2 stop 9.88 vs V1
  9.94 on the fixture; V1 binding unchanged, both books enter once each.
- Rollout: merge, rebuild engine. First F&O lock event: `fno_exit_paths`
  lines for the held position; a lock exit at least one look after the
  first breach. First Penny scan: two `penny_smart_paper_state` rows.
- Rollback: `FNO_PROFIT_LOCK_CONFIRM_SEC=0`; `FNO_EXIT_PATH_RECORDING=false`;
  `PENNY_SMART_V2_ENABLED=false`.
- Remaining:
  - [ ] Score `fno_exit_cadence` after ≥ 20 matched F&O trades recorded after
    deploy (CURRENT vs LOCK_FIRST_LOOK vs lock arms).
  - [ ] Score V2 vs V1 from 2026-10-22 (≥ 30 V2 closes, the four checks).
## October 21 (night, 2) — SX-M1 honest Momentum shadow scoring (done, Dev, commit `27ee87b`, branch `codex/production-correction-hedge-p0`, pushed, deployed: merged by PR #113 (`33065ed`), running in Production at `582d7a5` (Oct 23 audit attestation))

- Problem: next-open gap exits (missed 15:15 bar) were scored as variant results.
- Files: `momentum_shadow.py`, `promotion_readiness.py`, test in `tests/test_momentum_shadow.py`.
- Acceptance: a gap-exit close is counted apart, excluded from every metric and the promotion sample gate.
- Verification: related suites 58 pass (momentum shadow, Oct 21 fixes, promotion readiness); full suite not rerun (usage limit).
- Remaining:
  - [ ] SX-F1 (designed, not built): record the 10-second exit loop's quotes of held F&O options (fire-and-forget JSONL under `/data/research/fno_exit_paths`) and an offline evaluator replaying CURRENT (parity), FNO_LOCK_OFF, FNO_LOCK_LATE_ARM, FNO_LOCK_LOOSE_KEEP and a declared FNO_LOCK_CONFIRM_2 at live cadence (archive after the live exit). Why: Oct 15 live profit-lock exit +₹663 vs replay trail exit +₹3,515 on the same trade; post-Oct-5 archive replay of the lock arms differs only on one trade (3 NIFTY trades, inconclusive).
## October 21 (night) — O21-PX the partner's deeper review (done, Dev, commit `68eec28`, branch `codex/production-correction-hedge-p0`, pushed, deployed: merged by PR #113 (`33065ed`), running in Production at `582d7a5` (Oct 23 audit attestation))

- Problem: the owner merged PR #112 and asked that every evening, after the
  brief, the partner gets a review link (login, then the review), and that
  the feedback be enriched from everything the API offers. Gaps found: no
  link on a held-login day without trades; the coach saw only fills (no
  order changes, refusals, positions or cash) and no prices around a trade;
  a re-buy of the same option merged into one trade (a false "added to a
  losing option" and a hidden revenge re-entry); after the split, a re-entry
  under the card's SL would have been told to "sell at the SL" for a profit.
- Files: `partner_broker_sync.py` (allowlist, details, prompt,
  `ensure_review_message`), `partner_trade_paths.py` (new),
  `partner_insights.py` (new), `partner_coach.py` (round trips, re-entries,
  ENTRY_UNDER_STOP, context), `partner_lessons.py` (rules kept, option lines,
  day and window statistics, focus, fold cap), `partner_orchestrator.py`
  (wrap step); gateway `routes/partner-kite.js` (45 s); client
  `PartnerReview.jsx`, `utils/partnerReview.js`; tests
  `tests/test_partner_insights.py` (new), `tests/test_partner_broker_sync.py`,
  `tests/test_partner_lessons.py`, client `tests/partnerReview.test.mjs`.
- Contracts:
  - Kite allowlist adds GET `/portfolio/positions`, `/user/margins/equity`,
    `/orders/<digits>`; nothing else.
  - New tables `partner_orders`, `partner_order_changes`,
    `partner_broker_positions` (`partner_positions` is the hedge module's),
    `partner_account_days`, `partner_trade_paths`.
  - `sync_book` result adds `details` and `paths`. `analyse(...,
    context=None)`; trades split by round trip (`<key>#2`); card items may
    carry `reentry`/`card_time`; items carry `insight`; day rows `account`,
    `orders`, `open_positions`, `carried_in`, `stops_known`; summary
    `card_reentries`.
  - Review adds `score`, `stats`, `account`, `orders`, `open_positions`;
    stories add `reentry`, `checks`, `option_lines`, `chart`, `numbers`;
    progress adds `focus`, `stats`, per-day `rules_kept_pct`. The note's
    headline adds "rules kept k/n".
  - No new route, job or setting; no owner-facing behaviour or card text
    changed.
- Acceptance (met in Dev): every new lesson and positive has a firing and a
  non-firing test with recomputed rupees; spike only on 1-minute candles and
  off-card; give-back only off-card; a raise inside the card's limit is not
  chasing; the allowlist refuses POST/PUT/DELETE on order paths and GET of
  non-numeric ones; details survive a failed history; positions and cash are
  not read before the open; paths are read once after the close, fall back
  to prints and stop at the budget; one review link a day (prompt, or the
  coach note); a synthetic day was read end to end and its wording fixed
  (re-entry under the SL, card-SL risk, fold cap, same-minute order).
- Rollout: merge, rebuild engine and gateway. First evening: the 15:40 link
  (prompt or note); after the partner's login, `partner_paths_stored` and
  `partner_zerodha_synced` log lines; the review's charts and rules kept.
- Rollback: revert the commit (tables are inert); the partner flow itself is
  off with a blank `PARTNER_KITE_API_KEY`.
- Remaining:
  - [ ] Check the first real days on Production: the lessons' thresholds
    (20% spike, 20% give-back, 10% of cash) are declared, not fitted; change
    them only with the owner.
  - [ ] A re-entry on a card is its own item; a split position kept across
    days (carry-in) is shown as a note, not scored.
## October 21 (late) — Oct 21 audit fixes S21-R1/R2/R3/E1/L1, R21-M1/M2, T21-X; O21-ON overnight shadows (done, Dev, commit `462d28f`, branch `codex/oct21-audit-fixes` on top of `codex/partner-coach-standard-capital`, pushed, deployed: merged by PR #112 (`046f3ff`), running in Production at `582d7a5` (Oct 23 audit attestation))

- Problem: the Oct 21 Production audit (read-only; Production HEAD
  `2fc12ee`, PR #111 deployed) found: nine censored virtual Momentum trades
  (no terminal bar), an RS fingerprint that ignores the index and rule
  constants, a replay/runtime overnight admission mismatch, no entry-day
  event check in EDGE, a holiday counted as market time in restart
  receipts, a misleading EDGE dead-gate alarm, a "pool" label hiding the
  F&O drawdown, a generic transport error class, stale docs; the owner
  asked for fixes and for shadows where a better approach is supported.
- Files: `momentum_shadow.py`, `momentum_rs_pullback.py`, `main.py`,
  `edge_portfolio_replay.py`, `penny_edge_orchestrator.py`,
  `lifecycle_receipts.py`, `penny_accept_watchdog.py`,
  `fno_hourly_report.py`, `kite_client.py`, `edge_overnight_paper.py`,
  `routes_penny_experiments.py`, `config.py`; tests
  `tests/test_oct21_audit_fixes.py` (new), `tests/test_oct15_audit_fixes.py`.
- Contracts:
  - New tables `momentum_shadow_terminal_receipts`,
    `edge_overnight_shadow_trades`; new job `momentum_shadow_terminal`;
    route `GET /experiments/edge-overnight`; setting
    `EDGE_OVERNIGHT_SHADOWS_ENABLED`; goldens regenerated (one route, one
    job; additions only).
  - Startup receipt adds `weekday_overlap_sec`; `market_overlap_sec` is
    trading-session time. EDGE `penny_signals` rows: accepted = either leg
    entered; reasons `rank_not_selected`, `selected_not_entered`, or the
    leg's refusal. `transport_error_kind` kinds added. Hourly F&O line:
    `allocation=` / `equity=`.
  - RS shadow records from now on have a new identity (rules + pool +
    index + daily bars); earlier records are immutable and keep theirs.
- Acceptance (met in Dev): each audit counterexample has a test that now
  passes (terminal time exit and stop on missed bars, censored then closed;
  index/constant change alters the RS identity while older variants keep
  theirs; replay admits 414 at the dust boundary; entry-day event refusal;
  holiday overlap 0 with the raw 22,500 s kept; a 94-candidate/3-drift day
  names the drift and not the ranking; allocation and equity both shown;
  heartbeat delivery result); shadows open from the same picks with their
  declared rules, exit on the same quotes, and are compared with the book.
- Rollout: merge after `codex/production-correction-hedge-p0` and
  `codex/partner-coach-standard-capital` (this branch contains both);
  rebuild the engine. First evening: `momentum_shadow_terminal` log line;
  first 15:20: shadow rows in `edge_overnight_shadow_trades`.
- Rollback: `EDGE_OVERNIGHT_SHADOWS_ENABLED=false` (no shadow rows);
  `MOMENTUM_SHADOW_ENABLED=false` (no Momentum shadow or terminal pass);
  revert the commit for the rest. New tables are inert when unused.
- Remaining:
  - [ ] Score the overnight shadows only on nights after 2026-10-21; judge
    after at least 20 closed trades each, with the owner. No promotion from
    a few nights.
  - [ ] T21-B (penny universe refresh about 60 min) and F21-S (Smart 8W/40L)
    are not changed here: Smart's policy files are hashed and stay as they
    are; profile the refresh's symbol types separately. (T21-B profiled
    and done as T22-U on 2026-10-22; F21-S stays open.)
  - [ ] F21-Q (old pending signals, unsynced orders, September deadletters)
    needs the owner's dated disposition; nothing is resent automatically.
## October 21 (night) — O21-PL the partner's review page and explained lessons (done, Dev, commit `6f882f0`, branch `codex/partner-coach-standard-capital`, pushed, deployed: merged by PR #112 (`046f3ff`), running in Production at `582d7a5` (Oct 23 audit attestation))

- Problem:
  - Owner (Oct 21): log in from Telegram, land on their own dashboard, "a
    branch of our dashboard main one", showing the day's learnings first and
    more on demand; the teachings must be top quality, comprehensive,
    correct and well tested so the partner understands their mistakes and
    what would have been better.
  - Facts: flags said what happened and a generic rule, not why it mattered
    or what the better action would have paid; stop orders were not read;
    one trade with three mistakes read as three lessons with the same loss.
- Files: `partner_lessons.py` (new), `partner_coach.py`,
  `partner_broker_sync.py`, `routes_partner_coach.py`; gateway
  `routes/partner-kite.js`; client `App.jsx`, `pages/PartnerReview.jsx`
  (new), `pages/PartnerCoach.jsx`, `utils/partnerReview.js` (new).
- Contracts:
  - Flag fields `why`, `better`, `better_pnl`, `actual_pnl`; `impact_rs` =
    actual − better. New codes NO_STOP_ORDER, STOP_WIDER_THAN_CARD,
    STOP_CANCELLED; positives STOP_PLACED, EXITED_BEFORE_STOP,
    PAUSED_AFTER_LOSS; `item.stops`. `_rs(0)` is "₹0".
  - `analyse(..., stops=, stops_known_days=)`; `card_entry` basis
    PRINT_AT_STOP.
  - Zerodha: allowlist + GET `/gtt/triggers`; table `partner_stop_orders`;
    `partner_broker_days.stops_known` (the table was created only in Dev).
  - Engine GET `/partner/review`; golden regenerated (one addition).
    Gateway GET `/api/partner-kite/review`; login redirect `/?view=review`.
- Acceptance (met in Dev): every lesson figure in the tests is recomputed
  from prices with the same charges schedule; chased-entry risk, revenge,
  size-up, averaging, stop, early-exit, gave-back, square-off, overtrading
  and the three stop checks each have an exact-text test; stops are claimed
  only on complete days with GTTs read; one trade's mistakes fold into one
  lesson; a clean day says so; the page renders the real payload
  (server-side render check).
- Rollout: with this branch (expiry-v3 first). No new settings. The
  partner's app: a separate app in the owner's developer account (owner).
- Rollback: revert the commit; the review falls back to the coach page and
  the older note text. `partner_stop_orders` is inert when unused.
- Remaining:
  - [ ] First Zerodha evening on Production: read the lesson against the
    partner's Kite order book and the 5-minute prices; adjust wording or
    thresholds only with the owner.
  - [ ] Check how Kite reports a modified SL order's `order_timestamp`; the
    stop checks use it as the time the stop was placed.
  - [ ] After two weeks of reads, check the Progress patterns against what
    the partner says they did.
## October 21 (evening) — O21-PK the partner's Zerodha fills and a coach-only review page (done, Dev, commit `9648f95`, branch `codex/partner-coach-standard-capital`, pushed, deployed: merged by PR #112 (`046f3ff`), running in Production at `582d7a5` (Oct 23 audit attestation))

- Problem:
  - Owner (Oct 21): "the partner won't go on the dashboard for tracking his
    entries of the day ... fetch his orders and all from the free api? The
    partner should only go to dashboard at end of day to get his learnings."
  - Facts: O21-PC needs a tap or reply per trade; the dashboard needs the
    owner's Zerodha session, so the partner could not open it at all; Kite
    Connect Personal (free) reads orders and trades (no market data), and
    reads need no static IP.
- Files: `partner_broker_sync.py`, gateway `server/routes/partner-kite.js`
  (new); `partner_coach.py`, `partner_fill_capture.py`,
  `partner_orchestrator.py`, `routes_partner_coach.py`, `config.py`,
  `tests/conftest.py`; gateway `app.js`, `config.js`, `routes/auth.js`,
  `routes/proxy.js`, `services/kite.js`;
  client `App.jsx`, `pages/PartnerCoach.jsx`, `utils/partnerCoach.js`.
- Contracts:
  - New table `partner_broker_days`; reports in `partner_trade_reports` with
    `source` ZERODHA, `price_basis` BROKER_FILL, `trade_at_basis`
    EXCHANGE_FILL, `dedup_key` `kite:<order_id>` (upsert while ACTIVE).
  - New settings: `PARTNER_KITE_API_KEY`, `PARTNER_KITE_API_SECRET`,
    `PARTNER_KITE_USER_ID` (empty: feature off), `PARTNER_KITE_BASE_URL`,
    `PARTNER_ZERODHA_SYNC_ENABLED` (True), `PARTNER_FILL_BUTTONS_WITH_ZERODHA`
    (False).
  - Engine routes POST `/partner/broker/session`, GET `/partner/broker/status`,
    POST `/partner/broker/sync`; golden `tests/main_surface_golden.json`
    regenerated (three additions only). No new job: `partner_eod_wrap` calls
    `partner_broker_eod` before `partner_coach_eod`.
  - Gateway: `/api/partner-kite/callback`, `/api/partner-kite/coach`,
    `/api/proxy/partner/broker/sync`; session flag `partner_view`;
    `/api/auth/status.partner_view`. Owner callback guard: optional
    `ZERODHA_USER_ID` and `PARTNER_KITE_USER_ID` in `node-gateway/.env`; a
    refused account redirects to `/login?error=wrong_account`.
  - Coach: status NOT_TRADED, `summary.cards_not_traded`,
    `data_quality.superseded_by_zerodha`, `view.zerodha`, note
    `awaiting_zerodha`; `analyse(..., complete_days=)`.
- Acceptance (met in Dev): only the four allowlisted Kite calls can be made;
  a session for another account is refused and logged out; the token is in
  no response or status; one report per filled option order with exact
  prices and first-fill time; re-reads refresh the same row; Zerodha fills
  replace taps; untraded cards are NOT_TRADED only after a complete read;
  the note waits for the read and is sent once; a partner session opens only
  the coach view (gateway tests).
- Rollout:
  1. Merge after `codex/production-correction-hedge-p0` (expiry-v3), with
     the rest of this branch; rebuild engine and gateway.
  2. Owner: in their developer account, create a separate app with the
     partner's Zerodha client ID (the partner is the owner's parent:
     immediate family under Zerodha's static-IP rule; owner's decision,
     Oct 21 night); redirect URL
     `https://<NGROK_URL>/api/partner-kite/callback`; the free Personal type
     if the console offers it. The owner puts the key, secret and partner's
     Zerodha user ID in the root `.env`, never in chat. The owner also puts
     `PARTNER_KITE_USER_ID` (and their own `ZERODHA_USER_ID`) in
     `node-gateway/.env`, then restarts the engine and gateway.
  3. Tell the partner: after 15:40 tap "Open today's review", log in to
     Zerodha, read the review. The same day: Kite's order book holds only
     the current day's orders.
- Rollback: blank `PARTNER_KITE_API_KEY` or `PARTNER_ZERODHA_SYNC_ENABLED=false`
  (cards get their buttons back, the note goes back to tap-based); or revert.
  The table is inert when unused.
- Remaining:
  - [ ] First live login on Production: `partner_zerodha_login account=..`,
    `partner_zerodha_synced` with the partner's order count; compare the
    Coach page with the partner's Kite order book for that day.
  - [ ] Confirm the Personal plan returns `/trades` (Zerodha lists order
    management). If it is refused, `partner_zerodha_trades_unavailable` is
    logged and each order's own average price and exchange time are used.
  - [ ] Check whether ngrok shows its browser warning page on the callback;
    if it does, the partner taps "Visit site" once per login.
  - [ ] The O21-PC rows below still apply (flag wording only with the owner).
## October 21 (afternoon) — O21-PC partner fill capture + coach, O21-SC standard capital, O21-BS F&O broker backstop (done, Dev, commit `b580af2`, branch `codex/partner-coach-standard-capital`, pushed, deployed: merged by PR #112 (`046f3ff`), running in Production at `582d7a5` (Oct 23 audit attestation))

- Problem:
  - Owner (Oct 21, planning ₹10k–12.5k real money): standardise the books on
    one capital (₹2L/₹5L) to test properly, scale down later; "the broker
    side thing sure"; capture the partner's real fills and coach the manual
    partner on FOMO/revenge mistakes; the rest at our call. Host reliability
    (point 4) is the owner's decision, not done.
  - Facts: no partner fill was ever recorded (0 rows); every book uses a
    different notional; live F&O stops exist only in the engine (Oct 16:
    321-minute outage in market hours).
- Files: `partner_fill_capture.py`, `partner_coach.py`, `standard_capital.py`,
  `fno_broker_backstop.py`, `routes_partner_coach.py` (new); `partner_bot.py`,
  `hedge_advisory.py`, `partner_orchestrator.py`, `scheduler_setup.py`,
  `main.py`, `fno_executor.py`, `fno_orchestrator.py`, `fno_entry_plan.py`,
  `config.py`; gateway `server/routes/proxy.js`; client `App.jsx`,
  `pages/Dashboard.jsx`, `pages/PartnerCoach.jsx`, `pages/StandardCapital.jsx`,
  `utils/partnerCoach.js`, `utils/standardCapital.js`.
- Contracts:
  - New tables (idempotent DDL): `partner_trade_reports`,
    `partner_inbox_state`, `partner_coach_card_paths`, `fno_broker_backstops`.
  - New settings: `PARTNER_FILL_CAPTURE_ENABLED` (True),
    `PARTNER_INBOX_POLL_SEC` 20, `PARTNER_INBOX_LONG_POLL_SEC` 15,
    `PARTNER_COACH_REACTION_SEC` 120, `PARTNER_COACH_NOTE_ENABLED` (True),
    `STANDARD_CAPITAL_INR` 200000, `FNO_BROKER_BACKSTOP_ENABLED` (True),
    `FNO_BACKSTOP_EXTRA_PCT` 0.10, `FNO_BACKSTOP_LIMIT_GAP_PCT` 0.10.
  - New job `partner_inbox_tick` (interval); four routes; goldens
    `tests/main_surface_golden.json` and `tests/add_job_census_golden.json`
    regenerated (additions only).
  - `send_partner_result(text, *, kind, reply_markup=None)`;
    `FnoExecutor.place_stop_limit / order_state / cancel_and_read`;
    exit reason `broker_backstop`.
- Acceptance (met in Dev): see the handover receipt for tests; the
  standard-capital replay reproduces each book's own P&L at its own capital
  on Production data (read-only trial); a filled backstop is the exit and no
  sell is sent; an unprovable backstop holds the exit without claiming it.
- Rollout: merge after `codex/production-correction-hedge-p0` (expiry-v3,
  needed before the Thursday Oct 22 SENSEX expiry), rebuild engine and
  gateway outside 12:59–15:40 on an expiry day. Partner: tell them the new
  buttons ("tap Bought when you buy, Sold when you exit; reply with your
  price to correct"). With O21-PK Zerodha set up the buttons are off and
  the partner only taps the evening "Open today's review" button.
- Rollback: `PARTNER_FILL_CAPTURE_ENABLED=false` (no buttons, no polling),
  `PARTNER_COACH_NOTE_ENABLED=false`, `FNO_BROKER_BACKSTOP_ENABLED=false`;
  or revert the commit. New tables are inert when unused.
- Remaining:
  - [ ] After deploy: `partner_cron_registered jobs=16`; no
    `partner_api_rejected method=getUpdates status=409` (a webhook on the
    partner bot would block polling); the first card shows buttons; a tap
    logs `partner_fill_tap`.
  - [ ] First reported day: the Partner Coach page shows the card, plan and
    flags; the evening note arrives after the wrap; check the reasons read
    right to the partner and adjust wording only with the owner.
  - [ ] Live F&O (when the owner arms it): place-and-cancel one far SL on
    NFO to prove the order type and range before the first live entry.
  - [ ] Standard capital: EDGE morning positions cover 9 of 19 ledger closes;
    Smart Penny (event-sourced) is not in the replay; the expiry reference is
    a modelling choice (3 × budget at 2% risk) — revisit with the owner.
  - [ ] Owner decisions: host reliability (UPS / cloud VM with its own
    static IP); the standard amount to use for promotion (₹2L or ₹5L).

## October 21 — expiry-v3 (B takes BP's pair target), expiry-shadow-v5 and Oct 19 expiry-audit fixes (done, Dev, commit `a88da98`, pushed, deployed: merged by PR #112 (`046f3ff`), running in Production at `582d7a5` (Oct 23 audit attestation))

- Problem:
  - Owner order (Oct 21): apply the Oct 19 audit's expiry fixes, keep
    observing, promote a shadow that keeps beating its main (main becomes a
    shadow), add shadows where useful.
  - Oct 19 audit: BP − B +₹722.46 on the first full B window; B lost 4 of 4;
    X-1 15:38 sale read as unreachable; X-2 still index counted fresh; X-3
    tallies mixed C's v1 and v2; X-4 B's call line hid the dead put; X-5
    failed-break margin invisible.
- Files: `python-engine/expiry_paper.py`; `tests/test_expiry_paper.py` (63
  tests: BP test became the v3 B/BL test, paired test rewritten with rule
  versions, 3 new); `docs/2026-10-05-expiry-day-paper-book.md`.
- Contracts:
  - `RULES_VERSION = expiry-v3`; `SHADOW_VERSION = expiry-shadow-v5`;
    `CONTEXT_VERSION = expiry-context-v1.2`.
  - `POLICIES["B"]` = hold + pair target (`PAIR_PLAYS = B, BP`;
    `BP_TARGET` renamed `PAIR_TARGET`); `POLICIES["BL"]` = v2's B; BR = BL +
    leg stop.
  - `SHADOW_PLAYS` gains BL and CI and loses BP; `RETIRED_PLAYS = CX, BP`;
    `PAIRED_WITH` gains BL: B, CI: C; `STRUCTURE_BACK` (CI 0.0, others 0.25)
    with `STRUCTURE_PLAYS = tuple(STRUCTURE_BACK)`; `RULE_SINCE`.
  - Day-state keys `index_value`, `index_unchanged`, third `window_ticks`
    element; event keys `index`/`line` (FAILED_BREAK) and `intrinsic`
    (settlement). No schema, config or store change.
- Acceptance (met in Dev):
  - B sells both legs at the pair target and its two sell lines say "whole
    trade closed"; BL keeps per-leg exits; BP takes no entry;
  - CI sells at the box edge before C, while its ticket is worth more;
  - a still index is counted (before/from 15:15) and RV stops at 15:15;
  - tallies and paired lines split at each primary's rule change;
  - the five-expiry replay changes nothing except B = old BP, BL = old B and
    the new CI rows.
- Rollout: merge and rebuild the engine before the next expiry (SENSEX
  Thursday Oct 22). Scoring of v3 starts with the first expiry after the
  rebuild. Deploy outside 12:59–15:40 on an expiry day.
- Rollback: revert the commit. B returns to per-leg exits and BP to the
  shadows; stored BL/CI rows stay and print nothing.
- Remaining:
  - [ ] After deploy, on the first expiry: the header reads `rules
    expiry-v3`; B, BL, BH and BR share one strangle; the summary shows "index
    unchanged from the previous tick", "BL-B …", "CI-C …" and "B …/… (…;
    since expiry-v3 …)".
  - [ ] Promotion rule going forward (owner): a shadow that keeps beating its
    main on the paired line becomes the main. Watch CI − C and BL − B per
    entry; CI needs forward expiries (its rule was drawn from seen data).
  - [ ] A is unchanged (lost 4 of 5, +₹3,559.57 lifetime); AE was tested and
    rejected in-sample. Look for an A idea from new forward days only.
  - [ ] The ten-second clock costs money in 15:15–15:30 (Oct 19: B's trail
    line 32.47 filled at 28.15). A faster tick in the B window is an execution
    change (`expiry-exec-v3`), not done.

## October 19 — Oct 19 audit fixes O19-E1/P1/P2/S1/S2/O1/F1/M1/M2/B1 (done, Dev, commit `d12bb1d`, pushed, deployed by PR #111)

- Problem (Production deep audit 2026-10-19, non-expiry; owner: partner
  quality must not deteriorate, EDGE investigate/fix, profit-lock shadow,
  Smart fix and smarter, overnight and housekeeping at our call, Momentum/
  Penny smarter, DR-on-expiry and expiry left to the owner):
  - E1: EDGE morning scan scored today's partial bar (499 names) since late Sept;
  - P1/P2: partner updates 1 per 2 min across cards, cap could drop a reminder;
    never-sent cards stayed `can_send`;
  - S1/S2: Smart halted entries when a held name was unquoted; merged halt reason;
  - O1: overnight book 50% in one name;
  - F1: profit lock exits early on trend days (Oct 15, Oct 19);
  - M2: Momentum 0 accepts on red days (crossover-only entry);
  - B1/M1: F&O catalogue waited for the penny refresh; 19 heartbeat messages.
- Files: `penny_edge_live.py`, `penny_edge_orchestrator.py`, `hedge_advisory.py`,
  `partner_manual_advisory.py`, `penny_smart_shadow.py`, `penny_scanner.py`,
  `edge_overnight_paper.py`, `edge_portfolio_replay.py`, `fno_policy_replay.py`,
  new `momentum_rs_pullback.py`, `momentum_shadow.py`, `momentum_replay.py`,
  `backtest_lab.py`, `daily_bootstrap.py`, `main.py`, `scripts/backtest_all_yahoo.py`;
  tests `tests/test_oct19_audit_fixes.py` (15), `tests/test_momentum_shadow.py`.
- Acceptance:
  - next 09:30 EDGE scan logs `penny_edge_scan_data_window date=<previous session>`
    and a universe of ~940 band names (not 499);
  - two cards' 15:10 reminders leave in the same tick; a same-card update
    after 45 s; reminders never refused by the cap;
  - Smart `ENTRY_HALTED` rows name their condition; none from monitor batches;
  - overnight receipts: no pick above cash / open slots;
  - Momentum shadow rows include `MOM_RS_PULLBACK`;
  - `daily_bootstrap_task_done task=fno_instruments` before `penny_universe`.
- Rollout: merge to `evolve/smart-strategies`, rebuild the engine image.
  No schema migration, no new setting. Rollback: revert the commit.
- Remaining:
  - [ ] Verify the acceptance lines on the first session after deploy.
  - [ ] Score `FNO_LOCK_*` vs `CURRENT` on an export of post-Oct-7 NIFTY sessions.
  - [ ] Score `MOM_RS_PULLBACK` forward (shadow rows) and in the owner's
    simulations (`momentum-pullback` job); no promotion from one day.
  - [ ] Owner decision: DR spreads on expiry day (T-3).
  - [ ] Penny-universe refresh fetches daily history for ~10k instruments
    including bonds (60 min); an EQ-only filter would shorten it but changes
    the cache EDGE/overnight read (not done).

## October 18 — simulation-report fixes O18-F1/P1/E1/R1-R3 (done, Dev, commit `a0a3fd8`, pushed, merged by PR #111)

- Problem (Oct 13 current-strategy simulation report):
  - F1: the F&O replay read expiry days from one batch's series (INVALID
    −Rs 2,269.70 regular trade on Oct 13's expiry);
  - P1: the classic Penny replay filled paper exits at the reference price,
    the runtime 1% lower;
  - E1: EDGE overnight had no replay of the runtime book's ranking and
    realism refusals;
  - R1: EDGE/Swing/Range were entry-only ("P&L unavailable");
  - R2: no post-window data, so held positions could not resolve;
  - R3: Smart Penny and current Momentum needed hand-written scripts; the
    runner used the old Momentum T1 proxy and lacked the index context.
- Files: `fno_policy_replay.py`, `scripts/export_fno_replay_dataset.py`,
  `penny_lifecycle_replay.py`, `backtest_lab.py`, `edge_portfolio_replay.py`,
  `edge_overnight_paper.py` (refactor only), `scripts/backtest_all_yahoo.py`;
  tests `tests/test_oct18_sim_fidelity.py` (8), `scripts/tests/
  test_backtest_all_yahoo.py` (+5), updated `test_penny_lifecycle_replay.py`.
- Acceptance:
  - calendar day without archived 0DTE quotes → no trade,
    `chain_unavailable:calendar_expiry_not_archived`; archived 0DTE day →
    `expiry_day_block`; regular day unchanged; exporter records expiries;
  - PENNY_PAPER exit 97.00 → 96.03; REFERENCE keeps 97.00; broker book
    unchanged; Oct 13 REFERENCE reproduces −Rs 10.5226;
  - runtime overnight arm refuses SME/MR_mid/duplicate/day-high picks and
    fills the next ranked; study arm unchanged;
  - tail only in the portfolio snapshot; entry-dated windows; Smart/Momentum
    contracts follow settings; the index probe is reused, not re-requested.
- Rollout: none for the engine (research tools; the realism split keeps
  runtime behaviour). Next simulation: rerun Oct 13, then Oct 14, with the
  default module list. Rollback: revert the commit.
- Remaining:
  - [ ] Rerun the Oct 13 and Oct 14 simulations with this runner and the
    F&O `CURRENT` arm; compare per-module entry-dated results.
  - [ ] SENSEX single-leg and defined-risk F&O replay adapters (still
    unavailable); runtime Swing/Range bankrolls are declared defaults.
  - [ ] Strategy changes only from a multi-day window, not one seen day.

## October 15 — expiry-v2 (C takes CX's exit), expiry-shadow-v4 and Oct 15 expiry-audit fixes (done, Dev, commit `5458d2d`, pushed, deployed by PR #110)

- Problem:
  - Owner order: "replace the main with shadow if it worked", and improve the
    expiry section.
  - Oct 15 audit: CX − C +₹2,018.54 on its first forward entry; B's whole
    entry window had no data (DNS), and the whole-day tick count hid it.
  - Paired lines could pair different entries. "B entry 15:13:30" read like a
    trade.
- Files: `python-engine/expiry_paper.py`; `tests/test_expiry_paper.py` (60
  tests; CX test became the v2 C/CH test; paired test rewritten; 4 new);
  `docs/2026-10-05-expiry-day-paper-book.md`.
- Contracts:
  - `RULES_VERSION = expiry-v2`; `SHADOW_VERSION = expiry-shadow-v4`;
  - `SHADOW_PLAYS` replaces CX with CH; new `RETIRED_PLAYS = ("CX",)`;
  - `STRUCTURE_PLAYS = A, AL, C, CX`; `PAIRED_WITH` gains `CH: C`;
  - `ENTRY_WINDOWS`; day-state keys `window_ticks` and a mid-day `rules`
    mark.
  - No schema, config or store change.
- Acceptance (met in Dev):
  - C sells on the failed break, while CH and C500 hold;
  - C's buy and sell lines reach Telegram; CH sends none;
  - window counts show B 0 of 9 when B's quotes are missing;
  - paired lines match per entry (unmatched and open entries are named);
  - retired CX still prints;
  - the replay of four retained expiries changes only C's rows, exactly to
    CX's Production and replay results.
- Rollout: merge and rebuild the engine before the next expiry (NIFTY
  Oct 19 per the catalogue). Scoring of v2 starts with the first expiry after
  the rebuild. A day begun before it is labelled "expiry-v1+expiry-v2 from
  mid-day".
- Rollback: revert the commit. C returns to v1 and CX to the shadows; stored
  CH rows stay and print nothing.
- Remaining:
  - [ ] After deploy, on the first expiry: the header reads `rules
    expiry-v2`; a C row exists beside a CH row with the same entry; the
    summary shows "window ticks with a fresh index" and "CH-C … over n
    entries".
  - [ ] B is the weakest play (lost 3 of 3 traded). BP is the leading
    replacement (in-sample −₹1,185.33 against B −₹3,461.61), but it has no
    forward win. Promote only after BP − B is positive on later forward
    expiries, by the same per-entry paired line.
  - [ ] The Oct 15 B window was lost to DNS. Provider and DNS resilience is
    outside the expiry module; the owner is handling the rest of the system.

## October 15 (evening) — Oct 15 audit fixes O15-N1/H1/M1/R1/B2/D1/D2 (done, Dev, commit `a6d820d`, pushed, deployed by PR #110)

- Problem (Oct 15 audit, Production PR #109):
  - N1: a 14:57–15:15 DNS outage blanked quotes; `http_errors` was `{}`,
    health read OK afterwards, nobody was paged;
  - H1: historical peak 4/s against the documented 3/s, one 504;
  - M1: the 15:10 buyer reminder failed with a DNS `ConnectError`, went to
    manual recovery and expired unsent;
  - R1: a 168 s host restart with a spread held did not page (300 s bar);
    the EDGE token wait counted polls, not elapsed time;
  - B2: a stale sample could be labelled "at the stop"; wrap paths ran past
    the 15:15 exit;
  - D1: docs still said "not deployed" for code running since PR #109;
  - D2: Oct 14's NO ENTRY notice arrived Oct 15 with no date.
- Files: `kite_client.py`, `routes_ops.py`, `lifecycle_receipts.py`,
  `ops_watchdogs.py`, `partner_bot.py`, `hedge_advisory.py`,
  `partner_buyer.py`, `partner_orchestrator.py`, `penny_edge_orchestrator.py`,
  `edge_overnight_paper.py`; tests `tests/test_oct15_audit_fixes.py` (28),
  updated `test_oct13_audit_fixes.py`, `test_partner_orchestrator.py`,
  `test_kite_endpoint_budget.py`, `test_edge_overnight_paper.py`.
- Acceptance (Dev tests, fake clocks/transports):
  - DNS errors count as `transport_errors.dns`; any answer closes the
    outage; a 19-min market outage queues one start and one end page, the
    end retiring the start; < 120 s, < 5 failures or after hours: no page;
  - no 4 historical sends inside one window; all three call sites gated;
  - `ConnectError`/`ConnectTimeout` → `unsent_connect` → retried once after
    30 s and delivered; `ReadTimeout`/protocol errors stay manual;
  - 168 s gap with a spread open pages; flat book under 300 s does not;
  - a 10:00 sample is not "at the stop" for 11:45; 15:27 prints are not
    the card's result; EDGE wait ends by elapsed time and on a frozen clock;
  - late overnight notices are dated in the sent text only.
- Rollout: merge, rebuild the engine. No migration; no config change. The
  outbox file `restart_alert_outbox.json` also carries outage pages.
  Rollback: revert the commit; no stored state depends on it.
- Remaining:
  - [ ] After deploy: a provider outage ≥ 2 min in market hours gives one
    "down" and one "back" page; `/ops/provider-budget` shows
    `transport_errors`, `connectivity` and `historical_gate_waits`;
    historical `over_documented_limit` stays 0.
  - [ ] A buyer reminder that hits a connect failure is delivered on retry
    (`unsent_proven` in its claim detail).
  - [ ] Ops: the outage cause (host network/router/DNS) is outside the
    container; check the host when the page arrives.

## October 15 — expiry-shadow-v3 and Oct 13 expiry-audit diagnostics (done, Dev, commit `db6e028`, pushed, deployed by PR #109)

- Problem:
  - The owner wants the expiry book to profit more consistently and never
    lose "like crazy".
  - The Oct 13 audit: losing expiries were lost by bought options riding to
    zero (C's ticket on Oct 6 and 8; B's legs on all three days).
  - Medium findings: an OK context hid missing fields (903/966); path marks
    hid their denominators (95/159); paired shadow results were not printed.
- Files: `python-engine/expiry_paper.py`; `tests/test_expiry_paper.py` (57,
  6 new); `docs/2026-10-05-expiry-day-paper-book.md`.
- Contracts: `SHADOW_VERSION = expiry-shadow-v3`; `SHADOW_PLAYS` gains CX and
  BR; `PAIRED_WITH`, `STRUCTURE_PLAYS`, `BR_LEG_STOP = 0.50`. New day-state
  keys: `marks[*].held`, `marks[*].unmarked`, `context_fields`. No schema
  change; no new store or config.
- Acceptance (met in Dev):
  - CX sells at the first tick back past A's failed-break level, while C
    holds;
  - BR sells a decaying leg at ≤ 50% of entry and keeps B's exits on the
    other leg;
  - unmarked reasons are named; context fields are counted;
  - paired lines skip expiries where only one side traded;
  - the replay of the three retained expiries reproduces Production rows (0
    mismatches), and the diagnostics equal the audit's counts.
- Rollout: merge and rebuild the engine. Scoring starts at the first expiry
  after deploy. It was deployed before the Oct 15 SENSEX expiry (audit: CX row, v3 state). A day
  begun before the rebuild is labelled "+expiry-shadow-v3 joined mid-day".
- Rollback: revert the commit. Stored CX/BR rows stay in the store and
  print as plays; nothing reads them.
- Remaining:
  - [x] (Oct 15 audit; BR had no entry, DNS outage) After deploy, on the first expiry: CX and BR rows exist with their
    primary's entry; the summary shows "held ticks marked", "available on
    ticks" and "paired with its primary".
  - [ ] At the owner's 10-expiry review: present CX−C and BR−B to date with
    the per-play tally. Any promotion is `expiry-v2`, scored on later
    expiries only.

## October 15 — second review R1/R2 (done, Dev, commit `934aa2c`, pushed, deployed by PR #109)

- Problem:
  - R1: a slow first EDGE fill let a second admission happen at 15:16;
  - R2: a restart page queued during another page's send was lost by a
    stale whole-list save.
- Files: `penny_edge_orchestrator.py` (`_run_one_leg` cutoff and clock),
  `lifecycle_receipts.py` (`_update_alert`, row-scoped saves); 3 tests in
  `tests/test_oct13_audit_fixes.py` (49 total).
- Acceptance (met):
  - a delayed first fill blocks the second admission and keeps its own
    position; no cutoff means no change;
  - pause an old send, queue a new page, acknowledge the old → both kept,
    and the new one delivers next;
  - a failed send with a concurrent caller keeps both pages and respects
    the backoff.
- Remaining: first-day observation as in the F1–F5 entry.

## October 15 — review F1–F5 of the Oct 13 fixes (done, Dev, commit `ec1d5a2`, pushed, deployed by PR #109)

- Problem (independent review of `433a81a`):
  - F1: the EDGE catch-up could scan at 15:20;
  - F2: an EDGE error wrote the daily completion marker;
  - F3: target → stop → recovery still showed the recovery as held;
  - F4: restart exposure skipped the sibling books, and the page had no
    acknowledgement or retry;
  - F5: the hourly fill could be taken from an unrelated EDGE position.
- Files: `penny_edge_orchestrator.py`, `scheduler_setup.py`,
  `partner_orchestrator.py`, `lifecycle_receipts.py`, `main.py`,
  `ops_watchdogs.py`, `penny_hourly_report.py`; tests in
  `tests/test_oct13_audit_fixes.py` (46 total, 14 new for F1–F5).
- Acceptance (met in Dev tests, with fake clock, provider and gateway):
  - F1: a token at 15:20 after a 15:14:59 start gives no scan; a token
    before the cutoff gives one scan; a scan crossing 15:15 enters nothing;
  - F2: error then healthy run retries once, then is idempotent; a
    zero-candidate day counts as completed; a torn receipt allows recovery;
  - F3: target → stop → recovery is labelled not held, and target-only
    keeps the whole path;
  - F4: a sibling-only overnight position is counted; an unreadable store
    shows "unknown"; 503 then 200 delivers once; a 422 or stale page stops
    retrying;
  - F5: the fill matches by attempt identity; the unrelated EDGE ₹70 fill
    is never used; unfilled or ambiguous signals show "fill n/a".
- Rollout: merge, rebuild. New files `restart_alert_outbox.json` (last 50
  rows) and `penny_edge_scan_state.json` (now carries `status`). A
  pre-change state file has no status and reads as not completed, so at
  worst there is one extra catch-up scan on deploy day (entries are deduped
  per ticker per day).
- Remaining:
  - [ ] After deploy: one `penny_edge_scan_state.json` with
    `status: COMPLETED` a day; no EDGE entry after 15:15; on a market-hours
    restart, one acknowledged page listing every book.

## October 13 — Oct 13 audit fixes O13-B1/B2/B3/B4/Q1/Q2/R1/P1 (done, Dev, commit `433a81a`, pushed, deployed by PR #109)

- Problem (Production audit of the clean Oct 13 run, PR #108; expiry
  excluded):
  - buyer ideas got "Book profit" after "EXIT … Idea closed";
  - one quote over-limit came from a late batch task;
  - a dispatcher cancelled during admission stranded callers;
  - failed pulses used up the cap;
  - SENSEX was charged NSE option fees;
  - the wrap said "no level hit";
  - Penny Avg R read 0.0 and the hourly report showed the signal price;
  - a 94-minute market gap had no cause on record.
- Files:
  - `partner_manual_advisory.py`, `hedge_advisory.py`,
    `partner_delivery_blockers.py`, `partner_buyer.py`,
    `partner_orchestrator.py`;
  - `kite_client.py`;
  - `fno_costs.py`, `fno_orchestrator.py`, `fno_positions.py`,
    `fno_shadow.py`;
  - `lifecycle_receipts.py` (new), `main.py`, `ops_watchdogs.py`,
    `scheduler_setup.py` (EDGE catch-up);
  - `penny_daily_attribution.py`, `penny_hourly_report.py`,
    `penny_executor.py`;
  - tests: `tests/test_oct13_audit_fixes.py` (32 new) plus updates to
    `test_partner_buyer.py`, `test_partner_manual_advisory.py` and
    `test_scheduler_tick.py`.
- Acceptance (met in Dev tests):
  - after a stop: no target, reminder or authorizer pass, while the stop
    itself still sends;
  - pre-change rows are closed on the next pass;
  - the delayed-task probe keeps sends ≥ 1/rate apart; every numeric and
    keyed attempt goes through the gate;
  - a cancelled dispatcher releases queued callers;
  - six failed pulses leave the success cap intact;
  - BFO fees match the audit's same-fill figures;
  - Penny R = −3.72 and the hourly report shows "@ 51.92 (signal 52.92)";
  - restart receipts tell host sleep, stall and VM restart apart;
  - the EDGE catch-up waits for the token and runs at most once a day.
- Rollout: merge, rebuild the engine. No schema change: the new idea status
  is a TEXT value, and pulse detail is JSON. A new file,
  `lifecycle_events.jsonl`, is bounded to about 2,000 lines.
- Rollback: revert the commit. Ideas already `CLOSED_INVALIDATED` stay
  terminal, which is safe.
- Remaining:
  - [ ] After deploy:
    - no `TARGET_ZONE` or `SESSION_EXIT_REMINDER` after an `INVALIDATION`
      for the same `advisory_id`;
    - `/ops/provider-budget` quote `over_documented_limit` 0;
    - `send_gate_waits` small;
    - the restart receipt line `lifecycle_startup_receipt` at boot.
  - [ ] Ops: if a market-hours restart page fires, use the cause field plus
    host logs (Windows sleep and power settings) to stop it recurring.
    Oct 13's gap fits host sleep (container restarted at 11:40:05 after
    no output since 10:05).
  - [ ] Research collection whole-job p95 rose to 22 s (from 7.5 s) on an
    expiry day with held positions. It is under its 55 s misfire window;
    watch it after deploy, and do not move it to bulk (see
    `kite-provider-lanes`).
  - [ ] Data: deploy `/data/nifty500.csv` and the curated
    `penny_company_data.json`. The in-code universe still lists renamed
    names.
  - [ ] Option (needs a frozen comparison): a Penny paper exit at the
    visible bid walk instead of a 1 % fixed decrement.
  - [ ] Classic Penny positions close as `CLOSED_TIME` even on a stop
    (`main.py` settle path). This is a label only, since the ledger notes
    hold the true reason; change it only with consumers checked.

## October 12 (night) — O12-PB2 card numbers verified on Production data (done, Dev, commit `feed23e`, pushed, deployed by PR #108)

- Problem: the partner trades real money, so each number on the card must
  be checked against what markets actually did, not just modelled.
- Evidence (read-only, Production):
  - 41,950 snapshot pairs (premium model);
  - 184 SENSEX index samples (index conversion);
  - replay of the five delivered Oct 6–9 cards.
- Files: `partner_buyer.py` (`BUYER_VIEW_V2`: decay 60 min, target range
  0.85, loss at SL from the limit with spread and charges, exact stop price,
  near-stop flag, SL-order wording); `partner_orchestrator.py` (near-money
  PCR label); `tests/test_partner_buyer.py` (20 tests).
- Acceptance (met):
  - decay pinned to Black-76 at T − 60 min;
  - loss at SL equals the hand formula;
  - stop printed at its exact price;
  - Oct 7 13:11 card flagged near-stop;
  - "reward < risk" judged on the low end.
- Calibrations are in-sample (6 sessions) and documented with their samples.
  They are display estimates, not strategy parameters. Re-measure after
  20 more sessions.
- Remaining:
  - [ ] After deploy: compare each card's `≈` index levels with the real
    index, and each target range with the option at the target event.
  - [ ] Owner: 4 of 5 recent cards are reward < risk in premium terms. A
    premium-aware target or strike choice for buyers is a strategy change,
    so it needs frozen rules and forward scoring.

## October 12 (evening) — O12-PB partner messages for an option buyer (done, Dev, commit `304ad70`, pushed, deployed by PR #108)

- Problem:
  - the partner only buys options now and no longer hedges;
  - cards were 1,670-character debit-spread texts valid for 30 s, with
    levels on the future (about 60 points over the index on Oct 9);
  - updates spoke of "the paired structure";
  - OI alerts were silenced, or else came five to a minute.
- Files:
  - `partner_buyer.py` (new, pure);
  - `partner_manual_advisory.py` (`persist_candidate(buyer_view=)`, update
    and reminder wording);
  - `partner_orchestrator.py` (buyer view in the advisory tick, flow pulse,
    pin helper, crisis-only regime notice, brief and wrap);
  - `config.py`: `PARTNER_BUYER_MESSAGES`, `PARTNER_BUYER_INDICES`,
    `PARTNER_BUYER_ENTRY_WINDOW_MIN`, `PARTNER_FLOW_PULSE_DAILY_CAP`;
  - tests: `test_partner_buyer.py` (new, 13); `test_partner_orchestrator.py`
    (+5, legacy fixture pins the flag off).
- Acceptance (met in Dev tests):
  - card under 400 characters, still opening with the dispatch label;
  - identity unchanged; index levels shifted by the parity offset, or
    marked `fut` without parity;
  - one-line updates; one pulse per tick with throttle and carry-over;
  - brief under 500 characters; wrap with the option premium path.
- Rollout: merge, rebuild the engine. No schema change (`buyer_view` lives
  in the JSON payload). Rollback: `PARTNER_BUYER_MESSAGES=false`.
- Remaining:
  - [ ] First live day after deploy: read the partner log lines (cards,
    pulses, brief, wrap). Check the card's index levels against the actual
    NIFTY/SENSEX index, and count pulses per index.
  - [ ] Option (owner decision): pick the buyer's strike at the parity
    forward's ATM instead of the future's. It would need its own quote
    validation.
  - [ ] Option: align the scan with bar closes (every 5 min at :50 plus a
    retry). That first needs the collection-completeness slot model
    updated.

## October 12 — Oct 12 audit fixes O12-F1/R1/Q1/Q2/C1/C2/T1–T3/S1/D1 (done, Dev, commit `d4a75fc`, pushed, deployed by PR #108)

- Problem (Production audit, PR #107 deployed):
  - flat 10 s fast-exit passes took the F&O lock from 4 regular entry
    passes;
  - 10 DR entry passes ended at the 20 s read budget;
  - quote merger lane and fairness gaps; keyed requests > 500 unbounded;
  - a truncated instrument dump counted as a success, and naive or future
    snapshot clocks were not refused;
  - spread-tilt pairing lacked identity, used a live lot cap and had no
    drawdown, and its hourly read was synchronous;
  - the Smart day total omitted carried exits.
- Files:
  - `fno_orchestrator.py`, `fno_chain.py`, `scheduler_setup.py`,
    `kite_client.py`, `config.py` (`FNO_TICK_FAST_EXIT_WAIT_SEC`);
  - `fno_spread_tilt.py`, `fno_hourly_report.py`, `penny_smart_shadow.py`,
    `edge_overnight_paper.py`, `ops_watchdogs.py`;
  - tests: `test_oct12_audit_fixes.py` (new, 25), `test_fno_fast_exit.py`,
    `test_fno_orchestrator.py` (2 quote calls, not 3), `test_oct9_audit_fixes.py`,
    `test_kite_client.py` (dumps padded to ≥ 1,000), `test_edge_overnight_paper.py`.
- Acceptance (met in Dev tests):
  - a regular tick waits for a running fast pass and then runs;
  - a flat fast pass never calls management;
  - a regular tick still skips behind a regular tick;
  - an anchored chain makes 1 request, and a moved anchor retakes it;
  - DR reads run in the management lane, which does not leak to the caller;
  - a management read arriving during a bulk wait rides the next batch,
    labelled management;
  - a streaming management load cannot hold a 500-token bulk read beyond 3
    batches;
  - a cancelled batch releases its callers;
  - 501 keyed requests go as 500 + 1;
  - a truncated dump retries and then recovers, and a full dump drops
    delisted symbols;
  - naive, future and garbage snapshot clocks are refused;
  - the tilt does not pair across underlyings or expiries, an ambiguous
    spread is UNAVAILABLE, the frozen cap ignores runtime 9, open sides wait,
    and drawdown is in close order;
  - the hourly report keeps the loop alive and reports a late read;
  - the Smart exit date shows 12 closes / −₹11.44.
- Config/migration: one new setting (`FNO_TICK_FAST_EXIT_WAIT_SEC=20`); no
  schema change; new JSON fields only.
- Rollout: merge, rebuild the engine. Rollback: revert (no stored-state
  change).
- Next (after deploy):
  1. `fno_tick_skip reason=fno_pass_in_progress` should be ~0, and
     `fno_tick_wait` appears only with an open leg.
  2. `fno_dr_entry_skipped` count and `dr_entry_read_sec` per stage should
     be far below 10/day, with entry-read median well under 5 s.
  3. `/ops/provider-budget` quote: over_documented_limit 0, plus
     `fairness_promotions` and `spacing_waits`.
  4. Tilt: first forward pair; review at 20 with net, worst and drawdown
     (owner decides).
  5. Still open: C4/C7/finalizer deferred items; next expiry (NIFTY Oct 13,
     SENSEX Oct 15) is the expiry agent's.

## October 9 (night) — F&O shadow FNO_SPREAD_TILT_V1 (done, Dev, commit `2d658b8`, pushed, deployed by PR #107)

- Problem: the owner asked for more profit / less loss. The paper spreads
  outperform the naked options per rupee of risk but stay 1 lot.
- Files: `fno_spread_tilt.py` (new), `fno_hourly_report.py`, `routes_ops.py`,
  `tests/test_fno_spread_tilt.py` (new, 4), `tests/main_surface_golden.json`
  (one route).
- Acceptance (met): pairing by tick and option type; lot cap and never below
  the actual lots; cash net, not model net; forward/in-sample split; report
  line; read-only (`can_place_orders: false`).
- Decision rule (frozen now): after 20 forward paired signals, compare paired
  net, worst trade and drawdown. The owner decides whether the real book
  tilts. Not tuned further on seen days.
- Owner decisions recorded: no re-entry ban after a stop; no early cut of
  any expiry play (the 10-expiry rule is the decision point); Momentum and
  EDGE are left as they are unless a genuine improvement appears.

## October 9 (evening) — open items closed (done, Dev, commit `68e965a`, pushed, deployed by PR #107)

- Problem: the Oct 9 audit's remaining items: F&O profit-lock floor missed by
  the 90 s sample; gateway 413 for any oversized notify; unexplained
  ledger/position gaps; two Smart positions OPEN.
- Files: `config.py`, `tests/test_fno_fast_exit.py`, `tests/main_surface_golden.json`,
  `node-gateway/server/app.js`, `routes/internal.js`, `utils/split-message.js`
  (new), gateway tests (2 new files, 2 new notify tests),
  `docs/2026-10-09-ledger-position-reconciliation.md` (new).
- Acceptance: fast exit registered by default (surface golden lists
  `fno_fast_exit` 10 s); 30 KB notify accepted and other routes still 413;
  long best-effort alert sent as parts, each ≤ 4,096 and rebuilt exactly;
  every ledger gap matched row by row (sums equal the audit deltas).
- Rollout: merge, rebuild the engine and the gateway. Rollback:
  `FNO_FAST_EXIT_ENABLED=false`; revert the gateway commit.
- Next: after deploy, watch `fno_fast_exit` telemetry, `fno_tick_skip
  reason=fno_pass_in_progress`, and quote `over_documented_limit` on
  `/ops/provider-budget`.

## October 9 — Production audit fixes O9-R1/S1/M1/O1/Q1-Q3/E1 (done, Dev, commit `959392a`, pushed, deployed by PR #107)

- Problem: a DNS failure on the 11:19 restart left the symbol cache empty
  all afternoon (no retry); Smart held exits, Momentum, Penny and the
  overnight entry went blind; Momentum heartbeats hit HTTP 413; quote sends
  could bunch past 1/s; instrument-keyed 429s were uncounted; >500-token
  requests were unchunked; two bad expiry notices could block a healthy one.
- Files: `kite_client.py`, `main.py`, `ops_watchdogs.py`, `routes_ops.py`,
  `penny_smart_shadow.py`, `penny_scanner.py`, `edge_overnight_paper.py`, `expiry_paper.py`,
  tests `test_oct9_audit_fixes.py` (new, 14), `test_expiry_paper.py`,
  `test_penny_cron_gating.py`, `test_scheduler_closures_invoke.py`.
- Acceptance (met in Dev tests): restart + DNS failure loads the snapshot and
  the recovery job restores a provider refresh, then no-ops; no snapshot ->
  unusable and the watchdog pages; Smart held symbols quoted by symbol with
  an empty cache; 497 unknown tickers give one family line under 10 KB and
  a 413 is logged; overnight with no quotes retries at 15:25 then records
  DATA_UNAVAILABLE; 1,100 symbols quoted in 500/500/100; a delayed shared
  limiter no longer lets two sends fall within 1/rate; 429 on the instrument
  path counted; 971 tokens chunked; two 422 expiry notices do not block a
  healthy third in the first round; Penny skips at once after a failed
  refresh. The 13 tests written first all fail on the old code.
- Config/migration: no new setting; new file `/data/nse_instrument_cache.json`;
  two nullable columns on `expiry_paper_notices`; new scheduler job
  `instrument_cache_recovery`.
- Rollout: merge, rebuild the engine. Rollback: revert (the snapshot file
  and columns are inert to the old code).
- Next:
  1. After deploy, check `/health.instrument_cache` (source PROVIDER, size
     ~9k) and that the snapshot file exists after 08:00.
  2. Two Smart positions (STEELXIND, TATSILV) are still OPEN in Production;
     they will be quoted by symbol and their pending deadline exits retried
     at the next session's first executable bid. Watch `smart_penny` on /health.
  3. `/ops/provider-budget`: quote `over_documented_limit` should be 0.
  4. Still open: gateway-side 413 handling for other senders; historical
     position-store mismatches (O9 #11); C4/C7 deferred items.

## October 8 (late night, 2) — follow-up review F1–F3 (done, Dev, commit `1f4321b`, pushed, not deployed)

- Problem: overnight admission used the pre-scan clock (could enter after
  15:29 and record 15:20) and had no snapshot TTL (F1); two permanently
  rejected notices blocked healthy ones (F2); the quote budget was only
  measured (F3).
- Files: `edge_overnight_paper.py`, `notice_outbox.py` (new),
  `kite_client.py`, `config.py` (`KITE_QUOTE_RATE_PER_SEC`), `routes_ops.py`,
  `node-gateway/server/routes/internal.js`, `services/telegram.js`, tests.
- Acceptance (met): scan crossing 15:29 refuses; actual decision time
  recorded; missing/stale/future snapshot refuses; two 422 notices and two
  unknown-failure notices do not block a healthy one over 8 rounds; outage
  retries only the first row; an acknowledged part is not resent;
  concurrent load stays within the quote budget with merged calls and
  bounded management wait.
- Config impact: new `KITE_QUOTE_RATE_PER_SEC=1.0`. Gateway contract: 422
  for rejected content (engine and gateway must be rebuilt together).
  Schema: two nullable columns on the overnight notice table (added on open).
- Rollout: merge, rebuild engine and gateway together. Rollback: revert;
  or set `KITE_QUOTE_RATE_PER_SEC=3` to match the old shared rate.
- Next:
  1. After a market day, read `/ops/provider-budget`: quote `over_documented_limit`
     should be 0, `http_429` 0, `quote_budget.max_wait_sec.management` small.
  2. Expiry agent: adopt `notice_outbox` in `expiry_paper.flush_notices`.
  3. Watch overnight 15:20 receipts for `decided_at` and the new refusals.

## October 8 (late night) — review R2–R6 (done, Dev, commit `fc58da3`, pushed, not deployed)

- Problem: independent review of the Oct 8 fixes: research arms inherited
  the changed default (R2); overnight cash-trim kept the larger order's
  price and stale quotes passed on date (R3); cohort report mislabelled
  unavailable paths (R4); agent guard could stay held (R5); provider limits
  differ by endpoint (R6). The expiry agent also flagged the overnight
  outbox blocking flaw.
- Files: `edge_overnight_paper.py`, `momentum_paper_path_adapter.py`,
  `momentum_admission_cohorts.py`, `agent/agent.py`, `kite_client.py`,
  `routes_ops.py`, tests, the research scripts and README.
- Acceptance (met): tests for the re-walked price, the stale last trade,
  the failed re-quote, outbox step-over / gateway down / long-notice parts,
  cohort unavailable attribution, guard release, budget counting; the
  research re-run reproduces both figures.
- Rollout: merge and rebuild. No schema/config change. Rollback: revert.
- Next:
  1. After a market day, read `GET /ops/provider-budget` (or the
     `kite_endpoint_over_documented_limit` lines). If quotes exceed 1/s,
     batch callers first (one `/quote` takes up to 500 instruments), then
     add a quote-specific limiter tested with Penny, expiry and F&O exits
     together.
  2. Overnight: count `stale_last_trade` and `no_fresh_quote` refusals.

## October 8 (night) — review R1: expiry summary over Telegram's limit (done, Dev, commit `c4329bc`, pushed, not deployed)

- Problem: the expanded summary (4,277 characters) would be refused by
  Telegram and block every later expiry notice.
- Files: `python-engine/expiry_paper.py` (`notice_parts`, `_notice`,
  `flush_notices`), `python-engine/tests/test_expiry_paper.py`, the design
  doc, the guide and the checklist.
- Acceptance (met): parts stay within 3,500 characters and are rebuilt with
  nothing lost; a full day is accepted under the Telegram limit with the
  prefix; a refused row is stepped over after 3 attempts and stays pending;
  with the gateway down, the flush stops after two failures; the Oct 8
  replay splits into 3,472 + 826 characters.
- Rollout: with the same merge and rebuild before October 13. Rollback:
  revert; part rows are ordinary outbox rows.
- Left to the developer agent (outside expiry): the review's R2–R6, the EDGE
  overnight outbox's same blocking pattern, and per-endpoint Kite budgets.

## October 8 (night) — Oct 8 production audit fixes (done, Dev, commit `7f028ed`, pushed, not deployed)

- Problem: the Oct 8 audit reproduced latent defects (F&O peak persistence
  without futures, inverted bought-put time-stop sign, overnight missing
  depth fails open), a scorecard wording/lookback issue, the Momentum
  cohort-pooling limit and agent status timeouts.
- Files: `fno_exit_rules.py`, `fno_orchestrator.py`, `fno_positions.py`,
  `config.py`, `edge_overnight_paper.py`, `partner_orchestrator.py`,
  `momentum_admission_cohorts.py` (new), `agent/agent.py`, tests, research
  `docs/research/fno/2026-10-08-time-stop-sign/`.
- Acceptance (met): peak kept on a no-futures tick and arms the lock on the
  next; bought CE and PE defer/exit symmetrically; live default banks at the
  time stop; missing/empty/zero depth refused; entry capped at visible asks
  with walked price; scorecard says "observed"; 30-date window; cohort split
  with the Oct 6 freeze verifying; status publish skip/streak tests.
- Config impact: `FNO_TIME_STOP_RESPECTS_PREMIUM` True → False (no `.env`
  override in Production). No schema migration (`best_premium` exists).
- Rollout: merge and rebuild. Rollback: revert the commit; to keep the sign
  fix but restore the deferral set `FNO_TIME_STOP_RESPECTS_PREMIUM=true`
  (replayed worse).
- Next:
  1. Watch the first single-leg F&O trades: `time_stop` exits in profit,
     `profit_lock`, no `fno_time_stop_deferred_in_profit` lines.
  2. Overnight 15:20: count `no_depth`, `no_sellers`, `thin_asks_*` refusals
     and compare walked entry prices with LTP + 25 bps.
  3. Owner decision pending: the F&O 15% drawdown halt sits ₹10.6k below
     current paper equity; replays show it can stop the book right before
     its trend winners. Do not change without the owner.
  4. Score selective Momentum only on `SELECTIVE_ADMISSION_V1`.

## October 8 (evening) — owner's expiry stop rule (done, Dev, commit `ab5e3a1`, pushed, not deployed)

- Owner decision: observe 8 more expiries (10 in all). If every one loses,
  stop expiry-day F&O. Drop any play or section that keeps losing on its own.
- Each day summary now prints the tally (`owner_rule_lines`). At expiry 10,
  report the verdict to the owner with the per-play counts, and recommend
  which plays to drop even if the rule is not met. The owner decides; nothing
  stops automatically.

## October 8 — first SENSEX expiry audit follow-up (done, Dev, commit `b7d3f4d`, pushed, not deployed)

- Problem: the owner asked what went wrong and right on October 8, for the
  fixes, and for better strategies, on the expiry module and report only.
  The audit found:
  - strategy losses, not data faults: a one-lot A gave back ₹1,090 from its
    best mark; B's losing put and C both settled at zero;
  - a 966 vs 967 slot count;
  - latent stale OI in the context;
  - nominal snapshot labels;
  - a shared-limiter wait tail of up to 28.9 s.
- Files:
  - `python-engine/expiry_paper.py`;
  - `python-engine/scheduler_setup.py` (tick guard);
  - `python-engine/tests/test_expiry_paper.py`;
  - the design doc, the guide, this plan, the checklist and the atlas.
- Acceptance (all met):
  - 966 slots, and no tick at exactly 15:40;
  - stale OI is excluded, with coverage recorded;
  - the batch runs in the management lane and the lane is restored afterwards;
  - `liquidation_net` walks the depth and returns None on stale, shallow or
    missing quotes;
  - AL's lock is half the peak gain for one lot and A's bank for two or more;
  - AL copies A's entries;
  - BP sells both legs on the first tick at target, BH is unchanged, and the
    BP mark equals its fills;
  - the summary shows the path lines and the "read" times;
  - the Oct 8 replay reproduces Production exactly.
- Rollout: merge and rebuild before the next expiry (Tuesday October 13, NIFTY, unless the calendar shifts it). That is the
  first scored day for AL and BP and the first `expiry-context-v1.1` day. No
  schema or config change. Rollback: revert; old day states are read as
  before.
- Next:
  1. Watch October 13. Expect the summary to read "ticks N of 966", the
     coverage "from N/M fresh quotes", and AL/BP rows. Max decision lag
     should drop if limiter queueing was the cause.
  2. Confirm the official SENSEX/NIFTY settlement price against our sampled
     index (still open since October 6).
  3. Isolated Dev tests from audit item 5 (send failure, a crash between ACK
     and commit, restart with open legs, an absent final sample) are still to
     be written.
  4. After 20 expiries, score `expiry-v1`, v1 shadows and v2 shadows on their
     own records (AL/BP from October 13). Test an IV/RV gate on D's recorded
     context; freeze it as `expiry-context-v2` only if it holds.

## October 7 (evening) — owner-requested profit keeping + Oct 7 audit fixes (done, Dev)

- Source: Production `docs/2026-10-07-production-deep-audit.md` (read-only),
  and the owner's question of how to keep small profits without pausing half
  the market.
- Done:
  - F&O profit lock and re-entry confirmation (paper, on by default). The
    flags `FNO_PROFIT_LOCK_ENABLED` and `FNO_REENTRY_REQUIRES_CONFIRMATION`
    turn them off.
  - Audit fixes: T1 overnight retry, T2 D reserve breach reporting, T3
    attribution date check.
  - Momentum selective entry turned on (owner decision; round-3 skipped,
    unscored). Penny noise stop was already on.
  - Overnight: an exit records `open_is_prev_close`; the forward fidelity
    check is in SYSTEM_GUIDE.
  - Overnight realistic-entry guards, from the live-universe replay
    (`docs/research/edge-overnight/2026-10-07-live-universe/README.md`).
    The old +₹2.2 lakh study was mostly unbuyable circuit closes. The
    realistic edge is about +0.6% a trade, positive every quarter, and very
    sensitive to slippage.
- Not done, by evidence:
  - an overnight liquidity floor (it cut the edge: the edge is in thinner
    names);
  - an overnight strength filter (all live picks were already 0.96–1.0);
  - a faster F&O management cadence (no gain in the replay);
  - an early profit lock (lost money).
- Still open from the audit:
  - T4: finite research-writer wait and the unbounded outer finalizer;
  - T7 / C7: late-bar shadow closure (frozen source);
  - T8: four historical position-store mismatches;
  - T9: DB size and bootstrap cost.
- Rollout: an engine rebuild. Additive column `fno_positions.best_premium`.
  Rollback: set the two flags off, or revert.
- Watch: the evidence is in-sample (12 trades, and the margin was picked
  after seeing 4 re-entry cases). Judge only on forward paper trades.

## October 7 — expiry chain context `expiry-context-v1` (done, Dev, record-only)

- Problem: the owner asked whether the option chain, OI, change in OI and IV
  can improve the odds. The research ranked implied against realized
  volatility first, OI walls second, and change in OI, max pain and PCR as
  weak. The owner chose to observe first, then integrate what proves useful.
- Files: `python-engine/expiry_paper.py`, `python-engine/tests/test_expiry_paper.py`
  and the design doc.
- Acceptance:
  - the max pain and realized-volatility math is checked;
  - the straddle-implied IV recovers a known volatility;
  - walls, PCR, OI change and futures build-up are read correctly;
  - a whole day gives identical positions with and without OI;
  - snapshots are taken at 14:30 and 15:13:30, and the summary shows the
    context block.
- Rollout: an engine rebuild (the October 8 SENSEX expiry is the first
  observation). No schema change: the context lives in the tick JSON and the
  day state. Rollback: revert; the stored context is ignored.
- Next:
  - after October 8, check that the fields fill and look sensible on real
    SENSEX data;
  - after more expiries, freeze thresholds for a D/B IV-against-RV gate and
    an A wall label as a new version, and score them only on later expiries.

## October 6 (night) — Production audit follow-up: O1 overnight fees, A1 partner updates (done, Dev)

- Source: Production `docs/2026-10-06-production-deep-audit.md` (read-only).
  The expiry findings E1–E5 were done in `db5153d`.
- Problem:
  - O1: overnight admission debited premium only. Oct 6 left −Rs 7.59 after
    buy charges.
  - A1: a partner target update was refused by the 30 s quote bound and
    stayed QUEUED with no retry and no reason.
- Files: `edge_overnight_paper.py`, `partner_manual_advisory.py`,
  `hedge_advisory.py`, `partner_orchestrator.py`, and tests.
- Acceptance: the tests listed in HANDOVER_CHECKLIST.
- Rollout: an engine rebuild. The schema change only adds a column.
  Rollback: revert; the column is ignored.
- R1 done (`5817263`): research writers wait up to 5 s and name the holder.
  Expiry-tick telemetry was decided against (see SYSTEM_GUIDE).
- C3 done: the classic Penny kill switch is fed from the durable ledger.
- Momentum allocation holdout frozen (S7a). Evaluate after about 10 sessions
  with capital skips.
- Still blocked by the round-3 frozen sources: C4 (DP once per scrip per day,
  in `penny_risk.py`) and C7 (`momentum_shadow.py` late bars).

## October 6 (evening) — expiry shadow plays (done, Dev)

- Problem: the owner asked for changes that could make expiry trading
  profitable after the October 6 loss, without fitting October 6.
- Files: `python-engine/expiry_paper.py`, `python-engine/tests/test_expiry_paper.py`
  and the design doc.
- Acceptance:
  - BH, C500 and D run beside A, B and C on the same ticks, with no Telegram
    trade lines;
  - D's settlement loss stays inside its ceiling on a runaway close;
  - an outage values D at its maximum loss;
  - a credit too small for its charges is refused.
- Rollout: an engine rebuild, ideally before October 8, the shadow plays'
  first expiry. The schema additions only add columns. Rollback: revert; the
  extra columns and rows are ignored.
- Still open:
  - score the shadow plays beside `expiry-v1` after 20 expiries;
  - D's live use needs the owner's separate margin decision.

## October 6 — expiry first-day audit remediation, `expiry-exec-v2` (done, Dev)

- Problem: the first-day audit found these defects:
  - freshness and windows were judged at the request start;
  - fills could not be replayed (only top of book was logged);
  - a partial bank lost its remainder;
  - concurrent flushes could send a notice twice;
  - an expiry with no index quote vanished from the record;
  - SENSEX used NSE charges, and fees were not frozen per position;
  - messages showed a slice net that excluded buy fees;
  - 90 of 966 slots were skipped.
- Files:
  - `python-engine/expiry_paper.py` and `python-engine/edge_overnight_paper.py`;
  - `python-engine/cost_schedules.py` and `python-engine/config.py`
    (`FNO_BSE_EXCHANGE_TXN_PCT`);
  - `python-engine/scheduler_setup.py` (`expiry_paper_flush` job);
  - tests and goldens.
- Acceptance:
  - the audit's clock probe (one packet 15 s ahead of the start, one 15 s
    behind it) is judged at receipt;
  - a B window crossing in transit is refused;
  - the 3-wanted/1-filled bank keeps 2 pending across a restart;
  - two concurrent flushes deliver once (both books);
  - a dark index day records 217 ticks and a summary;
  - BFO charges are frozen at entry;
  - a v1 store migrates and settles.
- Rollout:
  - one engine rebuild. The gateway is unchanged; Production `70a2256`
    (PR #103) already serves `require_delivery`.
  - Schema additions are additive.
  - Rollback: revert the commit. The extra columns are ignored by v1 code.
- Not changed: strategy thresholds, the ₹2,500 ceilings, the 20 s and 5 s
  freshness limits, paper-only authority, and the owner's live halt.
- Still open:
  1. Merge and rebuild before Thursday's SENSEX expiry (October 8), the first
     BFO day.
  2. After it, read the summary's data line and the tick timing. If limiter
     wait dominates, consider reserving quote capacity for the expiry tick
     during 13:00–15:40. That decision needs evidence first.
  3. Compare our settlement sample with the official settlement price, without
     overwriting assumed rows.
  4. Run the 20-expiry review on `expiry-exec-v2` days, with October 6 shown
     separately.

## October 5 (late night) — expiry book second review (done, Dev)

- Problem: partial exits could exceed the ₹2,500 reserve; the gateway reported
  success for Telegram sends that failed.
- Files: `python-engine/expiry_paper.py`, `python-engine/scheduler_setup.py`,
  `node-gateway/server/routes/internal.js`,
  `node-gateway/server/services/telegram.js`, and their tests.
- Acceptance: the review's repro stays inside `max_loss`; `require_delivery`
  answers 502 on a refusal without a gateway retry.
- Rollout: one rebuild of both containers. Rollback: revert the commit; no
  schema change (column meanings: `costs` and `net_pnl` include the buy's
  charges from entry; no Production rows exist yet).
- Still open: as in the section below (merge and rebuild, first-expiry
  freshness check, 20-expiry review). Do not loosen the 20 s freshness rule to
  get trades; first find out whether missing timestamps, provider lag or
  request timing caused any rejections.

## October 5 (night) — expiry-day book review fixes (done, Dev)

The independent review of `f000acb` was applied. The details are in the
[design doc](2026-10-05-expiry-day-paper-book.md) "Revised" note.

Still open:

1. **Merge and rebuild.** Production runs `acc7181` and lacks the module.
2. **First expiry:** check the summary's stale-index and stale-future counts. If
   Kite index timestamps lag, the box is unusable, A and C stand down, and the
   freshness rule for index quotes needs evidence-based adjustment as
   `expiry-v2`.
3. **Initial review after 20 expiries:**
   - per play and per underlying;
   - no-trade days count as zero;
   - report net without the best day;
   - keep assumed settlements and auction-window fills separate.

## October 5 (night) — Production audit remediation (owner-directed order)

Source: [Production audit](../../Production_Trading-sentinel/docs/2026-10-05-production-deep-audit.md)
(Production report; read-only).

Done in Dev (this slice): C1 Momentum post-dispatch lock; partner informational
surfaces restored while advisory is unqualified; partner RV datetime fix; Kite
acquisition retries.

**Round-3 Kite scoring is postponed (owner, Oct 5 22:45).** The data and freezes
are committed (`ae2b775`). The 21:12 scoring run was killed at about 22:40 for
low system memory and wrote no results, so the Kite Jan–Jul 2026 data is still
unseen.
- Do not rerun until the owner names a date. Then run only
  `scripts/run_preregistered_study.py run <study> --out <dir> --jobs 1` for
  momentum-smart-t3, then penny-noise-t3. No new acquisition.
- **Freeze drift (found Oct 6).** Later commits changed bound common files:
  - `config.py`, for both studies: `653560a` added
    `PARTNER_MANUAL_ADVISORY_SEND_UNQUALIFIED` and `db5153d` added
    `FNO_BSE_EXCHANGE_TXN_PCT`;
  - `cost_schedules.py`, for Penny: `db5153d` added the BSE options path.
  - `run` therefore refuses to score.
  - A bound diff shows only those file hashes moved. The Penny effective
    settings and execution-cost snapshot are identical, and the equity cost
    path is untouched.
  - Since nothing was ever scored, the fix is to freeze both studies again
    into new dated folders right before scoring, with the same study
    definitions, and to record this reason in the study docs.
- Until then, the frozen sources stay unedited. That blocks items 1 (replay arm),
  2, 3 and 5 below.

Next, in order:
1. **Penny profit protection: paper rule implemented** (`penny_profit_lock.py`,
   see SYSTEM_GUIDE). Remaining: once round-3 scoring has finished, add a
   labelled diagnostic arm to `penny_lifecycle_replay.py` (seen data); judge the
   rule by forward paper days. No untouched Penny data is left.
2. ~~Penny durable, settlement-fed daily brake~~ done Oct 6 (`main.sync_penny_daily_brake`, no frozen file edited).
3. C7: late Momentum shadow bars (15:15 EOD exits unresolved).
4. ~~C8~~ done (whole-trade analytics).
5. C2 BSE option schedule and C4 one DP per scrip per day remain; DP ₹15.34 done.
6. ~~C5/C6~~ done (overnight outbox and catch-up).
7. ~~Scheduler IN_FLIGHT telemetry; Penny funnel stages~~ done (retried and
   parked completion writes; `ops_funnel_daily.stages_json`). Swing heads-up and
   the heatmap log name are done.
8. ~~Owner halt~~ decided: `OWNER_LIVE_ENTRY_HALT=true` in Production `.env`
   with Momentum automatic, so it trades on paper until the owner lifts the halt.
9. ~~Partner cards~~ decided: unqualified cards go out labelled PURE ADVICE —
   NOT CHECKED.

## October 5 (evening) — expiry-day paper book

[Design and frozen rules](2026-10-05-expiry-day-paper-book.md). Paper only.

1. It needs the merge and rebuild before its first expiry. The same PR carries
   the gateway fix that Telegram needs.
2. After each expiry, check the Telegram summary or `expiry_paper_days` /
   `expiry_paper_positions`. Confirm the box was READY and the tick log reaches
   15:40.
3. Score each play after 20 expiries against the pre-registered measures. Any
   rule change is `expiry-v2`, scored only on later expiries.
4. Watch the SEBI settlement decision (consultation closed Oct 3). If the auction
   settlement or session times change, record the date; B and C must be
   re-judged from then.

## October 4 (late) — start here: successor inheritance and gateway fix

Read [the inheritance doc](2026-10-04-successor-inheritance.md) first.

1. Confirm Production was rebuilt with the container uid fix and the gateway is
   healthy (it crash-looped with `SQLITE_READONLY` on October 4).
2. Read and record the round-3 Kite scoring results from the October 5, 17:07
   Windows task. The in-chat reminder was cancelled; nothing else prompts it.
3. Then continue with the items below.

## October 5 — EDGE overnight result and next steps

`edge-overnight-t1` is complete ([study](2026-10-05-edge-overnight-study.md)).
The candidate failed only the frozen drawdown check (measured against starting
capital); the S60 attribution arm passed all four.

Next, if the owner approves:

1. **E1 (done):** the `edge_overnight_paper.py` ₹25k paper book. After 10 or more
   sessions, compare it with the EDGE_PAPER book on the corrected costs. Watch
   for exits waiting on circuit-locked names (`OPEN_DELAYED`).
2. **E2 (done):** delivery costs fixed in `calc_penny_costs`. EDGE_PAPER rows
   recorded before Oct 5 used the old schedule and were not migrated, so compare
   from Oct 5 onwards.
3. **E3:** a future study must declare a peak-relative drawdown metric before
   freezing. Do not re-score `edge-overnight-t1`.

Capital floor: at least about ₹25,000 for this idea, because of the DP charge.

## October 5 — forward paper evidence and the Kite untouched scoring

Read [the slice](2026-10-05-forward-paper-evidence.md). Every module runs on paper
with live money off. New forward evidence comes from the `MOM_SELECTIVE` shadow
variant and the smart-Penny paper shadow.

Next:
1. After the owner's same-day Kite login (owner authorised ~16:30–17:00 IST,
   October 5), acquire January–July 2026 history with
   `scripts/acquire_kite_history.py`, checking coverage only. Then freeze, commit,
   push and score `momentum-smart-t3` and `penny-noise-t3` once.
2. After 5 or more sessions, compare forward `MOM_SELECTIVE` against `MOM_BASE`
   (`/api/experiments/momentum`, decision-quality report), and the smart-Penny
   shadow against the Penny paper book. Read forward data only after a
   predeclared count of sessions; do not tune on it.
3. Open items carried forward: fix the three Penny paper `exit_price` blob rows;
   Penny D1 live-risk reconciliation; momentum auto-execute stays the owner's call.

## October 4 — smart Penny implementation and matched diagnostics

Read [the current implementation receipt](2026-10-04-penny-smart-trader-implementation.md)
first. R1 strength ranking and R2 stateful affordable entry / confirmed-close
management are implemented as default-OFF paper/replay variants. The separate
paper book also owns its simulated cash, fees, working risk and daily brake;
this completes paper accounting, not R3's actual live fill/settlement contract.
T4 compares five arms on the ₹2,000 budget over two already examined windows;
do not label either an untouched holdout or optimize exits until it looks good.
Keep all losing arms and execution stress results.

T4 is complete and `NOT_SUPPORTED_STAYS_OFF`: incumbent broader net +₹91.7169
(38 trades), combined −₹47.5019 (153), entry/risk −₹47.7479 (79), exit −₹2.2712
(48), ranking unchanged. Do not promote any new trading arm. Follow the explicit
D1–D4 material slices in the receipt: reconcile live risk; independent data and
decision context; small calibrated entry utility under matched risk; exit tests
on fixed cohorts before whole-book replay. No September outcome-driven retuning.

Remaining sequence:
1. Review the frozen T4 results and failure paths. Select further work from
   stable evidence; no activation from a positive seen-window PnL.
2. R0/T3 still needs absent January–July Kite history. Acquire only through the
   existing owner-login/data-contract process; commit the freeze before any
   actual untouched scoring. No present task generated or invented that data.
3. Develop a separate exit hypothesis only after isolating selection/entry
   economics. Preserve the incumbent exit policy if thesis exits do not help.
4. R3 must reconcile actual fills, costs, open risk and classic daily settlements
   before live activation/increased risk. Candle replay cannot prove depth,
   intraminute fills or runtime sampled-quote management.
5. R4 requires genuine point-in-time universe/regime/eligibility, continuous
   portfolio capital and untouched data, then prospective paper execution
   observations. GitHub promotion is separate; Production/F&O stay protected.

Current changes remain uncommitted Dev at `a674740`; no push/deployment, funding
change or broker order. The broad regression's unchanged F&O fixture failure is
recorded in the receipt; do not silently call that run completely green.

## October 4 — authorized corrections completed; next Penny hypotheses

[Implementation and verification receipt](2026-10-04-penny-corrections-and-relative-strength-slice.md)
closes the explicit stop-arm/effective-freeze and decision-stop rounding findings
from the earlier review below. Current cached instrument ticks now control
Penny execution; dated metadata is required for new live entries. Final fill
risk, complete settlement-driven daily brakes and marked exposure remain open.
830 selected tests and a final 55-test source check passed; atlas regenerated.
Changes are uncommitted in Dev at base `a674740`, not pushed/promoted. No new
live flags, funding, F&O operational or Production changes.

Read [the researched strategy and explicit R0–R4 slices](2026-10-04-penny-consistent-returns-strategy.md).
Next: finish R0 once independently validated untouched Kite history exists and
a corrected source freeze is committed before scoring; then R1 tests persistent
positive stock-specific strength ranking while keeping entries/exits fixed.
Test broader reclaim entries and winner trails separately after selection has
evidence. R3 reconciled owner risk/daily cash accounting is required before any
live activation or increased admitted risk. Preserve all failed hypotheses,
unknown/missing-data status, costs and F&O resource priority. A daily 1% goal is
measured on allocated equity and never becomes a mandatory entry quota.

Pending T3 now distinguishes BAR_LOW/NOISE_FLOOR and ₹100,000/₹2,000 books;
its January–July snapshot path is absent. The earlier review remains a historical
receipt; its statement that no source changes were made refers to that stage.

## October 4 — Penny independent-review findings before the next study

Read [Penny efficiency review and discussion](2026-10-04-penny-efficiency-independent-review.md)
before the older round-3 sequence below. Current `penny-noise-t3` BASELINE calls
the default-ON runtime noise stop, so it cannot isolate the old-to-new stop
hypothesis. Add explicit, exactly-once stop-policy inputs and bind effective
settings before freezing/scoring. Correct rounded-distance quantity arithmetic;
review actual-instrument tick and fill/protection risk before any live promotion.
Preserve previous frozen results; do not relabel them as current-policy results.

Then complete the untouched Kite comparison with distinct old/current policies,
owner-budget economics and daily marked returns. Further hypotheses should
isolate a stop or execution/selection change on shipped entries. Research a
larger admitted risk allocation only after an edge survives; this is a material
change, not a rounding fix. Existing caps/own cash/exit recovery and F&O capacity
remain protected. The owner's daily target is an aspiration, not a trade quota.

This task is review/discussion only: findings and proposals remain open, no
source/flag change or new scoring. 45 focused tests passed; reproductions reveal
gaps those tests do not cover. `a674740` is confirmed pushed; no merge/deployment
by this task. Review docs are Dev-local/uncommitted. Tomorrow's Production/paper
decision is separate; Penny live and Momentum auto-execute remain default OFF.

## October 4 — round 3: smarter Momentum/Penny candidates; Momentum direct trading built (OFF)

Development (seen windows):
- `MOM_SELECTIVE` sat out the falling Aug–Oct market (0 trades vs shipped −₹3,110).
- The runner exit was worse on shipped entries.
- `PEN_NOISE_STOP` beat the Penny baseline (+₹93 vs +₹78; DD ₹32 vs ₹45).

Next, in order:
1. With a same-day Kite session (owner login; run after 15:45 IST), acquire Kite
   history Jan–Jul 2026 for Momentum (15-minute + NIFTY 50) and Penny (minute)
   into `docs/research/kite/2026-10-05-*`. Check coverage only.
2. Freeze `momentum-smart-t3` and `penny-noise-t3`, commit, then
   `run --jobs 3`, once each. Record the verdicts.
3. Port only a promising candidate to the runtime (paper twin first).
4. Owner decides `MOMENTUM_AUTO_EXECUTE` after promotion; recommended together
   with a passing selective entry.
5. Fix the `PENNY_PAPER` exit_price blob rows (3 rows, Aug 31).

## October 4 — owner direction: Momentum, then Penny; F&O only records SENSEX history

F&O: no further development except SENSEX/NIFTY future-candle recording
(`research_future_candles`, from the first Production run after promotion).
Next: smarter Momentum entries/exits plus direct (no-approval) execution, then
Penny, each tested with the freeze-then-score method.

## October 4 — F&O growth slice implemented (paper, Dev only)

[Growth slice](2026-10-04-fno-growth-slice.md): adaptive risk (shrink in drawdown,
grow only when proven, two-strike day halt), tighter brakes (3/6/10/15%), cap
₹40k, multi-lot capped-loss book, SENSEX on the paper single-leg book with a
NIFTY-participation proxy and a correlation guard. Vehicle-by-IV ships OFF.

Owner test Sep 17–Oct 1 (see slice): found and fixed the drawdown-cut
"silent halt"; fresh ₹2L = +₹11,821 on 10 sessions; minimum live test revised to
₹2L. Since July the paper book is −₹22k; risk rules trim drawdown only.

Remaining, in order:
1. Promote through GitHub after owner review; watch paper logs for
   `fno_adaptive_risk`, `two_strike_day_halt`, `correlated_exposure_open` and
   SENSEX entries.
2. SENSEX replay: a second read-only export with SENSEX futures candles
   (leave the frozen `2026-10-04-archive/_local` untouched), underlying-aware
   replay, frozen round on sessions from October 5, 2026.
3. BFO support in `fno_exit_evidence`/`fno_exit_recovery` before any live SENSEX.
4. Score vehicle-by-IV and the fast exit loop as frozen candidates on forward data.
5. Redesign the stale `test_mark_to_market` DR writer-row test.
6. Entry quality in losing stretches (e.g. an equity-curve pause): freeze first,
   score only on sessions from October 5.

Do not loosen F&O hard limits beyond owner approval. Nothing pushed or deployed.

## October 4 — F&O replay built; shipped book still best; speed features OFF

[F&O replay and speed slice](2026-10-04-fno-replay-and-speed-slice.md): read-only
export of the archived NIFTY quote batches, a full-policy single-leg replay
(8 of 9 live paper trades reproduced), the pure entry planner / entry brakes
now shared by live and research, and two default-OFF speed features (fast exit
loop, bar-close trigger) under one F&O lock. Pre-registered `fno-trader-v1`:
shipped baseline +₹13,306 on Sep 24–Oct 1; FNO_TRADER_V1 +₹7,128 →
NOT_SUPPORTED_STAYS_OFF (pyramid blocked by the ₹30k structural cap, trend
filter skipped winners, partial/fast exit neutral).

Next: keep the archive growing and re-export weekly; score new frozen F&O
rounds only on sessions from Oct 5, 2026 (IV-aware vehicle, time-stop variant,
BANKNIFTY); paper-enable the fast exit loop for protection after promotion.
Do not loosen F&O hard limits. Dev only; nothing pushed/deployed.

## October 4 — T2 scored; improvement options and F&O review written

[T2 receipt](2026-10-04-t2-range-swing-momentum-slice.md): shared own-cash
`daily_portfolio` book (EDGE moved onto it, regression-identical), Range and
Swing portfolio replays, Momentum `NEXT_BAR_OPEN` clock + `THESIS_EXIT`, one
pre-registration tool (`scripts/run_preregistered_study.py`) and the
[testing method guide](RESEARCH_TESTING_METHOD.md). All T2 verdicts
**NOT_SUPPORTED_STAYS_OFF**; Range reclaim (−30% loss) and SWING_TRADER_V1
(−80% loss vs baseline) are the best leads. Penny CNC fired 0 times in 9
months (rule conjunction is effectively unsatisfiable).

Owner direction: running modules (including EDGE) stay on as they are.
Next per [improvement options and F&O review](2026-10-04-improvement-options-and-fno-review.md):
Swing round 2 (market-weather switch + affordable universe) on 2024–2025;
EDGE/Range geometry rounds; F&O chain-archive retention → F&O replay →
tick-driven exit monitor → frozen F&O candidates. Windows Jan–Jun 2026 (daily)
and Aug 10–Oct 1 (Momentum) are now seen. Dev only; nothing pushed/deployed.

## October 4 — T1 Penny/EDGE trader candidates scored; none beat baseline

[T1 slice receipt](2026-10-04-t1-penny-edge-trader-slice.md). The T0 prototype
was corrected (WATCH invalidation, expiry clock, volatility stop, participation)
and completed into `PEN_TRADER_V1/V2` with thesis exits, wired into the exact
Penny replay; EDGE gained a causal own-cash portfolio replay
(`penny_edge_portfolio_replay`) and `EDGE_TRADER_V1`. Freezes were committed
before untouched windows were scored. Verdicts: **NOT_SUPPORTED_STAYS_OFF** for
both. Penny untouched (13 sessions): shipped baseline +₹63.17, V2 −₹17.02.
EDGE untouched Jan–Jun, ₹100k own cash: shipped baseline −40.17% marked, V1
−44.78%; stop/target geometry (≈+2.8% targets vs −5.2% stops at ~50% hits) is
structurally negative.

Next: (1) owner decision on pausing EDGE paper and keeping EDGE live disabled;
(2) EDGE round 2 on geometry, judged on 2024–2025 untouched daily data;
(3) weekly Penny minute archive for future untouched windows; (4) T2 Range/
Swing/Momentum adapters. Do not re-tune on Sep 7–23/Oct 1 or Jan–Jun 2026; they
are now seen. Dev commits only; nothing pushed or deployed; F&O untouched.

## October 4 — active next direction: complete adaptive trader candidates

Follow the [revised adaptive non-F&O plan](2026-10-04-adaptive-non-fno-trader-development-plan.md).
The owner wants opportunity recognition and timely thesis-based management,
not another layer of subset-only filters. T0 couples candidate selection,
complete condition evidence, native warm-up and causal cash/clock fixes with
runnable Penny/EDGE stateful prototypes. T1 completes those policies; T2 adds
Range/Swing/Momentum using existing research and audits CNC; T3 qualifies on
untouched data at matched cash/risk and proves F&O noninterference.

Preserve R1–R5 acceptance and immutable earlier results. Strategy quality cues
may change only in explicitly named research versions; hard cash/risk/approval,
execution evidence, protective stops/recovery and deadlines remain constraints.
Keep baseline reproducible, all failed trials visible and new candidates OFF.
F&O is excluded and must remain unhindered, including shared cash/resources/exits.
No live activation or promotion follows from this plan revision.

Plan-only revision at `434c4cc`, Dev-local/uncommitted, preserving earlier dirty
source/evidence. No source/configuration/schema/dependency change, new test or
backtest, Production access, broker action, commit, push or deployment. Prior
130 test passes belong to the preceding review. All T0–T3 work remains open.

## October 4 — latest independent review; finish fidelity before tuning

The owner requested minor fixes, a plan for larger gaps and an identical-parameter
Yahoo comparison. [Review and R1–R5 follow-up](2026-10-04-non-fno-independent-review-and-repeat-plan.md)
is the active next slice. **The original plan is partial**, despite N1–N3 helpers
being present. Default policies did not change; first repeat matches all 16 prior
outcomes. Candidate filters/measurement cannot imply improved live performance.

Minor corrections cover Penny retest/profile validity and Momentum ATR/regime,
same-session positive-volume/deadline evidence and settings receipts. EDGE is
PROXY until causal holding/entry/cash semantics are established. 130 focused
tests passed; compilation/diff and 241-module atlas checks passed. Final repeat
and separately named candidate evidence remain distinct in the review receipt.

Next major work: explicit candidate interface and historical context/warm-up;
causal EDGE/Momentum lifecycle with marked/partial equity; real Range/Swing
adapters and bounded hypotheses; untouched trial qualification and F&O cash/
resource compatibility. Keep F&O excluded and unhindered. No new runtime gates,
funding, shared defaults, orders or canary are authorized by this review.
Baseline `434c4cc`; Dev-local uncommitted work, no Production access/edit,
configuration/schema/dependency change, push or deployment.

[Completed comparison](2026-10-04-non-fno-review-and-backtest-results.md): both
all-module repeats reproduce all 16 original outcomes; PEN_CONTEXT zero entries
with missing profiles, Momentum exit diagnostic −₹19.01 and EDGE independent-
trial PROXY sum −₹60,813.84. None proves improvement; R1–R5 stay open. Integrity
receipts bind snapshots/raw responses, current source/settings and trial freezes.

## October 4 — active N1–N3 implementation slice (Dev only)

The owner authorized N1, N2 and N3 from the researched non-F&O plan.  The
current implementation contract is [N1–N3 implementation slice](2026-10-04-n1-n3-implementation-slice.md): first replace known optimistic research
shortcuts with deterministic lifecycle measurement, then add named,
broker-free candidates.  F&O and shared live infrastructure remain out of
scope; baseline policy stays active unless a separate rollout is approved.

**Source completion boundary.** N1–N3 code is now present: Momentum has a
named shipped-exit lifecycle, EDGE has next-open lifecycle evidence, Penny has
default-off `PEN_CONTEXT`, and Range/Swing gates are pure research helpers.
No candidate has earned a policy change. Next: freeze candidate manifests,
compare equal cash/risk with coverage and all failures retained, then pursue N4
only if full-system context can be recorded. F&O operational compatibility and
any broker/paper observation remain separate, unapproved work.

Source implementation commit `65e050a`; 109 focused tests passed (one existing
HTTPX deprecation), affected modules compiled, `git diff --check` passed and
the atlas was regenerated to 241 Python modules. Dev only: no push, deployment,
Production edit, broker action, configuration or schema migration.

## October 3 — active next direction: smarter non-F&O entries/exits

The owner requested a researched development plan after the Yahoo results.
[Smart entry/exit plan](2026-10-03-non-fno-smart-entry-exit-development-plan.md)
is the latest direction: N0 baseline/F&O isolation and N1 lifecycle economics,
then Penny MIS/EDGE experiments, followed by Range/Swing and existing Momentum
research/parity. Activity counts are setup/selection/fill-specific; ₹15.18 is
five-session Penny sensitivity, not full-system/live earnings.

**F&O development is excluded and must not be hindered**, including shared cash,
regime/configuration, scheduler/DB/broker resources and exit authority. New
variants stay broker-free/default OFF until separate qualification and rollout.
No guaranteed daily profit, capital increase or gate weakening to force activity.
Reuse existing shipped VWAP/ATR/regime/ranking/exit and S7/proactive functions.

The plan is documentation only against Dev `4be033a`; all N0–N4 source work,
data coverage, qualification and promotion remain open. Required docs/source
and primary research reviewed; delivery link/scope/diff checks recorded in the
plan. Dev-local uncommitted documentation, no source/configuration/schema change,
Production access, broker actions, push or deployment in this planning task.
Earlier instructions to await this discussion are superseded by this plan;
older F&O/S6 priorities are historical for this non-F&O development request.

## October 3 — Yahoo interface delivered; historical fidelity limits remain

The owner superseded reliance on Sentinel's retained price history for these
non-F&O tests. [Yahoo plan](2026-10-03-yahoo-all-module-backtest-plan.md),
[usage](YAHOO_BACKTEST_GUIDE.md) and [real results](2026-10-03-yahoo-backtest-results.md)
record the delivered one-script date-argument interface. Native Yahoo OHLCV,
900-day daily warm-up, immutable raw/import/validated archives and current
shipped functions are used. No strategy tuning or F&O/broker/Production path.
70 focused tests passed; final offline repeats and documentation/atlas checks
are recorded with the source commit receipt.
Source/research commit `df0c379` is Dev-local; all 16 repeated outcomes agree,
and immediate documentation/atlas/clean-worktree checks passed.

Q3 daily evaluator outputs are available, including Swing's missing index warm-up.
Yahoo does not supply expired Q3 minute/15-minute history; primaries stay
unavailable and Sep 24–30 studies stay separate. Current Penny finds 18 closes
in that partial-session sensitivity, with fragile +₹15.18 and negative adverse
fill/winner-exclusion diagnostics. Do not relax entry gates simply to trade more.

Before full-system profit claims, bind real EDGE/Swing/Range execution/exit
lifecycles, live Momentum partial/trail behavior, historical context/admission
and marked shared portfolio equity. Current membership/adjusted prices and
prospective qualification remain limitations. Discuss improvements after the
owner reviews these new Yahoo results. Dev-only artifacts; no promotion.

## October 3 — testing finished; discuss improvements before implementing

The owner's latest request is tests first, improvement discussion afterward.
[Results](2026-10-03-current-system-backtest-results.md) and
[test plan / remaining evidence defects](2026-10-03-current-system-backtest-plan.md)
supersede a claim of complete multi-module profitability testing. All 19 archived
jobs finished, including preserved unavailable/failed attempts; 11 delivered
runs bind current source after the EDGE handle-only cleanup. No strategy tuning.
28 focused tests passed; immutable evidence/source checks, repeat outcomes,
compile/diff and atlas verification passed. Source/research commit `4929bea`;
immediate consistency, deterministic atlas and clean-worktree checks passed.
See [completion receipt](2026-10-03-current-system-test-completion.md).

The quarter is not fully covered. F&O full-policy/exit replay is unavailable;
recorded cash is distinct. Penny has actual historical activity, but complete
minute coverage is 189/6,500 stock-days. Its partial shared-cash sensitivity
locks four unresolved entries and cash-rejects seven candidates. Momentum has
16 later-day fallback closes, so its negative diagnostic cannot estimate live
intraday profitability. Swing lacks index warm-up; EDGE/Range remain evaluators.

Discuss evidence-led priorities with the owner before changing entries/exits:
historical coverage and context; Penny unresolved exits and CNC gate overlap;
EDGE/Range/Swing lifecycle contracts; exact Momentum partial/trail/EOD behavior;
verified executable F&O capture and winner concentration. Normalize mixed UTC/
IST ledger clocks and retain date-only CNC conservatism before broader portfolio
claims; independently normalized actual streams agree on this study's metrics.
No full-system qualification is available. P1/P2/P4 delivered source slices do
not remove P3 historical fidelity or operational acceptance requirements.

Production `044c016` is currently stopped and was only read/copied into Dev.
No restart, Production edit, orders, push or promotion occurred. Test artifacts
and correction are Dev-local; original large snapshots remain locally retained.

## October 3 — P1/P2/P4 delivered; P3 partial evidence boundary remains (Dev only)

P2 now recursively binds local transitive source dependencies in the policy
manifest and exclusively publishes completed snapshot/report artifacts without
an exists/write race. Focused CLI/Lab verification: 26 passed, one existing
httpx deprecation warning. Dev-only; no source data, runtime configuration,
broker, Production, push or deployment action occurred.

The owner approved P1 nominal book allocations: Swing ₹1,000, Penny ₹2,000,
Momentum ₹3,000 and EDGE ₹3,000. Unused allocation may transfer, so the ledger
must protect the account-wide own-cash limit and record book attribution; it
must not turn the four nominal allocations into isolated, stranded pools.

The owner delegated the outstanding contingency decision: P1 uses full bounded
entry exposure + calculated charges + a 1% executable-notional reserve. This
is recorded with P1–P4 contracts, acceptance and rollback in
[the completion slice](2026-10-03-p1-p4-completion-slice.md). P2 source commit
`28876be` is Dev-only; its focused CLI/Lab verification passed (26 passed,
one existing httpx deprecation warning). No source data, runtime configuration,
broker, Production, push or deployment action occurred.

P1 source admission is now shared across Python and Node through the durable
`account_cash_reservations` protocol. Its immediate source acceptance covers
concurrent snapshot overcommitment, visible broker pending-order
de-duplication, ambiguity/partial retention, zero-fill release and exit
exemption. The owner-approved book allocation is recorded as attribution and
the account-wide own-cash invariant supports allowed transfers. Paper
observation and owner-controlled promotion remain required.

P3 now includes a joint Penny MIS/CNC cash reconciler and a declared
`PORTFOLIO_PARTIAL` adapter. It improves shared-cash/fill/exit accounting but
cannot become FULL_PORTFOLIO until the runtime has archived point-in-time
universe, regime, event, broker and scheduler evidence; Momentum, Swing, EDGE
and Range have the same evidence boundary. P4 has an append-only prospective
registry and rejects qualification of this partial scope. Do not bypass that
block or relabel prior/historical date declarations as untouched holdouts.
P1/P3/P4 source commit `919e042` is Dev-local. No push, deployment or
Production runtime action occurred. The native Node SQLite ABI limitation is
recorded in the slice; run its real ledger protocol suite inside the matching
gateway container before paper observation/promotion.

## October 3 — authoritative post-implementation review (Dev only)

[Review, correction slice and follow-up acceptance plan](2026-10-03-post-implementation-independent-review.md)
supersedes the earlier blanket B0-B6 completion claims. The small correction
slice covers order-bound F0 reconciliation, unresolved occupancy, malformed
order-book evidence and truthful report/holdout semantics. No migration/config
change or Production/push/deployment action is authorized by this review.

Remaining implementation order: **P1 F1-B account-wide atomic own-cash admission**
and catastrophe acceptance; **P2 B0/B1 complete manifests and point-in-time
evidence**; **P3 B2/B3/B4 historical lifecycle/portfolio parity**; **P4 B6
prospective holdout and session-block uncertainty**. The linked slice defines
files/contracts, adversarial acceptance and rollout/rollback for each.
B5 remains excluded in the recorded current scope. CNC real-data collection
and Dev release operational acceptance remain pending. Production resumed after
the owner's power cut and reports the older declared engine `044c016`; this
review did not restart it. Final affected regression: 294 passed, two existing
deprecations; atlas/compile/diff checks passed.
Correction source commit `284bb4a` is Dev-local; immediate documentation/plan
consistency and atlas reproducibility passed. The authorized review is complete;
implement P1-P4 only in their defined follow-up slices.
Older receipts below describe delivery at their commit, not current completion
of the full original plan.

## October 3 — B3 evaluator slice delivered: shipped Swing/EDGE daily decision parity (Dev only)

**Problem.** The registered `swing_regime_daily` runner is explicitly a
single-ticker proxy (it substitutes the tested ticker for NIFTY and supplies
neutral market context). `penny_edge_backtest.py` has older hard-coded
thresholds, database and fill assumptions. Neither result may be relabelled as
a replay of the deployed daily decision path.

**Delivered.** Distinct research-only adapters call the shipped Swing evaluator
and EDGE scanner. They freeze current defaults, retain the old proxy adapter's
label, and fail unavailable when index/history evidence is absent. This is an
**EVALUATOR** replay: it reports decisions/candidates and rejects, not a live
portfolio, fill, broker admission or historical breadth/universe reconstruction.

**Files/contracts.** `python-engine/backtest_lab.py` registry/adapter contract;
new pure daily replay helper and unit/differential tests; `backtest_catalogue.py`
family declaration; this plan, the system guide and checklist. Inputs are a
frozen `ohlcv_cache` snapshot with explicit stock and index symbols; all source
reads remain read-only.

**Acceptance completed.** Fixtures call the same shipped functions and prove:
no bar dated D informs a Swing D decision; configured EDGE rank/strength values
reach the exact scanner through a temporary frozen cache; and the catalogue
states evaluator-only scope. Binding found and fixed the RSI-history delta
off-by-one which could abort live Swing scans. No strategy thresholds, capital,
broker, runtime scheduling or Production file changed. Focused verification:
149 passed, one existing httpx deprecation warning.

**Rollout/rollback/remaining work.** Offline Dev tests only; archive manifests
through the existing CLI. Rollback removes only the new research adapters and
does not alter archived runs. Next: B6 held-out reporting, then owner review of
the separately listed live cross-book allocation
decisions. GitHub push/promotion and Production read-only checks remain pending.

## October 3 — B4 evaluator slice delivered: Momentum and Range shipped-policy replays (Dev only)

**Problem.** The existing Momentum 15-minute adapter correctly reuses the
evaluator but models a shadow full-quantity target and has no evidence of the
manual EXEC/admission path. Range Reversion is a pure entry profile reached
through the proactive dispatcher and has no Backtest Lab adapter at all. A
daily Swing result must not be relabelled as Range performance.

**Delivered.** The Momentum replay retains its evaluator scope but defaults to
the shipped `MOM_BASE`; `MOM_RECENCY_5` is explicit research only. The Range
evaluator invokes `range_reversion_entry` on completed point-in-time bars,
records every verdict/reason and reports no P&L. Where
historical manual approval, archived advisory context, broker admission,
reservation or exit evidence is missing, declare it unavailable rather than
construct a counterfactual portfolio. If a pure exact Momentum admission/exit
kernel is already shared by runtime, bind it with parity tests; otherwise
document the boundary and do not claim lifecycle completion.

**Files/contracts.** `range_reversion.py`, its dispatcher call site,
`momentum_replay.py`, Backtest Lab/catalogue, existing B1 data contracts and
focused tests. Frozen snapshots are read-only; no live/order modules may be
called. Update guide/checklist/atlas on source changes.

**Acceptance completed.** Range decisions use only completed, prior-known bars and are
catalogued separately from Swing. Momentum retains its actual evaluator/exit
assumptions and rejects unverifiable interval/context input. Tests prove
decision parity/clock behavior and no adapter can place orders. No settings,
capital policy, Telegram action, broker call, Production edit or deployment.
Focused verification: 70 passed, one existing httpx deprecation warning.

**Rollout/rollback/remaining work.** Dev-only offline tests and archived
manifests. Rollback removes research code only. Next B6 adds holdout/report
requirements. B5 stays excluded by the owner; the unresolved cross-book live
allocation decisions remain owner decisions.

## October 3 — B6 reporting slice delivered: standard reports and date comparison guard (Dev only)

**Problem.** `backtest_cli report` currently only echoes a run's summary;
`compare` checks snapshot/window equality but does not protect an untouched
holdout boundary or explain whether a metric has an adequate equity clock.
This can encourage false comparability and selection leakage.

**Delivered.** A deterministic report formatter over archived Backtest Lab
reports retains policy/code/settings/data manifests,
separate unavailable/evaluator results from cash-return results, show the
metrics actually evidenced (gross/net/costs/exposure/turnover/distributions/
MFE-MAE/holding/drawdown only when present), and label every unavailable field.
adds an archived holdout date declaration with no overlap; comparisons require
identical snapshot, scope and holdout
declaration. Bootstrap uncertainty is allowed only for actual closed-trade
samples and must be deterministically seeded; it is never a profitability or
deployment verdict.

**Files/contracts.** `backtest_cli.py`, a pure reporting helper, CLI tests and
docs/catalogue as needed. Reports remain read-only JSON; secrets stay excluded.
No strategy adapter, broker, cache source, live setting or Production file is
changed.

**Acceptance completed for this slice.** Snapshot/window/scope/date-declaration
compatibility and non-overlap are enforced; missing/invalid equity clocks yield
`null` risk-adjusted fields. Tests cover overlap, incompatible comparison,
deterministic IID uncertainty and unavailable metrics. They do not establish
prospective policy freezing or reject repeated selection/prior holdout use.
New declarations explicitly say `DECLARED_UNVERIFIED`.

**Rollout/rollback/remaining work.** Dev-only generated reports; rollback
removes report helpers without deleting archived reports. The original B0-B6
plan remains incomplete as listed in the authoritative review above.
B5 remains excluded; Production recovery/read-only checks, GitHub push
and promotion remain separate authorized steps.

## October 3 — B0/B2 complete: exact classic Penny CNC Connors paper lifecycle (Dev only)

[B2 CNC slice](2026-10-03-b2-penny-cnc-connors-lifecycle.md).
- **Entry.** The replay reproduces the 09:30 scan with today's in-progress
  candle, rebuilt from minute bars, and calls the real
  `evaluate_connors_entry` with real sizing, caps and executor checks.
- **Exits.** It reproduces the 15:45 `update_daily_positions` tracker
  (stop, T1 50% to breakeven, T2, 15 days), proved equal to the real
  tracker and scanner by parity tests (14 tests).
- **Lab and CLI.** `penny_cnc_connors_lifecycle_1d` and `--strategy cnc`.

Runtime findings, not changed:
- `evaluate_connors_exit` has no caller.
- Live CNC rows have no exit management besides a broker SL-M.
- The 09:30 volume gate compares about 15 minutes of volume with a daily
  median.
- Partial day candles are cached until replaced.
- The entry-day stop uses the pre-entry low.

**Real-data run pending:** Production is stopped.

The CNC paper lifecycle slice is delivered under declared assumptions. The
original full-system plan is incomplete; see the authoritative review above.
B5 is excluded in the current recorded scope; promotion is separate.

## October 3 — F1-A owner rule "no extra margin" enforced at both broker boundaries (Dev only)

[F1-A slice](2026-10-03-f1a-own-cash-no-leverage-guard.md).

**Owner's definition:** invest only one's own money. No leverage, and
losses are bounded by the cash put in.

**What is now enforced (gateway Momentum/Swing EXEC, and Python
Penny/EDGE/F&O live).** Every BUY entry must satisfy:

> full order value ≤ broker `available.cash` − open long cost − pending buys − today's realised loss

- Missing evidence or short positions fail closed. Exits are never checked.
- Before this change, the gateway accepted leveraged MIS buys by comparing
  only the broker's roughly-20% MIS margin.

**Tests.** 58 gateway executor tests and 16 Python F1-A tests. The full
Python suite gave 4733 passed, plus 4 pre-existing baseline failures.

**Owner decisions on book-level over-allocation are listed in the slice.**
F1 is still open beyond this: broker statement authenticity, any short or
multi-leg live path, and catastrophe drills.

## October 3 — F0-R5 implemented in Dev; F0 R1–R5 source work complete

[R5 slice and verification](2026-10-03-fno-f0-r5-occupancy-and-clocks.md).
- **Occupancy at the claim.** The existing single-leg limits (concurrency,
  trades/day, open-premium cap, no-pyramid) and "one DR structure at a time"
  are enforced inside the claim transaction, counting in-flight claims.
- **Clocks after the claim.** Live callers re-check the cutoff and quote/
  chain freshness after the claim. A failure releases the entry auditably
  without dispatch.
- **Proof.** The review's DR race went from 2 open structures to 1.
- **Tests.** 12 new; 865 regression passed, plus the known unrelated
  mark-to-market failure.
- **Harness note.** A pre-existing pytest-asyncio/`asyncio.run` socket
  warning appears under `-W error`.

Remaining after F0:
1. Promote R1–R5 through GitHub.
2. Run the R3 Production SQL check once the stack is back up.
3. Observe paper claims and recoveries.
4. F1 (owner cash-only semantics plus broker margin preflight).
5. B2 CNC Connors adapter, then B0 and B3–B6.

Commit `6d41192` (Dev-local). Dev only, not pushed or deployed.

## October 3 — F0-R4 implemented in Dev (broker payload binding)

[R4 slice and verification](2026-10-03-fno-f0-r4-broker-payload-binding.md).
- **Shared check.** `fno_exit_evidence.derive_exit_facts` is now the single
  interpretation of an exit packet. The live verifier and the shared-risk
  reader both use it; the reader never calls the broker.
- **Binding.** Every open partial's receipt must match its retained packet:
  account, order, symbol, tag, status, quantities and weighted price. It
  must also match the position's immutable entry premium, and recompute its
  charges from the cost snapshot frozen at write time.
- **Fail closed.** Empty or forged payloads, consistent wrong prices, wrong
  costs and missing provenance all deny entry.
- **Proof.** All 15 corruption tests fail on the pre-R4 reader and pass on
  R4.
- **Tests.** 18 new; 781 regression passed, plus the known unrelated
  mark-to-market failure.

Commit `0bc8fa4` (Dev-local). Next: **R5**. Dev only, not pushed or deployed.

## October 3 — F0-R3 implemented in Dev (canonical cash, clock, completed trades)

[R3 slice and verification](2026-10-03-fno-f0-r3-cash-clock-completion.md).
- **One reader.** The shared view and policy read one validated cash
  ledger. `TRADE_PARTIAL` and `TRADE_CLOSED` are each counted once.
- **Fail closed.** Future, naive, non-finite, duplicate-exact and
  unclassified cash all deny entry; the observation clock defaults to the
  wall clock. Settled positions without their exact cash also deny entry.
- **Brakes.** Buckets are bounded by the policy day, and the six-loss pause
  counts completed trades.
- **Manual cash.** A positive manual deposit is never capacity.
- **Legacy rows** (generation 0, or no origin) are reported, not rejected.
- **Probe.** The pre-R3 code allowed the partial-loss and future-masking
  cases and falsely paused on six partial exits; R3 fixes all three.
- **Tests.** 20 new; 727 regression passed, plus the known unrelated
  mark-to-market failure.

Production's stack was found **stopped** at 12:22 IST on October 3; this
task did not touch it. Before promoting R3, run the slice's read-only SQL
check on Production.

Commit `5a3b978` (Dev-local). Next: **R4**, then R5. Dev only, not pushed or deployed.

## October 3 — F0-R2 implemented in Dev (one dispatch owner)

[R2 slice and verification](2026-10-03-fno-f0-r2-dispatch-ownership.md).
- **Claims.** A reservation is now only a receipt.
  `claim_shared_fno_entry_dispatch` re-reads the entry policy and grants
  exactly one `DISPATCHING` owner per reservation. Positions require the
  claim, and a halted retry is denied and released before dispatch.
- **Executor.** It re-reads the final order state after a cancel and returns
  typed outcomes with evidence. Only no-dispatch, explicit 4xx rejection and
  verified zero-fill outcomes release capital. Partial, unknown and
  unrecorded fills keep the full reservation (`UNRESOLVED`) until
  `reconcile_shared_fno_entry_dispatch` is given verified evidence.
- **Broker client.** `place_order` reports `dispatch_certainty`.
- **Tests.** 37 new; 666 F&O/broker/settlement passed, plus the known
  unrelated mark-to-market failure; 118 Penny order-path passed.

Commit `54c500e` (Dev-local). Next: **R3**, then R4 and R5. Dev only, not pushed or deployed.

**Operator note.** After any live F&O entry, check for `UNRESOLVED` or
orphaned `DISPATCHING` rows in `fno_entry_dispatches`
(`SharedFnoRiskView.unresolved_entry_dispatch_count`). They hold capital by
design until reconciled.

## October 3 — F0-R1 implemented in Dev (fee-inclusive exposure)

[R1 slice and verification](2026-10-03-fno-f0-r1-fee-inclusive-exposure.md).
- Single-leg rows freeze `risk_fee_reserve_rupees` from the actual fill and
  quantity; DR uses its frozen `entry_cost_rs`.
- The shared view counts loss plus fee for every OPEN/UNRESOLVED row. A
  partial keeps the full fee; a close hands over to exact ledger cash.
- Unbound fee economics, or a single-leg loss below its premium at risk,
  fail closed. Immutability triggers protect the evidence.
- The review's reproduction now holds capacity at ₹1, where it previously
  leaked ₹51.58.
- Tests: 11 new warnings-fatal; 530 F&O/settlement passed, plus 1
  pre-existing unrelated mark-to-market failure.

Commit `d4fd298` (Dev-local). Next: **R2** (single dispatch owner; halt-safe retry; ambiguous entries keep
capital), then R3–R5. Dev only, not pushed or deployed.

## October 3 — B1/B2 implemented in Dev (current state; read first)

[B1/B2 slice, results and verification](2026-10-03-b1-b2-data-contracts-and-penny-lifecycle.md). The owner directed this
task to treat the F&O half of the October 3 plan as done and to implement
B1/B2. For the record, the [independent F0 review](2026-10-03-fno-f0-independent-review.md)
still lists R1–R5; this slice changed no F&O code.

- **B1 `research_data_contracts.py`.**
  - One interval label per run; other labels are reported and never merged;
    `legacy_unknown` is never usable.
  - IST bar-start clock; an invalid row invalidates its ticker-day.
  - Zero-volume bars are marks, not fills.
  - Coverage statuses: COMPLETE, PARTIAL, INVALID, UNAVAILABLE.
  - The audited calendar has an explicit validity range.
  - Daily bars are point-in-time; suspected corporate actions and
    off-calendar dates are reported, never repaired.
  - Manifests carry hashes; loaders are read-only.
- **B2 `penny_lifecycle_replay.py`.** Replays the exact classic Penny MIS
  lifecycle (scope `LIFECYCLE`):
  - the live completed-bar clock;
  - real `PennyRiskEngine` sizing, the circuit filter, one position per
    ticker and at most 3 MIS positions;
  - executor drift and stop-breach checks;
  - the paper LTP stop or a broker stop, the 14:30 smart-EOD / 30-minute
    time stop, and the 15:00 force close, with no target exit.

  It passed a minute-by-minute parity test against the real
  `PennyScanner._evaluate_ticker_breakout`. It is registered in the Lab as
  `penny_breakout_mis_lifecycle_1m` and available through
  `scripts/run_penny_research.py --strategy lifecycle`.
- **Tests.**
  - B1 + B2 + CLI: 57 passed, warnings-fatal.
  - Broad Penny/Lab/research/calendar selection: 809 passed and 1 skipped;
    its warnings are the known Starlette/HTTPX deprecations.
- **Predeclared runs on Production data (read-only).**
  - Primary (`complete_only`): 3 trades, net +₹31.52; excluding the best
    winner, −₹5.91.
  - Sensitivity (`allow_gaps`): 5 trades, net +₹81.12.

  This shows rare entries and dependence on winners running to the 14:30
  rule. It establishes no profitability, holdout or funding authority.
- **Findings left for the owner.**
  - The classic Penny daily kill switch is never fed by runtime
    settlements, so it is inert.
  - Minute capture stops at about 14:29 after 2026-09-03, which leaves later
    sessions without exit evidence.
  - The bankroll is a fixed setting.
- **Next.**
  - CNC Connors exact adapter, then B3–B6.
  - Point-in-time universe and regime before any `FULL_PORTFOLIO` claim.
  - The F0 R1–R5 items and F1 remain open.

Dev only: implementation commit `9a18445`, local, not pushed or deployed; Production is unchanged at `044c016`.

## October 3 — independent F0 review: acceptance reopened

Read [the independent F0 review](2026-10-03-fno-f0-independent-review.md)
before acting on the earlier completion receipts. Reviewed Dev `2b106f7`;
Production remains `044c016` and lacks the shared-risk module. Existing F0
paper gates and atomic writes are implemented; source acceptance is open.

- R1: preserve fee-inclusive exposure through consumed/open/unresolved/partial
  states, with exact cash conservation across both books.
- R2: one durable dispatch owner, current-policy retry checks and evidence-backed
  handling of ambiguous entry/cancel/partial outcomes; no timeout release.
- R3: canonical partial/terminal cash, aware observation bounds and completed
  trade identity for the existing consecutive-loss brake.
- R4: re-derive retained broker payload facts and bind immutable entry/cost
  economics, beyond checking a digest and consistent scalar arithmetic.
- R5: enforce existing occupancy/premium/daily/no-pyramid limits atomically,
  then refresh real deadlines/freshness after the new admission DB waits.

Two bounded corrections are implemented here: shared read helpers do not
create missing databases, and verified zero-fill recovery retains all exposure
without false unavailability. Three new regressions pass warnings-fatal; final
verification is 114 passed with one existing Starlette warning and normal
exit; compilation/atlas/whitespace checks passed. Commit identity is in the
review. Implementation commit `a3f082f` is Dev-local, with immediate
post-commit source/atlas/docs/plan consistency verified. No schema/configuration
change, push or Production action. B1/B2 remains the next requested phase;
do not carry the superseded F0 source-complete claim into that work.

## October 3 — successor and shipped-module backtesting (current priority)

Start with [the successor inheritance](2026-10-03-successor-inheritance.md) and
[F&O safety / B0–B6 backtest plan](2026-10-03-backtesting-and-fno-safety-plan.md).
**Historical implemented slice — F0-D verified partial-exit residual exposure (October 3, Dev only).**
Problem: the existing, operator-authorised `FNO_LIVE` recovery can record a
broker-verified partial exit and proportionally lower `fno_positions.max_loss_rupees`,
but the shared F&O view currently trusts that scalar without tying it to the
recovery receipt and exact ledger cash. Contract: for every still-open
single-leg position with recovery evidence, validate the ordered filled/residual
quantities, settlement generations, retained `ledger_id`/source/origin cash,
and the pro-rata residual catastrophe loss against immutable initial quantity
and loss. Any missing, stale, duplicate or inconsistent partial evidence makes
new shared-risk admission unavailable; it never fabricates a release. Closed
history is not retroactively repaired, and no partial DR execution mechanism is
invented. Acceptance: a verified partial release exposes only its residual
worst-case cash; tampered/missing recovery or ledger evidence fails closed;
concurrent/restart resolution produces one cash row and one residual state;
unresolved/reserved exposure remains blocked. No signal, sizing, live-entry,
broker call, DR legging or exit authority change. Rollout: Dev tests and
additive read validation only, then local commit/review and paper observation;
rollback reverts the validation, preserving cash/recovery evidence.

Implementation result: residual FNO exposure is accepted only after the
shared view verifies ordered recovery quantities/generations, the unique
source/origin/generation ledger event and pro-rata remaining structural loss.
This covers actual operator-reconciled partial fills without inventing a paper
or DR partial fill path. A scalar/cash/receipt mismatch fails closed. Focused
shared-risk tests: 10 warnings-fatal; shared-risk plus recovery selection: 32
passed with the existing deprecated-ASGI route test deselected; broader F&O
risk/DR/orchestrator coverage: 80 passed normally. Source commit `7b77341`;
Dev only, not pushed or deployed.

**Completed implementation slice — F0-E receipt-backed partial cash integrity
(October 3, Dev only).** Problem: F0-D binds a residual to the identity of a
partial-exit ledger event but does not re-derive that event's P&L from the
retained fill receipt, and its declared entry quantity/loss baselines are not
write-protected. An altered fill price, cash value or baseline could therefore
make an invalid residual appear internally consistent. Contract: the shared
view must verify the canonical broker-evidence digest, filled receipt price and
cost-derived cash against the exact ledger row; `initial_qty`, `initial_lots`
and `initial_max_loss_rupees` become migration-safe immutable baselines once
populated. Any discrepancy denies new entry without changing existing
management, exits, broker calls, signal selection, sizing or thresholds.
Acceptance: real verified partial recovery still exposes its pro-rata residual
and exact cash; altered evidence, fill price, cash, generation or baseline
fails closed; legacy-null baselines can be populated once, while a populated
baseline cannot be rewritten; concurrent/restart recovery continues to yield
one receipt/cash transition. Rollout: additive Dev schema trigger and read
validation, local tests/commit, then GitHub promotion and paper observation.
Rollback: revert only the view validation and trigger migration, retaining all
settlement/recovery evidence. Implementation result: recovery rows now persist
the entry/fill/gross/cost/P&L values calculated in their atomic resolution
transaction, and immutable triggers protect recovery receipts plus populated
quantity/loss baselines. The shared view verifies the receipt hash, arithmetic,
ledger identity/cash, ordered generation and pro-rata residual before it grants
capacity. Existing partial rows lacking the new economic evidence fail closed;
they are never silently backfilled. Focused shared-risk/recovery tests: 32
passed warnings-fatal (two documented non-F0 test exclusions). Broader F&O
admission/lifecycle/DR/orchestrator selection: 150 passed normally; its
warnings-fatal form has one pre-existing socket-lifecycle warning in an
orchestrator timing test after 149 assertions. F0's Dev source contract is
complete pending post-promotion paper admission/recovery observation. F1
remains the separately authorised broker cash/margin preflight before any live
funding. Source commit `a9fef57`; Dev only, not pushed or deployed.

**Completed implementation slice — F0-C shared paper entry-policy receipt (October 3, Dev only).**
Problem: F0-B atomically reserves paper F&O catastrophe cash across the
single-leg and defined-risk books, but the legacy directional kill switches and
drawdown gate do not count defined-risk/partial ledger cash and DR admission
does not consult them. Contracts: add a typed, source-scoped, fail-closed
shared-entry-policy receipt in `fno_shared_risk.py`; derive day/week/month
losses from exact `TRADE_CLOSED` ledger rows (all F&O origins) using explicit
IST event dates, and derive drawdown from the same shared realised equity view.
Both new paper entry paths must consult that same receipt; existing position
management and exits must remain callable during a halt. Do not change signal,
quote, sizing, structural-limit, broker, live-spread, or settlement authority.
Acceptance checks: one DR or partial ledger loss halts either prospective book;
source isolation, malformed/naive clocks and missing required evidence reject
new entries; no halt is introduced for a profitable/within-limit fixture; the
drawdown threshold remains the existing 25% allocation policy; and a halted
tick still manages single-leg/DR exits. Rollout: additive code/tests and paper
receipt only in Dev, then a local commit and GitHub promotion/review before
paper observation; no Production configuration/data/process changes. Rollback:
revert only admission-policy wiring while preserving reservation/ledger
evidence; an emergency entry disable never removes exit authority. Remaining
F0 work after this slice: exact partial-settlement release/restart/race
reconciliation and F1 broker cash/margin preflight. Implementation result:
both paper admissions now read the typed receipt, and reservation re-checks it
inside `BEGIN IMMEDIATE`; exact DR/partial `TRADE_CLOSED` cash is common to
both books, while malformed/naive evidence denies new entries. Existing values
remain 6%/12%/20%, six losses and 25% drawdown—no new restriction was tuned in.
Focused `test_fno_shared_risk.py` plus `test_fno_risk_switches.py` passed 24
warnings-fatal; F&O shared-risk/risk-switch/DR/orchestrator selection passed
79 normally. The corresponding warnings-fatal wider run hit one documented
Windows socket-lifecycle warning after 47 assertions. Implementation commit
`bc666fe`; Dev only, not pushed or deployed.

**F0-A foundation is now in Dev:** `fno_shared_risk.py` provides a fail-closed,
source-scoped view of exact settlement cash plus single-leg/defined-risk
OPEN/UNRESOLVED losses and durable reservations. Its transactionally inserted
reservations cannot expire automatically and one-way resolution needs a receipt.
F0-B now binds both paper entries' fee-inclusive worst-case reservations to
their position insert atomically, preserving feasible fixture admissions while
preventing cross-book double spending. Next, make shared loss/drawdown decisions
apply to both books, then add partial-settlement/restart/race characterization. F1 verifies cash-only broker
margin/legging safety; no live spread authority is implied. Recent positive F&O
results do not prove improvement was caused at September 17 (that is also a
cash-key sample boundary). F0-B source commit: `0ba2d29` (Dev; pushed, not deployed).

Completed: existing Penny minute baseline via new inert Dev CLI; two unavailable
samples retained, valid two-stock August 11–20 diagnostic has 5,774 evaluations
and no entries (profitability unavailable). Small research-only SQLite handle
closure fixes Windows temp cleanup. CLI 4 and replay 11 warnings-fatal; combined
82 passed with one existing dependency warning. Full all-module CLI, provider
history, regime/lifecycle/capital parity are **planned**, not code-complete.
B1 data contracts/B2 classic Penny lifecycle follow F0. R6 operational acceptance
and independently authorized partner qualification/canary remain open.

## October 2 — current F&O profitability request

Read [the assessment and concrete replay/data plan](2026-10-02-fno-profitability-assessment.md).
The Dev-only `scripts/assess_fno_profitability.py` ran against Production
SQLite read-only. Recent linked paper outcomes are +₹10,755.67 single-leg (9)
and +₹3,187.60 spreads (7), but all retained July–October position rows report
-₹18,367.22 / -₹3,721.71 and older cash is not exactly reconciled. This is
operational history, **not a current-policy backtest or funding approval**.
Quote archive directories cover only September 10–October 1; obtain licensed
historical executable quotes/contract masters before implementing a full-policy
chronological replay. Existing constant-IV synthetic backtest is insufficient.
The report specifies source/settings freeze, shared policy parity, missing-data
handling, shared-capital portfolio, cost/fill stress and independent holdout.
No Production edits/restarts, provider calls or live-order authority changes.

## October 2 — release candidate; operational acceptance next (R6)

All review source items R1–R5 are in Dev and pushed. Promote through the GitHub
PR to Production, then perform post-deployment checks (read-only first):

1. Containers healthy; the engine runs startup migrations (additive columns only).
2. Collection runs show `momentum_paper_paths.write` after a paper admission, plus `provider_timing`. Research `runtime_capped` should fall after the screener bulk lane.
3. The scheduler daily summary shows the `elapsed_distribution` for market hours.
4. The gateway backlog `report` is reviewed by the operator; `apply` is run only with separate approval.
5. AI unavailable: alerts arrive with an AI-unavailable banner and paper trading continues; check that no classifier calls happen.
6. Then R6: three representative sessions, five reconciled paths, fresh S6/S7 freezes before future data, and partner qualification plus a delivery canary (separately authorised).

## October 2 review priorities — R1–R3 done; R4–R6 remain

R1 `af6f424`, R2 `dcc2f35`, R3 `1550886` in Dev. Next in priority order:
- R4: S3 CSV archive quota/free-space handling and durable market-hours elapsed distributions.
- R5: S7/S8 source-bound entry/thesis evidence, equity-constrained allocation and complete decision-quality analytics.
- R6: operational acceptance.

Deployment notes:
- Deploy the engine diagnostics allow-list before setting `OPTIONAL_AI_REPORT_DIAGNOSTICS=true` on the agent.
- Running the backlog `apply` against Production needs separate operator approval after reviewing its `report` output.
- Freeze fresh S6 manifests before future data.

## October 2 continuation review — authoritative current status

Start with [the independent S7–S10 review](2026-10-02-s7-s10-independent-review.md).
Its implementation contracts/status supersede historical completion and next-
priority statements below. **Not all remaining work is operational**: S6 spread
is an unbound prototype, and S8 is an initial composer, not complete learning.

Small Dev corrections: S10 original deadline forwarding, dispatch-time budget
and request-local zero retries; S8 ordered cash including earlier admissions
and honest drawdown/coverage; S7 settings/fees freeze; reproduced test-fixture
current-loop dependency removed. Agent 368 warnings-fatal; focused research 28
warnings-fatal; expanded engine 1016 passed with six recorded warnings; Node
health two; Compose eight, rendered 500 MiB. No Production/authority change.
The expanded process hung after its pass summary and was stopped by verified
Dev PID; its clean teardown is not established. Focused runs exited normally.

Next source queue, with files/tests/rollout/rollback in the review:

1. **R1 / S6:** typed DR source/leg/economics/cash and actual freeze binding;
   both single-leg raw provider clocks/tokens and position-economics/cash binding.
   Fix reproduced stale-future, modified-manifest and NaN-cost acceptance
   before research interpretation. Freeze anew, never rewrite old manifests.
2. **R2 / S9:** read-only proposed-action reconciliation report and separately
   reviewed idempotent expiry/resolution migration; preserve rows, verify races,
   no fabricated fills or historical trade-card resend.
3. **R3 / S10:** bounded expiry/source/stage counters, once-only still-valid
   original-alert annotation updates and strict transport/shutdown acceptance.
   Daemon-thread join is not forced socket cancellation.
4. **R4 / S3:** bounded/off-path CSV quota/free-space behavior and durable
   elapsed distributions/market-hours summaries before raw-tail eviction.
5. **R5 / S7–S8:** immutable completed-bar/thesis/eligibility adapters,
   separate realized-equity/correlation capacity research, full unique-opportunity
   learning analytics and genuinely versioned human-reviewed proposals.

After GitHub promotion: S1 keyed cash/schema verification; S2 recovery and three
market sessions; S3 peak-volume/prior-boot logs; S4 five reconciled paths;
S5 frozen future protocol, initial 20-session target with adequate closes/
coverage, authorized qualification and separate delivery canary. S6/S7 need
future paired HOLDOUT review before a paper-policy pilot. Paper remains
autonomous, real-money momentum needs owner EXEC, Jev stays deferred. No fixed
calendar-day promise for tips. This review does not push, deploy or send messages.

## October 2 independent S1–S6 review — active correction slice

See [the independent review](2026-10-02-s1-s6-independent-review.md) for
small correction contracts, verification and larger remaining implementation.
Earlier source-complete receipts do not close S3 crash-fault acceptance, S4
fanout/source-packet binding, S5 qualification/canary or the missing S6
defined-risk experiment and archive/economics binding. No Production mutation,
authority expansion or profitable-strategy claim follows from this review.

S7a (Dev): capital-skipped admissions now get candidate economics and a
passive path, and `momentum_allocation_research.py` replays first-arrival
against equal and risk-proportional allocation on one frozen common book.
1114 selected tests passed. After promotion: freeze a manifest before the
next session and evaluate only holdout batches. S7b is completed below;
the next source priority is the S6 defined-risk experiment.

S7b (Dev): frozen completed-bar continuation and bounded-pullback/no-chase
research is now implemented with new-thesis/state re-entry validation and a
bounded read-only view of existing rejected shadow receipts. Focused
warnings-fatal timing/shadow checks: 18 passed. It has no runtime caller.
Before learning from it, freeze the manifest before a new session and use only
signals after that freeze as HOLDOUT; no result authorizes a change to entry
timing. Next meaningful source work is S6's defined-risk experiment.

S8 initial Dev slice: `daily_decision_quality.py` composes isolated daily
book/policy facts from existing read-only audits and shadow receipts, retaining
partial versus terminal cash and rejected evidence. It is explicitly human
review only. Focused warnings-fatal tests: 2 passed. Future source-complete
sessions and reviewed versioned proposals remain required.

S6 defined-risk prototype exists, with its own max-loss R and entry/exit terms.
Independent review found its packet contents are not bound to economics,
manifest verification is incomplete and NaN costs pass. R1 above is required
source development before using its HOLDOUT labels or paired results.

S9 initial Dev slice: gateway health now labels Telegram bot presence as a
diagnostic rather than a transport-confirmed connection, surfaces any durable
dead-letter backlog, and releases its Python probe timer on every response
path. Penny health separates the legacy completed scan clock from a bounded
attempt/outcome state; operator status uses IST ledger-day attribution and
lists each paper book without folding it into live cash. Focused checks: 2
Node, 14 operator-status and 5 Penny-health tests passed. Remaining S9 work is
operationally sensitive: define a reviewed read-only report and supported
expiry/reconciliation migration for old pending requests, callbacks, unsynced
orders and historical dead letters; then collect fresh slow-provider and
no-trade evidence after GitHub promotion. Never use ad-hoc Production SQL.

S10 first Dev slice: stale, undated and timezone-unverifiable classified
sources are excluded from the optional-AI review context rather than poisoning
the annotation deadline. The source renderer emits an explicit
`NEWS_UNAVAILABLE` exclusion summary; deterministic facts may still receive an
advisory review under `proceed` policy. Fresh sources retain their true
validity. Focused agent/async-queue checks: 55 warnings-fatal passed. Next:
make provider transport/retry consume the task's remaining deadline and
surface completed annotations back to the original operator alert.

S4 runtime wiring (Dev): subscribed paper tickers ride the research
collector's existing first quote request into byte-bound envelopes via one
background writer. The deadline-close policy and per-entry adapter exclusion
correct two blockers. 1091 selected tests passed. No Production environment
change is required. Next: after promotion, verify `momentum_paper_paths`
telemetry and five reconciled lifecycles.

Review response (Dev): S6 partial fees and archive pairing (`ea8695d`), S3
crash-recoverable rotation (`c054bf3`) and the S4 typed byte-bound envelope
(`bfd343d`) are corrected; 1024 selected tests passed. Remaining: S4 fanout
wiring, S3 archive quota/elapsed distributions, S5 qualification/canary, S6
DR experiment and F&O position-economics binding.

Small corrections are implemented in Dev with expanded 948-test regression
and isolated warnings-fatal checks; see the receipt for commands and known
runtime-warning limits. Next development: S4 typed source binding and bounded
fanout capture, S3 rotation-journal recovery, then S6 strict archive/economic
binding and versioned partial fees/DR experiment. Existing qualification still
requires frozen future evidence and authorized canary. Do not relabel missing
source work as a deployed-session-only requirement or edit old freeze manifests.

## October 2 S5 partner research readiness — in progress (Dev)

S5a (partner action clock, commit `f45ce43`) is complete in Dev: persistence
and protection prechecks use the live action clock, so a late-received chain
is no longer misclassified as a future quote. S5b is complete in Dev: the
owner-approved bulk Kite lane admits normal research/F&O/penny/partner requests
ahead of the momentum screener's per-ticker fetches with bounded fairness, and
research observes exact active legs with the future reference before the
optional ladder. Expect the screener to take roughly 10–20% longer; verify it
on deployed sessions (commit `18c7f2a`). S5c is complete in Dev: the read-only
`research_cli partner-delivery-blockers` report explains each candidate's
blockers. S5 source work is complete; the frozen protocol, 20-session holdout,
qualification package and canary need fresh post-promotion sessions. S5c commit:
`89a7595`.

## October 2 S6 exit research — S6a complete; S6b in progress (Dev)

S6b step 1 (done): the live single-leg F&O exit ladder is now the pure
`fno_exit_rules.evaluate_single_leg_exit`, shared by the orchestrator and
research; behaviour proven identical (characterization + 20,000-case
differential; 397 suite tests; commit `02047d4`). Step 2 (done):
`fno_exit_experiment.py` freezes `fno_partial_at_target_v1` or
`fno_confirmed_time_extension_v1` and replays the shared ladder on paired
archive paths. Next operational step: export real single-leg positions as
entries, build packets from the research archive, freeze a candidate before
the next session and evaluate only HOLDOUT positions after R1's binding
correction. The defined-risk spread prototype also requires R1 before review.
S5a–S6a commits are pushed (`19a5471`); the PR toward Production must be
opened on GitHub (no `gh` CLI in this environment).


`momentum_exit_experiment.py` freezes one candidate exit policy before
evaluation and reports paired, cost-stressed, holdout-labelled results against
the live evaluator. No runtime caller; no live or paper exit changed. Next S6
work: once S4 paths are deployed and collecting, freeze
`thesis_confirmed_extension_v1` (and/or `target_hold_trail_v1`) before the
next session, then evaluate only HOLDOUT entries. F&O single-leg and
defined-risk exit experiments need their own path sources and R definitions.
A positive small sample authorizes nothing; promotion is versioned paper-only
management after review. Frozen protocol, 20-session holdout,
qualification package and delivery canary reuse existing tooling and need
fresh post-promotion sessions. See the consolidated plan's S5 slice for the
Production evidence. Production remains untouched.

## October 2 S4 equity-path evidence — Dev complete, operational acceptance open

S4 now provides bounded, additive paper evidence only. Every new opened
admission records immutable v1 entry economics, the explicit fixed configured
paper-pool capital snapshot, and canonical accepted-signal packet bytes with a
SHA-256 receipt. The audit recomputes the digest from stored bytes. Existing
`zero_shares` is retained, with a reason that distinguishes exhausted capital,
risk budget and invalid input. A passive exact-admission-key subscription keeps
original quantity through scale-outs. `record_momentum_paper_path_observations`
accepts caller-supplied provider packet bytes plus provider/receipt clocks only;
it has no network capability. The read-only path adapter validates packet bytes,
exact ticker/key, deadline, clock order and configured gaps before it emits a
study packet. Focused S4 evidence tests: 73 passed; compilation passed.

Dev-only source must be pushed/reviewed through GitHub; Production remains
untouched. Before any deployment/learning conclusion, configure bounded caps,
verify the implemented existing-request passive fanout (without a new provider
request), and collect five fresh reconciled lifecycles. Missing/forged/gapped
paths remain insufficient evidence. No test or deployment proves profitability,
strategy quality, partner qualification or live authority. Next priority is S5
or the separately scoped S10 work, not a silent sizing or exit-policy change.

## October 2 S3 evidence-retention — Dev complete, operational acceptance open

S2 source completion is committed in Dev and must be promoted only through
GitHub; Production remains untouched. Start S3 with an inventory of existing
engine/Compose log retention, CSV evidence rotation, scheduler summaries and
archive/restart behavior. Maintain a plan slice before edits: files/contracts,
peak-session retention calculation, tests, rollout/rollback and no-delete
archive rule. Do not change Production or delete retained evidence. S3 needs
rendered Compose verification, bounded writer/disk-failure behavior and
rotation/restart coverage before any deployment request. The optional AI path
must remain non-blocking when its API is unavailable.

S3 implementation slice (October 2) covered
`docker-compose.yml`, `scripts/verify_compose_logging.py` and its focused
tests. The Python engine currently renders `json-file` `20m x 10` (200 MiB),
below the planned `20m x 25` (500 MiB) retention floor. Raise only that engine
contract, render and validate it without printing environment values, and test
rejection of smaller/malformed policies. Rollback is a GitHub reversion of the
Compose/verifier change; never delete old container logs or research archives.
Effective recreation/free-space verification is an operator deployment step.

Completion: the rendered Python-engine contract is now 500 MiB; session CSV
rotation preserves header/rows and SHA-256 manifest evidence; daily scheduler
rollups retain final outcomes/stage statistics before raw-tail pruning. Verify
deployed free space, preserve prior-boot logs and measure complete-session
volume before claiming operational retention. Do not delete archives during
rollback. Next implementation priority is S4; optional AI remains non-blocking
if its API is unavailable.

## October 2 independent S1/S2 review — completed source correction

Review found small S2 gaps: action time was not refreshed after held-option/DR
reads or at final dispatch, quote-age parsing discarded time-zone offsets, and
the scheduler omitted management observations from its completion log. Correct
these in `fno_orchestrator.py` and `scheduler_setup.py`, with cutoff, hard-flat,
quote-age and replay-clock regressions. Preserve frozen signal evaluation time,
all authority gates and non-cancellable mutations. Verify the affected suite,
compile, regenerate the atlas and review the diff. Dev only; promotion/rollback
through GitHub, no Production edit/restart or migration. The original S2 scope
also includes provider queue priority/fairness, exact-leg management reads and
DB-wait timing; existing exit-before-entry ordering is not shared-queue priority.
These source corrections are now complete; stale-IN_FLIGHT recovery review and
three deployed-session observations remain operational acceptance, not proof of
profitability, partner qualification or deployment.

## October 1 consolidated smart-trader plan — active, planning only

Start with [the consolidated implementation plan](2026-10-01-smart-trader-consolidated-plan.md).
It incorporates September 28–October 1 Production evidence and corrects audit
book/time/count errors. First reproduce/fix defined-risk contract lot identity
and truthful atomic settlement, then bound management reads and action clocks.
Preserve complete equity/research paths, compare entry/exit/allocation policies
on frozen future evidence, and complete the existing partner qualification
workflow. This is a smart-trader roadmap, not a mandate to add entry filters.
Jev is deferred. No implementation, Production change or delivery follows from
this planning update; all development remains in Dev with GitHub promotion.
The September 26 admission/economics tools are deployed in PR #99 and four
fresh momentum closes match cash; older "not deployed" receipts below remain
historical. Full paired paths/held-out review are still required.
S10 now covers frequent AI_REVIEW_EXPIRED: stale/undated classified news can
expire the whole review before submission. Correct sanitized context/expiry,
propagate remaining deadlines and expose valid completed annotations without
changing paper autonomy or owner EXEC. See the plan's reproduced evidence and
regression/rollout contracts; this fix is planned, not implemented.

## October 1 S1 defined-risk contract/settlement correction — Dev complete, pending review

The first implementation slice from the consolidated plan is complete in Dev
only (GitHub review/push pending; not deployed at this receipt). New
defined-risk admissions bind every selected leg to its exact NFO identity and
derive quantity economics from the selected contract lot rather than the
configured fallback. The lifecycle refuses missing/inconsistent/replaced
contracts, leaves legacy rows explicitly unverified, preserves an unpriced
hard-flat as `UNRESOLVED` with no fabricated ledger cash, and blocks another
DR opening while unresolved exposure exists. New priced closes use the named
`ENTRY_MID_EXIT_BID_ASK_V1` policy: mid valuation and executable cash are
separate; the terminal row and uniquely generated ledger event are atomic and
idempotent. `fno_audit_report.py` exposes settled/unresolved/legacy evidence
and model-versus-cash totals without recalculating legacy cash.

Verification: 24 focused warnings-fatal DR/audit tests pass; the surrounding
suite passes 84 with one intentionally deselected timing-sensitive recovery
test and one existing Starlette lifespan deprecation. That recovery test passes
alone but fails only in the grouped run and is outside this slice. Additive database columns only; no config,
broker, entry logic, schedule, owner EXEC, partner authority or Production
change. Next: regenerate/review atlas and documentation, commit the scoped Dev
slice, then use GitHub promotion and inspect real schema/settlement receipts.
Source commit `9e26e1b` is local on `codex/production-correction-hedge-p0`;
it is not pushed or deployed.

## October 2 S2 management-read containment — initial Dev slice

The first S2 sub-slice bounds only cancellable management provider reads:
five seconds for futures/open-exit quotes and ten seconds for an existing DR
snapshot. Tick telemetry now exposes per-read completion, deadline or failure
state plus elapsed/cap seconds. A deadline cancels and joins its read, then
uses existing degraded/unpriced handling; it never wraps broker execution,
cash settlement, admission or a database write. Focused checks pass 34. The
warnings-fatal variant encounters an existing unclosed-socket ResourceWarning
in an unrelated stage-duration test, so it is not a clean warnings-fatal
receipt. Source commit `5ae54a8` is Dev-local, unpushed and not deployed;
complete the remaining S2 clock/priority instrumentation before treating the
slice done.

## October 2 S2 management clocks and timing — partial Dev scope, review corrected

S2 now records provider limiter wait, transport, parsing, attempt/retry data
where the real Kite client provides it; non-production adapters explicitly say
the fine timing is unavailable. It retains exact-leg oldest quote age and
refreshes the real action clock after reads and before entry admission, without
altering supplied replay clocks or completed-bar causality. Exits continue to
precede optional DR entry work, and no provider-rate/concurrency increase was
made. Focused coverage passes 59. Pending work is GitHub promotion and three
complete deployed-session receipts. This historical completion claim is
superseded by the independent review: exact-leg DR reads, queue priority/fairness
and DB-wait/timeout-stage attribution still require development. Source commit
`d2319e2` is local, unpushed and not deployed.

Correction slice verification and remaining acceptance are recorded in
[the independent S1/S2 review](2026-10-02-s1-s2-independent-review.md). Small
clock/age/logging corrections are in Dev; no migration, rate/cadence change,
authority expansion, Production edit or restart. Continue with bounded exact-leg
management and shared-request priority before declaring the full S2 complete.

## September 28 Jev decision-layer proposal — design only

The revised [Jev decision-layer draft](superpowers/specs/2026-09-27-jev-decision-layer-design.md)
proposes one disabled-by-default, shadow-only news-category experiment after
a frozen labelled evaluation contract. It does not authorize classifier
replacement, trade grading, signal filtering, M2/M3 promotion, live orders, or
partner advice. The Word/PDF copies remain the earlier draft until the Markdown
design is approved and regenerated. No Jev implementation or deployment has
been performed.

## September 26 P1 economic binding — corrected in Dev

Follow [the economic-binding correction plan](2026-09-26-economic-binding-correction-plan.md).
Replay quantity, time, price and all recorded exit inputs must match immutable
original admission evidence, not mutable remaining shares. Legacy entries are
unavailable. Next is GitHub-based reviewed deployment, fresh keyed admissions
with snapshots and preserved LTP paths, then a predeclared reconciled sample
review. Independently verify archive provenance; a formatted source hash alone
does not authenticate quotes. Do not expand strategy code or interpret held-out
results until this evidence exists. Partner qualification and an authorized
delivery canary remain separate; no automatic tips/live promotion follows.

## September 25 owner vision — autonomous paper, approved real money

The owner's [adaptive trader roadmap](2026-09-25-adaptive-trader-vision-plan.md)
supersedes any proposed default-veto response to a news-classifier timeout.
Paper momentum remains autonomous under deterministic sizing/exits; optional
AI is an annotation, not trade authority. Every **new real-money momentum
entry** still requires explicit owner EXEC approval and the existing hard
broker/session/risk gates. The strategy objective is proactive discovery,
thesis-based management, upside capture and evidence-led capital allocation,
not merely more entry filters. Start with a paper-only paired exit study and
no automatic live promotion. Partner general ideas remain manual intraday
advice with their own qualification and delivery gates.

## September 25 Production audit response and partner activation

Start with the [September 25 corrected audit response and ordered plan](2026-09-25-production-audit-response-plan.md).
Production merge `f52f4d5c` contains the previous Dev source. Read-only checks
correct the audit's claimed missing paper-admission migration and distinguish
post-close container replacement from unproved log rotation. The saved general
intraday profile and per-index collection attempts exist; general strategy
qualification is still absent, while the 0/7 staging-days gate belongs to a
separate personalized-hedge phase. First preserve release-spanning logs and
verify deployed safety/coverage; then produce predeclared, costed, held-out
general NIFTY/SENSEX research for human review. No advice, order or gate
relaxation follows automatically from this plan or three paper-ledger days.

## September 26 completed Dev slice — momentum-paper decision baseline

The [phase 2 plan](2026-09-26-adaptive-decision-baseline-plan.md) is now
implemented. Future momentum-paper opens persist their exact admission key in
the additive position column, partial/final paper cash retains it as
`origin_ref`, and the new read-only audit refuses ticker/date matching.
Legacy/unlinked evidence remains unavailable. No runtime strategy, authority,
broker, scheduler, AI or partner behavior changed. New audit/lifecycle tests:
9 warnings-fatal; affected momentum surface: 194 passed with one existing
Starlette lifespan deprecation warning.

Source commit `94871f2` is pushed on `codex/production-correction-hedge-p0`;
it is not deployed.

Next: promote through reviewed GitHub flow, then collect new keyed paper
lifecycle records and source-bound LTP packets. Run both audit tools on those
records before beginning the predeclared strategy basket; historical unlinked
rows are not a reason to backfill or infer performance.

## September 26 completed Dev slice — source-bound evidence review

The [Phase 3 evidence-binding slice](2026-09-26-adaptive-evidence-binding-plan.md)
is implemented. It joins a Phase-1 exit study to a Phase-2 paper lifecycle
only through a supplied exact admission key; ticker/time similarity is never a
fallback. It remains read-only and reports missing/duplicate/mismatched keys,
incomplete paths and unreconciled cash explicitly. Phase 1/3 focused checks:
20 passed warnings-fatal; the affected paper/replay surface: 214 passed with
one existing Starlette lifespan warning. No entry, exit, sizing, scheduler,
broker, EXEC, partner or delivery behavior changed.

Source commit `beb7e78` is pushed on `codex/production-correction-hedge-p0`;
it is not deployed.

Next: promote the reviewed evidence instrumentation, preserve fresh keyed
admissions and source-bound LTP paths, then run the Phase 3 review on a
predeclared bounded sample. Any missing path or non-matching lifecycle remains
unavailable. Only after independent future-held-out data exists should the
already-implemented frozen strategy-basket comparison be run; do not invent
or tune a result from the current sample.

## September 25 completed Dev slice — paper-only adaptive exit study

`momentum_exit_study.py` now provides the scoped no-runtime paired study in
[2026-09-25-adaptive-exit-study-plan.md](2026-09-25-adaptive-exit-study-plan.md).
It requires source-bound timezone-aware LTP input, rejects incomplete path
evidence, compares the current evaluator to one target-hold/0.5R-trail policy,
accounts for costs/partials, and cannot claim qualification.  It has no live
monitor, entry, EXEC, broker, database, scheduler or partner-delivery caller.
Focused validation: 13 new tests warnings-fatal; affected momentum surface:
109 passed with one existing Starlette lifespan deprecation warning.

Next only after retained quote packets exist: run the report over a predeclared
bounded set of real momentum-paper entries.  If any path is unavailable, retain
`INSUFFICIENT_EVIDENCE` and improve evidence collection rather than changing an
exit parameter.  Compare future held-out sessions before any human-reviewed
proposal; no study result grants live-exit authority.  Preserve unrelated
unstaged fixtures and independent audit documents.

## September 24 implementation update — P2 F&O audit evidence

The P2 F&O audit/financial-interpretation slice is complete in Dev.
`fno_signals` now records the exact passed-gate prefix and active switch
evidence in additive JSON fields; the stable first-reject reason and all
decision behavior are unchanged.  The new read-only
`fno_audit_report.py --db <existing-db> --date YYYY-MM-DD` groups repeated
leg evaluations into one bar/underlying/direction decision unit, so the 24 Sep
two-bar/six-row pattern cannot be described as six trade opportunities.  It
reports per-source FNO_PAPER/FNO_LIVE partial cash events and closed outcomes
separately, labels isolated costs unavailable, and deliberately issues no
expectancy or qualification verdict.  Legacy rows remain readable but state
that switch/gate evidence was not retained.

Focused report/gate/log/orchestrator/hourly tests passed 84; the broader
F&O/performance/division surface passed 376 (two existing framework warnings).
The retained Production audit has no local SQLite copy, so the historical six
rows cannot be retroactively enriched.  After reviewed promotion, run the
read-only report against a retained database and compare the two decision units
and switch evidence to the log before interpreting a block.  No remaining
source change is currently unblocked in this three-day plan; its remaining
items are production promotion and real-session evidence gates.

## September 24 implementation update — P2 classifier latency containment

The classifier latency correction is complete in Dev. Source analysis showed
that the one-second informational classifier reused the analyst client with
one SDK retry. It now uses a separate MiniMax/OpenAI client configured with
`CLASSIFIER_MAX_RETRIES=0`; all direct/fallback classifier calls select that
client. The analyst review client retains its original retry budget. A
wall-clock regression confirms a timeout failure is one bounded call and
returns `UNKNOWN`; no background or detached retry is introduced. The complete
agent test suite passed 361 tests. AI remains informational/non-authoritative.

Next is the separately scoped P2 F&O signal-row and financial interpretation
review: first inspect retained Production evidence read-only and verify the
actual switch/gate path before changing any code or financial presentation.

## September 24 implementation update — P1 momentum-paper admission evidence

The TATATECH acceptance slice is complete in Dev. The paper book now persists
a bounded, idempotent outcome only after its real decision/transaction:
`opened`, `already_held`, `zero_shares`, `disabled`,
`upstream_deduplicated`, or `transaction_failure`. Repeated accepted signals
are recorded at `main.py`'s alert-dedup boundary, so the paper opener is not
credited with a decision it never received. The table contains an opaque
digest/ticker/outcome/timestamp, not raw strategy payloads. A position insert
rollback cannot be marked opened; reopening a closed position preserves a new
immutable attempt. The paper-only/no-order boundary is unchanged.

Next development is P2 classifier latency diagnosis, only after reproducing
the owned retry/transport tail. Do not change AI authority, paper-entry
authority or schedule cadence from this evidence work.

## September 24 implementation update — P1 F&O tick-tail containment

The F&O tick-tail slice is complete in Dev. Read-only retained Production logs
showed 27 ticks at/over cadence (12 on 23 Sep and 15 on 24 Sep); all had zero
DR opens/exits and the repeatable tail was defined-risk entry preparation. Dev
therefore bounds only the cancellable market-data reads that prepare a new
paper DR entry to a shared 20 seconds. Active DR management, hard-flat
handling, single-leg exits and database admissions are deliberately outside
that deadline. A stalled-read regression proves cancellation is joined, the
skip is explicit and no order is created; F&O/DR/scheduler focused tests pass.

Next operationally, promote only through reviewed GitHub flow and collect
comparable session telemetry using `defined_risk_snapshot`,
`defined_risk_management`, `defined_risk_entry_inputs`,
`defined_risk_entry_admission` and `dr_entry_skip_reason`. Do not change the
90-second cadence to conceal a slow active-exit path. The next Dev slice in
the ordered plan is TATATECH accepted-signal admission evidence.

## September 24 implementation update — P1 research collection deadline

The first P1 collector slice is complete in Dev. Each provider quote operation
is cancellation-bounded by the remaining 48-second tick budget, while the
60-second schedule stays unchanged. Normal, capped and error results plus
their durable collection-run journal now carry cap/elapsed/partial telemetry
and truthful per-index coverage states; the first underlying rotates by UTC
scheduler slot so repeated caps do not starve one index. A stalled NIFTY provider is cancelled
and joined before return; its known active leg and skipped SENSEX coverage are
retained as gaps. Focused tests passed 54 and the complete research surface
passed 62. No Production change or strategy qualification occurred.

Next operationally, observe three logged-in sessions before making cadence or
evidence-quality claims. See [the active plan](2026-09-24-three-day-production-audit-plan.md).

## September 24 implementation update — P0 decision-forensics retention

P0 is complete as a measured no-value-change Dev slice. Read-only Production
inspection confirmed `python-engine` already has a 200 MiB `json-file` cap and
retained 35.897 hours/18.13 MiB at an observed 0.50 MiB/hour; no rotation was
present to justify a speculative Compose increase. Dev now pins that rendered
contract through `scripts/verify_compose_logging.py` and eight focused tests.
It prints no Compose environment values and fails closed on an absent,
malformed or non-`json-file` engine configuration. No Production container was
recreated. The remaining P0 operational acceptance is three logged-in
opening-to-close retrievals after reviewed promotion; see the
[P0 receipt](2026-09-24-three-day-production-audit-plan.md).

## September 24 three-day Production audit reconciliation

The 22–24 September deep audits were cross-checked against Production evidence
and current Dev source. The new [audit reconciliation and ordered plan](2026-09-24-three-day-production-audit-plan.md)
corrects several auditor inferences and identifies a confirmed research
collector cap/telemetry defect. It supersedes the September 24 release-slice
statement that no unblocked product-code issue remained: that statement was
correct for the six release gates, but the later Production audit exposed a
separate collection defect. Do not lengthen research/F&O schedules or change
paper/AI authority solely from the audit's recommendation. Production remains
read-only and no new Dev application change is implemented by this plan.

The user additionally queued three Dev slices in that document. The
full-session `python-engine` Compose-retention, research-collection deadline,
F&O tick-tail containment and TATATECH momentum-paper-admission slices are
complete in Dev. None is authorized for Production by this documentation
update; the next code investigation is the separately scoped P2 classifier
latency reproduction.

## September 24 implementation update — real research package boundary

The next Dev-implementable package boundary after F&O exit recovery is complete:
the bounded operator workflow assembles already replayed, reviewed full-policy
evidence into the existing authorization envelope. It cannot manufacture
evidence or approve/register/deliver advice. The exact contracts, acceptance
checks and rollout boundary are in
[the real-research package slice](2026-09-24-real-research-package-plan.md).
Real completed-bar/active-leg collection, future held-out evidence and an
operator review remain operational prerequisites, not test-fixture substitutes.

## September 24 implementation update — Dev release acceptance

Dev-side release acceptance is now recorded, including the repair for a
post-Jest background holiday-refresh log. The compatible Node 20 gateway
receipt naturally exits zero (461 passed / 4 skipped), scripts pass 226,
agent tests pass 357, and dashboard tests/build pass (46 / build). The full
engine process remains an environment-limited non-receipt because its
aiosqlite-worker teardown did not terminate; do not call it green. The exact
commands, boundary and source contract are in
[the release-acceptance slice](2026-09-24-dev-release-acceptance-plan.md).
This is Dev evidence only: it does not merge, deploy, qualify advice or send
Telegram/broker traffic.

### Remaining-gate classification

There is no further unblocked product-development task in the current release
slice. The clean full-engine process exit is a test-runtime/CI follow-up, not
an application-behaviour change: prior full receipts completed assertions but
retained aiosqlite workers. Diagnose only from a minimal reproducer; do not
weaken warnings, force an exit, or add broad shutdown code speculatively. The
other outstanding gates—GitHub promotion/release identity, session evidence,
real broker reconciliation, held-out research, saved profile/review and an
authorized Telegram canary—are operational or evidence tasks. See the
[acceptance receipt](2026-09-24-dev-release-acceptance-plan.md).

## September 24 implementation update — F&O exit recovery

Item 3 of the September 23 next-agent order is implemented in Dev for same-day
`FNO_LIVE` terminal zero, partial and full exits. The authenticated operator
route verifies the current broker order, executions and net position, retains
the bounded source snapshot, and atomically resolves the intent with a ledger
entry for actual fills. Ambiguous, older, unaccounted concurrent orders and
broker read failures remain blocked. Partial economics and residual risk carry
through the eventual final close. See
[the active recovery slice](2026-09-23-fno-exit-recovery-plan.md) for exact
tests, migration and rollout status. Production HEAD `782bbb7` contains the
earlier handover commit `f0e23b4`; this new recovery source is Dev only until
GitHub promotion. Items 1, 2 and 4–6 still require their own evidence/work.

## Current handover — September 23 remediation completion

Start with [the independent review and next-agent execution order](2026-09-21-independent-remediation-review.md).
This supersedes earlier claims that A1–A6 helper tests alone completed integration.
The corrected Dev implementation and tests are ready for review; actual deployed
identity, inputs and partner qualification must be checked separately.

Remaining priorities: (1) GitHub promotion and stamped-release verification with
backups; (2) real-session readiness/coverage/contention evidence; (3) authenticated
F&O ambiguous/partial/zero-fill recovery workflow before live single-leg activation;
(4) real source activation and held-out per-index research; (5) explicit profile,
reviewed qualification and authorized Telegram canary; (6) broker reconciliation
and Production dashboard scope verification. Do not loosen gates to produce tips.
Never erase an unresolved exit intent to force a retry. No guarantee of profitability.

## September 20 Workflow I.4.D provenance correction (Dev only)

Classification is now bound to the exact feed snapshot shown to the verdict
model. The requested ticker, bounded source URL/name, aware publication clock
and source digest survive in each result; invalid source evidence fails closed
without a model call. HTTP(S)+host validation and a seven-day source-validity
boundary are explicit. Optional-review keys bind the deterministic
classification-context digest when the feature is enabled and preserve the
legacy key when disabled; the queue also rejects context-mismatched cache hits
for direct callers. Typed reviews retain digest/count/structured source
references and actual expiry on available, unavailable and worker-exception
paths. Synchronous late results are discarded as unavailable; cached repeats
can shorten but cannot extend validity. Focused warning-fatal acceptance is
**185 passed**, full isolated agent is **357 passed**, compilation/diff checks
pass, and the atlas remains **203
modules** after regeneration. No schema/config default/authority/trading
behavior changed. Production evidence is still required; I.4.G remains
deferred. See the
[active plan](2026-09-20-i4d-classification-provenance-plan.md).
Implementation commit: **`3495ecb`**; promotion remains GitHub-only.

## September 19 Workflow I usefulness-contract correction (Dev only)

The optional-AI status bridge no longer rejects the real ten-field usefulness
snapshot while accepting only reduced test doubles. Engine validation now
covers all producer fields and their internal counter/rate consistency; the
agent's hourly contract-health check uses the real status shape and actually
runs its leakage/usefulness invariants. The dashboard renders p95 response time
and last completion without converting absent legacy fields to zero. No schema,
flag-default, authority, delivery, risk, capital, strategy, or order behavior
changes. Focused engine is **72 passed** with four known deprecations, full
agent is **340 passed** warning-fatal, and dashboard is **46 passed** plus build.
Whole-engine validation is **4,117 passed/four skipped/46 known deprecations**;
implementation commit `8dd2c41` was consistency-checked and pushed to
`origin/codex/production-correction-hedge-p0`. Real
Production observations and operator-labelled usefulness remain required;
per-ticker I.4.G is still deferred. See the
[active plan](2026-09-19-workflow-i-usefulness-contract-plan.md).
This correction supersedes the historical six-field I.A allow-list wording in
the long-form state table below; the current authoritative contract has ten
fields.

## September 19 Workflow C.C2.SOURCE completion (Dev only)

The remaining causal-pricing defect in the modeled-partial path is corrected:
every modeled leg is bound to its own verified asymmetric quote packet rather
than priced from the earlier decision book. Missing legacy source projections
now return `INSUFFICIENT_EVIDENCE / partial_fill_model_unavailable`, and
held-out admission independently cross-checks source attribution and recomputes
the model. Focused acceptance is **87 passed** with warnings fatal; broader C
coverage is **259 passed**; whole-engine acceptance is **4,070 passed/four
skipped/42 known deprecations**. Genuine retained sessions, adequate predeclared
holdout coverage, human qualification and release/Production observation are
still required. Details are in the
[completed slice](2026-09-19-workflow-c-asymmetric-source-binding-plan.md).
Implementation commit `e2212cb` and verification receipt `1a97932` were pushed
to `origin/codex/production-correction-hedge-p0`. Production is unchanged.

## September 19 Workflow C.C2.HOLDOUT completion (Dev only)

`C.C2.HOLDOUT` closes the modeled-partial review seam. The evaluator now emits
a separately identified `MODELED_PARTIAL_FILL_V1` replay, and held-out/review
outputs split `full_closes` from `modeled_partial_closes`. Adverse mid-plus-2bps
entry slippage is non-positive; a degenerate missing-leg quote fails closed.
Modeled outcomes remain outside `VERIFIED_FULL_POLICY_REPORTS` until honest
cost-stress and archived-public-scope evidence exists. Verification: 90
focused, 134 broader qualification/held-out, 226 Workflow C/research, and
4,069 whole-engine tests passed; four skipped and 42 known deprecations in the
whole run. Details and remaining runtime evidence are in
[the completed slice](2026-09-19-workflow-c-partial-holdout-plan.md).
Production is read-only.

## 1. Mission, scope and non-negotiable user intent

September16 square-off acceptance update: pushed Dev commit `ee0a300` moves live momentum EOD ownership to 15:13 IST with a strict 15:14:30 submission cutoff and one shared monitor/EOD lock. Deadline expiry after protective-stop cancellation re-arms and persists replacement protection when possible and always escalates; no late sell is submitted. Focused momentum/calendar/lifecycle/surface coverage is green (79 passed), the scheduler/calendar regression subset is green (25 passed), agent is green (338 passed), and final Python is3730 passed/four skipped/42 existing deprecation warnings in214.84s. The completed pytest receipt again retained aiosqlite worker processes; the exact processes were stopped. Merge/release observation remains required before Production acceptance. This removes the identified 15:15 CAS collision in Dev source; it does not supply staging CAS evidence, broker execution verification or partner strategy qualification.

September16 current acceptance override: Dev correction `97e62e7` and receipt `93efbe4` are pushed, while Production is merge `967e07a` with source parent `315fa72`. Production containers are healthy, but `trading_ready=false`/order execution UNVERIFIED. The new partner-card path has zero qualifications, research artifacts and ideas; two observed sessions produced no setup. The independent J correction HMAC-binds eligibility, strictly expires/validates calendars, removes operational-coverage SQLite initialization races and makes SUMMARY verification deterministic without changing JSON output. Final validation: Python 3725 passed/four skipped/42 existing deprecation warnings (complete receipt, but lingering aiosqlite workers prevented natural process teardown); runtime-matching native Node 424 passed/four skipped; dashboard 43 passed plus build; agent 338 passed. Until merged/released/observed, historical J/H/DONE labels below are source-history claims, not operational acceptance. A single paper close of+INR2,194.54 is not repeatable/live expectancy.

September14 overriding acceptance status: external F2–F6/H/I/J source is preserved but F/J complete labels below are not independently accepted. [Independent audit](2026-09-14-external-work-independent-audit.md) identifies writer-contract, account/capital and live session defects requiring correction. G/C predeclared protocol correction is Dev-tested in ten-file acceptance:156 passed/no warnings6.84s using winvenv `-q -W error`. Full-run JUnit `sentinel-g-protocol-reviewed-20260914.xml` records3304 cases, zero failures/errors, four skips,173.475s; pytest teardown remains alive at inspection, so clean process exit/warning count is NOT confirmed. Next: reconcile this protocol commit, correct F3/F4/F5 and fail-closed F6, then execution/calendar defects and independent I review. Real heldout inputs, faithful range semantics, operator risk input, F/D evidence and GitHub release/session observation remain open; no full-goal completion or live promotion inferred.

Current September13 verification: F inventory/provenance corrections, cache integrity and immutable approval-budget/validity source pass full Dev engine **2,703 tests/four skips/23 existing deprecations in126.20s**, receipt `sentinel-fg-provenance-baseline-20260913.xml` in user Temp. F historical warning evidence, genuine G/C predeclared comparisons/approval gates, D release/session proof and other matrix residuals remain unfinished. No deployment or qualification inferred.

Improve Sentinel into an active, intelligent, cost-aware trading system for the owner and a timely intraday NIFTY/SENSEX manual-advisory system for the partner. The owner wants substantial profit and proactive discovery with mitigated risk. Treat that as a product objective, not a guarantee or justification to loosen safeguards. The engineering target is positive, repeatable net expectancy demonstrated with appropriate evidence, reliable execution/management, truthful accounting and bounded losses.

Do not spend another sequence of commits solely making evidence machinery safer without getting to operational collection, research comparisons and useful product outcomes. Each work item below must produce an observable result, with an explicit decision about what to do next. Equally, do not skip missing evidence to claim progress toward income.

The final requested handover wraps the current code and documentation; this plan preserves the broader unfinished mission. Read SYSTEM_GUIDE.md, SYSTEM_CODE_ATLAS.md and HANDOVER_CHECKLIST.md before implementation. Then inspect the actual worktree, branch, open PR and Production status. Historical chat and these documents are pointers, not fresh runtime truth.

## 2. User constraints to carry forward

- Owner capital: about INR 8k now; possible staged increases to INR 20–50k, INR 1 lakh, then INR 5 lakh only after confidence. Do not silently change capital or treat added funds as returns.
- Partner: independent manual intraday trader in NIFTY and SENSEX, prioritizing hedging. No overnight recommendation under the current policy.
- General tips do not require their personal strategy or holdings. Personalized protection does require actual exposure; conditional protection needs explicit assumptions.
- The owner accepts some risk and wants frequent proactive scanning. A trade quota is not a substitute for an edge.
- AI may help; deterministic operation must continue without it. No AI risk override or fabricated qualification.
- Changes belong in Dev. Promotion is through GitHub. No direct Production edits, live order tests or unrequested partner messages.
- Existing intraday profile was previously saved. Revalidate it rather than asking again reflexively. Ask only for genuinely missing operational preferences or credentials, through appropriate secure configuration.

## 3. Starting state

Recent work added full-policy replay, independent public lifecycle events, delayed-entry capital/risk checks, archived public inputs, candidate capture, immutable CLI reports, and pre-decision-book support. Detailed changes and limitations are in the system guide and September 12 progress record.

Last inspected Production archive had quote journals and masters but zero captured public-input files. At that inspection the application containers were stopped. Do not assume this remains true or that restarting is authorized by a research task. The new Dev commits had not been deployed by this work.

No qualified NIFTY/SENSEX strategy or reliable date for partner tips has been established. The current report functions intentionally return no qualification/delivery/order authority. General Telegram connectivity can be tested separately with an explicitly authorized TEST message; that does not qualify trading advice.

## 4. First working session: establish a reproducible baseline

1. Read git status, current branch, last commits and remote tracking. Preserve untracked audits, evidence and unrelated edits. Do not squash earlier commits without authorization.
2. Read HANDOVER_CHECKLIST.md and rerun only checks invalidated by current changes/environment.
3. Inspect Production containers, release identity and archive root read-only. Record time, SHA, source paths and limitations. Do not print `.env` or tokens.
4. Locate current profile, qualification records, readiness reasons and per-index data timestamps using authenticated/read-only surfaces. Explain each missing gate in plain language.
5. Write the active plan slice with IDs from this document, success conditions and a bounded acceptance procedure. Begin the highest-priority unblocked slice.

Deliverable: an updated state table separating Dev-tested, release-tested, deployed, input-ready, strategy-qualified and delivery-tested. A single green label is insufficient.

## 5. Workstream A — finish causal acquisition and decision timing

**Priority:** P0 for usable research. **Files:** `fno_signal_scan.py`, `partner_orchestrator.py`, `partner_qualification.py`, `partner_research_capture.py`, `partner_full_policy_replay.py`, `research_cli.py`.

Problem: the original tick clock precedes network acquisition. Newly captured candidate receipts honestly occur later, so feeding them back at the old clock is correctly rejected. Merely setting a replay timestamp later can change bar eligibility/strategy meaning and must not masquerade as the original decision.

Implementation:

1. Define explicit tick-start, public-response receipt, chain-response receipt, evaluation cutoff, candidate construction and dispatch clocks. Use injected clocks in tests.
2. Choose and document the deployed policy: either evaluate on a declared frozen completed-bar cutoff with later availability, or recompute at a genuine post-acquisition decision clock. Do not silently mix both.
3. Carry the chosen clocks and source IDs into the captured bundle and frozen decision manifest. Bind candidate and public captures to the same decision/run/account/index.
4. Ensure crossing a five-minute boundary, entry cutoff or session boundary during a fetch cannot create a backdated idea.
5. Keep final dispatch revalidation independent: source availability does not grant transport authority.

Acceptance: reproduce an actual delayed-fetch case without timestamp fabrication; delayed source past entry deadline yields no advice; identical frozen inputs reproduce identity; a newly eligible bar has an explicit new decision. Quote provider timestamps remain untouched. Test both indices and timezone-aware UTC/IST input.

Expected benefit: collected sessions become replayable and recommendations use genuinely available inputs. Risk: changing clocks can alter signal frequency/identity. Version the policy and invalidate incompatible prior qualifications. Retain old captures and migration notes.

## 6. Workstream B — complete collection coverage, not just valid files

**Priority:** P0. **Files:** archive/capture/quote collector/leg subscription modules, scheduler telemetry, ops readiness routes and dashboard hooks.

1. Persist per-attempt records with expected schedule/cutoff, index, source, requested/received contracts, completion/error and references to immutable artifacts.
2. Record public and candidate capture outcomes independently, including no-setup, missing-chain, disk-full, busy writer and malformed packet cases.
3. Preserve all selected legs through the advice lifecycle and management horizon. Verify shared-token accounting, terminal registrations, restarts and expiry changes.
4. Compute session completeness from expected market-aware intervals and retained attempt records. Distinguish never attempted, attempted unavailable, partial, stale, and complete. A directory containing valid files alone is not sufficient.
5. Track quote and public-event gaps independently. Avoid pretending a stop between unobserved samples has a known fill.
6. Finish conditional-protection input capture and declare whether it can use the same replay schema or needs a separate evaluator.
7. Bound disk work. Current `to_thread` avoids event-loop blocking but awaiting it can still delay the advisory job. Introduce a bounded queue only with saturation/drop evidence, cancellation semantics and restart tests; never spawn unlimited writes.

Acceptance: interrupted/restarted session reports gaps; one index failure does not erase the other; missing selected leg prevents complete replay; archive budget failure remains observable while public updates continue; no operational cash or position mutation occurs. Review retention cleanup so capture files and referenced masters outlive qualification review.

Expected benefit: usable evidence and an honest explanation of why qualification is pending. Dependency: A's clock contract. Failure mode: collecting everything without a storage budget creates contention; measure overhead at representative load before release.

## 7. Workstream C — replay fidelity and review integration

**Priority:** P0 before qualification. **Files:** all `intraday_spread_*`, `partner_full_policy_replay.py`, `partner_qualification_review.py`, CLI and tests.

1. Verify public-source scope includes the intended underlying/futures contract and relevant roll/expiry context, not only a name string.
2. Bind raw/canonical master, candidate chain, public inputs, selected contracts, code/config/profile and cost schedule to immutable evidence IDs.
3. Review delayed execution beyond capital/risk: price spread limits, liquidity, current quantity, economic reward/risk, stale public observations and exact expiry boundaries.
4. Validate manual delay and cancellation behavior at entry and exit, including an invalidation on the fill timestamp, no later book, partial book and missed management deadline.
5. Align management deadline/reminder semantics with the deployed policy; do not force a fill at an unavailable exact-minute quote or retroactively close unresolved exposure.
6. Reject conflicting same-receipt quote packets rather than selecting a convenient first packet. Include failure evidence in the report.
7. Freeze review criteria before held-out sessions; connect full-policy outcomes to review without replacing the full evaluator with `orb_threshold_v1`.
8. Preserve zero-opportunity days, no-fills, unresolved exposure and rejected candidates. Account for overlapping ideas and repeated evaluations so sample size means independent opportunities.

Acceptance: unmocked multi-session archive fixture reaches both a costed close and unresolved outcome; tampered sources fail; cost stress uses identical observations; changed policy/profile cannot inherit qualification; complete CLI reports are reproducible and cannot overwrite earlier economics.

Expected benefit: a defensible decision to deliver a specific strategy. It may demonstrate that the current ORB policy lacks an edge; that is useful evidence and should lead to comparison, not suppressed losses.

## 8. Workstream D — release and genuine operational evidence

**Priority:** P0 after the passive collection slice is reviewed. Do not wait for an entire innovation roadmap before deploying useful, tested passive evidence collection.

1. Run full relevant Python acceptance, scheduler/API contracts, gateway native-SQLite-compatible tests, dashboard tests/build and affected agent tests. Record exact command, runtime and failures.
2. Review migrations, defaults, flags and Docker volumes. Establish consistent backup/rollback procedures without deleting data.
3. Prepare a PR describing behavior, tests and remaining operational prerequisites. User authorization is required for actions outside existing scope, including actual partner messages or live canary orders.
4. Promote via the release runbook: reviewed branch/SHA, stamped builds, recreate application services, resolve nginx upstream and verify live fingerprints. Never claim a merge alone deployed new code.
5. Observe one real market session for collection correctness and latency. This session proves operations, not strategy profitability. Fix deterministic gaps promptly.
6. Continue evidence until the predeclared review has an adequate independent sample. Report opportunity count, uncertainty and unresolved risk—not a countdown in arbitrary days.

Acceptance: receipt confirms correct live SHA; per-index inputs and coverage are observable; no unsolicited messages/orders; source and delivery switches match intended rollout. Roll back code only with schema/archive compatibility checked.

## 9. Workstream E — partner product activation and usefulness

**Priority:** P1, prepared in parallel with evidence collection.

Checklist for meaningful delivery: saved intraday profile, current index inputs, valid candidate, genuine compatible qualification, configured destination/token, transport test, final dispatch/session gates. Diagnose each separately. Never require partner positions for a general market setup.

Improve cards around decisions a manual trader can take: index/exchange, timestamp/validity, setup rationale, entry trigger and bounded price, exact contract legs/expiry/lot, total debit and modeled costs, maximum defined loss, invalidation/target and intraday deadline. Explain uncertainty and liquidity limits without overwhelming the message.

Hedge-first must have an explicit interpretation. Conditional protection states the exposure assumption and coverage; market directional spreads are not automatically personalized hedges. Ask for exposure details only if personalized protection is requested. Do not describe an unconfirmed action as taken/closed.

Prioritize invalidation and urgent management above new ideas; suppress overlapping NIFTY/SENSEX directional exposure as appropriate. Keep destination backoff, ambiguity and claim ownership intact. A two-idea cap, if effective, is a maximum rather than a quality target.

Acceptance: representative message previews are understandable, actionable and internally consistent; TEST delivery is distinguishable from advice; duplicate/recovery tests pass; strategy approval is scoped and revocable; every suppressed idea has an operator-visible reason.

Expected benefit: timely usable information, rather than hedge logs/status spam. Outcome evaluation should measure timeliness, executability and costed thesis performance. Partner feedback is helpful but not broker-confirmed P&L.

## 10. Workstream F — trading losses and accounting truth

**Priority:** P1, independent of partner qualification.

1. Reconstruct the previously reported ORB losses from actual entry/exit records, signal input, spread/leg identity, fees and market regime. Separate strategy failure, execution slippage, stale data and accounting defects.
2. Investigate each reconciliation warning with retained ledger/position records and broker statements when supplied. Produce discrepancy IDs and explanations; never mutate books merely to make the dashboard agree.
3. Audit true cost per trade relative to expected edge for INR 8k capital. Prevent a large configured paper bankroll from implying owner live affordability.
4. Audit funding, expenses, partial closes, rejected/cancelled orders and open mark-to-market independently.
5. Establish capital-increase criteria from externally reconciled net results, drawdown, execution quality and operational stability. Leave the user's loss tolerance as an explicit input if not supplied.

Acceptance: per-strategy/mode/account reports reconcile or show precise unresolved differences; deposits are not profit; no forced trade is used to verify a status flag. Expected benefit: stop allocating to misunderstood losses and make future scaling decisions evidence-based.

## 11. Workstream G — strategy basket and entry/exit intelligence

**Priority:** P1/P2 after data/accounting reliability. These are hypotheses, not proven improvements.

Predeclare a small basket rather than searching hundreds of variants until one looks profitable:

| Research hypothesis | Intended condition | Comparison | Main risk |
|---|---|---|---|
| Trend continuation after bounded pullback | Directional session with liquidity | Existing ORB vs pullback entry | Missed strong moves; hindsight support levels |
| Breakout with completed-bar confirmation | Expansion from compression | First break vs confirmation | Worse entry price offsets fewer false breaks |
| Range mean reversion with strict invalidation | Stable range/no expansion | No-trade baseline and existing range logic | Regime shift produces tail losses |
| Cost-aware abstention | Weak edge relative to spread/fees | Same setup before/after cost threshold | Overfitting threshold to recent trades |
| Exit profile comparison | Existing accepted entries | Fixed stop/target vs bounded time/trailing exit | Selecting best exit after seeing the path |
| Exposure-aware allocation | Multiple simultaneous ideas | Independent allocation vs shared risk cap | Correlation estimate unstable on short samples |

Use `proactive_*`, watchlists and run identities to compare candidates without creating an execution consumer implicitly. Freeze training/holdout and cost assumptions. Report net expectancy with uncertainty, drawdown, frequency, turnover, rejected/no-fill count and capacity. Control for repeated trials and overlapping signals.

Acceptance: one retained comparison report can explain why a strategy is promoted, rejected or still uncertain. Promotion to live requires a separate reviewed bridge and risk budget. Expected benefit is improved selection/management; no fixed profit uplift should be predicted without evidence.

## 12. Workstream H — scheduling, provider efficiency and dashboard

Measure p50/p95/p99/max execution time, queue wait, provider calls, cache hits/misses and database/writer contention during market hours. Prioritize order exits and public advice management, then candidate scans, then research. Cache only with explicit instrument, interval, completed-bar cutoff and freshness semantics.

The wrap-up scheduler-closure tests passed but emitted an unawaited `_run_penny_edge_scan_safe` coroutine warning at scheduler_setup.py:594. Determine whether the mocked scheduling path or a runtime rejection path leaks the coroutine, add a warning-sensitive regression, and correct it before describing scheduler validation as warning-free.

Investigate historical zero intraday-cache hit rates: find actual caller/key/window behavior before adding a cache. Do not mix mutable forming bars with completed historical bars or cross-account/exchange tokens.

Dashboard should show effective source/scope/window and readiness reason beside numbers. Distinguish disabled, unconfigured, no session, no setup, no evidence, stale and error. Wire real Production account/run sources rather than replacing unexplained zeros with synthetic results.

Acceptance: lower measured contention without missed exits or lost evidence; mocked slow-provider tests plus retained live-session measurements; UI fixture covers unavailable and zero distinctly. Be precise: reducing a job average does not prove tail latency is controlled.

## 13. Workstream I — optional AI and news

Use AI for bounded annotation: explain a deterministic setup, classify sourced events, summarize risk context, compare research findings and identify missing evidence. Store model/prompt/version, source references, response time and expiry. The typed result must not change capital limits, qualification or order/delivery authority.

Test disabled mode, timeout, stale response, queue saturation, budget exhaustion and restart. Deterministic paths must still operate. News must have publication/event timestamps and a reliable source; an unsupported model statement is not a market fact.

Expected benefit: better explanations and event-awareness. Main risk: plausible but wrong context arriving too late. Evaluate annotation usefulness separately from trading outcome and do not add synchronous model latency to exits.

## 14. Workstream J — CAS and market-session correctness

Read [the CAS inventory](2026-09-12-production-evidence-and-cas-findings.md) and verify current official NSE/BSE/SEBI sources before implementation. September 12 NSE information described cash CAS eligibility and different session timings from continuous cash and equity derivatives.

Inventory hard-coded clocks in market calendars, gateway market-hours, scheduler jobs, bars, expiry/square-off, UI and replay. Introduce an exchange/security/session-phase model only after verifying effective dates and broker behavior. Preserve earlier strategy deadlines unless explicitly revised and qualified.

Do not assume auction imbalance is available in Kite's current feed. Verify actual feed fields/rights first. If unavailable, label that limitation rather than infer imbalance from LTP. Any auction-based strategy is separate research with auction execution semantics, not an extension of a continuous-market fill model.

Acceptance: ordinary days, eligibility differences, holidays, shortened/special sessions and phase transitions have tests. No accidental extension of partner holding horizon. Expected benefit: correct session behavior; an auction profit edge remains hypothetical.

## 15. Suggested order and dependency graph

Start A and B, then finish C. Release a reviewed passive collection slice through D as soon as its operational acceptance is satisfied. Prepare E's message/setup UX in parallel; activate only after compatible qualification. Run F independently because capital truth and losses matter now. Use G to replace an unpromising baseline with tested alternatives. H supports every operational phase. I is optional, and J begins with session correctness before strategy innovation.

Do not claim A–J complete because files exist. Maintain a requirement matrix with statuses: NOT_STARTED, IMPLEMENTING, TESTED_DEV, RELEASE_VALIDATED, DEPLOYED_OBSERVED, EVIDENCE_PENDING, ACCEPTED or REJECTED. Include the precise evidence reference for each status.

### Current requirement matrix — September 12 A/B slice

| Requirement | Status | Evidence | Remaining transition |
|---|---|---|---|
| A — causal acquisition/decision timing | TESTED_DEV | `docs/2026-09-12-clock-and-coverage-plan.md`; focused Python timing/capture/orchestrator tests | Full release acceptance, promotion and one observed session |
| B — per-attempt collection completeness | TESTED_DEV | Archive-local SQLite attempt journal, readiness API/card and restart/partial/unavailable/timeout tests | Production load/retention measurement and observed schedule coverage |
| H — scheduler coroutine warning | TESTED_DEV | 41 scheduler/isolation tests with RuntimeWarning fatal | Release acceptance and deployed scheduler observation |
| C — replay fidelity/review integration | TESTED_DEV | Real evaluator/archive multi-session fixture uses master-proven v3 public futures/roll captures and reaches costed close/unresolved outcomes; conflicts and unrelated packets are distinguished; exact deadlines/strictly-future expiry and delayed liquidity/cancellation/public-age gates are tested; source-bound stress/drawdown and pre-holdout criteria remain enforced; modeled asymmetric legs are bound to their verified source packets and separately identified | Obtain adequate genuine held-out evidence; verify real collection/retention and exchange-specific settlement assumptions during D/J; actual broker fills are not asserted by the modeled-partial research contract |
| D — release/operational evidence | IMPLEMENTING | Baseline: full Python 2,545 passed/3 skipped, scheduler 41 passed, dashboard 25/build, agent 91; resource plan: gateway 324 passed/4 skipped/natural exit, Python warning-fatal 32 and resource-fatal 181; `docs/2026-09-13-consistent-backup-plan.md`: offline verifier/runbook and 117 warning-fatal backup/deployment/migration/journal tests, native dummy-data CLI/tar roundtrip | Actual authorized quiescence/backup/restore and old/new schema compatibility, reviewed GitHub PR/release and real-session observation; currently application containers stopped, not implicitly restarted |
| E — partner activation/usefulness | EVIDENCE_PENDING | Existing profile/delivery gates remain independent | Genuine compatible qualification and authorized transport validation |
| F — trading losses and accounting truth | TESTED_DEV through F.10A; operational evidence still pending | Existing F1-F6 evidence remains in `docs/2026-09-13-workflow-f-state-of-codebase-audit.md` and the independent correction plan. F.10A adds `broker_internal_reconciliation.py`, three durable discrepancy categories, additive CLI/HTTP output and regressions for account binding, statement selection, fill aggregation, both position books, missing/duplicate/paper references, quantity excess and idempotency; see `docs/2026-09-19-f10a-broker-internal-reference-plan.md`. Unsupported sources also fail closed by contract. It never upgrades a reference match into broker reconciliation or authority. Focused: 118 passed; whole engine: 4,090 passed/four skipped. | Obtain genuine broker statements and perform operator review. Full bidirectional economic reconciliation remains blocked on statement period bounds, account-scoped internal books, universal order IDs and richer immutable fill metadata. Signed loss tolerance/capital decision, D release validation and deployed observation remain separate. |
| G — strategy basket and entry/exit intelligence | TESTED_DEV through G.7; pushed, genuine evidence pending | Existing predeclared protocol, exit composition, immutable caches and signed bridge remain documented in the G audit/promotion plans. G.7 makes `RANGE_REVERSION_V1` causal: first completed post-cutoff decision bar, 14 prior bars, execution strictly later, explicit fail-closed outcomes, verifier-derived stop/mean target, and no fallback to generic confirmation. The comparison protocol removes the obsolete alias/forced-uncertain rule but preserves completeness, economics, drawdown, paired uncertainty, immutable implementation identity and all no-authority fields. Focused 81, broader G 222 warning-fatal, and whole engine 4,095/four skipped pass; commits `fefa5a3`/`bc79325` pushed; see `docs/2026-09-19-g7-range-comparison-causality-plan.md`. | Obtain genuine predeclared held-out sessions and F/D evidence. BridgeDecision signing, shared-book capacity, default-v1 migration, release/deployment and strategy qualification remain separate operator/evidence gates. |
| H — scheduling / provider efficiency / dashboard | DONE (H1 scheduler coroutine warning closed and PROD-ready; H2 priority-tier breakdown closed; H3 intraday-cache caller/key/window diagnostic closed `fead40c`; H4 cache-add for ``get_intraday`` closed `d1d6e15` with three operator-tunable knobs honouring §12 four explicit semantics; H4.B by-token cache closed `bfb42ac` extending H4 to the F&O/partner path; H5 dashboard readiness vocabulary closed `b9cfc44` with bounded state->descriptor mapping and self-validation) | H1 — `python-engine/scheduler_setup.py`: ``run_penny_hourly_report_safe`` wrapper + cron re-registered with ``max_instances=1, coalesce=True, misfire_grace_time=600``; ALL_CLOSURES extended. H2 — `python-engine/scheduler_telemetry.py`: `JOB_TIER_MAP` + `TIER_ORDER` + `_tier_for` + `_aggregate_by_tier` + `by_tier` key in `scheduler_timing_report`; `operational_coverage.py` extended with `scheduler_tier:{tier}` entries. H3 — `python-engine/intraday_cache_diagnostic.py`: read-only diagnostic with `CACHED_CALLER_SITES`/`BY_TOKEN_CALLER_SITES` inventories, `cache_row_counts`/`cache_interval_breakdown`/`cache_freshness_window`/`audit_key_shape` queries, `cache_by_token_row_counts`/`cache_by_token_interval_breakdown` for the new table, `run_diagnostic` + CLI; reuses `reconciliation_cli._write_output_atomic`. H4 — `python-engine/kite_client.py:454-575`: explicit §12 four-semantics enforcement in `get_intraday` HIT path (instrument + interval + completed-bar cutoff + freshness); three new operator-tunable knobs in `python-engine/config.py`: `INTRADAY_CACHE_FRESHNESS_SECONDS=0`, `INTRADAY_CACHE_INCLUDE_FORMING=False`, `INTRADAY_CACHE_MIN_CANDLES=4`. H4.B — `python-engine/kite_client.py`: same four semantics extended to `get_intraday_by_token` via shared `_intraday_cache_gate_evaluate` helper; new `intraday_cache_by_token` table; daily interval exempt from forming-bar filter; `_interval_minutes("day") = 1440` (was a latent PROD crash on partner_orchestrator's daily calls). H5 — `python-engine/coverage_vocabulary.py`: seven §12 descriptors (DISABLED/UNCONFIGURED/NO_SESSION/NO_SETUP/NO_EVIDENCE/STALE/ERROR), `STATE_TO_DESCRIPTOR` mapping for the eight states produced by `operational_coverage_report`, `validate_coverage_report` called at end of report; drift attached to report under `vocabulary_drift`, logged at WARNING. 7 + 22 + 26 + 13 + 13 + 22 = 103 new H-series tests pass. whole-engine 3,026 passed/4 skipped/39 warnings (~+22 vs previous 3,004 after H4.B). No regression to the previously closed baseline failures; no new warnings. | H-series complete. Production acceptance remains separate per plan §15 |
| I — optional AI and news | IMPLEMENTING (I1 model/prompt/version provenance + response time closed `4ea9b54`; I2 news provenance — publication timestamps + source URLs closed `33d780c`; I3 usefulness-instrumentation snapshot + bounded CLI closed `f35d859`; I.A bridge I3 usefulness metrics from agent to engine closed `980636e` + `65d4bfe`; I.B surface I1 provenance in operator alert closed `d1e7d4f` + `9bd5286`; I.C operational_coverage_report includes optional AI closed `89a9804` + `c47941e`; I.F cross-container contract test closed `a226ec3` + `0f7120b`; I.4 deep-research proposal closed `aaa15d6`; **I.4.D source-event classification closed `c80e3fa` + `d60073b` + `bc0a0a6` + `557de73`**; **I.4.E bounded contract-health self-evaluation closed (5 invariants: status_envelope_authority, no_prompt_leakage, usefulness_counters_only, classifier_fail_closed, review_non_authoritative) + `evaluate_contract()` aggregate + read-only CLI `tools/contract_health_check.py` with print-config/check/self-check subcommands**; remaining I.4 opportunity G (per-ticker breakdown) explicitly deferred to separate slices after A/B/C/F prove themselves in PROD) | I1 — `agent/advisory.py`: `Review` gains six provenance fields (model/base_url/prompt_version/started_at/completed_at/response_seconds), all default None for backwards compatibility. `agent/agent.py`: `MINIMAX_PROMPT_VERSION` env var (default "v1"); `_attach_provenance` helper using `dataclasses.replace`; every return site of `analyze_with_minimax` wrapped. I2 — `agent/agent.py`: `NewsItem` frozen dataclass with title/source_url/published_at_raw/published_at_parsed/source_name/age_label; `fetch_news_items` returns structured list; `_parse_rss_pubdate` handles RFC 822 and RFC 1123; `_age_label` produces `fresh`/`N hours ago`/`N days ago`/`stale_aged_Nd`/`stale_or_unknown`/`future_dated`; `fetch_rss_feed` legacy string format preserved; `scrape_sentiment` renders structured `[age] (source) title` + `url:` lines. I3 — `agent/async_reviews.py`: bounded counters (`_response_seconds` buffer, `_verdict_counts`, `_cache_hits`, `_cache_misses`, `_circuit_opens`, `_last_response_seconds`, `_last_completed_at`); `submit` tracks cache hits/misses; `_run` captures response_seconds + verdict counts + circuit-open transitions; new `usefulness_snapshot()` returns 10 bounded JSON-serialisable fields. I.A — `agent/agent.py::publish_optional_ai_status` includes `usefulness_snapshot()` in payload; `python-engine/optional_ai_status.py` extends `clean_queue` allow-list; new `usefulness` envelope with bounded field validator; dashboard `OptionalAiEvidence` renders the new fields. I.B — `agent/advisory.py::Review.banner()` renders model + prompt_version + response_seconds when present; backwards-compatible (provenance absent → banner unchanged). I.C — `python-engine/operational_coverage.py` gains `optional_ai` producer with the standard `{state, reason, observed_at, ...}` contract; H5 vocabulary extended to map optional AI states to descriptors. I.F — `python-engine/tests/test_optional_ai_cross_container_contract.py` + `agent/tests/test_optional_ai_cross_container_contract.py` round-trip the bounded envelope and reject unknown keys. I.4 — `docs/2026-09-13-i4-deep-research.md` proposes 7 bounded AI-enrichment opportunities (A–G). I.4.D — `agent/news_classifier.py` pure/total bounded 8-category classifier; `analyze_with_minimax(pre_classifications=None)` with backward-compatible prompt; `_fetch_news_items_for_ticker`/`_maybe_classify_news` env-flagged helpers; operator CLI `agent/tools/news_classify_cli.py` (--ticker/--input/--dry-run/--json); 76 tests (36 module + 10 helper + 9 integration + 21 CLI + 6 async-queue via `inspect.signature` review). I.4.E — `agent/contract_health.py` pure self-evaluation (5 bounded invariants + `evaluate_contract()` aggregate + `ContractReport` with `schema_version="i4e-v1"`); operator CLI `agent/tools/contract_health_check.py` (print-config/check/self-check, read-only, exit 0/1/2); 53 tests pin the contract; agent suite grew 259 → 312 (+53 net). See [I.4.E done-doc](2026-09-14-i4e-contract-health-done.md) |. `agent/optional_ai_metrics.py` NEW: bounded CLI with `print-config` and `read-snapshot` subcommands, documented `CONFIG_CONTRACT`. 15 + 21 + 15 = 51 new tests pass. **I.A** — NEW `_ALLOWED_USEFULNESS_KEYS` / `_ALLOWED_VERDICT_KEYS` allow-lists in `python-engine/optional_ai_status.py` (6 top-level bounded fields + 4 verdict buckets); new `_clean_usefulness(raw)` validator that rejects unknown keys, bad types, bool-for-int, negative numbers, non-dict envelopes. NEW `record_optional_ai_status` integrates the validator: clean usefulness persisted under `detail.usefulness` when envelope present; absent when not. `OPTIONAL_AI_REPORT_USEFULNESS` opt-in env var. `agent/agent.py::publish_optional_ai_status` includes `usefulness_snapshot()` in payload. NEW `tests/test_optional_ai_usefulness_bridge.py` (21 tests across 4 classes: bounded validator / persistence / route surface / bounded contract — explicitly rejects `pitch`/`rationale`/`prompt`/`api_key` leaks). Whole-engine: python-engine 3026 → 3047 (+21); agent 153 → 174 (+21). **I.B** — `agent/advisory.py::Review.banner()` extended with model/prompt_version/response_seconds (1 decimal); backwards-compat substring tests preserved. NEW `tests/test_review_banner_provenance.py` (300 lines, banner-format contract). Whole-engine: 3047 → 3072 (+25); agent 174 unchanged. **I.C** — `python-engine/operational_coverage.py` extended with `optional_ai` producer sourced from `load_optional_ai_status`; H5 `STATE_TO_DESCRIPTOR` mapping extended with optional-AI states (`READY`, `DISABLED_*`, `OUTAGE_CIRCUIT_OPEN`, `UNAVAILABLE`). NEW `tests/test_coverage_vocabulary_optional_ai.py` (140 lines) + `tests/test_operational_coverage_optional_ai.py` (436 lines). Whole-engine: 3072 → 3097 (+25); agent unchanged. **I.F** — Cross-container contract test pins the producer/consumer invariant: a known-bad envelope (leaked prompt, leaked credentials, wrong types) is rejected at the engine boundary; the producer's `usefulness_snapshot()` is bit-shaped-compatible with the consumer's `_clean_usefulness()`. NEW `tests/test_optional_ai_cross_container_contract.py` (488 lines). Plus 4-line optional_ai_status consistency fix. NEW `tests/test_optional_ai_status_usefulness.py` (132 lines) on the agent side. **I.4** — `docs/2026-09-13-i4-deep-research.md` (the research proposal): 7 enrichment opportunities ranked by value/cost; recommended A+B+C+F as the visibility-focused slice (already implemented above); D (source-event classification, the §13 explicit gap), E (periodic self-evaluation), G (per-ticker breakdown) deferred to separate slices after A/B/C/F prove themselves in PROD. **I.4.D** — NEW `agent/news_classifier.py`: bounded source-event classifier against the fixed 8-category taxonomy (`REGULATORY`, `EARNINGS`, `M_AND_A`, `GUIDANCE`, `MACRO`, `RUMOR`, `TECHNICAL`, `UNKNOWN`). `NewsCategory` enum (string-valued); `ClassificationResult` frozen dataclass (ticker, title_hash, category, confidence [0,1], bounded rationale ≤ 280 chars, prompt_version, classified_at). `CONFIDENCE_THRESHOLD = 0.6` (fail-closed: below threshold → UNKNOWN). `CLASSIFIER_TIMEOUT_SEC = 1.0` (per-item latency budget per the deep-research doc). Pure / total: never raises; on timeout / parse error / disabled / model-exception returns `UNKNOWN` with confidence=0.0 and a human-readable rationale. Fixed taxonomy — a category the model invents (outside the enum) is forced to `UNKNOWN`. `DISABLE_CLASSIFIER` env var forces every classification to UNKNOWN (offline / CI / sandbox). `_extract_json_object` parser tolerates `<think>...</think>` blocks (MiniMax-M3 reasoning), `\`\`\`json\`\`\`` fences, leading prose, malformed input. **`c80e3fa`** ships the module + 36 tests (taxonomy, JSON parser, output normaliser, threshold rule, frozen immutability, title hashing, disabled/no-client paths, end-to-end with mock client, batch API, to_dict JSON-safety, config sanity). **`d60073b`** wires `pre_classifications` into `analyze_with_minimax` as an OPTIONAL keyword parameter; the verdict prompt gains a `CLASSIFIED SENTIMENT DATA` section (rendered ABOVE the existing `MULTI-SOURCE SENTIMENT DATA` section) listing `title_hash + category + confidence + rationale` per headline. When `pre_classifications` is None (the default, every existing caller's path), the prompt renders a placeholder text and is byte-identical to its pre-I.4.D shape. The verdict pipeline's existing path is unchanged. **`bc0a0a6`** adds two env-flagged helpers (`_fetch_news_items_for_ticker`, `_maybe_classify_news`) so the operator can flip `ENABLE_NEWS_CLASSIFIER=1` to wire classification into the call sites — the async-queue extension is explicitly deferred (carrying `pre_classifications` through `_Task` is a separate slice). The helpers never raise; the verdict pipeline's failure modes are unchanged. **`557de73`** lands the operator CLI `python -m agent.tools.news_classify_cli --ticker TICKER | --input PATH [--dry-run] [--json] [--limit N]` — runs without touching the verdict pipeline, exits 0/1/2/3 with structured diagnostics. 21 CLI tests pin the contract. Agent suite grew 213 → 253 (+40 across the 4 commits); zero regressions. | Annotations surface in operator dashboards; usefulness evaluation requires operator-supplied ground truth (deferred per plan §13 explicit constraint). I.A/B/C/F and the I.4 deep-research proposal are CLOSED. **I.4.D source-event classification is CLOSED.** Remaining I-series work (opportunities E and G per the I.4 proposal — periodic self-evaluation, per-ticker breakdown) is explicitly deferred — separate slices only after the visibility-focused work proves itself in PROD. |
| J — CAS and market-session correctness | IMPLEMENTING (J.1 classifier closed `d82258f`/`63a98ab`; J.2.1 eligibility list closed `ba117fb`; J.2.2 broker-behaviour probe closed `f6e07da`; J.2 docs sweep closed `211fc58`; J.3.1 probe-quality + classifier `cas_eligible` kwarg closed `6019279`; J.3 capture-review tool + runbook + receipt-directory scaffold closed `9ab8ad1`; J.4 wire `stamp_session_phase` to real classifier closed `cb309a8`; J.5 holiday reconciliation Python↔Node closed `e0061a4` + `c3d1649`; **J.5 holiday divergence actually fixed (Node fallback updated to 20 dates matching Python, drift detector now reports ALIGNED) closed `00dffbd` via independent correction plan `64e22a9`**; J.6 Node sessionPhase mirror closed `1b007c6` + `d5ae6de`; J.7 CAS-aware execution gating closed `cf43df8` + `c0d5c79`; **J.7 CAS-eligibility resolver hardened (Python `routes_market_session.py` is the single authoritative projection; Node `services/cas-eligibility.js` fetches it; `entrySessionVerdict` blocks before broker/DB calls when resolver unavailable) closed `00dffbd`**; J.8 operator dashboard session-phase card closed `6ced829` + `d00f463`; J.9 CAS-aware signal handling closed `e18a160` + `cea1c26`; J.10 CAS-branch reachability gate closed `ba91dcc` + `414207e`; **J.10.CLOSURE operator-facing SUMMARY.md surface closed `c734e4c` + `b8a490e`**; **holiday calendar validity bound (`NSE_HOLIDAYS_VALID_THROUGH = 2026-12-31`, `isHolidayCalendarUsable()` fails closed after that date) closed `fd450a3`**; operator-supplied staging captures still pending for J.10 to flip from UNREACHABLE to REACHABLE) | J.1: `python-engine/market_calendar.py` central constants + 10-phase classifier + `is_cas_eligible` + 41 tests. J.2.1: `CAS_PHASE1_FNO_UNDERLYINGS` env var (CSV) → `is_cas_eligible`. J.2.2: staging-only `tools/j2_cas_probe.py`. J.3.1: probe bumped to `SCHEMA_VERSION: 2` with inline JSON Schema; new flags `--schema-print` / `--eligibility-list` / `--require-eligible` / `--validate`; strict ISO 8601 parser; explicit `cas_eligible: bool | None = None` kwarg on `classify_session_phase`. J.3: NEW `tools/j2_capture_review.py` (six-point checklist + opt-in OHLC-continuity cross-window check); NEW `docs/2026-09-13-j3-capture-protocol.md`; NEW `docs/j2_captures/README.md`. J.4: `python-engine/proactive_intelligence.py::stamp_session_phase` wired to `classify_session_phase` via lazy import. Signature gains three opt-in keyword-only kwargs (`symbol`, `is_derivative`, `cas_eligible`). 17 new J.4 tests across 5 classes. J.5: `python-engine/market_calendar.py` re-verified canonical 20-date NSE Equity 2026 holiday list against NSE source. NEW `python-engine/holiday_drift.py`: pure drift detector (Node source as text + canonical set; reports `ALIGNED` / `DRIFT`). NEW `python-engine/tools/holiday_drift_check.py`: CI/operator CLI (exit 1 on drift). NEW `python-engine/routes_holidays.py`: GET `/holidays` route returning the canonical list; the response now exposes `valid_through: NSE_HOLIDAYS_VALID_THROUGH` so consumers can see when the static set expires. `main.py` wires the new route (1 import + 1 `include_router`; main_surface_golden.json updated for the +1 endpoint). NEW `python-engine/tests/test_holiday_drift.py`: 18 tests — the pre-correction drift signature (Python=20 / Node=18) is documented as historical; the post-correction state (Python=20 / Node=20 / drift=0 / verdict=ALIGNED) is pinned. `node-gateway/server/utils/market-hours.js` rewritten: live `NSE_HOLIDAYS` Set mutated in-place by an engine fetch at boot (5s timeout); `MARKET_HOURS_HOLIDAYS_JSON` env override; **the pre-correction 18-date `NSE_HOLIDAYS_FALLBACK` is replaced by the exact ISO projection of `market_calendar.NSE_HOLIDAYS_STATIC` (20 dates); `isHolidayCalendarUsable()` fails closed after `NSE_HOLIDAYS_VALID_THROUGH = '2026-12-31'`**; `replaceHolidays` records the source validity date so a successful engine refresh can extend the live set's validity. 6 new Node tests in `tests/unit/market-hours.test.js` (was 19, +4 for stale-calendar fail-closed and `isCashCasEligibilityResolutionWindow` → 23 total). Full python-engine suite: **3245 pass / 4 skip / 0 fail** (vs J.4 baseline 3225 / 4 / 1; +20 net, 1 net regression eliminated — the previously-failing surface test was a documented golden refresh). **J.7**: NEW Python `execution_allowed(observation_at, *, symbol, is_derivative, cas_eligible, allow_pre_market) -> {allowed, phase, reason}` in `python-engine/market_calendar.py`. Bit-perfect mirror in Node: `isExecutionAllowed(opts)` in `node-gateway/server/utils/market-hours.js`. Translation table: `CONTINUOUS_TRADING` / `DERIVATIVES_CAS_ALIGNED` -> allowed; `PRE_MARKET` -> blocked unless `allow_pre_market=true`; `CLOSED` / all `CAS_*` / `UNKNOWN` -> blocked. NEW `node-gateway/server/utils/errors.js::CasPhaseError(phase, reason)` (status 422, code `cas_phase_blocked`). Wired into `services/executor.js` (replaces J.6 observability with a hard CAS-aware guard; preserves `MarketClosedError` for the `CLOSED` phase) and `index.js` telegram callback (shows `verdict.reason` for CAS-blocked phases). NEW `python-engine/tests/test_execution_allowed.py` (19 tests across 5 classes: CLOSED/PRE_MARKET, CONTINUOUS_TRADING, CAS sub-windows, DERIVATIVES_CAS_ALIGNED, purity). NEW `python-engine/tests/fixtures/regenerate_execution_allowed_golden.py` produces 3,525 vectors and dual-writes both fixtures. NEW `node-gateway/server/tests/unit/isExecutionAllowed.test.js` (20 tests including the **golden-vector parity test** that asserts zero mismatches across all 3,525 vectors). All 4 existing mocks of `market-hours.js` extended to expose `isExecutionAllowed`. Window boundary correction: the J.6 docs listed CAS sub-window widths that did not match the live Python constants (15:30 -> 15:40 for CAS_MATCHING vs actual 15:30 -> 15:35); J.7 corrects the docs and tests use the actual constants (CAS_REFERENCE_PRICE_WINDOW 15:15-15:20, CAS_ORDER_ENTRY 15:20-15:25, CAS_LIMIT_ENTRY_ONLY 15:25-15:30, CAS_MATCHING 15:30-15:35, CAS_POST cash 15:35-16:00, DERIVATIVES_CAS_ALIGNED 15:30-15:40). Net: Node full suite **380 pass / 4 skip / 0 fail** (was 360/4/0 at J.6 close; +20 new); python-engine full suite **3267 pass / 4 skip / 1 pre-existing failure** (the J.6-documented `test_coverage_vocabulary.py::test_unmapped_state_appears_in_drift` aiosqlite-threading flake, verified zero J.7 imports). **J.7 hardening (independent correction plan)**: NEW `python-engine/routes_market_session.py` exposes `GET /market-session/cas-eligibility?symbol=...` (authenticated via `X-Internal-Secret`, returns `{symbol, cas_eligible, source, source_version}` where `source_version` is a SHA-256 of the configured CSV — no CSV disclosure). NEW `node-gateway/server/services/cas-eligibility.js`: `resolveCasEligibility(symbol, observationAt)` short-circuits outside `isCashCasEligibilityResolutionWindow` (the 15:15-15:29 IST cash-CAS-affected interval) with `{required: false, resolved: true, casEligible: false}`; inside the window it fetches the Python projection with the configured timeout; failures return `{required: true, resolved: false, casEligible: null, reason: ...}`. NEW `entrySessionVerdict(symbol, observationAt)` chains eligibility with the existing `isExecutionAllowed` verdict: an unresolved eligibility returns `{allowed: false, phase: 'CAS_ELIGIBILITY_UNAVAILABLE', reason: ...}`. `services/executor.js` and `index.js` now call `entrySessionVerdict(signalData.ticker, new Date())` BEFORE any DB UPDATE / EXECUTING transition / answerCallbackQuery; a `CAS_ELIGIBILITY_UNAVAILABLE` failure short-circuits execution; operator sees `show_alert: true`. NEW `tests/test_market_session_route.py` (3 tests: 403 without secret, 200 projects config, 200 returns false for unconfigured). NEW `tests/unit/cas-eligibility.test.js` (3 tests: no-fetch outside window, fetch inside window with X-Internal-Secret, fails closed when resolver unavailable). Updated `tests/unit/executor.test.js` (2 new tests: blocks before broker calls, passes actual ticker), `tests/integration/telegram-callbacks.test.js` (1 new test: blocks callback), `tests/integration/approved-snapshot.test.js` (mock added so existing tests reach executor). `utils/errors.js` now exports `CasPhaseError`. **J.10.CLOSURE**: NEW `update_summary(report, summary_path, *, captures_dir=None)` in `python-engine/cas_reachability_gate.py` renders the gate's verdict into a deterministic markdown SUMMARY.md. **Critical bug fix**: `_safe_phase_from_capture` was reading `doc["classifier"]["phase"]` and `doc["phase"]` -- the J.3 schema actually stores the bounded phase at `rows[i].classifier_phase`. The gate now iterates `rows[]` and reads `rows[0].classifier_phase`. NEW `--update-summary` / `--summary-path` flags on `python-engine/tools/cas_reachability_check.py`. NEW auto-update hook on `python-engine/tools/j2_capture_review.py` happy-path: the SUMMARY regenerates automatically when a capture review passes; fail-path leaves the SUMMARY untouched (fail-closed). NEW `python-engine/tests/test_cas_reachability_summary.py` (10 tests) and `python-engine/tests/test_j10_closure_e2e.py` (3 tests); `python-engine/tests/test_cas_reachability_gate.py` fixtures updated to the J.3 schema shape. **J.10.CLOSURE holiday validity**: `python-engine/market_calendar.py::NSE_HOLIDAYS_VALID_THROUGH = '2026-12-31'` is the documented validity period for the static set; `routes_holidays.py` exposes `valid_through` in the response. Net (after independent correction plan): python-engine +19 new tests (5 F6, 7 F3/F4/F5, 3 market-session, 4 holiday_drift updated); Node full suite **394 pass / 4 skip / 0 fail** (was 385 at J.10.CLOSURE close; +9 new); client 40/0/0 (no client changes). | **Operator-supplied staging captures still pending in staging** (CAS broker-behaviour verification). Plan §14: any auction-aware code must pass `tools/cas_reachability_check.py` before shipping -- this is the gate. The J.10.CLOSURE SUMMARY.md surface is the audit trail. `fno_chain.py::EXPIRY_CUTOFF_HOUR/_MIN = 15, 30` and `hedge_strategies.py::_EXPIRY_CUTOFF = time(15, 30)` preserved unchanged. Holiday reconciliation Python↔Node **DONE in J.5 + actually fixed in the independent correction plan (Node fallback aligned to 20 dates, drift=ALIGNED, holiday validity bound fail-closed at 2026-12-31)**; the `NSE_HOLIDAYS_FALLBACK` divergence is no longer a divergent degraded-mode -- it is now the exact ISO projection of the canonical Python set. Node `sessionPhase()` parity mirror **DONE in J.6**; J.7's CAS-aware execution gating **DONE in J.7** (and now hardened by the independent correction plan's authoritative Python projection + Node resolver); J.8's operator dashboard session-phase card **DONE in J.8**; J.9's CAS-aware signal handling **DONE in J.9**; J.10's CAS-branch reachability gate **DONE in J.10**; J.10.CLOSURE's operator-facing SUMMARY.md surface is the last J-series slice -- once operator-supplied staging captures land, the gate flips to REACHABLE and the J-series is operationally closed. |

## 16. Mandatory documentation and plan ritual

September 13 independent F/G audit correction: `2026-09-13-fg-independent-correction-plan.md` supersedes any implication that the whole new bridge/strategy basket is accepted. Atomic terminal-state/append-order fix, faithful trailing composition and immutable exit-cache manifests are tested in Dev. Approval budget/expiry/version checks now require immutable predeclared amount/DD/expiry and retain the original-clock validity window; twelve-file F/G acceptance passes 180 tests with warnings fatal. Reads still report `approval_usable=False`: frozen held-out/account/F/D evidence validation, faithful range semantics and unsupported F schema/provenance/historical closures remain open. External F/G work is preserved. The earlier whole-engine receipt predates cache and budget changes; full rerun remains required.

This is a user requirement for every future agent, including an agent continuing its own work:

1. Before editing, reconcile current state and write/update a plan slice: problem, user impact, affected files, dependencies, assumptions, acceptance tests, rollback and what will remain.
2. During implementation, record material discoveries and revise the plan when scope changes. Do not keep obsolete tasks marked pending or pretend abandoned approaches were implemented.
3. With every implementation commit, update SYSTEM_GUIDE.md for changed behavior and regenerate SYSTEM_CODE_ATLAS.md when files/declarations change. Update the active plan and acceptance evidence in the same commit when practical.
4. Immediately after every commit, inspect the commit/status. Confirm documentation and plan match actual behavior. If documentation was missed, make a prompt docs-only correction before further implementation.
5. Record commit ID, exact verification command/result, environment, migration/config impact, release/deployment status, remaining risks and next action. Never mark Production changed just because Dev was pushed.
6. At every handover, provide a concise current-state ledger and one executable next action. Preserve the whole product objective across context compaction.

Use the following plan slice template:

```text
ID / title:
Problem and user-visible impact:
Current authoritative evidence:
Files and contracts affected:
Implementation steps and dependencies:
Acceptance / negative / restart / timing tests:
Data and configuration migration:
Rollout and rollback:
Status and verified commit:
Documentation updated:
Unresolved limits and exact next action:
```

## 17. Completion and communication rules

A feature is done only when its acceptance conditions are met; a release is done only when promoted and verified; a strategy is qualified only when genuine reviewed evidence supports it. These are different claims.

Report progress as behavior and user value first, then tests and limits. Avoid repeated vague declarations that 'only operational evidence remains' while acquisition, collection or review integration is still unfinished. Avoid predicting a date for tips from the number of elapsed sessions alone. Explain what is missing and what action produces the needed evidence.

The next agent should review the complete Dev release diff/defaults and prepare the GitHub PR, while resolving actual authorized quiescence/backup/restore and previous-code schema compatibility using the consistent-backup plan/runbook. Production application containers were observed stopped; user was asked whether this was deliberate, with no implicit restart. The 17 earlier Python failures and two detected gateway handles are corrected; full baseline acceptance is 2,545 passed/3 skipped. Genuine Production collection and adequate held-out evidence remain required. Preserve the working replay/CLI, legacy-read compatibility and all retained artifacts. Do not restart the architecture from scratch.

## 18. September 20 closeout — AI activation and staging evidence

Status: **IMPLEMENTED_DEV, PUSHED; NOT DEPLOYED**. Source commit `1a6e0d9` is
on `origin/codex/production-correction-hedge-p0`. Detailed plan and Production facts:
`docs/2026-09-20-ai-and-partner-readiness-gap-plan.md`.

Completed in Dev:

- Compose explicitly enables bounded optional-AI annotation, source-event
  classification and usefulness reporting with non-blocking safe policies.
- Manual partner advisory is explicit; advanced hedge shadow observation is
  enabled while Phase-2/3 delivery remains explicitly disabled.
- A staging date is recorded only after genuine reconciled-portfolio and fresh
  option-chain shadow processing. One date is idempotent across repeated ticks.
- The E.1 readiness diagnostic now queries the deployed runtime schemas and
  hardened transport ledger. It no longer mislabels advanced Phase-3 0/7 as a
  blocker for ordinary manual index advice.
- Seven Phase-3 dates, live-chain verification and per-kind sample reviews are
  still required. No threshold was lowered and no delivery/order authority was
  added.

Remaining work is operational/evidence work, not another threshold change:

1. Promote through GitHub and restore healthy Production application services.
2. Verify deployed release/config identities and effective flags.
3. Log in on each intended market day and provide a genuine, fresh reconciled
   partner-position snapshot if advanced personalized hedge staging is wanted.
4. Observe actual shadow receipts/evaluations; perform live-chain and sample
   reviews. Do not backfill missed days from container uptime.
5. Separately complete genuine manual-advisory strategy qualification. The
   advanced hedge 7/7 counter is not that qualification and does not control
   generic NIFTY/SENSEX advisory scanning.

Acceptance receipt: 4,122 Python-engine tests passed/four skipped; 357 agent
tests passed in the built image with networking disabled; 27 corrected E.1
tests passed with warnings fatal; both affected images built; rendered and
runtime Compose flag checks match the safe matrix. Existing deprecation and
Dockerfile casing warnings remain. These checks establish Dev regression
fitness, not deployment, strategy profitability or qualification.

### 2026-09-20 D.3 exact-range correction

The bounded Dev release-note generator now makes `--base-ref` authoritative:
it resolves both endpoints, includes every commit in `base..HEAD` without the
legacy 30-commit cap, reports the exact SHA range/ahead count, and fails closed
on an invalid or unreadable range. Regression coverage includes the observed
31-commit boundary and a valid zero-commit range. D.3 PR preparation is now
truthful at the tooling boundary; reviewer approval, merge, deployment,
backup/restore evidence and Production verification remain operator-owned.

The same acceptance run closed an adjacent F.7 operator-tool defect: text
broker-statement reports now use `INR`, remaining encodable by cp1252 Windows
consoles. The full warning-fatal scripts suite passes 225/225. No calculation,
database, delivery or Production behavior changed.

The operator-ready PR handoff is captured in
`docs/2026-09-20-release-pr-handoff.md` from immutable source head `2766b00`
and base `fef35e7` (32 commits). Because the handoff is itself a final
documentation-only commit, regenerate once immediately before opening the PR;
the exact-range tool makes that final receipt deterministic.

### 2026-09-20 J.6 reproducibility correction

The session-phase golden producer is now byte-reproducible for unchanged
classifier semantics. It preserves provenance time only for an equal semantic
payload, updates it on a real change, writes both consumers from one canonical
string and avoids no-op writes. Focused acceptance: seven Python contract tests
and all 43 Node mirror tests pass. The two already-present local timestamp-only
fixture edits remain deliberately unstaged; a clean checkout running the new
producer will no longer create them.
