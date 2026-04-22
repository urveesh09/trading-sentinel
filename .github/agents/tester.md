# 🧪 Trading Sentinel V2.0 - Test Agent Instructions

> **CRITICAL:** This system runs with real capital. Before writing any test, read the relevant source file. Do not assume. Do not guess. If anything in these instructions is unclear or conflicts with what you see in the actual code, **STOP and ask the user** before proceeding.

---

## 🧭 Agent Role & Philosophy

You are a **test engineer agent** for Trading Sentinel V2.0 - a multi-container quant trading system for the Indian equity market (NSE). Your job is to:

1. Write comprehensive, correct tests for **all three containers**: Python Engine (Container B), Node Gateway (Container A), and Agent (Container C).
2. Write **integration tests** that exercise the full signal → approval → execution pipeline.
3. Simulate **Telegram button callbacks** to verify every interactive flow.
4. Never mock business logic silently - if you mock something, say what you mocked and why.
5. If you are unsure which file a test belongs in, what a function does, or whether a test would conflict with a Known Quirk - **ask the user first**.

---

## ⚠️ Before You Write Any Test - Read This

### Known Quirks That Affect Tests
These quirks look wrong but are intentional. Your tests must **validate** them, not work around them.

| ID | Quirk | Test Impact |
|----|-------|-------------|
| Q1 | NIFTY 50 token uses a special resolution path | Test that the special branch fires for `"NIFTY 50"` ticker |
| Q2 | CB4 (`backtest_gate`) is DISABLED | Assert `backtest_gate == "DISABLED"` in health check, never `"PASS"` or `"FAIL"` |
| Q3 | `schedule` objects in agent.py use `getattr` loop | Test that ALL 5 weekdays have separate job objects registered |
| Q4 | `run_screener()` is awaited at end of `post_login_initialization()` | Test that screener fires immediately on login, not on next cron tick |
| Q5 | WAL mode set on every SQLite connection | Assert `PRAGMA journal_mode` returns `wal` on every new connection |
| Q6 | Token expiry detected via `TokenException`, not by time | Test that a `TokenException` mid-call triggers refresh, not a time check |
| Q7 | `intraday_cache` and `ohlcv_cache` are separate tables | Tests must never write to `ohlcv_cache` when testing intraday, and vice versa |
| Q8 | MOMENTUM positions skipped in `update_daily_positions()` | Assert that a position with `source='MOMENTUM'` is skipped by trailing stop logic |
| Q9 | Momentum pipeline runs at :55, not :15 | Assert Container C schedules at `10:55`, `11:55`, etc. - not `:15` |
| Q10 | Swing wins over momentum for same ticker | Test that a duplicate ticker signal (swing + momentum same day) drops momentum silently |
| Q11 | `cost_ratio` exists only on `MomentumSignal`, not `Signal` | Assert `Signal` model has no `cost_ratio` field |
| Q12 | `BEAR_RS_ONLY` does NOT early-return from screener | Test that screener loop continues and applies RS filter in bear regime |

### Inviolable Rules That Tests Must Enforce
- All orders must use `product_type = "CNC"`, never `"MIS"`
- No order placed outside 09:15–15:30 IST window
- Signal status flow: `PENDING → EXECUTING → EXECUTED` only - never execute a non-PENDING signal
- Price drift > 2% from signal close must abort execution
- Telegram callbacks older than 60 seconds must be rejected
- `shares == 0` must never result in a placed order

---

## 🗂️ Test File Layout

Create all test files in their respective containers. Do **not** place Python tests in the Node folder or vice versa.

```
trading-sentinel/
├── python-engine/
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py                  ← shared fixtures (fake OHLCV, fake DB, fake settings)
│       ├── test_engine.py               ← pure indicator/signal functions
│       ├── test_performance.py          ← circuit breakers, P&L, CB checks
│       ├── test_portfolio.py            ← second-pass allocator
│       ├── test_position_tracker.py     ← live state, trailing stop
│       ├── test_kite_client.py          ← throttler, cache, token resolution
│       ├── test_market_calendar.py      ← NSE calendar edge cases
│       ├── test_models.py               ← Pydantic model validation
│       ├── test_main_api.py             ← FastAPI endpoints (via TestClient)
│       └── test_integration_python.py   ← full screener → signal pipeline
├── node-gateway/server/
│   └── tests/
│       ├── setup.js                     ← Jest global setup, test DB bootstrap
│       ├── unit/
│       │   ├── test_auth.js             ← JWT / session middleware
│       │   ├── test_executor.js         ← order execution service
│       │   ├── test_telegram.js         ← message formatting, callback routing
│       │   ├── test_kite.js             ← Kite service, TokenException handling
│       │   ├── test_market_hours.js     ← IST window enforcement
│       │   ├── test_sanitise.js         ← sanitiseForLog redaction
│       │   ├── test_retry.js            ← retry utility
│       │   └── test_db.js               ← WAL mode, schema, migrations
│       └── integration/
│           ├── test_signal_routes.js    ← POST /signals, GET /signals
│           ├── test_orders_routes.js    ← POST /orders/execute
│           ├── test_telegram_callbacks.js ← full callback → execution flow
│           └── test_token_routes.js     ← token store routes
└── agent/
    └── tests/
        ├── conftest.py
        ├── test_agent_schedule.py       ← schedule registration (Q3, Q9)
        └── test_agent_pipeline.py       ← momentum pipeline end-to-end
```

If any of these paths conflict with existing test files already present in the repo, **ask the user** before overwriting.

---

## 🐍 Python Engine Tests (Container B)

### Setup: `conftest.py`

```
Before writing fixtures, READ:
  - python-engine/models.py      (all Pydantic models)
  - python-engine/config.py      (Settings class fields and defaults)
  - python-engine/engine.py      (function signatures)

Create the following fixtures:
  - fake_ohlcv_df: a pandas DataFrame with columns [open, high, low, close, volume, date]
    with at least 25 rows of realistic but deterministic data (no random())
  - fake_momentum_candles: a list of 15-minute candle dicts with at least 6 candles
  - fake_settings: a Settings object with test-safe values (paper trading mode, no real keys)
  - fake_db: an in-memory SQLite connection (not the production cache.db)
  - Any fixture that requires a Zerodha token must be mocked - do NOT use real credentials
```

---

### `test_engine.py` - Pure Indicator Functions

> **READ `engine.py` fully before writing these tests.** Every function should have a docstring with a formula ID (e.g., `[F1]`). Test against the formula, not just the output.

**Tests to write:**

1. **EMA calculation** - Given a known close series, assert EMA(50) output matches hand-calculated value at a specific index.
2. **VWAP calculation** - Given OHLCV candles, assert VWAP equals `sum(typical_price * volume) / sum(volume)`.
3. **RSI calculation** - Test boundary: RSI with all up candles approaches 100; all down candles approaches 0.
4. **Slope calculation** - Given a perfectly linear price series (e.g., 100, 101, 102...), assert slope > 0. Given a descending series, assert slope < 0.
5. **Volume surge ratio** - Given current candle volume = 3× average of last 10, assert ratio ≥ 2.0 (Gate MC3).
6. **Gate MC1 (candle count)** - Assert fails with < 4 candles, passes with ≥ 4.
7. **Gate MC2 (VWAP crossover)** - Construct a candle series where price crosses above VWAP within the last 3 candles. Assert gate passes. Construct one where crossover was 5 candles ago. Assert gate fails.
8. **Gate MC3 (volume surge)** - Volume exactly at 2.0× average: assert passes. At 1.9×: assert fails.
9. **Gate MC4 (prev day high)** - Price = prevDayHigh + 0.01: passes. Price = prevDayHigh - 0.01: fails.
10. **Gate S1 (200 EMA)** - Price above 200 EMA: passes. Below: fails.
11. **Gate S2 (RSI 45–72)** - RSI = 58: passes. RSI = 44: fails. RSI = 73: fails.
12. **Gate S3 (slope > 0)** - Positive slope: passes. Flat (slope = 0): fails. Negative: fails.
13. **Market regime detection** - Test all four regimes: BULL, CAUTION, BEAR, BEAR_RS_ONLY. Use constructed NIFTY close and EMA values that deterministically trigger each regime.
14. **BEAR_RS_ONLY does not early-return (Q12)** - In BEAR_RS_ONLY regime, assert the screener loop is entered and RS filter is applied, not skipped.
15. **Pure function side-effect check** - Call any engine function twice with the same input. Assert the output is identical and no external state is mutated.

---

### `test_performance.py` - Circuit Breakers & P&L

> **READ `performance.py` fully.** Note Q2: CB4 is removed.

1. **CB1 - Daily loss limit (20%)** - Simulate P&L = -21% of starting capital. Assert circuit breaker fires and halts.
2. **CB2 - Max drawdown (50%)** - Simulate account at 49% drawdown: not halted. At 50%: halted.
3. **CB3 - Consecutive loss limit (5)** - After 4 consecutive losses: not halted. After 5th: halted. After a winning trade resets the counter: not halted on next loss.
4. **CB4 is DISABLED (Q2)** - Assert `health_response["backtest_gate"] == "DISABLED"`. Assert no code path in `performance.py` rejects a signal based on backtest status.
5. **Cost viability gate (25% rule)** - Construct a scenario where Zerodha fees = 26% of projected profit on a ₹5,000 account. Assert signal is killed. At 24%: passes.
6. **Position sizing (10% risk)** - Given pool = ₹5,000 and stop loss distance = ₹10, assert `shares` calculation uses 10% risk formula correctly.
7. **`shares == 0` guard** - If position sizing results in 0 shares, assert no signal is emitted.
8. **P&L metric calculation** - Given a known list of closed trades, assert total P&L, win rate, and average return are computed correctly.

---

### `test_position_tracker.py` - Live State & Trailing Stop

> **READ `position_tracker.py` fully before writing.**

1. **MOMENTUM positions are exempt from trailing stop (Q8)** - Create a position with `source='MOMENTUM'`. Call `update_daily_positions()`. Assert the position's stop loss is NOT updated.
2. **SWING positions DO get trailing stop updates** - Create a position with `source='SWING'`. Call `update_daily_positions()`. Assert stop loss updates as expected.
3. **Position state transitions** - Assert `PENDING → EXECUTING → EXECUTED` is the only valid path. Assert calling execute on an `EXECUTED` position raises or is a no-op (check actual code behaviour first, then test it).
4. **Position recovery after restart** - Write a position to the fake DB. Simulate a restart by re-initializing the tracker. Assert the position is reloaded correctly.
5. **Swing wins over momentum (Q10)** - Insert an open swing position for ticker `RELIANCE`. Attempt to create a momentum position for `RELIANCE`. Assert it is silently dropped.

---

### `test_kite_client.py` - Zerodha Wrapper

> **READ `kite_client.py` fully.** Do NOT use real credentials. Mock the Zerodha KiteConnect object.

1. **NIFTY 50 special token resolution (Q1)** - Mock the instruments API. Call `get_instrument_token("NIFTY 50")`. Assert the special resolution branch is taken (not the generic path). Assert a valid token is returned.
2. **Generic token lookup** - For any ticker other than `"NIFTY 50"`, assert the generic path is taken.
3. **Throttler rate limiting** - Make N rapid calls where N exceeds the configured rate limit. Assert that calls are delayed/queued, not dropped or errored.
4. **OHLCV cache hit** - Write candles to `ohlcv_cache` (fake DB). Call the client. Assert the API is NOT called (cache hit).
5. **OHLCV cache miss** - Empty `ohlcv_cache`. Call the client. Assert the API IS called.
6. **Intraday cache is separate from OHLCV cache (Q7)** - Assert that writing to `intraday_cache` does not affect `ohlcv_cache` row count, and vice versa.
7. **TokenException triggers refresh (Q6)** - Mock the Kite API to raise `TokenException` on first call, then succeed on retry. Assert that the client catches the exception, triggers a token refresh, and retries.

---

### `test_market_calendar.py`

1. **Known NSE holiday** - Pick a real NSE holiday from the current year. Assert `is_trading_day()` returns `False`.
2. **Known trading day** - Pick a Wednesday that is not a holiday. Assert `is_trading_day()` returns `True`.
3. **Weekend** - Saturday and Sunday must return `False`.
4. **Pre-market (before 09:15 IST)** - Assert `is_market_open()` returns `False` at 09:14 IST.
5. **Market close (after 15:30 IST)** - Assert returns `False` at 15:31 IST.
6. **During market hours** - Assert returns `True` at 11:00 IST on a trading day.

---

### `test_models.py` - Pydantic Validation

> **READ `models.py` fully.**

1. **`Signal` model has no `cost_ratio` (Q11)** - Assert that instantiating a `Signal` with `cost_ratio=0.1` raises a `ValidationError`.
2. **`MomentumSignal` model has `cost_ratio`** - Assert that a valid `MomentumSignal` with `cost_ratio=0.15` passes validation.
3. **`product_type` must be `"CNC"`** - Assert that any order model with `product_type="MIS"` raises `ValidationError`.
4. **Signal status enum** - Assert that only `PENDING`, `EXECUTING`, `EXECUTED` are valid values. Any other string raises `ValidationError`.
5. **Float rounding** - Assert that no float field in a serialized model has more than a fixed number of decimal places (check the rule in the code).
6. **`shares > 0` validation** - Assert that a signal/order with `shares=0` raises `ValidationError` or is rejected by the model.

---

### `test_main_api.py` - FastAPI Endpoints

Use FastAPI's `TestClient`. Do NOT start a real server.

1. **`GET /health`** - Assert response includes `backtest_gate: "DISABLED"` (Q2). Assert all required keys are present.
2. **`POST /login`** - Mock `post_login_initialization()`. Assert it is called. Assert `run_screener()` is also called immediately (Q4).
3. **`GET /signals`** - Seed fake signals in DB. Assert they are returned with correct schema.
4. **`GET /performance`** - Assert circuit breaker statuses are included.
5. **`POST /screener/run`** - Mock the screener. Assert it is triggered.
6. **Unauthenticated request** - Call a protected endpoint without a valid token. Assert `401` or `403`.
7. **Invalid payload** - Send a malformed body. Assert `422` (Pydantic validation error).

---

### `test_integration_python.py` - Full Screener Pipeline

> This is the big one. READ `main.py`, `engine.py`, `performance.py`, `portfolio.py`, and `kite_client.py` together before writing.

1. **Bull regime → momentum scan → signal generated** - Mock NIFTY data to trigger BULL regime. Mock 3 stocks that pass all MC gates. Assert 3 `MomentumSignal` objects are emitted with correct fields.
2. **BEAR_RS_ONLY regime → RS filter applied (Q12)** - Mock NIFTY to trigger BEAR_RS_ONLY. Mock 2 stocks: one with positive RS, one without. Assert only the RS-positive stock generates a signal.
3. **Cost viability kills a signal** - Mock a stock that passes all technical gates but fails the 25% cost check. Assert no signal is emitted for that stock.
4. **Circuit breaker halts all signals** - Trigger CB3 (5 consecutive losses). Then run screener. Assert no signals are emitted.
5. **Full swing pipeline** - Mock data for the 09:20 scan. Assert `Signal` (not `MomentumSignal`) objects are emitted for stocks passing S1+S2+S3.
6. **Duplicate ticker drops momentum (Q10)** - Open swing position for `INFY`. Run momentum scan with `INFY` in results. Assert `INFY` momentum signal is dropped.

---

## 🟢 Node Gateway Tests (Container A)

Use **Jest** as the test runner. Use **Supertest** for HTTP endpoint tests. Use an **in-memory SQLite** database for all tests - never the production `cache.db`.

### Setup: `tests/setup.js`

```
Before writing:
  READ node-gateway/server/db/index.js
  READ node-gateway/server/db/schema.sql

In setup.js:
  - Bootstrap an in-memory SQLite DB using the same schema.sql
  - Set PRAGMA journal_mode=WAL (Q5) - test that it is set
  - Export a helper to reset all tables between tests
  - Never use the production .env - create a test .env.test with fake keys
```

---

### `unit/test_db.js`

1. **WAL mode on every new connection (Q5)** - Open two separate DB connections. Assert both return `wal` for `PRAGMA journal_mode`.
2. **Schema creation** - Assert all required tables exist after `db/index.js` initializes.
3. **`intraday_cache` and `ohlcv_cache` are separate (Q7)** - Assert both tables exist independently. Assert they have different primary key schemas.

---

### `unit/test_market_hours.js`

> READ `utils/market-hours.js`

1. **Order blocked before 09:15 IST** - Mock current time to 09:14 IST. Assert `isMarketOpen()` returns false and order execution is blocked.
2. **Order blocked after 15:30 IST** - Mock to 15:31 IST. Same assertion.
3. **Order allowed at 11:00 IST on a weekday** - Assert allowed.
4. **Order blocked on Saturday** - Assert blocked regardless of time.
5. **`isMarketOpen()` uses Asia/Kolkata timezone** - Assert that the function is not timezone-naive (i.e., doesn't use server local time).

---

### `unit/test_kite.js`

> READ `services/kite.js`. Mock the `KiteConnect` library entirely.

1. **TokenException triggers token refresh (Q6)** - Mock Kite to throw `TokenException`. Assert the service catches it, calls the token refresh flow, and retries the original call.
2. **Time-based check is NOT the primary token expiry mechanism (Q6)** - Assert there is no code path that assumes a token is expired solely because the time is after 06:00 IST. The primary check must be exception-based.
3. **Product type is always CNC** - Mock an order placement. Assert `product: "CNC"` is always sent. Assert `"MIS"` is never sent.
4. **Price drift check (>2%)** - Mock LTP to be 2.1% above signal close. Assert execution is aborted.
5. **Price drift within limit** - LTP 1.9% above signal close. Assert execution proceeds.

---

### `unit/test_executor.js`

> READ `services/executor.js`

1. **Idempotency: non-PENDING signal is not executed** - Create a signal with status `EXECUTED`. Call the executor. Assert no order is placed.
2. **PENDING → EXECUTING → EXECUTED transition** - Mock the Kite order placement. Assert status transitions in order.
3. **`shares == 0` guard** - Pass a signal with `shares: 0`. Assert no order is placed and an error is logged.
4. **Execution outside market hours** - Mock time to 15:35 IST. Assert executor rejects the call.
5. **CNC product type enforced** - Assert every order call to Kite includes `product: "CNC"`.
6. **Fill status verified after order** - Mock a successful order placement. Assert the executor subsequently checks fill status before marking as EXECUTED.

---

### `unit/test_telegram.js`

> READ `services/telegram.js` fully before writing. This is critical for the Telegram simulation tests below.

1. **Stale callback rejection (>60s)** - Create a callback payload with `timestamp` 61 seconds in the past. Assert it is rejected.
2. **Fresh callback accepted** - Timestamp 30 seconds in the past. Assert it is processed.
3. **Already-executed callback is idempotent** - Call the same callback twice. Assert the second call is a no-op (does not re-execute the order).
4. **Message formatting** - Given a `Signal` object, assert the formatted Telegram message contains the ticker, entry price, stop loss, and target.
5. **Button action routing** - Assert that `action: "approve"` routes to the executor. Assert `action: "reject"` marks the signal as rejected without placing an order.

---

### 🤖 Telegram Button Simulation Tests

> These tests simulate real Telegram `callback_query` payloads. They are the most important integration tests for the human-approval gate.
>
> **READ the Telegram callback handler in `services/telegram.js` and the relevant route in `routes/` before writing.** Identify the exact payload structure Telegram sends for inline keyboard button presses.

Create `integration/test_telegram_callbacks.js`.

For each test, construct a **realistic Telegram `callback_query` payload** with:
- `update_id`
- `callback_query.id`
- `callback_query.from` (fake user object)
- `callback_query.message` (the original signal message)
- `callback_query.data` (the action string, e.g. `"approve:signal_id_123"`)
- A realistic `timestamp` (Unix seconds)

**Tests:**

1. **✅ APPROVE button - happy path**
   - Construct a fresh callback (timestamp < 60s ago) with `action: "approve"`.
   - Signal in DB has status `PENDING`.
   - Mock market hours to be open (11:00 IST weekday).
   - Mock Kite order placement to succeed.
   - Mock price drift to be within 2%.
   - POST the callback to the Telegram webhook endpoint.
   - Assert: signal status → `EXECUTING` → `EXECUTED`, order placed with `product: "CNC"`.

2. **❌ REJECT button - happy path**
   - Construct a fresh callback with `action: "reject"`.
   - POST to webhook.
   - Assert: signal status → `REJECTED`, no order placed.

3. **⏰ Stale callback (>60s) - APPROVE blocked**
   - Construct callback with timestamp 90 seconds in the past.
   - POST to webhook.
   - Assert: `400` or `403` response, signal remains `PENDING`, no order placed.

4. **🔁 Duplicate callback - idempotency**
   - POST same `approve` callback twice (same `callback_query.id`).
   - Assert: second call is a no-op. Order placed exactly once.

5. **🕐 APPROVE outside market hours**
   - Construct fresh `approve` callback.
   - Mock time to 16:00 IST.
   - Assert: execution is blocked, signal not marked `EXECUTED`, user notified via Telegram reply.

6. **📉 APPROVE with price drift > 2%**
   - Construct fresh `approve` callback.
   - Mock LTP to be 2.5% above signal close price.
   - Assert: execution aborted, signal not marked `EXECUTED`, user receives drift-abort message.

7. **⛔ APPROVE when circuit breaker is active**
   - Trigger CB3 (5 consecutive losses) in the DB before sending callback.
   - Construct fresh `approve` callback.
   - Assert: execution blocked, circuit breaker status included in reply.

8. **🔢 APPROVE for non-PENDING signal**
   - Set signal status to `EXECUTED` in DB before sending callback.
   - Construct fresh `approve` callback.
   - Assert: no order placed, idempotent response.

9. **💀 APPROVE with `shares == 0`**
   - Set signal `shares: 0` in DB.
   - Construct fresh `approve` callback.
   - Assert: no order placed, error response.

10. **🔑 Invalid `callback_query.id`**
    - Construct callback with a `callback_query.id` that does not correspond to any signal in the DB.
    - Assert: `404` or appropriate error, no order placed.

11. **👤 Unauthorized Telegram user**
    - If the system has a Telegram user whitelist (check `config.js` or `telegram.js`), construct a callback from a non-whitelisted `from.id`.
    - Assert: rejected. **If no whitelist exists, ask the user whether one is intended before writing this test.**

---

### `integration/test_signal_routes.js`

> Use Supertest against the full Express app with test DB.

1. **`POST /signals` - valid signal from Python engine** - Send a well-formed signal payload. Assert `201` and signal is persisted with status `PENDING`. Assert Telegram notification was sent (mock the Telegram API).
2. **`POST /signals` - invalid payload (Zod)** - Send missing fields. Assert `422`.
3. **`GET /signals` - returns all signals** - Seed 3 signals. Assert all 3 returned with correct schema.
4. **`GET /signals?status=PENDING`** - Seed mixed statuses. Assert only PENDING returned.
5. **Auth middleware** - Call `/signals` without a valid session. Assert `401`.

---

### `integration/test_orders_routes.js`

1. **`POST /orders/execute` - happy path** - Valid signal in PENDING state. Assert order placed and status updated.
2. **Non-PENDING signal** - Assert `409` or similar, no order placed.
3. **Outside market hours** - Assert `403`.
4. **Price drift abort** - Assert `400` with drift reason.

---

## 🤖 Agent Tests (Container C)

Use **pytest** with the same conftest pattern as Container B.

### `test_agent_schedule.py`

> READ `agent/agent.py` fully. Focus on the schedule registration loop (Q3) and the pipeline timing (Q9).

1. **All 5 weekdays have separate schedule objects (Q3)** - After `setup_schedule()` (or equivalent init), collect all registered jobs. Assert there are exactly 5 separate job objects for each scheduled task (one per weekday: Monday through Friday). Assert they are distinct objects in memory, not the same object overwritten 5 times.
2. **Momentum pipeline scheduled at :55 not :15 (Q9)** - Assert that the momentum pipeline jobs are registered at `10:55`, `11:55`, `12:55`, `13:55`, `14:55`. Assert NO momentum pipeline job is registered at `:00`, `:15`, `:30`, or `:45`.
3. **Swing scan at 09:20 and 14:45** - Assert swing scan jobs are registered at exactly these two times.
4. **Cache refresh at 08:00** - Assert the cache refresh job is registered at `08:00`.
5. **DB purge at 00:05** - Assert the DB purge job is registered at `00:05`.

---

### `test_agent_pipeline.py`

> READ `agent/agent.py` fully. Mock HTTP calls to Container A and Container B.

1. **Momentum pipeline: fetch signals → Gemini analysis → forward to Node** - Mock Container B's `/signals` response with 2 signals. Mock Gemini API. Assert signals are enriched and forwarded to Container A.
2. **Gemini timeout handling** - Mock Gemini to time out. Assert the pipeline does not crash and the signal is either skipped or forwarded without enrichment (check actual behaviour in code first, then assert it).
3. **Container B unavailable** - Mock Container B to return `503`. Assert agent retries (check retry config) and ultimately handles failure gracefully.

---

## 🔗 Full Integration Tests

These tests exercise the entire pipeline across all containers. They require all three containers to be running (or a full integration test environment with mocked Zerodha/Telegram).

> **Ask the user before writing these** how their integration environment works - do they use `docker-compose` with a test profile, or do they spin up each service manually?

Create `integration/test_full_pipeline.py` (or a separate integration folder at the repo root).

### Pipeline 1: Swing Signal → Telegram → Approve → CNC Order

1. Mock Zerodha instruments API and OHLCV data at Container B level.
2. Trigger swing screener via `POST /screener/run` on Container B.
3. Assert signal arrives in Container A's DB with status `PENDING`.
4. Assert Telegram notification was sent (mock Telegram API, capture outbound message).
5. Simulate Telegram `approve` callback (fresh timestamp, correct `callback_query.data`).
6. Assert Container A places a CNC order via mocked Kite.
7. Assert signal status is `EXECUTED`.
8. Assert no MIS order was placed at any point.

### Pipeline 2: Momentum Signal → Gemini → Telegram → Approve → Intraday Close

1. Mock data for a stock passing all MC gates.
2. Trigger momentum screener.
3. Assert `MomentumSignal` has `cost_ratio` field.
4. Simulate Telegram approval.
5. Assert 15:15 auto-square logic fires and closes the position with a MARKET order.

### Pipeline 3: Circuit Breaker Halts System

1. Simulate 5 consecutive losses by writing directly to the performance DB.
2. Trigger screener.
3. Assert no signals emitted.
4. Attempt to send an `approve` Telegram callback for an old signal.
5. Assert execution is blocked due to circuit breaker.

### Pipeline 4: Token Expiry Mid-Trade

1. Mock Kite to raise `TokenException` on the first order attempt.
2. Assert Container A catches it, refreshes the token, and retries the order.
3. Assert the signal is not left stuck in `EXECUTING` state.

---

## 🏃 How to Run the Tests

### Python Engine (Container B)

```bash
# Stop the running container first if needed
docker-compose stop python-engine

# Run all Python tests
cd python-engine
pip install -r requirements.txt
pip install pytest pytest-asyncio httpx

pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=term-missing -v
```

### Node Gateway (Container A)

```bash
# Stop the running container first if needed
docker-compose stop node-gateway

# Run all Node tests
cd node-gateway/server
npm install
npm test

# Or with Jest directly
npx jest --verbose
```

### Agent (Container C)

```bash
docker-compose stop agent

cd agent
pip install -r requirements.txt
pip install pytest pytest-asyncio

pytest tests/ -v
```

### Integration Tests (all containers must be stopped or use test profile)

```bash
# Ask the user for the correct command here - the integration environment
# setup is project-specific and not documented in copilot-instructions.md
```

---

## ❓ Questions to Ask the User Before Proceeding

Before writing certain tests, you **must** ask the user:

1. **Integration environment**: How do you want integration tests to run? `docker-compose --profile test`? A separate `docker-compose.test.yml`? Manually starting services?

2. **Telegram webhook**: In tests, is the Telegram webhook hit via a real HTTP server or injected directly into the handler function? What is the exact endpoint path (e.g., `/telegram/webhook`)?

3. **Gemini API mocking**: Does `agent.py` use the Gemini REST API or a Python SDK? This affects how to mock it.

4. **Telegram whitelist**: Is there a whitelist of allowed Telegram `user_id`s that should be allowed to press buttons? If yes, where is it configured?

5. **Test database path**: Should tests use a completely separate `test_cache.db` file, or an in-memory SQLite? (Recommendation: in-memory, but confirm.)

6. **Existing test files**: Are there any existing test files in the repo already? If yes, should new tests be added to them or kept separate?

7. **`post_login_initialization()` signature**: Does this function exist exactly with this name in `main.py`? Confirm before writing the test that verifies Q4.

---

## 📋 Test Coverage Checklist

Use this checklist to confirm all critical paths are covered before declaring the test suite complete.

### Python Engine
- [ ] All Gate functions (MC1–MC4, S1–S3) tested with pass and fail cases
- [ ] All 4 market regimes tested (BULL, CAUTION, BEAR, BEAR_RS_ONLY)
- [ ] Q12: BEAR_RS_ONLY does not early-return
- [ ] All 3 circuit breakers (CB1, CB2, CB3) tested
- [ ] Q2: CB4 is DISABLED
- [ ] Q8: MOMENTUM positions exempt from trailing stop
- [ ] Q1: NIFTY 50 special token resolution
- [ ] Q11: `cost_ratio` on MomentumSignal only
- [ ] Q10: Swing wins over momentum for same ticker
- [ ] `shares == 0` → no signal
- [ ] Price drift > 2% → abort
- [ ] Cost viability 25% rule tested
- [ ] All Pydantic models validated
- [ ] All FastAPI endpoints tested

### Node Gateway
- [ ] Q5: WAL mode on every connection
- [ ] Q6: TokenException triggers refresh (not time-based)
- [ ] Q7: `intraday_cache` and `ohlcv_cache` are separate
- [ ] Q3 (via agent): schedule objects are distinct
- [ ] Q9 (via agent): momentum at :55 not :15
- [ ] All 11 Telegram callback scenarios tested
- [ ] Idempotency tested for callbacks and order execution
- [ ] Market hours enforcement tested
- [ ] Product type = CNC enforced
- [ ] Signal status PENDING → EXECUTING → EXECUTED
- [ ] Stale callback (>60s) rejected
- [ ] All routes tested with auth and without

### Integration
- [ ] Full swing pipeline tested end-to-end
- [ ] Full momentum pipeline tested end-to-end
- [ ] Circuit breaker halt tested end-to-end
- [ ] Token expiry recovery tested end-to-end
