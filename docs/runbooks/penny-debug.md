# Penny Stock Subsystem — Operator Runbook

**Date:** 2026-06-21
**Owner:** Uru
**Spec:** `docs/superpowers/specs/2026-06-21-penny-stock-expansion-design.md`
**Plan:** `docs/superpowers/plans/2026-06-21-penny-stock-expansion.md`

## TL;DR

The penny subsystem runs in PARALLEL to the existing Nifty 500 system. It
has its own Rs 2,500 bankroll (Rs 500 paper + Rs 2,000 live opt-in), its own
universe, its own regime, and its own signal log. By default it's in PAPER
mode — no real orders. To enable live: set `PENNY_LIVE_TRADING=true` in
`python-engine/.env`.

## Quick diagnostics

### "Are penny scans running?"

```bash
# Look for these in logs every 30 seconds:
grep "penny_scan_done" /var/log/trading-sentinel.log | tail -5
# Expected: {"scan_id": "penny-...", "accept": N, "reject": M, "error": 0}
```

If you see no `penny_scan_done` log lines, the scheduler job `penny_scan_interval`
isn't registered. Check `main.py` imports + look for `penny_scan_interval` in
the apscheduler job list (set `SCHEDULER_DEBUG=1` to dump jobs at startup).

### "What regime is the penny subsystem in?"

```bash
curl -s http://localhost:8000/penny/regime/today   # when endpoint exists
# or
grep "penny_regime_computed" /var/log/trading-sentinel.log | tail -1
# Expected: {"regime": "PR1_CALM"|"PR2_ELEVATED"|"PR3_HOT"|"UNKNOWN", ...}
```

`PR3_HOT` is the kill-switch regime — no new entries will fire.

### "Is the kill-switch active?"

```bash
grep "penny_kill_switch_triggered" /var/log/trading-sentinel.log | tail -3
```

Daily loss exceeded 20% of `PENNY_LIVE_BANKROLL` (Rs 400). Resets at midnight
UTC (effectively 05:30 IST).

### "Are signals being accepted?"

```bash
# Last 10 penny signals (CSV is append-only):
tail -10 /data/penny_signals.csv
```

Columns: scan_id, scanned_at, ticker, leg, accepted, reject_reason, regime,
close, stop_loss, target_1, target_2, rsi_2, rsi_14, volume_ratio, breakout_level, shares.

```bash
# Win rate + reject-reason breakdown via analytics:
sqlite3 /data/cache.db "SELECT reject_reason, COUNT(*) FROM penny_signals \
  WHERE accepted=0 GROUP BY reject_reason ORDER BY 2 DESC LIMIT 10;"
```

### "What tickers are in the universe today?"

```bash
cat /data/penny_static.json | python3 -c "import json,sys; \
  d=json.load(sys.stdin); print(len(d['tickers']), 'tickers, as_of', d['as_of']); \
  print('Top 5 by ranking:'); \
  [print(' ', t['symbol'], 'Rs', t['prev_close'], 'promoter', t.get('promoter_holding_pct')) for t in d['tickers'][:5]]"
```

If the list is empty (0 tickers), the universe refresh job failed. Check:

```bash
grep "penny_universe_refresh" /var/log/trading-sentinel.log | tail -3
```

## Feature flag reference

All knobs in `python-engine/config.py` (auto-mapped from `python-engine/.env`):

| Flag | Default | Effect |
|---|---|---|
| `PENNY_LIVE_TRADING` | `False` | Set True to enable real orders |
| `PENNY_LIVE_BANKROLL` | `2000.0` | Rs amount for live sizing |
| `PENNY_PAPER_BANKROLL` | `500.0` | Rs amount for paper sizing |
| `PENNY_DISABLE_TICKERS` | `""` | Comma-separated ticker kill-switch |
| `PENNY_RISK_PCT_PR1` | `0.05` | PR1 per-trade risk (5%) |
| `PENNY_RISK_PCT_PR2` | `0.025` | PR2 per-trade risk (2.5%) |
| `PENNY_RISK_PCT_PR3` | `0.0` | PR3 size (0% — blocks all) |
| `PENNY_DAILY_KILL_SWITCH_PCT` | `0.20` | Daily loss limit (20% of bankroll) |
| `PENNY_PER_STOCK_CAP` | `500.0` | Hard per-stock cap (Rs) |
| `PENNY_MAX_POSITIONS_TOTAL` | `5` | Total concurrent positions |
| `PENNY_MAX_POSITIONS_CNC` | `2` | Max CNC positions |
| `PENNY_MAX_POSITIONS_MIS` | `3` | Max MIS positions |
| `PENNY_CONNORS_RSI2_BUY` | `10.0` | Connors RSI(2) trigger threshold |
| `PENNY_BREAKOUT_VOL_MULT` | `3.0` | Volume surge threshold (3x median) |
| `PENNY_BREAKOUT_TARGET_R` | `2.0` | Breakout target (2R) |
| `PENNY_SCAN_INTERVAL_SEC` | `30` | MIS polling cadence |
| `PENNY_CONNORS_TRAIL_ATR_MULT` | `2.0` | Post-T1 trail ATR multiplier |
| `PENNY_MIS_SMART_EOD_TIME` | `870` | 14:30 IST in minutes (smart-EOD) |
| `PENNY_MIS_SMART_EOD_WITHIN_R` | `0.5` | Within 0.5R of target = take profit |
| `PENNY_MIS_SMART_EOD_LOSS_MIN` | `30` | Cut loss if in loss >30 min |
| `PENNY_HOURLY_REPORT_START_HOUR` | `10` | First hourly report at HH:00 IST |
| `PENNY_HOURLY_REPORT_END_HOUR` | `14` | Last hourly report at HH:00 IST |
| `PENNY_HOURLY_REPORT_WEBHOOK` | `""` | Optional webhook URL for delivery |

## Emergency stops

| Action | How |
|---|---|
| Pause penny subsystem entirely | `PENNY_LIVE_TRADING=false` in `.env` + restart python-engine |
| Disable one ticker | `PENNY_DISABLE_TICKERS=XYZ` (append to existing list) + restart |
| Manual kill all open penny positions | `python -m penny_tools --action=panic-close` (NOT YET BUILT — see follow-ups) |
| Reset daily kill-switch | Restart python-engine (resets PennyRiskEngine in-memory state) |

## Rollout checklist

- [x] Spec approved by Uru (2026-06-21)
- [x] Plan approved by Uru
- [ ] Phase 2: code + tests + paper-trade (no real orders) — **CURRENT**
- [ ] Phase 3: 2 weeks of paper trading, review signal log
- [ ] Phase 4: backtest correlator run on paper data, surface suggestions
- [ ] Phase 5: Uru reviews paper P&L, flips `PENNY_LIVE_TRADING=true`
- [ ] Phase 6: live trade, iterate based on real data

## Hard go/no-go gates (before Phase 5)

- No crash in 2 weeks of paper-trade runs
- Signal count not down >50% vs Nifty momentum baseline
- No `penny_ticker_eval_failed` exceptions in logs
- No consecutive 0-signal days
- Win-rate of accepted paper trades > 50%
- No NaN/inf in `close`, `stop_loss`, `target_*` columns

If any gate fails, do NOT enable live trading. Open a Telegram thread.
