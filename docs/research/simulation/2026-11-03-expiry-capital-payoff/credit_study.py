"""Freeze directional credit economics before any primary score."""
from dataclasses import asdict
import json,socket,sys
def denied(*a,**k):raise AssertionError('Offline only')
socket.socket.connect=denied;socket.socket.connect_ex=denied;socket.create_connection=denied
import ledger_guard as G
import ledger_lab as K
import ledger_study as LS
import credit_lab as C

FILES=('CREDIT.md','credit_lab.py','credit_study.py','test_credit.py')
def freeze():
    G.save('freeze-credit.json',dict(head=G.git('rev-parse','HEAD').decode().strip(),files={n:G.sha(G.HERE/n) for n in FILES},
        parent=G.sha(G.HERE/'freeze-ledger.json'),arms={n:asdict(r) for n,r in C.ARMS.items()},
        classification='SEEN_LEGACY_YEARS_MARGIN_ATOMIC_EXECUTION_UNQUALIFIED',api_calls=0,year2023_read=False))

def verify():
    LS.verify();f=json.loads((G.HERE/'freeze-credit.json').read_text())
    for n,h in f['files'].items():assert G.sha(G.HERE/n)==h,n
    assert G.sha(G.HERE/'freeze-ledger.json')==f['parent']
    p=(G.HERE/'freeze-credit.json').relative_to(G.ROOT).as_posix()
    assert G.git('log','-1','--format=%H','--',p).strip()
    assert not G.git('status','--porcelain','--',p).strip()

def score():
    verify();ts=K.tapes();out={}
    for name,rule in C.ARMS.items():
        for basis,tt in [('continuous',ts[2024]+ts[2025]),('2024',ts[2024]),('2025',ts[2025])]:
            for sc in LS.SCENARIOS:
                r=C.run(tt,rule,sc,True);out[f'{name}|{basis}|{sc}']=r
                print(name,basis,sc,r['summary'],'unavailable later',len(r.get('unavailable_after_unresolved',[])),flush=True)
    G.save('credit-results.json',dict(runs=out,margin_qualified=False,execution='Hypothetical basket/short-first close with explicit long-only residual marks'))

if __name__=='__main__':globals()[sys.argv[1]]()
