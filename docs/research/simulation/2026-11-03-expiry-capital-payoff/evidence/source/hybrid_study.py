"""Materialize one-trigger original trade engines, freeze and score sequential hybrids."""
import inspect,json,socket,sys
def denied(*a,**k):raise AssertionError('Offline only')
socket.socket.connect=denied;socket.socket.connect_ex=denied;socket.create_connection=denied
import ledger_guard as G
import ledger_lab as K
import ledger_study as LS
import credit_lab as C
import credit_study as CS
import hybrid_lab as H
FILES=('HYBRID.md','hybrid_lab.py','hybrid_single.py','hybrid_study.py','test_hybrid.py')

def freeze():
    long=inspect.getsource(K.L.run_day)
    edits={
      'def run_day(t, rule, scenario="ordinary", cash=E.START_CASH, budget=E.BUDGET, details=False):':
        'def long_single(t, decision_index, signal, fixed_pick, rule, scenario="ordinary", cash=E.START_CASH, budget=E.BUDGET, details=False):',
      'dirs = directions(t, rule)':'dirs = single_dirs(t.n, decision_index, signal)',
      'pick = choose(t, i, sign, rule, room, cash)':'pick = fixed_pick if E.reserve(fixed_pick[2], fixed_pick[1]) <= room + .01 else None'
    }
    for old,new in edits.items():assert long.count(old)==1,old;long=long.replace(old,new)
    credit=inspect.getsource(C.run_day)
    edits={
      "def run_day(t,rule,scenario,cash,budget,details=False):":"def credit_single(t,decision_index,signal,rule,scenario,cash,budget,details=False):",
      'L.directions(t,K.BASE)*rule.side':'single_dirs(t.n,decision_index,signal)'
    }
    for old,new in edits.items():assert credit.count(old)==1,old;credit=credit.replace(old,new)
    p=G.HERE/'hybrid_single.py';assert not p.exists()
    p.write_text('"""Generated one-trigger trade engines; inspect asserted edits in hybrid_study.py."""\n'
       'from hybrid_lab import E,X,D,L,LOT,PARTIAL,stalled,timed_out,recover_lots,single_dirs\n'
       'from credit_lab import contracts,entry,close_quote,close_position,reserve,CLOSE_EXTRA,FEE_BUFFER\n'
       'import math\nimport numpy as np\n\n'+long+'\n\n'+credit,encoding='utf-8')
    G.save('freeze-hybrid.json',dict(head=G.git('rev-parse','HEAD').decode().strip(),files={n:G.sha(G.HERE/n) for n in FILES},
       parent=G.sha(G.HERE/'freeze-credit.json'),classification='SEEN_FULL_ELIGIBILITY_PAYOFF_ITERATION',api_calls=0))

def verify():
    CS.verify();f=json.loads((G.HERE/'freeze-hybrid.json').read_text())
    for n,h in f['files'].items():assert G.sha(G.HERE/n)==h,n
    assert G.sha(G.HERE/'freeze-credit.json')==f['parent']
    p=(G.HERE/'freeze-hybrid.json').relative_to(G.ROOT).as_posix()
    assert G.git('log','-1','--format=%H','--',p).strip()
    assert not G.git('status','--porcelain','--',p).strip()

def score():
    verify();ts=K.tapes();out={};raw={}
    for name,rule in H.ARMS.items():
        for basis,tt in [('continuous',ts[2024]+ts[2025]),('2024',ts[2024]),('2025',ts[2025])]:
            for sc in LS.SCENARIOS:
                r=H.run(tt,rule,sc,True);out[f'{name}|{basis}|{sc}']=r
                if name=='E031':
                    b=K.run(tt,K.BASE,sc,True)
                    assert r['summary']['net']==b['summary']['net'] and len(r['days'])==len(b['days'])
                    for d,old in zip(r['days'],b['days']):
                        assert d['net']==old['net'] and d['spent']==old['spent']
                        for p,q in zip(d['positions'],old['positions']):
                            assert all(p[k]==v for k,v in q.items()),(d['day'],sc)
                print('HYBRID',name,basis,sc,r['summary'],flush=True)
                if name!='E031':
                    u=H.run(tt,rule,sc,True,brakes=False);raw[f'{name}|{basis}|{sc}']=u
    for name,rule in C.ARMS.items():
        for basis,tt in [('continuous',ts[2024]+ts[2025]),('2024',ts[2024]),('2025',ts[2025])]:
            for sc in LS.SCENARIOS:
                u=H.credit_unbraked(tt,rule,sc,True);raw[f'{name}|{basis}|{sc}']=u
    G.save('hybrid-results.json',dict(runs=out,baseline_event_parity=True,margin_qualified=False))
    G.save('unbraked-results.json',dict(runs=raw,diagnostics_only=True,no_strategy_selected=True))

if __name__=='__main__':globals()[sys.argv[1]]()
