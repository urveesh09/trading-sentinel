"""Do not relabel the previous 699 raw/cache checks as newly executed."""
import json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import variant_lab as L
old=json.loads((L.PARENT/'freeze.json').read_text());new=json.loads((HERE/'freeze.json').read_text())
for y,b in old['bindings'].items():
    for k,v in b.items():
        if k=='sources':assert all(new['bindings'][y]['sources'][p]==h for p,h in v.items())
        else:assert new['bindings'][y][k]==v,(y,k)
original=HERE.parent/'2026-11-01-fno-eff-improvement'
files=[L.PARENT/'input-reuse.json',original/'input-crosschecks.json',original/'coverage.json']
L.X.write(HERE/'input-reuse.json',dict(all_inherited_bindings_identical=True,reused_files={p.relative_to(L.ROOT).as_posix():L.B.P.sha(p) for p in files},reused_raw_cache_sessions=699,fresh_raw_cache_checks_claimed=0,limitation='Original known gaps and 56 negative-volume 2025 bars preserved; not new tick/depth evidence.'))
print('INPUT_REUSE_VERIFIED')
