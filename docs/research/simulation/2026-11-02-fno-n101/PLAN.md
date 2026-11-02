# N10.1 — price-backed additions and genuine budget recovery

Written before any N10.1 candidate replay. Base: `7bbfb89`. Dev research only.
All 2023–2026 observations are already seen; this is NOT a fresh qualification.
2022 remains unopened. Preserve N10's original source, verdicts and exam sheet.

## Problems and two hypotheses

1. **WATCH_FLAT:** N10 can lower its floor for an expensive rejected option while
   another position is open. Keep its 20 newly closed positive paper outcomes,
   5%-of-best slice and 75%-of-best lower bound, but allow a slice only while
   flat, when free equity above the floor is below the median one-lot full
   reserve of the last 20 strictly earlier CLOSED shadow trades, and the
   rejected option itself costs no more than that median. No shadow result is
   evidence for its own entry. This isolates an account-control correction.
2. **PREMIUM_LOCK:** WATCH_FLAT plus a price-backed earned third lot. Retain the
   native one/two-lot entry, +1R threshold, one additional lot maximum, 14:45
   deadline and every native entry/exit gate. Retry once per observed minute
   while at/above +1R until one add succeeds or the parent closes. Before adding,
   require the parent option's current BID to support a raised option stop
   whose net proceeds cover the third lot's full 25% premium-stop loss, both
   roundtrip fees and each tranche's declared extra stress. Round the required
   parent stop UP to the existing Rs 0.05 option tick; it must be strictly below
   the current bid. Only install it if every add gate passes. Never infer zero
   option risk from an underlying-price trail. Keep actual child stop loss plus
   fees/stress within the original Rs 5,000 cap and stance limit. Continue
   reserving ALL premium above the account floor: protective stops are plans,
   not guaranteed fills. Execute breached stops at the next observed bid, never
   retrospectively at the requested trigger. All parent exits still close the
   child; an independently stopped child cannot be repurchased.

No new direction classifier, date/side/member exclusion, threshold search,
larger lot cap, margin, naked selling, calendar reset or fresh capital.

## Files and contracts

Only this new research directory, its root report/checkpoint and slices in
SYSTEM_GUIDE/NEXT_AGENT_PLAN/HANDOVER_CHECKLIST. Import the existing native
planner/exit/cost replay through N10, without editing ancestor studies or the
application. Bind source, dependency versions, raw cached inputs, old receipts,
effective books and tests before scoring. Store window-keyed terminal WATCH,
budget, admission and add-decision receipts; never overwrite old results.

## Finite experiment

- 16 control annuals: saved N08, N09.1 CUSHION, N10 strict and N10 retry on
  2023, 2024, 2025 and 2026 through October 28. Require exact economic parity.
- 16 candidate annuals: two hypotheses × four years × default/double extra
  stress. Rs 250,000 fresh EACH year, normalized 65-unit lots, current fees,
  archived candle-derived modeled bid/ask. These are distinct experiments.
- 48 continuous year slices: N10 retry and the two hypotheses × four years
  in chronological order × extra base costs 199, 200, 202 and 400. Corresponding
  quadratic cost term is base/40 (5 at 200, 10 at 400). No annual deposits or
  resets; persist equity, budget, true best and consumed paper evidence.
- Exactly **80 annual executions**, maximum two replay workers; do not add
  arms or retune after seeing candidate scores. Missing/unresolved evidence
  remains unavailable. Record all failures, cost sensitivities and tradeoffs.

## Acceptance and reporting, fixed before scoring

Economic superiority is deliberately difficult: annual aggregate net must
exceed N10 retry, 2023 must be no worse, 2024–26 remain positive, worst day and
worst annual CLOSED drawdown no worse, double-cost net no less, net after
removing each book's own five largest winners no less, and continuous ending
equity at every declared cost no less than same-cost N10 retry. ALL are needed.
Failing any means **not economically superior**, even if one headline improves.

Separately assess mechanical corrections: no WATCH slice while exposed, no
expensive-option-only slice, evidence strictly prior/not reused, monotone true
best and 75% funded lower bound, no add based on fictitious underlying lock,
net planned stop economics independently reconciled, stops never delayed,
cash/full-premium reserve conserved, existing deadlines unchanged. Passing this
is software/research correctness, not profit superiority.

Report annual net, trade/child counts, worst day/trade, best-winner exclusions,
closed drawdown, continuous cash and cost cliffs; exact matched/added/missed
trade attribution, changed exits, earned-lot contributions, weekly paired
differences and block-bootstrap uncertainty. No conditional success probability
or posterior overfitting claim from previously selected cousins. Fees/clock/
quotes/admissions/carry state and floor events require independent checks.

## Rollout / rollback / remaining work

No application setting, migration, live halt/lot/capital change, real order,
Telegram message, task registration or Production restart/deploy. These
research wrappers are not a live feature. Rollback means keep using the prior
research reference; no runtime rollback is required. This Rs 250k reserve is
not suitable for the Rs 12,500–15,000 live trial.

After the frozen comparison, stop in-sample tuning. Preserve the old 2022 exam;
new candidates need a separately frozen supplement before that data is opened.
Fresh keyed forward shadows and actual execution-cost observations remain the
meaningful evidence. User will acquire 2022 later; no download here.
