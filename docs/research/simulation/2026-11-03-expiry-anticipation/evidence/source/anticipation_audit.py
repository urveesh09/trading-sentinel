"""Native action/accounting parity, exact frozen replays and forecast/feature causality."""
import socket
NETWORK=[]
def denied(*a,**k):NETWORK.append(str(a[:1]));raise AssertionError('Offline research')
socket.socket.connect=denied;socket.socket.connect_ex=denied;socket.create_connection=denied
from collections import Counter
from dataclasses import asdict,replace
from types import SimpleNamespace
import csv,json,math,sys
import numpy as np
import guard as G
import risk_lab as R
import precursor as P
import forecast_study as F
import return_lab as V
import return_study as T
import smart_lab as S
import smart_study as SS
import forest as B
import forest_study as BS
import expiry_e02 as N
EP=R.D.EP

def native_replay(t,p,scenario,policy):
    con=SimpleNamespace(tradingsymbol=p['symbol'],token=p['j']+1,strike=float(t.strikes[p['j']]),
        instrument_type='CE' if p['direction']==1 else 'PE',lot_size=65)
    n=EP._new_position(t.day,'NIFTY','RESEARCH','NFO',con,p['entry'],p['lots'],t.now[p['entry_i']],R.E.FEE)
    n.update(stop=round(p['entry']*(1-policy['stop']),2),direction=p['direction'],underlying_stop=p['underlying_stop'],e02_policy=policy)
    pending=None;events=[]
    for i in range(p['entry_i'],t.n):
        if pending:
            lots,why,di=pending;filled,price=R.E.executable(t,i,p['j'],'SELL',scenario,min(lots,n['lots_open']))
            if filled:
                q=EP.Quote(((price,filled*65),),((price+.05,filled*65),),price,t.now[i])
                event=N.sell_base(n,q,filled,t.now[i]) if why=='TARGET_BASE' else EP._try_exit(n,q,filled,why,t.now[i])
                assert event and event['price']==price and event['lots']==filled
                events.append((i,di,filled,price,why))
            if not n['lots_open']:break
            pending=None if why=='TARGET_BASE' else (n['lots_open'],why,di)
            if pending:continue
        row=t.q[i,p['j']]
        bid=R.E.down(float(row[3])-R.E.half(float(row[3]))) if np.isfinite(row[3]) and np.isfinite(row[4]) and row[4]*.2>=65 else None
        if t.minute[i]>=928:pending=(n['lots_open'],'FLAT_TIME',i);continue
        if bid is None or bid<=0:continue
        spot=float(t.close[i]) if np.isfinite(t.close[i]) else None
        action=N.action(n,bid,spot,t.now[i])
        if action and i<t.n-1:pending=(*action,i)
    expected=[(e['i'],e['decision_i'],e['lots'],e['price'],e['reason']) for e in p['events'][1:]]
    assert events==expected,(t.day,events,expected)
    assert abs(n['net_pnl']-p['net'])<.03 and n['lots_open']==p['open']==0
    return len(events)

def policy(rule):
    if getattr(rule,'predictor','baseline')=='forecast':return dict(stop=.35,arm=999.,keep=.6,target=rule.multiple-1,hold=1200)
    return N.policy_for(N.E031)

def financial(run,tapes,rule):
    cash=peak=25000.;sampled_peak=25000.;marked_dd=0.;positions=orders=0;reasons=Counter()
    extra=rule.extra;cap=1250*(1+extra)
    for t,day in zip(tapes,run['days']):
        scale=0 if peak-cash>=4000 else .25 if peak-cash>=3000 else .5 if peak-cash>=1500 else 1
        assert day['scale']==scale;spent=0.;net=0.;fees=0.;pcash=cash
        for p in day['positions']:
            assert p['entry_i']==p['decision_i']+1 and p['reserve']<=min(cap,pcash)+.02
            assert 0<p['lots']<=rule.max_lots and 0<p['direction']*(t.strikes[p['j']]-t.close[p['decision_i']])<=200
            assert abs(EP.worst_case_loss(p['entry'],p['lots'],65,R.E.FEE)-p['reserve'])<.02
            gross=cost=0.;left=p['lots']
            for event in p['events']:
                assert event['i']>event['decision_i']
                assert event['lots']<=int(t.q[event['i'],p['j'],4]*.2)//65
                buy=event['side']=='BUY';qty=event['lots']*65
                charge=round((EP.buy_charges if buy else EP.sell_charges)(event['price'],qty,R.E.FEE),2)
                assert abs(charge-event['fees'])<.02
                cost+=charge
                if not buy:gross+=(event['price']-p['entry'])*qty;left-=event['lots'];reasons[event['reason']]+=1
            assert left==p['open']==0 and abs(gross-cost-p['net'])<.04 and abs(cost-p['fees'])<.04
            orders+=native_replay(t,p,run['scenario'],policy(rule));positions+=1
            spent+=p['reserve'];net+=p['net'];fees+=p['fees'];pcash=round(pcash+p['net'],2)
        assert len(day['positions'])<=2 and day['unresolved']==0
        assert abs(spent-day['spent'])<.03 and spent<=min(2500*(1+extra)*scale,cash)+.03
        assert abs(net-day['net'])<.03 and abs(fees-day['fees'])<.03
        # Complete-bar model NAV with exit charges, not intrabar broker NAV.
        for i in range(225,t.n):
            nav=cash;available=True
            for p in day['positions']:
                if i<p['entry_i']:continue
                realized=-R.E.fee(p['entry'],p['lots']*65,True);left=p['lots']
                for e in p['events'][1:]:
                    if e['i']<=i:realized+=(e['price']-p['entry'])*e['lots']*65-R.E.fee(e['price'],e['lots']*65,False);left-=e['lots']
                if left:
                    row=t.q[i,p['j']]
                    if not np.isfinite(row).all() or row[4]*.2<left*65:available=False;break
                    bid=R.E.down(float(row[3])-R.E.half(float(row[3])))
                    if bid<=0:available=False;break
                    realized+=(bid-p['entry'])*left*65-R.E.fee(bid,left*65,False)
                nav+=realized
            if available:sampled_peak=max(sampled_peak,nav);marked_dd=max(marked_dd,sampled_peak-nav)
        cash=round(cash+net,2);peak=max(peak,cash);assert cash==day['cash_after'] and cash>=0
    assert abs(cash-25000-run['summary']['net'])<.02
    return dict(native_position_replays=positions,native_exit_slices=orders,end_cash=cash,
        sampled_marked_drawdown=round(marked_dd,2),exit_reasons=dict(reasons),
        marked_basis='Complete-bar model bid marks and native fees; missing/insufficient marks omitted, not intrabar/depth broker NAV')

def score_replay(archive,runner,rules,ts):
    rows={}
    for key,old in archive.items():
        name,basis,sc=key.split('|');tt=ts[2024]+ts[2025] if basis=='continuous' else ts[int(basis)]
        new=runner(tt,rules[name],sc,True);assert old==new,key
        rows[key]=financial(old,tt,rules[name])
    return rows

def forecast_replay(source,kind,ts,x,ys,days,years,meta):
    results=json.loads((G.HERE/source).read_text());money={};all_tapes=ts[2024]+ts[2025]
    for multiple in (2,5):
        for train,test in ((2024,2025),(2025,2024)):
            key=f'{multiple}|train{train}|test{test}';b=years==test;mm=[r for r,keep in zip(meta,b) if keep]
            model=results['models'][key]
            if kind=='prob':pred=P.predict(model,x[b]);P.activate(mm,pred,multiple);runner=P.run
            else:pred=(V.predict if kind=='linear' else B.predict)(model,x[b],multiple);V.activate(mm,pred);runner=V.run
            for sc in F.SZ.SCENARIOS:
                old=results['runs'][f'{key}|{sc}'];new=runner(ts[test],P.forecast_rule(multiple),sc,True)
                assert old==new,(source,key,sc);money[f'{key}|{sc}']=financial(old,ts[test],P.forecast_rule(multiple))
        values=np.full(len(x),np.nan);key=f'{multiple}|causal'
        for quarter,model in results['models'][key].items():
            year=int(quarter[:4]);q=int(quarter[-1]);start=f'{year}-{(q-1)*3+1:02}-01'
            end=f'{year+1}-01-01' if q==4 else f'{year}-{q*3+1:02}-01'
            a=days<start;b=(days>=start)&(days<end)&(days>=all_tapes[13].day)
            assert max(days[a])<start and model['training_rows']==int(a.sum()) and model['training_days']==len(set(days[a]))
            values[b]=P.predict(model,x[b]) if kind=='prob' else (V.predict if kind=='linear' else B.predict)(model,x[b],multiple)
        b=np.isfinite(values);mm=[r for r,keep in zip(meta,b) if keep]
        if kind=='prob':P.activate(mm,values[b],multiple);runner=P.run
        else:V.activate(mm,values[b]);runner=V.run
        for sc in F.SZ.SCENARIOS:
            old=results['runs'][f'{key}|{sc}'];new=runner(all_tapes[13:],P.forecast_rule(multiple),sc,True)
            assert old==new,(source,key,sc);money[f'{key}|{sc}']=financial(old,all_tapes[13:],P.forecast_rule(multiple))
    return money

def features_and_labels(ts):
    data=np.load(G.LOCAL/'cases.npz');x=data['x'];meta=json.loads((G.LOCAL/'cases-meta.json').read_text());lookup={t.day:t for tt in ts.values() for t in tt}
    statuses=Counter();checks=0
    for idx,row in enumerate(meta):
        t=lookup[row['day']];i=row['i'];j=row['j'];d=row['direction'];feature=P.feature(t,i,j,d)
        assert np.array_equal(feature,x[idx],equal_nan=True)
        for multiple in (2,5):
            current=P.label(t,i,j,d,row['limit'],multiple);assert current==row[f'label{multiple}']
            assert current['hit']==int(data[f'y{multiple}'][idx]);statuses[f'{multiple}|{current["status"]}']+=1
            if current['entry_i'] is not None:assert current['entry_i']==i+1
            if current['exit_i'] is not None:assert current['exit_i']>current['entry_i']
            checks+=1
    # Rebuild actual prefixes (including the source Tape's rolling features), not a cached full-day view.
    rng=np.random.default_rng(731);prefixes=0
    for idx in rng.choice(len(meta),size=210,replace=False):
        row=meta[int(idx)];t=lookup[row['day']];end=row['i']+1
        p=R.D.Tape(t.day,t.x[:end].copy(),t.f[:end].copy(),t.q[:end].copy(),t.strikes.copy(),t.kinds.copy(),list(t.symbols),list(t.now[:end]),t.minute[:end].copy(),t.invalid)
        p.oi=t.oi[:end].copy()
        assert np.array_equal(P.feature(p,row['i'],row['j'],row['direction']),x[idx],equal_nan=True)
        prefixes+=1
    return dict(examples=len(meta),executable_labels_recomputed=checks,actual_prefix_rebuilds=prefixes,statuses=dict(statuses),mismatches=0)

def main():
    BS.verify();G.verify();ts,x,ys,days,years,meta=T.load();financials={}
    for source,runner,rules in [('size-results.json',R.run,R.ARMS),('smart-results.json',S.run,S.ARMS)]:
        if source.startswith('smart'):SS.prepare()
        financials[source]=score_replay(json.loads((G.HERE/source).read_text())['runs'],runner,rules,ts)
    for source,kind in [('forecast-results.json','prob'),('return-results.json','linear'),('forest-results.json','forest')]:
        financials[source]=forecast_replay(source,kind,ts,x,ys,days,years,meta)
    label_audit=features_and_labels(ts)
    assert not NETWORK
    G.save('audit-results.json',dict(financials=financials,feature_labels=label_audit,
        full_book_histories=sum(len(v) for v in financials.values()),
        native_position_replays=sum(v['native_position_replays'] for rows in financials.values() for v in rows.values()),
        native_exit_slices=sum(v['native_exit_slices'] for rows in financials.values() for v in rows.values()),
        native_money_action_mismatches=0,network_attempts=NETWORK,qualification=False,
        caveat='Repeated scenario/control histories are not independent market trades; labels overlap and eight unresolved training outcomes remain conservative non-hits'))
    print('AUDIT_COMPLETE',sum(len(v) for v in financials.values()),'histories;',label_audit['executable_labels_recomputed'],'labels;',label_audit['actual_prefix_rebuilds'],'prefixes; no native action/money mismatch',flush=True)

if __name__=='__main__':main()
