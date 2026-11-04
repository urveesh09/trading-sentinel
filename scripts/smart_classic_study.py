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
import pickle
import sys
from urllib.error import HTTPError
from urllib.parse import urlencode,quote
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python-engine'))
RUN=ROOT/'docs/research/penny/2026-11-04-smart-classic-enrichment'
OLD=ROOT/'docs/research/penny/2026-11-04-intraday'
IST=timezone(timedelta(hours=5,minutes=30))


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()


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


def legacy():
    if str(OLD) not in sys.path:sys.path.insert(0,str(OLD))
    import idata,minute_oar,oarsim
    return idata,minute_oar,oarsim


def source_hashes():
    files=[Path(__file__).resolve(),ROOT/'python-engine/smart_classic_enrichment.py',
        *[OLD/n for n in ['idata.py','minute_oar.py','oarsim.py']],
        *[ROOT/'python-engine'/n for n in ['penny_smart_v3.py','penny_engine_connors.py','penny_engine_breakout.py',
            'penny_risk.py','penny_universe.py','research_penny_cnc_lifecycle.py','research_data_contracts.py',
            'penny_lifecycle_replay.py','position_tracker.py','penny_instrument_identity.py','config.py']]]
    return {str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in files}


def inputs():
    idata,_,o=legacy()
    return [idata.DEV_DAILY,idata.EXAM_DB,o.OLD,o.V2/'yahoo/yahoo.sqlite',o.V2/'yahoo-split-cuts.json',
            o.V2/'yahoo-acquisition.json',RUN/'cross-name-acquisition.json',RUN/'nse-etf-identity.json']


def proposals(round_):
    from smart_classic_enrichment import Policy
    from dataclasses import asdict
    if round_==1:
        ps=[Policy('SV4_BASKET_LIQ','basket',slots=4,exit_minute=970),
            Policy('SV4_BASKET_FREQ','basket',rank='gapfreq',slots=4,exit_minute=970),
            Policy('MIS_RETEST','pullback'),Policy('MIS_FADE','fade'),
            Policy('CNC_NIGHT','cnc_night'),Policy('CNC_WILDER','cnc_wilder')]
    else:
        ps=[Policy(**p) for p in json.loads((RUN/f'round{round_}-proposals.json').read_text())]
    return [asdict(p) for p in ps]


def freeze_path(round_,revision=1):
    return RUN/(f'round{round_}-freeze.json' if revision==1 else f'round{round_}-revision{revision}-freeze.json')


def freeze(round_,revision=1):
    target=freeze_path(round_,revision)
    if target.exists():raise ValueError('immutable round freeze exists')
    write(target,{'round':round_,'revision':revision,'sources':source_hashes(),'data':{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in inputs()},
        'policies':proposals(round_),'development':{'h1':['2026-01-01','2026-07-31'],'recent':['2026-08-10','2026-11-02']},
        'daily_panels':{'old':['2011-01-01','2018-12-31'],'middle':['2019-01-01','2022-12-31'],'recent':['2023-01-01','2026-10-09']},
        'daily_tails':{'old':'2019-01-31','middle':'2023-01-31','recent':'2026-11-03'},
        'models':[[0,0,None],[25,25,None],[50,50,None],[100,100,None],[25,25,20261104]],
        'capital':2000,'cnc_capital_sensitivity':25000,'cash':'profits withheld; actual-clock exits/carry; no leverage',
        'auction_clock':'09:10 clearing outcome conditional; fixed limit quantities, orders preselected strictly from prior bars; cancel unfilled before continuous',
        'daily_clock':'previous closed bars; next-open regular entry or prior postclose conditional night entry',
        'cross_name_opened':False,'verdict':'all old panels seen, no prospective qualification','frozen_at':datetime.now(timezone.utc).isoformat()})


def excluded_etfs():
    paths=[ROOT/'docs/research/penny/2026-11-04-overnight-v2/_local/yahoo-acquisition.json',RUN/'cross-name-acquisition.json']
    out={'NIFTYBEES','NIFTY 50'}
    registry=RUN/'nse-etf-identity.json'
    if registry.exists():out.update(json.loads(registry.read_text())['symbols'])
    for p in paths:
        if not p.exists():continue
        x=json.loads(p.read_text())
        records=x.get('receipts',[]) if isinstance(x,dict) else x
        for r in records:
            if r.get('instrument_type') in ('ETF','INDEX'):out.add(r.get('symbol'))
    return out-{None}


def seen_panel(panel):
    idata,_,_=legacy();path=idata.EXAM_DB if panel=='h1' else idata.DEV_DAILY
    start,end=('2026-01-01','2026-07-31') if panel=='h1' else ('2026-07-30','2026-11-02')
    days=idata.build(path,path,start,end,min_bars=1);daily=idata._daily(path)
    names={d.ticker for d in days};daily={t:x for t,x in daily.items() if t in names}
    from research_data_contracts import default_calendar
    cal=default_calendar();dates=[];date=datetime.fromisoformat(start).date();last=datetime.fromisoformat(end).date()
    while date<=last:
        if cal.is_trading_day(date):dates.append(date.isoformat())
        date+=timedelta(days=1)
    return days,daily,dates


def score(round_,revision=1):
    from dataclasses import asdict
    from smart_classic_enrichment import Policy,auction_orders,intraday_orders,cnc_orders,run_book
    f=json.loads(freeze_path(round_,revision).read_text());assert f['sources']==source_hashes()
    for p,h in f['data'].items():assert sha(ROOT/p)==h,p
    excluded=excluded_etfs();rows=[];write(RUN/f'excluded-etfs-r{round_}v{revision}.json',sorted(excluded))
    for panel,window in f['development'].items():
        days,daily,calendar=seen_panel(panel)
        controls=([Policy('CNC_NIGHT_CONTROL','cnc_night'),Policy('CNC_WILDER_CONTROL','cnc_wilder')] if round_>1 else [])
        ps=[Policy('SV3_CARRY_CONTROL','auction_ref',exit_minute=970),Policy('MIS_BREAKOUT_CONTROL','breakout'),
            *[Policy(**p) for p in f['policies'] if not p['family'].startswith('cnc_')]]
        for p in ps:
            orders,counts=auction_orders(days,daily,calendar,p,2000,excluded) if p.family in ('basket','auction_ref') else intraday_orders(days,p,excluded)
            orders=[o for o in orders if window[0]<=o.day<=window[1]]
            for eb,xb,seed in f['models']:
                # Auction executes at a clearing price; shocks may deny a
                # fixed limit but never resize it using that clearing price.
                r=run_book(orders,daily,calendar,bankroll=2000,entry_bps=eb,exit_bps=xb,
                    max_new_day=p.slots if p.family=='basket' else 1,max_positions=p.slots,fill_seed=seed)
                target=RUN/f'_local/results/r{round_}v{revision}_{panel}_{p.name}_{eb}_{xb}_{seed}.json'
                if target.exists():raise ValueError('result already exists')
                write(target,r|{'policy':asdict(p),'order_counts':counts,'model':[eb,xb,seed]})
                rows.append({'panel':panel,'policy':asdict(p),'model':[eb,xb,seed],'summary':r['summary'],'order_counts':counts})
                print(panel,p.name,eb,xb,seed,r['summary'],flush=True)
    _,_,o=legacy();raw=o.load_bars(reserved=None)
    daily={t:[(d,*bar) for d,bar in seq] for t,seq in raw.items()};all_calendar=sorted({d for seq in daily.values() for d,*_ in seq})
    ps=[Policy('CNC_LEGACY_DAILY_CONTROL','cnc_legacy',hold_days=15),*controls,*[Policy(**p) for p in f['policies'] if p['family'].startswith('cnc_')]]
    for panel,window in f['daily_panels'].items():
        tail=[d for d in all_calendar if window[0]<=d<=f['daily_tails'][panel]]
        # Tail sessions settle existing exposure only, never new entries.
        calendar=tail;orders_calendar=[d for d in calendar if window[0]<=d<=window[1]]
        for p in ps:
            orders,_=cnc_orders(daily,calendar,p,excluded);orders=[x for x in orders if window[0]<=x.day<=window[1]]
            for cash in [2000,25000]:
                for eb,xb,seed in f['models']:
                    r=run_book(orders,daily,calendar,bankroll=cash,entry_bps=eb,exit_bps=xb,fill_seed=seed)
                    target=RUN/f'_local/results/r{round_}v{revision}_daily-{panel}_{p.name}_{cash}_{eb}_{xb}_{seed}.json'
                    if target.exists():raise ValueError('result already exists')
                    write(target,r|{'policy':asdict(p),'capital':cash,'model':[eb,xb,seed]})
                    rows.append({'panel':'daily-'+panel,'capital':cash,'policy':asdict(p),'model':[eb,xb,seed],'summary':r['summary']})
                    print('daily',panel,p.name,cash,eb,xb,seed,r['summary'],flush=True)
    assert f['sources']==source_hashes()
    write(RUN/(f'round{round_}-results.json' if revision==1 else f'round{round_}-revision{revision}-results.json'),rows)


def baseline():
    idata,mo,_=legacy();days=idata.build(idata.EXAM_DB,idata.EXAM_DB,'2026-01-01','2026-07-31',min_bars=1)
    r=mo.simulate(days,mo.MPolicy('legacy',capacity='c915',skip_thin=True),start='2026-01-01',end='2026-07-31',bankroll=2000)
    expected=json.loads((OLD/'exam-results.json').read_text())['minute']['S1_THIN_close_c915']['summary']
    assert r['summary']==expected,(r['summary'],expected)
    write(RUN/'legacy-smart-parity.json',{'summary':r['summary'],'mismatches':0,'lock_outcomes':r['outcomes'],
        'not_a_new_exam':'previously seen; old script preserved; new corrected carry control is separate'})
    from research_data_contracts import load_daily_dataset,load_intraday_dataset
    from research_penny_cnc_lifecycle import PennyCncConfig,run_penny_cnc_lifecycle
    native=[]
    for panel,start,end,through in [('h1','2026-01-01','2026-07-15','2026-07-31'),('recent','2026-08-10','2026-10-15','2026-11-02')]:
        path=idata.EXAM_DB if panel=='h1' else idata.DEV_DAILY
        c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);names=[t for t, in c.execute('SELECT DISTINCT ticker FROM intraday_cache')];c.close()
        before=(datetime.fromisoformat(through)+timedelta(days=1)).date().isoformat()
        d=load_daily_dataset(str(path),tickers=names,before=before)
        tape=load_intraday_dataset(str(path),interval='minute',tickers=names,start=start,end=through)
        result=run_penny_cnc_lifecycle(tape,d,PennyCncConfig(tuple(names)),start=start,end=end,settle_through=through)
        write(RUN/f'_local/native-cnc-{panel}.json',result)
        native.append({'panel':panel,'summary':result.get('summary'),'funnel':result.get('funnel'),'rejections':result.get('rejections'),
            'status':result.get('status'),'limits':'native PENNY_PAPER bankroll100000/constant PR1; not operational historical regime or live CNC'})
        print('native CNC',panel,native[-1],flush=True)
    write(RUN/'native-cnc-baselines.json',native)


def native_mis():
    idata,_,_=legacy()
    from research_data_contracts import load_daily_dataset,load_intraday_dataset
    from penny_lifecycle_replay import PennyLifecycleConfig,run_penny_lifecycle
    out=[]
    for panel,start,end in [('h1','2026-01-01','2026-07-31'),('recent','2026-08-10','2026-11-02')]:
        path=idata.EXAM_DB if panel=='h1' else idata.DEV_DAILY
        c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);names=[t for t, in c.execute('SELECT DISTINCT ticker FROM intraday_cache')];c.close()
        daily=load_daily_dataset(str(path),tickers=names,before=(datetime.fromisoformat(end)+timedelta(days=1)).date().isoformat())
        tape=load_intraday_dataset(str(path),interval='minute',tickers=names,start=start,end=end)
        r=run_penny_lifecycle(tape,daily,PennyLifecycleConfig(tuple(names),bankroll=2000),start=start,end=end)
        write(RUN/f'_local/native-mis-{panel}.json',r)
        out.append({'panel':panel,'status':r.get('status'),'summary':r.get('summary'),'funnel':r.get('funnel'),
            'scope':'exact native MIS/2000 own cash/constant PR1/data completeness gates; not historic operational regime'})
        print(out[-1],flush=True)
    write(RUN/'native-mis-baselines.json',out)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['select','acquire','freeze','score','baseline','native_mis']);p.add_argument('--round',type=int);p.add_argument('--revision',type=int,default=1)
    a=p.parse_args()
    if a.command in ('freeze','score'):globals()[a.command](a.round,a.revision)
    else:globals()[a.command]()
