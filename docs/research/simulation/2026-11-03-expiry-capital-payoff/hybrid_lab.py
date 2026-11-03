"""Sequential same-ticket eligibility, long/credit payoff choice and explicit cash."""
from dataclasses import dataclass,asdict,replace
import numpy as np
import ledger_lab as K
import credit_lab as C
E,X,D,L,LOT,PARTIAL=K.E,K.X,K.D,K.L,K.LOT,K.PARTIAL
stalled,timed_out,recover_lots=K.stalled,K.timed_out,K.recover_lots

@dataclass(frozen=True)
class HybridRule:
    name:str='E031'
    mode:str='long'
    credit_hold:int=8

ARMS={'E031':HybridRule(),'HYBRID_8M':HybridRule('HYBRID_8M','hybrid',8),
      'HYBRID_TREND':HybridRule('HYBRID_TREND','hybrid',0)}

def single_dirs(n,i,d):
    out=np.zeros(n,dtype=np.int8);out[i]=d;return out

def credit_plan(t,i,d,rule,room,cash):
    legs=C.contracts(t,i,d,rule)
    if not legs:return False
    q=C.entry(t,i,legs,'ordinary',mark=True)
    if not q or not 0<q['credit']<rule.width:return False
    return (C.reserve(q['credit']*.9,q['fees'],rule)<=room+.01 and
            (rule.width+C.CLOSE_EXTRA)*LOT+q['fees']+C.FEE_BUFFER<=cash+.01 and
            q['credit']*LOT>q['fees']+2*E.ORDER)

def run_day(t,rule,scenario,cash,budget,details=False):
    from hybrid_single import long_single,credit_single
    dirs=L.directions(t,K.BASE);positions=[];spent=0.;rejected=0;i=int(np.searchsorted(t.minute,780));unresolved=0
    credit_rule=C.CreditRule(name=rule.name,hold=rule.credit_hold)
    while i<t.n-1 and t.minute[i]<900 and len(positions)<2:
        d=int(dirs[i])
        if not d:i+=1;continue
        room=min(1250.,budget-spent,cash)
        if room<=0:break
        # Baseline control uses the original remaining room. Hybrid eligibility
        # retains the original full-ticket selector, then only resizes that plan.
        pick=L.choose(t,i,d,K.BASE,room if rule.mode=='long' else min(1250.,cash),cash)
        if not pick:i+=1;continue
        use_credit=(rule.mode=='hybrid' and pick[1]==1 and
                    credit_plan(t,i,d,credit_rule,min(budget-spent,cash),cash))
        if use_credit:
            row=credit_single(t,i,d,credit_rule,scenario,cash,min(budget-spent,cash),True)
        else:
            if rule.mode!='long':pick=K.R.resize(t,i,pick[0],pick[1],room,cash,K.BASE.chase)
            if not pick:i+=1;continue
            row=long_single(t,i,d,pick,K.BASE,scenario,cash,min(room,1250.),True)
        rejected+=row['rejected']
        if not row['positions']:i+=2;continue # failed next-bar entry consumes that observation
        p=row['positions'][0];p['instrument']='CREDIT' if use_credit else 'LONG'
        if not use_credit:
            p.update(filled_fee=p['net'],assumed=0.,residual_long=0,unresolved_short=0)
        positions.append(p);spent+=p['reserve'];cash=round(cash+p['net'],2)
        if row['unresolved']:
            unresolved=1;break
        i=p['exit_i']+5
    net=round(sum(p['net'] for p in positions),2)
    assert spent<=budget+.02
    return dict(day=t.day,net=net,filled_fee=round(sum(p['filled_fee'] for p in positions),2),
      assumed=round(sum(p['assumed'] for p in positions),2),trades=len(positions),spent=round(spent,2),
      fees=round(sum(p['fees'] for p in positions),2),unresolved=unresolved,
      residual_longs=sum(p['residual_long'] for p in positions),rejected=rejected,positions=positions if details else [])

def run(tapes,rule,scenario='ordinary',details=False,brakes=True):
    cash=peak=25000.;days=[];unavailable=[];day_limit=2500. if rule.mode=='long' else C.DAY_RISK
    for k,t in enumerate(tapes):
        dd=peak-cash;scale=0. if brakes and dd>=4000 else .25 if brakes and dd>=3000 else .5 if brakes and dd>=1500 else 1.
        row=run_day(t,rule,scenario,cash,min(day_limit*scale,cash),details)
        cash=round(cash+row['net'],2);peak=max(peak,cash);assert cash>=-.01
        row.update(cash_after=cash,scale=scale);days.append(row)
        if row['unresolved']:
            unavailable=[x.day for x in tapes[k+1:]];break
    summary=E.summary(days);summary.update(residual_longs=sum(d['residual_longs'] for d in days),
       filled_fee=round(sum(d['filled_fee'] for d in days),2),assumed=round(sum(d['assumed'] for d in days),2))
    out=dict(rule=asdict(rule),scenario=scenario,brakes=brakes,summary=summary,days=days,margin_qualified=rule.mode=='long')
    if unavailable:out['unavailable_after_unresolved']=unavailable
    return out

def credit_unbraked(tapes,rule,scenario='ordinary',details=False):
    cash=peak=25000.;days=[];unavailable=[]
    for k,t in enumerate(tapes):
        row=C.run_day(t,rule,scenario,cash,min(C.DAY_RISK,cash),details)
        cash=round(cash+row['net'],2);peak=max(peak,cash);assert cash>=-.01
        row.update(cash_after=cash,scale=1.);days.append(row)
        if row['unresolved']:unavailable=[x.day for x in tapes[k+1:]];break
    summary=E.summary(days);summary.update(residual_longs=sum(d['residual_longs'] for d in days),
       filled_fee=round(sum(d['filled_fee'] for d in days),2),assumed=round(sum(d['assumed'] for d in days),2))
    out=dict(rule=asdict(rule),scenario=scenario,brakes=False,summary=summary,days=days,margin_qualified=False)
    if unavailable:out['unavailable_after_unresolved']=unavailable
    return out
