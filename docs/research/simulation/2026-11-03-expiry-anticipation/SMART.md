# Use the forecast only to allocate the extra lot

The monetary models are not robust standalone entries. Train-2024/test-2025
HERO_RETURN makes 3,642 / 3,483 ordinary/adverse, but with drawdown around 3,500,
much worse than E03.1, and backwards-year/causal tests fail. DOUBLE_RETURN loses.
That result is retained, not rescued by modifying its entry threshold.

One final primary hypothesis: **SMART_RUNNER25** retains E03.1 entry, strike,
stops, clock, profit floor and runner. It consults only the fixed past-quarter
5x mean-return model to decide whether to fund the extra second lot. Positive
forecast -> permit two lots when the original planned one and they fit the
1,562.50 reserve; otherwise the original size. Original multi-lot tickets stay
unchanged. This confines a weak general forecast to an existing promising entry.

Same 3,125 daily maximum, own 25,000 cash, max two sequential trades, same
absolute brakes; no leveraged/short position, new strike or recycled premium.
First 13 expiries are ordinary E03.1, because no trained model exists. Thereafter
only prior-quarter models from the already frozen causal HERO_RETURN fit may
be used. No retraining, test-label threshold selection, altered coefficients
or near-neighbour search. Missing exact contract/minute prediction means no
extra lot. Counterfactual E03.1 and **CLOCK_RUNNER25** (all original one-lot
tickets get the extra allowance after the same 13-day warmup) are controls.

This is a further seen-data iteration, not an independent test or newly proved
factor. Apply PLAN.md's original 25%-risk-adjusted acceptance and loss limits;
do not lower them to make a version number. Report gain versus actual reserve
used as a diagnostic too, but not as a substitute for worst-case-risk limits.
Freeze this source/tests before any SMART book score. No engine/flag/live risk
change, protected 2023 or future exam access, download or deployment.
