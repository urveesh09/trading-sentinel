"""Reproduce the inherited 53-session E01.1 control before E02 selection."""
import json,sys
from pathlib import Path
import data as D


def main():
    prior=D.HERE.parent/'2026-11-03-expiry-year'
    sys.path.insert(0,str(prior))
    import study as S
    import minutes as M
    stored=json.loads((prior/'results-minute2025.json').read_text())
    expected=stored['positions']['E011'];actual={s:[] for s in expected};bad=[]
    for day in sorted({p['day'] for p in expected['ordinary']}):
        tape=M.Minute(day);state,signals=M.signals(tape)
        for scenario,adverse in (('ordinary',False),('adverse',True)):
            for i,d in signals:
                strike=S.L._pick(tape,i,d,S.FIXED['E011'])
                if strike is None:continue
                con,q=tape.quoted_chain(i)[strike,'CE' if d=='UP' else 'PE']
                pos=S.simulate(tape,(i,con.tradingsymbol,'RECORDED_CHAIN_BREAK'),S.FIXED['E011'],adverse,failed_back=True)
                if pos:actual[scenario].append(pos);break
    for sc in actual:
        if len(actual[sc])!=len(expected[sc]):bad.append((sc,'count'))
        for a,b in zip(actual[sc],expected[sc]):
            if a!=b:bad.append((sc,a['day'],'full position/event mismatch'))
    D.dump(D.HERE/'baseline-parity.json',dict(positions=sum(map(len,actual.values())),mismatches=bad,summary={s:S.stats(p) for s,p in actual.items()}))
    print('BASELINE',sum(map(len,actual.values())),'positions',len(bad),'mismatches',flush=True)
    assert not bad


if __name__=='__main__':main()
