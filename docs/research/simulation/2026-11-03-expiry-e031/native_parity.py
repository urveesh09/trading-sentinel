"""Network-blocked native parity, financial and causal review of frozen finalists."""
import socket
NETWORK_ATTEMPTS=[]
def denied(*args,**kwargs):
    NETWORK_ATTEMPTS.append(str(args[:1]));raise AssertionError('Network forbidden during E03.1 replay')
socket.socket.connect=denied
socket.socket.connect_ex=denied
socket.create_connection=denied

from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
import ast,csv,json,sys,subprocess
import numpy as np
import lab as L
import study as S
import expiry_e02 as P
EP=L.D.EP
HERE=L.HERE

def replay(t,p,scenario,variant):
    con=SimpleNamespace(tradingsymbol=p['symbol'],token=p['j']+1,strike=float(t.strikes[p['j']]),
                        instrument_type='CE' if p['direction']==1 else 'PE',lot_size=65)
    n=EP._new_position(t.day,'NIFTY',variant.play,'NFO',con,p['entry'],p['lots'],t.now[p['entry_i']],L.E.FEE)
    n.update(stop=round(p['entry']*(1-variant.initial_stop),2),direction=p['direction'],underlying_stop=p['underlying_stop'],e02_policy=P.policy_for(variant))
    pending=None;events=[]
    for i in range(p['entry_i'],t.n):
        if pending:
            lots,why,di=pending
            filled,price=L.E.executable(t,i,p['j'],'SELL',scenario,min(lots,n['lots_open']))
            if filled:
                q=EP.Quote(((price,filled*65),),((price+.05,filled*65),),price,t.now[i])
                if why=='TARGET_BASE':EP_event=P.sell_base(n,q,filled,t.now[i])
                else:EP_event=EP._try_exit(n,q,filled,why,t.now[i])
                assert EP_event and EP_event['price']==price and EP_event['lots']==filled
                events.append((i,di,filled,price,why))
            if not n['lots_open']:break
            pending=None if why=='TARGET_BASE' else (n['lots_open'],why,di)
            if pending:continue
        row=t.q[i,p['j']]
        bid=L.E.down(float(row[3])-L.E.half(float(row[3]))) if np.isfinite(row[3]) and np.isfinite(row[4]) and row[4]*.2>=65 else None
        if t.minute[i]>=928:pending=(n['lots_open'],'FLAT_TIME',i);continue
        if bid is None or bid<=0:continue
        spot=float(t.close[i]) if np.isfinite(t.close[i]) else None
        a=P.action(n,bid,spot,t.now[i])
        if a and i<t.n-1:pending=(*a,i)
    expected=[(e['i'],e['decision_i'],e['lots'],e['price'],e['reason']) for e in p['events'][1:]]
    assert events==expected,(t.day,scenario,events,expected)
    assert abs(n['net_pnl']-p['net'])<=.03,(t.day,n['net_pnl'],p['net'])
    assert n['lots_open']==p['open']==0
    return len(events)

def financial(r,tapes):
    cash=peak=25000.;sampled_peak=25000.;marked_dd=0.;orders=0
    for t,d in zip(tapes,r['days']):
        scale=0 if peak-cash>=4000 else .25 if peak-cash>=3000 else .5 if peak-cash>=1500 else 1
        assert d['scale']==scale
        paid=0.
        for p in d['positions']:
            entry=p['events'][0];exit_events=p['events'][1:]
            assert entry['i']==entry['decision_i']+1
            assert p['lots']<=3 and abs(t.strikes[p['j']]-t.close[entry['decision_i']])<=200
            assert p['reserve']<=1250.01
            assert sum(e['lots'] for e in exit_events)==p['lots']
            gross=sum((e['price']-p['entry'])*e['lots']*65 for e in exit_events)
            charges=sum(L.E.fee(e['price'],e['lots']*65,e['side']=='BUY') for e in p['events'])
            assert abs(gross-charges-p['net'])<.03
            assert all(e['i']>e['decision_i'] for e in p['events'])
            assert all(0<e['lots']<=int(t.q[e['i'],p['j'],4]*.2)//65 for e in p['events'])
            paid+=p['reserve'];orders+=len(p['events'])
        assert len(d['positions'])<=2 and abs(paid-d['spent'])<.03
        assert paid<=min(2500*scale,cash)+.02
        # Mark all open/closed positions in chronological completed-bar order.
        for i in range(225,t.n):
            nav=cash
            for p in d['positions']:
                if i<p['entry_i']:continue
                realized=-L.E.fee(p['entry'],p['lots']*65,True);left=p['lots']
                for e in p['events'][1:]:
                    if e['i']<=i:
                        realized+=(e['price']-p['entry'])*e['lots']*65-L.E.fee(e['price'],e['lots']*65,False)
                        left-=e['lots']
                if left:
                    row=t.q[i,p['j']]
                    if not np.isfinite(row).all() or row[4]*.2<65:continue
                    bid=L.E.down(float(row[3])-L.E.half(float(row[3])))
                    if bid<=0:continue
                    realized+=(bid-p['entry'])*left*65-L.E.fee(bid,left*65,False)
                nav+=realized
            sampled_peak=max(sampled_peak,nav);marked_dd=max(marked_dd,sampled_peak-nav)
        cash=round(cash+d['net'],2);peak=max(peak,cash)
        assert cash==d['cash_after'] and cash>=0
    return dict(orders=orders,end_cash=cash,sampled_marked_drawdown=round(marked_dd,2),
                marked_basis='Observed complete-bar model bids with charges; missing liquid marks omitted, no intrabar/depth NAV claim')

def main():
    assert not (HERE/'native-parity.json').exists()
    ts=L.tapes();archive=json.loads((HERE/'robustness.json').read_text());count=exits=0;money={};trades=[]
    for name,variant,rule in (('E03',P.E03,L.BASE),('DEFENSIVE',P.E031,L.Candidate(**json.loads((HERE/'finalists-freeze.json').read_text())['finalists']['DEFENSIVE']))):
        for year,tapes in [(2024,ts[2024]),(2025,ts[2025]),('continuous',ts[2024]+ts[2025])]:
            for scenario in ('ordinary','adverse','catastrophe'):
                result=L.run(tapes,rule,scenario,True)
                assert result==archive['detail'][name][f'{year}|{scenario}']
                key=f'{name}|{year}|{scenario}';money[key]=financial(result,tapes)
                for t,d in zip(tapes,result['days']):
                    for p in d['positions']:
                        exits+=replay(t,p,scenario,variant);count+=1
                        if year=='continuous':
                            trades.append(dict(arm=name,scenario=scenario,day=t.day,symbol=p['symbol'],entry_i=p['entry_i'],entry=p['entry'],
                                  lots=p['lots'],reserve=p['reserve'],peak=p['peak'],net=p['net'],fees=p['fees'],exit_i=p['exit_i'],reason=p['events'][-1]['reason']))
    # Protect old pure signal/entry/account functions from accidental edits.
    old=subprocess.check_output(['git','show','0a6d46e:python-engine/expiry_e02.py'],cwd=HERE.parents[3]).decode()
    new=(HERE.parents[3]/'python-engine/expiry_e02.py').read_text(encoding='utf-8')
    def functions(source):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    before,after=functions(old),functions(new)
    unchanged=[k for k in before if before[k]==after[k]]
    changed=[k for k in before if before[k]!=after[k]]
    assert set(changed)=={'policy_for','action','run_tick'},changed
    assert not NETWORK_ATTEMPTS
    S.save('native-parity.json',dict(position_replays=count,exit_slices=exits,mismatches=0,financial=money,network_attempts=0,
         classification='Native exits and accounting parity; historical entry fills remain the declared BAR_LIFECYCLE proxy',
         unchanged_native_functions=unchanged,extended_native_functions=changed))
    with (HERE/'trades.csv').open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(trades[0]));w.writeheader();w.writerows(trades)
    print('NATIVE_PARITY',count,'position replays',exits,'exit slices, zero mismatches; network attempts',len(NETWORK_ATTEMPTS),flush=True)

if __name__=='__main__':main()
