"""Actual full-path accounting and exact-entry exits against both references."""
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import analyze_refine as A
L=A.L
def run():
    objects=A.objects();result={};key=lambda t:(t['entry_time'],t['tradingsymbol'],t['direction'],t['bar_ts'],t['entry_expert']);fields=('initial_entry_time','initial_entry_premium','initial_quantity','initial_stop_underlying','initial_target_underlying')
    for sizing in ('NORMAL','ONE'):
        for mode in ('DELAY45','STRUCT30'):
            name=f'{sizing}|BALANCED_RETEST|{mode}';result[name]={}
            for reference in ('BASE','STALL30'):
                result[name][reference]={}
                for y in A.YEARS:
                    base=objects[y][f'{sizing}|BALANCED_RETEST|{reference}']['trades'];rows=objects[y][name]['trades'];index={key(t):t for t in rows};assert len(index)==len(rows);pairs=[];changed=[];missing=[]
                    for t in base:
                        hit=index.get(key(t))
                        if hit is None:missing.append({'admission_id':t['admission_id'],'entry_time':t['entry_time'],'expert':t['entry_expert']})
                        elif all(t.get(f)==hit.get(f) for f in fields):pairs.append((t,hit))
                        else:changed.append({'entry_time':t['entry_time'],'expert':t['entry_expert'],'baseline_qty':t['entry_qty'],'candidate_qty':hit['entry_qty'],'different_terms':[f for f in fields if t.get(f)!=hit.get(f)]})
                    net=lambda rs:sum(t['net_pnl'] for t in rs);eff=lambda rs:sum(t['net_pnl'] for t in rs if t['entry_expert']=='EFF')
                    v={'baseline_net':net(base),'candidate_net':net(rows),'whole_book_delta':net(rows)-net(base),'eff_delta':eff(rows)-eff(base),'other_member_delta':(net(rows)-eff(rows))-(net(base)-eff(base)),'same_economic_admissions':len(pairs),'changed_economic_admissions':changed,'unmatched_baseline_entries':missing,
                        'paired_exit_delta':sum(b['net_pnl']-a['net_pnl'] for a,b in pairs),'paired_eff_exit_delta':sum(b['net_pnl']-a['net_pnl'] for a,b in pairs if a['entry_expert']=='EFF')}
                    assert abs(v['eff_delta']+v['other_member_delta']-v['whole_book_delta'])<1e-8;result[name][reference][y]=v
    L.X.write(HERE/'effect-accounting.json',{'status':'POST_RUN_DESCRIPTIVE_NOT_ROUTING','limit':'Pairs require identical immutable economics; changed/missing/resized entries unpaired. Complete-path contribution differences are accounting, not separately tradable alpha.','books':result});print('EFFECTS_RECONCILED',flush=True)
if __name__=='__main__':run()
