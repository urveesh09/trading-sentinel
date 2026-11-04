"""Read-only auction-capacity and 09:30 bid evidence for Smart V3.

No order, assumed new position, realised P&L or native-book mutation. Default
off. An observed market packet is not proof of our order or queue position.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from contextlib import closing
from datetime import datetime,time
import json,math,sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo

IST=ZoneInfo('Asia/Kolkata')
WINDOWS={'AUCTION':(time(9,12),time(9,14)), 'MORNING':(time(9,30),time(9,32))}


def enabled():
    from config import settings
    return bool(getattr(settings,'PENNY_SMART_MORNING_EVIDENCE_ENABLED',False))


def store_path(cache):return str(cache)+'.penny-smart-morning-evidence.db'


def stamp(value):
    try:
        d=value if isinstance(value,datetime) else datetime.fromisoformat(str(value))
        return d.replace(tzinfo=IST) if d.tzinfo is None else d.astimezone(IST)
    except (TypeError,ValueError):return None


def positive(value):
    try:return math.isfinite(float(value)) and float(value)>0
    except (ValueError,TypeError):return False


def packet_quality(q,received,phase):
    received=stamp(received);provider=stamp(q.get('timestamp'));trade=stamp(q.get('last_trade_time'))
    if not received or not provider or not trade:return 'missing_timestamp'
    if not WINDOWS[phase][0]<=received.time()<WINDOWS[phase][1]:return 'outside_receipt_window'
    if len({received.date(),provider.date(),trade.date()})!=1:return 'cross_date_packet'
    if not -2<=(received-provider).total_seconds()<=30:return 'stale_or_future_packet'
    if (trade-provider).total_seconds()>2:return 'future_trade'
    if phase=='AUCTION':
        if not time(9,10)<=trade.time()<time(9,15):return 'no_observed_matching_trade'
        if not positive(q.get('volume')):return 'no_matching_volume'
    elif not time(9,15)<=trade.time()<=received.time():return 'no_trade_today'
    return None


def bid_projection(source,q,received):
    """Walk displayed bid QUANTITY. Missing/partial depth is not a full exit."""
    result={'status':'UNKNOWN','actual_fill':'UNKNOWN','scope':'DISPLAYED_BID_COUNTERFACTUAL',
            'modeled_net':None,'filled_quantity':0,'source_entry_basis':'native auction-price assumption'}
    why=packet_quality(q,received,'MORNING')
    if why:return result|{'reason':why}
    entry=source.get('entry_price');qty=source.get('shares')
    if not positive(entry) or not positive(qty):return result|{'reason':'no_native_entry'}
    qty=int(qty);levels=[]
    for b in (q.get('depth') or {}).get('buy',[]):
        if positive(b.get('price')) and positive(b.get('quantity')):levels.append((float(b['price']),int(b['quantity'])))
    levels.sort(reverse=True);left=qty;value=0.
    for price,n in levels:
        take=min(left,n);value+=price*take;left-=take
        if left==0:break
    if left:return result|{'status':'PARTIAL_BID_CAPACITY','reason':'not_enough_displayed_bids','filled_quantity':qty-left}
    exit_=value/qty
    from penny_risk import calc_penny_costs
    fees=float(calc_penny_costs(float(entry),exit_,qty,is_intraday=True))
    return result|{'status':'FULL_BID_CAPACITY_PROXY','reason':'not_an_order_fill','filled_quantity':qty,
        'exit_vwap':exit_,'fees':fees,'modeled_net':round((exit_-float(entry))*qty-fees,4),
        'native_quantity_was_frozen_preopen':False,'received_at':stamp(received).isoformat()}


def _schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS observations(run_date TEXT,phase TEXT,variant TEXT,ticker TEXT,payload TEXT,PRIMARY KEY(run_date,phase,variant,ticker))')
    c.execute('CREATE TABLE IF NOT EXISTS runs(run_date TEXT,phase TEXT,payload TEXT,PRIMARY KEY(run_date,phase))')


def _source_rows(cache,day,phase):
    from penny_smart_v3 import store_path as native_path
    path=Path(native_path(str(cache))).resolve()
    if not path.exists():return []
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as c:
        c.row_factory=sqlite3.Row
        where="variant='SV3_PREOPEN' AND status='DECIDED'" if phase=='AUCTION' else "status='OPEN'"
        return [dict(r) for r in c.execute('SELECT * FROM sv3_trades WHERE trade_date=? AND '+where+' ORDER BY variant,ticker',(day,))]


async def collect(kite,phase,cache=None,now=None):
    if not enabled():return {'status':'disabled'}
    if phase not in WINDOWS:raise ValueError('unknown phase')
    from config import settings
    from penny_smart_v3 import _quotes
    cache=cache or settings.DB_PATH;at=stamp(now or datetime.now(IST));day=at.date().isoformat()
    if not WINDOWS[phase][0]<=at.time()<WINDOWS[phase][1]:return {'status':'outside_window'}
    path=store_path(cache)
    with closing(sqlite3.connect(path)) as c:
        _schema(c)
        if c.execute('SELECT 1 FROM runs WHERE run_date=? AND phase=?',(day,phase)).fetchone():return {'status':'repeat'}
    sources=_source_rows(cache,day,phase);names=sorted({s['ticker'] for s in sources})[:10]
    sources=[s for s in sources if s['ticker'] in names]
    error=None
    try:quotes=await _quotes(kite,names) if names else {}
    except Exception as exc:quotes={};error=type(exc).__name__
    received=stamp(now) if now is not None else datetime.now(IST)
    def safe(value):
        if isinstance(value,dict):return {str(k):safe(v) for k,v in value.items()}
        if isinstance(value,(list,tuple)):return [safe(v) for v in value]
        if isinstance(value,float) and not math.isfinite(value):return str(value)
        return value
    rows=[]
    for source in sources:
        q=quotes.get(source['ticker']) or {};reason=packet_quality(q,received,phase)
        assessment=(bid_projection(source,q,received) if phase=='MORNING' else
            {'status':'MATCH_VOLUME_OBSERVED' if reason is None else 'UNKNOWN','reason':reason,
             'actual_fill':'UNKNOWN','auction_volume':q.get('volume') if reason is None else None,
             'matching_last_price':q.get('last_price') if reason is None else None,
             'native_planned_quantity':source.get('plan_shares'),
             'quantity_not_frozen_before_matching':source.get('plan_shares') is None})
        payload={'source':source,'quote':q,'received_at':received.isoformat(),'assessment':assessment,'error':error}
        rows.append((day,phase,source['variant'],source['ticker'],json.dumps(safe(payload),default=str,allow_nan=False)))
    result={'status':'observed','phase':phase,'requested_positions':len(sources),'requested_tickers':len(names),
            'quoted_tickers':sum(bool(quotes.get(t)) for t in names),'error':error,'received_at':received.isoformat()}
    with closing(sqlite3.connect(path)) as c:
        with c:
            c.executemany('INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?)',rows)
            c.execute('INSERT INTO runs VALUES(?,?,?)',(day,phase,json.dumps(result)))
    return result


def summary(cache):
    out={'enabled':enabled(),'actual_fill':'UNKNOWN','scope':'COUNTERFACTUAL_EVIDENCE_ONLY','rows':[],
         'entry_caveat':'PREOPEN indicative price/fills unproven; REF selected after auction; native quantity is calculated after clearing',
         'auction_caveat':'09:16 cumulative volume includes continuous trades; only a valid before09:15 packet isolates matching volume'}
    path=Path(store_path(cache)).resolve()
    if not path.exists():return out|{'status':'not_collected'}
    try:
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as c:
            rows=c.execute('SELECT run_date,phase,variant,ticker,payload FROM observations ORDER BY run_date,phase,variant,ticker').fetchall()
            runs=[json.loads(r[0]) for r in c.execute('SELECT payload FROM runs ORDER BY run_date,phase')]
        counts=Counter();per=defaultdict(lambda:{'bid_complete':0,'modeled_net':0.,'paired':0,'paired_bid_net':0.,'paired_native_net':0.})
        matching={}
        for day,phase,variant,t,payload in rows:
            if phase=='AUCTION':matching[(day,variant,t)]=json.loads(payload)['assessment']
        native={}
        from penny_smart_v3 import store_path as native_path
        original=Path(native_path(str(cache))).resolve()
        if original.exists():
            with closing(sqlite3.connect(original.as_uri()+'?mode=ro',uri=True)) as c:
                for v,d,t,status,entry,shares,net in c.execute('SELECT variant,trade_date,ticker,status,entry_price,shares,net_pnl FROM sv3_trades'):
                    native[(d,v,t)]=(status,entry,shares,net)
        for day,phase,variant,t,payload in rows:
            p=json.loads(payload);a=p['assessment'];counts[phase+':'+a['status']]+=1
            if phase=='MORNING':
                match=matching.get((day,variant,t));a['entry_capacity_grade']='UNKNOWN'
                if match and match.get('auction_volume') is not None and positive(p['source'].get('shares')):
                    cap=int(.1*float(match['auction_volume']));a['observed_auction_10pct_quantity']=cap
                    a['entry_capacity_grade']=('WITHIN_PARTICIPATION_PROXY' if p['source']['shares']<=cap else 'EXCEEDS_PARTICIPATION_PROXY')
                    a['matching_price_equals_native_model']=(abs(float(match['matching_last_price'])-float(p['source']['entry_price']))<1e-7
                        if positive(match.get('matching_last_price')) else None)
            out['rows'].append({'date':day,'phase':phase,'variant':variant,'ticker':t,**a})
            if phase!='MORNING' or a['modeled_net'] is None:continue
            per[variant]['bid_complete']+=1;per[variant]['modeled_net']+=a['modeled_net']
            n=native.get((day,variant,t));source=p['source']
            if n and n[0]=='CLOSED' and n[1]==source['entry_price'] and n[2]==source['shares'] and n[3] is not None:
                per[variant]['paired']+=1;per[variant]['paired_bid_net']+=a['modeled_net'];per[variant]['paired_native_net']+=n[3]
        return out|{'status':'observed','counts':dict(counts),'variants':dict(per),'runs':runs}
    except (sqlite3.Error,ValueError,KeyError,TypeError) as e:return out|{'status':'unreadable_evidence','error':type(e).__name__}
