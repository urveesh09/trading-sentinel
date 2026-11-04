"""Research-only Overnight v2 enrichment: portfolio downside and entry routing.

No broker, scheduler, notification or live-state access. Inputs are frozen
daily observations; next-session outcomes are read only when settling held
positions. All post-close fills are assumptions, not evidence of execution.
"""
from __future__ import annotations

from collections import Counter,defaultdict,deque
from dataclasses import asdict,dataclass
import hashlib
import importlib
import math
from pathlib import Path
from statistics import mean,pstdev
import sys


def legacy_lab():
    path=Path(__file__).resolve().parents[1]/'docs/research/penny/2026-11-04-overnight-v2'
    if str(path) not in sys.path:sys.path.insert(0,str(path))
    module=importlib.import_module('lab')
    if Path(module.__file__).resolve()!=path/'lab.py':raise RuntimeError('wrong legacy research module')
    return module


@dataclass(frozen=True)
class Policy:
    name:str
    portfolio:str='rank'            # rank | downside
    regular_fraction:float=0.0       # remaining budget is reserved for post-close
    slots:int=2
    night_min:float=.001
    depth:int=10
    inverse_risk_weights:bool=False
    covariance_prior:float=.015
    min_overlap:int=20
    max_weight:float=.65
    screen_before_depth:bool=False   # legacy research control only
    anchor_first:bool=False
    min_risk_improvement:float=.20
    route_rule:str='constant'        # constant | positive_net

    def __post_init__(self):
        if self.portfolio not in ('rank','downside'):raise ValueError('unknown portfolio')
        if not 0<=self.regular_fraction<=1:raise ValueError('invalid route fraction')
        if self.slots!=2:raise ValueError('this study uses two funded tickets')
        if not .5<=self.max_weight<=.75:raise ValueError('invalid concentration cap')
        if not 0<=self.min_risk_improvement<1:raise ValueError('invalid risk hurdle')
        if self.route_rule not in ('constant','positive_net'):raise ValueError('invalid route rule')


def risk_history(days):
    """Store only observation-time histories, never Day.nxt outcomes."""
    histories=defaultdict(lambda:deque(maxlen=60));out={}
    previous=None
    for d in days:
        if previous is not None and d.date<=previous:raise ValueError('unordered or duplicate sessions')
        previous=d.date
        for t,b in d.bar.items():
            p=d.prev_close.get(t)
            if p and p>0 and b['open']>0 and b['volume']>0:
                histories[t].append((d.date,b['open']/p-1))
        out[d.date]={c.ticker:tuple(histories[c.ticker]) for c in d.cands[:10]}
    return out


def eligible(day,p):
    source=day.cands
    if p.screen_before_depth:
        source=[c for c in source if c.f.get('night_mean',0)>=p.night_min][:p.depth]
    else:
        source=[c for c in source[:p.depth] if c.f.get('night_mean',0)>=p.night_min]
    result=[]
    for c in source:
        b=day.bar.get(c.ticker);pc=day.prev_close.get(c.ticker)
        if not b or b['volume']<=0 or c.kind=='MR_mid' or c.ticker.endswith(('-SM','-ST')):continue
        if pc and b['close']>=b['high']*.999 and b['close']/pc-1>=.019:continue
        result.append(c)
    return result


def pair_risk(a,b,histories,p):
    x=dict(histories.get(a,()));y=dict(histories.get(b,()));dates=sorted(set(x)&set(y))
    if len(dates)<p.min_overlap:return None
    # Downside covariance uses actual negative moves; a variance prior prevents
    # flat/placeholder histories being mistaken for riskless investments.
    xs=[min(x[d],0.) for d in dates];ys=[min(y[d],0.) for d in dates]
    vx=mean(z*z for z in xs);vy=mean(z*z for z in ys);cov=mean(u*v for u,v in zip(xs,ys))
    sx=math.sqrt(.5*vx+.5*p.covariance_prior**2)
    sy=math.sqrt(.5*vy+.5*p.covariance_prior**2)
    w=sy/(sx+sy) if p.inverse_risk_weights else .5
    w=max(1-p.max_weight,min(p.max_weight,w))
    risk=.5*(w*w*vx+(1-w)**2*vy+2*w*(1-w)*cov)+.5*(w*w+(1-w)**2)*p.covariance_prior**2
    return risk,w


def choose(day,p,histories):
    cands=eligible(day,p);weights={c.ticker:.5 for c in cands};status='RANK'
    if p.portfolio=='downside' and len(cands)>=2:
        options=[]
        for i,a in enumerate(cands):
            if p.anchor_first and i!=0:continue
            for j in range(i+1,len(cands)):
                b=cands[j]
                if a.ticker.split('-')[0]==b.ticker.split('-')[0]:continue
                r=pair_risk(a.ticker,b.ticker,histories,p)
                if r is not None:options.append((r[0],i,j,r[1]))
        if options:
            _,i,j,w=min(options)
            base=pair_risk(cands[0].ticker,cands[1].ticker,histories,p)
            if p.anchor_first and (base is None or min(options)[0]>base[0]*(1-p.min_risk_improvement)):
                return cands,weights,'ANCHOR_RETAINED_PAIR'
            selected=[cands[i],cands[j]]
            cands=selected+[c for k,c in enumerate(cands) if k not in (i,j)]
            weights[selected[0].ticker]=w;weights[selected[1].ticker]=1-w;status='DOWNSIDE_PAIR'
        else:status='RISK_HISTORY_UNAVAILABLE_FALLBACK'
    return cands,weights,status


def route_fraction(c,p,bankroll,regular_bps,exit_bps):
    """Earlier entry only when a causal night estimate clears declared costs.

    Daily close is a regular-session price proxy, not a tradable 15:20 quote.
    This hurdle cannot establish actual spread, slippage or pre-close drift.
    """
    if p.route_rule=='constant':return p.regular_fraction
    qty=int((bankroll/p.slots)//(c.close*1.002))
    if qty<1:return 0.
    fees=legacy_lab().cnc_costs(c.close,c.close,qty)/(qty*c.close)
    hurdle=fees+(regular_bps+exit_bps)/10000
    return p.regular_fraction if c.f.get('night_mean',0)>hurdle else 0.


def fill_uniform(ticker,day,seed):
    return int.from_bytes(hashlib.sha256(f'{seed}|{day}|{ticker}'.encode()).digest()[:8],'big')/2**64


def simulate(days,p,*,start,end,bankroll=25000.,regular_bps=36.,exit_bps=5.,
             winning_close_fill=1.,seed=20261104,keep=True,histories=None):
    """Fund both entry sleeves; missing close fills remain cash, fees only on fills.

    The adversary may deny post-close winning tickets. That outcome label is
    consumed at next-session settlement ONLY and never changes selection,
    routing, size or the pre-reserved cash. Regular fills remain assumptions.
    Profits are not reinvested; losses reduce the next day's own risk capital.
    """
    if not math.isfinite(bankroll) or bankroll<=0 or not 0<=winning_close_fill<=1:raise ValueError('invalid cash/fill model')
    if not 0<=regular_bps<10000 or not 0<=exit_bps<10000:raise ValueError('invalid execution cost')
    lab=legacy_lab();histories=histories if histories is not None else risk_history(days)
    cash=bankroll;realized=0.;held={};trades=[];curve=[];outcomes=Counter();intents=[]
    for d in days:
        if d.date<start:continue
        for t in sorted(list(held)):
            pos=held[t];b=d.bar.get(t)
            if not b or b['volume']<=0:pos['delayed']=True;continue
            exit_price=b['open']*(1-exit_bps/10000)
            reference_qty=int((bankroll/2)//(pos['close']*1.002))
            pc_win=(exit_price-pos['close'])*reference_qty-lab.cnc_costs(pos['close'],exit_price,reference_qty)>0 if reference_qty else False
            pc_fills=not(pc_win and fill_uniform(t,pos['day'],seed)>=winning_close_fill)
            pc_qty=pos['pc_qty'] if pc_fills else 0
            qty=pos['regular_qty']+pc_qty
            if not pc_fills:
                cash+=pos['pc_qty']*pos['close'];outcomes['POSTCLOSE_WINNER_NONFILL']+=1
            else:outcomes['POSTCLOSE_FILLED_ASSUMPTION']+=int(pc_qty>0)
            if qty:
                entry_notional=pos['regular_qty']*pos['regular_price']+pc_qty*pos['close']
                entry=entry_notional/qty
                fees=lab.cnc_costs(entry,exit_price,qty)
                net=exit_price*qty-entry_notional-fees
                cash+=exit_price*qty-fees;realized+=net
                trade={'ticker':t,'entry_date':pos['day'],'exit_date':d.date,'entry':entry,
                       'exit':exit_price,'shares':qty,'net':net,'cost':fees,'notional':entry_notional,
                       'regular_qty':pos['regular_qty'],'postclose_qty':pc_qty,'kind':pos['kind'],
                       'delayed':pos.get('delayed',False),'fill_grade':'ASSUMED_BAR_PROXY'}
                trades.append(trade if keep else {k:trade[k] for k in ['net','entry_date','notional']})
            else:outcomes['NO_POSITION_AFTER_NONFILL']+=1
            del held[t]
        if d.date<=end:
            risk_capital=min(bankroll,bankroll+realized)
            cands,weights,status=choose(d,p,histories.get(d.date,{}));outcomes[status]+=1;entered=0
            for c in cands:
                if entered>=p.slots:break
                if c.ticker in held or c.ticker.split('-')[0] in {t.split('-')[0] for t in held}:continue
                free=cash-max(realized,0.)
                # Rank/equal is exactly the legacy V2 cash split, including
                # replacement picks. Downside weights use a capped funded ticket.
                budget=free/(p.slots-entered) if p.portfolio=='rank' else min(free,risk_capital*weights[c.ticker])
                rp=c.close*(1+regular_bps/10000)
                fraction=route_fraction(c,p,risk_capital,regular_bps,exit_bps)
                if budget<=0:outcomes['NO_FREE_CASH']+=1;continue
                if fraction==0:
                    qp=int(budget//(c.close*1.002));qr=0
                elif fraction==1:
                    qr=int(budget//(rp*1.002));qp=0
                else:
                    qr=int(budget*fraction//(rp*1.002))
                    qp=int(budget*(1-fraction)//(c.close*1.002))
                planned_cash=risk_capital*(.5 if p.portfolio=='rank' else weights[c.ticker])
                qr=min(qr,int(planned_cash*fraction//rp))
                qp=min(qp,int(planned_cash*(1-fraction)//c.close))
                capacity=int(.01*c.close*d.bar[c.ticker]['volume']//c.close)
                total=qr+qp
                if total>capacity:
                    scale=capacity/total;qr=int(qr*scale);qp=int(qp*scale)
                total=qr+qp
                plan=int(risk_capital/p.slots/c.close)
                if total<1 or total<.25*plan:outcomes['LIQUIDITY_OR_DUST']+=1;continue
                reserve=qr*rp+qp*c.close
                if reserve>free+1e-8:raise AssertionError('unfunded entry')
                if c.stop>=c.close:outcomes['STOP_REFERENCE_BREACHED']+=1;continue
                cash-=reserve;entered+=1
                held[c.ticker]={'day':d.date,'close':c.close,'regular_price':rp,
                                'regular_qty':qr,'pc_qty':qp,'kind':c.kind}
                outcomes['FUNDED_INTENT']+=1
                intents.append({'date':d.date,'ticker':c.ticker,'regular_qty':qr,'pc_qty':qp,
                                'regular_price':rp,'close':c.close,'reserved':reserve})
        marked=cash+sum((d.bar[t]['close'] if t in d.bar else pos['close'])*(pos['regular_qty']+pos['pc_qty']) for t,pos in held.items())
        curve.append((d.date,marked))
        if d.date>end and not held:break
    summary=lab.summarize(trades,curve,bankroll)
    summary['dd_pct_initial']=round(100*summary['dd']/bankroll,3)
    return {'policy':asdict(p),'start':start,'end':end,'bankroll':bankroll,
            'regular_bps':regular_bps,'exit_bps':exit_bps,'winning_close_fill':winning_close_fill,
            'summary':summary,'outcomes':dict(outcomes),'open_at_end':len(held),'trades':trades,
            'curve':curve,'intents':intents,'scope':'CONDITIONAL_PORTFOLIO_PROXY',
            'fill_claim':'none: post-close and auction fills are assumed, not proven'}
