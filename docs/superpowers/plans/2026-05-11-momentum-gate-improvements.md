# Momentum Gate Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four new momentum signal gates (MC3-T, MC5, MC6, regime-adjusted R target) to reduce false positives from ATR-exhausted, lunchtime, and shooting-star breakouts without over-filtering legitimate signals.

**Architecture:** All changes are isolated to three files: `config.py` (new settings), `engine.py` (new gate logic + signature extension), `main.py` (lunchtime threshold computation + new arg threading). No DB schema changes. No new API calls. No Node Gateway changes.

**Tech Stack:** Python 3.11, pandas, numpy, pytest, pytest-asyncio. All new logic uses `calc_atr()` already present in `engine.py`.

**Spec:** `docs/superpowers/specs/2026-05-11-momentum-gate-improvements-design.md`

---

## File Map

| File | Action | What changes |
|---|---|---|
| `python-engine/config.py` | Modify | Add 8 new settings |
| `python-engine/engine.py` | Modify | Extend `evaluate_momentum_signal()` signature; add MC5, MC6; modify MC3, MR2 |
| `python-engine/main.py` | Modify | Compute `vol_surge_threshold`; pass `df_daily`, `vol_surge_threshold`, `market_regime` to `evaluate_momentum_signal()` |
| `python-engine/tests/test_engine.py` | Modify | Add tests for MC5, MC6, MC3-T, regime R target |

---

## Task 1: Add new config values

**Files:**
- Modify: `python-engine/config.py`

- [ ] **Step 1: Add the 8 new settings to the `Settings` class**

Open `python-engine/config.py`. Find the `# Momentum` block (currently ends at `MOMENTUM_RISK_PCT`). Add immediately after `MOMENTUM_RISK_PCT`:

```python
    MOMENTUM_ATR_FUEL_BUFFER:          float = 0.85   # [MC5] ATR exhaustion gate: target must fit within remaining_fuel * buffer
    MOMENTUM_VOL_SURGE_LUNCHTIME:      float = 1.75   # [MC3-T] Volume threshold during lunchtime dead zone (11:30–13:15 IST)
    MOMENTUM_LUNCHTIME_START_HOUR:     int   = 11     # [MC3-T] Lunchtime start hour (IST)
    MOMENTUM_LUNCHTIME_START_MIN:      int   = 30     # [MC3-T] Lunchtime start minute (IST)
    MOMENTUM_LUNCHTIME_END_HOUR:       int   = 13     # [MC3-T] Lunchtime end hour (IST)
    MOMENTUM_LUNCHTIME_END_MIN:        int   = 15     # [MC3-T] Lunchtime end minute (IST)
    MOMENTUM_MORPHOLOGY_MIN_SCORE:     float = 0.65   # [MC6] Minimum close_position_score to reject shooting-star candles
    MOMENTUM_R_TARGET_BEAR:            float = 1.5    # [MR2] R target in BEAR_RS_ONLY regime (reduced from 2.0R)
```

- [ ] **Step 2: Verify settings load without error**

```bash
cd python-engine
python -c "from config import settings; print(settings.MOMENTUM_ATR_FUEL_BUFFER, settings.MOMENTUM_VOL_SURGE_LUNCHTIME, settings.MOMENTUM_MORPHOLOGY_MIN_SCORE, settings.MOMENTUM_R_TARGET_BEAR)"
```

Expected output: `0.85 1.75 0.65 1.5`

- [ ] **Step 3: Commit**

```bash
git add python-engine/config.py
git commit -m "feat(config): add MC5/MC3-T/MC6/bear-R momentum gate settings"
```

---

## Task 2: Extend `evaluate_momentum_signal()` signature

**Files:**
- Modify: `python-engine/engine.py` (function signature and docstring only — no gate logic yet)

The current signature is:
```python
def evaluate_momentum_signal(
    ticker: str,
    df: pd.DataFrame,
    prev_day_high: float,
    bankroll: float,
    momentum_pool: float,
    min_candles: int = 4
) -> tuple[bool, dict]:
```

- [ ] **Step 1: Write a failing test that calls the new signature**

In `python-engine/tests/test_engine.py`, add at the end of the file:

```python
def test_evaluate_momentum_signal_accepts_new_params(minimal_intraday_df, minimal_daily_df):
    """New parameters df_daily, vol_surge_threshold, market_regime must be accepted."""
    fired, _ = evaluate_momentum_signal(
        ticker="TEST",
        df=minimal_intraday_df,
        df_daily=minimal_daily_df,
        prev_day_high=100.0,
        bankroll=10000.0,
        momentum_pool=5000.0,
        vol_surge_threshold=1.5,
        market_regime="BULL",
    )
    # We only care that it accepts the params without TypeError — result doesn't matter yet
    assert isinstance(fired, bool)
```

You will also need the `minimal_daily_df` fixture. In `python-engine/tests/conftest.py`, add:

```python
@pytest.fixture
def minimal_daily_df():
    """14+ daily OHLCV rows so calc_atr() has enough data."""
    n = 20
    dates = pd.date_range("2026-04-01", periods=n, freq="B")
    return pd.DataFrame({
        "open":   [100.0] * n,
        "high":   [105.0] * n,
        "low":    [95.0]  * n,
        "close":  [102.0] * n,
        "volume": [500000] * n,
    }, index=dates)
```

- [ ] **Step 2: Run to confirm it fails with TypeError**

```bash
cd python-engine
python -m pytest tests/test_engine.py::test_evaluate_momentum_signal_accepts_new_params -v
```

Expected: `FAILED` — `TypeError: evaluate_momentum_signal() got unexpected keyword argument 'df_daily'`

- [ ] **Step 3: Update the function signature and docstring**

In `python-engine/engine.py`, replace the `evaluate_momentum_signal` function signature and docstring:

```python
def evaluate_momentum_signal(
    ticker: str,
    df: pd.DataFrame,
    df_daily: pd.DataFrame,
    prev_day_high: float,
    bankroll: float,
    momentum_pool: float,
    min_candles: int = 4,
    vol_surge_threshold: float = 1.5,
    market_regime: str = "BULL",
) -> tuple[bool, dict]:
    """
    [MOM2] Intraday momentum signal evaluation.
    df must contain ONLY today's 15-minute candles (VWAP resets daily).
    df_daily must contain at least 14 daily OHLCV rows for ATR calculation.

    Entry conditions (ALL must be true):
      [MC1] Minimum candles: len(df) >= min_candles
      [MC2] Price crossed ABOVE VWAP in the LAST 3 candles + holding check
      [MC3] Last candle volume >= vol_surge_threshold (time-aware, set by caller)
            [MC3-T] Caller raises threshold to 1.75x during 11:30–13:15 IST
      [MC4] Current close in top 20% of today's intraday session range
      [MC5] Daily ATR exhaustion: target_distance <= remaining_fuel * ATR_FUEL_BUFFER
      [MC6] Morphology: close_position_score >= MOMENTUM_MORPHOLOGY_MIN_SCORE

    Risk:
      [MR1] Stop loss = low of the breakout candle (last candle)
      [MR2] Target = r_target × R  where r_target is regime-adjusted:
            BULL: settings.MOMENTUM_R_TARGET (2.0)
            BEAR_RS_ONLY: settings.MOMENTUM_R_TARGET_BEAR (1.5)
      [MR3] Product type decision: MIS if position_value < ₹5,000, else CNC
    """
```

- [ ] **Step 4: Run test — should now pass**

```bash
cd python-engine
python -m pytest tests/test_engine.py::test_evaluate_momentum_signal_accepts_new_params -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add python-engine/engine.py python-engine/tests/test_engine.py python-engine/tests/conftest.py
git commit -m "feat(engine): extend evaluate_momentum_signal signature for new gates"
```

---

## Task 3: Implement MC3-T (time-aware volume threshold)

**Files:**
- Modify: `python-engine/engine.py` (MC3 block only)

The goal: replace the hardcoded `settings.MOMENTUM_VOL_SURGE_PCT` in MC3 with the caller-supplied `vol_surge_threshold`.

- [ ] **Step 1: Write failing tests**

In `python-engine/tests/test_engine.py`, add:

```python
def test_mc3_uses_vol_surge_threshold_rejects_below(base_momentum_df, minimal_daily_df):
    """MC3: volume ratio below vol_surge_threshold → rejected."""
    # base_momentum_df has volume_ratio just above 1.5 — pass threshold=2.0 to force rejection
    fired, result = evaluate_momentum_signal(
        ticker="TEST",
        df=base_momentum_df,
        df_daily=minimal_daily_df,
        prev_day_high=80.0,
        bankroll=10000.0,
        momentum_pool=5000.0,
        vol_surge_threshold=2.0,   # higher than the candle's actual ratio
        market_regime="BULL",
    )
    assert fired is False
    assert result["reject_reason"] == "volume_surge_insufficient"


def test_mc3_uses_vol_surge_threshold_passes_above(base_momentum_df, minimal_daily_df):
    """MC3: volume ratio above vol_surge_threshold → not rejected by MC3."""
    fired, result = evaluate_momentum_signal(
        ticker="TEST",
        df=base_momentum_df,
        df_daily=minimal_daily_df,
        prev_day_high=80.0,
        bankroll=10000.0,
        momentum_pool=5000.0,
        vol_surge_threshold=1.0,   # lower than the candle's actual ratio
        market_regime="BULL",
    )
    # May fail on later gates (MC5, MC6) but NOT on volume_surge_insufficient
    assert result.get("reject_reason") != "volume_surge_insufficient"
```

Note: `base_momentum_df` must be a fixture that produces a valid intraday df with a VWAP crossover and volume ratio of ~1.6. Check `conftest.py` — if it doesn't exist yet, add it:

```python
@pytest.fixture
def base_momentum_df():
    """
    Minimal intraday df that passes MC1, MC2, MC4.
    Volume ratio on last candle is ~1.6x average.
    Close is near the high of the day (MC4 passes).
    """
    n = 6
    timestamps = pd.date_range("2026-05-11 09:15", periods=n, freq="15min")
    avg_vol = 100_000
    df = pd.DataFrame({
        "open":   [99.0, 99.5, 99.8, 100.0, 100.2, 100.5],
        "high":   [99.5, 100.0, 100.2, 100.5, 100.8, 101.5],
        "low":    [98.5,  99.0,  99.5, 99.8, 100.0, 100.0],
        "close":  [99.2,  99.6,  99.9, 100.1, 100.3, 101.2],
        "volume": [avg_vol] * (n - 1) + [int(avg_vol * 1.6)],
    }, index=timestamps)
    return df
```

- [ ] **Step 2: Run to confirm failures**

```bash
cd python-engine
python -m pytest tests/test_engine.py::test_mc3_uses_vol_surge_threshold_rejects_below tests/test_engine.py::test_mc3_uses_vol_surge_threshold_passes_above -v
```

Expected: both `FAILED`

- [ ] **Step 3: Replace the MC3 check in engine.py**

Find the `[MC3]` block in `evaluate_momentum_signal`. It currently reads:

```python
    if vol_ratio_intraday < settings.MOMENTUM_VOL_SURGE_PCT:
        return False, {"reject_reason": "volume_surge_insufficient", "ratio": vol_ratio_intraday, "threshold": settings.MOMENTUM_VOL_SURGE_PCT}
```

Replace with:

```python
    # [MC3-T] Volume threshold is time-aware — caller passes the correct threshold.
    # During lunchtime (11:30–13:15 IST): vol_surge_threshold = settings.MOMENTUM_VOL_SURGE_LUNCHTIME (1.75x)
    # Outside lunchtime: vol_surge_threshold = settings.MOMENTUM_VOL_SURGE_PCT (1.5x)
    if vol_ratio_intraday < vol_surge_threshold:
        return False, {"reject_reason": "volume_surge_insufficient", "ratio": round(vol_ratio_intraday, 4), "threshold": vol_surge_threshold}
```

- [ ] **Step 4: Run tests — should pass**

```bash
cd python-engine
python -m pytest tests/test_engine.py::test_mc3_uses_vol_surge_threshold_rejects_below tests/test_engine.py::test_mc3_uses_vol_surge_threshold_passes_above -v
```

Expected: both `PASSED`

- [ ] **Step 5: Commit**

```bash
git add python-engine/engine.py python-engine/tests/test_engine.py
git commit -m "feat(engine): MC3-T — vol_surge_threshold is now caller-supplied (time-aware)"
```

---

## Task 4: Implement MC5 — Daily ATR Exhaustion Gate

**Files:**
- Modify: `python-engine/engine.py` (add MC5 block after MC4)

- [ ] **Step 1: Write failing tests**

In `python-engine/tests/test_engine.py`, add:

```python
def test_mc5_rejects_when_target_exceeds_remaining_fuel(base_momentum_df, minimal_daily_df):
    """
    MC5: if target_distance > remaining_fuel * buffer, reject.
    We craft df_daily so daily_atr is small (e.g. 5 pts) and intraday range already consumed most of it.
    """
    n = 20
    dates = pd.date_range("2026-04-01", periods=n, freq="B")
    # Tight daily ATR: high-low spread = 5 pts every day
    tight_daily = pd.DataFrame({
        "open":   [100.0] * n,
        "high":   [102.5] * n,
        "low":    [97.5]  * n,  # ATR ≈ 5 pts
        "close":  [101.0] * n,
        "volume": [500000] * n,
    }, index=dates)
    # base_momentum_df has intraday_high=101.5, intraday_low=98.5 → range = 3 pts
    # remaining_fuel = 5 - 3 = 2 pts
    # stop = 100.0 (last candle low), close = 101.2, r_distance = 1.2
    # target_distance = 2.0 * 1.2 = 2.4 pts > 2 * 0.85 = 1.7 → reject
    fired, result = evaluate_momentum_signal(
        ticker="TEST",
        df=base_momentum_df,
        df_daily=tight_daily,
        prev_day_high=80.0,
        bankroll=10000.0,
        momentum_pool=5000.0,
        vol_surge_threshold=1.5,
        market_regime="BULL",
    )
    assert fired is False
    assert result["reject_reason"] == "daily_atr_exhausted"


def test_mc5_passes_when_fuel_sufficient(base_momentum_df, minimal_daily_df):
    """MC5: if remaining_fuel is large enough, gate passes."""
    n = 20
    dates = pd.date_range("2026-04-01", periods=n, freq="B")
    # Wide daily ATR: 50-pt range every day → plenty of fuel
    wide_daily = pd.DataFrame({
        "open":   [100.0] * n,
        "high":   [125.0] * n,
        "low":    [75.0]  * n,  # ATR ≈ 50 pts
        "close":  [101.0] * n,
        "volume": [500000] * n,
    }, index=dates)
    fired, result = evaluate_momentum_signal(
        ticker="TEST",
        df=base_momentum_df,
        df_daily=wide_daily,
        prev_day_high=80.0,
        bankroll=10000.0,
        momentum_pool=5000.0,
        vol_surge_threshold=1.5,
        market_regime="BULL",
    )
    assert result.get("reject_reason") != "daily_atr_exhausted"
```

- [ ] **Step 2: Run to confirm failures**

```bash
cd python-engine
python -m pytest tests/test_engine.py::test_mc5_rejects_when_target_exceeds_remaining_fuel tests/test_engine.py::test_mc5_passes_when_fuel_sufficient -v
```

Expected: both `FAILED`

- [ ] **Step 3: Add MC5 gate to engine.py**

Find the comment `# [MR1] Stop loss = low of breakout candle` in `evaluate_momentum_signal`. Insert the MC5 block **immediately before it** (after the existing MC4 block):

```python
    # [MC5] Daily ATR Exhaustion Gate
    # Reject if the distance to target exceeds the stock's remaining daily range budget.
    # remaining_fuel = daily_atr - intraday_range_consumed_so_far
    # target_distance must fit within remaining_fuel * MOMENTUM_ATR_FUEL_BUFFER
    if not df_daily.empty and len(df_daily) >= 14:
        daily_atr_series = calc_atr(df_daily['high'], df_daily['low'], df_daily['close'])
        daily_atr_val = daily_atr_series.iloc[-1]
        if daily_atr_val > 0:
            intraday_range_consumed = intraday_high - intraday_low
            remaining_fuel = daily_atr_val - intraday_range_consumed
            # Estimate target_distance using breakout_candle_low as stop proxy
            breakout_low_est = df['low'].iloc[-1]
            r_dist_est = current_close - breakout_low_est
            target_distance = settings.MOMENTUM_R_TARGET * r_dist_est
            if target_distance > remaining_fuel * settings.MOMENTUM_ATR_FUEL_BUFFER:
                return False, {
                    "reject_reason": "daily_atr_exhausted",
                    "daily_atr": round(daily_atr_val, 2),
                    "intraday_range_consumed": round(intraday_range_consumed, 2),
                    "remaining_fuel": round(remaining_fuel, 2),
                    "target_distance_needed": round(target_distance, 2),
                }
```

Note: `intraday_high` and `intraday_low` are already computed above this point by MC4. Use them directly.

- [ ] **Step 4: Run tests — should pass**

```bash
cd python-engine
python -m pytest tests/test_engine.py::test_mc5_rejects_when_target_exceeds_remaining_fuel tests/test_engine.py::test_mc5_passes_when_fuel_sufficient -v
```

Expected: both `PASSED`

- [ ] **Step 5: Commit**

```bash
git add python-engine/engine.py python-engine/tests/test_engine.py
git commit -m "feat(engine): add MC5 daily ATR exhaustion gate"
```

---

## Task 5: Implement MC6 — Morphology Gate

**Files:**
- Modify: `python-engine/engine.py` (add MC6 block after MC5)

- [ ] **Step 1: Write failing tests**

In `python-engine/tests/test_engine.py`, add:

```python
def test_mc6_rejects_shooting_star_candle(minimal_daily_df):
    """MC6: candle with close near the low (shooting star) is rejected."""
    n = 6
    timestamps = pd.date_range("2026-05-11 09:15", periods=n, freq="15min")
    avg_vol = 100_000
    # Last candle: open=100, high=110, low=99, close=100.5 → score=(100.5-99)/(110-99)=0.136 → reject
    df = pd.DataFrame({
        "open":   [99.0, 99.5, 99.8, 100.0, 100.2, 100.0],
        "high":   [99.5, 100.0, 100.2, 100.5, 100.8, 110.0],
        "low":    [98.5,  99.0,  99.5,  99.8, 100.0,  99.0],
        "close":  [99.2,  99.6,  99.9, 100.1, 100.3, 100.5],
        "volume": [avg_vol] * (n - 1) + [int(avg_vol * 1.6)],
    }, index=timestamps)
    fired, result = evaluate_momentum_signal(
        ticker="TEST",
        df=df,
        df_daily=minimal_daily_df,
        prev_day_high=80.0,
        bankroll=10000.0,
        momentum_pool=5000.0,
        vol_surge_threshold=1.5,
        market_regime="BULL",
    )
    assert fired is False
    assert result["reject_reason"] == "shooting_star_candle"


def test_mc6_passes_clean_bullish_candle(base_momentum_df, minimal_daily_df):
    """MC6: candle closing near its high passes morphology check."""
    fired, result = evaluate_momentum_signal(
        ticker="TEST",
        df=base_momentum_df,
        df_daily=minimal_daily_df,
        prev_day_high=80.0,
        bankroll=10000.0,
        momentum_pool=5000.0,
        vol_surge_threshold=1.5,
        market_regime="BULL",
    )
    assert result.get("reject_reason") != "shooting_star_candle"
```

- [ ] **Step 2: Run to confirm failures**

```bash
cd python-engine
python -m pytest tests/test_engine.py::test_mc6_rejects_shooting_star_candle tests/test_engine.py::test_mc6_passes_clean_bullish_candle -v
```

Expected: both `FAILED`

- [ ] **Step 3: Add MC6 gate to engine.py**

Insert immediately after the MC5 block (before `# [MR1] Stop loss`):

```python
    # [MC6] Morphology Gate: reject shooting-star / rejected-spike candles.
    # close_position_score = (close - candle_low) / (candle_high - candle_low)
    # Score < MOMENTUM_MORPHOLOGY_MIN_SCORE means bears fought back hard in this candle.
    candle_high_last = df['high'].iloc[-1]
    candle_low_last  = df['low'].iloc[-1]
    candle_range_last = candle_high_last - candle_low_last
    if candle_range_last > 0:
        close_position_score = (current_close - candle_low_last) / candle_range_last
        if close_position_score < settings.MOMENTUM_MORPHOLOGY_MIN_SCORE:
            return False, {
                "reject_reason": "shooting_star_candle",
                "close_position_score": round(close_position_score, 4),
                "threshold": settings.MOMENTUM_MORPHOLOGY_MIN_SCORE,
            }
```

- [ ] **Step 4: Run tests — should pass**

```bash
cd python-engine
python -m pytest tests/test_engine.py::test_mc6_rejects_shooting_star_candle tests/test_engine.py::test_mc6_passes_clean_bullish_candle -v
```

Expected: both `PASSED`

- [ ] **Step 5: Commit**

```bash
git add python-engine/engine.py python-engine/tests/test_engine.py
git commit -m "feat(engine): add MC6 morphology (shooting-star) gate"
```

---

## Task 6: Implement MR2 — Regime-Adjusted R Target

**Files:**
- Modify: `python-engine/engine.py` (MR2 block)

- [ ] **Step 1: Write failing tests**

In `python-engine/tests/test_engine.py`, add:

```python
def test_mr2_bear_regime_uses_reduced_r_target(base_momentum_df, minimal_daily_df):
    """MR2: BEAR_RS_ONLY regime uses MOMENTUM_R_TARGET_BEAR (1.5R) not 2.0R."""
    # Use wide daily df so MC5 passes
    n = 20
    dates = pd.date_range("2026-04-01", periods=n, freq="B")
    wide_daily = pd.DataFrame({
        "open":   [100.0] * n,
        "high":   [125.0] * n,
        "low":    [75.0]  * n,
        "close":  [101.0] * n,
        "volume": [500000] * n,
    }, index=dates)
    fired_bear, result_bear = evaluate_momentum_signal(
        ticker="TEST",
        df=base_momentum_df,
        df_daily=wide_daily,
        prev_day_high=80.0,
        bankroll=10000.0,
        momentum_pool=5000.0,
        vol_surge_threshold=1.5,
        market_regime="BEAR_RS_ONLY",
    )
    fired_bull, result_bull = evaluate_momentum_signal(
        ticker="TEST",
        df=base_momentum_df,
        df_daily=wide_daily,
        prev_day_high=80.0,
        bankroll=10000.0,
        momentum_pool=5000.0,
        vol_surge_threshold=1.5,
        market_regime="BULL",
    )
    if fired_bear and fired_bull:
        # Bear target must be strictly less than bull target
        assert result_bear["target_1"] < result_bull["target_1"]
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd python-engine
python -m pytest tests/test_engine.py::test_mr2_bear_regime_uses_reduced_r_target -v
```

Expected: `FAILED`

- [ ] **Step 3: Update MR2 in engine.py**

Find the `[MR2] Target: 2.0R` block in `evaluate_momentum_signal`. It currently reads:

```python
    # [MR2] Target: 2.0R
    r_distance = current_close - stop_loss
    target     = current_close + (2.0 * r_distance)
```

Replace with:

```python
    # [MR2] Target: regime-adjusted R
    # BULL / CAUTION: settings.MOMENTUM_R_TARGET (2.0R)
    # BEAR_RS_ONLY: settings.MOMENTUM_R_TARGET_BEAR (1.5R) — bear markets structurally
    # compress intraday upside; 2R targets are mathematically unreachable.
    r_distance = current_close - stop_loss
    r_target   = settings.MOMENTUM_R_TARGET_BEAR if market_regime == "BEAR_RS_ONLY" else settings.MOMENTUM_R_TARGET
    target     = current_close + (r_target * r_distance)
```

Also update the `is_cost_viable()` call immediately below to use `r_target`:

```python
    viable, cost_ratio = is_cost_viable(
        entry_price=current_close, shares=shares,
        risk_per_trade=momentum_risk, r_target=r_target,   # ← was settings.MOMENTUM_R_TARGET
        max_cost_ratio=settings.MOMENTUM_MAX_COST_RATIO, is_intraday=True
    )
```

And update the `net_ev` calculation:

```python
    estimated_exit = current_close + (r_target * r_distance)  # ← was settings.MOMENTUM_R_TARGET
    total_cost = calc_zerodha_costs(
        current_close, estimated_exit, shares, is_intraday=True, for_gate=True
    )
    net_ev = (momentum_risk * r_target) - total_cost  # ← was settings.MOMENTUM_R_TARGET
```

- [ ] **Step 4: Run test — should pass**

```bash
cd python-engine
python -m pytest tests/test_engine.py::test_mr2_bear_regime_uses_reduced_r_target -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add python-engine/engine.py python-engine/tests/test_engine.py
git commit -m "feat(engine): MR2 regime-adjusted R target (1.5R in BEAR_RS_ONLY)"
```

---

## Task 7: Wire new parameters in main.py

**Files:**
- Modify: `python-engine/main.py` (inside `run_momentum_screener()`)

This task makes `main.py` compute the lunchtime volume threshold and pass all three new arguments to `evaluate_momentum_signal()`.

- [ ] **Step 1: Write failing integration test**

In `python-engine/tests/test_main_api.py`, find or add the section that mocks `evaluate_momentum_signal`. Add:

```python
@pytest.mark.asyncio
async def test_momentum_screener_passes_lunchtime_threshold_during_lunchtime(
    client, mock_kite_with_intraday, monkeypatch
):
    """
    During lunchtime (11:30–13:15 IST), run_momentum_screener must call
    evaluate_momentum_signal with vol_surge_threshold=1.75.
    """
    import python_engine.engine as eng_module
    captured = {}

    original = eng_module.evaluate_momentum_signal
    def capturing_eval(*args, **kwargs):
        captured["vol_surge_threshold"] = kwargs.get("vol_surge_threshold", args[6] if len(args) > 6 else None)
        return original(*args, **kwargs)

    monkeypatch.setattr(eng_module, "evaluate_momentum_signal", capturing_eval)

    # Simulate 12:00 IST — inside lunchtime window
    import pytz
    from datetime import datetime
    IST = pytz.timezone("Asia/Kolkata")
    fake_now = IST.localize(datetime(2026, 5, 11, 12, 0, 0))
    monkeypatch.setattr("main.datetime", type("dt", (), {"now": staticmethod(lambda tz=None: fake_now)})())

    # POST /token to trigger screener (or call run_momentum_screener directly)
    # ... depends on your test setup. Adjust to match existing test patterns in test_main_api.py.
    # The key assertion is:
    assert captured.get("vol_surge_threshold") == 1.75
```

> **Note:** Adapt the mock pattern to match whatever pattern is already used in `test_main_api.py` for mocking time and kite. The important assertion is `vol_surge_threshold == 1.75` inside lunchtime and `== 1.5` outside.

- [ ] **Step 2: Run to confirm failure**

```bash
cd python-engine
python -m pytest tests/test_main_api.py::test_momentum_screener_passes_lunchtime_threshold_during_lunchtime -v
```

Expected: `FAILED`

- [ ] **Step 3: Update run_momentum_screener() in main.py**

Inside `run_momentum_screener()`, find the block that computes `from_dt` / `to_dt`. After that block, add:

```python
    # [MC3-T] Compute time-aware volume threshold.
    # Engine functions must remain pure — time logic lives here, threshold passed as parameter.
    _lunchtime_start = now_ist.replace(
        hour=settings.MOMENTUM_LUNCHTIME_START_HOUR,
        minute=settings.MOMENTUM_LUNCHTIME_START_MIN,
        second=0, microsecond=0
    )
    _lunchtime_end = now_ist.replace(
        hour=settings.MOMENTUM_LUNCHTIME_END_HOUR,
        minute=settings.MOMENTUM_LUNCHTIME_END_MIN,
        second=0, microsecond=0
    )
    vol_surge_threshold = (
        settings.MOMENTUM_VOL_SURGE_LUNCHTIME
        if _lunchtime_start <= now_ist < _lunchtime_end
        else settings.MOMENTUM_VOL_SURGE_PCT
    )
    logger.info("momentum_vol_threshold", threshold=vol_surge_threshold, lunchtime=(_lunchtime_start <= now_ist < _lunchtime_end))
```

Then find the `evaluate_momentum_signal(...)` call inside the ticker loop. Replace it with:

```python
            fired, sig_data = evaluate_momentum_signal(
                ticker=ticker,
                df=df_intra,
                df_daily=df_daily,
                prev_day_high=prev_day_high,
                bankroll=bankroll,
                momentum_pool=momentum_pool,
                vol_surge_threshold=vol_surge_threshold,
                market_regime=market_regime,
            )
```

Note: `df_daily` is already fetched in this loop as part of the `prev_day_high` logic. `market_regime` is the global variable already set by `run_screener()`. Both are already in scope.

- [ ] **Step 4: Run integration test — should pass**

```bash
cd python-engine
python -m pytest tests/test_main_api.py::test_momentum_screener_passes_lunchtime_threshold_during_lunchtime -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add python-engine/main.py python-engine/tests/test_main_api.py
git commit -m "feat(main): wire MC3-T threshold + df_daily + market_regime into evaluate_momentum_signal"
```

---

## Task 8: Full regression run

**Files:**
- No code changes — verification only

- [ ] **Step 1: Run all engine tests**

```bash
cd python-engine
python -m pytest tests/test_engine.py -v
```

Expected: all existing tests `PASSED`, all new tests `PASSED`. Zero regressions.

- [ ] **Step 2: Run all Python engine tests**

```bash
cd python-engine
python -m pytest tests/ -v --tb=short
```

Expected: all `PASSED`. If any pre-existing test fails, investigate before proceeding.

- [ ] **Step 3: Verify config loads cleanly**

```bash
cd python-engine
python -c "
from config import settings
print('ATR buffer:', settings.MOMENTUM_ATR_FUEL_BUFFER)
print('Lunchtime vol:', settings.MOMENTUM_VOL_SURGE_LUNCHTIME)
print('Lunchtime window:', settings.MOMENTUM_LUNCHTIME_START_HOUR, settings.MOMENTUM_LUNCHTIME_START_MIN, '-', settings.MOMENTUM_LUNCHTIME_END_HOUR, settings.MOMENTUM_LUNCHTIME_END_MIN)
print('Morphology min:', settings.MOMENTUM_MORPHOLOGY_MIN_SCORE)
print('Bear R target:', settings.MOMENTUM_R_TARGET_BEAR)
print('All OK')
"
```

Expected: values printed without error, `All OK` at end.

- [ ] **Step 4: Verify engine imports cleanly**

```bash
cd python-engine
python -c "from engine import evaluate_momentum_signal, calc_atr; print('engine OK')"
```

Expected: `engine OK`

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "test: full regression pass — momentum gate improvements complete"
```

---

## Known Quirk Cross-Check

Before closing, verify these Known Quirks are unaffected:

| Quirk | What to check |
|---|---|
| [Q13] MC4 replaced with intraday range check; old code preserved as comment | Confirm the `[MC4-LEGACY]` comment block is still present and unchanged in `engine.py` |
| [Q14] MC3 threshold 1.5x base | Confirm `settings.MOMENTUM_VOL_SURGE_PCT` is still 1.5 in `config.py`; only lunchtime raises it |
| [Q8] MOMENTUM positions exempt from trailing stop | Confirm no changes were made to `update_daily_positions()` in `position_tracker.py` |
| [Q11] `cost_ratio` on MomentumSignal | Confirm `models.py` was not touched |

---

## Gate Stack Summary (Post-Implementation)

```
MC1  Candle count >= 4
MC2  VWAP crossover in last 3 candles + holding check
MC3  Volume >= vol_surge_threshold
     [MC3-T] 1.5x outside 11:30–13:15 IST | 1.75x inside lunchtime
MC4  Close in top 20% of intraday session range
MC5  Daily ATR exhaustion: target_distance <= remaining_fuel * 0.85   ← NEW
MC6  Morphology: close_position_score >= 0.65                         ← NEW
MR1  Stop loss = breakout candle low
MR2  Target = r_target × R  (BULL: 2.0R | BEAR_RS_ONLY: 1.5R)        ← MODIFIED
MR3  Product type: MIS / CNC
     Cost viability: cost_ratio <= 25%
     Net EV > 0
```
