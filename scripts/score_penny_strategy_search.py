"""Offline bounded Penny rounds. Freeze this runner before any scoring."""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import redirect_stdout
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python-engine'))
from run_penny_strategy_search import atomic, load_inputs
from penny_strategy_research import (DailyGenome, accepts, daily_features, financial_summary,
                                    run_classic, run_daily, run_smart)
from penny_smart_policy import SMART_PARAMS
from penny_smart_v2 import SMART_V2_PARAMS


def bound_sources():
    paths=[*sorted((ROOT/'python-engine').glob('*.py')),
           ROOT/'scripts/run_penny_strategy_search.py',Path(__file__).resolve()]
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def verify(run):
    f=json.loads((run/'round1-freeze.json').read_text())
    if f['source']!=bound_sources(): raise ValueError('source drift: create explicit new freeze, never rescore silently')
    if f['snapshot_sha256']!=hashlib.sha256((run/'_local/research.sqlite').read_bytes()).hexdigest(): raise ValueError('data drift')
    return f


def freeze(run):
    f=json.loads((run/'freeze.json').read_text())
    f.update(source=bound_sources(),frozen_at=datetime.now(timezone.utc).isoformat(),
             daily_round1=[asdict(DailyGenome('D1_PULLBACK')),asdict(DailyGenome('D1_FLUSH',family='FLUSH'))],
             smart_round1={'S1_PARTICIPATION':asdict(replace(SMART_V2_PARAMS,policy_version='S1_PARTICIPATION',min_pace_rvol=1.8,min_surge=1.5,require_vwap=True)),
                           'S1_PATIENT':asdict(replace(SMART_V2_PARAMS,policy_version='S1_PATIENT',failed_breakout_closes=4,stall_minutes=60,trail_start_r=2.0))},
             note='preliminary freeze retained; complete runner and causal classic-gap correction bound before first score')
    if (run/'round1-freeze.json').exists():raise ValueError('freeze exists')
    atomic(run/'round1-freeze.json',f)


def inputs_daily(run,before):
    from research_data_contracts import load_daily_dataset
    f=json.loads((run/'freeze.json').read_text())
    daily=load_daily_dataset(run/'_local/research.sqlite',tickers=[*f['all_symbols'],'NIFTYBEES'],before=before)
    rows=[(t,b.day.isoformat(),b.open,b.high,b.low,b.close,b.volume) for t,bs in daily.bars.items() for b in bs]
    if not any(t=='NIFTYBEES' for t,*_ in rows):raise ValueError('benchmark unavailable')
    return rows,daily


def persist(run,name,func):
    path=run/'_local'/'results'/f'{name}.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():return json.loads(path.read_text())
    started=time.monotonic()
    with (path.parent/f'{name}.log').open('w',encoding='utf-8') as log,redirect_stdout(log):
        result=func()
    result['elapsed_seconds']=round(time.monotonic()-started,3)
    atomic(path,result)
    print(name,result.get('metrics',result.get('summary')),f"{result['elapsed_seconds']}s",flush=True)
    return result


def round1(run, family):
    f=verify(run)
    if family=='smart':
        _,daily,tape=load_inputs(run,*f['intraday_training'])
        kwargs=dict(start=f['intraday_training'][0],end=f['intraday_training'][1],bankroll=2000)
        names=f['intraday_symbols']
        persist(run,'train_classic_current',lambda:run_classic(tape,daily,names,**kwargs))
        for name,p in [('SMART_V1',SMART_PARAMS),('SMART_V2',SMART_V2_PARAMS),
                        *[(n,replace(SMART_V2_PARAMS,**{k:v for k,v in d.items() if k in SMART_V2_PARAMS.__dataclass_fields__})) for n,d in f['smart_round1'].items()]]:
            persist(run,'train_'+name,lambda p=p:run_smart(tape,daily,names,params=p,**kwargs))
    elif family=='daily':
        rows,daily=inputs_daily(run,'2023-02-01')
        features=daily_features(rows)
        atomic(run/'daily-training-data.json',{'invalid':daily.invalid,'manifest':daily.manifest,'features':sum(map(len,features.values()))})
        for g in map(lambda d:DailyGenome(**d),f['daily_round1']):
            persist(run,'train_'+g.name,lambda g=g:run_daily(rows,features,g,start=f['daily_training'][0],end=f['daily_training'][1]))
        from edge_portfolio_replay import EdgeReplayConfig,run_edge_portfolio
        available=tuple(sorted({r[0] for r in rows}-{'NIFTYBEES'}))
        for policy,bankroll in [('BASELINE',100000),('EDGE_OVERNIGHT_RUNTIME',100000)]:
            persist(run,'train_EDGE_'+policy,lambda p=policy,b=bankroll:run_edge_portfolio(rows,start=f['daily_training'][0],end=f['daily_training'][1],
                config=EdgeReplayConfig(available,bankroll=b,policy=p,slippage_bps=10)))
    else:raise ValueError(family)


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze','round1']);p.add_argument('--family',choices=['smart','daily'],default='smart');p.add_argument('--run',type=Path,required=True)
    a=p.parse_args();run=a.run.resolve()
    if a.command=='freeze':freeze(run)
    else:round1(run,a.family)


if __name__=='__main__': main()
