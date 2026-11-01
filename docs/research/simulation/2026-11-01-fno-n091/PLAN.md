# N09.1: preserve the opportunity, budget the exposure

November 1, 2026. Dev research only. Owner authorizes improvement research;
no orders, messages, downloads, Production edits, deployment or live halt change.

## Problem and learning

N08 has the highest observed aggregate return but fails its 2023 test. N09's
confirmation, structure exits, delta changes and complementary momentum did not
improve it. Do not repeat that search or claim a new predictor of direction.

Two concrete issues deserve a bounded next experiment:

1. N09 S_VOL changes low-day two-lot eligibility from before noon to before
   midnight as well as applying volatility sizing. Thus it is not simply a
   reduction of N08 size. Separate those changes.
2. N09's stress_years.path_end appends the current paper outcome before deciding
   whether to take that same outcome. That stress diagnostic is not causal at
   admission. Preserve it, reproduce with a synthetic counterexample, and provide
   a corrected entry/exit event simulation. This does not invalidate N09's full
   timestamped account replays, which use strictly earlier closed shadow labels.

N09's floor-reset restart can spend another 15% after every restart. N09.1 will
not lower/reset that floor. Investigate retaining the ability to trade within
the original cash budget instead of granting a fresh loss budget.

## Exactly two primary hypotheses, no parameter search

- **VOL_CLOCK**: unchanged N08 signals, exits and noon/14:00 limits; at most
  two lots, with N09's prior-day ATR/250-session-median rule allowed only to
  REDUCE the native lot count. Missing readings permit at most one lot.
- **CUSHION**: VOL_CLOCK plus a cash-backed floor initially 85% of starting
  capital, ratcheting toward 85% of the highest closed equity. For admission,
  reserve every open long option's FULL remaining premium, conservative current
  round-trip fees at unchanged premium, and the declared synthetic cost stress.
  Choose the largest whole native-accepted lot count that fits above this floor.
  If one lot cannot fit, decline that admission; all native exits continue.
  Never lower the floor or reset a breached halt. Ratchet only to a level backed
  by remaining cash after already-open exposure; a realized gain cannot promise
  protection against an existing open loss that is already funded.

These are exposure controls, not forecasts or guaranteed real-money insurance.
Fees, missing fills, operational faults and unarchived depth remain limitations.
No stop-price assumption substitutes for full-premium exposure in CUSHION.

## Contracts and files

Reuse n09_lab -> n08_lab -> N07 -> original BookReplay/native entry planner,
exit rules and costs. New files n091_rules.py, n091_lab.py, driver.py,
test_n091.py, score.py, audit.py and configuration/freeze receipts live here.
Never mutate old study files or application source. A smaller plan is recomputed
by the original planner before an OpenLeg is created, never resized after fill.
Per-admission receipts bind time, quote, cash, floor, open reserve, native and
final lots, and original gate outcome. Carry floor/high-water state across years.

## Runs and comparisons fixed before scoring

All four years are SEEN development data: 2023-2025 full years, 2026 to Oct 28.
Fresh Rs250000/year, normalized lot65, existing own-cash and native brakes.

1. Twelve exact annual controls: N08, old S_VOL, fixed-one-lot N08 with brakes
   off. Require complete economic trade parity against saved N09 outputs.
2. Eight primary annuals: two candidates x four years, base stress.
3. Twenty-four annual cost diagnostics: N08 and both candidates x four years x
   zero/double EXTRA stress (current fees/modeled quotes always remain).
4. Sixteen continuity annuals: N08, old S_VOL and two candidates, one account
   from January 2023, no resets/deposits at year boundaries. Persist all native
   closes/cash/risk and the new floor/high-water state.

Total60 full annual replays; cost arms and one-lot controls are not new hypotheses.
Three workers maximum, existing memory guard and network denial, bounded pieces.
Data and old receipts are hashed before scoring. Reuse immutable archives; do not
read 2022 or call Breeze. Keep known incomplete historical coverage explicit.

## Acceptance, fixed before candidate outcomes

Risk-improvement route (both needed): fresh annual net sum at least90% of N08;
worst day at least20% smaller; worst annual closed drawdown no larger than N08;
positive in the three previously profitable years; continuous ending equity no
less than never-restarted N08; positive aggregate at double extra cost. This is
an explicit opportunity-cost budget, not a guarantee of future risk/profit.

Profit-improvement route: aggregate annual net above N08, no larger worst day or
worst annual closed drawdown, no worse 2023 net, continuous equity no smaller,
positive aggregate at double extra cost. Report per-year opportunity costs even
if either route passes; do not silently substitute a weaker objective.

For CUSHION separately verify mechanical protection: every accepted entry fits
remaining full-premium/fees/stress reserve, floor never declines, floor is not
reset by restart or calendar, and all observed closed/catastrophic-loss paths
respect the funded floor within numeric tolerance. This mechanical property
is valuable even if it fails profit retention; it is not profitability evidence.

Independent audit recalculates trade economics, costs, immutable admission terms,
cash, daily/weekly vectors, worst losses, state continuity and admission clocks.
An entry/exit-aware repeated-year fixed-one-lot diagnostic includes all256 ordered
four-year paths with replacement. It is PORTFOLIO_PROXY, not new market replay;
preserve overlaps, delayed exits and strict shadow clocks; no claims about true
future loss probabilities. Report five-largest-winner concentration and paired
weekly uncertainty without calling all-seen results out of sample.

## Rollout / rollback / remaining work

No deployment. Rollback stops only these research workers. Keep original N08 and
N09 receipts unchanged and all failed N09.1 arms. Document tests, commands,
environment and commit identity in guide/active plan/checklist after each commit;
regenerate atlas. Any future shadow/live integration is separately reviewed.
Fresh forward evidence, real fills/costs and untouched-history qualification
remain necessary; no capital increase or automatic live restart follows.
