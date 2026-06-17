# Risk Management and Portfolio Overlay Frameworks for Algorithmic Trading

## 1. Position Sizing Frameworks

Position sizing determines how much capital to allocate to each trade. It is the primary lever for controlling risk and drawdowns.

### 1.1 Fixed Amount
Allocate a constant dollar amount per trade (e.g., $10,000 per position regardless of account size).

- **Pros:** Simple, predictable risk in absolute terms
- **Cons:** Does not adapt to account growth or volatility changes
- **Best for:** Beginner strategies, stable accounts

### 1.2 Fixed Fraction
Allocate a fixed percentage of current account equity per trade (e.g., 2% of portfolio value).

```python
position_size = account_value * fraction_rate
num_shares = position_size / share_price
```

- **Pros:** Scales with account growth; reduces risk as account shrinks
- **Cons:** Can be aggressive in large accounts; ignores asset volatility differences

### 1.3 Kelly Criterion

The Kelly criterion maximizes expected log wealth. Given win rate `p` and win/loss ratio `R`:

```
f* = (bp - q) / b
where:
  b = gross odds (reward/risk ratio)
  p = probability of win
  q = probability of loss = 1 - p
```

**Full Kelly:** Uses 100% of the calculated fraction. Aggressive; high variance.

**Fractional Kelly:** Use 25-50% of Kelly to reduce volatility while retaining edge.

```python
import numpy as np

def kelly_fraction(win_rate, win_loss_ratio):
    """Calculate full Kelly fraction for a strategy."""
    b = win_loss_ratio
    p = win_rate
    q = 1 - p
    kelly = (b * p - q) / b
    return max(0, kelly)

def fractional_kelly(win_rate, win_loss_ratio, fraction=0.5):
    """Fractional Kelly (commonly 25-50% of full Kelly)."""
    return kelly_fraction(win_rate, win_loss_ratio) * fraction

# Example: 55% win rate, 1.5:1 reward/risk
p, b = 0.55, 1.5
full_kelly = kelly_fraction(p, b)       # ~23.3%
half_kelly = fractional_kelly(p, b, 0.5) # ~11.7%
quarter_kelly = fractional_kelly(p, b, 0.25)  # ~5.8%
```

**Practical considerations:**
- Kelly assumes i.i.d. outcomes -- autocorrelated strategies violate this
- Real-world trading costs and slippage erode Kelly-advantaged strategies
- Use geometric mean optimization rather than arithmetic for multi-period growth

### 1.4 Volatility-Targeting

Volatility-targeting scales positions to achieve a target level of portfolio volatility, typically expressed as annualized standard deviation of returns.

```
Position Size = (Risk Capital x Target Vol%) / (Asset Volatility x sqrt252)

where:
  Risk Capital = total capital allocated to this strategy
  Target Vol% = annualized volatility target (e.g., 15%)
  Asset Volatility = realized or implied volatility of the asset
  sqrt252 = square root of trading days to annualize
```

**Example:**
- Account: $1,000,000
- Target vol: 15% annualized
- 20-day realized vol of strategy: 25% annualized
- Risk capital fraction: 10% ($100,000)

```
Notional = ($100,000 x 15%) / 25% = $60,000
```

**Key insights:**
- High-volatility environments -> smaller positions
- Low-volatility environments -> larger positions
- This mechanically reduces exposure during market stress (volatility spikes)
- Used by virtually all professional quantitative funds (Renaissance, Two Sigma, Bridgewater)

### 1.5 Risk-Parity Approach

Risk-parity (or risk-equity) allocates capital such that each asset contributes equally to total portfolio risk. Unlike equal-weighting, it accounts for differing volatilities and correlations.

```
Risk Contribution of Asset i = w_i x (Sum_j w_j x Cov(i,j)) / sigma_portfolio

Set all risk contributions equal:
w_i x dsigma_portfolio/dw_i = w_j x dsigma_portfolio/dw_j  for all i, j
```

**Simplified implementation:**
```python
def risk_parity_weights(volatility_series_dict, correlation_matrix=None):
    """
    Calculate risk-parity weights given volatilities and optional correlation matrix.
    volatility_series_dict: dict of {asset: annual_volatility}
    """
    vols = np.array(list(volatility_series_dict.values()))
    
    if correlation_matrix is None:
        # Assume zero correlation (inverse volatility weighting)
        weights = 1 / vols
    else:
        # Iterative risk-parity algorithm
        cov_matrix = np.outer(vols, vols) * correlation_matrix
        n = len(vols)
        weights = np.ones(n) / n
        
        for _ in range(100):  # iterative refinement
            portfolio_vol = np.sqrt(weights @ cov_matrix @ weights)
            marginal_contrib = cov_matrix @ weights
            risk_contrib = weights * marginal_contrib / portfolio_vol
            target_rc = portfolio_vol / n
            weights *= (target_rc / risk_contrib)
            weights /= weights.sum()
    
    return weights / weights.sum()

# Example: 3 assets with different vol profiles
vols = {
    'equities': 0.16,    # 16% annualized vol
    'bonds': 0.05,       # 5% annualized vol
    'commodities': 0.22  # 22% annualized vol
}
weights = risk_parity_weights(vols)
# Equities: ~36%, Bonds: ~72%, Commodities: ~26% (inverse vol weighting)
```

**Bridgewater All Weather reference:**
- 55% bonds, 30% stocks, 7.5% gold, 7.5% commodities (long-term, pre-2020)
- Goal: stable returns across economic regimes (growth up/down, inflation up/down)

---

## 2. Portfolio-Level Risk Controls

### 2.1 Correlation in Drawdowns

During market stress, correlations between assets tend to spike toward 1.0. This undermines diversification and can cause simultaneous drawdowns across the portfolio.

**Risk controls:**
- Monitor rolling correlation matrices (30-day, 60-day)
- Stress-test portfolio under correlation假设 (all correlations -> 1.0)
- Use Copula models for tail dependence
- Set maximum allowable portfolio correlation to safe-haven assets

```python
def correlation_risk_monitor(returns_df, window=30, corr_threshold=0.75):
    """Alert when rolling correlation exceeds threshold."""
    rolling_corr = returns_df.rolling(window).corr()
    
    # Find max correlation in off-diagonal elements
    n = returns_df.shape[1]
    corr_values = []
    for i in range(n):
        for j in range(i+1, n):
            corr_values.append(rolling_corr.iloc[:, i, j])
    
    return {
        'max_correlation': max(corr_values),
        'average_correlation': np.mean(corr_values),
        'breaches': [c for c in corr_values if c > corr_threshold]
    }
```

### 2.2 Sector Concentration Limits

Prevent over-exposure to a single sector/industry:

```python
SECTOR_LIMITS = {
    'Technology': 0.25,      # Max 25% in tech
    'Financials': 0.20,
    'Healthcare': 0.20,
    'Consumer': 0.15,
    'Energy': 0.10,
    'Industrials': 0.15,
    'Materials': 0.08,
    'Utilities': 0.08,
    'Real Estate': 0.08,
}

def check_sector_concentration(positions, sector_map, total_equity):
    """Check if any sector exceeds defined limits."""
    sector_exposure = {}
    for ticker, shares in positions.items():
        sector = sector_map.get(ticker, 'Other')
        sector_exposure[sector] = sector_exposure.get(sector, 0) + shares * get_price(ticker)
    
    violations = []
    for sector, exposure in sector_exposure.items():
        weight = exposure / total_equity
        limit = SECTOR_LIMITS.get(sector, 0.10)
        if weight > limit:
            violations.append(f"{sector}: {weight:.1%} (limit: {limit:.1%})")
    
    return violations
```

### 2.3 Maximum Loss Per Strategy/Period

Set hard limits on acceptable losses:

```python
MAX_LOSS_LIMITS = {
    'intraday': 0.015,    # 1.5% max intraday loss
    'daily': 0.025,       # 2.5% max daily loss
    'weekly': 0.05,        # 5% max weekly loss
    'monthly': 0.10,      # 10% max monthly loss
}

def check_loss_limits(current_pnl, running_max, limit_type):
    """Check if PnL has exceeded loss limit for time period."""
    drawdown = running_max - current_pnl
    limit = MAX_LOSS_LIMITS[limit_type]
    
    if drawdown > limit:
        return False, f"Loss limit breached: {drawdown:.2%} vs {limit:.2%}"
    return True, "Within limits"
```

---

## 3. Circuit Breakers (CB1-CB5)

Circuit breakers halt trading when predefined risk thresholds are breached. They are the last line of defense against runaway losses.

### CB1: Daily Loss Halt
**Trigger:** Daily realized PnL drops below `-2%` of portfolio value.

```python
CB1_HALT_THRESHOLD = -0.02  # -2%

def cb1_daily_loss_halt(current_day_pnl, portfolio_value, trading_enabled):
    """
    CB1: Halt all new position entries if daily loss exceeds threshold.
    Resumes next trading day automatically.
    """
    daily_loss_pct = current_day_pnl / portfolio_value
    
    if daily_loss_pct < CB1_HALT_THRESHOLD and trading_enabled:
        logger.warning(f"CB1 TRIGGERED: Daily loss {daily_loss_pct:.2%} exceeds {CB1_HALT_THRESHOLD:.2%}")
        return False  # trading halted
    return True
```

### CB2: Consecutive Loss Halt
**Trigger:** `N` consecutive losing trading days (e.g., 3 losses in a row).

```python
CB2_CONSECUTIVE_LOSS_LIMIT = 3

def cb2_consecutive_loss_halt(consecutive_losses, trading_enabled):
    """
    CB2: Halt if N consecutive losses detected.
    Prevents averaging down into extended drawdowns.
    """
    if consecutive_losses >= CB2_CONSECUTIVE_LOSS_LIMIT and trading_enabled:
        logger.warning(f"CB2 TRIGGERED: {consecutive_losses} consecutive losses")
        return False
    return True
```

### CB3: Drawdown Halt
**Trigger:** Peak-to-trough drawdown exceeds `X%` (e.g., 10% from high-water mark).

```python
CB3_DRAWDOWN_THRESHOLD = -0.10  # -10%

def cb3_drawdown_halt(current_value, high_water_mark, trading_enabled):
    """
    CB3: Halt trading if drawdown from HWM exceeds threshold.
    Mandatory cool-off period before resuming.
    """
    drawdown = (current_value - high_water_mark) / high_water_mark
    
    if drawdown < CB3_DRAWDOWN_THRESHOLD and trading_enabled:
        logger.critical(f"CB3 TRIGGERED: Drawdown {drawdown:.2%} exceeds {CB3_DRAWDOWN_THRESHOLD:.2%}")
        # Require manual review before resuming
        send_alert("CB3 Drawdown Halt - Manual intervention required")
        return False
    return True
```

### CB4: Backtest Gate
**Trigger:** Strategy live performance deviates significantly from backtest expectations.

```python
CB4_MAX_BETA_TO_BACKTEST = 0.60  # Live Sharpe must be > 60% of backtest Sharpe
CB4_P_VALUE_THRESHOLD = 0.05    # Statistical similarity threshold

def cb4_backtest_gate(strategy_id, live_metrics, backtest_metrics):
    """
    CB4: Gate that disables strategy if live performance diverges from backtest.
    Implemented per Q2 in GEMINI framework (Bridgewater's risk system).
    """
    sharpe_ratio = live_metrics['sharpe']
    backtest_sharpe = backtest_metrics['sharpe']
    
    beta = sharpe_ratio / backtest_sharpe if backtest_sharpe > 0 else 0
    
    if beta < CB4_MAX_BETA_TO_BACKTEST:
        logger.critical(f"CB4 TRIGGERED: Live/Backtest Sharpe beta {beta:.2f} < {CB4_MAX_BETA_TO_BACKTEST}")
        return False
    return True
```

### CB5: Bankroll Floor
**Trigger:** Equity drops below `Y%` of starting capital (e.g., 50%).

```python
CB5_BANKROLL_FLOOR = 0.50  # 50% of starting capital

def cb5_bankroll_floor(current_equity, starting_equity, trading_enabled):
    """
    CB5: Absolute floor - stop trading if equity falls below floor.
    Typically mandates strategy review or wind-down.
    """
    floor_ratio = current_equity / starting_equity
    
    if floor_ratio < CB5_BANKROLL_FLOOR and trading_enabled:
        logger.critical(f"CB5 TRIGGERED: Bankroll {floor_ratio:.2%} below floor {CB5_BANKROLL_FLOOR:.2%}")
        logger.critical("MANDATORY: Strategy wind-down initiated")
        return False
    return True
```

### Circuit Breaker Design Patterns

1. **Stacking:** Multiple CBs can fire simultaneously. CB1 (daily loss) is checked most frequently (every bar). CB5 (bankroll floor) is checked least frequently (end of day).

2. **Cooldown periods:** After a halt, require `N` bars/sessions before resuming:
   ```python
   CB_HALT_COOLDOWN_BARS = 5
   ```

3. **Escalation:** If CB3 fires 3 times in 30 days -> escalate to full strategy review:
   ```python
   CB3_ESCALATION_THRESHOLD = 3  # fires per month
   ```

4. **Logging and post-mortem:** Every CB trigger requires documented review before re-enabling.

---

## 4. Trailing Stops

Trailing stops lock in profits while allowing upside to continue. They move only in the direction favorable to the position.

### 4.1 Chandelier Exit
Developed by Chuck LeBeau. Based on highest close since entry minus a multiple of ATR.

```python
def chandelier_exit(highest_high_since_entry, atr, multiplier=3):
    """
    Chandelier Exit: Sell signal when price falls below
    (Highest High - 3 x ATR) for long positions.
    
    For short positions: Lowest Low + 3 x ATR
    """
    long_exit = highest_high_since_entry - (multiplier * atr)
    short_exit = get_current_low() + (multiplier * atr)  # for shorts
    return long_exit, short_exit

def update_chandelier_stop(position, entry_price, highest_close, atr, multiplier=3):
    """
    Track Chandelier stop level. Only moves up (for longs), never down.
    """
    stop_level = highest_close - (multiplier * atr)
    return max(position.get('stop', entry_price), stop_level)
```

**Variations:**
- `CLs` (Long Standard): Use highest close since entry, 3xATR
- `CLp` (Long Parabolic): ATR increases over time
- `CSs` (Short Standard): Use lowest close since entry, 3xATR

### 4.2 Parabolic SAR (Stop and Reverse)
Developed by J. Welles Wilder. Provides both stop-loss and reversal signals.

```
PSAR(t) = PSAR(t-1) + AF x (EP(t-1) - PSAR(t-1))

where:
  AF = Acceleration Factor (starts at 0.02, max 0.20)
  EP = Extreme Price (highest high for longs, lowest low for shorts)
```

```python
def parabolic_sar(highs, lows, af_start=0.02, af_max=0.20, af_step=0.02):
    """
    Calculate Parabolic SAR across a price series.
    """
    psar = np.zeros(len(highs))
    trend = 1  # 1 = long, -1 = short
    ep = highs[0]
    af = af_start
    
    psar[0] = lows[0]
    
    for i in range(1, len(highs)):
        prev_psar = psar[i-1]
        prev_af = af
        
        # New SAR
        psar[i] = prev_psar + prev_af * (ep - prev_psar)
        
        # Check for reversal
        if trend == 1:  # Currently long
            if lows[i] < psar[i]:
                trend = -1
                psar[i] = ep
                ep = lows[i]
                af = af_start
            else:
                if highs[i] > ep:
                    ep = highs[i]
                    af = min(af + af_step, af_max)
                psar[i] = min(psar[i], lows[i-1], lows[i-2] if i > 1 else lows[i-1])
        else:  # Currently short
            if highs[i] > psar[i]:
                trend = 1
                psar[i] = ep
                ep = highs[i]
                af = af_start
            else:
                if lows[i] < ep:
                    ep = lows[i]
                    af = min(af + af_step, af_max)
                psar[i] = max(psar[i], highs[i-1], highs[i-2] if i > 1 else highs[i-1])
    
    return psar, np.where(trend == 1, 'long', 'short')
```

### 4.3 High-Water Mark (HWM) Trailing Stop
Lock in profits relative to the peak value achieved since position entry.

```python
def hwm_trailing_stop(current_price, entry_price, peak_price, trail_pct=0.10):
    """
    Stop triggers when price falls trail_pct below peak price.
    
    Example: Bought at $100, peak $120, trail 10%
    -> Stop at $120 x (1 - 0.10) = $108
    -> If price rises to $125, stop moves to $125 x 0.90 = $112.50
    """
    peak = max(peak_price, current_price)  # Update peak if new high
    stop_level = peak * (1 - trail_pct)
    return stop_level, peak

def check_hwm_stop(current_value, hwm_value, stop_pct=0.10):
    """Check if trailing stop is hit."""
    stop_trigger = hwm_value * (1 - stop_pct)
    return current_value <= stop_trigger
```

### 4.4 Time-Based Trailing
Reduce exposure or exit after a fixed holding period regardless of PnL.

```python
MAX_HOLDING_PERIODS = {
    'intraday_scalp': 4,      # 4 15-min bars
    'swing': 20,              # 20 trading days
    'momentum': 60,           # 60 trading days
}

def time_based_exit(entry_bar, current_bar, strategy_type):
    """Exit if holding period exceeds maximum."""
    holding_bars = current_bar - entry_bar
    max_bars = MAX_HOLDING_PERIODS.get(strategy_type, 20)
    return holding_bars >= max_bars
```

---

## 5. Stop-Loss Types

### 5.1 Hard Stop vs. Soft Stop

| Type | Description | Execution |
|------|-------------|-----------|
| **Hard Stop** | Absolute price level; must be filled at or better | Market order on trigger |
| **Soft Stop** | Alert threshold; execution price not guaranteed | Limit order at soft_stop_price x multiplier |

```python
class StopLoss:
    def __init__(self, stop_type, stop_value, is_hard=True):
        self.stop_type = stop_type      # '固定价格', 'ATR', '百分比', 'support'
        self.stop_value = stop_value
        self.is_hard = is_hard
    
    def get_stop_price(self, entry_price, current_atr=None):
        if self.stop_type == '固定价格':
            return self.stop_value
        elif self.stop_type == 'ATR':
            return current_atr * self.stop_value
        elif self.stop_type == '百分比':
            return entry_price * (1 - self.stop_value)
        elif self.stop_type == 'support':
            return self.stop_value  # Nearest support level
```

### 5.2 ATR-Based Stops

```python
def atr_stop(entry_price, atr, stop_atr_multiples=2.0):
    """
    Stop-loss at entry_price - (N x ATR).
    Adapts to volatility; wider stops in volatile assets.
    """
    return entry_price - (stop_atr_multiples * atr)

def update_atr_stop(current_stop, entry_price, current_price, atr, 
                    multiplier=2.0, trailing=True):
    """
    ATR stop that can trail price movement.
    Stop only moves in direction favorable to position.
    """
    new_stop = current_price - (multiplier * atr)
    
    if trailing:
        # For long: stop only moves up
        return max(current_stop, new_stop)
    else:
        return new_stop
```

### 5.3 Percentage Stops
```python
FIXED_STOP_PCT = 0.02  # 2% stop from entry

def percentage_stop(entry_price, stop_pct=FIXED_STOP_PCT):
    return entry_price * (1 - stop_pct)

# Trailing version
def trailing_percentage_stop(peak_price, stop_pct=FIXED_STOP_PCT):
    return peak_price * (1 - stop_pct)
```

### 5.4 Support/Resistance Stops
Place stops just beyond key technical levels:

```python
def find_nearest_support(current_price, lookback=20):
    """Find nearest support level below current price."""
    lows = get_recent_lows(lookback)
    supports = find_swing_lows(lows)
    valid_supports = [s for s in supports if s < current_price]
    return min(valid_supports) if valid_supports else current_price * 0.95

def support_resistance_stop(entry_price, current_price, nearest_support, 
                            buffer_pct=0.005):
    """
    Stop placed just beyond support with buffer.
    """
    stop = nearest_support * (1 - buffer_pct)
    return min(stop, entry_price * 0.95)  # Never wider than 5% from entry
```

---

## 6. Risk of Ruin Calculation

Risk of Ruin (RoR) is the probability that a trading system will lose a specified portion of starting capital (typically 50% or more).

### 6.1 Binomial Ruin Formula

For a strategy with i.i.d. outcomes, win rate `p`, and fixed bet size:

```
RoR = ( (q/p)^B ) / ( (q/p)^(A+B) )

where:
  q = 1 - p
  B = bankroll units (starting capital / risk per trade)
  A = target losses in units = B - (target_ruin_level x B)
```

```python
def risk_of_ruin_binomial(p, bankroll_units, ruin_level=0.50):
    """
    Calculate risk of ruin using binomial model.
    
    Args:
        p: win probability
        bankroll_units: bankroll in units of bet size (e.g., $10,000 bankroll, $100 bets = 100 units)
        ruin_level: fraction of bankroll that constitutes "ruin" (default 50%)
    
    Returns:
        Probability of hitting ruin level before reaching goal
    """
    q = 1 - p
    
    if p <= q:
        return 1.0  # No positive expected value = certain ruin eventually
    
    # A = units we can lose before ruin
    A = bankroll_units * (1 - ruin_level)
    
    ratio = q / p
    RoR = (ratio ** bankroll_units - ratio ** (A + bankroll_units)) / (1 - ratio ** (A + bankroll_units))
    
    return max(0, min(1, RoR))

# Example: 55% win rate, $100,000 account, $2,000 risk per trade = 50 units
# Target ruin at 50% ($50,000 loss)
ror = risk_of_ruin_binomial(p=0.55, bankroll_units=50, ruin_level=0.50)
print(f"Risk of Ruin: {ror:.4%}")
```

### 6.2 Simulation-Based RoR

For complex strategies with varying position sizes:

```python
def risk_of_ruin_monte_carlo(returns, starting_capital, ruin_threshold=0.50,
                              n_simulations=10000, n_periods=252*5):
    """
    Monte Carlo simulation for risk of ruin.
    """
    ruin_count = 0
    
    for sim in range(n_simulations):
        capital = starting_capital
        
        for period in range(n_periods):
            # Random return from historical distribution
            ret = np.random.choice(returns)
            capital *= (1 + ret)
            
            if capital <= starting_capital * ruin_threshold:
                ruin_count += 1
                break
    
    return ruin_count / n_simulations

# Usage with historical strategy returns
historical_returns = [...]  # List of daily returns
ror_sim = risk_of_ruin_monte_carlo(historical_returns, 
                                    starting_capital=100000,
                                    ruin_threshold=0.50)
```

### 6.3 Position Size for Target RoR

Inverse problem: what bet size produces a desired risk of ruin?

```python
def position_size_for_ror(p, target_ror, bankroll, ruin_level=0.50):
    """
    Given target risk of ruin, find maximum position size.
    """
    q = 1 - p
    target_ror = min(target_ror, 0.9999)  # Prevent log(0)
    
    if p <= q:
        return 0  # No viable position size
    
    # Solve for bankroll_units from RoR formula
    import math
    ratio = q / p
    
    # RoR = (ratio^B - ratio^(A+B)) / (1 - ratio^(A+B))
    # Simplified for ruin at 50% (A = B):
    # RoR = (ratio^B - ratio^(2B)) / (1 - ratio^(2B)) = ratio^B
    
    bankroll_units = math.log(target_ror) / math.log(ratio)
    bet_size = bankroll / bankroll_units
    
    return bet_size

# Example: 55% win rate, 1% target RoR, $100,000 account
bet = position_size_for_ror(p=0.55, target_ror=0.01, bankroll=100000)
print(f"Maximum bet size for 1% RoR: ${bet:,.2f}")  # ~$6,300
```

---

## 7. Portfolio Overlay

Portfolio overlay manages risk at the multi-strategy, multi-asset portfolio level. It sits above individual strategy risk controls.

### 7.1 Rebalancing Triggers

```python
REBALANCE_TRIGGERS = {
    'threshold': 0.05,      # Rebalance if any asset drifts > 5% from target
    'calendar': 'quarterly', # Rebalance on fixed schedule
    'tolerance_band': 0.02,  # Allow 2% drift before rebalancing
    'max_deviation': 0.10,  # Force rebalance if any asset > 10% from target
}

def check_rebalance_needed(current_weights, target_weights, triggers):
    """
    Determine if portfolio needs rebalancing.
    """
    deviations = {asset: abs(current_weights.get(asset, 0) - target_weights.get(asset, 0))
                  for asset in target_weights}
    
    max_dev = max(deviations.values())
    threshold = triggers['threshold']
    
    if max_dev > triggers['max_deviation']:
        return True, "Max deviation exceeded - forced rebalance"
    
    if max_dev > threshold:
        return True, f"Drift {max_dev:.2%} exceeds threshold {threshold:.2%}"
    
    return False, "Within tolerance"

def calculate_rebalance_orders(current_weights, target_weights, total_capital):
    """Calculate orders needed to rebalance to target weights."""
    orders = {}
    for asset in target_weights:
        target_value = target_weights[asset] * total_capital
        current_value = current_weights.get(asset, 0) * total_capital
        diff = target_value - current_value
        
        if abs(diff) > REBALANCE_TOLERANCE * total_capital:
            orders[asset] = diff / get_asset_price(asset)
    
    return orders
```

### 7.2 Over-Concentration Checks

```python
MAX_SINGLE_NAME = 0.08       # Max 8% in single name
MAX_SINGLE_ISSUER = 0.15     # Max 15% with same issuer (e.g., parent company)
MAX_BROKER_DEALER = 0.10     # Max 10% with same broker/dealer

def concentration_check(positions, total_equity):
    """
    Check portfolio for over-concentration.
    """
    issues = []
    
    # Single name concentration
    for ticker, shares in positions.items():
        weight = (shares * get_price(ticker)) / total_equity
        if weight > MAX_SINGLE_NAME:
            issues.append(f"OVER-CONCENTRATION: {ticker} at {weight:.2%} (limit {MAX_SINGLE_NAME:.2%})")
    
    # Check for common issuer exposure
    issuer_map = get_issuer_map()
    issuer_exposure = {}
    for ticker, shares in positions.items():
        issuer = issuer_map.get(ticker, 'Unknown')
        value = shares * get_price(ticker)
        issuer_exposure[issuer] = issuer_exposure.get(issuer, 0) + value
    
    for issuer, exposure in issuer_exposure.items():
        weight = exposure / total_equity
        if weight > MAX_SINGLE_ISSUER:
            issues.append(f"ISSUER CONCENTRATION: {issuer} at {weight:.2%}")
    
    return issues
```

### 7.3 Sector Exposure Checks

See Section 2.2 for sector concentration limits and implementation.

---

## 8. Execution Risk Management

Execution risk is the risk that an order is not filled, fills at a worse price than expected, or partially fills.

### 8.1 Slippage Modeling

Slippage = Actual Fill Price - Expected Fill Price

```python
def estimate_slippage(order_size, market_volatility, liquidity_score=1.0):
    """
    Model expected slippage for a given order.
    
    Args:
        order_size: Order size in dollars
        market_volatility: Current annualized vol of the asset
        liquidity_score: 1.0 = liquid, <1.0 = illiquid, >1.0 = very liquid
    
    Returns:
        Estimated slippage in basis points
    """
    # Kyle's lambda model simplified
    # Slippage increases with order size and volatility, decreases with liquidity
    vol_factor = market_volatility / 0.16  # Normalize to 16% vol
    base_slippage_bps = 5  # Base slippage in bps for normal conditions
    
    # Order size impact (larger orders = more slippage)
    size_factor = np.log1p(order_size / 100000) * 2  # Log-scaled impact
    
    slippage = base_slippage_bps * vol_factor / liquidity_score * (1 + size_factor)
    
    return slippage  # in basis points

def apply_slippage_to_backtest(trade_pnl, order_size, volatility):
    """
    Adjust backtest PnL for realistic slippage.
    """
    slippage_bps = estimate_slippage(order_size, volatility)
    slippage_cost = trade_pnl * (slippage_bps / 10000)
    return trade_pnl - slippage_cost

# Example
slippage = estimate_slippage(order_size=500000, market_volatility=0.25, liquidity_score=0.8)
print(f"Estimated slippage: {slippage:.2f} bps = {slippage/10000:.2%}")
```

### 8.2 Order Fill Probability

```python
def fill_probability(order_type, distance_from_mid, order_size, 
                     market_volume, volatility, time_horizon_bars=1):
    """
    Estimate probability of order fill within time horizon.
    
    Args:
        distance_from_mid: How far limit price is from mid (bps)
        order_size: Order size in notional
        market_volume: Expected daily volume
        volatility: Asset volatility
        time_horizon_bars: Number of bars to wait for fill
    
    Returns:
        Probability of fill (0 to 1)
    """
    # Probability decreases with larger size and more volatility
    participation_rate = order_size / market_volume
    
    # Volume decays over time; volatility causes price to move away
    vol_factor = np.exp(-volatility * np.sqrt(time_horizon_bars / 252))
    
    # Base fill probability from distance
    if order_type == 'limit':
        distance_penalty = min(distance_from_mid / 50, 1.0)  # 50 bps = max penalty
        base_fill = 0.95 * (1 - distance_penalty * 0.5)
    else:  # market order
        base_fill = 0.99
    
    # Size impact: participation > 5% = significant fill probability reduction
    size_impact = max(0.5, 1 - participation_rate * 5)
    
    fill_prob = base_fill * size_impact * vol_factor
    
    return min(1.0, max(0.0, fill_prob))
```

### 8.3 Partial Fill Handling

```python
class PartialFillHandler:
    def __init__(self, strategy_id, target_size, order_type='limit'):
        self.strategy_id = strategy_id
        self.target_size = target_size
        self.filled_size = 0
        self.avg_fill_price = 0
        self.order_type = order_type
        self.retry_limit = 3
        self.retry_count = 0
    
    def on_partial_fill(self, fill_size, fill_price):
        """Update position with partial fill."""
        total_cost = self.avg_fill_price * self.filled_size + fill_price * fill_size
        self.filled_size += fill_size
        self.avg_fill_price = total_cost / self.filled_size if self.filled_size > 0 else 0
        
        logger.info(f"Partial fill: {fill_size} @ {fill_price}. "
                    f"Total: {self.filled_size}/{self.target_size}")
    
    def should_retry(self, current_price, limit_price=None):
        """Determine if we should continue trying to fill remainder."""
        remaining = self.target_size - self.filled_size
        
        if remaining <= 0:
            return False
        
        if self.retry_count >= self.retry_limit:
            logger.warning(f"Retry limit reached for {self.strategy_id}")
            return False
        
        if self.order_type == 'limit' and limit_price:
            # Check if price has moved away significantly
            distance_bps = abs(current_price - limit_price) / limit_price * 10000
            if distance_bps > 20:  # More than 20 bps away
                return False
        
        return True
    
    def adjust_order(self, current_price, new_limit_distance_bps=10):
        """Create adjusted order for remaining size."""
        remaining = self.target_size - self.filled_size
        
        if remaining <= 0:
            return None
        
        # Improve limit price to increase fill probability
        if self.order_type == 'limit':
            new_limit = current_price * (1 - new_limit_distance_bps / 10000)
            return {'size': remaining, 'price': new_limit, 'type': 'limit'}
        else:
            return {'size': remaining, 'type': 'market'}
```

---

## 9. Real Quant Fund Implementations

### 9.1 Renaissance Technologies (Medallion Fund)

- **Position sizing:** Volatility-targeting with short-term mean-reversion overlay
- **Risk limits:** Strict drawdown controls; max 2x leverage on any position
- **Execution:** Proprietary dark pool access; co-location; extremely low latency
- **Key insight:** Medallion's edge is primarily execution and microstructure, not just alpha
- **Drawdown management:** No public disclosure, but estimated < 10% annual drawdown

### 9.2 Bridgewater Associates (All Weather / Pure Alpha)

- **Risk parity:** All Weather uses risk-parity across asset classes
- **GEMINI:** Proprietary risk management system with CB4 backtest gate
  - Live performance continuously compared to backtest
  - Strategy disabled if Sharpe ratio beta < 60% of backtest
- **Daily risk report:** Flags any position > 2x its expected loss
- **Economic regime monitoring:** Adjusts exposure based on growth/inflation signals

### 9.3 Two Sigma

- **Risk management:** Multi-factor risk model; stress testing under 100+ scenarios
- **Volatility-targeting:** Dynamic position scaling based on realized vs implied vol
- **Concentration limits:** Max 3% in single name; max 20% in single sector
- **Slippage modeling:** Proprietary transaction cost model (TCM) integrated into alpha signal
- **Machine learning:** Uses ML for order execution optimization and fill prediction

### 9.4 Citadel Securities (Ken Griffin)

- **Execution:** One of the largest market makers; sees order flow before competitors
- **Internal crossing:** Internalizes order flow to reduce market impact
- **Adaptive execution:** Uses reinforcement learning for order execution
- **Risk:** Real-time Greeks monitoring; automatic circuit breakers trigger within milliseconds

### 9.5 DE Shaw

- **Quantamental:** Combines quantitative models with fundamental research
- **Risk model:** Barra ONEGEM-style multi-factor risk model
- **Rebalancing:** Systematic rebalancing with transaction cost optimization
- **Overlays:** Human risk managers can override algorithmic signals (human-in-the-loop)

### 9.6 Common Patterns Across Top Funds

1. **Volatility-targeting is universal** -- almost all professional quant funds use some form of vol-targeting
2. **Multi-layer risk controls** -- circuit breakers at strategy, portfolio, and firm level
3. **Real-time risk aggregation** -- positions valued and risk-calculated continuously (not EOD)
4. **Transaction cost modeling** -- slippage and market impact integrated into signal generation
5. **Stress testing** -- regular testing against historical crisis scenarios (2008, March 2020, etc.)
6. **Human oversight** -- even "pure" quant funds have human risk managers who can intervene

---

## Summary Table

| Component | Key Metric | Typical Threshold |
|-----------|-----------|-------------------|
| Position Sizing | Kelly % or Vol-target multiplier | Full Kelly rarely used; 25-50% fractional |
| Daily Loss CB | CB1 | -2% triggers halt |
| Drawdown CB | CB3 | -10% triggers review |
| Bankroll Floor | CB5 | 50% = mandatory wind-down |
| Trailing Stop | Chandelier ATR multiplier | 3x ATR common |
| Risk of Ruin | Target | < 1% for most strategies |
| Sector Limit | Max weight per sector | 20-25% typical |
| Single Name | Max weight per issuer | 5-8% typical |
| Slippage | bps | 5-20 bps depending on liquidity |

---

## References and Further Reading

- Thorp, E.O. -- "Kelly Money Management"
- LeBeau, C. -- " Chandelier Stops and Trailing Stops"
- Wilder, J.W. -- "New Concepts in Technical Trading Systems" (Parabolic SAR)
- Markowitz, H. -- "Portfolio Selection" (Modern Portfolio Theory)
- Maillard, S. -- "Risk Parity: About the Fragility of the Risk Parity Approach"
- Almgren, R. & Chriss, N. -- "Optimal Execution of Portfolio Transactions"
- Bloomberg GEMINI Risk System documentation
- Barra ONE Risk Model handbook
