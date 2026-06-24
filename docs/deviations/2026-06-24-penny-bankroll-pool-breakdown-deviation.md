# 2026-06-24 — Penny bankroll pool breakdown (B-tight, display-only)

## Problem

The previous penny-bankroll integration commit (9203dd7) wired penny
realized P&L into `bankroll_ledger` with `source='PENNY'`. But the
dashboard's `/bankroll` endpoint still reads `current_bankroll()`,
which returns the **last row** of the ledger — so:

- Before any penny trade closes: `/bankroll` shows 5,000 (swing initial).
- After penny close #1: `/bankroll` shows 5,000 + that trade's net P&L.
- The penny pool's Rs 2,000 **allocation** (Uru 2026-06-22 opt-in) is
  never reflected on the dashboard — it's a separate config constant.

The user (Uru 2026-06-24) asked for both pools to be visible on the
dashboard, but explicitly **without** changing the swing circuit
breaker math.

## Decision: B-tight (display only)

Three options were considered:

| Option | Description | Risk math change? |
|---|---|---|
| **A** | Seed an INITIAL row with `pnl=2000, source='PENNY'`, bumping bankroll to 7,000 baseline | Yes — swing CBs scale to 7,000, loosens risk gates |
| **B-tight** (chosen) | New `/bankroll/breakdown` endpoint shows swing + penny independently. Existing `/bankroll` and CB math untouched. | **No** |
| **B-combined** | `current_bankroll()` returns swing balance + penny balance + penny P&L | Yes — same as A but more invasive |

Uru 2026-06-24 picked B-tight after being shown the difference. The
combined number on the breakdown endpoint is **informational only**
and is never read by `check_circuit_breakers()`.

## What landed

### 1. `performance.pool_breakdown(db_path)` — new helper

Returns:
```python
{
  "swing":   {"balance": float, "trades": int},
  "penny":   {"balance": float, "allocated": float, "pnl": float,
              "trades": int, "mode": "live"|"paper"},
  "combined": float,    # informational only
  "as_of":   "<UTC ISO8601>",
}
```

Math (no schema change beyond what 9203dd7 already added):

- `swing.balance  = INITIAL_BANKROLL + SUM(pnl WHERE source='SYSTEM')`
- `penny.allocated = PENNY_LIVE_BANKROLL` (or PENNY_PAPER_BANKROLL in paper mode)
- `penny.pnl      = SUM(pnl WHERE source='PENNY')`
- `penny.balance  = penny.allocated + penny.pnl`
- `combined       = swing.balance + penny.balance`

### 2. `GET /bankroll/breakdown` endpoint in `main.py`

Returns the same shape as `pool_breakdown()`. Sits next to the
existing `/bankroll` endpoint, which is **unchanged**.

### 3. `tests/test_performance.py::TestPoolBreakdown` — 9 new tests

Coverage:

- Empty ledger → swing=5000, penny=2000, combined=7000
- Penny win → penny.balance increases, swing unchanged
- Penny loss → penny.balance decreases, swing unchanged
- Independent accumulation (both pools have trades)
- Zero-pnl rows (INITIAL seed) not counted as trades
- **Regression guard**: `current_bankroll()` still equals last ledger row,
  independent of `pool_breakdown()` — proves B-tight invariant
- Paper mode uses PENNY_PAPER_BANKROLL (Rs 500)
- Paper mode penny trades still tracked
- Response shape contract (every documented key present)

The regression-guard test (`test_current_bankroll_unaffected_by_penny`)
is the load-bearing one: it explicitly verifies that adding a penny
close moves `current_bankroll()` (because that's what `/bankroll` reads
and what `check_circuit_breakers` uses) but **does not** move
`pool_breakdown().swing.balance`. If a future commit accidentally
couples these, this test fails.

## What did NOT change (intentionally)

- `current_bankroll()` — still reads last ledger row.
- `check_circuit_breakers()` — still measures swing-only CB thresholds
  off `INITIAL_BANKROLL * CB_FLOOR_PCT` and `bankroll * CB_DAILY_LOSS_PCT`.
- `/bankroll` endpoint response — still `{"status": "ok", "bankroll": <float>}`.
- `INITIAL_BANKROLL = 5000.0` — unchanged.
- `PENNY_LIVE_BANKROLL = 2000.0` and `PENNY_PAPER_BANKROLL = 500.0` — unchanged.

## Operational impact after this lands

- New endpoint `/bankroll/breakdown` returns swing and penny balances
  side-by-side. Operators can verify that the penny pool is sized
  correctly (Rs 2,000 in live, Rs 500 in paper) and that penny P&L
  flows through.
- The existing `/bankroll` and circuit breakers behave exactly as
  before — no production behavior change beyond what 9203dd7 already
  enabled (penny closes now write to the ledger).

## Follow-up (not in this commit)

If the operator later wants B-combined semantics (single number scaled
to combined exposure), the cleanest path is:

1. Add a `PEAK_EXCLUDE_SOURCES` filter to `check_circuit_breakers()` so
   the `POOL_ALLOCATED` seed doesn't count toward peak.
2. Add a one-time seed row in `init_ledger` that increments bankroll
   by `PENNY_LIVE_BANKROLL`.
3. Switch `current_bankroll()` to a SUM-based aggregation across
   sources.

All three would require a separate deviation note and explicit sign-off
from Uru because they change swing CB math. **Do not do this without
asking.**