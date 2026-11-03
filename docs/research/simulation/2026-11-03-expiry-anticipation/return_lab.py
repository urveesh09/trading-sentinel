"""After-cost mean-return forecasts. No probability hurdle and no fitted threshold."""
from dataclasses import dataclass,asdict,replace
import numpy as np
import precursor as P
E,X,D,L,LOT,PARTIAL=P.E,P.X,P.D,P.L,P.LOT,P.PARTIAL
stalled,timed_out,recover_lots=P.stalled,P.timed_out,P.recover_lots
BASE=P.BASE

def fit(x,y,days):
    _,inverse,counts=np.unique(days,return_inverse=True,return_counts=True);w=1./counts[inverse]
    impute=np.array([np.median(x[np.isfinite(x[:,j]),j]) if np.isfinite(x[:,j]).any() else 0. for j in range(x.shape[1])])
    filled=np.where(np.isfinite(x),x,impute);mean=np.average(filled,axis=0,weights=w)
    scale=np.sqrt(np.average((filled-mean)**2,axis=0,weights=w));scale=np.where(scale<1e-8,1.,scale)
    z=P.transform(x,impute,mean,scale);penalty=np.ones(z.shape[1]);penalty[0]=1e-8
    b=np.linalg.solve(z.T@(w[:,None]*z)+np.diag(penalty),z.T@(w*y))
    return dict(impute=impute.tolist(),mean=mean.tolist(),scale=scale.tolist(),coefficients=b.tolist(),
       training_rows=len(x),training_days=len(counts),training_day_weight=float(w.sum()),
       training_mean_return=float(np.average(y,weights=w)),penalty=1.)

def predict(model,x,multiple):
    z=P.transform(x,np.array(model['impute']),np.array(model['mean']),np.array(model['scale']))
    return np.clip(z@np.array(model['coefficients']),-1.25,multiple-1)

ACTIVE={}
def activate(meta,values):
    global ACTIVE
    ACTIVE={}
    for row,v in zip(meta,values):
        now=ACTIVE.setdefault(row['day'],{});old=now.get(row['i'])
        if old is None or v>old[2]:now[row['i']]=(row['j'],row['direction'],float(v))

def directions(t,rule):
    if rule.predictor=='baseline':return L.directions(t,rule)
    out=np.zeros(t.n,dtype=np.int8)
    for i,(j,d,v) in ACTIVE.get(t.day,{}).items():
        if v>0:out[i]=d
    return out

def choose(t,i,d,rule,budget,cash):
    if rule.predictor=='baseline':return P.R.choose(t,i,d,rule,budget,cash)
    row=ACTIVE.get(t.day,{}).get(i)
    if row is None or row[1]!=d:return None
    return P.R.resize(t,i,row[0],1,budget,cash,.10)

def run(tapes,rule=BASE,scenario='ordinary',details=False):
    from return_day import run_day
    cash=peak=E.START_CASH;days=[]
    for t in tapes:
        dd=peak-cash;scale=0. if dd>=4000 else .25 if dd>=3000 else .5 if dd>=1500 else 1.
        row=run_day(t,rule,scenario,cash,min(E.BUDGET*scale,cash),details)
        cash=round(cash+row['net'],2);peak=max(peak,cash);assert cash>=-.01
        row.update(cash_after=cash,scale=scale);days.append(row)
    return dict(rule=asdict(rule),scenario=scenario,summary=E.summary(days),days=days)
