"""Post-freeze mechanics/sensitivity audit; fixed finalists, no selection/tuning."""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import mean
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'python-engine'))
from overnight_enrichment import Policy,legacy_lab,risk_history,simulate
import overnight_enrichment as engine


def main():
    files=sorted((HERE/'_local/results').glob('r*.json'))+sorted((HERE/'_local/older/results').glob('*.json'))
    checks=[]
    for path in files:
        r=json.loads(path.read_text());net=sum(t['net'] for t in r['trades'])
        assert abs(net-r['summary']['net'])<.011,path
        for t in r['trades']:
            assert abs(t['exit']*t['shares']-t['notional']-t['cost']-t['net'])<1e-6,path
            assert t['shares']==t['regular_qty']+t['postclose_qty'] and t['shares']>0
        byday=Counter()
        for i in r['intents']:byday[i['date']]+=i['reserved']
        assert max(byday.values(),default=0)<=25000.000001,path
        if not r['open_at_end']:assert abs(r['curve'][-1][1]-25000-net)<1e-6,path
        checks.append({'file':str(path.relative_to(HERE)),'trades':len(r['trades']),
                      'open_at_end':r['open_at_end'],'max_daily_reserved':max(byday.values(),default=0)})
    lab=legacy_lab();v2=HERE.parent/'2026-11-04-overnight-v2'
    # Actual-panel parity checks the *legacy* screen-before-depth control.
    import exam
    from dataclasses import replace
    days=lab.load(v2/'_local/days-kite.pkl');a=replace(exam.FINALISTS['TWO_NIGHT'],compound=False,entry_bps=0,exit_bps=5)
    old=lab.run_book(days,a,start='2025-07-15',end='2025-08-08')
    new=simulate(days,Policy('parity',screen_before_depth=True),start='2025-07-15',end='2025-08-08')
    assert old['summary']=={k:new['summary'][k] for k in old['summary']}
    assert [t['shares'] for t in old['trades']]==[t['shares'] for t in new['trades']]
    report={'mechanics':checks,'real_panel_parity':{'n':len(old['trades']),'mismatches':0,'summary':old['summary']},'sensitivity':[]}
    for panel,path,start,end in [
        ('yahoo',v2/'_local/days-yahoo.pkl','2023-01-01','2026-10-30'),
        ('older',HERE/'_local/older/days.pkl','2015-01-01','2018-12-31')]:
        days=lab.load(path);hist=risk_history(days)
        for rb,xb,pfill in [(36,5,.5),(36,5,.75),(60,20,.5)]:
            pairs=[]
            for seed in range(20261105,20261115):
                rows=[]
                for p in [Policy('V2_NATIVE'),Policy('V3_COST_ROUTE',regular_fraction=.5,route_rule='positive_net')]:
                    r=simulate(days,p,start=start,end=end,regular_bps=rb,exit_bps=xb,winning_close_fill=pfill,seed=seed,histories=hist)
                    rows.append({'name':p.name,'net':r['summary']['net'],'dd':r['summary']['dd'],'open':r['open_at_end']})
                pairs.append({'seed':seed,'rows':rows,'delta':rows[1]['net']-rows[0]['net']})
            report['sensitivity'].append({'panel':panel,'model':[rb,xb,pfill],'seeds':pairs,
                'positive_deltas':sum(p['delta']>0 for p in pairs),
                'mean_delta':mean(p['delta'] for p in pairs),'min_delta':min(p['delta'] for p in pairs),
                'max_delta':max(p['delta'] for p in pairs)})
        # Correlated day-level nonfills, same deterministic draw for both names.
        original=engine.fill_uniform
        try:
            engine.fill_uniform=lambda ticker,day,seed:original('SHARED_DAY',day,seed)
            rows=[]
            for p in [Policy('V2_NATIVE'),Policy('V3_COST_ROUTE',regular_fraction=.5,route_rule='positive_net')]:
                r=simulate(days,p,start=start,end=end,winning_close_fill=.5,histories=hist)
                rows.append({'name':p.name,'summary':r['summary'],'open':r['open_at_end']})
            report['sensitivity'].append({'panel':panel,'model':'50% winner fills correlated within day; seed20261104','rows':rows})
        finally:engine.fill_uniform=original
        print('audited',panel,flush=True)
    (HERE/'audit-results.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print('mechanics',len(checks),'artifacts; actual-panel parity',report['real_panel_parity']['n'],flush=True)


if __name__=='__main__':main()
