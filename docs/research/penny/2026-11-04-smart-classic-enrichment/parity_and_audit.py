"""Independent bookkeeping and fixed-capital native-selector parity checks."""
from __future__ import annotations
from collections import defaultdict,Counter
from pathlib import Path
import hashlib,json,sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'python-engine'));sys.path.insert(0,str(ROOT/'scripts'))
from smart_classic_study import seen_panel,excluded_etfs,write
from smart_classic_enrichment import snapshots,auction_orders,Policy
import penny_smart_v3 as native


def run():
    checks=[];excluded=excluded_etfs()
    for panel in ['h1','recent']:
        days,daily,calendar=seen_panel(panel);by={(d.ticker,d.date):d for d in days};history=defaultdict(list)
        hist=snapshots(daily,calendar);actual,_=auction_orders(days,daily,calendar,Policy('native','auction_ref',exit_minute=970),2000,excluded)
        chosen={o.day:o.ticker for o in actual};compared=0;diff=[]
        for day in calendar:
            candidates=[];thin={}
            for t,f in hist[day].items():
                d=by.get((t,day))
                if d and d.day_open:
                    candidates.append(native.Candidate(t,f['close'],d.day_open,f['tv'],f['medvol']))
                    thin[t]=native.thin_estimate(history[t],f['medvol'])[0]
            picks,_=native.select(candidates,capital=2000,thin=thin)
            expected=picks[0].ticker if picks else None
            if chosen.get(day)!=expected:diff.append({'date':day,'native':expected,'research':chosen.get(day)})
            compared+=1
            for (t,date),d in by.items():
                if date==day:history[t].append(d.bars[0][5] if d.bars and d.bars[0][0]==555 else 0.)
        checks.append({'panel':panel,'sessions':compared,'differences':diff,'scope':'pure native select/fixed2000/same historical proxy inputs; not lifecycle or fill parity'})
        assert not diff,diff[:3]
    write(HERE/'native-selector-parity.json',checks)
    manifests=[]
    for p in sorted((HERE/'_local/results').glob('*.json')):
        r=json.loads(p.read_text());trades=r.get('trades',[]);s=r['summary'];net=sum(t['net'] for t in trades)
        assert abs(net-s['net'])<.011,p
        for t in trades:assert abs(t['side']*(t['exit']-t['entry'])*t['qty']-t['fees']-t['net'])<1e-6,p
        if r['open']==0:
            inferred=r['cash']-net;assert min(abs(inferred-2000),abs(inferred-25000))<1e-6,p
        else:inferred=r.get('capital',25000 if '_25000_' in p.name else 2000)
        day=Counter()
        for i in r['intents']:day[i['date']]+=i['reserved']
        assert max(day.values(),default=0)<=inferred+.011,p
        manifests.append({'path':str(p.relative_to(HERE)).replace('\\','/'),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
            'n':s['n'],'net':s['net'],'open':r['open'],'max_daily_reserved':max(day.values(),default=0),
            'net_ex_best_winner':round(net-max([0.]+[t['net'] for t in trades]),2)})
    write(HERE/'financial-audit.json',{'artifacts':len(manifests),'checks':'trade fee/net identity; no own-cash over-allocation; flat terminal cash; original raw ex_best may mean best trade on all-loss arms',
        'selector_parity':checks,'results':manifests})
    print('Audited',len(manifests),'artifacts; native parity',sum(x['sessions'] for x in checks),'sessions,0 differences')


if __name__=='__main__':run()
