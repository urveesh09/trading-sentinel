# Self-Improvement Analytics — Trading Sentinel

**Branch:** `feat/momentum-regime-aware`
**Date:** 2026-06-16
**Scope:** Analytics layer that turns the signal-log + trade data into
actionable strategy changes. The system can now read its own output.

---

## What it does

Three things, all from the data we already persist:

1. **Gate-funnel report** — counts which MC-gate rejection reasons kill the
   most signals. The first place to look when "I'm getting too few / too many
   signals" or "entries aren't great."
2. **Outcome correlator** — joins closed trades with their original signal-log
   row to compute "what was the gate fingerprint of trades that won vs lost."
3. **Strategy suggestions** — turns (1) + (2) into 3-5 actionable changes
   the operator can A/B. Always returns reasoning + the data backing it.

---

## How to use

### CLI (terminal, human-readable)
```bash
cd ~/trading-sentinel/python-engine
.venv/bin/python -m analytics --days 14
```

Sample output (empty system):
```
======================================================================
  TRADING SENTINEL — ANALYTICS REPORT (last 14 days)
  As of: 2026-06-17T...
======================================================================

[1] GATE FUNNEL
    Scanned:   142
    Accepted:  8
    Rejected:  134 (94.4%)
    Top rejection reasons:
      MC0_too_early                  ████████████████████  78
      MC3_volume_surge_insufficient  ████████              32
      no_recent_vwap_crossover       ████                  18
      ...

[2] OUTCOME CORRELATION
    Trades:    12  (5W / 7L)
    Win rate:  41.7%
    Avg R:     0.380  (W: 1.420, L: -0.460)
    Predictive gates: volume_ratio
    By regime:
      REGIME_1_NORMAL          n=8   win=62%  avg_r=0.85
      REGIME_2_ELEVATED        n=3   win=33%  avg_r=-0.20
      REGIME_3_CRISIS          n=1   win=0%   avg_r=-0.50

[3] SUGGESTIONS
    1. [HIGH] 'MC0_too_early' kills 58% of signals
       Evidence: 78 of 134 rejections in last 14 days
       Action:   Consider lowering MOMENTUM_ENTRY_START_MIN from 45 to 30
    2. [HIGH] Winners have higher volume_ratio (3.2) than losers (1.4)
       Evidence: volume_ratio avg differs by 1.80 between winner/loser cohorts
       Action:   Consider raising the volume_ratio floor (require higher value to pass)
    3. [MEDIUM]  REGIME_1_NORMAL wins 62% but REGIME_2_ELEVATED wins 33%
       Evidence: R1: 8 trades, R2: 3 trades
       Action:   Consider disabling REGIME_2_ELEVATED entries until more data confirms edge
```

### HTTP API (JSON, for the dashboard)
| Endpoint | What it returns |
|----------|-----------------|
| `GET /analytics/funnel?days=7` | Gate rejection counts |
| `GET /analytics/outcomes?days=14` | Win rate, avg R, predictive gates |
| `GET /analytics/suggestions?days=14` | Same as CLI but JSON |
| `GET /rejected?days=7` | (legacy, still works) |

All endpoints read from the production DB. No writes. Safe to poll.

### How it learns (data flow)

```
momentum scan fires
   ↓
every ticker evaluated → logged to momentum_signals (CSV + SQLite)
   ↓
position closed (auto-square or manual) → record_trade_close in performance.py
   ↓
record_trade_outcome in analytics.py joins the close with the signal-log row
   ↓
trade_outcomes table accumulates (ticker, P&L, R-multiple, gate fingerprint)
   ↓
you run `python -m analytics --days 14` weekly → read suggestions → flip a knob
```

---

## Suggestion rules (priority order)

| # | Trigger | Suggestion |
|---|---------|------------|
| 1 | 1 reason > 40% of rejections (n≥10) | "Bottleneck gate. Consider relaxing it." |
| 2 | Gate field differs > 20% between winners/losers (n≥10) | "Predictive gate. Consider tightening the side that's worse for winners." |
| 3 | Win rate < 40% (n≥10) | "Tighten the entry bar — enable MOMENTUM_USE_RVOL=True." |
| 4 | avg_r_losers < -1.5R | "Oversized losers. Tighten stop or reduce size." |
| 5 | R1 win rate > 60% AND R2/R3 < 40% (n≥5 each) | "R1 is your edge. Consider disabling other regimes until more data." |
| (fallback) | n < 5 trades | "Insufficient data. Re-run in 7-14 days." |

Confidence levels:
- **HIGH** = n ≥ 20 trades
- **MEDIUM** = 5-20 trades
- **LOW** = < 5 trades

The system never makes changes on its own. It surfaces the data + an action
suggestion. You flip the knob.

---

## Files

- `python-engine/analytics.py` — NEW. Module: `gate_funnel_report`,
  `outcome_correlator`, `strategy_suggestions`, `record_trade_outcome`,
  `print_report`, plus `init_analytics_db` for the schema.
- `python-engine/performance.py` — `record_trade_close` now also calls
  `record_trade_outcome` (best-effort, can't break the ledger).
- `python-engine/main.py` — init analytics DB at startup, 3 new HTTP
  endpoints, r_multiple + notes passed through to the ledger on close.
- `python-engine/tests/test_analytics.py` — NEW. 17 tests covering schema,
  funnel, correlator, suggestions, CLI.

---

## What did NOT change

- Existing `/positions`, `/signals`, `/performance` endpoints — unchanged
- Strategy logic in `engine.py` — unchanged (the suggestions tell YOU what
  to change, not the system)
- Signal-log (signal_log.py) — unchanged
- All pre-existing tests — still pass (422/423, 1 pre-existing skip)

## Known limitations

- **Small sample = noisy suggestions.** Run weekly, not daily, until you
  have 30+ trades per regime.
- **Causation vs correlation.** "Winners have higher volume_ratio" doesn't
  mean raising the floor will help — it might just be descriptive. Treat
  suggestions as hypotheses to A/B, not commands to execute.
- **No backtest integration yet.** The correlator looks at LIVE trades only.
  A future PR can replay historical signal-log rows through the engine with
  hypothetical new gates. The `raw` JSON column in momentum_signals
  preserves everything needed for that.
