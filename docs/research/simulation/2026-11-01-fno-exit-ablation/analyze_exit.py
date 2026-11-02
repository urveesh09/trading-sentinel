"""N04 complete ledger, exact controls and predeclared eight-arm comparison."""
import json,sys
from collections import Counter
from datetime import datetime,timedelta
from pathlib import Path
import exit_lab as L
sys.path[:0]=[str(L.PARENT/'reporting'),str(L.E.PARENT)]
import reconcile as N
A=N.A;YEARS=N.YEARS;load=N.load;HERE=L.HERE
def objects():return {y:{n:load(L.LOCAL/'evals'/f'{key}.json') for n,key in load(L.LOCAL/f'keys-{y}.json').items()} for y in YEARS}

def verify(objs):
    errors={};identities=set();count=0;maxerror=0.;hashes={};parity={}
    for y,books in objs.items():
        for name,obj in books.items():
            b=obj['book'];rows=obj['trades'];bad=A.FIN.check_book(rows,{'cfg':b['cfg']},250000,b.get('cost'),3)
            memo={k:v for k,v in obj['notes'].items() if ('conflict' in k or k=='named_memo_miss') and v}
            if bad or memo:errors[y+'|'+name]={'financial':bad,'memo':memo}
            for t in rows:
                if t.get('net_pnl') is None:continue
                count+=1;qty=t['entry_qty'];e=t['entry_premium'];x=t['exit_premium'];error=abs((x-e)*qty-L.E.calc_fno_costs(e,x,qty)-t['extra_cost']-t['net_pnl']);maxerror=max(maxerror,error);assert error<.0001
                assert t['admission_id'] not in identities;identities.add(t['admission_id']);assert t['initial_quantity']==qty and t['initial_entry_premium']==e and t['initial_entry_time']==t['entry_time'] and t['adds']==0
                entry=datetime.fromisoformat(t['entry_time']);exit=datetime.fromisoformat(t['exit_time']);bar=datetime.fromisoformat(t['bar_ts']).replace(tzinfo=entry.tzinfo)
                assert bar+timedelta(minutes=5)<=entry<=exit and entry.date()==exit.date() and entry.hour*60+entry.minute<885 and exit.hour*60+exit.minute<=910
                if entry.date().isoformat() in L.X.CAL.SPECIAL:assert entry.hour*60+entry.minute<720 and exit.hour*60+exit.minute<=745
                if b['n03_sizing']=='ONE':assert qty==65
                if t['origin']=='TPB_LOW':assert t['direction']=='SHORT' and qty==65
                assert t['entry_expert']==b['members'][t['member']]['name'] and t['n04_mode']==b['n04_mode'] and t['n04_context']==b['n04_context']
                if t['selection_asof']:assert t['selection_asof']==entry.date().isoformat() and (not t['selection_latest_label_exit'] or t['selection_latest_label_exit'][:10]<t['selection_asof'])
                if t['entry_expert']=='EFF' and b['n04_mode']!='BASE':
                    c=t['n04_exit_context'];assert c['mode']==b['n04_mode']
                    if b['n04_mode']=='STALL_ONLY':assert c['action']!='CONTINUE90' and not t['n04_ever_extended']
                    else:assert c['action']!='STALL30'
            key=L.Y.task_key(b,'year',tuple(obj['window']));file=L.LOCAL/'evals'/f'{key}.json';trace=L.LOCAL/'traces'/f'{key}.json';assert trace.exists()
            hashes[file.relative_to(L.ROOT).as_posix()]=L.B.P.sha(file);hashes[trace.relative_to(L.ROOT).as_posix()]=L.B.P.sha(trace)
        oldkeys=load(L.OLD/f'keys-{y}.json')
        mapping={'NORMAL|MAIN|BASE':'NORMAL|MAIN|BASE','NORMAL|TPB_ONE|BASE':'NORMAL|TPB_ONE|BASE','NORMAL|BALANCED_RETEST|BASE':'NORMAL|TPB_ONE|RETEST','NORMAL|CORE_SELECT|BASE':'NORMAL|CORE_SELECT|BASE','ONE|MAIN|BASE':'ONE|MAIN|BASE'}
        for name,oldname in mapping.items():
            old=load(L.OLD/'evals'/f'{oldkeys[oldname]}.json')['trades'];new=books[name]['trades'];assert len(old)==len(new)
            for a,b in zip(old,new):assert {k:v for k,v in a.items() if k!='admission_id'}=={k:b.get(k) for k in a if k!='admission_id'},(y,name,'baseline parity')
            parity[y+'|'+name]={'records':len(old),'exact_economics':True}
    return {'errors':errors,'fresh_replays':sum(map(len,objs.values())),'closed_records':count,'max_net_error_rs':maxerror,'baseline_parity':parity,'file_sha256':hashes}

def analyze():
    objs=objects();check=verify(objs);ds=A.sessions();every=sorted(d for v in ds.values() for d in v);summaries={}
    for name in objs['2024']:
        paths={y:A.FIN.path(objs[y][name]['trades']) for y in YEARS};daily={d:v for p in paths.values() for d,v in p['daily'].items()}
        summaries[name]={'years':{y:A.FIN.pub(p) for y,p in paths.items()},'daily':daily,'weekly':A.W.weeks_of(daily,every),
            'years_without_best_trade':{y:sum(t['net_pnl'] for t in objs[y][name]['trades'])-max([0.,*[t['net_pnl'] for t in objs[y][name]['trades']]]) for y in YEARS},
            'member_net':{y:{m:sum(t['net_pnl'] for t in objs[y][name]['trades'] if t['entry_expert']==m) for m in ('SHIPPED','OR20','EFF','TPB')} for y in YEARS},
            'exit_actions':{y:dict(Counter(t.get('n04_exit_context',{}).get('action','UNCHANGED') for t in objs[y][name]['trades'])) for y in YEARS}}
    candidates={}
    for ctx in ('MAIN','TPB_ONE','BALANCED_RETEST','CORE_SELECT'):
        baseline=summaries[f'NORMAL|{ctx}|BASE']
        for mode in ('STALL_ONLY','CONTINUE_ONLY'):
            name=f'NORMAL|{ctx}|{mode}';s=summaries[name];halves=[sum(v for d,v in s['daily'].items() if a<=d<=b) for y in YEARS for a,b in A.A.A.HALVES[y]]
            flags={'positive_each_year':all(s['years'][y]['net']>0 for y in YEARS),'sample':min(s['years'][y]['trades'] for y in YEARS)>=12 and sum(s['years'][y]['trades'] for y in YEARS)>=60,
                'without_best_trade':all(s['years_without_best_trade'][y]>0 for y in YEARS),'without_best_day':all(s['years'][y]['net']-s['years'][y]['best_day']>0 for y in YEARS),
                'five_halves':sum(v>=0 for v in halves)>=5,'not_worse_each_year':all(s['years'][y]['net']>=baseline['years'][y]['net'] for y in YEARS),'better_total':sum(s['years'][y]['net'] for y in YEARS)>sum(baseline['years'][y]['net'] for y in YEARS),
                'drawdown':all(s['years'][y]['fall_pct']<=max(1.5*baseline['years'][y]['fall_pct'],.05) for y in YEARS),'paired_weekly':A.W.paired_t(s['weekly'],baseline['weekly'])>=2,'correct':not check['errors']}
            candidates[name]={'checks':flags,'halves':halves,'paired_t':A.W.paired_t(s['weekly'],baseline['weekly'])}
    diffs=[[a-b for a,b in zip(summaries[n]['weekly'],summaries[n.rsplit('|',1)[0]+'|BASE']['weekly'])] for n in candidates];_,ps=A.A.max_t_adjusted(diffs,samples=4096,seed=110401)
    for value,p in zip(candidates.values(),ps):value['search_adjusted_p']=float(p);value['checks']['max_t']=bool(p<=.05);value['passes']=all(value['checks'].values())
    result={'schema':'n04_exit_results_v1','books':summaries,'candidates':candidates,'passing':[n for n,v in candidates.items() if v['passes']],'correctness':check,'reference_id':'BALANCED_RETEST_N03','qualified':False,'can_place_orders':False,'all_years_seen':True}
    L.X.write(HERE/'results.json',result);print('N04_RESULTS',result['passing'],'errors',check['errors'],'records',check['closed_records'],flush=True)
if __name__=='__main__':analyze()
