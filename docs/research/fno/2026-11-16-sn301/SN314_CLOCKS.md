# SN314: the Dec 7, 2026 clock change against the code (Nov 16, 2026)

**Source:** NSE, "FAQs for CM and FO for CAS 2.0" (updated Nov 6, 2026; circulars NSE/CMTR/77355 and NSE/FAOP/77356), downloaded Nov 16.

## What changes on Monday, Dec 7, 2026

| Item | Until Dec 4 (current) | From Dec 7 |
|---|---|---|
| Equity derivatives close (index and stock F&O) | 15:40 | **15:45** on every day |
| Expiring index contracts on their expiry day | trade to the close | **stop at 15:30** (the other contracts continue to 15:45) |
| Cash: continuous trading of stocks in the closing auction (CAS) | to 15:15 | **to 15:30** |
| Cash closing auction | 15:15–15:35 | **15:30–15:45**: reference price 15:30–15:31, order entry 15:31–15:36, limit orders only 15:36–15:40 (random close), matching 15:40–15:45; transition 15:45–15:50; post-close 15:50–16:00 |
| Futures price band 15:30–15:45 | — | ±3% of the futures reference price (VWAP 15:15–15:30) |
| Index final settlement price (expiry) | constituents' VWAP of the last 30 minutes of continuous trading | **unchanged** (15:00–15:30) |
| Trade modification end | — | 16:15 |

## What the code assumes (Dev = Production `c6cbceb1` for these files)

**Breaks or misses minutes from Dec 7 (the session is 5 minutes longer, and expiry-day contracts stop 10 minutes earlier):**

- `market_calendar.py`:
  - `DERIVATIVES_CLOSE_TIME = 15:40`, so derivatives are CLOSED from 15:40, though they trade to 15:45;
  - the cash CAS sub-windows are the Aug 3 regime (15:15–15:35), but from Dec 7 the auction is 15:30–15:45;
  - `CAS_PHASE1_UNTIL = Dec 7` already ends the 15:15 rule for momentum, which is correct, but nothing describes the new auction.
- **The expiry cutoff is 15:40:**
  - `fno_chain.py` and `hedge_strategies.py`: "options settle at the 15:40 derivatives close";
  - `hedge_advisory.py`: the session close for its time-left reading.
  - From Dec 7 an expiring NIFTY/SENSEX contract cannot be traded after 15:30.
- **The partner companion's windows end at 15:40:**
  - `partner_fill_capture.py`, `partner_orchestrator.py`;
  - `partner_broker_sync.py` and `partner_trade_paths.py` (`CLOSE_MIN`).
  - A partner trade between 15:40 and 15:45 would fall outside them.
- **Hard-coded 15:40 elsewhere:**
  - `scheduler_setup.py` (the F&O tick runs to 15:39), `research_quote_collector.py` (quotes to 15:40), `expiry_paper.py` (`SESSION_END`);
  - `lifecycle_receipts.py`, `ops_metrics.py`, `ops_watchdogs.py`, `token_lifecycle.py`, `daily_bootstrap.py`, `scheduler_telemetry.py`, `fno_proving_week.py`.
  - These are watchdog and receipt windows that would miss 5 minutes.
- **The tick recorder** (`tick_recorder.py`) stops at 15:41, so it would not record 15:41–15:45.

**Unaffected:**
- **SN Gold v5:** flat at 15:10, failsafe 15:15.
- **WK-H:**
  - it enters at 15:15;
  - on expiry day its hedge closes at 15:24 from the 15:00–15:25 quotes, before the new 15:30 stop;
  - settlement is unchanged.
- **The expiry-day book:** its put exits are at 15:14.
- **The SN300a forward window:** decisions 09:30–14:30; SN298's holiday exit is at 15:10. `fwd2.py` tags sessions from Dec 7 separately.

## What to do

A runtime change (named session facts by date, so 15:40 until Dec 4 and 15:45 from Dec 7, plus the expiry-day 15:30 cutoff for expiring index contracts) is a separate Dev slice. It needs tests and a deploy before Dec 7, **on the owner's word**. This round did not change runtime code.
