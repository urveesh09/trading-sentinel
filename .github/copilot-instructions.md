# 🛡️ Trading Sentinel V2.0: Comprehensive Strategy Documentation

## 1. System Architecture: The "Triple-Lock" Framework
The Trading Sentinel is a high-frequency quant engine designed for the Indian Equity Market (NSE). It operates as a coordinated multi-container ecosystem:

*   **Node Gateway (Container A):** The **Executioner**. Handles Zerodha Kite Connect authentication, real-time order routing, and the Telegram Notification Bridge.
*   **Python Engine (Container B):** The **Brain**. Performs complex vector math on OHLCV data, calculates technical indicators, and enforces "The Gates."
*   **SQLite Persistence:** The **Memory**. A resilient `cache.db` that tracks instrument tokens, historical OHLCV data, and live trade states to ensure system recovery after a restart.

---

## 2. The Master Gate: Market Regime Detection
Before any stock is scanned, the engine evaluates the "Market Weather" using the **NIFTY 50** index.

*   **BULL Mode:** (Nifty > 50 EMA). Permissive mode. Bot hunts for breakouts.
*   **CAUTION Mode:** (Nifty < 50 EMA * 1.02). Risk per trade is halved.
*   **BEAR Mode:** (Nifty < 50 EMA). Defensive mode. The bot switches to **Relative Strength (RS) Only**—it will only buy stocks that are moving up while the market is moving down.
*   **Justification:** Trading with the trend increases the probability of success. Fighting a bear market is the #1 cause of account blowups.

---

## 3. High-Octane Momentum Gates (Intraday)
*Scheduled every 15 minutes (:00, :15, :30, :45) between 10:00 and 15:00 IST.*

### Gate MC1: Temporal Baseline (Candle Count >= 4)
*   **Rule:** The stock must have at least four 15-minute candles.
*   **Justification:** The first 60 minutes of the Indian market are "The Amateur Hour"—extreme volatility with no direction. Waiting 1 hour allows institutional intent to become visible.

### Gate MC2: The Institutional Value Gate (VWAP Crossover)
*   **Rule:** Price must have crossed from below VWAP to above VWAP within the last 3 candles.
*   **Justification:** VWAP (Volume Weighted Average Price) is the benchmark used by big banks and hedge funds. If the price is above VWAP, the "Big Money" is in profit and likely to continue buying.

### Gate MC3: The Power Gate (Volume Surge > 150%)
*   **Rule:** The current candle's volume must be at least 1.5x the average of the last 10 candles.
*   **Justification:** A price breakout without volume is a "Fakeout." Volume confirms institutional participation. Threshold lowered from 2.0x to 1.5x to reduce missed opportunities on moderate-volume breakouts — still filters pure noise.

### Gate MC4: The Intraday Range Strength Gate (Close in Top 20% of Day's Range)
*   **Rule:** The current close must be at or above `intraday_low + 80% × (intraday_high − intraday_low)`. In plain English: the stock must be trading near its intraday high.
*   **Justification:** The old MC4 (close > prev_day_high) filtered out 100% of signals on any weak market day (e.g. NIFTY −0.81%). Replaced with intraday range strength, which measures where price sits *within today's session* rather than comparing to yesterday. Stocks closing in the top quintile of their day's range are showing genuine intraday momentum.
*   **Legacy gate preserved:** The original `close > prev_day_high` check is commented out in engine.py with label `[MC4-LEGACY]` — see Known Quirk [Q13].

---

## 4. The Swing Strategy Gates (Positional)
*Scheduled at 09:20 and 14:45 IST.*

### Gate S1: The Trend Filter (Price > 200 EMA)
*   **Rule:** Long-term trend must be up.
*   **Justification:** Ensures we are not catching a "Falling Knife."

### Gate S2: The Exhaustion Filter (RSI 45 - 72)
*   **Rule:** RSI must be in the "Sweet Spot."
*   **Justification:** Below 45 is too weak; above 72 is "Overbought" and likely to crash. We buy in the momentum zone.

### Gate S3: The Velocity Filter (Slope > 0)
*   **Rule:** The 5-day price slope must be positive.
*   **Justification:** Confirms that the stock's speed of ascent is increasing.

---

## 5. Risk Audit & "Fort Knox" Protocols
Once a signal passes the technical gates, it must survive the **Risk Audit**:

1.  **Stop Loss Gate (breakout_low):** The stop loss is placed at the bottom of the breakout candle. If the market reverses, we exit instantly.
2.  **Cost Viability Gate (25% Rule):** On a ₹5,000 account, taxes eat profit. If Zerodha's fees > 25% of the projected profit, the trade is killed.
3.  **Position Sizing (10% Risk):** We risk 10% of the pool on one trade. This is a "Hyper-Aggressive" profile designed for rapid capital appreciation.

### 🚨 Circuit Breakers (The Kill Switches)
These protect you from "Black Swan" events:
*   **Daily Loss Limit (20%):** Allow 20% daily loss (allows for 2 consecutive full stop-outs).
*   **Max Drawdown (50%):** Account will halt if 50% of capital is lost.
*   **Consecutive Loss Limit (5):** If 5 trades fail in a row, the bot assumes the market strategy is currently "Out of Sync" and halts.

---

## 🕒 Operational Flow (IST)
*   **08:00:** **Cache Refresh.** Fetches `NSE` and `INDICES` tokens.
*   **09:15:** **Market Open.** Bot waits for data to stabilize.
*   **10:00 - 15:00:** **The Hunt.** Momentum scans every 15 minutes.
*   **15:15:** **The Great Exit.** Auto-Square logic forces `MARKET` orders to close all intraday risk.
*   **00:05:** **Purge.** Database clears old intraday candles to keep the engine fast.


════════════════════════════════════════════════════════════════════════
## SECTION 6 — FILE STRUCTURE (complete)
════════════════════════════════════════════════════════════════════════
```
trading-sentinel/                  ← repo root
├── agent
│   ├── Dockerfile
│   ├── Dockerfile_bkp
│   ├── agent.py
│   ├── agent_bkp.py
│   ├── requirements.txt
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_agent_pipeline.py
│       └── test_agent_schedule.py
├── docker-compose.yml
├── .env
├── .gitignore
├── extra-docker-file-without-logging.txt
├── node-gateway
│   ├── Dockerfile
│   ├── .env
│   ├── client
│   │   ├── index.html
│   │   ├── package-lock.json
│   │   ├── package.json
│   │   ├── src
│   │   │   ├── App.jsx
│   │   │   ├── api
│   │   │   │   └── client.js
│   │   │   ├── components
│   │   │   │   ├── CircuitBreaker.jsx
│   │   │   │   ├── PositionRow.jsx
│   │   │   │   ├── SignalCard.jsx
│   │   │   │   └── StatusBar.jsx
│   │   │   ├── hooks
│   │   │   │   ├── useHealth.js
│   │   │   │   ├── usePerformance.js
│   │   │   │   ├── usePositions.js
│   │   │   │   └── useSignals.js
│   │   │   ├── main.jsx
│   │   │   └── pages
│   │   │       ├── Dashboard.jsx
│   │   │       ├── Login.jsx
│   │   │       └── Positions.jsx
│   │   └── vite.config.js
│   ├── nginx
│   │   └── nginx.conf
│   └── server
│       ├── app.js
│       ├── config.js
│       ├── db
│       │   ├── index.js           ← SQLite init, WAL mode, migrations
│       │   └── schema.sql
│       ├── index.js
│       ├── jest.config.js
│       ├── .env.test
│       ├── middleware
│       │   ├── auth.js
│       │   ├── logger.js
│       │   ├── security.js
│       │   └── validate.js
│       ├── package-lock.json
│       ├── package.json
│       ├── routes
│       │   ├── auth.js
│       │   ├── health.js
│       │   ├── internal.js
│       │   ├── orders.js
│       │   ├── proxy.js
│       │   ├── signals.js
│       │   └── token.js
│       ├── services
│       │   ├── executor.js
│       │   ├── kite.js
│       │   ├── telegram.js
│       │   └── token-store.js
│       ├── tests/
│       │   ├── setup.js
│       │   ├── unit/
│       │   │   ├── market-hours.test.js
│       │   │   ├── sanitise.test.js
│       │   │   ├── retry.test.js
│       │   │   ├── token-store.test.js
│       │   │   ├── errors.test.js
│       │   │   ├── db.test.js
│       │   │   ├── executor.test.js
│       │   │   ├── kite.test.js
│       │   │   └── telegram.test.js
│       │   └── integration/
│       │       ├── telegram-callbacks.test.js
│       │       ├── signals.test.js
│       │       ├── orders.test.js
│       │       └── token.test.js
│       └── utils
│           ├── errors.js
│           ├── market-hours.js
│           ├── retry.js
│           └── sanitise.js
└── python-engine
    ├── Dockerfile
    ├── backtest.py            ← walk-forward backtester
    ├── config.py              ← pydantic-settings Settings class
    ├── engine.py              ← pure indicator + signal functions
    ├── kite_client.py         ← Zerodha wrapper + throttler + cache
    ├── main.py                ← FastAPI app + scheduler + startup
    ├── main_bkp.py
    ├── market_calendar.py     ← NSE trading calendar
    ├── models.py              ← Pydantic v2 models
    ├── performance.py         ← P&L metrics + circuit breakers
    ├── portfolio.py           ← second-pass portfolio allocator
    ├── position_tracker.py    ← live position state + trail stop
    ├── requirements.txt
    └── tests/
        ├── __init__.py
        ├── conftest.py
        ├── test_engine.py
        ├── test_integration_python.py
        ├── test_kite_client.py
        ├── test_main_api.py
        ├── test_market_calendar.py
        ├── test_models.py
        ├── test_performance.py
        ├── test_portfolio.py
        └── test_position_tracker.py
```
17 directories, 65 files


════════════════════════════════════════════════════════════════════════
## SECTION 7 — INVIOLABLE RULES
════════════════════════════════════════════════════════════════════════

Violating any rule below is a critical bug. No exceptions.

### Security
- No hardcoded secrets, tokens, keys, or passwords anywhere
- No wildcard CORS — explicit origin whitelist only
- No access_token in localStorage — memory + httpOnly cookie only
- No logging of sensitive fields — use sanitise.js / sanitiseForLog()
- All inbound payloads validated with Zod (Node) or Pydantic (Python)
- Telegram callbacks verified: not stale (>60s), not already executed
- Order execution hard-blocked outside 09:15–15:30 IST

### Financial safety
- Do not emit a signal if shares == 0
- No order placed without verifying fill status afterward
- GTT sell limit price = trigger * 1.002 (ABOVE trigger, not below)
- Product type on all orders = "CNC" (delivery). NEVER "MIS" (intraday)
  MIS auto-squares at 15:15 IST, destroying swing trade positions
- Price drift check before execution: abort if LTP drifted >2% from
  signal close
- Idempotency: signal status PENDING → EXECUTING → EXECUTED.
  Never execute a non-PENDING signal

### Code quality
- No ML libraries in Container B (no sklearn, tensorflow, statsmodels)
- No random(), no mock data, no TODO placeholders in production code
- No bare except: — catch specific exception types only
- No pandas SettingWithCopyWarning — use .loc[] and .copy() always
- No raw IEEE 754 floats in JSON — all floats explicitly rounded
- No synchronous file I/O in request handlers
- All external HTTP calls must have explicit timeouts
- All async calls must have .catch() or try/catch
- Engine functions in engine.py must be pure (no I/O, no side effects)
- Every formula function in engine.py must have a docstring citing
  its formula ID (e.g. # [F1], # [R3])

### Timezone
- All schedulers, cron jobs, and market hour checks use Asia/Kolkata
- All timestamps stored and logged in UTC ISO-8601
- All display to user in IST


════════════════════════════════════════════════════════════════════════
## SECTION 8 — KNOWN QUIRKS
════════════════════════════════════════════════════════════════════════

These are deliberate decisions, hotfixes, or workarounds for external
API limitations. They may look wrong. They are not. Do not "clean up",
refactor, or revert any of them without explicit instruction.
In case you want to clean up or change then just ask me and justify to me and I will agree if need be

### [Q1] NIFTY 50 instrument token — kite_client.py
The Zerodha instruments API does not reliably return a consistent
token for the "NIFTY 50" index. If `ticker == "NIFTY 50"`, the
instrument_token lookup follows a special resolution path in
kite_client.py. Do not convert this to a hardcoded token value and
do not remove the special-case branch.

### [Q2] CB4 Backtest Gate removed — performance.py
The [CB4] circuit breaker (which halted the system if a backtest
had not passed) has been intentionally removed (commented out) from
performance.py. The live system scans and signals without requiring
a backtest gate. Do not re-implement CB4. The `backtest_gate` field
in PortfolioResponse uses `Literal["PASS", "FAIL", "NOT_RUN"]`.
The `/signals` endpoint returns `"PASS"` unless `BACKTEST_GATE_FAILED`
appears in circuit breaker reasons (which it never will since CB4 is
commented out). Do not change this to `"DISABLED"`.

### [Q3] Schedule object generation — agent.py (Container C)
The schedule library is invoked using:
  `getattr(schedule.every(), day).at(time_str).do(job)`
inside a loop. This pattern forces the creation of distinct job
objects in memory for each day. Do NOT refactor this into:
  `schedule.every().monday.at(...).do(job)`
or any form of variable assignment inside the loop. Doing so causes
schedule objects to overwrite each other, resulting in only the last
day's job being registered.

### [Q4] Ignition switch — main.py (Container B)
At the end of `post_login_initialization()`, both `run_screener()`
and `run_momentum_screener()` are explicitly awaited. This is
intentional. It ensures the instrument cache is populated and the
market is scanned immediately when the user logs in via the browser,
rather than waiting for the next scheduled run. Do not move these
calls, make them non-blocking, or remove them.

### [Q5] WAL mode on every connection — db/index.js (Container A)
`PRAGMA journal_mode=WAL` is set on every SQLite connection open,
not just on database creation. This is deliberate — WAL mode must be
re-confirmed on each connection in the better-sqlite3 usage pattern
to ensure consistent behaviour after container restarts.

### [Q6] Token detection via TokenException — kite.js (Container A)
Token expiry is NOT assumed to occur at 06:00 IST. The primary
detection mechanism is catching `TokenException` from the Zerodha API
at the point of any API call. The 06:05 IST cron job is a secondary
backstop only. Do not replace this with a time-based primary check.

### [Q7] Intraday cache is a separate table
`intraday_cache` and `ohlcv_cache` are completely separate SQLite
tables with different schemas. `ohlcv_cache` uses `PRIMARY KEY (ticker, date)`.
`intraday_cache` uses `PRIMARY KEY (ticker, datetime)`. Do not merge
them. Do not modify `ohlcv_cache` schema.

### [Q8] MOMENTUM positions are exempt from daily trailing stop updates
`update_daily_positions()` in `position_tracker.py` explicitly skips
positions with `source='MOMENTUM'`. This is intentional — momentum
positions are squared intraday and never carry overnight. The trailing
stop logic is irrelevant for them and would cause incorrect P&L.

### [Q9] Momentum schedule in Container B vs Container C
Container B's `run_momentum_screener()` runs every 15 minutes at
:00, :15, :30, :45 for hours 10–14 IST (skipping 10:00 because
only 3 completed candles exist at that point). Container C's
`run_momentum_pipeline()` runs at :55 (10:55, 11:55, etc.) — 40
minutes after Container B's scan. This lag is intentional: it
ensures Container C processes fresh, complete signals. Do not move
Container C's pipeline to :15, and do not change Container B's
schedule from :00/:15/:30/:45.

### [Q10] Swing wins over momentum for same ticker
If a swing signal and momentum signal fire for the same ticker on
the same day, the momentum signal is silently dropped before it
reaches `filter_momentum_signals()`. This happens in both
`run_screener()` (skips tickers with open momentum positions) and
`run_momentum_screener()` (skips tickers in open swing positions).
Do not add UI to let the user choose — the rule is deterministic.

### [Q11] cost_ratio field semantics differ between Signal and MomentumSignal
The `cost_ratio` field is `Optional[float] = None` on `Signal` and
a required `float` on `MomentumSignal`. For swing trades, it is
optional and typically None. For intraday momentum trades, it is
required and critical for the 25% cost viability gate.
Additionally, `MomentumSignal.product_type` allows both `"MIS"`
and `"CNC"` — positions under ₹5,000 use MIS, above use CNC.

### [Q12] BEAR_RS_ONLY does not halt the swing screener
Unlike the previous "BEAR" regime which returned early and emitted
nothing, "BEAR_RS_ONLY" falls through to the screener loop and
applies additional RS filters. The regime filter no longer has an
early return in bear conditions. Do not revert this to an early return.

### [Q13] MC4 gate replaced with intraday range check — old code preserved
The original [MC4] gate `current_close > prev_day_high` (structural
breakout) was eliminating 100% of momentum signals on down-market days
because the market itself could not clear its own previous high.
It has been replaced with an intraday range strength check:
  close >= intraday_low + 0.80 × (intraday_high − intraday_low)
(i.e. close in the top 20% of today's session range).
The old gate code is preserved as a comment block labelled
`[MC4-LEGACY — commented out]` in engine.py immediately below the
new check. Do not delete that comment. Uncomment it to re-enable the
strict breakout gate if strategy changes require it.

### [Q14] MC3 volume threshold lowered from 2.0x to 1.5x; swing gate thresholds relaxed
Following analysis of a live trading day where all 100 momentum signals
were filtered out by aggressive thresholds:
- MC3 `MOMENTUM_VOL_SURGE_PCT` in config.py: 2.0x → 1.5x
- Swing EMA21 proximity band: 97%–110% → 93%–120%
- Swing volume ratio minimum: 1.5x → 1.2x
These changes widen the opportunity funnel while retaining meaningful
filters. Do not tighten these back to the old values without explicit
instruction — those values were calibrated against real market data.

════════════════════════════════════════════════════════════════════════
## SECTION 9 — WHAT TO DO WHEN UNCERTAIN
════════════════════════════════════════════════════════════════════════

If you are unsure about any of the following, STOP and ask:
- Which file a new function belongs in
- Whether a change affects the API contract between containers
- Whether a refactor would conflict with a Known Quirk
- Whether a library you want to suggest is already replaced by
  a deliberate choice in this stack
- Whether a "cleanup" would remove intentional behaviour

Do not assume. Do not guess. This system runs with real capital.
A wrong assumption in a prompt costs seconds to fix.
A wrong assumption in deployed code costs money.

════════════════════════════════════════════════════════════════════════
## SECTION 10 — DELIBERATE ARCHITECTURAL DECISIONS & WHY
════════════════════════════════════════════════════════════════════════

These decisions look unconventional. Here is the reasoning so you
do not suggest alternatives.

**SQLite over Redis:**
This is a single-VM, low-concurrency system. SQLite in WAL mode
handles the write load with zero operational overhead. Redis would
add a fourth process, another failure point, and memory cost with
no benefit at this scale.

**No ML in Container B:**
The quant engine is deliberately deterministic. Every signal must be
explainable by a formula with a source citation. ML models introduce
probabilistic reasoning and hallucination risk into capital allocation
decisions. This is a feature, not a limitation.

**Human approval via Telegram before execution:**
This system targets T+7 to T+15 swing trades. A 30-second approval
delay on a 10-day trade has zero impact on profitability. The human
gate prevents catastrophic errors during the learning phase.

**Container A as sole token authority:**
Zerodha access tokens are fragile (expire daily, invalidate on
logout). A single source of truth prevents race conditions and
desync between containers both trying to manage the same token.
