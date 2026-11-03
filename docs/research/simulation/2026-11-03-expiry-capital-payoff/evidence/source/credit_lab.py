"""Directional protected credit in a hypothetical basket; cash floor, no invented sales."""
from dataclasses import dataclass,asdict,replace
import math
import numpy as np
import ledger_lab as K
E,X,D,L,LOT=K.E,K.X,K.D,K.L,K.LOT

@dataclass(frozen=True)
class CreditRule:
    name:str='CREDIT_8M'
    hold:int=8
    side:int=1
    width:int=50
    flat:int=914
    stop:float=2.
    take:float=.5

ARMS={'CREDIT_8M':CreditRule(),'CREDIT_TREND':CreditRule(name='CREDIT_TREND',hold=0)}
FEE_BUFFER=500.
CLOSE_EXTRA=1.
DAY_RISK=5000.

def contracts(t,i,signal,rule):
    kind=-signal;spot=t.close[i]
    if not np.isfinite(spot):return None
    values=sorted({float(k) for k in t.strikes if 0<kind*(k-spot)<=50},key=lambda k:kind*k)
    if not values:return None
    anchor=values[0];legs=[]
    for k in (anchor,anchor+kind*rule.width):
        jj=np.flatnonzero((t.strikes==k)&(t.kinds==kind))
        if len(jj)!=1 or not 0<kind*(k-spot)<=200:return None
        j=int(jj[0]);row=t.q[i,j]
        if not np.isfinite(row).all() or row[4]*.2<LOT:return None
        legs.append(j)
    return tuple(legs)

def leg_price(t,i,j,buy,scenario,mark=False):
    row=t.q[i,j]
    if not np.isfinite(row).all() or row[4]*.2<LOT:return None
    raw=float(row[3] if mark else row[1 if buy else 2] if scenario=='catastrophe' else row[0])
    slip=E.half(raw)*(1 if scenario=='ordinary' or mark else 2)
    if scenario=='adverse' and not mark:slip+=max(.05,raw*.01)
    p=E.up(raw+slip) if buy else E.down(raw-slip)
    return p if p>0 else None

def entry(t,i,legs,scenario,mark=False):
    short=leg_price(t,i,legs[0],False,scenario,mark);hedge=leg_price(t,i,legs[1],True,scenario,mark)
    if short is None or hedge is None:return None
    fees=round(E.fee(short,LOT,False)+E.fee(hedge,LOT,True),2)
    return dict(short=short,hedge=hedge,credit=round(short-hedge,2),fees=fees)

def close_quote(t,i,legs,scenario,mark=False):
    short=leg_price(t,i,legs[0],True,scenario,mark)
    if short is None:return None
    hedge=leg_price(t,i,legs[1],False,scenario,mark)
    fees=E.fee(short,LOT,True)+(E.fee(hedge,LOT,False) if hedge is not None else 0.)
    cost=short-(hedge or 0.)
    if cost<0:return None # do not book asynchronous negative-cost arbitrage
    return dict(short=short,hedge=hedge,cost=round(cost,2),fees=round(fees,2))

def reserve(credit,fees,rule):return round((rule.width+CLOSE_EXTRA-credit)*LOT+fees+FEE_BUFFER,2)

def close_position(pos,q,i,decision,reason):
    # Actual close cash must fit the original full-loss cash reservation.
    net=round((pos['credit']-q['cost'])*LOT-pos['entry_fees']-q['fees'],2)
    if net < -pos['reserve']-.01:return False
    # No net closing price above the separately declared width allowance.
    if q['cost']>pos['width']+CLOSE_EXTRA:return False
    residual=q['hedge'] is None
    assumed=-pos['hedge_entry']*LOT if residual else 0.
    pos.update(exit_i=i,decision_exit_i=decision,reason=reason,exit_short=q['short'],exit_hedge=q['hedge'],
       exit_fees=q['fees'],fees=round(pos['entry_fees']+q['fees'],2),net=net,
       filled_fee=round(net-assumed,2),assumed=round(assumed,2),residual_long=int(residual),unresolved_short=0)
    return True

def run_day(t,rule,scenario,cash,budget,details=False):
    dirs=L.directions(t,K.BASE)*rule.side;positions=[];pending=None;closing=None;pos=None;spent=0.;next_i=0;rejected=0;marks=[]
    for i in range(int(np.searchsorted(t.minute,780)),t.n):
        if closing:
            reason,decision=closing;q=close_quote(t,i,pos['legs'],scenario)
            if q and close_position(pos,q,i,decision,reason):
                cash=round(cash+pos['net'],2);positions.append(pos);pos=None;closing=None;next_i=i+5
            if closing:continue
        if pending:
            legs,signal,decision,atr,limit,room=pending;pending=None;q=entry(t,i,legs,scenario)
            if not q or not 0<q['credit']<rule.width or q['credit']<limit:
                rejected+=1;continue
            risk=reserve(q['credit'],q['fees'],rule);collateral=(rule.width+CLOSE_EXTRA)*LOT+q['fees']+FEE_BUFFER
            if risk>room+.01 or collateral>cash+.01 or q['hedge']*LOT+E.fee(q['hedge'],LOT,True)>cash+.01:
                rejected+=1;continue
            if q['credit']*LOT<=q['fees']+2*E.ORDER:rejected+=1;continue
            spent+=risk
            pos=dict(day=t.day,entry_i=i,decision_i=decision,legs=list(legs),direction=int(signal),
              symbols=[t.symbols[j] for j in legs],width=rule.width,short_entry=q['short'],hedge_entry=q['hedge'],credit=q['credit'],
              entry_fees=q['fees'],reserve=risk,collateral=collateral,underlying_stop=float(t.close[decision]-signal*2*atr))
        if pos:
            q=close_quote(t,i,pos['legs'],scenario,mark=True);reason=None
            if t.minute[i]>=rule.flat:reason='FLAT_PRE_AUCTION'
            elif q:
                mark=(pos['credit']-q['cost'])*LOT-pos['entry_fees']-q['fees'];marks.append(mark+sum(p['net'] for p in positions))
                if pos['direction']*(t.close[i]-pos['underlying_stop'])<0:reason='STRUCTURE'
                elif q['cost']>=pos['credit']*rule.stop:reason='CREDIT_STOP'
                elif q['cost']<=pos['credit']*rule.take:reason='TAKE_HALF_CREDIT'
                elif rule.hold and i-pos['entry_i']>=rule.hold:reason='TIME'
            if reason and i<t.n-1:closing=(reason,i)
            continue
        if i<next_i or len(positions)>=2 or i>=t.n-1 or t.minute[i]>=900:continue
        signal=int(dirs[i])
        if not signal:continue
        legs=contracts(t,i,signal,rule)
        if not legs:continue
        q=entry(t,i,legs,scenario,mark=True)
        if not q or not 0<q['credit']<rule.width:continue
        room=min(budget-spent,cash)
        if reserve(q['credit']*.9,q['fees'],rule)>room+.01:continue
        pending=(legs,signal,i,float(t.features[10][i,4]),E.up(q['credit']*.9),room)
    unresolved=0
    if pos:
        unresolved=1;pos.update(unresolved_short=1,residual_long=1,net=-pos['reserve'],filled_fee=-pos['entry_fees'],
           assumed=round(-pos['reserve']+pos['entry_fees'],2),fees=pos['entry_fees'],reason='UNRESOLVED_SHORT',exit_i=None)
        positions.append(pos)
    assert spent<=budget+.02
    net=round(sum(p['net'] for p in positions),2)
    return dict(day=t.day,net=net,filled_fee=round(sum(p['filled_fee'] for p in positions),2),assumed=round(sum(p['assumed'] for p in positions),2),
      fees=round(sum(p['fees'] for p in positions),2),trades=len(positions),spent=round(spent,2),unresolved=unresolved,
      residual_longs=sum(p['residual_long'] for p in positions),rejected=rejected,positions=positions if details else [],marked_worst=min(marks,default=0.))

def run(tapes,rule,scenario='ordinary',details=False):
    cash=peak=25000.;days=[];unavailable=[]
    for k,t in enumerate(tapes):
        dd=peak-cash;scale=0. if dd>=4000 else .25 if dd>=3000 else .5 if dd>=1500 else 1.
        row=run_day(t,rule,scenario,cash,min(DAY_RISK*scale,cash),details)
        cash=round(cash+row['net'],2);peak=max(peak,cash);assert cash>=-.01
        row.update(cash_after=cash,scale=scale);days.append(row)
        if row['unresolved']:
            unavailable=[x.day for x in tapes[k+1:]];break
    s=E.summary(days);s.update(residual_longs=sum(d['residual_longs'] for d in days),
       filled_fee=round(sum(d['filled_fee'] for d in days),2),assumed=round(sum(d['assumed'] for d in days),2))
    out=dict(rule=asdict(rule),scenario=scenario,summary=s,days=days,margin_qualified=False)
    if unavailable:out['unavailable_after_unresolved']=unavailable
    return out
