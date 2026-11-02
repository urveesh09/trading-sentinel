"""Durable three-way checkpoint: no silent replacement of saved references."""
import json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import analyze_refine as A
L=A.L
def run():
    r=A.load(HERE/'results.json');objs=A.objects();name='NORMAL|BALANCED_RETEST|STRUCT30';years={}
    for y in A.YEARS:
        key=A.load(L.LOCAL/f'keys-{y}.json')[name];file=L.LOCAL/'evals'/f'{key}.json';years[y]={**r['books'][name]['years'][y],**r['books'][name]['exact_years'][y],'evaluation':file.relative_to(L.ROOT).as_posix(),'evaluation_sha256':L.B.P.sha(file)}
    record={'schema':'sentinel_research_progress_v1','preferred_reference_unchanged':'BALANCED_RETEST_N03','higher_total_lower_worst_drawdown_challenger':'BALANCED_RETEST_STALL_N04','all_year_original_reference_improvement':'STRUCTURAL_RETEST_N05',
        'structural_record':{'id':'STRUCTURAL_RETEST_N05','book_key':name,'book':objs['2024'][name]['book'],'source_commit':'f11544c630eeb5d3e36c29de01fdb0104476074c','study':HERE.relative_to(L.ROOT).as_posix(),'freeze_sha256':L.B.P.sha(HERE/'freeze.json'),'results_sha256':L.B.P.sha(HERE/'results.json'),'years':years,
            'failed_primary_checks':[k for k,v in r['candidates'][name]['checks'].items() if not v],'paired_t_stall':r['candidates'][name]['paired_t_stall'],'paired_t_base_diagnostic':r['candidates'][name]['paired_t_base'],'primary_adjusted_p':r['candidates'][name]['search_adjusted_p'],'qualified':False,'deployed':False,'can_place_orders':False},
        'interpretation':'STRUCT30 improves the original reference each year with identical economic admissions; STALL30 still has higher2025/26 profit and lower worst drawdown. No new candidate beats both references under the predeclared user objective. Keep all configurations, failed tests and limits.',
        'sizing':'unchanged lot caps/risk/cash; later research is conditional, bounded and requires prospective calibrated evidence, never a known winning trade',
        'orchestration':'structural research design corrected; profitable automatic variant selection NOT proven; no new selector trained here','2023':'option exam deferred/unscored'}
    (L.ROOT/'docs/FNO_RESEARCH_PROGRESS.json').write_text(json.dumps(record,indent=2)+'\n')
    text='''# F&O research progress — successor checkpoint

Read [the original reference](FNO_RESEARCH_REFERENCE.md) and
[the prior challenger](FNO_RESEARCH_CHALLENGERS.md) as well as this file.
All are seen-data, unqualified research books; nothing here changes Production.

| Configuration | 2024 modeled net | 2025 | 2026 to Oct28 | Worst annual closed fall |
|---|---:|---:|---:|---:|
| BALANCED_RETEST_N03 — original reference | Rs56,192 | Rs50,090 | Rs54,153 | 5.22% |
| BALANCED_RETEST_STALL_N04 — higher-total challenger | Rs51,303 | Rs54,051 | Rs77,135 | 4.65% |
| STRUCTURAL_RETEST_N05 — all-year original-reference improvement | Rs57,243 | Rs50,726 | Rs61,496 | 5.00% |

FreshRs250,000/year, same modeled quotes/fees/stress and normal2/3-lot caps,
ONLY extra LOW-day TPB1lot. No new size/risk limit or whole-system/continuous
wealth claim. N05 structural review retains the exact original169 economic
admissions and changes only six EFF losing exits; it reduces their losses.
This is not evidence of knowing a future winning entry or justification to add lots.

N05 does not beat BOTH saved references on profit/drawdown. Its diagnostic
paired t versus original reference is2.05; the registered primary comparison
versus STALL30 fails (t−1.03, adjusted p0.7374). Do not convert that secondary
comparison into a qualification pass or cherry-pick the favorable benchmark.

Exact new config/evaluation hashes and failures: [FNO_RESEARCH_PROGRESS.json](FNO_RESEARCH_PROGRESS.json).
[N05 full report](research/simulation/2026-11-01-fno-stall-refinement/README.md).
Preferred reference and high-total challenger remain unchanged. Future agents
must retain all three identities across compaction and compare before replacing.

Remaining: prospective costs/quote-path evidence and separately frozen past-only
variant selection;2023 exam remains deferred until the owner requests it. Larger
size research is later conditional work within unchanged cash/portfolio risk
budgets and stressed gap/spread/concentration checks; no unlimited lots, promised
drawdown or automatic live authority. The orchestration design fix is not proof
of profitable switching. Stop repeated parameter searches on these same years
from being presented as fresh evidence.
'''
    (L.ROOT/'docs/FNO_RESEARCH_PROGRESS.md').write_text(text,encoding='utf-8');print('PROGRESS_CHECKPOINT_RECORDED',flush=True)
if __name__=='__main__':run()
