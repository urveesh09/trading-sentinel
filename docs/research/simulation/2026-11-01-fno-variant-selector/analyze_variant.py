"""Frozen N06 financial acceptance; no extra offspring after outcomes."""
import json
import math
import sys
from datetime import datetime,timedelta
from collections import Counter
import variant_lab as L
sys.path.insert(0,str(L.PARENT))
import analyze_refine as N
A=N.A
YEARS=('2024','2025','2026')


def objects():
    out={}
    for y in YEARS:
        out[y]={}
        for phase in ('reference','candidate'):
            for n,k in json.loads((L.LOCAL/f'keys-{phase}-{y}.json').read_text()).items():
                out[y][n]=json.loads((L.LOCAL/'evals'/f'{k}.json').read_text())
    return out


def verify(objs):
    errors={};identities=set();count=0;maximum=0.;hashes={}
    for y,books in objs.items():
        ds=json.loads((L.LOCAL/f'decisions-{y}.json').read_text())
        for name,o in books.items():
            b=o['book'];rows=o['trades']
            bad=A.FIN.check_book(rows,{'cfg':b['cfg']},250000,b.get('cost'),3)
            memo={k:v for k,v in o['notes'].items() if (k=='named_memo_miss' or 'conflict' in k or k=='n06_decision_unavailable') and v}
            if bad or memo:errors[y+'|'+name]=dict(financial=bad,memo=memo)
            for t in rows:
                count+=1
                err=abs((t['exit_premium']-t['entry_premium'])*t['entry_qty']-L.P.P.E.calc_fno_costs(t['entry_premium'],t['exit_premium'],t['entry_qty'])-t['extra_cost']-t['net_pnl'])
                maximum=max(maximum,err);assert err<.0001
                assert t['admission_id'] not in identities;identities.add(t['admission_id'])
                assert t['initial_quantity']==t['entry_qty'] and t['initial_entry_premium']==t['entry_premium'] and t['initial_entry_time']==t['entry_time'] and t['adds']==0
                en=datetime.fromisoformat(t['entry_time']);ex=datetime.fromisoformat(t['exit_time']);bar=datetime.fromisoformat(t['bar_ts']).replace(tzinfo=en.tzinfo)
                assert bar+timedelta(minutes=5)<=en<=ex and en.date()==ex.date() and en.hour*60+en.minute<885 and ex.hour*60+ex.minute<=910
                if en.date().isoformat() in L.X.CAL.SPECIAL:assert en.hour*60+en.minute<720 and ex.hour*60+ex.minute<=745
                if t['origin']=='TPB_LOW':assert t['direction']=='SHORT' and t['entry_qty']==65
                d=t['n06_decision'];variant=t['n06_variant'];assert t['n05_mode']==('BASE' if variant=='MAIN' else variant)
                assert t['n03_variant']==('BASE' if variant=='MAIN' else 'RETEST')
                if b['n06_policy']!='STATIC':
                    assert d==ds[b['n06_policy']][en.date().isoformat()] and d['asof']==en.date().isoformat()
                    assert not d['latest_label_exit'] or d['latest_label_exit'][:10]<d['asof']
                    assert variant==d['variant']
            key=L.Y.task_key(b,'year',tuple(o['window']))
            for folder in ('evals','traces'):
                p=L.LOCAL/folder/f'{key}.json';hashes[p.relative_to(L.ROOT).as_posix()]=L.B.P.sha(p)
    assert not errors, errors
    return dict(errors=errors,closed_records=count,max_net_error_rs=maximum,fresh_annual_replays=18,file_sha256=hashes)


def run():
    from build_models import controls
    objs=objects();check=verify(objs);check['static_controls']=controls();ds=A.sessions();every=sorted(d for days in ds.values() for d in days);summaries={}
    for name in objs['2024']:
        ps={y:A.FIN.path(objs[y][name]['trades']) for y in YEARS}
        daily={d:v for p in ps.values() for d,v in p['daily'].items()}
        summaries[name]=dict(years={y:A.FIN.pub(p) for y,p in ps.items()},exact_years={y:N.exact_path(objs[y][name]['trades']) for y in YEARS},daily=daily,weekly=A.W.weeks_of(daily,every),
            variants={y:dict(Counter(t['n06_variant'] for t in objs[y][name]['trades'])) for y in YEARS})
    candidates={};stall=summaries['STALL30']
    for name in ('MAIN_ANCHOR','STRUCT_ANCHOR'):
        s=summaries[name];halves=[sum(v for d,v in s['daily'].items() if a<=d<=b) for y in YEARS for a,b in A.A.A.HALVES[y]]
        flags=dict(positive_each_year=all(s['exact_years'][y]['net']>0 for y in YEARS),sample=min(s['years'][y]['trades'] for y in YEARS)>=12 and sum(s['years'][y]['trades'] for y in YEARS)>=60,
                   without_best_trade=all(s['exact_years'][y]['net']-s['exact_years'][y]['best_trade']>0 for y in YEARS),without_best_day=all(s['exact_years'][y]['net']-s['exact_years'][y]['best_day']>0 for y in YEARS),
                   five_halves=sum(v>0 for v in halves)>=5,
                   net_not_worse_all_references_each_year=all(s['exact_years'][y]['net']>=max(summaries[v]['exact_years'][y]['net'] for v in ('BASE','STALL30','STRUCT30')) for y in YEARS),
                   drawdown_not_worse_all_references_each_year=all(s['exact_years'][y]['fall']<=min(summaries[v]['exact_years'][y]['fall'] for v in ('BASE','STALL30','STRUCT30')) for y in YEARS),
                   paired_weekly_stall=A.W.paired_t(s['weekly'],stall['weekly'])>=2,correct=not check['errors'])
        candidates[name]=dict(checks=flags,halves=halves,paired_t_stall=A.W.paired_t(s['weekly'],stall['weekly']))
    diffs=[[a-b for a,b in zip(summaries[n]['weekly'],stall['weekly'])] for n in candidates]
    _,ps=A.A.max_t_adjusted(diffs,samples=4096,seed=110601)
    for c,p in zip(candidates.values(),ps):c['adjusted_p']=float(p);c['checks']['max_t']=bool(p<=.05);c['passes']=all(c['checks'].values())
    out=dict(schema='n06_results_v1',books=summaries,candidates=candidates,passing=[n for n,c in candidates.items() if c['passes']],correctness=check,qualified=False,can_place_orders=False,all_years_seen=True)
    L.X.write(L.HERE/'results.json',out);print('N06_RESULTS',out['passing'],'records',check['closed_records'],flush=True)


if __name__=='__main__':run()
