"""Independent full-precision user-risk objective and two-arm resampling."""
import json,math,sys
from collections import defaultdict
from datetime import date
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import analyze_refine as A
L=A.L
def run():
    objects=A.objects();r=A.load(HERE/'results.json');every=sorted(d for ds in A.A.sessions().values() for d in ds);weeks=sorted({date.fromisoformat(d).isocalendar()[:2] for d in every});weekly={};exact={};maxres=0.
    for name in objects['2024']:
        ws={w:0. for w in weeks};exact[name]={}
        for y in A.YEARS:
            rows=sorted(objects[y][name]['trades'],key=lambda t:(t['exit_time'],t['entry_time']));cash=peak=250000.;dd=0.;daily=defaultdict(float)
            for t in rows:
                cash+=t['net_pnl'];peak=max(peak,cash);dd=max(dd,(peak-cash)/peak);day=t['exit_time'][:10];daily[day]+=t['net_pnl'];ws[date.fromisoformat(day).isocalendar()[:2]]+=t['net_pnl']
            net=math.fsum(t['net_pnl'] for t in rows);maxres=max(maxres,abs(net-(cash-250000.)));assert abs(net-(cash-250000.))<1e-7
            got=r['books'][name]['years'][y];assert got['net']==round(cash-250000.) and got['fall_pct']==round(dd,4) and got['trades']==len(rows)
            exact[name][y]={'net':net,'fall':dd,'best_day':max([0.,*daily.values()]),'best_trade':max([0.,*[t['net_pnl'] for t in rows]])}
            for k,v in exact[name][y].items():assert abs(v-r['books'][name]['exact_years'][y][k])<1e-10
        weekly[name]=list(ws.values());assert np.allclose(weekly[name],r['books'][name]['weekly'],rtol=0,atol=1e-8)
    base='NORMAL|BALANCED_RETEST|BASE';stall='NORMAL|BALANCED_RETEST|STALL30';vectors=[];ts=[]
    for name,c in r['candidates'].items():
        flags={'positive_each_year':all(exact[name][y]['net']>0 for y in A.YEARS),'without_best_trade':all(exact[name][y]['net']-exact[name][y]['best_trade']>0 for y in A.YEARS),'without_best_day':all(exact[name][y]['net']-exact[name][y]['best_day']>0 for y in A.YEARS),
            'net_not_worse_both_each_year':all(exact[name][y]['net']>=max(exact[base][y]['net'],exact[stall][y]['net']) for y in A.YEARS),'better_total_stall':sum(exact[name][y]['net'] for y in A.YEARS)>sum(exact[stall][y]['net'] for y in A.YEARS),
            'drawdown_not_worse_both_each_year':all(exact[name][y]['fall']<=min(exact[base][y]['fall'],exact[stall][y]['fall']) for y in A.YEARS)}
        for k,v in flags.items():assert c['checks'][k]==v,(name,k)
        for benchmark,label in [(stall,'paired_t_stall'),(base,'paired_t_base')]:
            diff=np.array(weekly[name])-np.array(weekly[benchmark]);sd=diff.std(ddof=1);t=float(diff.mean()/(sd/math.sqrt(len(diff)))) if sd>0 else 0.;assert round(t,2)==c[label]
            if benchmark==stall:vectors.append(diff);ts.append(t);assert c['checks']['paired_weekly_stall']==(t>=2)
    x=np.array(vectors);n=x.shape[1];signs=np.random.default_rng(110501).choice([-1.,1.],size=(4096,(n+3)//4));signs=np.repeat(signs,4,axis=1)[:,:n];z=signs[:,:,None]*x.T[None,:,:];sd=z.std(axis=1,ddof=1)/math.sqrt(n);tests=np.divide(z.mean(axis=1),sd,out=np.zeros_like(sd),where=sd>0);maxima=tests.max(axis=1)
    for (name,c),t in zip(r['candidates'].items(),ts):assert c['search_adjusted_p']==(1+int(np.sum(maxima>=t)))/4097
    out={'annual_paths':len(exact)*3,'weekly_vectors':len(weekly),'normal_candidate_tests':len(vectors),'strict_profit_and_drawdown_against_both':True,'resamples':4096,'block_weeks':4,'seed':110501,'max_cash_residual':maxres,'financial_or_acceptance_or_statistical_errors':0}
    L.X.write(HERE/'statistics-crosschecks.json',out);print('STATISTICS_VERIFIED',out,flush=True)
if __name__=='__main__':run()
