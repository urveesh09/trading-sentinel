"""Causal EN87–92/94–95 precomputation, with observable event receipts."""
from dataclasses import replace
import numpy as np
from data8 import L7,oi_series,basket,components
import lab8
L4,L6=L7.L4,L7.L6
WINDOW=(780,870)

def window(t): return (t.minute>=WINDOW[0])&(t.minute<WINDOW[1])

def ridge_fit(parts,penalty=10.,intercept_only=False):
    good=[(np.asarray(x,float),np.asarray(y,float)) for x,y in parts if len(y)]
    if not good: return None
    X=np.concatenate([x for x,y in good]); y=np.concatenate([y for x,y in good])
    w=np.concatenate([np.full(len(y),1./len(y)) for x,y in good]);w/=w.sum()
    mu=(w[:,None]*X).sum(0);sd=np.sqrt((w[:,None]*(X-mu)**2).sum(0));sd[sd<1e-10]=1.
    Z=(X-mu)/sd; mean=float(w@y)
    if intercept_only: beta=np.zeros(X.shape[1])
    else: beta=np.linalg.solve(Z.T@(w[:,None]*Z)+penalty/len(good)*np.eye(Z.shape[1]),Z.T@(w*(y-mean)))
    return dict(mu=mu,sd=sd,beta=beta,mean=mean,dates=len(good))

def predict(m,x): return m['mean']+(np.asarray(x)-m['mu'])/m['sd']@m['beta']

def price_features(t):
    F=t.f[:,3];out=np.full((t.n,3),np.nan)
    for i in range(30,t.n):
        w=F[i-30:i+1]; A=t.features[10][i,4]
        if np.isfinite(w).all() and w.min()>0 and np.isfinite(A) and A>0:
            out[i]=[(F[i]-F[i-15])/A,np.std(np.diff(np.log(w))), (t.minute[i]-780)/90]
    return out

def parity_innovation(t):
    """Synthetic spread on minute closes: research proxy, never a measured quote."""
    F=t.f[:,3];n=t.n;base=np.full(n,np.nan);innov=base.copy()
    lookup={(float(K),int(d)):j for j,(K,d) in enumerate(zip(t.strikes,t.kinds))}
    ks=sorted(set(map(float,t.strikes)))
    for i in range(n):
        if not np.isfinite(F[i]):continue
        values=[]
        for K in sorted(ks,key=lambda K:abs(K-F[i]))[:5]:
            c,p=lookup.get((K,1)),lookup.get((K,-1))
            if c is None or p is None:continue
            qc,qp=t.q[i,c],t.q[i,p]
            if np.isfinite(qc).all() and np.isfinite(qp).all() and qc[4]>0 and qp[4]>0:
                values.append(K+qc[3]-qp[3]-F[i])
        if len(values)>=3:base[i]=np.median(values)
        past=base[max(0,i-20):i];past=past[np.isfinite(past)]
        if np.isfinite(base[i]) and len(past)>=10:innov[i]=base[i]-np.median(past)
    return base,innov

def crossing(v,q,win):
    out=np.zeros(len(v),np.int8)
    if not np.isfinite(q):return out
    for i in np.flatnonzero(win):
        if i>0 and np.isfinite(v[i]) and np.isfinite(v[i-1]) and abs(v[i])>q>=abs(v[i-1]):out[i]=int(np.sign(v[i]))
    return out

def quantile(history,column=0):
    if len(history)<20:return np.nan
    p=np.concatenate([x[:,column] for x in history[-20:]])
    p=p[np.isfinite(p)]
    return float(np.percentile(abs(p),80)) if len(p)>=200 else np.nan

def pullbacks(t,raw,S,q,mode='reclaim',high=False,unrelated=None):
    out=np.zeros(t.n,np.int8);picks={};logs=[]; sp=L4.spec_of(t)
    for i in np.flatnonzero(raw):
        d=int(raw[i]); A=float(t.features[10][i,4])
        if not np.isfinite(A) or A<=0:continue
        chooser=lab8.highest if high else L4.choose4
        pick=chooser(sp,t,int(i),d,lab8.ARMS['EN83'],2500.,30000.)
        if pick is None:
            logs.append(dict(event_i=int(i),d=d,status='UNAFFORDABLE_AT_EVENT'));continue
        j=pick[0];ask0=L4.ask_of(t.q[i,j,3]);peak=d*float(t.f[i,3]);pulled=False;trigger=None;why='EXPIRED'
        for b in range(i+1,min(i+6,t.n)):
            if t.minute[b]>=870:why='WINDOW_END';break
            cur=S[b] if unrelated is None else unrelated[b]
            if not np.isfinite(cur) or d*cur<=q:why='INFORMATION_LOST';break
            f=float(t.f[b,3])
            if not np.isfinite(f):why='MISSING_FUTURE';break
            peak=max(peak,d*f);pulled=pulled or peak-d*f>=.5*A
            prev=t.f[b-1,1] if d>0 else t.f[b-1,2]
            reclaim=np.isfinite(prev) and d*(f-prev)>0
            if mode=='delay' or (pulled and reclaim):trigger=b;why='TRIGGER';break
        log=dict(event_i=int(i),d=d,j=int(j),ask0=float(ask0),atr=A,status=why)
        if trigger is not None:
            # One deterministic earliest-armed event wins a same-clock collision.
            if out[trigger]==0:
                out[trigger]=d;picks[trigger]=dict(j=int(j),ask0=float(ask0),event_i=int(i));log['i']=int(trigger)
            else:log['status']='SAME_CLOCK_COLLISION'
        logs.append(log)
    return out,picks,logs

def prepare(book):
    history=[]; feature_history=[]; score_history=[]; receipts=[]
    for t in book:
        C=oi_series(t);lag=oi_series(t,True);S,U,D=C[:,0],C[:,1],C[:,2];win=window(t)
        X=price_features(t);base,innovation=parity_innovation(t)
        t.frame8=dict(components=C,lag_components=lag,price=X,parity_base=base,innovation=innovation)
        t.signals8={};t.picks8={};t.events8=[]
        q=quantile(history,0);qu=quantile(history,1); t.threshold8=q
        raw=crossing(S,q,win); con=crossing(U,qu,win)
        t.signals8['RAW']=raw;t.signals8['CONTRACT']=con
        t.signals8['CONTRACT_GROWTH']=np.where(con,np.sign(np.nan_to_num(D)),0).astype(np.int8)
        t.signals8['CONTRACT_RAW']=np.where(con,np.sign(np.nan_to_num(S)),0).astype(np.int8)
        edirs=L7.signals7(t,L7.E03_ENV)[0]
        gate=np.zeros(t.n,np.int8);unrelated=np.full(t.n,np.nan)
        if len(score_history)>=20:unrelated=score_history[-20].copy()
        if np.isfinite(q):gate=np.where((edirs*S>q)&win,edirs,0).astype(np.int8)
        t.signals8['GATE']=gate
        t.signals8['GATE_UNRELATED']=np.where((edirs*unrelated>q)&win,edirs,0).astype(np.int8)
        for i in np.flatnonzero(edirs):
            status='WARMUP_THRESHOLD' if not np.isfinite(q) else 'MISSING_SCORE' if not np.isfinite(S[i]) else 'AGREE' if gate[i] else 'NO_AGREEMENT'
            t.events8.append(dict(setup='GATE_DECISION',i=int(i),m=int(t.minute[i]),d=int(edirs[i]),status=status,
                                  S=float(S[i]) if np.isfinite(S[i]) else None,threshold=float(q) if np.isfinite(q) else None))
        residual=np.full(t.n,np.nan);predS=residual.copy();qt=np.nan;model=None
        if len(feature_history)>=20:
            model=ridge_fit(feature_history[-20:])
            if model is not None:
                good=win&np.isfinite(X).all(1)&np.isfinite(S)
                predS[good]=predict(model,X[good]);residual[good]=S[good]-predS[good]
                past=np.concatenate([y-predict(model,x) for x,y in feature_history[-20:]])
                qt=float(np.percentile(abs(past),80)) if len(past)>=200 else np.nan
        resid=crossing(residual,qt,win)
        t.signals8['RESID']=resid
        t.signals8['RESID_PX']=np.where(resid,np.sign(np.nan_to_num(predS)),0).astype(np.int8)
        for mode,high,key in [('reclaim',False,'PULL'),('delay',False,'DELAY'),('reclaim',True,'PULL_HIGH')]:
            dirs,picks,logs=pullbacks(t,raw,S,q,mode,high)
            t.signals8[key]=dirs
            t.picks8.update({(key,i):v for i,v in picks.items()})
            t.events8.extend(dict(setup=key,**x) for x in logs)
        dirs,picks,logs=pullbacks(t,raw,S,q,unrelated=unrelated)
        t.signals8['PULL_UNRELATED']=dirs;t.picks8.update({('PULL_UNRELATED',i):v for i,v in picks.items()})
        t.events8.extend(dict(setup='PULL_UNRELATED',**x) for x in logs)
        t.residual8=residual
        for key in ('RAW','CONTRACT','RESID','GATE'):
            for i in np.flatnonzero(t.signals8[key]):
                t.events8.append(dict(setup=key,i=int(i),m=int(t.minute[i]),d=int(t.signals8[key][i]),
                                      S=float(S[i]) if np.isfinite(S[i]) else None,
                                      threshold=float(q) if np.isfinite(q) else None))
        covered=np.mean(np.isfinite(S[win]))>=.95
        good=win&np.isfinite(X).all(1)&np.isfinite(S)
        receipts.append(dict(day=t.day,covered=bool(covered),threshold=float(q) if np.isfinite(q) else None,
                             prior_covered_dates=[x['day'] for x in receipts if x['covered']][-20:],
                             residual_model_dates=0 if model is None else model['dates'],
                             events={k:int(np.count_nonzero(v)) for k,v in t.signals8.items()}))
        if covered:
            history.append(C[win].copy()); feature_history.append((X[good].copy(),S[good].copy()));score_history.append(S.copy())
    return receipts
