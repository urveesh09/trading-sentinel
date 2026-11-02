"""Keep the preferred identity intact and persist the separate N04 challenger."""
import json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import analyze_exit as A
L=A.L
def run():
    ref=json.loads((L.ROOT/'docs/FNO_RESEARCH_REFERENCE.json').read_text());assert ref['preferred_id']=='BALANCED_RETEST_N03'
    name='NORMAL|BALANCED_RETEST|STALL_ONLY';r=A.load(HERE/'results.json');obj=A.objects();years={}
    for y in A.YEARS:
        key=A.load(L.LOCAL/f'keys-{y}.json')[name];file=L.LOCAL/'evals'/f'{key}.json';years[y]={**r['books'][name]['years'][y],'net_exact':sum(t['net_pnl'] for t in obj[y][name]['trades']),'evaluation':file.relative_to(L.ROOT).as_posix(),'evaluation_sha256':L.B.P.sha(file)}
    record={'schema':'sentinel_research_challengers_v1','preferred_reference_unchanged':'BALANCED_RETEST_N03','challengers':[{'id':'BALANCED_RETEST_STALL_N04','book_key':name,'status':'RESEARCH_UNQUALIFIED_NOT_DEPLOYED',
        'source_commit':'a70e4e70a5d1f012f62f84e9fdd3377c79b3f3f9','study':HERE.relative_to(L.ROOT).as_posix(),'results_sha256':L.B.P.sha(HERE/'results.json'),'freeze_sha256':L.B.P.sha(HERE/'freeze.json'),'book':obj['2024'][name]['book'],'years':years,
        'failed_acceptance':[k for k,v in r['candidates'][name]['checks'].items() if not v],'paired_t':r['candidates'][name]['paired_t'],'adjusted_p':r['candidates'][name]['search_adjusted_p'],
        'interpretation':'Stronger seen-data total and minimum annual net, lower worst drawdown; gives up2024 profit and fails paired evidence. Retain alongside the original reference, never silently promote.','qualified':False,'deployed':False,'can_place_orders':False}]}
    (L.ROOT/'docs/FNO_RESEARCH_CHALLENGERS.json').write_text(json.dumps(record,indent=2)+'\n')
    text='''# F&O research challengers — retain alongside the preferred reference

The preferred reference remains **BALANCED_RETEST_N03**; read
[FNO_RESEARCH_REFERENCE.md](FNO_RESEARCH_REFERENCE.md). This file preserves the
new lead without overwriting that exact book, its failed tests or its identity.

**BALANCED_RETEST_STALL_N04** adds only the30-minute cost-aware stagnation exit
to the same main + one-lot LOW-day TPB + EFF retest entry book. No90-minute
extension, extra indicator, new size cap or fitted gate.

| Year | Modeled net after costs | Closed-cash drawdown | Trades |
|---|---:|---:|---:|
'''
    for y,v in years.items():text+=f"| {y}{' to Oct28' if y=='2026' else ''} | Rs{v['net']:+,} | {v['fall_pct']:.2%} | {v['trades']} |\n"
    text+='''
FreshRs250,000/year and the same normalized lots/fees/modeled quotes/stress;
not actual fills, continuous wealth, whole-system P&L or a small-account forecast.
Compared with the reference,2024 loses aboutRs4,888;2025 improvesRs3,961 and2026
Rs22,983. Better total and lower worst drawdown are still seen-data findings.
Paired weekly t1.50 and eight-comparison adjusted p0.1821 fail the frozen bar,
as does the requirement to improve every year. No live promotion is implied.

Exact book, source/result/freeze/evaluation hashes and failures are in
[FNO_RESEARCH_CHALLENGERS.json](FNO_RESEARCH_CHALLENGERS.json). Read the
[N04 report](research/simulation/2026-11-01-fno-exit-ablation/README.md) before
continuing. Future agents must keep BOTH references and all failed comparisons.
2023 remains deferred; a later replacement needs an explicit versioned decision
and prospective evidence. Nothing here authorizes Production or money changes.
'''
    (L.ROOT/'docs/FNO_RESEARCH_CHALLENGERS.md').write_text(text,encoding='utf-8');print('CHALLENGER_RECORDED_BALANCED_REFERENCE_UNCHANGED',flush=True)
if __name__=='__main__':run()
