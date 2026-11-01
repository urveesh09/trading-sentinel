"""Exact-admission exit effects; no fitted recovery rule or entry confidence."""
import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import analyze_refine as A
L=A.L
def run():
    objs=A.objects();records=[];unavailable=[];coverage={};fields=('initial_entry_time','initial_entry_premium','initial_quantity','initial_stop_underlying','initial_target_underlying');key=lambda t:(t['entry_time'],t['tradingsymbol'],t['direction'],t['bar_ts'],t['entry_expert'])
    for y,books in objs.items():
        base=books['NORMAL|BALANCED_RETEST|BASE']['trades'];index={key(t):t for t in base};assert len(index)==len(base)
        for mode in ('DELAY45','STRUCT30'):
            rows=books['NORMAL|BALANCED_RETEST|'+mode]['trades'];matched=0;non_eff_exact=0
            for t in rows:
                old=index.get(key(t))
                if old is None or not all(old.get(f)==t.get(f) for f in fields):
                    unavailable.append({'year':y,'mode':mode,'admission_id':t['admission_id'],'reason':'no exact immutable economic pair'});continue
                matched+=1
                changed=any(old[f]!=t[f] for f in ('exit_time','exit_premium','exit_reason','net_pnl'))
                if t['entry_expert']!='EFF':
                    if mode=='STRUCT30':assert not changed
                    non_eff_exact+=int(not changed);continue
                if not changed:continue
                econ={f:t[f] for f in fields};econ.update(tradingsymbol=t['tradingsymbol'],direction=t['direction']);label={'base_exit_time':old['exit_time'],'candidate_exit_time':t['exit_time'],'base_net':old['net_pnl'],'candidate_net':t['net_pnl'],'delta':t['net_pnl']-old['net_pnl']}
                records.append({'year':y,'mode':mode,'base_admission_id':old['admission_id'],'candidate_admission_id':t['admission_id'],'economic_fingerprint':hashlib.sha256(json.dumps(econ,sort_keys=True).encode()).hexdigest(),'immutable_terms':econ,'known_at_review':t['n05_exit_context'],'later_outcome_labels':label})
            coverage[y+'|'+mode]={'baseline_entries':len(base),'candidate_entries':len(rows),'identical_economic_admissions':matched,'unchanged_non_eff_lifecycles':non_eff_exact}
            if mode=='STRUCT30':assert matched==len(base)==len(rows)
    assert all(r['later_outcome_labels']['candidate_net']<=0 and r['later_outcome_labels']['delta']>0 for r in records if r['mode']=='STRUCT30')
    summaries={m:{y:{'changed_eff_exit_pairs':sum(r['mode']==m and r['year']==y for r in records),'paired_exit_delta':sum(r['later_outcome_labels']['delta'] for r in records if r['mode']==m and r['year']==y),'candidate_loss_exits':sum(r['mode']==m and r['year']==y and r['later_outcome_labels']['candidate_net']<=0 for r in records)} for y in A.YEARS} for m in ('DELAY45','STRUCT30')}
    L.X.write(HERE/'review-case-audit.json',{'status':'POST_RUN_DESCRIPTIVE_NO_ENTRY_CONFIDENCE_MODEL','records':records,'unavailable_pairs':unavailable,'admission_coverage':coverage,'summary':summaries,'limit':'All paired initial economics match. Later original outcomes are labels, never early inputs. Relative loss reduction is not proof a trade will profit or authority to increase its size.'});print('REVIEW_CASES',summaries,flush=True)
if __name__=='__main__':run()
