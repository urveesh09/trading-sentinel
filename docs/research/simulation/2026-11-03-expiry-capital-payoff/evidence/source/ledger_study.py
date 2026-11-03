"""Freeze original-policy cash-ledger experiments, then preserve every scored result."""
from dataclasses import asdict
import inspect,json,socket,sys
def denied(*a,**k):raise AssertionError('Offline only')
socket.socket.connect=denied;socket.socket.connect_ex=denied;socket.create_connection=denied
import ledger_guard as G
import ledger_lab as K

SCENARIOS=('ordinary','adverse','catastrophe')
FILES=('PLAN.md','ledger_guard.py','ledger_lab.py','ledger_day.py','ledger_study.py','test_ledger.py')

def freeze():
    source=inspect.getsource(K.L.run_day)
    edits={
      'spent += risk':'check_admission(rule, positions, budget, risk)\n            spent += risk',
      'or len(positions) >= rule.slots:':'or (rule.mode == "baseline" and len(positions) >= rule.slots):',
      'room = min(E.BUDGET / rule.slots, budget - spent, cash)':'room = room_for(rule, positions, spent, budget, cash)\n        set_phase(rule, positions)',
      'assert spent <= budget + .02 and net >= -spent - .03':'assert (rule.mode != "baseline" or spent <= budget + .02) and net >= -budget - .03'
    }
    for old,new in edits.items():assert source.count(old)==1,old;source=source.replace(old,new)
    p=G.HERE/'ledger_day.py';assert not p.exists()
    p.write_text('"""Generated original E03.1 loop with four asserted ledger hooks; inspect ledger_study.py."""\n'
       'from ledger_lab import E, X, LOT, PARTIAL, directions, choose, stalled, timed_out, recover_lots, room_for, check_admission, set_phase\n'
       'import math\nimport numpy as np\n\n'+source,encoding='utf-8')
    G.save('freeze-ledger.json',dict(head=G.git('rev-parse','HEAD').decode().strip(),files={n:G.sha(G.HERE/n) for n in FILES},
        initial_sha256=G.sha(G.HERE/'initial.json'),arms={n:asdict(r) for n,r in K.ARMS.items()},scenarios=SCENARIOS,
        classification='SEEN_2024_2025_RESEARCH',year2023_read=False,api_calls=0))

def verify():
    f=json.loads((G.HERE/'freeze-ledger.json').read_text())
    for n,h in f['files'].items():assert G.sha(G.HERE/n)==h,n
    assert G.sha(G.HERE/'initial.json')==f['initial_sha256']
    p=(G.HERE/'freeze-ledger.json').relative_to(G.ROOT).as_posix()
    assert G.git('log','-1','--format=%H','--',p).strip()
    assert not G.git('status','--porcelain','--',p).strip()

def score():
    verify();ts=K.tapes();out={};count=0
    for y,tt in ts.items():
        for sc in SCENARIOS:
            old=K.R.run(tt,K.R.BASE,sc,True);new=K.run(tt,K.BASE,sc,True)
            assert old['days']==new['days'] and old['summary']==new['summary'];count+=old['summary']['trades']
    print('BASELINE_EXACT',count,'position/event histories',flush=True)
    for name,rule in K.ARMS.items():
        for basis,tt in [('continuous',ts[2024]+ts[2025]),('2024',ts[2024]),('2025',ts[2025])]:
            for sc in SCENARIOS:
                r=K.run(tt,rule,sc,True);out[f'{name}|{basis}|{sc}']=r
                print(name,basis,sc,r['summary'],r.get('unavailable_after_unresolved',[]),flush=True)
    G.save('ledger-results.json',dict(parity_positions=count,mismatches=0,runs=out))

if __name__=='__main__':globals()[sys.argv[1]]()
