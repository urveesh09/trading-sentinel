"""Measured N03 findings and next contract; no strategy authority."""
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path[:0]=[str(HERE),str(HERE/'reporting')]
import reconcile as A
L=A.L
def run():
    r=A.load(HERE/'results.json');objects=A.objects();checks=A.load(HERE/'path-crosschecks.json')
    def table(names):
        lines=['| Experiment | 2024 | 2025 | 2026 to Oct28 |','|---|---:|---:|---:|']
        for name,label in names:lines.append('| '+label+' | '+' | '.join(f"Rs{r['books'][name]['years'][y]['net']:+,}" for y in A.YEARS)+' |')
        return '\n'.join(lines)
    main=table([(f'NORMAL|MAIN|{v}',n) for v,n in [('BASE','Unchanged main'),('RETEST','Main: EFF breakout retest'),('HORIZON','Main: EFF adaptive holding')]])
    extension=table([(f'NORMAL|TPB_ONE|{v}',n) for v,n in [('BASE','Main + one-lot low-day TPB'),('RETEST','Same book + EFF retest'),('HORIZON','Same book + EFF adaptive holding')]])
    alone=table([(f'NORMAL|EFF_ONLY|{v}',n) for v,n in [('BASE','EFF alone unchanged'),('RETEST','EFF alone retest'),('HORIZON','EFF alone adaptive holding')]])
    one=table([(f'ONE|MAIN|{v}',n) for v,n in [('BASE','One-lot main unchanged'),('RETEST','One-lot main: EFF retest'),('HORIZON','One-lot main: EFF adaptive holding')]])
    adaptive=table([(f'NORMAL|CORE_SELECT|{v}',n) for v,n in [('BASE','N02 selector unchanged'),('RETEST','Same choices: EFF retest'),('HORIZON','Same choices: EFF adaptive holding')]])
    appendix=['| Book | 2024 net / trades | 2025 net / trades | 2026 net / trades |','|---|---:|---:|---:|']
    for name,b in r['books'].items():appendix.append('| '+name+' | '+' | '.join(f"{b['years'][y]['net']:+,} / {b['years'][y]['trades']}" for y in A.YEARS)+' |')
    failures=['| Candidate/context | Failed frozen checks | Paired weekly t | Adjusted p |','|---|---|---:|---:|']
    for name,c in r['candidates'].items():failures.append('| '+name+' | '+', '.join(k for k,v in c['checks'].items() if not v)+f" | {c['paired_t']:.2f} | {c['search_adjusted_p']:.4f} |")
    text='''# N03 — improve EFF itself, then measure the complete book

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

'''+main+'''

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

'''+extension+'''

With RETEST, this book earns aboutRs56k/Rs50k/Rs54k across the three studied
years. Annual closed drawdowns are2.16%/5.22%/4.02%, versus BASE3.87%/7.88%/4.12%.
That is the most balanced lead here in descriptive terms. It nevertheless
gives up aboutRs17,290 in2026 and fails the paired-evidence threshold. We do
not relabel it a pass because its smoother outcomes look attractive.

The unchanged normal-size TPB_FULL control also remains in the ledger:
Rs15,337/Rs47,892/Rs77,233, exactly matching N02. Both comparison books already
have previously studied changes; these are not fresh independent discoveries.

## Did EFF become independently profitable?

'''+alone+'''

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

'''+one+'''

RETEST's one-lot MAIN improves all three years, but this was a diagnostic mode,
not an authorized alternate winner selected after results. Its2026 EFF component
actually drops from+Rs2,212 to+Rs968, while other-member changes offset that loss.
Thus even the one-lot gain is not universal EFF alpha. Normal-risk cash paths
and unchanged adaptive sizing must be measured, not inferred by multiplying.
This round does not recommend a new live lot limit.

## Under the existing adaptive selector

'''+adaptive+'''

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

'''+ '\n'.join(failures)+'''

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

'''+ '\n'.join(appendix)+'\n'
    (HERE/'README.md').write_text(text,encoding='utf-8');print('REPORT_WRITTEN',flush=True)
if __name__=='__main__':run()
