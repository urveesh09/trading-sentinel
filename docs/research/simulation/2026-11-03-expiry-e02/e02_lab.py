"""Causal long-option expiry families; native fees and bounded own-cash book."""
from __future__ import annotations
from dataclasses import dataclass,asdict
from datetime import time
import hashlib,json,math
import numpy as np
import data as D
EP=D.EP

LOT=65;BUDGET=2500.;START_CASH=25000.
FEE=EP.fee_schedule('NFO')
ORDER=EP.order_fee(FEE)
BUY_RATE=(EP.buy_charges(100,1,FEE)-ORDER)/100
SELL_RATE=(EP.sell_charges(100,1,FEE)-ORDER)/100


def up(x):return round(math.ceil(round(x/.05,6))*.05,2)
def down(x):return round(math.floor(round(x/.05,6))*.05,2)
def half(x):return .025 if x<10 else .05 if x<50 else .1 if x<100 else .525
def fee(price,qty,buy):return round(ORDER+price*qty*(BUY_RATE if buy else SELL_RATE),2)
def reserve(price,lots,lot=LOT):return price*lots*lot+fee(price,lots*lot,True)+lots*ORDER


@dataclass(frozen=True)
class Rule:
    setup:str='BREAK'
    look:int=10
    efficiency:float=.3
    stretch:float=2.5
    premium_low:float=2.
    premium_high:float=20.
    option_rise:float=0.
    stop:float=.3
    arm:float=1.
    keep:float=.6
    target:float=3.
    hold:int=30
    start:int=780
    end:int=900
    slots:int=1
    underlying_stop:float=1.

    @property
    def key(self):return hashlib.sha256(json.dumps(asdict(self),sort_keys=True).encode()).hexdigest()[:12]


def directions(t,rule):
    """Every reading is based on the completed current bar and earlier bars."""
    feat=t.features[rule.look];out=np.zeros(t.n,dtype=np.int8)
    waiting=None
    first=max(rule.look+1,int(np.searchsorted(t.minute,rule.start-5)))
    last=min(t.n,int(np.searchsorted(t.minute,rule.end)))
    for i in range(first,last):
        hi,lo,er,mean,atr,sd,fhi,flo=feat[i]
        if not np.isfinite(feat[i]).all() or not np.isfinite(t.x[i]).all() or not np.isfinite(t.f[i]).all():waiting=None;continue
        c=t.close[i];fc=t.f[i,3];d=0
        if rule.setup=='BOX':
            if t.box is None or t.minute[i]<810:continue
            bh,bl,fh,fl=t.box;buf=max((bh-bl)*.15,c*.0002)
            d=1 if c>bh+buf and fc>fh else -1 if c<bl-buf and fc<fl else 0
        elif rule.setup in ('BREAK','RETEST'):
            br=1 if c>hi and fc>fhi else -1 if c<lo and fc<flo else 0
            if rule.setup=='BREAK':d=br
            else:
                if waiting:
                    j,sign,level=waiting
                    if i-j>5 or sign*(c-level)<-atr*.5:waiting=None
                    elif i>j and t.x[i,2]<=level+atr*.25 and t.x[i,1]>=level-atr*.25 and sign*(c-level)>0 and sign*(c-t.x[i,0])>0 and sign*(c-t.close[i-1])>0:
                        d=sign;waiting=None
                if br and d==0:waiting=(i,br,hi if br==1 else lo)
        elif rule.setup=='PULLBACK':
            sign=1 if er>0 else -1
            if sign*(t.close[i-1]-t.close[i-3])<0 and sign*(c-t.close[i-1])>0 and sign*(fc-t.f[i-1,3])>0:d=sign
        elif rule.setup=='FADE':
            if abs(er)>max(.3,rule.efficiency) or sd<=0:continue
            if t.close[i-1]>mean+1.5*sd and c<t.close[i-1] and fc<t.f[i-1,3]:d=-1
            elif t.close[i-1]<mean-1.5*sd and c>t.close[i-1] and fc>t.f[i-1,3]:d=1
        if not d:continue
        if rule.setup!='FADE' and d*er<rule.efficiency:continue
        if abs(c-mean)>atr*rule.stretch:continue
        if rule.start<=t.minute[i]<rule.end:out[i]=d
    return out


def executable(t,i,j,side,scenario,lots):
    r=t.q[i,j]
    if not np.isfinite(r).all():return 0,None
    capacity=int(r[4]*.2)//LOT
    if capacity<=0:return 0,None
    raw=float(r[1 if side=='BUY' else 2] if scenario=='catastrophe' else r[0])
    slip=half(raw)*(1 if scenario=='ordinary' else 2)
    if scenario=='adverse':slip+=max(.05,raw*.01)
    price=up(raw+slip) if side=='BUY' else down(raw-slip)
    return (min(lots,capacity),price) if price>0 else (0,None)


def choose(t,i,d,rule,budget,cash,lot=LOT):
    if not np.isfinite(t.close[i]):return None
    asks=t.q[i,:,3]
    valid=(t.kinds==d)&(d*(t.strikes-t.close[i])>0)&(np.abs(t.strikes-t.close[i])<=400)
    valid&=np.isfinite(asks)&(asks>=rule.premium_low)&(asks<=rule.premium_high)
    for j in sorted(np.flatnonzero(valid),key=lambda j:d*t.strikes[j]):
        row=t.q[i,j];ask=up(float(row[3])+half(float(row[3])))
        if rule.option_rise:
            old=t.q[i-5,j,3] if i>=5 else np.nan
            if not np.isfinite(old) or old<=0 or ask/old<rule.option_rise:continue
        cap=min(10,int(row[4]*.2)//lot)
        for lots in range(cap,0,-1):
            limit=down(min(ask*1.10,(min(budget,cash)-ORDER-lots*ORDER)/(lots*lot*(1+BUY_RATE))))
            if limit>=ask and reserve(limit,lots,lot)<=min(budget,cash)+.01:return int(j),lots,limit
    return None


def run_day(t,rule,scenario='ordinary',cash=START_CASH,budget=BUDGET,details=False):
    dirs=directions(t,rule);spent=0.;positions=[];next_i=0;pending_entry=None;pending_exit=None;pos=None
    rejected=0;marks=[]
    for i in range(int(np.searchsorted(t.minute,rule.start)),t.n):
        if pending_exit:
            qty,reason,decided=pending_exit
            filled,price=executable(t,i,pos['j'],'SELL',scenario,min(qty,pos['open']))
            if filled:
                cost=fee(price,filled*LOT,False);gross=round((price-pos['entry'])*filled*LOT,2)
                pos['net']=round(pos['net']+gross-cost,2);pos['fees']=round(pos['fees']+cost,2);pos['open']-=filled
                pos['events'].append(dict(i=i,decision_i=decided,side='SELL',reason=reason,lots=filled,price=price,fees=cost))
                if not pos['open']:
                    cash=round(cash+pos['net'],2);pos['exit_i']=i;positions.append(pos);pos=None;pending_exit=None;next_i=i+5
                else:pending_exit=(pos['open'],reason,decided)
            if pending_exit:continue
        if pending_entry:
            j,lots,limit,decision,sign,atr,room=pending_entry;pending_entry=None
            filled,price=executable(t,i,j,'BUY',scenario,lots)
            if filled<max(1,math.ceil(lots*.25)) or price is None or price>limit:rejected+=1;continue
            risk=reserve(price,filled);assert risk<=room+.01
            spent+=risk
            pos=dict(day=t.day,j=j,symbol=t.symbols[j],direction=sign,entry_i=i,decision_i=decision,entry=price,lots=filled,open=filled,
                     reserve=round(risk,2),peak=price,stop=round(price*(1-rule.stop),2),net=-fee(price,filled*LOT,True),fees=fee(price,filled*LOT,True),
                     underlying_stop=float(t.close[decision]-sign*atr*rule.underlying_stop),events=[dict(i=i,decision_i=decision,side='BUY',lots=filled,price=price,fees=fee(price,filled*LOT,True))])
        if pos:
            row=t.q[i,pos['j']]
            bid=down(float(row[3])-half(float(row[3]))) if np.isfinite(row[3]) else None
            reason=None
            if t.minute[i]>=928:reason='FLAT_TIME'
            elif bid is not None and bid>0:
                pos['peak']=max(pos['peak'],bid)
                gain=pos['peak']/pos['entry']-1
                if gain>=rule.arm:pos['stop']=max(pos['stop'],round(pos['peak']*rule.keep,2))
                if bid<=pos['stop']:reason='TRAIL' if pos['stop']>=pos['entry'] else 'STOP'
                elif np.isfinite(t.close[i]) and rule.underlying_stop>0 and pos['direction']*(t.close[i]-pos['underlying_stop'])<0:reason='STRUCTURE'
                elif bid>=pos['entry']*(1+rule.target):reason='TARGET'
                elif i-pos['entry_i']>=rule.hold:reason='TIME'
                mark=pos['net']+(bid-pos['entry'])*pos['open']*LOT-fee(bid,pos['open']*LOT,False)
                marks.append(mark+sum(p['net'] for p in positions))
            if reason and i<t.n-1:pending_exit=(pos['open'],reason,i)
            continue
        if pending_exit or pending_entry or i<next_i or i>=t.n-1 or len(positions)>=rule.slots:continue
        sign=int(dirs[i])
        if not sign:continue
        room=min(BUDGET/rule.slots,budget-spent,cash)
        if room<=0:continue
        pick=choose(t,i,sign,rule,room,cash)
        if pick:
            j,lots,limit=pick;pending_entry=(j,lots,limit,i,sign,t.features[rule.look][i,4],room)
    unresolved=0
    if pos:
        unresolved=1
        pos['net']=round(pos['net']-pos['entry']*pos['open']*LOT,2)
        pos['unresolved']=True;positions.append(pos)
    net=round(sum(p['net'] for p in positions),2)
    assert spent<=budget+.02 and net>=-spent-.03
    return dict(day=t.day,net=net,trades=len(positions),spent=round(spent,2),fees=round(sum(p['fees'] for p in positions),2),
                unresolved=unresolved,rejected=rejected,positions=positions if details else [],marked_worst=min(marks,default=0.))


def summary(days):
    values=[d['net'] for d in days];curve=peak=dd=0.;streak=longest=0
    for v in values:
        curve+=v;peak=max(peak,curve);dd=max(dd,peak-curve)
        streak=streak+1 if v<0 else 0;longest=max(longest,streak)
    gains=sum(v for v in values if v>0);loss=-sum(v for v in values if v<0)
    qs=[sum(d['net'] for d in days if (int(d['day'][5:7])-1)//3==q) for q in range(4)]
    return dict(net=round(sum(values),2),without_best=round(sum(values)-max(values,default=0),2),worst=round(min(values,default=0),2),
                drawdown=round(dd,2),trades=sum(d['trades'] for d in days),profit_factor=round(gains/loss,4) if loss else 99.,
                wins=sum(v>0 for v in values),loss_days=sum(v<0 for v in values),losing_streak=longest,quarters=[round(x,2) for x in qs],
                first_half=round(sum(d['net'] for d in days if d['day'][5:7]<'07'),2),second_half=round(sum(d['net'] for d in days if d['day'][5:7]>='07'),2),
                unresolved=sum(d['unresolved'] for d in days),fees=round(sum(d['fees'] for d in days),2))


def run_year(tapes,rule,scenario='ordinary',details=False,brakes=True):
    cash=peak=START_CASH;days=[]
    for t in tapes:
        dd=peak-cash
        scale=0. if brakes and dd>=4000 else .25 if brakes and dd>=3000 else .5 if brakes and dd>=1500 else 1.
        row=run_day(t,rule,scenario,cash,min(BUDGET*scale,cash),details)
        cash=round(cash+row['net'],2);peak=max(peak,cash);assert cash>=-.01
        row['cash_after']=cash;row['scale']=scale;days.append(row)
    return dict(rule=asdict(rule),scenario=scenario,summary=summary(days),days=days)


def qualifies(s):
    return dict(positive=s['net']>0,ex_best_positive=s['without_best']>0,profit_factor=s['profit_factor']>=1.2,
                activity=s['trades']>=15,worst=s['worst']>=-1250,drawdown=s['drawdown']<=5000,
                quarters=sum(x>0 for x in s['quarters'])>=2,unresolved=s['unresolved']==0)


def score(ordinary,adverse):
    # Avoid rewarding a single winner, sparse lucky trades, or a score achieved
    # by halting permanently after early losses. All settings/trials are logged.
    scores=[]
    for r in (ordinary,adverse):
        s=r['summary'];q=s['quarters']
        v=s['without_best']-.5*s['drawdown']+min(q)*.5
        v-=max(0,15-s['trades'])*500
        v-=max(0,-1250-s['worst'])*2
        scores.append(v)
    return round(min(scores),2)
