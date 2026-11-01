"""N05 exact controls and strict predeclared more-profit/no-more-drawdown rule."""
import sys
from collections import Counter
from datetime import datetime,timedelta
from pathlib import Path
import math
import refine_lab as L
sys.path.insert(0,str(L.PARENT))
import analyze_exit as N
A=N.A;YEARS=N.YEARS;load=N.load;HERE=L.HERE
def objects():return {y:{n:load(L.LOCAL/'evals'/f'{key}.json') for n,key in load(L.LOCAL/f'keys-{y}.json').items()} for y in YEARS}

def exact_path(rows):
    cash=peak=250000.;fall=0.;daily={}
    for t in sorted(rows,key=lambda t:(t['exit_time'],t['entry_time'])):
        cash+=t['net_pnl'];peak=max(peak,cash);fall=max(fall,(peak-cash)/peak);day=t['exit_time'][:10];daily[day]=daily.get(day,0.)+t['net_pnl']
    return {'net':math.fsum(t['net_pnl'] for t in rows),'fall':fall,'best_day':max([0.,*daily.values()]),'best_trade':max([0.,*[t['net_pnl'] for t in rows]])}

def verify(objs):
    errors={};identities=set();count=0;maxerror=0.;hashes={};parity={}
    for y,books in objs.items():
        for name,obj in books.items():
            b=obj['book'];rows=obj['trades'];bad=A.FIN.check_book(rows,{'cfg':b['cfg']},250000,b.get('cost'),3);memo={k:v for k,v in obj['notes'].items() if ('conflict' in k or k=='named_memo_miss') and v}
            if bad or memo:errors[y+'|'+name]={'financial':bad,'memo':memo}
            for t in rows:
                if t.get('net_pnl') is None:continue
                count+=1;qty=t['entry_qty'];e=t['entry_premium'];x=t['exit_premium'];error=abs((x-e)*qty-L.P.E.calc_fno_costs(e,x,qty)-t['extra_cost']-t['net_pnl']);maxerror=max(maxerror,error);assert error<.0001
                assert t['admission_id'] not in identities;identities.add(t['admission_id']);assert t['initial_quantity']==qty and t['initial_entry_premium']==e and t['initial_entry_time']==t['entry_time'] and t['adds']==0
                entry=datetime.fromisoformat(t['entry_time']);exit=datetime.fromisoformat(t['exit_time']);bar=datetime.fromisoformat(t['bar_ts']).replace(tzinfo=entry.tzinfo)
                assert bar+timedelta(minutes=5)<=entry<=exit and entry.date()==exit.date() and entry.hour*60+entry.minute<885 and exit.hour*60+exit.minute<=910
                if entry.date().isoformat() in L.X.CAL.SPECIAL:assert entry.hour*60+entry.minute<720 and exit.hour*60+exit.minute<=745
                if b['n03_sizing']=='ONE':assert qty==65
                if t['origin']=='TPB_LOW':assert t['direction']=='SHORT' and qty==65
                assert t['entry_expert']==b['members'][t['member']]['name'] and t['n05_mode']==b['n05_mode']
                if t['entry_expert']=='EFF' and t['n05_mode']!='BASE':
                    c=t['n05_exit_context'];assert c['review_mode']==t['n05_mode'] and c['action'] in ('BASE60','STALL30','DELAY45','STRUCT30')
                    if c['action']=='DELAY45':assert 45<=c['age_minutes']<60 and c['parent_stall_eligible']
                    if c['action']=='STRUCT30':assert c['structure']['fresh'] and c['original_retest_level']==t['n03_entry_context']['broken_level']
            key=L.Y.task_key(b,'year',tuple(obj['window']));file=L.LOCAL/'evals'/f'{key}.json';trace=L.LOCAL/'traces'/f'{key}.json';assert trace.exists();hashes[file.relative_to(L.ROOT).as_posix()]=L.B.P.sha(file);hashes[trace.relative_to(L.ROOT).as_posix()]=L.B.P.sha(trace)
        oldkeys=load(L.OLD/f'keys-{y}.json');mapping={'NORMAL|MAIN|BASE':'NORMAL|MAIN|BASE',**{f'{s}|BALANCED_RETEST|{new}':f'{s}|BALANCED_RETEST|{old}' for s in ('NORMAL','ONE') for new,old in [('BASE','BASE'),('STALL30','STALL_ONLY')]}}
        excluded={'admission_id','n04_mode','n04_exit_context','n04_ever_extended'}
        for name,oldname in mapping.items():
            old=load(L.OLD/'evals'/f'{oldkeys[oldname]}.json')['trades'];new=books[name]['trades'];assert len(old)==len(new)
            for a,b in zip(old,new):assert {k:v for k,v in a.items() if k not in excluded}=={k:b.get(k) for k in a if k not in excluded},(y,name,'control parity')
            parity[y+'|'+name]={'records':len(old),'exact_economics':True}
    return {'errors':errors,'fresh_replays':sum(map(len,objs.values())),'closed_records':count,'max_net_error_rs':maxerror,'baseline_parity':parity,'file_sha256':hashes}

def analyze():
    objs=objects();check=verify(objs);ds=A.sessions();every=sorted(d for v in ds.values() for d in v);summaries={}
    for name in objs['2024']:
        ps={y:A.FIN.path(objs[y][name]['trades']) for y in YEARS};daily={d:v for p in ps.values() for d,v in p['daily'].items()}
        summaries[name]={'years':{y:A.FIN.pub(p) for y,p in ps.items()},'exact_years':{y:exact_path(objs[y][name]['trades']) for y in YEARS},'daily':daily,'weekly':A.W.weeks_of(daily,every),'years_without_best_trade':{y:sum(t['net_pnl'] for t in objs[y][name]['trades'])-max([0.,*[t['net_pnl'] for t in objs[y][name]['trades']]]) for y in YEARS},
            'member_net':{y:{m:sum(t['net_pnl'] for t in objs[y][name]['trades'] if t['entry_expert']==m) for m in ('SHIPPED','OR20','EFF','TPB')} for y in YEARS},'exit_actions':{y:dict(Counter(t.get('n05_exit_context',{}).get('action','UNCHANGED') for t in objs[y][name]['trades'])) for y in YEARS}}
    base=summaries['NORMAL|BALANCED_RETEST|BASE'];stall=summaries['NORMAL|BALANCED_RETEST|STALL30'];candidates={}
    for mode in ('DELAY45','STRUCT30'):
        name='NORMAL|BALANCED_RETEST|'+mode;s=summaries[name];halves=[sum(v for d,v in s['daily'].items() if a<=d<=b) for y in YEARS for a,b in A.A.A.HALVES[y]]
        flags={'positive_each_year':all(s['exact_years'][y]['net']>0 for y in YEARS),'sample':min(s['years'][y]['trades'] for y in YEARS)>=12 and sum(s['years'][y]['trades'] for y in YEARS)>=60,'without_best_trade':all(s['exact_years'][y]['net']-s['exact_years'][y]['best_trade']>0 for y in YEARS),'without_best_day':all(s['exact_years'][y]['net']-s['exact_years'][y]['best_day']>0 for y in YEARS),'five_halves':sum(v>=0 for v in halves)>=5,
            'net_not_worse_both_each_year':all(s['exact_years'][y]['net']>=max(base['exact_years'][y]['net'],stall['exact_years'][y]['net']) for y in YEARS),'better_total_stall':sum(s['exact_years'][y]['net'] for y in YEARS)>sum(stall['exact_years'][y]['net'] for y in YEARS),
            'drawdown_not_worse_both_each_year':all(s['exact_years'][y]['fall']<=min(base['exact_years'][y]['fall'],stall['exact_years'][y]['fall']) for y in YEARS),'paired_weekly_stall':A.W.paired_t(s['weekly'],stall['weekly'])>=2,'correct':not check['errors']}
        candidates[name]={'checks':flags,'halves':halves,'paired_t_stall':A.W.paired_t(s['weekly'],stall['weekly']),'paired_t_base':A.W.paired_t(s['weekly'],base['weekly'])}
    diffs=[[a-b for a,b in zip(summaries[n]['weekly'],stall['weekly'])] for n in candidates];_,ps=A.A.max_t_adjusted(diffs,samples=4096,seed=110501)
    for v,p in zip(candidates.values(),ps):v['search_adjusted_p']=float(p);v['checks']['max_t']=bool(p<=.05);v['passes']=all(v['checks'].values())
    L.X.write(HERE/'results.json',{'schema':'n05_refine_results_v1','books':summaries,'candidates':candidates,'passing':[n for n,v in candidates.items() if v['passes']],'correctness':check,'qualified':False,'can_place_orders':False,'all_years_seen':True});print('N05_RESULTS',[n for n,v in candidates.items() if v['passes']],'errors',check['errors'],'records',check['closed_records'],flush=True)
if __name__=='__main__':analyze()
