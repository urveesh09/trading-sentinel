"""Freeze the final fixed-model allocation hypothesis before its book is scored."""
import json,sys,socket
def denied(*a,**k):raise AssertionError('Offline only')
socket.socket.connect=denied;socket.create_connection=denied
import guard as G
import risk_lab as R
import precursor as P
import return_lab as V
import return_study as T
import smart_lab as S
import numpy as np

FILES=('SMART.md','smart_lab.py','smart_day.py','smart_study.py','test_smart.py')

def freeze():
    source=(G.HERE/'risk_day.py').read_text();assert source.count('from risk_lab import')==1
    p=G.HERE/'smart_day.py';assert not p.exists();p.write_text(source.replace('from risk_lab import','from smart_lab import',1),encoding='utf-8')
    G.save('freeze-smart.json',dict(head=G.git('rev-parse','HEAD').decode().strip(),files={n:G.sha(G.HERE/n) for n in FILES},
       parents={n:G.sha(G.HERE/n) for n in ('freeze-return.json','return-results.json','return-predictions.json')},
       classification='SEEN_ITERATION_FIXED_PAST_QUARTER_FORECAST',api_calls=0))

def verify():
    T.verify();f=json.loads((G.HERE/'freeze-smart.json').read_text())
    for n,h in {**f['files'],**f['parents']}.items():assert G.sha(G.HERE/n)==h,n
    path=(G.HERE/'freeze-smart.json').relative_to(G.ROOT).as_posix()
    assert G.git('log','-1','--format=%H','--',path).strip()
    assert not G.git('status','--porcelain','--',path).strip()

def prepare():
    ts,x,ys,days,years,meta=T.load();result=json.loads((G.HERE/'return-results.json').read_text())
    models=result['models']['5|causal'];values=np.full(len(x),np.nan)
    for quarter,model in models.items():
        year=int(quarter[:4]);q=int(quarter[-1]);start=f'{year}-{(q-1)*3+1:02}-01'
        end=f'{year+1}-01-01' if q==4 else f'{year}-{q*3+1:02}-01'
        mask=(days>=start)&(days<end)&(days>=(ts[2024]+ts[2025])[13].day)
        values[mask]=V.predict(model,x[mask],5)
    actual=np.array(json.loads((G.HERE/'return-predictions.json').read_text())['5|causal'])
    assert np.array_equal(actual,values[np.isfinite(values)])
    S.FORECAST={(r['day'],r['i'],r['j'],r['direction']):float(v) for r,v in zip(meta,values) if np.isfinite(v)}
    S.ELIGIBLE_DAYS={t.day for t in (ts[2024]+ts[2025])[13:]}
    return ts

def score():
    verify();ts=prepare();out={}
    for name,rule in S.ARMS.items():
        for basis,tt in [('continuous',ts[2024]+ts[2025]),('2024',ts[2024]),('2025',ts[2025])]:
            for sc in T.F.SZ.SCENARIOS:
                r=S.run(tt,rule,sc,True);out[f'{name}|{basis}|{sc}']=r
                if name=='E031':assert r['days']==R.run(tt,R.BASE,sc,True)['days']
                print('SMART',name,basis,sc,r['summary'],flush=True)
    G.save('smart-results.json',dict(runs=out,existing_predictions_reproduced_exactly=True,classification='SEEN_NOT_QUALIFIED'))

if __name__=='__main__':globals()[sys.argv[1]]()
