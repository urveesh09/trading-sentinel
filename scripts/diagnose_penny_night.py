"""Fixed non-selection diagnostics after the frozen daily validation."""
import argparse
from collections import defaultdict
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python-engine'))
from iterate_penny_strategy_search import NightGenome,night_features,night_signals,run_night
from validate_penny_finalists import edge_cache,audit_result
from score_penny_strategy_search import inputs_daily,persist
from run_penny_strategy_search import atomic


def freeze(run):
    f=json.loads((run/'final-freeze.json').read_text());g=next(x for x in f['finalists'] if x['name']=='N3_G05')
    atomic(run/'diagnostic-freeze.json',{'selected_candidate':g,'source':f['source'],
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope':'post-validation attribution/robustness only; no new finalist or promotion selected',
        'controls':['two slots without overnight-mean screen','three slots with overnight-mean screen'],
        'native_stress':[[25000,50,30],[25000,100,60]],'prefix_checks':20,
        'bootstrap':{'seed':20261104,'samples':2000,'block_sessions':20,'statistic':'descriptive realised exit-day PnL difference; not a new simulation or confidence of future profit'}})


def run_diagnostics(run):
    f=json.loads((run/'diagnostic-freeze.json').read_text())
    assert f['script_sha256']==hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    rows,_=inputs_daily(run,'2026-02-01');features=night_features(rows)
    shipped=edge_cache(rows,'2024-01-01','2025-12-31');g=NightGenome(**f['selected_candidate']);results=[]
    for c in [replace(g,name='SLOTS_ONLY_CONTROL',min_edge=-1.),replace(g,name='EDGE60_ONLY_CONTROL',slots=3)]:
        r=persist(run,'diagnostic_'+c.name,lambda c=c:run_night(rows,features,c,start='2024-01-01',end='2025-12-31',bankroll=25000,shipped=shipped))
        audit_result(r,25000);results.append({'name':c.name,'metrics':r['metrics']})
    from validate_penny_finalists import cached_edge
    for capital,entry,exit_ in f['native_stress']:
        baseline=persist(run,f'diagnostic_EDGE_25000_{entry}_{exit_}',lambda:cached_edge(rows,*shipped,start='2024-01-01',end='2025-12-31',bankroll=capital,entry_slip=entry,exit_slip=exit_))
        r=persist(run,f'diagnostic_G05_25000_{entry}_{exit_}',lambda:run_night(rows,features,g,start='2024-01-01',end='2025-12-31',bankroll=capital,entry_slip=entry,slip=exit_,shipped=shipped))
        results.append({'name':f'stress_{entry}_{exit_}','metrics':r['metrics'],'baseline':baseline['metrics']})
    days=sorted(d for d in features if '2024-01-01'<=d<='2025-12-31')
    rng=random.Random(20261104);chosen=sorted(rng.sample(days,min(f['prefix_checks'],len(days))))
    for day in chosen:
        prefix=[row for row in rows if row[1]<=day]
        prefix_features=night_features(prefix)
        prefix_shipped=edge_cache(prefix,day,day)
        actual=night_signals(features,day,25000,g,shipped=shipped)
        truncated=night_signals(prefix_features,day,25000,g,shipped=prefix_shipped)
        assert actual==truncated,day
    a=json.loads((run/'_local/results/validation_N3_G05_25000_entry25_exit10.json').read_text())
    b=json.loads((run/'_local/results/validation_EDGE_25000_entry25_exit10.json').read_text())
    flows=defaultdict(float)
    for sign,r in [(1,a),(-1,b)]:
        for t in r['trades']:
            if t['status']=='CLOSED':flows[t['exit_date']]+=sign*t['net_pnl']
    calendar=sorted(set(d for d,_ in a['equity_curve'])|set(d for d,_ in b['equity_curve']))
    delta=[flows[d] for d in calendar];samples=[];n=len(delta);block=20
    for _ in range(2000):
        draw=[]
        while len(draw)<n:
            i=rng.randrange(n);draw.extend(delta[(i+j)%n] for j in range(block))
        samples.append(sum(draw[:n]))
    samples.sort()
    out={'controls':results,'causal_prefix_checks':len(chosen),
         'native_net_delta':sum(delta),'descriptive_block_interval_95':[samples[49],samples[1949]],
         'qualification':False,'control_results_do_not_select_a_new_strategy':True}
    atomic(run/'diagnostic-results.json',out)


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze','run']);p.add_argument('--run',type=Path,required=True)
    a=p.parse_args();{'freeze':freeze,'run':run_diagnostics}[a.command](a.run.resolve())


if __name__=='__main__':main()
