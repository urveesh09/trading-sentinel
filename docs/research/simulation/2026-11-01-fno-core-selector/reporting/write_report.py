"""Readable post-run report; frozen policy/configuration remain unchanged."""
import json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import analyze_core as A
X=A.X
def run():
    r=A.load(HERE/'results.json');refs=A.objects('reference');children=A.objects('candidate')
    names=[('MAIN','Current main',refs),('NO_EFF','Main without EFF',refs),('TPB_FULL','Main + normal-size low-day TPB puts',refs),('TPB_ONE','Main + one-lot low-day TPB puts',refs),('CORE_ADD','Adaptive additions',children),('CORE_SELECT','Adaptive additions / EFF selection',children)]
    table=['| Policy | 2024 | 2025 | 2026 to Oct28 | Three independent years |','|---|---:|---:|---:|---:|']
    dd=['| Policy | 2024 | 2025 | 2026 |','|---|---:|---:|---:|']
    sample=['| Policy | 2024 | 2025 | 2026 | Total |','|---|---:|---:|---:|---:|']
    for name,label,objects in names:
        net=[sum(t['net_pnl'] for t in objects[y][name]['trades']) for y in A.YEARS];counts=[len(objects[y][name]['trades']) for y in A.YEARS]
        s=r['baselines'][name] if name in r['baselines'] else r['candidates'][name]['book']
        table.append('| '+label+' | '+' | '.join(f'Rs{v:+,.0f}' for v in [*net,sum(net)])+' |')
        dd.append('| '+label+' | '+' | '.join(f"{s['years'][y]['fall_pct']:.2%}" for y in A.YEARS)+' |')
        sample.append('| '+label+' | '+' | '.join(map(str,[*counts,sum(counts)]))+' |')
    text='''# N02: fix the selector that displaced the working main book

**The revised selector improves these historical results and preserves the main's
2026 opportunities. It still does not pass the declared promotion test.**
This is offline Dev research, not a Production change.2023 remains uninspected,
unscored and deferred at the owner's request. All2024–2026 data has already been
used repeatedly. These results cannot qualify a new profitable live policy.

## What was wrong with the earlier switch

The owner identified a real design weakness. N01 asked which individual expert
had earned in a coarse market-state bucket. It did not offer the complete MAIN
policy as a competing expert, and removed its dailyADX eligibility/priority.
MAIN's combination of gates, priority, risk state and exits was therefore absent.
The2026 learner took60 LOW-daily-ADX TPB trades and matched none of MAIN's33 exact
signal/entry opportunities. Its2026 net was aboutRs5,090 versus MAIN Rs30,540.
This was a failed research design, not evidence of a Production switching bug.

A valid trend/range label describes the path so far. It does not know whether
the next breakout will continue, or whether the option bought at its current
premium will earn enough after spreads, fees and time. Switching cannot infer
the year's winning strategy from that year's future result.

## Why the main wins, and why2025 is weaker

MAIN here means the original four members in priority order, prior dailyADX>=30
and the0.5 entry-stretch rule, with normal sizing/exits/brakes. It is already
adaptive at the signal level; it does not buy on every high-ADX session.

- **2025:** TPB earnedRs21,414 but EFF lostRs21,174; OR20 and SHIPPED added
  Rs3,262 andRs2,209. EFF lost on both calls and puts. EFF's fixed-one-lot
  diagnostic also losesRs13,653, so quantity alone is not the explanation.
  The separate fixed-lot population is not an exact sizing counterfactual.
- EFF is a short-horizon efficiency breakout: last4 five-minute bars,
  efficiency>=0.35, breakout buffer0.2ATR, candle body>=55%, participation>=1.2,
  target1.8R and a60-minute time stop.15 of27 MAIN EFF2025 trades reached the
  time stop. Its option gross was already negativeRs8,798, and fees/extra
  stress costs took it to negativeRs21,174. Five of those trades lost net
  despite a favorable underlying move at exit. Direction alone was insufficient.
- **2026:** OR20 earnedRs10,639 and TPB Rs12,899; SHIPPED Rs3,098 and EFF
  Rs3,904. TPB's median signed underlying exit move was1.86 initial-risk units
  versus0.47 in2025, with median holding145 versus97.5 minutes. This is
  descriptive evidence of stronger captured follow-through, not an advance rule.
- TPB waits for a directional intraday move, sustained trading on the relevant
  side of VWAP, a pullback toward it and a resumption candle. Its own trailing
  and time exits remain intact. TPB calls earnedRs15,346 in2025 but lostRs731
  in2026. A blanket calls ban would remove actual2025 winners.
- Removing EFF permanently is also imperfect: the whole-book NO_EFF control
  improves2025 but loses profit against MAIN in2024 and2026. Member sums do
  not exactly equal the effect of deletion because priority/cash/exposure change.

See diagnosis.json and execution-crosschecks.json for reconciled member/side,
fees, exit, size and archived-path figures. Post-entry path labels were NOT
used to train the selector. These observations do not isolate IV or time decay.

## What changed in the research implementation

MAIN is now the explicit default. Alternatives compete on **previously closed
whole-policy improvement versus MAIN on matched dates**, not absolute profit.
Prior84 archived sessions only; eight-week/sample, best-improvement-day and
drawdown guards; score mean weekly improvement minus one standard error;
two consecutive winning decisions required. Failed evidence returns MAIN now.
Daily model choices are fixed before the session. Current closed-bar signals
still control intraday admissions; this is a daily policy selector, not a newly
proven intraday forecasting model.

CORE_ADD may add TPB puts on low-daily-ADX days. CORE_SELECT may also omit EFF
when the prior relative evidence favors it. Only extra LOW-day TPB is capped
at one lot; normal main sizing stays intact, and temporary caps are always
restored. Profile changes never force an exit or reset cash/brakes. Existing
positions keep their strategy's exits. Stale closed-bar state blocks only new
selector admissions; management and deadlines continue normally.

## Results after the same declared costs

Each year starts with a freshRs250,000, normal2-lot/3-when-proven limits,
normalized lot65 and current shipped risk functions. Net includes modeled
bid/ask, shipped fees and additional(200+5*lots)*lots cash-path stress costs.
The three-year sum is not a continuous account balance. It does not predict
the outcome of aRs15,000 one-lot live test. Totals are independently rounded.

'''+ '\n'.join(table)+'''

Closed-cash drawdown (not mark-to-market worst loss):

'''+ '\n'.join(dd)+'''

Completed trades:

'''+ '\n'.join(sample)+'''

The static one-lot extension is an important new reference: it beats MAIN in
each of these seen years. Both static extensions beat the selectors in2025
and2026. The selector's evidence requirements and delayed activation leave
opportunities unused. That is a measured trade-off, not justification for
loosening thresholds after viewing the result. Neither static reference is
qualified or authorized for activation by this study.

## Did it retain the winning main opportunities?

- CORE_ADD retains all25/50/33 MAIN signal-and-entry opportunities by year.
  All2024/2025 main lifecycles also match economics exactly. In2026,26 of33
  match economics; seven have different quantities through the shared cash/risk
  path. No main trade was silently replaced by a coarse state choice.
- CORE_SELECT retains25/47/33. The three missing2025 entries are deliberately
  omitted EFF trades on selected NO_EFF dates: two losses and one tiny winner.
  Other changed exposures are explicit in results.json; no displaced baseline
  P&L is added back as if both accounts could have been traded.
- Both2026 candidates add four low-day trades, netRs9,305. The otherRs10,546
  of theirRs19,851 improvement comes from the changed main-origin cash/sizing
  path. It is **not all better entry selection**. Normal exits/timing remain;
  the larger sizes also carry more possible loss.
- CORE_SELECT2025 improvementRs8,791 includesRs3,003 from eight added low-day
  trades andRs5,788 main-origin difference after omissions/resizing. NO_EFF's
  six actually taken trades loseRs3,121; that does not by itself measure its
  relative contribution versus the main counterfactual. See outcome-accounting.

## Acceptance: improved, still not proven

Both candidates are profitable each year, at least as profitable as MAIN in each
year, have sufficient total trades, pass five-of-six half-years and the declared
drawdown comparison. Neither passes all frozen checks:

- CORE_SELECT2025 netRs14,501 is below its best dayRs15,755. Removing that day
  leaves approximately negativeRs1,254. CORE_ADD is weaker on the same check.
- Paired weekly t: CORE_ADD1.22, CORE_SELECT1.42, below the required2.
- Two-candidate shared four-week sign-flip adjusted p:0.1613 and0.1006,
  above0.05. This is exploratory sensitivity for these two candidates only;
  it does not undo the wider repeated research/selection across these years.
- CORE_SELECT2025 closed drawdown rises from MAIN7.47% to7.96%; CORE_ADD8.13%.
  A better total did not mean losses were prevented.

The acceptance rule is unchanged. No more offspring or relaxed thresholds were
tried after these results. Failed candidates and all controls remain visible.

## Verification and limits

18 new full annual shared-cash replays:12 references plus6 candidates. Nine
legacy whole-policy controls reproduce exactly after member-name normalization.
806 closed records/immutable admission identities and accepted trace bindings,
1,612 archived entry/exit prices and699 freshly reparsed raw/cache sessions
verify with zero choice/price/financial/clock errors. Independent arithmetic
reproduces699 daily models and1,398 choices, with no current/future/unclosed
labels used.16 new focused contract tests and49 existing affected tests pass.
Commands and pre-score source/model commit identities are in VERIFICATION.md.

Known data/model limits remain: normalized lot/current fees, candle-derived
adverse quotes, incomplete historical depth/regime coverage and known gaps.
The sealed2025 inputs contain56 negative-volume bars from the earlier dataset;
they were not silently repaired. These are research paths, not historical
broker fills or proof of future returns. All three years have been seen.

## Next improvement round — before2023

1. Keep MAIN as an explicit whole-policy option/default and preserve its
   admission/exit contracts. Do not promote these selectors on these scores.
2. Use static TPB_ONE as a named comparison in the next frozen experiment,
   alongside MAIN, TPB_FULL and the unchanged adaptive candidates. Include a
   matched fixed-one-lot run to distinguish selector merit from path-dependent
   sizing. Do not choose a new lot cap after looking at the next results.
3. Audit causal feature availability before any new model: prior-day trend,
   intraday breakout/resumption quality, distance to VWAP, option premium,
   expiry/time remaining and archived quote age/spread. No invented IV,
   historical news or order-book depth. Test at most two predeclared net-payoff
   hypotheses, score relative improvement on matched dates and replay their
   complete cash paths. Preserve the failed baselines and all adverse costs.
4. Specifically investigate EFF's entry-to-exit option payoff, rather than
   assuming ADX or underlying direction is enough. Any shorter time stop,
   scale-out or trail change is a separately frozen later test, not a fix
   inferred from these post-entry paths. Keep existing management active.
5. Recheck best-day dependence, paired improvement, size attribution and
   half-year stability. Keep2023 untouched until the owner later requests its
   exam; record that multiple prior research rounds influence all hypotheses.
   Fresh prospective trades remain necessary before a live recommendation.

No application source, configuration, migration, money switch, real order,
partner message or Production service was changed. Research is committed/pushed
in Dev only. Stop research workers for rollback; existing outputs are resumable.
'''
    (HERE/'README.md').write_text(text,encoding='utf-8')
    print('REPORT_WRITTEN',HERE/'README.md')
if __name__=='__main__':run()
