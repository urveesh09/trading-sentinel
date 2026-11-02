# N03 — improve EFF itself, then measure the complete book

**The breakout-retest entry is a useful research lead: higher main-book total
profit and lower annual drawdown, but less2026 profit. Neither tested variant
passes the frozen acceptance test. No application or Production change.**

The orchestration design defect identified in N02 was corrected in research;
its decisions remain unqualified. This experiment keeps its daily choices fixed
and changes EFF underneath it. It does not claim the orchestra now knows the
right future strategy.2023's option exam/data remains uninspected and unscored.

## What was implemented

EFF was the first target because MAIN2025 EFF lostRs21,174 on27 trades,
including15 time stops; losses remained at fixed one-lot size. Direction alone
was not enough: five of those trades lost after costs despite a favorable
underlying move at exit. Other members can still be profitable that year.

Only two variants were frozen, separately, before any new scores:

1. **RETEST entry:** a normal EFF breakout arms a setup instead of buying
   immediately. In the next three consecutive completed5-minute bars, require
   a pullback to the broken four-bar high/low and a directional resumption
   candle. Keep the original stop, recompute1.8R target from confirmation and
   let the ordinary planner select/size the option at the current quote.
   Gap, stale state, day change, failed level, stop breach, crisis or expired
   setup cancels it. This is a different entry, not a replay of old buys.
2. **HORIZON exit:** keep original EFF entries/stops/trails. From30min, leave
   a stalled trade if liquidation at the bid is nonpositive after fees and
   declared stress costs and progress is below0.5 initial-risk units. From
   60min, allow up to90min only while liquidation is positive, progress>=1R,
   and a fresh closed bar is continuing on the directional side of VWAP.
   Losing those conditions returns the original60min rule immediately.

Hard-flat and underlying/premium/trailing stops remain active throughout;
per-leg soft clocks restore on every call/error. Concurrent EFF positions can
have different clocks. No additional lots, averaging, partials or widened stops.
There is no combined entry+exit arm or a parameter grid.

## Main-book results

Each year is a freshRs250,000 account, normal2-lot/3-when-proven sizing and
existing cash/risk/brakes. Net includes current shipped fees, modeled adverse
bid/ask and extra(200+5*lots)*lots paid in the actual cash path.2026 endsOct28.
These are NIFTY single-leg books; SENSEX and defined-risk spreads are outside
this study, and these independent experiments are not a whole-system portfolio.
This is not a continuous three-year account or a forecast for a small live test.

| Experiment | 2024 | 2025 | 2026 to Oct28 |
|---|---:|---:|---:|
| Unchanged main | Rs+16,371 | Rs+5,710 | Rs+30,540 |
| Main: EFF breakout retest | Rs+37,258 | Rs+14,899 | Rs+25,066 |
| Main: EFF adaptive holding | Rs+5,890 | Rs+279 | Rs+47,191 |

RETEST's normal main closed-cash drawdown falls **3.87%→2.16%**, **7.47%→4.79%**,
**4.80%→3.77%** by year. It is profitable in each year and improves2024/2025,
but2026 loses aboutRs5,474 against unchanged MAIN. Its2025 net depends on the
best day even though removing the best individual trade leaves a profit.

HORIZON improves MAIN2026 by aboutRs16,651, but reduces2024 profit byRs10,481
and2025 byRs5,430. A stronger2026 is insufficient to adopt it across all cases.

## The stronger low-day extension benchmark

The inherited TPB_ONE book means original MAIN plus puts-only TPB on low-ADX
days, with ONLY those additions capped at one lot. It is still an unqualified
research comparison, not today's activated live strategy.

| Experiment | 2024 | 2025 | 2026 to Oct28 |
|---|---:|---:|---:|
| Main + one-lot low-day TPB | Rs+28,540 | Rs+36,173 | Rs+71,443 |
| Same book + EFF retest | Rs+56,192 | Rs+50,090 | Rs+54,153 |
| Same book + EFF adaptive holding | Rs+17,653 | Rs+32,129 | Rs+76,763 |

With RETEST, this book earns aboutRs56k/Rs50k/Rs54k across the three studied
years. Annual closed drawdowns are2.16%/5.22%/4.02%, versus BASE3.87%/7.88%/4.12%.
That is the most balanced lead here in descriptive terms. It nevertheless
gives up aboutRs17,290 in2026 and fails the paired-evidence threshold. We do
not relabel it a pass because its smoother outcomes look attractive.

The unchanged normal-size TPB_FULL control also remains in the ledger:
Rs15,337/Rs47,892/Rs77,233, exactly matching N02. Both comparison books already
have previously studied changes; these are not fresh independent discoveries.

## Did EFF become independently profitable?

| Experiment | 2024 | 2025 | 2026 to Oct28 |
|---|---:|---:|---:|
| EFF alone unchanged | Rs+8,085 | Rs-12,444 | Rs-12,114 |
| EFF alone retest | Rs+30,691 | Rs-15,283 | Rs+5,264 |
| EFF alone adaptive holding | Rs-8,549 | Rs-7,456 | Rs-13,947 |

No variant is profitable in all three years on its own. RETEST helps isolated
EFF2024/2026 but worsens2025 and has only7/11/9 normal-sized trades. HORIZON
reduces the standalone2025 loss but worsens the other years. EFF's contribution
inside MAIN is different because earlier-priority strategies, occupied symbols,
cash/brakes and permitted later entries change which opportunities it takes.
Do not add standalone member profits to form a fictitious portfolio.

Inside MAIN, RETEST changes EFF2025 from−Rs21,174 to−Rs10,824; TPB stays+Rs21,414.
In2026, MAIN EFF changes from+Rs3,904 to−Rs4,469, partly offset by gains in other
members. HORIZON EFF2026 becomes+Rs21,646, but EFF2024/2025 become−Rs7,304/−Rs23,027.
This is why a whole-book improvement does not prove the isolated member wins.

## Separating strategy from position size

Same entry/risk/brake rules, but both maximum-lot caps fixed at one:

| Experiment | 2024 | 2025 | 2026 to Oct28 |
|---|---:|---:|---:|
| One-lot main unchanged | Rs+5,974 | Rs+14,810 | Rs+24,671 |
| One-lot main: EFF retest | Rs+22,242 | Rs+17,017 | Rs+25,566 |
| One-lot main: EFF adaptive holding | Rs+3,894 | Rs+8,958 | Rs+32,146 |

RETEST's one-lot MAIN improves all three years, but this was a diagnostic mode,
not an authorized alternate winner selected after results. Its2026 EFF component
actually drops from+Rs2,212 to+Rs968, while other-member changes offset that loss.
Thus even the one-lot gain is not universal EFF alpha. Normal-risk cash paths
and unchanged adaptive sizing must be measured, not inferred by multiplying.
This round does not recommend a new live lot limit.

## Under the existing adaptive selector

| Experiment | 2024 | 2025 | 2026 to Oct28 |
|---|---:|---:|---:|
| N02 selector unchanged | Rs+16,371 | Rs+14,501 | Rs+50,391 |
| Same choices: EFF retest | Rs+37,258 | Rs+24,194 | Rs+39,436 |
| Same choices: EFF adaptive holding | Rs+5,890 | Rs+898 | Rs+59,449 |

These use exactly the699 N02 daily choices already sealed before these trials;
there is no retraining on changed EFF returns. RETEST improves2024/2025 but
hurts2026. HORIZON improves2026 but hurts earlier years. Choosing RETEST for
2024/2025 and HORIZON for2026 retrospectively would be a year-labelled oracle,
not a usable strategy. A causal rule would need to recognize the relevant
conditions before the trade and survive a separately frozen test.

## Acceptance, evidence and reproducibility

Zero of the eight predeclared normal candidate/context pairs passes. Every
failure remains, including standalone losses/small samples, best-day dependence,
the loss of profit in at least one year, and paired statistical weakness.
Four-week shared sign-flip adjustment covers all eight comparisons, not only
the attractive ones. It does not undo the wider repeated research on seen data.

| Candidate/context | Failed frozen checks | Paired weekly t | Adjusted p |
|---|---|---:|---:|
| NORMAL|EFF_ONLY|RETEST | positive_each_year, sample, without_best_trade, without_best_day, five_halves, not_worse_each_year, paired_weekly, max_t | 1.32 | 0.2992 |
| NORMAL|EFF_ONLY|HORIZON | positive_each_year, without_best_trade, without_best_day, five_halves, not_worse_each_year, better_total, paired_weekly, max_t | -0.71 | 1.0000 |
| NORMAL|MAIN|RETEST | without_best_day, not_worse_each_year, paired_weekly, max_t | 0.94 | 0.5487 |
| NORMAL|MAIN|HORIZON | without_best_trade, without_best_day, not_worse_each_year, paired_weekly, max_t | 0.03 | 0.9531 |
| NORMAL|TPB_ONE|RETEST | not_worse_each_year, paired_weekly, max_t | 0.70 | 0.7061 |
| NORMAL|TPB_ONE|HORIZON | not_worse_each_year, better_total, paired_weekly, max_t | -0.58 | 1.0000 |
| NORMAL|CORE_SELECT|RETEST | not_worse_each_year, paired_weekly, max_t | 0.62 | 0.7432 |
| NORMAL|CORE_SELECT|HORIZON | without_best_trade, without_best_day, not_worse_each_year, better_total, paired_weekly, max_t | -0.75 | 1.0000 |

Source/configuration/inputs/57-book contract committed **2de5448** before scoring.
A reporting-only TPB_FULL size assertion was corrected in **31d1dd9** before
outcome review. Original frozen source/failed assertion remains intact;
reporting/reconcile.py is the canonical corrected reporter, root results.json
the canonical output. No strategy or acceptance parameter changed.

- 57 fresh annual full-cash replays, all completed within their first550s slice
  (194/210/176s per year). Four unchanged normal contexts/year reproduce all
  twelve N02 controls exactly after admission-key normalization.
- 2,001 closed trades reconcile exact initial economic identities, fees/stress,
  own cash, risk/size limits, entry/exit clocks and accepted admission traces.
  All4,002 archived entry/exit prices verify. Maximum equation rounding error
  is belowRs0.0001.
- 144 retest admissions are independently reconstructed from their original
  breakout and intermediate closed bars.381 HORIZON lifecycles are independently
  replayed to their first executable exit over15,001 management observations;
 38 receive an extension. These counts overlap the repeated book experiments;
  they are not independent market samples. Ordinary urgent exits retain priority.
- 699 raw/cache sessions freshly reparse identically. Pre-score availability
  checks cover all63 earlier MAIN EFF admissions; new paths are separately
  verified. Historical IV, news and order-book depth were not invented.
- Independent arithmetic checks all57 annual paths,19 weekly vectors and eight
  adjusted tests; no rounded-versus-exact acceptance differences.30 new focused
  tests plus49 existing book/replay/weak-spot tests pass. Atlas291, no diff.

VERIFICATION.md records commands, known reporting failure, source/hash contracts,
environment, packet identity and deployment status. Full machine evidence is
results.json, effect-accounting.json, path-crosschecks.json, statistics-crosschecks
and the private keyed evaluations/traces. Research only: normalized65-unit lots,
current fees/candle-model quotes, gaps and unknown archived regimes limit
execution fidelity. coverage.json retains per-session footprints and gaps;
all699 declared sessions have some observations, which does not establish full
real execution coverage. The unchanged2025 source contains56 negative-volume bars;
unavailable continuation features fall back to ordinary management. Closed-cash
drawdown is not worst intraday MTM loss. These years were repeatedly inspected.
No2023 option path/exam was read; inherited earlier daily/futures warmup remains
the declared dataset warmup, not a2023 option backtest.

## Concrete next round, still before2023

1. Retain unchanged MAIN and N02 choices as controls. Keep RETEST as the leading
   entry research candidate and preserve these full failures; no live replacement
   or new cap recommendation from this round.
2. Separate HORIZON into **stall-only30** and **continuation-only90** in a new
   frozen two-arm exit study, with identical entries/initial economic terms.
   This round combines those two exit behaviors and cannot causally attribute
   its net change to either one. Require the same whole-cash/cost/clock checks
   and disclose unchanged/new admissions after altered exits.
3. Audit the missed/different2026 RETEST EFF setups using only knowable source
   features: breakout efficiency/body/participation, distance to VWAP, original
   stop/target distances, premium/spread, DTE and clock. Describe failure cases
   without turning post-entry favorable moves or the calendar year into inputs.
   Any adaptive selection of BASE/RETEST/exit variants is a separate small
   past-only hypothesis with MAIN explicit, not a hindsight best-year mix.
4. Preserve fixed-one-lot attribution and TPB_ONE/TPB_FULL benchmarks, and test
   per-year/best-day/half-year/paired improvement with all arms disclosed. No
   threshold sweeps or a new combination chosen from the same results.
5. Keep the owner's2023 examination deferred. Fresh prospective observation and
   later authorized held-out testing are required before promotion. Qualification,
   Production rollout, partner tips and real-money authority are separate gates.

Only Dev research files and documentation changed. No runtime application,
configuration, migration, capital, orders, messages or Production service changed.
Other authors' dirty work is preserved. Stop research workers for rollback;
all scores are resumable and no Production rollback is needed.

## Complete57-run inventory (19 books ×3 years)

| Book | 2024 net / trades | 2025 net / trades | 2026 net / trades |
|---|---:|---:|---:|
| NORMAL|EFF_ONLY|BASE | +8,085 / 20 | -12,444 / 34 | -12,114 / 18 |
| NORMAL|EFF_ONLY|RETEST | +30,691 / 7 | -15,283 / 11 | +5,264 / 9 |
| NORMAL|EFF_ONLY|HORIZON | -8,549 / 14 | -7,456 / 35 | -13,947 / 17 |
| NORMAL|MAIN|BASE | +16,371 / 25 | +5,710 / 50 | +30,540 / 33 |
| NORMAL|MAIN|RETEST | +37,258 / 15 | +14,899 / 32 | +25,066 / 26 |
| NORMAL|MAIN|HORIZON | +5,890 / 22 | +279 / 50 | +47,191 / 34 |
| NORMAL|TPB_ONE|BASE | +28,540 / 44 | +36,173 / 98 | +71,443 / 63 |
| NORMAL|TPB_ONE|RETEST | +56,192 / 33 | +50,090 / 80 | +54,153 / 56 |
| NORMAL|TPB_ONE|HORIZON | +17,653 / 41 | +32,129 / 98 | +76,763 / 63 |
| NORMAL|CORE_SELECT|BASE | +16,371 / 25 | +14,501 / 55 | +50,391 / 37 |
| NORMAL|CORE_SELECT|RETEST | +37,258 / 15 | +24,194 / 39 | +39,436 / 30 |
| NORMAL|CORE_SELECT|HORIZON | +5,890 / 22 | +898 / 55 | +59,449 / 38 |
| ONE|EFF_ONLY|BASE | +1,583 / 20 | -6,651 / 34 | -10,764 / 18 |
| ONE|EFF_ONLY|RETEST | +11,827 / 6 | -11,277 / 11 | +2,668 / 9 |
| ONE|EFF_ONLY|HORIZON | -8,312 / 14 | -4,160 / 35 | -13,947 / 17 |
| ONE|MAIN|BASE | +5,974 / 25 | +14,810 / 50 | +24,671 / 33 |
| ONE|MAIN|RETEST | +22,242 / 15 | +17,017 / 32 | +25,566 / 26 |
| ONE|MAIN|HORIZON | +3,894 / 22 | +8,958 / 50 | +32,146 / 34 |
| NORMAL|TPB_FULL|BASE | +15,337 / 44 | +47,892 / 98 | +77,233 / 64 |
