"""Freeze/fixed-fit nonlinear factor check, no new book mechanics."""
import json,socket,sys
def denied(*a,**k):raise AssertionError('Offline only')
socket.socket.connect=denied;socket.create_connection=denied
import guard as G
import risk_lab as R
import precursor as P
import return_lab as V
import return_study as T
import smart_study as S
import forest as B
import numpy as np

FILES=('FOREST.md','forest.py','forest_study.py','test_forest.py')

def freeze():
    G.save('freeze-forest.json',dict(head=G.git('rev-parse','HEAD').decode().strip(),files={n:G.sha(G.HERE/n) for n in FILES},
       parents={n:G.sha(G.HERE/n) for n in ('freeze-smart.json','smart-results.json')},classification='SEEN_FIXED_NONLINEAR_CHECK',api_calls=0))

def verify():
    S.verify();f=json.loads((G.HERE/'freeze-forest.json').read_text())
    for n,h in {**f['files'],**f['parents']}.items():assert G.sha(G.HERE/n)==h,n
    path=(G.HERE/'freeze-forest.json').relative_to(G.ROOT).as_posix()
    assert G.git('log','-1','--format=%H','--',path).strip()
    assert not G.git('status','--porcelain','--',path).strip()

def score():
    verify();ts,x,ys,days,years,meta=T.load();out={};models={};diagnostics={};allpred={}
    hits=np.load(G.LOCAL/'cases.npz')
    for multiple in (2,5):
        y=ys[multiple]
        for train,test in ((2024,2025),(2025,2024)):
            a=years==train;b=years==test;model=B.fit(x[a],y[a],days[a]);pred=B.predict(model,x[b],multiple)
            mm=[r for r,keep in zip(meta,b) if keep];key=f'{multiple}|train{train}|test{test}';models[key]=model;allpred[key]=pred
            actual=hits[f'y{multiple}'][b]
            diagnostics[key]=dict(positive_predictions=int(np.sum(pred>0)),mean_predicted=float(pred.mean()),
                top5_precision=float(actual[np.argsort(pred)[-int(np.ceil(len(pred)*.05)):]].mean()),
                top1_precision=float(actual[np.argsort(pred)[-int(np.ceil(len(pred)*.01)):]].mean()),
                actual_prevalence=float(actual.mean()),ranking_only_not_a_portfolio=True)
            V.activate(mm,pred)
            for sc in T.F.SZ.SCENARIOS:
                r=V.run(ts[test],P.forecast_rule(multiple),sc,True);out[f'{key}|{sc}']=r
                print('FOREST_TRANSFER',key,sc,{k:r['summary'][k] for k in ('net','without_best','worst','drawdown','trades')},flush=True)
        all_tapes=ts[2024]+ts[2025];tt=all_tapes[13:];pred=np.full(len(y),np.nan);quarter_models={}
        quarters=sorted({f'{t.day[:4]}Q{(int(t.day[5:7])-1)//3+1}' for t in tt})
        for quarter in quarters:
            year=int(quarter[:4]);q=int(quarter[-1]);start=f'{year}-{(q-1)*3+1:02}-01'
            end=f'{year+1}-01-01' if q==4 else f'{year}-{q*3+1:02}-01'
            a=days<start;b=(days>=start)&(days<end)&(days>=tt[0].day)
            model=B.fit(x[a],y[a],days[a]);pred[b]=B.predict(model,x[b],multiple);quarter_models[quarter]=model
        mask=np.isfinite(pred);mm=[r for r,keep in zip(meta,mask) if keep];key=f'{multiple}|causal';models[key]=quarter_models;allpred[key]=pred[mask]
        V.activate(mm,pred[mask])
        for sc in T.F.SZ.SCENARIOS:
            r=V.run(tt,P.forecast_rule(multiple),sc,True);out[f'{key}|{sc}']=r
            print('FOREST_CAUSAL',multiple,sc,{k:r['summary'][k] for k in ('net','without_best','worst','drawdown','trades')},flush=True)
    G.save('forest-results.json',dict(models=models,diagnostics=diagnostics,runs=out,classification='SEEN_NOT_QUALIFIED'))
    G.save('forest-predictions.json',{k:v.tolist() for k,v in allpred.items()})

if __name__=='__main__':globals()[sys.argv[1]]()
