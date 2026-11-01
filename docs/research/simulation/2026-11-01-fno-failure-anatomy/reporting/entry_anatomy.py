"""Descriptive, known-at-entry context for all wins AND losses; no fitted filter."""
from datetime import date,datetime
import json,sys,math
from collections import defaultdict
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path[:0]=[str(HERE),str(HERE.parent/'2026-11-01-fno-variant-selector')]
import variant_lab as L


def run():
    L.B.O27F.deny_network();L.B.L._init();y=L.B.YEAR;data=L.Y.dataset('year');file=L.reference_files()[y]['STALL30'];rows=json.loads(file.read_text())['trades'];frames={};packets={};records=[];groups={}
    for t in rows:
        day=t['entry_time'][:10];d=date.fromisoformat(day);now=datetime.fromisoformat(t['entry_time'])
        if day not in frames:frames[day]=data.futures_frame(data.future_contract(data.front_expiry(d)).token,d);packets[day]={o.at.isoformat():o for o in data.observations(day)[0]}
        c=L.P.P.E.context(frames[day],now);sign=1 if t['direction']=='LONG' else -1;obs=packets[day][t['entry_time']];quotes=[q for q in obs.options.values() if q.contract.tradingsymbol==t['tradingsymbol']];assert len(quotes)==1;q=quotes[0]
        if c:assert datetime.fromisoformat(c['bar']).replace(tzinfo=now.tzinfo).timestamp()+300<=now.timestamp()
        vwap_side='UNKNOWN' if not c else 'WITH_VWAP' if sign*(c['close']-c['vwap'])>=0 else 'BEHIND_VWAP'
        bar_side='UNKNOWN' if not c else 'WITH_LAST_CLOSE_CHANGE' if sign*(c['close']-c['previous_close'])>=0 else 'AGAINST_LAST_CLOSE_CHANGE'
        known=dict(entry_time=t['entry_time'],expert=t['entry_expert'],direction=t['direction'],origin=t['origin'],entry_premium=t['entry_premium'],quantity=t['entry_qty'],
            underlying=t['entry_underlying'],initial_stop=t['initial_stop_underlying'],initial_target=t['initial_target_underlying'],closed_context=c,vwap_side=vwap_side,last_bar_side=bar_side,spread=q.ask-q.bid)
        record=dict(admission_id=t['admission_id'],known_at_entry=known,later_labels=dict(net=t['net_pnl'],exit_reason=t['exit_reason'],exit_time=t['exit_time']));records.append(record)
        for label in ('vwap_side','last_bar_side'):
            key=label+'|'+known[label];g=groups.setdefault(key,dict(trades=0,wins=0,losses=0,net=0.,win_net=0.,loss_net=0.));g['trades']+=1;g['wins']+=int(t['net_pnl']>0);g['losses']+=int(t['net_pnl']<0);g['net']+=t['net_pnl'];g['win_net']+=max(0.,t['net_pnl']);g['loss_net']+=min(0.,t['net_pnl'])
    L.X.write(HERE/f'entry-anatomy-{y}.json',dict(year=y,records=records,descriptive_groups=groups,entry_clock_errors=0,limit='All N04 admissions, including wins; groups are retrospective seen-data diagnostics, not a selected gate or proof that excluding a bucket preserves future profit.'))
    print('ENTRY_ANATOMY',y,len(records),groups,flush=True)


if __name__=='__main__':run()
