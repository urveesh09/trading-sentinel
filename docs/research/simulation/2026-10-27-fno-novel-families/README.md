# O27e: new entry families and bounded genetic research

**All archived dates are seen. No untouched validation or profit guarantee.**
Production and the pinned O27c forward panel remain unchanged.

Question: do genuinely different futures-entry predicates yield a more stable
single-leg research candidate than another combination of the existing ORB genes?

- EFFICIENCY_BREAK: fresh rolling-channel break with directional efficiency,
  candle body and optional session-VWAP slope agreement.
- COMPRESSION_RELEASE: the same fresh break, restricted to a compressed preceding
  rolling range measured in prior-bar ATR units.
- FAILED_AUCTION: a completed close beyond the opening range followed by a close
  back inside, after displacement from VWAP in a low-efficiency path. Buy the
  opposite option direction; stops cover the failed excursion.

These mechanisms are new relative to O27/O27b's 17 ORB genes. MOMO, PULLBACK and
FADE were explored previously; this study does not claim to invent those concepts.
Shared stops, targets, RVOL and exits are inherited parameters, not new discoveries.

Search: three separate populations of eight, five generations, fixed seed,
tournament selection, crossover, mutation and immigrants. Evaluate each family
leader's one-step neighbours and freeze two finalists before the late-period
diagnostic. Numeric rules and every allele are in `freeze.json` and `lab.py`.
Inactive compression alleles are canonicalized rather than counted as new strategies.

Data: existing hash-verified Production export, September 10–October 26, 29 sessions.
Search: September 10–October 9. Later diagnostic: October 12–26, **also seen**.
The search is exploratory even though its later diagnostics are hidden from its
fitness function. No existing forward panel is edited or extended.

The original planner, costs, sizing, loss brakes, entry grid and exit ladder are
reused. Primary fills inherit bid-or-LTP exits to reproduce the prior control;
separate stricter diagnostics require displayed max-lot depth at entry and a bid
with full held-quantity depth at exit. Those diagnostics change admission and are
not live parity. Neither mode models real broker fills or shared capital across books.

The preserved inherited limitations include a quote-derived expiry catalogue,
logged regimes, exogenous spread closes, minute-sampled option observations and
unpriced holds outside the recorded strike window. No weekday or theoretical
option price is substituted. Drawdown is on closed-trade P&L, not marked equity.

Research references (ideas, not evidence of an Indian-options edge):
- CME, systematic trend and mean-reversion approaches:
  https://www.cmegroup.com/content/dam/cmegroup/education/files/big-data-investment-management-the-potential-to-quantify-traditionally-qualitative-factors.pdf
- Bailey, selection bias and backtest overfitting:
  https://www.davidhbailey.com/dhbtalks/dhb-jbcc-fin.pdf

## Reproduce

From Dev, with the existing venv, before any scoring:

```powershell
python-engine/winvenv/Scripts/python.exe -m pytest docs/research/simulation/2026-10-27-fno-novel-families/test_lab.py -q
python-engine/winvenv/Scripts/python.exe docs/research/simulation/2026-10-27-fno-novel-families/lab.py freeze
# Commit frozen source, tests, README, configuration and freeze before run.
python-engine/winvenv/Scripts/python.exe docs/research/simulation/2026-10-27-fno-novel-families/lab.py run --jobs 6
```

The runner refuses overwritten results, uncommitted freezes and changed bindings.
Raw quote files, private caches and detailed arm receipts remain under ignored
`_local/`. A restarted interrupted search needs an explicit recovery; never delete
the evidence to pretend it did not run.

## Results

Pending. No study result has been computed at the time this section is frozen.

## Completed results (post-score)

See [learning and results](ANALYSIS.md), [completion/audit notes](COMPLETION.md),
[all evaluated arms](results.json), [independent audit](audit.json) and
[commit-aware verification](verification.json).

The frozen search evaluated 121 distinct genomes in three new entry families.
Efficiency break modeled +INR 31,063.33 versus shipped +10,801.09, but its INR
6,748.74 closed-trade drawdown fails the frozen later-period cap and neighbour
sensitivity is weak. No candidate qualifies. All dates are previously seen.

57 focused tests pass. The unmodified generic helper's REPORT remains INVALID
because its original HEAD pin predates the mandatory freeze commit; that failure
and the separate unchanged-source/raw-ledger audit are explained in COMPLETION.
No Production/paper/forward-panel change or push/deployment was made.
