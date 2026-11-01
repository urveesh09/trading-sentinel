"""Frozen whole-account verdicts, with ONE/cost diagnostics kept non-primary."""
import json,math,sys
from collections import Counter
from datetime import datetime,timedelta
import anatomy_lab as L
sys.path.insert(0,str(L.PARENT))
import analyze_refine as N
A=N.A;YEARS=('2024','2025','2026');load=lambda p:json.loads(p.read_text())


def objects():
    return {y:{n:load(L.LOCAL/'evals'/f'{key}.json') for phase in ('reference','candidate') for n,key in load(L.LOCAL/f'keys-{phase}-{y}.json').items()} for y in YEARS}


def verify(objs):
    errors={};ids=set();count=0;maxerror=0.;hashes={}
    for y,books in objs.items():
        for name,o in books.items():
            b=o['book'];rows=o['trades'];bad=A.FIN.check_book(rows,{'cfg':b['cfg']},250000,b.get('cost'),3)
            memo={k:v for k,v in o['notes'].items() if ('conflict' in k or k=='named_memo_miss') and v}
            if bad or memo:errors[y+'|'+name]=dict(financial=bad,memo=memo)
            for t in rows:
                count+=1;assert t['admission_id'] not in ids;ids.add(t['admission_id']);q=t['entry_qty'];extra=t.get('extra_cost',0.);err=abs((t['exit_premium']-t['entry_premium'])*q-L.P.P.E.calc_fno_costs(t['entry_premium'],t['exit_premium'],q)-extra-t['net_pnl']);maxerror=max(maxerror,err);assert err<.0001
                assert t['initial_quantity']==q and t['initial_entry_premium']==t['entry_premium'] and t['initial_entry_time']==t['entry_time'] and t['adds']==0
                en=datetime.fromisoformat(t['entry_time']);ex=datetime.fromisoformat(t['exit_time']);bar=datetime.fromisoformat(t['bar_ts']).replace(tzinfo=en.tzinfo)
                assert bar+timedelta(minutes=5)<=en<=ex and en.date()==ex.date() and en.hour*60+en.minute<885 and ex.hour*60+ex.minute<=910
                if en.date().isoformat() in L.X.CAL.SPECIAL:assert en.hour*60+en.minute<720 and ex.hour*60+ex.minute<=745
                if name.startswith('ONE|'):assert q==65
                if t['origin']=='TPB_LOW':assert q==65 and t['direction']=='SHORT'
                assert t['n07_mode']==b['n07_mode'] and t['entry_expert']==b['members'][t['member']]['name']
                if t['entry_expert']=='EFF' and b['n07_mode'] in ('PREMIUM_STALL','STRUCT_OR_PREMIUM'):assert t['n07_exit_context']['review_mode']==b['n07_mode']
            key=L.Y.task_key(b,'year',tuple(o['window']))
            for folder in ('evals','traces'):
                p=L.LOCAL/folder/f'{key}.json';hashes[p.relative_to(L.ROOT).as_posix()]=L.B.P.sha(p)
    assert not errors,errors
    from build_controls import controls
    return dict(errors=errors,closed_records=count,max_net_error_rs=maxerror,fresh_annual_replays=45,file_sha256=hashes,static_controls=controls())


def run():
    objs=objects();check=verify(objs);ds=A.sessions();every=sorted(d for days in ds.values() for d in days);summaries={};config=load(L.HERE/'configuration.json')
    for name in objs['2024']:
        ps={y:A.FIN.path(objs[y][name]['trades']) for y in YEARS};daily={d:v for p in ps.values() for d,v in p['daily'].items()}
        summaries[name]=dict(years={y:A.FIN.pub(p) for y,p in ps.items()},exact_years={y:N.exact_path(objs[y][name]['trades']) for y in YEARS},daily=daily,weekly=A.W.weeks_of(daily,every),
            member_net={y:{m:math.fsum(t['net_pnl'] for t in objs[y][name]['trades'] if t['entry_expert']==m) for m in ('SHIPPED','OR20','EFF','TPB')} for y in YEARS})
    candidates={};stall=summaries['NORMAL|STALL30'];structure=summaries['NORMAL|STRUCT30']
    for mode in ('PREMIUM_STALL','STRUCT_OR_PREMIUM'):
        name='NORMAL|'+mode;s=summaries[name];halves=[math.fsum(v for d,v in s['daily'].items() if a<=d<=b) for y in YEARS for a,b in config['periods'][y]]
        flags=dict(positive_each_year=all(s['exact_years'][y]['net']>0 for y in YEARS),sample=min(s['years'][y]['trades'] for y in YEARS)>=12 and sum(s['years'][y]['trades'] for y in YEARS)>=60,
            without_best_trade=all(s['exact_years'][y]['net']-s['exact_years'][y]['best_trade']>0 for y in YEARS),without_best_day=all(s['exact_years'][y]['net']-s['exact_years'][y]['best_day']>0 for y in YEARS),five_periods=sum(v>0 for v in halves)>=5,
            higher_net_than_both_each_year=all(s['exact_years'][y]['net']>max(stall['exact_years'][y]['net'],structure['exact_years'][y]['net']) for y in YEARS),
            closed_drawdown_no_larger_either_each_year=all(s['exact_years'][y]['fall']<=min(stall['exact_years'][y]['fall'],structure['exact_years'][y]['fall']) for y in YEARS),
            paired_weekly_stall=A.W.paired_t(s['weekly'],stall['weekly'])>=2,correct=not check['errors'])
        candidates[name]=dict(checks=flags,periods=halves,paired_t_stall=A.W.paired_t(s['weekly'],stall['weekly']),paired_t_structure=A.W.paired_t(s['weekly'],structure['weekly']))
    diffs=[[a-b for a,b in zip(summaries[n]['weekly'],stall['weekly'])] for n in candidates];_,ps=A.A.max_t_adjusted(diffs,samples=4096,seed=110701)
    for c,p in zip(candidates.values(),ps):c['adjusted_p']=float(p);c['checks']['max_t']=bool(p<=.05);c['passes']=all(c['checks'].values())
    L.X.write(L.HERE/'results.json',dict(schema='n07_anatomy_results_v1',books=summaries,candidates=candidates,passing=[n for n,c in candidates.items() if c['passes']],correctness=check,qualified=False,can_place_orders=False,all_years_seen=True))
    print('N07_RESULTS',[n for n,c in candidates.items() if c['passes']],'records',check['closed_records'],flush=True)


if __name__=='__main__':run()
