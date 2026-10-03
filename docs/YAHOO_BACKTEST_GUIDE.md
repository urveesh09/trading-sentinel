# Run all non-F&O modules using Yahoo Finance

Run from **Dev**, using its existing Python environment:

```powershell
Set-Location 'C:\Users\Urveesh\Desktop\trading-sentinel'
.\python-engine\winvenv\Scripts\python.exe scripts\backtest_all_yahoo.py --start 2026-07-01 --end 2026-09-30
```

Start and end are inclusive IST dates. The script automatically creates a new
dated folder under `docs/research/yahoo/` and prints its `summary.md` path. Read
that file for the comparison, `summary.json` for machine results, `coverage.json`
for missing/invalid sessions, and `provider-manifest.json` for Yahoo receipts.
Large raw responses, imported/validated SQLite snapshots and detailed results
are in the ignored `_local/` subfolder. Full per-day `coverage.json` and full
`provider-manifest.json` are also locally retained and Git-ignored; dated
delivery sidecars bind their hashes and summarize them. Keep the **whole run
folder** if you need an offline rerun. Git receipts alone do not contain the data.
No new package is needed beyond the existing engine environment: Yahoo downloads
use Python's standard library; replays reuse the Lab and shipped functions.

## Useful arguments

```powershell
# A small explicit universe, still using each real strategy's rules
.\python-engine\winvenv\Scripts\python.exe scripts\backtest_all_yahoo.py --start 2026-09-24 --end 2026-09-30 --tickers PCJEWELLER,SOUTHBANK,RELIANCE

# Only selected modules
.\python-engine\winvenv\Scripts\python.exe scripts\backtest_all_yahoo.py --start 2026-07-01 --end 2026-09-30 --modules edge,swing,range

# Same archived Yahoo data, today's code, no new downloads
.\python-engine\winvenv\Scripts\python.exe scripts\backtest_all_yahoo.py --start 2026-07-01 --end 2026-09-30 --offline docs\research\yahoo\2026-10-03-q3 --out docs\research\yahoo\my-new-rerun
```

Other options:

- `--out NEW_DIRECTORY`: existing directories are refused to preserve evidence.
- `--workers 1..8`: bounded download concurrency; default 4. Rate-limit retry
  respects a bounded Retry-After delay; a failed response stays unavailable.
- `--stock-universe PATH` / `--penny-universe PATH`: JSON lists of symbols, or
  objects with `tickers: [{"symbol": "..."}]`. The default stock list is Dev's
  current 500-name configuration. A nonempty Dev Penny universe is preferred;
  otherwise the explicit October 1, 100-symbol fallback is used. This is current
  configuration, not reconstructed historical membership.
- `--symbol-map PATH`: explicit internal-symbol-to-Yahoo-symbol JSON. Defaults
  append `.NS`; actual NIFTY/BANKNIFTY indices use `^NSEI`/`^NSEBANK`, and EDGE
  uses the shipped NIFTYBEES proxy. No automatic guessed/fuzzy replacements.
- `--intraday-diagnostic-days 0..30`: default 7. An independently labelled
  shorter study within the original window; 0 disables it. Offline mode reuses
  the source's archived windows; it cannot acquire a different window.
- `--from`/`--to` are aliases for `--start`/`--end`. Future dates and unfinished
  current-session end dates are rejected.

Default modules are `penny-mis,penny-cnc,penny-joint,edge,swing,momentum,range,partner`.
Joint cash automatically includes MIS/CNC inputs, reuses their results once, and
normalizes aware clocks to UTC. Partner is reported `NOT_ADAPTED`: there is no
OHLCV advisory/protection money-book replay. F&O selections are rejected.

## What the output means

Yahoo daily history includes 900 calendar days of warm-up. Native minute and
15-minute bars are fetched separately; daily bars never replace intraday bars.
Observed October 3 provider limits are 30-day retention for minute bars, eight
days per minute request, and 60-day retention for 15-minute bars. Minute requests
are chunked into at most seven days; chunking cannot recover expired history.
The earliest requested interval is probed first. A rejected quarter stays
unavailable. A recent diagnostic does not become a quarter result. See the
[yfinance download documentation](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html)
and the preserved provider error receipts for the generic and observed limits.

The importer preserves original Yahoo quote OHLCV/actions without local
adjustment, resampling, repair, forward-fill or volume invention. All-null
timestamp slots represent no candle; flat zero-volume known-holiday marks and
the metadata-bound closing quote mark represent no session/interval candle.
Their dates stay in the raw receipts. Other malformed candles remain invalid.
B1 rejects their entire ticker-day in the separately hashed validated snapshot;
the original imported snapshot is retained. Missing/invalid daily symbols are
listed before scoring and make the effective universe explicitly partial.

Yahoo frequently reports zero-volume opening bars with a price range. Those
remain in the data, so the strict Penny complete-session result can be
unavailable. Separately named `gap-sensitivity` reports apply the existing
`allow_gaps` contract without changing entry thresholds or inventing volume.
Their assumptions and PARTIAL status remain visible.

MIS/CNC reports call the shipped paper lifecycle; joint cash is PORTFOLIO_PARTIAL.
EDGE, Swing and Range currently report decisions/selections, not trade profit.
Momentum has a virtual full-quantity T1 lifecycle, not its live partial runner;
`exit_fidelity` counts any later-day fallback exits. No result qualifies a strategy,
reconstructs broker/manual approval, or combines the books into a system return.
Current Dev defaults are frozen, rather than historical runtime overrides.

Policy/settings/importer hashes are frozen before acquisition and checked around
scoring; drift fails the module. Offline reuse verifies both the source snapshot
and every archived raw response. Module errors remain in the summary and do not
suppress other modules. No Sentinel candle/trade/ledger history, broker order
path, Production edit, runtime configuration change or deployment is involved.
