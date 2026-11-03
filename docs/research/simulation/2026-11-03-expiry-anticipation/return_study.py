"""Freeze a monetary forecast objective; preserve original probability forecasts."""
from pathlib import Path
from dataclasses import asdict
import json,socket,sys
def denied(*a,**k):raise AssertionError('Offline only')
socket.socket.connect=denied;socket.create_connection=denied
import guard as G
import risk_lab as R
import precursor as P
import forecast_study as F
import return_lab as V
import numpy as np

FILES=('RETURNS.md','return_lab.py','return_day.py','return_study.py','test_return.py')

def freeze():
    source=(G.HERE/'precursor_day.py').read_text();assert source.count('from precursor import')==1
    p=G.HERE/'return_day.py';assert not p.exists();p.write_text(source.replace('from precursor import','from return_lab import',1),encoding='utf-8')
    G.save('freeze-return.json',dict(head=G.git('rev-parse','HEAD').decode().strip(),files={n:G.sha(G.HERE/n) for n in FILES},
       parents={n:G.sha(G.HERE/n) for n in ('freeze-forecast.json','forecast-results.json','dataset-summary.json')},
       targets=[2,5],regularization=1.,classification='SEEN_DEVELOPMENT_NEW_MONETARY_OBJECTIVE',api_calls=0))

def verify():
    F.verify();f=json.loads((G.HERE/'freeze-return.json').read_text())
    for n,h in {**f['files'],**f['parents']}.items():assert G.sha(G.HERE/n)==h,n
    path=(G.HERE/'freeze-return.json').relative_to(G.ROOT).as_posix()
    assert G.git('log','-1','--format=%H','--',path).strip()
    assert not G.git('status','--porcelain','--',path).strip()

def load():
    data=np.load(G.LOCAL/'cases.npz');meta=json.loads((G.LOCAL/'cases-meta.json').read_text());ts=R.tapes()
    summary=json.loads((G.HERE/'dataset-summary.json').read_text())
    assert G.sha(G.LOCAL/'cases.npz')==summary['private_case_sha256'] and G.sha(G.LOCAL/'cases-meta.json')==summary['private_meta_sha256']
    lookup={t.day:t for tt in ts.values() for t in tt};targets={}
    for multiple in (2,5):
        y=[]
        for row in meta:
            label=row[f'label{multiple}']
            if label['entry_i'] is None:y.append(0.);continue
            t=lookup[row['day']];n,entry=R.E.executable(t,label['entry_i'],row['j'],'BUY','adverse',1);assert n==1
            y.append(float(np.clip(label['net']/(entry*R.LOT),-1.25,multiple-1)))
        targets[multiple]=np.array(y)
    return ts,data['x'],targets,data['days'],data['years'],meta

def score():
    verify();ts,x,ys,days,years,meta=load();out={};models={};evaluations={};predictions={}
    for multiple in (2,5):
        y=ys[multiple]
        for train,test in ((2024,2025),(2025,2024)):
            a=years==train;b=years==test;model=V.fit(x[a],y[a],days[a]);pred=V.predict(model,x[b],multiple)
            mm=[r for r,keep in zip(meta,b) if keep];key=f'{multiple}|train{train}|test{test}'
            models[key]=model;predictions[key]=pred
            admitted=pred>0
            evaluations[key]=dict(rows=len(pred),positive_predictions=int(admitted.sum()),mean_predicted_return=float(pred.mean()),
               mean_actual_return=float(y[b].mean()),mean_actual_selected=float(y[b][admitted].mean()) if admitted.any() else None,
               caveat='Overlapping bounded evaluator returns, NOT summed portfolio money')
            V.activate(mm,pred)
            for sc in F.SZ.SCENARIOS:
                r=V.run(ts[test],P.forecast_rule(multiple),sc,True);out[f'{key}|{sc}']=r
                print('RETURN_FORECAST',key,sc,r['summary'],flush=True)
        all_tapes=ts[2024]+ts[2025];evaluation_tapes=all_tapes[13:];pred=np.full(len(y),np.nan);quarter_models={}
        quarters=sorted({f'{t.day[:4]}Q{(int(t.day[5:7])-1)//3+1}' for t in evaluation_tapes})
        for quarter in quarters:
            year=int(quarter[:4]);q=int(quarter[-1]);start=f'{year}-{(q-1)*3+1:02}-01'
            end=f'{year+1}-01-01' if q==4 else f'{year}-{q*3+1:02}-01'
            a=days<start;b=(days>=start)&(days<end)&(days>=evaluation_tapes[0].day)
            model=V.fit(x[a],y[a],days[a]);pred[b]=V.predict(model,x[b],multiple);quarter_models[quarter]=model
        selected=np.isfinite(pred);mm=[r for r,keep in zip(meta,selected) if keep];key=f'{multiple}|causal'
        models[key]=quarter_models;predictions[key]=pred[selected];V.activate(mm,pred[selected])
        for sc in F.SZ.SCENARIOS:
            r=V.run(evaluation_tapes,P.forecast_rule(multiple),sc,True);out[f'{key}|{sc}']=r
            print('RETURN_CAUSAL',multiple,sc,r['summary'],flush=True)
    G.save('return-results.json',dict(models=models,evaluations=evaluations,runs=out,classification='SEEN_NOT_QUALIFIED'))
    G.save('return-predictions.json',{k:v.tolist() for k,v in predictions.items()})

if __name__=='__main__':globals()[sys.argv[1]]()
