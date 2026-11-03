"""Seal standard skill receipts without upgrading failed research to financial qualification."""
from datetime import date,timedelta
from pathlib import Path
import importlib.util,json,shutil,subprocess
import structure_checkpoint as C
HERE,ROOT=C.HERE,C.ROOT

def dump(p,x):p.write_text(json.dumps(x,indent=2)+'\n',encoding='utf-8')
sha=C.sha

def helper():
    p=ROOT/'.agents/skills/sentinel-trading-simulation/scripts/simulation_evidence.py'
    spec=importlib.util.spec_from_file_location('structure_stock_helper',p)
    h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h);return h

def main():
    C.verify()
    assert not C.git('diff','HEAD','--','python-engine').strip()
    h=helper();out=HERE/'evidence';runs={}
    for f in ('round1-results.json','round2-results.json','round3-results.json'):
        runs.update(json.loads((HERE/f).read_text())['runs'])
    arms=('E031','PATIENT','OPTION_LED','RECLAIM','VALUE_CHECK','DEBIT_VERTICAL','BUTTERFLY')
    specs={f'expiry_{arm.lower()}_{sc}':(arm,sc) for arm in arms for sc in ('ordinary','adverse','catastrophe')}
    modules=[*specs,'expiry_micro_30s','expiry_micro_120s','expiry_sensex_unavailable']
    h.initialize(ROOT,ROOT.parent/'Production_Trading-sentinel',out,'2024-01-01','2026-11-03','2026-11-03',modules)
    original=json.loads((HERE/'initial.json').read_text());microfreeze=json.loads((HERE/'freeze-micro-v2.json').read_text())
    proof={}
    for y,want in original['data'].items():
        p=HERE.parent/f'2026-11-03-expiry-e02/_local/{y}.sqlite';assert sha(p)==want
        proof[str(p.resolve())]=dict(sha256=want,verified_current_sha256=sha(p))
    for path,want in microfreeze['sources'].items():
        assert sha(path)==want;proof[path]=dict(sha256=want,verified_current_sha256=sha(path))
    dump(out/'data-proof.json',dict(files=proof,api_calls=0,year2023_read=False,
        limitation='Raw DBs remain ignored local owner evidence outside this receipt folder; full-file hashes checked before sealing'))
    dump(out/'configuration.json',dict(classification='SEEN_DEVELOPMENT_NO_QUALIFICATION',
        own_cash=25000,lot=65,ticket=1250,day_original_reserve=2500,slots=2,drawdown_brakes=[1500,3000,4000],
        ordinary_adverse_severe='Inherited completed-bar/next-open or severe high-low model with spread and 20% volume proxy',
        pack_model='Explicit simultaneous legs; net-debit reserve, gross-long own-cash check, not atomic execution or margin proof',
        quote_model='EVALUATOR conditional next-snapshot fixed-horizon marks, never a portfolio or summed strategy PnL',
        before_scoring_commits={'round1':'120acde','round2':'ee8b147','round3':'bd3653b','micro':'15ed70b'},
        selected_candidate=None,enabled=False,deployed=False))
    inputs=['configuration.json','data-proof.json']
    for p in sorted(HERE.glob('*.py')):
        n='source/'+p.name;target=out/n;target.parent.mkdir(exist_ok=True);shutil.copyfile(p,target);inputs.append(n)
    for n in ('PLAN.md','ROUND2.md','ROUND3.md','MICRO.md','NEXT_EXAM.md','LITERATURE.md','initial.json',
              'freeze-round1.json','freeze-round2.json','freeze-round3.json','freeze-micro-v2.json'):
        shutil.copyfile(HERE/n,out/n);inputs.append(n)
    h.seal(out,inputs)
    artifacts=['analysis.md','verification.json','audit-results.json','round1-results.json','round2-results.json',
       'round3-results.json','micro-results.json','micro-diagnostics.json','daily-results.csv']
    shutil.copyfile(ROOT/'docs/EXPIRY_RESEARCH_E032_STRUCTURE.md',out/'analysis.md')
    for n in artifacts[1:]:shutil.copyfile(HERE/n,out/n)
    dates=[];day=date(2024,1,1)
    while day<=date(2026,11,3):dates.append(day.isoformat());day+=timedelta(days=1)
    empty={k:None for k in ('closed_trades','signals','filled_fee_pnl','assumed_pnl','modeled_net','unresolved')}
    limitations=['Previously fitted 2024/2025; no independent profitability proof',
        'Current 65-unit lot/current fees normalized historically; no historical lot/tax claim',
        'No historical bid-depth, queue or intrabar execution proof for minute tapes',
        'Missing dates unavailable, not zeros; independent modules are not whole-system profit']
    for module,(arm,sc) in specs.items():
        run=runs[f'{arm}|continuous|{sc}'];known={d['day']:d for d in run['days']};unresolved=run['summary']['unresolved']
        invalid=arm=='BUTTERFLY' and unresolved>0
        def metrics(d):return dict(closed_trades=d['trades']-d['unresolved'],signals=None,filled_fee_pnl=d['net'],assumed_pnl=0.,modeled_net=d['net'],unresolved=d['unresolved'])
        daily=[]
        if not invalid:
            for d in dates:
                row=known.get(d)
                daily.append(dict(date=d,status='PARTIAL' if row else 'UNAVAILABLE',
                  reason='Selected known expiry bar model only' if row else 'No assessed expiry-chain evidence for this requested calendar date',
                  metrics=metrics(row) if row else empty.copy()))
        row=dict(module=module,start=dates[0],end=dates[-1],status='INVALID' if invalid else 'PARTIAL',
            fidelity='BAR_LIFECYCLE',population='SHADOW',coverage='PARTIAL',
            reason=('Unresolved pack written off and freed for continuation: cannot establish a verified flat portfolio; original failed results retained'
                if invalid else f'{arm}, {sc}, seen selected NIFTY expiry bar model; no candidate qualified; severe zeros can mean no accepted fills'),
            metrics=empty.copy() if invalid else metrics(dict(trades=run['summary']['trades'],net=run['summary']['net'],unresolved=unresolved)),
            daily_results=daily,inputs=inputs,artifacts=artifacts,
            assumptions=['Fresh declared own cash continues across selected expiry sessions','Completed-bar decisions and later executions','Native fees on whole lots'],
            limitations=limitations+(['Simultaneous leg fills hypothetical; no broker margin/legging proof'] if arm in ('DEBIT_VERTICAL','BUTTERFLY') else []))
        dump(out/'modules'/(module+'.json'),row)
    micro=json.loads((HERE/'micro-results.json').read_text())
    for horizon in (30,120):
        module=f'expiry_micro_{horizon}s';s=micro['summaries'][f'all|PRESSURE|{horizon}']
        def mm(s):return {**empty,'signals':s['decisions'],'mean_fee_adjusted_markout':s['mean_net'],'measured_events':s['measured']}
        daily=[]
        for d in dates:
            sday=micro['summaries'].get(f'{d}|PRESSURE|{horizon}')
            available=sday is not None and sday['measured']>0
            daily.append(dict(date=d,status='PARTIAL' if available else 'UNAVAILABLE',
              reason='Overlapping fixed-horizon quote observations, not a portfolio' if available else 'No five-level measured pressure events in this study; unavailable is not zero profit',
              metrics=mm(sday) if available else empty.copy()))
        dump(out/'modules'/(module+'.json'),dict(module=module,start=dates[0],end=dates[-1],status='PARTIAL',
           fidelity='EVALUATOR',population='SHADOW',coverage='PARTIAL',metrics=mm(s),daily_results=daily,inputs=inputs,artifacts=artifacts,
           reason='Four seen recorded quote days; mean markout after costs is negative; no filled trade PnL claimed',
           assumptions=['Decision quote then next-snapshot fresh ask walk; fixed-horizon later bid walk; current fees'],
           limitations=['Overlapping events, four day clusters, no independent forward qualification','Ten-second snapshots cannot prove subsecond order flow or queue','Not a funded, stopped, cash-continuous lifecycle']))
    module='expiry_sensex_unavailable'
    dump(out/'modules'/(module+'.json'),dict(module=module,start=dates[0],end=dates[-1],status='UNAVAILABLE',
       fidelity='NONE',population='SHADOW',coverage='UNAVAILABLE',metrics=empty.copy(),daily_results=[],inputs=inputs,artifacts=artifacts,
       reason='No two-year full SENSEX expiry selection chain/policy qualified in this frozen NIFTY study; no SENSEX replay inferred from opening-ATM history',
       assumptions=[],limitations=['No new acquisition; SENSEX performance unknown']))
    assert not h.render(out)['errors']
    assert not h.verify(out)
    print('STOCK_EVIDENCE_VERIFIED',len(modules),'modules; butterfly orphan portfolio claims INVALID; evaluator PnL null; qualification FALSE')

if __name__=='__main__':main()
