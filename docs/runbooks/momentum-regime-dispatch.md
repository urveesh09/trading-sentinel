# Momentum Regime Dispatch (R1 / R2 / R3)

**Branch:** `feat/momentum-regime-aware`
**Date:** 2026-06-16
**Scope:** Replaces the legacy 4-state `market_regime` string with a 3-regime
dispatch wired into `evaluate_momentum_signal`. Swing regime computed at
09:20 IST and cached; momentum reads the cache for all 19 daily scans.

---

## What changed (operator summary)

| Regime | Position size | R target | Entry? |
|--------|---------------|----------|--------|
| R1 Normal | 7% of pool | 2.0R | ✅ Yes |
| R2 Elevated | 5% of pool | 1.5R | ✅ Yes (tighter) |
| R3 Crisis | 0% of pool | — | ⛔ **Blocked** (default) |

**Before:** Momentum used a 4-state string (`BULL` / `BEAR_RS_ONLY` /
`CAUTION` / `UNKNOWN`) and sized at flat 7% with 2.0/1.5R target based on
the swing screener's `market_regime` string. It did NOT block entries in
crisis conditions.

**After:** Momentum reads the 3-regime state from the swing screener's
`_momentum_regime_for_today` cache, gets regime-aware sizing and R-target
via the `resolve_momentum_regime_params()` helper, and **blocks all entries
in R3 by default** (`MOMENTUM_BLOCK_R3_ENTRIES=True`).

---

## Knobs (all in `python-engine/.env`)

| Setting | Default | Effect |
|---------|---------|--------|
| `MOMENTUM_BLOCK_R3_ENTRIES` | `True` | R3 → no entries. Set to `False` to allow (still 0% risk, so still nothing fires). |
| `MOMENTUM_RISK_PCT_R1` | `0.07` | R1 sizing (% of momentum pool). |
| `MOMENTUM_RISK_PCT_R2` | `0.05` | R2 sizing. |
| `MOMENTUM_RISK_PCT_R3` | `0.00` | R3 sizing. Defense in depth — even with BLOCK off, 0% risk = no shares. |
| `MOMENTUM_R_TARGET_R1` | `2.0` | R1 target (R-multiples). |
| `MOMENTUM_R_TARGET_R2` | `1.5` | R2 target. |
| `MOMENTUM_RISK_PCT` | `0.10` | **Legacy** — still respected when caller does NOT pass `regime=` (backward compat). |

---

## Caching behavior

1. `run_screener()` (swing) computes the regime at 09:20 IST using the
   full Nifty/BankNifty/ATR/breadth pipeline.
2. It writes the result to `main._momentum_regime_for_today`.
3. All 19 momentum scans in the day (10:15–14:45) read that cached value.
4. **Why not recompute per scan?** With 19 scans/day, recomputing on each
   would flip the regime 5+ times in a noisy session. The swing's 09:20
   compute has hysteresis + 2-scan confirmation; carrying it forward
   gives the momentum system regime stability for the trading day.
5. The next swing scan at 14:45 (EOD) overwrites the cache for the
   *next* day.

---

## Audit: what to monitor

```sql
-- How many R3 blocks happened today?
SELECT COUNT(*) FROM momentum_signals
WHERE date = DATE('now') AND reject_reason = 'regime_r3_block';

-- Distribution of signals by regime (last 7 days)
SELECT date, regime, COUNT(*) as n
FROM momentum_signals
WHERE date >= DATE('now', '-7 days')
GROUP BY date, regime
ORDER BY date DESC;
```

If you see **> 0 R3 blocks on a "should-be-normal" day**, the swing regime
is firing too aggressively. Check `regime_score` in the swing logs.

---

## Rollback

If R3 is too restrictive (e.g., it blocks a high-conviction rebound
opportunity), set in `python-engine/.env`:

```bash
MOMENTUM_BLOCK_R3_ENTRIES=False
```

This allows R3 evaluations to reach MC1-MC6, but `MOMENTUM_RISK_PCT_R3=0.0`
still produces 0 shares. So the **only behavioral change is rejection
reason**: `regime_r3_block` → one of the MC1-MC6 gates (e.g.,
`insufficient_intraday_candles`).

For full removal of regime dispatch, revert the call sites in
`main.py:run_momentum_screener` and `engine.py:evaluate_momentum_signal`.
No migration needed — the legacy `MOMENTUM_RISK_PCT` / `MOMENTUM_R_TARGET`
defaults are preserved.

---

## Validation protocol (2-week live)

After merge to `main` and Kite restart:

1. **Day 1–3:** Compare accept rate vs. pre-regime baseline. Expect a
   small dip in R3 days (those were losers anyway). No action needed.
2. **Day 4–7:** Check that the regime in `MomentumSignal` matches the
   swing's logged regime. If mismatch, cache isn't writing.
3. **Day 8–14:** Compare win rate × avg R-multiple vs. last 30 trading
   days. Expect R2 days to have *higher* win rate (tighter targets =
   fewer "ran past target and reversed" losses).
4. **Day 15:** Roll decision. If win rate unchanged AND R2 day count
   < 5, keep the feature. If R2 day count > 10 and win rate is worse,
   tighten `MOMENTUM_R_TARGET_R2` from 1.5 → 1.25.
