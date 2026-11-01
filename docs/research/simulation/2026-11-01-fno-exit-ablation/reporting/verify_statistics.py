"""Independent cash paths, weekly differences and eight-arm multiplicity check."""
import json,math,statistics,sys
from collections import defaultdict
from datetime import date
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parents[1];sys.path[:0]=[str(HERE),str(HERE/'reporting')]
import analyze_exit as A
L=A.L
def run():
    objects=A.objects();results=A.load(HERE/'results.json');sessions=A.A.sessions();every=sorted(d for ds in sessions.values() for d in ds);weeks=sorted({date.fromisoformat(d).isocalendar()[:2] for d in every});weekly={};paths={};maxerror=0.
    for name in objects['2024']:
        cash_by_week={w:0. for w in weeks};paths[name]={}
        for y in A.YEARS:
            rows=sorted(objects[y][name]['trades'],key=lambda t:(t['exit_time'],t['entry_time']));cash=peak=250000.;dd=0.;daily=defaultdict(float)
            for t in rows:
                cash+=t['net_pnl'];peak=max(peak,cash);dd=max(dd,1-cash/peak);d=t['exit_time'][:10];daily[d]+=t['net_pnl'];cash_by_week[date.fromisoformat(d).isocalendar()[:2]]+=t['net_pnl']
            got=results['books'][name]['years'][y];assert got['net']==round(cash-250000) and got['fall_pct']==round(dd,4) and got['trades']==len(rows)
            assert got['best_day']==round(max([0.,*daily.values()]))
            exact=sum(t['net_pnl'] for t in rows);maxerror=max(maxerror,abs(exact-(cash-250000)));assert abs(exact-(cash-250000))<1e-7
            paths[name][y]={'net':exact,'dd':dd,'without_best_day':exact-max([0.,*daily.values()]),'without_best_trade':exact-max([0.,*[t['net_pnl'] for t in rows]])}
        weekly[name]=list(cash_by_week.values());assert np.allclose(weekly[name],results['books'][name]['weekly'],rtol=0,atol=1e-8)
    vectors=[];real_t=[];rounded_differences=[]
    for name,candidate in results['candidates'].items():
        baseline=name.rsplit('|',1)[0]+'|BASE';diff=np.array(weekly[name])-np.array(weekly[baseline]);vectors.append(diff);t=float(diff.mean()/(diff.std(ddof=1)/math.sqrt(len(diff)))) if diff.std(ddof=1)>0 else 0.;real_t.append(t)
        assert round(t,2)==candidate['paired_t']
        exact={'positive_each_year':all(paths[name][y]['net']>0 for y in A.YEARS),'without_best_trade':all(paths[name][y]['without_best_trade']>0 for y in A.YEARS),'without_best_day':all(paths[name][y]['without_best_day']>0 for y in A.YEARS),
            'not_worse_each_year':all(paths[name][y]['net']>=paths[baseline][y]['net']-1e-7 for y in A.YEARS),'better_total':sum(paths[name][y]['net'] for y in A.YEARS)>sum(paths[baseline][y]['net'] for y in A.YEARS),
            'drawdown':all(paths[name][y]['dd']<=max(1.5*paths[baseline][y]['dd'],.05) for y in A.YEARS),'paired_weekly':t>=2}
        for flag,value in exact.items():
            if value!=candidate['checks'][flag]:rounded_differences.append({'book':name,'flag':flag,'exact':value,'reported':candidate['checks'][flag]})
    x=np.array(vectors);n=x.shape[1];signs=np.random.default_rng(110401).choice([-1.,1.],size=(4096,(n+3)//4));signs=np.repeat(signs,4,axis=1)[:,:n];z=signs[:,:,None]*x.T[None,:,:];sd=z.std(axis=1,ddof=1)/math.sqrt(n)
    tests=np.divide(z.mean(axis=1),sd,out=np.zeros_like(sd),where=sd>0);maxima=tests.max(axis=1);ps=[(1+int(np.sum(maxima>=t)))/4097 for t in real_t]
    for (name,candidate),p in zip(results['candidates'].items(),ps):assert abs(candidate['search_adjusted_p']-p)<1e-12
    assert not rounded_differences,rounded_differences
    out={'annual_paths':len(paths)*3,'weekly_vectors':len(weekly),'candidate_relative_tests':len(vectors),'block_weeks':4,'resamples':4096,'seed':110401,'max_cash_reconciliation_residual':maxerror,'rounded_decision_differences':rounded_differences,'score_p_or_cash_errors':0}
    L.X.write(HERE/'statistics-crosschecks.json',out);print('STATISTICS_VERIFIED',out,flush=True)
if __name__=='__main__':run()
