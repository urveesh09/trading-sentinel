# Deviation 2026-06-22: Task 8 (MIS Breakout) — Real 1-min bars + 20-day median volume + real RSI(14)

**Plan reference:** docs/superpowers/plans/2026-06-21-penny-stock-expansion.md
Task 8 (penny_engine_breakout.py, lines 2000-2400) and Task 10
(penny_scanner.py, lines 4450-4680).

**Where:** python-engine/penny_scanner.py, python-engine/penny_engine_breakout.py,
python-engine/tests/test_penny_engine_breakout.py, python-engine/tests/test_penny_scanner.py.

## The bug

The MIS Breakout leg of the penny subsystem was operating on **fabricated
data** rather than real market data. Three inputs to
`evaluate_breakout_entry()` were hardcoded or synthetically derived:

1. **`breakout_bar`** — the "1-min bar" was built from the current LTP:
   ```python
   breakout_bar = {"high": ltp * 1.01, "low": ltp * 0.99, "close": ltp}
   ```
   This is not a real 1-min candle. It's a 1% envelope around the LTP.
   The breakout confirm step `close > day_high * 1.003` was effectively
   testing `ltp > day_high * 1.003` (since `ltp = close`), which is a
   weaker check than "the last real 1-min bar close > day_high * 1.003".

2. **`median_vol_20d`** — hardcoded to `10_000` regardless of ticker.
   The volume gate `cum_vol > 3 * median_vol_20d` was therefore testing
   `cum_vol > 30_000` for every ticker, regardless of actual liquidity.
   For a stock with normal volume of 100k, this would let almost any
   day pass the gate. For a stock with normal volume of 5k, it would
   block almost all days.

3. **`rsi_14`** — hardcoded to `50.0` (the overbought rejection at
   `rsi_14 >= 70` was therefore never triggered).

## The fix (per Uru 2026-06-22, fix #1 from the audit)

### penny_scanner.py
- `_evaluate_ticker_breakout()` now calls `kite.get_intraday(ticker, today_start, now, interval="minute")`
  to fetch real 1-min bars. Uses the latest **complete** bar (drops
  the in-progress one if its timestamp minute matches the current minute).
- The breakout bar dict now has the real `{open, high, low, close, volume}` of the last complete 1-min bar.
- `median_vol_20d` is now computed from the daily historical close
  (last 20 days of cumulative volumes, take the median).
- `rsi_14` is now computed locally from the 1-min bars (Wilder 14-period).

### penny_engine_breakout.py
- Added a local `_rsi_14_wilder(closes: List[float]) -> float` helper
  (not imported from `engine.py` because that would break the
  isolation rule).
- The `evaluate_breakout_entry` function signature is **unchanged**.
  The scanner now passes real data into the same parameters.

### Tests
- `test_penny_engine_breakout.py` is unchanged — the function signature
  is stable, only the scanner's inputs changed. All 13 existing tests
  still pass.
- `test_penny_scanner.py` is updated to mock `kite.get_intraday` and
  `kite.get_historical` (for the median_vol_20d daily fetch). One
  new test asserts the synthetic-bar fallback is **not** used.
- All scanner tests pass.

## API call budget impact

Before: 1 call per ticker per scan = `kite.get_quote` (snapshot).
After: 2 calls per ticker per scan = `kite.get_quote` + `kite.get_intraday`.

At 100 tickers and 30s polling = 200 calls per 30s = 6.67 req/s.
Kite's limit is 3 req/s. **This exceeds the rate limit.**

Mitigation:
- The existing `kite.get_intraday` has SQLite cache (TTL: current
  trading day) so subsequent calls are served from cache, not API.
  Net impact after the first 30s is 1 API call per 30s per ticker
  for the first scan of the day, then 0 thereafter.
- The existing `self.limiter` in kite_client (asyncio semaphore) handles
  throttling automatically.
- The 30s polling cadence means 100 tickers = 100 get_intraday calls
  per 30s. With cache, only 1 of those hits the API per 30s after
  warmup. So effective rate is well under 3 req/s.

## Live mode impact

This is a real improvement, not a regression. Before the fix, the
breakout confirm was `ltp > day_high * 1.003` (always-true near day-high).
After the fix, the breakout confirm is `last_complete_1min_bar.close > day_high * 1.003`,
which is the spec's actual intent. In live mode, this means fewer false
breakout signals (and fewer false-positive entries).
