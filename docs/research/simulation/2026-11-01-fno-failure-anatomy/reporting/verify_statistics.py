"""Independently reconstruct full cash, periods, weekly vectors and primary max-T."""
import json,sys,math
from datetime import date
from collections import defaultdict
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import analyze_anatomy as A
L=A.L


def run():
    objs=A.objects();r=json.loads((HERE/'results.json').read_text());ds=A.A.sessions();weeks=sorted({date.fromisoformat(d).isocalendar()[:2] for days in ds.values() for d in days});weekly={};exact={};counts={};maxerror=0.
    for name in objs['2024']:
        ws={w:0. for w in weeks};exact[name]={};counts[name]={}
        for y in A.YEARS:
            rows=sorted(objs[y][name]['trades'],key=lambda t:(t['exit_time'],t['entry_time']));cash=peak=250000.;dd=0.;daily=defaultdict(float)
            for t in rows:cash+=t['net_pnl'];peak=max(peak,cash);dd=max(dd,(peak-cash)/peak);daily[t['exit_time'][:10]]+=t['net_pnl'];ws[date.fromisoformat(t['exit_time'][:10]).isocalendar()[:2]]+=t['net_pnl']
            net=math.fsum(t['net_pnl'] for t in rows);maxerror=max(maxerror,abs(net-cash+250000.));assert abs(net-cash+250000.)<1e-7
            exact[name][y]=dict(net=net,fall=dd,best_day=max([0.,*daily.values()]),best_trade=max([0.,*[t['net_pnl'] for t in rows]]));counts[name][y]=len(rows)
            for k,v in exact[name][y].items():assert abs(v-r['books'][name]['exact_years'][y][k])<1e-10
            got=r['books'][name]['years'][y];assert got['net']==round(net) and got['fall_pct']==round(dd,4) and got['trades']==len(rows)
        weekly[name]=list(ws.values());assert np.allclose(weekly[name],r['books'][name]['weekly'],atol=1e-8,rtol=0)
    diffs=[];ts=[]
    for name,c in r['candidates'].items():
        z=exact[name];a=exact['NORMAL|STALL30'];b=exact['NORMAL|STRUCT30']
        flags=dict(positive_each_year=all(z[y]['net']>0 for y in A.YEARS),sample=min(counts[name].values())>=12 and sum(counts[name].values())>=60,
            without_best_trade=all(z[y]['net']-z[y]['best_trade']>0 for y in A.YEARS),without_best_day=all(z[y]['net']-z[y]['best_day']>0 for y in A.YEARS),
            higher_net_than_both_each_year=all(z[y]['net']>max(a[y]['net'],b[y]['net']) for y in A.YEARS),closed_drawdown_no_larger_either_each_year=all(z[y]['fall']<=min(a[y]['fall'],b[y]['fall']) for y in A.YEARS))
        periods=[]
        for y in A.YEARS:
            for lo,hi in (((1,5),(6,10)) if y=='2026' else ((1,6),(7,12))):periods.append(math.fsum(t['net_pnl'] for t in objs[y][name]['trades'] if lo<=int(t['exit_time'][5:7])<=hi))
        assert np.allclose(periods,c['periods'],atol=1e-8,rtol=0);flags['five_periods']=sum(v>0 for v in periods)>=5
        for bench,label in [('NORMAL|STALL30','paired_t_stall'),('NORMAL|STRUCT30','paired_t_structure')]:
            diff=np.array(weekly[name])-np.array(weekly[bench]);se=diff.std(ddof=1)/math.sqrt(len(diff));t=float(diff.mean()/se) if se else 0.;assert round(t,2)==c[label]
            if bench=='NORMAL|STALL30':diffs.append(diff);ts.append(t);flags['paired_weekly_stall']=t>=2
        for k,v in flags.items():assert c['checks'][k]==v,(name,k)
    x=np.array(diffs);n=x.shape[1];signs=np.random.default_rng(110701).choice([-1.,1.],size=(4096,(n+3)//4));signs=np.repeat(signs,4,axis=1)[:,:n];z=signs[:,:,None]*x.T[None,:,:];se=z.std(axis=1,ddof=1)/math.sqrt(n);tests=np.divide(z.mean(axis=1),se,out=np.zeros_like(se),where=se>0);maximum=tests.max(axis=1)
    for c,t in zip(r['candidates'].values(),ts):assert c['adjusted_p']==(1+int(np.sum(maximum>=t)))/4097 and c['passes']==all(c['checks'].values())
    out=dict(annual_cash_paths=45,weekly_vectors=15,primary_comparisons=2,block_weeks=4,resamples=4096,seed=110701,max_cash_residual=maxerror,financial_or_acceptance_or_statistical_errors=0)
    L.X.write(HERE/'statistics-crosschecks.json',out);print('STATISTICS_VERIFIED',out,flush=True)


if __name__=='__main__':run()
