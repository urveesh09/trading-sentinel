from dataclasses import replace,asdict
import json,sys
import structure_checkpoint as C
import mechanisms as M
import payoff as P
import run_study as R

ARMS={'DEBIT_VERTICAL':P.BASE,'BUTTERFLY':replace(P.BASE,shape='butterfly')}
FILES=('ROUND3.md','payoff.py','round3.py','test_payoff.py')

def freeze():
    R.save('freeze-round3.json',dict(head=C.git('rev-parse','HEAD').decode().strip(),
        files={n:C.sha(M.HERE/n) for n in FILES},prior=C.sha(M.HERE/'freeze-round1.json'),
        arms={k:asdict(v) for k,v in ARMS.items()},classification='SEEN_DEVELOPMENT_SIMULTANEOUS_PACK_ASSUMPTION'))

def verify():
    R.verify();f=json.loads((M.HERE/'freeze-round3.json').read_text())
    for n,h in f['files'].items():assert C.sha(M.HERE/n)==h,n
    path=(M.HERE/'freeze-round3.json').relative_to(C.ROOT).as_posix()
    assert C.git('log','-1','--format=%H','--',path).strip()
    assert not C.git('status','--porcelain','--',path).strip()

def score():
    verify();ts=M.tapes();out={}
    for name,rule in ARMS.items():
        for basis,tt in [('continuous',ts[2024]+ts[2025]),('2024',ts[2024]),('2025',ts[2025])]:
            for sc in R.SCENARIOS:
                r=P.run(tt,rule,sc,True);out[f'{name}|{basis}|{sc}']=r
                print(name,basis,sc,{k:r['summary'][k] for k in ('net','without_best','worst','drawdown','trades','fees','unresolved')},flush=True)
    R.save('round3-results.json',dict(runs=out))

if __name__=='__main__':globals()[sys.argv[1]]()
