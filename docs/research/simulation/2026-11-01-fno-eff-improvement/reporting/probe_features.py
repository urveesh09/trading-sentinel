"""Pre-score availability only; historical admissions are probe locations."""
import json,sys
from datetime import datetime,date
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import eff_lab as L
def run():
    L.B.O27F.deny_network();L.Y.speedups();year=L.B.YEAR;data=L.Y.dataset('year');keys=json.loads((L.PARENT_LOCAL/f'keys-reference-{year}.json').read_text())
    rows=json.loads((L.PARENT_LOCAL/'evals'/f'{keys["MAIN"]}.json').read_text())['trades'];rows=[r for r in rows if r['entry_expert']=='EFF'];days={};frames={};checks=[]
    for t in rows:
        day=t['entry_time'][:10];d=date.fromisoformat(day)
        if day not in days:
            days[day]={o.at.isoformat():o for o in data.observations(day)[0]};frames[day]=data.futures_frame(data.future_contract(data.front_expiry(d)).token,d)
        obs=days[day][t['entry_time']];qs=[q for q in obs.options.values() if q.contract.tradingsymbol==t['tradingsymbol']];assert len(qs)==1
        ctx=L.context(frames[day],datetime.fromisoformat(t['entry_time']))
        checks.append({'entry_time':t['entry_time'],'context_available':ctx is not None,'fresh':bool(ctx and ctx['fresh']),'valid_volume':bool(ctx and ctx['valid_volume']),
            'positive_bid_ask':qs[0].bid>0 and qs[0].ask>0,'dated_contract':qs[0].contract.expiry.isoformat(),'initial_stop_known':t['initial_stop_underlying'] is not None})
    out={'year':year,'probed_eff_admissions':len(rows),'causal_contexts':sum(c['context_available'] for c in checks),'fresh_contexts':sum(c['fresh'] for c in checks),
         'positive_bid_ask':sum(c['positive_bid_ask'] for c in checks),'invalid_volume_contexts':sum(not c['valid_volume'] for c in checks),'historical_iv_news_depth_not_available':True,'checks':checks}
    L.X.write(L.LOCAL/f'feature-audit-{year}.json',out);print('FEATURES',year,{k:v for k,v in out.items() if k!='checks'},flush=True)
if __name__=='__main__':run()
