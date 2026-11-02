# Independent checker correction — no policy or P&L changed

The first full carry audits failed at terminal cash:

- 2023: recomputed217166.626037 versus saved trade sum217166.3259.
- 2024: recomputed247167.472127 versus saved trade sum247167.3819.

`audit_n101.py` at controls commit `f4f92f2` used each trade's displayed
`extra_cost` to rebuild cash. The old risk-spectrum writer deliberately records
that display rounded to TWO decimals while subtracting the FULL cost function
from cash/P&L. At the declared199 base/4.975 quadratic cost, one lot costs
203.975; its display is203.97 (binary rounding), half a paise less. That
accumulates across trades. Each individual comparison passed its small tolerance
but the terminal comparison correctly failed. Original failures are retained
here; the original checker source is in Git. They were not passing audits.

The corrected independent checker computes `(base + quadratic*lots)*lots` from
the frozen book configuration. It still checks the rounded display separately.
It does NOT widen the existing cash tolerance or alter a rule, receipt, trade,
cost schedule, budget, cash or score. A regression fixes the half-paise case.
All annual/trading/source/input freezes remain original and unchanged.

Other pre-audit checker details: opening equity is the evaluation's
`notes.start_equity`, not a top-level key; same-time cash settlements preserve
their existing sequence. These were corrected before the first full audit.
