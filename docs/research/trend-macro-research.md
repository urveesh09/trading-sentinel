# Trend-Following and Macro Algorithmic Trading Strategies

## 1. Trend-Following Foundations

### 1.1 Donchian Channel

The Donchian Channel is a trend-following indicator formed by price bands derived from the highest high and lowest low over a specified period.

**Construction:**
- Upper Band = Highest High over N periods
- Lower Band = Lowest Low over N periods
- Middle Band = (Upper + Lower) / 2

**Standard Parameters:**
- Short-term: 10-20 periods (intraday/day)
- Medium-term: 20-55 periods
- Long-term: 55-200 periods

**Trading Rules:**
- **Long Entry**: Price closes above upper band -> buy
- **Short Entry**: Price closes below lower band -> sell short
- **Exit**: Price reverses to middle band or opposite signal

**Variations:**
- Morning Star: Uses highest high/lowest low of yesterday for overnight positions
- Triple Donchian: Uses 3 different timeframes for confirmation

### 1.2 Turtle Trading Rules

The Turtle trading system is one of the most famous trend-following approaches, developed by Richard Dennis and William Eckhardt in the 1980s.

**Original Turtle Rules:**

**Entry:**
- Buy breakouts above highest high of last 20 days
- Sell short breakouts below lowest low of last 20 days

**Exit:**
- Exit long when price falls below lowest low of last 10 days
- Exit short when price rises above highest high of last 10 days

**Position Sizing:**
- Unit = 1% of account risk per trade
- Maximum 4 units per instrument
- Maximum 6 correlated instruments
- Maximum 10 total units across all positions

**Stops:**
- Initial stop: 2N from entry (N = 20-day ATR)
- Pyramid additions every 0.5N up to 4 units

**Modern Adaptations:**
- ATR-based exits replacing fixed-period exits
- Dynamic lookback windows (22-55 days range)
- Volatility-normalized position sizing

### 1.3 Moving Average Crossover Systems

**Simple Moving Average (SMA):**
- Equal weighting of all periods
- Formula: SMA = (P1 + P2 + ... + Pn) / n
- Best for: Long-term trends, reduced noise sensitivity

**Exponential Moving Average (EMA):**
- More weight on recent prices
- Formula: EMA = (Price x k) + (Previous EMA x (1-k)), where k = 2/(n+1)
- Best for: Short-to-medium term, faster signal generation

**Weighted Moving Average (WMA):**
- Linear weighting (most recent = highest weight)
- Formula: WMA = (P1x1 + P2x2 + ... + Pnxn) / (1+2+...+n)
- Best for: Medium-term, balances responsiveness vs. smoothness

**Dual Moving Average Systems:**
- **Golden Cross**: Short MA crosses above long MA -> Buy signal
- **Death Cross**: Short MA crosses below long MA -> Sell signal
- **Common Pairs:**
  - 5/20-day (short-term)
  - 20/50-day (medium-term)
  - 50/200-day (long-term, "200-day rule")

**Triple Moving Average System:**
- Uses three MAs to filter false signals
- Example: 4/9/18-day system
  - Entry: When fastest MA aligns with medium MA direction, confirmed by slowest
  - Exit: When fastest MA reverses
- Reduces whipsaws but introduces lag

**Guppy Multi-Moving Average (GMMA):**
- Short group: 3, 5, 8, 10, 12, 15 EMAs
- Long group: 30, 35, 40, 45, 50, 55 EMAs
- Crossover between groups indicates trend changes
- Spread expansion = trend strengthening

---

## 2. Time-Series Momentum (TSMOM)

### 2.1 Moskowitz (2012) Paper: "Time Series Momentum"

**Core Finding:** Past returns predict future returns across asset classes and timeframes.

**Key Parameters:**
- **Lookback Period**: 12 months (252 trading days)
- **Holding Period**: 1 month (21 trading days)
- **Skip Month**: 1-month gap between lookback and holding to avoid microstructure biases

**Methodology:**
```
Signal(t) = sign of return(t-12, t-1)
Position = Signal x (1/Volatility)
```

### 2.2 Volatility Scaling

**Purpose:** Equalize risk contribution across assets and timeframes.

**Implementation:**
- Target volatility = 40% annualized (or asset-specific)
- Position = (Target Vol / Realized Vol) x Signal
- Lookback for volatility: 60-90 days

**Exponential Volatility Estimation:**
```
sigma^2(t) = lambda x sigma^2(t-1) + (1-lambda) x r^2(t-1)
where lambda typically 0.94-0.96
```

### 2.3 Rebalancing Frequency

| Frequency | Pros | Cons |
|-----------|------|------|
| Monthly | Low transaction costs, aligns with TSMOM academic research | Lag in signal, less responsive |
| Weekly | Better responsiveness, moderate costs | Higher turnover |
| Daily | Most responsive, captures short-term trends | High transaction costs, whipsaws |

**Evidence:**
- Moskowitz et al.: Monthly rebalancing optimal for long-term TSMOM
- Daily rebalancing shows momentum craps (short-term reversal)
- Weekly provides good balance for medium-frequency systems

### 2.4 Extensions and Variations

- **Hussain:** 3-month lookback with 1-month skip shows stronger results
- **12-month momentum with 1-month reversal:** Evidence of "momentum gap"
- **Multi-horizon TSMOM:** Combining 1, 3, 6, 12-month signals

---

## 3. Cross-Sectional Momentum

### 3.1 Relative Strength Ranking

**Construction:**
1. Calculate total return for each asset over lookback period
2. Rank all assets by return
3. Go long top performers, short bottom performers

**Parameters:**
- Lookback: 1-12 months (commonly 6 or 12)
- Holding: 1 week to 1 month
- Number of assets: Top/bottom 10-20%

### 3.2 Top-N Basket Approach

**Long-Only Version:**
- Rank all candidates by momentum score
- Select top N (typically 10-30)
- Equal weight or risk-weighted

**Long-Short Version:**
- Long: Top decile
- Short: Bottom decile
- Net zero market exposure

**Key Considerations:**
- Minimum capitalization/liquidity filters
- Sector diversification constraints
- Transaction cost estimation

### 3.3 Sector-Relative Momentum

**Approach:**
- Calculate momentum within each sector
- Go long top sectors, short bottom sectors
- Reduces market-wide factor exposure

**Two-Pass Method:**
1. First pass: Compute relative strength within each sector
2. Second pass: Rank sectors by aggregate relative strength

### 3.4 Cross-Sectional vs. Time-Series Momentum

| Aspect | Time-Series | Cross-Sectional |
|--------|-------------|-----------------|
| Signal | Absolute return | Return vs. peer group |
| Direction | Always in trend direction | Long top, short bottom |
| Market exposure | Varies with market direction | Market-neutral option |
| Turnover | Lower | Higher |
| Max drawdown | Can be severe in reversals | More stable |

---

## 4. Macro Strategies

### 4.1 Currency Trend Following (G10)

**G10 Currencies:** USD, EUR, JPY, GBP, AUD, NZD, CAD, CHF, SEK, NOK

**Characteristics:**
- High liquidity, low transaction costs
- 24-hour market, no gaps
- Interest rate differential (roll) matters
- Central bank intervention risk

**Trend-Following Application:**
- Uses same Donchian/Turtle/MACD rules as equities/commodities
- Typical lookback: 20-60 days
- Position sizing reduced by higher volatility

**Key Factors:**
- Real exchange rates vs. PPP
- Interest rate differentials
- Current account balances
- Political risk

### 4.2 Commodities Trend Following

**Asset Universe:**
- Agricultural: Corn, wheat, soybeans, sugar, cotton
- Energy: Crude oil, natural gas, heating oil
- Metals: Gold, silver, copper, platinum

**Commodity-Specific Considerations:**
- **Contango vs. Backwardation:** Roll yield affects returns
- **Seasonality:** Agricultural patterns, heating/cooling demand
- **Supply shocks:** Weather, geopolitical events
- **Correlation to equities:** Varies (gold = safe haven, oil = risk-on)

**Trend Following Performance (Futures):**
- Strong in trending markets
- Underperforms in range-bound, choppy markets
- Positive skew due to rare large trends

### 4.3 Bond Futures Trend Following

**Instruments:**
- Government bonds: US Treasuries, German Bunds, UK Gilts, Japanese JGBs
- Duration: 2-year to 30-year

**Strategies:**
- Yield curve positioning
- Duration extension/shortening based on trend
- Cross-country relative value

**Correlation to Equities:**
- Normal: Negative correlation (bonds = risk-off)
- Crisis: Positive correlation (liquidation = correlation goes to 1)
- Trend-following provides diversification in normal environments

### 4.4 Correlation of Trend to Other Assets

**Diversification Benefit:**
- Trend-following CTAs show low correlation to traditional assets
- Crisis period correlation increases (all correlations go to 1)
- Bridgewater All Weather: 60% bonds, 30% stocks, 10% commodities

**Correlation Structure:**
```
Traditional Portfolio: 
  Bonds (-) <-> Stocks (+), low correlation when most needed

Trend-Following Portfolio:
  Often negatively correlated to stocks in bear markets
  Positively correlated in strong trends
```

---

## 5. Multi-Timeframe Analysis

### 5.1 Weekly Trend Confirmation of Daily Signals

**Framework:**
1. **Weekly timeframe:** Determine primary trend direction
2. **Daily timeframe:** Identify entry points in direction of weekly trend

**Rules:**
- Only take long signals when weekly trend is bullish
- Only take short signals when weekly trend is bearish
- Daily signals against weekly trend are ignored or used for exits

**Implementation:**
- Weekly MA (e.g., 20-week SMA) for trend direction
- Daily Donchian or MA crossover for entry timing
- Stops placed below/above daily structure

### 5.2 Daily Trend Confirmation of Intraday

**Higher-Order Confirmation:**
- Intraday (e.g., 15-min, 1-hour) signals confirmed by daily trend
- Reduces false breakouts in direction of larger trend

**Timeframe Hierarchy:**
```
Primary: Weekly/Monthly (direction)
Secondary: Daily (entry timing)
Tertiary: Intraday (execution)
```

### 5.3 Multi-Timeframe Momentum

**Combined Signal:**
```
Weekly Return (12M) -> Direction bias
Daily Return (20D) -> Entry signal
Intraday (4H) -> Refinement
```

**Filter Approach:**
- Higher timeframe must confirm before entry
- Conflicting signals = no position or smaller size

---

## 6. Trend Quality Indicators

### 6.1 Supertrend Indicator

**Construction:**
- ATR-based bands above/below price
- Supertrend = Close crosses ATR bands

**Parameters:**
- Period: 10 (default)
- Multiplier: 3 (default for volatility bands)

**Calculation:**
```
Upper Band = (High + Low) / 2 + Multiplier x ATR
Lower Band = (High + Low) / 2 - Multiplier x ATR
Supertrend = 
  If close > upper band -> Bullish
  If close < lower band -> Bearish
```

### 6.2 Ichimoku Cloud

**Components:**
1. **Tenkan-sen (Conversion Line):** 9-period high/low average
2. **Kijun-sen (Base Line):** 26-period high/low average
3. **Senkou Span A:** Average of Tenkan + Kijun, projected 26 periods ahead
4. **Senkou Span B:** 52-period high/low average, projected 26 periods ahead
5. **Chikou Span (Lagging Span):** Current close, plotted 26 periods back
6. **Cloud (Kumo):** Space between Senkou Span A and B

**Signals:**
- **Bullish:** Price above cloud, Tenkan > Kijun
- **Bearish:** Price below cloud, Tenkan < Kijun
- **Cloud Thickness:** Indicates strength of support/resistance

### 6.3 Parabolic SAR (Stop and Reverse)

**Parameters:**
- Step: 0.02 (acceleration factor)
- Maximum: 0.2 (cap on acceleration)

**Calculation:**
```
SAR(t) = SAR(t-1) + AF x (EP - SAR(t-1))
where EP = Extreme Price (highest high for longs, lowest low for shorts)
```

**Interpretation:**
- SAR below price = Bullish trend
- SAR above price = Bearish trend
- SAR crossing price = Signal to reverse

### 6.4 Trend Exhaustion Indicators

**ADX (Average Directional Index):**
- < 20: Weak/absent trend
- 20-25: Emerging trend
- 25-50: Strong trend
- > 50: Extremely strong trend (possible exhaustion)

**Choppiness Index:**
- > 61.8: Choppy, ranging market
- < 38.2: Trending market

**Trend Quality Score:**
```
TQS = (Higher Highs + Higher Lows) / (Total Price Movements)
```
- TQS > 0.5 = Trending
- TQS < 0.5 = Ranging

---

## 7. Dynamic Position Sizing in Trends

### 7.1 Pyramid/Addition Rules

**Turtle-style Pyramiding:**
- Add to winning positions at intervals
- Each addition = same dollar risk as initial position
- Maximum 4-6 units per instrument

**Rules:**
- Entry: Breakout of 20-day high/low
- Addition: Every 0.5N move in favor
- Maximum exposure cap: e.g., 4% of portfolio per instrument

**Risks of Pyramiding:**
- Increased drawdown risk if trend reverses
- Correlation of additions to initial position
- Volatility expansion during drawdowns

### 7.2 Volatility-Adjusted Notional

**Concept:** Scale positions so each instrument contributes equally to portfolio volatility.

**Formula:**
```
Position Size = (Risk Allocation) / (ATR x Multiplier)
```

**Example:**
- Risk allocation per trade: 1% of portfolio
- 20-day ATR: $2,000
- Position = $10,000 / ($2,000 x 2) = 2.5 contracts

**Benefits:**
- Equal risk contribution across instruments
- Automatic reduction in volatile markets
- Natural rebalancing effect

### 7.3 Risk Allocation Changes

**Volatility Targeting:**
- Target portfolio volatility: e.g., 15% annualized
- If realized vol > target: reduce exposure
- If realized vol < target: increase exposure

**Risk Parity Approach:**
- Each asset contributes equal volatility
- Example: 60% bonds, 30% stocks, 10% commodities to equalize risk

**Dynamic Risk Budgeting:**
- Increase risk budget when trend is confirmed
- Reduce in uncertain/volatile environments
- Drawdown-based risk reduction

---

## 8. Regime-Adaptive Trend Following

### 8.1 Trend vs. Counter-Trend Switching

**Regime Detection:**
- High ADX (> 25): Trend-following mode
- Low ADX (< 20): Counter-trend/mean-reversion mode

**Switching Logic:**
```
If ADX > threshold:
    Use trend-following rules (breakouts, MA crossovers)
Else:
    Use counter-trend rules (RSI extremes, Bollinger Band bounces)
```

### 8.2 Adaptive Lookback Windows

**Concept:** Adjust lookback period based on market conditions.

**Methods:**

**Volatility-Based:**
- High volatility -> longer lookback (smoother signals)
- Low volatility -> shorter lookback (faster signals)

**State-Space Models:**
- Hidden Markov Models to detect market regimes
- Different parameters per regime

**Adaptive Donchian:**
```
Lookback = Base x (Current ATR / Historical ATR)
```

### 8.3 Regime Detection Indicators

**Market Regime Features:**
- Volatility level (realized vs. implied)
- Trend strength (ADX)
- Correlation structure
- Liquidity conditions

**Practical Implementation:**
- Rolling 60-day ADX for regime classification
- VIX level for volatility regime
- Credit spreads for risk sentiment

---

## 9. Carry Trade Strategies

### 9.1 Concept and Mechanics

**Definition:** Borrow in low-interest currency, invest in high-interest currency.

**Profit Source:**
- Interest rate differential (carry)
- Exchange rate appreciation of high-yield currency

**Risk:**
- Exchange rate depreciation wiping out carry
- Sudden risk-off moves (carry crash)

### 9.2 Traditional G10 Carry Trade

**High-Yielders (typical):** AUD, NZD, emerging market currencies
**Low-Yielders:** JPY, CHF, EUR (post-ECB policy)

**Example:**
- Borrow JPY at 0% interest
- Invest in AUD at 4% interest
- Gross carry = 4% annually
- Net depends on exchange rate movement

### 9.3 Indian Context Carry Strategies

**INR Carry Trade Considerations:**

**Onshore INR:**
- Limited convertibility (current account restrictions)
- Capital controls limit full carry implementation
- INR Forward Premium reflects interest rate differential

**Offshore INR (INR-I):**
- Non-deliverable forwards (NDF)
- Gained popularity with offshore participation
- Higher volatility, intervention risk

**USD-INR Specifics:**
- Forward premium = Interest rate differential (approx)
- RBI intervention can suppress volatility
- Correlation with global risk appetite

**Potential Strategies:**
1. **USD-INR NDF Short:** If USD-INR forward > expected move
2. **Cross-currency INR position:** USD-INR vs. other EM currencies
3. **INR-correlated assets:** Target multinationals with INR revenues

**Risks Specific to INR:**
- RBI foreign exchange reserves ($600B+) for intervention
- Current account deficit sensitivity
- Crude oil import dependency (INR weakness with oil price rises)

**Historical Context:**
- INR depreciation trend: ~3-5% annually against USD
- Carry available via forward premium when interest rates higher than USD
- Intervention risk during periods of rapid depreciation

---

## 10. Real-World Implementations

### 10.1 Man Group (AHL)

**History:**
- Founded 1983 by Michael Adam and Martin Lueck
- Acquired by Man Group in 1989
- One of largest CTAs globally

**Strategy Overview:**

**AHL Alpha:**
- Quantitative, systematic trend-following
- Predominantly short-term (days to weeks)
- High-frequency data-driven

**AHL Evolution:**
- Traditional momentum-based entry
- ML/AI for signal generation (added later)
- Multi-strategy approach beyond pure trend-following

**Portfolio Construction:**
- Diversified across 100+ markets
- Volatility targeting (~15-20% annualized target)
- Futures-based, no physical commodities

**Key Innovations:**
- Electronic trading infrastructure
- Low-latency execution
- Risk management systems

**Performance Characteristics:**
- Trend-following in trending markets
- Drawdown in choppy, mean-reverting periods
- Managed futures advantage in crisis periods

### 10.2 BlueCrest Capital Management

**History:**
- Founded 2000 by Michael Platt and Rob B. "Bob" Gillespie
- Spin-off from JPMorgan proprietary trading
- One of largest private trading firms

**Strategy Overview:**

**BlueCrest Trend Following:**
- Systematic macro, predominantly trend-following
- Multiple timeframes (short, medium, long)
- Global macro fundamental overlay

**Key Differentiators:**
- Proprietary trading technology
- In-house developed execution systems
- Strong risk management culture

**Capital Allocation:**
- BlueCrest allocates to own strategies (proprietary)
- Outside capital in BlueCrest managed funds
- Funded via family office and institutional investors

**Strategies:**
- Fixed Income trend-following
- Currency trend-following
- Commodity futures
- Equity index futures

**Performance:**
- Historically strong trend-following returns
- 2014: Challenges due to low volatility environment
- Pivot away from external capital after investor redemptions

### 10.3 Millburn & Company

**History:**
- Founded 1971 by Ronald S. Millburn
- One of oldest systematic trading firms
- Pioneers in quantitative trading

**Key Approach:**

**Millburn Trend Following:**
- Multi-market systematic trading
- Long-term trend-following with short-term overlay
- Proprietary models and indicators

**Technology:**
- Early adopter of computer-based trading
- Proprietary simulation and execution platforms
- Continuous research and development

**Investment Universe:**
- 80+ markets globally
- Financial futures, currency, commodities
- Extended over time with new asset classes

**Research Process:**
- Systematic, rules-based approach
- Ongoing refinement of entry/exit rules
- Risk management embedded in models

### 10.4 Comparison Summary

| Aspect | AHL (Man Group) | BlueCrest | Millburn |
|--------|-----------------|-----------|----------|
| Founded | 1983 | 2000 | 1971 |
| Primary Focus | Short-term systematic | Multi-strategy | Long-term trend |
| Timeframe | Days | Multi | Weeks-Months |
| Technology | Very High | High | High |
| AUM (historical peak) | $15B+ | $10B+ | $1B+ |
| Edge Source | Speed, data | Macro, trends | Systematic models |

### 10.5 Key Lessons from Real Implementations

1. **Diversification is critical:** Across markets, timeframes, and strategies
2. **Risk management separates survivors:** Position sizing, drawdown limits
3. **Technology provides edge:** Execution, data processing, latency
4. **Research iteration:** Continuous improvement of models
5. **Operational infrastructure:** Custody, compliance, reporting
6. **Investor education:** Understanding of trend-following characteristics
7. **Capacity constraints:** Strategy capacity limits exist for large funds

---

## References and Further Reading

### Academic Papers
- Moskowitz, T.J., Ooi, Y.H., & Pedersen, L.H. (2012). "Time Series Momentum." *Journal of Financial Economics*
- Jegadeesh, N., & Titman, S. (1993). "Returns to Buying Winners and Selling Losers." *Journal of Finance*
- Hurst, B., Ooi, Y.H., & Pedersen, L.H. (2017). "A Century of Evidence on Trend-Following." *AQR Capital Management*

### Books
- Schwager, J.D. "The New Market Wizards" - Turtle trading interviews
- Dunn, R. "The TurtleTrader" - Turtle system documentation
- Kaufman, P. "Trading Systems and Methods" - Comprehensive reference
- Chan, E. "Quantitative Trading" - Implementation guide

### Additional Topics for Further Research
- Machine learning applications in trend-following
- ESG integration in macro strategies
- Cryptocurrency trend-following
- High-frequency trend extraction
- Factor-based vs. pure momentum approaches
