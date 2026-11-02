"""N03 corrected reporting: TPB_FULL retains normal LOW sizing; frozen policy unchanged."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
"""Complete predeclared N03 trial ledger and unchanged-book controls."""
import argparse,json,sys
from collections import Counter
from pathlib import Path
import eff_lab as L
sys.path.insert(0,str(L.PARENT))
import analyze_core as A
HERE=L.HERE;YEARS=A.YEARS;load=A.load

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
                count+=1;qty=t['entry_qty'];e=t['entry_premium'];x=t['exit_premium'];error=abs((x-e)*qty-L.calc_fno_costs(e,x,qty)-t['extra_cost']-t['net_pnl']);maxerror=max(maxerror,error);assert error<.0001
                assert t['admission_id'] not in identities;identities.add(t['admission_id'])
                assert t['initial_quantity']==qty and t['initial_entry_premium']==e and t['initial_entry_time']==t['entry_time'] and t['adds']==0
                entry=L.datetime.fromisoformat(t['entry_time']);exit=L.datetime.fromisoformat(t['exit_time']);bar=L.datetime.fromisoformat(t['bar_ts']).replace(tzinfo=entry.tzinfo)
                assert bar+L.timedelta(minutes=5)<=entry<=exit and entry.date()==exit.date()
                assert entry.hour*60+entry.minute<885 and exit.hour*60+exit.minute<=910
                if entry.date().isoformat() in L.X.CAL.SPECIAL:assert entry.hour*60+entry.minute<720 and exit.hour*60+exit.minute<=745
                if b['n03_sizing']=='ONE':assert qty==65
                if t['origin']=='TPB_LOW':
                    assert t['direction']=='SHORT'
                    if t['selected_profile']=='TPB_ONE':assert qty==65
                assert t['entry_expert']==b['members'][t['member']]['name'] and t['n03_variant']==b['n03_variant']
                if t['selection_asof']:assert t['selection_asof']==entry.date().isoformat() and (not t['selection_latest_label_exit'] or t['selection_latest_label_exit'][:10]<t['selection_asof'])
                if b['n03_variant']=='RETEST' and t['entry_expert']=='EFF':
                    c=t['n03_entry_context'];assert c['reason']=='retest_confirmed' and c['confirmation_bar']==t['bar_ts']
                    delta=L.datetime.fromisoformat(c['confirmation_bar'])-L.datetime.fromisoformat(c['source_bar']);assert L.timedelta(0)<delta<=L.timedelta(minutes=15)
                    assert t['initial_stop_underlying']==c['original_stop']
            key=L.Y.task_key(b,'year',tuple(obj['window']));file=L.LOCAL/'evals'/f'{key}.json';trace=L.LOCAL/'traces'/f'{key}.json'
            assert trace.exists();hashes[file.relative_to(L.ROOT).as_posix()]=L.B.P.sha(file);hashes[trace.relative_to(L.ROOT).as_posix()]=L.B.P.sha(trace)
        for ctx,phase in [('MAIN','reference'),('TPB_ONE','reference'),('TPB_FULL','reference'),('CORE_SELECT','candidate')]:
            keys=load(L.PARENT_LOCAL/f'keys-{phase}-{y}.json');old=load(L.PARENT_LOCAL/'evals'/f'{keys[ctx]}.json')['trades'];new=books[f'NORMAL|{ctx}|BASE']['trades'];assert len(old)==len(new)
            for a,b in zip(old,new):assert {k:v for k,v in a.items() if k!='admission_id'}=={k:b.get(k) for k in a if k!='admission_id'},(y,ctx,'baseline parity')
            parity[y+'|'+ctx]={'records':len(old),'exact_economics':True}
    return {'errors':errors,'fresh_replays':sum(map(len,objs.values())),'closed_records':count,'max_net_error_rs':maxerror,'baseline_parity':parity,'file_sha256':hashes}

def analyze():
    objs=objects();check=verify(objs);ds=A.sessions();every=sorted(d for v in ds.values() for d in v);summaries={}
    for name in objs['2024']:
        paths={y:A.FIN.path(objs[y][name]['trades']) for y in YEARS};daily={d:v for p in paths.values() for d,v in p['daily'].items()}
        summaries[name]={'years':{y:A.FIN.pub(p) for y,p in paths.items()},'daily':daily,'weekly':A.W.weeks_of(daily,every),
            'years_without_best_trade':{y:sum(t['net_pnl'] for t in objs[y][name]['trades'])-max([0.,*[t['net_pnl'] for t in objs[y][name]['trades']]]) for y in YEARS},
            'member_net':{y:{m:sum(t['net_pnl'] for t in objs[y][name]['trades'] if t['entry_expert']==m) for m in ('SHIPPED','OR20','EFF','TPB')} for y in YEARS},
            'exit_actions':{y:dict(Counter(t.get('n03_exit_context',{}).get('action','UNCHANGED') for t in objs[y][name]['trades'])) for y in YEARS}}
    candidates={}
    for ctx in ('EFF_ONLY','MAIN','TPB_ONE','CORE_SELECT'):
        baseline=summaries[f'NORMAL|{ctx}|BASE']
        for variant in ('RETEST','HORIZON'):
            name=f'NORMAL|{ctx}|{variant}';s=summaries[name];min_year,min_total=(8,40) if ctx=='EFF_ONLY' else (12,60)
            halves=[sum(v for d,v in s['daily'].items() if a<=d<=b) for y in YEARS for a,b in A.A.A.HALVES[y]]
            flags={'positive_each_year':all(s['years'][y]['net']>0 for y in YEARS),'sample':min(s['years'][y]['trades'] for y in YEARS)>=min_year and sum(s['years'][y]['trades'] for y in YEARS)>=min_total,
                'without_best_trade':all(s['years_without_best_trade'][y]>0 for y in YEARS),'without_best_day':all(s['years'][y]['net']-s['years'][y]['best_day']>0 for y in YEARS),
                'five_halves':sum(v>=0 for v in halves)>=5,'not_worse_each_year':all(s['years'][y]['net']>=baseline['years'][y]['net'] for y in YEARS),'better_total':sum(s['years'][y]['net'] for y in YEARS)>sum(baseline['years'][y]['net'] for y in YEARS),
                'drawdown':all(s['years'][y]['fall_pct']<=max(1.5*baseline['years'][y]['fall_pct'],.05) for y in YEARS),'paired_weekly':A.W.paired_t(s['weekly'],baseline['weekly'])>=2,'correct':not check['errors']}
            candidates[name]={'checks':flags,'halves':halves,'paired_t':A.W.paired_t(s['weekly'],baseline['weekly'])}
    differences=[[a-b for a,b in zip(summaries[n]['weekly'],summaries[n.rsplit('|',1)[0]+'|BASE']['weekly'])] for n in candidates]
    _,ps=A.A.max_t_adjusted(differences,samples=4096,seed=110301)
    for value,p in zip(candidates.values(),ps):value['search_adjusted_p']=float(p);value['checks']['max_t']=bool(p<=.05);value['passes']=all(value['checks'].values())
    result={'schema':'n03_eff_results_v1','books':summaries,'candidates':candidates,'passing':[n for n,v in candidates.items() if v['passes']],'correctness':check,'qualified':False,'can_place_orders':False,'all_years_seen':True}
    L.X.write(HERE/'results.json',result);print('N03_RESULTS',result['passing'],'errors',check['errors'],'records',check['closed_records'],flush=True)

if __name__=='__main__':p=argparse.ArgumentParser();p.parse_args();analyze()
