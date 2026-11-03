"""Recorded snapshot-imbalance markouts. EVALUATOR, never a portfolio result."""
from collections import Counter,defaultdict
from datetime import datetime,timedelta
from pathlib import Path
import importlib.util,json,math,re,sqlite3,sys
import numpy as np
import structure_checkpoint as C
import mechanisms as M
import run_study as R

spec=importlib.util.spec_from_file_location('structure_native_e02',C.ROOT/'python-engine/expiry_e02.py')
N=importlib.util.module_from_spec(spec);sys.modules[spec.name]=N;spec.loader.exec_module(N)
EP=N.EP;SC=EP.fee_schedule('NFO')
DATES=('2026-10-06','2026-10-13','2026-10-19','2026-10-27','2026-11-03')
MANIFEST=M.HERE.parent/'2026-11-03-expiry-e031/recorded-proxy-freeze.json'

def fresh_underlying(payload,key,now):
    raw=payload.get(key)
    if not isinstance(raw,dict) or raw.get('status')!='FRESH':return False
    try:
        dt=datetime.fromisoformat(raw['ts'])
        if dt.tzinfo is None:dt=dt.replace(tzinfo=EP.IST)
        age=(now-dt).total_seconds()
        return -EP.CLOCK_SKEW_SEC<=age<=EP.QUOTE_MAX_AGE_SEC and float(raw['ltp'])>0
    except (TypeError,ValueError,KeyError):return False

def view(raw,now):
    q=N.logged_quote(raw)
    if not q or len(q.bids)!=5 or len(q.asks)!=5 or not q.fresh(now) or not q.spread_ok(.10):return None
    if any(a[0]<b[0] for a,b in zip(q.bids,q.bids[1:])):return None
    if any(a[0]>b[0] for a,b in zip(q.asks,q.asks[1:])):return None
    return q

def imbalance(q):
    b=sum(v for p,v in q.bids);a=sum(v for p,v in q.asks)
    return (b-a)/(b+a)

def metadata():
    manifest=json.loads(MANIFEST.read_text())
    sources={p:C.sha(p) for p in manifest['source']}
    assert sources==manifest['source']
    return sources

def freeze():
    R.save('freeze-micro-v2.json',dict(head=C.git('rev-parse','HEAD').decode().strip(),sources=metadata(),
       files={n:C.sha(M.HERE/n) for n in ('MICRO.md','micro.py','test_micro.py')},
       horizon_seconds=[30,120],dates=DATES,classification='SEEN_QUOTE_EVALUATOR_ONLY',
       engine_sha256={n:C.sha(C.ROOT/'python-engine'/n) for n in ('expiry_e02.py','expiry_paper.py','cost_schedules.py')},
       api_calls=0,year2023_read=False))

def verify():
    R.verify();f=json.loads((M.HERE/'freeze-micro-v2.json').read_text())
    assert metadata()==f['sources']
    for n,h in f['files'].items():assert C.sha(M.HERE/n)==h,n
    for n,h in f['engine_sha256'].items():assert C.sha(C.ROOT/'python-engine'/n)==h,n
    path=(M.HERE/'freeze-micro-v2.json').relative_to(C.ROOT).as_posix()
    assert C.git('log','-1','--format=%H','--',path).strip()
    assert not C.git('status','--porcelain','--',path).strip()

def load():
    days={}
    for p in metadata():
        c=sqlite3.connect(Path(p).resolve().as_uri()+'?mode=ro',uri=True)
        for day in DATES:
            if day in days:continue
            rows=c.execute("SELECT ts,spot,fut,quotes FROM expiry_paper_ticks WHERE day=? AND underlying='NIFTY' ORDER BY ts",(day,)).fetchall()
            if not rows:continue
            days[day]=[dict(ts=datetime.fromisoformat(ts),spot=spot,fut=fut,payload=json.loads(q)) for ts,spot,fut,q in rows]
        c.close()
    return days

def event(rows,k,symbol,q,horizon):
    signal=rows[k];row=rows[k+1];now=row['ts']
    result=dict(day=signal['ts'].date().isoformat(),decision_ts=signal['ts'].isoformat(),symbol=symbol,
       horizon=horizon,pressure=imbalance(q),status='NO_ENTRY',net_markout=None,midpoint_markout=None)
    if not 0<(now-signal['ts']).total_seconds()<=15:return result
    nextq=view(row['payload'].get('legs',{}).get(symbol),now)
    if not nextq:return result
    lots,ask=EP.walk(nextq.asks,1,N.LOT)
    if not lots or ask>q.ask*1.10 or EP.worst_case_loss(ask,1,N.LOT,SC)>1250:return result
    result.update(status='EXIT_UNAVAILABLE',entry_ts=now.isoformat(),entry=ask,
       premium=ask*N.LOT,entry_fee=round(EP.buy_charges(ask,N.LOT,SC),2),
       full_loss_bound=round(-ask*N.LOT-EP.buy_charges(ask,N.LOT,SC)-EP.order_fee(SC),2))
    target=now+timedelta(seconds=horizon)
    # First sample after the frozen horizon, never a best quote within the interval.
    n=next((i for i in range(k+2,len(rows)) if rows[i]['ts']>=target),None)
    if n is None or (rows[n]['ts']-target).total_seconds()>25:return result
    out=view(rows[n]['payload'].get('legs',{}).get(symbol),rows[n]['ts'])
    if not out:return result
    filled,bid=EP.walk(out.bids,1,N.LOT)
    if not filled:return result
    charges=round(result['entry_fee']+EP.sell_charges(bid,N.LOT,SC),2)
    net=round((bid-ask)*N.LOT-charges,2)
    mid0=(nextq.bid+nextq.ask)/2;mid1=(out.bid+out.ask)/2
    result.update(status='MEASURED',exit_ts=rows[n]['ts'].isoformat(),exit=bid,fees=charges,
       net_markout=net,midpoint_markout=round((mid1-mid0)*N.LOT,2),
       spread_and_depth_cost=round(((ask-mid0)+(mid1-bid))*N.LOT,2))
    return result

def summarize(events):
    measured=[e for e in events if e['status']=='MEASURED'];net=[e['net_markout'] for e in measured]
    # Means, not sums: overlapping marks never establish a funded book return.
    return dict(decisions=len(events),measured=len(measured),statuses=dict(Counter(e['status'] for e in events)),
      mean_net=round(float(np.mean(net)),2) if net else None,median_net=round(float(np.median(net)),2) if net else None,
      positive_fraction=round(float(np.mean(np.array(net)>0)),4) if net else None,
      mean_midpoint=round(float(np.mean([e['midpoint_markout'] for e in measured])),2) if measured else None,
      mean_fees=round(float(np.mean([e['fees'] for e in measured])),2) if measured else None,
      mean_spread_depth=round(float(np.mean([e['spread_and_depth_cost'] for e in measured])),2) if measured else None,
      mean_fee_fraction=round(float(np.mean([e['fees']/e['premium'] for e in measured])),4) if measured else None,
      mean_missing_full_loss_bound=round(float(np.mean([e['full_loss_bound'] for e in events if e['status']=='EXIT_UNAVAILABLE'])),2) if any(e['status']=='EXIT_UNAVAILABLE' for e in events) else None)

def score():
    verify();days=load();events=[];audit=[]
    for day,rows in days.items():
        counts=Counter();age=[];gaps=[];latency=[];prior={}
        for k,row in enumerate(rows):
            if k:gaps.append((row['ts']-rows[k-1]['ts']).total_seconds())
            for timing in row['payload'].get('timing',[]):
                if isinstance(timing,dict):latency.append(float(timing.get('limiter_wait_sec',0))+float(timing.get('transport_sec',0)))
            now=row['ts'];minute=now.hour*60+now.minute
            for sym,raw in row['payload'].get('legs',{}).items():
                counts['leg_observations']+=1
                if not isinstance(raw,dict):counts['compact_no_five_level_proof']+=1;continue
                q=view(raw,now)
                if not q:counts['invalid_stale_or_wide']+=1;continue
                age.append((now-q.ts).total_seconds());counts['valid_five_level']+=1
                old=prior.get(sym);prior[sym]=(k,q)
                if not 780<=minute<900 or k<2 or k>=len(rows)-1:continue
                if not old or old[0]!=k-1:continue
                m=re.search(r'(\d{5})(CE|PE)$',sym)
                if not m:continue
                strike=float(m.group(1));d=1 if m.group(2)=='CE' else -1
                if row['spot'] is None or row['fut'] is None or not 0<d*(strike-row['spot'])<=200 or not 5<=q.ask<=20:continue
                if not fresh_underlying(row['payload'],'index',now) or not fresh_underlying(row['payload'],'future',now):continue
                prev=rows[k-2]
                if not all(0<(rows[z]['ts']-rows[z-1]['ts']).total_seconds()<=15 for z in (k-1,k)) or prev['spot'] is None or prev['fut'] is None:continue
                if not fresh_underlying(prev['payload'],'index',prev['ts']) or not fresh_underlying(prev['payload'],'future',prev['ts']):continue
                if d*(row['spot']-prev['spot'])<=0 or d*(row['fut']-prev['fut'])<=0:continue
                counts['eligible_control']+=1
                pressure=imbalance(q)>1/3 and imbalance(old[1])<=1/3
                if pressure:counts['new_pressure']+=1
                for horizon in (30,120):
                    e=event(rows,k,sym,q,horizon);e['arm']='PRESSURE' if pressure else 'CONTROL'
                    events.append(e)
        def stat(v):return dict(p50=round(float(np.median(v)),4),p95=round(float(np.percentile(v,95)),4),max=round(float(max(v)),4)) if v else None
        audit.append(dict(day=day,snapshots=len(rows),counts=dict(counts),snapshot_gap_seconds=stat(gaps),quote_age_seconds=stat(age),request_wait_plus_transport_seconds=stat(latency)))
    out={}
    for day in ['all',*DATES]:
        for arm in ('PRESSURE','CONTROL'):
            for h in (30,120):
                es=[e for e in events if (day=='all' or e['day']==day) and e['arm']==arm and e['horizon']==h]
                s=summarize(es);out[f'{day}|{arm}|{h}']=s
                print(day,arm,h,s,flush=True)
    R.save('micro-results.json',dict(classification='EVALUATOR_NOT_PORTFOLIO',audit=audit,summaries=out,events=events))

if __name__=='__main__':globals()[sys.argv[1]]()
