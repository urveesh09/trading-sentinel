"""Independent native-money/controller audit and fixed-entry friction stress."""
from dataclasses import replace
from datetime import time
from types import SimpleNamespace
import json
import data as D
import e02_lab as E


def native_audit(t,rule,row,scenario):
    count=0
    for p in row['positions']:
        con=SimpleNamespace(tradingsymbol=p['symbol'],token=p['j']+1,strike=float(t.strikes[p['j']]),instrument_type='CE' if p['direction']==1 else 'PE',lot_size=65)
        n=D.EP._new_position(t.day,'NIFTY','E02LAB','NFO',con,p['entry'],p['lots'],t.now[p['entry_i']],E.FEE)
        n['stop']=round(p['entry']*(1-rule.stop),2)
        policy=D.EP.ExitPolicy(hard_stop=rule.stop,bank_at=None,bank_stop=None,trails=((rule.arm,rule.keep),),late=None,time_stop=None,flat_at=time(15,28))
        pending=None;events=[]
        for i in range(p['entry_i'],t.n):
            if pending:
                lots,why,di=pending
                filled,price=E.executable(t,i,p['j'],'SELL',scenario,min(lots,n['lots_open']))
                if filled:
                    D.EP._sell(n,filled,price,why,t.now[i]);events.append((i,di,filled,price,why))
                if not n['lots_open']:break
                continue
            r=t.q[i,p['j']]
            bid=E.down(float(r[3])-E.half(float(r[3]))) if E.np.isfinite(r[3]) and E.np.isfinite(r[4]) and r[4]*.2>=65 else None
            if t.minute[i]>=928:pending=(n['lots_open'],'FLAT_TIME',i);continue
            if bid is None or bid<=0:continue
            broken=bool(rule.underlying_stop>0 and E.np.isfinite(t.close[i]) and p['direction']*(t.close[i]-p['underlying_stop'])<0)
            action=D.EP.manage_position(n,policy,bid,t.now[i],structure_broken=broken)
            if action:
                lots,why=action
                pending=(lots,'STRUCTURE' if why=='FAILED_BREAK' else why,i)
            elif bid>=p['entry']*(1+rule.target):pending=(n['lots_open'],'TARGET',i)
            elif i-p['entry_i']>=rule.hold:pending=(n['lots_open'],'TIME',i)
        actual=[(e['i'],e['decision_i'],e['lots'],e['price'],e['reason']) for e in p['events'][1:]]
        assert events==actual,(t.day,rule.key,events,actual)
        assert abs(n['net_pnl']-p['net'])<.03,(t.day,n['net_pnl'],p['net'])
        assert abs(n['costs']-p['fees'])<.03
        assert n['lots_open']==p['open']
        assert D.EP.worst_case_loss(p['entry'],p['lots'],65,E.FEE)<=p['reserve']+.01
        count+=1
    return count


def fixed_entry_stress(result):
    days=[]
    for row in result['days']:
        value=fees=0.;reserve=0.
        for p in row['positions']:
            entry=E.up(p['entry']+max(.05,p['entry']*.01))
            reserve+=E.reserve(entry,p['lots'])
            cash=-entry*p['lots']*65-E.fee(entry,p['lots']*65,True)
            fees+=E.fee(entry,p['lots']*65,True)
            for e in p['events'][1:]:
                sale=max(.05,E.down(e['price']-max(.05,e['price']*.01)))
                cost=E.fee(sale,e['lots']*65,False);fees+=cost
                cash+=sale*e['lots']*65-cost
            value+=round(cash,2)
        days.append(dict(day=row['day'],net=round(value,2),trades=row['trades'],spent=round(reserve,2),fees=round(fees,2),unresolved=row['unresolved']))
    return dict(summary=E.summary(days),days=days,qualification='Friction-only same-contract/entry/exit-clock test; quantities unchanged, not a replay of order refusals or stop decisions')


def evaluate_finalist(tapes,rule):
    results={};count=0
    for scenario in ('ordinary','adverse','catastrophe'):
        result=E.run_year(tapes,rule,scenario,True)
        for t,row in zip(tapes,result['days']):count+=native_audit(t,rule,row,scenario)
        results[scenario]=result
    results['fixed_entry_stress']=fixed_entry_stress(results['ordinary'])
    return dict(results=results,native_positions_checked=count,mismatches=0)


def neighbours(tapes,rule):
    space={'efficiency':(.3,.5,.7),'look':(5,10,20),'premium_high':(15.,20.,25.,35.),'stop':(.15,.2,.25,.3),'hold':(10,15,20,30)}
    out=[]
    for key,values in space.items():
        for v in values:
            if getattr(rule,key)==v:continue
            r=replace(rule,**{key:v})
            row=dict(parameter=key,value=v,ordinary=E.run_year(tapes,r)['summary'],adverse=E.run_year(tapes,r,'adverse')['summary'])
            out.append(row)
    return out


def main():
    tapes=D.load_year(2025)
    leaders=json.loads((D.HERE/'round-01.json').read_text())['leaders']
    out={}
    for p in leaders[:8]:
        rule=E.Rule(**p['rule'])
        data=evaluate_finalist(tapes,rule);data['neighbours']=neighbours(tapes,rule)
        out[rule.key]=data
        print('AUDITED_LEADER',rule.key,{s:r['summary']['net'] for s,r in data['results'].items()},'native',data['native_positions_checked'],flush=True)
    D.dump(D.HERE/'round-01-audit.json',out)
    baseline=E.run_year(tapes,E.Rule(setup='E011'),details=True)
    adverse=E.run_year(tapes,E.Rule(setup='E011'),'adverse',True)
    D.dump(D.HERE/'same-cash-baseline-2025.json',dict(ordinary=baseline,adverse=adverse,contract='Same cash/day reserve/limit/fee/brake/flat/next-open scenarios as E02; native E011 entry/management'))


if __name__=='__main__':main()
