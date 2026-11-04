"""Frozen exit-only Smart V3 extension; no new selection or order API."""
from __future__ import annotations
from collections import defaultdict
from dataclasses import asdict,replace
from pathlib import Path
import argparse
import json
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'python-engine'));sys.path.insert(0,str(ROOT/'scripts'))
from smart_classic_enrichment import Policy,auction_orders,bar5,run_book
from smart_classic_study import source_hashes,inputs,sha,write,seen_panel,excluded_etfs


def pending_sale(days_by_t,t,day):
    for later in days_by_t[t]:
        if later.date<=day:continue
        if later.day_low and later.day_open<=later.day_low*1.0001 and later.day_close<=later.day_low*1.0001:continue
        b=next((b for b in bar5(later) if b[5]>0 and b[2]>b[3]),None)
        if b:return (later.date,b[0],b[1],'MORNING_EXIT_CARRY_FIRST_OBSERVED_BAR')
    return None


def morning_exit(o,d,*,target=False):
    deadline=600 if target else 570
    level=d.prev_close*.995
    for m,op,hi,lo,cl,v in bar5(d):
        if v<=0 or (hi==lo and op<o.entry):continue
        if m>=deadline:return (d.date,m,op,'MORNING_TIMED_FIRST_TRADE')
        if target:
            if op>=level:return (d.date,m,op,'GAP_TARGET_AT_BAR_OPEN')
            if hi>level*1.0001:return (d.date,m+5,level,'GAP_TARGET_CROSSED_PROXY')
    return None


def arms(days,daily,calendar,excluded):
    control=Policy('SV3_CARRY_CONTROL','auction_ref',exit_minute=970)
    orders,counts=auction_orders(days,daily,calendar,control,2000,excluded)
    by={(d.ticker,d.date):d for d in days};seq=defaultdict(list)
    for d in sorted(days,key=lambda x:(x.ticker,x.date)):seq[d.ticker].append(d)
    out={'SV3_CARRY_CONTROL':orders}
    for name,target in [('SV3_MORNING_0930',False),('SV3_GAP_TARGET_1000',True)]:
        out[name]=[]
        for o in orders:
            outcome=morning_exit(o,by[(o.ticker,o.day)],target=target)
            if outcome is None:outcome=pending_sale(seq,o.ticker,o.day)
            out[name].append(replace(o,outcome=outcome))
    return out,counts


def bound():return source_hashes()|{str(Path(__file__).resolve().relative_to(ROOT)).replace('\\','/'):sha(Path(__file__).resolve())}


def freeze():
    target=HERE/'smart-exit-freeze.json'
    if target.exists():raise ValueError('exit freeze exists')
    write(target,{'sources':bound(),'data':{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in inputs()},
        'arms':['SV3_MORNING_0930','SV3_GAP_TARGET_1000'],'entry':'identical V3 final-auction reference pool, cash/volume proxy, ETF exclusion; no claim of pre-auction selection',
        'exits':['first positive-volume/non-flat-down bar from09:30','resting prevclose*0.995 crossed before10:00, else first tradable bar from10:00'],
        'models':[[0,0,None],[25,25,None],[50,50,None],[100,100,None],[25,25,20261104]],
        'cash':2000,'cross_name_opened':False,'acceptance':'positive/ex-best,30+ closes,no open; >=10% net improvement OR20% lower DD with95% net retained on both seen panels; cross-name check separate, not chronology'})


def score():
    f=json.loads((HERE/'smart-exit-freeze.json').read_text());assert f['sources']==bound()
    for path,h in f['data'].items():assert sha(ROOT/path)==h,path
    rows=[];excluded=excluded_etfs()
    for panel in ['h1','recent']:
        days,daily,calendar=seen_panel(panel);sets,counts=arms(days,daily,calendar,excluded)
        for name,orders in sets.items():
            orders=[o for o in orders if o.day>=('2026-01-01' if panel=='h1' else '2026-08-10')]
            for eb,xb,seed in f['models']:
                path=HERE/f'_local/results/smart3_{panel}_{name}_{eb}_{xb}_{seed}.json'
                if path.exists():raise ValueError('result exists')
                r=run_book(orders,daily,calendar,entry_bps=eb,exit_bps=xb,fill_seed=seed)
                write(path,r|{'name':name,'model':[eb,xb,seed],'order_counts':counts})
                rows.append({'panel':panel,'name':name,'model':[eb,xb,seed],'summary':r['summary']})
                print(panel,name,eb,xb,seed,r['summary'],flush=True)
    assert f['sources']==bound();write(HERE/'smart-exit-results.json',rows)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze','score']);a=p.parse_args();globals()[a.command]()
