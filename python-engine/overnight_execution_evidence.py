"""Conservative post-close capacity evidence; never orders or assumed fills.

The independent collector is disabled by default. It measures only the
broker-supported 15:50-16:00 interval and preserves missing/stale observations.
Even a positive capacity proxy says nothing about our place in the order queue.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from contextlib import closing
from datetime import datetime,time
import json
import math
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

IST=ZoneInfo('Asia/Kolkata')
WINDOWS={'PRE':(time(15,49),time(15,50)),
         'DECISION':(time(15,51),time(15,52)),
         'END':(time(16,3),time(16,5))}


def stamp(value):
    if not value:return None
    try:
        d=value if isinstance(value,datetime) else datetime.fromisoformat(str(value))
        # Kite's naive provider timestamps are documented/treated as exchange IST.
        return d.replace(tzinfo=IST) if d.tzinfo is None else d.astimezone(IST)
    except (TypeError,ValueError):return None


def finite(value,positive=False):
    try:return math.isfinite(float(value)) and (float(value)>0 if positive else float(value)>=0)
    except (ValueError,TypeError):return False


def assess(snapshots,*,ticket=12500.,participation=.01):
    """Each input is one provider observation, never an executed order receipt."""
    if not finite(ticket,True) or not 0<participation<=1:raise ValueError('invalid hypothetical size')
    result={'status':'UNKNOWN','reason':None,'actual_fill':'UNKNOWN','ticket':ticket,
            'participation':participation,'scope':'CAPACITY_PROXY_ONLY','supports_fill_claim':False}
    def unknown(reason):return result|{'reason':reason}
    parsed={}
    for phase in WINDOWS:
        s=snapshots.get(phase)
        if not s:return unknown('missing_'+phase.lower())
        received=stamp(s.get('received_at'));provider=stamp(s.get('quote_time'));trade=stamp(s.get('last_trade_time'))
        if not all((received,provider,trade)):return unknown('missing_or_invalid_timestamp_'+phase.lower())
        start,end=WINDOWS[phase]
        if not start<=received.time()<end:return unknown('outside_window_'+phase.lower())
        if provider.date()!=received.date() or trade.date()!=received.date():return unknown('cross_date_'+phase.lower())
        if not -2<=(received-provider).total_seconds()<=30:return unknown('stale_or_future_quote_'+phase.lower())
        if (trade-provider).total_seconds()>2:return unknown('future_trade_'+phase.lower())
        if not finite(s.get('volume')) or not finite(s.get('last_price'),True):return unknown('invalid_values_'+phase.lower())
        parsed[phase]=(s,received,provider,trade)
    pre,decision,end=[parsed[x] for x in WINDOWS]
    if len({x[1].date() for x in parsed.values()})!=1:return unknown('cross_date_pair')
    volumes=[float(x[0]['volume']) for x in (pre,decision,end)]
    if not volumes[0]<=volumes[1]<=volumes[2]:return unknown('cumulative_volume_reset')
    for phase,item in [('decision',decision),('end',end)]:
        if not time(15,50)<=item[3].time()<=time(16):return unknown('no_supported_session_trade_'+phase)
    if volumes[1]<=volumes[0]:return unknown('no_observed_trade_before_decision')
    if end[3]<=decision[1]:return unknown('no_later_trade_after_decision')
    if volumes[2]==volumes[1]:return unknown('later_trade_without_volume_increment')
    price=float(decision[0]['last_price'])
    if abs(float(end[0]['last_price'])-price)>1e-7:return unknown('postclose_price_changed')
    qty=int(ticket//(price*1.002))
    if qty<1:return unknown('ticket_below_one_share')
    delta=volumes[2]-volumes[1]
    # No queue position, counterparties or our order acceptance exists here.
    proxy_qty=int(delta*participation)
    return result|{'status':'CAPACITY_PROXY_MET' if proxy_qty>=qty else 'CAPACITY_PROXY_SHORT',
        'reason':'observed_later_trades_only','reference_price':price,
        'reference_basis':'fixed post-close last trade, not quote ohlc.close',
        'hypothetical_quantity':qty,'later_volume':delta,'participation_quantity':proxy_qty,
        'decision_received_at':decision[1].isoformat(),'end_received_at':end[1].isoformat()}


def evidence_path(cache_path):return str(cache_path)+'.overnight-execution-evidence.db'


def enabled():
    from config import settings
    return bool(getattr(settings,'EDGE_OVERNIGHT_EXECUTION_EVIDENCE_ENABLED',False))


def _schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS observations(run_date TEXT, phase TEXT, ticker TEXT, payload TEXT NOT NULL, PRIMARY KEY(run_date,phase,ticker))')
    c.execute('CREATE TABLE IF NOT EXISTS runs(run_date TEXT, phase TEXT, payload TEXT NOT NULL, PRIMARY KEY(run_date,phase))')
    c.execute('CREATE TABLE IF NOT EXISTS shortlists(run_date TEXT PRIMARY KEY, payload TEXT NOT NULL)')


def capture_entry(cache_path,*,day,decided,picks,quotes,nights,late):
    """Archive existing decision inputs only; no new quote, fill or P&L.

    This is the bridge from final-candle research to point-in-time forward
    testing. Missing histories/quotes remain missing. Older data is not repaired.
    """
    if not enabled():return
    def safe(value):
        if isinstance(value,dict):return {str(k):safe(v) for k,v in value.items()}
        if isinstance(value,(list,tuple)):return [safe(v) for v in value]
        if isinstance(value,float) and not math.isfinite(value):return str(value)
        return value
    payload={'decided_at':stamp(decided).isoformat(),'late':late,'scope':'OBSERVED_SHORTLIST_ONLY',
             'actual_fill':'UNKNOWN','picks':[]}
    for rank,p in enumerate(picks[:10],1):
        payload['picks'].append({'ticker':p.ticker,'rank':rank,'kind':p.signal_subtype,
            'night_mean':(nights or {}).get(p.ticker),'quote':quotes.get(p.ticker),
            'adjusted_strength':getattr(p,'adjusted_strength',None)})
    with closing(sqlite3.connect(evidence_path(cache_path))) as c:
        _schema(c)
        with c:c.execute('INSERT OR IGNORE INTO shortlists VALUES(?,?)',
                        (day,json.dumps(safe(payload),allow_nan=False,default=str)))


async def collect(kite,phase,db_path=None,now=None):
    """At most one quote batch of the existing ENTRY receipt's bounded shortlist.

    No rescan, order, notification, paper fill or capital change. Failed/missing
    quotes persist for every requested ticker, so absence stays in the denominator.
    """
    if not enabled():return {'status':'disabled'}
    from config import settings
    import edge_overnight_paper as eop
    if phase not in WINDOWS:raise ValueError('invalid evidence phase')
    at=stamp(now or datetime.now(IST));start,end=WINDOWS[phase]
    if not start<=at.time()<end:return {'status':'outside_window'}
    cache=db_path or settings.DB_PATH;path=evidence_path(cache);day=at.date().isoformat()
    with closing(sqlite3.connect(path)) as c:
        _schema(c)
        if c.execute('SELECT 1 FROM runs WHERE run_date=? AND phase=?',(day,phase)).fetchone():return {'status':'repeat'}
        shortlist=c.execute('SELECT payload FROM shortlists WHERE run_date=?',(day,)).fetchone()
    source=eop.overnight_db_path(cache)
    if shortlist:
        tickers=[p['ticker'] for p in json.loads(shortlist[0])['picks']][:eop.RANK_DEPTH]
    else:
        try:
            with closing(sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True)) as c:
                tickers=eop._probe_tickers(c,day)[:eop.RANK_DEPTH]
        except sqlite3.OperationalError:tickers=[]
    error=None
    try:quotes=await eop._quotes(kite,tickers) if tickers else {}
    except Exception as exc:quotes={};error=type(exc).__name__
    received=stamp(now) if now is not None else datetime.now(IST)
    rows=[]
    for ticker in tickers:
        q=quotes.get(ticker) or {}
        def cell(value):
            return str(value) if isinstance(value,float) and not math.isfinite(value) else value
        payload={'received_at':received.isoformat(),'quote_time':str(q.get('timestamp') or ''),
            'last_trade_time':str(q.get('last_trade_time') or ''),'volume':cell(q.get('volume',q.get('volume_traded'))),
            'last_price':cell(q.get('last_price')),'error':error or (None if q else 'missing_quote')}
        rows.append((day,phase,ticker,json.dumps(payload,allow_nan=False,default=str)))
    status={'status':'observed' if tickers else 'no_entry_receipt','phase':phase,'requested':len(tickers),
            'quoted':sum(bool(quotes.get(t)) for t in tickers),'error':error,'received_at':received.isoformat()}
    with closing(sqlite3.connect(path)) as c:
        with c:
            c.executemany('INSERT OR IGNORE INTO observations VALUES(?,?,?,?)',rows)
            c.execute('INSERT OR IGNORE INTO runs VALUES(?,?,?)',(day,phase,json.dumps(status)))
    return status


def summary(cache_path,*,ticket=12500.):
    """Read-only additive API field; does not create a missing store."""
    out={'enabled':enabled(),'protocol':'broker-supported-window-v1','scope':'CAPACITY_PROXY_ONLY',
         'actual_fill':'UNKNOWN','supports_fill_claim':False,'pairs':0,'counts':{},'rows':[],
         'legacy_probe_caveat':'15:32-16:03 delta may include closing-auction/late reports; it cannot prove fills',
         'windows':{k:[a.isoformat(),b.isoformat()] for k,(a,b) in WINDOWS.items()}}
    path=Path(evidence_path(cache_path)).resolve()
    if not path.exists():return out|{'status':'not_collected'}
    grouped=defaultdict(dict);runs=[];shortlists=[]
    try:
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as c:
            for day,phase,ticker,payload in c.execute('SELECT * FROM observations ORDER BY run_date,ticker,phase'):
                grouped[(day,ticker)][phase]=json.loads(payload)
            runs=[json.loads(p[0]) for p in c.execute('SELECT payload FROM runs ORDER BY run_date,phase')]
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='shortlists'").fetchone():
                shortlists=[{'date':day,**json.loads(payload)} for day,payload in c.execute('SELECT * FROM shortlists ORDER BY run_date')]
    except (sqlite3.Error,ValueError,TypeError) as exc:
        return out|{'status':'unreadable_evidence','error':type(exc).__name__}
    for shortlist in shortlists:
        for p in shortlist['picks']:
            grouped.setdefault((shortlist['date'],p['ticker']),{})
    counts=Counter();reasons=Counter()
    for (day,ticker),snapshots in grouped.items():
        assessment=assess(snapshots,ticket=ticket);counts[assessment['status']]+=1;reasons[assessment['reason']]+=1
        out['rows'].append({'date':day,'ticker':ticker,**assessment})
    return out|{'status':'observed','pairs':len(grouped),'counts':dict(counts),'reasons':dict(reasons),
                'runs':runs,'entry_shortlists':shortlists,'ticket':ticket}
