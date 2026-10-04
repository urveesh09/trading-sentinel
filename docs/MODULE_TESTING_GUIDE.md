# How each Sentinel module is tested

A plain guide to how every trading module is tested before any change is
switched on, with the exact commands. The detailed rules are in
[RESEARCH_TESTING_METHOD.md](RESEARCH_TESTING_METHOD.md); how to download
Yahoo data is in [YAHOO_BACKTEST_GUIDE.md](YAHOO_BACKTEST_GUIDE.md).
Everything here runs in **Dev**, offline, and never places an order.

## The idea in plain words

1. **Replay the past minute by minute.** The module's real code decides what it
   would have bought and sold, using only prices it could have seen at that
   moment. Fills include trading costs and slippage. If the high and the low
   happen in the same bar, we assume the stop was hit first (the worse case).
2. **Compare against what we run today.** The current version ("BASELINE") is
   replayed on exactly the same days, with the same money, next to the new idea.
3. **Two sets of days.**
   - **Development days** are where ideas are designed and debugged.
   - **Untouched days** are kept hidden until the idea is frozen, then scored **once**.
   - Once we have looked at a day, it can never be "untouched" again.
4. **Freeze before scoring.** A `freeze.json` file records the exact code, data,
   days and pass/fail rule. It is committed to git *before* the score is run, so
   nobody, including the agent, can quietly change the rules after seeing results.
5. **The same four checks every time.** A new version passes only if, on the
   untouched days, all four hold:
   - it made money;
   - it still made money without its single best trade;
   - it beat the current version;
   - its worst fall was no more than 1.5× the current version's.

   Passing means "keep watching it on paper". It never means "go live".

## Which data each module uses

| Module | What it trades | Price data used for tests | Test tool |
| --- | --- | --- | --- |
| Momentum | Intraday Nifty-500 stocks (MIS) | Yahoo 15-minute bars (about 60 days kept by Yahoo) + NIFTY 50 15-minute bars | `momentum_replay.py` via Lab id `momentum_intraday_15m_replay` |
| Penny (same-day) | Intraday penny stocks (MIS) | Yahoo 1-minute bars (about 30 days kept) | `penny_lifecycle_replay.py` via `penny_breakout_mis_lifecycle_1m` |
| EDGE | Penny stocks held for days (CNC) | Yahoo daily bars (900 days) | `edge_portfolio_replay.py` via `penny_edge_portfolio_replay` |
| Range | Range reversion, daily | Yahoo daily bars | `range_portfolio_replay.py` |
| Swing | Trend swing trades, daily | Yahoo daily bars | `swing_portfolio_replay.py` |
| F&O single option | NIFTY options intraday | Sentinel's own recorded option quotes (Production archive, exported read-only) | `fno_policy_replay.py` |

Intraday Yahoo data expires quickly, so **untouched intraday days are scarce**.
They come from (a) new trading days recorded going forward, or (b) Kite
historical candles for older months, which needs a Kite login on the day of
download.

### Getting untouched intraday data from Kite

```powershell
# Needs a same-day Kite session: KITE_ACCESS_TOKEN, or --token-file pointing at
# the engine's kite_token.json. Read-only market data; run after 15:45 IST so it
# never competes with live trading for the broker's rate limit.
& $py scripts\acquire_kite_history.py --tickers-from docs\research\yahoo\2026-10-04-momentum-thesis-t2\freeze.json `
  --start 2026-01-01 --end 2026-07-31 --interval 15minute --index "NIFTY 50" `
  --out docs\research\kite\2026-10-05-momentum-h1\_local\validated-kite.sqlite
& $py scripts\acquire_kite_history.py --tickers-from docs\research\yahoo\2026-10-04-penny-trader-oos\freeze.json `
  --start 2026-01-01 --end 2026-07-31 --interval minute --index "" `
  --out docs\research\kite\2026-10-05-penny-h1\_local\validated-kite.sqlite
```

Look only at the printed coverage (and `coverage.json`), never at strategy
results, before freezing a study on that data.

## Step by step (any module)

```powershell
Set-Location 'C:\Users\Urveesh\Desktop\trading-sentinel'
$py = '.\python-engine\winvenv\Scripts\python.exe'

# 1. See the registered studies
& $py scripts\run_preregistered_study.py list

# 2. Freeze (writes freeze.json; the output folder must not exist yet)
& $py scripts\run_preregistered_study.py freeze <study> --out docs\research\yahoo\<date>-<study>

# 3. Commit the freeze BEFORE scoring
git add docs\research\yahoo\<date>-<study>\freeze.json
git commit -m "research: freeze <study>"

# 4. Score once (refuses to run if code or data changed since the freeze).
#    --jobs runs the independent arms in parallel (long intraday studies).
& $py scripts\run_preregistered_study.py run <study> --out docs\research\yahoo\<date>-<study> --jobs 3
```

`results.json` (committed) holds every arm's numbers and the verdict. The full
per-trade reports stay in the git-ignored `_local/` folder.

## Module notes

### Momentum
- The replay runs the live evaluator (`engine.evaluate_momentum_signal`) on every
  completed 15-minute bar. Orders fill at the **next bar's open**, resized to the
  same rupee risk. The 15:15 square-off uses the exact 15:15 bar.
- Exit models: `LIVE_EXIT_LIFECYCLE` (today's exits), `THESIS_EXIT` (tested
  October 4, failed) and `RUNNER_EXIT` (new: no fixed target, break-even after
  +1R, trail under completed bar lows).
- Entry variants: `MOM_BASE` (today), and `MOM_SELECTIVE` (new: market up, stock
  stronger than NIFTY, above yesterday's high). `MOM_SELECTIVE` needs NIFTY 50
  15-minute bars in the same data file (ticker `NIFTY 50`).
- Books: ₹50,000 paper size (the decision book) and the live ₹2,500 pool.

### Penny (same-day)
- Replays the shipped Penny breakout minute by minute: LTP fills, drift and
  circuit checks, a paper stop monitor, a 15:00 square-off, MIS costs per order
  and an own-cash check.
- The baseline must reproduce its archived receipt (+₹15.18 / 18 trades on
  Sep 24–30) before any candidate result counts.

### EDGE, Range and Swing (daily)
- Shared own-cash daily book (`daily_portfolio.py`). Signals are decided after
  the close and filled at the next day's open (the 09:30 stand-in), with stop
  before target, no doubled ticker and dust fills skipped.
- Untouched daily history still exists for **2024–2025**.

### F&O
1. Export Sentinel's own recorded quotes read-only from Production (command in
   RESEARCH_TESTING_METHOD.md).
2. Replay with `fno_policy_replay.py`. It runs the shipped entry planner, risk
   brakes, adaptive sizing and exit ladder, buying at the ask and selling at the bid.
3. Check `parity_vs_live` first. The baseline must reproduce the real paper
   trades (October 4: 8 of 9) before trusting anything else.
- From October 5, 2026 Production also records SENSEX and NIFTY futures candles
  after each session (`research_future_candles`), so SENSEX can be replayed later.
- One-off what-if tests (for example a different starting amount) use
  `docs/research/fno/2026-10-04-growth-window-test/run_window.py` and
  `ledger_whatif.py`.

## Results so far (all candidates stayed OFF)

| Module | Study | Current version on untouched days | Best new idea | Verdict |
| --- | --- | --- | --- | --- |
| Penny MIS | `penny-trader-t1` (Sep 7–23 + Oct 1) | 24 trades, +₹63.17 | PEN_TRADER_V2: −₹17.02 | Stays OFF |
| EDGE | `edge-trader-t1` (Jan–Jun 2026, ₹1L book) | 140 trades, −₹40,166 | EDGE_TRADER_V1: −₹44,777 | Stays OFF |
| Range | `range-trader-t2` (Jan–Jun 2026) | 174 trades, −₹9,024 | RANGE_TRADER_V1: −₹6,650 | Stays OFF (better, still losing) |
| Swing | `swing-trader-t2` (Jan–Jun 2026, ₹4,500) | 70 trades, −₹1,288 | SWING_TRADER_V1: −₹255 | Stays OFF (better, still losing) |
| Momentum | `momentum-thesis-t2` (Aug 10–Sep 23 + Oct 1) | 54 trades, −₹120.87 | MOM_THESIS_EXIT: −₹149.76 | Stays OFF |
| F&O | `fno-trader-v1` (Sep 24–Oct 1) | 7 trades, +₹13,306 | FNO_TRADER_V1: +₹7,128 | Stays OFF |

Which days are already used up is listed in the window ledger in
RESEARCH_TESTING_METHOD.md. Update both files whenever a new study is scored.

## What a test can and cannot tell you

- It shows how the rules would have behaved on those days, after costs. It
  cannot show broker rejections, partial fills, or your own manual decisions.
- A few weeks of results is not proof of a lasting edge. Passing leads to more
  paper watching, then a separate decision to promote through GitHub.
- Never re-tune an idea on days you have already scored. That is how backtests
  lie.
