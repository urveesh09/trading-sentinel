# Nonlinear check: does the combination of factors matter?

The selective fixed-quarter SMART allocator adds only 90.84 ordinary / 42.09
adverse over two years, worsens drawdown and loses versus E03.1 in 2024. Rejected.
Linear forecasts may miss feature interactions, so one final method tests that
limitation, without a grid or more feature/outcome selection.

Two primary models, **DOUBLE_FOREST** and **HERO_FOREST**, reuse RETURNS.md's
same bounded adverse monetary targets, frozen 16 causal features plus missing
indicators, preprocessing, 1,250/2,500 old risk limits and whole-book mechanics.
The only change is the fixed forecasting method:

- 64 regression trees, seed 314159, bootstrap **whole expiry days**, not rows.
- Maximum depth two; at each node randomly consider sqrt(feature count)
  features and only their training 25/50/75 percentiles as splits.
- Every child needs at least six distinct positively weighted training days.
  Select the largest positive weighted squared-error reduction, never test PnL.
- Every leaf's mean is shrunk by eight day-equivalents toward the bag's global
  training mean. No minimum probabilities, posterior tuning or test-set leaves.
- Average tree forecasts; admit only positive predicted after-cost return.
  Use the same current-direction comparison, hard stop/target/time policy,
  cash/brakes and actual costs as the original return-model portfolios.

One-year transfer, backward-year diagnostic apart and the same prior-quarter
92-day causal evaluation. No selecting the best tree, seed, threshold, depth,
feature, year or split afterwards. This is nonlinear interaction testing, not
an assertion of causal factors or independent market validation. Top-5% and
top-1% precision/mean-return diagnostics may describe forecast ranking but do
not become a hindsight daily entry rule or summed overlapping-event profit.

Apply the same PRECURSORS.md portfolio acceptance. Preserve every result.
If failed, conclude the tested feature families have not earned a tradable
anticipation model here; do not claim every possible factor or faster feed
has been disproved. No engine/config/flag/schema/Production/download change.
Source/tests frozen before these models are fit.
