"""N02: exact reference parity, past-only daily choices and shared-book results."""
import argparse,json,sys
from collections import Counter,defaultdict
from datetime import datetime,timedelta
from pathlib import Path
import core_lab as X
import analyze_broad as A
HERE,ROOT=X.HERE,X.ROOT;YEARS=('2024','2025','2026');FIN=A.FIN;W=A.A.A
load=lambda p:json.loads(p.read_text())


def sessions():
    f=load(HERE/'freeze.json')
    return {y:[d for d in load(ROOT/f['bindings'][y]['dataset']/'manifest.json')['sessions'] if d<=(y+'-12-31' if y!='2026' else '2026-10-28')] for y in YEARS}


def objects(phase):
    return {y:{n:load(HERE/'_local/evals'/f'{k}.json') for n,k in load(HERE/f'_local/keys-{phase}-{y}.json').items()} for y in YEARS}


def verify_books(all_books):
    errors={};count=0;maxerror=0.;identities=set();hashes={}
    from fno_costs import calc_fno_costs
    for phase,ys in all_books.items():
        for y,books in ys.items():
            for name,obj in books.items():
                b=obj['book'];rows=obj['trades'];bad=FIN.check_book(rows,{'cfg':b['cfg']},250000,b.get('cost'),3)
                memo={k:v for k,v in obj['notes'].items() if ('conflict' in k or k=='named_memo_miss') and v}
                if bad or memo:errors[f'{phase}|{y}|{name}']={'financial':bad,'memo':memo}
                for t in rows:
                    if t.get('net_pnl') is None:continue
                    count+=1;qty=t['entry_qty'];e=t['entry_premium'];x=t['exit_premium']
                    err=abs((x-e)*qty-calc_fno_costs(e,x,qty)-t['extra_cost']-t['net_pnl']);maxerror=max(maxerror,err);assert err<.0001
                    assert t['admission_id'] not in identities;identities.add(t['admission_id'])
                    assert t['initial_quantity']==qty and t['initial_entry_premium']==e and t['initial_entry_time']==t['entry_time'] and t['adds']==0
                    entry=datetime.fromisoformat(t['entry_time']);exit=datetime.fromisoformat(t['exit_time']);bar=datetime.fromisoformat(t['bar_ts']).replace(tzinfo=entry.tzinfo)
                    assert bar+timedelta(minutes=5)<=entry<=exit and entry.date()==exit.date()
                    assert entry.hour*60+entry.minute<885 and exit.hour*60+exit.minute<=910
                    if entry.date().isoformat() in X.CAL.SPECIAL:assert entry.hour*60+entry.minute<720 and exit.hour*60+exit.minute<=745
                    if t['selection_asof']:assert t['selection_asof']==entry.date().isoformat() and (t['selection_latest_label_exit'] is None or t['selection_latest_label_exit'][:10]<t['selection_asof'])
                    if t['origin']=='TPB_LOW':
                        assert t['direction']=='SHORT'
                        if t['selected_profile']=='TPB_ONE':assert qty==65
                    assert t['entry_expert']==b['members'][t['member']]['name'] and t['signal_bar']==t['bar_ts']
                key=X.Y.task_key(b,'year',tuple(obj['window']));file=HERE/'_local/evals'/f'{key}.json';trace=HERE/'_local/traces'/f'{key}.json'
                assert trace.exists(),'missing admission trace';hashes[file.relative_to(ROOT).as_posix()]=X.B.P.sha(file);hashes[trace.relative_to(ROOT).as_posix()]=X.B.P.sha(trace)
    return {'errors':errors,'fresh_replays':sum(len(bs) for ys in all_books.values() for bs in ys.values()),'closed_records':count,'max_net_error_rs':maxerror,'file_sha256':hashes}


def legacy_parity():
    refs=objects('reference');receipts={}
    for y in YEARS:
        oldkeys=load(X.B.W.LOCAL/f'keys-{y}.json')
        for name,oldname in [('MAIN','EX|MAIN'),('NO_EFF','EX|C|no_eff'),('TPB_FULL','EX|D|tpb_puts_closed')]:
            p=X.B.W.LOCAL/'evals'/f'{oldkeys[oldname]}.json';old=load(p);current=refs[y][name]
            assert len(old['trades'])==len(current['trades']),(y,name,'count')
            for a,b in zip(old['trades'],current['trades']):
                assert {k:v for k,v in a.items() if k!='member'}=={k:b.get(k) for k in a if k!='member'},(y,name,'economic parity')
                assert old['book']['members'][a['member']]['name']==b['entry_expert']
            receipts[f'{y}|{name}']={'records':len(old['trades']),'old_file_sha256':X.B.P.sha(p),'economic_parity':True}
    out=verify_books({'reference':refs});assert not out['errors'],out['errors'];out['legacy_parity']=receipts
    X.write(HERE/'reference-crosschecks.json',out);print('REFERENCES_VERIFIED',out['closed_records'],'records;9 legacy controls exact',flush=True)


def train():
    legacy_parity();refs=objects('reference');ds=sessions();every=sorted(d for v in ds.values() for d in v)
    records={p:[t for y in YEARS for t in refs[y][p]['trades']] for p in ('MAIN','TPB_ONE','NO_EFF')}
    models={d:X.P.evidence(records,d,every) for d in every}
    choices={'CORE_ADD':X.P.choose(models,('TPB_ONE',)),'CORE_SELECT':X.P.choose(models,X.P.ORDER)}
    manifest={'schema':'n02_decisions_v1','freeze_sha256':X.B.P.sha(HERE/'freeze.json'),'reference_files':{},'decisions':{},'qualified':False,'all_years_seen':True}
    for y in YEARS:
        p=HERE/f'_local/decisions-{y}.json';assert not p.exists()
        X.write(p,{policy:{d:v for d,v in days.items() if d[:4]==y} for policy,days in choices.items()})
        X.write(HERE/f'_local/models-{y}.json',{d:v for d,v in models.items() if d[:4]==y})
        manifest['decisions'][y]={'path':p.relative_to(ROOT).as_posix(),'sha256':X.B.P.sha(p),'days':len(ds[y]),'usage':{policy:dict(Counter(v['profile'] for d,v in days.items() if d[:4]==y)) for policy,days in choices.items()}}
        for key in load(HERE/f'_local/keys-reference-{y}.json').values():
            file=HERE/'_local/evals'/f'{key}.json';manifest['reference_files'][file.relative_to(ROOT).as_posix()]=X.B.P.sha(file)
    X.write(HERE/'decision-manifest.json',manifest);print('DAILY_DECISIONS_FROZEN',len(models),'as-of days',flush=True)


def compare_entries(main,candidate,traces,choices):
    key=lambda t:(t['bar_ts'],t['tradingsymbol'],t['direction'],t['entry_time'],t['entry_expert'])
    index={key(t):t for t in candidate};assert len(index)==len(candidate)
    matched=exact=0;missing=[];different=[]
    for t in main:
        hit=index.get(key(t))
        if hit:
            matched+=1
            fields=('entry_premium','entry_qty','exit_time','exit_premium','initial_stop_underlying','initial_target_underlying')
            if all(t[f]==hit[f] for f in fields):exact+=1
            else:different.append({'bar':t['bar_ts'],'expert':t['entry_expert'],'main_qty':t['entry_qty'],'candidate_qty':hit['entry_qty']})
        else:
            day=t['entry_time'][:10];profile=choices[day]['profile'];attempts=[r for r in traces if r.get('signal_bar')==t['bar_ts'] and r.get('entry_expert')==t['entry_expert']]
            missing.append({'bar':t['bar_ts'],'expert':t['entry_expert'],'selected_profile':profile,'intentional_no_eff':profile=='NO_EFF' and t['entry_expert']=='EFF',
                            'admission_attempts':[{'at':r['at'],'outcome':r['outcome'],'halts':r.get('halts')} for r in attempts],
                            'baseline_net_descriptive_not_paired_delta':t['net_pnl']})
    return {'main_entries':len(main),'candidate_entries':len(candidate),'same_signal_entry_matches':matched,'fully_matching_economic_lifecycles':exact,'changed_exposures_or_exits':different,'unretained_main':missing,
            'paired_delta_limit':'Unretained baseline net is descriptive; sizes/exits/cash differ, so it is not added as a counterfactual profit.'}


def analyze():
    refs=objects('reference');children=objects('candidate');check=verify_books({'reference':refs,'candidate':children});ds=sessions();every=sorted(d for v in ds.values() for d in v)
    def summary(source,name):
        paths={y:FIN.path(source[y][name]['trades']) for y in YEARS};daily={d:v for p in paths.values() for d,v in p['daily'].items()}
        return {'years':{y:FIN.pub(p) for y,p in paths.items()},'daily':daily,'weekly':W.weeks_of(daily,every)}
    baselines={p:summary(refs,p) for p in ('MAIN','NO_EFF','TPB_FULL','TPB_ONE')};main=baselines['MAIN'];out={}
    for policy in ('CORE_ADD','CORE_SELECT'):
        s=summary(children,policy);halves=[sum(v for d,v in s['daily'].items() if a<=d<=b) for y in YEARS for a,b in A.A.HALVES[y]]
        flags={'positive_each_year':all(s['years'][y]['net']>0 for y in YEARS),'sample':min(s['years'][y]['trades'] for y in YEARS)>=12 and sum(s['years'][y]['trades'] for y in YEARS)>=60,
               'five_halves':sum(v>=0 for v in halves)>=5,'without_year_best':all(s['years'][y]['net']-s['years'][y]['best_day']>0 for y in YEARS),
               'not_worse_each_year':all(s['years'][y]['net']>=main['years'][y]['net'] for y in YEARS),'better_total':sum(s['years'][y]['net'] for y in YEARS)>sum(main['years'][y]['net'] for y in YEARS),
               'drawdown':all(s['years'][y]['fall_pct']<=max(1.5*main['years'][y]['fall_pct'],.05) for y in YEARS),'paired_weekly':W.paired_t(s['weekly'],main['weekly'])>=2,'correct':not check['errors']}
        retention={};usage={}
        for y in YEARS:
            b=children[y][policy]['book'];key=X.Y.task_key(b,'year',tuple(children[y][policy]['window']));trace=load(HERE/'_local/traces'/f'{key}.json')['decisions']
            decisions=load(HERE/f'_local/decisions-{y}.json')[policy]
            retention[y]=compare_entries(refs[y]['MAIN']['trades'],children[y][policy]['trades'],trace,decisions)
            usage[y]=dict(Counter(t['selected_profile'] for t in children[y][policy]['trades']))
        out[policy]={'book':s,'checks':flags,'halves':halves,'entry_usage':usage,'main_opportunities':retention,'paired_t':W.paired_t(s['weekly'],main['weekly'])}
    diffs=[[a-b for a,b in zip(v['book']['weekly'],main['weekly'])] for v in out.values()]
    _,ps=A.max_t_adjusted(diffs,samples=4096,seed=110201)
    for v,p in zip(out.values(),ps):v['search_adjusted_p']=float(p);v['checks']['max_t']=bool(p<=.05);v['passes']=all(v['checks'].values())
    result={'schema':'n02_results_v1','baselines':baselines,'candidates':out,'passing':[n for n,v in out.items() if v['passes']],'correctness':check,'all_years_seen':True,'qualified':False,'can_place_orders':False}
    X.write(HERE/'results.json',result);print('CORE_RESULTS',result['passing'],'errors',check['errors'],'records',check['closed_records'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['train','analyze']);a=p.parse_args();{'train':train,'analyze':analyze}[a.action]()
