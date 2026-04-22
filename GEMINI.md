# Trading Sentinel - AI Assistant Context File
# Version: 1.0 (Live Production)
# READ THIS ENTIRE FILE BEFORE GENERATING ANY CODE.
# If you are uncertain about any architectural decision, ASK before
# implementing. Do not guess. Do not "improve" without being asked.

════════════════════════════════════════════════════════════════════════
## SECTION 1 - PROJECT IDENTITY
════════════════════════════════════════════════════════════════════════

**Name:** Trading Sentinel
**Type:** Production algorithmic swing trading system, Indian Stock
          Market (NSE), long-only, daily candles.
**Bankroll:** ₹5,000 (live capital). Every engineering decision must
              treat capital preservation as the top priority.
**Strategy:** T+7 to T+15 swing trades. EMA pullback + volume surge
              + RSI filter. Two-leg exit: 1.5R and 3.0R.
**Risk model:** 10% risk per trade (₹50 max loss per position).
                Max 4 open positions simultaneously.

════════════════════════════════════════════════════════════════════════
## SECTION 2 - SYSTEM ARCHITECTURE
════════════════════════════════════════════════════════════════════════

Three Docker containers on a bridge network named `trading_net`.
Deployed on a single Google Cloud Ubuntu VM.
```
Internet
    │
    ▼
Container A  (node-gateway)        ← ONLY internet-facing container
    │  Port 80/443 via nginx
    │  Reverse proxy to Express :3000
    │
    ├──→ Container B  (quant-engine)    internal: python-engine:8000
    │
    └──→ Container C  (agent)        internal: agent:PORT
```

**Container A - Node.js Gateway**
- The sole internet entry point. Nothing else is publicly accessible.
- Responsibilities: Zerodha OAuth, session/token lifecycle, React
  dashboard (static build), Telegram bot, trade execution,
  reverse proxy to B for the dashboard, token provisioning to B.
- Stack: Node.js 20, Express, React 18 + Vite + Tailwind, pino,
  better-sqlite3, express-session + connect-sqlite3, kiteconnect
  (official Node SDK), node-telegram-bot-api, Zod, helmet,
  express-rate-limit, node-cron, axios.

**Container B - Python Quant Engine**
- The mathematical brain. Never exposed to internet.
- Responsibilities: Nifty 500 screening, indicator calculation,
  signal generation, portfolio risk management, position tracking,
  performance accounting, circuit breakers, bankroll management.
- Stack: Python 3.11, FastAPI, uvicorn, APScheduler, pandas,
  pandas_ta, kiteconnect (Python SDK), pydantic-settings (v2),
  aiosqlite, structlog, httpx.
- Runs screener at 09:20 IST and 14:45 IST via APScheduler.

**Container C - Intelligence Orchestrator**
- The communication and AI reasoning layer.
- Responsibilities: polls Container B for signals, fetches news
  sentiment, runs Gemini AI analysis, sends interactive Telegram
  alerts, manages system heartbeat.
- Stack: Python 3.11, schedule library, google-generativeai,
  httpx, python-telegram-bot.

════════════════════════════════════════════════════════════════════════
## SECTION 3 - FILE STRUCTURE (complete, do not deviate)
════════════════════════════════════════════════════════════════════════
```
trading-sentinel/                  ← repo root
├── agent
│   ├── Dockerfile
│   ├── Dockerfile_bkp
│   ├── agent.py
│   ├── agent_bkp.py
│   └── requirements.txt
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
│       │   ├── orders.js
│       │   ├── proxy.js
│       │   ├── signals.js
│       │   └── token.js
│       ├── services
│       │   ├── executor.js
│       │   ├── kite.js
│       │   ├── telegram.js
│       │   └── token-store.js
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
    └── requirements.txt
```
17 directories, 65 files
════════════════════════════════════════════════════════════════════════
## SECTION 4 - ENVIRONMENT VARIABLES
════════════════════════════════════════════════════════════════════════

Single `.env` file at repo root. Injected into all containers via
`env_file: - .env` in docker-compose.yml. Each container reads only
the variables it needs and ignores the rest.
```
# Zerodha (A + B both use these)
ZERODHA_API_KEY=
ZERODHA_API_SECRET=
ZERODHA_REDIRECT_URL=

# Telegram (A and C)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_WEBHOOK_SECRET=
TELEGRAM_MODE=pooling

# Security (A)
SESSION_SECRET=
INTERNAL_API_SECRET=
# AI (C)
GEMINI_API_KEY=

```

════════════════════════════════════════════════════════════════════════
## SECTION 5 - API CONTRACTS (exact schemas, do not invent fields)
════════════════════════════════════════════════════════════════════════

These are the original JSON schemas flowing between containers though during the development they could have been altered.
You are allowed to add, remove, or rename fields only if needed and have to be updating all consumers.

### Signal object (B → C → A → Telegram)
```json
{
  "ticker":              "string (e.g. RELIANCE)",
  "exchange":            "NSE",
  "signal_time":         "ISO-8601 UTC",
  "close":               "float 2dp",
  "ema_21":              "float 2dp",
  "ema_50":              "float 2dp",
  "ema_200":             "float 2dp",
  "atr_14":              "float 2dp",
  "volume_ratio":        "float 2dp",
  "rsi_14":              "float 1dp",
  "slope_5":             "float 4dp",
  "stop_loss":           "float 2dp",
  "target_1":            "float 2dp",
  "target_2":            "float 2dp",
  "trailing_stop":       "float 2dp",
  "shares":              "int",
  "capital_deployed":    "float 2dp",
  "capital_at_risk":     "float 2dp (hard max 50)",
  "net_ev":              "float 2dp",
  "score":               "int 0-100",
  "sector":              "string",
  "portfolio_slot":      "int 1-4",
  "stale_data":          "bool",
  "strategy_version":    "string semver"
}
```

### GET /signals response (B exposes, A proxies, C polls)
```json
{
  "run_time":                 "ISO-8601",
  "market_regime":            "BULL | CAUTION | BEAR | UNKNOWN",
  "trading_halted":           "bool",
  "halt_reasons":             ["string"],
  "stale_data":               "bool",
  "total_capital_at_risk":    "float",
  "total_capital_deployed":   "float",
  "bankroll_utilization_pct": "float",
  "open_positions_count":     "int",
  "remaining_slots":          "int",
  "signals":                  ["Signal"]
}
```

### POST /positions/manual (A → B, after order fill confirmed)
```json
{
  "ticker":        "string",
  "exchange":      "NSE",
  "entry_price":   "float (actual fill, not signal close)",
  "shares":        "int",
  "stop_loss":     "float",
  "target_1":      "float",
  "target_2":      "float",
  "order_id":      "string (Zerodha order ID)",
  "gtt_stop_id":   "string | null",
  "gtt_target_id": "string | null",
  "notes":         "string"
}
```

### GET /health response (both A and B expose this)
Container A health:
```json
{
  "status":               "ok | degraded | critical",
  "uptime_seconds":       "int",
  "token_status":         "active | expired | none",
  "token_age_minutes":    "int | null",
  "telegram_status":      "connected | error",
  "telegram_mode":        "webhook | polling",
  "python_engine":        "reachable | unreachable",
  "python_engine_ms":     "int",
  "market_open":          "bool",
  "last_signal_received": "ISO-8601 | null",
  "last_order_placed":    "ISO-8601 | null",
  "pending_signals":      "int",
  "unsynced_orders":      "int",
  "timestamp":            "ISO-8601"
}
```

Container B health:
```json
{
  "status":          "ok | degraded | halted",
  "last_run_utc":    "ISO-8601 | null",
  "next_run_utc":    "ISO-8601",
  "tickers_scanned": "int",
  "signals_found":   "int",
  "trading_halted":  "bool",
  "backtest_gate":   "PASS | FAIL | NOT_RUN | DISABLED",
  "engine_version":  "string",
  "cache_hit_rate":  "float",
  "uptime_seconds":  "int"
}
```

### Container A internal DB tables
**received_signals:**
  signal_id (PK), ticker, signal_time, received_at, payload_json,
  telegram_msg_id, status (PENDING|EXECUTING|EXECUTED|REJECTED|EXPIRED)

**executed_orders:**
  id, signal_id (FK), ticker, order_id (UNIQUE), order_type,
  entry_price, shares, status, gtt_stop_id, gtt_target_id,
  placed_at, filled_at, sync_to_b (0=pending,1=done,2=failed), notes

════════════════════════════════════════════════════════════════════════
## SECTION 6 - INVIOLABLE RULES
════════════════════════════════════════════════════════════════════════

Violating any rule below is a critical bug. No exceptions.

### Security
- No hardcoded secrets, tokens, keys, or passwords anywhere
- No wildcard CORS - explicit origin whitelist only
- No access_token in localStorage - memory + httpOnly cookie only
- No logging of sensitive fields - use sanitise.js / sanitiseForLog()
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
- No bare except: - catch specific exception types only
- No pandas SettingWithCopyWarning - use .loc[] and .copy() always
- No raw IEEE 754 floats in JSON - all floats explicitly rounded
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
## SECTION 7 - KNOWN QUIRKS (DO NOT REVERT THESE)
════════════════════════════════════════════════════════════════════════

These are deliberate decisions, hotfixes, or workarounds for external
API limitations. They may look wrong. They are not. Do not "clean up",
refactor, or revert any of them without explicit instruction.

### [Q1] NIFTY 50 instrument token - kite_client.py
The Zerodha instruments API does not reliably return a consistent
token for the "NIFTY 50" index. If `ticker == "NIFTY 50"`, the
instrument_token lookup follows a special resolution path in
kite_client.py. Do not convert this to a hardcoded token value and
do not remove the special-case branch.

### [Q2] CB4 Backtest Gate removed - performance.py
The [CB4] circuit breaker (which halted the system if a backtest
had not passed) has been intentionally removed from performance.py.
The live system scans and signals without requiring a backtest gate.
Do not re-implement CB4. The `backtest_gate` field in health responses
should return "DISABLED", not "FAIL".

### [Q3] Schedule object generation - agent.py (Container C)
The schedule library is invoked using:
  `getattr(schedule.every(), day).at(time_str).do(job)`
inside a loop. This pattern forces the creation of distinct job
objects in memory for each day. Do NOT refactor this into:
  `schedule.every().monday.at(...).do(job)`
or any form of variable assignment inside the loop. Doing so causes
schedule objects to overwrite each other, resulting in only the last
day's job being registered.

### [Q4] Ignition switch - main.py (Container B)
At the end of `post_login_initialization()`, `run_screener()` is
explicitly awaited. This is intentional. It ensures the instrument
cache is populated and the market is scanned immediately when the user
logs in via the browser, rather than waiting for the next scheduled
run. Do not move this call, make it non-blocking, or remove it.

### [Q5] WAL mode on every connection - db/index.js (Container A)
`PRAGMA journal_mode=WAL` is set on every SQLite connection open,
not just on database creation. This is deliberate - WAL mode must be
re-confirmed on each connection in the better-sqlite3 usage pattern
to ensure consistent behaviour after container restarts.

### [Q6] Token detection via TokenException - kite.js (Container A)
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
positions with `source='MOMENTUM'`. This is intentional - momentum
positions are squared intraday and never carry overnight. The trailing
stop logic is irrelevant for them and would cause incorrect P&L.

### [Q9] Momentum pipeline runs at :55 not :15
Container C's `run_momentum_pipeline()` runs at 10:55, 11:55, 12:55,
13:55, 14:55 IST - 40 minutes after Container B's scan at :15.
This lag is intentional: Nifty 500 takes ~3 minutes to scan, plus
Gemini analysis per signal takes 2–5 seconds each. The 40-minute
window ensures Container C processes fresh, complete signals rather
than a partial scan. Do not move the pipeline to run at :15.

### [Q10] Swing wins over momentum for same ticker
If a swing signal and momentum signal fire for the same ticker on
the same day, the momentum signal is silently dropped before it
reaches `filter_momentum_signals()`. This happens in both
`run_screener()` (skips tickers with open momentum positions) and
`run_momentum_screener()` (skips tickers in open swing positions).
Do not add UI to let the user choose - the rule is deterministic.

### [Q11] cost_ratio field is momentum-only
The `cost_ratio` field exists only on `MomentumSignal`, not on `Signal`.
This is by design - for swing trades held 7–15 days, cost ratio is
negligible and not displayed. For intraday trades, it is critical.
Do not add cost_ratio to the swing Signal model.

### [Q12] BEAR_RS_ONLY does not halt the swing screener
Unlike the previous "BEAR" regime which returned early and emitted
nothing, "BEAR_RS_ONLY" falls through to the screener loop and
applies additional RS filters. The regime filter no longer has an
early return in bear conditions. Do not revert this to an early return.

### [Q13] MC4 gate replaced with intraday range check - old code preserved
The original [MC4] gate `current_close > prev_day_high` (structural
breakout) was eliminating 100% of momentum signals on down-market days
because the market itself could not clear its own previous high.
It has been replaced with an intraday range strength check:
  close >= intraday_low + 0.80 × (intraday_high − intraday_low)
(i.e. close in the top 20% of today's session range).
The old gate code is preserved as a comment block labelled
`[MC4-LEGACY - commented out]` in engine.py immediately below the
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
instruction - those values were calibrated against real market data.

════════════════════════════════════════════════════════════════════════
## SECTION 8 - WHAT TO DO WHEN UNCERTAIN
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
## SECTION 9 - DELIBERATE ARCHITECTURAL DECISIONS & WHY
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

════════════════════════════════════════════════════════════════════════
## SECTION 10 - QUICK REFERENCE: KEY THRESHOLDS
════════════════════════════════════════════════════════════════════════

These values are in config and env vars. Listed here for reference they may change based on enrichment during development

| Parameter               | Value   | Location          |
|-------------------------|---------|-------------------|
| Bankroll                | ₹5,000  | BANKROLL env      |
| Risk per trade          | 10%     | RISK_PCT env      |
| Max open positions      | 4       | MAX_OPEN_POSITIONS|
| Max capital per trade   | 30%     | MAX_CAPITAL_PER_TRADE |
| Max sector exposure     | 40%     | MAX_SECTOR_EXPOSURE |
| Daily loss halt         | 2%      | hardcoded in CB1  |
| Drawdown halt           | 10%     | hardcoded in CB3  |
| Consecutive loss halt   | 3       | hardcoded in CB2  |
| Bankroll floor          | 50%     | hardcoded in BK5  |
| Price drift abort       | 2%      | executor.js       |
| Signal staleness        | 5 min   | signals.js        |
| Callback staleness      | 60 sec  | telegram.js       |
| EMA pullback band       | 97–101% | config.py [C2]    |
| Volume ratio min        | 1.5×    | config.py [C3]    |
| RSI band                | 45–72   | config.py [C4]    |
| ATR stop multiplier     | 1.5×    | config.py [R1]    |
| Percent stop floor      | 5%      | config.py [R2]    |
| Target 1                | 1.5R    | config.py [R5]    |
| Target 2                | 3.0R    | config.py [R5]    |
| Screener runs           | 09:20, 14:45 IST | main.py  |
| Position update         | 15:45 IST | main.py         |
| Market hours            | 09:15–15:30 IST | market-hours.js | 