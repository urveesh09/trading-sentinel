"""Exact immutable economics and full lifecycle parity before candidate replay."""
import json
import anatomy_lab as L


def controls():
    out={}
    for y,files in L.reference_files().items():
        keys=json.loads((L.LOCAL/f'keys-reference-{y}.json').read_text())
        for n,oldfile in files.items():
            fresh=L.LOCAL/'evals'/f'{keys[n]}.json';old=json.loads(oldfile.read_text())['trades'];new=json.loads(fresh.read_text())['trades'];assert len(old)==len(new),(y,n,'count')
            for a,b in zip(old,new):assert {k:v for k,v in a.items() if k!='admission_id'}=={k:b.get(k) for k in a if k!='admission_id'},(y,n,'exact control')
            out[y+'|'+n]=dict(records=len(old),exact_economics=True,old_sha256=L.B.P.sha(oldfile),fresh_sha256=L.B.P.sha(fresh))
    return out


if __name__=='__main__':
    out=controls();L.X.write(L.HERE/'control-parity.json',out);print('EXACT_STATIC_CONTROLS',len(out),flush=True)
