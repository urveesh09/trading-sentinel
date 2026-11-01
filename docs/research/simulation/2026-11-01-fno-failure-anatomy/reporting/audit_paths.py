"""Independent first-executable exit and actual price/trace/admission audit."""
import importlib.util,json,sys
from collections import Counter
from datetime import date,datetime
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import anatomy_lab as L
from fno_exit_rules import evaluate_single_leg_exit,live_single_leg_exit_params
spec=importlib.util.spec_from_file_location('n07_parent_path_verifier',L.PARENT/'reporting/audit_paths.py');V=importlib.util.module_from_spec(spec);spec.loader.exec_module(V)


def check_exit(t,b,frame,observations):
    entry=datetime.fromisoformat(t['entry_time']);mode=t['n07_mode'];atr=L.P.P.E.context(frame,entry)['atr'];level=t['n03_entry_context']['broken_level'];risk=abs(t['entry_underlying']-t['initial_stop_underlying']);sign=1 if t['direction']=='LONG' else -1
    leg=L.Y.replay.OpenLeg(id=1,tradingsymbol=t['tradingsymbol'],token=1,direction=t['direction'],lots=t['entry_qty']//65,lot_size=65,entry_time=t['entry_time'],entry_premium=t['entry_premium'],entry_underlying=t['entry_underlying'],stop_underlying=t['initial_stop_underlying'],target_underlying=t['initial_target_underlying'],premium_stop=round((1-L.X.settings.FNO_STOP_PREMIUM_PCT)*t['entry_premium'],2),atr_at_entry=atr,delta_at_entry=.5,bar_ts=t['bar_ts'],initial_qty=t['entry_qty'],best_underlying=t['entry_underlying'])
    policy=L.Y.member_policy(L.Y.named('EFF'));params={**live_single_leg_exit_params(L.X.settings),**dict(policy.exit_overrides)};looks=structures=0;cost=b.get('cost') or (0.,0.)
    for obs in observations:
        if not t['entry_time']<obs.at.isoformat()<=t['exit_time']:continue
        qs=[q for q in obs.options.values() if q.contract.tradingsymbol==leg.tradingsymbol];q=qs[0] if len(qs)==1 else None;bid=q.bid if q and q.bid>0 else None
        net=(bid-leg.entry_premium)*leg.qty-L.P.P.E.calc_fno_costs(leg.entry_premium,bid,leg.qty)-(cost[0]+cost[1]*leg.lots)*leg.lots if bid is not None else None
        age=(obs.at-entry).total_seconds()/60;progress=sign*(obs.future.ltp-leg.entry_underlying)/risk;eligible=30<=age<60 and not leg.trail_active and net is not None and net<=0 and progress<.5;clock=60.;structure=None
        action='BASE60' if mode in ('BASE','STALL30','STRUCT30') else 'NATIVE60'
        if eligible and mode!='BASE':
            lost=False
            if mode in ('STRUCT30','STRUCT_OR_PREMIUM'):
                structure=V.V4.V.independent_context(frame,obs.at);structures+=1
                lost=bool(structure and structure['fresh'] and sign*(structure['close']-level)<0)
            if mode=='STALL30':clock=30.;action='STALL30'
            elif mode=='STRUCT30' and lost:clock=30.;action='STRUCT30'
            elif mode in ('PREMIUM_STALL','STRUCT_OR_PREMIUM'):
                if bid<=leg.entry_premium:clock=30.;action='PREMIUM_STALL'
                elif mode=='STRUCT_OR_PREMIUM' and lost:clock=30.;action='STRUCTURE_STALL'
                else:action='PRESERVE_GAINING_PREMIUM'
        basis=q.bid if q and q.bid>0 else q.ltp if q else 0.;hard=obs.at.hour*60+obs.at.minute>=(745 if obs.at.date().isoformat() in L.X.CAL.SPECIAL else 910)
        decision=evaluate_single_leg_exit(leg,now_ist=obs.at,fut_price=obs.future.ltp,exit_px_basis=basis,hard_flat=hard,params={**params,'FNO_TIME_STOP_MIN':clock},lock_breach_since=leg.lock_breach_since)
        leg.lock_breach_since=decision.lock_breach_since;leg.best_premium=decision.best_premium
        if decision.persist_trail:leg.trail_active=int(decision.trail_active);leg.trail_stop_underlying=decision.trail_stop;leg.best_underlying=decision.best_underlying
        looks+=1
        if decision.exit_reason and basis>0:
            assert obs.at.isoformat()==t['exit_time'] and decision.exit_reason==t['exit_reason'] and abs(basis-t['exit_premium'])<.001,(t['admission_id'],'first exit')
            if mode!='BASE':
                ctx=t['n07_exit_context'] if mode in ('PREMIUM_STALL','STRUCT_OR_PREMIUM') else t['n05_exit_context']
                assert ctx['action']==action and ctx['review_mode']==mode and ctx['parent_stall_eligible']==eligible and ctx['original_retest_level']==level
                assert abs(ctx['age_minutes']-age)<1e-8 and abs(ctx['progress_r']-progress)<1e-8
                assert (ctx['net_at_bid_after_cost'] is None)==(net is None)
                if net is not None:assert abs(ctx['net_at_bid_after_cost']-net)<1e-8
                if mode in ('STRUCT30','STRUCT_OR_PREMIUM') and eligible:
                    assert (ctx['structure'] is None)==(structure is None)
                    if structure:assert ctx['structure']['close']==structure['close'] and ctx['structure']['fresh']==structure['fresh']
            return looks,structures
    raise AssertionError(('no independently verified exit',t['admission_id']))


def run():
    L.B.O27F.deny_network();L.verify();L.B.L._init();y=L.B.YEAR;data=L.Y.dataset('year');table=L.C.table('year');counts=Counter();days={};frames={};hashes={}
    for phase in ('reference','candidate'):
        for name,key in json.loads((L.LOCAL/f'keys-{phase}-{y}.json').read_text()).items():
            p=L.LOCAL/'evals'/f'{key}.json';o=json.loads(p.read_text());b=o['book'];trace=json.loads((L.LOCAL/'traces'/f'{key}.json').read_text());accepted=[r for r in trace['decisions'] if r['outcome']=='accepted'];assert len(accepted)==len(o['trades']);hashes[p.relative_to(L.ROOT).as_posix()]=L.B.P.sha(p)
            for t in o['trades']:
                day=t['entry_time'][:10];d=date.fromisoformat(day)
                if day not in days:days[day]=data.observations(day)[0];frames[day]=data.futures_frame(data.future_contract(data.front_expiry(d)).token,d)
                packets={o.at.isoformat():o for o in days[day]};a,z=packets[t['entry_time']],packets[t['exit_time']]
                es=[q for q in a.options.values() if q.contract.tradingsymbol==t['tradingsymbol']];xs=[q for q in z.options.values() if q.contract.tradingsymbol==t['tradingsymbol']]
                assert len(es)==len(xs)==1 and abs(es[0].ask-t['entry_premium'])<.001 and abs((xs[0].bid if xs[0].bid>0 else xs[0].ltp)-t['exit_premium'])<.001
                matches=[r for r in accepted if r['at']==t['entry_time'] and r['bar_ts']==t['bar_ts'] and r['entry_expert']==t['entry_expert']];assert len(matches)==1 and matches[0]['selected_profile']==t['selected_profile']
                assert L.Y.ROUTER.allowed(t['entry_gate'],table[day]);counts['admissions_and_trace_bindings']+=1;counts['archive_prices']+=2
                if t['entry_expert']=='EFF':
                    V.V4.V.check_retest(t,frames[day],data);counts['retest_paths']+=1
                    looks,structures=check_exit(t,b,frames[day],days[day]);counts['exit_lifecycles']+=1;counts['management_observations']+=looks;counts['structure_reviews']+=structures
    L.verify();out=dict(year=y,counts=dict(counts),path_or_price_or_admission_errors=0,file_sha256=hashes);L.X.write(L.LOCAL/f'path-check-{y}.json',out);print('PATHS_VERIFIED',y,dict(counts),flush=True)


if __name__=='__main__':run()
