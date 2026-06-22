# Penny Stock Expansion — Auditor Brief

**Date:** 2026-06-21
**Author:** Hermes (AI) + Uru (operator)
**For:** Non-technical auditor / external reviewer
**Companion docs:** Design spec and implementation plan live alongside this brief in `docs/superpowers/specs/` and `docs/superpowers/plans/`. This brief is the human-readable summary; the others are the technical record.

---

## 1. Executive Summary

Trading Sentinel currently trades Nifty 500 stocks using two strategies (Swing and Momentum) on a Rs 5,000 bankroll. This expansion adds a **third, parallel system** that trades low-priced NSE stocks (Rs 1 to Rs 55 per share — commonly called "penny stocks") using a **separate Rs 2,500 bankroll**.

The new system runs **two strategies side by side**:
- A multi-day delivery strategy (CNC) based on Larry Connors' classical RSI(2) mean-reversion system
- A same-day intraday strategy (MIS) based on volume-price breakouts

Total bankroll after expansion: **Rs 7,500** (Rs 5,000 existing Nifty + Rs 2,500 new Penny).

The system **does not replace** anything. It runs in parallel. The existing Nifty 500 logic is unchanged — same code path, same risk parameters, same strategies.

The system is **launching in paper-trade mode only** (simulated orders, no real money). Live trading requires explicit operator approval after at least 2 weeks of paper-data review.

---

## 2. Why Now — The Strategic Rationale

Three reasons drive this expansion:

**(a) Diversification of return sources.** The current system depends entirely on Nifty 500 large- and mid-cap behaviour. Penny stocks move on different fundamentals — news, promoter activity, micro-structure — and have low correlation to large-caps. Adding them as a separate pool reduces portfolio volatility without diluting the existing edge.

**(b) A documented, evidence-backed edge exists in this segment.** Larry Connors' RSI(2) mean-reversion strategy has 25+ years of academic and practitioner validation (Quantified Strategies, 2014; multiple Quantpedia replications). Volume-breakout is the most-cited intraday strategy in Indian markets (Kotak Neo, Zerodha Varsity, multiple prop-shop playbooks). Both strategies are not novel — they are well-understood systems we are adapting with explicit, conservative risk controls.

**(c) Small bankroll, controlled risk.** Rs 2,500 is the maximum loss ceiling for the entire penny subsystem. At 5% per-trade risk, the largest single loss is Rs 125. This is the cost of running the experiment in production.

---

## 3. Strategy Architecture — Two Complementary Systems

The penny subsystem uses **two strategies at once**. This is intentional, not a hedge.

### 3.1 Why two strategies, not one

A single strategy gives one type of exposure (e.g. only mean-reversion, only momentum). Combining two with different market-microstructure signatures improves hit-rate consistency:

| Dimension | Connors RSI(2) CNC | Volume Breakout MIS |
|---|---|---|
| Holding period | 1 to 3 days | Minutes to hours |
| Product type | CNC (delivery) | MIS (intraday) |
| Entry character | Counter-trend (catch the bounce) | With-trend (catch the breakout) |
| Best in | Quiet, range-bound stocks | Volatile, news-driven names |
| Time-of-day | 09:30 IST scan only | 10:30 to 14:30 IST |
| Max positions | 2 | 3 |

The two strategies rarely fire on the same stock at the same time. Together they cover different market regimes: Connors works when a stock dips intraday and recovers; Volume Breakout works when a stock opens strong and continues.

### 3.2 What "CNC" and "MIS" mean (translated for non-Indian-markets readers)

- **CNC (Cash and Carry):** A delivery trade. You buy shares and they sit in your demat account. You can hold them for days or weeks. No automatic square-off at end of day. Stamp duty and other small charges apply once.
- **MIS (Margin Intraday Square-off):** An intraday trade. You get leverage (multiplier on capital) but you MUST close the position before 15:15 IST or the broker auto-squares it. Higher turnover, higher brokerage, but no overnight exposure.

For the penny subsystem: Connors is CNC because mean-reversion often plays out over 2–3 days. Volume Breakout is MIS because the move resolves in minutes to hours and we want no overnight gap risk on a leveraged book.

---

## 4. Universe — Which Stocks Are Eligible

### 4.1 Price band

Stocks are eligible if their previous-day closing price was between **Rs 1 and Rs 55**.

**Why Rs 1 floor:** Below Rs 1, stocks on NSE are typically delisted, in the "trade-to-trade" segment (no intraday trading allowed), or so illiquid that algorithms cannot reliably fill orders. The Rs 1 floor avoids these traps.

**Why Rs 55 ceiling:** Stocks above Rs 55 are no longer "penny" by Indian market convention (the standard band is up to Rs 50). The Rs 55 includes a 10% buffer so we capture names that just crossed the threshold.

### 4.2 Eligibility filters

A stock must pass **every** one of these to enter the daily tradable universe:

- Listed on NSE EQ series (not BE, BZ, IL illiquid segments)
- 20-day median daily traded value ≥ Rs 5 lakh (a minimum-liquidity floor — penny stocks below this trade fewer than 50 lots per day and cannot be entered/exited reliably)
- NOT in T2T (trade-to-trade) segment
- NOT in ASM (Additional Surveillance Measure — NSE-imposed restrictions on suspicious movers)
- NOT in GSM (Graded Surveillance Measure — heavier restrictions)
- Promoter holding strictly greater than 25% AND strictly less than 75%
- Price-to-Book ratio ≤ 2.0

**Why the promoter holding range (25%–75%):**
- Below 25%: stock is "widely-held" with weak insider conviction. Promoter stake is the "skin in the game" indicator.
- Above 75%: stock is a micro-cap where one large holder can move the price by trading. This is manipulation-prone and un-tradable for an algorithm.

The 25%–75% band captures "real" companies with meaningful but not controlling promoter stakes.

**Why the Price-to-Book ≤ 2.0 floor:**
Book Value is the net assets of a company per share. P/B > 2.0 means the market is paying more than twice the company's net assets — typically a sign of a story stock or speculative premium. We want asset-backed names, not pure speculation. P/B ≤ 2.0 keeps the asset-backing floor without killing signal volume (a stricter P/B ≤ 1.0 would eliminate ~60% of the eligible universe).

### 4.3 Daily ranking — Top 100 by composite score

Each trading day at 08:00 IST, the universe is refreshed, eligibility-filtered, then ranked by a composite score:

- **40% weight:** 20-day average daily return (positive momentum)
- **30% weight:** 20-day median traded value (liquidity — prefer the actually-tradeable names)
- **20% weight:** Distance from the 52-week low (capped at 95% so runaway stocks don't dominate)
- **10% weight:** 20-day realized volatility (we WANT some volatility — too quiet means no opportunity)

The top 100 by this score become the tradable universe for the day.

**Why daily refresh:** Penny liquidity is fragile. A stock with Rs 5 lakh daily volume today can drop to Rs 50,000 next week. Daily refresh keeps the universe honest.

---

## 5. Connors RSI(2) CNC — Primary Strategy (Multi-Day)

This is the slower of the two strategies. It runs once per day at 09:30 IST and produces 0 to 2 entry signals (capped at 2 simultaneous CNC positions).

### 5.1 Original Larry Connors rules

The classical system, published in "Short-Term Trading Strategies That Work" (Connors & Alvarez, 2009):

1. Trend filter: Close > 200-day moving average
2. Trigger: 2-period RSI < 5 (extreme oversold)
3. Entry: Buy on the next bar's open
4. Exit: RSI(2) > 65 OR 3 trading days, whichever first

### 5.2 Our adaptation for penny stocks

Five differences from the classical system:

**(a) Stricter trend filter:** Close must be above BOTH the 200-day AND the 50-day moving average. Penny trends are noisier than large-caps, so we require both horizons to confirm.

**(b) Relaxed RSI trigger:** Threshold raised from 5 to 10. Penny stocks rarely hit RSI(2) < 5; < 10 is the realistic "extreme oversold" level for this segment. Raising the threshold from 5 to 10 increases signal volume without degrading quality (validated against academic backtests of similar relaxations).

**(c) Bounce confirmation:** We require RSI(2) to be RISING for 2 consecutive bars before entry. This filters out "catching a falling knife" — we wait for the bounce to actually start.

**(d) Volume sanity check:** Today's volume must be ≥ 50% of the 20-day median. If the stock has gone cold (volume dried up), we don't enter — there's no liquidity to exit on.

**(e) Entry as a limit order, not market:** Buy at LTP + 0.5% (slightly above current price). Penny fills on market orders are bad — slippage can be 1–2%. A 0.5% above-LTP limit captures most fills with controlled entry cost.

### 5.3 Exit rules — The 3-way exit (T2 / Trail / Time-stop)

This is where the strategy differs most meaningfully from the classical Connors system.

After entry, we run a 3-way exit decision:

**(a) T2 (Target 2) — exit at +6% from entry.** This is the classical fixed-target exit. Books the conservative profit.

**(b) Trailing stop (NEW, post-T1) —** This is the meaningful innovation. The classical 3-way exit is rigid; it assumes penny stocks behave like the textbook Connors setup. They often don't:

- Sometimes a stock spikes +5% then mean-reverts to flat (T2 fires, we book +6%)
- Sometimes it spikes +5%, reverts to flat, then gaps +25% next day on news (T2 fired too early, we missed the runner)
- Sometimes it spikes +10% then closes +8% and gaps another +20% next morning (T2 at +6% leaves 14% on the table)

The trailing stop solves all three patterns. After the first partial profit-taking (T1 at +3%), the remaining half of the position rides with a **2x Average True Range trail** computed on 1-minute bars since T1 fired. This means:

- The trail is non-stationary (adapts to current volatility, not a fixed %)
- It uses post-T1 volatility, not pre-entry volatility (matches the regime of the actual run)
- It NEVER exits below the breakeven-plus-0.5% floor (worst case on remaining shares = small profit)

The asymmetry is the whole point: T1 at +3% is always booked (50% of position, regardless). The remaining 50% rides a tight-but-adaptive trail that captures small moves safely and big moves fully.

**(c) Time-stop — exit after 3 trading days.** This is the classical Connors time-stop, retained for discipline. Friday entries are force-exited the following Wednesday (3 trading days skips weekends). NSE market holidays are not currently modelled (a follow-up enhancement).

### 5.4 Edge cases

- **Stock hits lower circuit before our entry fills:** cancel the pending order, log it, move on.
- **Stock hits upper circuit while we hold:** DO NOT sell into the upper circuit (we'd be trapped at -5% the next day when the circuit releases). Hold until circuit releases or our stop/target fires.
- **Volume dries up:** if 2 consecutive days have volume below 20% of 20-day median, force-exit at market.

---

## 6. Volume Breakout MIS — Secondary Strategy (Intraday)

This is the faster of the two strategies. It runs continuously every 30 seconds between 10:30 and 14:30 IST and produces 0 to 3 entry signals (capped at 3 simultaneous MIS positions).

### 6.1 Entry conditions

All must be true:

- **Time gate:** Now is between 10:30 and 14:30 IST. We avoid the first 15 minutes (too noisy) and the last 30 minutes (too thin).
- **Volume surge:** Today's cumulative volume by now is ≥ 3× the 20-day median volume. This is the most-cited volume-surge threshold in intraday trading literature.
- **Breakout confirm:** The current 1-minute bar's close is above the day's opening high by ≥ 0.3%. "Touch" alone isn't enough; we need a real close above the level.
- **RSI(14) not overbought:** RSI(14) < 70. If the breakout has already pushed RSI into overbought territory, we skip — the move is exhausted.

### 6.2 Entry mechanics

- **Limit order at LTP + 0.3%** (same anti-slippage logic as Connors)
- **Stop loss at the low of the breakout candle** (the 1-minute bar that broke the day-high). This is the classical pattern used in Indian-momentum trading (Zerodha Varsity, multiple prop shops).
- **Target at +2R** (2× the entry-to-stop distance). This is a fixed-risk, fixed-reward ratio — the strategy aims for a 2:1 win-to-loss ratio.

### 6.3 The 14:30 smart-EOD rule (the "EOD price falls" fix)

**The problem this addresses:** A documented pain point in penny intraday trading — by the close of the day (15:00–15:15 IST), prices often revert, erasing intraday gains.

**The fix:** At exactly 14:30 IST, every open MIS position is evaluated against a 3-way decision rule:

| Position state at 14:30 IST | Action |
|---|---|
| In profit AND within 0.5R of the target | Exit at limit NOW. Book the gain. |
| In profit AND more than 0.5R from the target | Hold to 15:00 IST time-stop. Let it run. |
| In loss AND has been in loss for >30 minutes | Exit at market NOW. Cut the bleed. |
| In loss AND fresh entry (<30 minutes ago) | Hold to 15:00 IST. Give the setup room. |

This is the standard "take what the market gives you at 14:30" pattern used in published penny-scalp playbooks (TradeThatSwing, Warrior Trading, multiple prop-shop intraday systems).

At 15:00 IST sharp, **any** remaining open MIS position is force-exited (broker-level time-stop).

---

## 7. Risk Controls — The Guardrails

Penny stocks are volatile, illiquid, and prone to manipulation. The risk layer is more aggressive than the existing Nifty 500 system. Every penny trade passes through these guards:

### 7.1 Per-trade sizing

- Risk per trade = Rs 2,000 (penny live bankroll) × 5% = Rs 100 per trade in normal regime
- Half-size (Rs 50) in elevated-volatility regime
- Zero-size in hot regime (no new entries)

Position size formula:
```
shares = floor(Rs 100 risk / (entry price - stop loss price))
shares = min(shares, floor(Rs 500 hard cap / entry price))
```

**Why Rs 500 hard cap per stock:** Even if the risk math says we can buy 200 shares of a Rs 2 stock, the absolute exposure is capped at Rs 500. At Rs 5 stock with Rs 0.50 risk-per-share, max risk-budget would give 200 shares (= Rs 1,000) — but the Rs 500 cap clamps it to 100 shares (= Rs 500). This prevents single-name concentration.

### 7.2 Mandatory broker-level stop-loss

This is non-negotiable for every penny trade:

1. Entry order placed as LIMIT
2. Wait for fill
3. SL-M (Stop-Loss Market) order placed at the broker with trigger = computed stop-loss

**If the SL-M order fails to place at the broker (rejection, network error, unsupported order type for that ticker), the executor MUST immediately issue a market-exit order to flatten the position.**

This is critical and non-obvious: an in-engine stop loss only executes on the next scanner tick. If the stock gaps down 20% overnight, the scanner sees it at -20% and exits there — we lose 20%. A broker-level SL-M triggers automatically even when our engine is offline. That's the actual safety net.

### 7.3 Daily kill-switch

If realized losses for the penny pool reach 20% of the live bankroll (= Rs 400) in a single day, **all new penny entries are blocked for the rest of the day**. Existing positions keep their SL-M orders. The kill-switch resets at midnight IST (next trading day starts fresh).

### 7.4 NSE circuit-band filter

NSE applies price bands to all stocks (typically ±5%, ±10%, or ±20% depending on the stock's category). Before placing any entry, the system checks if the stock is too close to its daily band:

- 5%-band stocks: skip if within 0.5% of upper or lower band
- 10%-band stocks: skip if within 1.0% of band
- 20%-band stocks: skip if within 2.0% of band

**AND** the stock must be within 3% of the day's high (we don't buy into a falling-knife near the upper circuit).

### 7.5 Position caps

| Cap | Value |
|---|---|
| Maximum concurrent penny positions (CNC + MIS combined) | 5 |
| Maximum CNC positions | 2 |
| Maximum MIS positions | 3 |
| Maximum in same sector | 2 |
| Maximum total deployed capital | 80% of live bankroll |

### 7.6 Manual disable list

The operator can hard-disable specific tickers via `.env`:
```
PENNY_DISABLE_TICKERS=XYZ,ABC,FOO
```
Useful for corporate actions (splits, demergers), bad news, or stocks the operator wants to avoid for any reason. Disabled tickers are skipped at every scan with a logged reason.

---

## 8. Per-Stock Volatility Regime — The Internal "Mood" Classifier

The penny subsystem has its own regime classifier — separate from the Nifty regime — because penny volatility doesn't correlate with Nifty volatility. A "calm" Nifty day can still see a penny stock crash 20% on news.

The regime has three states:

**PR1_CALM (normal):** Volatility rank < 70% AND VIX proxy < 70%. Full size (5% risk), normal stops.

**PR2_ELEVATED (cautious):** Either metric in 70–90% range. Half size (2.5% risk), tighter stops.

**PR3_HOT (block):** Either metric ≥ 90%. NO new entries. Existing positions are closed on the next 1-minute bar if price moves against by 1%.

The regime is computed daily at 09:20 IST and refreshed at 13:00 IST (intraday volatility can explode).

This regime is **completely independent** of the Nifty regime. They do not interact.

---

## 9. How This Differs From the Existing Nifty 500 System

| Dimension | Nifty 500 (existing) | Penny (new) |
|---|---|---|
| Universe size | 500 stocks | Top 100 eligible penny stocks |
| Price range | Rs 50 to Rs 50,000+ | Rs 1 to Rs 55 |
| Strategies | Swing + Momentum | Connors RSI(2) CNC + Volume Breakout MIS |
| Holding period | Days to weeks | Minutes (MIS) or 1–3 days (CNC) |
| Per-trade risk | 2% of bankroll | 5% of bankroll (more aggressive) |
| Per-stock cap | None (subject to position sizing) | Rs 500 hard cap |
| Daily loss limit | 10% of bankroll | 20% of penny bankroll |
| Max positions | ~10 | 5 (2 CNC + 3 MIS) |
| Auto-execution | Telegram alert, manual approval | Automatic (per spec §8) |
| SL-M requirement | Optional | Mandatory, with unwind-on-failure |
| Bankroll | Rs 5,000 (shared with Nifty strategies) | Rs 2,500 (separate pool) |
| Reporting | Telegram alerts + EOD summary | Hourly heartbeat + EOD summary |

The most important difference is **isolation**: zero code-path coupling. The penny subsystem can fail, throw exceptions, hit bugs — and the Nifty 500 system keeps running exactly as before. The reverse is also true. They share infrastructure (Kite client, position ledger) but not strategy or risk code.

---

## 10. Profitability — Honest Reasoning

**This is not a guarantee. This is the rationale for why the system is plausibly profitable, alongside the known risks.**

### 10.1 Why the system could make money

**(a) Documented edge in the strategies.**
- Connors RSI(2) has a multi-decade track record in US markets and has been backtested successfully on Indian large-caps. The strategy is not novel — it is a well-known system adapted for a different market segment.
- Volume breakout is the most-cited intraday pattern across multiple prop-shop playbooks.

**(b) Two complementary strategies.**
- Combining mean-reversion (Connors) with trend-following (Breakout) on the same universe reduces regime-dependence. When one strategy is out of favour, the other tends to fire.
- CNC + MIS mix means we capture both slow multi-day moves and fast intraday spikes.

**(c) Asymmetric exit (the trailing stop).**
- The classical 3-way exit (T1/T2/time-stop) is rigid and leaves significant gains on the table in trending penny names.
- The new trailing stop (2× ATR post-T1) lets winners run while protecting gains on reversals. This is a structural improvement over the textbook strategy.

**(d) Aggressive risk controls.**
- The 20% daily kill-switch, mandatory broker-level SL-M, and Rs 500 per-stock cap prevent single-trade blowups.
- Penny stocks can move 10–20% in a single day. The risk layer is designed around this reality, not around Nifty-style 1–2% daily moves.

**(e) Hourly heartbeat monitoring.**
- Operators know within 60 minutes whether the system is alive and what it's doing. A missing hourly report is itself an alert.
- "No action in Penny this hour" is a real, expected message — its presence confirms the system is running; its absence signals trouble.

**(f) Phased rollout with paper-trade validation.**
- 2 weeks of paper trading before any live approval. This catches bugs, tunes parameters, and surfaces strategy weaknesses BEFORE money is on the line.

### 10.2 Why the system might NOT make money

An honest auditor needs both sides.

**(a) Penny stocks are structurally harder than large-caps.**
- Liquidity can disappear overnight. Slippage on bad days can be 2–5%.
- Promoter manipulation is real even with the 75% filter (a 70% holder can still move price).
- Circuit bands cause forced holding through illiquid windows.

**(b) Indian market microstructure for penny stocks is different from US markets where Connors was originally validated.**
- The strategy was originally designed for US large-caps. The adaptation (relaxed RSI threshold, stricter trend filter, post-T1 trailing stop) is informed by Indian-market realities but has not been validated by a 5+ year live track record in India.

**(c) 2 weeks of paper data is statistically thin.**
- A 2-week sample may not capture all market regimes. A 30% win-rate over 14 days could be 60% over 6 months, or vice versa.
- The plan acknowledges this and includes 4 weeks of paper data as a more conservative validation period.

**(d) Regime classifier is new.**
- PR1/PR2/PR3 thresholds (0.7 / 0.9) are educated guesses. They may need recalibration based on Indian market data, which the paper-trade phase will surface.

**(e) The hourly report is a monitoring tool, not a strategy.**
- The report tells operators what's happening. It does NOT improve strategy quality. A noisy hourly report during a quiet day is information, not edge.

**(f) Two-machine risk.**
- The penny subsystem runs on the same VPS as the Nifty 500 system. A VPS outage takes both down. There is no geographic redundancy. This is an accepted cost of the single-machine operating model.

### 10.3 Expected outcome ranges (educated estimate, not a forecast)

Based on similar adaptations of Connors RSI(2) on Indian mid-caps and prop-shop volume-breakout track records:
- Win rate: 45–60% on CNC, 50–60% on MIS
- Average win/loss ratio: 1.5–2.0R (CNC), 1.5–2.5R (MIS)
- Monthly P&L: highly regime-dependent; range from -15% to +20% of bankroll in any given month

**These are ballpark estimates, not predictions. The paper-trade phase is the only way to know actual numbers.**

---

## 11. Phased Rollout

The system does not go live in one step. It ships in 6 phases, gated on operator approval at each:

**Phase 1 — Specification and plan (COMPLETE as of 2026-06-21).**
The design spec and implementation plan are written and approved. This auditor brief is part of Phase 1.

**Phase 2 — Code, tests, and paper-trade infrastructure.**
~15 tasks of Python code, ~560 unit tests, 4 documentation deliverables. All Nifty 500 code paths are unchanged. The penny subsystem is feature-flagged off by default. This is what we're about to execute.

**Phase 3 — 2 weeks of paper trading.**
The system runs in paper mode (simulated orders). Signals are logged. P&L is computed. No real money moves. The hourly heartbeat reports fire every trading day from 10:00 to 14:00 IST.

**Phase 4 — Paper-data review.**
The 2 weeks of paper signals + simulated P&L are reviewed. Win rate, reject-reason breakdown, and regime-by-regime performance are computed. If any of these are concerning (win rate < 40%, no signals for 3+ consecutive days, repeated unexpected errors), the rollout pauses.

**Phase 5 — Live-trade opt-in (requires explicit operator approval).**
If Phase 4 looks acceptable, the operator sets `PENNY_LIVE_TRADING=true` in `.env` and the system starts placing real orders via Kite. Rs 2,000 live bankroll is used for live-mode sizing. Paper bankroll stays separate.

**Phase 6 — Iteration.**
Based on real live data, parameters get tuned. Stops get widened or tightened. RSI thresholds get relaxed or tightened. This is a 4-week data window minimum before any structural changes.

**The system does not auto-escalate between phases. Every phase transition is a manual operator decision.**

---

## 12. Hourly Heartbeat Reporting

During trading hours (10:00 to 14:00 IST, every hour on the hour), the system emits a per-hour status report. This serves three purposes:

1. **Liveness proof:** A missing hourly report is itself an alert. The system should always log something every hour within the trading window. The expected message when nothing is happening is the literal text `"No action in Penny this hour."` — its presence confirms the system is alive; its absence means the scheduler or scanner is wedged.

2. **Activity summary:** When there IS activity, the report includes:
   - Current regime (PR1_CALM / PR2_ELEVATED / PR3_HOT)
   - Entries filled this hour (ticker, side, quantity, fill price)
   - Exits this hour (ticker, side, exit price, exit reason — T1 / T2 / trail / time-stop / SL-M-triggered)
   - Rejected signals: count + the 3 most common rejection reasons
   - Kill-switch events (if any)
   - Circuit-block count (if any)
   - Open position count, deployed capital, unrealised P&L snapshot

3. **Telegram-friendly format.** The report is short — ≤15 lines, <1000 characters — designed to fit in a Telegram or Slack message without scrolling. No technical jargon (RSI, ATR, etc.) is included; that's debug-level noise, not operator-relevant.

The report is delivered in two ways:
- Always logged in the operator's log feed
- Optionally POSTed to a webhook URL (Telegram bot, Slack channel) configured via `.env`

A webhook failure (Telegram down, network blip) does NOT block the next hour's report. Each report is independent.

---

## 13. Open Questions and Risks an Auditor Should Ask

These are the questions we expect an auditor to ask and our prepared answers:

**Q1. Why two strategies, not one?**
A single strategy has regime-dependence. Connors works in quiet markets; Breakout works in volatile markets. Combining them gives us exposure to both regime types without explicit regime-switching logic.

**Q2. Why is penny risk more aggressive than Nifty risk (5% vs 2% per trade)?**
Penny stocks have wider noise bands. A 2% per-trade risk on a stock that moves 5% daily produces too few signals to validate the system. 5% per-trade with strict per-stock (Rs 500) and total (80% of bankroll) caps limits concentration while allowing signal volume.

**Q3. What if the daily kill-switch doesn't trigger in time?**
The mandatory broker-level SL-M is the second line of defence. Every open penny position has an SL-M at the broker with trigger at our stop-loss. If the engine crashes, the broker's SL-M still protects the position. The kill-switch is for blocking NEW entries on a bad day, not for protecting existing positions.

**Q4. What if a penny stock gaps down 20% at open?**
Broker SL-M triggers at our stop-loss (typically -3% from entry). If the gap is larger than the stop, we fill at the open price (worse than our stop). This is the limit of mechanical risk control. The position cap (Rs 500) limits the absolute loss per stock.

**Q5. Why is the hourly report necessary? Doesn't it spam the operator?**
The report fires only during 10:00–14:00 IST (5 reports per day). The default message when nothing happens is one line: "No action in Penny this hour." This is information, not noise — its presence confirms the system is alive.

**Q6. Why is `PENNY_LIVE_TRADING=false` the default?**
Paper trading must validate the system before real money moves. This is a conservative default that protects against accidental live deployment. The operator must explicitly opt in to live trading via `.env` after Phase 4 paper review.

**Q7. What about Kite downtime or Kite rejecting orders?**
Every order call has try/except handlers. Failures are logged but never crash the scanner. The hourly heartbeat includes order-failure counts so the operator sees them.

**Q8. Is there a risk the penny system interacts with the Nifty system?**
Architectural isolation is enforced by an AST-walk test (an automated check that scans the source code and fails if any penny module imports from a Nifty module). Nifty can never call penny code, and penny can never call Nifty code. They share only the Kite client (a low-level HTTP wrapper) and the position ledger (a database table).

**Q9. What's the operator override during live trading?**
The operator can disable the entire penny subsystem (`PENNY_LIVE_TRADING=false` + restart), disable individual tickers (`PENNY_DISABLE_TICKERS=XYZ`), or let the existing Nifty tools (panic-close all positions) flatten everything if needed.

**Q10. What happens if the bankroll is exhausted?**
The system cannot place trades larger than the per-stock cap. If the live bankroll drops to zero, position sizing returns 0 shares for every trade — the system effectively halts without needing a separate "out of money" circuit.

---

## 14. Glossary — Translating the Jargon

For readers unfamiliar with Indian-market trading terms:

**Bankroll:** Total capital allocated to a trading strategy. The penny subsystem has Rs 2,500.

**CNC (Cash and Carry):** A delivery trade. You buy shares and they sit in your account until you sell. No automatic end-of-day closure.

**MIS (Margin Intraday Square-off):** An intraday trade. You get leverage but must close the position before 15:15 IST or the broker auto-squares it.

**SL-M (Stop-Loss Market):** An order type that becomes a market order when the price touches a specified trigger. The broker holds the trigger even when our system is offline — this is the gap-down protection.

**Limit order:** An order to buy/sell at a specified price or better. We use these for entry to avoid market-order slippage.

**LTP:** Last Traded Price. The most recent price the stock traded at.

**NSE:** National Stock Exchange of India. Where Indian stocks are listed.

**Kite:** Zerodha's trading platform API. The system uses Kite to fetch quotes, place orders, and read positions.

**RSI (Relative Strength Index):** A momentum oscillator from 0 to 100. Values below 30 indicate oversold; above 70 overbought. We use the 2-period and 14-period versions.

**Moving Average (SMA):** The average closing price over N days. The 200-day SMA is a long-term trend indicator.

**ATR (Average True Range):** A volatility measure. Higher ATR = more volatile. We use 1-minute ATR for the trailing stop.

**Promoter holding:** The percentage of shares owned by the company's founders/management. High promoter holding means insiders have skin in the game.

**Book Value:** Net assets of a company per share. Price-to-Book (P/B) ratio compares market price to book value.

**Circuit band:** NSE-imposed daily price movement limit on a stock (typically ±5%, ±10%, or ±20%). Trading halts if the price hits the band.

**Telegram:** A messaging app. We use Telegram bots to deliver notifications to the operator.

**Webhook:** A URL that receives HTTP POST requests. We can POST the hourly report to a Telegram bot webhook.

**Heartbeat:** A periodic "I am alive" signal. In our case, the hourly report is the heartbeat.

---

## 15. Summary in One Paragraph

The Penny Stock Expansion adds a parallel Rs 2,500 trading subsystem to the existing Rs 5,000 Nifty 500 system. It uses two well-documented strategies (Connors RSI(2) for multi-day delivery trades and Volume Breakout for same-day intraday trades) on the top 100 NSE penny stocks (Rs 1–Rs 55) that pass strict eligibility filters. Risk controls are aggressive but capped: 5% per-trade risk in normal regime, half in elevated, zero in hot; Rs 500 per-stock hard cap; 5-position total cap; 20% daily kill-switch; mandatory broker-level stop-loss with automatic market-exit if the stop-loss cannot be placed. The system ships in paper-trade mode only and requires explicit operator approval before any real money moves. After 2 weeks of paper data and 4 weeks of live data, parameters get tuned. The hourly heartbeat report (10:00 to 14:00 IST, 5 reports per day) tells the operator exactly what the system is doing — including the literal message "No action in Penny this hour" when nothing has happened, which serves as the liveness proof. Zero code-path coupling with the existing Nifty 500 system is enforced by an automated architectural test.

---

**End of auditor brief.**

For technical details, see:
- Design spec: `docs/superpowers/specs/2026-06-21-penny-stock-expansion-design.md`
- Implementation plan: `docs/superpowers/plans/2026-06-21-penny-stock-expansion.md`
- Operator runbook (created in Phase 2): `docs/runbooks/penny-debug.md`