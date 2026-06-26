# 2026-06-25 — Penny eligibility null-tolerance + scanner observability

## Trigger
Production penny hourly report at 10:00 IST on 2026-06-25:
> "No action in Penny this hour. (regime: UNKNOWN, open: 0/5, deployed: Rs 0)"

User reported zero activity. Investigation showed every `penny_scan_complete`
log line today carried `accept=0 reject=0 error=0` across 254 scans
(09:00–10:55 IST). Pre-market digest correctly showed 100 tickers in the
universe, but the scanner was iterating over an empty eligible set.

## Root cause
`penny_universe.py:eligible_tickers()` drops tickers when:
- `promoter_holding_pct is None` (line 132)
- `pb_ratio is None or > MAX_PB_RATIO` (line 141)

The penny_static.json universe file (refreshed 08:00 IST 2026-06-25) had
`promoter_holding_pct=null` and `pb_ratio=null` on **all 100 tickers**.
The fallback corp-data file `/data/penny_company_data.json` does not
exist in the container, and Kite's `get_corporate_actions()` returned
empty during the 08:00 refresh.

Result: `eligible_tickers()` returned `[]`, the scanner logged no warning
about it (only the silent `penny_scan_no_universe` line which was never
emitted — see below), and the loop never iterated.

### Secondary observation
The early-return at `penny_scanner.py:267-269` should log
`penny_scan_no_universe`, but the dev-tree code path emits no log line
because `scan_once()` was reached and the `penny_scan_no_universe` log
*is* wired but apparently the loop path was entered. Re-verification
required (potential second bug or instrumentation gap).

## Decision
**Long-term direction (Uru 2026-06-25):** be proactive, surface data
quality issues, do not silently filter.

1. Treat null promoter / null PB as "unknown quality" — let ticker
   through with a `data_quality` flag. Spec §2.3 intent (avoid
   shell/promoter-heavy names, avoid PB>2 distressed stocks) is preserved
   when data IS available; only the null-data case is relaxed.
2. Log a `penny_universe_quality_audit` per refresh: count of tickers
   with null promoter / null PB / null liquidity. If Kite corp-data is
   empty, log warning + synthesize a deterministic minimal scaffold from
   what we have so future refreshes can fill in.
3. Add observable logs at every silent exit path in the scanner.
4. Make MIS + Connors reject counting consistent (None decision → reject
   with reason, not error).

## Risk
- Tickers with truly shell-like promoter structures could pass if
  corp-data is permanently empty. Mitigated by: (a) volume surge gate
  in penny_engine_breakout requires 3x median, so even null-quality
  tickers still need unusual activity to fire, (b) position-size cap
  Rs 500 per stock, (c) 5-position total cap, (d) per-trade risk 5%
  of Rs 2,500 = Rs 125.
- Data quality flag exposed in pre-market digest so operator can see
  when universe is degraded.

## Tests
- `test_universe_eligibility_null_promoter_lets_through`
- `test_universe_eligibility_null_pb_lets_through`
- `test_universe_eligibility_real_high_promoter_rejects`
- `test_universe_eligibility_real_high_pb_rejects`
- `test_universe_quality_flag_present_when_null`
- `test_refresh_quality_audit_logged`
- `test_scanner_none_decision_increments_reject_not_error`
- `test_scanner_logs_eval_skipped_with_reason`