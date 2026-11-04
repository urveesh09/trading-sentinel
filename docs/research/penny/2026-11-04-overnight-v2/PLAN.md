# Penny overnight v2 — plan (written before any new arm was scored)

Owner request (Nov 4, 2026): a much better Penny strategy, by iterations that
learn from each failure, genome search allowed, any architecture or execution
change allowed. Built on the other agent's study
(`../2026-11-04-strategy-search/REPORT.md`, e0ad826) and its lessons.

## What the earlier work got wrong or left open

1. **Universe.** The earlier search used a fixed 108-stock cohort. The live
   overnight book ranks ~1,100 non-SME tickers in the Rs 4–60 band; six of its
   first seven live picks were outside the old tested list. Here: the broad band
   universe (Kite cache copy, 1,535 tickers; public Yahoo, 867 names).
2. **Execution was treated as fixed.** Production's forward record (Oct 21) split
   the edge: close->open +0.77%/trade, entry paid at the ask 0.36%, charges 0.42%.
   The costs, not the signal, take the edge. The earlier study stressed costs up
   but never tried to *lower* them.
3. **Fee economics were mistaken for alpha.** "Two slots" helped mostly because
   the fixed DP charge (Rs 15.34 per scrip per sell day) weighs less on bigger
   tickets. Treat ticket size as an explicit design variable.
4. **Selection by in-sample rank.** Use walk-forward of the whole selection
   procedure and a random-pick null with the same budget (F&O O27f lesson).

## Data (fingerprints in `data-manifest.json`)

| Panel | Source | Span | Use |
|---|---|---|---|
| K | stopped-Production Kite daily cache copy (Oct 3) | 2025-07-01 – 2026-10-01, 310 sessions | development (already seen by the Oct 7 live-universe study) |
| Y-DEV | public Yahoo daily, 874 requested names | 2023-01-01 – 2026-11-03 | development / walk-forward |
| **Y-EXAM** | same pull | **2019-04-01 – 2022-12-30** | **sealed exam, opened once for frozen finalists** |

Y-EXAM caveats, declared now: 144 of the 874 names were in the earlier study's
153-name universe, which trained on 2019–2022 (its G05 screen). Universe is
2025–26 band membership (survivorship). Yahoo prices are split-adjusted; each
split ticker's history before its last split is dropped. Zero-volume rows are
not sessions. No Breeze, broker or Production call was made for any panel.

## Lab and parity

`lab.py` precomputes the shipped EDGE evaluators per session and replays an
own-cash overnight book. It reproduced the shipped `run_overnight_book`
(split_cash, runtime realism refusals, close +25 bp / open −5 bp) exactly on
Kite Jul 15 – Oct 31 2025: 175 closes, 0 mismatches, net equal to 4 decimals,
cost arithmetic identical to `calc_penny_costs` (`parity-2025-07-15-2025-10-31.json`).

## Execution models (every comparison is made inside one model)

- `E25`: close +25 bp, open −5 bp (the paper book's model).
- `E36`: close +36 bp, open −5 bp (Production's measured average entry premium).
- `PC`: official close, open −5 bp — the NSE post-close session (15:40–16:00)
  fills CNC market orders at the official close. Fill rate unknown: also scored
  at 50% deterministic fill and with adverse fill bounds.
- `E60`: close +60 bp, open −20 bp (stress).

A selection/sizing change counts only if it wins **inside the same model**.
An execution change is reported as a separate, conditional value.

## Exam rule (frozen now; applied once on Y-EXAM, Rs 25,000 own cash, compounding)

For each finalist C against the incumbent BASE (shipped book, 3 slots) under
E36 and under PC:
1. at least 100 closes; net > 0 and net excluding the best trade > 0;
2. net > BASE net;
3. peak-relative drawdown <= max(1.5 x BASE's, 15%);
4. positive in at least 3 of the 4 exam years (2019 from April);
5. selection null: net above the 90th percentile of 200 books that pick at
   random from the same eligible pool with the same slots and sizing.

"Pass" means: worth a forward paper shadow. It never means qualified or live.

## Rollout / rollback (if anything passes)

Forward shadow beside the paper book, own cash, declared before scoring, with a
one-line flag rollback; post-close fill measurement is read-only (no orders).
Any real-money probe of post-close fills is the owner's call.
