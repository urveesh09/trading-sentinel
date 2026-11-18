"""Independent arithmetic and event-quantity checks against frozen inputs."""
from pathlib import Path
import json
import numpy as np
import score8,data8
HERE=Path(__file__).resolve().parent

def main():
    f,B=score8.verify_freeze();r=json.loads((HERE/'results8.json').read_text());a=json.loads((HERE/'anatomy8.json').read_text())
    count=orders=parents=0
    for key,days in a['days'].items():
        m=r['arms'][key]['ordinary'];vals=[d['net'] for d in days];top=sorted(vals,reverse=True)+[0,0]
        checks=dict(net=round(sum(vals),2),trades=sum(d['trades'] for d in days),sessions=len(days),fees=round(sum(d['fees'] for d in days),2),
                    traded_expiries=sum(d['trades']>0 for d in days),worst=round(min(vals),2),
                    without_top2=round(sum(vals)-max(0,top[0])-max(0,top[1]),2))
        for k,v in checks.items():assert abs(m[k]-v)<.011,(key,k,m[k],v);count+=1
        ts=a['tickets'][key];assert len(ts)==m['trades'];assert abs(sum(t['net'] for t in ts)-m['net'])<.011
        lot=65 if key.endswith('|NIFTY') else 20
        for p in ts:
            paid=sold=fees=0.;bought_lots=sold_lots=0
            last=-1
            for e in p['events']:
                assert e['lots']>0 and e['i']>=e['decision_i'] and e['i']>=last
                last=e['i'];fees+=e['fees'];orders+=1
                if e['side']=='BUY':paid+=e['price']*e['lots']*lot;bought_lots+=e['lots']
                else:sold+=e['price']*e['lots']*lot;sold_lots+=e['lots']
                assert sold_lots<=bought_lots
            assert bought_lots-sold_lots==p['open_lots']
            assert abs(round(sold-paid-fees,2)-p['net'])<.02,(key,p)
            assert p['reserve']<=p['room']+.02
            parents+=1
        assert abs(m['modeled_filled_fee_pnl']+m['assumed_unresolved_loss']-m['net'])<.011
        if not key.startswith(('E032_native','EN55_native')):
            for d in days:assert d['net']>=-2500.03 and d['intents']<=2
    assert len(r['hypotheses'])==18
    for key,h in r['hypotheses'].items():
        assert not h.get('qualified',False)
        if key.endswith('|SENSEX'):assert h['status']=='DATA UNAVAILABLE' and h['metrics'] is None
    # Deterministic additional replay at ordinary fills for every primary, exact day results.
    import signals8,lab8,payoff8
    signals8.prepare(B['NIFTY']);payoff8.prepare(B['NIFTY'])
    replays=0
    for name in lab8.PRIMARY:
        got=lab8.run_fixed(B['NIFTY'],lab8.ARMS[name],'ordinary',False)
        expect=a['days'][name+'|NIFTY']
        for d,e in zip(got,expect):assert all(d[k]==e[k] for k in ('day','net','fees','trades','marked_worst','minutes_in'))
        replays+=len(got)
    score8.write(HERE/'verification8.json',dict(status='PASS',financial_checks=count,parents=parents,order_events=orders,
                     primary_day_replays=replays,frozen_files=len(f['files']),result_sha256=data8.sha(HERE/'results8.json'),
                     anatomy_sha256=data8.sha(HERE/'anatomy8.json'),limits='no live fills, no new expiry holdout, no engine-suite claim'))
    print('VERIFY PASS',count,'financial identities',parents,'parents',orders,'orders',replays,'primary-day replays',flush=True)

if __name__=='__main__':main()
