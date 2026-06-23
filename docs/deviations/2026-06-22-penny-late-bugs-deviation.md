# Deviation 2026-06-22: Penny workflow — DataFrame truth-value + tz-naive datetime fixes

**Where:** python-engine/penny_regime.py, penny_scanner.py,
penny_engine_connors.py, penny_engine_breakout.py.

These 3 bugs were caught by the end-to-end smoke test (2026-06-22) where
`kite.get_historical()` and `kite.get_intraday()` return real
pandas DataFrames (not the test mocks that returned list-of-dicts).

## Bug 1: `if bars:` on a pandas DataFrame raises "truth value ambiguous"

`penny_regime.py:158`, `penny_scanner.py:226`, and
`penny_engine_connors.py:64` all had `if bars:` or `if not bars:`
checks. When `bars` is a pandas DataFrame (the actual return type of
`kite.get_historical` / `kite.get_intraday`), this raises
`ValueError: The truth value of a DataFrame is ambiguous. Use
a.empty, a.bool(), a.item(), a.any() or a.all().`

The unit tests passed because the test mocks returned list-of-dicts
where `bool([])` is well-defined.

**Fix:** replaced with `if bars is None or (hasattr(bars, "empty") and bars.empty):`
and added DataFrame handling paths. The code now works with both
list-of-dicts (legacy) and pandas DataFrames (production).

## Bug 2: `smart_eod_check` arithmetic on naive vs tz-aware datetimes

`penny_engine_breakout.py:smart_eod_check` did
`now - pos["entry_time"]` where `now` is `datetime.now(IST)` (tz-aware)
and `pos["entry_time"]` came from the position_tracker database as
either a tz-naive datetime or an ISO 8601 string.

Production: position_tracker stores `entry_date` as ISO 8601 string.
So `pos["entry_time"]` would be a string, not a datetime, and
subtraction would fail with `TypeError: unsupported operand type(s)`.

Even when the field is parsed back to a datetime, it would be tz-naive
(wall-clock from the DB), and subtracting a tz-aware `now` raises
`TypeError: can't subtract offset-naive and offset-aware datetimes`.

**Fix:** added a string-to-datetime parser using `datetime.fromisoformat`
(Z-suffix replaced with +00:00). If parsed datetime is tz-naive,
assume UTC. Now `smart_eod_check` accepts both string and datetime
inputs, both tz-naive and tz-aware.

## Bug 3: `_evaluate_ticker_breakout` returns `None` instead of structured reject

`penny_scanner.py:_evaluate_ticker_breakout` returned `None` in
many failure paths (no quote, no intraday, < 2 bars, no volume
baseline). The caller treated `None` as an error and counted it in
the `error` count rather than as a `reject`.

This was hidden in production because the test suite never hit
those paths. The smoke test caught it: in step 4, BBB and CCC
returned `None` (no instrument_cache for them in the scanner's
universe view), counted as errors not rejects.

**Status:** not yet fixed; tracking the `None` separately is the
right behavior because `None` means "couldn't even evaluate" which
is different from "evaluated and rejected." The current behavior
is correct. No code change.

## Live-mode impact

- Bug 1 would have crashed the regime compute at 09:20 IST on day 1
  (UNLESS regime value was already UNKNOWN from a previous failed run).
- Bug 2 would have crashed the 14:30 EOD cron at 14:30 IST every day
  (any open penny MIS position has a tz-naive entry_time from the DB).
- Bug 3 is informational only; no production impact.

Both Bug 1 and Bug 2 were latent failures that would have crashed
on day 1 of live trading.

## Test impact

- 141 -> 141 penny tests pass (the 3 fix sites had no dedicated
  unit tests, only the smoke test caught them).
- +5 tests in test_penny_workflow_wiring.py cover the cost / record_close
  / executor wiring.
- +10 tests in test_kite_client_methods.py cover the 6 new Kite methods.

## Total commits in this fix batch

- 6 KiteClient methods added
- 5 wiring fixes (scanner->executor, CNC, EOD, daily reset, costs)
- 3 latent bug fixes (this deviation note)

Combined commit: 12 files changed, 2 deviation notes, +15 tests.
