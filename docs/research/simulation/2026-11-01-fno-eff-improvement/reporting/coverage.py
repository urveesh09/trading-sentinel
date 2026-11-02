"""Post-run per-session evidence footprint; unavailable is never a zero outcome."""
import argparse,json,os,subprocess,sys
from collections import Counter
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import eff_lab as L
def one():
    L.B.O27F.deny_network();L.verify();L.Y.speedups();data=L.Y.dataset('year');days=[d for d in data.days if L.C.WINDOW[0]<=d<=L.C.WINDOW[1]];rows={};reasons=Counter()
    for day in days:
        observations,excluded=data.observations(day);reasons.update(excluded);times=[o.at for o in observations]
        rows[day]={'status':'PARTIAL' if observations else 'UNAVAILABLE','observations':len(times),'first':times[0].isoformat() if times else None,'last':times[-1].isoformat() if times else None,
            'max_observed_gap_seconds':max(((b-a).total_seconds() for a,b in zip(times,times[1:])),default=None),'exclusions':dict(excluded)}
    L.verify();L.X.write(L.LOCAL/f'coverage-{L.B.YEAR}.json',{'year':L.B.YEAR,'days':rows,'sessions':len(days),'unavailable_sessions':sum(v['status']=='UNAVAILABLE' for v in rows.values()),'exclusions':dict(reasons)})
    print('COVERAGE',L.B.YEAR,len(days),sum(v['status']=='UNAVAILABLE' for v in rows.values()),flush=True)
def all_years():
    for y in ('2024','2025','2026'):
        env={k:v for k,v in os.environ.items() if k not in ('O30F_YEAR','O30C_YEAR')};env['O30F_YEAR' if y=='2024' else 'O30C_YEAR']=y
        subprocess.check_call([sys.executable,__file__,'--one'],cwd=L.ROOT,env=env)
    rows=[json.loads((L.LOCAL/f'coverage-{y}.json').read_text()) for y in ('2024','2025','2026')]
    L.X.write(HERE/'coverage.json',{'status':'PARTIAL_CANDLE_MODEL','years':rows,'limitation':'Observation availability is not full real-depth/regime coverage or proof of executable historical fills. Gaps/exclusions are retained, not repaired.'})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--one',action='store_true');a=p.parse_args();one() if a.one else all_years()
