"""Complete opportunity costs; retain adverse exact pairs and changed-size paths."""
import json,math,sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import analyze_anatomy as A
L=A.L
FIELDS=('entry_time','tradingsymbol','direction','entry_premium','entry_underlying','entry_qty','initial_stop_underlying','initial_target_underlying','bar_ts','entry_expert')


def run():
    objs=A.objects();out={};changed=[];same_candidates={}
    for y,books in objs.items():
        for sizing in ('NORMAL','ONE','NO_EXTRA_STRESS'):
            a=books[sizing+'|PREMIUM_STALL']['trades'];b=books[sizing+'|STRUCT_OR_PREMIUM']['trades'];economic_fields=(*FIELDS,'exit_time','exit_premium','exit_reason','net_pnl')
            same_candidates[y+'|'+sizing]=len(a)==len(b) and all(tuple(t.get(k) for k in economic_fields)==tuple(u.get(k) for k in economic_fields) for t,u in zip(a,b))
            for mode in ('PREMIUM_STALL','STRUCT_OR_PREMIUM'):
                for reference in ('STALL30','STRUCT30'):
                    candidate=books[sizing+'|'+mode]['trades'];baseline=books[sizing+'|'+reference]['trades'];a={tuple(t[k] for k in FIELDS):t for t in candidate};b={tuple(t[k] for k in FIELDS):t for t in baseline};assert len(a)==len(candidate) and len(b)==len(baseline)
                    common=a.keys()&b.keys();paired=math.fsum(a[k]['net_pnl']-b[k]['net_pnl'] for k in common);new=math.fsum(a[k]['net_pnl'] for k in a.keys()-b.keys());old=math.fsum(b[k]['net_pnl'] for k in b.keys()-a.keys());total=math.fsum(t['net_pnl'] for t in candidate)-math.fsum(t['net_pnl'] for t in baseline);assert abs(total-paired-new+old)<1e-7
                    effects=[a[k]['net_pnl']-b[k]['net_pnl'] for k in common if a[k]['net_pnl']!=b[k]['net_pnl']]
                    label=y+'|'+sizing+'|'+mode+'_vs_'+reference
                    out[label]=dict(total_delta=total,paired_exit_delta=paired,unpaired_candidate_net=new,unpaired_reference_net=old,identical_economic_admissions=len(common),candidate_only=len(a.keys()-b.keys()),reference_only=len(b.keys()-a.keys()),
                        helped_pairs=sum(v>0 for v in effects),hurt_pairs=sum(v<0 for v in effects),helped_net=math.fsum(v for v in effects if v>0),hurt_net=math.fsum(v for v in effects if v<0))
                    for k in sorted(common):
                        a1,b1=a[k],b[k]
                        if a1['net_pnl']==b1['net_pnl'] and a1['exit_time']==b1['exit_time']:continue
                        changed.append(dict(comparison=label,candidate_admission=a1['admission_id'],reference_admission=b1['admission_id'],immutable_terms={f:a1[f] for f in FIELDS},known_at_candidate_exit=a1.get('n07_exit_context'),
                            later_labels=dict(candidate_net=a1['net_pnl'],reference_net=b1['net_pnl'],delta=a1['net_pnl']-b1['net_pnl'],candidate_exit=a1['exit_time'],reference_exit=b1['exit_time'])))
    L.X.write(HERE/'repair-effects.json',dict(comparisons=out,changed_exact_pairs=changed,candidate_pair_equivalence=same_candidates,economic_attribution_errors=0,
        limits='Unmatched/resized evidence is not a pure paired-exit delta; full account differences retained. Later recovery labels never become current decision inputs. No perfect-peak fill credit.'))
    print('REPAIR_EFFECTS_VERIFIED',len(out),'changed',len(changed),'candidate_equivalence',same_candidates,flush=True)


if __name__=='__main__':run()
