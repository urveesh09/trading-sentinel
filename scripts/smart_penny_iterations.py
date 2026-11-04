"""Bounded Smart Penny setup/management rounds and one frozen validation pass."""
import argparse
from dataclasses import asdict,replace
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python-engine'))
from penny_smart_policy import SMART_PARAMS
from penny_smart_v2 import SMART_V2_PARAMS
from penny_strategy_research import run_smart,accepts
from run_penny_strategy_search import atomic,load_inputs
from score_penny_strategy_search import persist


def sources():
    paths=[*sorted((ROOT/'python-engine').glob('*.py')),Path(__file__).resolve(),
           ROOT/'scripts/run_penny_strategy_search.py',ROOT/'scripts/score_penny_strategy_search.py']
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def freeze(run,round_):
    if round_==2:
        common=replace(SMART_V2_PARAMS,min_pace_rvol=1.8,min_surge=1.5,require_vwap=True)
        candidates=[replace(common,policy_version='S2_RETEST',fast_entry_score=1.1,max_chase_atr=.5,
                            failed_breakout_closes=4,stall_minutes=60,trail_start_r=2.),
                    replace(common,policy_version='S2_DAY_HIGH',anchor_mode='day_high',
                            min_surge=2.,failed_breakout_closes=4,stall_minutes=60)]
    elif round_==3:
        prior=json.loads((run/'smart-round2-freeze.json').read_text())['candidates']
        scored=[(json.loads((run/'_local/results'/('train_'+p['policy_version']+'.json')).read_text())['summary']['ex_best'],p) for p in prior]
        parent=max(scored,key=lambda x:x[0])[1]
        common=replace(SMART_V2_PARAMS,**parent)
        candidates=[replace(common,policy_version='S3_WINNER_ROOM',failed_breakout_closes=6,
                            stall_minutes=75,trail_start_r=2.,trail_atr_mult=3.),
                    replace(common,policy_version='S3_CLEAN_RETEST',fast_entry_score=1.1,
                            max_closes_inside_base=3,retest_atr=.35,min_pace_rvol=1.5,
                            min_surge=1.5,noise_atr_mult=2.,min_noise_pct=.015)]
    else:raise ValueError(round_)
    parent=json.loads((run/'round1-freeze.json').read_text())
    f={'source':sources(),'snapshot_sha256':parent['snapshot_sha256'],'round':round_,
       'candidates':[asdict(p) for p in candidates],'training':parent['intraday_training'],
       'validation':parent['intraday_validation'],'symbols':parent['intraday_symbols'],
       'bankroll':2000,'spread_bps':10,'reason':'R1 participation improves gross but costs/thesis failures still dominate. R2 waits for a retest or day-high structure; R3 tests winner room and cleaner structural retest on the better R2 entry.',
       'validation_status':'conditional partial-bar research, not untouched qualification',
       'frozen_at':datetime.now(timezone.utc).isoformat()}
    p=run/f'smart-round{round_}-freeze.json'
    if p.exists():raise ValueError('freeze exists')
    atomic(p,f)


def run_round(run,round_):
    f=json.loads((run/f'smart-round{round_}-freeze.json').read_text())
    assert f['source']==sources()
    assert f['snapshot_sha256']==hashlib.sha256((run/'_local/research.sqlite').read_bytes()).hexdigest()
    _,daily,tape=load_inputs(run,*f['training'])
    for spec in f['candidates']:
        p=replace(SMART_V2_PARAMS,**spec)
        persist(run,'train_'+p.policy_version,lambda p=p:run_smart(tape,daily,f['symbols'],start=f['training'][0],end=f['training'][1],params=p))


def freeze_final(run):
    base=json.loads((run/'round1-freeze.json').read_text());trials=[]
    for path in sorted((run/'_local/results').glob('train_S*.json')):
        r=json.loads(path.read_text())
        if 'params' in r:trials.append({'policy':r['params'],'training':r['summary']})
    trials.sort(key=lambda r:(-r['training']['ex_best'],r['policy']['policy_version']))
    f={'source':sources(),'snapshot_sha256':base['snapshot_sha256'],'finalists':[r['policy'] for r in trials[:2]],
       'all_training_trials':trials,'selection':'highest training net without best trade; no validation outcomes used',
       'validation':base['intraday_validation'],'symbols':base['intraday_symbols'],'bankroll':2000,
       'stress_spread_bps':[10,30,60],'acceptance':base['acceptance'],
       'status':'conditional research only; all days have known data limitations'}
    if (run/'smart-final-freeze.json').exists():raise ValueError('final freeze exists')
    atomic(run/'smart-final-freeze.json',f)


def validate(run):
    f=json.loads((run/'smart-final-freeze.json').read_text());assert f['source']==sources()
    assert f['snapshot_sha256']==hashlib.sha256((run/'_local/research.sqlite').read_bytes()).hexdigest()
    _,daily,tape=load_inputs(run,*f['validation']);results={}
    for spread in f['stress_spread_bps']:
        for p in [SMART_PARAMS,SMART_V2_PARAMS,*[replace(SMART_V2_PARAMS,**x) for x in f['finalists']]]:
            result=persist(run,f'validation_{p.policy_version}_spread{spread}',lambda p=p,s=spread:run_smart(tape,daily,f['symbols'],start=f['validation'][0],end=f['validation'][1],params=p,spread_bps=s))
            results[(p.policy_version,spread)]=result['summary']
    verdict=[]
    for p in f['finalists']:
        name=p['policy_version'];m=results[name,10];baseline=results[SMART_V2_PARAMS.policy_version,10]
        verdict.append({'name':name,'primary':m,'passes':accepts(m,baseline,2000),
                        'stress':{str(s):results[name,s] for s in f['stress_spread_bps']}})
    atomic(run/'smart-validation.json',{'baseline_v1':results[SMART_PARAMS.policy_version,10],
                                      'baseline_v2':results[SMART_V2_PARAMS.policy_version,10],
                                      'candidates':verdict,'qualification':False})


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze','run','freeze-final','validate']);p.add_argument('--round',type=int,choices=[2,3]);p.add_argument('--run',type=Path,required=True)
    a=p.parse_args();run=a.run.resolve()
    if a.command=='freeze':freeze(run,a.round)
    elif a.command=='run':run_round(run,a.round)
    elif a.command=='freeze-final':freeze_final(run)
    else:validate(run)


if __name__=='__main__':main()
