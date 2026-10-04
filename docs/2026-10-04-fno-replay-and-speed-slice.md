# F&O replay, trader candidates and speed (Dev) — October 4, 2026

Status: **built and scored on a pre-registered window. The shipped F&O book
remains the best version; no candidate is enabled. The two speed features
ship OFF.** Nothing is pushed or deployed. The Production data volume was read
only (read-only mount; containers were already stopped). This executes the
owner-approved F&O plan in
[improvement options and F&O review](2026-10-04-improvement-options-and-fno-review.md).

## What was built

| Piece | File | What it does |
| --- | --- | --- |
| Read-only dataset export | `scripts/export_fno_replay_dataset.py` | Run in a throwaway container with the data volume mounted `:ro`. Copies the research quote archive byte-for-byte (finalized segments plus past sessions' unsealed journals, flagged) and writes `fno-replay.sqlite` with NIFTY futures 5-minute candles, the live `fno_signals` log and paper positions, all SHA-256 bound in `manifest.json`. Output lives in git-ignored `docs/research/fno/<dated>/_local/`. |
| Pure entry planner | `python-engine/fno_entry_plan.py` | `plan_single_leg_entry` is the pure part of `_try_entry_for_leg` extracted verbatim: strike pick (|delta|≈0.55, ATM/ITM), §7 gate ladder, no-pyramid, pool sizing with the open-premium cap, §4 max-loss constitution, net reward/risk. The orchestrator now calls it, so live and research run one implementation. |
| Pure entry brakes | `fno_shared_risk.entry_halts` | Daily/weekly/monthly loss, drawdown and loss-streak brakes extracted from `_read_entry_policy`; behaviour unchanged. |
| Full-policy replay | `python-engine/fno_policy_replay.py` | Replays the shipped single-leg book tick by tick: verified archived quote batches (raw packets → the same `_parse_quote_entry`/`ChainSnapshot`), futures candles, live per-bar regime, `evaluate_fno_mom`, the entry planner, `evaluate_single_leg_exit`, `calc_fno_costs`, paper fills at ask/bid. The 90 s grid is phase-aligned to each day's logged live evaluations. FNO_PAPER equity is seeded with all earlier closes; the defined-risk book's actual closes are applied at their times, identically for every arm. Inert research (guard test). |
| Shared management helper | `fno_orchestrator._manage_single_leg_books` | The futures-quote + exit-ladder section of `run_fno_tick`, extracted verbatim and reused by the fast exit path. |
| Fast exit loop (OFF) | `run_fno_fast_exit`, `scheduler_setup` job `fno_fast_exit` | Every `FNO_FAST_EXIT_INTERVAL_SEC` (10 s) when `FNO_FAST_EXIT_ENABLED`: management only; one DB read when flat. |
| Bar-close trigger (OFF) | `scheduler_setup` job `fno_bar_close_tick` | When `FNO_BAR_CLOSE_TRIGGER_ENABLED`: the regular tick at :00/:05/… + `FNO_BAR_CLOSE_DELAY_SEC` (3 s). |
| One F&O lock | `scheduler_setup.register_fno_scheduler_jobs` | Regular tick, bar-close tick and fast exit never overlap; an overlapping pass is skipped with a log line. |
| Study runner | `scripts/run_preregistered_study.py` (`fno-trader-v1`) | `fno_replay` runner; the dataset is bound by re-hashing every manifest file. |

## Replay parity with the live paper book (Sep 10–Oct 1, 14 sessions)

The replay reproduced **8 of the 9 live paper trades**: same signal bar, same
contract, same exit reason, entry premium within a few rupees (for example Oct 1
NIFTY 22650 PE: live 199.95 → trail, replay 195.00 → trail; Sep 30 11:15 PE:
underlying stop in both, −₹2,056 live vs −₹1,991 replay). Residual differences:

- borderline reward/risk decisions flip with quote timing — the archive samples
  every ~60 s while live quoted at its own tick (Sep 21 11:50 in the aligned
  run, Sep 28 11:50 in the unaligned run);
- on Sep 10 and Sep 24 the live book was halted by a loss brake the current
  code does not produce (the logged rows predate the halt-name column; the
  shared-risk implementation changed with F0 on Oct 3), so the replay trades
  there and live did not.

Replayed baseline over all 14 sessions: 11 trades, +₹12,207 (live: 9, +₹10,756).

## Pre-registered result (`docs/research/fno/2026-10-04-fno-trader-v1/results.json`)

Frozen in commit `d973f05` before scoring. Development Sep 10–23 (8 sessions),
scored Sep 24–Oct 1 (6 sessions). Decision candidate `FNO_TRADER_V1`; the
component arms are attribution.

| Arm | Dev: trades / net | **Scored: trades / net / net excl. best / max DD** |
| --- | --- | --- |
| BASELINE (shipped) | 4 / −₹1,099 | **7 / +₹13,306 / +₹6,199 / ₹1,991** |
| FNO_FAST_EXIT | 4 / −₹1,271 | 7 / +₹13,112 / +₹6,004 / ₹1,991 |
| FNO_PARTIAL_TRAIL | 4 / −₹1,099 | 7 / +₹13,285 / +₹6,178 / ₹1,991 |
| FNO_HOUSE_MONEY_PYRAMID | 4 / −₹1,099 | 7 / +₹13,306 / +₹6,199 / ₹1,991 |
| FNO_TREND_DAY | 3 / −₹643 | 3 / +₹7,128 / +₹20 / ₹1,991 |
| FNO_TRADER_V1 | 3 / −₹814 | 3 / +₹7,128 / +₹20 / ₹1,991 |

Verdict: **NOT_SUPPORTED_STAYS_OFF** (profitable but does not beat the baseline).

- **Pyramid** never fired: the existing ₹30,000 structural max-loss cap refused
  the add on both one-lot winners (two lots of a ~₹230+ premium exceed it) and
  the two-lot winner was at `FNO_MAX_LOTS`. The owner's hard limits win.
- **Partial at target** banked once and cost ₹22 (the winner kept running).
- **Fast exit** moved one time-stop exit a minute earlier (−₹194); no stop
  overshoot happened in these sessions, and 60 s archive data cannot show the
  benefit it exists for (stops slipping on fast days).
- **Trend-day filter** was wrong: it skipped Sep 24 and all of Sep 28,
  including the +₹4,841 winner; good trend days often open wide.

Honest reading: six sessions and seven trades are far too few to qualify
anything, but they are enough to show that none of these ideas added value
here and that the shipped exit ladder (time stop + trail) is doing the work.

## Verification

- F&O suite before changes: 520 passed; after both refactors 534 (with the
  division report) — behaviour-neutral; final F&O + new tests 545+; full engine
  suite receipt in the handover entry.
- New tests: `test_fno_entry_plan.py` (planner outcomes, halts), `test_fno_policy_replay.py`
  (end-to-end on a format-genuine archive: entry at ask after bar close, time
  stop at bid, exact costs, fast exit, trail exit, partial, pyramid add and the
  structural-cap refusal, inertness guard), `test_fno_fast_exit.py`
  (default-off registration, bar-close cron, shared lock, no-op when flat,
  shared management path).
- Dev only; nothing pushed or deployed; Production only read.

## Rollout / rollback

Replay and planner extraction change no live behaviour. To try the speed
features in paper: set `FNO_FAST_EXIT_ENABLED=true` and/or
`FNO_BAR_CLOSE_TRIGGER_ENABLED=true` after the normal GitHub promotion; turn
them off to roll back. Watch `fno_tick_skip reason=fno_pass_in_progress` and
Kite quote-rate usage (one futures + one held-contract quote per 10 s).

## Next

1. Keep the archive growing (Production must be running) and re-export weekly;
   re-run `fno-trader-v1`-style studies on new, untouched sessions.
2. Ideas worth a frozen round on fresh sessions: IV-aware vehicle choice
   (debit spread when IV is rich), a time-stop variant (the replay shows the
   45-minute stop drives most outcomes), and BANKNIFTY as a second underlying
   under the shared budget.
3. Paper-enable the fast exit loop for protection; measure tick latency.
4. Go-live bar unchanged (40 days, 60 trades, PF ≥ 1.2); then a separately
   authorised 1-lot defined-risk pilot.
