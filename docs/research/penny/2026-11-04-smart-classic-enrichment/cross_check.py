"""One-opening cross-name check; dates already seen, not a chronological exam."""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import datetime,timedelta
from pathlib import Path
import argparse,json,math,sqlite3,sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'python-engine'));sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(HERE))
from smart_classic_study import (source_hashes,sha,write,excluded_etfs,legacy)
from smart_classic_enrichment import Policy,intraday_orders,run_book
from opening_exits import arms


def bound():
    return source_hashes()|{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in [Path(__file__).resolve(),HERE/'opening_exits.py']}


def freeze():
    p=HERE/'cross-name-freeze.json'
    if p.exists():raise ValueError('cross-name freeze exists')
    paths=[HERE/'_local/cross-name/bars.sqlite',HERE/'cross-name-selection.json',HERE/'cross-name-acquisition.json',
           HERE/'nse-etf-identity.json',ROOT/'docs/research/penny/2026-11-04-overnight-v2/_local/yahoo/yahoo.sqlite',
           ROOT/'docs/research/penny/2026-11-04-overnight-v2/_local/yahoo-split-cuts.json']
    write(p,{'sources':bound(),'data':{str(x.relative_to(ROOT)).replace('\\','/'):sha(x) for x in paths},
        'window':['2026-09-07','2026-11-03'],'capital':2000,'models':[[0,0,None],[25,25,None],[50,50,None],[100,100,None],[25,25,20261104]],
        'finalists':['SV3_MORNING_0930','SV3_GAP_TARGET_1000','MIS_AFTERNOON','MIS_AFTERNOON_RETEST'],
        'acceptance':'positive net/ex-best;>=30 closes;no open;>=10%more net OR20%less DD/95%net vs same-model control. Previously negative seen-panel arms cannot qualify from one lucky cross-name result.',
        'limits':['five-minute volume is not measured auction volume','same dates/new minute names,not a fresh chronological exam','current universe and current ETF/split identity restrictions','all fills remain proxies'],
        'cnc':'daily outcomes already seen; no fresh CNC check claimed','opened':False})


def load(f):
    idata,_,_=legacy();sel=json.loads((HERE/'cross-name-selection.json').read_text());names=set(sel['names'])
    daily_path=ROOT/'docs/research/penny/2026-11-04-overnight-v2/_local/yahoo/yahoo.sqlite'
    cuts=json.loads((daily_path.parents[1]/'yahoo-split-cuts.json').read_text())
    daily={t:[r for r in rows if r[0]>=cuts.get(t,'')] for t,rows in idata._daily(daily_path).items() if t in names}
    index={t:{r[0]:i for i,r in enumerate(rows)} for t,rows in daily.items()};mins=defaultdict(list);audit=Counter()
    path=HERE/'_local/cross-name/bars.sqlite';c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    for t,dt,o,h,l,cl,v in c.execute('SELECT ticker,datetime,open,high,low,close,volume FROM intraday_cache ORDER BY ticker,datetime'):
        audit['raw_rows']+=1
        if any(x is None or not math.isfinite(x) for x in (o,h,l,cl,v)) or min(o,h,l,cl)<=0 or v<0:
            audit['invalid_cells']+=1;continue
        if l>min(o,cl)*1.0000001 or h<max(o,cl)*.9999999:audit['inconsistent_ohlc']+=1;continue
        if dt[:10]<cuts.get(t,''):audit['pre_last_split']+=1;continue
        m=int(dt[11:13])*60+int(dt[14:16]);mins[(t,dt[:10])].append((m,o,h,l,cl,v))
    c.close();days=[]
    for (t,d),bars in sorted(mins.items(),key=lambda x:(x[0][1],x[0][0])):
        i=index.get(t,{}).get(d)
        if i is None or i<20:audit['no_daily_warmup_stockdays']+=1;continue
        rows=daily[t];prior=rows[max(0,i-60):i];vols=sorted(x[5] for x in prior[-20:]);vals=sorted(x[4]*x[5] for x in prior[-20:]);nxt=rows[i+1] if i+1<len(rows) else None
        med=lambda x:(x[len(x)//2]+x[(len(x)-1)//2])/2
        days.append(idata.Day(t,d,bars,rows[i-1][4],med(vols),med(vals),prior,
            nxt[1] if nxt else None,nxt[0] if nxt else None,rows[i][1],rows[i][4],rows[i][3],nxt[3] if nxt else None,nxt[4] if nxt else None))
    from research_data_contracts import default_calendar
    cal=default_calendar();d=datetime.fromisoformat(f['window'][0]).date();last=datetime.fromisoformat(f['window'][1]).date();calendar=[]
    while d<=last:
        if cal.is_trading_day(d):calendar.append(d.isoformat())
        d+=timedelta(days=1)
    audit.update({'stockdays':len(days),'retained_names':len({d.ticker for d in days}),'calendar_sessions':len(calendar),
        'observed_trading_rows':sum(sum(b[5]>0 for b in d.bars) for d in days)})
    write(HERE/'cross-name-data-audit.json',dict(audit));return days,daily,calendar


def score():
    f=json.loads((HERE/'cross-name-freeze.json').read_text());assert f['sources']==bound()
    for path,h in f['data'].items():assert sha(ROOT/path)==h,path
    with (HERE/'CROSS_NAME_OPENED.json').open('x') as h:json.dump({'freeze_sha256':sha(HERE/'cross-name-freeze.json'),'at':datetime.now().isoformat()},h)
    days,daily,calendar=load(f);excluded=excluded_etfs();sets,counts=arms(days,daily,calendar,excluded)
    for p in [Policy('MIS_BREAKOUT_CONTROL','breakout'),Policy('MIS_AFTERNOON','breakout',afternoon=True),Policy('MIS_AFTERNOON_RETEST','pullback',afternoon=True)]:
        sets[p.name],_=intraday_orders(days,p,excluded)
    results=[]
    for name,orders in sets.items():
        for eb,xb,seed in f['models']:
            r=run_book(orders,daily,calendar,entry_bps=eb,exit_bps=xb,fill_seed=seed)
            write(HERE/f'_local/results/cross_{name}_{eb}_{xb}_{seed}.json',r|{'name':name,'model':[eb,xb,seed]})
            results.append({'name':name,'model':[eb,xb,seed],'summary':r['summary']})
            print(name,eb,xb,seed,r['summary'],flush=True)
    assert f['sources']==bound()
    for path,h in f['data'].items():assert sha(ROOT/path)==h,path
    write(HERE/'cross-name-results.json',results)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze','score']);a=p.parse_args();globals()[a.command]()
