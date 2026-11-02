"""Independent causal structural-review and first-executable-exit audit."""
import json,sys
from collections import Counter
from datetime import date,datetime,timedelta
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path[:0]=[str(HERE),str(HERE.parent/'2026-11-01-fno-exit-ablation/reporting')]
import refine_lab as L
import audit_paths as V4
from fno_exit_rules import evaluate_single_leg_exit,live_single_leg_exit_params

def exit_path(t,frame,observations):
    entry=datetime.fromisoformat(t['entry_time']);mode=t['n05_mode'];atr=L.P.E.context(frame,entry)['atr'];level=t['n03_entry_context']['broken_level']
    leg=L.Y.replay.OpenLeg(id=1,tradingsymbol=t['tradingsymbol'],token=1,direction=t['direction'],lots=t['entry_qty']//65,lot_size=65,entry_time=t['entry_time'],entry_premium=t['entry_premium'],entry_underlying=t['entry_underlying'],stop_underlying=t['initial_stop_underlying'],target_underlying=t['initial_target_underlying'],premium_stop=round((1-L.X.settings.FNO_STOP_PREMIUM_PCT)*t['entry_premium'],2),atr_at_entry=atr,delta_at_entry=.5,bar_ts=t['bar_ts'],initial_qty=t['entry_qty'],best_underlying=t['entry_underlying'])
    p=L.Y.member_policy(L.Y.named('EFF'));params={**live_single_leg_exit_params(L.X.settings),**dict(p.exit_overrides)};risk=abs(leg.entry_underlying-leg.stop_underlying);looks=0;structure_checks=0
    for obs in observations:
        if not t['entry_time']<obs.at.isoformat()<=t['exit_time']:continue
        qs=[q for q in obs.options.values() if q.contract.tradingsymbol==leg.tradingsymbol];q=qs[0] if qs else None;bid=q.bid if q and q.bid>0 else None
        net=(bid-leg.entry_premium)*leg.qty-L.P.E.calc_fno_costs(leg.entry_premium,bid,leg.qty)-(200+5*leg.lots)*leg.lots if bid is not None else None
        sign=1 if leg.direction=='LONG' else -1;progress=sign*(obs.future.ltp-leg.entry_underlying)/risk;age=(obs.at-entry).total_seconds()/60;eligible=30<=age<60 and not leg.trail_active and net is not None and net<=0 and progress<.5;clock=60.;action='BASE60';s=None
        if eligible:
            if mode=='STALL30':clock=30.;action='STALL30'
            elif mode=='DELAY45' and age>=45:clock=45.;action='DELAY45'
            elif mode=='STRUCT30':
                s=V4.V.independent_context(frame,obs.at);structure_checks+=1
                if s and s['fresh'] and sign*(s['close']-level)<0:clock=30.;action='STRUCT30'
        basis=q.bid if q and q.bid>0 else (q.ltp if q else 0.);hard=obs.at.hour*60+obs.at.minute>=(745 if obs.at.date().isoformat() in L.X.CAL.SPECIAL else 910)
        d=evaluate_single_leg_exit(leg,now_ist=obs.at,fut_price=obs.future.ltp,exit_px_basis=basis,hard_flat=hard,params={**params,'FNO_TIME_STOP_MIN':clock},lock_breach_since=leg.lock_breach_since)
        leg.lock_breach_since=d.lock_breach_since;leg.best_premium=d.best_premium
        if d.persist_trail:leg.trail_active=int(d.trail_active);leg.trail_stop_underlying=d.trail_stop;leg.best_underlying=d.best_underlying
        looks+=1
        if d.exit_reason and basis>0:
            assert obs.at.isoformat()==t['exit_time'] and d.exit_reason==t['exit_reason'] and abs(basis-t['exit_premium'])<.001,(t['admission_id'],'first exit',obs.at.isoformat(),t['exit_time'])
            c=t['n05_exit_context'];assert c['action']==action and c['review_mode']==mode and c['parent_stall_eligible']==eligible and c['original_retest_level']==level and abs(c['age_minutes']-age)<1e-8 and abs(c['progress_r']-progress)<1e-8
            assert (c['net_at_bid_after_cost'] is None)==(net is None)
            if net is not None:assert abs(c['net_at_bid_after_cost']-net)<1e-8
            if mode=='STRUCT30' and eligible:
                assert (c['structure'] is None)==(s is None)
                if s:assert c['structure']['fresh']==s['fresh'] and c['structure']['close']==s['close']
            return looks,structure_checks
    raise AssertionError(('no verified exit',t['admission_id']))

def run():
    L.B.O27F.deny_network();L.verify();L.B.L._init();y=L.B.YEAR;data=L.Y.dataset('year');table=L.C.table('year');keys=json.loads((L.LOCAL/f'keys-{y}.json').read_text());days={};frames={};count=prices=retests=exits=looks=structures=0;actions=Counter();hashes={}
    for name,key in keys.items():
        file=L.LOCAL/'evals'/f'{key}.json';obj=json.loads(file.read_text());trace=json.loads((L.LOCAL/'traces'/f'{key}.json').read_text());accepted=[r for r in trace['decisions'] if r['outcome']=='accepted'];assert len(accepted)==len(obj['trades']);hashes[file.relative_to(L.ROOT).as_posix()]=L.B.P.sha(file)
        for t in obj['trades']:
            day=t['entry_time'][:10];d=date.fromisoformat(day)
            if day not in days:days[day]=data.observations(day)[0];frames[day]=data.futures_frame(data.future_contract(data.front_expiry(d)).token,d)
            frame=frames[day];packets={o.at.isoformat():o for o in days[day]};a=packets[t['entry_time']];b=packets[t['exit_time']]
            es=[q for q in a.options.values() if q.contract.tradingsymbol==t['tradingsymbol']];xs=[q for q in b.options.values() if q.contract.tradingsymbol==t['tradingsymbol']]
            assert len(es)==len(xs)==1 and abs(es[0].ask-t['entry_premium'])<.001 and abs((xs[0].bid if xs[0].bid>0 else xs[0].ltp)-t['exit_premium'])<.001
            matches=[r for r in accepted if r['at']==t['entry_time'] and r.get('entry_expert')==t['entry_expert'] and r['bar_ts']==t['bar_ts']];assert len(matches)==1 and matches[0]['selected_profile']==t['selected_profile']
            assert L.Y.ROUTER.allowed(t['entry_gate'],table[day])
            if t['entry_expert']=='EFF' and t['n03_variant']=='RETEST':V4.V.check_retest(t,frame,data);retests+=1
            if t['entry_expert']=='EFF' and t['n05_mode']!='BASE':
                a,b=exit_path(t,frame,days[day]);looks+=a;structures+=b;exits+=1;actions[t['n05_exit_context']['action']]+=1
            count+=1;prices+=2
    L.verify();out={'year':y,'admissions_and_trace_bindings':count,'archive_prices':prices,'retests_verified':retests,'exit_lifecycles':exits,'management_observations':looks,'structural_reviews':structures,'exit_actions':dict(actions),'choice_price_path_errors':0,'file_sha256':hashes}
    L.X.write(L.LOCAL/f'path-check-{y}.json',out);print('PATHS_VERIFIED',y,{k:v for k,v in out.items() if k!='file_sha256'},flush=True)
if __name__=='__main__':run()
