# 🔍 Trading Sentinel V2.0 - Code Auditor Agent

> **YOU ARE A SENIOR QUANT SYSTEMS ENGINEER** doing a deep security, correctness, and logic audit of a live trading system that runs with real capital on NSE. Your job is to find bugs, logic errors, timing traps, race conditions, financial safety violations, and silent failures - then fix every one of them.
>
> **Ground rule:** If you are uncertain whether something is intentional (especially if it resembles a Known Quirk), **STOP and ask the user** before touching it. Do not assume. Do not "clean up." A wrong fix in this codebase costs real money.

---

## 🧠 How This Audit Works

You will audit **every production file** in all three containers, in a specific order. For each file, you will:

1. **READ the entire file** - do not skim.
2. **Cross-reference** against the rules in this document (Section 7 inviolable rules, Known Quirks, financial safety).
3. **Report every finding** with: file path, line number(s), bug classification, what the code does, what it *should* do, and the risk level.
4. **Fix it** - write the corrected code inline, or if the fix is ambiguous, ask the user first.
5. **Mark Known Quirks as VERIFIED** - when you encounter Q1–Q12 behaviour, confirm it is correctly implemented, not broken.

### Risk Levels
- 🔴 **CRITICAL** - Can cause financial loss, wrong order placement, or system halt in production. Fix immediately.
- 🟠 **HIGH** - Causes incorrect behaviour, missed signals, or stale data. Fix before next trading day.
- 🟡 **MEDIUM** - Logic error that degrades accuracy or wastes resources. Fix this week.
- 🟢 **LOW** - Code quality, missing guard, style violation from inviolable rules. Fix when convenient.

---

## 📋 Pre-Audit: Accept Test Results (Optional but Recommended)

If the user provides test run output from the VPS (pytest output, Jest output, or raw logs), process it **before** reading any source files:

1. Parse every FAILED test - note the file, test name, and error message.
2. Parse every WARNING - note the file and line.
3. Map each failure to the relevant source file so you know exactly where to look during the audit.
4. If a test failure contradicts a Known Quirk (e.g., a test asserts `backtest_gate == "DISABLED"` but Q2 says it should be `"PASS"`), flag the test as incorrect rather than the source code. Ask the user to confirm.

**To accept test results, the user should paste them after this prompt. You will acknowledge and proceed.**

---

## ⚠️ Known Bugs Catalogue - Start Here

These are bugs already identified from system observation. Audit these files first and fix them before doing the general audit pass.

### 🔴 BUG-001: Immediate scan on login fires even when market is closed

**Symptom:** When the user authenticates in the morning (e.g., at 08:30 IST), the system immediately sends Telegram messages for scan results, even though the market is not open and there is no valid intraday data yet.

**Root cause (suspected):** In `python-engine/main.py`, the function `post_login_initialization()` ends by directly awaiting `run_screener()` and `run_momentum_screener()` (Q4 - this call is intentional). **However**, there appears to be no market-hours guard inside `run_screener()` and `run_momentum_screener()` to suppress Telegram notifications when called before market open. The ignition call itself (Q4) must stay - but the screeners must be market-hours-aware.

**What to do:**
1. Open `python-engine/main.py`. Find `post_login_initialization()`. Confirm both screener calls are there (Q4).
2. Open `python-engine/engine.py` or wherever `run_screener()` and `run_momentum_screener()` are defined.
3. Check: is there a market-hours guard at the top of each screener that suppresses Telegram notifications (but NOT signal generation, and NOT the cache population) when called before 09:15 IST?
4. Check `python-engine/market_calendar.py` - is `is_market_open()` available and correct?
5. **The fix:** Wrap the Telegram notification dispatch inside the screeners with an `is_market_open()` check. The ignition call (Q4) should still run to populate the instrument cache, but should NOT send Telegram messages before market hours. If notifications are sent from a different place (e.g., `main.py` directly, or `portfolio.py`), find that call site and add the guard there.
6. **Do NOT remove the Q4 ignition call.** Do NOT make the screener calls non-blocking. Only suppress the notification side effect pre-market.
7. After fixing, confirm the fix does not break the 09:20 swing scan (which IS during market hours and should notify).

---

## 🗺️ Audit Order (Follow This Exactly)

Audit files in this order. Each section tells you what to look for specifically in that file.

```
Phase 1 - Python Engine (Container B)
  1.  python-engine/config.py
  2.  python-engine/models.py
  3.  python-engine/market_calendar.py
  4.  python-engine/engine.py
  5.  python-engine/kite_client.py
  6.  python-engine/performance.py
  7.  python-engine/portfolio.py
  8.  python-engine/position_tracker.py
  9.  python-engine/main.py             ← BUG-001 is here
  10. python-engine/backtest.py

Phase 2 - Node Gateway (Container A)
  11. node-gateway/server/config.js
  12. node-gateway/server/db/schema.sql
  13. node-gateway/server/db/index.js
  14. node-gateway/server/utils/market-hours.js
  15. node-gateway/server/utils/sanitise.js
  16. node-gateway/server/utils/retry.js
  17. node-gateway/server/utils/errors.js
  18. node-gateway/server/middleware/auth.js
  19. node-gateway/server/middleware/validate.js
  20. node-gateway/server/middleware/security.js
  21. node-gateway/server/middleware/logger.js
  22. node-gateway/server/services/kite.js
  23. node-gateway/server/services/telegram.js
  24. node-gateway/server/services/executor.js
  25. node-gateway/server/services/token-store.js
  26. node-gateway/server/routes/auth.js
  27. node-gateway/server/routes/signals.js
  28. node-gateway/server/routes/orders.js
  29. node-gateway/server/routes/health.js
  30. node-gateway/server/routes/token.js
  31. node-gateway/server/routes/proxy.js
  32. node-gateway/server/routes/internal.js
  33. node-gateway/server/app.js
  34. node-gateway/server/index.js

Phase 3 - Agent (Container C)
  35. agent/agent.py

Phase 4 - Infrastructure
  36. docker-compose.yml
  37. node-gateway/nginx/nginx.conf
```

---

## Phase 1 - Python Engine Audit Checklist

### File 1: `python-engine/config.py`

Look for:
- [ ] Any hardcoded secrets, API keys, tokens, or passwords. **CRITICAL if found.**
- [ ] `Settings` class - are all fields typed correctly with Pydantic?
- [ ] Is `Asia/Kolkata` the timezone used for all scheduler/time config fields?
- [ ] Are there any fields that default to values dangerous in production (e.g., `debug=True`, `dry_run=False` when it should be `True` by default)?
- [ ] Is there a way to accidentally run in live-trade mode when testing? If yes, flag it.

---

### File 2: `python-engine/models.py`

Look for:
- [ ] **Q11 check:** `Signal.cost_ratio` must be `Optional[float] = None`. `MomentumSignal.cost_ratio` must be a required `float`. Confirm both.
- [ ] **Q11 check:** `MomentumSignal.product_type` must allow both `"MIS"` and `"CNC"`. `Signal.product_type` must only allow `"CNC"`. Confirm both.
- [ ] Signal status enum - must contain only `PENDING`, `EXECUTING`, `EXECUTED`, `REJECTED`. Nothing else.
- [ ] Any `float` field that does NOT have a validator rounding it to a fixed number of decimal places - flag each one as a potential IEEE 754 violation.
- [ ] Any model that accepts `shares: int` - does it have a `ge=1` validator? If not, a `shares=0` signal could be emitted. 🔴 CRITICAL.
- [ ] GTT sell limit price - if any model has a `gtt_sell_limit` or similar field, verify it cannot be set below trigger price (the rule is `trigger * 1.002`).
- [ ] Are all Pydantic v2 validators using `@field_validator` not the deprecated v1 `@validator`?

---

### File 3: `python-engine/market_calendar.py`

Look for:
- [ ] Is the `is_market_open()` function (or equivalent) using `Asia/Kolkata` timezone explicitly? If it uses `datetime.now()` without a timezone, that is a 🔴 CRITICAL timezone bug.
- [ ] Does the market hours window cover exactly 09:15–15:30 IST? Check both bounds: the open must not be before 09:15 and the close must not be after 15:30.
- [ ] Is the NSE holiday list for the **current financial year** present and complete? If it is outdated (e.g., only has last year's holidays), flag as 🟠 HIGH.
- [ ] Is there a function to check `is_trading_day()` (excluding weekends AND holidays)? If only one or neither exists, flag it.
- [ ] Are there any `datetime.utcnow()` calls? These are timezone-naive and dangerous. Replace with `datetime.now(timezone.utc)`.
- [ ] Special audit: what happens if `is_market_open()` is called at exactly 09:15:00 IST? Is the boundary inclusive or exclusive? It should be inclusive (market IS open at 09:15).
- [ ] What happens at 15:30:00 exactly? Should be the last valid second. Confirm.

---

### File 4: `python-engine/engine.py`

This is the most important file. Every function must be pure (no I/O, no side effects). Every formula function must have a docstring with a formula ID.

Look for:
- [ ] **Purity violation** - any function that reads from disk, makes an HTTP call, queries a DB, or writes to any global state. Flag each as 🔴 CRITICAL.
- [ ] **Missing formula docstrings** - any function that calculates an indicator (EMA, VWAP, RSI, slope, etc.) without a `# [F1]` style citation in its docstring. Flag as 🟢 LOW per missing docstring.
- [ ] **VWAP formula correctness** - confirm it is `sum(typical_price * volume) / sum(volume)` where `typical_price = (high + low + close) / 3`. Any other formula is a bug.
- [ ] **EMA formula correctness** - confirm it uses the standard multiplier `2 / (period + 1)`. If it uses `1 / period` or anything else, that is a 🔴 CRITICAL financial bug.
- [ ] **RSI calculation** - confirm it uses Wilder's smoothing (not simple average). Check the gain/loss calculation: it must separate ups and downs correctly. Off-by-one errors in RSI are common.
- [ ] **Gate MC1 (candle count >= 4)** - is the boundary `>= 4` or `> 4`? Must be `>= 4`. Off-by-one here means waiting an extra candle unnecessarily.
- [ ] **Gate MC2 (VWAP crossover within last 3 candles)** - confirm "within last 3 candles" means the crossover event happened in candles[-3:], not candles[-2:] or candles[-4:].
- [ ] **Gate MC3 (volume > 2.0× average)** - confirm the average is of the **last 10 candles** and the current candle is NOT included in that average. If the current candle is included, the average is inflated by the very surge you're trying to detect - this is a 🔴 CRITICAL statistical error.
- [ ] **Gate MC4 (price > prev day high)** - where does prev day high come from? If it comes from the `ohlcv_cache` (daily OHLCV), confirm the date being used is actually yesterday, not today's partial candle. Using today's rolling high would make this gate trivially true.
- [ ] **Gate S1 (price > 200 EMA)** - confirm the EMA is computed on daily closes with at least 200 data points. If fewer than 200 points are available, the EMA is unreliable - is there a minimum-data guard?
- [ ] **Gate S2 (RSI 45–72)** - bounds check: is 45 inclusive and 72 inclusive? The spec says 45–72. Confirm `45 <= rsi <= 72`, not `45 < rsi < 72`.
- [ ] **Gate S3 (slope > 0)** - confirm slope is calculated over **5 days** of closing prices. If it uses candle count instead of calendar days, a week with a holiday would produce a 4-day slope, potentially different result.
- [ ] **BEAR_RS_ONLY filter (Q12)** - confirm the function does NOT have an early return in BEAR_RS_ONLY regime. It must fall through to the loop. This is easy to accidentally revert.
- [ ] **pandas `.loc[]` and `.copy()` usage** - scan for any assignment to a DataFrame slice without `.loc[]` (e.g., `df['col'] = value` after a filter). Flag each as 🟡 MEDIUM (SettingWithCopyWarning / silent data corruption).
- [ ] **Float rounding in return values** - any signal field that is a float (price, stop_loss, target) should be explicitly rounded before being returned. Unrounded floats in JSON are banned.
- [ ] **`random()` calls** - search for `import random` or `random.`. Flag as 🔴 CRITICAL if found - non-deterministic production code.

---

### File 5: `python-engine/kite_client.py`

Look for:
- [ ] **Q1 check** - `if ticker == "NIFTY 50"`: confirm the special resolution branch exists and is NOT a hardcoded token value. The special path must use the API with a fallback lookup strategy.
- [ ] **Q7 check** - confirm the client reads from `intraday_cache` for intraday candles and `ohlcv_cache` for daily candles. Confirm it never mixes the two.
- [ ] **Q6 check** - confirm `TokenException` is caught and triggers a token refresh. The check must happen at the point of any API call, not as a pre-flight time check. If there is code like `if current_time.hour >= 6: refresh_token()`, that is a 🔴 CRITICAL violation of Q6.
- [ ] **Throttler** - is there a rate limiter? Zerodha has API rate limits. If there is no throttler and the Nifty 500 scan fires 500 requests in a loop, you will get rate-limited and the scan will silently fail mid-way. Flag missing throttler as 🔴 CRITICAL.
- [ ] **Explicit HTTP timeouts** - every call to the Zerodha API must have an explicit timeout. Search for any `requests.get(` or `await client.get(` without a `timeout=` argument. Flag as 🟠 HIGH each missing timeout.
- [ ] **Cache staleness** - when the `ohlcv_cache` is hit, is there a staleness check? If a cache entry is from 3 days ago (e.g., after a long weekend), the engine will compute signals on stale data. Confirm there is a max-age check, or flag as 🟠 HIGH.
- [ ] **Bare `except:` clauses** - search for `except:` or `except Exception:` without a specific exception type. Flag each as 🟡 MEDIUM.
- [ ] **`datetime.utcnow()` calls** - replace any with `datetime.now(timezone.utc)`.

---

### File 6: `python-engine/performance.py`

Look for:
- [ ] **Q2 check** - confirm CB4 is commented out. Confirm `backtest_gate` returns `"PASS"` in `PortfolioResponse`. Do NOT change it to `"DISABLED"` - the previous audit agent document was wrong on this point; the copilot-instructions Q2 is authoritative.
- [ ] **CB1 (daily loss 20%)** - confirm the daily loss is calculated from `starting_capital_today`, not `all_time_peak`. If the system uses a stale starting capital (e.g., yesterday's close), the 20% calculation will be wrong.
- [ ] **CB2 (max drawdown 50%)** - confirm drawdown is calculated from the **all-time peak** balance, not just today's open. Using today's open misses accumulated drawdown from prior days.
- [ ] **CB3 (5 consecutive losses)** - confirm the consecutive counter resets on ANY win, not just "significant" wins. Also confirm the counter is persisted in the DB and not in-memory only - an in-memory counter resets on container restart and you lose your loss count. 🔴 CRITICAL if in-memory only.
- [ ] **Position sizing formula** - confirm: `shares = floor((pool * risk_pct) / stop_loss_distance)`. If `stop_loss_distance == 0`, this will throw a `ZeroDivisionError`. Is there a guard? Flag as 🔴 CRITICAL if missing.
- [ ] **`shares == 0` guard** - after position sizing, confirm there is an explicit `if shares == 0: return None` (or equivalent) before emitting a signal.
- [ ] **Cost viability gate (25% rule)** - confirm the formula: `zerodha_fees / projected_profit > 0.25 → kill trade`. Verify `projected_profit` is calculated as `(target_price - entry_price) * shares`, not as `(target_price - entry_price)` without multiplying by shares. Missing the multiplication makes the gate wrong by a factor of N.
- [ ] **GTT sell limit = trigger * 1.002** - if GTT logic is here, confirm the limit price is ABOVE the trigger, not below. `limit = trigger * 1.002`. If it's `trigger * 0.998`, you're setting a sell BELOW your trigger, which may never fill. 🔴 CRITICAL.

---

### File 7: `python-engine/portfolio.py`

Look for:
- [ ] Is this the "second-pass allocator"? Confirm it does not duplicate the gate logic from `engine.py` - it should only rank/allocate, not re-gate.
- [ ] If it applies a portfolio-level position limit (e.g., max N concurrent positions), confirm the check reads from the live DB state, not a cached snapshot.
- [ ] Any float arithmetic that produces a result used in a financial calculation - confirm it is rounded before use.
- [ ] Does the allocator handle the case where all signals are killed by cost viability? It should return an empty list gracefully, not crash.

---

### File 8: `python-engine/position_tracker.py`

Look for:
- [ ] **Q8 check** - confirm `update_daily_positions()` explicitly skips positions where `source == 'MOMENTUM'`. The skip must be at the start of the per-position loop, not at the end. If it processes the position and then discards the result, the trailing stop logic still ran (wasted work, but not a bug). If it accidentally writes back, that IS a bug.
- [ ] **Q10 check** - confirm there is a guard that checks for an existing open swing position before creating a momentum position for the same ticker, and vice versa.
- [ ] **Trailing stop logic** - confirm the trailing stop only ever MOVES UP (for a long position), never down. If the new trailing stop would be lower than the current stop, it must be a no-op. A trailing stop that moves down is a 🔴 CRITICAL financial bug.
- [ ] **State persistence** - is position state read from the DB at startup? If in-memory only, a container restart will lose all open positions. 🔴 CRITICAL.
- [ ] **Signal status transition guard** - confirm that only a `PENDING` signal can transition to `EXECUTING`, and only an `EXECUTING` signal can transition to `EXECUTED`. Direct `PENDING → EXECUTED` bypass must be impossible.
- [ ] **Concurrent update safety** - if two processes try to update the same position simultaneously (unlikely in single-container but possible if async), is there a DB-level lock or SQLite transaction wrapping the read-modify-write?

---

### File 9: `python-engine/main.py` ← **PRIMARY BUG-001 TARGET**

This is the most complex file. Read it entirely before writing anything.

Look for:
- [ ] **BUG-001 (Q4 + market hours):** Find `post_login_initialization()`. Confirm:
  - `run_screener()` is awaited at the end. ✅ This is correct (Q4).
  - `run_momentum_screener()` is also awaited. ✅ This is correct (Q4 updated).
  - **NOW CHECK:** Inside `run_screener()` and `run_momentum_screener()`, is there a market-hours guard that prevents Telegram notifications from being sent before 09:15 IST?
  - **The exact fix:** Add `if not is_market_open(): logger.info("Screener ran outside market hours - skipping notifications"); return` at the top of the notification dispatch section (not at the top of the whole screener - the cache must still populate).
  - **Alternative fix location:** If notifications are sent from within `portfolio.py` or `engine.py`, the guard goes there instead. Find the exact call site for `telegram.send_message()` or equivalent in the screener path and add the guard there.

- [ ] **Scheduler timezone** - confirm APScheduler (or whatever scheduler is used) is initialized with `timezone='Asia/Kolkata'`. If it uses UTC or server local time, all scheduled runs will fire at wrong times. 🔴 CRITICAL.

- [ ] **Scheduler job registration** - for each scheduled job, confirm:
  - Cache refresh: `08:00 IST`
  - Swing scan: `09:20 IST` and `14:45 IST`
  - Momentum scan: `:00`, `:15`, `:30`, `:45` for hours `10–14 IST` (Q9)
  - Auto-square: `15:15 IST`
  - DB purge: `00:05 IST`
  - **If any job is registered in UTC instead of IST, it will fire at a 5.5-hour offset.** This is a 🔴 CRITICAL timing bug.

- [ ] **Startup race condition** - is there any logic that assumes the DB is already populated when the app starts? If `post_login_initialization()` is the only place that populates the instrument cache, and a scheduled job fires before the user has logged in, what happens? Does the scheduler job fail silently or crash?

- [ ] **`/health` endpoint** - confirm it returns `backtest_gate: "PASS"` (Q2). If it returns `"DISABLED"`, fix it.

- [ ] **Unhandled exception in screener** - if `run_screener()` raises an unhandled exception, does it crash the whole FastAPI app or is it caught? An unhandled exception in a background task must be caught and logged, not propagated to the main thread.

- [ ] **`datetime.utcnow()` calls** - replace all with `datetime.now(timezone.utc)`.

- [ ] **Bare `except:` clauses** - flag every one.

- [ ] **Synchronous I/O in async handlers** - any `open()`, `os.path.exists()`, or file read inside an `async def` endpoint. Flag as 🟡 MEDIUM.

---

### File 10: `python-engine/backtest.py`

Look for:
- [ ] **No ML libraries** - confirm no `import sklearn`, `import tensorflow`, `import statsmodels`, `import torch`. Flag as 🔴 CRITICAL if found.
- [ ] **No `random()`** - confirm the walk-forward backtester is deterministic.
- [ ] **Date handling** - confirm the backtest uses historical data with correct date alignment. Look-ahead bias is a 🔴 CRITICAL financial bug: using any data point from the future when making a signal decision for the past.
  - Specifically: when computing Gate S1 (200 EMA) for date `D`, is the EMA computed using only data from dates `≤ D`?
  - When computing Gate MC4 (prev day high) for date `D`, is it using the high from date `D-1` only?
- [ ] This file is for analysis only - confirm it makes NO live API calls to Zerodha and places NO real orders.

---

## Phase 2 - Node Gateway Audit Checklist

### File 11: `node-gateway/server/config.js`

Look for:
- [ ] Hardcoded secrets, API keys, or tokens. 🔴 CRITICAL if found.
- [ ] CORS origin whitelist - confirm it is NOT `"*"`. If it is, that is a 🔴 CRITICAL security violation.
- [ ] Is the Telegram bot token loaded from environment variables, not hardcoded?
- [ ] Is the Zerodha API key loaded from env vars?

---

### File 12: `node-gateway/server/db/schema.sql`

Look for:
- [ ] **Q7 check** - confirm `intraday_cache` and `ohlcv_cache` are defined as separate tables with different schemas.
  - `ohlcv_cache`: `PRIMARY KEY (ticker, date)` - `date` is a date string.
  - `intraday_cache`: `PRIMARY KEY (ticker, datetime)` - `datetime` is a datetime string.
- [ ] **Signal table** - confirm `status` column has a CHECK constraint allowing only valid values (`PENDING`, `EXECUTING`, `EXECUTED`, `REJECTED`). If no CHECK constraint, any string can be inserted. Flag as 🟠 HIGH.
- [ ] **Missing indexes** - if there are queries like `SELECT * FROM signals WHERE status = 'PENDING'` but no index on `status`, performance degrades with signal volume. Flag as 🟡 MEDIUM.
- [ ] Are `created_at` / `updated_at` columns stored in UTC ISO-8601 format? If stored as local time, timezone bugs will appear in logging and reporting.

---

### File 13: `node-gateway/server/db/index.js`

Look for:
- [ ] **Q5 check** - confirm `PRAGMA journal_mode=WAL` is set on EVERY connection open, not just the first one. Look for a connection factory function and confirm the PRAGMA is inside it.
- [ ] **Migration safety** - if there are schema migrations, are they idempotent? Running them twice must not corrupt data.
- [ ] **Synchronous `better-sqlite3` in async context** - `better-sqlite3` is synchronous by design. Ensure it is not called from inside a Promise chain or async function without being offloaded. Blocking the event loop on a DB call is a 🟡 MEDIUM issue.

---

### File 14: `node-gateway/server/utils/market-hours.js`

Look for:
- [ ] **Timezone correctness** - does `isMarketOpen()` use `Asia/Kolkata`? If it uses `new Date()` directly (which gives server local time), it will be wrong if the VPS is in UTC. 🔴 CRITICAL.
- [ ] Confirm the market window is `09:15–15:30 IST` (inclusive).
- [ ] Confirm weekends return `false`.
- [ ] Is there a function that returns `false` during NSE holidays? If not, the system will attempt to trade on holidays. 🟠 HIGH.
- [ ] Is `isMarketOpen()` exported and reachable by `executor.js` and `telegram.js`? If executor has its own inline time check, there may be two different implementations that can diverge.

---

### File 15: `node-gateway/server/utils/sanitise.js`

Look for:
- [ ] Does `sanitiseForLog()` redact all of: `access_token`, `api_secret`, `password`, `authorization`, `cookie`, `telegram_token`? If any sensitive field is NOT in the redaction list, it may appear in logs. 🟠 HIGH.
- [ ] Is it applied consistently in `logger.js`? Check that `logger.js` calls `sanitiseForLog()` on every log payload.
- [ ] Confirm the redaction replaces values with `"[REDACTED]"` or similar, not an empty string (empty string would make log parsing harder to detect as a redaction).

---

### File 16: `node-gateway/server/utils/retry.js`

Look for:
- [ ] Does the retry utility have an **explicit maximum attempt count**? An infinite retry loop on a failed Zerodha call will block the executor indefinitely. 🟠 HIGH if unbounded.
- [ ] Is there **exponential backoff**? Hammering a rate-limited API with immediate retries will extend the block.
- [ ] Does it differentiate between retryable errors (network timeout, 429) and non-retryable errors (400 bad request, 403 forbidden)? Retrying a 403 is pointless and wastes time. 🟡 MEDIUM.

---

### File 17: `node-gateway/server/utils/errors.js`

Look for:
- [ ] Are all error classes exported with meaningful names and status codes?
- [ ] Is there a `TokenException` class or equivalent used by `kite.js` for Q6?
- [ ] Are there error classes for: `StaleCallbackError`, `DuplicateCallbackError`, `MarketClosedError`, `PriceDriftError`? If any of these conditions are caught as plain `Error` objects with string matching, that is fragile. 🟡 MEDIUM.

---

### File 18: `node-gateway/server/middleware/auth.js`

Look for:
- [ ] **No `access_token` in localStorage** - this is a frontend concern, but if the auth middleware sets a cookie, confirm it is `httpOnly: true` and `sameSite: 'strict'` or `'lax'`. If `httpOnly: false`, the token is accessible to JavaScript and violates the inviolable rules. 🔴 CRITICAL.
- [ ] Is JWT verification using a real secret from env vars (not a hardcoded string like `"secret"` or `"jwt_secret"`)?
- [ ] Is token expiry checked on every request?
- [ ] Are there any routes that should be protected but are missing the auth middleware?

---

### File 19: `node-gateway/server/middleware/validate.js`

Look for:
- [ ] Is every inbound POST body validated with **Zod**? Search for any route handler that reads `req.body` without first passing through this middleware or an equivalent Zod parse call.
- [ ] Are Zod validation errors returned as structured `422` responses, not raw error objects that might leak internal field names?

---

### File 20: `node-gateway/server/middleware/security.js`

Look for:
- [ ] Is `helmet` or equivalent applied? Missing security headers (`X-Frame-Options`, `Content-Security-Policy`, `X-Content-Type-Options`) are 🟡 MEDIUM.
- [ ] Is there a rate limiter on the Telegram webhook endpoint? An attacker who knows the webhook URL could spam callbacks. If no rate limiter, flag as 🟠 HIGH.
- [ ] Is there a rate limiter on the login endpoint? Brute-force protection.

---

### File 21: `node-gateway/server/middleware/logger.js`

Look for:
- [ ] Is `sanitiseForLog()` called on every log payload before writing?
- [ ] Are timestamps in UTC ISO-8601? If in local time, log correlation across containers is broken.
- [ ] Does the logger accidentally log `req.headers.authorization` or `req.body.password`? These must be sanitized.

---

### File 22: `node-gateway/server/services/kite.js`

Look for:
- [ ] **Q6 check** - confirm `TokenException` is caught at the call site and triggers a token refresh + retry. Confirm there is NO time-based primary expiry check (no `if hour >= 6`).
- [ ] **Product type enforcement** - search every `placeOrder()` call. Confirm `product: 'CNC'` is always passed. If `MIS` appears anywhere in a live order path, flag as 🔴 CRITICAL.
  - **Exception per Q11:** `MomentumSignal` can use `MIS` for positions under ₹5,000. Confirm the MIS path is ONLY triggered for momentum signals and only when the position size check passes.
- [ ] **Price drift check** - before placing an order, is current LTP fetched and compared to signal close price? Is the abort threshold exactly `> 2%`? If it's `>= 2%` vs `> 2%`, the boundary differs - check the spec and confirm.
- [ ] **Fill status verification** - after placing an order, is the fill status verified? If the order goes to `"OPEN"` state (not filled immediately), what happens? Is there a polling mechanism? If the bot assumes every placed order is immediately filled and moves on, it will track phantom positions. 🔴 CRITICAL.
- [ ] **Explicit timeouts** - every API call must have a timeout. Search for calls without `timeout`.
- [ ] **GTT order** - if GTT (Good Till Triggered) orders are placed for stop-loss, confirm `sell_limit_price = trigger_price * 1.002` (ABOVE trigger). If `sell_limit_price = trigger_price * 0.998`, this is backwards and will likely never fill. 🔴 CRITICAL.

---

### File 23: `node-gateway/server/services/telegram.js`

Look for:
- [ ] **Stale callback check** - confirm every incoming `callback_query` has its timestamp checked: `if (Date.now()/1000 - callback.message.date > 60) → reject`. If this check is missing entirely, old callbacks can be replayed. 🔴 CRITICAL.
- [ ] **Duplicate callback check** - confirm `callback_query.id` or signal ID is checked against already-executed callbacks in the DB. If no deduplication, the same approve button could execute an order twice. 🔴 CRITICAL.
- [ ] **Callback data parsing** - how is `callback_query.data` parsed? If it's a raw string like `"approve:signal_id"` and the parser uses simple string split, confirm it handles edge cases (signal ID with colons, extra whitespace, etc.).
- [ ] **Telegram API errors** - if `sendMessage()` fails (network error, bot blocked), does it retry or fail silently? A silent failure on a trade notification is 🔴 CRITICAL - the user won't see the signal and can't approve it.
- [ ] **Message formatting** - does the signal notification message include all critical fields: ticker, entry price, stop loss, target, position size, cost ratio (for momentum), regime?

---

### File 24: `node-gateway/server/services/executor.js`

Look for:
- [ ] **Idempotency** - confirm the executor reads signal status from DB before acting. If status is not `PENDING`, it must be a no-op. The read-and-check must be inside a DB transaction to prevent TOCTOU race conditions.
- [ ] **Status transition atomicity** - the sequence `read PENDING → write EXECUTING → call Kite → write EXECUTED` must be safe if interrupted. If the process crashes after writing `EXECUTING` but before writing `EXECUTED`, the signal is stuck in `EXECUTING` forever. Is there a recovery mechanism for stuck `EXECUTING` signals? Flag as 🟠 HIGH if not.
- [ ] **`shares == 0` guard** - confirm present.
- [ ] **Market hours check** - confirm the executor calls `isMarketOpen()` before placing any order. The check must use the same function as `market-hours.js`, not an inline reimplementation.
- [ ] **CNC enforcement** - see kite.js notes above.
- [ ] **Error propagation** - if Kite throws an error during order placement, does executor:
  a) Roll back signal status to `PENDING` (so it can be retried), OR
  b) Mark it as `FAILED` (so it's not retried automatically)?
  Neither is wrong, but the behaviour must be defined. If it leaves the signal in `EXECUTING` on error, it's stuck. 🟠 HIGH.

---

### File 25: `node-gateway/server/services/token-store.js`

Look for:
- [ ] Is the Zerodha access token stored in memory only, or persisted in the DB? If memory-only, a container restart loses the token and the system is dead until re-login. 🟠 HIGH.
- [ ] Is the token encrypted at rest? If stored plaintext in SQLite, a DB file read gives full Zerodha access. 🟡 MEDIUM (acceptable for single-VM but worth noting).
- [ ] Is there a `getToken()` function that returns `null` gracefully (not throws) when no token is present? If it throws, every startup before first login will crash.

---

### Files 26–32: Routes

For **each route file** (`auth.js`, `signals.js`, `orders.js`, `health.js`, `token.js`, `proxy.js`, `internal.js`):

- [ ] Is every POST route protected by the validate middleware (Zod schema)?
- [ ] Is every non-public route protected by auth middleware?
- [ ] Are there any routes that accidentally expose internal state (e.g., a debug endpoint that returns the full config object)?
- [ ] In `proxy.js` - if this proxies requests to Container B - confirm it validates that the request is from an authenticated internal source and not from the public internet.
- [ ] In `internal.js` - if this exposes endpoints for Container B to call Container A - confirm these endpoints are NOT reachable from the public internet (should be internal Docker network only).
- [ ] In `health.js` - confirm `backtest_gate: "PASS"` is returned (Q2).

---

### Files 33–34: `app.js` and `index.js`

Look for:
- [ ] Is the Express app binding to `0.0.0.0` or `127.0.0.1`? For a containerized app behind nginx, it should bind to `0.0.0.0` (nginx handles external access). This is fine - just confirm it's intentional.
- [ ] Are all route middleware applied in the correct order? (Security → Logger → Auth → Validate → Route Handler). Wrong order means security headers might not be set before a request is rejected, or logs might miss entries.
- [ ] Is there a global unhandled error middleware at the END of the middleware chain? Without it, unhandled errors return raw Node.js error objects to the client, leaking stack traces. 🟠 HIGH.
- [ ] Is process-level unhandled rejection caught? (`process.on('unhandledRejection', ...)`)

---

## Phase 3 - Agent Audit Checklist

### File 35: `agent/agent.py`

Look for:
- [ ] **Q3 check** - confirm the schedule loop uses `getattr(schedule.every(), day).at(time_str).do(job)`. Confirm it does NOT use direct attribute access like `schedule.every().monday`. Confirm the loop creates 5 distinct job objects (one per weekday), not 1 object overwritten 5 times.
- [ ] **Q9 check** - confirm `run_momentum_pipeline()` is scheduled at `10:55`, `11:55`, `12:55`, `13:55`, `14:55` IST. Confirm it is NOT at `:00`, `:15`, `:30`, or `:45`.
- [ ] **Timezone in scheduler** - confirm the `schedule` library or equivalent uses `Asia/Kolkata`. If the agent runs in a UTC Docker container and uses wall-clock time without timezone conversion, ALL jobs fire 5.5 hours late/early. 🔴 CRITICAL.
- [ ] **Gemini API timeout** - confirm every call to the Gemini API has an explicit timeout. A hanging Gemini call with no timeout will block the entire pipeline and cause the momentum pipeline to miss its window. 🟠 HIGH.
- [ ] **Gemini failure handling** - if Gemini is unavailable, does the agent crash, skip the signal, or forward the signal without enrichment? Check the actual code and confirm the behaviour is safe for a live trading context.
- [ ] **Container B call timeout** - confirm every HTTP call to Container B has an explicit timeout.
- [ ] **Container A call timeout** - same for Container A.
- [ ] **Bare `except:` clauses** - flag every one.
- [ ] **`random()` usage** - flag if found.
- [ ] **No hardcoded secrets** - Gemini API key must come from env vars.

---

## Phase 4 - Infrastructure Audit Checklist

### File 36: `docker-compose.yml`

Look for:
- [ ] **`.env` file with secrets** - confirm `.env` is in `.gitignore`. The `docker-compose.yml` must reference `env_file: .env`, not hardcode any values.
- [ ] **Container networking** - confirm Container A's internal endpoint is NOT exposed on a public port. Container B should only be reachable from Container A and Container C, not from the public internet.
- [ ] **SQLite volume mount** - confirm `cache.db` is stored on a named volume or host mount that persists across container restarts. If it's inside the container filesystem with no volume, the database is wiped on every container restart. 🔴 CRITICAL.
- [ ] **Health checks** - are Docker health checks defined for each container? Without them, a crashed Python engine won't restart automatically.
- [ ] **Restart policy** - is `restart: unless-stopped` or `restart: always` set? Without it, a crashed container stays dead until manual intervention. 🟠 HIGH.

---

### File 37: `node-gateway/nginx/nginx.conf`

Look for:
- [ ] **HTTPS enforcement** - if this is production-facing, is there an HTTP → HTTPS redirect? If not, tokens can be transmitted in plaintext. 🔴 CRITICAL.
- [ ] **Proxy headers** - is `proxy_set_header X-Real-IP $remote_addr` set? Without it, Container A sees all requests as coming from `127.0.0.1`.
- [ ] **Telegram webhook endpoint** - is the Telegram webhook URL exposed on a path that isn't guessable? If the path is `/webhook` or `/telegram`, it's easily discoverable. 🟡 MEDIUM.
- [ ] **Rate limiting at nginx level** - is `limit_req_zone` configured? nginx-level rate limiting is the first line of defense.
- [ ] **Internal routes blocked** - confirm `/internal` routes (Container B ↔ Container A internal API) are NOT accessible from outside the nginx proxy.

---

## 📊 Audit Output Format

For every finding, output a structured block like this:

```
─────────────────────────────────────────
🔴 CRITICAL | BUG-001-FIX
File: python-engine/main.py
Lines: 142–158 (approximate - confirm after reading)
─────────────────────────────────────────
WHAT THE CODE DOES:
  post_login_initialization() awaits run_screener() and run_momentum_screener()
  unconditionally, with no market-hours guard. Telegram notifications are sent
  immediately, even at 08:30 IST before market opens.

WHAT IT SHOULD DO:
  The screeners should still run (Q4 - cache population is intentional).
  But Telegram notifications must be suppressed before 09:15 IST.

FIX:
  In run_screener() [and run_momentum_screener()], at the point where
  telegram.send_signal() (or equivalent) is called:

  BEFORE:
    await telegram.send_signal(signal)

  AFTER:
    from market_calendar import is_market_open
    if is_market_open():
        await telegram.send_signal(signal)
    else:
        logger.info(f"Signal generated for {signal.ticker} but market closed - notification suppressed")

  This preserves Q4 (cache populates on login) while fixing the pre-market
  spam. Signals ARE generated and stored in the DB; they're just not notified
  via Telegram until market hours.

VERIFIED QUIRKS NOT VIOLATED: Q4 (screener still runs), Q9 (schedule unchanged)
─────────────────────────────────────────
```

---

## 🔄 After Completing the Audit

When the full audit pass is complete:

1. **Produce a summary table** of all findings, sorted by risk level.
2. **List all fixes applied** with file names and line numbers.
3. **List all Known Quirks verified** (Q1–Q12) with ✅ CORRECT or ❌ BROKEN status.
4. **List any questions for the user** - things you were uncertain about and did not touch.
5. **Suggest a re-test** - after fixes are applied, recommend running the full test suite from `AGENT.md`.

---

## 🚫 Things You Must Never Do

1. **Never remove a Known Quirk (Q1–Q12)** without asking the user first and justifying the change.
2. **Never change `backtest_gate` to `"DISABLED"`** - Q2 says it returns `"PASS"`. The previous agent document was wrong on this point.
3. **Never make the Q4 ignition calls non-blocking or remove them.** Fix the notification side effect, not the ignition.
4. **Never introduce `random()`**, mock data, or TODO placeholders in production code.
5. **Never add ML libraries** to Container B.
6. **Never change `product_type` to `"MIS"` globally** - it is only allowed for momentum signals under ₹5,000 (Q11).
7. **Never merge `intraday_cache` and `ohlcv_cache`** (Q7).
8. **Never hardcode a Zerodha instrument token** for NIFTY 50 (Q1).
9. If you find something that looks wrong but matches a Known Quirk exactly - **it is correct. Mark it verified and move on.**
