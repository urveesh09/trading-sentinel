# NSE India Algorithmic Trading -- Market Structure & Execution Research

**Compiled:** 2026-05-18
**Scope:** NSE India-specific market structure, transaction costs, regulatory framework, execution timing, F&O integration, volatility regime, sector rotation, and historical anomalies for algorithmic trading systems.
**Target system:** `python-engine` in `trading-sentinel`, NSE equity / NFO spread.

---

## Table of Contents

1. [Market Structure](#1-market-structure)
2. [Liquidity Patterns](#2-liquidity-patterns)
3. [Circuit Breakers & Price Bands](#3-circuit-breakers--price-bands)
4. [Regulatory Framework (SEBI)](#4-regulatory-framework-sebi)
5. [Transaction Cost Model](#5-transaction-cost-model)
6. [Market Hours & Execution Windows](#6-market-hours--execution-windows)
7. [F&O Integration](#7-fo-integration)
8. [India VIX for Regime Detection](#8-india-vix-for-regime-detection)
9. [Sector Rotation Patterns](#9-sector-rotation-patterns)
10. [Historical Anomalies on NSE](#10-historical-anomalies-on-nse)

---

## 1. Market Structure

### 1.1 T+1 Settlement

NSE operates on **T+1 settlement** (mandatory since 2022 for cash equity):
- Trade date T: Order execution happens during market hours
- Settlement date T+1: Stock delivery vs funds exchange occurs the next business day
- **Intraday (MIS/MIS-PRO):** Positions auto-squared off at 15:30 IST -- no actual delivery; T+1 applies to funds, not stock
- **Delivery (CNC):** Stock credited to Demat account T+1; funds debited T+1
- **Implication for algos:** Intraday margin is not capital-efficient for overnight positions; CNC requires next-day settlement awareness

**Key edge:** T+1 creates overnight gap risk (overnight news, global moves) not present in T+0 markets. Position sizing must account for overnight hold without intraday exit.

### 1.2 Pre-Open Session (09:00-09:15 IST)

NSE conducts a **15-minute pre-open auction** before regular market opens:

| Sub-phase | Time | Purpose |
|-----------|------|---------|
| Order collection | 09:00-09:08 | Accept limit orders; no matching |
| Order matching | 09:08-09:12 | Single-price auction execution |
| Post-auction | 09:12-09:15 | Buffer before regular market |
| Regular market | 09:15 | Continuous trading begins |

- **Eligible securities:** All NSE equity scrips (max 5% upper/lower price band during auction)
- **Order types in auction:** Limit orders only; no market orders
- **Price discovery:** Single weighted average price (WAP) determined from buy-sell order book
- **Information content:** Opening auction price reflects overnight news, global cues, pre-market sentiment
- **Algo implication:** Avoid signal evaluation during 09:00-09:15 -- volatility is elevated, spreads wide, false breakouts common. System should start at 09:30+ per current calibration.

### 1.3 Intraday Auction Session (14:00-14:45 IST)

NSE conducts a **45-minute intraday auction** (also called the closing auction or MGM -- Modify Given Market) starting at 14:00 for select securities:

- **Purpose:** Allows institutional block trades, late-order matching at competitive prices
- **Mechanism:** Orders accumulate 14:00-14:45; single-price auction executes at 14:45
- **Tracked by algos:** Volume surge during 14:00-14:45 may signal institutional accumulation/distribution
- **Impact on momentum signals:** Late-day range compression often precedes directional moves next day

### 1.4 Closing Session (15:30-15:40 IST)

NSE closing is a **10-minute closing auction** (15:30-15:40):

| Sub-phase | Time | Purpose |
|-----------|------|---------|
| Closing auction order entry | 15:30-15:35 | Last chance to submit closing auction orders |
| Pre-close | 15:35-15:40 | Index constituents priced; arbitrage vs futures basis narrows |
| Close price published | 15:40 | Official NSE closing price for benchmarks |

- **Closing price relevance:** Index funds, index derivatives, and MSCI-rebalanced securities all anchor to 15:40 close
- **Execution quality:** Closing auction often has better liquidity for large orders than intraday -- institutional preference
- **Algo implication:** Closing-price strategies (e.g., buying at close, selling next open) are viable. Avoid pre-close (15:35-15:40) for new entries -- direction is ambiguous due to index tracking flows.

### 1.5 Block Deals

Block deals on NSE occur during a **15-minute window** (09:15-09:30 or 14:45-15:00) where large orders (>=Rs5 crore per order) are matched at a single price:

- **Minimum order size:** Rs5 crore (~=$6M USD)
- **Pre-arranged:** Typically bilateral, pre-agreed between two parties
- **Visible to market:** Price and volume of block deals published by NSE after execution
- **Significance for algos:** Large block deals in pre-open or intraday auction window signal institutional activity. Can precede directional moves in the scrip, especially in mid/small-cap stocks.
- **Practical use:** Monitor block deal data to gauge institutional accumulation/distribution as a confluence factor.

### 1.6 Post-Broadcast Session (15:40-17:00 IST)

After market close, institutional and proprietary traders continue trading in:
- **NSE Derivative segment:** Futures and options continue until 17:30 IST
- **Currency derivatives:** 09:00-17:00 IST
- **OTC / risk transfer:** Large institutions use Nifty futures for position adjustment post-close

**Algo implication:** Overnight futures positioning (Nifty, BankNifty) after 15:40 reflects institutional sentiment. Monitor Nifty futures price action 15:40-17:00 for overnight directional clues.

---

## 2. Liquidity Patterns

### 2.1 Average Daily Volume by Market Cap Tier

NSE equity liquidity is highly tiered:

| Tier | Scrips | ADV (approx.) | Market Impact |
|------|--------|---------------|---------------|
| **Nifty 50** | 50 stocks | Rs15,000-25,000 Cr/day | Very low; tight spreads (0.02-0.05%) |
| **Nifty Midcap 100** | 100 stocks | Rs3,000-6,000 Cr/day | Low; spreads 0.05-0.15% |
| **Nifty Smallcap 250** | 250 stocks | Rs1,000-2,500 Cr/day | Moderate; spreads 0.15-0.50% |
| **Micro-cap (<Rs500 Cr mkt cap)** | Thousands | Rs10-200 Cr/day | High; spreads 0.5-3%+, impact significant |

**ADV = Average Daily Volume (combined buy+sell turnover)**

### 2.2 Impact Cost Data

Impact cost on NSE varies significantly by tier:

| Scrip Type | Typical Impact Cost (1% of ADV) | Notes |
|-----------|--------------------------------|-------|
| Nifty 50 liquid stock | 0.02-0.05% | Virtually negligible for retail/small algo orders |
| Midcap liquid | 0.10-0.25% | Meaningful for orders >Rs1 Cr |
| Smallcap | 0.30-1.00% | Significant; large orders move price materially |
| Lower-circuit stocks | Undefined | Cannot trade; avoid |

**Formula:** For a Rs5 crore order in a stock with 0.25% impact cost:
```
Slippage = Rs5 Cr x 0.0025 = Rs1,25,000
```

### 2.3 Liquidity Tiers for Strategy Assignment

| Strategy | Recommended Tier | Rationale |
|----------|-----------------|-----------|
| Momentum / Breakout | Nifty 50 + Midcap 100 | Volume sufficient; low impact cost |
| Mean Reversion | Nifty 50 preferred | Tighter spreads; mean reversion signals more reliable |
| Statistical Arbitrage | Nifty 50 + Nifty Jr. | Basis trades require liquid underlyings |
| Pairs Trading | Sector peers within tier | Ensure both legs have comparable liquidity |
| VWAP Execution | Any tier with sufficient ADV | Impact cost modeling required per scrip |

### 2.4 Bid-Ask Spread Dynamics

- **Nifty 50 stocks:** Rs0.05-0.25 tick size; spreads 0.01-0.05% of price
- **Midcap:** Rs0.25-1.00 tick size; spreads 0.05-0.20%
- **Smallcap:** Rs1.00-5.00 tick size; spreads 0.20-1.00%
- **Liquidity degrades:** During 12:30-13:30 (lunch), spreads widen 1.5-3x; during 14:45-15:30 (pre-close), spreads narrow but volume concentrated

---

## 3. Circuit Breakers & Price Bands

### 3.1 Index-Level Circuit Breakers (Nifty)

NSE Nifty index has three circuit levels that halt the entire market:

| Circuit Level | Nifty Move | Trigger | Action |
|---------------|-----------|---------|--------|
| **Stage 1** | +/-10% | On or before 1:00 PM | Halt for 15 min; resume at 13:15+ |
| **Stage 2** | +/-15% | On or before 2:00 PM | Halt for 15 min; resume at 14:15+ |
| **Stage 3** | +/-20% | Anytime | Halt for remainder of day; no trading |

**Stage 1 & 2 only apply if circuit is hit by 13:00 / 14:00 respectively.** After those times, market trades through.

### 3.2 Stock-Level Price Bands (Individual Scrips)

Individual NSE stocks have mandatory price bands:

| Circuit | Applicable To | Notes |
|---------|--------------|-------|
| **5% circuit** | Most stocks (Nifty 100, other liquid) | Cannot trade beyond +/-5% from previous close |
| **10% circuit** | Midcap / some smallcap | Wider band; more volatile |
| **20% circuit** | Smallcap / illiquid / recently listed | Extreme volatility; hard to exit |

- **Pre-open auction band:** +/-5% from reference price (previous close or theoretical price)
- **Effect on stop-loss:** Stop-loss orders placed beyond circuit levels will not execute. Algorithmic stops must be placed within current circuit band.
- **Circuit avoidance rule:** Lower circuits (stocks hitting 5% lower circuit) should be avoided -- probability of further decline elevated; buying into a lower circuit stock is high-risk.

### 3.3 Impact on Stop-Loss Execution

| Scenario | Stop-Loss Behavior | Algo Handling |
|----------|-------------------|---------------|
| Stock hits upper circuit | No sellers available; stop-loss BUY cannot execute | Avoid shorting upper-circuit stocks |
| Stock hits lower circuit | No buyers available; stop-loss SELL cannot execute | Avoid holding lower-circuit stocks overnight |
| Volatile stock near circuit | Spreads widen dramatically; actual fill far from trigger | Use limit orders, not market stop-loss |
| Circuit halt (index) | Entire market pauses 15 min; resume may gap | Cancel/re-submit orders post-halt |

**Best practice:** Set stops at prices *within* the current circuit band. For a 5% circuit stock at Rs100, stop-loss sell must be >=Rs95 (not below). Monitor circuit proximity in real-time.

---

## 4. Regulatory Framework (SEBI)

### 4.1 SEBI Algorithmic Trading Rules

SEBI has progressively regulated algorithmic trading since 2012:

**Mandatory Registration:**
- All algorithmic traders (proprietary) must register with SEBI as "Algorithmic Trading Authorised Persons" (ATAPs)
- System audit / compliance required for registered algos
- NSE/BSE compliance infrastructure must be in place

**Order-to-Trade Ratio (OTR):**
- SEBI mandates OTR <= 50:1 (no more than 50 orders per 1 executed trade)
- Purpose: Prevent quote stuffing and unnecessary market data traffic
- **Algo implication:** If strategy generates frequent order updates without fills, OTR monitoring is required

**Co-location (Co-lo) Rules:**
- SEBI mandates equal access for all colocation users
- Co-located servers must be registered; unfair latency advantage penalized
- NSE offers co-location in Mumbai (CHennai for BSE); latency tiers exist
- **Practical:** Most retail/semi-professional algos trade via internet; co-location adds ~1-3ms advantage -- only meaningful for high-frequency strategies

**Market Manipulation Rules:**
- Front-running detection algorithms monitor unusual order patterns
- Algorithmic orders flagged for "circular trading" or "wash trades" are investigated
- Position limits per exchange participant for equity derivatives

### 4.2 SEBI Risk Controls Required for Algos

- **Kill switch:** Mandatory ability to cancel all open orders within 1 second
- **Position limit monitoring:** Real-time tracking of exposure and margin utilization
- **Price reasonability checks:** Orders outside +/-20% of reference price automatically rejected by broker
- **Message throttling:** NSE enforces maximum messages per second per member

### 4.3 SEBI Insider Trading & Algorithm Code of Conduct

- **Algorithmic code:** SEBI requires documented algo design, testing, and audit trail
- **Audit trail:** All orders must carry a unique "algorithm ID" tag
- **Risk management integration:** Brokers must integrate algos with their RMS before enabling live trading

---

## 5. Transaction Cost Model

### 5.1 Complete NSE Equity Transaction Cost Breakdown

For a **buy and sell intraday trade** (MIS -- Margin Intraday Square-off):

**BUY Side:**
| Component | Rate | Tax Base | Amount (Rs100 trade) |
|-----------|------|----------|---------------------|
| Brokerage | Flat Rs20/trade OR 0.02-0.05% per side | Per trade | Rs20 flat or Rs0.05 |
| Exchange Transaction Charge | 0.00345% | On turnover | Rs0.0035 |
| SEBI Charges | 0.0001% | On turnover | Rs0.0001 |
| GST | 18% | On brokerage | Rs3.60 |
| Stamp Duty | 0.02% | On buy side turnover | Rs0.02 |
| **Total Buy Cost** | | | **~=Rs23.62 + brokerage** |

**SELL Side (Intraday):**
| Component | Rate | Tax Base | Amount (Rs100 trade) |
|-----------|------|----------|---------------------|
| Brokerage | Same as buy | Per trade | Rs20 flat or Rs0.05 |
| Exchange Transaction Charge | 0.00345% | On turnover | Rs0.0035 |
| STT (Securities Transaction Tax) | 0.025% | On sell side turnover | Rs0.025 |
| SEBI Charges | 0.0001% | On turnover | Rs0.0001 |
| GST | 18% | On brokerage | Rs3.60 |
| Stamp Duty | 0.03% | On sell side turnover | Rs0.03 |
| **Total Sell Cost** | | | **~=Rs23.66 + brokerage + STT** |

**For delivery (CNC) trades:** STT is 0.1% on sell side (instead of 0.025%), and stamp duty is also charged on sell side at 0.03%. No auto-square.

### 5.2 Complete Per-Trade Cost Formula

For a **round-trip intraday trade** (buy + sell):

```python
def calc_nse_total_cost(trade_value, brokerage_per_side=20, brokerage_type='flat'):
    """
    Calculate total transaction cost for NSE equity intraday trade.
    
    Args:
        trade_value: Single-side trade value (Rs)
        brokerage_per_side: Brokerage in Rs (flat) or % (if percentage type)
        brokerage_type: 'flat' or 'percentage'
    
    Returns:
        dict with cost breakdown and total
    """
    if brokerage_type == 'flat':
        brokerage = brokerage_per_side  # per side
    else:
        brokerage = trade_value * (brokerage_per_side / 100)  # per side
    
    # BUY SIDE
    buy_exchange_txn = trade_value * 0.0000345
    buy_sebi = trade_value * 0.000001
    buy_gst = brokerage * 0.18
    buy_stamp = trade_value * 0.0002  # 0.02%
    
    buy_total = brokerage + buy_exchange_txn + buy_sebi + buy_gst + buy_stamp
    
    # SELL SIDE
    sell_exchange_txn = trade_value * 0.0000345
    sell_stt = trade_value * 0.00025  # 0.025% intraday
    sell_sebi = trade_value * 0.000001
    sell_gst = brokerage * 0.18
    sell_stamp = trade_value * 0.0003  # 0.03%
    
    sell_total = brokerage + sell_exchange_txn + sell_stt + sell_sebi + sell_gst + sell_stamp
    
    round_trip_cost = buy_total + sell_total
    cost_pct = (round_trip_cost / trade_value) * 100
    
    return {
        'buy_cost': round(buy_total, 2),
        'sell_cost': round(sell_total, 2),
        'round_trip_cost': round(round_trip_cost, 2),
        'cost_pct': round(cost_pct, 4),
        'effective_bp_cost': round(cost_pct * 100, 2)  # basis points
    }
```

**Example:** Rs1,00,000 single-side trade (Rs2,00,000 round trip):
```
Brokerage (flat Rs20x2):     Rs40.00
Exchange Txn (0.00345%x2):   Rs6.90
STT (0.025% sell):          Rs25.00
SEBI (0.0001%x2):            Rs0.20
GST (18%xRs40):               Rs7.20
Stamp duty (0.02%+0.03%):    Rs50.00
----------------------------------------
Total:                     Rs129.30
Effective round-trip cost: 0.065% (~=6.5 bp)
```

**For small trades (Rs10,000 single-side):**
```
Effective cost ~= 0.13-0.15% (13-15 bp) -- brokerage flat fee dominates
For large trades (Rs10L single-side):
Effective cost ~= 0.065% (6.5 bp) -- fees as % of value
```

### 5.3 Cost Impact on Strategy Profitability

| Strategy | Min. Edge Required | Notes |
|----------|-------------------|-------|
| Momentum (intraday) | >=0.15% per trade | After all costs; R-multiple must cover |
| Mean Reversion | >=0.10% per trade | Faster cycle; costs dominate |
| Trend Following (swing) | >=0.20% per trade | Overnight hold adds gap risk |
| Pairs Trading | >=0.05% per leg | Both legs incur costs; spread must cover |

---

## 6. Market Hours & Execution Windows

### 6.1 NSE Market Hours (All Segments)

| Segment | Pre-Open | Regular | Close |
|---------|----------|---------|-------|
| **Equity Cash** | 09:00-09:15 | 09:15-15:30 | 15:40 |
| **Equity F&O** | 09:00-09:15 | 09:15-15:30 | 15:40 |
| **Nifty Futures** | 09:00-09:15 | 09:15-15:30 | 15:40 |
| **BankNifty Futures** | 09:00-09:15 | 09:15-15:30 | 15:40 |
| **Options (Equity)** | 09:00-09:15 | 09:15-15:30 | 15:30 |
| **Currency Derivatives** | 09:00-09:15 | 09:00-17:00 | 17:00 |
| **Commodity (MCX)** | 09:00-09:15 | 09:00-23:30 | 23:30 |

### 6.2 Execution Quality by Time Window

| Time Window | Character | Execution Quality | Algo Recommendation |
|-------------|-----------|-------------------|----------------------|
| **09:00-09:15** | Pre-open auction; no continuous matching | Avoid -- high volatility, no fills on stops | No new entries |
| **09:15-09:30** | Opening batch auction + volatile start | High slippage, false breakouts | Reduce size; confirm signals |
| **09:30-10:00** | Active trend establishment | **Best window** for momentum | Full signal evaluation |
| **10:00-11:30** | Normal trading | Good execution quality | Normal operation |
| **11:30-13:15** | Lunchtime dead zone | Low volume, elevated false breakouts | Volume gates elevated (MC3-T); reduce |
| **13:15-14:30** | Afternoon session | Institutional resumes; **second-best** | Good for momentum continuation |
| **14:30-15:15** | Pre-close | Range compression, direction ambiguous | Reduce; prepare for close |
| **15:15-15:30** | Closing auction | Used for close-price strategies only | Only for close-anchored strategies |
| **15:30-15:40** | Closing print | Index benchmark pricing | Monitor only |
| **15:40-17:00** | Post-close futures | Nifty/BankNifty futures active | Watch for overnight cues |

### 6.3 Optimal Execution Windows Summary

**Best windows for new entries:**
1. **09:30-10:00 IST** -- Primary momentum window; trends establish with high conviction
2. **13:15-14:30 IST** -- Secondary window; institutional afternoon activity resumes

**Worst windows for new entries:**
1. **11:30-13:15 IST** -- Lunchtime; low volume, mean-reversion bias, false breakouts
2. **09:00-09:15 IST** -- Pre-open; no continuous market, high volatility
3. **14:30-15:30 IST** -- Pre-close compression; ambiguous direction

**Current system calibration:** `MC3-T` volume threshold is raised during 11:30-13:15 (lunchtime) -- correctly reducing false signals in the dead zone.

---

## 7. F&O Integration

### 7.1 Nifty/BankNifty Hedging

**Hedging equity exposure with index derivatives:**
- Long equity + Short Nifty/BankNifty futures = Beta-adjusted hedge
- Beta calculation: `Beta = Cov(Stock, Nifty) / Var(Nifty)`
- Example: Stock with Beta 1.2 -> hedge with 1.2x notional in short futures
- **Hedge ratio:** `Hedge Contracts = (Stock Value x Beta) / (Futures Price x Lot Size)`

**Nifty lot sizes (approximate):**
| Instrument | Lot Size | Notional (Nifty ~24,500) |
|------------|----------|--------------------------|
| Nifty Futures | 25 | Rs6,12,500 |
| BankNifty Futures | 15 | Rs12,00,000+ |
| Nifty Options (ITM) | 25 | Varies by strike |
| BankNifty Options | 15 | Varies by strike |

### 7.2 Options for Structured Trades

**Covered Call (Equity + Short Call):**
- Hold CNC position in stock; sell OTM call against it
- Income generation; caps upside but provides downside cushion
- Works well in rangebound / slightly bearish markets

**Protective Put (Equity + Long Put):**
- Hold CNC position; buy OTM put as insurance
- Expensive (pay premium); use when expecting volatility spike
- Better to use for event-driven trades (earnings, budget, RBI policy)

**Bull Call Spread (Both legs via NFO):**
- Buy lower-strike Call + Sell higher-strike Call (same expiry)
- Net debit; limited risk; defined reward
- Good for moderately bullish views with limited capital

**Collar (Equity + Long Put + Short Call):**
- Hold stock + Long OTM put + Short OTM call
- Essentially a covered call with put protection
- Low/no cost if call premium ~= put premium

### 7.3 Basis Trade Mechanics (Nifty Futures vs Cash)

**Cash-Futures Basis:**
- Basis = Futures Price - Spot Price
- Positive basis (contango): Futures > Spot (normal; carry cost)
- Negative basis (backwardation): Futures < Spot (inverted; dividend expectations, shortage)

**Basis Trade:**
- Buy spot (Nifty ETF or constituent stock basket) + Sell futures = Lock in basis
- Basis converges to zero at expiry
- **Typical return:** ~8-12% annualized on basis (risk-free if correctly delta-hedged)
- **Execution:** Basis widest at market open; narrows toward expiry

**Nifty ETF vs Futures Basis:**
- Nifty BEES / Nifty Bees ETF tracks Nifty with tracking error <0.05%
- ETF vs Futures basis typically 0.02-0.10% (small but tradeable)
- Institutional basis trades move the ETF; monitor ETF flow as leading indicator

### 7.4 F&O Segment Timing Edge

- F&O closes at 15:30 (options) and 15:40 (futures) for equity derivatives
- Post-close Nifty futures in global markets (SGX Nifty) trade 15:40-17:00 and 17:15-09:00
- **SGX Nifty as overnight cue:** SGX contract (+/-0.3% of Nifty) is best leading indicator for 09:15 open
- **Practical:** Check SGX Nifty at 08:30 IST for overnight US/EU session impact assessment

---

## 8. India VIX for Regime Detection

### 8.1 India VIX Calculation Methodology

India VIX (Bloomberg: INDIAVIX) is computed by NSE using CBOE VIX methodology adapted for Nifty options:

**Formula:**
```
VIX = sqrt( (2 x discounted strike sum) / T - (forward price - strike)^2 / T )
```

**Key components:**
- **Option strip:** OTM puts and calls across multiple strikes (>=4 strikes above/below ATM)
- **Weighting:** Out-of-the-money options weighted by 1/K^2 (higher weight for strikes near ATM)
- **Time to expiry:** T measured in minutes to expiration
- **Risk-free rate:** Internally computed (not published separately)
- **Forward price:** Derived from put-call parity

**VIX interpretation:**
- VIX = 15 -> "Normal" market; expected daily move ~= 15%/sqrt252 ~= 0.94%
- VIX = 20 -> Elevated volatility; expected daily move ~= 1.26%
- VIX = 30 -> High volatility; expected daily move ~= 1.89%
- VIX = 40 -> Crisis level; expected daily move ~= 2.52%

### 8.2 VIX Thresholds for Strategy Adjustment

| VIX Level | Market Regime | Algo Adjustment |
|-----------|--------------|------------------|
| **< 12** | Low volatility / complacency | Reduce hedges; expand R-target; more aggressive sizing |
| **12-17** | Normal range | Standard parameters; no regime change needed |
| **17-22** | Elevated volatility | Increase volume threshold (MC3+0.2), reduce position size 20-30%, tighten stops |
| **22-28** | High volatility / uncertain | Significant size reduction, wider stops, prefer mean-reversion over momentum |
| **> 28** | Crisis / panic | Minimal positions; momentum signals unreliable; focus on hedges only |

### 8.3 Position Sizing Using India VIX

**Volatility-targeting formula adapted for VIX:**
```python
def vix_adjusted_position_size(capital, risk_pct, entry_price, atr_pct, india_vix, target_vol_pct=15):
    """
    Adjust position size based on India VIX for vol-targeting.
    
    Args:
        capital: Total trading capital (Rs)
        risk_pct: Risk per trade as % of capital (e.g., 0.10 = 10%)
        entry_price: Entry price (Rs)
        atr_pct: ATR as % of price (e.g., 0.02 = 2%)
        india_vix: Current India VIX level
        target_vol_pct: Target portfolio volatility (default 15%)
    
    Returns:
        Number of shares to trade
    """
    # VIX-normalized risk amount
    vol_ratio = india_vix / target_vol_pct
    
    # Adjust risk capital: reduce when VIX is high
    adjusted_risk_capital = capital * risk_pct / vol_ratio
    
    # Risk per share
    risk_per_share = entry_price * atr_pct
    
    # Adjusted position
    shares = int(adjusted_risk_capital / risk_per_share)
    
    return max(shares, 0)
```

### 8.4 VIX as Regime Indicator

**VIX regime rules for NSE momentum system:**

| Regime | VIX Level | ADX Requirement | Volume Surge Threshold | R Target Adjustment |
|--------|-----------|-----------------|------------------------|---------------------|
| BULL | < 17 | > 20 | 1.5x (standard) | 2.0R |
| BULL | 17-22 | > 25 | 1.75x | 1.75R |
| HIGH_VOL | 22-28 | > 30 | 2.0x | 1.5R |
| BEAR | > 28 | < 20 | Any surge filtered | No momentum trades |

**Additional VIX checks:**
- VIX > 25 for 3+ consecutive days: Reduce all momentum positions 50%
- VIX spike (>20% in single day): Exit all positions same day; no new entries
- VIX rising + price falling: Confirm downtrend; momentum shorts may work
- VIX falling + price rising: Confirm uptrend; momentum longs preferred

---

## 9. Sector Rotation Patterns

### 9.1 IT Sector (January-March Pattern)

**Historical rotation pattern:**
- IT stocks (TCS, Infosys, Wipro, HCL) historically outperform Q1 (Jan-Mar)
- **Driver:** Fiscal year-end for US corporates (Jan 1 start) -> IT budgets released -> Indian IT receives orders
- **USD-INR dynamics:** Rupee depreciation in Q1 amplifies IT earnings in INR terms
- **Rotation significance:** Large institutional buying in IT Jan-Mar creates upward momentum; rotation out Apr-May

**Algo implication:** Momentum signals in IT stocks during Jan-Mar have higher conviction. During Apr-May, IT momentum signals deteriorate -- sector rotation check recommended.

### 9.2 Pharma Sector (October-December Pattern)

**Historical rotation pattern:**
- Pharma (Sun Pharma, Dr. Reddy's, Cipla, Lupin) historically outperforms Oct-Dec
- **Driver:** US FDA approvals typically peak in Q4; Indian pharma benefits from cost arbitrage narrative
- **Defensive nature:** Pharma is defensive; outperforms when market breadth is weak
- **Global risk-on:** Pharma underperforms during strong risk-on (when Nifty surges)

**Algo implication:** Pharma momentum signals in Oct-Dec are more reliable. Monitor Nifty breadth -- if market is strong, pharma momentum may lag.

### 9.3 BFSI Sector (Banking, Financials, Insurance)

**Rotation dynamics:**
- BFSI is the largest sector weight in Nifty (~35%); drives index-level moves
- **RBI policy cycle:** Rate-cut cycles benefit banks (NIM expansion); rate-hike cycles hurt
- **PSU banks vs Private banks:** Divergent rotation -- PSU banks rally on government spending; private banks on earnings growth
- **Seasonal:** Banks historically underperform in March (year-end) and outperform in June-September

**BFSI impact on sector rotation:**
- When BFSI rotates in, other sectors rotate out (index-heavy)
- Large BFSI moves can mask broader market breadth deterioration
- **Algo implication:** Sector RS checks must isolate BFSI effect -- stock RS vs Nifty may be dominated by BFSI beta rather than stock-specific momentum

### 9.4 Index-Heavy Names Effect on Sector Rotation

**Nifty's top 10 stocks (~60% of index weight):**
| Stock | Weight (approx.) | Sector |
|-------|-----------------|--------|
| Reliance Industries | 8-9% | Energy/Petrochemicals |
| HDFC Bank | 7-8% | Private Banking |
| ICICI Bank | 5-6% | Private Banking |
| Infosys | 4-5% | IT |
| TCS | 4-5% | IT |
| L&T | 3-4% | Infrastructure |
| Bharti Airtel | 3-4% | Telecom |
| State Bank | 3-4% | PSU Banking |
|ITC | 2-3% | FMCG |
|[zhou]心 Hindustan Unilever | 2-3% | FMCG |

**Rotation detection logic:**
- When top-5 stocks rally, Nifty outperforms but breadth may be weak
- When mid/small cap rally with top-5 flat, true breadth improvement -- better for momentum
- **Implementation:** Add Nifty equal-weight vs price-weighted divergence check to detect rotation quality

### 9.5 Bharat 22 ETF Effect

The **Bharat 22 ETF** (launched 2017, managed by SBI MF) tracks 22 stocks across 6 sectors:
- Large FII/DII flow through this ETF creates correlated buying/selling pressure
- When Bharat 22 sees inflows, PSU banks, energy, and utilities outperform
- **Algo implication:** Monitor Bharat 22 ETF flow as a sector rotation leading indicator. Sudden inflows indicate sector rotation toward value/PSU names.

---

## 10. Historical Anomalies on NSE

### 10.1 Monday Effect

**Data:** NSE historically shows slightly negative Monday returns vs other weekdays.

| Day | Avg Return (Nifty) | Volatility |
|-----|-------------------|------------|
| Monday | -0.05% to -0.10% | Highest |
| Tuesday | +0.05% to +0.10% | Normal |
| Wednesday | +0.08% to +0.12% | Normal |
| Thursday | +0.05% to +0.08% | Normal |
| Friday | +0.03% to +0.06% | Lower |

**Proposed explanations:**
- Weekend news risk priced in on Monday open
- US markets closed Saturday/Sunday; Asian open Monday absorbs Friday US close + weekend news
- Window dressing by funds at month/quarter-end (last trading day of week sometimes manipulated)

**Algo implication:** Monday open (09:15-09:30) tends to be more volatile. Reduce momentum entries on Mondays; wait for 10:00+ confirmation.

### 10.2 Month-End Effect

**Observations:**
- Last 3 trading days of month: DII (domestic institutional) activity surges as they meet SIP targets
- First 3 trading days of month: DII reinvestment creates buying support
- **Index outperformance:** Nifty historically outperforms on last day of month due to index rebalancing flows
- **Small-cap underperformance:** Mid/small caps may underperform last week of month as retail liquidity dries up

**Algo implication:** Month-end (25th-30th) momentum in large-cap stocks is partially institutional flow-driven. Small-cap momentum signals weaker in last week of month.

### 10.3 Diwali / Festival Effect

**Diwali (October-November):**
- Diwali is the most important Indian financial festival for markets
- **Diwali muhurat trading:** Historically held for ~1 hour on Diwali day; considered auspicious
- **Pre-Diwali rally:** Markets historically rally 2-3 weeks before Diwali
- **Post-Diwali:** Returns tend to normalize; no reliable post-Diwali directional edge
- **Financial year:** Diwali marks approximate start of Hindu financial year; psychologically significant for new positions

**Other festivals:**
- Ganesh Chaturthi (September): Mild positive bias in select mid-cap sectors
- Dussehra (October): No consistent directional pattern
- Holi (March): No significant market effect

### 10.4 Earnings Season Effect

**Earnings calendar impact on NSE:**

| Quarter | Reporting Period | Market Behavior |
|---------|-----------------|-----------------|
| Q1 (Jul-Sep) | Aug-Oct | IT sector rally; Q1 US budget effect |
| Q2 (Oct-Dec) | Jan-Feb | BFSI strength; Q3 festive season |
| Q3 (Jan-Mar) | Apr-May | Mid-cap reporting; year-end pressures |
| Q4 (Apr-Jun) | Jul-Aug | Q4 FY results; full year earnings |

**Pre-earnings drift:**
- Stocks with strong Q3/Q4 earnings typically drift 3-5% higher in month before reporting
- **Algo strategy:** Buy 30 days before earnings in momentum stocks with +15% Q-o-Q guidance; close 5 days before earnings (avoid volatility crush from IV collapse)

**Post-earnings drift (PEAD -- Post Earnings Announcement Drift):**
- Nifty stocks show ~2-4% drift over 20 days post earnings beat
- **Implementation:** After earnings beat, wait for reaction day (day 1), then fade the initial reaction if it overextends (mean reversion on day 2-3)

### 10.5 Expiry Week Effect (F&O)

**Monthly options expiry (last Thursday):**
- **Mark-to-market swings:** Large futures positions cause volatile moves on expiry week
- **Pin risk:** At-the-money strikes tend to pin near key round numbers (24,000, 25,000 for Nifty)
- **Monday-Wednesday:** Expiry week historically has higher intraday volatility
- **Wednesday/Thursday:** Largest absolute moves; afternoon sessions 14:00-15:30 can be extreme

**Algo implication during expiry week:**
- Reduce intraday position sizes Wed-Thu
- Avoid short gamma strategies (selling options near expiry)
- Watch for short covering / covering on expiry day 14:30-15:30

### 10.6 Index Rebalancing Effect

**Nifty rebalancing (quarterly):**
- March, June, September, December review months
- **Additions:** Stock typically rallies 3-5% in month leading up to announcement
- **Deletions:** Stock typically falls 3-5% in month leading up to announcement
- **Passive flow:** On rebalancing date, ~Rs5,000-15,000 Cr of passive buying/selling in a single day

**MSCI India rebalancing:**
- Causes extended-hours (post-15:40) moves in stocks added/deleted from MSCI India
- More relevant for large-cap foreign-invested stocks
- **Algo implication:** Monitor MSCI calendar for additional institutional flow signals

---

## Appendix: Quick Reference Tables

### A. NSE Market Hours Summary

| Session | Time (IST) | Notes |
|---------|-----------|-------|
| Pre-open auction | 09:00-09:15 | Order matching; no continuous |
| Regular market | 09:15-15:30 | Continuous trading |
| Closing auction | 15:30-15:40 | Index pricing |
| F&O close | 15:30/15:40 | Options/Futures close |
| Post-close futures | 15:40-17:00 | SGX Nifty leading |

### B. India VIX Regime Table

| VIX Range | Regime | Strategy Adjustment |
|-----------|--------|--------------------|
| < 12 | Low Vol | Aggressive sizing, lower volume threshold |
| 12-17 | Normal | Standard parameters |
| 17-22 | Elevated | Reduce size 20%, raise vol threshold |
| 22-28 | High | Reduce 40-50%, wider stops, prefer MR |
| > 28 | Crisis | Minimal positions, focus on hedges only |

### C. Transaction Cost Quick Calculator

```python
# For Rs1,00,000 single-side intraday trade (Rs2L round trip):
ROUND_TRIP_COST_BP = 6.5  # basis points (approx., flat brokerage Rs20)
# For small trades (Rs10K single-side): ~15 bp
# For large trades (Rs10L single-side): ~6.5 bp
```

### D. Sector Rotation Calendar

| Period | Sector | Driver |
|--------|--------|--------|
| Jan-Mar | IT | US fiscal year start, USD/INR |
| Apr-May | IT rotation out | Earnings season shift |
| Jun-Sep | PSU Banks, Infra | Budget expectations, monsoon |
| Oct-Dec | Pharma | US FDA approvals, defensive bid |
| Nov-Dec | BFSI (Private) | Q3 results, year-end |

---

*Research compiled: May 2026*
*Target system: python-engine / trading-sentinel (NSE India)*
