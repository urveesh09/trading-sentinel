"""Post-run accounting descriptions, never reused as training or routing."""
import json,sys
from collections import defaultdict
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import analyze_core as A
X=A.X
def run():
    refs=A.objects('reference');children=A.objects('candidate');result={}
    for policy in ('CORE_ADD','CORE_SELECT'):
        result[policy]={}
        for y in A.YEARS:
            main=refs[y]['MAIN']['trades'];actual=children[y][policy]['trades'];base=sum(t['net_pnl'] for t in main)
            m=[t for t in actual if t['origin']=='MAIN'];extra=[t for t in actual if t['origin']=='TPB_LOW']
            mainnet=sum(t['net_pnl'] for t in m);extranet=sum(t['net_pnl'] for t in extra)
            assert abs(mainnet+extranet-sum(t['net_pnl'] for t in actual))<1e-8
            byprofile=defaultdict(list)
            for t in actual:byprofile[t['selected_profile']].append(t)
            result[policy][y]={'main_baseline_net':base,'actual_main_origin_net':mainnet,'actual_low_addition_net':extranet,'low_additions':len(extra),
                'main_origin_net_difference':mainnet-base,'total_difference':mainnet+extranet-base,
                'profile_admissions':{p:{'trades':len(rs),'net':sum(t['net_pnl'] for t in rs)} for p,rs in byprofile.items()},
                'limit':'Accounting decomposition of two complete paths, not isolated causal alpha. MAIN-origin difference includes changed sizing/brakes/omissions. Do not add displaced baseline trades back.'}
    X.write(HERE/'outcome-accounting.json',{'status':'POST_RUN_DESCRIPTIVE_NOT_ROUTING','years':result})
    print(json.dumps(result,indent=2))
if __name__=='__main__':run()
