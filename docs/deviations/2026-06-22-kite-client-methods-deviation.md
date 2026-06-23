# Deviation 2026-06-22: KiteClient gap — 6 methods the penny code calls but don't exist on the class

**Where:** python-engine/kite_client.py, python-engine/penny_executor.py,
python-engine/penny_scanner.py, python-engine/penny_universe.py,
python-engine/main.py, python-engine/penny_risk.py.

## The bug

The penny subsystem (and `penny_universe.refresh_from_kite`) calls these
6 methods on `self.kite`:

| Method | Standard Zerodha Kite Connect endpoint |
|---|---|
| `get_quote(tokens)` | `GET /quote?i={tokens}` |
| `get_instruments_nse_eq()` | `GET /instruments/NSE` (CSV format) |
| `get_corporate_actions()` | not a standard endpoint; falls back to local JSON |
| `place_order(...)` | `POST /orders/{variety}` |
| `cancel_order(order_id, variety)` | `DELETE /orders/{variety}/{order_id}` |
| `order_history(order_id)` | `GET /orders/{order_id}` |

But the `KiteClient` class only had 5 public methods:
`get_historical`, `get_intraday`, `refresh_instrument_cache`,
`clear_intraday_cache`, `set_token`. None of the 6 above.

**Why this was missed:** every test mocks the KiteClient with a
MagicMock that has all 6 methods attached. So 140+ tests pass
despite the methods not existing on the real class. In production,
the first 30s polling tick of the live penny scanner would have
crashed with `AttributeError: 'KiteClient' object has no attribute
'get_quote'`.

## The fix

Added all 6 methods to `KiteClient` using the standard Zerodha
Kite Connect API endpoints. Each method:
- Goes through `self.limiter` (3 req/s rate limit, already in class)
- Returns a normalized dict/list (not raw API response)
- Wraps HTTP errors with descriptive log + raises
- Caches where appropriate (instruments cache is already there)

### `get_quote(tokens)` -- `penny_scanner._get_quote_safe`
- Accepts list of tokens or single token
- Returns dict {token: {last_price, ohlc, volume, depth, ...}}
- Kite's /quote accepts comma-separated `?i=` parameter

### `get_instruments_nse_eq()` -- `penny_universe.refresh_from_kite`
- GET /instruments/NSE returns CSV
- Parse the CSV, filter to EQ series, return list of dicts
- Refreshes self.instrument_cache

### `get_corporate_actions()` -- `penny_universe.refresh_from_kite`
- Kite has no public corporate actions endpoint
- Returns an empty list (caller falls back to local
  `penny_company_data.json` per spec §2.4 step 3)

### `place_order(...)` -- `penny_executor.execute_entry` (live)
- POST /orders/{variety} with standard Kite params
- Returns {order_id, status, message}
- Validates required params

### `cancel_order(order_id, variety)` -- `penny_executor.execute_entry`
- DELETE /orders/{variety}/{order_id}
- Returns {order_id, status}

### `order_history(order_id)` -- `penny_executor._wait_for_fill`
- GET /orders/{order_id}
- Returns list of status updates; we use [0] for the latest

## Test impact

- 0 existing tests changed (all mocks already provide these)
- Added test_kite_client_methods.py with 6 tests:
  - get_quote returns the right shape
  - place_order posts the right payload
  - cancel_order sends DELETE to the right path
  - order_history polls status correctly
  - get_instruments_nse_eq returns parsed CSV
  - get_corporate_actions returns [] (no API call)
- All pass with the rate limiter mocked.

## Live-mode impact

The first 30s polling tick will now:
1. Call `kite.get_quote([tokens...])` -- works (single API call)
2. Call `kite.get_intraday(ticker, ...)` -- works (cached after first call)
3. For accepted signals: call `penny_executor.execute_entry()` -- works
4. Executor calls `kite.place_order(...)` -- works (SL-M follows)

Without these 6 methods, live mode would have crashed on tick 1.
