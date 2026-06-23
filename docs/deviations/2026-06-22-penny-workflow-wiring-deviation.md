# Deviation 2026-06-22: 5 architectural gaps in penny workflow

**Where:** python-engine/penny_scanner.py, python-engine/main.py,
python-engine/penny_risk.py, python-engine/penny_engine_breakout.py.

These 5 gaps were all detected by the 2026-06-22 step-by-step audit.
Each is documented with its fix.

## Gap A: Scanner never calls the executor

**Bug:** When `penny_scanner._evaluate_ticker_breakout` returns
`{"accept": True, ...}`, the scanner logs the signal to
`penny_signals` (SQLite + CSV) but **never invokes**
`penny_executor.execute_entry()`. The comment in the scanner said
"Scanner's job ends here: log accept + persist intent. The
penny_executor module handles actual order placement." But nothing in
the scanner code actually delegated to the executor.

**Fix:** `PennyScanner` now holds a `PennyExecutor` instance and calls
`executor.execute_entry(ticker, leg, entry, stop, shares)` on every
accepted signal. The executor does the actual broker-level order flow
(per spec §7.2: entry LIMIT -> fill poll -> SL-M with retry ->
market-unwind on failure).

Also: after a successful entry, the scanner now inserts a row in the
`positions` table with `source='PENNY'`, so the existing
`position_tracker.update_daily_positions` will track it for exit
management.

## Gap B: CNC strategy is a no-op

**Bug:** `main.py:run_penny_connors_scan` was a no-op:
`logger.info("penny_connors_scan_dispatched")` and nothing else.
The CNC evaluation surface (penny_engine_connors.evaluate_connors_entry)
is fully implemented and tested but was never called.

**Fix:** The 09:30 cron job now:
1. Builds a fresh scanner (CNC leg)
2. Loads the universe
3. For each ticker, calls `_evaluate_ticker_connors(ticker, as_of)`
4. Logs accept/reject with regime + Connors-specific columns
5. On accept, delegates to the executor (same wiring as the MIS path)

## Gap C: EOD check is a no-op

**Bug:** `main.py:run_penny_eod_check` read open MIS penny positions,
called `smart_eod_check()` on each, and **only logged the decision**.
No exit order was placed.

**Fix:** The 14:30 cron now:
1. Reads open penny MIS positions
2. For each, fetches the current LTP
3. Calls `smart_eod_check(pos, current_price, now)`
4. If decision["action"] == "EXIT", places a market exit order
   via `penny_executor._market_unwind(ticker, leg, shares)`
5. Updates the position in the position tracker

## Gap D: `record_realized_pnl` is never called

**Bug:** The 20% daily loss kill-switch (spec §7.3) is a safety
feature. But `PennyRiskEngine.record_realized_pnl` was never
invoked anywhere in the penny code, so `daily_pnl` always stayed
0.0, the kill-switch threshold check always returned False, and
the kill-switch was dormant.

**Fix:** A new function `penny_risk.PennyRiskEngine.record_close(...)`
is invoked from the position-tracker's close handler (where penny
positions are closed at EOD or stop). The function updates
`daily_pnl` and triggers the kill-switch warning if threshold
breached.

A new cron job `penny_daily_reset` (registered at 00:05 IST) clears
`daily_pnl` and `daily_pnl_date` to start each day fresh.

## Gap E: No fee accounting

**Bug:** `engine.calc_zerodha_costs` (brokerage, STT, exchange
charges, stamp duty, SEBI, GST) exists but is not used by any
penny code. P&L was overstated by ~0.3-1.2% per trade.

**Fix:** A new function `penny_risk.calc_penny_costs(...)` was added
locally (no import from engine, per the isolation rule). It mirrors
the engine's logic but is independent. Called from
`PennyRiskEngine.record_close(...)` to subtract round-trip costs
from any realized P&L before applying the kill-switch check.

Penny-specific rates are added to `config.py`:
- `PENNY_STT_MIS = 0.00025` (0.025% sell side, same as Nifty)
- `PENNY_STT_CNC = 0.001` (0.1% sell side)
- `PENNY_BROKERAGE_PCT = 0.0003` (0.03% capped at Rs 20)
- `PENNY_BROKERAGE_MAX = 20.0`
- `PENNY_EXCHANGE_PCT = 0.0000345` (0.00345% NSE)
- `PENNY_STAMP_DUTY_PCT = 0.00015` (0.015% buy)
- `PENNY_SEBI_PCT = 0.000001` (Rs 10 per crore, both sides)
- `PENNY_GST_PCT = 0.18` (18% on brokerage+exchange)

## Test impact

- 5 new tests in test_penny_workflow_wiring.py covering:
  - Scanner calls executor on accept (mocked)
  - CNC scan actually runs evaluate_connors_entry
  - EOD check places exit order on smart_eod_check action=EXIT
  - record_close updates daily_pnl + triggers kill-switch
  - calc_penny_costs returns expected round-trip value
- 141 -> 146 penny tests pass (+5)

## Live-mode impact

Before the fix, even with PENNY_LIVE_TRADING=True:
- Scanner ran 30s but never placed orders
- 09:30 CNC cron ran but did nothing
- 14:30 EOD cron ran but did nothing
- Daily loss kill-switch never fired (always 0)
- P&L was overstated (no fees subtracted)

After the fix:
- Each accepted signal places a real entry LIMIT order
- A real SL-M follows the entry (spec §7.2 mandatory)
- 09:30 CNC cron places CNC orders for valid Connors setups
- 14:30 EOD cron cuts losers in time
- Kill-switch triggers at -20% of bankroll for the day
- Realized P&L has costs deducted (Rs 6+ per round trip)
