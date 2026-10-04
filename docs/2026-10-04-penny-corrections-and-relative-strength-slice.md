# Penny corrections and relative-strength strategy discussion — October 4

Status: authorized code corrections implemented and verified in Dev at base
`a674740`; stable-source development regression completed. The owner
authorized the preceding review's corrections and requested comprehensive web
research on consistent returns, including rising stocks in falling markets.
Preserve prior uncommitted review documentation and frozen research receipts.

Problem: the pending noise study applies the intervention to its baseline,
stop sizing uses a different distance from the rounded protection, and Penny
execution assumes coarse ticks. Files/contracts: Penny breakout/lifecycle/Lab,
study runner, executor and universe metadata. Add explicit replay stop policies,
bind effective Penny settings/costs, size against final quantized stops and use
instrument ticks without adding per-order instrument downloads. Keep current
cash/risk ceilings, protective-stop recovery, exit authority and live-OFF flags.

Acceptance: distinct exactly-once old/new stop arms; environment drift detected
before scoring; rounded stop distance meets its floor and quantity cannot exceed
original planned risk; instrument-aware entry/protection prices; missing tick
metadata never causes an unsafe new live entry and never blocks existing exits.
Meaningful regression tests, frozen baseline reproduction where data permits,
source compilation/diff checks and regenerated atlas. No untouched Kite scoring
without independently validated available data and a committed corrected freeze.

Rollout/rollback: Dev changes only, no push/merge/deployment or broker call.
Pure price helpers and explicit research inputs first. Missing exit metadata
retains the previous conservative pricing fallback. Old records/positions and
receipts remain intact. No funding, risk ceilings or strategy-live flags changed.
F&O source/configuration/admission/exits and shared scheduling remain protected.

Remaining strategy work: distinguish a possible 1% day from proven daily
expectancy; research market/sector-relative strength, catalyst/volume persistence,
liquidity, causal entries, winner management and risk-budget mathematics. Record
transfer limits and propose bounded experiments; do not deploy a new untested
strategy or relax mandatory risk/execution restrictions to meet a daily quota.

## Implemented contracts

- Decimal stop quantization precedes quantity calculation. At entry ₹5.10,
  old stop ₹5.07 and 98 shares, the ₹0.01-tick result is stop ₹5.02 and 36
  shares: ₹2.88 planned risk <= the original ₹2.94. At a ₹0.05 tick the stop
  is ₹5.00 with 29 shares: ₹2.90. Quantity never increases.
- Runtime noise stops use locally cached current-date instrument ticks where
  available. Universe refresh saves `tick_size` and `tick_size_as_of` from its
  existing instrument download; no added broker call or download per order.
  Exact executor prices use the same metadata. Missing/stale metadata refuses
  new live entries before quote/order submission. Existing protective-stop,
  unwind and exit paths can still attempt the legacy ₹0.10 fallback. A fallback
  attempt does not guarantee broker acceptance or a fill.
- Current-date metadata is required before future live entries. After GitHub
  promotion the normal universe refresh must run successfully; old universe
  files lack the new fields. The shared Penny executor also serves EDGE: live
  EDGE entries outside the refreshed universe likewise lack verified ticks and
  are refused. Neither live flag is enabled by this change.
- Lifecycle v3 / Lab adapter 1.2.0 distinguish `RUNTIME`, `BAR_LOW` and
  `NOISE_FLOOR`, apply the shipped evaluator's noise rule once and record its
  resolved setting. Stateful TRADER candidates keep their own structural stops;
  this input controls their shipped-evaluator counterfactual, not their candidate
  stop implementation. Historical replay declares ₹0.01 stop quantization and
  does not substitute today's instrument metadata for missing historical ticks.
- Optional positive `bankroll` is an explicit research input, not a runtime
  funding change. Pending T3 compares BAR_LOW to NOISE_FLOOR in separate
  ₹100,000 paper and ₹2,000 owner-budget books; owner_2000 is the decision book.
  Effective Penny settings, costs, executor and price-helper source hashes now
  bind pre-registration. No old freeze/results were rewritten.

Limits: this correction preserves **decision-price planned stop risk**, not a
maximum loss at the eventual entry/exit fill. Entry limit drift, partial fills,
stop-limit gaps/non-fills and complete marked-risk/daily-settlement accounting
remain material R3 work. The original risk ceiling, funding and live flags are
unchanged. No DB schema migration or new dependency is required; universe JSON
gains additive fields. Existing records/positions remain readable.

## Verification receipt

- `python -m pytest python-engine/tests -k 'penny or backtest_lab or backtest_cli or preregistered' -q --tb=short`:
  **830 passed, 1 skipped, 4,066 deselected, 15 dependency deprecation warnings**.
- After the final source edits, price-contract/executor/lifecycle selection:
  **55 passed**. Fixtures explicitly supply their assumed instrument tick;
  independent tests cover unknown/stale metadata and recovery availability.
- `python -m py_compile` on the seven affected source modules: passed.
- `python scripts/build_system_code_atlas.py`: 252 modules; second regeneration
  produced identical bytes. `git -c core.safecrlf=false diff --check`: passed.
- First five-day development regression freeze drifted during two finishing
  source edits. It is preserved under `penny-correction-parity` with an explicit
  `INVALID_SOURCE_DRIFT` validation record; do not score or promote from it.
  A new stable-source freeze/run uses `penny-correction-parity-stable`, checks
  source/settings and snapshot equality before/after scoring and asserts old
  baseline receipt parity. No candidate parameters were selected from this run.
- Stable run, Sep 24–30, same 95 symbols / PR1_CALM / allow_gaps / ₹100,000
  paper book: BAR_LOW **18 closes, +₹15.1765 net, ₹45.0962 realized drawdown**,
  exactly reproducing the archived baseline's gross/net/costs/exits/daily totals.
  Corrected NOISE_FLOOR **15 closes, +₹36.4486 net, ₹30.8560 drawdown**.
  Removing its best winner leaves **−₹4.8747** and its adverse-fill bound is
  **−₹41.0747**. This modest seen-window gain is not independent evidence,
  owner-budget performance, robust daily consistency or live qualification.
  [Stable results](research/yahoo/2026-10-04-penny-correction-parity-stable/results.json)
  and [freeze](research/yahoo/2026-10-04-penny-correction-parity-stable/freeze.json)
  retain source/settings/data fingerprints; detailed reports are local `_local`
  artifacts. The freeze was written before scoring but is uncommitted, suitable
  only for this seen-window regression, not an untouched qualification study.
- T3's required `docs/research/kite/2026-10-05-penny-h1/_local/validated-kite.sqlite`
  does not exist. No untouched test was frozen/scored, no dates invented, and
  no broker/data download was attempted.

[Detailed strategy and next development contracts](2026-10-04-penny-consistent-returns-strategy.md)
contain the completed primary research. Proposed selection/exit/risk experiments
remain unimplemented and OFF. Work is Dev-local/uncommitted, with no push,
merge, deployment, F&O operational change or Production edit.
