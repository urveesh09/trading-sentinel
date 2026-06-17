# Volume-Based Trading Strategies & Price Action Research

## Table of Contents
1. [Volume Surge Detection Algorithms](#1-volume-surge-detection-algorithms)
2. [Volume Profile Analysis](#2-volume-profile-analysis)
3. [Money Flow Indicators](#3-money-flow-indicators)
4. [Volume as Leading vs Confirming Indicator](#4-volume-as-leading-vs-confirming-indicator)
5. [Candlestick Pattern Algorithms](#5-candlestick-pattern-algorithms)
6. [Support/Resistance Detection](#6-supportresistance-detection)
7. [Volume Confirmation with Price Movement](#7-volume-confirmation-with-price-movement)
8. [Liquidity Considerations for Indian NSE Stocks](#8-liquidity-considerations-for-indian-nse-stocks)

---

## 1. Volume Surge Detection Algorithms

### 1.1 Absolute Volume Surge

Absolute volume surge detects when current volume exceeds a threshold multiplier over a baseline average.

**Algorithm:**
```
Input: volumes[], period (typically 20), multiplier (typically 2.0-3.0)
Output: boolean is_surge

baseline_avg = SMA(volumes, period)
current_vol = volumes[-1]

if current_vol > (baseline_avg * multiplier):
    is_surge = True
else:
    is_surge = False
```

**Pseudocode (Python-like):**
```python
def detect_absolute_volume_surge(volumes: list, period: int = 20, multiplier: float = 2.0) -> bool:
    if len(volumes) < period:
        return False
    baseline_avg = sum(volumes[-period:]) / period
    current_vol = volumes[-1]
    return current_vol > (baseline_avg * multiplier)
```

### 1.2 Relative Volume (RVI) Surge

Relative Volume compares current volume to the average volume at the same time of day (for intraday) or same day-of-week (for daily).

**Algorithm:**
```
Input: volumes[], current_time, time_bucket_avg_volumes{}
Output: relative_volume_ratio

current_bucket_avg = time_bucket_avg_volumes[current_time]
relative_volume = current_vol / current_bucket_avg
```

**Pseudocode:**
```python
def calculate_relative_volume(volumes: list, current_bar_index: int, 
                               avg_volumes_by_time: dict) -> float:
    current_vol = volumes[current_bar_index]
    time_bucket = get_time_bucket(current_bar_index)  # e.g., "09:30-09:45"
    expected_vol = avg_volumes_by_time.get(time_bucket, 
                                           sum(avg_volumes_by_time.values()) / len(avg_volumes_by_time))
    return current_vol / expected_vol if expected_vol > 0 else 0
```

### 1.3 Volume Spike Detection with VWAP Confirmation

A more robust approach combines volume surge with VWAP-relative price action.

**Algorithm:**
```
Input: candles[] (OHLCV), volume_surge_threshold, vwap_tolerance
Output: signal

for each candle:
    if candle.volume > (SMA(candle.volumes[-20:]) * 2.0):
        if candle.close > candle.vwap AND candle.close > candle.open:
            signal = "BULLISH_VOLUME_SPIKE"
        elif candle.close < candle.vwap AND candle.close < candle.open:
            signal = "BEARISH_VOLUME_SPIKE"
        else:
            signal = "VOLUME_SPIKE_UNCONFIRMED"
```

### 1.4 Implementation Notes

| Parameter | Typical Value | Notes |
|-----------|--------------|-------|
| Volume SMA period | 20 bars | Shorter for volatile stocks |
| Surge multiplier | 2.0 - 3.0 | Higher = fewer signals |
| Relative volume lookback | 20-30 days | For seasonal patterns |
| VWAP tolerance | 0.1-0.5% | For price confirmation |

---

## 2. Volume Profile Analysis

### 2.1 Core Concept

Volume Profile divides the price range into bins and accumulates volume traded at each price level, revealing:
- **High-Volume Nodes (HVN)**: Price zones with significant trading activity (equilibrium zones)
- **Low-Volume Areas (LVA) / Pool Areas**: Zones with minimal volume (liquidity voids)
- **Point of Control (POC)**: The price level with the highest traded volume

### 2.2 Volume Profile Algorithm

**Algorithm:**
```
Input: candles[], num_bins (typically 20-50)
Output: profile{} mapping price_level -> volume

price_min = min(candle.low for candle in candles)
price_max = max(candle.high for candle in candles)
bin_width = (price_max - price_min) / num_bins

for each candle in candles:
    for price from candle.low to candle.high step bin_width:
        bin_index = int((price - price_min) / bin_width)
        profile[bin_index] += candle.volume * (bin_width / (candle.high - candle.low))

POC = bin_index with maximum volume in profile
HVN_regions = bins where volume > threshold (e.g., 70% of average)
LVA_regions = bins where volume < threshold (e.g., 30% of average)
```

**Pseudocode:**
```python
def calculate_volume_profile(candles: list, num_bins: int = 30) -> dict:
    lows = [c['low'] for c in candles]
    highs = [c['high'] for c in candles]
    
    price_min, price_max = min(lows), max(highs)
    bin_width = (price_max - price_min) / num_bins
    
    profile = [0.0] * num_bins
    
    for candle in candles:
        candle_height = candle['high'] - candle['low']
        if candle_height == 0:
            continue
        # Distribute volume proportionally across price range
        for i in range(num_bins):
            bin_price = price_min + (i * bin_width)
            if price_min <= bin_price <= price_max:
                # Find overlap between candle range and bin
                overlap = min(candle['high'], price_min + (i+1)*bin_width) - \
                          max(candle['low'], price_min + i*bin_width)
                if overlap > 0:
                    profile[i] += candle['volume'] * (overlap / candle_height)
    
    return {
        'profile': profile,
        'bin_width': bin_width,
        'price_min': price_min,
        'poc': price_min + (profile.index(max(profile)) * bin_width)
    }
```

### 2.3 VWAP (Volume-Weighted Average Price)

VWAP represents the average price weighted by volume, serving as the intraday benchmark.

**Formula:**
```
VWAP = Sum(Price x Volume) / Sum(Volume)
```

**Running VWAP Calculation:**
```python
def calculate_running_vwap(candles: list) -> list:
    vwaps = []
    cumulative_pv = 0.0
    cumulative_vol = 0.0
    
    for candle in candles:
        typical_price = (candle['high'] + candle['low'] + candle['close']) / 3
        cumulative_pv += typical_price * candle['volume']
        cumulative_vol += candle['volume']
        vwaps.append(cumulative_pv / cumulative_vol if cumulative_vol > 0 else 0)
    
    return vwaps
```

### 2.4 VWAP Usage in Trading

| Scenario | VWAP Interpretation |
|----------|---------------------|
| Price > VWAP | Bullish bias (for intraday) |
| Price < VWAP | Bearish bias (for intraday) |
| Price crossing VWAP | Potential trend change |
| VWAP slope | Trend direction confirmation |
| Price reverting to VWAP | Mean reversion opportunity |

---

## 3. Money Flow Indicators

### 3.1 On-Balance Volume (OBV)

OBV accumulates volume based on price direction, assuming volume precedes price movement.

**Algorithm:**
```
if close > close_prev:
    OBV += volume
elif close < close_prev:
    OBV -= volume
else:
    OBV unchanged
```

**Pseudocode:**
```python
def calculate_obv(candles: list) -> list:
    obv = [0]
    for i in range(1, len(candles)):
        if candles[i]['close'] > candles[i-1]['close']:
            obv.append(obv[-1] + candles[i]['volume'])
        elif candles[i]['close'] < candles[i-1]['close']:
            obv.append(obv[-1] - candles[i]['volume'])
        else:
            obv.append(obv[-1])
    return obv
```

**Trading Signals:**
- OBV rising + price rising = Confirmed uptrend
- OBV falling + price falling = Confirmed downtrend
- OBV rising + price flat = Potential accumulation (bullish divergence)
- OBV falling + price flat = Potential distribution (bearish divergence)

### 3.2 Accumulation/Distribution Line (A/D)

A/D uses the close position within the daily range (close location value) multiplied by volume.

**Formula:**
```
Money Flow Multiplier = [(Close - Low) - (High - Close)] / (High - Low)
                        = (2 x Close - High - Low) / (High - Low)

Money Flow Volume = Money Flow Multiplier x Volume
A/D = Cumulative Sum of Money Flow Volume
```

**Pseudocode:**
```python
def calculate_ad_line(candles: list) -> list:
    ad = []
    cumulative_ad = 0
    
    for candle in candles:
        high, low, close, volume = candle['high'], candle['low'], candle['close'], candle['volume']
        range_ = high - low
        
        if range_ > 0:
            mfm = ((close - low) - (high - close)) / range_
            mfv = mfm * volume
            cumulative_ad += mfv
        
        ad.append(cumulative_ad)
    
    return ad
```

### 3.3 Money Flow Index (MFI)

MFI is volume-weighted RSI--measuring the rate at which money flows in and out of a security.

**Algorithm:**
```
1. Typical Price = (High + Low + Close) / 3
2. Raw Money Flow = Typical Price x Volume
3. Classify as Positive or Negative Money Flow based on TP vs Previous TP
4. Money Ratio = Sum(Positive Money Flow) / Sum(Negative Money Flow)
5. MFI = 100 - (100 / (1 + Money Ratio))

Alternatively:
MFI = 100 x (Positive Money Flow / (Positive Money Flow + Negative Money Flow))
```

**Pseudocode:**
```python
def calculate_mfi(candles: list, period: int = 14) -> list:
    mfi_values = []
    typical_prices = [(c['high'] + c['low'] + c['close']) / 3 for c in candles]
    raw_money_flow = [tp * candles[i]['volume'] for i, tp in enumerate(typical_prices)]
    
    for i in range(period, len(candles)):
        positive_flow = 0
        negative_flow = 0
        
        for j in range(i - period + 1, i + 1):
            if typical_prices[j] > typical_prices[j-1]:
                positive_flow += raw_money_flow[j]
            elif typical_prices[j] < typical_prices[j-1]:
                negative_flow += raw_money_flow[j]
        
        if negative_flow == 0:
            mfi = 100
        else:
            money_ratio = positive_flow / negative_flow
            mfi = 100 - (100 / (1 + money_ratio))
        
        mfi_values.append(mfi)
    
    return mfi_values
```

**Signal Interpretation:**
| MFI Range | Interpretation |
|-----------|----------------|
| > 80 | Overbought (potential reversal) |
| < 20 | Oversold (potential reversal) |
| > 80 + Price divergence | Strong bearish signal |
| < 20 + Price divergence | Strong bullish signal |

### 3.4 Chaikin Money Flow (CMF)

CMF measures the amount of Money Flow Volume over a specific period, scaled to -1 to +1.

**Formula:**
```
CMF = Sum(Money Flow Volume for N periods) / Sum(Volume for N periods)
```

**Pseudocode:**
```python
def calculate_cmf(candles: list, period: int = 20) -> list:
    cmf_values = []
    
    for i in range(period - 1, len(candles)):
        ad_sum = 0
        volume_sum = 0
        
        for j in range(i - period + 1, i + 1):
            high, low, close, volume = candles[j]['high'], candles[j]['low'], \
                                       candles[j]['close'], candles[j]['volume']
            range_ = high - low
            
            if range_ > 0:
                mfm = ((close - low) - (high - close)) / range_
                ad_sum += mfm * volume
                volume_sum += volume
        
        cmf = ad_sum / volume_sum if volume_sum > 0 else 0
        cmf_values.append(cmf)
    
    return cmf_values
```

**Signal Interpretation:**
| CMF Value | Interpretation |
|-----------|----------------|
| CMF > 0 | Buying pressure (accumulation) |
| CMF < 0 | Selling pressure (distribution) |
| CMF crossing above 0 | Bullish signal |
| CMF crossing below 0 | Bearish signal |

### 3.5 Comparison Table

| Indicator | Scale | Best Use Case |
|-----------|-------|---------------|
| OBV | Cumulative | Trend confirmation, divergence |
| A/D | Cumulative | Accumulation/distribution detection |
| MFI | 0-100 | Overbought/oversold with volume |
| CMF | -1 to +1 | Short-term pressure shifts |

---

## 4. Volume as Leading vs Confirming Indicator

### 4.1 Leading Indicators (Volume Precedes Price)

Volume often leads price because institutional players accumulate positions before price moves.

**Leading Signals:**
- Volume surge without price move = Smart money positioning
- OBV divergence from price = Reversal warning
- Low volume on breakout = False breakout likely

**Algorithm for Volume Leading Signal:**
```
if (volume[-1] > avg_volume * 2) AND (abs(price_change[-1]) < threshold):
    signal = "VOLUME_LEADING_PRICE"
```

### 4.2 Confirming Indicators (Price Confirms Volume)

Volume confirms the validity of price moves.

**Confirming Signals:**
- Price breaking resistance + high volume = Valid breakout
- Price making new high + OBV making new high = Strong uptrend
- Volume decreasing as price rises = Weak momentum (divergence)

### 4.3 Volume-Price Relationship Matrix

| Volume | Price | Interpretation |
|--------|-------|----------------|
| up | up | Strong bullish (follow through likely) |
| up | down | Strong bearish (follow through likely) |
| down | up | Weak bullish (reversal possible) |
| down | down | Weak bearish (reversal possible) |
| up | Flat | Accumulation/distribution (watch for breakout) |

---

## 5. Candlestick Pattern Algorithms

### 5.1 Candlestick Representation

```python
@dataclass
class Candle:
    open: float
    high: float
    low: float
    close: float
    volume: float

# Body size
body_size = abs(candle.close - candle.open)

# Upper shadow
upper_shadow = candle.high - max(candle.open, candle.close)

# Lower shadow
lower_shadow = min(candle.open, candle.close) - candle.low

# Is bullish/bearish
is_bullish = candle.close > candle.open
is_bearish = candle.close < candle.open
```

### 5.2 Doji Pattern

A doji forms when open and close are nearly equal, indicating indecision.

**Algorithm:**
```python
def is_doji(candle: Candle, threshold: float = 0.1) -> bool:
    body_size = abs(candle.close - candle.open)
    total_range = candle.high - candle.low
    
    if total_range == 0:
        return False
    
    # Doji: body is small relative to full range
    return body_size / total_range < threshold
```

**Variants:**
- **Gravestone Doji**: Open = Close near low (bearish reversal)
- **Dragonfly Doji**: Open = Close near high (bullish reversal)
- **Long-legged Doji**: Large range with centered open/close

### 5.3 Hammer and Hanging Man

**Hammer** (bullish reversal at bottom):
```python
def is_hammer(candle: Candle, lookback_percent: float = 0.02) -> bool:
    body_size = abs(candle.close - candle.open)
    lower_shadow = min(candle.open, candle.close) - candle.low
    upper_shadow = candle.high - max(candle.open, candle.close)
    total_range = candle.high - candle.low
    
    # Lower shadow at least 2x body
    # Upper shadow small
    # Appears near bottom of recent range
    recent_low = min(candle.low for c in recent_candles)  # defined elsewhere
    
    return (lower_shadow >= 2 * body_size and 
            upper_shadow < body_size * 0.5 and
            candle.low <= recent_low * (1 + lookback_percent))
```

**Hanging Man** (bearish at top): Same pattern but after uptrend.

### 5.4 Engulfing Pattern

**Bullish Engulfing:**
```python
def is_bullish_engulfing(current: Candle, previous: Candle) -> bool:
    # Previous is bearish
    prev_bearish = previous.close < previous.open
    # Current is bullish
    curr_bullish = current.close > current.open
    # Current body engulfs previous body
    engulfs = (current.open < previous.close and 
               current.close > previous.open)
    
    return prev_bearish and curr_bullish and engulfs
```

**Bearish Engulfing:**
```python
def is_bearish_engulfing(current: Candle, previous: Candle) -> bool:
    prev_bullish = previous.close > previous.open
    curr_bearish = current.close < current.open
    engulfs = (current.open > previous.close and 
               current.close < previous.open)
    
    return prev_bullish and curr_bearish and engulfs
```

### 5.5 Morning Star / Evening Star

**Morning Star** (3-candle bullish reversal):
```python
def is_morning_star(candles: list, i: int) -> bool:
    """
    candles[i-2]: Large bearish candle
    candles[i-1]: Small body (doji or small candle)
    candles[i]: Large bullish candle
    """
    c1, c2, c3 = candles[i-2], candles[i-1], candles[i]
    
    c1_bearish = c1.close < c1.open
    c3_bullish = c3.close > c3.open
    
    c2_small_body = abs(c2.close - c2.open) < abs(c1.close - c1.open) * 0.3
    
    # Gap down from c1 to c2, gap up from c2 to c3
    c2_in_range = max(c2.low, c2.open, c2.close) < c1.close
    c3_closes_above_c1_mid = c3.close > (c1.open + c1.close) / 2
    
    return c1_bearish and c2_small_body and c3_bullish and c2_in_range and c3_closes_above_c1_mid
```

**Evening Star**: Inverse of Morning Star (bearish reversal).

### 5.6 Pattern Recognition Summary Table

| Pattern | Candles | Type | Key Requirement |
|---------|---------|------|-----------------|
| Doji | 1 | Reversal | Open ~= Close |
| Hammer | 1 | Reversal | Long lower shadow |
| Engulfing | 2 | Reversal | Body 2 engulfs Body 1 |
| Morning Star | 3 | Reversal | Gap + small middle |
| Evening Star | 3 | Reversal | Gap + small middle |
| Three White Soldiers | 3 | Continuation | Three rising bullish |
| Three Black Crows | 3 | Continuation | Three falling bearish |

### 5.7 Algorithmic Pattern Confidence Scoring

```python
def pattern_confidence(pattern_name: str, candles: list, index: int) -> float:
    """
    Returns confidence score 0.0 to 1.0 based on multiple factors:
    - Volume confirmation
    - Trend context
    - Shadow ratios
    - Gap presence
    """
    base_confidence = 0.5
    volume_boost = 0.2 if candles[index].volume > avg_volume(candles, 20) else 0
    trend_context = calculate_trend_context(candles, index)  # -0.2 to +0.2
    
    return min(1.0, base_confidence + volume_boost + trend_context)
```

---

## 6. Support/Resistance Detection

### 6.1 Pivot Points (Classical)

Standard pivot points use previous period's high, low, and close.

**Formulas:**
```
Pivot Point (PP) = (Previous High + Previous Low + Previous Close) / 3

Support 1 (S1) = (2 x PP) - Previous High
Support 2 (S2) = PP - (Previous High - Previous Low)
Support 3 (S3) = Previous Low - 2 x (Previous High - PP)

Resistance 1 (R1) = (2 x PP) - Previous Low
Resistance 2 (R2) = PP + (Previous High - Previous Low)
Resistance 3 (R3) = Previous High + 2 x (PP - Previous Low)
```

**Pseudocode:**
```python
def calculate_pivot_points(high: float, low: float, close: float) -> dict:
    pp = (high + low + close) / 3
    
    return {
        'pp': pp,
        'r1': 2 * pp - low,
        'r2': pp + (high - low),
        'r3': high + 2 * (pp - low),
        's1': 2 * pp - high,
        's2': pp - (high - low),
        's3': low - 2 * (high - pp)
    }
```

### 6.2 Fibonacci Pivot Points

```python
def calculate_fib_pivot_points(high: float, low: float, close: float) -> dict:
    pp = (high + low + close) / 3
    range_ = high - low
    
    return {
        'pp': pp,
        'r1': pp + 0.382 * range_,
        'r2': pp + 0.618 * range_,
        'r3': pp + 1.0 * range_,
        's1': pp - 0.382 * range_,
        's2': pp - 0.618 * range_,
        's3': pp - 1.0 * range_
    }
```

### 6.3 Fractal Support/Resistance

Fractals identify significant swing highs and lows.

**Algorithm (Bill Williams Fractal):**
```
For a 5-bar sequence [i-2, i-1, i, i+1, i+2]:
- Bullish Fractal: bar[i] is highest high
- Bearish Fractal: bar[i] is lowest low
```

```python
def detect_fractals(candles: list, period: int = 2) -> tuple:
    """
    Returns lists of bullish and bearish fractal levels.
    period=2 means 5-bar fractal (2 left + center + 2 right)
    """
    bullish_fractals = []
    bearish_fractals = []
    
    for i in range(period, len(candles) - period):
        is_bullish = True
        is_bearish = True
        
        center_high = candles[i]['high']
        center_low = candles[i]['low']
        
        # Check left side
        for j in range(i - period, i):
            if candles[j]['high'] >= center_high:
                is_bullish = False
            if candles[j]['low'] <= center_low:
                is_bearish = False
        
        # Check right side
        for j in range(i + 1, i + period + 1):
            if candles[j]['high'] >= center_high:
                is_bullish = False
            if candles[j]['low'] <= center_low:
                is_bearish = False
        
        if is_bullish:
            bullish_fractals.append(center_high)
        if is_bearish:
            bearish_fractals.append(center_low)
    
    return bullish_fractals, bearish_fractals
```

### 6.4 Volume-Based Support/Resistance

Support/resistance strengthens when volume clusters at price levels.

**Algorithm:**
```python
def detect_volume_support_resistance(candles: list, num_price_bins: int = 50,
                                      volume_threshold_percentile: float = 80) -> list:
    """
    Identify S/R levels based on volume profile.
    """
    price_levels = extract_price_levels(candles)  # Volume at each price
    threshold = numpy.percentile(list(price_levels.values()), 
                                  volume_threshold_percentile)
    
    sr_levels = [price for price, vol in price_levels.items() 
                 if vol >= threshold]
    
    return sorted(sr_levels)
```

### 6.5 Supply/Demand Zone Detection

**Demand Zone** (bullish):
- Price dropped sharply on high volume
- Price rebounded with low volume
- Zone retested after consolidation

**Supply Zone** (bearish):
- Price rose sharply on high volume  
- Price reversed with low volume
- Zone retested after consolidation

**Algorithm:**
```python
def detect_supply_demand_zones(candles: list, impulse_threshold: float = 2.0) -> list:
    """
    Identify supply and demand zones based on impulse moves.
    impulse_threshold: Volume multiple for impulse[rentong]定 (e.g., 2.0 = 2x average)
    """
    zones = []
    avg_volume = sum(c['volume'] for c in candles) / len(candles)
    
    for i in range(1, len(candles) - 1):
        prev_vol = candles[i-1]['volume']
        
        # Impulsive move down (demand setup)
        if candles[i]['volume'] > avg_volume * impulse_threshold:
            drop = candles[i-1]['close'] - candles[i]['close']
            if drop > 0 and (candles[i]['close'] - candles[i]['low']) < drop * 0.3:
                zones.append({
                    'type': 'demand',
                    'high': candles[i-1]['close'],
                    'low': candles[i]['low'],
                    'strength': candles[i]['volume'] / avg_volume
                })
        
        # Impulsive move up (supply setup)
        if candles[i]['volume'] > avg_volume * impulse_threshold:
            rise = candles[i]['close'] - candles[i-1]['close']
            if rise > 0 and (candles[i]['high'] - candles[i]['close']) < rise * 0.3:
                zones.append({
                    'type': 'supply',
                    'high': candles[i]['high'],
                    'low': candles[i-1]['close'],
                    'strength': candles[i]['volume'] / avg_volume
                })
    
    return zones
```

### 6.6 S/R Detection Algorithm Comparison

| Method | Lookback | Best For |
|--------|----------|----------|
| Pivot Points | 1 period | Intraday trading |
| Fractals | 2-5 bars | Swing trading |
| Volume Profile | All data | Finding key levels |
| Supply/Demand | Impulse moves | Trend reversal setups |

---

## 7. Volume Confirmation with Price Movement

### 7.1 Divergence Strategies

Divergence occurs when price and volume/indicators move in opposite directions.

**Bullish Divergence (Reversal to Upside):**
- Price makes lower low
- Indicator (OBV/MFI/CMF) makes higher low
- Indicates hidden buying pressure

**Bearish Divergence (Reversal to Downside):**
- Price makes higher high
- Indicator makes lower high
- Indicates hidden selling pressure

**Algorithm:**
```python
def detect_divergence(price: list, indicator: list, 
                      lookback: int = 20, threshold: float = 0.05) -> str:
    """
    Detect price-indicator divergence.
    """
    # Find recent price highs/lows
    price_slope = (price[-1] - price[-lookback]) / lookback
    indicator_slope = (indicator[-1] - indicator[-lookback]) / lookback
    
    # Normalize slopes to same scale
    price_normalized = price_slope / price[-lookback]
    indicator_normalized = indicator_slope / indicator[-lookback] if indicator[-lookback] != 0 else 0
    
    diff = price_normalized - indicator_normalized
    
    if diff > threshold:
        return "BULLISH_DIVERGENCE"  # Price down, indicator up
    elif diff < -threshold:
        return "BEARISH_DIVERGENCE"  # Price up, indicator down
    else:
        return "NO_DIVERGENCE"
```

### 7.2 Volume Confirmation for Breakouts

**Breakout Confirmation Algorithm:**
```python
def confirm_breakout(price: float, resistance: float, 
                     volume: float, avg_volume: float,
                     volume_multiplier: float = 1.5) -> dict:
    """
    Determine if breakout is genuine based on volume.
    """
    price_breakout = price > resistance
    
    if not price_breakout:
        return {'confirmed': False, 'reason': 'price_not_broken'}
    
    volume_surge = volume > avg_volume * volume_multiplier
    
    return {
        'confirmed': price_breakout and volume_surge,
        'price_breakout': price_breakout,
        'volume_surge': volume_surge,
        'volume_ratio': volume / avg_volume if avg_volume > 0 else 0
    }
```

### 7.3 Volume Confirmation Matrix

| Price Action | Volume | Signal Strength |
|--------------|--------|-----------------|
| Breakout up | Volume up | Very Strong |
| Breakout up | Volume down | Weak (false breakout risk) |
| Breakdown down | Volume up | Very Strong |
| Breakdown down | Volume down | Weak (false breakdown risk) |
| Price up | Volume up | Strong Uptrend |
| Price up | Volume down | Weak (exhaustion risk) |
| Price down | Volume up | Strong Downtrend |
| Price down | Volume down | Weak (exhaustion risk) |

---

## 8. Liquidity Considerations for Indian NSE Stocks

### 8.1 Liquidity Metrics

**Average Daily Volume (ADV):**
```python
def calculate_adv(candles: list, days: int = 20) -> float:
    """Calculate Average Daily Volume."""
    volumes = [c['volume'] for c in candles[-days:]]
    return sum(volumes) / len(volumes)
```

**Turnover (INR):**
```python
def calculate_turnover(candle: Candle) -> float:
    """Calculate turnover in INR."""
    typical_price = (candle.high + candle.low + candle.close) / 3
    return typical_price * candle.volume
```

### 8.2 Liquidity Criteria for Indian NSE

| Metric | Liquid Stock | Illiquid Stock |
|--------|-------------|----------------|
| Average Daily Turnover | > Rs5 Crores | < Rs1 Crore |
| Bid-Ask Spread | < 0.2% | > 0.5% |
| Impact Cost | < 0.1% | > 0.3% |
| Delivery Percentage | 20-60% typical | > 80% or < 10% |

### 8.3 Impact Cost Calculation

```python
def calculate_impact_cost(bid_levels: list, ask_levels: list, 
                          order_quantity: float) -> float:
    """
    Calculate impact cost for given order size.
    bid_levels, ask_levels: list of (price, quantity) tuples
    """
    def weighted_price(levels, qty):
        remaining = qty
        total_cost = 0
        for price, quantity in levels:
            fill = min(remaining, quantity)
            total_cost += fill * price
            remaining -= fill
            if remaining <= 0:
                break
        return total_cost / (qty - remaining) if remaining < qty else None
    
    mid_price = (bid_levels[0][0] + ask_levels[0][0]) / 2
    
    buy_cost = weighted_price(ask_levels, order_quantity)
    sell_cost = weighted_price(bid_levels, order_quantity)
    
    if buy_cost is None or sell_cost is None:
        return float('inf')
    
    return ((buy_cost - sell_cost) / (2 * mid_price)) * 100
```

### 8.4 NSE-Specific Liquidity Screening

**For Algorithmic Trading in India:**
```python
def liquidity_screen(stock_data: dict, min_adv: float = 5_00_00_000,  # 5 Crore
                     min_free_float: float = 0.2) -> dict:
    """
    Screen stock for liquidity suitability.
    """
    adv = stock_data['adv_20_days']
    market_cap = stock_data['market_cap']
    free_float = stock_data['outstanding_shares'] * stock_data['public_shareholding']
    free_float_market_cap = free_float * stock_data['current_price']
    
    return {
        'adv_ok': adv >= min_adv,
        'free_float_ok': free_float_market_cap >= min_adv * 3,  # 3x ADV typical
        'liquid_indices': stock_data['index_membership'],  # Nifty 50, Nifty 200, etc.
        'futures_available': stock_data['has_futures'],  # Can hedge with futures
        'options_available': stock_data['has_options'],
        'overall_suitable': (adv >= min_adv and 
                            free_float_market_cap >= min_adv * 3)
    }
```

### 8.5 Volume Filtering for Illiquid Stocks

```python
def adjust_for_liquidity(raw_signal: dict, stock: Stock, 
                        max_position_percent: float = 0.02) -> dict:
    """
    Adjust trade size based on stock liquidity.
    """
    adv = stock.avg_daily_volume
    
    # Maximum position based on ADV (don't exceed 10% of ADV)
    max_volume = adv * 0.10
    
    # Further reduce for mid-cap stocks
    if stock.market_cap < 10_000:  # Crores
        max_position_percent *= 0.5
    
    # For Nifty 50 stocks, can use full parameter
    if stock.index == 'Nifty 50':
        max_position_percent = min(max_position_percent * 2, 0.05)
    
    return {
        **raw_signal,
        'max_position_size': max_volume,
        'position_percent': max_position_percent,
        'estimated_impact': estimate_market_impact(stock, max_volume)
    }
```

### 8.6 Considerations for NSE Algorithmic Trading

| Factor | Consideration |
|--------|----------------|
| **Circuit Filters** | 5%/10%/20% price bands - cannot trade beyond |
| **Auction Sessions** | Pre-open session (09:00-09:08) affects opening price |
| **Block Deals** | Large trades in pre-open may indicate institutional activity |
| **Mutual Fund Flow** | DII activity often visible in volume patterns |
| **F&O Securities** | Preferred for algo due to better liquidity |
| **T+2 Settlement** | Position keeping in mind settlement cycle |

---

## Summary: Key Implementation Points

### Volume-Based Strategy Checklist

- [ ] Calculate volume surge with relative threshold (not absolute)
- [ ] Use VWAP as intraday benchmark; above = bullish, below = bearish
- [ ] Combine OBV/MFI/CMF for robust money flow analysis
- [ ] Require volume confirmation for breakout trades
- [ ] Implement candlestick patterns with volume filter
- [ ] Use fractal/pivot combinations for S/R detection
- [ ] Always filter for NSE liquidity before generating signals

### Recommended Indicator Combinations

| Strategy | Indicators |
|----------|------------|
| Trend Following | VWAP + OBV + Volume Profile |
| Mean Reversion | MFI + VWAP + Doji patterns |
| Breakout | Volume surge + CMF + Fractals |
| Reversal | Divergence (OBV/MFI) + Hammer/Engulfing |

### Risk Management with Volume

1. **Reduce position size** when volume is abnormally low (illiquid market)
2. **Avoid trading** when volume spikes coincide with news events
3. **Use limit orders** for illiquid stocks to avoid impact cost
4. **Monitor bid-ask spread** as proxy for transaction costs

---

*Research completed for algorithmic trading system implementation. All formulas should be validated with historical backtesting before live deployment.*