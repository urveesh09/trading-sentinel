"""Availability of all prior balanced early-exit review locations, no fitting."""
import json,sys
from datetime import datetime,date
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import refine_lab as L
def run():
    L.B.O27F.deny_network();L.B.L._init();y=L.B.YEAR;data=L.Y.dataset('year');keys=json.loads((L.OLD/f'keys-{y}.json').read_text());rows=json.loads((L.OLD/'evals'/f'{keys["NORMAL|BALANCED_RETEST|STALL_ONLY"]}.json').read_text())['trades'];frames={};checks=[]
    for t in rows:
        if t['entry_expert']!='EFF' or t['n04_exit_context']['action']!='STALL30':continue
        day=t['exit_time'][:10];d=date.fromisoformat(day)
        if day not in frames:frames[day]=data.futures_frame(data.future_contract(data.front_expiry(d)).token,d)
        c=L.P.E.context(frames[day],datetime.fromisoformat(t['exit_time']));level=t['n03_entry_context'].get('broken_level')
        checks.append({'admission_id':t['admission_id'],'review_time':t['exit_time'],'immutable_level_available':level is not None,'closed_context_available':c is not None,'fresh':bool(c and c['fresh']),'positive_bid':t['n04_exit_context']['bid'] is not None})
    L.X.write(L.LOCAL/f'early-feature-audit-{y}.json',{'year':y,'status':'PRE_SCORE_AVAILABILITY_ONLY','review_locations':len(checks),'checks':checks});print('EARLY_FEATURES',y,len(checks),sum(c['fresh'] and c['immutable_level_available'] and c['positive_bid'] for c in checks),flush=True)
if __name__=='__main__':run()
