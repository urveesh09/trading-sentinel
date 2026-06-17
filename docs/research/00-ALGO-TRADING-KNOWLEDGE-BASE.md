# Algorithmic Trading Knowledge Base
> Compiled: 2026-05-18 | Total: ~30,240 words across 7 deep-research documents

## Quick Navigation

- [**Phase 1: Momentum / Breakout Strategies**](#momentum) -- 5.6K words
- [**Phase 2: Volume & Price Action**](#volume) -- 4.1K words
- [**Phase 3: Mean Reversion Strategies**](#mean_reversion) -- 5.1K words
- [**Phase 4: Trend-Following & Macro**](#trend_macro) -- 3.0K words
- [**Phase 5: Statistical Arbitrage & Market-Making**](#stat_arb) -- 3.1K words
- [**Phase 6: NSE India Market Structure**](#nse_india) -- 5.1K words
- [**Phase 7: Risk Management & Portfolio Overlay**](#risk) -- 4.3K words

---

## Phase 1: Momentum / Breakout Strategies <a name='momentum'></a>

**File:** `projects/trading-research/momentum-research.md`
**Word count:** 5,608 words

**Key sections:**
- NSE Swing Trading -- Deep Reference Document
- Table of Contents
- 1. Indicator Variations
- #1.1 MACD Variants
- #1.2 Bollinger Band Breakouts
- #1.3 Donchian / Keltner Channel Breakouts
- #1.4 ATR-Based Momentum Indicators
- 2. Academic Momentum Factor Research
- #2.1 Carhart 4-Factor Model (1997)
- #2.2 Fama-French 3-Factor Model (1993)
- #2.3 Asymmetric Momentum -- Novus Research (2019)
- #2.4 Time-Series Momentum (Moskowitz, Ooi, Pedersen, 2012)

---

## Phase 2: Volume & Price Action <a name='volume'></a>

**File:** `projects/trading-research/volume-research.md`
**Word count:** 4,077 words

**Key sections:**
- Table of Contents
- 1. Volume Surge Detection Algorithms
- #1.1 Absolute Volume Surge
- #1.2 Relative Volume (RVI) Surge
- #1.3 Volume Spike Detection with VWAP Confirmation
- #1.4 Implementation Notes
- 2. Volume Profile Analysis
- #2.1 Core Concept
- #2.2 Volume Profile Algorithm
- #2.3 VWAP (Volume-Weighted Average Price)
- #2.4 VWAP Usage in Trading
- 3. Money Flow Indicators

---

## Phase 3: Mean Reversion Strategies <a name='mean_reversion'></a>

**File:** `projects/trading-research/mean-reversion-research.md`
**Word count:** 5,091 words

**Key sections:**
- Table of Contents
- 1. Core Theory: Mean Reversion Fundamentals
- #1.1 The Ornstein-Uhlenbeck (OU) Process
- #1.2 Half-Life of Mean Reversion
- #1.3 ADF Stationarity Test
- #1.4 Mean Reversion vs Momentum Thresholds
- 2. Bollinger Bands Mean Reversion
- #2.1 Core Concept
- #2.2 Key Metrics
- #2.3 Bandwidth as Regime Indicator
- #2.4 Entry/Exit Rules
- #2.5 Bollinger + RSI Overlay Strategy

---

## Phase 4: Trend-Following & Macro <a name='trend_macro'></a>

**File:** `projects/trading-research/trend-macro-research.md`
**Word count:** 3,012 words

**Key sections:**
- 1. Trend-Following Foundations
- #1.1 Donchian Channel
- #1.2 Turtle Trading Rules
- #1.3 Moving Average Crossover Systems
- 2. Time-Series Momentum (TSMOM)
- #2.1 Moskowitz (2012) Paper: "Time Series Momentum"
- #2.2 Volatility Scaling
- #2.3 Rebalancing Frequency
- #2.4 Extensions and Variations
- 3. Cross-Sectional Momentum
- #3.1 Relative Strength Ranking
- #3.2 Top-N Basket Approach

---

## Phase 5: Statistical Arbitrage & Market-Making <a name='stat_arb'></a>

**File:** `projects/trading-research/stat-arb-research.md`
**Word count:** 3,082 words

**Key sections:**
- 1. Statistical Arbitrage Theory
- #Core Foundation: Stationarity & Mean-Reversion
- 2. Pairs Trading: Deep Dive
- #2.1 Distance Method (Z-Score)
- #2.2 Cointegration Methods
- #2.3 Kalman Filter Adaptive Pairs Trading
- 3. Index Arbitrage
- #3.1 ETF vs. Nifty Basket Basis Trade
- #3.2 Nifty Futures Basis Trade
- #3.3 ETF Creation/Redemption Arbitrage
- 4. Market Making
- #4.1 Bid-Ask Spread Optimization

---

## Phase 6: NSE India Market Structure <a name='nse_india'></a>

**File:** `projects/trading-research/nse-india-research.md`
**Word count:** 5,102 words

**Key sections:**
- Table of Contents
- 1. Market Structure
- #1.1 T+1 Settlement
- #1.2 Pre-Open Session (09:00-09:15 IST)
- #1.3 Intraday Auction Session (14:00-14:45 IST)
- #1.4 Closing Session (15:30-15:40 IST)
- #1.5 Block Deals
- #1.6 Post-Broadcast Session (15:40-17:00 IST)
- 2. Liquidity Patterns
- #2.1 Average Daily Volume by Market Cap Tier
- #2.2 Impact Cost Data
- #2.3 Liquidity Tiers for Strategy Assignment

---

## Phase 7: Risk Management & Portfolio Overlay <a name='risk'></a>

**File:** `projects/trading-research/risk-research.md`
**Word count:** 4,268 words

**Key sections:**
- 1. Position Sizing Frameworks
- #1.1 Fixed Amount
- #1.2 Fixed Fraction
- #1.3 Kelly Criterion
- #1.4 Volatility-Targeting
- #1.5 Risk-Parity Approach
- 2. Portfolio-Level Risk Controls
- #2.1 Correlation in Drawdowns
- #2.2 Sector Concentration Limits
- #2.3 Maximum Loss Per Strategy/Period
- 3. Circuit Breakers (CB1-CB5)
- #CB1: Daily Loss Halt

---

