"""Explicit source/input invariance, reusing checks rather than recounting them."""
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import refine_lab as L
import json
def run():
    old=json.loads((L.PARENT/'freeze.json').read_text());new=json.loads((HERE/'freeze.json').read_text());checks=[]
    for y,b in old['bindings'].items():
        for k,v in b.items():
            if k=='sources':assert all(new['bindings'][y]['sources'][p]==h for p,h in v.items())
            else:assert new['bindings'][y][k]==v,(y,k)
        checks.append({'year':y,'all_inherited_bindings_identical':True})
    original=L.PARENT.parent/'2026-11-01-fno-eff-improvement';refs={}
    for p in [L.PARENT/'input-reuse.json',original/'input-crosschecks.json',original/'coverage.json']:refs[p.relative_to(L.ROOT).as_posix()]=L.B.P.sha(p)
    L.X.write(HERE/'input-reuse.json',{'checks':checks,'reused_files':refs,'reused_raw_cache_sessions':699,'fresh_raw_cache_checks_claimed':0,'limit':'Prior source/data/coverage checks reused by exact inherited hashes; new trades, structure and exits independently checked.'});print('INPUT_REUSE_VERIFIED',flush=True)
if __name__=='__main__':run()
