# Yahoo-only non-F&O backtesting slice — October 3

## Problem and authorized scope

The owner requests one repeatable script with start/end date arguments, Yahoo
market data instead of retained Sentinel price/trade history, and current shipped
non-F&O strategy functions. Implement and exercise it in Dev `3cbf0ff` only.
Do not tune strategy rules, change live scheduling/funding, call a broker, edit
Production or push/deploy. Current universe configuration is allowed; historical
positions, cash, candles, quotes and operational results are not inputs.

## Files and contracts before implementation

- `scripts/backtest_all_yahoo.py`: single entry point; inclusive `--start/--end`,
  optional explicit ticker/universe/module selection, fresh output directories,
  raw provider receipts, native interval parsing, immutable Lab snapshot, frozen
  source/default assumptions, independent module reports and readable summary.
- `scripts/data/backtest_penny_universe.json`: symbol-only fallback copied from
  the last frozen current 100-name configuration, because the checked-in Dev
  Penny universe is empty. Prefer a nonempty current configured universe; accept
  explicit overrides. Label current membership, never historical constituents.
- `scripts/tests/test_backtest_all_yahoo.py`: deterministic provider fixtures,
  dates/timezones/intervals, missing/corrupt rows, errors, exclusions, no overwrite,
  F&O rejection, adapter scope, all-module isolation and same-data offline reruns.
- Existing Lab/CLI/B1 functions supply current strategy/default-cost behavior;
  the script does not invent lifecycle adapters for evaluator-only books. Joint
  Penny uses the shipped cash reconciler on cached MIS/CNC results with explicit
  UTC-normalized clocks, avoiding duplicate expensive strategy execution.
- Guide, active plan, checklist and regenerated atlas; dated real-run receipts.

Yahoo chart endpoint is publicly reachable in this environment. Use Python's
standard HTTP/JSON libraries (no runtime dependency addition), native NSE `.NS`
mapping plus `NIFTY 50 -> ^NSEI`, `NIFTY BANK -> ^NSEBANK`. Validate provider
identity, INR and exchange timezone. Preserve raw quote OHLCV/actions exactly;
no local price adjustment, interpolation, repair, interval substitution or
corporate-action smoothing. Record provider adjustment ambiguity.
All-five-null provider timestamps are absence placeholders, not candles; retain
their dates in the receipt and raw payload, leave sessions missing, and do not
insert fake OHLC rows. Partially null or malformed actual candles remain invalid.
Known closed-session flat zero-volume daily marks likewise remain archived as
non-session marks instead of entering a 20-day volume/SMA history as a traded
holiday. Positive-volume special sessions or ranged bad marks are not removed.
Keep the full imported snapshot, then build a separately hashed B1-validated
snapshot that excludes entire INVALID ticker-days and invalid daily symbols.
This lets valid other days run without deleting selected bad bars inside a day.
All exclusions and raw coverage remain in the report; never claim full coverage.
The provider's flat zero-volume latest quote at the metadata's exact 15:30
regularMarketTime is a closing mark, not a native interval candle; archive its
timestamp separately. Reject an unfinished current-session end date. Freeze
policy/settings/importer baselines before acquisition and reject mid-run drift
before and after scoring. Use a final offline Yahoo-only rerun after importer
corrections; earlier development trials remain preserved.
Yahoo's 09:15 minute bars can have zero volume with a nonzero range. Preserve
them and the resulting PARTIAL B1 status. In addition to unchanged complete-only
MIS/joint primaries, predeclare separately named allow-gaps sensitivities; never
replace a strict result or fabricate traded volume. CNC retains its real inputs.

Fetch at least 900 calendar days of daily warm-up. Chunk native one-minute
requests into at most seven calendar days. Probe the earliest requested chunk
before bulk intraday requests. Observed Yahoo errors: one-minute request span
at most eight days, retention last 30 days; 15-minute retention last 60 days.
These are observed provider contracts, not promises of future availability.
Preserve errors and actual coverage; do not bypass retention with chunking.

All requested daily modules run on data-valid available names, with requested,
excluded and effective universes frozen before scoring. Missing market indices
block their dependent module. Explicit data exclusions remain visible and make
the result partial; they cannot become a full-universe claim. Invalid rows are
retained in raw evidence, never converted into valid executable bars.

Primary intraday modules keep the exact requested window and fail unavailable
when the provider rejects it. Also predeclare an independently labelled recent
diagnostic inside that same window: by default its final seven calendar days,
never dates outside the requested window. Its availability is separately probed;
never present it as the full quarter. Native recent minute/15-minute data may
support MIS/CNC/Momentum/partial shared-cash studies where daily data cannot.
`--intraday-diagnostic-days 0` disables it.

Reuse of archived Yahoo output must verify source data hashes and remains Yahoo
only; no hidden Production fallback. Freeze new current source manifests on each
rerun. Publish JSON and Markdown with coverage, scope, entries/candidates,
closed/unresolved counts, costs, and cash/exit caveats where supported. Momentum
later-day fallback exits must be counted and labelled unsuitable for live MIS
attribution. No sum of evaluator or partial-book P&L into a system return.

## Acceptance, rollout/rollback and remaining work

Fixtures must prove end-date inclusivity without accepting future extra provider
bars; aware UTC-to-IST conversion; NaN/missing OHLC rejection; raw digest and
snapshot verification; incomplete/provider-failed scopes not becoming zero
profit; no F&O/broker/Production access; isolated module failure; reproducible
same-Yahoo-data execution and immutable publication.

Run the owner-requested Q3 window using Yahoo daily data for all current names,
plus the predeclared intraday diagnostic when available. Exercise a small recent
all-module run before the full universe run. Preserve failed attempts and return
actual results, not only a plan. Record tests, commands, source commit and
immediate documentation/atlas consistency. Outputs are Dev-local and large raw
responses remain ignored. Rollback removes the inert script/configuration without
deleting archived evidence; no live schema/configuration/migration change.

Remaining full-system limits are historical membership/context, broker/manual
admission, evaluator-only lifecycle gaps and prospective qualification. Yahoo
does not erase these by supplying more OHLCV. Later strategy improvement remains
a separate owner discussion.

## Delivered receipt

Source/research commit `df0c379` is Dev-local. All 16 original/final outcomes
agree on the archived Yahoo data; 1,203 raw response digests, both snapshots and
current source/settings/importer hashes verified. Focused suite: 70 passed, one
existing HTTPX deprecation. Compilation/diff checks and 240-module atlas
regeneration passed. Immediately after commit the guide/plan/checklist/results,
deterministic atlas and clean Dev worktree agreed. No push/deployment/Production
action. See [results and integrity receipt](2026-10-03-yahoo-backtest-results.md).
