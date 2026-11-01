"""Archive path anatomy; causal snapshots separated from later observed extrema."""
from datetime import date,datetime
import json,sys
import diagnose as D
N=D.N6;L=N.P;load=D.load


def run():
    N.B.O27F.deny_network();N.B.L._init();y=N.B.YEAR;data=N.Y.dataset('year');frames={};packets={};rows={v:load(p)['trades'] for v,p in N.reference_files()[y].items()};records=[]
    bases={D.key(t):t for t in rows['BASE']}
    for t in rows['STALL30']:
        day=t['entry_time'][:10];d=date.fromisoformat(day)
        if day not in packets:
            packets[day]=data.observations(day)[0];frames[day]=data.futures_frame(data.future_contract(data.front_expiry(d)).token,d)
        entry=datetime.fromisoformat(t['entry_time']);end=datetime.fromisoformat(t['exit_time']);old=bases.get(D.key(t));base_end=datetime.fromisoformat(old['exit_time']) if old else end
        risk=abs(t['entry_underlying']-t['initial_stop_underlying']);sign=1 if t['direction']=='LONG' else -1;path=[];review=None
        for obs in packets[day]:
            if not entry<obs.at<=max(end,base_end):continue
            qs=[q for q in obs.options.values() if q.contract.tradingsymbol==t['tradingsymbol']];q=qs[0] if len(qs)==1 else None
            if q is None or q.bid<=0:continue
            gross=(q.bid-t['entry_premium'])*t['entry_qty'];cost=N.P.P.E.calc_fno_costs(t['entry_premium'],q.bid,t['entry_qty'])+(200+5*t['entry_qty']//65)*(t['entry_qty']//65);net=gross-cost
            state=dict(at=obs.at.isoformat(),age=(obs.at-entry).total_seconds()/60,bid=q.bid,gross=gross,net=net,progress_r=sign*(obs.future.ltp-t['entry_underlying'])/risk)
            path.append(state)
            if obs.at==end:
                c=N.P.P.E.context(frames[day],obs.at);level=(t.get('n03_entry_context') or {}).get('broken_level')
                review={**state,'structure':c,'level':level,'underlying_level_lost':bool(c and level is not None and sign*(c['close']-level)<0),
                    'closed_bar_direction':sign*(c['close']-c['previous_close']) if c else None,'directional_vwap_gap':sign*(c['close']-c['vwap']) if c else None}
        held=[p for p in path if p['at']<=t['exit_time']];after=[p for p in path if p['at']>t['exit_time']]
        assert held and review and abs(held[-1]['net']-t['net_pnl'])<.0001
        records.append(dict(admission_id=t['admission_id'],entry_time=t['entry_time'],expert=t['entry_expert'],direction=t['direction'],entry_premium=t['entry_premium'],quantity=t['entry_qty'],exit_reason=t['exit_reason'],
            known_at_exit=review,later_labels=dict(net=t['net_pnl'],best_observed_held_net=max(p['net'] for p in held),worst_observed_held_net=min(p['net'] for p in held),
                best_at=max(held,key=lambda p:p['net'])['at'],last_same_economics_base_net=old['net_pnl'] if old else None,
                later_base_path_min_gross=min((p['gross'] for p in after),default=None),later_base_path_max_net=max((p['net'] for p in after),default=None)),
            gross_positive_but_net_losing_exit=review['gross']>0 and t['net_pnl']<0))
    N.X.write(D.HERE/f'path-anatomy-{y}.json',dict(year=y,records=records,observed_snapshots_not_intrabar_extrema=True,missing_quotes_not_interpolated=True));print('PATH_ANATOMY',y,'all_trades',len(records),'eff',[dict(day=r['entry_time'][:10],net=r['later_labels']['net'],gross=r['known_at_exit']['gross'],best=r['later_labels']['best_observed_held_net'],reason=r['exit_reason']) for r in records if r['expert']=='EFF'],flush=True)


if __name__=='__main__':run()
