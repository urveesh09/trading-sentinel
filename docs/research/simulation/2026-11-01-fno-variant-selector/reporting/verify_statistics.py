"""Independent cash/weekly/resampling reconstruction of all frozen tests."""
import json,math,sys
from collections import defaultdict
from datetime import date
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import analyze_variant as A
L=A.L


def run():
    objs=A.objects();r=json.loads((HERE/'results.json').read_text());every=sorted(d for ds in A.A.sessions().values() for d in ds);weeks=sorted({date.fromisoformat(d).isocalendar()[:2] for d in every});weekly={};exact={};maxerror=0.
    for name in objs['2024']:
        ws={w:0. for w in weeks};exact[name]={}
        for y in A.YEARS:
            rows=sorted(objs[y][name]['trades'],key=lambda t:(t['exit_time'],t['entry_time']));cash=peak=250000.;fall=0.;daily=defaultdict(float)
            for t in rows:
                cash+=t['net_pnl'];peak=max(peak,cash);fall=max(fall,(peak-cash)/peak);day=t['exit_time'][:10];daily[day]+=t['net_pnl'];ws[date.fromisoformat(day).isocalendar()[:2]]+=t['net_pnl']
            net=math.fsum(t['net_pnl'] for t in rows);maxerror=max(maxerror,abs(net-(cash-250000.)));assert abs(net-(cash-250000.))<1e-7
            exact[name][y]=dict(net=net,fall=fall,best_day=max([0.,*daily.values()]),best_trade=max([0.,*[t['net_pnl'] for t in rows]]))
            got=r['books'][name];assert got['years'][y]['net']==round(net) and got['years'][y]['fall_pct']==round(fall,4) and got['years'][y]['trades']==len(rows)
            for k,v in exact[name][y].items():assert abs(v-got['exact_years'][y][k])<1e-10
        weekly[name]=list(ws.values());assert np.allclose(weekly[name],r['books'][name]['weekly'],rtol=0,atol=1e-8)
    differences=[];ts=[]
    for name,c in r['candidates'].items():
        x=exact[name];flags=dict(positive_each_year=all(x[y]['net']>0 for y in A.YEARS),
            sample=min(len(objs[y][name]['trades']) for y in A.YEARS)>=12 and sum(len(objs[y][name]['trades']) for y in A.YEARS)>=60,
            without_best_trade=all(x[y]['net']-x[y]['best_trade']>0 for y in A.YEARS),without_best_day=all(x[y]['net']-x[y]['best_day']>0 for y in A.YEARS),
            net_not_worse_all_references_each_year=all(x[y]['net']>=max(exact[v][y]['net'] for v in ('BASE','STALL30','STRUCT30')) for y in A.YEARS),
            drawdown_not_worse_all_references_each_year=all(x[y]['fall']<=min(exact[v][y]['fall'] for v in ('BASE','STALL30','STRUCT30')) for y in A.YEARS))
        halves=[]
        for y in A.YEARS:
            for low,high in ((1,6),(7,12)):
                halves.append(math.fsum(t['net_pnl'] for t in objs[y][name]['trades'] if low<=int(t['exit_time'][5:7])<=high))
        assert np.allclose(halves,c['halves'],atol=1e-8,rtol=0);flags['five_halves']=sum(v>0 for v in halves)>=5
        diff=np.array(weekly[name])-np.array(weekly['STALL30']);sd=diff.std(ddof=1);t=float(diff.mean()/(sd/math.sqrt(len(diff)))) if sd else 0.
        assert round(t,2)==c['paired_t_stall'];flags['paired_weekly_stall']=t>=2
        for k,v in flags.items():assert c['checks'][k]==v,(name,k)
        differences.append(diff);ts.append(t)
    x=np.array(differences);n=x.shape[1];signs=np.random.default_rng(110601).choice([-1.,1.],size=(4096,(n+3)//4));signs=np.repeat(signs,4,axis=1)[:,:n]
    z=signs[:,:,None]*x.T[None,:,:];sd=z.std(axis=1,ddof=1)/math.sqrt(n);tests=np.divide(z.mean(axis=1),sd,out=np.zeros_like(sd),where=sd>0);maximum=tests.max(axis=1)
    for (name,c),t in zip(r['candidates'].items(),ts):
        p=(1+int(np.sum(maximum>=t)))/4097
        assert c['adjusted_p']==p and c['checks']['max_t']==(p<=.05) and c['passes']==all(c['checks'].values())
    out=dict(annual_cash_paths=18,weekly_vectors=6,primary_comparisons=2,resamples=4096,block_weeks=4,seed=110601,max_cash_residual=maxerror,financial_or_acceptance_or_statistical_errors=0)
    L.X.write(HERE/'statistics-crosschecks.json',out);print('STATISTICS_VERIFIED',out,flush=True)


if __name__=='__main__':run()
