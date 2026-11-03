"""E02 R3 research shadow: one-lot trend pullbacks, disabled by default.

Joint-fitted on already-seen 2024/2025, NOT qualified by an untouched test.
Reads the existing expiry quote archive only: no provider, broker, order or
notification client. Separate cash/state DB, never the operational ledger.
Live bars are sampled from ten-second observations, a distinct forward data
basis from historical exchange minute OHLC. Gaps refuse signals.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime,time,timedelta
from pathlib import Path
from contextlib import closing
import json,math,sqlite3
from typing import Optional

import expiry_paper as EP

VERSION='expiry-e02-r3-v1'
QUALIFICATION='RESEARCH_ONLY_JOINT_FIT'
START_CASH=25000.0
DAY_CEILING=2500.0
MAX_TRADES=2
LOT=65


@dataclass(frozen=True)
class Reading:
    direction:int
    spot:float
    atr:float
    minute:int
    efficiency:float


def path_for(db_path):return str(db_path)+'.expiry-e02.db'


def signal(bars:list[dict])->Optional[Reading]:
    """Twelve completed consecutive bars; no future/missing sample imputation."""
    if len(bars)<12:return None
    b=bars[-12:]
    stamps=[datetime.fromisoformat(x['end']) for x in b]
    if any(y-x!=timedelta(minutes=1) for x,y in zip(stamps,stamps[1:])):return None
    if len({x.date() for x in stamps})!=1:return None
    if any(len(x.get('s',[]))!=4 or len(x.get('f',[]))!=4 for x in b):return None
    values=[v for x in b for k in ('s','f') for v in x[k]]
    if not all(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in values):return None
    for x in b:
        for k in ('s','f'):
            o,h,l,c=x[k]
            if not l<=min(o,c)<=max(o,c)<=h:return None
    now=stamps[-1];minute=now.hour*60+now.minute
    if not 780<=minute<900:return None
    closes=[x['s'][3] for x in b]
    history=closes[-11:]
    distance=sum(abs(y-x) for x,y in zip(history,history[1:]))
    if distance<=0:return None
    er=(history[-1]-history[0])/distance
    sign=1 if er>0 else -1
    if sign*er<.7:return None
    tr=[max(x['s'][1]-x['s'][2],abs(x['s'][1]-prev),abs(x['s'][2]-prev)) for x,prev in zip(b[-11:-1],closes[-12:-2])]
    atr=sum(tr)/10.
    if atr<=0 or abs(closes[-1]-sum(closes[-11:-1])/10.)>4*atr:return None
    if sign*(closes[-2]-closes[-4])>=0:return None
    if sign*(closes[-1]-closes[-2])<=0:return None
    if sign*(b[-1]['f'][3]-b[-2]['f'][3])<=0:return None
    return Reading(sign,closes[-1],atr,minute,er)


def policy():
    return EP.ExitPolicy(hard_stop=.4,bank_at=None,bank_stop=None,trails=((.4,.6),),late=None,time_stop=None,flat_at=time(15,28))


def action(pos,bid,spot,now):
    broken=spot is not None and pos['direction']*(spot-pos['underlying_stop'])<0
    frozen=pos.get('e02_policy',dict(stop=.4,arm=.4,keep=.6,target=1.,hold=480))
    exits=EP.ExitPolicy(hard_stop=frozen['stop'],bank_at=None,bank_stop=None,trails=((frozen['arm'],frozen['keep']),),late=None,time_stop=None,flat_at=time(15,28))
    native=EP.manage_position(pos,exits,bid,now,structure_broken=broken)
    if native:
        lots,reason=native
        return lots,'STRUCTURE' if reason=='FAILED_BREAK' else reason
    if bid>=pos['entry_price']*(1+frozen['target']):return pos['lots_open'],'TARGET'
    if (now-datetime.fromisoformat(pos['entry_ts'])).total_seconds()>=frozen['hold']:return pos['lots_open'],'TIME'
    return None


def logged_quote(raw):
    if not isinstance(raw,dict):return None
    try:
        def levels(key):
            out=[]
            for p,q in raw.get(key,[]):
                p=float(p);q=int(q)
                if not math.isfinite(p) or p<=0 or q<=0:return ()
                out.append((p,q))
            return tuple(out)
        stamp=datetime.fromisoformat(raw['ts']) if raw.get('ts') else None
        if stamp is not None and stamp.tzinfo is None:stamp=stamp.replace(tzinfo=EP.IST)
        return EP.Quote(levels('b'),levels('a'),EP._positive(raw.get('ltp')),stamp)
    except (TypeError,ValueError,KeyError):return None


def plan(reading,legs,book,now,budget,cash):
    """Nearest observed OTM strike within a causal move allowance; one lot."""
    expected=reading.atr*math.sqrt(max(1,930-reading.minute))
    candidates=[];schedule=EP.fee_schedule('NFO')
    for symbol,raw in legs.items():
        contract=book.by_symbol.get(symbol)
        if contract is None or contract.underlying!='NIFTY' or contract.expiry!=now.date() or contract.lot_size!=LOT:continue
        if contract.instrument_type!=('CE' if reading.direction==1 else 'PE'):continue
        distance=reading.direction*(contract.strike-reading.spot)
        if not 0<distance<=min(400,expected):continue
        q=logged_quote(raw)
        if q is None or not q.fresh(now) or not q.spread_ok(.10) or not 5<=q.ask<=20:continue
        filled,ask=EP.walk(q.asks,1,LOT)
        if filled!=1:continue
        # No future-based sizing: this cap is fixed before any later quote.
        cap=min(ask*1.10,(min(budget,cash)-2*EP.order_fee(schedule))/(LOT*(1+(EP.buy_charges(100,1,schedule)-EP.order_fee(schedule))/100)))
        limit=math.floor(round(cap/.05,6))*.05
        if limit<ask or EP.worst_case_loss(limit,1,LOT,schedule)>min(budget,cash)+.001:continue
        candidates.append((distance,symbol,round(limit,2)))
    if not candidates:return None
    _,symbol,limit=min(candidates)
    return dict(symbol=symbol,limit=limit,at=now.isoformat(),expires=(now+timedelta(minutes=1)).isoformat(),
                direction=reading.direction,underlying_stop=reading.spot-reading.direction*2*reading.atr)


def _new_state(now):
    return dict(version=VERSION,qualification=QUALIFICATION,basis='SAMPLED_10S_FORWARD',cash=START_CASH,peak=START_CASH,
                activation=now.isoformat(),watermark=None,bars=[],building=None,day=None,position=None,pending=None,last_close=None,last_decided=None)


def _store(c,state):
    c.execute('INSERT OR REPLACE INTO e02_state VALUES(1,?)',(json.dumps(state,allow_nan=False),))


def _save_position(c,p):
    if p['id'] is None:
        p['id']=c.execute('INSERT INTO e02_positions(day,status,payload) VALUES(?,?,?)',(p['day'],p['status'],'{}')).lastrowid
    c.execute('UPDATE e02_positions SET status=?,payload=? WHERE id=?',(p['status'],json.dumps(p,allow_nan=False),p['id']))


def _sample(state,row):
    stamp=datetime.fromisoformat(row['ts']);minute=stamp.replace(second=0,microsecond=0)
    payload=json.loads(row['quotes']);fresh=row['spot'] is not None and row['fut'] is not None
    if not all(EP._positive(row[k]) is not None for k in ('spot','fut')):fresh=False
    current=state.get('building');completed=None
    if current and current['minute']!=minute.isoformat():
        times=[datetime.fromisoformat(t) for t in current['times']]
        if len(times)>=4 and (times[-1]-times[0]).total_seconds()>=30 and all(0<(b-a).total_seconds()<=25 for a,b in zip(times,times[1:])):
            def ohlc(x):return [x[0],max(x),min(x),x[-1]]
            completed=dict(end=(datetime.fromisoformat(current['minute'])+timedelta(minutes=1)).isoformat(),s=ohlc(current['s']),f=ohlc(current['f']))
            state['bars']=(state['bars']+[completed])[-20:]
            state['last_bar_legs']=current['legs']
        current=None
    if current is None:current=dict(minute=minute.isoformat(),s=[],f=[],times=[],legs={})
    if fresh:
        current['s'].append(float(row['spot']));current['f'].append(float(row['fut']));current['times'].append(stamp.isoformat());current['legs']=payload.get('legs',{})
    state['building']=current
    return completed


def has_open_book(db_path):
    path=Path(path_for(db_path))
    if not path.exists():return False
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=1)) as c:
        r=c.execute('SELECT payload FROM e02_state WHERE id=1').fetchone()
        return bool(r and json.loads(r[0]).get('position'))


def held_contracts(db_path,book):
    """Keep the one open research leg in the primary's existing quote batch."""
    path=Path(path_for(db_path))
    if not path.exists():return []
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=1)) as c:
        row=c.execute('SELECT payload FROM e02_state WHERE id=1').fetchone()
    p=json.loads(row[0]).get('position') if row else None
    if not p or p.get('status')!='OPEN':return []
    contract=book.by_symbol.get(p['symbol'])
    return [contract] if contract is not None else []


def run_tick(db_path,*,enabled=False,now=None,book=None):
    """Incremental read-only source, separate transactional paper state, no network."""
    now=now or datetime.now(EP.IST)
    if now.tzinfo is None:raise ValueError('Timezone-aware E02 clock required')
    destination=Path(path_for(db_path));source=Path(str(db_path)+'.expiry-paper.db')
    if not enabled and not destination.exists():return {'status':'DISABLED'}
    if not source.exists():return {'status':'NO_SOURCE'}
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True,timeout=1)) as src:
        src.row_factory=sqlite3.Row
        latest=src.execute("SELECT * FROM expiry_paper_ticks WHERE day=? AND underlying='NIFTY' ORDER BY ts DESC LIMIT 1",(now.date().isoformat(),)).fetchone()
        if latest is None:return {'status':'NO_NIFTY_SOURCE'}
        observed=datetime.fromisoformat(latest['ts'])
        if not -5<=(now-observed).total_seconds()<=20:return {'status':'STALE_SOURCE'}
        with closing(sqlite3.connect(destination,timeout=1)) as dst:
            dst.execute('CREATE TABLE IF NOT EXISTS e02_state(id INTEGER PRIMARY KEY,payload TEXT NOT NULL)')
            dst.execute('CREATE TABLE IF NOT EXISTS e02_positions(id INTEGER PRIMARY KEY,day TEXT,status TEXT,payload TEXT NOT NULL)')
            with dst:
                dst.execute('BEGIN IMMEDIATE')
                saved=dst.execute('SELECT payload FROM e02_state WHERE id=1').fetchone()
                state=json.loads(saved[0]) if saved else _new_state(now)
                if state['version']!=VERSION:raise ValueError('Unknown E02 state version')
                if not state.get('day') or state['day']['date']!=now.date().isoformat():
                    if state['position']:return {'status':'UNRESOLVED_PRIOR_DAY'}
                    dd=state['peak']-state['cash'];scale=0 if dd>=4000 else .25 if dd>=3000 else .5 if dd>=1500 else 1
                    state.update(day=dict(date=now.date().isoformat(),budget=min(DAY_CEILING*scale,state['cash']),spent=0.,trades=0),bars=[],building=None,pending=None,last_decided=None)
                # Reconcile realized cash from immutable closed records before risk admission.
                closed=[json.loads(r[0]) for r in dst.execute("SELECT payload FROM e02_positions WHERE status='CLOSED' ORDER BY id")]
                expected=peak=START_CASH
                for p in closed:
                    if not all(math.isfinite(p[k]) for k in ('net_pnl','gross','costs')) or abs(p['gross']-p['costs']-p['net_pnl'])>.02:raise ValueError('E02 malformed close')
                    expected=round(expected+p['net_pnl'],2);peak=max(peak,expected)
                if not all(math.isfinite(state[k]) for k in ('cash','peak')) or abs(state['cash']-expected)>.01 or abs(state['peak']-peak)>.01 or state['cash']<0:raise ValueError('E02 cash journal mismatch')
                rows=src.execute("SELECT * FROM expiry_paper_ticks WHERE day=? AND underlying='NIFTY' AND ts>? ORDER BY ts",(now.date().isoformat(),state['watermark'] or '')).fetchall()
                completed=None
                for row in rows:
                    bar=_sample(state,row)
                    if bar:completed=bar
                if completed and not timedelta(0)<=(now-datetime.fromisoformat(completed['end']))<timedelta(minutes=1):completed=None
                state['watermark']=latest['ts']
                legs=json.loads(latest['quotes']).get('legs',{});position=state['position'];event=None
                if position:
                    q=logged_quote(legs.get(position['symbol']))
                    if position['exit_pending']:
                        event=EP._try_exit(position,q,position['lots_open'],position['exit_pending'],now)
                    elif completed:
                        close_q=logged_quote(state.get('last_bar_legs',{}).get(position['symbol']))
                        decision_time=datetime.fromisoformat(completed['end'])
                        if close_q and close_q.bid and close_q.fresh(decision_time):
                            sell=action(position,close_q.bid,completed['s'][3],decision_time)
                            if sell:event=EP._try_exit(position,q,*sell,now)
                    if now.time()>=time(15,28) and position['status']=='OPEN':event=EP._try_exit(position,q,position['lots_open'],'FLAT_TIME',now)
                    _save_position(dst,position)
                    if position['status']=='CLOSED':
                        state['cash']=round(state['cash']+position['net_pnl'],2);state['peak']=max(state['peak'],state['cash']);state['last_close']=now.isoformat();state['position']=None
                if enabled and not state['position']:
                    day=state['day']
                    cool=not state['last_close'] or now-datetime.fromisoformat(state['last_close'])>=timedelta(minutes=5)
                    if completed and completed['end']!=state['last_decided']:
                        state['last_decided']=completed['end']
                        reading=signal(state['bars'])
                        if reading and datetime.fromisoformat(completed['end'])>datetime.fromisoformat(state['activation']) and cool and day['trades']<MAX_TRADES:
                            if book is None:
                                from fno_underlyings import get_instruments_for
                                book=get_instruments_for('NIFTY')
                            state['pending']=plan(reading,state.get('last_bar_legs',{}),book,datetime.fromisoformat(completed['end']),min(1250.,day['budget']-day['spent']),state['cash'])
                    pending=state['pending']
                    if pending:
                        if now>datetime.fromisoformat(pending['expires']) or now.time()>=time(15,0) or day['trades']>=MAX_TRADES:state['pending']=None
                        else:
                            if book is None:
                                from fno_underlyings import get_instruments_for
                                book=get_instruments_for('NIFTY')
                            q=logged_quote(legs.get(pending['symbol']))
                            con=book.by_symbol.get(pending['symbol']) if book else None
                            if con and con.expiry==now.date() and con.lot_size==LOT and q and q.fresh(now) and q.spread_ok(.10):
                                lots,price=EP.walk(q.asks,1,LOT)
                                schedule=EP.fee_schedule('NFO')
                                risk=EP.worst_case_loss(price,1,LOT,schedule) if lots else math.inf
                                if lots and price<=pending['limit'] and risk<=min(1250.,day['budget']-day['spent'],state['cash']):
                                    p=EP._new_position(now.date().isoformat(),'NIFTY','E02R3','NFO',con,price,1,now,schedule)
                                    p.update(stop=round(price*.6,2),direction=pending['direction'],underlying_stop=pending['underlying_stop'],e02_version=VERSION,data_basis='SAMPLED_10S_FORWARD',e02_policy=dict(stop=.4,arm=.4,keep=.6,target=1.,hold=480))
                                    _save_position(dst,p);state['position']=p;day['spent']=round(day['spent']+risk,2);day['trades']+=1;state['pending']=None
                if not enabled:state['pending']=None
                if state['day']['spent']>state['day']['budget']+.01:raise ValueError('E02 daily reserve exceeded')
                _store(dst,state)
                return dict(status='OPEN' if state['position'] else 'OBSERVING',version=VERSION,qualification=QUALIFICATION,cash=state['cash'],day=state['day'],event=event)
