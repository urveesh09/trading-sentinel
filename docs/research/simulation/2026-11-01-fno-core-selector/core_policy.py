"""Past-only whole-policy comparison with explicit MAIN fallback."""
from collections import defaultdict
from datetime import date,timedelta
import math,statistics

ORDER=('TPB_ONE','NO_EFF')


def week(day):
    d=date.fromisoformat(day);return (d-timedelta(days=d.weekday())).isoformat()


def drawdown(rows):
    equity=peak=250000.;fall=0.
    for r in sorted(rows,key=lambda r:r['exit_time']):
        equity+=r['net_pnl'];peak=max(peak,equity);fall=max(fall,(peak-equity)/peak)
    return fall


def evidence(records,asof,sessions):
    days=[d for d in sorted(sessions) if d<asof][-84:];inside=set(days)
    histories={p:[r for r in rs if r['exit_time'][:10] in inside and r['exit_time'][:10]<asof] for p,rs in records.items()}
    daily={p:defaultdict(float) for p in histories}
    for p,rows in histories.items():
        for r in rows:
            assert r['entry_time']<=r['exit_time'] and r['exit_time'][:10]<asof
            daily[p][r['exit_time'][:10]]+=r['net_pnl']
    base=histories['MAIN'];base_dd=drawdown(base);out={}
    weeks=sorted({week(d) for d in days})
    for p in ORDER:
        rows=histories[p];diff={d:daily[p][d]-daily['MAIN'][d] for d in days};weekly={w:0. for w in weeks}
        for d,n in diff.items():weekly[week(d)]+=n
        values=list(weekly.values());n=len(values)
        score=statistics.fmean(values)-statistics.stdev(values)/math.sqrt(n) if n>=2 else None
        active=sum(abs(v)>1e-8 for v in diff.values());without=sum(diff.values())-max([0.,*diff.values()]);dd=drawdown(rows)
        checks={'weeks':n>=8,'paired_days':active>=10,'challenger_trades':len(rows)>=12,'main_trades':len(base)>=6,
                'score':score is not None and score>0,'without_best':without>0,'drawdown':dd<=max(1.5*base_dd,.05)}
        out[p]={'score':score,'eligible':all(checks.values()),'checks':checks,'paired_days':active,'trades':len(rows),'main_trades':len(base),
                'paired_net':sum(diff.values()),'without_best_improvement_day':without,'drawdown':dd,'main_drawdown':base_dd}
    return {'asof':asof,'window_start':days[0] if days else None,'window_end':days[-1] if days else None,'sessions':len(days),
            'latest_label_exit':max((r['exit_time'] for rows in histories.values() for r in rows),default=None),'profiles':out}


def choose(models,allowed):
    """Require two consecutive decision days; a failed case returns MAIN now."""
    out={};pending=None;count=0
    for day,m in sorted(models.items()):
        candidates=[p for p in ORDER if p in allowed and m['profiles'][p]['eligible']]
        candidates.sort(key=lambda p:(-m['profiles'][p]['score'],ORDER.index(p)))
        best=candidates[0] if candidates else 'MAIN'
        if best=='MAIN':pending=None;count=0;active='MAIN'
        else:
            count=count+1 if pending==best else 1;pending=best;active=best if count>=2 else 'MAIN'
        out[day]={'profile':active,'best_evidence':best,'consecutive_days':count,'asof':day,
                  'window_start':m['window_start'],'window_end':m['window_end'],'latest_label_exit':m['latest_label_exit']}
    return out
