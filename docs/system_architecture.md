# Trading Sentinel — System Architecture & Strategy Reference

_Last updated: 2026-06-25 (post-audit)_

This is the canonical reference for **how the system actually works today** —
every strategy, every scheduler, every data flow, every operator-facing
endpoint. Use it alongside `docs/penny_telegram_commands.md` (operator
manual) and `docs/evolution/DESIGN_DOC.md` (May 2025 design spec).

> **Scope:** Python engine + Node gateway + Telegram bot integration.
> Frontend dashboard (separate repo) is out of scope.

---

## 1. Bird's-eye view

```
┌────────────────────────────────────────────────────────────────────┐
│  External                                                           │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│   │  Kite Connect │    │  Telegram    │    │  Container A │          │
│   │  (broker)     │    │  (operator)  │    │  (sibling)   │          │
│   └──────┬───────┘    └──────┬───────┘    └──────┬───────┘          │
└──────────┼───────────────────┼───────────────────┼──────────────────┘
           │ HTTPS (rate-limited 3 req/s)
           │                   │ bot token + chat_id
           │                   │ internal API secret
           │                   │
┌──────────┼───────────────────┼───────────────────┼──────────────────┐
│  Trading Sentinel                                                    │
│                                                                     │
│  ┌──────────────────┐                ┌────────────────────────┐    │
│  │   Node gateway    │  POST /penny/  │   python-engine        │    │
│  │   (Express +      │  command/{cmd} │   (FastAPI + APScheduler)  │
│  │    Telegram bot)  │ ─────────────► │                          │    │
│  └────────┬─────────┘                │  ┌────────────────────┐  │    │
│           │                           │  │  Scanner loop       │  │    │
│           │ callback_query            │  │  (30s, 09:30, 14:30)  │  │    │
│           │ (EXEC:shortId:ts /       │  └─────────┬──────────┘  │    │
│           │  EM:TICKER_MOM:ts)        │            │             │    │
│           ▼                           │            ▼             │    │
│  ┌──────────────────┐                │  ┌────────────────────┐  │    │
│  │   SQLite (signals)│ ◄────────────►│  │  DB (positions,     │  │    │
│  │   received_signals│  read/write   │  │   bankroll_ledger,  │  │    │
│  └──────────────────┘                │  │   bankroll_subsystem)│  │    │
│                                     │  └────────────────────┘  │    │
│                                     └────────────────────────┘    │
└────────────────────────────────────────────────────────────────────┘
```

**Two-language split:**
- **Python engine** — strategy logic, scheduler, DB, HTTP API. Heavy lifting.
- **Node gateway** — Telegram bot + signal execution lock (prevents double-fire).
  Relays `/penny` and `/nifty` slash commands to python-engine.

**Strict separation** (operator mandate, 2026-06-24):
- Penny pool (Rs 2,500 paper / Rs 2,500 live, allocated) is **fully isolated**
  from Nifty pool (Rs 5,000 swing + Rs 2,500 momentum, same DB but separate
  queries). A penny loss cannot trigger a Nifty circuit-breaker and vice
  versa.

---

## 2. Subsystem overview

### 2.1 Nifty subsystem (swing + momentum)

**Goal:** Generate daily/intraday signals on Nifty 100 stocks using
trend-following (swing) and intraday momentum (momentum).

**Bankroll:** `INITIAL_BANKROLL = 5000` (configurable). Strict-separation
`nifty_bankroll()` returns `5000 + SUM(pnl WHERE source IN ('SYSTEM','MOMENTUM'))`.

| Component | File | Cadence |
|---|---|---|
| `run_screener` | `main.py` (function) | 09:20 + 14:45 IST daily |
| `run_momentum_screener` | `main.py` (function) | Every 15 min from 10:00 to 14:45 IST |
| `auto_square_momentum` | `main.py` (function) | 15:15 IST (if `MOMENTUM_ALLOW_OVERNIGHT=False`) |
| `check_circuit_breakers` | `performance.py` | On every signal evaluation + daily |
| `run_daily_post_market` | `main.py` (function) | 15:45 IST |

**Signal evaluation chain (per ticker):**
1. **Indicator computation** (`engine.py:evaluate_signal`)
   - EMA(21, 50, 200) for trend
   - ATR(14) for volatility-adjusted stops
   - RSI(14) Wilder
   - Volume ratio (current bar / 20-day avg)
   - 5-bar slope for short-term momentum
   - Net EV (expected value after costs)
2. **Score** = weighted combination of all the above. Threshold per regime.
3. **Regime filter** (`regime.py:compute_score_full` — VIX-free, ATR compression
   + realized vol + breadth). Produces `REGIME_1_BULL`, `REGIME_2_ELEVATED`,
   `REGIME_3_CRISIS`.
4. **Position sizing** — regime-based % of bankroll, capped at per-stock Rs.
5. **Risk gates** — circuit filter (band-aware), kill-switch on daily loss
   > 20% of bankroll, manual disable list.
6. **Executor** — places LIMIT entry, polls for fill, places SL-M.
   On SL-M failure → emergency market unwind (best-effort, logged).

### 2.2 Penny subsystem

**Goal:** Trade small-cap NSE stocks (Rs 1–55 range) using either:
- **Connors RSI(2) mean-reversion** (CNC leg, once daily 09:30 IST)
- **Volume breakout** (MIS leg, every 30s scan during market hours)

**Bankroll:** Allocated separately. `penny_pool_pnl()` sums per-source
`source='PENNY'` rows. Hard cap Rs 500 per stock, max 5 positions
(2 CNC + 3 MIS), Rs 20 brokerage bypass available for paper mode.

| Component | File | Cadence |
|---|---|---|
| `run_penny_scanner_once` | `main.py` (function) | Every 30s during market hours (MIS) |
| `run_penny_connors_scan` | `main.py` (function) | 09:30 IST daily (CNC) |
| `run_penny_force_close_mis` | `main.py` (function) | 15:00 IST (MIS must not hold overnight) |
| `run_penny_eod_check` | `main.py` (function) | 14:30 IST (smart-EOD, partial-exit logic) |
| `run_penny_universe_refresh` | `main.py` (function) | 08:00 IST daily |
| `run_penny_premarket_report` | (function) | 08:30 IST |
| `run_penny_hourly_report` | `main.py` (function) | Every hour 10:00–14:00 IST |
| `_run_penny_heatmap` | `main.py` (function) | Every 15 min (10:00–14:45 IST) |
| `_run_penny_daily_attribution` | `main.py` (function) | 15:30 IST |
| `_run_penny_eod_digest` | `main.py` (function) | 16:00 IST |

---

## 3. Penny strategies in detail

### 3.1 Connors RSI(2) mean-reversion (CNC leg)

**File:** `python-engine/penny_engine_connors.py`

**Premise:** Stocks that have fallen hard (RSI(2) below 10) tend to bounce
within 3 trading days. Buy on the close, exit at +3% T1, then trail
remaining 50% with post-T1 trailing stop.

**Entry criteria (all must pass):**
1. **Universe eligibility** — ticker in penny_static.json, price in
   `[PENNY_PRICE_MIN=1.0, PENNY_PRICE_MAX=55.0]`, promoter holding known,
   PB ratio known (null-tolerant since 2026-06-25).
2. **History** — at least 250 daily bars (since G4 fix; was 210).
3. **Volume filter** — `today_volume >= 0.5 * avg20_volume` (G1 fix; was
   hardcoded 50k/100k).
4. **Trigger** — `RSI(2) < PENNY_CONNORS_RSI2_BUY` (default 10).
   Optional: `cumulative RSI(2) days` (T2-A refinement, default disabled).
   Optional: `RSI(2) > PENNY_CONNORS_RSI2_FLOOR` (T2-A, default disabled = 1.0).
5. **Time-of-day filter** — current IST within
   `[PENNY_CONNORS_TIME_START=09:30, PENNY_CONNORS_TIME_END=12:30]` (T2-D).

**Position construction:**
- `entry = round(last * 1.005, 2)` (LTP + 0.5%, rounded to 2 dp).
- `stop_loss = round(entry * 0.97, 2)` (−3%).
- `target_1 = round(entry * 1.03, 2)` (+3%).
- `target_2 = round(entry * 1.06, 2)` (+6%, used as exit signal).
- `shares = floor(risk_budget / (entry - stop_loss))` capped at Rs 500.

**Exit logic (`evaluate_connors_exit`):**
- T1 hit → close 50%, trail remaining at `max(breakeven + 0.5%, highest close - atr_1min_post_t1 * 2.0)`.
- T2 hit OR time-stop (3 trading days) → close 100%.
- 14:30 IST smart-EOD → close if in profit.
- 15:00 IST force-close (G5) → close 100% (MIS must not hold overnight).

**Performance characteristic** (per academic literature):
- 75–80% historical win rate (1–3 day hold).
- Average winner ~3%, average loser ~3% (asymmetric R:R).
- Most failures = RSI(2) didn't bounce within 3 days.

### 3.2 Volume breakout (MIS leg)

**File:** `python-engine/penny_engine_breakout.py`

**Premise:** When a stock breaks its day high on volume > 1.8x the 20-day
average, momentum continues intraday. Enter with stop at breakout low,
target at 2× the risk.

**Entry criteria (all must pass):**
1. **Time window** — IST within
   `[PENNY_BREAKOUT_TIME_START=10:30, PENNY_BREAKOUT_TIME_END=14:00]`.
2. **Volume** — `cum_vol_today >= 1.8 × median_vol_20d`.
3. **Breakout** — `last > day_high + PENNY_BREAKOUT_BUFFER_PCT × price`
   (default 0.3%, see T2-B refinements below).
4. **RSI(14) not extreme** — guards against chasing into a blow-off top.
5. **Sector filter** (T2-C, default ON) — if the ticker's sector ETF is
   in the top 10% losers today (≥1.65% drop), reject.

**Optional T2-B refinements** (all default OFF to preserve current
behaviour; flip via `PENNY_BREAKOUT_USE_VWAP` / `PENNY_BREAKOUT_ADAPTIVE_THRESHOLD`):
- **VWAP-anchored breakout** — use `VWAP + 0.3%` instead of `day_high + 0.3%`.
- **Adaptive threshold** — scale buffer by `current ATR(20) / median ATR(20)`,
  clamped 0.3–2.0×.

**Position construction:**
- `entry = round(bar_close * 1.003, 2)` (LTP + 0.3%).
- `stop_loss = breakout_bar.low` (the bar that broke out).
- `target = entry + PENNY_BREAKOUT_TARGET_R × risk_per_share` (default 2R).
- `shares = floor(risk_budget / risk_per_share)` capped at Rs 500.

**Exit logic (`smart_eod_check`):**
- T1 hit → partial exit at 1R, trail remaining at `highest_close - 0.5R`.
- T2 hit → full exit.
- Intraday time-stop at 14:30 IST → exit if in profit, hold losers.
- 15:00 IST force-close → exit all open MIS positions.

**Performance characteristic:**
- Lower win rate (~50%) but larger R:R (2:1 target).
- Sensitive to volume filter quality — false breakouts on low volume are
  the main loss source.

### 3.3 Sector filter (T2-C, cross-cutting)

**File:** `python-engine/penny_sector_filter.py`

**Premise:** A breakout signal in a sector that's already crashing is
more likely to be a "bull trap" continuation than a real breakout.
Reject if sector ETF is severely weak.

**Data source:** `python-engine/data/penny_sectors.csv` — operator-curated
`(symbol, sector)` mapping. Plus a hard-coded `SECTOR_TO_ETF` dict in the
module.

**Logic:**
- Group tickers by sector → fetch each unique sector's ETF quote (one
  Kite call per sector, deduped).
- Compute ETF change = `(current - prev_close) / prev_close`.
- If `etf_change <= PENNY_SECTOR_ETF_CHANGE_THRESHOLD_PCT` (−1.5% by default)
  AND the sector ETF is in the top 10% losers today → REJECT.
- Otherwise → ALLOW.
- Unknown sector (no CSV entry, no ETF map) → ALLOW (fail-open).

**Failures:** file missing → empty map, ALLOW. CSV malformed → warn, ALLOW.
Kite quote fails → UNKNOWN → ALLOW. Never blocks the scanner.

---

## 4. Data flow per signal

### 4.1 Penny scanner (MIS Breakout)

```
30s tick (scheduler.interval)
  └─> run_penny_scanner_once()
        ├─> _get_penny_scanner()    -- lazy singleton, builds if missing
        ├─> scanner._load_universe() -- reads penny_static.json + corp data
        ├─> risk_engine.is_disabled(ticker) -- checks /penny skip list
        ├─> asyncio.gather(_evaluate_ticker_breakout(t) for t in surviving)
        │     ├─> kite.get_historical(ticker, 30 days)        -- 20-day median vol
        │     ├─> kite.get_quote(token)                         -- LTP + ohlc
        │     ├─> _build_position_snap → evaluate_breakout_entry
        │     └─> returns decision dict {accept, entry, stop_loss, ...}
        ├─> filter_universe_by_sector()           -- T2-C batch dedupe
        ├─> for each (ticker, decision):
        │     ├─> log_penny_signal(DB, scan_id, ticker, leg, accepted, ...)
        │     ├─> if accepted AND sector_OK:
        │     │     ├─> INSERT positions (with atr_1min_post_t1, t1_fired)   [G5]
        │     │     ├─> executor.execute_entry()
        │     │     │     ├─> place LIMIT entry → poll fill (60s timeout)
        │     │     │     ├─> place SL-M at broker (with retry)
        │     │     │     └─> on SL-M failure: market unwind
        │     │     └─> if filled: record_pnl_cb on close
        │     └─> if rejected: log skip + reason
        ├─> scan_id = uuid per cycle (rejection reasons can be joined back)
        └─> log: accept=N reject=N error=N
```

### 4.2 Penny CNC scan (Connors)

```
09:30 IST (scheduler.cron)
  └─> run_penny_connors_scan()
        ├─> _penny_scanner = None; _get_penny_scanner()  -- force rebuild
        ├─> scanner._load_universe()
        ├─> for t in universe:
        │     ├─> if is_disabled → skip
        │     ├─> scanner._evaluate_ticker_connors(t, as_of=now)
        │     │     ├─> kite.get_historical (250 bars)
        │     │     ├─> kite.get_quote
        │     │     ├─> compute RSI(2) on closes
        │     │     ├─> check trigger (RSI<10), volume, time-of-day
        │     │     └─> returns {accept, entry, sl, t1, t2, shares, atr_1min}
        │     ├─> if accepted:
        │     │     ├─> executor.execute_entry(leg=CNC)
        │     │     └─> on filled: INSERT positions (with atr_1min_post_t1)
        │     └─> log accept/reject
```

### 4.3 Exit lifecycle (both legs)

```
every 30s (MIS only): position_tracker.update_daily_positions()
  ├─> for each open position: evaluate_connors_exit / smart_eod_check
  ├─> if T1 hit (price >= target_1): partial close, update trailing_stop
  ├─> if T2 hit (price >= target_2): full close
  ├─> if 14:30 IST smart-EOD: close profitable, hold losers
  ├─> if 15:00 IST force-close: close all MIS
  ├─> if max-hold-days reached: time-stop close
  └─> on any close: record_pnl_cb → risk_engine.record_realized_pnl
                   → ledger_writer → bankroll_ledger (source='PENNY')
```

---

## 5. Risk model

### 5.1 Penny risk (`penny_risk.PennyRiskEngine`)

| Knob | Default | Effect |
|---|---|---|
| `PENNY_PER_STOCK_CAP` | Rs 500 | Max Rs deployed per single stock |
| `PENNY_MAX_POSITIONS_TOTAL` | 5 | Hard cap on concurrent positions |
| `PENNY_MAX_POSITIONS_CNC` | 2 | CNC-specific cap |
| `PENNY_MAX_POSITIONS_MIS` | 3 | MIS-specific cap |
| `PENNY_RISK_PCT_PR1` | 5% | Position size as % of bankroll in PR1_CALM |
| `PENNY_RISK_PCT_PR2` | 2.5% | Same for PR2_ELEVATED |
| `PENNY_RISK_PCT_PR3` | 0% | Same for PR3_HOT (block all entries) |
| `PENNY_DAILY_KILL_SWITCH_PCT` | 20% | If daily loss > 20% of bankroll, block new entries |
| `PENNY_CIRCUIT_SKIP_DISTANCE` | 0.5% | Skip if price within X% of band |
| `PENNY_CIRCUIT_FROM_HIGH_PCT` | 3% | + skip if price > 3% below day high |
| `PENNY_BROKERAGE_BYPASS` | False | Paper mode: skip costs (see `penny_risk.calc_penny_costs`) |
| `PENNY_HEATMAP_WARN_PCT` | 1% | Heat-map WARN threshold (T3-D / 2.5) |

**Sizing formula** (`position_size`):
```
risk_per_share = entry - stop_loss        # absolute risk per share
risk_budget   = bankroll × regime_pct     # allowed risk per trade
shares       = min(
    floor(risk_budget / risk_per_share),  # risk-based cap
    floor(PER_STOCK_CAP / entry),         # absolute cap
)
```

### 5.2 Nifty risk (`risk_engine.RiskEngine`)

Standard 1% risk per trade, capped by per-stock cap. Three regime multipliers
(R1×3.5, R2×3.0, R3×2.5) used for Chandelier exit trailing.

### 5.3 Kill-switch

```python
def kill_switch_active(as_of):
    threshold = -1.0 * bankroll * PENNY_DAILY_KILL_SWITCH_PCT  # -20%
    return self.daily_pnl <= threshold
```

Resets daily at 00:05 IST (`_penny_daily_reset`). Once tripped, **no new
entries** are placed until midnight reset; existing positions still managed.

---

## 6. Data tables (SQLite)

```sql
-- positions: every open + closed position, source-filtered
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT, status TEXT, source TEXT,         -- 'PENNY' / 'SYSTEM' / 'MOMENTUM'
    entry_date TEXT, exit_date TEXT,
    entry_price REAL, exit_price REAL, shares INTEGER,
    stop_loss_initial REAL, trailing_stop_current REAL,
    target_1 REAL, target_2 REAL,
    atr_14_at_entry REAL, highest_close_since_entry REAL,
    atr_1min_post_t1 REAL, t1_fired INTEGER DEFAULT 0,  -- G5 migration
    product_type TEXT DEFAULT 'CNC',         -- MIS / CNC / NRML [AUDIT-FIX-1.2]
    regime_at_entry TEXT,
    realised_pnl REAL, r_multiple REAL
);

-- bankroll_ledger: append-only, partitioned by source (AUDIT-FIX-1.1)
CREATE TABLE bankroll_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT, event_type TEXT, ticker TEXT,
    pnl REAL,
    bankroll_before REAL, bankroll_after REAL,    -- per-source now (post-fix)
    source TEXT,                                    -- 'PENNY' / 'SYSTEM' / 'MOMENTUM'
    notes TEXT
);

-- penny_signals: scan outcomes (CSV mirror in penny_signals.csv)
CREATE TABLE penny_signals (
    scan_id TEXT, scanned_at TEXT, ticker TEXT, leg TEXT,
    accepted INTEGER, reject_reason TEXT,
    regime TEXT, close REAL,
    -- entry decision (if accepted):
    stop_loss REAL, target_1 REAL, target_2 REAL,
    rsi_2 REAL, rsi_14 REAL, volume_ratio REAL,
    breakout_level REAL, shares INTEGER
);

-- trade_outcomes (analytics.self_improvement): joined on ticker + timestamp
CREATE TABLE trade_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT, ticker TEXT, pnl REAL, r_multiple REAL,
    signal_id INTEGER, notes TEXT
);
```

**Strict separation invariants** (enforced by tests):
- `nifty_bankroll()` reads ONLY `source IN ('SYSTEM','MOMENTUM')` rows.
- `penny_pool_pnl()` reads ONLY `source='PENNY'` rows.
- Penny losses do NOT contaminate Nifty circuit-breaker, and vice versa.

---

## 7. Schedulers (APScheduler in `lifespan()`)

| Time (IST) | Job | Purpose |
|---|---|---|
| 00:05 | `_penny_daily_reset` | Reset penny daily P&L counter |
| 00:05 | `kite.clear_intraday_cache` | Clean intraday cache |
| 08:00 | `run_penny_universe_refresh` | Refresh penny_static.json from Kite |
| 08:30 | `run_penny_premarket_report` | Top 10 tickers by composite score |
| 09:20 | `run_screener` | Nifty swing regime compute |
| 09:30 | `run_penny_connors_scan` | CNC leg (Connors RSI(2)) |
| 10:00–14:45 (every 15min) | `run_momentum_screener` | Nifty momentum scan |
| 10:00–14:00 (every 15min) | `_run_penny_heatmap` | Penny position heat-map |
| 10:00–14:00 (top of hour) | `run_penny_hourly_report` | Telegram status message |
| 14:30 | `run_penny_eod_check` | Smart-EOD (partial exits, hold losers) |
| 14:45 | `run_screener` (2nd call) | End-of-day swing re-classify |
| 15:00 | `run_penny_force_close_mis` | Hard force-close all MIS positions |
| 15:10 | `momentum_eod_warning` | 5-min warning before auto-square |
| 15:15 | `auto_square_momentum` (if `MOMENTUM_ALLOW_OVERNIGHT=False`) | Momentum EOD square-off |
| 15:30 | `_run_penny_daily_attribution` | Penny's daily P&L attribution to Telegram |
| 15:45 | `daily_post_market` | Nifty daily summary |
| 16:00 | `_run_penny_eod_digest` | Penny EOD digest to Telegram |

All jobs are best-effort: any single job crashing logs + continues, never
crashes the loop.

---

## 8. Operator console (Telegram)

Documented in detail in `docs/penny_telegram_commands.md`. Quick reference:

| Group | Commands |
|---|---|
| Penny | `/penny stats`, `/penny regime`, `/penny heatmap`, `/penny skip TICKER`, `/penny unskip TICKER`, `/penny skips`, `/penny help` |
| Nifty | `/nifty stats`, `/nifty swing`, `/nifty momentum`, `/nifty regime`, `/nifty circuit`, `/nifty help` |
| Cross-subsystem | `/health`, `/regime`, `/status`, `/performance` |

**All slash commands are read-only.** The operator mandate (2026-06-25) is firm:
no `/` command can execute trades, change settings, or modify state.
State changes happen via the inline `EXEC`/`REJ`/`EM` callback buttons on
signal alerts, or via the HTTP API (`POST /positions/close`).

The callback buttons are wired through the **Node gateway's callback_query
handler** (`node-gateway/server/index.js`) which atomically updates a
`received_signals` table (in node-gateway's SQLite) to prevent
double-fires.

---

## 9. External integrations

### 9.1 Kite Connect (broker)

- **Auth:** API key + access token in `KITE_API_KEY` / `KITE_ACCESS_TOKEN`
  env vars. Token expires daily at 06:00 IST.
- **Rate limit:** `kite_client.RateLimiter(rate=3.0, burst=1)` = 3 req/sec.
  Every public method awaits `self.limiter.acquire()` first.
- **Failure modes:** httpx errors caught, return `{}` (silent at caller).
  Empty result for a NON-empty request → CRITICAL log (AUDIT-FIX-2.3,
  once per process, resets on success).

### 9.2 Telegram

- **Auth:** bot token + chat ID. `_isValidChat(msg.chat.id)` filters by
  configured `TELEGRAM_CHAT_ID`.
- **Transport:** `/command/{cmd}` HTTP endpoint on python-engine (port
  from settings), reached via axios from node-gateway.
- **Health monitoring:** the polling handler occasionally emits
  `EFATAL: AggregateError` in logs (network blips). These are recoverable
  and the bot reconnects automatically. To monitor: count occurrences
  per hour.

### 9.3 Container A (sibling)

- **Auth:** shared `INTERNAL_API_SECRET` header.
- **Endpoints used:**
  - `POST /api/internal/notify` — fire Telegram alerts (CNC position
    untracked, internal-secret missing, etc.).
  - `POST /positions/manual` — Container A reports a successful execution;
    we persist it.
  - `POST /positions/close` — Container A reports a square-off; we
    compute P&L and persist.
- **Misconfig protection (AUDIT-FIX-2.2):** empty `INTERNAL_API_SECRET`
  → these endpoints return HTTP 503 instead of silently accepting
  empty-secret calls.

---

## 10. Observability & debugging

### 10.1 Logs

- All modules use module-level `logger = logging.getLogger(__name__)`.
- python-engine logs go to stderr (Docker captures).
- Look for `penny_*` prefixes for penny subsystem events.
- Look for `kite_*` for broker interaction events.
- `CRITICAL` level = operator-must-see (empty secret, full-batch failure).
- `WARNING` = degraded state (stale universe, no live price).
- `INFO` = lifecycle (scan started, position opened).

### 10.2 Audit trail (who did what)

- **Penny signals:** every signal outcome logged in `penny_signals` table
  AND `penny_signals.csv` (CSV is the canonical audit trail).
- **Trade outcomes:** `trade_outcomes` table joined to `penny_signals` on
  ticker + scan timestamp range.
- **bankroll_ledger:** append-only, per-source partitioned (post AUDIT-FIX-1.1).
- **Manual overrides:** `penny_disable_overrides.json` records every
  `/penny skip` / `/penny unskip` with timestamp.

### 10.3 Common diagnostic queries

```sql
-- Today's penny P&L by ticker
SELECT ticker, SUM(realised_pnl), COUNT(*) AS trades
FROM bankroll_ledger
WHERE event_type = 'TRADE_CLOSED'
  AND source = 'PENNY'
  AND DATE(timestamp) = DATE('now')
GROUP BY ticker ORDER BY 2 DESC;

-- Open positions across all subsystems
SELECT source, COUNT(*), SUM(entry_price * shares)
FROM positions WHERE status IN ('OPEN', 'CLOSED_T1')
GROUP BY source;

-- Recent rejections (last 24h)
SELECT reject_reason, COUNT(*)
FROM penny_signals
WHERE accepted = 0
  AND scanned_at > datetime('now', '-1 day')
GROUP BY reject_reason ORDER BY 2 DESC;

-- Nifty bankroll over time
SELECT DATE(timestamp), source, SUM(pnl)
FROM bankroll_ledger
WHERE source IN ('SYSTEM', 'MOMENTUM')
GROUP BY DATE(timestamp), source;
```

---

## 11. Configuration knobs (top-level `config.py`)

Settings live in `Settings(BaseSettings)` and override via env vars.

### 11.1 Penny pool

| Setting | Default | Notes |
|---|---|---|
| `PENNY_LIVE_TRADING` | False | If True, executor places real orders |
| `PENNY_PAPER_BANKROLL` | 2500.0 | Paper mode bankroll |
| `PENNY_LIVE_BANKROLL` | 2500.0 | Live mode bankroll |
| `PENNY_BROKERAGE_BYPASS` | False | If True, skip cost erosion (paper/test only) |
| `PENNY_PRICE_MIN` / `_MAX` | 1.0 / 55.0 | Universe price band |
| `PENNY_PER_STOCK_CAP` | 500.0 | Rs cap per single position |
| `PENNY_USE_SECTOR_FILTER` | True | T2-C gate (recommended) |
| `PENNY_HEATMAP_WARN_PCT` | 0.01 | AUDIT-FIX-2.5 (1% threshold for WARN) |
| `PENNY_SECTOR_ETF_CHANGE_THRESHOLD_PCT` | -0.015 | T2-C (-1.5% threshold) |
| `PENNY_DISABLE_TICKERS` | "" | Comma-separated static list |

### 11.2 Nifty pool

| Setting | Default | Notes |
|---|---|---|
| `INITIAL_BANKROLL` | 5000.0 | Nifty pool starting bankroll |
| `MOMENTUM_POOL_PCT` | 0.5 | 50% of Nifty pool is for momentum |
| `MOMENTUM_ALLOW_OVERNIGHT` | False | If True, 15:15 auto-square is disabled |
| `SWING_MAX_POSITIONS` | 4 | Swing position cap |
| `SWING_RISK_PCT` | 0.01 | 1% risk per swing trade |
| `NIFTY_REGIME_*` | various | Regime classifier thresholds |

### 11.3 Operational

| Setting | Default | Notes |
|---|---|---|
| `INTERNAL_API_SECRET` | "" | AUDIT-FIX-2.2 — empty triggers 503 |
| `TELEGRAM_BOT_TOKEN` | "" | Required for Telegram |
| `TELEGRAM_CHAT_ID` | "" | Required for Telegram |
| `DB_PATH` | `python-engine/data/trading.db` | SQLite location |
| `PENNY_UNIVERSE_JSON_PATH` | `python-engine/data/penny_static.json` | Universe data |
| `PENNY_SECTORS_CSV_PATH` | `python-engine/data/penny_sectors.csv` | Operator-curated sector mapping |

---

## 12. Recent changes (last 7 days)

For full change log see `git log --oneline -20` on the branch.

| Date | Change |
|---|---|
| 2026-06-25 | 5 audit correctness fixes (AUDIT-FIX 1.1–1.5) — bankroll double-counting, is_intraday cost calc, stale regime, missing-field 500, CNC DB write failure alert |
| 2026-06-25 | 6 medium-risk fixes (AUDIT-FIX 2.1–2.6) — VIX warnings demoted, empty-secret 503, full-batch quote failure CRITICAL, universe staleness, heat-map warn threshold, /performance shared helper |
| 2026-06-25 | Operator console Phase A/B/C — `/nifty` commands, `/health`, `/regime`, `/status`, `/performance`, EOD digest |
| 2026-06-25 | Penny Tier 1 bug sweep (G1–G10) — null-tolerant eligibility, real volume, history floor, VWAP/adaptive breakout, sector filter, force-close at 15:00 IST, parallel scanning |
| 2026-06-25 | Penny Tier 2 strategy enrichments — Connors refinements, VWAP breakout, sector-relative strength gate |
| 2026-06-25 | Penny Tier 3 UX — interactive Telegram, daily attribution, regime confidence reasons, position heat-map |
| 2026-06-21 | Initial PennyExector (broker SL-M + emergency unwind) |
| 2026-06-14 | Breadth engine (banknifty ratio as breadth proxy) |
| 2026-06-16 | Trailing exits with regime-aware Chandelier multipliers |
| 2026-06-13 | Universe expansion (Nifty 500 CSV fallback) |

---

## 13. Known limitations & operator's-eye-view

| Limitation | Why | Workaround |
|---|---|---|
| Penny strategies untested at scale (~20 trades total) | New system, paper mode only | Tier 4 ML recommended in 90+ days when data exists |
| ML signal ranking not implemented | Audit-trail recommendation | Build in 90 days if dataset grows |
| Backtest covers strategy logic only, not the executor/SL-M flow | Tested separately | Manual paper trade before live |
| Penny strategies may underperform in low-volume regimes | No volume filter at exit | Use smart-EOD to limit exposure |
| Telemetry on telegram polling errors is sparse | node-gateway logs EFATAL but doesn't track frequency | Manual grep of `telegram_polling_error` events |
| Frontend dashboard is separate | This doc doesn't cover it | (out of scope) |

---

## 14. Where to look for more

| Doc | Purpose |
|---|---|
| `docs/penny_telegram_commands.md` | Operator manual — every slash command |
| `docs/evolution/DESIGN_DOC.md` | May 2025 design spec (original plan) |
| `docs/evolution/PENNY_EXPANSION_CHANGES.md` | Penny subsystem build notes |
| `docs/evolution/UNIVERSE_EXPANSION_CHANGES.md` | Universe load + CSV fallback |
| `docs/runbooks/penny-debug.md` | Penny-specific debugging playbook |
| `docs/runbooks/breadth-debug.md` | Breadth signal debugging |
| `docs/runbooks/self-improvement-analytics.md` | Self-improvement loop |
| `docs/runbooks/momentum-regime-dispatch.md` | Momentum regime + dispatch |
| `docs/deviations/*.md` | Per-decision deviations from spec (12+ entries) |
| `~/.hermes/skills/trading-sentinel/trading-sentinel-ops/SKILL.md` | Agent-side ops guide (in Hermes) |
