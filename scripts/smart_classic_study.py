"""Independent Smart/Classic study data; no broker, scheduler or live book."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone,timedelta
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import sys
from urllib.error import HTTPError
from urllib.parse import urlencode,quote
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python-engine'))
RUN=ROOT/'docs/research/penny/2026-11-04-smart-classic-enrichment'
OLD=ROOT/'docs/research/penny/2026-11-04-intraday'
IST=timezone(timedelta(hours=5,minutes=30))


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(p,obj):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    tmp=Path(str(p)+'.tmp');tmp.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n',encoding='utf-8');tmp.replace(p)


def select():
    from penny_universe import _is_non_equity_symbol
    inputs=[ROOT/'docs/research/penny/2026-11-04-strategy-search/_local/production-cash.sqlite',
            ROOT/'docs/research/kite/2026-10-05-penny-h1/_local/validated-kite.sqlite']
    seen=set()
    for p in inputs:
        c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
        seen.update(t for t, in c.execute('SELECT DISTINCT ticker FROM intraday_cache'));c.close()
    p=ROOT/'docs/research/penny/2026-11-04-overnight-v2/universe-yahoo.json'
    universe=json.loads(p.read_text())['symbols']
    candidates=[t for t in universe if t not in seen and '-' not in t and not _is_non_equity_symbol(t)]
    names=sorted(candidates,key=lambda t:hashlib.sha256(('smart-classic-20261104|'+t).encode()).hexdigest())[:160]
    target=RUN/'cross-name-selection.json'
    if target.exists():raise ValueError('immutable name selection exists')
    write(target,{'names':names,'requested':len(names),'excluded_seen_minute_names':sorted(seen),
        'rule':'first160 by sha256(smart-classic-20261104|ticker), no outcomes','window':['2026-09-07','2026-11-03'],
        'scope':'new minute histories on seen dates; not a fresh chronological exam',
        'breeze_calls':0,'broker_calls':0,'source_universe_sha256':sha(p),'selected_at':datetime.now(timezone.utc).isoformat()})


def fetch(t,start,end,local):
    first=datetime.fromisoformat(start).replace(tzinfo=IST)
    last=datetime.fromisoformat(end).replace(tzinfo=IST)+timedelta(days=1)
    url='https://query1.finance.yahoo.com/v8/finance/chart/'+quote(t+'.NS')+'?'+urlencode(
        {'period1':int(first.timestamp()),'period2':int(last.timestamp()),'interval':'5m','events':'div,splits','includePrePost':'false'})
    receipt={'symbol':t,'url':url,'interval':'5m','fetched_at':datetime.now(timezone.utc).isoformat()}
    target=local/'raw'/f'{t}_5m.json';target.parent.mkdir(parents=True,exist_ok=True)
    try:
        try:response=urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 TradingSentinelResearch/1.0'}),timeout=25)
        except HTTPError as e:response=e
        with response as r:data=r.read(10000001);status=r.code
        if len(data)>10000000:raise ValueError('bounded response exceeded')
        with target.open('xb') as f:f.write(data)
        receipt.update(http_status=status,raw_file=str(target.relative_to(RUN)).replace('\\','/'),raw_sha256=sha(target))
        payload=json.loads(data);chart=payload.get('chart',{})
        if status!=200 or chart.get('error'):raise ValueError(str(chart.get('error') or status))
        res=chart['result'][0];meta=res['meta'];q=res['indicators']['quote'][0];times=res['timestamp']
        if meta['symbol']!=t+'.NS' or meta['currency']!='INR' or meta['exchangeTimezoneName'] not in ('Asia/Kolkata','Asia/Calcutta') or meta.get('dataGranularity')!='5m':raise ValueError('identity/interval/timezone mismatch')
        fields=['open','high','low','close','volume']
        if any(len(q[k])!=len(times) for k in fields):raise ValueError('unaligned arrays')
        rows=[];invalid=0;outside=0
        for i,secs in enumerate(times):
            dt=datetime.fromtimestamp(secs,IST)
            if not start<=dt.date().isoformat()<=end or not 555<=dt.hour*60+dt.minute<930:outside+=1;continue
            if dt.minute%5 or dt.second:raise ValueError('off-grid 5-minute start')
            cells=[q[k][i] for k in fields]
            if all(v is None for v in cells):continue
            values=[float(v) if not isinstance(v,bool) and isinstance(v,(int,float)) and math.isfinite(v) else None for v in cells]
            invalid+=int(None in values)
            rows.append((t,'5minute',dt.isoformat(),*values))
        receipt.update(state='AVAILABLE' if rows else 'EMPTY',rows=len(rows),invalid_rows=invalid,outside_rows=outside,
            instrument_type=meta.get('instrumentType'),corporate_actions=res.get('events',{}))
        return rows,receipt
    except Exception as e:return [],receipt|{'state':'UNAVAILABLE','reason':type(e).__name__+': '+str(e)}


def acquire():
    sel=json.loads((RUN/'cross-name-selection.json').read_text());local=RUN/'_local/cross-name';local.mkdir(parents=True,exist_ok=True)
    target=local/'bars.sqlite'
    if target.exists():raise ValueError('immutable acquisition exists')
    c=sqlite3.connect(target);c.execute('CREATE TABLE intraday_cache(ticker,interval,datetime,open,high,low,close,volume,PRIMARY KEY(ticker,interval,datetime))')
    receipts=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        fs={pool.submit(fetch,t,*sel['window'],local):t for t in sel['names']}
        for f in as_completed(fs):
            rows,r=f.result();receipts.append(r);c.executemany('INSERT OR IGNORE INTO intraday_cache VALUES(?,?,?,?,?,?,?,?)',rows);c.commit()
            if len(receipts)%20==0:print('cross-name acquisition',len(receipts),'/',len(sel['names']),flush=True)
    metadata=c.execute('SELECT COUNT(*),COUNT(DISTINCT ticker),MIN(datetime),MAX(datetime) FROM intraday_cache').fetchone();c.close()
    write(RUN/'cross-name-acquisition.json',{'metadata_only':metadata,'database_sha256':sha(target),'receipts':receipts,
        'outcomes_opened':False,'breeze_calls':0,'broker_calls':0})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['select','acquire']);a=p.parse_args();globals()[a.command]()
