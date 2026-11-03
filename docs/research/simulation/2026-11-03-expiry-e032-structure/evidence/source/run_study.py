"""Committed freezes, event parity and two mechanism scores; immutable outputs."""
from dataclasses import asdict,replace
import argparse,json,subprocess,time
import mechanisms as M
import structure_checkpoint as C

ARMS={'E031':M.BASE,'PATIENT':replace(M.BASE,mechanism='patient'),
      'OPTION_LED':replace(M.BASE,mechanism='option_led')}
SCENARIOS=('ordinary','adverse','catastrophe')
FILES=('PLAN.md','mechanisms.py','mechanism_day.py','build_loop.py','run_study.py','test_mechanisms.py','structure_checkpoint.py')

def save(name,obj):
    p=M.HERE/name;assert not p.exists(),p
    M.D.dump(p,obj)

def freeze():
    save('freeze-round1.json',dict(head=C.git('rev-parse','HEAD').decode().strip(),
        files={n:C.sha(M.HERE/n) for n in FILES},initial_sha256=C.sha(M.HERE/'initial.json'),
        arms={k:asdict(v) for k,v in ARMS.items()},scenarios=SCENARIOS,
        classification='SEEN_DEVELOPMENT_NOT_OUT_OF_SAMPLE',year2023_read=False,api_calls=0))
    print('FROZEN_ROUND1_BEFORE_ANY_PRIMARY_SCORE')

def verify():
    f=json.loads((M.HERE/'freeze-round1.json').read_text())
    for n,h in f['files'].items():assert C.sha(M.HERE/n)==h,n
    assert C.sha(M.HERE/'initial.json')==f['initial_sha256']
    path=(M.HERE/'freeze-round1.json').relative_to(C.ROOT).as_posix()
    assert C.git('log','-1','--format=%H','--',path).strip(),'commit freeze first'
    assert not C.git('status','--porcelain','--',path).strip(),'freeze must be clean'
    return f

def parity(ts):
    histories=0
    for y,tt in ts.items():
        for sc in SCENARIOS:
            a=M.L.run(tt,M.L.Candidate(**asdict(M.L.BASE)),sc,True)
            b=M.run(tt,M.E03,sc,True)
            assert a['days']==b['days'] and a['summary']==b['summary'],(y,sc,'E03')
            a=M.L.run(tt,replace(M.L.BASE,stop=.35,lock_arm=.5,lock_floor=1.1),sc,True)
            b=M.run(tt,M.BASE,sc,True)
            assert a['days']==b['days'] and a['summary']==b['summary'],(y,sc,'E031')
            histories+=sum(d['trades'] for d in a['days'])
    print('BASELINE_DAILY_EVENT_PARITY',histories,'E031 histories; E03 also exact',flush=True)
    return histories

def score():
    verify();started=time.time();ts=M.tapes();histories=parity(ts);results={}
    all_tapes=[*ts[2024],*ts[2025]]
    for name,rule in ARMS.items():
        for basis,tt in [('continuous',all_tapes),('2024',ts[2024]),('2025',ts[2025])]:
            for sc in SCENARIOS:
                r=M.run(tt,rule,sc,True);results[f'{name}|{basis}|{sc}']=r
                print(name,basis,sc,{k:r['summary'][k] for k in ('net','without_best','worst','drawdown','trades','unresolved')},flush=True)
    save('round1-results.json',dict(parity_histories=histories,mismatches=0,elapsed=time.time()-started,runs=results))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=('freeze','score','verify'))
    globals()[p.parse_args().command]()
