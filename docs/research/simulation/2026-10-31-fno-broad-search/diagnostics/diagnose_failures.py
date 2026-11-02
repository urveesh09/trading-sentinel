"""Descriptive causal partitions; never a router or new selection rule."""
import json,sys
from datetime import date
from pathlib import Path
from collections import defaultdict
import pandas as pd
HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'2026-10-31-fno-conditional-followup')]
import lab_broad as B
import diagnose as D


def run():
    B.O27F.deny_network();B.Y.speedups();year=B.YEAR;data=B.Y.dataset('year');daily=B.P.daily_bars()
    files={json.loads(p.read_text())['book'].get('o31'):p for p in (HERE/'_local/evals').glob('year_'+year+'*.json')}
    frames={};out=[]
    for control in ('RAW|MAIN','RAW|E|tpb_puts'):
        trades=json.loads(files[control].read_text())['trades']
        for i,t in enumerate(trades):
            assert t.get('net_pnl') is not None
            day=t['entry_time'][:10];d=date.fromisoformat(day)
            if day not in frames:frames[day]=data.futures_frame(data.future_contract(data.front_expiry(d)).token,d)
            frame=frames[day];f=D.causal_inputs(frame,day,t['bar_ts'],t['direction'],daily)
            changed=frame.copy();changed.loc[changed.index>pd.Timestamp(t['bar_ts']),['open','high','low','close']]*=2
            future=daily.copy();future.loc[future.index>=pd.Timestamp(day),:]*=2
            B.O27F._FEATURES.clear()
            assert f==D.causal_inputs(changed,day,t['bar_ts'],t['direction'],future),('future leakage',year,control,i)
            member=('SHIPPED','OR20','EFF','TPB')[t['member']] if control=='RAW|MAIN' else 'TPB_LOW_PUT'
            out.append({'year':year,'day':day,'control':control,'member':member,'direction':t['direction'],'inputs':f,'net':float(t['net_pnl'])-200,'entry_time':t['entry_time'],'exit_reason':t['exit_reason']})
    B.P.write(HERE/f'_local/failure-inputs-{year}.json',out)
    print('Causal failure partitions',year,len(out),'future mutations pass',flush=True)


def report():
    rows=sum((json.loads((HERE/f'_local/failure-inputs-{y}.json').read_text()) for y in ('2024','2025','2026')),[])
    out={}
    for control in ('RAW|MAIN','RAW|E|tpb_puts'):
        group=[r for r in rows if r['control']==control]
        cuts={'TOTAL':group}
        for r in group:
            for key,value in [('direction',r['direction']),('member',r['member']),('exit',r['exit_reason'])]:cuts.setdefault(key+'='+str(value),[]).append(r)
            for key,value in r['inputs'].items():
                if key=='direction':continue
                b=('GE30' if value is not None and value>=30 else D.bucket(key,value)) if key=='daily_adx' else D.bucket(key,value)
                cuts.setdefault(key+'='+str(b),[]).append(r)
        stats={name:{y:D.aggregate([r for r in part if r['year']==y]) for y in ('2024','2025','2026')} for name,part in cuts.items()}
        for dimension in ('direction','member','daily_dmi_with','daily_ema_with','daily_adx','rv10','opening_range_daily_atr','stretch','rvol','efficiency6','with_gap','minute'):
            for y in ('2024','2025','2026'):
                assert abs(sum(v[y]['net'] for n,v in stats.items() if n.startswith(dimension+'='))-stats['TOTAL'][y]['net'])<.03,(control,dimension,y)
        out[control]=stats
    B.P.write(HERE/'failure-diagnostics.json',{'status':'DESCRIPTIVE_ONLY_ALL_YEARS_SEEN','prefix_mutation_records':len(rows),'controls':out,'new_rules_selected':False,'qualified':False})
    print('Failure partitions reconcile',len(rows))


if __name__=='__main__':{'run':run,'report':report}[sys.argv[1]]()
