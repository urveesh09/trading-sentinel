# How we test a strategy change (pre-registered candidate studies)

Companion to [YAHOO_BACKTEST_GUIDE.md](YAHOO_BACKTEST_GUIDE.md). That guide
explains how to download Yahoo data and run every module. This one explains how
to decide whether a **new version of a module is actually better** without
fooling ourselves. Everything runs from **Dev**, offline, with no broker access.

## The method in one paragraph

Reproduce the shipped baseline exactly. Express the idea as a named candidate
next to it, never by editing the baseline. Replay both on the same frozen data
with the same execution clock, own-cash book and costs. Design and debug only on
a *development* window. Before looking at anything else, commit a freeze that
binds the code, data, windows and pass/fail rule. Score the *untouched* window
exactly once. Accept the verdict, record it, and never re-tune on a window that
has now been seen.

## Rules every study follows

1. **Baseline first.** The baseline arm must reproduce the archived receipt for
   the same data (for example Penny MIS +₹15.1765 / 18 trades on Sep 24–30). If it
   doesn't, fix the harness before testing anything.
2. **Causal clocks.** A decision uses only bars already complete. Daily signals
   are decided after the close and fill at the next open (the 09:30 proxy).
   Intraday decisions on bar *k* fill at bar *k+1*'s open. One OHLC bar cannot
   show whether the high or the low came first, so **the stop always wins a tie**.
   A scheduled exit never looks at a later bar.
3. **Own cash only.** No margin or leverage. Open notional plus a new entry can
   never exceed the book. One position per ticker. Fills smaller than a quarter of
   the planned size are skipped as dust. This is the owner's rule, and the book
   enforces it for every arm, including baselines whose runtime does not.
4. **Real costs and slippage.** Use the runtime cost schedules (`calc_penny_costs`,
   `calc_zerodha_costs`, MIS snapshots) per order. Brokerage bypass is refused.
5. **Report the money, not the activity.** Net P&L, net excluding the best winner,
   marked or realised drawdown, win rate, profit factor and exit reasons. Trade
   counts, signal counts and win rate alone prove nothing.
6. **Two windows.** *Development* is where candidates are designed; it is
   in-sample by definition. *Untouched* is scored once after the freeze. A window
   becomes development data forever once any result on it has been seen.
7. **Freeze before scoring.** `freeze.json` binds source hashes, the validated
   snapshot, configuration, arms, books, windows and the decision rule. Commit it
   before `run`. `run` refuses to start if anything bound has changed.
8. **The same decision rule everywhere.** A candidate is *promising* only if, on
   the untouched window: net P&L > 0, net excluding the best winner > 0, net P&L
   beats the baseline, and drawdown ≤ max(1.5 × baseline drawdown, floor).
   *Promising* means "continue broker-free shadow". It never means qualified or
   live.
9. **At most two candidates per module per round**, ideally one entry change and
   one exit change, so causes stay identifiable. Every failed or unavailable
   result stays in the ledger.

## Running a study

```powershell
Set-Location 'C:\Users\Urveesh\Desktop\trading-sentinel'
$py = '.\python-engine\winvenv\Scripts\python.exe'
& $py scripts\run_preregistered_study.py list
& $py scripts\run_preregistered_study.py freeze swing-trader-t2 --out docs\research\yahoo\2026-10-05-swing-round2
git add docs\research\yahoo\2026-10-05-swing-round2\freeze.json; git commit -m "research: freeze swing round 2"
& $py scripts\run_preregistered_study.py run swing-trader-t2 --out docs\research\yahoo\2026-10-05-swing-round2
```

`run` prints one line per (window, book, arm) and the verdict, and writes
`results.json` (committed) plus per-run reports under `_local/` (git-ignored,
keep locally). Momentum and Penny MIS runs take tens of minutes; daily modules
take a few minutes.

## Getting fresh untouched data

Untouched windows are the scarce resource. Yahoo keeps about **30 days of 1-minute**
and **60 days of 15-minute** history, so intraday windows expire. Archive forward
data regularly:

```powershell
# Penny minute data for the last ~4 weeks (start no earlier than today - 29 days)
& $py scripts\backtest_all_yahoo.py --start 2026-10-05 --end 2026-10-30 --modules penny-mis --tickers <list> --intraday-diagnostic-days 0 --out docs\research\yahoo\<dated>-penny-window
# 15-minute stock data for Momentum
& $py scripts\backtest_all_yahoo.py --start <today-55d> --end <yesterday> --modules momentum --intraday-diagnostic-days 0 --out docs\research\yahoo\<dated>-momentum-window
```

Do **not** read the module results that the acquisition run prints for a window
you intend to keep untouched; check only coverage (`coverage.json`). Do not edit
source files while an acquisition runs: its own guard refuses the module result.
Daily data has 900 days of history, so 2024–2025 daily windows remain untouched
for every daily module.

## Adding a new candidate or study

1. Put strategy logic in a pure research module. Do not touch runtime modules,
   `engine.py`, `regime.py`, scheduler, broker or F&O code.
2. Daily modules plug into `python-engine/daily_portfolio.py`. Supply
   `signals_after_close(day, equity)` and an exit policy (`admit`,
   `resting_levels`, `on_partial`, `at_close`). Do not write a new book.
3. Register a Lab adapter (subclass `DailyPortfolioAdapter` in `backtest_lab.py`)
   and add it to `backtest_catalogue.py`.
4. Add tests for the clock, cash, ties and each new rule, then a smoke run on a
   few development days.
5. Add a `Study` entry in `scripts/run_preregistered_study.py`. Then freeze,
   commit, run and record.

## F&O studies (archived quotes, not Yahoo)

F&O option history is not on Yahoo. The engine already archives every NIFTY
quote batch (future + ATM±5 calls/puts, two expiries, raw packets) on the data
volume. Export it read-only, then study it with the same tool:

```powershell
# 1. Export (data volume mounted read-only; output folder must be empty)
docker run --rm -v production_trading-sentinel_trading_data:/data:ro `
  -v "C:\Users\Urveesh\Desktop\trading-sentinel\docs\research\fno\<dated>-archive\_local:/out" `
  -v "C:\Users\Urveesh\Desktop\trading-sentinel\scripts:/scripts:ro" `
  --entrypoint python production_trading-sentinel-python-engine:latest `
  /scripts/export_fno_replay_dataset.py --data /data --out /out
# 2. Quick look at one policy (development days only)
& $py python-engine\fno_policy_replay.py --data docs\research\fno\<dated>-archive\_local --start <d1> --end <d2> --policy BASELINE
# 3. Pre-registered comparison: add/adjust a Study with runner="fno_replay", then freeze, commit, run
```

Always read the replay's `parity_vs_live` block first: the BASELINE must
reproduce the live paper trades on the same days before any candidate result
means anything (October 4 receipt: 8 of 9). The replay runs the shipped entry
planner, gates, exit ladder, costs and brakes; never fork them for research.

## Window ledger (what has already been seen)

| Module | Development (seen) | Scored untouched (now seen) | Still untouched |
| --- | --- | --- | --- |
| Penny MIS | Sep 24–30, 2026 | Sep 7–23 + Oct 1, 2026 | forward data from Oct 5, 2026 |
| EDGE | Jul–Sep 2026 | Jan–Jun 2026 | 2024–2025 daily |
| Range | Jul–Sep 2026 | Jan–Jun 2026 (T2) | 2024–2025 daily |
| Swing | Jul–Sep 2026 | Jan–Jun 2026 (T2) | 2024–2025 daily |
| Momentum | Sep 24–30, 2026 | Aug 10–Sep 23 + Oct 1, 2026 (T2) | forward 15-minute data |
| F&O single-leg | Sep 10–23, 2026 | Sep 24–Oct 1, 2026 (`fno-trader-v1`) | archive sessions from Oct 5, 2026 |

Historical note: the T1 Penny and EDGE freezes were made with the earlier
per-module scripts (`scripts/run_penny_trader_oos.py`,
`scripts/run_edge_trader_oos.py`, commits `22a7ce6` and `684de3d`). The generic
tool replaced them and carries the same study definitions.

## What a result can and cannot tell you

- Replays are `PORTFOLIO_PROXY` / `LIFECYCLE` scope. They cover no manual approval,
  broker rejection, partial fill or point-in-time universe/event calendar.
- Daily bars cannot show 09:30 or 15:15 prices; the open and close stand in.
- A promising verdict on a few weeks or one half-year is not a durable edge.
  The next step is forward shadow data, then a separately authorised GitHub
  promotion with F&O noninterference checks.
