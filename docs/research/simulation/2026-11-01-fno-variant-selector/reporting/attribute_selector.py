"""Separate supported decisions, matched exit effects and changed admissions."""
import json,sys,math
from collections import Counter
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import analyze_variant as A
L=A.L


def identity(t):
    return tuple(t.get(k) for k in ('entry_time','tradingsymbol','direction','entry_premium','entry_underlying','entry_qty','initial_stop_underlying','initial_target_underlying','bar_ts','entry_expert'))


def run():
    objs=A.objects();out={}
    for y,books in objs.items():
        models=json.loads((L.LOCAL/f'models-{y}.json').read_text());ds=json.loads((L.LOCAL/f'decisions-{y}.json').read_text())
        for policy,anchor in [('MAIN_ANCHOR','MAIN'),('STRUCT_ANCHOR','STRUCT30')]:
            new={identity(t):t for t in books[policy]['trades']};old={identity(t):t for t in books[anchor]['trades']}
            assert len(new)==len(books[policy]['trades']) and len(old)==len(books[anchor]['trades'])
            common=new.keys()&old.keys();paired=math.fsum(new[k]['net_pnl']-old[k]['net_pnl'] for k in common);new_only=math.fsum(new[k]['net_pnl'] for k in new.keys()-old.keys());old_only=math.fsum(old[k]['net_pnl'] for k in old.keys()-new.keys())
            actual=math.fsum(t['net_pnl'] for t in new.values())-math.fsum(t['net_pnl'] for t in old.values());assert abs(actual-(paired+new_only-old_only))<1e-7
            support={v:dict(max_paired_days=max(m['profiles'][v]['paired_days'] for m in models[policy].values()),eligible_dates=sum(m['profiles'][v]['eligible'] for m in models[policy].values()),
                failed_guard_dates=dict(Counter(k for m in models[policy].values() for k,passed in m['profiles'][v]['checks'].items() if not passed))) for v in L.R.ORDER if v!=anchor}
            out[y+'|'+policy]=dict(anchor=anchor,selected_days=dict(Counter(d['variant'] for d in ds[policy].values())),admitted_variants=dict(Counter(t['n06_variant'] for t in new.values())),
                modeled_net_by_admitted_variant={v:math.fsum(t['net_pnl'] for t in new.values() if t['n06_variant']==v) for v in L.R.ORDER},
                support=support,matched_economic_admissions=len(common),candidate_only_admissions=len(new.keys()-old.keys()),anchor_only_admissions=len(old.keys()-new.keys()),
                paired_exit_delta=paired,unpaired_candidate_net=new_only,unpaired_anchor_net=old_only,total_delta=actual)
    L.X.write(HERE/'selector-attribution.json',dict(comparisons=out,unpaired_terms='Changed original-vs-retest/LOW-day/cash/priority opportunities; not pure paired exit improvement.',attribution_errors=0));print('ATTRIBUTION_VERIFIED',flush=True)


if __name__=='__main__':run()
