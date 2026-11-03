"""Correct a stress label without overwriting its original evidence.

robustness.py used max(1%, one tick), rounded to tick, but the predeclared
description said 1% PLUS one tick. Recalculate the stronger, intended stress.
No strategy, trades, finalist selection or historical execution changes.
"""
import json
import lab as L
import study as S

def stressed(price,buy):
    return L.E.up(price*1.01+.05) if buy else max(.05,L.E.down(price*.99-.05))

def main():
    assert stressed(10.,True)==10.15 and stressed(10.,False)==9.85
    out={};archive=json.loads((L.HERE/'robustness.json').read_text())
    for arm,ds in archive['detail'].items():
        out[arm]={}
        for key,r in ds.items():
            values=[]
            for d in r['days']:
                extra=0.
                for p in d['positions']:
                    for e in p['events']:
                        buy=e['side']=='BUY';qty=e['lots']*65;old=e['price'];new=stressed(old,buy)
                        extra+=abs(new-old)*qty+L.E.fee(new,qty,buy)-L.E.fee(old,qty,buy)
                values.append(round(d['net']-extra,2))
            out[arm][key]=dict(net=round(sum(values),2),without_best=round(sum(values)-max(values,default=0),2),
                 worst=round(min(values,default=0),2))
    S.save('friction-audit-v2.json',dict(correction='Original retained; max(1%,tick) stress mislabeled as PLUS. This implements 1%+0.05 each side, then tick rounds.',
       basis='Fixed same original entries/exits/quantities; additional costs; no re-selection or dynamic brake rerun',results=out))
    print('STRONGER_FIXED_FRICTION', {a:d['continuous|ordinary']['net'] for a,d in out.items()})

if __name__=='__main__':main()
