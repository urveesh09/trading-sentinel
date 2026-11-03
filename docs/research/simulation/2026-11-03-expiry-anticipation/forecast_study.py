"""Freeze causal label definitions and fixed models before constructing outcome labels."""
from collections import Counter
from dataclasses import asdict,replace
from pathlib import Path
import csv,json,socket,sys,time
def denied(*a,**k):raise AssertionError('Offline only')
socket.socket.connect=denied;socket.create_connection=denied
import guard as G
import risk_lab as R
import precursor as P
import size_study as SZ
import numpy as np

FILES=('PRECURSORS.md','precursor.py','precursor_day.py','forecast_study.py','test_precursor.py')

def freeze():
    old=(G.HERE/'risk_day.py').read_text()
    assert old.count('from risk_lab import')==1
    p=G.HERE/'precursor_day.py';assert not p.exists()
    p.write_text(old.replace('from risk_lab import','from precursor import',1),encoding='utf-8')
    G.save('freeze-forecast.json',dict(head=G.git('rev-parse','HEAD').decode().strip(),files={n:G.sha(G.HERE/n) for n in FILES},
        parent=G.sha(G.HERE/'freeze-size.json'),classification='SEEN_YEARS_FIXED_MODELS_NOT_INDEPENDENT_VALIDATION',
        features=P.NAMES,targets=[2,5],regularization=1.,training_weight='one per expiry day',api_calls=0,year2023_read=False))

def verify():
    SZ.verify();f=json.loads((G.HERE/'freeze-forecast.json').read_text())
    for n,h in f['files'].items():assert G.sha(G.HERE/n)==h,n
    assert G.sha(G.HERE/'freeze-size.json')==f['parent']
    path=(G.HERE/'freeze-forecast.json').relative_to(G.ROOT).as_posix()
    assert G.git('log','-1','--format=%H','--',path).strip()
    assert not G.git('status','--porcelain','--',path).strip()

def dataset(ts):
    path=G.LOCAL/'cases.npz'
    assert not path.exists()
    features=[];meta=[];labels={2:[],5:[]};statuses=Counter()
    selector=replace(R.BASE,max_lots=1)
    for year,tt in ts.items():
        for t in tt:
            for i in np.flatnonzero((t.minute>=780)&(t.minute<900)):
                for d in (1,-1):
                    picked=R.L.choose(t,int(i),d,selector,1250.,25000.)
                    if not picked:continue
                    j,lots,limit=picked;x=P.feature(t,int(i),j,d)
                    if x is None:continue
                    row=dict(day=t.day,year=year,i=int(i),j=j,direction=d,limit=limit,symbol=t.symbols[j])
                    for multiple in (2,5):
                        label=P.label(t,int(i),j,d,limit,multiple);labels[multiple].append(label['hit'])
                        row[f'label{multiple}']=label
                        row[f'fees{multiple}']=P.hurdle(t,int(i),j,multiple)*multiple-1
                        statuses[f'{year}|{multiple}|{label["status"]}']+=1
                    features.append(x);meta.append(row)
            print('LABELLED',t.day,'rows so far',len(meta),flush=True)
    x=np.array(features);y2=np.array(labels[2]);y5=np.array(labels[5]);days=np.array([r['day'] for r in meta]);years=np.array([r['year'] for r in meta])
    np.savez_compressed(path,x=x,y2=y2,y5=y5,days=days,years=years)
    (G.LOCAL/'cases-meta.json').write_text(json.dumps(meta),encoding='utf-8')
    G.save('dataset-summary.json',dict(rows=len(x),features=list(P.NAMES),days=len(set(days)),statuses=dict(statuses),
        private_case_sha256=G.sha(path),private_meta_sha256=G.sha(G.LOCAL/'cases-meta.json'),
        by_year={str(y):dict(rows=int(np.sum(years==y)),days=len(set(days[years==y])),double_hits=int(np.sum(y2[years==y])),hero_hits=int(np.sum(y5[years==y]))) for y in (2024,2025)},
        caveat='Overlapping evaluator examples, never independent or summed portfolio PnL'))
    return x,{2:y2,5:y5},days,years,meta

def metrics(y,p,hurdles):
    n=max(1,int(math_ceil(len(p)*.05)))
    top=np.argsort(p)[-n:];admitted=p>hurdles
    return dict(rows=len(y),hits=int(y.sum()),prevalence=float(y.mean()),brier=float(np.mean((p-y)**2)),
        top5_precision=float(y[top].mean()),top5_lift=float(y[top].mean()/y.mean()) if y.mean()>0 else None,
        hurdle_admissions=int(admitted.sum()),hurdle_hits=int(y[admitted].sum()),
        hurdle_precision=float(y[admitted].mean()) if admitted.any() else None,
        max_probability=float(max(p)),mean_probability=float(np.mean(p)))

def math_ceil(x):return int(np.ceil(x))

def score():
    verify();ts=R.tapes();x,ys,days,years,meta=dataset(ts);out={};models={};evaluations={};predictions={}
    for year,tt in ts.items():
        for sc in SZ.SCENARIOS:
            assert P.run(tt,P.BASE,sc,True)['days']==R.run(tt,R.BASE,sc,True)['days']
    for multiple in (2,5):
        y=ys[multiple]
        for train,test in ((2024,2025),(2025,2024)):
            a=years==train;b=years==test;model=P.fit(x[a],y[a],days[a]);p=P.predict(model,x[b]);mm=[r for r,keep in zip(meta,b) if keep]
            key=f'{multiple}|train{train}|test{test}';models[key]=model
            evaluations[key]=metrics(y[b],p,np.array([(1+r[f'fees{multiple}'])/multiple for r in mm]));predictions[key]=p
            P.activate(mm,p,multiple)
            for sc in SZ.SCENARIOS:
                r=P.run(ts[test],P.forecast_rule(multiple),sc,True);out[f'{key}|{sc}']=r
                print('FORECAST',key,sc,r['summary'],flush=True)
            print('PREDICTION',key,evaluations[key],flush=True)
        # First 13 expiries train only; quarterly refits use prior quarters' completed days.
        all_tapes=ts[2024]+ts[2025];evaluation_tapes=all_tapes[13:];prob=np.full(len(y),np.nan);causal_models={}
        quarters=sorted({f'{t.day[:4]}Q{(int(t.day[5:7])-1)//3+1}' for t in evaluation_tapes})
        for quarter in quarters:
            year=int(quarter[:4]);q=int(quarter[-1]);start=f'{year}-{(q-1)*3+1:02}-01'
            end=f'{year+1}-01-01' if q==4 else f'{year}-{q*3+1:02}-01'
            train=days<start;test=(days>=start)&(days<end)&(days>=evaluation_tapes[0].day)
            assert sum(t.day<start for t in all_tapes)>=13 and len(set(days[train]))>=2
            model=P.fit(x[train],y[train],days[train]);prob[test]=P.predict(model,x[test]);causal_models[quarter]=model
        selected=np.isfinite(prob);mm=[r for r,keep in zip(meta,selected) if keep];p=prob[selected]
        key=f'{multiple}|causal';models[key]=causal_models
        evaluations[key]=metrics(y[selected],p,np.array([(1+r[f'fees{multiple}'])/multiple for r in mm]));predictions[key]=p
        P.activate(mm,p,multiple)
        for sc in SZ.SCENARIOS:
            r=P.run(evaluation_tapes,P.forecast_rule(multiple),sc,True);out[f'{key}|{sc}']=r
            print('CAUSAL',multiple,sc,r['summary'],flush=True)
            if multiple==2:out[f'E031|matched_causal|{sc}']=P.run(evaluation_tapes,P.BASE,sc,True)
    # Bind trained coefficients/probabilities; never retune on these results.
    G.save('forecast-results.json',dict(classification='SEEN_RESEARCH_NOT_QUALIFIED',models=models,evaluations=evaluations,runs=out,
        causal_calendar=[t.day for t in (ts[2024]+ts[2025])[13:]],baseline_daily_event_parity=True))
    G.save('forecast-predictions.json',{k:v.tolist() for k,v in predictions.items()})

if __name__=='__main__':globals()[sys.argv[1]]()
