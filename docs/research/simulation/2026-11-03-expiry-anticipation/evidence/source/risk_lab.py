"""Same entry/contract, fixed extra reserve. Isolate whole-lot runner economics."""
from dataclasses import dataclass,asdict,replace
from pathlib import Path
import math,sys
import numpy as np
import guard as G
sys.path.insert(0,str(G.HERE.parent/'2026-11-03-expiry-e031'))
import lab as L
E,X,D=L.E,L.X,L.D
LOT,PARTIAL=L.LOT,L.PARTIAL

@dataclass(frozen=True)
class RiskRule(L.Candidate):
    allocation:str='baseline'
    extra:float=0.

BASE=RiskRule(**{**asdict(L.BASE),'stop':.35,'lock_arm':.5,'lock_floor':1.1})
ARMS={'E031':BASE,'SCALE25':replace(BASE,allocation='scale',extra=.25),
      'RUNNER25':replace(BASE,allocation='runner',extra=.25)}
directions,stalled,timed_out=L.directions,L.stalled,L.timed_out
recover_lots=X.recover_lots

def resize(t,i,j,wanted,room,cash,chase):
    row=t.q[i,j];ask=E.up(float(row[3])+E.half(float(row[3])))
    cap=min(wanted,int(row[4]*.2)//LOT)
    for lots in range(cap,0,-1):
        limit=E.down(min(ask*(1+chase),(min(room,cash)-E.ORDER-lots*E.ORDER)/(lots*LOT*(1+E.BUY_RATE))))
        if limit>=ask and E.reserve(limit,lots)<=min(room,cash)+.01:return j,lots,limit
    return None

def choose(t,i,d,rule,budget,cash):
    # The BASE selector is run before sizing; no new strike or signal becomes admissible.
    picked=L.choose(t,i,d,rule,min(1250.,budget),cash)
    if not picked or rule.allocation=='baseline':return picked
    j,lots,limit=picked
    if rule.allocation=='runner' and lots!=1:return picked
    most=2 if rule.allocation=='runner' else rule.max_lots
    bigger=resize(t,i,j,most,budget,cash,rule.chase)
    return bigger if bigger and bigger[1]>lots else picked

def run(tapes,rule=BASE,scenario='ordinary',details=False):
    from risk_day import run_day
    cash=peak=E.START_CASH;days=[]
    for t in tapes:
        dd=peak-cash;scale=0. if dd>=4000 else .25 if dd>=3000 else .5 if dd>=1500 else 1.
        row=run_day(t,rule,scenario,cash,min(E.BUDGET*(1+rule.extra)*scale,cash),details)
        cash=round(cash+row['net'],2);peak=max(peak,cash);assert cash>=-.01
        row.update(cash_after=cash,scale=scale);days.append(row)
    return dict(rule=asdict(rule),scenario=scenario,summary=E.summary(days),days=days)

def tapes():return L.tapes()
