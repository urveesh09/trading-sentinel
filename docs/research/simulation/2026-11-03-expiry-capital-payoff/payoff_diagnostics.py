"""Fixed nonselective sensitivity checks; no new primary candidate."""
from dataclasses import replace
import json,socket,sys
def denied(*a,**k):raise AssertionError('Offline only')
socket.socket.connect=denied;socket.socket.connect_ex=denied;socket.create_connection=denied
import ledger_guard as G
import ledger_lab as K
import credit_lab as C
import hybrid_lab as H
import hybrid_study as HS
FILES=('DIAGNOSTICS.md','payoff_diagnostics.py','payoff_audit.py')

def freeze():
    G.save('freeze-diagnostics.json',dict(files={n:G.sha(G.HERE/n) for n in FILES},
        parent=G.sha(G.HERE/'freeze-hybrid.json'),classification='SEEN_DIAGNOSTICS_NO_SELECTION'))

def verify():
    HS.verify();f=json.loads((G.HERE/'freeze-diagnostics.json').read_text())
    for n,h in f['files'].items():assert G.sha(G.HERE/n)==h,n
    assert f['parent']==G.sha(G.HERE/'freeze-hybrid.json')
    p=(G.HERE/'freeze-diagnostics.json').relative_to(G.ROOT).as_posix()
    assert G.git('log','-1','--format=%H','--',p).strip() and not G.git('status','--porcelain','--',p).strip()

def score():
    verify();ts=K.tapes();out={};original=C.leg_price
    def friction(t,i,j,buy,scenario,mark=False):
        p=original(t,i,j,buy,scenario,mark)
        if p is None or mark:return p
        p=K.E.up(p*1.01+.05) if buy else K.E.down(p*.99-.05)
        return p if p>0 else None
    rules={'REVERSE':replace(C.ARMS['CREDIT_8M'],side=-1),
           'HOLD6':replace(C.ARMS['CREDIT_8M'],hold=6),'HOLD10':replace(C.ARMS['CREDIT_8M'],hold=10),
           'WIDTH100':replace(C.ARMS['CREDIT_8M'],width=100),'EXTRA_FRICTION':C.ARMS['CREDIT_8M']}
    for label,rule in rules.items():
        C.leg_price=friction if label=='EXTRA_FRICTION' else original
        for brakes in (True,False):
            for basis,tt in [('continuous',ts[2024]+ts[2025]),('2024',ts[2024]),('2025',ts[2025])]:
                for sc in ('ordinary','adverse'):
                    r=(C.run if brakes else H.credit_unbraked)(tt,rule,sc,True)
                    out[f'{label}|{brakes}|{basis}|{sc}']=r
    C.leg_price=original
    G.save('diagnostics.json',dict(runs=out,selected_candidate=None,diagnostics_only=True))
    print('FIXED_DIAGNOSTICS',len(out),'runs; no selection')

if __name__=='__main__':globals()[sys.argv[1]]()
