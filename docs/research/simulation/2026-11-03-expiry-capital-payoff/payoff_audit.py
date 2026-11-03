"""Exact replays, native long actions, independent cash/fees and causal prefixes."""
import csv,json,socket
from collections import Counter
from types import SimpleNamespace
import numpy as np
NETWORK=[]
def denied(*a,**k):NETWORK.append(str(a[:1]));raise AssertionError('Offline only')
socket.socket.connect=denied;socket.socket.connect_ex=denied;socket.create_connection=denied
import ledger_guard as G
import ledger_lab as K
import credit_lab as C
import hybrid_lab as H
import payoff_diagnostics as V
import expiry_e02 as N
EP=K.D.EP

def native_replay(t,p,scenario):
    # Independently invoke the shipped policy, rather than the research exit fork.
    con=SimpleNamespace(tradingsymbol=p['symbol'],token=p['j']+1,strike=float(t.strikes[p['j']]),
        instrument_type='CE' if p['direction']==1 else 'PE',lot_size=65)
    policy=N.policy_for(N.E031)
    n=EP._new_position(t.day,'NIFTY','RESEARCH','NFO',con,p['entry'],p['lots'],t.now[p['entry_i']],K.E.FEE)
    n.update(stop=round(p['entry']*(1-policy['stop']),2),direction=p['direction'],underlying_stop=p['underlying_stop'],e02_policy=policy)
    pending=None;events=[]
    for i in range(p['entry_i'],t.n):
        if pending:
            lots,why,di=pending;filled,price=K.E.executable(t,i,p['j'],'SELL',scenario,min(lots,n['lots_open']))
            if filled:
                q=EP.Quote(((price,filled*65),),((price+.05,filled*65),),price,t.now[i])
                event=N.sell_base(n,q,filled,t.now[i]) if why=='TARGET_BASE' else EP._try_exit(n,q,filled,why,t.now[i])
                assert event and event['price']==price and event['lots']==filled
                events.append((i,di,filled,price,why))
            if not n['lots_open']:break
            pending=None if why=='TARGET_BASE' else (n['lots_open'],why,di)
            if pending:continue
        row=t.q[i,p['j']]
        bid=K.E.down(float(row[3])-K.E.half(float(row[3]))) if np.isfinite(row[3]) and np.isfinite(row[4]) and row[4]*.2>=65 else None
        if t.minute[i]>=928:pending=(n['lots_open'],'FLAT_TIME',i);continue
        if bid is None or bid<=0:continue
        spot=float(t.close[i]) if np.isfinite(t.close[i]) else None
        action=N.action(n,bid,spot,t.now[i])
        if action and i<t.n-1:pending=(*action,i)
    expected=[(e['i'],e['decision_i'],e['lots'],e['price'],e['reason']) for e in p['events'][1:]]
    assert events==expected,(t.day,events,expected)
    assert abs(n['net_pnl']-p['net'])<.03 and n['lots_open']==p['open']==0
    return len(events)

def charge(price,buy):
    return round((EP.buy_charges if buy else EP.sell_charges)(price,65,K.E.FEE),2)

def credit_check(t,p,sc):
    a,b=p['legs'];d=p['direction'];di=p['decision_i'];i=p['entry_i'];ei=p['exit_i']
    assert t.kinds[a]==t.kinds[b]==-d and d*(t.strikes[a]-t.strikes[b])==p['width']
    assert all(0<-d*(t.strikes[j]-t.close[di])<=200 for j in (a,b))
    assert p['credit']==round(p['short_entry']-p['hedge_entry'],2) and 0<p['credit']<p['width']
    entry_fees=round(charge(p['short_entry'],False)+charge(p['hedge_entry'],True),2)
    assert entry_fees==p['entry_fees']
    assert p['reserve']==round((p['width']+1-p['credit'])*65+entry_fees+500,2)
    assert p['collateral']==(p['width']+1)*65+entry_fees+500
    assert not p['unresolved_short'] and ei>p['decision_exit_i']>=i
    q=C.entry(t,i,(a,b),sc);assert q['short']==p['short_entry'] and q['hedge']==p['hedge_entry']
    q=C.close_quote(t,ei,(a,b),sc);assert q['short']==p['exit_short'] and q['hedge']==p['exit_hedge']
    fees_out=charge(p['exit_short'],True)+(charge(p['exit_hedge'],False) if p['exit_hedge'] is not None else 0.)
    fees_out=round(fees_out,2);assert fees_out==p['exit_fees']
    cashflow=(p['short_entry']-p['hedge_entry']-p['exit_short']+(p['exit_hedge'] or 0))*65-entry_fees-fees_out
    assert abs(cashflow-p['net'])<.02 and p['net']>=-p['reserve']-.01
    assert abs(p['filled_fee']+p['assumed']-p['net'])<.01
    assert p['residual_long']==int(p['exit_hedge'] is None)
    assert p['assumed']==(-p['hedge_entry']*65 if p['residual_long'] else 0.)
    assert p['fees']==round(entry_fees+fees_out,2)
    for k in np.linspace(t.strikes.min()-500,t.strikes.max()+500,61):
        kind=-d;terminal=max(0,kind*(k-t.strikes[a]))-max(0,kind*(k-t.strikes[b]))
        assert -.001<=terminal<=p['width']+.001
    return 4-p['residual_long']

def financial(run,tapes,family,rule):
    cash=peak=25000.;sample_peak=25000.;sample_dd=0.;missing_marks=0;longs=credits=orders=0;reasons=Counter();decisions=set()
    for t,day in zip(tapes,run['days']):
        brake=run.get('brakes',True);dd=peak-cash
        scale=0. if brake and dd>=4000 else .25 if brake and dd>=3000 else .5 if brake and dd>=1500 else 1.
        assert scale==day['scale'];cap=2500 if family=='ledger' or rule.name=='E031' else 5000
        budget=min(cap*scale,cash);spent=net=fees=0.;pcash=cash;last=None
        for ordinal,p in enumerate(day['positions']):
            di=p['decision_i'];i=p['entry_i'];decisions.add((t.day,di))
            assert i==di+1 and 780<=t.minute[di]<900 and p['reserve']<=pcash+.02
            if last is not None:assert di>=last+5
            last=p['exit_i'];is_credit='legs' in p
            if family=='ledger':
                mode=rule.mode
                if mode=='net':assert net-p['reserve']>=-budget-.02
                elif mode=='profit' and ordinal>=2:assert net-p['reserve']>=-.02
                else:assert spent+p['reserve']<=budget+.02
            else:assert spent+p['reserve']<=budget+.02
            if is_credit:
                assert p['collateral']<=pcash+.02
                orders+=credit_check(t,p,run['scenario']);credits+=1;reasons[p['reason']]+=1
            else:
                assert p['reserve']<=1250.02 and 0<p['lots']<=3
                assert 0<p['direction']*(t.strikes[p['j']]-t.close[di])<=200
                assert abs(EP.worst_case_loss(p['entry'],p['lots'],65,K.E.FEE)-p['reserve'])<.02
                orders+=1+native_replay(t,p,run['scenario']);longs+=1
                for event in p['events'][1:]:reasons[event['reason']]+=1
            spent+=p['reserve'];net+=p['net'];fees+=p['fees'];pcash=round(pcash+p['net'],2)
        assert day['unresolved']==0 and abs(spent-day['spent'])<.03 and abs(net-day['net'])<.03 and abs(fees-day['fees'])<.03
        if family!='ledger':assert len(day['positions'])<=2
        for i in range(int(np.searchsorted(t.minute,780)),t.n):
            nav=cash;available=True
            for p in day['positions']:
                if i<p['entry_i']:continue
                if i>=p['exit_i']:nav+=p['net'];continue
                if 'legs' in p:
                    q=C.close_quote(t,i,p['legs'],'ordinary',mark=True)
                    if not q:available=False;break
                    nav+=(p['credit']-q['cost'])*65-p['entry_fees']-q['fees']
                else:
                    realized=-K.E.fee(p['entry'],p['lots']*65,True);left=p['lots']
                    for e in p['events'][1:]:
                        if e['i']<=i:realized+=(e['price']-p['entry'])*e['lots']*65-K.E.fee(e['price'],e['lots']*65,False);left-=e['lots']
                    if left:
                        row=t.q[i,p['j']];bid=K.E.down(float(row[3])-K.E.half(float(row[3]))) if np.isfinite(row).all() and row[4]*.2>=left*65 else None
                        if bid is None or bid<=0:available=False;break
                        realized+=(bid-p['entry'])*left*65-K.E.fee(bid,left*65,False)
                    nav+=realized
            if available:sample_peak=max(sample_peak,nav);sample_dd=max(sample_dd,sample_peak-nav)
            else:missing_marks+=1
        cash=round(cash+net,2);peak=max(peak,cash);assert cash==day['cash_after'] and cash>=0
    assert len(run['days'])==len(tapes) and abs(cash-25000-run['summary']['net'])<.02
    return dict(long_positions=longs,credit_positions=credits,filled_orders=orders,exit_reasons=dict(reasons),
        sampled_marked_drawdown=round(sample_dd,2),missing_nav_marks=missing_marks,end_cash=cash),decisions

def prefixes(ts,keys):
    lookup={t.day:t for tt in ts.values() for t in tt};checks=0
    for day,i in sorted(keys):
        t=lookup[day];end=i+1
        p=K.D.Tape(t.day,t.x[:end].copy(),t.f[:end].copy(),t.q[:end].copy(),t.strikes.copy(),t.kinds.copy(),list(t.symbols),list(t.now[:end]),t.minute[:end].copy(),t.invalid)
        p.oi=t.oi[:end].copy();d=int(K.L.directions(t,K.BASE)[i]);assert K.L.directions(p,K.BASE)[i]==d
        for room in (1250.,625.):
            assert K.L.choose(p,i,d,K.BASE,room,25000.)==K.L.choose(t,i,d,K.BASE,room,25000.)
        assert C.contracts(p,i,d,C.ARMS['CREDIT_8M'])==C.contracts(t,i,d,C.ARMS['CREDIT_8M'])
        checks+=1
    return checks

def main():
    V.verify();G.verify();ts=K.tapes();audit={};keys=set();daily=[];trades=[]
    for source,family,rules in [('ledger-results.json','ledger',K.ARMS),('credit-results.json','credit',C.ARMS),
         ('hybrid-results.json','hybrid',H.ARMS),('unbraked-results.json','unbraked',{**H.ARMS,**C.ARMS})]:
        for key,old in json.loads((G.HERE/source).read_text())['runs'].items():
            name,basis,sc=key.split('|');tt=ts[2024]+ts[2025] if basis=='continuous' else ts[int(basis)];rule=rules[name]
            if family=='ledger':new=K.run(tt,rule,sc,True)
            elif family=='credit':new=C.run(tt,rule,sc,True)
            elif family=='hybrid':new=H.run(tt,rule,sc,True)
            elif name in C.ARMS:new=H.credit_unbraked(tt,rule,sc,True)
            else:new=H.run(tt,rule,sc,True,brakes=False)
            assert old==new,(source,key)
            proof,decisions=financial(old,tt,'ledger' if family=='ledger' else family,rule);keys.update(decisions);audit[source+'|'+key]=proof
            if basis=='continuous':
                for d in old['days']:
                    daily.append(dict(source=source,arm=name,scenario=sc,day=d['day'],net=d['net'],fees=d['fees'],trades=d['trades'],spent=d['spent'],cash_after=d['cash_after'],scale=d['scale'],unresolved=d['unresolved']))
                    for p in d['positions']:
                        trades.append(dict(source=source,arm=name,scenario=sc,day=d['day'],instrument='CREDIT' if 'legs' in p else 'LONG',entry_i=p['entry_i'],exit_i=p['exit_i'],net=p['net'],fees=p['fees'],reserve=p['reserve'],filled_fee=p.get('filled_fee',p['net']),assumed=p.get('assumed',0.),residual_long=p.get('residual_long',0)))
    count=prefixes(ts,keys);assert not NETWORK
    for name,rows in [('daily-results.csv',daily),('trades.csv',trades)]:
        with (G.HERE/name).open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    G.save('audit-results.json',dict(histories=len(audit),runs=audit,distinct_actual_prefixes=count,
        native_long_positions=sum(r['long_positions'] for r in audit.values()),credit_positions=sum(r['credit_positions'] for r in audit.values()),
        financial_action_mismatches=0,network_attempts=NETWORK,qualification=False,
        marked_basis='Complete-bar estimated liquidation NAV with fees; missing marks omitted/counts; not intrabar/depth broker NAV'))
    print('PAYOFF_AUDIT',len(audit),'histories;',count,'causal prefixes; no cash/native mismatch')

if __name__=='__main__':main()
