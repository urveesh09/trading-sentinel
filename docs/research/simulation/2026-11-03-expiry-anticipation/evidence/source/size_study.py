"""Freeze before scoring. Materialized E03.1 with only per-ticket room generalized."""
from dataclasses import asdict
import inspect,json,socket,sys
def denied(*a,**k):raise AssertionError('Offline only')
socket.socket.connect=denied;socket.create_connection=denied
import guard as G
import risk_lab as R
SCENARIOS=('ordinary','adverse','catastrophe')
FILES=('PLAN.md','guard.py','risk_lab.py','risk_day.py','size_study.py','test_risk.py')

def freeze():
    old=inspect.getsource(R.L.run_day)
    target='room = min(E.BUDGET / rule.slots, budget - spent, cash)'
    assert old.count(target)==1
    source='from risk_lab import E, X, LOT, PARTIAL, directions, choose, stalled, timed_out, recover_lots\nimport math\nimport numpy as np\n\n'+old.replace(target,'room = min(E.BUDGET * (1 + rule.extra) / rule.slots, budget - spent, cash)')
    p=G.HERE/'risk_day.py';assert not p.exists();p.write_text(source,encoding='utf-8')
    G.save('freeze-size.json',dict(head=G.git('rev-parse','HEAD').decode().strip(),files={n:G.sha(G.HERE/n) for n in FILES},
       initial_sha256=G.sha(G.HERE/'initial.json'),arms={k:asdict(v) for k,v in R.ARMS.items()},scenarios=SCENARIOS,
       classification='SEEN_DEVELOPMENT',api_calls=0,year2023_read=False))

def verify():
    f=json.loads((G.HERE/'freeze-size.json').read_text())
    for n,h in f['files'].items():assert G.sha(G.HERE/n)==h,n
    assert G.sha(G.HERE/'initial.json')==f['initial_sha256']
    p=(G.HERE/'freeze-size.json').relative_to(G.ROOT).as_posix()
    assert G.git('log','-1','--format=%H','--',p).strip()
    assert not G.git('status','--porcelain','--',p).strip()

def score():
    verify();ts=R.tapes();out={};count=0
    for y,tt in ts.items():
        for sc in SCENARIOS:
            control=R.L.run(tt,R.L.Candidate(**{**asdict(R.L.BASE),'stop':.35,'lock_arm':.5,'lock_floor':1.1}),sc,True)
            current=R.run(tt,R.BASE,sc,True)
            assert current['days']==control['days'] and current['summary']==control['summary']
            count+=sum(d['trades'] for d in current['days'])
    print('BASELINE_EVENT_AND_MONEY_EXACT',count,flush=True)
    for name,rule in R.ARMS.items():
        for basis,tt in [('continuous',ts[2024]+ts[2025]),('2024',ts[2024]),('2025',ts[2025])]:
            for sc in SCENARIOS:
                r=R.run(tt,rule,sc,True);out[f'{name}|{basis}|{sc}']=r
                print(name,basis,sc,{k:r['summary'][k] for k in ('net','without_best','worst','drawdown','trades','unresolved')},flush=True)
    G.save('size-results.json',dict(parity_position_histories=count,mismatches=0,runs=out))

if __name__=='__main__':globals()[sys.argv[1]]()
