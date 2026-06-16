# Trailing Exits — Operator Runbook

**Audience:** Whoever is on-call when position exits behave unexpectedly.
**Spec:** Branch `feat/trailing-exits` (off `evolve/smart-strategies`)
**Plan:** This document IS the plan + runbook (no separate plan file for a 1-hour config change).

---

## What this feature does

Makes position exits **regime-aware** so winners run longer in calm markets and
get cut faster in crisis. Three changes, all conservative and reversible:

1. **Regime 1 target bumped: 3.0R → 4.5R** — the hard ceiling in calm markets
2. **Hard cap added: 5.0R absolute ceiling** — safety valve, never hold past 5R
3. **Chandelier trail now regime-aware:**
   - Regime 1 (calm): **3.5×ATR** (was 3.0×) — more room for mid-cap trends
   - Regime 2 (elevated): **3.0×ATR** (unchanged)
   - Regime 3 (crisis): **2.5×ATR** (was 3.0×) — cut losses fast

**Why this matters:** trend-following research (Turtles, AHL, Winton) shows
that the single biggest P&L multiplier is letting winners run. The old
3.0R target in Regime 1 was capping winners too early. The trailing
Chandelier was already in place — this just widens it slightly to give
mid-cap Indian trends room to breathe.

**Risk profile:** Low. The hard cap at 5R prevents infinite holds. The
tighter Regime 3 trail reduces whipsaw risk. Regime 2 is unchanged.

---

## Settings reference

| Env var | Default | What it does |
|---------|---------|--------------|
| `TARGET2_R_REGIME1` | `4.5` | Hard T2 target in Regime 1 (was 3.0). |
| `TARGET2_R_REGIME2` | `3.0` | Hard T2 target in Regime 2 (unchanged). |
| `TARGET2_R_REGIME3` | `1.0` | Hard T2 target in Regime 3 (unchanged — exit at T1). |
| `HARD_CAP_R_REGIME1` | `5.0` | Absolute ceiling — never hold past this in Regime 1, regardless of target_2. |
| `CHANDELIER_ATR_REGIME1_MULT` | `3.5` | Trail width in Regime 1 (was 3.0). |
| `CHANDELIER_ATR_REGIME2_MULT` | `3.0` | Trail width in Regime 2 (unchanged). |
| `CHANDELIER_ATR_REGIME3_MULT` | `2.5` | Trail width in Regime 3 (was 3.0). |
| `CHANDELIER_ATR_MULT` | `3.0` | Legacy single multiplier — used only when `regime_at_entry` is NULL. |

All new settings are in `python-engine/config.py` (Target structure + Chandelier
sections). All are env-overridable.

---

## Backward compatibility

Pre-existing positions in the DB (with NULL `regime_at_entry`) use the **legacy
3.0×ATR trail**. The new behavior only applies to positions opened after this
change is deployed AND where the entry path writes `regime_at_entry`.

**Migration:** the `regime_at_entry` column is added with a NULL default. No
data backfill. Old positions will eventually close out (via T1, T2, stop, or
15-day time exit) and be replaced by new ones with proper regime tracking.

---

## How to know which regime a position is using

```sql
-- SQLite: list open positions with their entry regime
SELECT ticker, status, source, regime_at_entry, target_2, trailing_stop_current
FROM positions
WHERE status IN ('OPEN', 'CLOSED_T1');
```

A `regime_at_entry` of NULL means legacy (3.0×ATR). A value of `REGIME_1_NORMAL`,
`REGIME_2_ELEVATED`, or `REGIME_3_CRISIS` means the new behavior.

**Source filter:** only `source='SYSTEM'` (swing) positions use this regime-aware
trail. `source='MOMENTUM'` positions are auto-squared intraday (no trail applied)
and `source='MANUAL'` positions have whatever regime the operator specified.

---

## 2-week live validation protocol

This is **mandatory** before declaring the change a success. Run the system
for 2 weeks with the new settings, then evaluate.

### What to track (daily)

| Metric | Where | Pass criterion |
|---|---|---|
| Avg R-multiple of closed positions | `performance.py` / DB | **> 10% improvement** vs the prior 2 weeks |
| Max R-multiple of closed positions | `performance.py` / DB | At least 1 position > 3R (proves T2 widening fires) |
| % of T2 exits vs trailing-stop exits | log lines `CLOSED_T2` vs `STOPPED_OUT` | Roughly even split (T2 widening should produce more CLOSED_T2) |
| Avg days held | DB | **Stable** — should NOT increase >30% (would mean too many 4-5R holds) |
| Max drawdown | `performance.py` | **NOT 2x worse** than prior 2 weeks |

### What to log

The code already logs the key events:
- `trailing_exits_hard_cap_applied` — fired when hard cap reduces effective T2
- `chandelier_stop_out` — fired when Chandelier triggers
- `CLOSED_T2` / `STOPPED_OUT` / `CLOSED_TIME` — exit events

**New log line to watch for:** `trailing_exits_hard_cap_applied`. If this fires
frequently (more than once per week), it means the hard cap is being hit a lot
— which is fine in trending markets, but worth noting.

### Pass/fail decision

After 2 weeks:
- **Pass:** avg R improved AND max drawdown NOT 2x worse → keep the settings
- **Fail (drawdown):** max drawdown > 2x → revert T2 to 3.0R (try just the wider trail)
- **Fail (no P&L lift):** avg R unchanged → the trailing Chandelier was already catching trends; revert everything
- **Mixed:** avg R +5% but drawdown +20% → tighten back: T2=4.0, Regime 1 trail=3.25

### Rollback procedure

```bash
# Option 1: .env override (no code change)
echo "TARGET2_R_REGIME1=3.0" >> ~/trading-sentinel/python-engine/.env
echo "CHANDELIER_ATR_REGIME1_MULT=3.0" >> ~/trading-sentinel/python-engine/.env
echo "HARD_CAP_R_REGIME1=10.0" >> ~/trading-sentinel/python-engine/.env  # disable
ssh oracle-vm "docker restart python-engine"
```

```bash
# Option 2: git revert (full rollback)
cd ~/trading-sentinel
git revert <commit-hash-of-trailing-exits>
```

---

## What does NOT change

- **Engine scoring** (`engine.py`) — untouched
- **Regime engine** — untouched
- **Momentum screener** — uses its own R/R target (MOMENTUM_R_TARGET=2.0), unchanged.
  **Deliberate scope decision** (2026-06-16): momentum positions are
  intraday MIS, auto-squared at 15:15 IST, and `position_tracker.update_daily_positions`
  skips them entirely (`if pos.get('source') == 'MOMENTUM': continue`).
  The 3.5×/3.0×/2.5× trail and 5R cap are **unreachable for momentum** —
  the 1.5–2.0R momentum target is hit long before 5R, and the trail never
  gets a chance to fire before the 15:15 auto-square. So this branch
  doesn't touch the momentum path. A separate `feat/momentum-regime-aware`
  branch will handle momentum-specific changes (R3 entry blocking, R2
  size reduction, R2 tighter target). See "Momentum follow-up" below.
- **Time-exit** at 15 days — still applies as the ultimate backstop
- **T1 partial-exit** at 50% — still fires
- **Breakeven stop** after T1 hit — still applies

---

## Cross-references

- **Config:** `python-engine/config.py` (`TARGET2_R_REGIME1`, `HARD_CAP_R_REGIME1`, `CHANDELIER_ATR_REGIME*_MULT`)
- **Position tracking:** `python-engine/position_tracker.py` (regime-aware trail + hard cap logic in `update_daily_positions`)
- **Tests:** `python-engine/tests/test_trailing_exits.py` (config) + `test_trailing_exits_position_tracker.py` (behavior)
- **Chandelier implementation:** `python-engine/chandelier_stop.py` (untouched, but the multiplier is now passed in)

---

## Momentum follow-up (separate branch — `feat/momentum-regime-aware`)

Momentum is where 90–95% of P&L comes from in this system, but **this
branch does not change momentum behavior.** Momentum needs its own
branch with its own design pass because the regime affects it
differently — not via exit, but via entry and sizing.

### Why trailing-exits doesn't apply to momentum

| Trailing-exit feature | Effect on swing | Effect on momentum |
|---|---|---|
| 3.0R → 4.5R target | Lets winners run | **Unreachable** — momentum target is 1.5–2.0R, hit long before 4.5R |
| 5.0R hard cap | Safety valve | **Unreachable** — same reason |
| 3.5×/3.0×/2.5× Chandelier trail | Catches reversals | **Never fires** — momentum is squared at 15:15 IST, before the trail has data to act on |

The momentum auto-square is at 15:15 IST (`main.py:201`,
`auto_square_momentum` scheduler job). The Chandelier trail needs
**days** of price data to ratchet up. Momentum positions live for
**hours**. The two systems don't overlap.

### What momentum DOES need (planned for `feat/momentum-regime-aware`)

1. **Compute the 3-regime state in `run_momentum_screener`** — currently
   it only uses a 4-state string ("BULL"/"BEAR_RS_ONLY"/"CAUTION"/
   "UNKNOWN"). The 3-regime engine is bypassed.
2. **Block new entries in Regime 3 (Crisis)** — currently a VIX spike
   mid-day still fires momentum signals. In R3 → reject all momentum
   signals. Pure defense, saves money in crashes.
3. **Tighter R target in Regime 2** — currently flat 2.0R. In R2 → 1.5R
   (faster profit-take, less time in chop).
4. **Smaller position size in R2/R3** — currently flat 7% of momentum
   pool. In R2 → 5%, in R3 → 0% (gated above).
5. **Stamp regime on `MomentumSignal`** — already a field on the model
   (`models.py:95`) but never populated. Pure analytics — lets you
   later answer "are momentum entries in R2 actually profitable?".
6. **Time-of-day filter tuning** — mid-day (11:30–13:15 IST) is
   currently the "lunchtime dead zone" with elevated volume threshold
   (MC3-T). Could be extended to skip certain regime-time combinations
   (e.g. R3 + first 30 min = no entries).

### Suggested exploration order

1. **First:** stamp `regime` on `MomentumSignal` (analytics only, no
   behavioral change). Run for 1–2 weeks. Query the DB to see "how
   many momentum signals fired in R1 vs R2 vs R3, and their P&L."
2. **Then:** based on the data, decide the R2/R3 sizing and gating
   rules. If R2 momentum signals are unprofitable, block them. If R3
   signals are catastrophic, block them harder.
3. **Last:** time-of-day filters. By then you'll have the data to know
   which time × regime combos are winners vs losers.

This is a **separate branch with its own spec and validation**, not
back-wrapped into trailing-exits.
