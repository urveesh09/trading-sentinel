"""Retained audit fix: transient prefix objects must not reuse an id-keyed cache."""
import json,sys
import numpy as np
import payoff_audit as A
G,K,C=A.G,A.K,A.C

def prefixes(ts,keys):
    lookup={t.day:t for tt in ts.values() for t in tt};checks=0
    for day,i in sorted(keys):
        t=lookup[day];end=i+1
        p=K.D.Tape(t.day,t.x[:end].copy(),t.f[:end].copy(),t.q[:end].copy(),t.strikes.copy(),t.kinds.copy(),list(t.symbols),list(t.now[:end]),t.minute[:end].copy(),t.invalid)
        p.oi=t.oi[:end].copy()
        # All scored rules use no confirmation. Bypass the old id(t)-keyed
        # memoizer for temporary rebuilt prefixes; full-day objects remain alive.
        assert K.BASE.confirmation=='none'
        full=K.X.directions(t,K.BASE);prefix=K.X.directions(p,K.BASE)
        assert np.array_equal(K.L.directions(t,K.BASE),full)
        assert np.array_equal(prefix,full[:end])
        d=int(full[i])
        for room in (1250.,625.):
            assert K.L.choose(p,i,d,K.BASE,room,25000.)==K.L.choose(t,i,d,K.BASE,room,25000.)
        assert C.contracts(p,i,d,C.ARMS['CREDIT_8M'])==C.contracts(t,i,d,C.ARMS['CREDIT_8M'])
        checks+=1
    return checks

def freeze():
    G.save('audit-failure.json',dict(command='python payoff_audit.py',exit_code=1,
        error='IndexError: index 338 is out of bounds for axis 0 with size 302',
        cause='Old pure-signal memoizer keys by id(t). Temporary prefix objects can reuse freed ids. Full scored tapes remain alive and do not collide.',
        correction='Use uncached original signal function on rebuilt prefixes; compare entire prefix and cached full signal.',
        primary_scores_changed=False))
    G.save('freeze-audit-v2.json',dict(files={'payoff_audit_v2.py':G.sha(__file__)},
        parent=G.sha(G.HERE/'freeze-diagnostics.json'),scores_changed=False))

def main():
    f=json.loads((G.HERE/'freeze-audit-v2.json').read_text())
    for n,want in f['files'].items():assert G.sha(G.HERE/n)==want
    assert f['parent']==G.sha(G.HERE/'freeze-diagnostics.json')
    path=(G.HERE/'freeze-audit-v2.json').relative_to(G.ROOT).as_posix()
    assert G.git('log','-1','--format=%H','--',path).strip() and not G.git('status','--porcelain','--',path).strip()
    A.prefixes=prefixes;A.main()

if __name__=='__main__':freeze() if len(sys.argv)>1 and sys.argv[1]=='freeze' else main()
