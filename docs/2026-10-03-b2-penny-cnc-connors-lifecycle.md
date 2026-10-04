# B2 (second half) — exact classic Penny CNC Connors lifecycle replay (October 3, 2026)

Parent: [October 3 plan](2026-10-03-backtesting-and-fno-safety-plan.md) B2;
first half in [B1/B2](2026-10-03-b1-b2-data-contracts-and-penny-lifecycle.md).

## What the shipped CNC book actually does (source-verified)

**Entry.** `run_penny_connors_scan` runs once daily at 09:30 IST
(`main.py:437`), on trading days only.
- **Daily history.** `PennyScanner._evaluate_ticker_connors` calls
  `get_historical(from = as_of − DAILY_HISTORY_DAYS, to = today)`. At 09:30
  the cache cannot hold today's row, so this **fetches Kite day candles up to
  today**. These include today's *in-progress* candle (roughly 09:15–09:30),
  and the fetch also writes it to `ohlcv_cache`; a later fetch overwrites it
  with the final candle.
- **Evaluator inputs.** `evaluate_connors_entry` receives:
  - `closes`, whose last value is today's partial close;
  - `today_volume`, the partial candle's volume (about 15 minutes);
  - `avg20_volume`, the median of the last 20 of the last 21 volumes,
    including the partial bar;
  - `regime_size_pct` from `PennyRegimeEngine().size_pct(regime)`.
- **Gates.** At least 250 bars, then the trend gates (above SMA-200 and
  SMA-50), RSI(2) below 10, RSI rising for 2 bars, and the volume sanity
  check.
- **Sizing.** `PennyRiskEngine` with the fixed bankroll.
- **Admission.** Per-ticker reservation plus caps
  (`PENNY_MAX_POSITIONS_TOTAL=5`, `PENNY_MAX_POSITIONS_CNC=2`), then the
  executor's drift and stop checks. Paper fills at the LTP. The position
  stores `atr_14_at_entry = decision.get("atr_14", 0.0)`, which is **0**,
  because Connors decisions carry no `atr_14`.

**Exits for the paper book.** `position_tracker.update_daily_positions`,
called by `run_daily_post_market` at **15:45 IST**, applies only to
`PENNY_PAPER`/`EDGE_PAPER`. On each day's daily bar:
- **Trailing stop:** chandelier trail only if `atr_14_at_entry > 0`, so for
  CNC the trail is disabled and the stop stays put.
- **Stop:** the stop is hit (low ≤ trailing stop) unless T1 or T2 was also
  hit that day. Exit at `min(stop, open)`.
- **T2:** exit at `max(T2, open)`.
- **T1:** while the row is `OPEN`, `floor(shares × 0.5)` shares exit (all of
  them for a 1-share position) at `max(T1, open)`. The rest stay open as
  `CLOSED_T1`, with the stop raised to breakeven.
- **Time stop:** at 15 or more calendar days held, exit at the close.
- **Costs:** `engine.calc_zerodha_costs(..., is_intraday=False)`.

**Shipped facts found and recorded, not changed:**
1. `penny_engine_connors.evaluate_connors_exit` (3-day time stop, T2,
   post-T1 trail) has **no runtime caller**. The spec's Connors exits are
   not what runs.
2. **Live** CNC (`PENNY`) rows are skipped by the tracker, so only the
   broker SL-M ever exits them. There is no time, target or T1 management.
   Live classic Penny trading is off by default (`PENNY_LIVE_TRADING=False`).
3. The entry-day 15:45 check uses the whole day's low and high, including
   trading before the 09:30 fill.
4. After a T1 partial, a day that touches both the stop and T1 (without T2)
   neither stops nor exits, because the stop branch requires "no target hit".
5. The 09:30 volume gate compares about 15 minutes of volume with a daily
   median, so it is very hard to pass.
6. Mid-session partial daily candles are written to `ohlcv_cache` until a
   later fetch replaces them.

## Contract — `python-engine/research_penny_cnc_lifecycle.py` (new, offline)

The module is deliberately **not** named `penny_*`: it reuses
`engine.calc_zerodha_costs` (as the tracker does), which the Penny
isolation rule forbids for runtime Penny modules.

- **Data (B1 contracts).**
  - Daily bars dated before D (point-in-time) inside the
    `DAILY_HISTORY_DAYS` window.
  - **Today's partial candle**, rebuilt from validated minute bars
    09:15–09:29 of D. The open is the first bar's open, the high and low
    are the extremes, the close is the last close, and the volume is the
    sum. A day with no such bars is `NO_PARTIAL_CANDLE_EVIDENCE` and is not
    evaluated; nothing is invented.
  - The **final** daily bar of D for the 15:45 tracker.
- **Entry.** The real `evaluate_connors_entry` with the scanner's exact
  input construction, real `PennyRiskEngine` sizing, the CNC caps (CNC
  max 2; total 5 counting only replayed CNC positions) and one position per
  ticker.
  - The executor checks use the LTP at 09:30: the open of the 09:30 bar if
    it traded, otherwise a mark.
  - The fill requires a traded bar. Without one the entry is
    `NO_EXECUTABLE_EVIDENCE`.
- **Exits.** A pure re-implementation of the tracker's branch order and
  arithmetic, **proved equal** by a parity test that runs the real
  `update_daily_positions` (fake broker, temporary DB) day by day on the
  same bars. The entry is likewise proved equal to the real
  `PennyScanner._evaluate_ticker_connors`.
- **Book scope.** `PENNY_PAPER` only. `PENNY` (live) has no shipped exit
  management to replay and is reported `UNSUPPORTED`.
- **Not replayed (declared):**
  - point-in-time universe and regime;
  - MIS positions occupying total capacity;
  - broker blocks and rejections;
  - scheduler jitter.

## Acceptance

- Entry parity with the real scanner across accept and reject paths.
- Tracker parity with the real `update_daily_positions` for:
  - stop (and gap), T1 partial then breakeven stop, T2, and T1-then-T2;
  - the 15-day time stop;
  - the quirks: a 1-share T1 closes fully; stop plus T1 on the same day
    after T1 holds.
- A missing partial candle or a missing final daily bar is reported, never
  invented.
- The run is deterministic, and the Lab adapter `penny_cnc_connors_lifecycle_1d`
  (`LIFECYCLE`) plus CLI `--strategy cnc` exist.

## Rollout and rollback

- **Rollout.** Offline, Dev only. A new module, an additive Lab entry and
  a CLI option. The predeclared real-data run waits until Production is
  running again; it is read-only collection.
- **Rollback.** Revert the module, Lab entry and CLI option.

## Implementation result (Dev only; not pushed, not deployed)

### New files

- **`python-engine/research_penny_cnc_lifecycle.py`.**
  - `partial_candle` and `scanner_daily_frame` rebuild the scanner's exact
    09:30 inputs, point-in-time.
  - `connors_decision` calls the real `evaluate_connors_entry`.
  - `tracker_step` mirrors `update_daily_positions` exactly.
  - `run_penny_cnc_lifecycle` handles admission, the executor checks, the
    15:45 tracker, missing-bar reporting and the summary. For `PENNY` (live)
    it returns `UNSUPPORTED`.
- **Backtest Lab.** `PennyCncConnorsLifecycleAdapter`
  (`penny_cnc_connors_lifecycle_1d`, `LIFECYCLE`).
- **CLI.** `scripts/run_penny_research.py --strategy cnc`, using a
  read-only collector that reads only the 09:15–09:30 minute slice plus
  about 1,100 days of daily bars, with a coverage-only selection rule.

### Verification (from `python-engine`, Windows)

| Command | Result |
| --- | --- |
| `-m pytest tests/test_research_penny_cnc_lifecycle.py -q -W error` | **14 passed** |
| `scripts/tests/test_run_penny_research.py` (from the Dev root) | **7 passed** |
| Lab, MIS lifecycle, CNC lifecycle and Penny isolation | **57 passed** (known HTTPX deprecation) |

**Tracker parity.** For each scenario the real `update_daily_positions` ran
on a temporary DB with a fake broker, against the pure tracker on the same
bars. Status, shares, trailing stop, exit price, exit date and realised P&L
matched for:
- stop, and gap stop;
- T1 partial then breakeven stop;
- T1 then T2;
- the 15-day time stop;
- after T1, a day with both the stop and T1 touched (holds);
- stop and T1 on the same day while open (T1 wins);
- a 1-share T1 (closes fully).

**Entry parity.** The real `PennyScanner._evaluate_ticker_connors` and the
replay agree on an accepted setup (entry, stop, T1, T2, shares, RSI(2)) and
on the partial-candle volume reject.

**End to end.** One trade: the T1 partial, then T2.

**Not run yet.** The predeclared real-data run uses the read-only Production
collector, and the Production stack is stopped (exit 137 at 12:22 IST). Run
it once Production is up:

```
.\python-engine\winvenv\Scripts\python.exe scripts/run_penny_research.py --container python-engine \
  --strategy cnc --from 2026-07-30 --to 2026-09-03 --sample-count 40 \
  --output docs/<new>-penny-cnc-lifecycle.json
```
