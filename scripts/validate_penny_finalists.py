"""Single declared daily validation, native-capital/stress controls and audits."""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict
from datetime import date,datetime,timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python-engine'))
from daily_portfolio import DailySignal,bars_by_ticker,calendar_from,penny_cnc_costs
from edge_portfolio_replay import EdgeReplayConfig,run_overnight_book,runtime_realism_refusal
from penny_strategy_research import financial_summary,accepts
from penny_edge_engine import rank_and_pick,scan_single_ticker_with_reason
from penny_edge_backtest import compute_nifty_regime
from event_calendar import event_block
from score_penny_strategy_search import inputs_daily,persist
from run_penny_strategy_search import atomic
from iterate_penny_strategy_search import NightGenome,night_features,run_night


def edge_cache(rows,start,end):
    histories=defaultdict(list)
    for t,d,o,h,l,c,v in sorted(rows):
        histories[t].append({'ticker':t,'date':d,'open':o,'high':h,'low':l,'close':c,'volume':v})
    cache=defaultdict(list)
    for t,history in histories.items():
        for i,b in enumerate(history):
            if not start<=b['date']<=end:continue
            if event_block(t,date.fromisoformat(b['date']))[0]:continue
            window=history[max(0,i-59):i+1]
            cache[b['date']].extend(scan_single_ticker_with_reason(window,len(window)-1)[0])
    nifty=histories['NIFTYBEES'];regimes={}
    for i,b in enumerate(nifty):
        if start<=b['date']<=end:regimes[b['date']]=compute_nifty_regime(nifty,i)
    return dict(cache),regimes


def edge_signals(cache,regimes,bars,day,equity):
    from edge_overnight_paper import RANK_DEPTH
    if day not in regimes:return []
    picks=rank_and_pick(cache.get(day,[]),regimes[day],equity,max_positions=RANK_DEPTH,min_strength=.45)
    out=[]
    for p in picks:
        b=bars[p.ticker][day]
        out.append(DailySignal(p.ticker,day,p.entry_price,p.stop_loss,p.target,p.shares,p.signal_subtype,
                   context={'signal_low':b['low'],'signal_mid':(b['open']+b['close'])/2,
                            'hold_days':p.hold_days,'adjusted_strength':round(p.adjusted_strength,6)}))
    return out


def cached_edge(rows,cache,regimes,*,start,end,bankroll,entry_slip,exit_slip):
    bars=bars_by_ticker(rows);calendar=calendar_from(bars,'NIFTYBEES',start)
    cfg=EdgeReplayConfig(tuple(sorted(set(bars)-{'NIFTYBEES'})),bankroll=bankroll,
                        policy='EDGE_OVERNIGHT_RUNTIME',slippage_bps=exit_slip,
                        overnight_entry_slippage_bps=entry_slip)
    result=run_overnight_book(bars,calendar,end=end,config=cfg,costs=penny_cnc_costs,
        signals_at_close=lambda d,e:edge_signals(cache,regimes,bars,d,e),
        refuse=runtime_realism_refusal(bars),split_cash=True)
    return {'scope':'PORTFOLIO_PROXY','metrics':financial_summary(result['trades'],result['equity_curve'],bankroll),**result}


def source_hashes():
    paths=[*sorted((ROOT/'python-engine').glob('*.py')),Path(__file__).resolve(),
           ROOT/'scripts/iterate_penny_strategy_search.py',ROOT/'scripts/score_penny_strategy_search.py',
           ROOT/'scripts/run_penny_strategy_search.py']
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def freeze(run):
    selected=json.loads((run/'genome-selection.json').read_text())
    parent=json.loads((run/'round3-freeze.json').read_text())
    f={'source':source_hashes(),'snapshot_sha256':parent['snapshot_sha256'],
       'finalists':selected['finalists'],'validation':['2024-01-01','2025-12-31'],
       'scenarios':[[100000,25,10],[100000,50,30],[100000,100,60],[25000,25,10],[2000,25,10]],
       'acceptance':parent['acceptance'],'selection_sha256':hashlib.sha256((run/'genome-selection.json').read_bytes()).hexdigest(),
       'frozen_at':datetime.now(timezone.utc).isoformat(),'qualification':False,
       'limitations':['108-stock no-split fixed cohort, survivorship','daily close entry and next-open sale proxies','no historical bid/ask/depth or dated full universe','historical periods previously used by other Sentinel studies; conditional validation only']}
    if (run/'final-freeze.json').exists():raise ValueError('final freeze exists')
    atomic(run/'final-freeze.json',f)


def audit_result(r,bankroll):
    trades=r['trades'];closed=[t for t in trades if t['status']=='CLOSED']
    for t in closed:
        assert abs(t['gross_pnl']-t['costs']-t['net_pnl'])<=.011
        assert t['costs']>=0
        assert t['shares']>=1
        assert t['exit_date']>t['entry_date'],'overnight exit must follow entry'
    metrics=r['metrics']
    assert abs(sum(t['net_pnl'] for t in closed)-metrics['net'])<.011
    if not metrics['unresolved']:
        assert abs(r['equity_curve'][-1][1]-bankroll-metrics['net'])<.011
    assert min(e for _,e in r['equity_curve'])>=-.011
    return {'closed_checked':len(closed),'cash_fee_identity':'PASS'}


def validate(run):
    f=json.loads((run/'final-freeze.json').read_text());assert f['source']==source_hashes()
    assert f['snapshot_sha256']==hashlib.sha256((run/'_local/research.sqlite').read_bytes()).hexdigest()
    rows,daily=inputs_daily(run,'2026-02-01');features=night_features(rows)
    cache,regimes=edge_cache(rows,*f['validation']);all_results=[]
    for bankroll,entry_slip,exit_slip in f['scenarios']:
        suffix=f'{bankroll}_entry{entry_slip}_exit{exit_slip}'
        baseline=persist(run,'validation_EDGE_'+suffix,lambda:cached_edge(rows,cache,regimes,start=f['validation'][0],end=f['validation'][1],bankroll=bankroll,entry_slip=entry_slip,exit_slip=exit_slip))
        audit_result(baseline,bankroll)
        for spec in f['finalists']:
            g=NightGenome(**spec)
            r=persist(run,'validation_'+g.name+'_'+suffix,lambda g=g:run_night(rows,features,g,start=f['validation'][0],end=f['validation'][1],bankroll=bankroll,entry_slip=entry_slip,slip=exit_slip))
            audit=audit_result(r,bankroll)
            all_results.append({'name':g.name,'bankroll':bankroll,'entry_slip':entry_slip,'exit_slip':exit_slip,
                                'metrics':r['metrics'],'baseline':baseline['metrics'],
                                'passes':accepts(r['metrics'],baseline['metrics'],bankroll), 'audit':audit})
    atomic(run/'validation-results.json',{'comparisons':all_results,'qualification':False})
    assert f['source']==source_hashes(),'post-score source drift'


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze','validate']);p.add_argument('--run',type=Path,required=True)
    a=p.parse_args();{'freeze':freeze,'validate':validate}[a.command](a.run.resolve())


if __name__=='__main__':main()
