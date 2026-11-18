# Round 8 — EN86–EN95 implementation and test plan

Owner authorized implementation and testing of all ten proposed slots, with a
complete anatomy report. Work is research-only in Dev, starting at 21735463.
Production checkout remains 55b5e942. Existing dirty files belong to other work.

## Problem and contracts

Implement docs/EXPIRY_RESEARCH_EN86_EN95.md without changing the frozen earlier
rounds, E03.2/EN55 registrations, runtime engine or Production. Build explicit OI
source routing, quantity-correct labels, transactional forward receipts and
pre-score checks. Then freeze code/data/rules and score already-seen history once.
No historical result is new out-of-sample evidence. No broker/data-download calls.

Files: data8.py, lab8.py, signals8.py, information8.py, execution8.py, forward8.py,
stats8.py, score8.py, test8.py, registration/, freeze8.json, results8.json,
anatomy8.json, ANATOMY8.md, ANATOMY8-tables.md, verification8.json and receipts.

## Effective specifications and pre-score resolutions

- Exactly EN86 diagnostic plus EN87–95 primaries; both indices registered (18
  strategy cells). SENSEX OI is unavailable in the stored sample: record that
  status, never turn its provider's zero-filled OI field into real positioning.
- Native E03.2/EN55, matched E03_env and raw EN83 are controls. The new OI panel
  preserves genuine NIFTY zero observations; report differences versus frozen
  EN83 rather than silently changing its result.
- Cash 30,000, 50% cumulative-positive-profit sweep; existing 1,500/3,000/4,000
  brakes; 2,500 parent and day room, losses consume room and profits do not add
  room; max two submitted parents, one open. Default max three lots. No shorts,
  margin, top-ups or other-book funding. Common inherited E03 exits and chooser.
- EN87: strong continuous raw score agreeing at exact E03 clock, q80 over the
  prior 20 covered expiries, no requirement for simultaneous OI crossing.
- EN88: prior-20-expiry equal-day ridge, lambda 10, target current OI S and
  predictors normalized r15, RV30, linear clock; fresh q80 residual crossing.
- EN89: raw OI crossing arms five completed bars; frozen E03 contract/event ask,
  frozen ATR; >=0.5 ATR pullback in futures closes then close beyond previous
  futures high/low; raw OI retains sign and exceeds the frozen threshold. One
  order/setup, price <= min(current 8% cap, event ask*1.08). Trigger may occur
  at event+1 through event+5 inclusive; cancel on invalid/lost OI/window end.
- EN90: per-contract contraction U/growth D, S=U+D; q80 crossing of U with
  prior-20-expiry history. Same-basket identity asserted.
- EN91: raw EN83 with time hold 24 minutes, all other exits identical.
- EN92: raw EN83, exactly one most-moneyness affordable covered contract,
  two-sided synthetic market/20%-bar capacity at the decision in bar screens,
  true fresh depth required on packets. Ranking d*(K-index), cost, strike.
- EN93: raw OI events, real net/reserve labels from the exact eight-minute
  lifecycle; four features: d*S scaled from prior rows, d*parity basis innovation,
  round-trip friction/reserve, linear clock. Missing input -> unavailable
  decision. Last 80 prior covered expiries: first60 train, last20 calibration;
  >=100 rows/40 training dates and20 calibration dates. Equal-day ridge lambda10,
  standardize on training; conservative score = forecast + mean calibration-day
  residual -1.645*SE. Threshold zero. This is a heuristic, not guaranteed coverage.
  Model errors/selection calibration reported, no post-score tuning. For this
  model, an event-covered date has at least one decision-observable candidate
  with all four inputs; choose the last80 such prior dates, with no selection on
  labels/fills/P&L. Target denominator is the decision-time reserved commitment,
  so partial/no-fill outcomes retain actual cash P&L and no future quantity is
  used to choose candidates. No-fills label0. The contemplated-money forecast
  is never described as known realized quantity. This resolution precedes scoring.
- EN94: raw EN83 plus exit after two valid consecutive opposite held-basket
  scores, basket frozen at actual fill; missing resets. Native exits take
  precedence; no flip and no removal of time/stop exits.
- EN95: exactly EN89+EN92+EN94; contract selected/frozen at the arming event,
  OI exit basket frozen at actual fill. Three remove-one ablations are explanatory
  controls, never alternative primary winners. No component selection after score.
- Basket at decision: current rounded cash ATM +/- two dated strike steps, at
  least three complete call/put pairs with endpoints available. EN86 lag-anchor
  diagnostic uses ATM from i-15. Held basket retains entry contract identities.
- All raw events are recorded, including no fill/unaffordable, separately from
  actual cash-constrained admissions. Canonical one-lot matched-clock comparisons
  use fixed-hold labels, with correct remaining quantity and actual order fees.

## Checks before freeze and scoring

Baseline parity against frozen round7 across all dates/three fills; synthetic
mechanics for each slot, partial exits, budgets, fees, failures, fresh/old OI,
2027 source routing, no lookahead; causality with future bars and later sessions
erased/corrupted; signal/label planted controls. Calibration on >=1,000 synthetic
paths each with symmetric/skewed/heavy-tail/dependent nulls and positive effects.
Receipt crash/concurrency, missing-data retry/deadline and calendar tests.

Statistical specification: development only. Primary test/interval from eight
long chronological calendar-week groups (at least10 weeks/group, at least4
groups), Student-t reference across group means. It assumes approximate group
independence; economic means retain all expiry weights and the equal-period
test mean is shown separately. A four-week bootstrap over-rejected AR(.6) nulls
(115/1000); that rejected pre-score calibration is retained. Longer-group t
rejections are40–57/1000 across the four registered nulls. Circular 4/8-week
bootstrap intervals remain sensitivity diagnostics only. Paired comparisons
are versus matched E03 and cash; cell p=max(the two), Holm18 including
unavailable cells at1. Support >=20 parents/10 traded expiries, and >=20 changed
opportunities/10 dates for a change-effect claim. Report multiple block lengths;
no claim of distribution-free testing. Minimum worthwhile paired improvement:
25 rupees per scheduled expiry (planning, not a tuned acceptance threshold).
Both ordinary/adverse net positive before profit-candidate label. Income needs
positive intervals and net without best2; tails need >=3 independent days >=2500,
positive paired gain and visible survival; protection is a separate label.
Source validation unresolved -> no qualified edge even if the bar screen passes.

## Forward, rollout and rollback

Versioned local forward ledger, SQLite unique keys and immutable final receipts;
PENDING until48h after scheduled session close, then MISSING. Per-arm coverage,
actual selected front, required warm-up/decision/exit minutes and side coverage.
Calendar must be supplied as a dated explicit snapshot independent of download
presence; absent calendar -> unavailable, no guessed future expiries. New cohort
starts only after freeze/verification. Never append to the earlier EN85 ledger.
Implement status, run-from-sealed-session, review and rehearsal only; no scheduler.

Freeze before looking at candidate P&L, commit only this work plus own documentation
additions (preserve other staged/dirty work). Scorer refuses changed code/data and
second execution. Results/report in a separate commit. No promotion or deployment.
Rollback is removal of this independent research folder; no runtime migration.

## Remaining

Implement and verify; freeze; score once; independently reconcile and write anatomy,
documentation and remaining-work receipt. No claims of profitable forward evidence.
