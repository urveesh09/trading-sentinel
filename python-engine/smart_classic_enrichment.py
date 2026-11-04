"""Pure Smart/Classic research; funded orders, causal inputs, real-clock carries.

Never starts a scheduler, broker, executor or paper book. Historical auction
and OHLC prices remain conditional proxies, never evidence of own order fills.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from dataclasses import dataclass,asdict
import heapq
import math
from statistics import mean,median

from penny_engine_connors import _rsi_2
from penny_risk import calc_penny_costs


def wilder_rsi(closes,period=2):
    out=[50.]*len(closes)
    if len(closes)<=period:return out
    changes=[b-a for a,b in zip(closes,closes[1:])]
    gain=mean(max(x,0) for x in changes[:period]);loss=mean(max(-x,0) for x in changes[:period])
    def value():return 100*gain/(gain+loss) if gain+loss else 0.
    out[period]=value()
    for i,x in enumerate(changes[period:],period+1):
        gain=(gain*(period-1)+max(x,0))/period
        loss=(loss*(period-1)+max(-x,0))/period;out[i]=value()
    return out


def snapshots(daily,calendar):
    """Only bars dated strictly before a session; missing today never removes a name."""
    ordered=sorted(calendar);out={d:{} for d in ordered}
    for ticker,rows in daily.items():
        idx=0;closes=[r[4] for r in rows];wr=wilder_rsi(closes)
        for day in ordered:
            while idx<len(rows) and rows[idx][0]<day:idx+=1
            if idx<20:continue
            prior=rows[max(0,idx-250):idx];p=prior[-1];cv=closes[:idx]
            nights=[b[1]/a[4]-1 for a,b in zip(prior[-61:],prior[-60:])] if len(prior)>60 else [b[1]/a[4]-1 for a,b in zip(prior,prior[1:])]
            out[day][ticker]={'close':p[4],'volume':p[5],'medvol':median(r[5] for r in prior[-20:]),
                'tv':median(r[4]*r[5] for r in prior[-20:]),'gapfreq':sum(x<=-.02 for x in nights)/(len(nights)+10),
                'rsi':_rsi_2(cv),'rsi_prev':_rsi_2(cv[:-1]),'rsi_prev2':_rsi_2(cv[:-2]),
                'wilder':wr[idx-1],'sma5':mean(cv[-5:]),'sma50':mean(cv[-50:]) if idx>=50 else None,
                'sma200':mean(cv[-200:]) if idx>=200 else None,'n':idx}
    return out


def universe_ok(t,f,excluded):
    return (t not in excluded and '-' not in t and 1<=f['close']<=55 and f['tv']>=500000)


@dataclass(frozen=True)
class Policy:
    name:str
    family:str                 # auction_ref, basket, confirm, breakout, pullback, fade, cnc_legacy, cnc_night, cnc_wilder
    rank:str='liquidity'
    slots:int=1
    exit_minute:int=900
    gap_limit:float=-.02
    hold_days:int=5
    afternoon:bool=False
    stop_pct:float=.03


@dataclass
class Order:
    day:str
    minute:int
    ticker:str
    entry:float
    side:int
    score:tuple
    cap_known:int
    cap_actual:int
    outcome:tuple|None          # future settlement only; never selection/sizing
    meta:dict
    limit:float|None=None


def bar5(day):
    """Observed minutes aggregate; no forward-filled bars or zeros invented."""
    grouped=defaultdict(list)
    for b in day.bars:grouped[555+((b[0]-555)//5)*5].append(b)
    return [(m,x[0][1],max(b[2] for b in x),min(b[3] for b in x),x[-1][4],sum(b[5] for b in x))
            for m,x in sorted(grouped.items())]


def long_close_outcome(t,day,by,calendar,index):
    """No fictional haircut or immediate booking of tomorrow's locked exit."""
    i=index[day]
    for k in range(i,len(calendar)):
        d=by.get((t,calendar[k]))
        if not d or not d.day_close or not d.day_open:continue
        locked=d.day_low and d.day_close<=d.day_low*1.0001 and d.day_close<d.day_open*.9999
        if k==i:
            if not locked:return (calendar[k],970,d.day_close,'OFFICIAL_CLOSE_PROXY')
        elif not (d.day_low and d.day_open<=d.day_low*1.0001 and d.day_close<=d.day_low*1.0001):
            return (calendar[k],555,d.day_open,'LOCKED_CARRY_OPEN_PROXY')
    return None


def intraday_outcome(d,entry_i,entry,side,stop,exit_minute,*,target=None):
    bars=bar5(d)
    for m,o,h,l,c,v in bars[entry_i:]:
        if v<=0:continue
        # Flat circuit prints do not establish an available counterparty.
        if h==l and ((side==1 and o<=stop) or (side==-1 and o>=stop)):continue
        if m>=exit_minute:return (d.date,m,o,'TIMED_NEXT_BAR')
        if side==1:
            if l<=stop:return (d.date,m,min(o,stop),'STOP_ADVERSE')
            if target and h>=target:return (d.date,m,max(o,target),'TARGET')
        else:
            if h>=stop:return (d.date,m,max(o,stop),'STOP_ADVERSE')
            if target and l<=target:return (d.date,m,min(o,target),'TARGET')
    return None


def auction_orders(days,daily,calendar,p,bankroll,excluded=()):
    by={(d.ticker,d.date):d for d in days};index={d:i for i,d in enumerate(calendar)};hist=snapshots(daily,calendar)
    volhist=defaultdict(list);orders=[];counts=Counter()
    for day in calendar:
        pool=[]
        for t,f in hist[day].items():
            if not universe_ok(t,f,excluded):continue
            est=median(volhist[t][-20:]) if len(volhist[t])>=5 else .008*f['medvol']
            limit=f['close']*(1+p.gap_limit);plan=int((bankroll/p.slots)//limit)
            if .1*est<.25*plan:continue
            if p.family=='auction_ref':
                d=by.get((t,day))
                if not d or not d.day_open or d.day_open/f['close']-1>p.gap_limit:continue
                rank=(d.day_open/f['close'],t) # openly labelled final-auction reference
            elif p.rank=='gapfreq':rank=(-f['gapfreq'],-f['tv'],t)
            else:rank=(-f['tv'],t)
            pool.append((rank,t,f,est,limit))
        chosen=sorted(pool)[:p.slots]
        for rank,t,f,est,limit in chosen:
            d=by.get((t,day));counts['PRESELECTED_LIMIT']+=1
            if not d or not d.day_open:
                counts['MISSING_AUCTION_OUTCOME']+=1;continue
            if p.family!='auction_ref' and d.day_open>limit:
                counts['UNMATCHED_CANCEL_BEFORE_CONTINUOUS']+=1;continue
            first=d.bars[0] if d.bars and d.bars[0][0]==555 else None
            cap=int(.1*(first[5] if first else 0))
            outcome=long_close_outcome(t,day,by,calendar,index)
            if p.exit_minute<930:
                bs=bar5(d)
                outcome=intraday_outcome(d,0,d.day_open,1,0.,p.exit_minute)
            # On 5-minute data this is explicitly a first-5-minute volume proxy.
            orders.append(Order(day,550,t,d.day_open,1,rank,int(.1*est),cap,
                outcome,{'slot_fraction':1/p.slots,'entry_basis':'AUCTION_ASSUMPTION'},
                limit if p.family!='auction_ref' else None))
        # Today's opening volume is learned only AFTER today's orders.
        for (t,date),d in by.items():
            if date==day:
                first=d.bars[0] if d.bars and d.bars[0][0]==555 else None
                volhist[t].append(first[5] if first else 0.)
    return orders,dict(counts)


def intraday_orders(days,p,excluded=()):
    from penny_engine_breakout import _rsi_14_wilder
    orders=[]
    for d in days:
        if d.ticker in excluded or '-' in d.ticker or not 1<=d.prev_close<=55 or d.median_value20<500000:continue
        bs=bar5(d)
        if not bs or bs[0][0]!=555:continue
        high=None;cum=0.;vp=0.;closes=[];breakout=None
        for i,b in enumerate(bs[:-1]):
            m,o,h,l,c,v=b;cum+=v;vp+=(h+l+c)/3*v;closes.append(c)
            if bs[i+1][0]!=m+5:high=max(high or h,h);continue
            vwap=vp/cum if cum>0 else c;signal=False;side=1;stop=c*(1-p.stop_pct);target=None
            if p.family=='confirm':
                signal=(m==555 and d.day_open and d.day_open/d.prev_close-1<=p.gap_limit and c>o and c>vwap)
                stop=min(l,c*.985)
            elif p.family in ('breakout','pullback'):
                clock_ok=(780 if p.afternoon else 630)<=m<870
                is_break=(clock_ok and high and c>high*1.003 and cum>=1.8*d.median_vol20*min(m+5-555,375)/375
                          and _rsi_14_wilder(closes)<70)
                if p.family=='breakout':signal=is_break;stop=min(l,c*.985)
                else:
                    if breakout and m<=breakout[1]+30 and l<=breakout[0]*1.003 and c>=breakout[0] and c>vwap:
                        signal=True;stop=min(l,c*.985)
                    if is_break and breakout is None:breakout=(high,m)
            elif p.family=='fade':
                side=-1
                signal=(630<=m<840 and c/d.day_open-1>=.02 and c<o and c<vwap and high and c<high*.995)
                stop=max(h,c*1.015)
            high=max(high or h,h)
            if not signal:continue
            entry=bs[i+1][1];target=entry+side*2*abs(entry-stop)
            if side*(entry-stop)<=0:continue
            cap_known=int(.01*v);cap_actual=int(.01*bs[i+1][5])
            outcome=intraday_outcome(d,i+1,entry,side,stop,p.exit_minute,target=target)
            orders.append(Order(d.date,m+5,d.ticker,entry,side,(m+5,d.ticker),cap_known,cap_actual,outcome,
                {'slot_fraction':1.,'decision_completed_at':m+5,'entry_basis':'NEXT_FIVE_MINUTE_BAR'}));break
    return orders,{}


def cnc_orders(daily,calendar,p,excluded=()):
    orders=[];allowed=set(calendar)
    for t,rows in daily.items():
        if t in excluded or '-' in t:continue
        closes=[r[4] for r in rows];wr=wilder_rsi(closes)
        for i in range(250,len(rows)):
            day=rows[i][0]
            if day not in allowed:continue
            prior=rows[i-20:i];cv=closes[max(0,i-5):i]
            f={'n':i,'close':closes[i-1],'tv':median(r[4]*r[5] for r in prior),
                'medvol':median(r[5] for r in prior),'sma200':mean(closes[i-200:i]),
                'sma50':mean(closes[i-50:i]),'sma5':mean(closes[i-5:i]),'wilder':wr[i-1],
                'rsi':_rsi_2(cv),'rsi_prev':_rsi_2(cv[:-1]),'rsi_prev2':_rsi_2(cv[:-2])}
            if not universe_ok(t,f,excluded):continue
            # Hist is before day. Signals refer to previous completed session;
            # regular entry is today's open, never yesterday's attainable close.
            if not f['sma200'] or f['close']<=f['sma200']:continue
            if p.family=='cnc_wilder':trigger=f['wilder']<10 and f['close']<f['sma5']
            else:
                trigger=(f['sma50'] and f['close']>f['sma50'] and f['rsi']<10)
                if p.family=='cnc_legacy':trigger=trigger and f['rsi']>f['rsi_prev']>f['rsi_prev2']
            if not trigger:continue
            bar=rows[i];entry=bar[1];outcome=None
            if p.family=='cnc_night':
                # This alternative buys previous close in post-close, exits
                # today's open. The order is timestamped at that prior close.
                prevday=rows[i-1][0];entry=f['close'];outcome=(day,555,bar[1],'NEXT_OPEN_PROXY')
                orderday,minute=prevday,970
            else:
                orderday,minute=day,555;stop=entry*(1-p.stop_pct);target=entry*1.06
                for j in range(i,min(len(rows),i+p.hold_days+2)):
                    date,o,h,l,c,v=rows[j]
                    if v<=0:continue
                    if j>i and o<=stop:
                        if o==h==l==c:continue
                        outcome=(date,555,o,'GAP_STOP');break
                    if j>i and o>=target:outcome=(date,555,o,'GAP_TARGET');break
                    if l<=stop:
                        if o==h==l==c:continue
                        outcome=(date,960,min(o,stop),'DAILY_STOP_FIRST');break
                    if h>=target:outcome=(date,960,max(o,target),'DAILY_TARGET');break
                    cs=[r[4] for r in rows[:j+1]]
                    exit_signal=(j-i+1>=p.hold_days or (p.family=='cnc_wilder' and (c>mean(cs[-5:]) or wr[j]>70)))
                    if exit_signal and j+1<len(rows):
                        nxt=rows[j+1]
                        if nxt[5]>0:outcome=(nxt[0],555,nxt[1],'NEXT_OPEN_AFTER_CLOSE_SIGNAL');break
            cap=int(.001*f['medvol'])
            actual=cap if p.family=='cnc_night' else int(.01*bar[5])
            orders.append(Order(orderday,minute,t,entry,1,(-f['tv'],t),cap,actual,outcome,
                {'slot_fraction':1.,'entry_basis':'POSTCLOSE_PROXY' if p.family=='cnc_night' else 'NEXT_DAY_OPEN'}))
    return orders,{}


def run_book(orders,daily,calendar,*,bankroll=2000.,entry_bps=25.,exit_bps=25.,max_new_day=1,max_positions=1,fill_seed=None):
    """Future outcomes are scheduled; cash is released only at their actual clock."""
    if bankroll<=0 or not math.isfinite(bankroll):raise ValueError('invalid bankroll')
    by=defaultdict(list)
    for o in orders:by[o.day].append(o)
    daily_index={t:{r[0]:r for r in rows} for t,rows in daily.items()}
    cash=bankroll;realized=0.;held={};heap=[];seq=0;trades=[];intents=[];curve=[];counts=Counter()
    def settle(clock):
        nonlocal cash,realized
        while heap and heap[0][:2]<=clock:
            day,minute,key=heapq.heappop(heap);pos=held.pop(key);o=pos['order'];raw=o.outcome[2]
            exit_price=raw*(1-o.side*exit_bps/10000)
            intraday=o.day==day;fees=float(calc_penny_costs(pos['entry'],exit_price,pos['qty'],is_intraday=intraday)) if o.side==1 else float(calc_penny_costs(exit_price,pos['entry'],pos['qty'],is_intraday=True))
            gross=o.side*(exit_price-pos['entry'])*pos['qty'];net=gross-fees
            cash+=pos['principal']+gross-fees;realized+=net
            trades.append({'ticker':o.ticker,'entry_day':o.day,'entry_minute':o.minute,'exit_day':day,'exit_minute':minute,
                'entry':pos['entry'],'exit':exit_price,'side':o.side,'qty':pos['qty'],'fees':fees,'net':net,
                'principal':pos['principal'],'reason':o.outcome[3],'scope':'CONDITIONAL_BAR_PROXY'})
    for day in calendar:
        settle((day,-1));taken=0
        for o in sorted(by.get(day,()),key=lambda x:(x.minute,x.score)):
            settle((day,o.minute))
            if taken>=max_new_day:counts['DAILY_ORDER_LIMIT']+=1;continue
            if len(held)>=max_positions:counts['POSITIONS_RESERVED_BY_CARRY']+=1;continue
            if o.ticker in {p['order'].ticker for p in held.values()}:counts['ALREADY_HELD']+=1;continue
            risk=max(0,min(bankroll,bankroll+realized));free=cash-max(realized,0)-sum(p['buffer'] for p in held.values())
            budget=min(free,risk*o.meta['slot_fraction'])
            if budget<=16:counts['NO_FREE_FUNDED_TICKET']+=1;continue
            entry=o.entry*(1+o.side*entry_bps/10000)
            if o.limit is not None and entry>o.limit:counts['PRICE_ABOVE_LIMIT']+=1;taken+=1;continue
            # Pre-open limit quantities use the known limit, not the unknown
            # eventual auction price. A better fill cannot enlarge the order.
            quantity_price=o.limit if o.limit is not None else entry
            plan=int(max(0,budget-15.34)//(quantity_price*1.002))
            qty=min(plan,o.cap_known,o.cap_actual)
            taken+=1
            if qty<1 or qty<.25*plan:counts['CAPACITY_OR_DUST']+=1;continue
            if fill_seed is not None and o.outcome is not None:
                import hashlib
                u=int.from_bytes(hashlib.sha256(f'{fill_seed}|{day}|{o.ticker}'.encode()).digest()[:8],'big')/2**64
                if o.side*(o.outcome[2]-entry)>0 and u>=.5:counts['WINNER_DENIED']+=1;continue
            principal=qty*entry;buffer=min(15.34+principal*.002,budget-principal)
            if principal+buffer>free+1e-7:raise AssertionError('unfunded order')
            cash-=principal;seq+=1
            held[seq]={'order':o,'qty':qty,'entry':entry,'principal':principal,'buffer':buffer}
            intents.append({'date':day,'minute':o.minute,'ticker':o.ticker,'budget':budget,'reserved':principal+buffer,'qty':qty})
            if o.outcome is not None:heapq.heappush(heap,(o.outcome[0],o.outcome[1],seq))
            counts['FUNDED_FILL_ASSUMPTION']+=1
        settle((day,2000))
        marked=cash
        for pos in held.values():
            o=pos['order'];row=daily_index.get(o.ticker,{}).get(day);mark=row[4] if row else pos['entry']
            marked+=pos['principal']+o.side*(mark-pos['entry'])*pos['qty']
        curve.append((day,marked))
    nets=[t['net'] for t in trades];peak=bankroll;dd=0.
    for _,equity in curve:peak=max(peak,equity);dd=max(dd,peak-equity)
    months=defaultdict(float);years=defaultdict(float)
    for t in trades:months[t['exit_day'][:7]]+=t['net'];years[t['exit_day'][:4]]+=t['net']
    net=sum(nets);s={'n':len(trades),'net':round(net,2),'ex_best':round(net-max(nets,default=0),2),
        'dd':round(dd,2),'dd_pct_initial':round(100*dd/bankroll,2),'fees':round(sum(t['fees'] for t in trades),2),
        'win':round(100*sum(x>0 for x in nets)/len(nets),2) if nets else None,
        'months':{k:round(v,2) for k,v in months.items()},'years':{k:round(v,2) for k,v in years.items()},'open':len(held)}
    if not held:assert abs(cash-bankroll-net)<1e-6
    return {'summary':s,'trades':trades,'curve':curve,'intents':intents,'outcomes':dict(counts),
        'cash':cash,'realized':realized,'open':len(held),'filled_fee_pnl':None,'scope':'CONDITIONAL_BAR_PROXY'}
