# B3 — Swing and EDGE daily evaluator replay (Dev only)

## Problem

The historical `swing_regime_daily` adapter is a labelled proxy: it uses the
tested share as NIFTY and supplies neutral market context. The old
`penny_edge_backtest.py` has older hard-coded sizing, threshold and fill
assumptions. Neither is evidence that the currently shipped daily scanner made
the recorded live decisions.

## Delivered contract

Two Backtest Lab adapters use only a frozen daily snapshot and are both
`EVALUATOR`, never a trade or portfolio backtest:

| Adapter | Shipped code called | Declared boundary |
| --- | --- | --- |
| `swing_regime_daily_evaluator` | `engine.evaluate_signal` | Explicit stock/NIFTY 50/NIFTY BANK history, one before-open regime update per session, then one decision per stock. |
| `penny_edge_daily_evaluator` | `penny_edge_live.scan_today` | Explicit stock universe plus the scanner's NIFTYBEES proxy, with the actual orchestrator defaults `max_positions=3`, `min_strength=0.45`. |

The former proxy Swing adapter remains available and labelled `PROXY`; it was
not upgraded by name. The catalogue now says Swing and EDGE have evaluator
coverage, not a historical portfolio.

Daily bar D is never visible to the Swing before-open decision for D. EDGE
uses the shipped scan against a frozen temporary SQLite cache; its daily-bar
decision is labelled available only after D's session. Missing index, universe
or warm-up evidence is unavailable/a skip, not a substitute proxy or fill.

## Improvement found while binding the actual evaluator

`engine.calc_rsi_series` indexed `gains[i]`/`losses[i]` while iterating a
length-`n` close series. Those delta arrays end at `n-2`; enough history raised
`IndexError` before the live Swing evaluator could run. It now reads the delta
for close `i` at `i - 1`, with a regression test. This is a correctness fix,
not a strategy tuning change.

## Verification

- The Swing test spies on the shipped evaluator and proves every supplied stock
  history ends before its decision date.
- The EDGE test proves the exact scanner is called with frozen configuration
  and a temporary snapshot, never the source database.
- `python-engine/winvenv/Scripts/python.exe -m pytest python-engine/tests/test_backtest_lab.py python-engine/tests/test_engine.py python-engine/tests/test_entry_v2_gates.py -q`
  returned **149 passed**; one pre-existing httpx deprecation warning remained.

## Limits, rollout and rollback

No broker, order, runtime scheduler, allocation, strategy threshold, Production
file or database was changed. Historical live scheduler calls, full
constituent-breadth ranks, historical event-calendar snapshots, manual Telegram
approval, actual entry fills, exits, cash reservation and position overlap are
not archived by this adapter. Those limits prevent a profit or deployment
claim. B4 covers Momentum and Range with explicit scope; B6 adds report/holdout
controls. Reverting this work removes only the research adapters and preserves
already archived reports.

**State:** Dev only; not pushed, deployed or promoted.
