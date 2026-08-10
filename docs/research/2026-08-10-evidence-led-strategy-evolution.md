# Evidence-led strategy evolution — 2026-08-10

## Decision

Do not increase live allocation or weaken live gates yet. Production has not
demonstrated positive expectancy. Increase activity through isolated paper
variants, replay them with frozen datasets, and promote only when net results
survive costs and out-of-sample checks.

This document is a research and release protocol, not a profit promise.

## Production baseline (read-only audit, through 2026-08-10 ~14:10 IST)

The authoritative runtime database was `/data/cache.db` in the Production
Docker volume. No Production files or state were changed during the audit.

| Book | Mode | Closed sample | Recorded net P&L | Key observation |
|---|---:|---:|---:|---|
| Momentum | live | 24 ledger closes | -Rs 137.28 | 195 accepts from 254,653 evaluations (0.0766%) |
| Edge | live | 7 ledger closes | +Rs 8.43 | Ledger and current position history disagree |
| Momentum | paper | 3 ledger closes | -Rs 677.62 | Sample is too small and all three lost |
| Edge | paper | 11 ledger closes | -Rs 1,974.13 | Ledger and current position history disagree |
| F&O vanilla + defined risk | paper | 22 ledger closes | -Rs 16,046.41 | Costs and stop cohorts dominate |

Additional evidence:

- Momentum evaluated 254,653 rows and accepted 195. Rejections were dominated
  by `no_recent_vwap_crossover` (79.3%), then insufficient volume surge
  (12.5%), then failure to hold VWAP (5.0%).
- Penny evaluated 1,061,215 rows and accepted 48. The largest recorded blockers
  were volume, the entry time window, historical evaluator `None` results, and
  breakout confirmation. Raw accepts are inflated by repeat accepts for the
  same ticker/day (21 for ALMONDZ on one day and 25 for KCPSUGIND on another).
- F&O evaluated 1,062 rows and accepted 16. `no_or_break` (557) and
  `not_fresh_break` (431) dominate; low RVOL accounts for only 29 rejects.
- F&O vanilla exits were negative for time stops (-Rs 7,009.77), underlying
  stops (-Rs 7,642.48), and the premium backstop (-Rs 3,570.34). Only the two
  trail-stop exits were positive (+Rs 2,869.31).
- Defined-risk F&O gross loss was only about Rs 18.74, but Rs 674.39 of costs
  made the six-trade sample materially negative.
- Ledger and position histories disagree for several books. Ledger is cash
  truth; position rows are reconciliation evidence until stable trade IDs are
  present end to end.

## Research constraints

1. Every candidate runs paper-only and must be incapable of calling broker
   order methods.
2. Baseline and candidate consume the same immutable data snapshot. Store a
   dataset fingerprint, full configuration, fill assumptions, fees, slippage,
   code version, and warnings with each run.
3. A scan evaluation is not a trade. The funnel must distinguish raw
   evaluation, qualifying signal, distinct ticker/day candidate, portfolio-gate
   pass, paper order, live order, fill, and close.
4. Deduplicate at least by `(strategy, variant, trading_date, ticker,
   direction)` before reporting opportunity counts.
5. Optimize net expectancy subject to drawdown and capacity. Raw trade count is
   a diagnostic, never the objective.
6. Never derive intraday live parameters from the Penny daily proxy. Do not use
   the F&O synthetic-option replay as proof of live option-chain performance.

These constraints follow the known risk of backtest selection bias and
overfitting described by Bailey et al., *The Probability of Backtest
Overfitting* (2015):
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253

Kite historical candles provide timestamp, OHLC, volume and optionally OI, but
expired option instrument tokens are not generally recoverable unless cached;
continuous history applies to futures daily candles, not a reconstructed option
chain. That is why F&O option-chain assumptions must remain explicit:
https://kite.trade/docs/connect/v3/historical/

## Paper experiment A — Momentum crossover recency

### Hypothesis

The three-candle VWAP-cross window creates unnecessary timing blindness. A
five-candle window can admit valid continuation setups without accepting a
resident, exhausted move if distance and hold-quality guards remain intact.

### Variants

- `MOM_BASE`: existing three-candle crossover and current volume thresholds.
- `MOM_RECENCY_5`: last five 15-minute candles; require current close above
  VWAP, current close in the top 20% of the session range, existing ATR-fuel and
  morphology gates, and entry no farther than 0.50 daily ATR above VWAP.
- `MOM_RECENCY_5_VOL`: same as `MOM_RECENCY_5`; test the normal-session volume
  threshold on a small declared grid. Keep the stricter lunchtime threshold.

### Falsifiers

Reject the recency hypothesis if incremental candidates have non-positive net
expectancy, materially worse median adverse excursion, or are primarily late
entries that exit through thesis/VWAP or stop loss.

## Paper experiment B — Penny opportunity semantics

### Hypothesis

The existing raw accept count overstates activity because repeated scans of one
ticker are counted repeatedly. After deduplication, the pace-adjusted volume
and time-window gates may still suppress viable distinct opportunities.

### Variants

- `PEN_BASE`: shipped one-minute rules.
- `PEN_WINDOW`: test 10:00 and 10:15 starts against the current 10:30 start;
  retain the current end time and all risk/circuit-breaker rules.
- `PEN_VOLUME`: small grid around the pace-adjusted volume multiplier; do not
  reuse the daily proxy as the deciding evidence.
- `PEN_COMBINED`: only after each single-axis variant has a positive paper
  result. This prevents an unidentifiable multi-parameter change.

Every report must include raw evaluations, distinct candidates, deduplicated
paper entries, fills, and closed trades. Repeated accepts for the same ticker/day
do not add to sample size.

## Paper experiment C — F&O opening-range freshness

### Hypothesis

The single crossing-bar freshness rule is the dominant activity constraint.
Allowing one confirmation bar may improve conversion, but the option cost model
and stop cohorts can erase any gross edge.

### Variants

- `FNO_BASE`: current opening-range crossing bar only.
- `FNO_CONFIRM_1`: permit entry on the first closed bar after the break only if
  it remains outside the buffered range, trend agrees, and price has not moved
  more than 0.35 ATR beyond the break level.
- `FNO_OR_20` and `FNO_OR_45`: opening-range sensitivity tests, never direct
  live settings.

For every run, replay spread, brokerage/taxes, slippage, premium stop,
underlying stop, time stop, and hard-flat behavior. Report gross and net
results separately. The current defined-risk sample shows why cost drag cannot
be represented as zero.

## Promotion gates

A candidate may progress from exploratory replay to ongoing paper shadow only
when it has:

- no look-ahead or interval contamination in parity tests;
- at least three non-overlapping chronological out-of-sample folds;
- positive net expectancy and profit factor above 1.20 after declared costs;
- at least half of out-of-sample folds positive;
- max drawdown within its division's declared budget;
- stable behavior across reasonable slippage/cost stress, not one best point;
- no unexplained ledger/position reconciliation mismatch.

A candidate may be considered for live promotion only after the strategy's
existing minimum paper-day and trade-count constitution is also satisfied. F&O
specifically remains disabled: its current sample is below its 40-day/60-trade
gate and is net negative.

Position risk must not be raised to compensate for low frequency. Volatility
scaling can stabilize exposure, but it does not create an edge; transaction
costs create meaningful no-trade regions and can erase high-turnover returns.
Relevant primary research:

- https://academic.oup.com/imaman/article/34/2/355/6427746
- https://www.nber.org/papers/w8311

## Regulatory/operational check

SEBI's retail-algorithm framework became applicable to stock brokers from
2026-04-01 under the published implementation timeline. Before any new live
strategy is enabled, confirm the broker/exchange registration and operational
requirements that apply to this account and API workflow:
https://www.sebi.gov.in/sebi_data/attachdocs/sep-2025/1759232056254.pdf

## Delivery order

1. Correct interval-contaminated market data and fail-safe live defaults.
2. Productize the Backtest Lab with immutable runs and honest limitations.
3. Ship source-separated performance and reconciliation metrics.
4. Add broker-free shadow evaluators and distinct-candidate funnels.
5. Accumulate paper evidence, compare baseline/candidates, and promote only
   through the gates above.

