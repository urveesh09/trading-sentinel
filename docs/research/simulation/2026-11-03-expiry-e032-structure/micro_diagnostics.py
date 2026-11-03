"""Fixed stricter-age/extra-latency diagnostics. No new threshold or profitable-rule selection."""
import socket
def denied(*a,**k):raise AssertionError('Network forbidden')
socket.socket.connect=denied;socket.create_connection=denied
from contextlib import redirect_stdout
from pathlib import Path
import json
import micro as Q
import run_study as R

def main():
    Q.verify();results={};original_view=Q.view;original_underlying=Q.fresh_underlying;original_event=Q.event;original_save=R.save
    for name in ('strict_age_2_seconds','entry_one_additional_snapshot'):
        captured=[]
        def capture(filename,obj):captured.append(obj)
        R.save=capture
        if name=='strict_age_2_seconds':
            def view(raw,now):
                q=original_view(raw,now)
                return q if q and -Q.EP.CLOCK_SKEW_SEC<=(now-q.ts).total_seconds()<=2 else None
            def fresh(payload,key,now):
                if not original_underlying(payload,key,now):return False
                dt=Q.datetime.fromisoformat(payload[key]['ts'])
                if dt.tzinfo is None:dt=dt.replace(tzinfo=Q.EP.IST)
                return (now-dt).total_seconds()<=2
            Q.view=view;Q.fresh_underlying=fresh
        else:
            def event(rows,k,symbol,q,horizon):
                if k+2>=len(rows):return original_event(rows,k,symbol,q,horizon)
                e=original_event(rows,k+1,symbol,q,horizon)
                e['decision_ts']=rows[k]['ts'].isoformat();e['additional_entry_snapshot']=True
                return e
            Q.event=event
        try:
            log=Q.M.HERE/'_local'/f'{name}.log'
            with log.open('x',encoding='utf-8') as f,redirect_stdout(f):Q.score()
            assert len(captured)==1
            results[name]=dict(summaries=captured[0]['summaries'],audit=captured[0]['audit'])
        finally:
            Q.view=original_view;Q.fresh_underlying=original_underlying;Q.event=original_event;R.save=original_save
    R.save('micro-diagnostics.json',dict(classification='EVALUATOR_NOT_PORTFOLIO',fixed_diagnostics=results,
       no_new_optimum_selected=True,limitations=['Only four five-level recorded days','Overlapping events, not independent trades','No queue or subsecond inference']))
    print('MICRO_DIAGNOSTICS',{n:{str(h):r['summaries'][f'all|PRESSURE|{h}']['mean_net'] for h in (30,120)} for n,r in results.items()})

if __name__=='__main__':main()
