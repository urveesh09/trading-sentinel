"""Freeze only causal decisions after exact static parity, before candidate replay."""
import json
from pathlib import Path
import subprocess
import variant_lab as L


def controls():
    excluded = {'admission_id','n03_context','n04_context','n05_context'}
    out = {}
    for y, files in L.reference_files().items():
        keys = json.loads((L.LOCAL/f'keys-reference-{y}.json').read_text())
        for variant, oldfile in files.items():
            newfile = L.LOCAL/'evals'/f'{keys[variant]}.json'
            a = json.loads(oldfile.read_text())['trades']
            b = json.loads(newfile.read_text())['trades']
            assert len(a) == len(b), (y,variant,'reference count')
            for old,new in zip(a,b):
                assert {k:v for k,v in old.items() if k not in excluded} == {k:new.get(k) for k in old if k not in excluded}, (y,variant,'control economics')
            out[y+'|'+variant] = dict(records=len(a),exact=True,old_sha256=L.B.P.sha(oldfile),fresh_sha256=L.B.P.sha(newfile))
    return out


def run():
    import sys
    sys.path.insert(0,str(L.P.P.E.PARENT))
    import analyze_core as A
    parity = controls()
    manifests, references, counts = {}, {}, {}
    for y, files in L.reference_files().items():
        records = {v:json.loads(p.read_text())['trades'] for v,p in files.items()}
        ds = sorted(A.sessions()[y])
        models, decisions = {}, {}
        for policy,anchor in [('MAIN_ANCHOR','MAIN'),('STRUCT_ANCHOR','STRUCT30')]:
            models[policy] = {d:L.R.evidence(records,d,ds,anchor) for d in ds}
            decisions[policy] = L.R.choose(models[policy],anchor)
        L.X.write(L.LOCAL/f'models-{y}.json',models)
        file = L.LOCAL/f'decisions-{y}.json'
        L.X.write(file,decisions)
        manifests[y] = dict(sha256=L.B.P.sha(file),sessions=len(ds),models_sha256=L.B.P.sha(L.LOCAL/f'models-{y}.json'))
        from collections import Counter
        counts[y] = {p:dict(Counter(d['variant'] for d in days.values())) for p,days in decisions.items()}
        for p in files.values():references[p.relative_to(L.ROOT).as_posix()]=L.B.P.sha(p)
    assert not (L.HERE/'decision-manifest.json').exists()
    L.X.write(L.HERE/'decision-manifest.json',dict(schema='n06_decisions_v1',pre_candidate_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=L.ROOT).decode().strip(),
        decisions=manifests,reference_files=references,static_controls=parity,selection_counts=counts,qualified=False,all_years_seen=True))
    print('MODELS_BUILT_STATIC_PARITY',len(parity),'SELECTION_COUNTS',counts,flush=True)


if __name__ == '__main__':run()
