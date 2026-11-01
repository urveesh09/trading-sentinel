"""Descriptive original EFF source features; no rule fitting or P&L pairing."""
import json,math,sys
from collections import defaultdict
from datetime import date,datetime
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import exit_lab as L
def load(p):return json.loads(p.read_text())
def number(v):return float(v) if v is not None and math.isfinite(v) else None
def one():
    L.B.O27F.deny_network();L.verify();L.B.L._init();L.Y.speedups();y=L.B.YEAR;data=L.Y.dataset('year');keys=load(L.OLD/f'keys-{y}.json');base=load(L.OLD/'evals'/f'{keys["NORMAL|MAIN|BASE"]}.json')['trades'];retest=load(L.OLD/'evals'/f'{keys["NORMAL|MAIN|RETEST"]}.json')['trades'];links=defaultdict(list);frames={};packets={};out=[]
    for t in retest:
        if t['entry_expert']=='EFF':links[(t['n03_entry_context']['source_bar'],t['direction'])].append({'admission_id':t['admission_id'],'confirmation_bar':t['bar_ts'],'entry_time':t['entry_time']})
    for t in base:
        if t['entry_expert']!='EFF':continue
        day=t['entry_time'][:10];d=date.fromisoformat(day);now=datetime.fromisoformat(t['entry_time'])
        if day not in frames:frames[day]=data.futures_frame(data.future_contract(data.front_expiry(d)).token,d);packets[day]={o.at.isoformat():o for o in data.observations(day)[0]}
        features=L.E._features(frames[day]);r=features.loc[t['bar_ts']]
        obs=packets[day][t['entry_time']];qs=[q for q in obs.options.values() if q.contract.tradingsymbol==t['tradingsymbol']];assert len(qs)==1;q=qs[0];qty=t['entry_qty'];lots=qty//65
        linked=links[(t['bar_ts'],t['direction'])];assert len(linked)<=1
        record={'original_admission_id':t['admission_id'],'source_bar':t['bar_ts'],'entry_time':t['entry_time'],'year':y,'direction':t['direction'],
            'known_at_original_entry':{'atr':number(r.atr),'efficiency4':number(r.er4),'body_fraction':number(abs(r.close-r.open)/max(r.high-r.low,1e-9)),'rvol':number(r.rvol),
                'signed_distance_vwap_atr':number((1 if t['direction']=='LONG' else -1)*(r.close-r.vwap)/r.atr),'stretch':t['stretch'],
                'stop_distance':abs(t['entry_underlying']-t['initial_stop_underlying']),'target_distance':abs(t['initial_target_underlying']-t['entry_underlying']),
                'option_ask':q.ask,'option_bid':q.bid,'spread':q.ask-q.bid,'premium_per_atr':number(q.ask/r.atr),'days_to_expiry':(q.contract.expiry-d).days,'minutes_after_open':now.hour*60+now.minute-555,
                'immediate_roundtrip_cost_at_current_quote':(q.ask-q.bid)*qty+L.E.calc_fno_costs(q.ask,q.bid,qty)+(200+5*lots)*lots if q.bid>0 else None},
            'later_labels_never_earlier_inputs':{'original_net':t['net_pnl'],'original_exit_reason':t['exit_reason'],'admitted_n03_retest_setup_lineage':linked},
            'lineage_limit':'Source-bar/direction links describe a later setup; they are NOT economic admission pairs and are never used to calculate paired P&L or route trades.'}
        out.append(record)
    L.verify();L.X.write(L.LOCAL/f'entry-cases-{y}.json',{'status':'POST_RUN_DESCRIPTIVE_ONLY_NO_FITTED_GATE','records':out});print('ENTRY_CASES',y,len(out),flush=True)
if __name__=='__main__':one()
