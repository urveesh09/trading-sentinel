"""Independent financial reconciliation, frozen replay and extra-cost risk diagnostics."""
import socket
NETWORK_ATTEMPTS=[]
def denied(*a,**k):
    NETWORK_ATTEMPTS.append(str(a[:1]));raise AssertionError('Offline research: network forbidden')
socket.socket.connect=denied;socket.create_connection=denied

from collections import Counter
from contextlib import redirect_stdout
from dataclasses import replace
import csv,json,math,sys
import numpy as np
import structure_checkpoint as C
import mechanisms as M
import structural as S
import payoff as P
import micro as Q
import run_study as R
import round2,round3

def reconcile(run,shape=False):
    count=events=0;cash=peak=M.E.START_CASH;assumed=0.;sampled_mark_dd=0.;closed=0;reasons=Counter()
    for day in run['days']:
        dd=peak-cash;scale=0. if dd>=4000 else .25 if dd>=3000 else .5 if dd>=1500 else 1.
        assert scale==day['scale'] and day['spent']<=min(2500*scale,cash)+.02
        if day.get('marked_worst') is not None:
            sampled_mark_dd=max(sampled_mark_dd,peak-(cash+day['marked_worst']))
        pcash=cash;net=fees=spent=0.;unresolved=0
        for p in day['positions']:
            count+=1;assert p['reserve']<=1250.01 and p['reserve']<=pcash+.01
            if shape:assert p['gross_long']<=pcash+.01
            assert p['entry_i']>p['decision_i']
            assert 0<p['lots']<=3
            gross=0.;cost=0.;bought=sold=0
            for ev in p['events']:
                events+=1;assert ev['i']>ev['decision_i']
                n=ev['lots'];price=ev['price'];buy=ev['side']=='BUY'
                if buy:bought+=n
                else:sold+=n;gross+=(price-p['entry'])*n*M.LOT;reasons[ev['reason']]+=1
                if shape:
                    assert math.isclose(sum(w*x for (j,w),x in zip(p['legs'],ev['leg_prices'])),price,abs_tol=.011)
                    fee=round(sum(round((Q.EP.buy_charges if ((w>0)==buy) else Q.EP.sell_charges)(x,n*M.LOT*abs(w),Q.SC),2)
                        for (j,w),x in zip(p['legs'],ev['leg_prices'])),2)
                else:
                    fee=round((Q.EP.buy_charges if buy else Q.EP.sell_charges)(price,n*M.LOT,Q.SC),2)
                assert abs(fee-ev['fees'])<.02,(fee,ev)
                cost+=fee
            assert bought==p['lots'] and bought-sold==p['open']
            lost=0.
            if p.get('unresolved'):
                unresolved+=1;lost=p['entry']*p['open']*M.LOT;assumed-=lost
            else:
                closed+=1;assert p['open']==0
            assert abs(gross-cost-lost-p['net'])<.04,(gross,cost,lost,p['net'])
            assert abs(cost-p['fees'])<.04
            net+=p['net'];fees+=p['fees'];spent+=p['reserve'];pcash=round(pcash+p['net'],2)
        assert abs(net-day['net'])<.02 and abs(fees-day['fees'])<.03 and abs(spent-day['spent'])<.03
        assert unresolved==day['unresolved']
        cash=round(cash+net,2);peak=max(peak,cash)
        assert abs(cash-day['cash_after'])<.02 and cash>=0
    assert abs(cash-25000-run['summary']['net'])<.02
    return dict(replayed_positions=count,sale_and_buy_events=events,closed=closed,
       sampled_mark_drawdown=round(sampled_mark_dd,2),assumed_full_premium=round(assumed,2),
       filled_fee_component=round(run['summary']['net']-assumed,2),exit_reasons=dict(reasons))

def main():
    R.verify();round2.verify();round3.verify();Q.verify();C.verify()
    ts=M.tapes();audit={};runs={}
    sources={}
    for f in ('round1-results.json','round2-results.json','round3-results.json'):
        sources[f]=C.sha(M.HERE/f);runs.update(json.loads((M.HERE/f).read_text())['runs'])
    # Re-run every frozen primary history offline, not only the displayed summaries.
    for key,old in runs.items():
        name,basis,sc=key.split('|');tt=ts[2024]+ts[2025] if basis=='continuous' else ts[int(basis)]
        if name in R.ARMS:new=M.run(tt,R.ARMS[name],sc,True)
        elif name in round2.ARMS:new=S.run(tt,round2.ARMS[name],sc,True)
        else:new=P.run(tt,round3.ARMS[name],sc,True)
        # JSON archives normalize leg tuples to lists; compare the full serialized histories.
        assert old==json.loads(json.dumps(new)),key
        audit[key]=reconcile(old,name in round3.ARMS)
    # All six primary candidates use the PREDECLARED material acceptance; no winner relabelled.
    decisions={}
    for name in ('PATIENT','OPTION_LED','RECLAIM','VALUE_CHECK','DEBIT_VERTICAL','BUTTERFLY'):
        criteria={}
        for sc in ('ordinary','adverse'):
            b=runs[f'E031|continuous|{sc}'];a=runs[f'{name}|continuous|{sc}']
            inc=[x['net']-y['net'] for x,y in zip(a['days'],b['days'])]
            criteria[f'{sc}_material']=a['summary']['net']>=b['summary']['net']*1.25
            criteria[f'{sc}_increment_ex_best']=round(sum(inc)-max(inc),2)
            criteria[f'{sc}_day_risk']=a['summary']['worst']>=b['summary']['worst']*1.1
            criteria[f'{sc}_dd_risk']=a['summary']['drawdown']<=b['summary']['drawdown']*1.1
            criteria[f'{sc}_resolved']=a['summary']['unresolved']==0
            for y in (2024,2025):
                s=runs[f'{name}|{y}|{sc}']['summary'];base=runs[f'E031|{y}|{sc}']['summary']
                criteria[f'{y}_{sc}_better']=s['net']>base['net']
                criteria[f'{y}_{sc}_ex_best_positive']=s['without_best']>0
        criteria['accepted']=all(v if isinstance(v,bool) else v>0 for v in criteria.values())
        decisions[name]=criteria
    # Fixed-policy one additional percent PLUS one tick, not a new rule selection.
    original=M.E.executable
    def friction(t,i,j,side,scenario,lots):
        n,price=original(t,i,j,side,scenario,lots)
        if not n:return n,price
        price=M.E.up(price*1.01+.05) if side=='BUY' else M.E.down(price*.99-.05)
        return (n,price) if price>0 else (0,None)
    costs={}
    try:
        M.E.executable=friction
        for name in ('E031','PATIENT'):
            for sc in R.SCENARIOS:
                r=M.run(ts[2024]+ts[2025],R.ARMS[name],sc,True)
                costs[f'{name}|{sc}']=dict(summary=r['summary'],audit=reconcile(r))
    finally:M.E.executable=original
    daily=M.HERE/'daily-results.csv';assert not daily.exists()
    with daily.open('x',newline='',encoding='utf-8') as f:
        fields=('arm','basis','scenario','day','net','fees','trades','unresolved','spent','cash_after','scale')
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for key,r in runs.items():
            arm,basis,scenario=key.split('|')
            for d in r['days']:w.writerow(dict(arm=arm,basis=basis,scenario=scenario,**{k:d[k] for k in fields[3:]}))
    R.save('audit-results.json',dict(immutable_sources=sources,all_daily_event_histories_identical=True,
       histories_checked=len(runs),replayed_position_records=sum(x['replayed_positions'] for x in audit.values()),
       # Repeated independent/reset/continuous scenarios are not independent trades.
       audit=audit,decisions=decisions,additional_one_percent_plus_tick=costs,
       native_fee_snapshot=Q.SC,network_attempts=NETWORK_ATTEMPTS,qualification=False))
    print('AUDIT_PASSED',len(runs),'full histories;',sum(x['replayed_positions'] for x in audit.values()),'repeated position records; no accepted candidate; network attempts',len(NETWORK_ATTEMPTS))
    print('EXTRA_FRICTION',{k:v['summary']['net'] for k,v in costs.items()})

if __name__=='__main__':main()
