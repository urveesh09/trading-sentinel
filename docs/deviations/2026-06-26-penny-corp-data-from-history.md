# 2026-06-26 — Penny corp-data fallback: derive from Kite history

## Trigger

Production penny scanner on 2026-06-26 morning: every `penny_scan_complete`
log line carried `accept=0 reject=0 error=0` since 06:43 IST.

`eligible_tickers()` eligibility breakdown on prod (per operator's docker-exec
diagnostic):

```
{'non-EQ': 0, 'bad-price': 21, 'no-tv': 79, 'low-tv': 0,
 'segment-blocked': 0, 'OK': 0}
```

100/100 tickers killed. Universe file dated `2026-06-25` with
`median_traded_value_20d=0` on every ticker.

## Root cause

The 2026-06-25 deviation (`2026-06-25-penny-eligibility-null-tolerance.md`)
made the **promoter** and **PB** gates null-tolerant, but it missed the
**liquidity** gate, which hard-rejects on `tv < PENNY_MIN_20D_TV=500_000`.
Without corp data the universe gets `tv=0`, so the liquidity gate now kills
every ticker the moment the previous deviation saved it.

The corp-data source chain is **completely empty** in production:

1. `KiteClient.get_corporate_actions()` returns `[]` always (Kite Connect
   has no corporate-actions endpoint; the stub at `kite_client.py:450-456`
   says so explicitly).
2. The fallback file `/data/penny_company_data.json` does not exist in the
   container — the refresh job logs `penny_corp_data_missing` and proceeds
   with `corp=[]`.

Combined: `median_traded_value_20d=0` for every ticker, every ticker fails
`if tv < 500_000: continue`, eligible set is `[]`, scanner silently
emits `accept=0 reject=0 error=0` every 30 seconds.

## Decision

Add a third corp-data tier that always runs: derive the four numeric
metrics the universe needs directly from Kite's daily history per ticker.

New helper: `penny_universe.compute_metrics_from_history(kite, symbols)`
returns `{symbol: {median_traded_value_20d, avg_return_20d, vol_20d,
dist_from_52w_low_pct, bars_used}}` for any symbol with >=10 daily bars
in the SQLite cache.

Wired into `refresh_from_kite` **after** the existing kite-corp / fallback
chain, with explicit non-overwrite semantics:

```python
if rec.get(k) in (None, 0) and hm.get(k) is not None:
    rec[k] = hm[k]
```

History-derived values fill missing fields only. A curated corp record
with real `promoter_holding_pct` is never overwritten by history-derived
noise. The precedence order is now:

1. Kite `get_corporate_actions` (when it returns data; today always empty)
2. `penny_company_data.json` fallback file (when present; today absent)
3. **NEW: history-derived metrics** (always runs, fills gaps)

Cost: ~30s for ~100 EQ tickers on day 1 (Kite self-throttles at 3 req/s
via `KiteClient.limiter`). From day 2 onward, the SQLite `ohlcv_cache`
absorbs almost all of it.

## What this does NOT change

- Spec §2.3 promoter / PB gates still hard-reject when data IS present.
  Null-tolerance from the 2026-06-25 deviation is preserved.
- Spec §2.3 liquidity gate is unchanged. The gate still rejects on
  `tv < 500_000`. We are not loosening the gate; we are feeding it real
  data instead of zeros.
- The 100-ticker universe size, the ranker weights, and the eligibility
  threshold values are unchanged.
- The scheduler (08:00 IST cron) is unchanged. The fix is in the job,
  not the schedule.

## Why not just curate `penny_company_data.json`?

The fallback-file path exists precisely for this scenario. But:

1. It is a manual curation step. There is no automation to fill it.
2. The data we'd put in it (`promoter_holding_pct`, `pb_ratio`,
   `is_t2t/asm/gsm`) is not available without a paid fundamental-data
   vendor.
3. Kite's own endpoint for this returns `[]` by design.

The metrics the new helper computes (median tv, 20d momentum, realized
vol, 52w-low distance) are all derivable from Kite's free daily-bars
endpoint. That is the correct place to source them.

## Risk

- History-derived metrics are noisier than audited corp data.
  - `median_traded_value_20d` over 20 bars vs audited 90-day median: a
    single-volume spike can lift the median. Mitigated by using the
    trailing 20-bar median, which is the same window the gate already
    trusts for the ranker's liquidity weight.
  - `vol_20d` is short-window vol. Spec §2.4 ranker uses it with a 10%
    weight. Volatility regime shifts affect rank but not eligibility.
  - `dist_from_52w_low_pct` requires 1y history. New listings (< 1y old)
    get `dist=0`, which biases their rank slightly. Acceptable: spec
    already truncates at 0.95; a 0 just means "no rank contribution
    from low-distance".
- A Kite outage during the 08:00 refresh would now leave the universe
  with `median_traded_value_20d=null` for the affected tickers (not 0).
  Eligibility is null-tolerant for this field today only via the
  2026-06-25 deviation? NO — re-checking: the liquidity gate at
  `penny_universe.py:198` is still a hard `tv < 500_000`. If history
  returns null, `tv = rec.get(...) or 0 = 0`, and the ticker gets
  rejected. **Behavior on Kite-outage day is the same as before
  this fix.** Net effect: in a Kite-outage day the universe writes
  empty/partial data; the scan stays silent. No regression.

## Tests added

- `test_compute_metrics_from_history_returns_four_fields`
- `test_compute_metrics_from_history_skips_empty_df`
- `test_compute_metrics_from_history_handles_fetch_exception`
- `test_compute_metrics_from_history_empty_symbols_list`
- `test_refresh_from_kite_falls_back_to_history_when_corp_empty`
- `test_refresh_from_kite_does_not_overwrite_corp_data_with_history`

Full suite: 862 pass / 3 pre-existing flake failures (cross-test-file
fixture leakage; fail in full run, pass in isolation; unrelated to this
change).

## Smoke test (in-session, dev tree)

```
Helper output for TEST (30 bars, Rs 12, 50k volume/day):
  median_traded_value_20d = Rs 619,367    (above 500K floor)
  avg_return_20d          = 1.0015         (~0.15%/day)
  vol_20d                 = 0.0143         (~1.4%/day)
  dist_from_52w_low_pct   = 0.0866         (8.7% above 52w low)

refresh_from_kite with empty corp + missing fallback file:
  as_of: 2026-06-26
  count: 1
  AAA   pc= 12.00  tv=619,367  ret=1.0015  vol=0.0143  dist52w=0.0866

PennyUniverse.eligible_tickers() returns 1 (was 0).
  AAA eligible (data_quality=DEGRADED:promoter_missing,pb_missing)
```

The `data_quality` flag proves the 2026-06-25 deviation is intact
(promoter + PB still null-tolerant, just tv now sourced from history).