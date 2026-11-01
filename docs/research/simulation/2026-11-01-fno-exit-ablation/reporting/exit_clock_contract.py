"""Explain soft-clock redundancy using effective params and exact lifecycles."""
import json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path[:0]=[str(HERE)]
import analyze_exit as A
L=A.L
def run():
    L.B.O27F.deny_network();L.B.L._init();params={k:getattr(L.X.settings,k) for k in ('FNO_TIME_STOP_MIN_R','FNO_TIME_STOP_RESPECTS_PREMIUM','FNO_HARD_FLAT_MIN')}
    books=A.objects();pairs={};total=0
    for y,objects in books.items():
        for name,obj in objects.items():
            if not name.endswith('|BASE'):continue
            other=name.rsplit('|',1)[0]+'|CONTINUE_ONLY';a=obj['trades'];b=objects[other]['trades'];assert len(a)==len(b)
            for x,z in zip(a,b):assert {k:v for k,v in x.items() if k!='admission_id' and not k.startswith('n04_')}=={k:v for k,v in z.items() if k!='admission_id' and not k.startswith('n04_')}
            pairs[y+'|'+name]={'closed_records':len(a),'exact_entry_exit_quantity_price_fee_economics':True};total+=len(a)
    combined_pairs={};fields=('entry_time','bar_ts','tradingsymbol','direction','entry_premium','entry_qty','lots_at_exit','exit_time','exit_premium','exit_reason','gross_pnl','net_pnl','extra_cost','member','origin','initial_stop_underlying','initial_target_underlying','initial_quantity')
    for y,objects in books.items():
        oldkeys=A.load(L.OLD/f'keys-{y}.json')
        for prefix in ('NORMAL|MAIN','NORMAL|TPB_ONE','NORMAL|CORE_SELECT','ONE|MAIN'):
            old=A.load(L.OLD/'evals'/f'{oldkeys[prefix+"|HORIZON"]}.json')['trades'];new=objects[prefix+'|STALL_ONLY']['trades'];assert len(old)==len(new)
            for a,b in zip(old,new):assert {f:a.get(f) for f in fields}=={f:b.get(f) for f in fields},(y,prefix,'combined/stall parity')
            combined_pairs[y+'|'+prefix]={'closed_records':len(old),'exact_economic_parity':True}
    L.X.write(HERE/'exit-clock-contract.json',{'effective_parameters':params,'exit_rules_source_sha256':L.B.P.sha(L.ROOT/'python-engine/fno_exit_rules.py'),'extension_requires_progress_r':1.,'original_clock_is_soft_stagnation_check_not_maximum_hold':True,
        'extension_redundant_under_current_progress_threshold':params['FNO_TIME_STOP_MIN_R']<=1.,'base_continue_annual_pairs':len(pairs),'matched_closed_lifecycles':total,'exact_parity':pairs,'n03_combined_vs_n04_stall_parity':combined_pairs,
        'reason':'Original time-stop only closes untrailed positions below MIN_R progress. CONTINUE_ONLY requires>=1R, already exempt when MIN_R<=1. Changing60 to90 does not improve these decisions; neither value is a maximum holding cap. Stops/trail/hard-flat remain active.'})
    print('CLOCK_CONTRACT',params,len(pairs),total,flush=True)
if __name__=='__main__':run()
