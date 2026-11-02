"""Hash/source invariance proof for reusing N03 input/coverage checks."""
import json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import exit_lab as L
def run():
    old=json.loads((L.PARENT/'freeze.json').read_text());new=json.loads((HERE/'freeze.json').read_text());checks=[]
    for y,b in old['bindings'].items():
        for key,value in b.items():
            if key=='sources':assert all(new['bindings'][y]['sources'][p]==v for p,v in value.items())
            else:assert new['bindings'][y][key]==value,(y,key)
        checks.append({'year':y,'all_inherited_source_data_calendar_daily_memo_decision_bindings_identical':True})
    reused={}
    for name in ('input-crosschecks.json','coverage.json','path-crosschecks.json'):
        p=L.PARENT/name;reused[name]={'path':p.relative_to(L.ROOT).as_posix(),'sha256':L.B.P.sha(p)}
    assert sum(v['sessions'] for v in json.loads((L.PARENT/'input-crosschecks.json').read_text())['years'])==699
    L.X.write(HERE/'input-reuse.json',{'schema':'n04_reused_input_evidence_v1','checks':checks,'reused_files':reused,'reused_raw_cache_sessions':699,'fresh_raw_cache_checks_claimed':0,
        'limit':'Unchanged N03 data/cache/source and dated clocks proven by bound hashes. Old input checks are reused, not recounted as fresh; all new admissions/prices/exits independently audited.'});print('INPUT_REUSE_VERIFIED',flush=True)
if __name__=='__main__':run()
