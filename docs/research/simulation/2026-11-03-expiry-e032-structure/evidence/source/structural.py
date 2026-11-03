"""Failed-auction entry and fee-aware value diagnostic; hypotheses, not theoretical fills."""
from dataclasses import dataclass,asdict
import math
import numpy as np
import mechanisms as M

E,X,D,L=M.E,M.X,M.D,M.L
LOT,PARTIAL=M.LOT,M.PARTIAL
stalled,timed_out,recover_lots,patient_cancel=M.stalled,M.timed_out,M.recover_lots,M.patient_cancel

@dataclass(frozen=True)
class Structural(M.Rule):
    sweep_look:int=20
    value_noise:int=30
    value_drift:int=10
    drift_uncertainty:float=1.

BASE=Structural(**asdict(M.BASE))

def reclaim(t,rule):
    out=np.zeros(t.n,dtype=np.int8)
    for i in range(rule.sweep_look,t.n):
        if not rule.start<=t.minute[i]<rule.end:continue
        x=t.x[i-rule.sweep_look:i];f=t.f[i-rule.sweep_look:i]
        if not all(np.isfinite(a).all() for a in (x,f,t.x[i],t.f[i])):continue
        hi,lo=x[:,1].max(),x[:,2].min();fh,fl=f[:,1].max(),f[:,2].min()
        if t.x[i,2]<lo<t.close[i] and t.x[i,0]<t.close[i] and t.f[i,2]<fl<t.f[i,3] and t.f[i,0]<t.f[i,3]:out[i]=1
        elif t.x[i,1]>hi>t.close[i] and t.x[i,0]>t.close[i] and t.f[i,1]>fh>t.f[i,3] and t.f[i,0]>t.f[i,3]:out[i]=-1
    return out

CACHE={}
def directions(t,rule):
    if rule.mechanism!='reclaim':return M.directions(t,rule)
    key=(id(t),rule.sweep_look,rule.start,rule.end)
    if key not in CACHE:CACHE[key]=reclaim(t,rule)
    return CACHE[key]

def normal_option(forward,strike,sd,d):
    x=d*(forward-strike)
    if sd<=0:return max(0.,x)
    z=x/sd
    return x*.5*math.erfc(-z/math.sqrt(2))+sd*math.exp(-.5*z*z)/math.sqrt(2*math.pi)

def implied_sd(price,forward,strike,d):
    if not np.isfinite([price,forward,strike]).all() or price<=max(0,d*(forward-strike)):return None
    lo,hi=0.,max(price*10,abs(forward-strike)*2,1.)
    while normal_option(forward,strike,hi,d)<price:hi*=2
    for _ in range(45):
        mid=(lo+hi)/2
        if normal_option(forward,strike,mid,d)<price:lo=mid
        else:hi=mid
    return (lo+hi)/2

def expiry_forward(t,i):
    spot=t.close[i];pairs=[]
    for k in sorted(np.unique(t.strikes),key=lambda k:abs(k-spot)):
        if abs(k-spot)>100:continue
        js=[np.flatnonzero((t.strikes==k)&(t.kinds==d)) for d in (1,-1)]
        if any(len(j)!=1 for j in js):continue
        c,p=[t.q[i,int(j[0])] for j in js]
        if not np.isfinite([c[3],p[3],c[4],p[4]]).all() or min(c[3],p[3],c[4],p[4])<=0:continue
        pairs.append(float(k+c[3]-p[3]))
        if len(pairs)==3:break
    return float(np.median(pairs)) if len(pairs)==3 else None

def value_edge(t,i,j,d,rule):
    n=rule.value_noise;look=rule.value_drift;hold=rule.hold;remaining=930-t.minute[i]
    if i<max(n,look) or remaining<=hold:return None
    c=t.close[i-n:i+1];f=t.f[i-look:i+1,3]
    if not np.isfinite(c).all() or not np.isfinite(f).all():return None
    forward=expiry_forward(t,i)
    if forward is None:return None
    raw=float(t.q[i,j,3]);k=float(t.strikes[j]);sd=implied_sd(raw,forward,k,d)
    if sd is None:return None
    noise=float(np.std(np.diff(c),ddof=1))
    drift=d*max(0.,min(d*(c[-1]-c[-look-1])/look,d*(f[-1]-f[0])/look)-rule.drift_uncertainty*noise/math.sqrt(look))
    variance=sd*sd*(remaining-hold)/remaining+noise*noise*hold
    future_value=normal_option(forward+drift*hold,k,math.sqrt(variance),d)
    ask=E.up(raw+E.half(raw));bid=E.down(max(0.,future_value-E.half(future_value)))
    edge=(bid-ask)*LOT-E.fee(ask,LOT,True)-E.fee(bid,LOT,False)
    return dict(edge=edge,forward=forward,sd=sd,drift=drift,noise=noise,future_value=future_value)

def choose(t,i,d,rule,budget,cash):
    pick=M.choose(t,i,d,rule,budget,cash)
    if pick and rule.mechanism=='value':
        v=value_edge(t,i,pick[0],d,rule)
        if v is None or v['edge']<=0:return None
    return pick

def run(tapes,rule=BASE,scenario='ordinary',details=False,brakes=True):
    from structural_day import run_day
    cash=peak=E.START_CASH;days=[]
    for t in tapes:
        dd=peak-cash
        scale=0. if brakes and dd>=4000 else .25 if brakes and dd>=3000 else .5 if brakes and dd>=1500 else 1.
        row=run_day(t,rule,scenario,cash,min(E.BUDGET*scale,cash),details)
        cash=round(cash+row['net'],2);peak=max(peak,cash);assert cash>=-.01
        row.update(cash_after=cash,scale=scale);days.append(row)
    return dict(rule=asdict(rule),scenario=scenario,summary=E.summary(days),days=days)
