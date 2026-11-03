"""Offline defined-risk combination model. Simultaneous leg fills are an explicit assumption."""
from dataclasses import dataclass,asdict,replace
import math
import numpy as np
import mechanisms as M
E,X,D,LOT=M.E,M.X,M.D,M.LOT

@dataclass(frozen=True)
class Shape(M.Rule):
    shape:str='vertical'

BASE=Shape(**asdict(M.BASE))

def contracts(t,i,d,rule):
    spot=t.close[i]
    if not np.isfinite(spot):return None
    otm=sorted({float(k) for k in t.strikes if 0<d*(k-spot)<=50},key=lambda k:d*k)
    if not otm:return None
    anchor=otm[0];weights=(1,-1) if rule.shape=='vertical' else (1,-2,1)
    legs=[]
    for offset,w in enumerate(weights):
        k=anchor+d*50*offset
        js=np.flatnonzero((t.strikes==k)&(t.kinds==d))
        if len(js)!=1 or not 0<d*(k-spot)<=200:return None
        j=int(js[0]);r=t.q[i,j]
        if not np.isfinite(r).all() or r[4]<=0:return None
        legs.append((j,w))
    return legs

def quote(t,i,legs,buy,scenario='ordinary',packs=3,close=False):
    rows=[t.q[i,j] for j,w in legs]
    if any(not np.isfinite(r).all() for r in rows):return None
    capacity=min(int(r[4]*.2)//(LOT*abs(w)) for r,(j,w) in zip(rows,legs))
    filled=min(packs,capacity)
    if filled<=0:return None
    prices=[]
    for r,(j,w) in zip(rows,legs):
        side_buy=(w>0)==buy
        raw=float(r[3] if close else r[1 if side_buy else 2] if scenario=='catastrophe' else r[0])
        slip=E.half(raw)*(1 if scenario=='ordinary' or close else 2)
        if scenario=='adverse' and not close:slip+=max(.05,raw*.01)
        p=E.up(raw+slip) if side_buy else E.down(raw-slip)
        if p<=0:return None
        prices.append(p)
    debit=sum(w*p for (j,w),p in zip(legs,prices))
    fees=round(sum(E.fee(p,filled*LOT*abs(w),(w>0)==buy) for (j,w),p in zip(legs,prices)),2)
    gross_long=sum(w*p*filled*LOT+E.fee(p,w*filled*LOT,True) for (j,w),p in zip(legs,prices) if w>0)
    return dict(packs=filled,value=round(debit,2),prices=prices,fees=fees,gross_long=gross_long)

def reserve(value,packs,entry_fees,legs):
    return round(value*packs*LOT+entry_fees+packs*len(legs)*E.ORDER,2)

def run_day(t,rule,scenario='ordinary',cash=E.START_CASH,budget=E.BUDGET,details=False):
    dirs=M.directions(t,rule);spent=0.;positions=[];pending=None;order=None;pos=None;next_i=0;marks=[];rejected=0
    for i in range(int(np.searchsorted(t.minute,rule.start)),t.n):
        if order:
            qty,reason,decision=order
            q=quote(t,i,pos['legs'],False,scenario,min(qty,pos['open']))
            if q:
                n=q['packs'];p=q['value'];pos['net']=round(pos['net']+(p-pos['entry'])*n*LOT-q['fees'],2)
                pos['fees']=round(pos['fees']+q['fees'],2);pos['open']-=n
                pos['events'].append(dict(i=i,decision_i=decision,side='SELL',reason=reason,lots=n,price=p,fees=q['fees'],leg_prices=q['prices']))
                if reason=='TARGET_BASE':
                    pos['runner']=True;pos['stop']=max(pos['entry']*rule.runner_floor,pos['peak']*rule.runner_keep)
                if not pos['open']:
                    pos['exit_i']=i;positions.append(pos);cash=round(cash+pos['net'],2);pos=None;order=None;next_i=i+5
                else:order=(pos['open'],reason,decision) if reason!='TARGET_BASE' else None
            elif reason=='TARGET_BASE':order=None
            if order:continue
        if pending:
            legs,n,limit,decision,d,atr,room=pending;pending=None
            q=quote(t,i,legs,True,scenario,n)
            if q:
                risk=reserve(q['value'],q['packs'],q['fees'],legs)
            if not q or q['value']<=0 or q['value']>limit or risk>room+.01 or q['gross_long']>cash+.01:
                rejected+=1;continue
            spent+=risk;p=q['value'];n=q['packs']
            pos=dict(day=t.day,legs=legs,j=legs[0][0],symbol=' / '.join(f'{w:+}*{t.symbols[j]}' for j,w in legs),
                entry_i=i,decision_i=decision,direction=d,entry=p,lots=n,open=n,reserve=risk,gross_long=q['gross_long'],
                peak=p,stop=round(p*(1-rule.stop),2),net=-q['fees'],fees=q['fees'],
                underlying_stop=float(t.close[decision]-d*atr*rule.underlying_stop),
                events=[dict(i=i,decision_i=decision,side='BUY',lots=n,price=p,fees=q['fees'],leg_prices=q['prices'])])
        if pos:
            q=quote(t,i,pos['legs'],False,packs=pos['open'],close=True)
            reason=None;qty=pos['open']
            if t.minute[i]>=928:reason='FLAT_TIME'
            elif q:
                bid=q['value'];pos['peak']=max(pos['peak'],bid);gain=pos['peak']/pos['entry']-1
                if pos.get('runner'):
                    pos['stop']=max(pos['stop'],pos['entry']*rule.runner_floor,pos['peak']*rule.runner_keep)
                    if bid<=pos['stop']:reason='RUNNER_TRAIL'
                    elif rule.hero_target and bid>=pos['entry']*(1+rule.hero_target):reason='HERO_TARGET'
                else:
                    if gain>=rule.arm:pos['stop']=max(pos['stop'],round(pos['peak']*rule.keep,2))
                    if rule.lock_arm and gain>=rule.lock_arm:pos['stop']=max(pos['stop'],round(pos['entry']*rule.lock_floor,2))
                    if bid<=pos['stop']:reason='TRAIL' if pos['stop']>=pos['entry'] else 'STOP'
                    elif np.isfinite(t.close[i]) and pos['direction']*(t.close[i]-pos['underlying_stop'])<0:reason='STRUCTURE'
                    elif bid>=pos['entry']*(1+rule.target):
                        reason='TARGET'
                        if rule.split and qty>=2:reason,qty='TARGET_BASE',qty-qty//2
                    elif i-pos['entry_i']>=rule.hold:reason='TIME'
                mark=pos['net']+(bid-pos['entry'])*pos['open']*LOT-q['fees']
                marks.append(sum(p['net'] for p in positions)+mark)
            if reason and i<t.n-1:order=(qty,reason,i)
            continue
        if pending or order or i<next_i or i>=t.n-1 or len(positions)>=rule.slots:continue
        d=int(dirs[i])
        if not d:continue
        room=min(E.BUDGET/rule.slots,budget-spent,cash)
        legs=contracts(t,i,d,rule)
        if not legs or room<=0:continue
        for n in range(rule.max_lots,0,-1):
            q=quote(t,i,legs,True,packs=n,close=True)
            if not q or q['packs']!=n or q['value']<=0:continue
            limit=E.down(q['value']*1.1)
            # Reserve at the limit, fee schedule prorated by each leg's notional.
            extra=math.ceil(max(0.,limit-q['value'])*n*LOT*E.BUY_RATE*100)/100
            if reserve(limit,n,q['fees']+extra,legs)<=room+.01 and q['gross_long']<=cash+.01:
                pending=(legs,n,limit,i,d,t.features[rule.look][i,4],room);break
    unresolved=0
    if pos:
        unresolved=1;pos['unresolved']=True
        pos['net']=round(pos['net']-pos['entry']*pos['open']*LOT,2);positions.append(pos)
    net=round(sum(p['net'] for p in positions),2)
    assert spent<=budget+.02
    return dict(day=t.day,net=net,trades=len(positions),spent=round(spent,2),fees=round(sum(p['fees'] for p in positions),2),
        unresolved=unresolved,rejected=rejected,positions=positions if details else [],marked_worst=min(marks,default=0.))

def run(tapes,rule=BASE,scenario='ordinary',details=False):
    cash=peak=E.START_CASH;days=[]
    for t in tapes:
        dd=peak-cash;scale=0. if dd>=4000 else .25 if dd>=3000 else .5 if dd>=1500 else 1.
        row=run_day(t,rule,scenario,cash,min(E.BUDGET*scale,cash),details)
        cash=round(cash+row['net'],2);peak=max(peak,cash);assert cash>=-.01
        row.update(cash_after=cash,scale=scale);days.append(row)
    return dict(rule=asdict(rule),scenario=scenario,summary=E.summary(days),days=days)
