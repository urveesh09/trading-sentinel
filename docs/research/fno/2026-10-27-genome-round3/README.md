# O27f: genome round 3. New entry families, option-contract genes, a walk-forward of the search itself, and a random-entry null

Status: **frozen before scoring** (this file is replaced by the results write-up after the run). Research only. Production is read-only, and no paper, live or forward-panel rule changes.

## Why a third round

O27 (360-arm grid), O27b (17-gene ORB evolution) and O27e (efficiency, compression and failed-auction families) all searched the same 29 seen sessions. O27e's best arm made more money than the shipped book, but its drawdown was larger and its neighbouring settings were unstable.

Neither round could answer the question that matters: **does searching this data find anything that holds up on sessions the search did not see?** This round adds two tools to answer it:

1. **An anchored walk-forward of the whole search procedure.** The pool, the evolution and the plateau pick are re-run per fold, using only sessions before that fold's test block:
   - F1: train Sep 10 – Sep 30, test Oct 1 – Oct 9.
   - F2: train to Oct 9, test Oct 12 – Oct 16.
   - F3: train to Oct 16, test Oct 19 – Oct 26.

   The three test blocks give 16 out-of-sample sessions for the procedure, not for one hand-picked genome. A FINAL fold searches all 29 sessions and yields a forward-test candidate only.
2. **A random-entry NULL family searched with the same budget.** It has the same shared genes and exits, but its entries come from a seeded coin. Whatever fitness and out-of-sample profit the NULL track reaches is what search on noise alone produces. The real families must beat it.

## What is new in the genome

- **Entry families** (none were in O27, O27b or O27e):
  - TREND_PULLBACK: on an established trend day, a VWAP or EMA20 pullback followed by a resumption bar.
  - PDL_BREAK: a close through the prior day's high or low.
  - VWAP_BAND: a close through VWAP ± k session σ, with VWAP sloping the same way.
  - MOMO_BURST: an N-bar move of at least m ATR with every bar the same colour.
  - ENSEMBLE: votes across six sub-signals (OR20 break, the O27e efficiency break, PDL, VWB, TPB, MOMO); k = 1 is a union of signals, k = 2 needs agreement.
- **New genes:**
  - SENSEX cross-index confirmation;
  - multi-day trend alignment (prior close against the prior five closes);
  - AM or PM entry windows;
  - a VWAP-lost exit;
  - option strike depth (target delta 0.55 or 0.65, never OTM);
  - expiry week (nearest or next).
- **Crossover across families:** shared genes (filters, exits, contract) mix between families; entry genes stay with their family.

## Fixed contract (see `freeze.json`)

- **The book:** every genome is replayed once over Sep 10 – Oct 26 through the shipped single-leg book: planner, sizing, brakes, exit ladder at about 60 s, costs, ask entry and bid exit.
  - `LabReplay` copies `SingleLegReplay._entry` with three marked changes: the lab signal, the expiry week, and the target delta during planning.
  - The run aborts unless the copy with no genome trades exactly as the shipped book (13 trades, ₹10,801.09).
- **Fitness on a fold's training sessions:** (net − best day) / max(closed-trade drawdown, ₹1,000) + (green weeks − red weeks) / weeks, minus 1 if the fixed-trade stressed net ≤ 0. Below max(6, 35% of sessions) trades, the score is −5 + trades / min.
- **Pick:** of the five best training-fitness genomes the fold itself evaluated, the one with the highest plateau (the median fitness of the genome and all its one-step neighbours).
- **Verdict rule:** the search works only if the REAL out-of-sample result over the 16 test sessions:
  - is above zero;
  - beats SHIPPED on the same sessions;
  - beats the NULL track;
  - has at least 2 of 3 folds above zero.
- **Disclosure:** every session is seen. A 12-genome timing smoke test ran before the freeze. It removed only the delta 0.75 allele, which the shipped risk cap leaves almost always unaffordable.

## Run

```
python-engine\winvenv\Scripts\python.exe docs\research\fno\2026-10-27-genome-round3\lab.py freeze
(commit freeze.json, lab.py, test_lab.py)
python-engine\winvenv\Scripts\python.exe docs\research\fno\2026-10-27-genome-round3\lab.py run --jobs 8
```
