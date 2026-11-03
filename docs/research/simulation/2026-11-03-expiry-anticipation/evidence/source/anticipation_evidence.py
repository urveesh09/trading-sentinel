"""Standard skill receipts for independent research books and evaluator examples."""
from pathlib import Path
from datetime import date,timedelta
import importlib.util,json,shutil,sys
import guard as G
HERE,ROOT=G.HERE,G.ROOT
sha=G.sha

def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def helper():
    p=ROOT/'.agents/skills/sentinel-trading-simulation/scripts/simulation_evidence.py'
    spec=importlib.util.spec_from_file_location('anticipation_stock_helper',p)
    h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h);return h

def main():
    G.verify();assert not G.git('diff','HEAD','--','python-engine').strip()
    h=helper();out=HERE/'evidence'
    raw={n:json.loads((HERE/n).read_text()) for n in ('size-results.json','smart-results.json','forecast-results.json','return-results.json','forest-results.json')}
    specs={}
    for name in ('E031','SCALE25','RUNNER25'):
        for sc in ('ordinary','adverse','catastrophe'):
            specs[f'expiry_{name.lower()}_{sc}']=('size-results.json',f'{name}|continuous|{sc}')
    for name in ('SMART_RUNNER25','CLOCK_RUNNER25'):
        for sc in ('ordinary','adverse','catastrophe'):
            specs[f'expiry_{name.lower()}_{sc}']=('smart-results.json',f'{name}|continuous|{sc}')
    for prefix,source in [('prob','forecast-results.json'),('return','return-results.json'),('forest','forest-results.json')]:
        for m in (2,5):
            for sc in ('ordinary','adverse','catastrophe'):
                specs[f'expiry_{prefix}_{m}_{sc}']=(source,f'{m}|causal|{sc}')
    for sc in ('ordinary','adverse','catastrophe'):
        specs[f'expiry_e031_causal_{sc}']=('forecast-results.json',f'E031|matched_causal|{sc}')
    modules=[*specs,'expiry_precursor_evaluator','expiry_sensex_unavailable']
    h.initialize(ROOT,ROOT.parent/'Production_Trading-sentinel',out,'2024-01-01','2025-12-31','2026-11-03',modules)
    initial=json.loads((HERE/'initial.json').read_text());proof={}
    for y,want in initial['data'].items():
        p=HERE.parent/f'2026-11-03-expiry-e02/_local/{y}.sqlite';assert sha(p)==want
        proof[str(p.resolve())]=dict(sha256=want,verified_current_sha256=sha(p))
    summary=json.loads((HERE/'dataset-summary.json').read_text())
    for n,key in [('cases.npz','private_case_sha256'),('cases-meta.json','private_meta_sha256')]:
        p=HERE/'_local'/n;assert sha(p)==summary[key]
        proof[str(p.resolve())]=dict(sha256=summary[key],verified_current_sha256=sha(p))
    sys.path.insert(0,str(ROOT/'python-engine'))
    import expiry_paper as EP
    from config import settings
    fee_snapshot=EP.fee_schedule('NFO')
    prior_fee=json.loads((HERE.parent/'2026-11-03-expiry-e032-structure/audit-results.json').read_text())['native_fee_snapshot']
    assert fee_snapshot==prior_fee,'Research fee basis changed from exactly reproduced baseline'
    dump(out/'data-proof.json',dict(files=proof,api_calls=0,year2023_read=False,
      caveat='Raw selected DBs and private arrays remain ignored owner evidence outside this folder; full bytes verified before sealing'))
    dump(out/'configuration.json',dict(classification='SEEN_2024_2025_NO_QUALIFICATION',own_cash=25000,normalized_lot=65,
       native_fees='Current NFO snapshot, not historical lot/tax performance',native_fee_snapshot=fee_snapshot,
       observed_dev_switches={k:bool(getattr(settings,k)) for k in ('EXPIRY_E02_SHADOW_ENABLED','EXPIRY_E03_SHADOW_ENABLED','EXPIRY_E031_SHADOW_ENABLED')},
       baseline_ticket=1250,baseline_day=2500,
       extra_risk_ticket=1562.5,extra_risk_day=3125,brakes=[1500,3000,4000],slots=2,
       causal_calendar='April 4 2024-December 30 2025; first 13 expiries train only; separate fresh matched control',
       forecast_basis='Fixed causal features, adverse labels, day weights, training-only transforms, prior-quarter refits',
       fill_basis='Completed-bar decisions; next executable open or stated severe high/low; model spreads and 20% volume proxy',
       nine_primary_verdicts=json.loads((HERE/'decisions.json').read_text()),
       before_score_commits=['83fdf76','db05ff6','0b77af6','8b78a40','2bb557e'],
       enabled=False,deployed=False,runtime_changed=False,selected_candidate=None))
    inputs=['configuration.json','data-proof.json']
    for p in sorted(HERE.glob('*.py')):
        n='source/'+p.name;target=out/n;target.parent.mkdir(exist_ok=True);shutil.copyfile(p,target);inputs.append(n)
    for n in ('PLAN.md','PRECURSORS.md','RETURNS.md','SMART.md','FOREST.md','LITERATURE.md','initial.json','dataset-summary.json',
              'freeze-size.json','freeze-forecast.json','freeze-return.json','freeze-smart.json','freeze-forest.json'):
        shutil.copyfile(HERE/n,out/n);inputs.append(n)
    h.seal(out,inputs)
    artifacts=['analysis.md','verification.json','audit-results.json','diagnostics.json','decisions.json','daily-results.csv','trades.csv',
               'size-results.json','smart-results.json','forecast-results.json','return-results.json','forest-results.json']
    shutil.copyfile(ROOT/'docs/EXPIRY_RESEARCH_ANTICIPATION.md',out/'analysis.md')
    for n in artifacts[1:]:shutil.copyfile(HERE/n,out/n)
    dates=[];dt=date(2024,1,1)
    while dt<=date(2025,12,31):dates.append(dt.isoformat());dt+=timedelta(days=1)
    empty={k:None for k in ('closed_trades','signals','filled_fee_pnl','assumed_pnl','modeled_net','unresolved')}
    limitations=['Both years seen by the research program; no independent qualification',
      'Current lot/fees normalized; not historically realizable tax/lot returns',
      'No historical quote/depth/queue or intrabar fill proof; stops may gap',
      'Unknown dates unavailable, not zero; standalone arms are not whole-system profit']
    for module,(source,key) in specs.items():
        run=raw[source]['runs'][key];known={d['day']:d for d in run['days']}
        def money(d):return dict(closed_trades=d['trades'],signals=None,filled_fee_pnl=d['net'],assumed_pnl=0.,modeled_net=d['net'],unresolved=d['unresolved'])
        daily=[]
        for day in dates:
            d=known.get(day)
            daily.append(dict(date=day,status='PARTIAL' if d else 'UNAVAILABLE',metrics=money(d) if d else empty.copy(),
                reason='Known selected expiry bar experiment; zero means no model entry' if d else 'Outside fixed evaluation calendar/training-only or no assessed selected expiry tape; not a zero profit day'))
        metrics=money(dict(trades=run['summary']['trades'],net=run['summary']['net'],unresolved=run['summary']['unresolved']))
        assert metrics['unresolved']==0
        dump(out/'modules'/(module+'.json'),dict(module=module,start=dates[0],end=dates[-1],status='PARTIAL',
           fidelity='BAR_LIFECYCLE',population='SHADOW',coverage='PARTIAL',metrics=metrics,daily_results=daily,inputs=inputs,artifacts=artifacts,
           reason=f'{key}, seen-market counterfactual; all new primary hypotheses rejected; no selected candidate',
           assumptions=['Own-cash book continuous over its stated evaluation calendar','Completed-bar decisions, later fills, native fees','No fresh independent test or deployment claim'],limitations=limitations))
    meta=json.loads((HERE/'_local/cases-meta.json').read_text());by_day={}
    for row in meta:
        d=by_day.setdefault(row['day'],dict(signals=0,hits2=0,hits5=0,unresolved_labels=0));d['signals']+=1
        for m in (2,5):d[f'hits{m}']+=row[f'label{m}']['hit'];d['unresolved_labels']+=int(row[f'label{m}']['status']=='UNRESOLVED')
    def ev(d):return {**empty,**d}
    totals={k:sum(d[k] for d in by_day.values()) for k in ('signals','hits2','hits5','unresolved_labels')}
    module='expiry_precursor_evaluator'
    dump(out/'modules'/(module+'.json'),dict(module=module,start=dates[0],end=dates[-1],status='PARTIAL',fidelity='EVALUATOR',
       population='SHADOW',coverage='PARTIAL',reason='18,787 overlapping potential decisions and 37,574 labels; no portfolio or independent trade PnL',
       metrics=ev(totals),inputs=inputs,artifacts=artifacts,
       daily_results=[dict(date=day,status='PARTIAL' if day in by_day else 'UNAVAILABLE',
           reason='Selected expiry evaluator; labels overlap' if day in by_day else 'No assessed tape for this requested calendar date',
           metrics=ev(by_day[day]) if day in by_day else empty.copy()) for day in dates],
       assumptions=['Causal decision features, next-bar adverse labels','Eight unresolved training labels conservative non-hits/full-premium losses'],
       limitations=['Only 105 day clusters, not 18,787 independent samples','Diagnostic precision/mean outcomes cannot be summed as trading profit']))
    module='expiry_sensex_unavailable'
    dump(out/'modules'/(module+'.json'),dict(module=module,start=dates[0],end=dates[-1],status='UNAVAILABLE',fidelity='NONE',
       population='SHADOW',coverage='UNAVAILABLE',reason='No qualified full SENSEX chain/policy in this frozen NIFTY input set; no new acquisition',
       metrics=empty.copy(),daily_results=[],inputs=inputs,artifacts=artifacts,assumptions=[],limitations=['SENSEX performance not inferred from opening-ATM evidence']))
    assert not h.render(out)['errors'];assert not h.verify(out)
    print('ANTICIPATION_STOCK_RECEIPTS_VERIFIED',len(modules),'modules; qualification FALSE; evaluator PnL NULL')

if __name__=='__main__':main()
