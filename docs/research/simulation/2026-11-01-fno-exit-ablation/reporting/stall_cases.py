"""Paired exit labels only when complete immutable admissions match."""
import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import analyze_exit as A
L=A.L
def run():
    objects=A.objects();records=[];unavailable=[]
    key=lambda t:(t['entry_time'],t['tradingsymbol'],t['direction'],t['bar_ts'],t['entry_expert'])
    fields=('initial_entry_time','initial_entry_premium','initial_quantity','initial_stop_underlying','initial_target_underlying')
    for y,books in objects.items():
        name='NORMAL|BALANCED_RETEST|STALL_ONLY';baseline=books['NORMAL|BALANCED_RETEST|BASE']['trades'];index={key(t):t for t in baseline};assert len(index)==len(baseline)
        for t in books[name]['trades']:
            if t['entry_expert']!='EFF' or t.get('n04_exit_context',{}).get('action')!='STALL30' or t['exit_reason']!='time_stop':continue
            old=index.get(key(t))
            if old is None or not all(old.get(f)==t.get(f) for f in fields):unavailable.append({'year':y,'admission_id':t['admission_id'],'reason':'no exact immutable economic admission pair'});continue
            econ={f:t[f] for f in fields};econ.update(tradingsymbol=t['tradingsymbol'],direction=t['direction'])
            records.append({'year':y,'base_admission_id':old['admission_id'],'stall_admission_id':t['admission_id'],'economic_fingerprint':hashlib.sha256(json.dumps(econ,sort_keys=True).encode()).hexdigest(),'immutable_terms':econ,
                'known_when_stall_exit_chosen':t['n04_exit_context'],'later_paired_exit_label':{'base_exit_time':old['exit_time'],'stall_exit_time':t['exit_time'],'base_net':old['net_pnl'],'stall_net':t['net_pnl'],'delta':t['net_pnl']-old['net_pnl']}})
    summary={y:{'pairs':sum(t['year']==y for t in records),'paired_delta':sum(t['later_paired_exit_label']['delta'] for t in records if t['year']==y),'helped':sum(t['year']==y and t['later_paired_exit_label']['delta']>0 for t in records),'hurt':sum(t['year']==y and t['later_paired_exit_label']['delta']<0 for t in records)} for y in A.YEARS}
    L.X.write(HERE/'stall-case-audit.json',{'status':'POST_RUN_DESCRIPTIVE_NO_NEW_GATE','exact_economic_pairs':records,'unavailable_pairs':unavailable,'summary':summary,'limit':'Later base exit outcomes are labels only; not inputs available at the early decision. Resized/unmatched admissions remain unavailable, never paired by ticker/date.'});print('STALL_CASES',summary,flush=True)
if __name__=='__main__':run()
