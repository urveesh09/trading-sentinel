"""Complete N04 findings, exact retained reference and next bounded contract."""
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import analyze_exit as A
L=A.L
def run():
    r=A.load(HERE/'results.json');objects=A.objects();paths=A.load(HERE/'path-crosschecks.json');cases=A.load(HERE/'entry-case-audit.json');clock=A.load(HERE/'exit-clock-contract.json')
    def table(ctx,sizing='NORMAL'):
        lines=['| Exit variant | 2024 net | 2025 net | 2026 to Oct28 |','|---|---:|---:|---:|']
        for mode,label in [('BASE','Unchanged exits'),('STALL_ONLY','Early stagnation exit only'),('CONTINUE_ONLY','Continuation threshold only')]:
            b=r['books'][f'{sizing}|{ctx}|{mode}'];lines.append('| '+label+' | '+' | '.join(f"Rs{b['years'][y]['net']:+,}" for y in A.YEARS)+' |')
        return '\n'.join(lines)
    full=['| Book | 2024 net / trades | 2025 net / trades | 2026 net / trades |','|---|---:|---:|---:|']
    for n,b in r['books'].items():full.append('| '+n.replace('|',' / ')+' | '+' | '.join(f"{b['years'][y]['net']:+,} / {b['years'][y]['trades']}" for y in A.YEARS)+' |')
    failures=['| Normal candidate/context | Failed checks | Paired t | Adjusted p |','|---|---|---:|---:|']
    for n,v in r['candidates'].items():failures.append('| '+n.replace('|',' / ')+' | '+', '.join(k for k,b in v['checks'].items() if not b)+f" | {v['paired_t']:.2f} | {v['search_adjusted_p']:.4f} |")
    text='''# N04 — separate early departure from the redundant continuation threshold

**The useful new lead is early stagnation exit on the retained balanced retest
book: approximatelyRs51,303/Rs54,051/Rs77,135. It remains unqualified. The
preferred reference is preserved unchanged as BALANCED_RETEST_N03.**

For compaction/new agents, read [the preferred reference](../../../FNO_RESEARCH_REFERENCE.md)
and [the challenger](../../../FNO_RESEARCH_CHALLENGERS.md) first. Their JSON
records bind exact books, source/result/freeze/evaluation hashes and failed
acceptance. Do not rely on conversation recall or silently replace the original.

## What was tested

No new threshold or indicator. Split N03's combined HORIZON into two exact
branches: STALL_ONLY permits the existing30-minute soft stagnation check when
untrailed, progress<0.5R and actual positive-bid liquidation net after fees and
stress<=0; CONTINUE_ONLY changes the soft check to90 when net>0, progress>=1R
and fresh directional VWAP/close continuation holds. All native stops, trail,
entry cutoff, hard-flat, cash/brakes and original/retest entries stay active.

Four normal contexts (MAIN, TPB_ONE, BALANCED_RETEST, CORE_SELECT), each BASE
and the two modes; fixed-one-lot MAIN/BALANCED diagnostics.54 fresh annual
cash-path replays, all2024–2026 already studied. CORE_SELECT's old699 daily
choices remain fixed; this isolates underlying exits, not new selector learning.
The switch's original design flaw is corrected in research, but profitable
strategy-variant switching is not established by these tests.

## Retained balanced book — main comparison

'''+table('BALANCED_RETEST')+'''

All results are modeled NIFTY single-leg net after shipped fees, adverse candle
quotes and stress(200+5*lots)*lots. FreshRs250,000 each year, normal2/3-lot limits,
only added LOW-day TPB capped at1. Independent years/books are not a continuous
wallet, whole-system portfolio or forecast for the small live-account test.

STALL_ONLY changes reference net by−Rs4,888/+Rs3,961/+Rs22,983. Annual closed-cash
drawdown is2.16%/4.65%/2.76%, against2.16%/5.22%/4.02%. The minimum annual net
and total improve in these seen years. It fails the frozen requirement to
improve every year, paired t1.50<2 and adjusted p0.1821>0.05. Keep it as the
separate **BALANCED_RETEST_STALL_N04** challenger, not a qualified replacement.

## Important correction:60/90 are soft checks, not maximum holding times

Earlier explanations described the proposed extension as allowing winners to
hold up to90min. That wording was inaccurate. The actual native exit ladder
checks time only for an untrailed trade whose underlying progress is below
FNO_TIME_STOP_MIN_R. The tested effective threshold is0.5R. A trade still making
enough progress can remain open after60 or90, subject to stops/trail/hard-flat.

CONTINUE_ONLY requires>=1R progress, already exempt from that native time exit.
Its extra90-minute threshold is therefore redundant under this configuration.
It produces EXACTLY the same entry/exit/quantity/price/fee economics in all18
matched BASE/CONTINUE annual comparisons (877 closed lifecycles). Selecting a
90-minute threshold on54 replayed lifecycles is not evidence of additional
holding benefit. Five native-exit boundary tests confirm the soft-check behavior,
including sufficient-progress trades beyond90min. Do not stack this unused
parameter into the next candidate or imply the current system caps all holds
at60/90. This is a research finding/description correction, not a Production fix.

## The early exit both helps and hurts

Exact immutable economic admissions on the retained normal balanced book:

- 2024: three matched early-exit trades, one helps and two hurt; combined
  paired delta−Rs4,888. Those two trades recovered after the early exit.
- 2025: three exact pairs help byRs2,426. Total book improvementRs3,961 also
  includes later changed exposure; do not call it all exit timing alpha.
- 2026: five exact early-exit pairs help byRs10,117. Total book upliftRs22,983
  includes anotherRs12,866 from other members' changed cash/sizing path.
  Same overall trade count does not mean all admissions/economic terms match.

stall-case-audit.json retains exact entry time/premium/quantity/stop/target
fingerprints, both admission IDs, knowable early-exit context and later base
outcome labels. Resized/unmatched admissions remain unavailable, never paired
by ticker/date. Later recoveries are research labels, not information available
at the early decision. No recovery gate or threshold was fitted this round.

## Unchanged original-entry main and other contexts

MAIN:

'''+table('MAIN')+'''

TPB_ONE with original EFF entries:

'''+table('TPB_ONE')+'''

CORE_SELECT with old daily choices and original EFF entries:

'''+table('CORE_SELECT')+'''

Early departure is not universally beneficial; it hurts original MAIN2024/2025.
Its MAIN/TPB_ONE/CORE_SELECT original-entry annual economics exactly match the
prior combined N03 HORIZON results, confirming that the additional continuation
threshold was not the source of N03's apparent improvement. Those old combined
results and TPB_FULL (+15,337/+47,892/+77,233) are hash-bound reused comparisons,
not additional fresh runs. Do not add branch deltas to form an invented portfolio.

## Equal-size diagnostics

Matched one-lot balanced book, all brakes retained:

'''+table('BALANCED_RETEST','ONE')+'''

The direction of early-exit benefit remains weaker2024/stronger2025–2026 even
at equal quantity. It is not solely a normal-sizing artifact, but normal2026
profit improvement is amplified by the shared account's later exposure.
ONE remains a diagnostic, not a post-results recommendation for a new live cap.

## Source-bar case audit and parameter caution

entry-case-audit.json records63 original MAIN EFF admissions in all three years:
closed-bar efficiency/body/rvol, ATR/VWAP/stretch, stop/target distances, premium/
spread and dated expiry/clock as known at that entry. Future original net and
later retest-confirmation lineage are separate labels, never routed inputs or
economic P&L pairs. Confirmation is later information, not an advance label.

The retest source setups linked to an admitted later retest have original net
about+Rs17,780 in2024,−Rs14,485 in2025,+Rs5,616 in2026. A retest confirmation is
not itself a guarantee of profit or a universally useful day label. The2026
original setups without an admitted child total about−Rs1,712; therefore lost
retest profit cannot simply be blamed on excluding a group of obvious old
winners. Different confirmation time/price/stop economics, additional setups,
priority and cash history matter. No new parameter is justified by that partition
alone, and these totals are not compared as if they were paired trades.

## Acceptance and verification

No normal candidate passes every unchanged check. All failures remain:

'''+ '\n'.join(failures)+'''

The preferred reference is not overwritten. Both reference and challenger remain
research-only, all years seen. Max-t covers the eight current comparisons only;
it does not undo prior repeated searches. No new offspring after these results.

- 54 new annual cash-path replays completed in184/194/162 seconds per year,
  first550s slice,3 memory-guarded workers. Fifteen annual controls reproduce
  N03 exactly after new admission-key normalization.
- 2,622 financial/immutable-admission/accepted-trace identities and5,244 actual
  archived entry/exit prices verified, with zero source/memo/clock/cash errors.
- 138 retest confirmations independently rebuilt;591 new exit-variant lifecycles
  reconstructed to the first executable exit over29,649 observations.54 received
  a continuation threshold, but no economic change resulted. These counts
  overlap repeated books and are not independent market samples.
- Independent54 cash paths,18 weekly vectors/eight adjusted tests match; zero
  exact-versus-rounded acceptance differences.99 focused tests pass:15 new
  ablation+30 parent strategy+49 existing affected+5 soft-clock boundary tests.
- 699 raw/cache session checks and footprints are explicitly REUSED from N03
  by unchanged source/data/calendar/daily/memo/decision hashes. No fresh699
  reparse is claimed. All new trade/price/exit evidence is separately checked.
  Coverage remains PARTIAL candle-model evidence, not real execution coverage.

Source/freeze/reference commit **a70e4e7** preceded all scores. All frozen source,
configuration, reference and acceptance files remain unchanged. Commands,
environment/status and evidence packaging are in VERIFICATION.md. All2024–2026
years were repeatedly inspected; normalized65 lots/current fees/candle-derived
quotes, unknown historical depth/regimes, gaps and unchanged56 original2025
negative-volume bars remain limitations. No2023 option exam/path was read;
inherited earlier daily/futures warmup remains declared.

## Next bounded experiment

1. Keep BALANCED_RETEST_N03 as the exact retained reference and record the
   separate BALANCED_RETEST_STALL_N04 challenger. Do not replace either identity
   after compaction, cherry-pick years or activate a failed candidate.
2. Drop redundant90-minute continuation from the next hypothesis. Preserve
   the native profit-progress/trailing management that already keeps winners.
3. Refine early departure in a separately frozen TWO-arm study on the balanced
   entry book only: a single later45-minute stagnation review versus a30-minute
   review requiring a fresh closed-bar loss of the original retest level. Keep
   ordinary60min soft checks/stops/trail/hard-flat when no new condition holds.
   Compare with BOTH unchanged and STALL30 references, original-main control
   and matched one-lot attribution. No parameter sweep or fitted retrospective
   recovery labels. First audit the causal fields at the early review point.
4. A strategy-variant selector needs a separately frozen past-only test; do not
   claim N04 trained a smarter orchestrator. Keep the complete main as explicit
   incumbent and preserve existing-position management across any future choice.
5. 2023 stays deferred until the owner requests its exam. These seen-data leads
   require prospective evidence before money, deployment or partner qualification.

No application/config/migration/Production/order/message/capital change. Dev
research/documents pushed only; unrelated dirty work retained. Research workers
finish before handoff. Rollback stops research workers; no Production action.

## Complete54-run inventory

'''+ '\n'.join(full)+'\n'
    (HERE/'README.md').write_text(text,encoding='utf-8');print('REPORT_WRITTEN',flush=True)
if __name__=='__main__':run()
