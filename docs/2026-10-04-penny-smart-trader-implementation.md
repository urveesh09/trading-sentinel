# Penny smart trader implementation — October 4, 2026

Status: implementation verified; frozen diagnostics complete, hypothesis not
supported, candidate OFF. Dev base
`a6747406094f607b3e120a5c2b185603ac3b6b8b`, preserving preceding uncommitted
corrections/research. Owner authorized development of the proposed Penny
selection, entry and exit intelligence. Production is read-only; F&O operational
contracts, funding, broker subscriptions and shared scheduler are protected.

Problem: earlier stateful variants increased churn and did not establish an
untouched edge. Build causal opportunity ranking, bounded retest entries,
winner-preserving management and durable paper state before live promotion.

Files/contracts: new Penny smart policy and paper-shadow store, existing
adaptive state functions, lifecycle/Lab candidate variants, scanner's existing
data/shadow hooks and Penny-only configuration. Reuse shipped detection/advance
functions; rank independent positive momentum/persistence with optional actual
benchmark context. Missing context is recorded rather than fabricated. Reuse
existing cash/position/risk ceilings and cost schedule, include costs in the
paper budget, and make exits independent of entry eligibility. No actual order
or funding increase. Entries reuse existing fetched data. Opt-in exit observation
uses one bounded quote batch for at most three held paper symbols on the existing
monitor cadence; it adds no history request, subscription or scheduler job.
Session and state identity
must survive restart; duplicate/out-of-order bars cannot create repeated trades.

Acceptance: counterexamples for falling index/rising stock, stale/future bars,
late/overextended intent, cash and total-risk overcommit, duplicate observations,
restart equivalence, missing/stale quotes, entry halt with exit authority, no
premature breakeven/partial, stops never widening and causal next-bar fills.
Matched selection/entry/exit ablations over already-seen September data with
source/settings/data frozen before scoring; no use of missing untouched Kite
history. Record zero-trade/losing days and owner-budget economics. Test F&O
source isolation and original Penny behavior with shadow disabled.

Rollout: broker-free paper shadow, separately recorded from incumbent positions
and funds. Scanner observations reuse fetched candles/quotes during its current
entry cadence; no early-session or exit scheduler change in this slice. Research
replay records its declared clock. Live flags remain OFF. Disable the shadow to
stop new observations; persisted unresolved exposure remains visible and can
continue management when enabled. Promotion remains GitHub-only.

Remaining: new candidate is not qualified until independently measured; untouched stop test
requires absent Kite history. Actual broker fill/partial settlement and classic
Penny daily-risk reconciliation remain a separate material pre-live contract.
This slice's shadow owns and reconciles its own simulated cash/risk state; it
does not claim to repair those live contracts or guarantee daily income.

## Implemented contracts

- `penny_smart_policy.py`: causal stock strength (absolute progress, persistence,
  rolling progress, VWAP support; optional observed benchmark excess), reused
  `detect_breakout`/`advance_setup`, bounded reclaim/continuation intentions.
  Scores are transparent evidence ranks, not predicted win probabilities.
  The existing 10:30 start stays fixed; fresh setup detection ends at 14:15,
  and an armed setup can advance until its bounded expiry before 14:30.
  One entry per ticker/day, failure cooldown, expiry and price budget are explicit.
- `penny_smart_book.py`: exits before ranked allocations; cost-inclusive single
  risk 0.25%, total working risk 0.75%, daily marked-loss latch 1% of the paper
  allocation. Maximum three holdings and the existing ₹500 stock cap. These are
  research paper limits; ₹5 risk can exceed incumbent admitted rupee risk and
  is never authorized as a live increase by these experiments. Stops can be
  exceeded by gaps; the latch is not a guaranteed maximum realized loss.
- Winner manager: trail confirmed closes after 1.5R, never widen a stop or force
  a +1R breakeven/partial. Losing failed/stalled setups and 14:30 losers exit;
  15:00 remains the paper deadline. Missing execution evidence persists an exit
  intention; it does not create a fill. A gap resets consecutive failure closes.
- `penny_smart_shadow.py`: separate sibling store
  `<DB_PATH>.penny-smart-paper.db`, with `penny_smart_paper_state` and
  `penny_smart_paper_events`. Atomic transactions, event deduplication and
  clock/bar cursors survive restart. Frozen policy hashes/params/costs/caps
  halt new admissions on drift. Settled equity carries between days without
  refilling it; prior unresolved positions prevent a reset.
- Timestamped uncrossed bid/ask depth and whole-share size are necessary for
  runtime simulated fills. Entry uses ask, exit/mark uses bid. Invalid frames
  are isolated per ticker. Exit monitoring uses actual completed candles when
  available; otherwise the last archived bid sample only after its minute
  finishes. Sample records are labelled `SAMPLED_BID_CLOSE`, with no fabricated
  candle range/volume or gap fills. Quote samples preserve management when entry
  scans halt, without new history requests. Stops/deadlines use current quotes.
- Runtime flag `PENNY_SMART_SHADOW_ENABLED=False`, virtual bankroll ₹2,000.
  The new smart-shadow flag remains OFF. Processing runs in a worker thread, with a
  two-second runtime timeout and an independent DB so shadow writes do not lock
  F&O/operational cash. Incumbent stop exits take precedence. Broker order
  capability does not exist in the new modules.
- Lifecycle v4 / Penny Lab adapter 1.3.0 adds `PEN_STRENGTH_RANK`,
  `PEN_SMART_EXIT`, `PEN_SMART_ENTRY`, `PEN_SMART_TRADER`, optional benchmark and
  daily zero/losing-day returns. Ranking-only preserves existing candidates and
  risk; exit-only preserves the shipped entry evaluator, but subsequent entry
  occupancy can change. Entry/full arms share the new paper cash/risk contract;
  they are not pure entry-only changes relative to incumbent sizing.

## Verification and limitations

Broad selection: 1,410 passed, one skipped, 3,513 deselected, one existing F&O
fixture failure (`test_mark_to_market.py::TestFnoDrMark::test_actual_dr_writer_row_is_explicitly_unsupported`).
That fixture calls `PlannedStructure` without required `contract_legs`. It and
`fno_dr_book.py` match HEAD, and the same isolated test reproduces the failure.
No F&O runtime or test correction is included in this Penny slice. Existing
dependency deprecations and scheduler test teardown/thread warnings also appear.
The latest new-policy suite passes 28 tests, including an actual replay fill
after reclaim and invariance to a future candle wick. Earlier scanner/new-policy
combined check passed 49 tests; new test added afterwards. Compilation passed.

Commands (Dev Python): `python -m pytest python-engine/tests -q -k
'penny or backtest_lab or backtest_cli or preregistered or fno' --tb=short`;
`python -m pytest python-engine/tests/test_penny_smart_policy.py -q --tb=short`;
`python -m py_compile ...`; `python scripts/build_system_code_atlas.py`.
AST comparison with HEAD: only `run_penny_paper_stop_monitor` changed in `main.py`;
only `PennyMisLifecycleAdapter` changed in `backtest_lab.py`. F&O declarations
and adapters, scheduler jobs, broker clients and funds are unchanged.

Synthetic 95-symbol benchmark: fresh 76-bar policy batch median 27.533 ms,
maximum 34.898 ms; optimized candle conversion 120.536 ms. These are local
synthetic processing timings, not exchange latency or trading performance.
Full 375-bar conversion across 95 symbols took 439.914 ms; policy step at the
session deadline took 23.754 ms. Final policy/scanner/lifecycle selection passed
74 tests, including all 28 new-policy tests; the preregistered runner passed
two more. The scanner/new-policy portion contains 50 checks after the final addition.
Black was used as an isolated temporary formatter; no runtime dependency added.

The replay uses minute opens as quote proxies, fixed allocation per independent
session, constant PR1_CALM and retrospectively coverage-selected symbols.
Historical ticks/depth/slippage, runtime sampled-quote exits, continuous runtime
equity rollover, current event/sector eligibility and actual broker execution
are not fully replayed. `allow_gaps` remains explicit. Neither tests nor profits
in these already examined data establish live safety, profitability or a daily
1% floor. Preserve zero/losing days, costs, ex-best-winner and adverse-fill bounds.

Rollout/rollback: no flag enabled, new store created only on opt-in, operational
positions/ledger have no migration. Disabling the master flag pauses the shadow;
unresolved simulated state remains for exit management when re-enabled. There
are no real orders to unwind. Do not delete its DB to conceal open exposure.
Production HEAD remains `044c016584118fd5c5b515fc6d03909dbcaa8c4b`, inspected
read-only. Dev changes are uncommitted, not pushed, merged or deployed.

## Frozen results and decision

[Freeze](research/yahoo/2026-10-04-penny-smart-t4/freeze.json),
[verdict](research/yahoo/2026-10-04-penny-smart-t4/results.json), and
[daily economics/marked-risk receipt](research/yahoo/2026-10-04-penny-smart-t4/daily-economics.json).
Source/settings/data verified unchanged before and after all ten scores.
This is a local/uncommitted diagnostic freeze on previously examined data,
not committed untouched preregistration or qualification. No parameters were
changed to rescue outcomes. Short and broader windows overlap deliberately;
their profits must not be added or treated as independent validation samples.

Fixed ₹2,000 per-session paper budgets, 95 retrospective requested symbols,
constant PR1_CALM, real MIS costs, explicit gap sensitivity, no benchmark fetched:

| Policy | Sep 24–30 closes / net | Sep 7–Oct 1 closes / net | Broader realized DD | Broader net ex-best |
|---|---:|---:|---:|---:|
| Incumbent NOISE_FLOOR | 15 / +₹36.4486 | 38 / +₹91.7169 | ₹30.8560 | +₹50.3936 |
| Strength rank only | 15 / +₹36.4486 | 38 / +₹91.7169 | ₹30.8560 | +₹50.3936 |
| Shipped entries, smart exits | 20 / −₹20.9639 | 48 / −₹2.2712 | ₹66.1880 | −₹32.7811 |
| Smart entries/risk, incumbent exits | 22 / +₹31.7253 | 79 / −₹47.7479 | ₹71.7711 | −₹65.6878 |
| Combined smart trader | 33 / −₹6.3359 | 153 / −₹47.5019 | ₹97.1379 | −₹66.3592 |

The full candidate fails all four declared checks: positive net, positive net
without its best winner, beating incumbent net and staying inside the relative
drawdown bound. `NOT_SUPPORTED_STAYS_OFF`, `qualification=NOT_ASSESSED`.
Ranking did not change the realized admitted set in either diagnostic. Reclaim
entries are more active; the broader return and stress results reject activity
as a substitute for an edge. Entry-only's attractive short result does not
survive the broader seen sample. Exit changes alter future occupancy/admissions;
these are policy ablations, not fixed-entry-cohort counterfactuals.

Across 18 usable sessions: incumbent 8 positive / 8 losing / 2 zero-trade days,
3 days reaching 1%; full candidate 7 positive / 11 losing / no zero-trade days,
2 reaching 1%. Incumbent costs ₹13.0031, full candidate ₹64.4619. Adverse-fill
bounds are −₹91.8522 and −₹957.0363 respectively; these are declared stress
bounds, not measured slippage. Full paper daily brake latched on Sep 22, but
realized loss was ₹24.3498 (1.21749%): planned risk/brakes do not bound gap fills
to 1%. Neither candidate nor incumbent supports a consistent daily income claim.

## Next material slice — evidence-led entry and exit utility, not more churn

No new thresholds or flags are implemented from these scores. Keep incumbent
trading decisions and the candidate OFF. This is the next plan, not completed work.

1. **D1: reconcile live risk first.** Files/contracts: `penny_risk.py`, execution
   journal/settlement, `performance.py`, Penny scheduled exit wiring and existing
   reservations. Bind all entry/partial/close cash exactly once, reconcile on
   restart, count outstanding stop-loss/cost exposure, and cap new risk by the
   remaining daily allowance while exits continue. Do not change F&O budgets,
   generic broker clients or its execution pathways. Acceptance: actual-fill
   drift, partial/cancelled fills, duplicate settlement, restart and daily
   admission counterexamples. Paper first; migrate/reconcile before activation,
   no larger allocation. Roll back entry eligibility while preserving exits.
2. **D2: acquire independent usable observations and preserve decision context.**
   Use the existing collectors/contracts plus archived shadow events. Retain
   entry family, original setup context, price/spread/depth/tick/time evidence,
   fee/reservation and exit decisions with one identity. Capture rejected as
   well as admitted opportunities so selection effects are visible. Require
   point-in-time cash universe/eligibility and actual benchmark histories for
   relative-return claims. No historical candles invented from samples. Run
   off-market/bounded provider jobs; F&O resource priority stays fixed.
3. **D3: test a small conditional utility model.** Preserve shipped entries and
   exits while asking which setup families leave enough executable price room
   after costs, which sustain participation and which fail after a reclaim.
   Use a small declared score/model and explicit abstention for missing context;
   estimate and calibrate from independent development data with purged temporal
   validation. Freeze features/model/risk before untouched testing; include
   negative sessions and periods without trades. Compare with incumbent under
   the same simulator/cash contract so sizing/brakes are not mixed with entry
   recognition. A rising stock in a falling index remains eligible when its
   actual evidence and risk allow; no assumption that every day offers an edge.
4. **D4: exit calibration on fixed entry cohorts.** The automatic two-close
   thesis failure and stall/trail rules did not demonstrate benefit here. Test
   one alternative manager against identical filled entries, then separately
   replay the entire endogenous book to measure changed occupancy/churn. Examine
   giveback, premature exits, loss-tail size, fees and winner concentration.
   Preserve incumbent exits until a net-cost/marked-risk improvement survives
   unseen and prospective execution evidence. No mandatory +1R breakeven or
   partials, wider stops, averaging down, daily trade/profit quota, or tuning
   these same September outcomes until the table turns green.

Acceptance for each material slice: independent data/coverage, frozen model and
costs, matched bankroll/cash/risk, positive net excluding best winner, bounded
marked loss tails, conservative execution sensitivity, preserved zero/losing
days, passing counterexample tests and F&O isolation. No test creates a guarantee
of 1% daily. Rollout: observation → separately funded virtual paper book →
owner-reviewed qualification and GitHub promotion. Rollback always stops new
admissions while reconciling and managing existing exposure. Outstanding R0/T3
Kite data and R3 live settlement remain explicitly incomplete.
