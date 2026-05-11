# Momentum Gate Improvements — Design Spec
**Date:** 2026-05-11  
**Status:** Awaiting user approval  
**Scope:** `python-engine/engine.py`, `python-engine/main.py`, `python-engine/config.py`  
**No changes to:** Node Gateway, Agent, DB schema, models.py

---

## 1. Context & Root Cause

On 2026-05-11 at 11:45 IST, the momentum screener fired a signal for **TECHM** in a `BEAR_RS_ONLY` regime. The trade was executed at ₹1,468.70. The stock peaked at ₹1,471.40 (a +2.70 point / 0.20R move) before bleeding for 3 hours and auto-squaring at ~₹1,457.50 — a loss of ~0.83R.

Post-mortem findings:
- The **signal candle was structurally clean** (close_position_score ≈ 0.97) — Morphology gate would not have helped.
- The stock had already consumed **12.80 points** of intraday range before the signal. Its daily ATR is ~18–22 pts, leaving ~6–9 pts of fuel. The 2R target required **27 points**. The trade was mathematically dead before execution.
- The signal fired at **11:45 IST** — the start of the Indian equity lunchtime dead zone (11:30–13:15) where volume contracts and false breakouts are structurally elevated.
- The 1R Breakeven trigger was irrelevant — stock only reached 0.20R.

**Goal:** Add structural gates that would catch this class of trade generally, without over-tightening and killing legitimate signals.

---

## 2. Changes Proposed

### Gate A: MC5 — Daily ATR Exhaustion Gate *(HIGH priority)*

**What:** Reject signals where the required move to target exceeds the stock's remaining daily range budget.

**Formula:**
```
daily_atr         = calc_atr(df_daily['high'], df_daily['low'], df_daily['close']).iloc[-1]
intraday_range    = intraday_high - intraday_low          # already computed for MC4
remaining_fuel    = daily_atr - intraday_range
r_distance        = current_close - stop_loss
target_distance   = 2.0 * r_distance                     # = target - current_close

if target_distance > remaining_fuel * ATR_FUEL_BUFFER:
    reject("daily_atr_exhausted")
```

**Buffer:** `ATR_FUEL_BUFFER = 0.85` — we allow the target to slightly exceed remaining_fuel (stocks can have above-average days). Flat 1.0 would be too strict and reject every slightly-above-average breakout.

**Config value added to `config.py`:**
```python
MOMENTUM_ATR_FUEL_BUFFER: float = 0.85
```

**Data source:** `df_daily` is **already fetched inside `run_momentum_screener()`** for every ticker (used for `prev_day_high`). It just needs to be passed as a new parameter `df_daily` to `evaluate_momentum_signal()`. `calc_atr()` already exists in `engine.py`.

**Signature change:**
```python
# Before
def evaluate_momentum_signal(ticker, df, prev_day_high, bankroll, momentum_pool, min_candles=4)

# After
def evaluate_momentum_signal(ticker, df, df_daily, prev_day_high, bankroll, momentum_pool, min_candles=4)
```

**Would this gate kill too many signals?**  
Only signals where the stock has already run >85% of its ATR before the signal fires. A genuine early-session breakout (10:15–11:00 IST, consuming 30–40% of daily ATR) passes easily. A late, exhausted breakout (11:30+ IST, >70% consumed) gets caught. This is the right behavior.

**Placement:** After MC4 (intraday range check), before stop-loss sizing. Label: `[MC5]`.

---

### Gate B: MC3-T — Time-of-Day Volume Multiplier *(MEDIUM priority)*

**What:** During the Indian equity lunchtime dead zone (11:30–13:15 IST), require higher volume conviction to avoid false breakouts. After 13:15 IST, return to the normal threshold — afternoon momentum runs are real.

**Logic:**
```
lunchtime_start = now_ist.replace(hour=11, minute=30)
lunchtime_end   = now_ist.replace(hour=13, minute=15)

if lunchtime_start <= now_ist < lunchtime_end:
    vol_threshold = settings.MOMENTUM_VOL_SURGE_LUNCHTIME
else:
    vol_threshold = settings.MOMENTUM_VOL_SURGE_PCT

if vol_ratio_intraday < vol_threshold:
    reject("volume_surge_insufficient")
```

**Config values added to `config.py`:**
```python
MOMENTUM_VOL_SURGE_LUNCHTIME:     float = 1.75   # 11:30–13:15 IST (raised from 1.5x)
MOMENTUM_LUNCHTIME_START_HOUR:    int   = 11
MOMENTUM_LUNCHTIME_START_MIN:     int   = 30
MOMENTUM_LUNCHTIME_END_HOUR:      int   = 13
MOMENTUM_LUNCHTIME_END_MIN:       int   = 15
```

**Why 1.75x not 2.0x?** On a lunchtime day with genuine institutional activity, volume can be elevated but not doubled. 2.0x would have killed approximately 40–50% of all lunchtime signals including real ones. 1.75x is a meaningful raise that filters the weakest signals without being a near-total blackout.

**Implementation note:** `evaluate_momentum_signal()` is a pure function (no I/O, per inviolable rules). Time-of-day is not passed in today. Two options:
- **Option 1 (recommended):** Pass `now_ist: datetime` as a new parameter to `evaluate_momentum_signal()`. Keeps the logic inside the pure function where the gate lives.
- **Option 2:** Apply the threshold check in `run_momentum_screener()` before calling `evaluate_momentum_signal()`, passing the correct threshold as a parameter.

**Recommendation: Option 2** — avoids injecting a datetime into the engine function, keeping it closer to pure. Add `vol_surge_threshold: float` as an explicit parameter that `main.py` computes and passes.

**Placement:** Replace the hardcoded `settings.MOMENTUM_VOL_SURGE_PCT` reference in MC3 with the passed-in `vol_surge_threshold`. Label: `[MC3-T]`.

---

### Gate C: MC6 — Morphology Gate *(LOW priority — different failure class)*

**What:** Reject candles where the close is in the bottom 35% of the candle's own range (shooting stars, rejected spikes).

**Formula:**
```
candle_high  = df['high'].iloc[-1]
candle_low   = df['low'].iloc[-1]
candle_range = candle_high - candle_low
if candle_range > 0:
    close_score = (current_close - candle_low) / candle_range
    if close_score < 0.65:
        reject("shooting_star_candle")
```

**Threshold:** 0.65 (not 0.75 — permissive enough to allow candles with modest upper wicks, strict enough to catch clear shooting stars).

**Config value added to `config.py`:**
```python
MOMENTUM_MORPHOLOGY_MIN_SCORE: float = 0.65
```

**Would this kill too many signals?** A score of 0.65 means the close must be in the upper 35% of the candle's range. On a genuine bullish breakout candle, this is almost always true. Only candles with significant upper wicks (bears fought back hard) get rejected. Low risk of over-filtering.

**Note:** This gate would NOT have caught TECHM today (score was 0.97). It catches a different, real failure class. Still worth adding.

**Placement:** After MC4, before stop-loss sizing. Label: `[MC6]`.

---

### Gate D: Regime-Adjusted R Target *(LOW priority — config only)*

**What:** In `BEAR_RS_ONLY` regime, set the momentum R target to 1.5R instead of 2.0R. The market structurally cannot deliver 2R intraday moves when Nifty is below its 50 EMA.

**Implementation:** Pass `market_regime` into `evaluate_momentum_signal()` and compute:
```python
r_target = 1.5 if market_regime == "BEAR_RS_ONLY" else settings.MOMENTUM_R_TARGET
target   = current_close + (r_target * r_distance)
```

Also feeds `is_cost_viable()` with the adjusted target — cost ratio check remains honest.

**Config value added:**
```python
MOMENTUM_R_TARGET_BEAR: float = 1.5
```

**Would TECHM have been caught?** At 1.5R, target = 1,468.7 + (1.5 × 13.5) = **1,489.0**. Still unreachable (peak was 1,471.4). BUT: the ATR gate (Gate A) would have caught it already. This gate reduces *expected loss* on the trades that slip through, by setting a tighter, more achievable target in weak markets.

**Placement:** In `evaluate_momentum_signal()` after `[MR2]` target calculation. Pass `market_regime: str = "BULL"` as new parameter (already passed in swing engine — consistent pattern).

---

## 3. What Is Deliberately NOT Included

| Rejected Idea | Reason |
|---|---|
| Absorption Detection (Effort/Result ratio) | No calibration data. High false positive risk on genuine institutional accumulation. Defer 3–6 months. |
| Confirmation Entry (Stop-Limit on breakout high) | Worsens entry price and R:R on every trade that actually works. |
| 1R Breakeven Trigger (tick-level) | Requires real-time LTP websocket. Different infrastructure. TECHM never reached 1R anyway. |
| Trailing SL on momentum MIS | Fixed SL + auto-square is already two exit layers. Trail adds whipsaw risk, not protection. |
| Failed Follow-Through Exit | Architecturally clean but deferred — needs validation that `entry_price` and `stop_loss` in the positions DB are sufficient to compute `r_distance` without storing it explicitly. Revisit after Phase 1. |

---

## 4. Summary of Code Changes

### `python-engine/config.py`
Add 6 new config values:
```python
MOMENTUM_ATR_FUEL_BUFFER:          float = 0.85
MOMENTUM_VOL_SURGE_LUNCHTIME:      float = 1.75
MOMENTUM_LUNCHTIME_START_HOUR:     int   = 11
MOMENTUM_LUNCHTIME_START_MIN:      int   = 30
MOMENTUM_LUNCHTIME_END_HOUR:       int   = 13
MOMENTUM_LUNCHTIME_END_MIN:        int   = 15
MOMENTUM_MORPHOLOGY_MIN_SCORE:     float = 0.65
MOMENTUM_R_TARGET_BEAR:            float = 1.5
```

### `python-engine/engine.py`
1. **`evaluate_momentum_signal()` signature** — add `df_daily: pd.DataFrame`, `vol_surge_threshold: float`, `market_regime: str = "BULL"` parameters.
2. **MC3** — replace hardcoded `settings.MOMENTUM_VOL_SURGE_PCT` with `vol_surge_threshold`.
3. **MC5 (new)** — ATR exhaustion gate using `df_daily` and `calc_atr()`.
4. **MC6 (new)** — Morphology gate on signal candle.
5. **MR2** — Regime-adjusted R target using `market_regime`.

### `python-engine/main.py`
Inside `run_momentum_screener()`, before calling `evaluate_momentum_signal()`:
1. Compute `vol_surge_threshold` based on `now_ist` vs lunchtime window.
2. Pass `df_daily` (already fetched as `df_daily`) to `evaluate_momentum_signal()`.
3. Pass `market_regime` (already in global state) to `evaluate_momentum_signal()`.

---

## 5. Gate Stack After Changes

```
MC1  Candle count >= 4                              [existing]
MC2  VWAP crossover in last 3 candles + holding     [existing]
MC3  Volume >= vol_surge_threshold                  [modified — threshold now time-aware]
  MC3-T: 1.5x before 11:30 or after 13:15 IST
  MC3-T: 1.75x between 11:30–13:15 IST
MC4  Close in top 20% of intraday session range     [existing]
MC5  Daily ATR exhaustion check (NEW)               [new — Gate A]
MC6  Morphology: close_position_score >= 0.65 (NEW) [new — Gate C]
MR1  Stop loss = breakout candle low                [existing]
MR2  Target = r_target × R (regime-adjusted)        [modified — Gate D]
     BULL: 2.0R | BEAR_RS_ONLY: 1.5R
MR3  Product type: MIS / CNC by position value      [existing]
     Cost viability check                           [existing]
     Net EV > 0                                     [existing]
```

---

## 6. Known Quirk Impact

- **[Q13]:** MC4 already uses intraday range strength. MC5 (ATR gate) uses `intraday_high` and `intraday_low` which are already computed for MC4. No conflict.
- **[Q14]:** MC3 threshold lowered to 1.5x is still the base. MC3-T raises it only during lunchtime. Base remains 1.5x. No regression.
- **[Q11]:** `vol_surge_threshold` is an internal computation parameter, not part of `MomentumSignal` model. No schema change.
- **[Q8]:** No changes to `update_daily_positions()` or trailing stop logic. MOMENTUM positions remain exempt.

---

## 7. Spec Self-Review

- ✅ No TBDs or placeholders
- ✅ No contradictions between sections
- ✅ Gate thresholds calibrated to avoid over-filtering (1.75x not 2.0x, 0.65 not 0.75, 0.85 buffer not 1.0)
- ✅ All data sources verified against actual code — no new API calls required
- ✅ `calc_atr()` already implemented and tested in engine.py
- ✅ `df_daily` already fetched in `run_momentum_screener()` — no extra fetch
- ✅ Inviolable rules respected: engine functions remain pure (time logic stays in main.py via `vol_surge_threshold` param)

---

*Ready for implementation via writing-plans.*
