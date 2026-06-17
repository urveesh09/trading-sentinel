# Trading Sentinel: Adaptive Multi-Strategy Evolution
## Design Document v1.0

**Project:** Trading Sentinel System Upgrade
**Phase:** Phase 2 -- Design Specification
**Date:** May 2025
**Status:** Draft -- Pending Implementation

---

## 1. Problem Statement

Trading Sentinel operates with fixed-rule signal generation and risk parameters. This design document specifies an upgrade to a **regime-aware adaptive system** that:
- Adjusts signal filters based on detected market volatility regime
- Scales position sizing dynamically to match current risk environment
- Uses smarter indicator inputs (RSI percentile, volume z-score) instead of fixed thresholds

**Scope of this document:** Signal quality improvements (1), risk intelligence improvements (2), regime detection mechanism (3). Strategy portfolio expansion (4, 5, 6) is deferred to a future phase.

---

## 2. Regime Detection Engine

### 2.1 Inputs

Three data sources feed the regime engine:

| Input | Source | Purpose |
|---|---|---|
| India VIX | NSE/Bhavcopy or Upstox API | Primary volatility measure |
| Nifty 50 EMA20 | Computed from Nifty 50 data | Trend direction confirmation |
| Breadth (% stocks above SMA50) | Computed from universe | Market health check |

### 2.2 Continuous Regime Score (0-100)

Each scan cycle computes a regime score:

```
base_score = clamp(100 - (VIX - 12) * 5, 0, 100)   # VIX 12 -> 100, VIX 32 -> 0

if Nifty_50 < EMA20: base_score *= 0.7               # Downtrend penalty
if breadth < 0.3: base_score *= 0.8                # Weak breadth penalty

regime_score = max(0, min(100, base_score))
```

**Regime mapping:**
- `regime_score >= 70` -- **Regime 1 (Normal)**
- `regime_score 40-69` -- **Regime 2 (Elevated)**
- `regime_score < 40` -- **Regime 3 (Crisis)**

### 2.3 Regime Transition Rules

- Regime transitions require score to remain in new range for **2 consecutive scan cycles** (anti-flash Signal)
- Hysteresis buffer: score must cross threshold by 5 points before transitioning (prevents rapid switching at boundaries)
- Regime score is computed on every scan (09:20 and 14:45 IST)
- Logging: every regime transition is logged with full score breakdown for post-analysis

### 2.4 Regime Parameters by Level

| Parameter | Regime 1 (Normal) | Regime 2 (Elevated) | Regime 3 (Crisis) |
|---|---|---|---|
| Position size (% risk) | 10% | 7% | 5% |
| Stop loss (ATR multiplier) | 1.5x | 2.0x | 2.0x |
| RSI filter | Percentile less than 20 | Percentile less than 15 + Nifty filter | RS vs Nifty greater than 5% |
| Volume threshold | Z-score greater than 1.5 | Z-score greater than 2.0 | Z-score greater than 2.5 |
| Target 1 | 1.5R (50% exit) | 1.5R (50% exit) | 1.0R (50% exit) |
| Target 2 | 3.0R | 3.0R | None |
| Intraday momentum | Allowed | Allowed (if Nifty filter passes) | No -- swing only |
| Chandelier stop | Optional | Default | Default |

---

## 3. Signal Quality Improvements

### 3.1 RSI Percentile (Replaces Fixed RSI Band)

**Current:** RSI must be between 45 and 72

**New approach:**

For each stock in universe, maintain a rolling 6-month window of RSI readings. Compute:

```
current_rsi_percentile = percentile_rank(current_rsi, rolling_6_month_rsi_series)
```

**Signal entry criterion:**
- Regime 1: RSI_percentile less than 20 (stock is at bottom 20% of its own historical RSI range)
- Regime 2: RSI_percentile less than 15 (tighter because we are in elevated uncertainty)
- Regime 3: Not used -- replaced by RS vs Nifty requirement

**Why this is better:** A stock at RSI 55 might be oversold relative to its own history (if it typically trades RSI 65-80) or overbought relative to its history (if it typically trades RSI 35-50). Percentile captures this context. Fixed band treats a stock at RSI 55 the same whether it is historically a 70-RSI stock or a 45-RSI stock.

### 3.2 Volume Z-Score (Replaces Fixed Volume Ratio)

**Current:** volume_ratio >= 1.2 (volume > 1.2x 20-day average)

**New approach:**

For each stock, maintain a rolling 20-day volume series. Compute:

```
volume_z_score = (current_volume - rolling_mean_20d) / rolling_std_20d
```

**Signal entry criterion:**
- Regime 1: volume_z_score > 1.5 (volume is 1.5 standard deviations above recent average)
- Regime 2: volume_z_score > 2.0
- Regime 3: volume_z_score > 2.5

**Why this is better:** A volume spike to 1.5x might be trivial for a high-beta stock (where volume naturally fluctuates plus/minus 30%) but extraordinary for a low-beta stock (where volume rarely deviates 10%). Z-score is measured against the stock's own volatility distribution, not a fixed multiplier.

### 3.3 Relative Strength Filter (Regime 3 Only)

In Regime 3, additionally require:

```
rs_vs_nifty = (stock_1d_return - nifty_1d_return) > 5%
```

Only stocks that are outperforming Nifty by greater than 5% in the last session generate signals in Crisis regime. This ensures the system is only buying stocks that are demonstrating strength relative to the broad market.

### 3.4 Nifty Trend Confirmation (Regime 2)

In Regime 2, additionally require:

```
nifty_50_current > nifty_50_EMA20   # Nifty is above its 20-day EMA
```

If Nifty is below its EMA20, all signals are suppressed regardless of individual stock metrics. This prevents fighting a broad market downtrend.

### 3.5 Chandelier Stop (Optional in Regimes 1-2, Default in Regime 3)

**Implementation:**

```
chandelier_stop = highest_close_since_entry - (3 * ATR_14)
```

The stop trails the highest closing price since entry. It locks in profits when a stock rises strongly, but does not get triggered by normal pullbacks within a trend.

- **Regime 1:** Optional -- user can choose static ATR or Chandelier via config flag
- **Regime 2:** Default -- Chandelier is recommended for uncertain markets
- **Regime 3:** Mandatory -- static ATR is too vulnerable to intraday noise in high-vol environments

**Note:** Chandelier stop does not replace the entry stop loss. It IS the stop loss -- once the entry stop is set at 2.0x ATR, the Chandelier becomes the trailing stop and will be tighter than the initial ATR stop once the stock moves favorably.

---

## 4. Risk Intelligence Improvements

### 4.1 Dynamic Position Sizing

**Current:** Fixed 10% risk per trade, regardless of market conditions

**New approach:** Position size is a function of regime and available bankroll

```
risk_per_trade = bankroll * (regime_risk_pct / 100)

shares = floor(risk_per_trade / (entry_price - stop_loss))

capital_deployed = shares * entry_price
capital_at_risk = shares * (entry_price - stop_loss)
```

**Check:** capital_at_risk <= risk_per_trade + 0.05 (0.05 is rounding tolerance)

### 4.2 Partial Exit at Target 1

In all regimes, the following partial exit applies at Target 1:

- When price reaches entry + (risk_per_unit * 1.5), sell 50% of position
- Remaining 50% runs with trailing Chandelier stop to Target 2 (Regimes 1 and 2) or is manually managed (Regime 3)

**Why:** Taking 50% off at 1.5R locks in partial profit and reduces emotional pressure on the remaining position. The remaining 50% has a risk-free entry (stop moved to entry price) after Target 1 is hit.

### 4.3 Regime-Specific Target Structure

| Regime | Target 1 | Target 2 | Notes |
|---|---|---|---|
| Regime 1 | 1.5R, 50% exit | 3.0R, remaining exit | Full structure |
| Regime 2 | 1.5R, 50% exit | 3.0R, remaining exit | Same, higher quality |
| Regime 3 | 1.0R, 50% exit | None | Exit fully at T1, no holding for T2 |

**Rationale for Regime 3:** Chasing 3.0R in a high-volatility market extends exposure to an unpredictable environment. 1.0R is typically achievable in 1-3 days in a crisis recovery. Taking it and moving on preserves capital for the next opportunity.

### 4.4 Drawdown Contingent Risk Reduction

After any Regime 3 period, the following applies for the next 5 trading sessions:

```
effective_risk_pct = configured_risk_pct * 0.7   # 30% reduction
```

This means after a crisis (where the system is already at 5% position size), the next 5 trades are at 3.5% risk. This is an automatic recovery-speed governor -- it prevents the system from chasing losses by immediately sizing back up after a drawdown.

Reset condition: After 2 consecutive winning trades in the 5-session window, normal regime sizing resumes.

---

## 5. Configuration

All regime parameters are defined in config.py and can be overridden per-environment:

```python
# Regime thresholds
REGIME_VIX_BOUNDARY_12 = 18    # Regime 1/2 boundary
REGIME_VIX_BOUNDARY_23 = 25    # Regime 2/3 boundary

# RSI Percentile thresholds
RSI_PERCENTILE_REGIME1 = 20    # Bottom 20% of 6-month RSI range
RSI_PERCENTILE_REGIME2 = 15    # Bottom 15% (tighter in uncertain market)

# Volume Z-score thresholds
VOL_ZSCORE_REGIME1 = 1.5
VOL_ZSCORE_REGIME2 = 2.0
VOL_ZSCORE_REGIME3 = 2.5

# Position sizing by regime
RISK_PCT_REGIME1 = 0.10        # 10%
RISK_PCT_REGIME2 = 0.07        # 7%
RISK_PCT_REGIME3 = 0.05        # 5%

# Stop loss by regime (ATR multipliers)
STOP_ATR_REGIME1 = 1.5
STOP_ATR_REGIME2 = 2.0
STOP_ATR_REGIME3 = 2.0

# Target structure
TARGET1_R = 1.5               # All regimes
TARGET2_R_REGIME3 = None      # No T2 in crisis

# Chandelier
CHANDELIER_ATR_MULT = 3.0     # Highest close - 3 * ATR

# Regime transition guard
REGIME_TRANSITION_SCANS = 2    # Score must hold for 2 consecutive scans
REGIME_HYSTERESIS = 5         # Must cross threshold by 5 points

# RS vs Nifty filter (Regime 3)
RS_VS_NIFTY_THRESHOLD = 0.05  # 5% outperformance required

# Drawdown governor
DRAWDOWN_RECOVERY_TRADES = 5  # Reduced sizing for next 5 trades post-crisis
DRAWDOWN_RECOVERY_MULT = 0.7  # 30% size reduction
```

---

## 6. Data Requirements

| Data Point | Source | Frequency | Storage |
|---|---|---|---|
| India VIX | NSE/Bhavcopy or Upstox candle | Every scan | In-memory, not persisted |
| Nifty 50 EMA20 | Computed from Nifty 50 OHLC | Every scan | In-memory |
| Breadth | Computed from universe scan | Every scan | In-memory |
| Stock RSI 20-day history | Indicator service | Per scan per stock | Rolling 6-month per stock |
| Stock Volume 20-day history | OHLC service | Per scan per stock | Rolling 20-day per stock |
| Regime transitions | Computed | Per scan | Logger output |

**Implementation note:** RSI and volume history must be maintained in memory (or persisted to Redis/memory DB) between scan cycles. The 6-month RSI percentile requires ~126 RSI readings per stock. At 50 stocks, this is ~6,300 float values -- well within memory constraints.

---

## 7. Architecture: New Components

### 7.1 New Files

| File | Purpose |
|---|---|
| regime.py | Regime detection engine -- computes regime score, handles transitions |
| indicators_adaptive.py | RSI percentile, volume z-score calculations |
| chandelier_stop.py | Chandelier trailing stop logic |
| risk_engine.py | Dynamic position sizing, partial exit management |

### 7.2 Modified Files

| File | Changes |
|---|---|
| config.py | Add all regime configuration parameters |
| engine.py (or screener.py) | Integrate regime score into signal generation flow |
| portfolio.py | Update filter_momentum_signals to use regime-aware position sizing |
| models.py | Add Regime enum, extend Signal model with regime metadata |

### 7.3 Backward Compatibility

All existing signals, portfolio rules, and circuit breakers remain functional. The adaptive layer sits **on top of** the existing system -- it filters signals before they reach the allocation engine, not after.

If the regime engine fails (e.g., VIX data unavailable), the system falls back to Regime 1 (normal mode) as the conservative default.

---

## 8. Testing Strategy

### 8.1 Historical Backtesting

Test the new regime engine against two historical stress periods:
- **March 2020:** COVID crash (VIX peaked at 85, Nifty -38% peak-to-trough)
- **February-March 2022:** Russia-Ukraine war escalation (VIX 20-35 for 6 weeks)

Metrics to capture:
- Number of signals generated in each regime
- Win rate by regime
- Maximum drawdown vs flat buy-and-hold
- Compare to current system performance on same data

**Pass criterion:** New system must show materially lower drawdown (target: 40-50% reduction) in crisis periods with comparable or better win rate.

### 8.2 Paper Trading

After backtesting passes, run 2 weeks of paper trading (real market, simulated capital) before any real capital deployment.

**Pass criterion:** No regime transition errors, no calculation bugs, consistent signal generation.

### 8.3 Production Deployment

Full deployment with:
- Telegram notification on every regime transition
- Daily regime report logged (score, regime, key inputs)
- Circuit breaker override: if VIX spikes to greater than 40, system automatically enters Regime 3 regardless of score

---

## 9. Open Questions / Deferred Decisions

1. **Backtest data source:** We need reliable NSE OHLC data for 2019-2025 for backtesting. Is Upstox historical data available for this period, or do we need to source from NSE/Bhavcopy?

2. **Nifty 500 breadth calculation:** This requires scanning 500 stocks each cycle for SMA50 position. Is this computationally acceptable, or should we limit to Nifty 100?

3. **Chandelier stop implementation:** The current system uses GTT orders via Upstox. Does Upstox support trailing stop orders, or does the Chandelier stop need to be managed manually in the Python engine (i.e., monitor and close when triggered)?

4. **RSI percentile storage:** 6-month rolling window per stock. If the engine restarts, does this history need to be persisted to DB/Redis, or can we rebuild from historical data?

---

## 10. Success Metrics

After 3 months of live deployment:

| Metric | Target | Measurement |
|---|---|---|
| Regime 1 win rate | greater than 60% | Signals that close at profit / total signals in Regime 1 |
| Regime 3 drawdown | less than 12% | Max drawdown during any Regime 3 period |
| Average R per trade | greater than 1.2R | Mean reward-to-risk across all regimes |
| Regime transitions | Logged, no missed transitions | Count vs expected transitions from VIX |
| Signal count (Regime 1) | No decrease vs current | Monthly average signals in normal market |

---

*This document is the authoritative technical specification for the Trading Sentinel adaptive evolution. All implementation must conform to this document. Any deviation requires a design doc revision.*