"""Frozen N01 model construction, actual book comparisons and reconciliation."""
from __future__ import annotations
import argparse,json,sys
from collections import Counter,defaultdict
from datetime import date,datetime,timedelta
from pathlib import Path
import numpy as np
import router_lab as X
import analyze_broad as A
HERE,ROOT=X.HERE,X.ROOT
YEARS=('2024','2025','2026');FIN=A.FIN
load=lambda p:json.loads(p.read_text())


def sessions():
    f=load(HERE/'freeze.json')
    return {y:[d for d in load(ROOT/f['bindings'][y]['dataset']/'manifest.json')['sessions'] if d<=(y+'-12-31' if y!='2026' else '2026-10-28')] for y in YEARS}


def objects(phase):
    out={}
    for y in YEARS:
        keys=load(HERE/f'_local/keys-{phase}-{y}.json');out[y]={}
        for n,k in keys.items():out[y][n]=load(HERE/'_local/evals'/f'{k}.json')
    return out


def prepare():
    X.B.O27F.deny_network();X.verify('base');X.Y.speedups();y=X.B.YEAR
    keys=load(HERE/f'_local/keys-base-{y}.json');data=X.Y.dataset('year');frames={};training=[];old_rows=[];main_rows=[]
    def state(t):
        day=t['entry_time'][:10];d=date.fromisoformat(day)
        if day not in frames:frames[day]=data.futures_frame(data.future_contract(data.front_expiry(d)).token,d)
        return X.states(frames[day],d)[0].get(t['bar_ts'],{'state':'UNAVAILABLE'})
    for name,key in keys.items():
        obj=load(HERE/'_local/evals'/f'{key}.json')
        if name=='MAIN':
            oldkeys=load(X.PREVIOUS/f'_local/keys-screen-{y}.json');old=load(X.PREVIOUS/'_local/evals'/f"{oldkeys['EX|MAIN']}.json")
            assert obj['trades']==old['trades'],'main parity'
            for t in obj['trades']:
                assert t.get('net_pnl') is not None
                label=state(t)['state'];path=X.states(frames[t['entry_time'][:10]],date.fromisoformat(t['entry_time'][:10]))[1]['t']
                width=float(path['high'].max()-path['low'].min());progress=abs(float(path['close'].iloc[-1]-path['open'].iloc[0]))/width if width>0 else 0.
                main_rows.append({'year':y,'day':t['entry_time'][:10],'state':label,'hindsight_shape':'ARCHIVED_TREND' if progress>=.5 else 'ARCHIVED_TWO_WAY','direction':t['direction'],'net':float(t['net_pnl']),'entry_time':t['entry_time']})
        if name=='OLD_BREAKOUT_LOW':
            base=X.PREVIOUS/'calendar' if y=='2024' else X.PREVIOUS
            oldkeys=load(base/f'_local/keys-screen-{y}.json');old=load(base/'_local/evals'/f"{oldkeys['RAW|DONCHIAN|g2']}.json")
            assert obj['trades']==old['trades'],'old-breakout parity'
            for t in obj['trades']:
                assert t.get('net_pnl') is not None
                label=state(t)['state'];path=X.states(frames[t['entry_time'][:10]],date.fromisoformat(t['entry_time'][:10]))[1]['t']
                width=float(path['high'].max()-path['low'].min());progress=abs(float(path['close'].iloc[-1]-path['open'].iloc[0]))/width if width>0 else 0.
                old_rows.append({'year':y,'day':t['entry_time'][:10],'state':label,'hindsight_shape':'ARCHIVED_TREND' if progress>=.5 else 'ARCHIVED_TWO_WAY','direction':t['direction'],'exit_reason':t['exit_reason'],'net':float(t['net_pnl'])-200.,'entry_time':t['entry_time']})
        if name.startswith('LIB|'):
            for t in obj['trades']:
                assert t.get('net_pnl') is not None and t['entry_qty']==65 and t['router_expert']==name[4:]
                assert state(t)['state']==t['router_state'],'entry-state reconstruction mismatch'
                training.append({'year':y,'day':t['entry_time'][:10],'expert':name[4:],'cell':t['router_cell'],
                                 'entry_time':t['entry_time'],'exit_time':t['exit_time'],'net':float(t['net_pnl'])-200.,'admission_id':t['router_admission_id']})
    X.write(HERE/f'_local/training-records-{y}.json',training)
    X.write(HERE/f'_local/old-breakout-states-{y}.json',old_rows)
    X.write(HERE/f'_local/main-states-{y}.json',main_rows)
    X.verify('base');print('PREPARED',y,len(training),'past-outcome labels; old/main exact parity',flush=True)


def train():
    all_sessions=sorted(d for ds in sessions().values() for d in ds)
    records=sum((load(HERE/f'_local/training-records-{y}.json') for y in YEARS),[])
    manifest={'schema':'n01_training_v1','source_freeze_sha256':X.B.P.sha(HERE/'freeze.json'),'models':{},'library_sha256':{},'all_years_seen':True,'asof_labels_only':True}
    for y in YEARS:
        months=sorted({d[:7]+'-01' for d in all_sessions if d[:4]==y})
        models={m:X.R.fit_model(records,m,all_sessions) for m in months}
        out={'models':models,'session_index':{d:i for i,d in enumerate(all_sessions) if d[:4]==y},'qualified':False}
        p=HERE/f'_local/models-{y}.json';assert not p.exists();X.write(p,out)
        manifest['models'][y]={'path':p.relative_to(ROOT).as_posix(),'sha256':X.B.P.sha(p),'monthly_models':len(models),'latest_training_exits':{m:v['latest_label_exit'] for m,v in models.items()},'positive_choices':{m:sum(len(v) for v in z['choices'].values()) for m,z in models.items()}}
        for key in load(HERE/f'_local/keys-base-{y}.json').values():
            file=HERE/'_local/evals'/f'{key}.json';manifest['library_sha256'][file.relative_to(ROOT).as_posix()]=X.B.P.sha(file)
    assert not (HERE/'training-manifest.json').exists();X.write(HERE/'training-manifest.json',manifest)
    print('TRAINING_FROZEN',len(records),'counterfactual labels;34 past-only monthly models',flush=True)


def partition(rows,key):
    groups={}
    for value in sorted({r[key] for r in rows}):
        groups[str(value)]={}
        for y in YEARS:
            part=[r for r in rows if r['year']==y and r[key]==value]
            groups[str(value)][y]={'trades':len(part),'net':round(sum(r['net'] for r in part),2),'wins':sum(r['net']>0 for r in part)}
    for y in YEARS:assert abs(sum(v[y]['net'] for v in groups.values())-sum(r['net'] for r in rows if r['year']==y))<.04
    return groups


def reconcile(all_books):
    from fno_costs import calc_fno_costs
    issues={};count=0;maxerror=0.;ids=set();files={}
    for phase,by_year in all_books.items():
        for y,books in by_year.items():
            for name,obj in books.items():
                b=obj['book'];rows=obj['trades'];bad=FIN.check_book(rows,{'cfg':b['cfg']},250000,b.get('cost'),b['cfg'].get('FNO_MAX_TRADES_PER_DAY',3))
                memo={k:v for k,v in obj['notes'].items() if 'conflict' in k or k=='named_memo_miss'}
                if bad or memo:issues[f'{phase}|{y}|{name}']={'financial':bad,'memo':memo}
                for t in rows:
                    if t.get('net_pnl') is None:continue
                    count+=1;qty=t['entry_qty'];e=t['entry_premium'];x=t['exit_premium'];error=abs((x-e)*qty-calc_fno_costs(e,x,qty)-float(t.get('extra_cost') or 0)-t['net_pnl']);maxerror=max(error,maxerror);assert error<.0001
                    entry=datetime.fromisoformat(t['entry_time']);exit=datetime.fromisoformat(t['exit_time']);bar=datetime.fromisoformat(t['bar_ts']).replace(tzinfo=entry.tzinfo)
                    assert bar+timedelta(minutes=5)<=entry<=exit and entry.date()==exit.date()
                    assert entry.hour*60+entry.minute<885 and exit.hour*60+exit.minute<=910
                    if entry.date().isoformat() in X.CAL.SPECIAL:assert entry.hour*60+entry.minute<720 and exit.hour*60+exit.minute<=745
                    if 'n01_policy' in b:
                        identity=t['router_admission_id'];assert identity not in ids;ids.add(identity)
                        assert t['initial_quantity']==qty and t['initial_entry_premium']==e and t['initial_entry_time']==t['entry_time'] and t['adds']==0
                        assert t['initial_stop_underlying']>0 and t['initial_target_underlying']>0
                        assert t['router_expert']==b['n01_experts'][t['member']]
                        if t['router_model_asof']:assert t['router_model_asof']<=t['entry_time'][:10]
                        if b['n01_policy']!='STATIC':assert t['router_state'] not in ('SHOCK','UNAVAILABLE')
                        if t['exit_reason']=='router_state_invalidated':assert exit-entry>=timedelta(minutes=15) and b['n01_policy']=='RULE_EXIT'
                key=X.Y.task_key(b,'year',tuple(obj['window']));p=HERE/'_local/evals'/f'{key}.json';files[p.relative_to(ROOT).as_posix()]=X.B.P.sha(p)
    return {'issues':issues,'closed_records':count,'max_net_error_rs':maxerror,'unique_router_admissions':len(ids),'file_sha256':files,'fresh_replays':sum(len(v) for ys in all_books.values() for v in ys.values())}


def analyze():
    base=objects('base');child=objects('candidate');ds=sessions();every=sorted(d for v in ds.values() for d in v)
    check=reconcile({'base':base,'candidate':child})
    def curve(name,source):
        paths={y:FIN.path(source[y][name]['trades']) for y in YEARS}
        daily={d:v for p in paths.values() for d,v in p['daily'].items()}
        return {'years':{y:FIN.pub(v) for y,v in paths.items()},'weekly':A.A.A.weeks_of(daily,every),'daily':daily}
    # analyze_gap.A is analyze_w, which supplies weeks_of/plain_t/paired_t.
    main=curve('MAIN',base);static=curve('STATIC_UNION',base);summary={};series=[]
    for policy in ('RULE','RULE_EXIT','LEARN'):
        exact=curve('EX|'+policy,child);raw=A.A.raw_summary({y:child[y]['RAW|'+policy]['trades'] for y in YEARS},ds)
        stress=A.A.raw_summary({y:child[y]['RAW|'+policy]['trades'] for y in YEARS},ds,300)
        days=exact['daily'];halves=[sum(v for d,v in days.items() if a<=d<=b) for y in YEARS for a,b in A.A.HALVES[y]]
        flags={'positive_each_year':all(exact['years'][y]['net']>0 for y in YEARS),'sample':min(exact['years'][y]['trades'] for y in YEARS)>=12 and sum(exact['years'][y]['trades'] for y in YEARS)>=60,
               'five_halves':sum(v>=0 for v in halves)>=5,'without_year_best':all(exact['years'][y]['net']-exact['years'][y]['best_day']>0 for y in YEARS),
               'beats_main_each_year':all(exact['years'][y]['net']>main['years'][y]['net'] for y in YEARS),'beats_static_each_year':all(exact['years'][y]['net']>static['years'][y]['net'] for y in YEARS),
               'drawdown':all(exact['years'][y]['fall_pct']<=max(1.5*main['years'][y]['fall_pct'],.05) for y in YEARS),
               'paired_main':A.A.A.paired_t(exact['weekly'],main['weekly'])>=2,'paired_static':A.A.A.paired_t(exact['weekly'],static['weekly'])>=2,'correct':not check['issues']}
        usage={y:dict(Counter(t['router_expert'] for t in child[y]['EX|'+policy]['trades'] if t.get('net_pnl') is not None)) for y in YEARS}
        state_usage={y:dict(Counter(t['router_state'] for t in child[y]['EX|'+policy]['trades'] if t.get('net_pnl') is not None)) for y in YEARS}
        summary[policy]={'exact':exact,'raw':raw,'stress300':stress,'halves':halves,'checks':flags,'usage':usage,'entry_states':state_usage,
                         'fallback_trades':{y:sum(t.get('router_fallback',False) for t in child[y]['EX|'+policy]['trades']) for y in YEARS},
                         'switch_exits':{y:sum(t.get('exit_reason')=='router_state_invalidated' for t in child[y]['EX|'+policy]['trades']) for y in YEARS}}
        series.extend([raw['weekly'],exact['weekly']])
    _,ps=A.max_t_adjusted(series,samples=4096,seed=110126)
    for i,(policy,v) in enumerate(summary.items()):
        v['raw_max_t_p']=float(ps[2*i]);v['exact_max_t_p']=float(ps[2*i+1]);v['checks']['max_t']=bool(ps[2*i+1]<=.05);v['passes']=all(v['checks'].values())
    old=sum((load(HERE/f'_local/old-breakout-states-{y}.json') for y in YEARS),[])
    main_rows=sum((load(HERE/f'_local/main-states-{y}.json') for y in YEARS),[])
    result={'schema':'n01_results_v1','main':main,'static':static,'candidates':summary,'passing':[p for p,v in summary.items() if v['passes']],
            'old_breakout_attribution':{key:partition(old,key) for key in ('state','direction','exit_reason','hindsight_shape')},'main_attribution':{key:partition(main_rows,key) for key in ('state','direction','hindsight_shape')},
            'hindsight_shape_limit':'Archived full-path labels are descriptive after the session, never available to routing/training.','correctness':check,'qualified':False,'can_place_orders':False,'all_years_seen':True}
    X.write(HERE/'results.json',result);print('ROUTER_RESULTS',result['passing'],'issues',check['issues'],'records',check['closed_records'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','train','analyze']);a=p.parse_args();{'prepare':prepare,'train':train,'analyze':analyze}[a.action]()
