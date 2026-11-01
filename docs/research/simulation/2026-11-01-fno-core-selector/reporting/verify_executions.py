"""Archive-price, admission-key, chosen-profile and management continuity audit."""
import json,sys
from datetime import date,datetime,timedelta
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import core_lab as X
def run():
    X.B.O27F.deny_network();X.verify('candidate');X.Y.speedups();year=X.B.YEAR;data=X.Y.dataset('year');table=X.C.table('year')
    frames={};packets={};count=prices=trace_count=0;profile_counts={};hashes={};choices=json.loads((X.LOCAL/f'decisions-{year}.json').read_text())
    for phase in ('reference','candidate'):
        keys=json.loads((X.LOCAL/f'keys-{phase}-{year}.json').read_text())
        for name,key in keys.items():
            f=X.LOCAL/'evals'/f'{key}.json';obj=json.loads(f.read_text());tracefile=X.LOCAL/'traces'/f'{key}.json';trace=json.loads(tracefile.read_text())
            assert trace['book']==obj['book'] and trace['window']==obj['window'];hashes[f.relative_to(X.ROOT).as_posix()]=X.B.P.sha(f)
            accepted=[v for v in trace['decisions'] if v['outcome']=='accepted'];assert len(accepted)==len(obj['trades'])
            for t in obj['trades']:
                assert t.get('net_pnl') is not None
                day=t['entry_time'][:10];entry=datetime.fromisoformat(t['entry_time']);exit=datetime.fromisoformat(t['exit_time']);d=date.fromisoformat(day)
                if day not in frames:frames[day]=data.futures_frame(data.future_contract(data.front_expiry(d)).token,d)
                bar=X.Y.replay._last_closed_bar(frames[day],entry);assert bar==t['bar_ts']
                if phase=='candidate':
                    decision=choices[name][day];assert decision['profile']==t['selected_profile'] and decision['asof']==t['selection_asof']==day
                    assert decision['latest_label_exit']==t['selection_latest_label_exit']
                    assert entry-(datetime.fromisoformat(bar).replace(tzinfo=entry.tzinfo)+timedelta(minutes=5))<timedelta(minutes=5)
                    assert not decision['latest_label_exit'] or decision['latest_label_exit'][:10]<day
                else:assert t['selected_profile']==name and t['selection_asof'] is None
                assert X.Y.ROUTER.allowed(t['entry_gate'],table[day])
                if t['origin']=='TPB_LOW':
                    assert t['entry_expert']=='TPB' and t['direction']=='SHORT' and t['selected_profile'] in ('TPB_ONE','TPB_FULL')
                    if t['selected_profile']=='TPB_ONE':assert t['entry_qty']==65
                else:assert t['entry_gate']==X.B.W.OPEN
                if t['selected_profile']=='NO_EFF':assert t['entry_expert']!='EFF'
                assert t['exit_reason'] not in ('router_state_invalidated','profile_changed','strategy_switched')
                hits=[a for a in accepted if a.get('signal_bar')==t['bar_ts'] and a.get('entry_expert')==t['entry_expert'] and a['at']==t['entry_time']]
                assert len(hits)==1 and hits[0]['selected_profile']==t['selected_profile'];trace_count+=1
                if day not in packets:packets[day]={o.at.isoformat():o for o in data.observations(day)[0]}
                a=packets[day][t['entry_time']];b=packets[day][t['exit_time']]
                es=[q for q in a.options.values() if q.contract.tradingsymbol==t['tradingsymbol']];xs=[q for q in b.options.values() if q.contract.tradingsymbol==t['tradingsymbol']]
                assert len(es)==len(xs)==1 and abs(es[0].ask-t['entry_premium'])<.001
                assert abs((xs[0].bid if xs[0].bid>0 else xs[0].ltp)-t['exit_premium'])<.001
                prices+=2;count+=1;profile_counts[t['selected_profile']]=profile_counts.get(t['selected_profile'],0)+1
    X.verify('candidate');out={'year':year,'admissions_verified':count,'archive_prices_verified':prices,'accepted_trace_bindings':trace_count,'choice_gate_or_price_errors':0,'profile_admissions':profile_counts,'file_sha256':hashes}
    X.write(X.LOCAL/f'execution-check-{year}.json',out);print('EXECUTIONS_VERIFIED',year,count,prices,flush=True)
if __name__=='__main__':run()
