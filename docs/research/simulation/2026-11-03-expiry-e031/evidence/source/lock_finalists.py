"""Freeze two distinct hypotheses before execution robustness scoring."""
from dataclasses import asdict,replace
import json
import lab as L
import study as S

def main():
    trials=json.loads((L.HERE/'genome.json').read_text())
    simple=replace(L.BASE,stop=.35,lock_arm=.5,lock_floor=1.1)
    follow=replace(L.BASE,stop=.35,keep=.7,extend_minutes=4,extend_gain=0.)
    selected={'DEFENSIVE':simple,'FOLLOW':follow}
    for r in selected.values():assert any(x['key']==r.key for x in trials['leaders'])
    S.freeze('finalists-freeze.json',dict(finalists={k:asdict(v) for k,v in selected.items()},
       reason='DEFENSIVE has distributed positive increment in every seen year/scenario; FOLLOW tests larger but less uniform trend extension',
       additional_predeclared_checks=['one extra minute exit latency; entries unchanged',
          'one extra minute entry/exit latency with original entry limit',
          'fixed baseline executions with added 1% plus tick each side; no favourable reselection',
          'severe next-high buys/next-low sells', '12:59 native start requiring 12 consecutive completed bars',
          'local coarse neighbours, cross-year and expanding quarterly selection',
          'paired four-expiry circular block bootstrap, 10000 samples seed 731',
          'continuous own cash over both years; no year reset'],
       acceptance='PLAN.md; both years seen; no additional tuning after this freeze'))
    print('LOCKED', {k:r.key for k,r in selected.items()})

if __name__=='__main__':main()
