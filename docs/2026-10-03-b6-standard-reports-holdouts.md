# B6 — Standard reports and holdout guard (Dev only)

**Independent review correction:** see
[current status and remaining acceptance](2026-10-03-post-implementation-independent-review.md).
This is a reporting/date-guard slice; the original B6 is not complete.

`backtest_cli report` now returns `standard_metrics` derived only from archived
closed-trade fields. It reports gross/net/costs, turnover/exposure/holding,
win-loss, MFE/MAE, monthly net and winner exclusion only when those fields are
actually present; otherwise they are `null`. Risk-adjusted performance is
always `null` unless a valid marked equity clock plus capital base is archived
(none of the current adapters supplies both). Evaluator-only results therefore
cannot acquire invented P&L.

`run --holdout-from YYYY-MM-DD --holdout-to YYYY-MM-DD` records an archived
interval that must start after the development window. New declarations are
`DECLARED_UNVERIFIED` and `untouched_verified=false`; they do not prove a
prospective policy freeze, absence of observation or lack of prior selection.
`compare` now
requires the same snapshot, chronology, fidelity scope and holdout declaration.
It rejects overlap and incompatible reports. The report's bootstrap is a
deterministically seeded IID closed-trade sample interval, explicitly not a
profitability verdict and not a correction for overlap/selection dependence.

Focused verification:

`python-engine/winvenv/Scripts/python.exe -m pytest python-engine/tests/test_backtest_cli.py python-engine/tests/test_backtest_lab.py python-engine/tests/test_momentum_replay.py -q`

returned **37 passed** with one existing httpx deprecation warning. No broker,
order path, strategy policy, runtime setting, Production file/database,
migration, push or deployment changed. B5 remains excluded. This delivers the
bounded reporting slice. Prospective holdouts, complete manifest compatibility,
session-block uncertainty and marked portfolio evidence remain open in the
original plan. Reporting corrections leave incomplete aggregate fields null,
expose coverage and subtract only positive winners in winner-exclusion metrics.
