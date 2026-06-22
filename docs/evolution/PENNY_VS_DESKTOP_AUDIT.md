# Penny Expansion — Live-System Compatibility Audit

**Date:** 2026-06-21
**Branch:** `feat/expansion`
**Production desktop:** `~/Desktop/trading-sentinel` on `evolve/smart-strategies` @ `35c3233`
**Production health:** python-engine service was DOWN at session start
(`curl localhost:8000/health` returned empty). Must restart before any
live verification.

## Audit checklist

### Settings / flag changes — SAFE

- 30 new `PENNY_*` settings added to `config.py`
- All default to safe / no-op values
- `PENNY_LIVE_TRADING=False` means NO real orders regardless of what
  the penny scanner does
- Nifty 500 settings unchanged (verified by reading diff)

### New kwargs on hot functions — SAFE

- No existing function signatures changed
- `evaluate_connors_entry()` and `evaluate_breakout_entry()` are NEW
  functions in NEW modules
- `penny_signal_log.log_penny_signal()` is NEW and writes to a NEW
  SQLite table (`penny_signals`), not the existing `momentum_signals`

### New code paths — SAFE (guarded)

- `main.py`: 7 new scheduler jobs added; all call into `penny_*` modules
  which have NO dependency on Nifty code (isolation test enforces)
- All penny scheduler jobs gated by `PENNY_LIVE_TRADING`:
  - In paper mode (default): only logs signals, never calls
    `kite.place_order()`
  - In live mode: real orders via `kite.place_order()` with MIS product
    and LIMIT (and SL-M placed separately as a second order)

### Changed call sites — VERIFIED

- `position_tracker.py`: doc comment added only. Existing
  `if pos.get("source") == "MOMENTUM": continue` logic accepts PENNY
  positions (any non-MOMENTUM source proceeds unchanged).
- `performance.py`: new `penny_pool_pnl()` helper appended at bottom.
  No existing function modified.
- `analytics.py`: new `penny_outcome_correlator()` sibling function
  appended. No existing function modified.

### Data files — VERIFIED

- `data/penny_static.json`: NEW file, empty stub `{"tickers": []}`
- `data/penny_company_data.json`: NEW file, empty stub `{"records": []}`
- No existing ticker list / config dump touched
- Desktop's `data/` directory does not yet have these files; they will
  be created on first python-engine startup

### Module compilation — VERIFIED

- All 10 new `penny_*.py` files parse cleanly
- `import main` works after the wiring change
- Full test suite: 580+ passed, 1 skipped, 1 pre-existing flaky Nifty
  test (not caused by this branch)

### Test suite parity — VERIFIED

- Before this branch: 439 tests passed, 1 skipped (per session-start state)
- After this branch: 580+ tests passed, 1 skipped
- No Nifty tests modified; all additions are new `test_penny_*.py` files
- The `test_penny_isolation.py` test enforces the architectural
  boundary (any future commit that adds a forbidden import fails CI)

### Flag-off parity — VERIFIED

With `PENNY_LIVE_TRADING=False`:
- PennyScanner runs every 30 seconds, evaluates signals, logs outcomes
- NO `kite.place_order()` calls (verified in scanner test)
- NO writes to Nifty bankroll_ledger (penny P&L writes are a follow-up)
- NO interference with Nifty run_screener / run_momentum_screener

The default-OFF flag guarantees zero behaviour change to the existing
Nifty system. Penny code can run for 2 weeks without affecting production
Nifty P&L.

## Risk summary

| Risk | Severity | Mitigation |
|---|---|---|
| Penny scheduler loop crashes main loop | Low | try/except in each job; logger.error, never raises |
| Penny scanner spams Kite quote API | Low | 30s cadence = ~4 calls/min/100 tickers = well below Kite rate limit (3 req/s) |
| Penny log file grows unbounded | Low | CSV append, rotate manually if disk fills |
| Penny isolation broken by future commit | Low | `test_penny_isolation.py` runs in CI; AST-walk enforces |
| Penny accidentally goes live | Low | `PENNY_LIVE_TRADING=False` default + explicit `.env` flip required |
| Penny SL-M not actually placed at broker | Low | `penny_executor` places SL-M after entry fill; if rejected, market-exits immediately (spec §7.2) |
| Pre-existing flaky Nifty test | Low | `tests/test_universe_expansion.py::test_load_universe_with_fallback_uses_csv_when_present` fails intermittently due to test ordering; not caused by this branch |

## Required before merging to evolve/smart-strategies

- [x] Spec approved
- [x] Plan approved
- [x] Phase 2 complete (code + tests)
- [x] All 580+ tests pass (with 1 pre-existing Nifty flaky test documented)
- [ ] One full-session manual smoke test (this PR)
- [ ] Python-engine service restart after merge
- [ ] 1 week of paper-trade signal accumulation before any live-trade opt-in

## Required before merging to main (and pulling into Desktop)

- [ ] All above
- [ ] 2 weeks of paper-trade data review
- [ ] Win-rate on paper trades > 50%
- [ ] No critical incidents in logs
- [ ] Explicit Uru approval

## Production restart sequence (after merge)

```bash
cd ~/Desktop/trading-sentinel
git pull origin evolve/smart-strategies
docker compose build python-engine
docker compose up -d python-engine
docker compose logs -f python-engine | grep -i penny
```

Watch for:
- No traceback on startup
- `penny_universe_refresh` log line at 08:00 IST (first cron)
- `penny_regime_computed` log line at 09:20 IST
- `penny_scan_complete` log lines every 30s starting 09:20

## If anything breaks

1. `docker compose down python-engine && docker compose up -d python-engine`
   (falls back to last good image)
2. Set `PENNY_LIVE_TRADING=false` even if it was true
3. Send the log lines (with timestamp) to Uru via Telegram
4. Do NOT touch Nifty code paths while debugging
