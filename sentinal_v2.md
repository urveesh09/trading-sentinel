Copmlete implimentation
You can impliment all in one go but I also want you to keep interval checks of yourself, in any case of memory loss or hallucination you may finish the phase and then tell me to instruct you to continue in the next prompt/session
ENSURE CORRECTNESS, since this involves real money and this will affect production directly
ENSURE ACCURACY as well, though chances are less, maybe the code may also not fit the architecture then you have to tell me what is happening and issue and get back to me to how to solve that
---

```markdown
# Trading Sentinel V2.0 — Agentic Implementation Prompt
# Mission: Upgrade Container B and Container C to a dual-strategy
# (Swing + Intraday Momentum) all-weather system.
# READ EVERY SECTION BEFORE GENERATING A SINGLE LINE OF CODE.
# If uncertain about anything: ASK. Do not guess. Real capital is at risk.

════════════════════════════════════════════════════════════════════════
## SECTION 0 — AUDIT FINDINGS (what the code audit revealed)
════════════════════════════════════════════════════════════════════════

Before implementing anything, understand the current state of each
file as confirmed by direct code audit. These are facts, not
assumptions.

### engine.py (confirmed)
- All functions are pure with no side effects. ✓
- Function signatures: `(pd.Series) → float` for indicators,
  `(ticker, df, bankroll, risk_pct) → Tuple[bool, Dict]` for
  `evaluate_signal()`. All new functions MUST match these patterns.
- Cost model currently uses `cost_per_side = c * shares * 0.001`.
  This is inaccurate. V2.0 replaces it with the full Zerodha model.
- No RS, VWAP, or momentum logic exists yet.

### kite_client.py (confirmed)
- `get_historical()` supports `interval="day"` ONLY.
- SQLite cache table `ohlcv_cache` uses `PRIMARY KEY (ticker, date)`.
  This schema is incompatible with intraday candles (multiple rows
  per ticker per date). DO NOT modify this table.
- A NEW table `intraday_cache` must be created for 15-minute candles
  with `PRIMARY KEY (ticker, datetime)`.
- A NEW method `get_intraday()` must be added alongside the existing
  `get_historical()`. Do not modify `get_historical()`.

### main.py (confirmed)
- APScheduler instance is named `scheduler`, timezone Asia/Kolkata.
- `run_screener()` is the existing swing function. Do not rename it.
- `post_login_initialization()` ends with `await run_screener()`.
  The new `run_momentum_screener()` must also be awaited at the end
  of `post_login_initialization()` — after `run_screener()`.
- Regime filter currently sets `"BEAR"` and returns early. The new
  `"BEAR_RS_ONLY"` state requires modifying this logic without
  breaking the existing BULL/CAUTION path.
- `/token` endpoint calls `post_login_initialization()` — this is
  the ignition switch. Do not change its trigger.

### models.py (confirmed)
- `OpenPosition.source` is `Literal["SYSTEM", "MANUAL"]`.
  `"MOMENTUM"` must be added: `Literal["SYSTEM", "MANUAL", "MOMENTUM"]`.
- `Signal` model has no `strategy_type` field. It must be added as
  `Optional[Literal["SWING", "MOMENTUM"]] = "SWING"` to preserve
  backward compatibility with Container A and Container C.
- `PortfolioResponse.market_regime` must add `"BEAR_RS_ONLY"` to
  its Literal type.

### position_tracker.py (confirmed)
- DB table `positions` has a `source TEXT` column. ✓ No migration
  needed for the column — only the Pydantic Literal needs updating.
- `update_daily_positions()` processes ALL open positions regardless
  of source. The new momentum auto-square logic must run BEFORE this
  function's general update loop, not inside it, at 15:15 IST.
- Cost model: `costs = (entry + exit) * shares * 0.001`. Replace
  with accurate Zerodha model for both SWING and MOMENTUM.

### portfolio.py (confirmed)
- `filter_and_allocate()` takes `List[Dict]` signals.
- Momentum signals need a SEPARATE allocator `filter_momentum_signals()`
  that enforces the momentum capital pool (20% of bankroll dynamic).
  Do NOT route momentum signals through `filter_and_allocate()`.

### performance.py (confirmed)
- CB4 is commented out and must stay commented out. ✓
- `check_circuit_breakers()` is called before every screener run.
  The momentum screener must also call it before every hourly scan.

### agent.py (confirmed)
- Gemini integration is FULLY WORKING with `response_schema=SignalOutput`
  and `temperature=0.0`. The prompt string is the target of Phase 3.
- `run_pipeline()` polls `/signals` and processes swing signals.
  A new `run_momentum_pipeline()` must be added for intraday signals.
- `processed_signals_today` deduplication set uses ticker as key.
  Momentum signals use `f"{ticker}_MOM"` as key to avoid collisions
  with same-day swing signals for the same stock (swing wins rule).
- Schedule uses `getattr(schedule.every(), day).at(...).do(...)`.
  All new momentum schedule jobs MUST use this exact pattern.
  DO NOT use `schedule.every().monday.at(...).do(...)` — Known Quirk Q3.

════════════════════════════════════════════════════════════════════════
## SECTION 1 — CAPITAL ARCHITECTURE
════════════════════════════════════════════════════════════════════════

### Bankroll Segregation
  total_bankroll          = current_bankroll()   ← from bankroll_ledger
  momentum_pool           = total_bankroll × 0.20   ← dynamic, recalcs
  swing_pool              = total_bankroll × 0.80   ← dynamic, recalcs

Both pools recalculate from the live bankroll every time a screener
runs. If bankroll grows to ₹6,700, momentum pool = ₹1,340 automatically.
If bankroll drops to ₹4,200, momentum pool = ₹840 automatically.

### Risk Per Trade
  swing_risk_per_trade    = swing_pool × 0.01
  momentum_risk_per_trade = momentum_pool × 0.01

At ₹5,000 starting bankroll:
  swing risk    = ₹4,000 × 0.01 = ₹40 per trade
  momentum risk = ₹1,000 × 0.01 = ₹10 per trade

### Momentum Pool Freeze
  IF total_bankroll < initial_bankroll × 0.80 (₹4,000 at start):
    freeze momentum pool entirely
    log event_type="momentum_pool_frozen", reason="bankroll_floor"
    momentum screener returns early with no signals

### Position Limits
  MAX_SWING_POSITIONS     = 4   ← unchanged, env: MAX_OPEN_POSITIONS
  MAX_MOMENTUM_POSITIONS  = 2   ← new, env: MAX_MOMENTUM_POSITIONS=2
  (2 momentum positions × ₹10 risk = ₹20 max momentum exposure)

════════════════════════════════════════════════════════════════════════
## SECTION 2 — ACCURATE ZERODHA COST MODEL
════════════════════════════════════════════════════════════════════════

Replace the existing `cost_per_side = c * shares * 0.001` approximation
in BOTH `engine.py` and `position_tracker.py` with this exact model.
Implement as a pure function in `engine.py`. Import it everywhere needed.

```python
def calc_zerodha_costs(
    entry_price: float,
    exit_price: float,
    shares: int,
    is_intraday: bool
) -> float:
    """
    Accurate Zerodha cost model for NSE equity trades.
    
    Delivery (CNC): STT on sell side only (0.1%)
    Intraday (MIS): STT on sell side only (0.025%)
    
    Returns total round-trip cost in rupees.
    """
    buy_value  = entry_price * shares
    sell_value = exit_price  * shares

    # Brokerage: min(0.03% of turnover, ₹20) per executed order
    brokerage_buy  = min(buy_value  * 0.0003, 20.0)
    brokerage_sell = min(sell_value * 0.0003, 20.0)

    # STT (Securities Transaction Tax) — sell side only
    stt_rate = 0.00025 if is_intraday else 0.001
    stt = sell_value * stt_rate

    # Exchange transaction charges (NSE): 0.00345% both sides
    exchange_txn = (buy_value + sell_value) * 0.0000345

    # Stamp duty: 0.015% on buy side only
    stamp_duty = buy_value * 0.00015

    # SEBI turnover fee: ₹10 per crore = 0.0001% both sides
    sebi = (buy_value + sell_value) * 0.000001

    # GST: 18% on (brokerage + exchange charges)
    gst = (brokerage_buy + brokerage_sell + exchange_txn) * 0.18

    total = (brokerage_buy + brokerage_sell + stt +
             exchange_txn + stamp_duty + sebi + gst)

    return round(total, 4)
```

### Cost viability gate for momentum signals
```python
def is_cost_viable(
    entry_price: float,
    shares: int,
    risk_per_trade: float,
    r_target: float = 2.0,
    max_cost_ratio: float = 0.25,
    is_intraday: bool = True
) -> tuple[bool, float]:
    """
    Rejects momentum trades where costs eat >25% of expected profit.
    Uses estimated exit at r_target × R above entry.
    Returns (is_viable, cost_ratio).
    """
    r_distance     = risk_per_trade / shares   # stop distance per share
    estimated_exit = entry_price + (r_target * r_distance)
    total_cost     = calc_zerodha_costs(
        entry_price, estimated_exit, shares, is_intraday
    )
    expected_gross = risk_per_trade * r_target
    cost_ratio     = total_cost / expected_gross if expected_gross > 0 else 1.0
    return cost_ratio <= max_cost_ratio, round(cost_ratio, 4)
```

Update `evaluate_signal()` in `engine.py` to use `calc_zerodha_costs()`
with `is_intraday=False` instead of the current `0.001` approximation.
Update `update_daily_positions()` in `position_tracker.py` the same way.

════════════════════════════════════════════════════════════════════════
## SECTION 3 — PHASE 1: RELATIVE STRENGTH MODULE
════════════════════════════════════════════════════════════════════════

### 3.1 New pure functions in engine.py

Add BELOW existing indicator functions. Do not modify anything above.

```python
def calc_relative_strength(
    stock_close: pd.Series,
    nifty_close: pd.Series,
    periods: int = 20
) -> float:
    """
    [RS1] Relative Strength vs Nifty 50 over N periods.
    RS = stock_return_pct - nifty_return_pct over last `periods` bars.
    Positive RS = stock outperforming Nifty.
    """
    if len(stock_close) < periods + 1 or len(nifty_close) < periods + 1:
        return -999.0   # sentinel: insufficient data

    stock_return = (stock_close.iloc[-1] - stock_close.iloc[-periods]) \
                   / stock_close.iloc[-periods] * 100
    nifty_return = (nifty_close.iloc[-1] - nifty_close.iloc[-periods]) \
                   / nifty_close.iloc[-periods] * 100

    return round(stock_return - nifty_return, 4)


def calc_volume_consistency(volume: pd.Series, n_days: int = 5,
                            lookback: int = 20) -> bool:
    """
    [RS2] Volume Consistency check.
    Returns True if volume exceeded 20-day average on at least
    3 of the last 5 completed sessions (excludes today).
    """
    if len(volume) < lookback + n_days + 1:
        return False

    avg_vol = volume.iloc[-(lookback + n_days + 1):-(n_days + 1)].mean()
    recent_vols = volume.iloc[-(n_days + 1):-1]   # last 5 completed sessions

    days_above = sum(1 for v in recent_vols if v > avg_vol)
    return days_above >= 3
```

### 3.2 Regime filter update in main.py

Replace the existing regime block in `run_screener()`:

```python
# CURRENT (replace this):
if nifty_close < nifty_ema50:
    market_regime = "BEAR"
    logger.info("regime_filter", regime="BEAR", reason="Nifty below EMA50")
    return

# NEW (replace with this):
if nifty_close < nifty_ema50:
    market_regime = "BEAR_RS_ONLY"
    logger.info("regime_filter", regime="BEAR_RS_ONLY",
                reason="Nifty below EMA50 — switching to RS-only mode")
    # DO NOT return early — fall through to screener loop
    # The screener loop will apply RS filters based on market_regime
elif nifty_close < nifty_ema50 * 1.02:
    market_regime = "CAUTION"
else:
    market_regime = "BULL"
```

Update `PortfolioResponse.market_regime` Literal in `models.py`:
```python
market_regime: Literal["BULL", "CAUTION", "BEAR_RS_ONLY", "UNKNOWN"]
```

### 3.3 Screener loop modification in main.py

Inside `run_screener()`, after `evaluate_signal()` returns `valid=True`,
add the RS filter block BEFORE appending to `raw_signals`:

```python
valid, sig_data = evaluate_signal(ticker, df, bankroll, risk_pct)
if not valid:
    continue

# [RS-FILTER] BEAR_RS_ONLY regime: apply RS gate
if market_regime == "BEAR_RS_ONLY":
    rs_score = calc_relative_strength(df['close'], nifty_df['close'])
    vol_consistent = calc_volume_consistency(df['volume'])

    if rs_score < 5.0:
        logger.info("rs_filter_reject", ticker=ticker,
                    rs=rs_score, reason="RS below 5.0 in BEAR regime")
        continue

    if not vol_consistent:
        logger.info("rs_filter_reject", ticker=ticker,
                    reason="Volume inconsistency in BEAR regime")
        continue

    sig_data['rs_score'] = rs_score
    sig_data['volume_consistent'] = vol_consistent
    logger.info("rs_filter_pass", ticker=ticker, rs=rs_score)
else:
    sig_data['rs_score'] = calc_relative_strength(df['close'], nifty_df['close'])
    sig_data['volume_consistent'] = calc_volume_consistency(df['volume'])

# SWING WINS: skip if this ticker already has an open momentum position
open_momentum_tickers = {
    p['ticker'] for p in open_pos if p.get('source') == 'MOMENTUM'
}
if ticker in open_momentum_tickers:
    logger.info("swing_priority", ticker=ticker,
                reason="Momentum position already open — swing wins")
    continue

sig_data['strategy_type'] = 'SWING'
raw_signals.append(sig_data)
```

### 3.4 RS regime mathematical justification (for code comments)

In BEAR_RS_ONLY regime, `[C1]` (stock > EMA200 AND EMA50 > EMA200) is
REPLACED by RS > 5.0. All other conditions [C2]–[C8] still apply.

Rationale: A stock below its EMA200 is in a downtrend in absolute
terms. However if it has outperformed the Nifty by 5%+ over 20 days
while the market fell, institutional accumulation is the most probable
explanation. This is a relative strength play, not a trend-following
play. The stock must still be near its own 21-EMA support [C2], have
volume confirmation [C3], not be overbought [C4], be liquid [C6],
and have a positive short-term slope [C7] — because even a strong RS
stock must show positive near-term momentum to be a valid entry.

### 3.5 Add rs_score and volume_consistent to Signal model (models.py)

```python
class Signal(BaseModel):
    # ... existing fields unchanged ...
    strategy_type: Optional[Literal["SWING", "MOMENTUM"]] = "SWING"
    rs_score: Optional[float] = None
    volume_consistent: Optional[bool] = None
    cost_ratio: Optional[float] = None   # for momentum signals
```

### 3.6 pytest tests — python-engine/tests/test_engine.py

Create `python-engine/tests/__init__.py` (empty).
Create `python-engine/tests/test_engine.py`:

```python
"""
Tests for V2.0 engine additions.
Run: pytest python-engine/tests/test_engine.py -v
All tests use dummy DataFrames. No API calls. No mocking of math.
"""
import pytest
import pandas as pd
import numpy as np
from engine import (
    calc_relative_strength,
    calc_volume_consistency,
    calc_zerodha_costs,
    is_cost_viable,
    calc_vwap,
    evaluate_momentum_signal,
)


# ── RS Tests ─────────────────────────────────────────────────────────

def make_price_series(start: float, pct_change: float,
                      periods: int = 25) -> pd.Series:
    """Helper: create a price series with a fixed % change over periods."""
    end = start * (1 + pct_change / 100)
    prices = np.linspace(start, end, periods)
    return pd.Series(prices)


def test_relative_strength_stock_outperforms():
    """
    Nifty drops 10%, stock gains 2%.
    RS = 2 - (-10) = 12. Must be > 5.0.
    """
    stock = make_price_series(100, +2.0)
    nifty = make_price_series(18000, -10.0)
    rs = calc_relative_strength(stock, nifty, periods=20)
    assert rs > 5.0, f"Expected RS > 5.0, got {rs}"
    assert abs(rs - 12.0) < 0.5, f"Expected RS ~12.0, got {rs}"


def test_relative_strength_stock_underperforms():
    """Stock drops with Nifty. RS must be <= 0."""
    stock = make_price_series(100, -8.0)
    nifty = make_price_series(18000, -5.0)
    rs = calc_relative_strength(stock, nifty, periods=20)
    assert rs <= 0.0, f"Expected RS <= 0, got {rs}"


def test_relative_strength_insufficient_data():
    """Fewer than periods+1 bars returns sentinel -999.0."""
    stock = pd.Series([100.0, 102.0])
    nifty = pd.Series([18000.0, 18100.0])
    rs = calc_relative_strength(stock, nifty, periods=20)
    assert rs == -999.0


def test_volume_consistency_passes():
    """Volume above average on 4 of last 5 days — should pass."""
    avg = 100_000
    volume = pd.Series(
        [avg] * 20 +          # 20-day baseline
        [avg * 2] * 4 +       # 4 days above average
        [avg * 0.5]           # 1 day below
    )
    assert calc_volume_consistency(volume) is True


def test_volume_consistency_fails():
    """Volume above average on only 1 of last 5 days — should fail."""
    avg = 100_000
    volume = pd.Series(
        [avg] * 20 +
        [avg * 0.5] * 4 +
        [avg * 2]
    )
    assert calc_volume_consistency(volume) is False


# ── Cost Model Tests ─────────────────────────────────────────────────

def test_zerodha_costs_delivery_positive():
    """Round-trip delivery costs must be positive and non-zero."""
    cost = calc_zerodha_costs(500.0, 525.0, 10, is_intraday=False)
    assert cost > 0
    assert cost < 50   # sanity: costs should not exceed trade value


def test_zerodha_costs_intraday_lower_stt():
    """Intraday STT (0.025%) must be lower than delivery STT (0.1%)."""
    cost_intraday  = calc_zerodha_costs(500.0, 510.0, 10, is_intraday=True)
    cost_delivery  = calc_zerodha_costs(500.0, 510.0, 10, is_intraday=False)
    assert cost_intraday < cost_delivery


def test_cost_viable_rejects_when_ratio_exceeds_threshold():
    """
    Very small position where costs eat > 25% of expected profit.
    Should return is_viable=False.
    """
    # Tiny position: 1 share at ₹50, risk = ₹0.50
    viable, ratio = is_cost_viable(
        entry_price=50.0, shares=1,
        risk_per_trade=0.5, r_target=2.0,
        max_cost_ratio=0.25, is_intraday=True
    )
    # Expected profit = 0.5 * 2.0 = ₹1.0
    # Costs on 1 share ≈ ₹0.30+ which is >25% of ₹1.0
    assert viable is False


def test_cost_viable_accepts_normal_position():
    """Normal momentum position at ₹10 risk should be viable."""
    # ₹500 position, ₹10 risk, 2R target = ₹20 gross profit
    viable, ratio = is_cost_viable(
        entry_price=500.0, shares=10,
        risk_per_trade=10.0, r_target=2.0,
        max_cost_ratio=0.25, is_intraday=True
    )
    assert viable is True
    assert ratio < 0.25


# ── VWAP Tests ───────────────────────────────────────────────────────

def make_intraday_df(n_candles: int = 10) -> pd.DataFrame:
    """Helper: generate synthetic 15-min intraday candles."""
    base = 1000.0
    data = {
        'open':   [base + i for i in range(n_candles)],
        'high':   [base + i + 5 for i in range(n_candles)],
        'low':    [base + i - 5 for i in range(n_candles)],
        'close':  [base + i + 2 for i in range(n_candles)],
        'volume': [100_000 + i * 10_000 for i in range(n_candles)],
    }
    return pd.DataFrame(data)


def test_vwap_increases_with_price():
    """VWAP of a monotonically increasing price series must increase."""
    df = make_intraday_df(10)
    vwap_series = calc_vwap(df)
    assert vwap_series.iloc[-1] > vwap_series.iloc[0]


def test_vwap_length_matches_input():
    """VWAP series must have same length as input DataFrame."""
    df = make_intraday_df(8)
    vwap_series = calc_vwap(df)
    assert len(vwap_series) == len(df)


def test_vwap_all_positive():
    """All VWAP values must be positive for positive price inputs."""
    df = make_intraday_df(8)
    vwap_series = calc_vwap(df)
    assert (vwap_series > 0).all()


# ── Momentum Signal Integration Test ─────────────────────────────────

def test_momentum_signal_rejects_below_vwap():
    """
    If current price is below VWAP, momentum signal must not fire.
    """
    df = make_intraday_df(10)
    # Force close of last candle well below VWAP
    df.loc[df.index[-1], 'close'] = 900.0

    prev_day_high = 950.0
    bankroll = 5000.0

    fired, result = evaluate_momentum_signal(
        ticker="TEST", df=df,
        prev_day_high=prev_day_high,
        bankroll=bankroll,
        momentum_pool=1000.0
    )
    assert fired is False


def test_momentum_signal_insufficient_data():
    """
    Fewer than MIN_MOMENTUM_CANDLES returns False.
    """
    df = make_intraday_df(3)   # below minimum of 4
    fired, result = evaluate_momentum_signal(
        ticker="TEST", df=df,
        prev_day_high=1000.0,
        bankroll=5000.0,
        momentum_pool=1000.0
    )
    assert fired is False
```

**ENFORCEMENT RULE:** All tests in this file must PASS before any
changes to `main.py`, `portfolio.py`, or `position_tracker.py` are
made. Run: `pytest python-engine/tests/test_engine.py -v --tb=short`

════════════════════════════════════════════════════════════════════════
## SECTION 4 — PHASE 2: HOURLY MOMENTUM SCANNER
════════════════════════════════════════════════════════════════════════

### 4.1 kite_client.py — add intraday cache and get_intraday()

Add a NEW SQLite table. Do NOT modify `ohlcv_cache`:

```python
async def _init_intraday_db(self):
    async with aiosqlite.connect(self.db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS intraday_cache (
                ticker   TEXT,
                datetime TEXT,
                open     REAL,
                high     REAL,
                low      REAL,
                close    REAL,
                volume   INTEGER,
                fetched_at TIMESTAMP,
                PRIMARY KEY (ticker, datetime)
            )
        """)
        await db.commit()
```

Add a NEW method `get_intraday()` alongside `get_historical()`.
Do NOT modify `get_historical()`:

```python
async def get_intraday(
    self,
    ticker: str,
    from_datetime: str,
    to_datetime: str,
    interval: str = "15minute"
) -> pd.DataFrame:
    """
    Fetch intraday candles (15-minute default).
    Cache TTL: current trading day only.
    Cache is invalidated at next day's 00:00 IST.
    
    from_datetime / to_datetime format: "YYYY-MM-DD HH:MM:SS"
    """
    await self._init_intraday_db()
    trade_date = from_datetime[:10]   # YYYY-MM-DD portion

    # Check cache: only use if all rows are from today
    async with aiosqlite.connect(self.db_path) as db:
        cursor = await db.execute(
            """SELECT datetime, open, high, low, close, volume
               FROM intraday_cache
               WHERE ticker=? AND datetime >= ? AND datetime <= ?
               ORDER BY datetime""",
            (ticker, from_datetime, to_datetime)
        )
        rows = await cursor.fetchall()
        if rows and len(rows) >= 4:   # minimum 4 candles for VWAP
            logger.info("data_fetch", event_type="intraday_cache_hit",
                        ticker=ticker, candles=len(rows))
            df = pd.DataFrame(
                rows, columns=['datetime','open','high','low','close','volume']
            )
            df['datetime'] = pd.to_datetime(df['datetime'])
            df.set_index('datetime', inplace=True)
            return df

    # Cache miss → API
    logger.info("data_fetch", event_type="intraday_cache_miss", ticker=ticker)
    instrument_token = self.instrument_cache.get(ticker)
    if not instrument_token:
        raise ValueError(f"Unknown ticker: {ticker}")

    for attempt in range(5):
        await self.limiter.acquire()
        try:
            resp = await self.client.get(
                f"/instruments/historical/{instrument_token}/{interval}",
                params={"from": from_datetime, "to": to_datetime}
            )
            resp.raise_for_status()
            data = resp.json().get("data", {}).get("candles", [])
            if not data:
                return pd.DataFrame()

            df = pd.DataFrame(
                data, columns=['datetime','open','high','low','close','volume']
            )
            df['datetime'] = pd.to_datetime(df['datetime']).dt.tz_localize(None)

            # Write to intraday cache
            async with aiosqlite.connect(self.db_path) as db:
                for _, row in df.iterrows():
                    await db.execute(
                        """INSERT OR REPLACE INTO intraday_cache
                           (ticker, datetime, open, high, low, close,
                            volume, fetched_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                        (ticker,
                         row['datetime'].strftime("%Y-%m-%d %H:%M:%S"),
                         row['open'], row['high'], row['low'],
                         row['close'], row['volume'])
                    )
                await db.commit()

            df.set_index('datetime', inplace=True)
            return df

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 503):
                await asyncio.sleep(2 ** attempt)
                continue
            raise
        except httpx.RequestError:
            await asyncio.sleep(2 ** attempt)
            continue

    logger.error("max_retries_exceeded_intraday", ticker=ticker)
    return pd.DataFrame()
```

Add an intraday cache cleanup job in `main.py` startup:
```python
scheduler.add_job(
    kite.clear_intraday_cache,
    'cron', hour=0, minute=5
)
```

And the cleanup method in `kite_client.py`:
```python
async def clear_intraday_cache(self):
    """Purge yesterday's intraday candles at midnight."""
    from datetime import datetime, timedelta
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    async with aiosqlite.connect(self.db_path) as db:
        await db.execute(
            "DELETE FROM intraday_cache WHERE datetime < ?",
            (yesterday + " 23:59:59",)
        )
        await db.commit()
    logger.info("intraday_cache_cleared", before=yesterday)
```

### 4.2 New pure functions in engine.py

Add BELOW the RS functions from Section 3.

```python
def calc_vwap(df: pd.DataFrame) -> pd.Series:
    """
    [MOM1] VWAP calculation for intraday candles.
    VWAP = cumsum(typical_price × volume) / cumsum(volume)
    Typical price = (high + low + close) / 3
    Resets at start of each day — caller must pass only today's candles.
    df must have columns: high, low, close, volume
    Returns pd.Series indexed same as df.
    """
    typical_price  = (df['high'] + df['low'] + df['close']) / 3
    cumulative_tpv = (typical_price * df['volume']).cumsum()
    cumulative_vol = df['volume'].cumsum()
    vwap = cumulative_tpv / cumulative_vol
    return vwap


def evaluate_momentum_signal(
    ticker: str,
    df: pd.DataFrame,
    prev_day_high: float,
    bankroll: float,
    momentum_pool: float,
    min_candles: int = 4
) -> tuple[bool, dict]:
    """
    [MOM2] Intraday momentum signal evaluation.
    df must contain ONLY today's 15-minute candles (VWAP resets daily).
    
    Entry conditions (ALL must be true):
      [MC1] Minimum candles: len(df) >= min_candles
      [MC2] Price crossed ABOVE VWAP in the LAST candle
            (prev candle close was below VWAP, current close is above)
      [MC3] Last candle volume >= 300% of previous 10-candle avg volume
      [MC4] Current close > prev_day_high (structural breakout)
    
    Risk:
      [MR1] Stop loss = low of the breakout candle (last candle)
      [MR2] Target = entry + 2.0R
      [MR3] Product type decision: MIS if position_value < ₹5,000,
            CNC if position_value >= ₹5,000 (for this bankroll, will
            almost always be MIS — system squares at 3:15pm either way)
    """
    if len(df) < min_candles:
        return False, {}

    df = df.copy()
    vwap = calc_vwap(df)

    current_close = df['close'].iloc[-1]
    prev_close    = df['close'].iloc[-2]
    current_vwap  = vwap.iloc[-1]
    prev_vwap     = vwap.iloc[-2]

    # [MC2] VWAP crossover: was below, now above
    if not (prev_close <= prev_vwap and current_close > current_vwap):
        return False, {}

    # [MC3] Volume surge: 300% of 10-candle average
    if len(df) < 11:
        return False, {}
    avg_vol_10 = df['volume'].iloc[-11:-1].mean()
    if avg_vol_10 == 0:
        return False, {}
    current_vol = df['volume'].iloc[-1]
    vol_ratio_intraday = current_vol / avg_vol_10
    if vol_ratio_intraday < 3.0:
        return False, {}

    # [MC4] Structural breakout: above previous day's high
    if current_close <= prev_day_high:
        return False, {}

    # [MR1] Stop loss = low of breakout candle
    breakout_candle_low = df['low'].iloc[-1]
    stop_loss = breakout_candle_low

    risk_per_share = current_close - stop_loss
    if risk_per_share <= 0:
        return False, {}

    # Position sizing: 1% of momentum pool
    momentum_risk = momentum_pool * 0.01
    shares = math.floor(momentum_risk / risk_per_share)
    if shares == 0:
        return False, {}

    position_value = shares * current_close
    if position_value > momentum_pool:
        return False, {}

    # [MR2] Target: 2.0R
    r_distance = current_close - stop_loss
    target     = current_close + (2.0 * r_distance)

    # [MR3] Product type decision
    product_type = "MIS" if position_value < 5000 else "CNC"

    # Cost viability check
    viable, cost_ratio = is_cost_viable(
        entry_price=current_close, shares=shares,
        risk_per_trade=momentum_risk, r_target=2.0,
        max_cost_ratio=0.25, is_intraday=True
    )
    if not viable:
        return False, {}

    # Accurate cost for net_ev
    estimated_exit = current_close + (2.0 * r_distance)
    total_cost = calc_zerodha_costs(
        current_close, estimated_exit, shares, is_intraday=True
    )
    net_ev = (momentum_risk * 2.0) - total_cost
    if net_ev <= 0:
        return False, {}

    result = {
        "close":               round(current_close, 2),
        "vwap":                round(current_vwap, 2),
        "prev_day_high":       round(prev_day_high, 2),
        "stop_loss":           round(stop_loss, 2),
        "target_1":            round(target, 2),
        "target_2":            round(target, 2),   # single target for momentum
        "trailing_stop":       round(stop_loss, 2),
        "shares":              shares,
        "capital_deployed":    round(position_value, 2),
        "capital_at_risk":     round(shares * risk_per_share, 2),
        "net_ev":              round(net_ev, 2),
        "cost_ratio":          cost_ratio,
        "volume_ratio":        round(vol_ratio_intraday, 2),
        "product_type":        product_type,
        "strategy_type":       "MOMENTUM",
    }
    return True, result
```

### 4.3 New MomentumSignal model in models.py

```python
class MomentumSignal(BaseModel):
    """Intraday momentum signal. Subset of Signal fields."""
    ticker:            str
    exchange:          str = "NSE"
    signal_time:       datetime
    strategy_type:     Literal["MOMENTUM"] = "MOMENTUM"
    close:             float
    vwap:              float
    prev_day_high:     float
    stop_loss:         float
    target_1:          float
    trailing_stop:     float
    shares:            int
    capital_deployed:  float
    capital_at_risk:   float
    net_ev:            float
    cost_ratio:        float
    volume_ratio:      float
    product_type:      Literal["MIS", "CNC"]
    sector:            str = "UNKNOWN"
    portfolio_slot:    Optional[int] = None
    stale_data:        bool = False
    strategy_version:  str

    _round_2dp = field_validator(
        "close", "vwap", "prev_day_high", "stop_loss", "target_1",
        "trailing_stop", "capital_deployed", "capital_at_risk",
        "net_ev", "cost_ratio", "volume_ratio", mode="after"
    )(round_float_2dp)
```

Add to `PortfolioResponse`:
```python
momentum_signals: List[MomentumSignal] = []
momentum_pool:    float = 0.0
```

### 4.4 Momentum allocator in portfolio.py

Add as a NEW function. Do NOT modify `filter_and_allocate()`:

```python
def filter_momentum_signals(
    signals: List[Dict],
    open_momentum_positions: List[Dict],
    momentum_pool: float,
    max_momentum_positions: int = 2
) -> tuple[List[MomentumSignal], List[Dict]]:
    """
    Second-pass allocator for momentum signals.
    Enforces momentum capital pool limits independently from swing.
    """
    from models import MomentumSignal
    accepted = []
    rejected = []

    remaining_slots = max_momentum_positions - len(open_momentum_positions)
    deployed_pool   = sum(
        p['entry_price'] * p['shares'] for p in open_momentum_positions
    )

    # Sort by net_ev DESC, then volume_ratio DESC
    valid = sorted(
        [s for s in signals if s.get('net_ev', 0) > 0],
        key=lambda x: (x['net_ev'], x['volume_ratio']),
        reverse=True
    )

    for sig in valid:
        if remaining_slots <= 0:
            sig['reject_reason'] = "MAX_MOMENTUM_POSITIONS"
            rejected.append(sig)
            continue

        ticker = sig['ticker']
        if any(p['ticker'] == ticker for p in open_momentum_positions):
            sig['reject_reason'] = "MOMENTUM_ALREADY_OPEN"
            rejected.append(sig)
            continue

        if deployed_pool + sig['capital_deployed'] > momentum_pool:
            sig['reject_reason'] = "MOMENTUM_POOL_EXHAUSTED"
            rejected.append(sig)
            continue

        deployed_pool   += sig['capital_deployed']
        remaining_slots -= 1
        sig['portfolio_slot'] = max_momentum_positions - remaining_slots
        accepted.append(MomentumSignal(**sig))

    return accepted, rejected
```

### 4.5 run_momentum_screener() in main.py

Add as a NEW async function. Do NOT modify `run_screener()`:

```python
async def run_momentum_screener():
    """
    Hourly intraday momentum scanner.
    Runs from 10:15 IST to 14:15 IST at :15 of each hour.
    Uses Nifty 100 universe filtered from the Nifty 500 CSV
    (momentum requires liquid, fast-moving stocks).
    Full Nifty 500 scanned: lag accepted by design.
    """
    global current_momentum_signals

    today = datetime.utcnow().date()
    if not await is_trading_day(today, settings.DB_PATH):
        return

    halted, reasons = await check_circuit_breakers(settings.DB_PATH)
    if halted:
        logger.warning("momentum_screener_halted", reasons=reasons)
        return

    bankroll       = await current_bankroll(settings.DB_PATH)
    momentum_pool  = bankroll * 0.20

    # Momentum pool freeze check
    if bankroll < settings.INITIAL_BANKROLL * 0.80:
        logger.warning("momentum_pool_frozen",
                       bankroll=bankroll,
                       threshold=settings.INITIAL_BANKROLL * 0.80)
        return

    from_dt = f"{today.strftime('%Y-%m-%d')} 09:15:00"
    to_dt   = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    try:
        universe = pd.read_csv(settings.UNIVERSE_PATH)
    except Exception:
        logger.warning("universe_csv_missing_fallback_momentum")
        universe = pd.DataFrame({
            "tradingsymbol": ["RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK"],
            "exchange":      ["NSE"] * 5,
            "sector":        ["Energy","IT","Financial","IT","Financial"]
        })

    open_pos          = await get_open_positions(settings.DB_PATH)
    open_momentum_pos = [p for p in open_pos if p.get('source') == 'MOMENTUM']
    open_swing_tickers = {
        p['ticker'] for p in open_pos if p.get('source') != 'MOMENTUM'
    }

    raw_momentum = []

    for _, row in universe.iterrows():
        ticker = row['tradingsymbol']

        # SWING WINS: skip if swing position open for this ticker
        if ticker in open_swing_tickers:
            continue

        try:
            # Get today's intraday candles
            df_intra = await kite.get_intraday(ticker, from_dt, to_dt)
            if df_intra.empty or len(df_intra) < 4:
                continue

            # Get previous day's high from daily cache
            yesterday = (today - pd.Timedelta(days=3)).strftime("%Y-%m-%d")
            df_daily  = await kite.get_historical(
                ticker, yesterday, today.strftime("%Y-%m-%d")
            )
            if df_daily.empty or len(df_daily) < 2:
                continue

            prev_day_high = float(df_daily['high'].iloc[-2])

            fired, sig_data = evaluate_momentum_signal(
                ticker=ticker,
                df=df_intra,
                prev_day_high=prev_day_high,
                bankroll=bankroll,
                momentum_pool=momentum_pool
            )

            if fired:
                sig_data.update({
                    "ticker":           ticker,
                    "exchange":         row.get('exchange', 'NSE'),
                    "sector":           row.get('sector', 'UNKNOWN'),
                    "signal_time":      datetime.utcnow(),
                    "strategy_version": settings.STRATEGY_VERSION,
                    "ema_21": 0.0, "ema_50": 0.0, "ema_200": 0.0,
                    "atr_14": 0.0, "rsi_14": 0.0, "slope_5": 0.0,
                    "target_2": sig_data["target_1"],
                })
                raw_momentum.append(sig_data)

        except Exception as e:
            logger.error("momentum_scan_error", ticker=ticker, error=str(e))
            continue   # NEVER crash the full scan on one ticker failure

    accepted, rejected_mom = filter_momentum_signals(
        raw_momentum, open_momentum_pos, momentum_pool,
        settings.MAX_MOMENTUM_POSITIONS
    )

    async with state_lock:
        current_momentum_signals = accepted

    logger.info("momentum_scan_complete",
                tickers_scanned=len(universe),
                signals_found=len(accepted))
```

Add to module-level shared state in `main.py`:
```python
current_momentum_signals = []
```

Update `post_login_initialization()` to await momentum screener:
```python
async def post_login_initialization():
    try:
        logger.info("running_post_login_setup")
        await kite.refresh_instrument_cache()
        df = await kite.get_historical(
            "RELIANCE", "2024-01-01",
            datetime.utcnow().strftime("%Y-%m-%d")
        )
        if not df.empty:
            await run_backtest(
                settings.DB_PATH, {"RELIANCE": df}, settings.STRATEGY_VERSION
            )
        await run_screener()           # existing swing screener
        await run_momentum_screener()  # NEW: momentum scan on login
    except Exception as e:
        logger.error("post_login_init_error", error=str(e))
```

### 4.6 Scheduler jobs for momentum in main.py

Add to `startup()` AFTER existing scheduler jobs. Do NOT modify them:

```python
# Momentum hourly jobs: 10:15 to 14:15 IST at :15 each hour
for hour in [10, 11, 12, 13, 14]:
    scheduler.add_job(
        run_momentum_screener, 'cron',
        hour=hour, minute=15,
        id=f"momentum_scan_{hour}15"
    )

# Intraday cache cleanup at midnight
scheduler.add_job(
    kite.clear_intraday_cache, 'cron',
    hour=0, minute=5, id="intraday_cache_cleanup"
)
```

### 4.7 Momentum signals endpoint in main.py (The developer has already done this no need to impliment this one)

Added a new endpoint. Do NOT modify `/signals`:
```python
@app.get("/momentum-signals")
async def get_momentum_signals():
    async with state_lock:
        bankroll      = await current_bankroll(settings.DB_PATH)
        momentum_pool = bankroll * 0.20
        halted, reasons = await check_circuit_breakers(settings.DB_PATH)

        for s in current_momentum_signals:
            s.stale_data = (
                datetime.utcnow() - s.signal_time
            ).total_seconds() > 1800   # 30 min stale for intraday

        return {
            "run_time":         last_run,
            "market_regime":    market_regime,
            "momentum_pool":    round(momentum_pool, 2),
            "trading_halted":   halted,
            "halt_reasons":     reasons,
            "signals":          current_momentum_signals
        }

```

════════════════════════════════════════════════════════════════════════
## SECTION 5 — PHASE 2B: 3:15 PM AUTO-SQUARE OFF
════════════════════════════════════════════════════════════════════════

### Architecture
Container B identifies open MOMENTUM positions at 15:15 IST.
Container B calls Container A's internal endpoint `POST /api/orders/square-off`.
Container A places the market order via Zerodha.
Container A syncs the close back to Container B via `POST /positions/close`.
Container B sends Telegram alert at 15:10 IST as a 5-minute warning.

### 5.1 New endpoint in Container B (main.py)

```python
@app.post("/positions/close")
async def close_position(request: Request):
    """
    Called by Container A after a square-off order is confirmed.
    Updates position status to CLOSED_MANUAL and records P&L.
    """
    data = await request.json()
    secret = request.headers.get("X-Internal-Secret", "")
    if secret != settings.INTERNAL_API_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")

    ticker     = data["ticker"]
    exit_price = float(data["exit_price"])
    order_id   = data.get("order_id", "")

    open_pos = await get_open_positions(settings.DB_PATH)
    pos = next((p for p in open_pos if p['ticker'] == ticker
                and p.get('source') == 'MOMENTUM'), None)
    if not pos:
        raise HTTPException(status_code=404,
                            detail=f"No open MOMENTUM position for {ticker}")

    gross = (exit_price - pos['entry_price']) * pos['shares']
    costs = calc_zerodha_costs(
        pos['entry_price'], exit_price, pos['shares'], is_intraday=True
    )
    realised_pnl = gross - costs
    risk_initial = (pos['entry_price'] - pos['stop_loss_initial']) * pos['shares']
    r_multiple   = realised_pnl / risk_initial if risk_initial > 0 else 0

    async with aiosqlite.connect(settings.DB_PATH) as db:
        await db.execute("""
            UPDATE positions
            SET status='CLOSED_MANUAL', exit_price=?, exit_date=?,
                realised_pnl=?, r_multiple=?
            WHERE ticker=? AND source='MOMENTUM' AND status='OPEN'
        """, (exit_price, datetime.utcnow().isoformat(),
              realised_pnl, r_multiple, ticker))
        await db.commit()

    await record_trade_close(settings.DB_PATH, ticker, realised_pnl)
    logger.info("momentum_position_closed", ticker=ticker,
                exit_price=exit_price, pnl=realised_pnl, r=r_multiple)

    return {"status": "closed", "ticker": ticker,
            "realised_pnl": round(realised_pnl, 2),
            "r_multiple":   round(r_multiple, 4)}
```

### 5.2 Auto-square job in main.py

```python
async def auto_square_momentum():
    """
    [AUTO-SQUARE] 15:15 IST: Square off all open MOMENTUM positions.
    Calls Container A's internal square-off API.
    Uses smart order selection based on P&L state and market conditions.
    """
    import httpx as _httpx

    open_pos = await get_open_positions(settings.DB_PATH)
    momentum_pos = [p for p in open_pos if p.get('source') == 'MOMENTUM']

    if not momentum_pos:
        logger.info("auto_square", event="no_momentum_positions")
        return

    container_a_url = settings.CONTAINER_A_URL

    for pos in momentum_pos:
        ticker = pos['ticker']
        try:
            # Fetch current LTP to decide order type
            ltp_resp = await _httpx.AsyncClient().get(
                f"{container_a_url}/api/orders/ltp",
                headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
                params={"ticker": ticker},
                timeout=5.0
            )
            ltp_data = ltp_resp.json()
            ltp = float(ltp_data.get("ltp", pos['entry_price']))

            current_pnl   = (ltp - pos['entry_price']) * pos['shares']
            is_profitable = current_pnl > 0

            # Smart order selection [as per user-confirmed factors]:
            # 1. In profit → limit order to protect gains
            # 2. After 15:00 IST → always market order (time constraint)
            # 3. Fast-moving stock (LTP far from entry) → market order
            # 4. Low liquidity → limit order to avoid slippage
            now_ist = datetime.utcnow()   # scheduler is IST-aware

            price_movement_pct = abs(ltp - pos['entry_price']) / pos['entry_price']
            is_fast_moving     = price_movement_pct > 0.02

            if is_profitable and not is_fast_moving:
                order_type  = "LIMIT"
                limit_price = round(ltp * 0.999, 2)  # 0.1% below LTP
            else:
                order_type  = "MARKET"
                limit_price = None

            payload = {
                "ticker":       ticker,
                "shares":       pos['shares'],
                "order_type":   order_type,
                "limit_price":  limit_price,
                "product_type": pos.get('product_type', 'MIS'),
                "reason":       "AUTO_SQUARE_EOD"
            }

            resp = await _httpx.AsyncClient().post(
                f"{container_a_url}/api/orders/square-off",
                json=payload,
                headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
                timeout=10.0
            )
            resp.raise_for_status()
            logger.info("auto_square_sent", ticker=ticker,
                        order_type=order_type, pnl_estimate=current_pnl)

        except Exception as e:
            logger.error("auto_square_failed", ticker=ticker, error=str(e))
            # On failure: send Telegram alert for manual intervention
            await _notify_telegram_square_off_failure(ticker, pos)


async def momentum_eod_warning():
    """15:10 IST: Send 5-minute warning before auto-square."""
    open_pos = await get_open_positions(settings.DB_PATH)
    momentum_pos = [p for p in open_pos if p.get('source') == 'MOMENTUM']
    if not momentum_pos:
        return

    tickers = ", ".join(p['ticker'] for p in momentum_pos)
    # Uses existing Telegram notification mechanism in Container A
    import httpx as _httpx
    try:
        await _httpx.AsyncClient().post(
            f"{settings.CONTAINER_A_URL}/api/internal/notify",
            json={"message": f"⚠️ AUTO-SQUARE in 5 min: {tickers}"},
            headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
            timeout=5.0
        )
    except Exception as e:
        logger.error("eod_warning_failed", error=str(e))
```

Add scheduler jobs for auto-square:
```python
scheduler.add_job(
    momentum_eod_warning, 'cron',
    hour=15, minute=10, id="momentum_eod_warning"
)
scheduler.add_job(
    auto_square_momentum, 'cron',
    hour=15, minute=15, id="momentum_auto_square"
)
```

### 5.3 Container A additions required (note for node-gateway)

Add to `routes/orders.js`:
```javascript
// POST /api/orders/square-off
// Called by Container B at 15:15 IST for momentum auto-square
// Auth: X-Internal-Secret header
// Body: { ticker, shares, order_type, limit_price, product_type, reason }
```

Add to `routes/orders.js`:
```javascript
// GET /api/orders/ltp?ticker=RELIANCE
// Called by Container B before square-off order type decision
// Auth: X-Internal-Secret header
// Returns: { ticker, ltp, timestamp }
```

Add to `server/`:
```javascript
// POST /api/internal/notify
// Auth: X-Internal-Secret header
// Body: { message: string }
// Forwards message to TELEGRAM_CHAT_ID
// Used for system alerts that originate in Container B
```

════════════════════════════════════════════════════════════════════════
## SECTION 6 — PHASE 3: AGENT INTELLIGENCE UPGRADE
════════════════════════════════════════════════════════════════════════

### 6.1 Updated Gemini prompt in agent.py

Replace the `prompt` string inside `analyze_with_gemini()`:

```python
prompt = f"""
You are a cynical, risk-first quantitative trading analyst.
Your job is NOT to find reasons to approve trades.
Your job is to find reasons to REJECT them.
Only approve a trade if the evidence is overwhelmingly clean.

═══════════════════════════════════════════
TRADE CONTEXT
═══════════════════════════════════════════
Strategy Type : {signal.get('strategy_type', 'SWING')}
Market Regime : {market_regime}
Ticker        : {ticker}
Entry Price   : ₹{price}
Stop Loss     : ₹{stop_loss}
Target        : ₹{target}
Net EV        : ₹{signal.get('net_ev', 'N/A')}
Score         : {signal.get('score', 'N/A')}/100
Volume Ratio  : {signal.get('volume_ratio', 'N/A')}x
RSI           : {signal.get('rsi_14', 'N/A')}
RS Score      : {signal.get('rs_score', 'N/A')} (vs Nifty, 20-day)

═══════════════════════════════════════════
REGIME-SPECIFIC INSTRUCTIONS
═══════════════════════════════════════════

IF regime is "BEAR_RS_ONLY":
  Be EXTREMELY cynical. The broad market is falling.
  This stock is only being evaluated because its math shows
  outperformance vs the Nifty. Your primary job here is to
  determine WHY it is outperforming:
  - Quiet institutional accumulation (VALID) → keep conviction high
  - Unverified rumour, single contract win, retail social media hype → 
    REDUCE conviction_score below 50 immediately
  - Short-covering rally in a falling stock → REDUCE below 40
  - If you cannot determine a credible structural reason from the
    sentiment data: REDUCE below 55

IF strategy is "MOMENTUM" (intraday):
  Evaluate whether the news/catalyst justifies a 3-hour sustained
  move, not just a 15-minute spike.
  - Genuine earnings beat, sector tailwind → conviction can be high
  - Single news headline with no follow-through evidence → max 65
  - No news at all (pure technical breakout) → max 70
  - Negative news despite price rising → REDUCE below 45

IF regime is "CAUTION":
  Apply the same cynicism as BEAR_RS_ONLY but one level less severe.
  Reduce all scores by 10 points before outputting.

IF regime is "BULL" and strategy is "SWING":
  Standard evaluation. Do not manufacture cynicism.
  Follow the contradiction check rules below.

═══════════════════════════════════════════
UNIVERSAL EVALUATION RULES
═══════════════════════════════════════════

1. CONTRADICTION CHECK:
   If sentiment reveals critical legal, regulatory, fraud,
   accounting irregularity, or catastrophic operational news
   that contradicts a long position: REDUCE below 35.

2. NO HALLUCINATION:
   Base rationale ONLY on the text provided.
   Do not invent news. Do not cite sources not in the data.
   If no sentiment data: say so explicitly in rationale.

3. DO NOT over-react to routine market news.
   Quarterly results in line with estimates = neutral.
   Standard analyst upgrades/downgrades = minor adjustment only.

4. SCORING SCALE:
   80-100 : Clean setup, sentiment confirms technicals
   60-79  : Acceptable, standard market risks present
   50-59  : Marginal, one significant concern exists
   0-49   : High risk of false positive, do not execute

═══════════════════════════════════════════
MULTI-SOURCE SENTIMENT DATA
═══════════════════════════════════════════
{sentiment_text if sentiment_text else
 "NO SENTIMENT DATA AVAILABLE. Evaluate on technicals only. "
 "Apply caution: absence of news for an active signal is unusual. "
 "Cap conviction at 70 unless regime is BULL."}

Respond in strict JSON matching the required schema.
No markdown. No explanation outside the JSON fields.
"""
```

### 6.2 Pass market_regime to analyze_with_gemini

Update the function signature:
```python
def analyze_with_gemini(
    signal: Dict,
    sentiment_text: str,
    market_regime: str = "UNKNOWN"
) -> Optional[Dict]:
```

Update `run_pipeline()` to fetch and pass regime:
```python
def run_pipeline():
    # Fetch regime from Container B health/signals endpoint
    try:
        resp = requests.get(
            QUANT_ENGINE_URL, timeout=10
        )
        data       = resp.json()
        signals    = data.get("signals", [])
        regime     = data.get("market_regime", "UNKNOWN")
    except Exception as e:
        logger.error(f"Failed to fetch signals: {e}")
        return

    for signal in signals:
        # ... existing deduplication ...
        analysis = analyze_with_gemini(signal, sentiment_text, regime)
```

### 6.3 New run_momentum_pipeline() in agent.py

Add alongside `run_pipeline()`. Uses `getattr` pattern — DO NOT change:

```python
MOMENTUM_ENGINE_URL = os.getenv(
    "QUANT_ENGINE_URL", "http://python-engine:8000"
).replace("/signals", "") + "/momentum-signals"

def run_momentum_pipeline():
    """Poll Container B momentum signals and process them."""
    logger.info("Starting momentum signal pipeline...")
    try:
        resp = requests.get(MOMENTUM_ENGINE_URL, timeout=10)
        resp.raise_for_status()
        data           = resp.json()
        signals        = data.get("signals", [])
        regime         = data.get("market_regime", "UNKNOWN")
        momentum_pool  = data.get("momentum_pool", 0)
    except Exception as e:
        logger.error(f"Failed to fetch momentum signals: {e}")
        return

    if not signals:
        return

    for signal in signals:
        ticker  = signal.get("ticker")
        sig_id  = f"{ticker}_MOM"   # prevent collision with swing dedup

        if not ticker:
            continue
        if sig_id in processed_signals_today:
            logger.info(f"Momentum signal {sig_id} already processed. Skipping.")
            continue

        sentiment_text = scrape_sentiment(ticker)
        analysis       = analyze_with_gemini(signal, sentiment_text, regime)

        if analysis and analysis.get('conviction_score', 0) < 60:
            logger.info(f"Momentum {ticker} skipped. Low conviction: "
                        f"{analysis.get('conviction_score')}")
            processed_signals_today.add(sig_id)
            continue

        send_momentum_telegram_alert(signal, analysis, momentum_pool)
        processed_signals_today.add(sig_id)
        time.sleep(2)
```

### 6.4 Momentum Telegram alert format in agent.py

```python
def send_momentum_telegram_alert(
    signal: Dict, analysis: Dict, momentum_pool: float
):
    """Distinct format from swing alerts — clearly labelled INTRADAY."""
    url    = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    ticker = signal.get("ticker", "UNKNOWN")
    price  = signal.get("close")
    target = signal.get("target_1")
    sl     = signal.get("stop_loss")
    vwap   = signal.get("vwap")
    ptype  = signal.get("product_type", "MIS")
    ratio  = signal.get("cost_ratio", 0)

    header = f"⚡ INTRADAY MOMENTUM: {ticker} ({ptype})"

    if not analysis:
        text = (f"{header}\n"
                f"Price: ₹{price} | VWAP: ₹{vwap}\n"
                f"Target: ₹{target} | SL: ₹{sl}\n"
                f"⚠️ AI analysis failed. Manual review required.\n"
                f"Auto-square at 15:15 IST.")
    else:
        text = (f"{header}\n\n"
                f"Entry: ₹{price} | VWAP: ₹{vwap}\n"
                f"Target: ₹{target} | SL: ₹{sl}\n"
                f"Cost ratio: {ratio:.1%} of expected profit\n"
                f"Conviction: {analysis.get('conviction_score')}/100\n\n"
                f"Pitch: {analysis.get('pitch', 'N/A')}\n"
                f"Risk: {analysis.get('risks', 'N/A')}\n\n"
                f"⚠️ INTRADAY: Auto-square at 15:15 IST regardless of P&L.")

    sig_id = f"{ticker}_MOM"[:40]
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ EXECUTE INTRADAY",
             "callback_data": json.dumps(
                 {"a": "EM", "i": sig_id}, separators=(',', ':')
             )},
            {"text": "❌ REJECT",
             "callback_data": json.dumps(
                 {"a": "R", "i": sig_id}, separators=(',', ':')
             )}
        ]]
    }
    payload = {
        "chat_id":      TELEGRAM_CHAT_ID,
        "text":         text,
        "parse_mode":   "Markdown",
        "reply_markup": json.dumps(keyboard)
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        res.raise_for_status()
        logger.info(f"Momentum Telegram sent: {ticker}")
    except Exception as e:
        logger.error(f"Momentum Telegram failed: {ticker}: {e}")
```

### 6.5 Schedule momentum pipeline in agent.py main()

Add inside `main()` using `getattr` pattern (Known Quirk Q3).
Add AFTER existing weekday schedule blocks. Do NOT modify them:

```python
    # Momentum pipeline: runs at :55 each hour to process signals
    # from the :15 scan (gives scan ~40 min to complete on Nifty 500)
    momentum_hours = ["10:55", "11:55", "12:55", "13:55", "14:55"]
    for day in days:
        for t in momentum_hours:
            getattr(schedule.every(), day).at(t).do(run_momentum_pipeline)
```

════════════════════════════════════════════════════════════════════════
## SECTION 7 — REGULATORY & COMPLIANCE REQUIREMENTS
════════════════════════════════════════════════════════════════════════

These are non-negotiable for live trading on NSE. The system must
enforce all of them in code, not just in documentation.

### SEBI Position Limits
  CNC (delivery) equity: No intraday leverage — position value cannot
  exceed available cash in Zerodha account. The system's capital pool
  limits (₹1,000 momentum, ₹4,000 swing) are well within this.

### Zerodha Product Type Rules
  MIS: Auto-squared at 15:15 IST by Zerodha if not closed manually.
       Use for momentum trades where position_value < ₹5,000.
       Leverage available but NOT used (full cash position only).
  CNC: Delivery. No auto-square. Used for swing trades.
       Must have sufficient free margin in account.
  NRML: For F&O only. PROHIBITED in this system. Never use.

### Order Tagging
  All orders placed by the system must use tag="QUANT_SENTINEL".
  This allows manual audit of bot orders in Zerodha Console.

### Brokerage Deduction Accuracy
  The `calc_zerodha_costs()` function is the single source of truth.
  It must be used for:
    - net_ev calculation in engine.py (pre-trade)
    - realised_pnl calculation in position_tracker.py (post-trade)
    - performance metrics in performance.py
  Never use the old 0.001 approximation anywhere in the codebase.

### STT Note (critical for P&L accuracy)
  STT is charged on the SELL side only for both CNC and MIS equity.
  STT rate: 0.1% for CNC delivery, 0.025% for MIS intraday.
  The formula in calc_zerodha_costs() implements this correctly.
  Do not modify these rates.

### Circuit Breaker Compliance
  NSE circuit breakers (market-wide): 10%, 15%, 20% index movement
  triggers market halt. The system cannot trade during NSE halts.
  The Zerodha API will return an error on order placement during halts.
  Container A must catch Zerodha `NetworkException` / `OrderException`
  during halts and log clearly without retrying more than once.

### Data Retention
  All trade records must be retained in SQLite indefinitely.
  Do not implement any automatic purge of the positions table
  or bankroll_ledger table.

════════════════════════════════════════════════════════════════════════
## SECTION 8 — RISK CONTAINMENT (ALL SCENARIOS)
════════════════════════════════════════════════════════════════════════

Every failure scenario must have a defined, coded response.
"The system should handle it" is not acceptable. Specify exactly what.

| Scenario | Response | Where |
|----------|----------|-------|
| Momentum scan fails for one ticker | `continue`, log ERROR, scan next ticker | run_momentum_screener() |
| Container A unreachable at 15:15pm auto-square | Log CRITICAL, send Telegram alert for manual square-off | auto_square_momentum() |
| Zerodha API returns 429 during momentum scan | Exponential backoff 2^n, max 5 retries, then skip | kite_client.get_intraday() |
| Momentum position not squared by 15:15 (MIS) | Zerodha auto-squares at 15:15 as safety net | Zerodha infrastructure |
| Circuit breaker trips mid-scan | Return immediately, log halted, emit no signals | run_momentum_screener() |
| Bankroll drops below 80% of initial | Freeze momentum pool, swing continues | run_momentum_screener() |
| Duplicate signal for same ticker (swing + momentum) | Swing wins, momentum signal dropped silently | run_screener() + run_momentum_screener() |
| VWAP crossover on 0-volume candle | vol_ratio_intraday = 0, fails [MC3], rejected | evaluate_momentum_signal() |
| Gemini API failure | Send Telegram with SYSTEM FALLBACK message, no conviction filter applied | analyze_with_gemini() |
| Intraday cache has stale data from yesterday | clear_intraday_cache() runs at 00:05 IST, cache is clean each day | kite_client.py |
| Auto-square limit order not filled within 2 min | Container A re-tries as market order | executor.js (Container A) |
| Position tracker update_daily_positions() encounters MOMENTUM position | Skip trailing stop update for MOMENTUM (intraday positions do not trail) | position_tracker.py |

### Position tracker MOMENTUM exemption
Inside `update_daily_positions()`, add this guard:
```python
for pos in open_pos:
    # MOMENTUM positions are squared intraday — skip daily update
    if pos.get('source') == 'MOMENTUM':
        continue
    # ... existing logic for SWING positions unchanged ...
```

════════════════════════════════════════════════════════════════════════
## SECTION 9 — CONFIG ADDITIONS (config.py)
════════════════════════════════════════════════════════════════════════

Add to `Settings` class. All must be env-var overridable:

```python
# Momentum
MAX_MOMENTUM_POSITIONS:   int   = 2
MOMENTUM_POOL_PCT:        float = 0.20    # 20% of bankroll
MOMENTUM_POOL_FREEZE_PCT: float = 0.80    # freeze if bankroll < 80% of initial
MOMENTUM_MIN_CANDLES:     int   = 4
MOMENTUM_VOL_SURGE_PCT:   float = 3.0     # 300% of 10-candle avg
MOMENTUM_R_TARGET:        float = 2.0
MOMENTUM_MAX_COST_RATIO:  float = 0.25    # reject if costs > 25% of expected profit
MOMENTUM_FIRST_SCAN_HOUR: int   = 10
MOMENTUM_FIRST_SCAN_MIN:  int   = 15
CONTAINER_A_URL:          str   = "http://node-gateway:3000"
INTERNAL_API_SECRET:      str   = ""      # must be set in .env

# RS Module
RS_PERIODS:               int   = 20
RS_MIN_THRESHOLD:         float = 5.0
RS_MIN_DAYS_ABOVE_AVG:    int   = 3
RS_LOOKBACK_DAYS:         int   = 5

# Cost model
ZERODHA_BROKERAGE_PCT:    float = 0.0003  # 0.03%
ZERODHA_BROKERAGE_MAX:    float = 20.0    # ₹20 cap
ZERODHA_STT_CNC:          float = 0.001   # 0.1% sell side
ZERODHA_STT_MIS:          float = 0.00025 # 0.025% sell side
ZERODHA_EXCHANGE_PCT:     float = 0.0000345
ZERODHA_STAMP_DUTY_PCT:   float = 0.00015
ZERODHA_SEBI_PCT:         float = 0.000001
ZERODHA_GST_PCT:          float = 0.18
```

════════════════════════════════════════════════════════════════════════
## SECTION 10 — KNOWN QUIRKS ADDENDUM (add to GEMINI.md)
════════════════════════════════════════════════════════════════════════

These new quirks join the existing [Q1]–[Q6] in GEMINI.md.

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

### [Q9] Momentum pipeline runs at :55 not :15
Container C's `run_momentum_pipeline()` runs at 10:55, 11:55, 12:55,
13:55, 14:55 IST — 40 minutes after Container B's scan at :15.
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
Do not add UI to let the user choose — the rule is deterministic.

### [Q11] cost_ratio field is momentum-only
The `cost_ratio` field exists only on `MomentumSignal`, not on `Signal`.
This is by design — for swing trades held 7–15 days, cost ratio is
negligible and not displayed. For intraday trades, it is critical.
Do not add cost_ratio to the swing Signal model.

### [Q12] BEAR_RS_ONLY does not halt the swing screener
Unlike the previous "BEAR" regime which returned early and emitted
nothing, "BEAR_RS_ONLY" falls through to the screener loop and
applies additional RS filters. The regime filter no longer has an
early return in bear conditions. Do not revert this to an early return.

════════════════════════════════════════════════════════════════════════
## SECTION 11 — EXECUTION ORDER
════════════════════════════════════════════════════════════════════════

Implement in this exact order. Do not skip phases or implement
out of order. Each phase must pass its tests before the next begins.

Phase 1A: Add `calc_zerodha_costs()` and `is_cost_viable()` to engine.py
          Update `evaluate_signal()` to use new cost model.
          Update `update_daily_positions()` to use new cost model.

Phase 1B: Add `calc_relative_strength()` and `calc_volume_consistency()`
          to engine.py.

Phase 1C: Update regime filter in main.py (BEAR → BEAR_RS_ONLY).
          Update Pydantic Literals in models.py.

Phase 1D: Write all tests in python-engine/tests/test_engine.py.
          RUN TESTS. All must pass before Phase 2.

Phase 2A: Add `get_intraday()` and `clear_intraday_cache()` to kite_client.py.
          Add `_init_intraday_db()` method.

Phase 2B: Add `calc_vwap()` and `evaluate_momentum_signal()` to engine.py.
          RUN TESTS AGAIN. Momentum tests must pass.

Phase 2C: Add `MomentumSignal` to models.py.
          Add `filter_momentum_signals()` to portfolio.py.

Phase 2D: Add `run_momentum_screener()` to main.py.
          Add `/momentum-signals` endpoint.
          Add `/positions/close` endpoint.
          Add scheduler jobs.
          Update `post_login_initialization()`.

Phase 2E: Add `auto_square_momentum()` and `momentum_eod_warning()` to main.py.
          Add Container A endpoints (square-off, LTP, internal notify).

Phase 3:  Update `analyze_with_gemini()` prompt in agent.py.
          Add `run_momentum_pipeline()`.
          Add `send_momentum_telegram_alert()`.
          Add momentum schedule jobs.

Phase 4:  Run full integration check.
          Verify all tests pass.
          Verify no import errors across all files.
```

---

That is the complete V2.0 implementation prompt. Here is a summary of every decision embedded in it and why, so you have a full record.

The cost model replacement throughout the codebase uses your confirmed accurate Zerodha breakdown. The existing `0.001` approximation underestimates actual costs by roughly 50% for small positions because it misses STT entirely for intraday. The new `calc_zerodha_costs()` is the single source of truth used in pre-trade EV calculation, post-trade P&L recording, and the momentum cost viability gate.

The `BEAR_RS_ONLY` regime replaces `C1` only, with `C2`–`C8` still enforced. This is the mathematically sound choice — you confirmed it. A stock outperforming the index in a bear market still needs to be near its own support, have volume, and not be overbought. The RS score alone is not sufficient.

The momentum pipeline runs at `:55` not `:15` because Nifty 500 takes ~3 minutes to scan at 3 req/sec, and Gemini adds more time per signal. Running Container C 40 minutes after Container B ensures it processes a complete scan, not a partial one. This is encoded as Known Quirk Q9 so it is never "optimised" away.

The `source='MOMENTUM'` exemption in `update_daily_positions()` prevents the trailing stop logic from running on intraday positions that have already been squared off or will be by 3:15pm. Without this guard, the daily update job would attempt to fetch a closing price for a position that no longer exists and produce garbage P&L numbers.