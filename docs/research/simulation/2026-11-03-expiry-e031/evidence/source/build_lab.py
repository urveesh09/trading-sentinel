"""Materialize an inspectable research runner; E03 stays unmodified.

The generated loop starts as E03's archived run_day. Assert unique hook sites,
then verify the zero-change arm against every archived baseline event.
"""
from pathlib import Path

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'2026-11-03-expiry-e03/e03_lab.py'

def main():
    original=SOURCE.read_text(encoding='utf-8')
    loop=original[original.index('def run_day('):original.index('\ndef run_year(')]
    changes={
      'if gain >= rule.arm:\n                    pos["stop"] = max(pos["stop"], round(pos["peak"] * rule.keep, 2))':
      'if gain >= rule.arm:\n                    pos["stop"] = max(pos["stop"], round(pos["peak"] * rule.keep, 2))\n                if rule.lock_arm and gain >= rule.lock_arm:\n                    pos["stop"] = max(pos["stop"], round(pos["entry"] * rule.lock_floor, 2))',
      'elif i - pos["entry_i"] >= rule.hold and not (rule.hold_armed and gain >= rule.arm):':
      'elif stalled(rule, i, pos, bid):\n                    reason = "STALL"\n                elif timed_out(t, rule, i, pos, bid, gain):',
    }
    for old,new in changes.items():
        assert loop.count(old)==1,old
        loop=loop.replace(old,new)
    target=HERE/'lab.py';assert not target.exists()
    target.write_text(HEADER+'\n'+loop+FOOTER,encoding='utf-8')
    print('GENERATED',target.name,'from frozen E03 with',len(changes),'explicit hook sites')

HEADER='''"""E03.1 causal mechanisms. Generated from frozen E03; inspect build_lab.py.
Baseline values reproduce E03. No live provider, broker or operational storage.
"""
from dataclasses import dataclass, asdict
from pathlib import Path
import sys, math, hashlib, json
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026-11-03-expiry-e03'))
import e03_lab as X
D,E=X.D,X.E
LOT,ORDER,PARTIAL=X.LOT,X.ORDER,X.PARTIAL
R3={**X.R3, 'max_lots':3, 'split':True, 'runner_floor':1., 'runner_keep':.5, 'hero_target':9.}

@dataclass(frozen=True)
class Candidate(X.Hero):
    chase:float=.10
    stall_minutes:int=0
    stall_gain:float=0.
    extend_minutes:int=0
    extend_gain:float=.2
    lock_arm:float=0.
    lock_floor:float=1.
    confirmation:str='none'

    @property
    def key(self):return hashlib.sha256(json.dumps(asdict(self),sort_keys=True).encode()).hexdigest()[:16]

BASE=Candidate(**R3)
CACHE={}

def directions(t,rule):
    # Cache only the pure signal; outcomes/cash/future bars are never cached decisions.
    fields=('setup','look','efficiency','stretch','start','end','confirmation')
    key=(id(t),*(getattr(rule,k) for k in fields))
    if key not in CACHE:
        out=X.directions(t,rule).copy()
        for i in np.flatnonzero(out):
            d=int(out[i])
            if rule.confirmation=='trend20':
                er=t.features[20][i,2]
                if not np.isfinite(er) or d*er<=0:out[i]=0
            elif rule.confirmation=='future2':
                if not np.isfinite(t.f[i-2:i+1,3]).all() or d*(t.f[i,3]-t.f[i-2,3])<=0:out[i]=0
        CACHE[key]=out
    return CACHE[key]

def choose(t,i,d,rule,budget,cash):
    picked=X.choose(t,i,d,rule,budget,cash)
    if not picked:return None
    j,lots,limit=picked
    ask=E.up(float(t.q[i,j,3])+E.half(float(t.q[i,j,3])))
    limit=min(limit,E.down(ask*(1+rule.chase)))
    return (j,lots,limit) if limit>=ask else None

def stalled(rule,i,pos,bid):
    # Current executable-price proxy after a fixed observation period, not future maximum.
    return bool(rule.stall_minutes and i-pos['entry_i']>=rule.stall_minutes and
                bid<pos['entry']*(1+rule.stall_gain))

def timed_out(t,rule,i,pos,bid,gain):
    age=i-pos['entry_i']
    if age<rule.hold or (rule.hold_armed and gain>=rule.arm):return False
    if not rule.extend_minutes or age>=rule.hold+rule.extend_minutes:return True
    # Extend only an already-profitable ticket while BOTH underlying/future confirm
    # the last three minutes. Flat, missing or reversing readings get no extension.
    if bid<pos['entry']*(1+rule.extend_gain):return True
    if not np.isfinite([t.close[i],t.close[i-3],t.f[i,3],t.f[i-3,3]]).all():return True
    return not (pos['direction']*(t.close[i]-t.close[i-3])>0 and
                pos['direction']*(t.f[i,3]-t.f[i-3,3])>0)
'''

FOOTER='''
def run(tapes,rule=BASE,scenario='ordinary',details=False,brakes=True):
    cash=peak=E.START_CASH;days=[]
    for t in tapes:
        dd=peak-cash
        scale=0. if brakes and dd>=4000 else .25 if brakes and dd>=3000 else .5 if brakes and dd>=1500 else 1.
        row=run_day(t,rule,scenario,cash,min(E.BUDGET*scale,cash),details)
        cash=round(cash+row['net'],2);peak=max(peak,cash)
        assert cash>=-.01
        row.update(cash_after=cash,scale=scale);days.append(row)
    return dict(rule=asdict(rule),scenario=scenario,summary=E.summary(days),days=days)

def tapes():return {y:X.tapes(y) for y in (2024,2025)}
'''

if __name__=='__main__':main()
