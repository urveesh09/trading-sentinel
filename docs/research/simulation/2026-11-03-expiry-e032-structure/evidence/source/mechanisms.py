"""Distinct information/execution hypotheses; all trading is offline research."""
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib, json, math, sys
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026-11-03-expiry-e031'))
import lab as L
X,E,D=L.X,L.E,L.D
LOT,PARTIAL=L.LOT,L.PARTIAL

@dataclass(frozen=True)
class Rule(L.Candidate):
    mechanism:str='control'
    wait_bars:int=3
    option_bars:int=3
    history:int=20

BASE=Rule(**{**asdict(L.BASE),'stop':.35,'lock_arm':.5,'lock_floor':1.1})
E03=Rule(**asdict(L.BASE))

def option_signal(t,rule):
    """Price-only cross-section; neither OI nor trade volume identifies dealer inventory."""
    out=np.zeros(t.n,dtype=np.int8)
    pairs={float(k):[np.flatnonzero((t.strikes==k)&(t.kinds==d)) for d in (1,-1)] for k in np.unique(t.strikes)}
    pairs={k:tuple(int(a[0]) for a in v) for k,v in pairs.items() if all(len(a)==1 for a in v)}
    prev=0
    for i in range(rule.history+rule.option_bars,t.n):
        if not rule.start<=t.minute[i]<rule.end:prev=0;continue
        if not np.isfinite(t.close[i]):prev=0;continue
        near=sorted((k for k in pairs if abs(k-t.close[i])<=100),key=lambda k:abs(k-t.close[i]))[:3]
        if len(near)!=3:prev=0;continue
        jj=[j for k in near for j in pairs[k]]
        # Fix today's CURRENT three strikes throughout the lookback. No future strike map.
        q=t.q[i-rule.history-rule.option_bars:i+1,jj]
        if not np.isfinite(q[:,:,3:]).all() or (q[:,:,3]<=0).any() or (q[:,:,4]<=0).any():prev=0;continue
        odds=np.log(q[:,0::2,3]/q[:,1::2,3])
        delta=odds[rule.option_bars:]-odds[:-rule.option_bars]
        movement=float(np.median(delta[-1]));d=int(np.sign(movement))
        typical=float(np.median(np.abs(np.median(delta[:-1],axis=1))))
        okay=(d!=0 and typical>0 and abs(movement)>typical and np.sum(d*delta[-1]>0)>=2)
        old=i-rule.option_bars
        okay=okay and np.isfinite([t.close[old],t.f[i,3],t.f[old,3]]).all() and d*(t.close[i]-t.close[old])>0 and d*(t.f[i,3]-t.f[old,3])>0
        now=d if okay else 0
        if now and now!=prev:out[i]=now
        prev=now
    return out

SIGNALS={}
def directions(t,rule):
    if rule.mechanism!='option_led':return L.directions(t,rule)
    key=(id(t),rule.option_bars,rule.history,rule.start,rule.end)
    if key not in SIGNALS:SIGNALS[key]=option_signal(t,rule)
    return SIGNALS[key]

def choose(t,i,d,rule,budget,cash):
    picked=L.choose(t,i,d,rule,budget,cash)
    if picked and rule.mechanism=='patient':
        j,lots,limit=picked
        return j,lots,min(limit,E.down(float(t.q[i,j,3])))
    return picked

def patient_cancel(t,i,decision,sign,atr,rule):
    if i-decision>rule.wait_bars or t.minute[i]>rule.end:return True
    # Only the PREVIOUS completed index bar can cancel an order at this open.
    c=t.close[i-1]
    return not np.isfinite(c) or sign*(c-t.close[decision]) < -atr

stalled,timed_out=L.stalled,L.timed_out
recover_lots=X.recover_lots

def run(tapes,rule=BASE,scenario='ordinary',details=False,brakes=True):
    from mechanism_day import run_day
    cash=peak=E.START_CASH;days=[]
    for t in tapes:
        dd=peak-cash
        scale=0. if brakes and dd>=4000 else .25 if brakes and dd>=3000 else .5 if brakes and dd>=1500 else 1.
        row=run_day(t,rule,scenario,cash,min(E.BUDGET*scale,cash),details)
        cash=round(cash+row['net'],2);peak=max(peak,cash)
        assert cash>=-.01
        row.update(cash_after=cash,scale=scale);days.append(row)
    return dict(rule=asdict(rule),scenario=scenario,summary=E.summary(days),days=days)

def tapes():return L.tapes()
