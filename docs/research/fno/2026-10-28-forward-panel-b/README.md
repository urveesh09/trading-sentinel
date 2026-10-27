# O27g: forward panel B, the O27f picks and the O27e efficiency break against a random-entry control (Oct 28 – Nov 27)

Research only. No arm trades: each is replayed through the shipped single-leg book on sessions that did not exist when it was frozen. Production's paper and live books, the proving week and panel A (O27c) are unchanged.

## Why

O27f showed that on the 29 archived sessions the past does not rank the future, and that random entries with good exits also made money. Only forward sessions can tell skill from luck.

Panel A (O27c) already forward-tests the O27 and O27b arms. Panel B adds:

- this round's candidates;
- the O27e efficiency break, which was never forward-tested;
- **a random-entry control**, so a candidate has to beat luck as well as the shipped book.

## Arms (frozen in `freeze.json` before the first forward session)

| Arm | What it is | Where it came from |
| --- | --- | --- |
| SHIPPED | The live single-leg book, as configured | Control (same as panel A) |
| O27F_TREND_PULLBACK | Trend day from 11:30 (≥ 1.5 ATR from open, ≥ 75% of closes on the trend side of VWAP); pullback within 0.5 ATR of VWAP; resumption bar; stop 1.5 ATR, 3R, 120-min time stop, 2-ATR trail, no lock | O27f FINAL pick (frozen rule) |
| O27F_ENSEMBLE_EFF_MOMO | Efficiency break and momentum burst agreeing within 3 bars, before 12:30, RVOL ≥ 0.8; stop 2 ATR, 2.4R, LOOSE exit | O27f best fitness |
| O27E_EFFICIENCY_BREAK | Break of the prior four 5-min bars, path efficiency ≥ 0.35, body ≥ 0.55, RVOL ≥ 1.2; stop 2 ATR, 1.8R, LOOSE exit | O27e finalist |
| NULL_CONTROL | Random entries (seeded coin, p = 0.04 per bar) after 11:30 with the multi-day trend, RVOL ≥ 0.8; stop 2 ATR, 1.8R, LATE exit, VWAP-lost exit | O27f NULL track's FINAL pick |

## Rule (frozen)

**A candidate is promising** when it passes panel A's checks:

- at least 5 forward trades;
- net above zero;
- net without its best day above zero;
- net above SHIPPED;
- maximum drawdown no more than max(1.5 × SHIPPED's, ₹5,000).

It must **also have a net above NULL_CONTROL**.

The rule is read once, after Nov 27. Interim reports are provisional: nothing is promoted or dropped early. A promising arm is only a candidate for the owner's decision, through Dev → GitHub → Production, never during a proving week. The real-money test keeps mirroring the paper book until the owner says otherwise.

## How it runs

`panel_b.py run` performs these steps:

1. A fresh read-only export, using panel A's exporter (a throwaway container with the data volume mounted read-only, `--include-finished-today`).
2. A replay of every arm from Oct 28 to the newest exported session.
3. It writes `_local/REPORT.md`, `_local/latest.json` and `_local/history.jsonl`.

The run refuses to start if any bound source or the effective F&O settings changed since the freeze.

- **Pinned copy:** `C:\Users\Urveesh\sentinel-operations\fno-forward-panel-b-20261028\`.
- **Schedule:** panel A's daily 16:00 launcher calls `run_panel_b.cmd` after panel A, so the one scheduled task covers both. The report is at `docs\research\fno\2026-10-28-forward-panel-b\_local\REPORT.md` inside the pinned copy.

## Tests

`test_panel_b.py` has 3 tests:

- every arm replays exactly as its study did (SHIPPED as the O27 CURRENT arm, the O27f arms as their O27f replays, O27e as its FULL replay) over Sep 10–30;
- the freeze matches the panel and predates the window;
- a candidate that does not beat the random-entry control is never promising.
