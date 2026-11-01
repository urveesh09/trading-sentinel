"""Post-run contribution, quantity and exact-entry-pair attribution only."""
import json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path[:0]=[str(HERE),str(HERE/'reporting')]
import reconcile as A
L=A.L
def run():
    objs=A.objects();result={}
    key=lambda t:(t['entry_time'],t['tradingsymbol'],t['direction'],t['bar_ts'],t['entry_expert'])
    immutable=('initial_entry_time','initial_entry_premium','initial_quantity','initial_stop_underlying','initial_target_underlying')
    for name in objs['2024']:
        if name.endswith('|BASE'):continue
        baseline=name.rsplit('|',1)[0]+'|BASE';result[name]={}
        for y in A.YEARS:
            base=objs[y][baseline]['trades'];rows=objs[y][name]['trades'];indices={key(t):t for t in rows};assert len(indices)==len(rows)
            matched=[];changed=[];missing=[]
            for t in base:
                current=indices.get(key(t))
                if current is None:missing.append({'entry_time':t['entry_time'],'bar':t['bar_ts'],'expert':t['entry_expert'],'baseline_net_descriptive':t['net_pnl']})
                elif all(t.get(f)==current.get(f) for f in immutable):matched.append((t,current))
                else:changed.append({'entry_time':t['entry_time'],'expert':t['entry_expert'],'baseline_qty':t['entry_qty'],'candidate_qty':current['entry_qty'],'different_terms':[f for f in immutable if t.get(f)!=current.get(f)]})
            eff=lambda ts:sum(t['net_pnl'] for t in ts if t['entry_expert']=='EFF')
            net=lambda ts:sum(t['net_pnl'] for t in ts)
            effect={'baseline_net':net(base),'candidate_net':net(rows),'whole_book_delta':net(rows)-net(base),'eff_delta':eff(rows)-eff(base),
                'other_members_delta':(net(rows)-eff(rows))-(net(base)-eff(base)),'baseline_entries':len(base),'candidate_entries':len(rows),
                'same_economic_admissions':len(matched),'changed_economic_admissions':changed,'unmatched_baseline_entries':missing,
                'exact_entry_pairs_exit_delta':sum(b['net_pnl']-a['net_pnl'] for a,b in matched),'exact_entry_pairs_eff_exit_delta':sum(b['net_pnl']-a['net_pnl'] for a,b in matched if a['entry_expert']=='EFF')}
            assert abs(effect['eff_delta']+effect['other_members_delta']-effect['whole_book_delta'])<1e-8
            result[name][y]=effect
    L.X.write(HERE/'effect-accounting.json',{'status':'POST_RUN_DESCRIPTIVE_NOT_ROUTING','limit':'Exact-entry exit pairs require identical immutable economic admission terms; unmatched or resized trades are not paired. Contribution deltas account for full actual paths, not a separately tradable causal decomposition.','books':result})
    print('EFFECTS_RECONCILED',len(result),'books',flush=True)
if __name__=='__main__':run()
