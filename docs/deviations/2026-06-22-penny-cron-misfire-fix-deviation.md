# Deviation 2026-06-22: penny_cron_misfire_fix — penny crons blocked by Nifty momentum scan

**Where:** python-engine/main.py, python-engine/penny_universe.py.

## The bug (detected by the prod log audit 2026-06-23)

The Nifty momentum scan registers a cron job for every (hour, minute)
combination in `[10..14] x [0, 15, 30, 45]` except `10:00`. Each scan takes
~5 minutes to walk 500 tickers (one `data_fetch` API call per ticker,
serialized through the rate limiter).

When the Nifty scan fires at :00, :15, :30, :45 IST, the
`AsyncIOScheduler` event loop is blocked on it. Any other job scheduled
for the same minute is queued but cannot run until the Nifty scan
finishes.

apscheduler default `misfire_grace_time=1` second. If a queued job's
fire time was missed by more than 1 second, the job is marked
"missed" and **silently dropped** (no log, no retry, no error).

Result observed in the running prod logs (2026-06-23):

  08:00:00 IST  penny_universe_refresh FIRED  (nothing else running)
  09:20:00 IST  penny_regime_compute FIRED   (nothing else running)
  09:30:00 IST  penny_connors_scan FIRED     (nothing else running)
  10:00:00 IST  penny_hourly_report MISSED   (Nifty scan blocked)
  11:00:00 IST  penny_hourly_report MISSED   (Nifty scan blocked)
  12:00:00 IST  penny_hourly_report MISSED   (Nifty scan blocked)
  13:00:00 IST  penny_regime_refresh MISSED  (Nifty scan blocked)
  14:30:00 IST  penny_eod_check MISSED       (Nifty scan blocked)
  00:05:00 IST  penny_daily_reset MISSED      (Nifty clear_intraday_cache blocked)

The 30s interval (`penny_scan_interval`) was never affected because
its trigger has a 30-second buffer that absorbs the contention.

## The fix

`main.py:35`: extend `misfire_grace_time` to 600 seconds (10 min),
and set `coalesce=False` so accumulated fires are not merged into one.

```python
scheduler = AsyncIOScheduler(
    timezone="Asia/Kolkata",
    job_defaults={
        "coalesce": False,
        "misfire_grace_time": 600,
    },
)
```

This means: if a penny cron is blocked by a long-running Nifty scan,
the penny cron will still fire up to 10 minutes late instead of being
permanently dropped. The next fire is still scheduled at the next
:00 minute.

## Bonus fix

`penny_universe.py:233`: `kite.get_quote(all_tokens)` was passing the
full ~2000 NSE EQ token list as a single `?i=...` URL parameter,
which exceeded Kite's URL length limit (the prod log shows:
`penny_universe_refresh_failed error=URL component 'query' too long`).

The fix batches the call into 500-token chunks:

```python
batch_size = 500
for start in range(0, len(all_tokens), batch_size):
    batch = all_tokens[start:start + batch_size]
    chunk = await kite.get_quote(batch)
    if isinstance(chunk, dict):
        quotes.update(chunk)
```

Each batch is well under Kite's URL limit, and per-batch failures are
logged + skipped so one bad chunk doesn't kill the whole refresh.

## Live-mode impact (after merge to Desktop)

- `penny_hourly_report` will start firing at 10:00, 11:00, 12:00,
  13:00, 14:00 IST. The Telegram send will follow the 3-tier chain
  (Telegram primary, urllib webhook backup, local log always).
- `penny_eod_check` will run at 14:30 IST and cut losses as designed.
- `penny_daily_reset` will reset `daily_pnl` at 00:05 IST.
- `penny_universe_refresh` will succeed at 08:00 IST instead of
  failing with URL too long.
- `penny_regime_refresh` will run at 13:00 IST for intraday refresh.

## Test impact

159 penny tests pass. The `test_refresh_from_kite_writes_static_json`
test continues to pass with the batched quote fetcher (the fake Kite
returns the same dict regardless of how the tokens are batched).