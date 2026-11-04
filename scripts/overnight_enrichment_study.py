"""Acquire independent older cash data and run frozen Overnight enrichment rounds."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from dataclasses import asdict
from datetime import datetime,timezone,timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'python-engine'))
from overnight_enrichment import Policy,legacy_lab,risk_history,simulate
V2=ROOT/'docs/research/penny/2026-11-04-overnight-v2'


def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf-8');tmp.replace(path)


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def acquire(run):
    from backtest_all_yahoo import fetch_chart
    names=json.loads((V2/'universe-yahoo.json').read_text())['symbols']
    local=run/'_local/older';local.mkdir(parents=True,exist_ok=True);target=local/'yahoo.sqlite'
    if target.exists():raise ValueError('immutable acquisition exists')
    c=sqlite3.connect(target);c.execute('CREATE TABLE ohlcv_cache(ticker,date,open,high,low,close,volume,PRIMARY KEY(ticker,date))');receipts=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(fetch_chart,local,s,s+'.NS','1d','2010-01-01','2019-01-10'):s for s in names}
        for future in as_completed(futures):
            s=futures[future]
            try:
                rows,r=future.result();c.executemany('INSERT OR IGNORE INTO ohlcv_cache VALUES (?,?,?,?,?,?,?)',rows);c.commit()
            except Exception as e:r={'symbol':s,'state':'FAILED','reason':repr(e)}
            receipts.append(r)
            if len(receipts)%50==0:print('older acquisition',len(receipts),'/',len(names),flush=True)
    counts=c.execute('SELECT COUNT(*),COUNT(DISTINCT ticker),MIN(date),MAX(date) FROM ohlcv_cache').fetchone();c.close()
    write(run/'older-acquisition.json',{'requests':len(names),'breeze_calls':0,'broker_calls':0,
        'metadata_counts_only':counts,'database_sha256':sha(target),'receipts':receipts})


def sources():
    paths=[ROOT/'python-engine/overnight_enrichment.py',Path(__file__).resolve(),
           *[V2/n for n in ['lab.py','arms.py','round2.py','exam.py']],
           *[ROOT/'python-engine'/n for n in ['penny_edge_engine.py','penny_edge_backtest.py','penny_risk.py','config.py']]]
    return {p.relative_to(ROOT).as_posix():sha(p) for p in paths}


def freeze(run,round_):
    proposals=run/f'round{round_}-proposals.json';items=json.loads(proposals.read_text())
    f={'round':round_,'source':sources(),'policies':[asdict(Policy(**x)) for x in items],
       'development':{'yahoo':['2023-01-01','2026-10-30'],'kite':['2025-07-01','2026-09-30']},
       'data':{s:sha(V2/f'_local/days-{s}.pkl') for s in ['yahoo','kite']},
       'models':[[36,5,1.],[36,5,.75],[36,5,.5],[60,20,.75]],
       'cash':'fixed 25000; no reinvestment; losses reduce own capital',
       'old_history_check':['2015-01-01','2018-12-31'],'old_history_opened':False,
       'acceptance':'net/ex-best positive, >=100 closes, 10% more same-model net with <=1.5x DD OR 20% lower DD with >=95% net; no unresolved; conditional, not live qualification',
       'frozen_at':datetime.now(timezone.utc).isoformat()}
    p=run/f'round{round_}-freeze.json'
    if p.exists():raise ValueError('freeze exists')
    write(p,f)


def score(run,round_):
    f=json.loads((run/f'round{round_}-freeze.json').read_text());assert f['source']==sources()
    lab=legacy_lab()
    for panel,window in f['development'].items():
        path=V2/f'_local/days-{panel}.pkl';assert f['data'][panel]==sha(path)
        days=lab.load(path);hist=risk_history(days)
        policies=[Policy('V2_NATIVE'),*[Policy(**p) for p in f['policies']]]
        for rb,xb,pfill in f['models']:
            for p in policies:
                target=run/f'_local/results/r{round_}_{panel}_{p.name}_{rb}_{xb}_{pfill}.json'
                if target.exists():continue
                r=simulate(days,p,start=window[0],end=window[1],regular_bps=rb,exit_bps=xb,
                           winning_close_fill=pfill,histories=hist)
                write(target,r);print(panel,p.name,rb,xb,pfill,r['summary'],flush=True)
        del days,hist
    assert f['source']==sources(),'post-score source drift'


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['acquire','freeze','score']);p.add_argument('--round',type=int);p.add_argument('--run',type=Path,required=True)
    a=p.parse_args();run=a.run.resolve()
    if a.command=='acquire':acquire(run)
    elif a.command=='freeze':freeze(run,a.round)
    else:score(run,a.round)


if __name__=='__main__':main()
