# Penny Stock Expansion — Design Spec

**Date:** 2026-06-21
**Branch base:** `evolve/smart-strategies` @ `35c3233` (current prod SHA)
**Working branch (planned):** `feat/expansion` (already created off `origin/evolve/smart-strategies`)
**Author:** Hermes + Uru collaborative
**Status:** Draft — awaiting Uru approval

---

## 1. Motivation and Goals

### 1.1 Why expand into penny stocks

The current Trading Sentinel universe is the Nifty 500. We want to add a parallel **penny-stock subsystem** that:

- Operates a **separate bankroll pool** (Rs 2,500) with **no contamination** of the Nifty 500 logic
- Runs **auto-execution without human approval** for penny positions (a hard new requirement)
- Uses **fundamentally different micro-structure rules** (volatility, liquidity, circuit bands)
- Adopts **evidence-backed entry strategies** tuned for low-priced names

Total bankroll after this work: **Rs 7,500** (Rs 5,000 Nifty + Rs 2,500 penny).

### 1.2 Goals

1. Ship a parallel penny subsystem on a **separate code path** (new Python modules), not a branch in `engine.py`.
2. **Two complementary strategies** running side-by-side, sharing infra but not logic:
   - **Primary (CNC, multi-day):** Larry Connors RSI(2) mean-reversion
   - **Secondary (MIS, intraday):** Volume-price breakout
3. **Hard guardrails** tuned for penny volatility (daily kill-switch, broker-level SL-M, circuit-band filter, position caps).
4. **Paper-trade mode first**, live-trade opt-in, full instrumentation (signal log + outcome correlator).
5. **Strict isolation** — zero changes to Nifty 500 code path.

### 1.3 Non-goals (explicit)

- NOT changing Nifty 500 strategies, regime, or risk parameters
- NOT changing the existing Nifty bankroll (Rs 5,000 stays)
- NOT enabling short-selling on penny (Kite intraday shorting allowed but adds complexity; defer)
- NOT automating F&O penny (none exist in this price range anyway)
- NOT auto-compounding penny wins into Nifty pool (each pool is independent)

---

## 2. Universe Definition

### 2.1 Price band (with buffer)

**Inclusion:** Rs 1 <= LTP <= Rs 55 (10% buffer above the Rs 1-50 "penny" convention per Uru's confirmation).

**Rationale for Rs 1 floor:** Sub-Rs 1 stocks on NSE are often delisted, in T2T (trade-to-trade) segment, or illiquid beyond algorithmic reach. Rs 1 floor avoids these.

**Rationale for Rs 55 ceiling:** Uru specified 10% buffer above Rs 50. Above Rs 55 the stock is no longer "penny" by user convention.

### 2.2 Universe size and refresh

- **Target size:** Top 100 NSE EQ-series penny stocks (the "Top 100 performing" was the original ask — see §2.4 for ranking)
- **Source:** NSE EQ-series instruments list (already loaded via `kite_client.refresh_instrument_cache`)
- **Refresh cadence:** Daily at 08:00 IST — fetch instruments, filter by price band using **previous-day close** as proxy (intraday price filter applied at scan time)
- **Static fallback:** `data/penny100.json` shipped with the system for offline / first-run mode (mirrors the `nifty500.json` pattern)

### 2.3 Eligibility filters (pre-scan)

A stock passes the eligibility gate if ALL are true:
- LTP in Rs 1-55 band (using previous close at universe-refresh time)
- Series = EQ (NSE equity, not BE / BZ / IL illiquid segments)
- 20-day median traded value >= Rs 5 lakh (liquidity floor — penny stocks below this trade fewer than 50 lots/day)
- NOT in T2T (trade-to-trade) segment — these require 100% upfront margin, broker may block
- NOT in ASM (Additional Surveillance Measure) — illiquid and high-risk
- NOT in GSM (Graded Surveillance Measure) — heavily restricted
- Promoter holding: strictly greater than 25% AND strictly less than 75% (avoid micro-caps where 1 trade moves price; also avoid widely-held names where promoter stake has been diluted below the meaningful "skin in the game" threshold)
- Price-to-Book ratio <= 2.0 (loose asset-backing floor; Book Value >= Market Value / 2; per Uru's aggressive-path call 2026-06-21, P/B <= 1.0 was too restrictive and would slash the universe by ~60%, killing signal volume. P/B <= 2.0 keeps the asset-backed floor — pure story stocks trading at 5-10x book still get filtered — without starving the strategy)

### 2.4 Ranking — "Top 100 performing"

Since the user asked for "top 100 performing", we define "performing" as a composite score:
- **40% weight:** 20-day average daily return (positive momentum)
- **30% weight:** 20-day median traded value (liquidity — picks the actually-tradeable names)
- **20% weight:** distance from 52-week low (momentum proxy, but cap so we don't pick only runners)
- **10% weight:** 20-day realized volatility (we WANT some vol — too quiet = no opportunity)

Ranking computed daily at universe refresh. Top 100 ship in `penny100.json`.

---

## 3. Architecture — Strict Module Isolation

### 3.1 New modules (do not touch existing)

| Module | Purpose | Lines (est.) |
|---|---|---|
| `python-engine/penny_universe.py` | Load + filter + rank penny universe. Mirrors `universe.py` API but for penny. | ~150 |
| `python-engine/penny_regime.py` | Per-stock volatility rank + India VIX proxy (Nifty vs EMA50) + breadth fallback. Independent of `regime.py`. | ~120 |
| `python-engine/penny_engine_connors.py` | RSI(2) mean-reversion evaluator. Returns `PennySignal` (CNC). | ~180 |
| `python-engine/penny_engine_breakout.py` | Volume breakout evaluator. Returns `PennySignal` (MIS). | ~160 |
| `python-engine/penny_risk.py` | Per-trade sizing, daily loss tracker, kill-switch logic. Independent of `risk_engine.py`. | ~140 |
| `python-engine/penny_scanner.py` | Orchestrates the 30-sec scan cycle, calls both engines, applies portfolio caps. | ~200 |
| `python-engine/penny_models.py` | `PennySignal` pydantic model, `PennyRegime` enum, `PennyLeg` Literal["CNC","MIS"]. | ~100 |
| `python-engine/penny_signal_log.py` | Append-only signal log (CSV + SQLite) for penny. Independent of `signal_log.py`. | ~150 |

**Total new code:** ~1,200 LOC + ~400 LOC of tests = ~1,600 LOC.

### 3.2 Reused (not modified)

| Module | How reused |
|---|---|
| `kite_client.py` | Quote fetching (poll every 30s), historical data (daily for Connors 200-MA), instrument cache refresh |
| `position_tracker.py` | EXTENDED via a new `source="PENNY"` tag — uses same ledger but separate pool |
| `performance.py` | EXTENDED to compute penny pool P&L alongside Nifty pool (read-only extension) |
| `main.py` | EXTENDED to schedule `run_penny_scanner` in parallel with existing screeners |
| `portfolio.py` | NOT used — penny has its own portfolio logic in `penny_risk.py` |
| `regime.py` | NOT used — penny has its own regime |
| `risk_engine.py` | NOT used — penny has its own risk |

### 3.3 Isolation contract

A **hard architectural rule**: `penny_*` modules MUST NOT import from `engine.py`, `regime.py`, `risk_engine.py`, `portfolio.py`, `evaluate_signal`, `evaluate_momentum_signal`, or any Nifty-side module. The reverse is also true — no Nifty module imports `penny_*`.

Allowed shared imports: `kite_client`, `models` (base classes only, no Nifty-specific signals), `config` (settings only), `position_tracker` (extended ledger), `performance` (extended P&L), `analytics` (extended correlator).

A new linter rule (test) enforces this: `tests/test_penny_isolation.py` walks the AST of every `penny_*.py` file and asserts no forbidden imports.

### 3.4 Bankroll split

| Pool | Amount | Source of truth |
|---|---|---|
| Nifty 500 (existing) | Rs 5,000 | `RiskEngine.bankroll` |
| Penny paper-trade (initial) | Rs 500 | `PennyRiskEngine.paper_bankroll` |
| Penny live-trade (initial) | Rs 2,000 | `PennyRiskEngine.live_bankroll` |
| Reserve (untouched) | Rs 0 | (no reserve — both pools are at max) |
| **Total** | **Rs 7,500** | |

Live bankroll is opt-in via `PENNY_LIVE_TRADING=false` in `.env` (default OFF — paper-trade first).

---

## 4. Strategy 1 — Connors RSI(2) Mean-Reversion (CNC, Primary)

### 4.1 Original Larry Connors rules

1. **Trend filter:** Close > 200-day SMA (long-term uptrend required)
2. **Mean-reversion trigger:** RSI(2) < 5 (extreme oversold on 2-period RSI)
3. **Entry:** Buy on next bar open
4. **Exit:** RSI(2) > 65 (mean reversion complete) OR 3 days, whichever first

### 4.2 Our adaptation for penny stocks

- **Trend filter:** Close > 200-day SMA **AND** Close > 50-day SMA (extra trend confirm, since penny trends are noisier)
- **Trigger:** RSI(2) < 10 (relaxed from 5 — penny RSI(2) hits < 5 rarely, < 10 is the realistic extreme)
- **Confirmation:** RSI(2) rising for 2 consecutive bars (we're not catching a falling knife)
- **Volume sanity:** Today's volume >= 0.5x 20-day median (NOT dead)
- **Entry:** Limit order at LTP + 0.5% (don't chase on penny — fills are bad otherwise)
- **Stop loss:** -3% from entry, hard SL-M order at broker
- **Target 1:** +3% from entry, exit 50% (book profit, leave rest)
- **Target 2 OR trail OR time-stop (3-way exit, whichever fires first):**
  - **T2:** +6% from entry, exit remaining 50%
  - **Trailing stop (NEW, post-T1):** After T1 fires, move SL-M on remaining shares to breakeven + 0.5%. Then trail up at `max(breakeven + 0.5%, highest_close_since_T1 - 2.0 * ATR_1min)`. ATR is computed on 1-min bars since T1 (not pre-entry bars) — this adapts to the current volatility regime of the actual run.
  - **Time-stop:** 3 trading days from entry (per Connors original)
- **Daily check:** 09:30 IST scan only — one signal per stock per day

### 4.3 Edge cases specific to penny

- **Stock hits lower circuit before our entry:** cancel order, log `circuit_lower_blocked`
- **Stock hits upper circuit while we're holding:** DO NOT sell into circuit (you'll get trapped at -5% next day). Hold until circuit releases or stop triggers.
- **Volume dries up:** if 2 consecutive days volume < 20% of 20-day median, force-exit at market
- **Promoter news / corporate action:** manual kill-switch in `.env` (`PENNY_DISABLE_TICKERS=XYZ,ABC`)

### 4.4 Why this fits CNC

CNC (delivery) has zero leverage, no auto-square, and allows multi-day holds. RSI(2) < 10 setups on penny names often resolve over 2-5 days. MIS would force us to close at 15:15 IST, defeating the strategy.

### 4.5 Trailing stop on remaining shares — why this is the missing piece

The original 3-way exit (T1/T2/time-stop) is rigid and assumes penny stocks behave like the textbook Connors setup. They don't. Penny names that trigger RSI(2) < 10 often:

- Spike +5% intraday then mean-revert (T2 fires, we book conservative profit)
- Spike +5% intraday, mean-revert to flat, then gap up +25% next day on news (T2 fired too early, we miss the runner)
- Spike +10% intraday, hold +8% by close, then gap +20% next morning (T2 fired at +6%, we left 14% on the table)

The trailing stop solves all three: after T1 at +3%, the remaining 50% rides with a 2x ATR_1min trail. If the spike reverses, we exit at breakeven + 0.5% — small profit booked. If the spike continues, we ride the trail up. The asymmetry: small loss avoided (tight stop) but big winners still captured (loose trail once in motion).

**Why 2x ATR_1min and not a fixed %:** penny volatility is non-stationary. A 3% fixed trail is too tight on a 20% band day (gets stopped on noise) and too loose on a 5% band day (gives back too much). 1-min ATR adapts to the actual recent volatility, which is the right denominator.

**Why "since T1" not "since entry":** pre-T1 volatility was the setup volatility (low, mean-reverting). Post-T1 volatility is the breakout volatility (high, trending). Using post-T1 ATR matches the regime of the actual run we're trying to capture.

**Risk profile:** the trailing stop CANNOT exit below breakeven + 0.5%. Worst case on the remaining 50% = small profit. Best case = trail captures the full runner. The first 50% (T1) is always booked at +3% regardless.

---

## 5. Strategy 2 — Volume Breakout (MIS, Secondary)

### 5.1 Original rules

Volume breakout is the most-cited penny strategy. The signal:
1. **Today's cumulative volume** > 3x the 20-day average by 10:30 IST
2. **Price** breaks above the day's opening high (after 10:30 IST, not the first 15 min)
3. **RSI(14)** < 70 (not already overbought on the breakout)
4. **Entry:** Buy on first pullback to breakout level (limit order), not market order

### 5.2 Our adaptation

- **Volume surge threshold:** 3x 20-day median volume (industry standard)
- **Time gate:** scan starts 10:30 IST, ends 14:30 IST (avoid morning noise, avoid EOD thin book)
- **Breakout confirm:** price must close (not just touch) above day's high by at least 0.3% on a 1-min bar
- **Entry:** limit at LTP + 0.3% once breakout confirmed (penny fills are bad on market orders)
- **Stop loss:** low of the breakout candle (1-min) — mirrors Nifty momentum pattern
- **Target:** +2.0R (R = risk per share)
- **Time stop:** 15:00 IST hard exit (15 min before MIS auto-square)
- **Daily limit:** max 3 MIS positions (in addition to CNC cap)

### 5.3 Smart-EOD rule at 14:30 IST (NEW — addresses the "EOD price falls" pain point)

At 14:30 IST, every open MIS position is evaluated against a 3-way decision rule. This is the explicit answer to "many times by EOD the price falls":

| Position state at 14:30 IST | Action |
|---|---|
| **In profit AND within 0.5R of target** | Exit at limit NOW. Book the gain. Don't wait for the EOD reversal. |
| **In profit AND > 0.5R from target** | Hold to 15:00 IST time-stop. Let it run; trail not needed at this scale. |
| **In loss AND has been in loss for >30 min** | Exit at market NOW. Cut the bleed before EOD adds to it. |
| **In loss AND recently entered (<30 min ago)** | Hold to 15:00 IST time-stop. Give the setup room to work; don't panic-cut a fresh entry. |

This is the standard "take what the market gives you at 14:30" rule used in published penny-scalp playbooks (TradeThatSwing, Warrior Trading, most prop-shop intraday systems). It directly addresses the EOD-fall pattern by booking profits earlier when they're available.

**Configurable thresholds (in `.env`):**
- `PENNY_MIS_SMART_EOD_TIME=870` (14:30 IST in minutes from midnight)
- `PENNY_MIS_SMART_EOD_WITHIN_R=0.5` (the "close to target" threshold)
- `PENNY_MIS_SMART_EOD_LOSS_MINUTES=30` (the "give it room" window)

### 5.4 Why intraday only

Penny moves that hit 3x volume by 10:30 IST usually resolve in 30-90 minutes. Holding overnight MIS = leverage tax + STT. CNC is for the slow mean-reversion leg (Connors); MIS is for the spike scalp.

---

## 6. Regime Engine (Penny-Specific)

### 6.1 Why a new regime

The Nifty regime engine uses realized volatility on Nifty index. Penny stocks have idiosyncratic volatility that doesn't correlate with Nifty. A penny stock in a "calm" regime can still crash 20% on a single news item. We need per-stock awareness.

### 6.2 Three inputs

1. **Per-stock volatility rank (40% weight):** Today's 5-min realized vol vs the stock's own 60-day distribution. Rank 0-1, where 1 = highest vol in 60 days.
2. **India VIX proxy (40% weight):** Nifty 50 close vs Nifty 50 EMA50 ratio (same proxy we use for Nifty regime since Zerodha doesn't expose VIX). High Nifty close-vs-EMA50 = elevated vol.
3. **Breadth fallback (20% weight):** Same placeholder 0.5 as Nifty regime (until we wire breadth for penny universe too — out of scope for v1).

### 6.3 Three regimes

| Regime | Conditions | Behavior |
|---|---|---|
| **PR1_CALM** | vol_rank < 0.7 AND vix_proxy < 0.7 | Full size (5% risk), normal stops, normal targets |
| **PR2_ELEVATED** | 0.7 <= vol_rank < 0.9 OR 0.7 <= vix_proxy < 0.9 | Half size (2.5% risk), tighter stops (2.0x ATR instead of 3.0x), same targets |
| **PR3_HOT** | vol_rank >= 0.9 OR vix_proxy >= 0.9 | NO NEW ENTRIES. Close existing on next 1-min bar if price moves against by 1%. |

Computed at 09:20 IST, cached for the day, refreshed at 13:00 IST (in case of intraday vol explosion).

### 6.4 Independent of Nifty regime

A penny PR3 does NOT affect Nifty regime. They are completely separate. The existing Nifty regime stays as-is.

---

## 7. Risk Engine (Penny-Specific)

### 7.1 Per-trade sizing

```
risk_per_trade = penny_live_bankroll * RISK_PCT_BY_REGIME
                = Rs 2,000 * 0.05 (PR1) = Rs 100 per trade
shares = floor(risk_per_trade / (entry - stop_loss))
cap_per_stock = min(Rs 500, 0.30 * penny_live_bankroll)  # hard cap
max_shares = floor(cap_per_stock / entry)
shares = min(shares, max_shares)
```

### 7.2 Mandatory broker-level stop-loss

Every penny order MUST be placed as **SL-M (Stop-Loss Market)** with the trigger at the engine-computed stop. This is a non-negotiable rule. If the order placement fails (broker rejects, no SL-M support, etc.), the signal is REJECTED — the system does NOT fall back to in-engine stops only.

For CNC (Connors): SL-M stays until exit or time-stop, whichever first.
For MIS (Breakout): SL-M plus a 15:00 IST time-exit limit order.

### 7.3 Daily kill-switch

Track realized P&L for the penny pool per day. If daily loss >= 20% of live penny bankroll (= Rs 400), stop all new penny entries for the day. Existing positions keep their SL-M orders (no manual intervention needed).

### 7.4 NSE circuit-band filter

Before placing any entry, check if the stock is at or near its daily price band:
- 5% band stocks: skip if within 0.5% of upper/lower band
- 10% band stocks: skip if within 1.0% of band
- 20% band stocks: skip if within 2.0% of band

Per Uru's choice: "only skip if at circuit AND >3% from day high". We implement this as: skip if `(band_pct - distance_to_band) < 0.5%` AND `(day_high - current_price) / day_high > 0.03`. The 0.5% and 3% thresholds are configurable in `.env`.

### 7.5 Per-stock cap

Rs 500 per single penny stock (per Uru's directive). Hard cap. No exceptions.

### 7.6 Position caps

| Cap | Value |
|---|---|
| Max concurrent penny positions (CNC + MIS) | 5 |
| Max concurrent CNC (Connors) | 2 |
| Max concurrent MIS (Breakout) | 3 |
| Max same-sector | 2 |
| Max total deployed capital | 80% of penny live bankroll |

---

## 8. Execution and Order Management

### 8.1 Auto-execution (no human approval)

Per Uru's directive, penny trades execute WITHOUT human approval. This is a deviation from the existing Nifty system (which sends Telegram alerts and waits). For penny:

- Signal fires → `penny_scanner` validates risk + circuit filter
- Order placed via `KiteClient.place_order()` with SL-M variant
- Telegram notification sent for record-keeping (not for approval)
- Position tracked in extended `position_tracker`

If the Telegram is down or order fails, the signal is **NOT retried automatically** (no double-orders). It logs and moves on. Next scan can re-fire.

### 8.2 Order types

| Leg | Order | Variant | Notes |
|---|---|---|---|
| Connors CNC entry | LIMIT | day | LTP + 0.5%, valid for 1 day, auto-cancel at 15:00 |
| Connors CNC entry SL | SL-M | day | Trigger = stop_loss |
| Connors CNC T1 partial | LIMIT | day | Target +0%, IOC, exit 50% |
| Connors CNC T2 | LIMIT | day | Target +6%, exit remaining |
| Connors CNC time-stop | MARKET | day | At 15:00 on day 3, force-exit |
| Breakout MIS entry | LIMIT | day | LTP + 0.3% |
| Breakout MIS entry SL | SL-M | day | Trigger = breakout candle low |
| Breakout MIS exit | LIMIT | day | Target +2R, exit 100% |
| Breakout MIS time-stop | MARKET | day | At 15:00, exit 100% |

### 8.3 Paper-trade mode

When `PENNY_LIVE_TRADING=false` (default):
- All signals fire normally
- "Orders" are simulated: PnL tracked, position ledger updated, but NO real orders to Kite
- Same signal log, same analytics, same alerts
- Operators can review paper P&L before flipping live

When `PENNY_LIVE_TRADING=true`:
- Real orders via Kite
- All other behavior identical

---

## 9. Data Flow and Timing

### 9.1 Daily schedule (IST)

| Time | Action |
|---|---|
| 08:00 | Refresh penny universe (`penny_universe.refresh()`), compute rankings, persist to `penny100.json` |
| 09:00 | Pre-market: pre-fetch daily candles for top 100 (needed for Connors 200-MA) |
| 09:20 | Compute penny regime (cached for day, refreshed at 13:00) |
| 09:30 | Connors scan #1 (CNC entry signals) — once per day |
| 09:30-15:00 | Breakout scan every 30 seconds (MIS entry signals) |
| 10:00, 11:00, 12:00, 13:00, 14:00 | Hourly penny report (see §9.4) |
| 13:00 | Re-compute penny regime (intraday vol check) |
| 15:00 | Breakout MIS time-stop (force-exit any open MIS positions) |
| 15:15 | All open MIS auto-squared by broker (Kite rule, not us) |
| 15:30 | EOD post-market: update paper/live P&L, sync position ledger, send Telegram daily summary |
| 16:00 | Analytics correlator runs on the day's signal log |

### 9.4 Hourly Penny Report

A concise per-hour status report fires at every `:00` IST from 10:00 through 14:00 (5 reports/day, skipping the 09:00 pre-market slot when no scans have run yet). Each report covers the trailing 60 minutes of penny subsystem activity and is delivered as a structured log line + optional webhook (Telegram/Slack) message.

**Mandatory heartbeat rule:** the report fires every hour regardless of activity. If nothing happened, the body is the literal text `"No action in Penny this hour."` This proves the subsystem is alive — a missing hourly report is itself an alert.

**Report contents (when there IS action):**

- Regime snapshot (one line: PR1_CALM / PR2_ELEVATED / PR3_HOT)
- Entries filled in the hour: ticker, leg (CNC/MIS), qty, fill price, regime, entry reason
- Exits in the hour: ticker, leg, qty, exit price, exit reason (T1 / T2 / trail / time-stop / 14:30-EOD / SL-M-triggered / manual-kill)
- Pending signals rejected: count + top 3 reject reasons
- Kill-switch events (if any)
- Circuit-block count (if any)
- Open penny positions: count + total deployed capital + unrealised P&L snapshot
- Bankroll snapshot: paper and live

**Report contents (when there is NO action):**

- One line: `No action in Penny this hour.`
- Optionally followed by `(regime: PR1_CALM, open: 2/5, deployed: Rs 980/2000)`

**Format:** short markdown block, ≤ 15 lines, no RSI/ATR noise. Telegram-friendly (under 1000 chars).

**Delivery:**
- Always logged at INFO level (`penny_hourly_report` event key)
- Optionally POSTed to a webhook URL if `PENNY_HOURLY_REPORT_WEBHOOK` is set in `.env`
- Webhook failure does NOT block the next hour's report

**Open question for Uru:** should the 10:00 report fire (first hour of scanning, often quiet) or skip until 11:00? Per default we ship 10:00–14:00 (5 reports). User can disable 10:00 via `PENNY_HOURLY_REPORT_START_HOUR=11` if the empty report is annoying.

### 9.2 Per-scan flow (Breakout MIS, every 30s)

```
1. Fetch LTP for all 100 penny tickers via batched Kite quote API
2. For each ticker, maintain 1-min bar (rolling buffer in-memory)
3. Run volume-breakout evaluator on completed 1-min bars
4. Apply risk filters: max positions, circuit, kill-switch, regime
5. If signal passes: place limit order + SL-M
6. Log to signal log (CSV + SQLite)
7. Send Telegram notification (record-keeping)
```

Latency budget: 30s scan must complete in < 25s (5s buffer for next cycle).

### 9.3 Per-day flow (Connors CNC, once at 09:30)

```
1. For each ticker in top-100 penny, fetch daily OHLCV (cached, ~60-day window)
2. Compute 200-SMA, 50-SMA, RSI(2)
3. Run Connors evaluator
4. Apply risk filters
5. If signal: place limit + SL-M
6. Log + Telegram
```

---

## 10. Analytics and Self-Improvement

### 10.1 Signal log

Append-only CSV at `/data/penny_signals.csv` with columns:
- scan_time_ist, ticker, leg (CNC/MIS), regime, signal_id
- entry_price, stop_loss, target_1, target_2, r_target, shares
- indicators (RSI(2), RSI(14), vol_ratio, breakout_level)
- accept/reject, reject_reason

Schema mirrors the Nifty signal log so the existing analytics correlator can be extended.

### 10.2 Outcome correlator

Reuse `analytics.outcome_correlator` with new `source="PENNY"` filter. Same reject-reason taxonomy (extended with `penny_circuit_blocked`, `penny_paper_only`, etc.).

### 10.3 Self-improvement suggestions

`analytics.strategy_suggestions` extended to surface penny-specific suggestions:
- "Connors win-rate dropped from 78% to 62% in last 10 trades — consider tightening RSI(2) trigger from 10 to 7"
- "Breakout hit rate is 38% — below target 50%. Consider increasing volume surge threshold from 3x to 4x"

Suggestions never auto-applied. Operator flips the `.env` flag.

---

## 11. Testing Strategy

### 11.1 Unit tests (TDD)

Each new module ships with tests:
- `tests/test_penny_universe.py` — filter logic, ranking, eligibility gates
- `tests/test_penny_regime.py` — vol rank, VIX proxy, three-regime mapping
- `tests/test_penny_engine_connors.py` — RSI(2) trigger, trend filter, exit rules
- `tests/test_penny_engine_breakout.py` — volume surge, breakout confirm, time gate
- `tests/test_penny_risk.py` — sizing, kill-switch, circuit filter, position caps
- `tests/test_penny_scanner.py` — orchestration, 30-sec cadence, paper mode
- `tests/test_penny_signal_log.py` — append, dedup, schema
- `tests/test_penny_isolation.py` — AST walk asserting no Nifty imports

### 11.2 Integration tests

- `tests/test_penny_integration.py` — full signal-to-paper-position flow
- `tests/test_penny_kill_switch.py` — simulate 3 losses, assert day halts
- `tests/test_penny_circuit_filter.py` — simulate stock at circuit, assert skip

### 11.3 Coverage target

`pytest --cov=python_engine.penny_*` >= 85% (matching existing modules).

---

## 12. Configuration Surface

### 12.1 New `PENNY_*` settings in `config.py`

```python
# Universe
PENNY_PRICE_MIN:               float = 1.0
PENNY_PRICE_MAX:               float = 55.0
PENNY_UNIVERSE_SIZE:           int   = 100
PENNY_MIN_20D_TV:              float = 500_000   # Rs 5 lakh liquidity floor
PENNY_MIN_PROMOTER_HOLD:       float = 0.25      # strictly > 25% promoter (skin in game floor)
PENNY_MAX_PROMOTER_HOLD:       float = 0.75      # strictly < 75% promoter (avoid micro-cap concentration)
PENNY_MAX_PB_RATIO:            float = 2.0       # Price-to-Book <= 2.0 (loose asset-backing floor)
PENNY_REFRESH_HOUR:            int   = 8

# Connors strategy
PENNY_CONNORS_RSI2_BUY:        float = 10.0
PENNY_CONNORS_RSI2_SELL:       float = 65.0
PENNY_CONNORS_T1_PCT:          float = 0.03
PENNY_CONNORS_T2_PCT:          float = 0.06
PENNY_CONNORS_STOP_PCT:        float = 0.03
PENNY_CONNORS_MAX_HOLD_DAYS:   int   = 3

# Breakout strategy
PENNY_BREAKOUT_VOL_MULT:       float = 3.0
PENNY_BREAKOUT_TARGET_R:       float = 2.0
PENNY_BREAKOUT_TIME_START:     int   = 10*60 + 30  # 10:30 IST in minutes
PENNY_BREAKOUT_TIME_END:       int   = 14*60 + 30  # 14:30 IST in minutes
PENNY_BREAKOUT_TIME_EXIT:      int   = 15*60       # 15:00 IST
PENNY_CONNORS_TRAIL_ATR_MULT:   float = 2.0        # 2x ATR_1min trailing stop after T1
PENNY_MIS_SMART_EOD_TIME:       int   = 14*60 + 30 # 14:30 IST in minutes (EOD check)
PENNY_MIS_SMART_EOD_WITHIN_R:   float = 0.5        # Within 0.5R of target = take profit at 14:30
PENNY_MIS_SMART_EOD_LOSS_MIN:   int   = 30         # Loss for >30 min = cut at 14:30

# Risk
PENNY_LIVE_BANKROLL:           float = 2000.0
PENNY_PAPER_BANKROLL:          float = 500.0
PENNY_RISK_PCT_PR1:            float = 0.05
PENNY_RISK_PCT_PR2:            float = 0.025
PENNY_RISK_PCT_PR3:            float = 0.0
PENNY_DAILY_KILL_SWITCH_PCT:   float = 0.20
PENNY_PER_STOCK_CAP:           float = 500.0
PENNY_MAX_POSITIONS_TOTAL:     int   = 5
PENNY_MAX_POSITIONS_CNC:       int   = 2
PENNY_MAX_POSITIONS_MIS:       int   = 3
PENNY_CIRCUIT_SKIP_DISTANCE:   float = 0.005  # 0.5%
PENNY_CIRCUIT_FROM_HIGH_PCT:   float = 0.03   # 3%

# Cadence
PENNY_SCAN_INTERVAL_SEC:       int   = 30
PENNY_LIVE_TRADING:            bool  = False  # default OFF — paper-trade first
PENNY_DISABLE_TICKERS:         str   = ""     # comma-separated manual kill-switch
PENNY_HOURLY_REPORT_START_HOUR: int  = 10     # first hourly report hour IST (10 = 10:00)
PENNY_HOURLY_REPORT_END_HOUR:   int  = 14     # last hourly report hour IST (14 = 14:00)
PENNY_HOURLY_REPORT_WEBHOOK:   str   = ""     # optional webhook URL for delivery
```

### 12.2 `.env` defaults (operator opts in)

```
PENNY_LIVE_TRADING=false
PENNY_DISABLE_TICKERS=
```

---

## 13. Rollout Plan (post-spec)

This is OUT OF SCOPE for this design doc — the writing-plans skill will produce a TDD plan. But the high-level rollout phases for context:

1. **Phase 1 — Spec + Plan** (this doc + writing-plans skill)
2. **Phase 2 — Code + Tests + Paper-trade** (all 8 modules + 8 test files, paper mode default)
3. **Phase 3 — 2 weeks of paper trading** (collect signal log + paper P&L data)
4. **Phase 4 — Backtest correlator** (run analytics on paper data, surface suggestions)
5. **Phase 5 — Live-trade opt-in** (Uru reviews paper P&L, flips `PENNY_LIVE_TRADING=true`)
6. **Phase 6 — Iterate** (regime/stop/sizing adjustments based on real data)

This design does NOT commit to a launch date. Phase 5 requires Uru's explicit approval.

---

## 14. Open Questions and Risks

### 14.1 Risks

- **Penny liquidity is fragile:** even Rs 5L 20-day median can disappear overnight. Universe refresh must run daily.
- **NSE circuit changes mid-day:** the circuit band can change (rare, but happens during volatility). System should detect this and halt.
- **Promoter manipulation:** even with the 75% filter, manipulators can be at 70%. We rely on volume + RSI for protection.
- **Rs 500/stock cap is tight:** at Rs 5 stock with Rs 0.50 risk, max shares = 1000 (worth Rs 5,000). Cap will fire. This is intentional — caps prevents concentration.
- **Paper-trade validation:** 2 weeks of paper data may not be enough to validate live. Plan for 4 weeks.
- **Two-machine pipeline still applies:** dev on ~/trading-sentinel, prod on ~/Desktop/trading-sentinel. Penny code follows the same flow.

### 14.2 Resolved by brainstorming

- Universe definition: Rs 1-55 with buffer
- Risk appetite: aggressive (Rs 100/trade, 5% risk, max 5 positions)
- Product type: hybrid (CNC + MIS)
- Scan cadence: 30s polling
- Regime: own module (per-stock vol rank + VIX proxy)
- Strategy combo: Connors RSI(2) CNC + Volume Breakout MIS
- Guardrails: smart hybrid (SL-M mandatory, 20% daily loss, circuit filter, max 5 positions)
- Workflow: spec first, plan second, code third (this design enforces that)

### 14.3 Open questions for Uru (post-spec)

1. Should the Telegram daily summary for penny go to the same chat as Nifty, or a separate channel?
2. Should we cap penny max daily loss as % of live bankroll (20%) or absolute Rs (Rs 400)? Currently % — easier to scale with bankroll changes.
3. ~~Should the Connors CNC RSI(2) threshold be 5 (per Larry Connors original) or 10 (per our penny adaptation)?~~ **RESOLVED 2026-06-21: keep at 10 for v1.**

---

## 15. What this design does NOT include

- No F&O penny (none exist)
- No BSE penny (NSE-only for v1)
- No short-selling on penny (long-only)
- No auto-compounding between pools
- No modifications to Nifty 500 code
- No modifications to existing regime, risk, portfolio modules
- No live launch approval (Phase 5 needs separate go-ahead)

---

## 16. References

- Larry Connors RSI(2) — https://www.quantifiedstrategies.com/rsi-2-strategy/
- RSI(2) vs RSI(14) backtest — https://lirannh.medium.com/why-rsi-2-beats-rsi-14-in-every-backtest-ive-ever-run-71de36be15fb
- Indian large-cap RSI(2) backtest — sahilsawhney01 (Facebook video, Jan 2026)
- Volume breakout on Indian markets — https://www.kotakneo.com/stockshaala/introduction-to-technical-analysis/breakout-trading-strategies/
- 1,872-breakout volume study — https://www.youtube.com/watch?v=FQva6CQjYB0
- Penny stock risks (TradersPost) — https://blog.traderspost.io/article/penny-stock-trading-strategies
- FIA automated trading risk controls — https://www.fia.org/sites/default/files/2024-07/FIA_WP_AUTOMATED%20TRADING%20RISK%20CONTROLS_FINAL_0.pdf
- NSE circuit breakers — https://www.nseindia.com/products-services/equity-market-circuit-breakers
- Existing Nifty signal log / analytics — `python-engine/analytics.py` and `python-engine/signal_log.py`
- Existing safe-improvements skill — `~/.hermes/skills/trading-sentinel/trading-strategy-safe-improvements/`
- Lifecycle mismatch audit — `~/.hermes/skills/trading-sentinel/momentum-vs-trailing-exits-audit/`

---

**END OF DESIGN SPEC**

Status: **Draft, awaiting Uru review and approval.**
After approval, Uru will explicitly request the writing-plans skill to produce the TDD implementation plan.
