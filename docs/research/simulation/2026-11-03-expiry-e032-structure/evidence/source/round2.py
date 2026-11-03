"""Round two freeze and score. Does not alter the round-one implementation or evidence."""
from dataclasses import replace,asdict
import json,sys
import structure_checkpoint as C
import mechanisms as M
import structural as S
import run_study as R

ARMS={'RECLAIM':replace(S.BASE,mechanism='reclaim'),'VALUE_CHECK':replace(S.BASE,mechanism='value')}
FILES=('ROUND2.md','structural.py','structural_day.py','round2.py','test_structural.py')

def freeze():
    source=(M.HERE/'mechanism_day.py').read_text().replace('from mechanisms import','from structural import',1)
    p=M.HERE/'structural_day.py';assert not p.exists();p.write_text(source,encoding='utf-8')
    R.save('freeze-round2.json',dict(head=C.git('rev-parse','HEAD').decode().strip(),
       files={n:C.sha(M.HERE/n) for n in FILES},prior_freeze=C.sha(M.HERE/'freeze-round1.json'),
       arms={k:asdict(v) for k,v in ARMS.items()},classification='SEEN_DEVELOPMENT',api_calls=0))

def verify():
    R.verify();f=json.loads((M.HERE/'freeze-round2.json').read_text())
    for n,h in f['files'].items():assert C.sha(M.HERE/n)==h,n
    path=(M.HERE/'freeze-round2.json').relative_to(C.ROOT).as_posix()
    assert C.git('log','-1','--format=%H','--',path).strip()
    assert not C.git('status','--porcelain','--',path).strip()

def score():
    verify();ts=M.tapes();out={}
    for y,tt in ts.items():
        for sc in R.SCENARIOS:
            assert S.run(tt,S.BASE,sc,True)['days']==M.run(tt,M.BASE,sc,True)['days']
    for name,rule in ARMS.items():
        for basis,tt in [('continuous',ts[2024]+ts[2025]),('2024',ts[2024]),('2025',ts[2025])]:
            for sc in R.SCENARIOS:
                r=S.run(tt,rule,sc,True);out[f'{name}|{basis}|{sc}']=r
                print(name,basis,sc,{k:r['summary'][k] for k in ('net','without_best','worst','drawdown','trades','unresolved')},flush=True)
    R.save('round2-results.json',dict(baseline_daily_event_parity=True,runs=out))

if __name__=='__main__':globals()[sys.argv[1]]()
