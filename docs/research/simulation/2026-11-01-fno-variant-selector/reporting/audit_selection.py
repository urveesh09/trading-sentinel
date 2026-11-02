"""Independent model construction/persistence audit, not policy-function reuse."""
from collections import defaultdict,Counter
from datetime import date,timedelta
import json,math,statistics,sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import variant_lab as L


def audit():
    import analyze_variant as A
    manifest=json.loads((HERE/'decision-manifest.json').read_text());models_count=choices=0;counts={};hashes={}
    for y,files in L.reference_files().items():
        records={v:json.loads(p.read_text())['trades'] for v,p in files.items()};days=sorted(A.A.sessions()[y]);actual=json.loads((L.LOCAL/f'decisions-{y}.json').read_text());models=json.loads((L.LOCAL/f'models-{y}.json').read_text())
        for policy,anchor in [('MAIN_ANCHOR','MAIN'),('STRUCT_ANCHOR','STRUCT30')]:
            pending=None;streak=0;counts[y+'|'+policy]=Counter()
            for pos,day in enumerate(days):
                window=days[max(0,pos-84):pos];allowed=set(window);hist={v:[t for t in rs if t['exit_time'][:10] in allowed] for v,rs in records.items()}
                daily={v:defaultdict(float) for v in hist}
                for v,rs in hist.items():
                    for t in rs:daily[v][t['exit_time'][:10]]+=t['net_pnl'];assert t['exit_time'][:10]<day
                def dd(rs):
                    cash=high=250000.;worst=0.
                    for t in sorted(rs,key=lambda t:(t['exit_time'],t['entry_time'])):cash+=t['net_pnl'];high=max(high,cash);worst=max(worst,1-cash/high)
                    return worst
                def week(d):
                    stamp=date.fromisoformat(d);return (stamp-timedelta(days=stamp.weekday())).isoformat()
                weeks=sorted({week(d) for d in window});eligible=[]
                m=models[policy][day];latest=max((t['exit_time'] for rs in hist.values() for t in rs),default=None)
                assert m['latest_label_exit']==latest and m['sessions']==len(window)
                for v in ('BASE','STALL30','STRUCT30','MAIN'):
                    if v==anchor:continue
                    delta={d:daily[v][d]-daily[anchor][d] for d in window};w={k:0. for k in weeks}
                    for d,n in delta.items():w[week(d)]+=n
                    xs=list(w.values());score=statistics.mean(xs)-statistics.stdev(xs)/math.sqrt(len(xs)) if len(xs)>=2 else None
                    checks=dict(weeks=len(xs)>=8,paired_days=sum(abs(n)>1e-8 for n in delta.values())>=10,challenger_trades=len(hist[v])>=12,anchor_trades=len(hist[anchor])>=6,
                                score=score is not None and score>0,without_best=math.fsum(delta.values())-max([0.,*delta.values()])>0,drawdown=dd(hist[v])<=dd(hist[anchor])+1e-14)
                    got=m['profiles'][v];assert checks==got['checks'] and all(checks.values())==got['eligible'],(y,day,policy,v,checks,got)
                    if score is None:assert got['score'] is None
                    else:assert abs(score-got['score'])<1e-8
                    if all(checks.values()):eligible.append((v,score))
                    models_count+=1
                eligible.sort(key=lambda z:(-z[1],('BASE','STALL30','STRUCT30','MAIN').index(z[0])))
                best=eligible[0][0] if eligible else anchor
                if best==anchor:pending=None;streak=0;chosen=anchor
                else:streak=streak+1 if pending==best else 1;pending=best;chosen=best if streak>=2 else anchor
                d=actual[policy][day];assert d['variant']==chosen and d['best_evidence']==best and d['consecutive_days']==streak and d['asof']==day and d['latest_label_exit']==latest
                counts[y+'|'+policy][chosen]+=1;choices+=1
        for prefix in ('models','decisions'):
            file=L.LOCAL/f'{prefix}-{y}.json';hashes[file.relative_to(L.ROOT).as_posix()]=L.B.P.sha(file)
        assert manifest['decisions'][y]['sha256']==hashes[(L.LOCAL/f'decisions-{y}.json').relative_to(L.ROOT).as_posix()]
    out=dict(independent_profile_models=models_count,causal_daily_choices=choices,counts=counts,selection_errors=0,file_sha256=hashes)
    L.X.write(HERE/'selection-crosschecks.json',out);print('SELECTION_VERIFIED',models_count,choices,flush=True)


if __name__=='__main__':audit()
