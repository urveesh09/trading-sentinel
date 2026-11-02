"""Independent arithmetic and past-label audit; does not call selector scoring."""
import json,math,statistics,sys
from collections import defaultdict,Counter
from datetime import date,timedelta
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import analyze_core as A
X=A.X
def run():
    ds=A.sessions();every=sorted(d for days in ds.values() for d in days);refs=A.objects('reference')
    records={p:[t for y in A.YEARS for t in refs[y][p]['trades']] for p in ('MAIN','TPB_ONE','NO_EFF')}
    models={d:v for y in A.YEARS for d,v in A.load(HERE/f'_local/models-{y}.json').items()}
    eligibility={};maxerror=0.;scores=0
    def week(d):
        day=date.fromisoformat(d);return (day-timedelta(days=day.weekday())).isoformat()
    def fall(rows):
        cash=peak=250000.;worst=0.
        for r in sorted(rows,key=lambda r:r['exit_time']):
            cash+=r['net_pnl'];peak=max(peak,cash);worst=max(worst,1-cash/peak)
        return worst
    for d,m in sorted(models.items()):
        days=[v for v in every if v<d][-84:];inside=set(days)
        rows={p:[r for r in rs if r['exit_time'][:10] in inside and r['exit_time'][:10]<d] for p,rs in records.items()}
        assert all(r['entry_time']<=r['exit_time'] and r['exit_time'][:10]<d for rs in rows.values() for r in rs)
        assert m['asof']==d and m['sessions']==len(days) and m['window_start']==(days[0] if days else None) and m['window_end']==(days[-1] if days else None)
        assert m['latest_label_exit']==max((r['exit_time'] for rs in rows.values() for r in rs),default=None)
        daily={p:defaultdict(float) for p in rows}
        for p,rs in rows.items():
            for r in rs:daily[p][r['exit_time'][:10]]+=r['net_pnl']
        eligibility[d]={}
        for p in ('TPB_ONE','NO_EFF'):
            diff={v:daily[p][v]-daily['MAIN'][v] for v in days};weeks={week(v):0. for v in days}
            for day,value in diff.items():weeks[week(day)]+=value
            vals=list(weeks.values());n=len(vals);score=statistics.mean(vals)-statistics.stdev(vals)/math.sqrt(n) if n>=2 else None
            without=sum(diff.values())-max([0.,*diff.values()]);dd=fall(rows[p]);base=fall(rows['MAIN'])
            checks={'weeks':n>=8,'paired_days':sum(abs(v)>1e-8 for v in diff.values())>=10,'challenger_trades':len(rows[p])>=12,'main_trades':len(rows['MAIN'])>=6,
                    'score':score is not None and score>0,'without_best':without>0,'drawdown':dd<=max(1.5*base,.05)}
            got=m['profiles'][p];assert checks==got['checks'] and all(checks.values())==got['eligible']
            for a,b in ((score,got['score']),(without,got['without_best_improvement_day']),(sum(diff.values()),got['paired_net']),(dd,got['drawdown']),(base,got['main_drawdown'])):
                if a is None:assert b is None
                else:maxerror=max(maxerror,abs(a-b));assert abs(a-b)<1e-8
            assert got['trades']==len(rows[p]) and got['main_trades']==len(rows['MAIN']) and got['paired_days']==sum(abs(v)>1e-8 for v in diff.values())
            eligibility[d][p]=(all(checks.values()),score);scores+=1
    usage={};choice_count=0
    for policy,allowed in [('CORE_ADD',('TPB_ONE',)),('CORE_SELECT',('TPB_ONE','NO_EFF'))]:
        pending=None;count=0;usage[policy]=Counter()
        for day in every:
            ranked=sorted([p for p in allowed if eligibility[day][p][0]],key=lambda p:(-eligibility[day][p][1],allowed.index(p)))
            best=ranked[0] if ranked else 'MAIN'
            if best=='MAIN':pending=None;count=0;active='MAIN'
            else:count=count+1 if pending==best else 1;pending=best;active=best if count>=2 else 'MAIN'
            actual=A.load(HERE/f'_local/decisions-{day[:4]}.json')[policy][day]
            assert (actual['profile'],actual['best_evidence'],actual['consecutive_days'])==(active,best,count)
            assert actual['asof']==day and actual['window_start']==models[day]['window_start'] and actual['window_end']==models[day]['window_end'] and actual['latest_label_exit']==models[day]['latest_label_exit']
            usage[policy][active]+=1;choice_count+=1
    out={'daily_models':len(models),'relative_scores':scores,'daily_policy_choices':choice_count,'future_or_unclosed_labels_used':0,
         'independent_arithmetic_max_error':maxerror,'mismatches':0,'decision_days':{p:dict(v) for p,v in usage.items()}}
    X.write(HERE/'training-crosschecks.json',out);print('TRAINING_VERIFIED',out,flush=True)
if __name__=='__main__':run()
