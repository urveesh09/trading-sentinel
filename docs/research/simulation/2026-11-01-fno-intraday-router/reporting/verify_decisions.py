"""Audit corrected decisions against actual archived packets and past models."""
import json,sys
from collections import defaultdict
from datetime import date,datetime
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path[:0]=[str(HERE/'freshness'),str(HERE)]
import fresh_lab as F
X=F.X


def run():
    X.B.O27F.deny_network();F.verify('candidate');X.Y.speedups();year=X.B.YEAR;data=X.Y.dataset('year');table=X.C.table('year')
    frames={};packets={};checked=0;prices=0;switches=0;mixed={};hashes={}
    models=json.loads((F.LOCAL/f'models-{year}.json').read_text())
    keys=json.loads((F.LOCAL/f'keys-candidate-{year}.json').read_text())
    for name,key in keys.items():
        p=F.LOCAL/'evals'/f'{key}.json';obj=json.loads(p.read_text());hashes[p.relative_to(X.ROOT).as_posix()]=X.B.P.sha(p);days=defaultdict(list)
        for t in obj['trades']:
            assert t.get('net_pnl') is not None
            day=t['entry_time'][:10];d=date.fromisoformat(day);entry=datetime.fromisoformat(t['entry_time']);exit=datetime.fromisoformat(t['exit_time'])
            if day not in frames:frames[day]=data.futures_frame(data.future_contract(data.front_expiry(d)).token,d)
            observed,bar,history=F.state_at(frames[day],entry)
            assert bar==t['bar_ts'] and observed['state']==t['router_state'] and not F.stale(bar,entry)
            macro='HIGH' if X.Y.ROUTER.allowed('adx_abs30:HIGH',table[day]) else 'LOW'
            assert t['router_cell']==t['router_state']+'|'+macro
            policy=t['router_policy'];expert=t['router_expert']
            if policy=='LEARN' and not t['router_fallback']:
                month=entry.date().isoformat()[:7]+'-01';m=models['models'][month]
                assert t['router_model_asof']==month and m['latest_label_exit'][:10]<month
                assert expert in [r['expert'] for r in m['choices'].get(t['router_cell'],[])]
                assert models['session_index'][day]>=90
            else:
                assert expert in X.R.rule_experts(t['router_state'])
                if policy=='LEARN':assert models['session_index'][day]<90
            assert X.R.direction_allowed(t['router_state'],t['direction'])
            if day not in packets:packets[day]={o.at.isoformat():o for o in data.observations(day)[0]}
            a=packets[day][t['entry_time']];b=packets[day][t['exit_time']]
            e=[q for q in a.options.values() if q.contract.tradingsymbol==t['tradingsymbol']]
            z=[q for q in b.options.values() if q.contract.tradingsymbol==t['tradingsymbol']]
            assert len(e)==len(z)==1
            assert abs(e[0].ask-t['entry_premium'])<.001
            basis=z[0].bid if z[0].bid>0 else z[0].ltp
            assert abs(basis-t['exit_premium'])<.001
            prices+=2
            if t['exit_reason']=='router_state_invalidated':
                state,last,states=F.state_at(frames[day],exit);tail=[v['state'] for k,v in states.items() if k<=last][-3:]
                assert X.R.invalidates(t['router_state'],tail,t['direction']) and z[0].bid>0 and (exit-entry).total_seconds()>=900
                assert t['exit_router_state']==state['state'];switches+=1
            days[day].append({'entry':t['entry_time'],'exit':t['exit_time'],'state':t['router_state'],'expert':expert,'net':t['net_pnl'],'exit_reason':t['exit_reason']});checked+=1
        if name.startswith('EX|'):
            mix=[d for d,rows in sorted(days.items()) if len({r['expert'] for r in rows})>1]
            mixed[name]={'days_with_multiple_experts':len(mix),'first_chronological_example':days[mix[0]] if mix else None,'example_date':mix[0] if mix else None}
    F.verify('candidate')
    out={'year':year,'decisions_verified':checked,'exact_archive_quote_checks':prices,'switch_exits_verified':switches,'state_or_choice_or_price_errors':0,'actual_intraday_mix':mixed,'candidate_file_sha256':hashes}
    X.write(F.LOCAL/f'decision-check-{year}.json',out);print('DECISIONS_VERIFIED',year,checked,'prices',prices,'state_exits',switches,flush=True)


if __name__=='__main__':run()
