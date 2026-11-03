# Frozen anticipation experiment: executable doubles and heroes

Written before generating target labels or fitting any model. The sizing
experiment already found more money at higher risk, not a risk-adjusted pass:
RUNNER25 +13,549 / +12,438, versus +12,427 / +11,498; severe -4,131 versus -3,234.
Do not use the new allowance to disguise a new entry edge.

## Question

Can causal price, participation and futures features identify an executable
large option move **before** it happens, often enough to clear actual costs?
Two primary fixed targets, no genome or threshold search:

- **DOUBLE_MODEL:** first completed-bid trigger at 2x purchase, realized at the
  next executable open, before a 35% initial stop or 20-minute/15:28 clock.
- **HERO_MODEL:** the same at 5x. No pre-target trail, partial or profit floor;
  otherwise it would test a different event. Underlying stop remains 2 ATR.

These are different experimental exits from E03.1, NOT changes to E03.1.
All modelled entries one lot, at most 1,250 ticket / 2,500 day, two sequential
tickets, five-minute cooldown, same own 25,000 cash and absolute brakes. No
new extra-risk model combinations unless separately frozen after these fail/pass.

## Examples and causal outcomes

Every completed minute 13:00-15:00, each direction: use the nearest contract
the original one-lot selector can actually choose in its 5-20 band, <=200
points away and within reach. The full causal four-strike selection is kept.
Freeze before accessing any outcome. Decide on bar i, attempt entry on i+1 at
the inherited adverse price, 10% limit and full fees. No entry is a zero hit,
not a removed future winner. Only a fully executed TARGET counts as positive;
missing/unresolved exits are conservative non-hits, reported separately with
full-premium loss bound. Future highs never label an assumed fill. Inspect
every unknown status, not only positive examples. Whole-book fills remain
separate ordinary/adverse/severe experiments, not sums of overlapping examples.

## Fixed features (all at decision or earlier)

Direction-adjusted index returns over 3/10 bars, future return over 3, 3-bar
future-basis change, 10-bar directional efficiency; option 3-bar log momentum
and acceleration; 3-bar volume relative to preceding 20-bar median; five-bar
fractional OI change; strike distance / (ATR*sqrt(20)); minutes remaining;
round-trip fee fraction; same-strike option-implied-forward vs spot / ATR;
short/long realized-noise ratio; log premium; call/put direction. OI is neither
signed order flow nor dealer inventory. Bar volume does not identify aggressors.
Missing values use **training-only** imputation with missingness indicators.
No total-day highs, future contract availability, settlement or daily labels
are features. Early prefix recomputation must equal the original features.

## Fit and score without test-label selection

One fixed L2 logistic model per target, numpy implementation, regularization
1.0 on standardized coefficients, unpenalized intercept, max 60 Newton steps,
fixed line search and convergence tolerance. No tuned hyperparameters. Each
expiry day carries total training weight one; overlapping examples are not
thousands of independent expiry observations. Normalize on training rows only,
append missing indicators and cap normalized features at +/-5. Train labels
are adverse executions, and actual fees are included in the trading hurdle.

Entry requires p > (1 + current round-trip fee fraction at target) / target
multiple: even if every non-hit lost the whole premium, the probability should
clear the model's gross loss/reward hurdle. It is a model assumption, NOT a
guaranteed expected return; slippage, probability error and temporal instability
can defeat it. Among currently eligible directions choose largest p*multiple
minus (1+fee fraction); no selecting the day's best future score.

1. Train 2024, score 2025; separately train 2025, score 2024. The latter is a
   backwards-time diagnostic, not a deployable experiment. Both years were
   already seen by the research program, so neither is independent market proof.
2. Main causal path: first 13 expiries are training only. From the next expiry,
   refit once per calendar quarter using **only prior quarters**, with labels
   from completed prior sessions. Cash is continuous over that evaluation
   path; E03.1 gets a separate fresh matched-calendar book for comparison.
3. Report event prevalence, day counts, Brier score, top-5% precision/lift as
   diagnostic only (NOT an optimized entry), economic-hurdle admissions, every
   trade/day, costs, worst day, drawdown and ex-best. Never sum overlapping
   example net outcomes into performance.

## Acceptance

A model must beat matched-calendar E03.1 ordinary/adverse net in the causal
path, positive without best day, worst day >=-750, drawdown <=2,000, unresolved
zero. It must also beat the E03.1 2025 control after training only on 2024.
No passing backwards-time score can rescue failed causal results. Severe
results always retained. Any promising hypothesis requires separately frozen
new market data and observed execution before promotion. No native engine,
flags, Production, downloader or capital changes in this experiment.
