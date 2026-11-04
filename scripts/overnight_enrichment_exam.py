"""One-opening older-history check of already-frozen enrichment finalists.

This is a backwards historical check on a surviving universe, not prospective
qualification. No orders, broker connections or runtime state are accessed.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
import json
import math
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python-engine'))
sys.path.insert(0,str(ROOT/'scripts'))
from overnight_enrichment import Policy,legacy_lab,risk_history,simulate
from overnight_enrichment_study import V2,sha,sources,write


def bound_sources():
    return {**sources(),Path(__file__).resolve().relative_to(ROOT).as_posix():sha(Path(__file__).resolve())}


def freeze(run):
    target=run/'final-freeze.json'
    if target.exists():raise ValueError('final freeze already exists')
    write(target,{'source':bound_sources(),
        'policies':[{'name':'V2_NATIVE'},{'name':'V3_HYBRID','regular_fraction':.5},
                    {'name':'V3_COST_ROUTE','regular_fraction':.5,'route_rule':'positive_net'}],
        'data':{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in
                [run/'_local/older/yahoo.sqlite',run/'older-acquisition.json',V2/'_local/yahoo-split-cuts.json']},
        'score_window':['2015-01-01','2018-12-31'],'risk_warmup':'2014-01-01','tail':'2019-01-10',
        'models':[[36,5,1.],[36,5,.75],[36,5,.5],[60,20,.75]],'seed':20261104,
        'preparation':'raw positive finite OHLCV, high/low consistency, positive volume; drop history before latest archived split (including later known splits); NIFTYBEES calendar exempt; no repair',
        'capital':'25000 fixed; positive profits withheld; losses reduce risk capital',
        'acceptance':{'per_model':'net/exbest positive, >=100 closes, no unresolved; >=10% more net with <=1.5x DD OR >=20% lower DD with >=95% net',
                      'robustness':'all 4 models net/exbest positive, >=100 closes, no unresolved; minimum net across declared models >=1.10x V2 minimum; maximum DD <=1.5x V2 maximum; separate from full-fill dominance'},
        'selection':'Round1 half-regular route protects poor-fill cases; round2 cost gate preserves ideal profit. Both diversification candidates rejected on development. No adjustment after this opening.',
        'limits':['current surviving membership','future split restriction','revised public OHLC basis','daily auction/postclose/regular fills assumed','single historical dataset','not forward qualification'],
        'frozen_at':datetime.now(timezone.utc).isoformat(),'old_outcomes_opened':False})


def prepare(run,f):
    lab=legacy_lab();audit=Counter();bars=defaultdict(list);nifty=[]
    cuts=json.loads((V2/'_local/yahoo-split-cuts.json').read_text())
    receipts=json.loads((run/'older-acquisition.json').read_text())['receipts']
    for r in receipts:
        for event in r.get('corporate_actions',{}).get('splits',{}).values():
            # UTC midnight events may correspond to a different Indian date.
            from zoneinfo import ZoneInfo
            d=datetime.fromtimestamp(event['date'],ZoneInfo('Asia/Kolkata')).date().isoformat()
            cuts[r['symbol']]=max(cuts.get(r['symbol'],''),d)
    path=run/'_local/older/yahoo.sqlite';c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    for t,d,o,h,l,cl,v in c.execute('SELECT ticker,date,open,high,low,close,volume FROM ohlcv_cache ORDER BY ticker,date'):
        audit['raw_rows']+=1
        if any(x is None or not math.isfinite(float(x)) for x in (o,h,l,cl,v)) or min(o,h,l,cl)<=0 or v<0:
            audit['invalid_cells']+=1;continue
        if t=='NIFTYBEES':nifty.append({'date':d,'close':float(cl)});continue
        if d<cuts.get(t,''):audit['pre_last_split']+=1;continue
        if v<=0:audit['zero_volume']+=1;continue
        if l>min(o,cl)*(1+1e-7) or h<max(o,cl)*(1-1e-7) or h<l:
            audit['inconsistent_ohlc']+=1;continue
        bars[t].append({'ticker':t,'date':d,'open':float(o),'high':float(h),'low':float(l),'close':float(cl),'volume':float(v)})
        audit['retained_equity_rows']+=1
    c.close()
    nifty.sort(key=lambda x:x['date'])
    audit['retained_tickers']=len(bars);audit['benchmark_sessions']=len(nifty)
    if not nifty:raise ValueError('missing benchmark')
    days=lab.build_days(dict(bars),nifty,f['risk_warmup'],f['tail'])
    audit['scoring_sessions']=sum(f['score_window'][0]<=d.date<=f['score_window'][1] for d in days)
    audit['sessions_with_candidates']=sum(bool(d.cands) and f['score_window'][0]<=d.date<=f['score_window'][1] for d in days)
    audit['candidate_observations']=sum(len(d.cands) for d in days if f['score_window'][0]<=d.date<=f['score_window'][1])
    write(run/'older-data-audit.json',dict(audit));lab.save(days,run/'_local/older/days.pkl')
    return days


def evaluate(results):
    base={tuple(r['model']):r for r in results if r['policy']['name']=='V2_NATIVE'};out={}
    for name in ['V3_HYBRID','V3_COST_ROUTE']:
        rows=[r for r in results if r['policy']['name']==name];per=[]
        adequate=all(r['summary']['net']>0 and r['summary']['ex_best']>0 and r['summary']['n']>=100 and r['open_at_end']==0 for r in rows)
        for r in rows:
            s=r['summary'];b=base[tuple(r['model'])]['summary']
            passed=adequate and ((s['net']>=1.1*b['net'] and s['dd']<=1.5*b['dd']) or (s['dd']<=.8*b['dd'] and s['net']>=.95*b['net']))
            per.append({'model':r['model'],'pass':passed,'net_ratio':s['net']/b['net'],'dd_ratio':s['dd']/b['dd']})
        worst=min(r['summary']['net'] for r in rows);bw=min(r['summary']['net'] for r in base.values())
        maxdd=max(r['summary']['dd'] for r in rows);bmax=max(r['summary']['dd'] for r in base.values())
        out[name]={'per_model':per,'adequate':adequate,'worst_net':worst,'base_worst_net':bw,
                   'max_dd':maxdd,'base_max_dd':bmax,'robustness_pass':adequate and worst>=1.1*bw and maxdd<=1.5*bmax,
                   'full_fill_pass':per[0]['pass'],'scope':'conditional daily model, not actual fills or forward qualification'}
    return out


def score(run):
    f=json.loads((run/'final-freeze.json').read_text());assert f['source']==bound_sources()
    for path,h in f['data'].items():assert sha(ROOT/path)==h,path
    marker=run/'OLDER_OPENED.json'
    with marker.open('x',encoding='utf-8') as out:
        json.dump({'opened_at':datetime.now(timezone.utc).isoformat(),'freeze_sha256':sha(run/'final-freeze.json')},out,indent=2)
    days=prepare(run,f);hist=risk_history(days);rows=[]
    for rb,xb,pfill in f['models']:
        for item in f['policies']:
            p=Policy(**item);r=simulate(days,p,start=f['score_window'][0],end=f['score_window'][1],
                regular_bps=rb,exit_bps=xb,winning_close_fill=pfill,seed=f['seed'],histories=hist)
            assert abs(sum(t['net'] for t in r['trades'])-r['summary']['net'])<.011
            if r['open_at_end']==0:assert abs(r['curve'][-1][1]-25000-r['summary']['net'])<.011
            write(run/f'_local/older/results/{p.name}_{rb}_{xb}_{pfill}.json',r)
            rows.append({k:r[k] for k in ['policy','summary','open_at_end','outcomes']}|{'model':[rb,xb,pfill]})
            print(p.name,[rb,xb,pfill],r['summary'],flush=True)
    assert f['source']==bound_sources()
    for path,h in f['data'].items():assert sha(ROOT/path)==h,path
    write(run/'older-results.json',rows);write(run/'older-verdict.json',evaluate(rows))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze','score']);p.add_argument('--run',required=True,type=Path)
    a=p.parse_args();globals()[a.command](a.run.resolve())
