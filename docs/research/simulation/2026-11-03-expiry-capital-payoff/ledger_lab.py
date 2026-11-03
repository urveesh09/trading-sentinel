"""Original E03.1 entry/exits with closed-cash daily loss/reentry ledgers."""
from dataclasses import dataclass,asdict,replace
import math,sys
import numpy as np
import ledger_guard as G
sys.path.insert(0,str(G.HERE.parent/'2026-11-03-expiry-anticipation'))
import risk_lab as R
E,X,D,L,LOT,PARTIAL=R.E,R.X,R.D,R.L,R.LOT,R.PARTIAL
directions,stalled,timed_out,recover_lots=L.directions,L.stalled,L.timed_out,X.recover_lots

@dataclass(frozen=True)
class LedgerRule(R.RiskRule):
    mode:str='baseline'

BASE=LedgerRule(**asdict(R.BASE))
ARMS={'E031':BASE,'NET_RISK_LEDGER':replace(BASE,mode='net'),'PROFIT_REENTRY':replace(BASE,mode='profit')}

def room_for(rule,positions,spent,budget,cash):
    realized=sum(p['net'] for p in positions)
    if rule.mode=='net':return min(1250.,max(0.,budget+realized),cash)
    if rule.mode=='profit' and len(positions)>=2:return min(1250.,max(0.,realized),cash)
    return min(1250.,budget-spent,cash)

def check_admission(rule,positions,budget,risk):
    realized=sum(p['net'] for p in positions)
    if rule.mode=='net':assert realized-risk>=-budget-.02
    elif rule.mode=='profit' and len(positions)>=2:assert realized-risk>=-.02

def choose(t,i,d,rule,budget,cash):
    # Original first two PROFIT tickets match the original selector's remaining budget.
    if rule.mode=='baseline' or (rule.mode=='profit' and not EXTRA_PHASE):return L.choose(t,i,d,rule,budget,cash)
    pick=L.choose(t,i,d,rule,1250.,cash)
    if not pick:return None
    j,lots,limit=pick
    # Only downsize the originally selected contract; no new/cheaper strike search.
    return R.resize(t,i,j,lots,budget,cash,rule.chase)

EXTRA_PHASE=False
def set_phase(rule,positions):
    global EXTRA_PHASE
    EXTRA_PHASE=rule.mode=='profit' and len(positions)>=2

def run(tapes,rule=BASE,scenario='ordinary',details=False):
    from ledger_day import run_day
    cash=peak=E.START_CASH;days=[];unavailable=[]
    for k,t in enumerate(tapes):
        dd=peak-cash;scale=0. if dd>=4000 else .25 if dd>=3000 else .5 if dd>=1500 else 1.
        row=run_day(t,rule,scenario,cash,min(E.BUDGET*scale,cash),details)
        cash=round(cash+row['net'],2);peak=max(peak,cash);assert cash>=-.01
        row.update(cash_after=cash,scale=scale);days.append(row)
        if row['unresolved']:
            unavailable=[x.day for x in tapes[k+1:]];break
    out=dict(rule=asdict(rule),scenario=scenario,summary=E.summary(days),days=days)
    if unavailable:out['unavailable_after_unresolved']=unavailable
    return out

def tapes():return R.tapes()
