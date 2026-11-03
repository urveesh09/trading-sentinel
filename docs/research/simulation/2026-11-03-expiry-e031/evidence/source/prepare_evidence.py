"""Populate stock skill receipts after native source is committed and checked."""
from pathlib import Path
from datetime import date,timedelta
import hashlib,importlib.util,json,shutil,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]

def dump(p,obj):p.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def helper():
    p=ROOT/'.agents/skills/sentinel-trading-simulation/scripts/simulation_evidence.py'
    spec=importlib.util.spec_from_file_location('e031_stock_evidence',p)
    h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    return h

def main():
    assert not subprocess.check_output(['git','diff','HEAD','--','python-engine'],cwd=ROOT)
    h=helper();out=HERE/'evidence'
    modules=['expiry_e03_control','expiry_e031_ordinary','expiry_e031_adverse','expiry_e031_severe']
    h.initialize(ROOT,ROOT.parent/'Production_Trading-sentinel',out,'2024-01-01','2025-12-31','2026-11-03',modules)
    initial=json.loads((HERE/'initial-freeze.json').read_text())
    proof={}
    for y,v in initial['datasets'].items():
        assert sha(v['path'])==v['sha256']
        proof[y]=dict(**v,verified_sha256=sha(v['path']),exists=True)
    dump(out/'data-proof.json',dict(datasets=proof,api_calls=0,year2023_read=False,
             caveat='Raw selected-year snapshots remain in ignored Dev folders; manifest full-file hashes verified, not just manifest bytes'))
    dump(out/'configuration.json',dict(rule=json.loads((HERE/'candidate.json').read_text()),cash_continuity=True,
          starting_cash=25000,daily_original_premium_fees=2500,ticket_ceiling=1250,maximum_tickets=2,lot=65,
          fees='current NFO native fee snapshot, historical normalization',brakes=[1500,3000,4000],
          basis='completed historical exchange minute bars; next bar executions, 20% bar volume proxy, no historical bid-depth proof',
          classification='BOTH YEARS SEEN; not untouched; no financial qualification; disabled; not deployed'))
    inputs=['configuration.json','data-proof.json']
    for p in sorted(HERE.glob('*.py')):
        target=out/'source'/p.name;target.parent.mkdir(exist_ok=True);shutil.copyfile(p,target);inputs.append('source/'+p.name)
    recorded=json.loads((HERE/'recorded-proxy-freeze.json').read_text())
    for path,want in recorded['source'].items():assert sha(path)==want,path
    for name in ('PLAN.md','IMPLEMENTATION_PLAN.md','initial-freeze.json','finalists-freeze.json','forward-freeze.json','candidate.json','recorded-proxy-freeze.json'):
        shutil.copyfile(HERE/name,out/name);inputs.append(name)
    h.seal(out,inputs)
    artifacts=['analysis.md','native-parity.json','robustness.json','friction-audit-v2.json','engine-tests.json','verification.json','recorded-proxy.json']
    shutil.copyfile(ROOT/'docs/EXPIRY_RESEARCH_E031.md',out/'analysis.md')
    for name in artifacts[1:]:shutil.copyfile(HERE/name,out/name)
    raw=json.loads((HERE/'robustness.json').read_text())
    for module,name,sc in zip(modules,('E03','DEFENSIVE','DEFENSIVE','DEFENSIVE'),('ordinary','ordinary','adverse','catastrophe')):
        r=raw['detail'][name][f'continuous|{sc}'];known={d['day']:d for d in r['days']}
        assert sum(d['trades'] for d in known.values())==r['summary']['trades']
        assert abs(sum(d['net'] for d in known.values())-r['summary']['net'])<.02
        def metrics(d):return dict(closed_trades=d['trades'],unresolved=d['unresolved'],filled_fee_pnl=d['net'],assumed_pnl=0.,modeled_net=d['net'])
        daily=[];day=date(2024,1,1)
        while day<=date(2025,12,31):
            d=known.get(day.isoformat())
            daily.append(dict(date=day.isoformat(),status='PARTIAL' if d else 'UNAVAILABLE',
                 reason='Recorded selected-expiry bar model only; zero is a model no-fill' if d else 'No assessed expiry-chain evidence; not a verified non-expiry or a zero-profit day',
                 metrics=metrics(d) if d else {k:None for k in metrics({'trades':0,'unresolved':0,'net':0})}))
            day+=timedelta(days=1)
        row=dict(module=module,start='2024-01-01',end='2025-12-31',status='PARTIAL',fidelity='BAR_LIFECYCLE',population='SHADOW',coverage='PARTIAL',
            reason=f'{name}, {sc}, continuous own cash on SEEN 2024/2025; no financial qualification, disabled, not deployed',
            metrics=metrics(dict(trades=r['summary']['trades'],unresolved=r['summary']['unresolved'],net=r['summary']['net'])),
            daily_results=daily,inputs=inputs,artifacts=artifacts,
            assumptions=['Current 65-unit lot and current fees normalized across years','Fresh declared Rs 25,000 book continues across years',
                         'Completed-bar decisions, next bar open or declared severe high/low, model spread and capped participation'],
            limitations=['Both years previously fitted; no untouched pass','No historical depth/queue or intraminute fill proof',
                         'Missing/unacquired dates unavailable','Severe losses; no guarantee a stop executes at trigger',
                         'Not the unified live portfolio; SENSEX and 2026 full-chain replay unavailable'])
        dump(out/'modules'/(module+'.json'),row)
    report=h.render(out);assert not report['errors'],report['errors']
    assert not h.verify(out)
    print('E031_EVIDENCE_CHECKS_PASSED',len(modules),'modules; original helper unmodified; financial qualification FALSE')

if __name__=='__main__':main()
