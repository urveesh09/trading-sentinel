# Mean Reversion Trading Strategies: Deep Research for NSE Swing Trading

> **Scope:** Quantitative mean reversion strategies applicable to NSE (National Stock Exchange of India) swing trading -- holding periods of 1-5 days. Covers Ornstein-Uhlenbeck theory, Bollinger/RSI methods, pairs trading, VWAP deviation, gap fill, Keltner/CCI, exit strategies, risk management, and real-world implementations.

---

## Table of Contents

1. [Core Theory: Mean Reversion Fundamentals](#1-core-theory)
2. [Bollinger Bands Mean Reversion](#2-bollinger-bands)
3. [RSI Mean Reversion](#3-rsi-mean-reversion)
4. [Pairs Trading: Cointegration & Distance Methods](#4-pairs-trading)
5. [VWAP Mean Reversion](#5-vwap-mean-reversion)
6. [Gap Fill Strategies for NSE](#6-gap-fill)
7. [Keltner Channel & CCI Mean Reversion](#7-keltner-cci)
8. [Exit Strategies](#8-exit-strategies)
9. [Risk Management](#9-risk-management)
10. [Real-World Implementations](#10-real-implementations)
11. [NSE-Specific Considerations](#11-nse-specific-considerations)
12. [Strategy Comparison & Summary](#12-strategy-comparison)

---

## 1. Core Theory: Mean Reversion Fundamentals

### 1.1 The Ornstein-Uhlenbeck (OU) Process

The OU process is the mathematical backbone of mean reversion modeling. It describes a stochastic process where a variable tends to drift toward its long-term mean.

**SDE Form:**
```
dr_t = theta(mu - r_t)dt + sigmadW_t
```

Where:
- `r_t` = current price or log price
- `theta` = mean reversion speed (rate at which deviations decay)
- `mu` = long-term mean level
- `sigma` = volatility of the process
- `dW_t` = Wiener process (Brownian motion increment)

**Discrete Form (for implementation):**
```
r_{t+1} - r_t = theta(mu - r_t)Deltat + sigmasqrtDeltat . epsilon
```
Where `epsilon ~ N(0,1)`

### 1.2 Half-Life of Mean Reversion

The **half-life** tells us how long it takes for a deviation from mean to decay by half. Critical for setting swing trade timeframes.

**Formula:**
```
HL = ln(2) / theta = -ln(2) / ln(1 - thetaDeltat)
```

**Simplified (Hurst Exponent approach):**
```
HL = T / (2H)
```
Where `T` = observation period, `H` = Hurst exponent. `H < 0.5` indicates mean reversion.

**Practical interpretation for NSE swing:**
- HL < 3 days -> fast reversion, aggressive entries
- HL 3-7 days -> moderate reversion, standard swing (our sweet spot)
- HL > 7 days -> slow reversion, avoid or use larger stop losses

### 1.3 ADF Stationarity Test

The Augmented Dickey-Fuller (ADF) test determines if a series is stationary (mean-reverting) or non-stationary (random walk).

**Null hypothesis:** Series has a unit root (non-stationary)  
**Reject H0:** Series is stationary at the chosen significance level

**ADF Test Statistic:**
```
Deltay_t = alpha + betat + gammay_{t-1} + Sumdelta_iDeltay_{t-i} + epsilon_t
```
Test against critical values. More negative = stronger stationarity.

**Critical values (common):**
| Confidence | ADF Statistic |
|---|---|
| 90% | -2.57 |
| 95% | -2.86 |
| 99% | -3.43 |

**NSE practical threshold:** ADF < -3.0 strongly suggests mean reversion is viable for the instrument.

**Python implementation:**
```python
from statsmodels.tsa.stattools import adfuller

def adf_test(series, name="Series"):
    result = adfuller(series.dropna(), autolag='AIC')
    print(f"ADF Statistic: {result[0]:.4f}")
    print(f"p-value: {result[1]:.4f}")
    print(f"Critical Values: {result[4]}")
    return result[1] < 0.05  # True if stationary at 5%
```

### 1.4 Mean Reversion vs Momentum Thresholds

**Key insight:** Mean reversion works best when:
1. Price is far from mean (high z-score)
2. Market is in range-bound regime (low VIX, low ATR)
3. Volume is contracting (smart money not accumulating/distributing)

**Hurst Exponent (H):**
- H < 0.5 -> mean reversion regime
- H = 0.5 -> random walk (no edge)
- H > 0.5 -> momentum/trend regime

**NSE instruments with stronger mean reversion properties:**
- Sector ETFs (NIFTYBEES, JUNIORBEES)
- High-liquidity large-caps (HDFC, ITC, TCS)
- Index futures at extreme deviations

---

## 2. Bollinger Bands Mean Reversion

### 2.1 Core Concept

Bollinger Bands (+/-2 standard deviations from 20-period SMA) provide dynamic support/resistance levels. Mean reversion entries occur when price reaches the outer bands.

### 2.2 Key Metrics

**%B (Percent Bandwidth):**
```
%B = (Price - Lower Band) / (Upper Band - Lower Band)
```

| %B Value | Interpretation |
|---|---|
| > 1.0 | Price above upper band -- overbought, short signal |
| 0.5 | Price at middle band (SMA) |
| < 0.0 | Price below lower band -- oversold, long signal |

### 2.3 Bandwidth as Regime Indicator

**Bandwidth:**
```
Bandwidth = (Upper Band - Lower Band) / Middle Band x 100
```

- **Bandwidth contraction (< 4%)** -> "Bollinger Squeeze" -> low volatility, impending breakout
- **Bandwidth expansion (> 10%)** -> high volatility, mean reversion signals more reliable
- **Bandwidth stability** -> range-bound market, mean reversion favored

### 2.4 Entry/Exit Rules

**Mean Reversion Long Entry:**
1. Price closes below lower Bollinger Band
2. %B < -0.1 (below lower band)
3. RSI(14) < 30 (confirm oversold)
4. Bandwidth > 6% (not in squeeze)
5. Stop: Below lower band + 1.5x ATR
6. Target: Middle band (SMA) or upper band

**Mean Reversion Short Entry:**
1. Price closes above upper Bollinger Band
2. %B > 1.1
3. RSI(14) > 70 (confirm overbought)
4. Bandwidth > 6%
5. Stop: Above upper band + 1.5x ATR
6. Target: Middle band

**NSE-specific tuning:**
- Use 20-period SMA, 2 SD for daily NSE charts
- For intraday (15-min), use 20-period with 1.5 SD initially tighter
- Stock-specific SD lookback may improve results

### 2.5 Bollinger + RSI Overlay Strategy

```python
def bollinger_rsi_signal(close, period=20, std_dev=2, rsi_period=14,
                          oversold=35, overbought=65):
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    
    rsi = ta.rsi(close, rsi_period)
    bb_pos = (close - lower) / (upper - lower)
    
    # Long signal
    long = (close < lower) & (rsi < oversold)
    
    # Short signal
    short = (close > upper) & (rsi > overbought)
    
    return long, short, sma
```

### 2.6 Limitations

- Bands are lagging (based on past prices)
- False signals in strong trending markets
- Sideways markets with low volume = best performance

---

## 3. RSI Mean Reversion

### 3.1 RSI as Mean Reversion Tool

RSI (Relative Strength Index) measures momentum but can identify exhaustion and mean reversion opportunities.

**RSI Formula:**
```
RSI = 100 - (100 / (1 + RS))
RS = Average Gain / Average Loss over period
```

Standard period = 14. For swing trading, 7 or 10 often works better on NSE.

### 3.2 RSI Zones

| RSI Value | Zone | Interpretation |
|---|---|---|
| < 30 | Oversold | Potential long mean reversion |
| 30-50 | Bearish | No edge |
| 50-70 | Bullish | No edge |
| > 70 | Overbought | Potential short mean reversion |

### 3.3 Mean Reversion RSI Strategies

**Strategy A: RSI Divergence (Most Reliable)**
- Price makes lower low, RSI makes higher low = bullish divergence
- Price makes higher high, RSI makes lower high = bearish divergence
- Requires at least 5-7 candle separation

**Strategy B: RSI Extreme Zone Reversal**
- RSI touches or exceeds 70/30
- Wait for RSI to exit extreme zone (> 35 for longs, < 65 for shorts)
- Entry on the first candle that breaks back inside

**Strategy C: RSI with Bollinger Overlay**
```python
def rsi_bollinger_reversion(prices, rsi_period=10, bb_period=20, 
                             bb_std=2, oversold=35, overbought=65):
    rsi = calculate_rsi(prices, rsi_period)
    bb = bollinger_bands(prices, bb_period, bb_std)
    
    # Long: RSI exits oversold AND price above lower BB
    long = (rsi.shift(1) < oversold) & (rsi > oversold) & \
           (prices > bb['lower'])
    
    # Short: RSI exits overbought AND price below upper BB
    short = (rsi.shift(1) > overbought) & (rsi < overbought) & \
            (prices < bb['upper'])
    
    return long, short
```

### 3.4 RSI Mean Reversion in NSE

**Key observations for NSE stocks:**
- Individual stocks can stay oversold/overbought for longer than Western markets
- Use wider thresholds for Indian stocks: 35/65 instead of 30/70
- Sector rotation plays a role -- avoid RSI mean reversion in trending sectors
- Earnings weeks = RSI less reliable due to momentum shifts

### 3.5 RSI Failures to Watch

1. **Trending stocks:** Infosys, TCS during bull runs -- RSI stays overbought for weeks
2. **Post-results:** RSI extreme zones often valid for 3-5 days after results
3. **Index vs stock divergence:** Nifty 50 RSI can signal while individual stocks diverge

---

## 4. Pairs Trading: Cointegration & Distance Methods

### 4.1 Overview

Pairs trading = market-neutral strategy betting that two correlated instruments will converge. Long the underperformer, short the overperformer.

**NSE pairs to consider:**
- HDFC Bank vs ICICI Bank
- Infosys vs TCS
- Reliance vs ONGC
- Nifty 50 ETF vs Nifty Future

### 4.2 Distance Method

**Step 1:** Normalize prices to same scale
```
P_norm_A = P_A / P_A(t0)
P_norm_B = P_B / P_B(t0)
```

**Step 2:** Calculate normalized price ratio
```
Ratio = P_norm_A / P_norm_B
```

**Step 3:** Compute distance from historical mean
```
Z-score = (Ratio - Mean(Ratio)) / Std(Ratio)
```

**Entry:**
- Z-score > +2.0 -> Short A, Long B (expect ratio to fall)
- Z-score < -2.0 -> Long A, Short B (expect ratio to rise)

**Exit:**
- Z-score reverts to 0
- Or: Z-score crosses moving average of Z-score

```python
import numpy as np
from sklearn.preprocessing import StandardScaler

def pairs_distance_method(stock_a, stock_b, lookback=60, entry_threshold=2.0):
    # Normalize
    norm_a = stock_a / stock_a.iloc[0]
    norm_b = stock_b / stock_b.iloc[0]
    
    # Ratio
    ratio = norm_a / norm_b
    
    # Z-score
    mean_ratio = ratio.rolling(lookback).mean()
    std_ratio = ratio.rolling(lookback).std()
    z_score = (ratio - mean_ratio) / std_ratio
    
    # Signals
    long_a_short_b = z_score < -entry_threshold
    short_a_long_b = z_score > entry_threshold
    exit_signal = np.abs(z_score) < 0.5
    
    return z_score, long_a_short_b, short_a_long_b, exit_signal
```

### 4.3 Cointegration Method (CADF)

Cointegration tests whether a linear combination of two series is stationary, even if individual series are not.

**Engle-Granger Two-Step Method:**

**Step 1:** Run OLS regression
```
Stock_A = alpha + beta x Stock_B + epsilon_t
```

**Step 2:** Test residuals (epsilon_t) for stationarity using ADF test
- If ADF rejects unit root -> series are cointegrated

**CADF Statistic:** The test statistic from testing residuals

**Critical values for cointegration ( Engle-Granger table):**
| Sample Size | 1% | 5% | 10% |
|---|---|---|---|
| 100 | -3.90 | -3.34 | -3.04 |
| 200 | -3.87 | -3.31 | -3.01 |
| 500 | -3.86 | -3.29 | -2.99 |

**Python implementation:**
```python
from statsmodels.tsa.stattools import coint, adfuller
from statsmodels.regression.linear_model import OLS

def cointegration_pairs(stock_a, stock_b):
    # Engle-Granger test
    score, pvalue, _ = coint(stock_a, stock_b)
    
    # Step 1: OLS regression
    X = sm.add_constant(stock_b)
    model = OLS(stock_a, X).fit()
    residuals = model.resid
    
    # Step 2: ADF on residuals
    adf_res = adfuller(residuals, maxlag=1, regression='c')
    
    # Hedge ratio
    hedge_ratio = model.params[1]
    
    return {
        'coint_pvalue': pvalue,
        'adf_residuals': adf_res[0],
        'hedge_ratio': hedge_ratio,
        'residuals': residuals,
        'cointegrated': pvalue < 0.05
    }
```

### 4.4 Kalman Filter for Pairs Trading

The Kalman filter dynamically estimates the hedge ratio, adapting to changing relationships.

**State-space model:**
```
Observation: y_t = H_t . theta_t + epsilon_t
State: theta_t = F_t . theta_{t-1} + η_t
```

For pairs:
- y_t = price of stock A
- H_t = [1, price of stock B]
- theta_t = [alpha, beta] (intercept, hedge ratio)
- F_t = Identity (random walk for coefficients)

```python
from numpy import ones, concatenate

def kalman_filter_pairs(stock_a, stock_b, delta=1e-4, Ve=1e-3):
    n = len(stock_a)
    
    # State: [hedge_ratio, intercept]
    theta = zeros((2, n))
    P = zeros((2, 2, n))  # Covariance
    
    # Initialize
    theta[:, 0] = [1.0, 0.0]
    P[:, :, 0] = eye(2)
    
    spread = zeros(n)
    
    for t in range(1, n):
        # Predict
        theta_pred = theta[:, t-1]  # Random walk
        P_pred = P[:, :, t-1] + delta * eye(2)
        
        # Observation matrix
        F = array([[stock_b[t], 1]]).T
        
        # Kalman gain
        S = F.T @ P_pred @ F + Ve
        K = P_pred @ F / S
        
        # Update
        y_pred = F.T @ theta_pred
        spread[t] = stock_a[t] - y_pred
        
        theta[:, t] = theta_pred + K.flatten() * (stock_a[t] - y_pred)
        P[:, :, t] = (eye(2) - K @ F.T) @ P_pred
    
    return theta, spread
```

### 4.5 Pairs Trading on NSE: Practical Notes

**Correlation requirement:** Minimum 0.70 rolling 20-day correlation  
**Entry threshold:** Z-score > 2.0 or CADF confirms cointegration at p < 0.05  
**NSE-specific pairs with history:**
1. ICICI Bank vs HDFC Bank (banking sector)
2. Infosys vs TCS (IT sector)
3. Nifty 50 ETF vs individual heavyweights (beta trade)
4. Gold ETF vs metal stocks (commodity linkage)

**Avoid pairs with:**
- One stock in legal trouble
- Different average daily volume (execution risk)
- Index inclusions/exclusions pending

---

## 5. VWAP Mean Reversion

### 5.1 VWAP Fundamentals

VWAP (Volume Weighted Average Price) = cumulative typical price x volume / cumulative volume. Acts as fair value benchmark for the day.

**Formula:**
```
VWAP = Sum(Price x Volume) / Sum(Volume)
```

### 5.2 VWAP Deviation Bands

Standard deviation of VWAP deviations creates dynamic mean reversion bands.

**Deviation from VWAP:**
```
Deviation = (Price - VWAP) / VWAP x 100
```

**VWAP Bands (typically +/-1SD, +/-2SD, +/-3SD):**
```python
def vwap_deviation_bands(df, period=20, multipliers=[1, 2, 3]):
    df = df.copy()
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df['Deviation'] = df['Close'] - df['VWAP']
    df['AbsDev'] = df['Deviation'].abs()
    
    # Rolling SD of absolute deviation
    df['Dev_SD'] = df['AbsDev'].rolling(period).std()
    
    bands = {}
    for m in multipliers:
        bands[f'+{m}SD'] = df['VWAP'] + m * df['Dev_SD']
        bands[f'-{m}SD'] = df['VWAP'] - m * df['Dev_SD']
    
    return df, bands
```

**NSE practical thresholds:**
- +/-1 SD (68% expected): Minor reversion, scalping only
- +/-2 SD (95% expected): Standard swing entry zone
- +/-3 SD (99.7% expected): High conviction, larger position

### 5.3 Mean Reversion Entry Triggers

**VWAP Long Entry:**
1. Price closes below -2 SD VWAP band
2. Price shows rejection candle (hammer, engulfing) near the band
3. Volume increases on bounce
4. Stop: Below -3 SD or daily VWAP low
5. Target: VWAP (mean) or +1 SD

**VWAP Short Entry:**
1. Price closes above +2 SD VWAP band
2. Price shows rejection candle (shooting star, bearish engulfing)
3. Volume increases on reversal
4. Stop: Above +3 SD or daily VWAP high
5. Target: VWAP or -1 SD

### 5.4 VWAP Mean Reversion for Intraday NSE

**9:15-9:30 AM:** Avoid entries -- highest volatility, VWAP unreliable  
**9:30-11:00 AM:** Best mean reversion window  
**11:00-2:30 PM:** Quiet period, less edge  
**2:30-3:15 PM:** Good for intraday mean reversion setups  
**3:15-3:30 PM:** VWAP resets, avoid new swing entries

### 5.5 VWAP vs Bhavcopy Data

NSE bhavcopy (daily data) has specific considerations:
- OHLC from bhavcopy can compute intraday VWAP approximation
- For proper VWAP, tick data or 1-min data needed
- Most NSE brokers provide VWAP indicator in trading platforms

---

## 6. Gap Fill Strategies for NSE

### 6.1 Overnight Gap Statistics on NSE

Gaps are common on NSE due to:
- After-hours news, earnings, global cues
- Index moves from SGX Nifty (pre-market)
- Bulk deal announcements

**NSE gap frequency (approximate):**
- Nifty 50 stocks: 40-50% of trading days show measurable gaps (>0.5%)
- Mid-caps: 60-70%
- Small-caps: 80%+

**Average gap fill rate (NSE historical):**
- Gaps < 1%: ~75% fill same day
- Gaps 1-2%: ~60% fill within 3 days
- Gaps > 2%: ~45% fill within 5 days
- Gaps > 5%: ~30% fill, often requires catalyst

### 6.2 Gap Fade Algorithm

**Step 1: Gap Detection**
```python
def detect_gap(open_price, prev_close, threshold=0.005):
    gap_pct = (open_price - prev_close) / prev_close
    gap_type = 'up' if gap_pct > threshold else ('down' if gap_pct < -threshold else 'none')
    return gap_pct, gap_type
```

**Step 2: Gap Magnitude Classification**
- **Small gap** (< 1%): Aggressive fade, small stop
- **Medium gap** (1-2%): Standard fade, wider stop
- **Large gap** (> 2%): Cautious fade, news-dependent
- **Huge gap** (> 5%): Avoid fading without strong catalyst

**Step 3: Gap Fade Entry Rules**

*Long (gap down fade):*
1. Gap down > 0.5%
2. Price stabilizes above open (not continuing down)
3. 15-min candle closes above 15-min VWAP
4. RSI(14) < 45 (not oversold, more room to run)
5. Entry: After first 30-min consolidation above open
6. Stop: Below day low or -1% from entry
7. Target: Previous close (gap fill) or VWAP

*Short (gap up fade):*
1. Gap up > 0.5%
2. Price fails to sustain above open
3. 15-min candle closes below 15-min VWAP
4. RSI(14) > 55
5. Entry: After first 30-min consolidation below open
6. Stop: Above day high or +1% from entry
7. Target: Previous close or VWAP

### 6.3 News-Based Gap Handling

| Gap Type | Likely Outcome | Action |
|---|---|---|
| Positive earnings surprise | Gap up holds/fills partially | Fade only if gap > 5% and analyst revision < actual |
| Negative earnings surprise | Gap down continues | Don't fade -- momentum against you |
| Index-only gap (no stock news) | High fill probability | Standard fade strategy |
| Sector rotation gap | Mixed | Check peer stocks, volume profile |
| Bulk deal/Block deal | Wait for 2nd day | Often re-tests gap level |

### 6.4 NSE Gap Fill Strategy Parameters

```python
NSE_GAP_PARAMS = {
    'small_gap_threshold': 0.005,   # 0.5%
    'medium_gap_threshold': 0.02,    # 2%
    'large_gap_threshold': 0.05,    # 5%
    'max_hold_days': 5,
    'partial_profit_levels': [0.5, 0.75],  # Fill percentages
    'stop_pct': 0.015,               # 1.5% stop
}
```

---

## 7. Keltner Channel & CCI Mean Reversion

### 7.1 Keltner Channel

Keltner Channel uses ATR to create volatility-based bands around an EMA.

**Middle Line:** 20-period EMA  
**Upper Band:** EMA + (multiplier x ATR)  
**Lower Band:** EMA - (multiplier x ATR)  
**Multipliers:** 2.0 for normal, 3.0 for volatility expansion

**NSE parameters:**
- EMA period: 20
- ATR period: 10 or 14
- Multiplier: 2.0 (conservative) to 3.0 (aggressive)

```python
def keltner_channels(high, low, close, ema_period=20, atr_period=10, 
                      multiplier=2.0):
    ema = close.ewm(span=ema_period).mean()
    tr = true_range(high, low, close)
    atr = tr.rolling(atr_period).mean()
    
    upper = ema + multiplier * atr
    lower = ema - multiplier * atr
    
    return {'middle': ema, 'upper': upper, 'lower': lower, 'atr': atr}
```

### 7.2 CCI (Commodity Channel Index)

CCI measures deviation from average price. Unlike RSI, it can exceed +/-100.

**CCI Formula:**
```
CCI = (Typical Price - SMA(Typical Price)) / (0.015 x Mean Deviation)
Typical Price = (High + Low + Close) / 3
```

**CCI Zones:**
| CCI Value | Interpretation |
|---|---|
| > +100 | Overbought -- potential short |
| 0 to +100 | Neutral/bullish |
| -100 to 0 | Neutral/bearish |
| < -100 | Oversold -- potential long |

### 7.3 Combined Keltner-CCI Strategy

**Long Entry:**
1. Price touches/closes below lower Keltner band
2. CCI < -100 (oversold confirmation)
3. EMA aligned with entry direction
4. Stop: Below lower band - 1 ATR
5. Target: Middle band (EMA) or upper band

**Short Entry:**
1. Price touches/closes above upper Keltner band
2. CCI > +100 (overbought confirmation)
3. Stop: Above upper band + 1 ATR
4. Target: Middle band or lower band

```python
def keltner_cci_strategy(high, low, close, period=20, 
                          atr_period=10, kelt_mult=2.0,
                          cci_oversold=-100, cci_overbought=100):
    kc = keltner_channels(high, low, close, period, atr_period, kelt_mult)
    cci = calculate_cci(high, low, close, period)
    
    long = (close <= kc['lower']) & (cci < cci_oversold)
    short = (close >= kc['upper']) & (cci > cci_overbought)
    
    return long, short, kc, cci
```

### 7.4 Z-Score of Price

Z-score standardizes price deviation from mean, useful across different price levels.

**Formula:**
```
Z = (Price - SMA) / StdDev
```

**Entry thresholds:**
- Z > +2.0 -> Short signal
- Z < -2.0 -> Long signal
- Z crosses below +1.0 from above -> Exit short
- Z crosses above -1.0 from below -> Exit long

---

## 8. Exit Strategies

### 8.1 Time-Based Exits

| Holding Period | Exit Rationale |
|---|---|
| Intraday (15:20) | NSE settlement, avoid overnight risk |
| 1 day | Mean reversion expected within 1 day |
| 2-3 days | If no progress toward mean, exit |
| 5 days | Maximum swing hold -- re-evaluate |

**Rule:** If no reversion toward mean within 2 days, exit regardless of P&L.

### 8.2 Bollinger Squeeze Exit

When Bollinger Bands contract (bandwidth falls below threshold), a volatility expansion is imminent. Exit before the squeeze if you're not positioned for the breakout.

**Squeeze indicator:**
```python
def bollinger_squeeze(close, period=20, std_dev=2):
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    bandwidth = ((sma + std_dev*std) - (sma - std_dev*std)) / sma
    
    squeeze_threshold = 0.04  # 4% bandwidth
    is_squeeze = bandwidth < squeeze_threshold
    
    return squeeze_threshold, is_squeeze
```

### 8.3 Partial Profit Booking at Mean

**Tiered exit strategy:**
1. **50% profit:** Price reaches middle band (SMA/VWAP/EMA) -> Exit half position
2. **75% profit:** Price reaches 75% of target -> Trail stop to entry
3. **Full target:** Upper/lower band or fixed risk:reward (2:1)

```python
def partial_exit_strategy(entry_price, current_price, mean_price, 
                           target_price, stop_price):
    pct_to_mean = abs(current_price - entry_price) / abs(mean_price - entry_price)
    pct_to_target = abs(current_price - entry_price) / abs(target_price - entry_price)
    
    exits = []
    
    if pct_to_mean >= 0.5 and not exits:
        exits.append(('50%_mean', 0.5))  # Exit 50% at mean
    
    if pct_to_target >= 0.75:
        exits.append(('75%_target', 0.25))  # Exit another 25%
    
    if current_price >= target_price:
        exits.append(('full_target', 0.25))  # Exit remaining
    
    return exits
```

### 8.4 Trailing Stop Methods

| Method | Formula | Best For |
|---|---|---|
| ATR Trail | Stop = Low - 2xATR | Volatile stocks |
| SMA Trail | Stop below 20-SMA | Trend-following exits |
| Chandelier Exit | Stop = Highest High - 3xATR | Trend trades |
| VWAP Trail | Stop below VWAP | Intraday |

### 8.5 Mean Reversion Exit Priority

1. **Primary:** Time-based (5-day max on swing)
2. **Secondary:** Mean reached (target)
3. **Emergency:** Stop loss triggered
4. **Opportunistic:** Partial profits at 50% mean

---

## 9. Risk Management

### 9.1 Win-Rate Aware Position Sizing

**Basic position size:**
```
Position = (Risk Amount) / (Entry Price - Stop Price)
```

**Risk amount:** 1-2% of capital per trade (NSE swing: 1% preferred for overnight)

**Win-rate adjusted sizing:**
```python
def position_size_kelly(capital, win_rate, avg_win, avg_loss, fraction=0.25):
    """
    Kelly Criterion with fractional application for safety
    """
    # Kelly percentage
    W = win_rate
    R = avg_win / avg_loss if avg_loss > 0 else 1
    
    kelly_pct = (W * R - (1 - W)) / R
    
    # Fractional Kelly (use 25-50% of Kelly for safety)
    kelly_pct *= fraction
    
    # Cap at 10% of capital per trade
    kelly_pct = min(kelly_pct, 0.10)
    
    return capital * kelly_pct
```

**Kelly Criterion Table:**
| Win Rate | Risk:Reward | Kelly % | 25% Kelly |
|---|---|---|---|
| 40% | 1:1 | 0% | 0% |
| 50% | 2:1 | 25% | 6.25% |
| 55% | 2:1 | 40% | 10% |
| 60% | 2:1 | 53% | 13.25% |
| 65% | 2:1 | 65% | 16.25% |

**Practical:** Never exceed 10% Kelly (25% fraction of 40% Kelly).

### 9.2 Max Adverse Excursion (MAE) Stops

MAE measures the maximum unfavorable move before the trade becomes profitable. Use historical trade data to set stops beyond typical noise.

**MAE calculation:**
```python
def calculate_mae(trades, window_minutes=60):
    """
    trades: list of (entry, high, low, exit) tuples
    Returns MAE percentile (e.g., 95th percentile of adverse moves)
    """
    adverse_moves = []
    for entry, high, low, exit_price, direction in trades:
        if direction == 'long':
            adverse = (low - entry) / entry  # Negative = adverse
        else:
            adverse = (entry - high) / entry
        
        adverse_moves.append(adverse)
    
    return percentile(adverse_moves, 95)  # 95th percentile MAE
```

**Stop placement:** Place stop at 1.5x to 2x the 95th percentile MAE.

### 9.3 Drawdown Management

| Drawdown | Action |
|---|---|
| -5% | Pause new entries, review strategy |
| -10% | Reduce position size 50% |
| -15% | Stop trading, investigate |
| -20% | Full reset, recalibrate |

### 9.4 NSE Swing Trading Risk Rules

1. **Max 5 open positions** per portfolio
2. **Max 20% capital deployed** in mean reversion at any time
3. **Max 2% risk per trade** (ideally 1%)
4. **Correlation filter:** No >3 positions in same sector
5. **Liquidity filter:** Only trade stocks with ADV > Rs5 crore
6. **No earnings positions:** Exit 2 days before earnings

### 9.5 Position Sizing Algorithm

```python
def calculate_nse_position(capital, entry, stop, max_risk_pct=0.01, 
                            min_lot_size=1, exchange='NSE'):
    # Calculate raw position size
    risk_per_share = abs(entry - stop)
    risk_amount = capital * max_risk_pct
    
    shares = risk_amount / risk_per_share
    
    # Adjust for lot size (NSE stocks trade in lot multiples)
    # For NSE equity: check broker lot size
    # For Nifty options: lot size = 75 (varies)
    
    # Cap at 10% capital
    max_shares = capital * 0.10 / entry
    shares = min(shares, max_shares)
    
    return int(shares)
```

---

## 10. Real-World Implementations

### 10.1 Morgan Stanley Statistical Arbitrage (1990s-2000s)

**Strategy:** Automated pairs trading with mean reversion on residuals  
**Approach:**
- CADF cointegration for pair selection
- Kalman filter for dynamic hedge ratio
- Entry at 2sigma deviation, exit at 0.5sigma
- Mean reversion half-life targeting 1-5 days
- Overnight positions held with delta hedging

**Results:**
- Consistently 10-15% annual returns with low correlation to market
- Max drawdown < 5% in normal years
- Peak AUM: $4.6 billion in Stat Arb strategies

**Key insight:** High-frequency mean reversion (intraday) scaled to swing trading

### 10.2 Goldman Sachs_pairs Trading (2000s)

**Strategy:** Sector pairs with cointegration and momentum filter  
**Approach:**
- OLS + CADF for cointegration
- Momentum filter: Only trade when short-term momentum agrees with mean reversion
- Entry: 2sigma deviation, 3-day hold max
- Exit: 0sigma or time-based

**Results:**
- 8-12% annual returns in equity pairs
- Strong in trending markets (momentum filter prevented adverse selection)

**Key insight:** Hybrid approach -- don't fight momentum, confirm with it

### 10.3 Research Paper: "Statistical Arbitrage in the U.S. Equity Markets" (Hedge Fund Literature)

**2003-2007 study:**
- 2,500+ stock pairs analyzed
- Mean reversion half-life < 10 days: Best performance
- Win rate: 58-62%
- Average profit: 0.8% per trade
- Maximum adverse excursion: 1.2% before mean reversion

**Key formulas:**
```
Expected Return = Win Rate x Avg Win - Loss Rate x Avg Loss
Sharpe Ratio (annualized) = (252 x Mean Daily Return) / (Std Dev x sqrt252)
```

### 10.4 Academic: Ornstein-Uhlenbeck in Trading (Brennan, Dai, Zeng 1999)

**Model:** OU process for spread dynamics in pairs  
**Finding:** theta (mean reversion speed) is the most important parameter  
**Recommendation:**
- Only trade pairs with theta > 0.1 (meaningful reversion within 5 days)
- Half-life = ln(2)/theta < 7 days for swing trading suitability

### 10.5 Practical Implementation Framework

**Step 1: Universe Screening**
- NSE 100 + Nifty ETF pairs
- Filter: Correlation > 0.70, CADF p < 0.05
- Liquidity: ADV > Rs5 crore

**Step 2: Entry Signal**
- Z-score > 2.0 or Bollinger %B > 1.1 / < -0.1
- RSI confirmation (RSI > 65 or < 35)
- Volume confirmation

**Step 3: Position Management**
- Entry: 50% target position
- Scale in at 2.5sigma if not immediately profitable
- Stop: 3sigma or ATR-based

**Step 4: Exit Execution**
- 50% at mean
- Remaining at target or time-based
- Trail stop after 50% mean hit

---

## 11. NSE-Specific Considerations

### 11.1 Market Structure

- **Trading hours:** 9:15 AM - 3:30 PM IST
- **Pre-open:** 9:00-9:15 AM (only Nifty/MidCap ETF orders)
- **Settlement:** T+1 (same day stock, next day funds)
- **Circuit filters:** 5%/10%/20% price bands (lower circuit = avoid)

### 11.2 NSE Liquidity Constraints

| Segment | Min ADV for Entry | Preferred ADV |
|---|---|---|
| Nifty 50 | Rs50 crore | Rs200 crore+ |
| Nifty Midcap 100 | Rs20 crore | Rs50 crore+ |
| Nifty Smallcap 250 | Rs5 crore | Rs20 crore+ |

**Avoid:** Stocks with bid-ask spread > 0.3% of price

### 11.3 Index Impact on Mean Reversion

NSE is heavily index-driven (Nifty 50 = 65% of NSE total turnover). Mean reversion strategies must account for:

- **Index futures impact:** SGX Nifty moves affect open
- **FII activity:** Large-cap mean reversion affected by FII flows
- **Domestic flows:** Mutual fund SIPs create unpredictable mean shifts

### 11.4 NSE Sector Mean Reversion Characteristics

| Sector | Mean Reversion Speed | Notes |
|---|---|---|
| Banking | Fast (2-3 days) | Sector rotation drives reversion |
| IT | Medium (3-5 days) | USD-INR impacts, global correlation |
| FMCG | Slow (5-7 days) | Defensive, sticky prices |
| Metal | Fast (1-3 days) | Commodity-driven, volatile |
| PSU Bank | Very Fast | Government actions, rapid reversion |

### 11.5 Regulatory & Tax Considerations

- **Securities Transaction Tax (STT):** 0.1% on equity delivery, 0.025% on intraday
- **Capital Gains:** Long-term (1 year) 10%, Short-term 15%
- **GST:** 18% on brokerage (if applicable)
- **Sebi turnover tax:** 0.02% (on sell side)

---

## 12. Strategy Comparison & Summary

### 12.1 Strategy Comparison Matrix

| Strategy | Timeframe | Win Rate Target | Risk:Reward | Complexity | Best Market |
|---|---|---|---|---|---|
| Bollinger Mean Reversion | 1-5 days | 55-65% | 1.5:1 | Low | Range-bound |
| RSI Mean Reversion | 1-3 days | 50-60% | 1:1 | Low | Oversold bounce |
| Pairs Trading (Distance) | 2-7 days | 60-70% | 1.5:1 | Medium | Sector rotation |
| Pairs Trading (Cointegration) | 3-10 days | 58-68% | 2:1 | High | All markets |
| VWAP Deviation | Intraday-2 days | 55-65% | 1.5:1 | Medium | Liquid stocks |
| Gap Fill | Same day-3 days | 60-70% | 2:1 | Medium | Gap fade |
| Keltner/CCI | 2-5 days | 50-60% | 1.5:1 | Medium | Volatile |

### 12.2 Parameter Cheat Sheet

**Bollinger Bands:**
- Period: 20
- Standard Deviation: 2.0
- Entry: %B < -0.1 or > 1.1
- Stop: 1.5x ATR beyond band

**RSI:**
- Period: 10-14
- Entry: < 35 (long), > 65 (short)
- Confirmation divergence required

**Pairs Trading:**
- Lookback: 60 days
- Entry Z-score: +/-2.0
- Exit Z-score: +/-0.5
- Min correlation: 0.70
- Cointegration p-value: < 0.05

**VWAP:**
- Entry: +/-2 SD bands
- Stop: +/-3 SD or VWAP extremes
- Target: VWAP (mean)

**Keltner Channel:**
- EMA: 20
- ATR: 10
- Multiplier: 2.0-3.0

**Gap Fill:**
- Entry threshold: 0.5% gap
- Stop: 1.5%
- Target: Previous close

### 12.3 Implementation Priority for NSE Swing

1. **Start:** Bollinger Bands + RSI combination (simplest, most robust)
2. **Add:** VWAP deviation for intraday confirmation
3. **Add:** Gap fill for overnight positions
4. **Advanced:** Pairs trading with cointegration
5. **Advanced:** Kalman filter pairs

### 12.4 Key Formulas Reference

**Half-life of mean reversion:**
```
HL = ln(2) / theta
```

**Z-score:**
```
Z = (X - mu) / sigma
```

**RSI:**
```
RSI = 100 - 100/(1 + RS)
RS = Avg Gain / Avg Loss
```

**CCI:**
```
CCI = (TP - SMA(TP)) / (0.015 x Mean Deviation)
```

**Kelly Criterion:**
```
Kelly % = (WxR - (1-W)) / R
W = win rate, R = win/loss ratio
```

**VWAP deviation:**
```
Deviation = (Price - VWAP) / VWAP x 100
```

---

## Appendix: Recommended Tools & Data Sources

- **Data:** NSE bhavcopy (daily), Kite Connect API (intraday), Alpha Vantage
- **Analysis:** Python (pandas, statsmodels, scipy, sklearn)
- **Visualization:** matplotlib, plotly
- **Backtesting:** Backtrader, vectorbt, custom
- **Broker integration:** Zerodha Kite, Angel Broking, Interactive Brokers

---

*Research compiled: May 2026*  
*Last reviewed: NSE market structure applicable to T+1 settlement framework*
