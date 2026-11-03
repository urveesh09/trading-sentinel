"""Use an already fixed causal return forecast only for a baseline ticket's extra lot."""
from dataclasses import dataclass,asdict,replace
import risk_lab as R
E,X,D,L,LOT,PARTIAL=R.E,R.X,R.D,R.L,R.LOT,R.PARTIAL
directions,stalled,timed_out,recover_lots=R.directions,R.stalled,R.timed_out,R.recover_lots

@dataclass(frozen=True)
class SmartRule(R.RiskRule):
    smart:str='baseline'

BASE=SmartRule(**asdict(R.BASE))
ARMS={'E031':BASE,'CLOCK_RUNNER25':replace(BASE,smart='clock',extra=.25),
      'SMART_RUNNER25':replace(BASE,smart='forecast',extra=.25)}
FORECAST={};ELIGIBLE_DAYS=set()

def choose(t,i,d,rule,budget,cash):
    picked=L.choose(t,i,d,rule,min(1250.,budget),cash)
    if not picked or rule.smart=='baseline':return picked
    j,lots,limit=picked
    if lots!=1 or t.day not in ELIGIBLE_DAYS:return picked
    if rule.smart=='forecast' and FORECAST.get((t.day,i,j,d),float('-inf'))<=0:return picked
    larger=R.resize(t,i,j,2,budget,cash,rule.chase)
    return larger if larger and larger[1]>lots else picked

def run(tapes,rule=BASE,scenario='ordinary',details=False):
    from smart_day import run_day
    cash=peak=E.START_CASH;days=[]
    for t in tapes:
        dd=peak-cash;scale=0. if dd>=4000 else .25 if dd>=3000 else .5 if dd>=1500 else 1.
        row=run_day(t,rule,scenario,cash,min(E.BUDGET*(1+rule.extra)*scale,cash),details)
        cash=round(cash+row['net'],2);peak=max(peak,cash);assert cash>=-.01
        row.update(cash_after=cash,scale=scale);days.append(row)
    return dict(rule=asdict(rule),scenario=scenario,summary=E.summary(days),days=days)
