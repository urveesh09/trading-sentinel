# Trading Sentinel — Strategy Documentation
**Branch:** `evolve/smart-strategies`  
**Version:** 1.0.0  
**Bankroll:** ₹5,000 (initial) — conservative capital-preservation mode

---

## System Overview

Trading Sentinel is a dual-strategy quantitative trading system for NSE equities:

| Strategy | Horizon | Frequency | Pool |
|---|---|---|---|
| **Swing** (EMA Pullback) | 3–15 days | 09:20 & 14:45 IST | 100% bankroll |
| **Momentum** (Intraday) | Minutes–EOD | Every 15 min (10:00–14:45 IST) | 50% of bankroll |

Both strategies share a common **regime-aware risk management layer** that adjusts
position sizing, stop loss, and targets based on detected market volatility conditions.

---

## 1. Market Regime System

Before every scan, the `RegimeEngine` computes a continuous **regime score (0–100)**
from three data inputs:

| Input | Source | Weight |
|---|---|---|
| **India VIX** | Kite historical (`INDIAVIX`) | Primary driver |
| **Nifty 50 vs EMA20** | Kite historical (`NIFTY 50`) | Trend penalty |
| **Market Breadth** | Placeholder (0.5) | Disabled until Nifty 500 data available |

### Score Mapping

```
Score ≥ 70  → REGIME_1_NORMAL     (calm, full universe, 10% risk)
Score 40–69 → REGIME_2_ELEVATED   (elevated vol, selective, 7% risk)
Score < 40  → REGIME_3_CRISIS    (high stress, RS filter only, 5% risk)
```

### Transition Guard

A regime change requires the score to stay in the new range for **2 consecutive scans**
before transitioning. Hysteresis prevents flip-flopping at boundaries.

### Circuit Breaker

If VIX > 40, the system forces **Regime 3 regardless of score** to protect capital
during extreme stress events.

### Regime Parameters

| Parameter | Regime 1 (Normal) | Regime 2 (Elevated) | Regime 3 (Crisis) |
|---|---|---|---|
| Risk per trade | 10% | 7% | 5% |
| Stop ATR mult | 1.5× | 2.0× | 2.0× |
| T1 target | 1.5R | 1.5R | 1.5R |
| T2 target | 3.0R | 3.0R | 1.0R (exit all at T1) |
| RSI filter | Bottom 20% of 126d range | Bottom 15% of 126d range | RS vs Nifty gate |
| Vol Z-score gate | ≥ 1.5 | ≥ 2.0 | ≥ 2.5 |

### Post-Crisis Recovery Governor

After a Regime 3 scan is observed, `RiskEngine.enter_recovery_mode()` is called
at the next `daily_post_market()`. For the next **5 trades**, risk is reduced by 30%
(`DRAWDOWN_RECOVERY_MULT = 0.7`). The governor exits early after 2 consecutive winners.

---

## 2. Swing Strategy (EMA Pullback)

### Objective

Enter during short-term pullbacks within established uptrends. The setup requires
the stock to be in a confirmed long-term uptrend, offering a pullback entry with
a tight stop and favorable risk/reward.

### Universe

Nifty 500 stocks, loaded from `/data/nifty500.csv`. Falls back to Nifty 100 list
if CSV is missing.

### Entry Filters (in evaluation order)

| # | Filter | Condition | Rationale |
|---|---|---|---|
| C1 | **Trend** | `close > EMA200` AND `EMA50 > EMA200` | Established uptrend |
| C2 | **EMA21 Proximity** | `0.93 × EMA21 ≤ close ≤ 1.20 × EMA21` | Pullback zone or slight extension |
| C3 | **Volume Surge** | `vol_ratio ≥ 1.2` (vs 20d avg) | Participation confirmation |
| C4 | **RSI Range** (fallback) | `45 ≤ RSI_14 ≤ 72` | Not overbought; not oversold |
| C4a | **RSI Percentile** (when history available) | RSI in bottom 20% (R1) or 15% (R2) of 126d range | Stock-specific; adaptive |
| C5 | **Price floor** | `close ≥ 50` | Liquid stocks only |
| C6 | **Volume floor** | `avg_20d_vol ≥ 100,000` | Liquidity filter |
| C7 | **Slope positive** | `slope_5d > 0` | Short-term momentum |
| C8 | **ATR valid** | `ATR_14 > 0` | Volatility exists |
| C9 | **RS vs Nifty** (Regime 3 only) | Stock outperformed Nifty by ≥ 5% today | Relative strength gate |
| C10 | **Net EV positive** | `gross_profit − costs > 0` | Viability gate |
| C11 | **Capital sufficiency** | `shares × close ≤ bankroll` | Account for position |

### RS vs Nifty Filter (Regime 3)

This replaces the RSI percentile filter in Regime 3. Only stocks that significantly
outperform Nifty on a 1-day return are considered. Formula:
```
RS_vs_Nifty = stock_return_1d − nifty_return_1d
Pass if RS_vs_Nifty ≥ 0.05 (5 percentage points outperformance)
```

### Risk Management

**Stop loss** = `max(close − 1.5×ATR, close × 0.95)`  
**T1** = `close + 1.5R`  
**T2** = `close + 3.0R` (Regime 1 & 2); exit all at T1 in Regime 3

**Partial exit at T1:** 50% of position exited. Stop moves to breakeven.

### Trailing Stop

The Chandelier stop (`highest_close_since_entry − 3×ATR`) is tracked in
`position_tracker.py` after each daily close. Currently managed in-engine
(not via GTT orders).

### Position Sizing

```
risk_per_trade = bankroll × risk_pct_by_regime
risk_per_share = close − stop_loss
shares = floor(risk_per_trade / risk_per_share)
cap_deployed = shares × close
```

Cap at `50% of bankroll` per trade.

---

## 3. Intraday Momentum Strategy

### Objective

Capture intraday momentum breakouts on a 15-minute timeframe, closing all
positions at or before 15:15 IST.

### Entry Filters (MC gates)

| # | Gate | Condition | Notes |
|---|---|---|---|
| MC1 | **Min candles** | `len(df) ≥ 4` (60 min of data) | Warm-up period |
| MC2 | **VWAP crossover** | Close crossed above VWAP in last 3 candles and still holding | Prevents "sniper blindness" false entries |
| MC3 | **Volume surge** | `vol_ratio ≥ 1.5×` (time-aware: 1.75× during 11:30–13:15 IST) | Momentum confirmation |
| MC4 | **Intraday range** | Close in top 20% of today's intraday range | Confirms strength |
| MC5 | **ATR fuel** | Target distance ≤ `remaining_fuel × 0.85` | Prevents entries when day's range already consumed |
| MC6 | **Morphology** | `close_position_score ≥ 0.65` (candle not a shooting star/doji) | Candle quality gate |

### VWAP Calculation

`VWAP = cumsum(typical_price × volume) / cumsum(volume)` — resets daily.
Requires only today's 15-minute candles.

### Risk Management

**Stop loss** = Low of the breakout candle (last candle)  
**Target** = `close + 2.0R` (BULL) / `close + 1.5R` (BEAR_RS_ONLY)  
**Product type:** MIS if position value < ₹5,000; CNC otherwise

### Cost Viability Check

```
cost_ratio = total_costs / (risk × r_target)
Reject if cost_ratio > 0.25 (costs eat >25% of expected profit)
```

### Auto-Square-Off

At 15:10 IST: Telegram warning.  
At 15:15 IST: All open momentum positions squared via limit order.

---

## 4. Portfolio Allocation & Filters

After signals pass individual gate evaluation, `filter_and_allocate()` applies
portfolio-level constraints:

| Constraint | Limit |
|---|---|
| Max open positions | 6 (swing + momentum combined) |
| Max capital per trade | 50% of bankroll |
| Max sector exposure | 40% of bankroll |
| Max correlated positions (same sector) | 2 |
| Max total capital at risk | 60% of bankroll |
| Regime risk limit | Inviolable — per-trade risk ≤ regime limit |

Downsizing (reducing shares to fit) is preferred over outright rejection
when possible.

---

## 5. Cost Model (Zerodha NSE Equity)

| Cost Component | Delivery (CNC) | Intraday (MIS) |
|---|---|---|
| Brokerage | min(0.03% turnover, ₹20) | min(0.03% turnover, ₹20) |
| STT | 0.1% (sell side only) | 0.025% (sell side only) |
| Exchange txn | 0.00345% both sides | 0.00345% both sides |
| Stamp duty | 0.015% (buy side) | 0.015% (buy side) |
| SEBI fee | 0.0001% both sides | 0.0001% both sides |
| GST | 18% on (brokerage + exchange) | 18% on (brokerage + exchange) |

**Note:** At ₹5K bankroll the ₹20 flat brokerage + STT + GST kills most viable
signals. The `for_gate=True` flag in `calc_zerodha_costs()` zeros these for
signal viability gates only. Actual P&L tracking uses the full cost model.
This bypass should be removed when bankroll reaches ₹50,000+.

---

## 6. Circuit Breakers

| Circuit Breaker | Threshold | Action |
|---|---|---|
| Daily loss halt | ≥ 20% of bankroll lost today | Halt trading for the day |
| Consecutive losses | ≥ 5 consecutive losers | Halt until next day |
| Max drawdown | ≥ 50% peak bankroll | Halt until bankroll > 40% of peak |
| VIX extreme | VIX > 40 | Force Regime 3 regardless of score |

---

## 7. Key Files Reference

| File | Purpose |
|---|---|
| `main.py` | FastAPI app, scan scheduler, regime wiring |
| `engine.py` | `evaluate_signal()` / `evaluate_momentum_signal()` — all gate logic |
| `regime.py` | `RegimeEngine` — VIX + Nifty + breadth → regime score |
| `risk_engine.py` | `RiskEngine` — position sizing, partial exits, recovery governor |
| `indicators_adaptive.py` | `AdaptiveIndicators` — RSI percentile, volume z-score |
| `portfolio.py` | `filter_and_allocate()` — portfolio-level constraints |
| `chandelier_stop.py` | `ChandelierStop` — trailing stop (in-engine, not GTT) |
| `position_tracker.py` | Daily position tracking, trailing stop updates |
| `performance.py` | Bankroll ledger, P&L recording |
| `backtest.py` | Regime-aware backtesting harness |
| `models.py` | Pydantic signal/position/report models |
| `config.py` | All strategy parameters and constants |

---

## 8. Open Questions & Known Gaps

| Item | Status | Notes |
|---|---|---|
| **VIX data source** | ✅ Resolved | Kite doesn't support INDIAVIX; graceful `vix=None` fallback, system falls back to regime 1 |
| **Breadth data** | ✅ Resolved | Live proxy: `nifty_close / nifty_ema50` ratio mapped to [0.30, 0.70]; no extra API calls. Full constituent-level breadth remains a future enhancement |
| **GTT trailing stops** | ✅ Not needed | Kite GTT v3 supports `trigger_type=ohlc` but `trigger_price` is FIXED at GTT creation time — cannot express a Chandelier stop (highest_close moves each candle). In-engine management via `position_tracker.py` is correct architecture |
| **Bankroll update** | ✅ Resolved | `risk_engine.update_bankroll()` now called in `daily_post_market()` after `record_trade_close()`. Recovery governor also receives `record_trade_outcome()` for correct win/loss tracking |
| **Brokerage bypass** | ⚠️ Temp | `for_gate=True` zeros ₹20 brokerage for signal viability gates; remove at ₹50K+ bankroll |
| **RS vs Nifty data** | ⚠️ Minor | `nifty_return_1d` not passed to `evaluate_signal()`; defaults to 0.0. Should be wired for accuracy |

---

## 9. Configuration Summary

```
Bankroll:              ₹5,000
Risk/trade (R1):       10%   = ₹500
Max positions:         6
Max capital/trade:      50% of bankroll
Max sector exposure:    40% of bankroll
Max total risk:         60% of bankroll
Momentum pool:          50% of bankroll
Momentum max positions: 5
RS periods:             20
RS min threshold:       5.0
ATR stop (R1):          1.5×
T1 target:              1.5R
T2 target (R1/R2):      3.0R
T2 target (R3):         1.0R (exit all at T1)
```