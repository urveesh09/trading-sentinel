"""Frozen later Penny rounds; training-only night persistence and finite genomes."""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
from statistics import mean, median, pstdev
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python-engine'))
from daily_portfolio import DailySignal,bars_by_ticker,calendar_from,penny_cnc_costs
from edge_portfolio_replay import EdgeReplayConfig,run_overnight_book,runtime_realism_refusal
from penny_strategy_research import financial_summary,run_smart,accepts
from penny_smart_v2 import SMART_V2_PARAMS
from run_penny_strategy_search import atomic,load_inputs
from score_penny_strategy_search import inputs_daily,persist


@dataclass(frozen=True)
class NightGenome:
    name: str
    lookback: int=20
    day_fade_weight: float=0.0
    momentum_weight: float=0.0
    slots: int=3
    min_edge: float=0.0
    risk_tilt: float=0.0
    use_shipped_candidates: bool=False
    strength_weight: float=0.8


def night_features(rows):
    """Every return ends on or before the decision close; no D+1 labels."""
    grouped=defaultdict(list)
    for t,d,o,h,l,c,v in rows:
        grouped[t].append({'ticker':t,'date':d,'open':o,'high':h,'low':l,'close':c,'volume':v})
    out=defaultdict(list)
    for t,history in grouped.items():
        history.sort(key=lambda b:b['date'])
        if t=='NIFTYBEES':continue
        for i in range(60,len(history)):
            b=history[i];prior=history[i-20:i]
            if not 1<=b['close']<=55 or b['volume']<=0:continue
            if median([x['close']*x['volume'] for x in prior])<500000:continue
            if any(abs(history[j]['close']/history[j-1]['close']-1)>.4 for j in range(i-60,i+1) if j>0):continue
            nights=[max(-.05,min(.05,history[j]['open']/history[j-1]['close']-1)) for j in range(i-59,i+1)]
            days=[max(-.05,min(.05,history[j]['close']/history[j]['open']-1)) for j in range(i-59,i+1)]
            out[b['date']].append({**b,'nights':nights,'days':days,'momentum':b['close']/history[i-20]['close']-1})
    return dict(out)


def night_signals(features,day,equity,g,shipped=None,bars=None):
    if g.use_shipped_candidates:
        from penny_edge_engine import rank_and_pick
        from edge_overnight_paper import RANK_DEPTH
        cache,regimes=shipped
        if day not in regimes:return []
        picks=rank_and_pick(cache.get(day,[]),regimes[day],equity,max_positions=RANK_DEPTH,min_strength=.45)
        lookup={f['ticker']:f for f in features.get(day,())};ranked=[]
        for p in picks:
            f=lookup.get(p.ticker)
            if f:
                n=f['nights'][-g.lookback:];d=f['days'][-g.lookback:]
                edge=mean(n)*len(n)/(len(n)+20)
                pressure=(edge-g.day_fade_weight*mean(d)+g.momentum_weight*max(-.1,min(.1,f['momentum'])))/max(pstdev(n),.005)**g.risk_tilt
            else:edge,pressure=0.,0.
            if edge<g.min_edge:continue
            score=g.strength_weight*p.adjusted_strength+(1-g.strength_weight)*max(0,min(1,.5+10*pressure))
            ranked.append((score,p))
        return [DailySignal(p.ticker,day,p.entry_price,p.stop_loss,p.target,p.shares,p.signal_subtype,
                            context={'score':score,'genome':asdict(g)})
                for score,p in sorted(ranked,key=lambda x:(-x[0],x[1].ticker))]
    ranked=[]
    for f in features.get(day,()):
        n=f['nights'][-g.lookback:];d=f['days'][-g.lookback:]
        edge=mean(n)*len(n)/(len(n)+20)
        if edge<g.min_edge:continue
        score=(edge-g.day_fade_weight*mean(d)+g.momentum_weight*max(-.1,min(.1,f['momentum'])))/max(pstdev(n),.005)**g.risk_tilt
        ranked.append((score,f))
    out=[]
    for score,f in sorted(ranked,key=lambda x:(-x[0],x[1]['ticker'])):
        q=int(equity/g.slots/f['close'])
        if q<1:continue
        # The required geometry is an admission reference only. There is no
        # executable overnight stop; the whole funded position can gap.
        out.append(DailySignal(f['ticker'],day,f['close'],f['close']*.85,None,q,
                               'NIGHT_PERSISTENCE',context={'score':score,'genome':asdict(g)}))
    return out


def run_night(rows,features,g,*,start,end,bankroll=100000,slip=10,entry_slip=25,shipped=None):
    bars=bars_by_ticker(rows);calendar=calendar_from(bars,'NIFTYBEES',start)
    if g.use_shipped_candidates and shipped is None:
        from validate_penny_finalists import edge_cache
        shipped=edge_cache(rows,start,end)
    cfg=EdgeReplayConfig(tuple(sorted(set(bars)-{'NIFTYBEES'})),bankroll=bankroll,
                        max_positions=g.slots,policy='EDGE_OVERNIGHT_RUNTIME',
                        slippage_bps=slip,overnight_entry_slippage_bps=entry_slip)
    result=run_overnight_book(bars,calendar,end=end,config=cfg,costs=penny_cnc_costs,
        signals_at_close=lambda d,e:night_signals(features,d,e,g,shipped=shipped,bars=bars),
        refuse=runtime_realism_refusal(bars),split_cash=True)
    return {'scope':'PORTFOLIO_PROXY','genome':asdict(g),'entry_slip_bps':entry_slip,
            'exit_slip_bps':slip,'metrics':financial_summary(result['trades'],result['equity_curve'],bankroll),**result}


def sources():
    paths=[*sorted((ROOT/'python-engine').glob('*.py')),Path(__file__).resolve(),
           ROOT/'scripts/score_penny_strategy_search.py',ROOT/'scripts/run_penny_strategy_search.py']
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def freeze(run,round_):
    base=json.loads((run/'round1-freeze.json').read_text())
    f={'round':round_,'source':sources(),'snapshot_sha256':base['snapshot_sha256'],
       'frozen_at':datetime.now(timezone.utc).isoformat(),'validation':base['daily_validation'],
       'reason':'R1 daytime families lose; R2 standalone night ranking trails the shipped overnight book. R3 retains shipped candidate generation/sizing and breeds only causal night-pressure re-ranking and concentration alleles; R2 controls retained.',
       'round2':[asdict(NightGenome('N2_PERSISTENT')),asdict(NightGenome('N2_PRESSURE',day_fade_weight=.5,risk_tilt=.5))],
       'gene_pool':{'lookback':[10,20,60],'day_fade_weight':[0.,.5,1.],
                    'momentum_weight':[0.,.05,.1],'slots':[2,3],
                    'min_edge':[-1.,0.,.001],'risk_tilt':[0.,.5],
                    'use_shipped_candidates':[True],'strength_weight':[.5,.8,1.]},
       'seed':20261104,'trial_cap':12,'selection':'choose two by worst of train annualised net and 2023 calibration net divided by max drawdown; train must have positive ex-best and >=100 closes; retain all failures',
       'acceptance':base['acceptance'],'stress':base['stress'],
       'no_genuine_unseen_claim':True,'reserved_exam_unscored':True}
    path=run/f'round{round_}-freeze.json'
    if path.exists():raise ValueError('round freeze exists')
    atomic(path,f)


def verify(run,round_):
    f=json.loads((run/f'round{round_}-freeze.json').read_text())
    assert f['source']==sources(),'source drift'
    assert f['snapshot_sha256']==hashlib.sha256((run/'_local/research.sqlite').read_bytes()).hexdigest(),'data drift'
    return f


def run_round(run,round_):
    f=verify(run,round_)
    rows,daily=inputs_daily(run,'2024-02-01');features=night_features(rows)
    if round_==2:
        for spec in f['round2']:
            g=NightGenome(**spec)
            persist(run,'train_'+g.name,lambda g=g:run_night(rows,features,g,start='2019-01-01',end='2022-12-30'))
        return
    if round_!=3:raise ValueError('round must be 2 or 3')
    rng=random.Random(f['seed']);genomes=[NightGenome(**d) for d in f['round2']]
    while len(genomes)<f['trial_cap']:
        genes={k:rng.choice(v) for k,v in f['gene_pool'].items()}
        g=NightGenome(f'N3_G{len(genomes):02}',**genes)
        if any({k:v for k,v in asdict(x).items() if k!='name'}==genes for x in genomes):continue
        genomes.append(g)
    atomic(run/'genome-population.json',[asdict(g) for g in genomes])
    scored=[]
    from validate_penny_finalists import edge_cache
    shipped=edge_cache(rows,'2019-01-01','2023-12-29')
    for g in genomes:
        a=persist(run,'genome_train_'+g.name,lambda g=g:run_night(rows,features,g,start='2019-01-01',end='2022-12-30',shipped=shipped))
        b=persist(run,'genome_calibration_'+g.name,lambda g=g:run_night(rows,features,g,start='2023-01-01',end='2023-12-29',shipped=shipped))
        am,bm=a['metrics'],b['metrics']
        eligible=am['ex_best']>0 and am['closed']>=100 and am['unresolved']==0 and bm['unresolved']==0
        fitness=min(am['net']/4,bm['net'])/max(am['drawdown'],bm['drawdown'],2500)
        scored.append({'genome':asdict(g),'train':am,'calibration':bm,'fitness':fitness,'eligible':eligible})
    scored.sort(key=lambda x:(not x['eligible'],-x['fitness'],x['genome']['name']))
    atomic(run/'genome-selection.json',{'all_trials':scored,'finalists':[x['genome'] for x in scored[:2]],'validation_opened':False})


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze','run']);p.add_argument('--round',type=int,choices=[2,3],required=True);p.add_argument('--run',type=Path,required=True)
    a=p.parse_args();run=a.run.resolve()
    {'freeze':freeze,'run':run_round}[a.command](run,a.round)


if __name__=='__main__':main()
