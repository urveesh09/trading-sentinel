"""Quantity-correct research liquidation and conditional passive scenarios."""
import math
import numpy as np
from data8 import L7
L4,L6=L7.L4,L7.L6

def liquidate(sp,t,start,j,lots,entry,scenario='ordinary'):
    left=lots; gross=fees=0.; events=[]
    for i in range(start,t.n):
        f,p=L6._exe(sp,t,i,j,'SELL',scenario,left)
        if f:
            assert 0<f<=left
            fee=L4.fee(sp,p,f*sp.lot,False)
            gross+=(p-entry)*f*sp.lot; fees+=fee; left-=f
            events.append(dict(i=i,lots=f,price=p,fees=fee))
        if not left: break
    assumed=-entry*left*sp.lot
    return dict(net=round(gross-fees+assumed,2),filled_net=round(gross-fees,2),assumed_net=round(assumed,2),
                fees=round(fees,2),remaining=left,events=events)

def fixed_action(t,i,d,rule=None,scenario='ordinary',lots_cap=1,hold=8,delay=0):
    rule=L7.E03_ENV if rule is None else rule
    from dataclasses import replace
    sp=L4.spec_of(t)
    pick=L4.choose4(sp,t,i,d,replace(rule,max_lots=lots_cap),2500.,30000.)
    if not pick: return dict(status='UNAFFORDABLE',net=0.,events=[])
    j,n,lim=pick; b=i+1+delay
    if b+hold>=t.n: return dict(status='MISSING',net=None,events=[])
    f,p=L6._exe(sp,t,b,j,'BUY',scenario,n)
    if not f or p is None or p>lim: return dict(status='NO_FILL',net=0.,events=[])
    bf=L4.fee(sp,p,f*sp.lot,True)
    r=liquidate(sp,t,b+hold,j,f,p,scenario)
    r.update(status='FILLED',net=round(r['net']-bf,2),filled_net=round(r['filled_net']-bf,2),
             fees=round(r['fees']+bf,2),j=int(j),lots=f,entry_i=b,entry=p,buy_fee=bf)
    return r

def passive_scenario(book,s,limit,units,until,mode='STRICT_TRADE',lot=65,latency=1.):
    """Not an execution bound. Quote opportunity is quantity-limited, never called definite.

    STRICT_TRADE requires a post-arrival new traded-through witness and enough
    incremental volume; cumulative volume attribution remains an explicit proxy.
    QUOTE_OPPORTUNITY offers at most the fresh visible whole-lot quantity once.
    No confirmed fill is claimed by either model.
    """
    import pk6
    k0=book.at(s)
    if k0 is None: return None
    arrival=s+latency; prev=int(book.a['vol'][k0])
    for k in book.after(s,until):
        volume=int(book.a['vol'][k]); dv=max(0,volume-prev); prev=volume
        if book.s[k]<arrival: continue
        if mode=='QUOTE_OPPORTUNITY':
            qty=sum(int(q) for p,q in zip(book.a['ap'][k],book.a['aq'][k]) if np.isfinite(p) and p<=limit)
            got=min(units,qty)//lot*lot
        elif mode=='STRICT_TRADE':
            lt=book.a['lt'][k]
            after=lt>0 and float(pk6.ist(lt))>=arrival
            got=min(units,dv)//lot*lot if after and book.a['ltp'][k]<=limit-.05+1e-9 else 0
        else: raise ValueError(mode)
        if got: return dict(time=float(book.s[k]),units=got,scenario=mode,confirmed=False)
    return None
