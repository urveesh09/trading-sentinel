# Second objective, fixed before fitting: forecast money instead of a rare event

The first two binary forecasts trade nothing. Their probability hurdle assumes
every non-hit loses the entire premium, despite an intended 35% stop. That is
conservative but can miss an economically useful low-win-rate rule. Do not
lower that hurdle until a chosen backtest wins or overwrite its zero-trade result.

Two new primary experiments use exactly the already frozen features, causal
labels, one-lot 2x/5x exits, fees, cash/risk/cooldown and calendars:

- **DOUBLE_RETURN**: regularized forecast of actual adverse one-lot net return
  divided by its actual entry premium, using the 2x policy's historical label.
- **HERO_RETURN**: the corresponding 5x policy. This predicts the entire
  outcome distribution's mean, rather than just a rare successful target.

No-entry outcomes have zero return and remain represented. Missing exits retain
the conservative full-premium-loss training label and count, never a positive
mark or removed loser. Wins are capped in training at target multiple minus
one, losses at -1.25 (premium plus fee allowance). These fixed caps prevent
one overshoot or bad-data tail from dominating the fit. Actual funded-book
results are **never clipped**. No future entry price or label is an input feature.

One L2 linear regression per target, coefficient penalty 1.0, training-only
median imputation/weighted standardization and missing indicators from the
original forecast implementation. Each expiry day totals weight one. No
hyperparameter search. Predictions clipped to those same physical training
bounds. Trade only a strictly positive predicted net return; if both current
directions qualify, use the larger current prediction. No day's future best
score or hindsight ranking. Same one-lot, 1,250 ticket / 2,500 daily reserve,
25,000 own cash, two sequential entries, absolute brakes and 35% hard stop.

Train 2024/test 2025, backwards-year diagnostic apart, and past-only quarterly
refits after 13 training expiries, all exactly as PRECURSORS.md. These are two
previously seen years, not a new independent exam. Same acceptance: beat
matched E03.1 ordinary/adverse and ex-best positive, worst day >=-750, realized
drawdown <=2,000, no unresolved, and pass the 2024-to-2025 transfer. Additional
risk combinations cannot rescue a failure. Source/tests committed before fit.
No engine, settings, flags, Production, download or live money changes.
