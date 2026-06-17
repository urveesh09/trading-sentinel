# Statistical Arbitrage & Market-Making Strategies Research

## 1. Statistical Arbitrage Theory

### Core Foundation: Stationarity & Mean-Reversion

Statistical arbitrage (stat arb) exploits persistent mispricings between related financial instruments, relying on the assumption that deviations from equilibrium are temporary and self-correcting.

**Stationarity Requirement**
- A time series is stationary if its mean, variance, and autocorrelation structure are constant over time
- Stat arb only works on stationary (or differenced-stationary) spreads
- Dickey-Fuller (ADF) and KPSS tests verify stationarity
- Spread must revert to a constant mean or long-run equilibrium relationship

**Residual Mean-Reversion**
- Model: `spread_t = mu + rho.spread_{t-1} + epsilon_t` where |rho| < 1 for mean-reversion
- Half-life of deviation: `h = -ln(2)/ln(rho)`
- Speed of mean-reversion (rho) is critical -- too slow means[ziben]本占用 too high
- Cointegration implies a specific linear combination of non-stationary series is stationary

**Factor Models in Stat Arb**
- **CAPM**: `E[R_i] = R_f + beta_i.(E[R_m] - R_f)` -- residuals (alpha) are candidates for stat arb
- **APT**: Multi-factor: `E[R_i] = R_f + Sumbeta_{ij}.F_j` -- mispriced residuals across factors
- Industry-specific factor models (Fama-French 3/5 factor) extract alphas
- Stat arb on residuals after factor exposure removes systematic risk

---

## 2. Pairs Trading: Deep Dive

Pairs trading is the canonical stat arb strategy -- going long one asset and short a correlated asset when their spread widens/narrows.

### 2.1 Distance Method (Z-Score)

**Normalized Price Ratio**
```
ratio_t = P_a,t / P_b,t
z_t = (ratio_t - mu_ratio) / sigma_ratio
```

**Implementation Steps**
1. Select candidate pairs (sector, correlation > 0.7)
2. Compute rolling mean and std of price ratio (lookback: 20-60 min)
3. Entry: z-score > +/-2sigma -> short spread (short A, long B)
4. Exit: z-score reverts to +/-0.5sigma or time-based stop

**Issues with Distance Method**
- Sensitive to lookback window
- Doesn't account for non-stationarity
- Correlation is symmetric; cointegration is directional

### 2.2 Cointegration Methods

**CADF (Cointegrated Augmented Dickey-Fuller)**
Tests whether two non-stationary series have a stable long-run equilibrium.

```
Deltaepsilon_t = alpha + gamma.t + rho.epsilon_{t-1} + Sumdelta_i.Deltaepsilon_{t-i} + u_t
```
- Null: No cointegration (rho = 0)
- Reject H0 at 5% CV -> cointegration exists

**Engle-Granger Two-Step**
1. Regress Y on X: `Y_t = alpha + beta.X_t + epsilon_t`
2. Test residuals epsilon_t for stationarity (ADF test)
3. If stationary: form pairs trade on `epsilon_t`

**Johansen Test**
- Eigenvalue-based test for multiple cointegrating relationships
- Trace statistic and Max-Eigen statistic
- Preferred when >2 assets involved

### 2.3 Kalman Filter Adaptive Pairs Trading

The Kalman filter dynamically estimates the hedge ratio (beta), adapting to regime changes without requiring a fixed lookback window.

**State-Space Model**
```
State equation:  beta_t = beta_{t-1} + η_t          (random walk hedge ratio)
Measurement:     Y_t = alpha_t + beta_t.X_t + epsilon_t    (spread observation)
```

**Kalman Filter Recursions**
```
Prediction:
  beta_t|t-1 = beta_{t-1|t-1}
  P_t|t-1 = P_{t-1|t-1} + Q                    (Q = state noise variance)

Update:
  K_t = P_t|t-1 / (P_t|t-1 + R)               (Kalman gain)
  beta_t|t = beta_t|t-1 + K_t.(Y_t - alpha - beta_t|t-1.X_t)
  P_t|t = (1 - K_t).P_t|t-1                   (R = measurement noise)
```

**Spread & Z-Score with Kalman**
```
spread_t = Y_t - beta_t.X_t
z_t = spread_t / sqrt(P_t|t)                      (normalized by filter uncertainty)
```

**Advantages over Fixed Window**
- Adapts to drifting hedge ratios (option expiry, index rebalancing)
- Shorper effective lookback in stable regimes
- Produces natural entry/exit via uncertainty bands

**Kalman Filter Code Structure**
```python
# Pseudocode
beta = 0.0          # initial hedge ratio
P = 1.0             # initial state covariance
Q = 0.001           # process noise (hedge ratio drift)
R = 0.01            # measurement noise

for t in data:
    # Predict
    beta_pred = beta
    P_pred = P + Q
    
    # Update
    residual = Y[t] - beta_pred * X[t]
    K = P_pred / (P_pred + R)
    beta = beta_pred + K * residual
    P = (1 - K) * P_pred
    
    spread = residual
    z = residual / sqrt(P)
```

---

## 3. Index Arbitrage

Index arbitrage exploits mispricings between an index (or index ETF) and its constituent stocks or derivatives.

### 3.1 ETF vs. Nifty Basket Basis Trade

**The Arbitrage Relationship**
```
Fair ETF value = Sum(w_i . P_i)        (weighted sum of constituents)
Basis = ETF_price - Fair_value

If basis > transaction_costs -> buy basket, short ETF
If basis < -transaction_costs -> buy ETF, short basket
```

**Execution Mechanics**
- ETFs trade on exchange; basket constituents also trade
- Creation/redemption mechanism keeps ETF close to NAV
- Institutional traders arbitrage via program trading

### 3.2 Nifty Futures Basis Trade

**Futures Pricing Relationship**
```
F_t,T = S_t . e^(r-q)(T-t)           (cost-of-carry model)
Basis = F_t,T - S_t

If F > S.e^(r-q)(T-t) -> futures overpriced -> short futures, long spot
If F < S.e^(r-q)(T-t) -> futures underpriced -> long futures, short spot
```

**Arbitrage Trigger Thresholds**
```
Trigger_buy = S_t . e^(r-q)(T-t) + tc   (futures expensive)
Trigger_sell = S_t . e^(r-q)(T-t) - tc  (futures cheap)

Practical triggers add buffer for:
  - Bid-ask spread on both legs
  - Margin calls risk (daily settlement)
  - Execution risk on large orders
  - Overnight carry cost uncertainty
```

**Nifty Basis Dynamics**
- Basis typically narrows toward expiration
- Roll cost (when shifting from front to next month)
- Dividend expectations affect futures pricing
- Corporate action adjustments (index weight changes)

### 3.3 ETF Creation/Redemption Arbitrage

**Creation Process**
1. AP (Authorized Participant) buys underlying stocks
2. Submits creation order to ETF issuer
3. Receives ETF shares (in large blocks called "creation units")
4. Redeem: reverse process -> ETF share -> underlying stocks

**Arbitrage Band**
```
ETF_price > NAV + costs -> AP creates new ETF shares (buys stocks, sells ETF)
ETF_price < NAV - costs -> AP redeems ETF shares (buys ETF, sells stocks)

This keeps ETF market price close to NAV throughout trading day.
```

---

## 4. Market Making

Market makers (MM) provide liquidity by simultaneously quoting bid and ask prices, earning the spread while managing inventory risk.

### 4.1 Bid-Ask Spread Optimization

**Spread Components**
```
Total Spread = 2.s
s = s_orderflow + s_inventory + s_adverse_selection + s_operation

Microstructure sources:
  - Order processing cost (exchange fees, clearing)
  - Inventory holding cost (capital cost of positions)
  - Adverse selection cost (informed traders)
  - Uncertainty/volatility component
```

**Garman (1976) Model**
For a MM quoting in a pure orderflow-driven market:
```
Optimal spread = 2.sigma . sqrt(lambda.C / mu)
sigma = asset volatility
lambda = order arrival rate (Poisson)
C = cost per trade
mu = expected profit per trade
```

**Stoll (1978) Decomposition**
- Spread = 50% inventory + 40% adverse selection + 10% order processing
- More liquid assets: adverse selection dominates
- Less liquid assets: inventory cost dominates

### 4.2 Avellaneda-Stoikov Market Making Model

The canonical quantitative MM model by Marco Avellaneda & Sasha Stoikov (2008).

**Setup**
- MM quotes bid/ask around mid-price `m_t`
- Inventory held: `q_t` units (can be long or short)
- Reservation price `r_t`: price at which MM is indifferent to trading

**Reservation Price**
```
r_t = s_t - q_t.gamma.sigma^2.(T-t)

s_t = mid-price
gamma = inventory risk aversion parameter
sigma = volatility
T = expiry / liquidation horizon
(T-t) = time remaining
```

As `q_t` increases (more long inventory), `r_t` decreases -> MM lowers bid to buy less / encourage selling.

**Optimal Bid-Ask Quotes**
```
Bid: p_b = r_t - delta.sigma.sqrt(T-t)
Ask: p_a = r_t + delta.sigma.sqrt(T-t)

delta = constant capturing spread parameter (often delta ~= 0.3-0.6)
```

**Spread Widens Over Time**: As (T-t) decreases, the spread widens (sigma.sqrt(T-t) shrinks, but the whole term becomes more dominated by delta).

**Maximizing Expected Utility**
MM maximizes `E[U(W_T)]` where `W_T` is terminal wealth with CRRA utility:
```
max E[U(W_T)] subject to inventory dynamics
U(W) = W^(1-gamma_u) / (1-gamma_u), gamma_u = risk aversion
```

**Practical Adjustments**
- Add sensitivity to order flow imbalance (OFI)
- Tweak gamma based on current inventory levels
- Cap maximum inventory `|q_t| < Q_max`
- Add jump risk for sudden price moves

### 4.3 Order Book Imbalance (OBI) Signals

**OBI Definition**
```
OBI = (bid_vol - ask_vol) / (bid_vol + ask_vol)
OBI ∈ [-1, +1]

+1 = all volume on bid side (buying pressure)
-1 = all volume on ask side (selling pressure)
```

**OBI as a Signal**
- Positive OBI -> price likely to rise -> MM can skew quotes (wider ask, tighter bid)
- Negative OBI -> price likely to fall -> MM skews opposite
- OBI reverts faster than price, giving predictive signal

**Multi-Level OBI**
```
OBI_weighted = Sum(v_i.w_i) / Sum|v_i|
v_i = volume at level i (positive for bid, negative for ask)
w_i = weight (higher weight for closer levels)
```

### 4.4 Adverse Selection Mitigation

**Information Asymmetry Problem**
Informed traders (who know true value) hit the "wrong" side of MM quotes, causing losses.

**Mitigation Techniques**

1. **Quote Skewing**: Adjust quotes based on OFI or flow toxicity
   ```
   p_b = r_t - delta.sigma.sqrt(T-t).(1 - alpha.OBI)
   p_a = r_t + delta.sigma.sqrt(T-t).(1 + alpha.OBI)
   alpha = adverse selection sensitivity
   ```

2. **Flow Toxicity Detection**: Track order flow in short windows
   - If order flow is serially correlated, adverse selection risk is high
   - Win rate on each side provides real-time toxicity estimate

3. **Inventory Management**: Reduce size / widen spread when inventory is against you

4. **Speed Advantage**: Fast cancellation ability (pinging exchanges) crucial to avoid being "picked off" by informed traders

5. **Order Classification**: Distinguish retail (noise) vs institutional (informed) flow using:
   - Order size patterns
   - Time-of-day patterns
   - Fill rates

---

## 5. High-Frequency Strategies

### 5.1 Latency Arbitrage

**Mechanism**
Exploiting price discrepancies between exchanges or venues that arise from propagation delays.

**Requirements**
- Co-location (server physically near exchange matching engines)
- Ultra-low latency connections (<1 microsecond)
- Smart order routing ( SOR) across fragmented markets

**Types**
- **Direct Latency Arb**: Arbing price diffs between exchanges (e.g., NYSE vs NASDAQ)
- **Dark Pool Arb**: Price diffs between lit and dark venues
- **Index Arb on Futures**: Microsecond-level delays in index vs futures pricing

**Competition Dynamics**
- >90% of latency arbitrage capacity held by top 3 HFT firms
- Competition drives latency to physical limits (speed of light)
- Arms race: microwave towers, fiber optics, FPGA servers

### 5.2 Order Book Dynamics & LOB Modeling

**Limit Order Book (LOB) Structure**
```
Bid side (price descending):    Ask side (price ascending):
Level 1: B1, Vb1                Level 1: A1, Va1
Level 2: B2, Vb2                Level 2: A2, Va2
...
```

**LOB Dynamics**
- New limit orders add liquidity
- Market orders remove liquidity
- Cancellations return liquidity
- Each action provides information about trader intentions

**Queue Position (Time Priority)**
- First to post at a price level has priority when that level is touched
- Getting to front of queue matters for fill probability
- "Iceberg" orders hide true size

**Predictive Signals from LOB**
- **Order Flow Imbalance**: Predictive of next price move at high frequency
- **Queue Depletion**: When bid queue is almost exhausted -> price likely to drop
- **Resilience**: How fast liquidity returns after large market order

### 5.3 High-Frequency Market Making

**HFT MM vs Traditional MM**
- Much shorter holding periods (seconds to milliseconds)
- Inventory risk minimal due to cancellation speed
- Relies on spread capturing vs directional moves
- Adverse selection is primary risk

**HFT MM Profit Model**
```
P = Sum(ξ_i . s_i) - C_market - C_adverse

ξ_i = indicator if trade occurs at i (1 = hit ask, 0 = no fill)
s_i = half-spread at time of fill
C_market = market impact cost
C_adverse = adverse selection loss (informed trader hitting you)
```

---

## 6. Volatility Arbitrage

### 6.1 Implied vs Realized Volatility

**Implied Volatility (IV)**
- Derived from option prices via Black-Scholes inversion
- Market's expectation of future realized volatility
- Different strikes give different IV -> volatility smile/skew

**Realized Volatility (RV)**
```
RV = sqrt(Sum ln(r_i)^2) . sqrt(252)     (r_i = log returns, 1-min bars)
   = OLS estimator of daily vol

Alternative: Parkinson, Garman-Klass, Rogers-Satchell estimators
```

**Variance Premium**
```
VP = IV^2 - RV^2

Typical: IV > RV by 2-5 vol points (equity indices)
This premium is compensation for:
  - Jump risk
  - Model misspecification
  - Leverage constraints
```

### 6.2 Vol Surface Dynamics

**Volatility Smile**
- OTM puts (high delta < 0.5) trade at higher IV than ATM
- Creates smile shape when plotting IV vs strike
- Reflects skewness preference / demand for downside protection

**Term Structure**
- Front-month IV often differs from back-month
- Contango (IV higher further out) typical in calm markets
- Backwardation during crises

**Vol Arbitrage Strategies**

1. **Short Vol / Long Vol Dispersion**
   - Short index volatility, long single-stock volatility
   - Index vol < weighted avg of single-stock vols (due to correlation)
   - Profitable unless correlation spikes

2. **Variance Swap Replication**
   - Long realized vol = delta-hedge a straddle/strangle
   - P&L roughly = realized vol - implied vol

3. **Skew Trading**
   - Buy OTM puts (short skew) when skew is "too high"
   - Bet skew will flatten toward model value

### 6.3 VIX & Volatility Products

- VIX calculated from SPX option strip (weighted blend of OTM puts/calls)
- VIX futures allow direct vol exposure
- VIX ETFs (VXX) track VIX futures via rolling
- Contango in VIX futures erodes long positions

---

## 7. Risk Management

### 7.1 Correlation Breakdown

**Problem**
Pairs trading assumes correlation holds. During stress events:
- Correlations often go to 1 (everything sells off together)
- Historical lookback windows include benign periods only
- Kalman filter adapts slowly in fast regime changes

**Mitigation**
- Dynamic pair selection (rolling correlation windows)
- Stress testing: check performance in 2008, 2020-type scenarios
- Stop-loss triggers based on spread deviation exceeding 3sigma
- Diversify across uncorrelated pairs

### 7.2 Drawdown Controls

**Drawdown Definition**
```
DD_t = (Peak_t - NAV_t) / Peak_t
Max Drawdown = max(DD_t) over backtest period
```

**Controls**
- **Position Sizing**: Kelly criterion or fractional Kelly (e.g., Kelly/4)
  ```
  f* = (bp - q) / b    (Kelly fraction)
  b = net odds, p = win prob, q = 1-p
  
  For pairs: f* = mean_PnL / variance_PnL   (simplified)
  ```
- **Drawdown Halts**: Stop trading if drawdown > threshold (e.g., 5%)
- **Maximum Drawdown Recovery Rule**: Reduce size while recovering

### 7.3 Capacity Constraints

**Constraints by Strategy**
| Strategy | Capacity | Notes |
|----------|----------|-------|
| Pairs Trading | $50M-$500M | Depends on liquidity of pair |
| Index Arb | $1B+ | Large capital, small edge |
| Market Making | $100M-$2B | Bid-ask spread widens with size |
| HFT | $10M-$100M | Speed advantage degrades with size |

**Capacity Scaling**
- More liquid pairs = higher capacity
- Higher frequency = lower capacity (more competition, smaller edges)
- Spread must widen to absorb larger orders (market impact)

---

## 8. Real Implementations & Performance Metrics

### 8.1 Pairs Trading Performance

**Classic Performance Benchmarks**
- Annual return: 5-15% (retail / small fund)
- Sharpe ratio: 0.5-1.5 (before costs)
- Max drawdown: 5-15% in normal conditions

**Key Metrics**
```
Spread Hit Rate: % of pairs where spread mean-reverts
Avg Holding Period: typically 1 day to 1 week
Turnover: high (daily rebalancing of pairs)
Slippage: typically 1-5 bps for liquid pairs
```

**Slippage Impact Example**
- Assume 10 bps avg edge per trade, 5 bps slippage (50% erosion)
- 100 bps avg edge (liquid index arb) with 1 bp slippage (1% erosion)

### 8.2 Market Making Performance

**Industry Spreads**
- US Equity ETFs: 1-3 bps (retail), <0.5 bps (institutional)
- FX majors (EUR/USD): 0.1-0.3 pips (0.001-0.003%)
- Options: depends heavily on IV rank and product

**MM Profitability Metrics**
```
Turnover of inventory per day
Avg inventory days held
Spread capture rate: % of quoted spread actually earned
Cancel rate: % of orders cancelled before fill (HFT: 95%+)
```

**MM P&L Decomposition**
```
Total P&L = Spread earned + Inventory gains/losses + Adverse selection losses
Spread earned ~= 80% of gross in liquid markets
Adverse selection ~= 15-20% drag
```

### 8.3 Risk Metrics Summary

**Strategy Risk Measures**
- **VaR (95%)**: 1-day loss at 95% confidence
- **CVaR/ES**: Expected shortfall beyond VaR
- **Beta exposure**: Systematic risk not hedged
- **Concentration risk**: Overweight in any single pair/asset

**Operational Risk**
- Technology failures
- Feed latency / data quality
- Execution errors (wrong quantity, wrong side)
- Counterparty / settlement risk

---

## 9. Implementation Framework Summary

### Pairs Trading Pipeline
```
1. Pair Selection
   - Universe screening (sector, market cap similarity)
   - Correlation filtering (|corr| > 0.7)
   - Cointegration testing (Engle-Granger or Johansen)

2. Signal Generation
   - Compute spread = Y - beta.X (Kalman or rolling OLS)
   - z-score = (spread - rolling_mean) / rolling_std
   - Entry: |z| > 2.0; Exit: |z| < 0.5

3. Risk Management
   - Max positions: 10-20 pairs simultaneously
   - Position sizing: equal weight or Kelly-based
   - Stop-loss: |z| > 3.0 triggers close
   - Drawdown halt: stop new entries if DD > 5%

4. Execution
   - Algo execution to minimize market impact
   - Partial fills handled
   - Transaction cost estimation before entry
```

### Market Making Pipeline
```
1. Quote Generation
   - Compute reservation price r_t via Avellaneda-Stoikov
   - Quote bid/ask around r_t with spread parameter delta

2. Inventory Management
   - Track real-time inventory q_t
   - Adjust quotes: skew bid/ask based on q_t and OFI
   - Max inventory cap per asset

3. Adverse Selection Monitoring
   - Win rate tracking per side
   - If fill rate asymmetry -> recalibrate quote widths
   - Cancel passive orders if toxic flow detected

4. Execution & Cancellation
   - Cancel stale quotes (>X seconds old)
   - Replace with new quotes reflecting updated state
   - Jitter: randomize quote prices slightly to avoid pattern detection
```

---

## Appendix: Key Papers & References

| Topic | Key Reference |
|-------|---------------|
| Pairs Trading | Gatev et al. (2006) -- "Pairs Trading: Performance of a Relative Value Arbitrage Rule" |
| Cointegration | Engle & Granger (1987) -- "Cointegration and Error Correction" |
| Kalman Filter Pairs | Elliot et al. (2008) -- "Pairs Trading with Cointegration" |
| Market Making | Avellaneda & Stoikov (2008) -- "High-Frequency Trading in a Limit Order Book" |
| Market Making Theory | Garman (1976) -- "Market Microstructure" |
| Volatility Arbitrage | Bondarenko (2003) -- "Statistical Arbitrage and Market Efficiency" |
| Index Arbitrage | Burgess (1999) -- "Index Arbitrage and the futures market" |
| HFT LOB | Cont et al. (2010) -- "Stochastic Models of Order Book Dynamics" |

---

*Research compiled for algorithmic trading strategy development. All strategies require backtesting and risk validation before live deployment. Past performance metrics are illustrative; actual results depend on execution quality, market conditions, and operational factors.*