"""Score committed finalists once. No parameter changes after this examination.

This is robustness on seen data, NOT an untouched exam. Every failed check stays.
"""
from dataclasses import asdict,replace
from types import SimpleNamespace
from collections import Counter
import csv,inspect,json,math
import numpy as np
import lab as L
import study as S

HERE=L.HERE

def delayed_runner(entry_delay,exit_delay):
    """Wait extra complete bars; preserve original admission limits and actual fill clocks."""
    source=inspect.getsource(L.run_day)
    a='if pending_exit:\n            qty, reason, decided = pending_exit'
    b='if pending_exit:\n            qty, reason, decided = pending_exit\n            if i < decided + 1 + EXIT_DELAY:continue'
    c='if pending_entry:\n            j, lots, limit, decision, sign, atr, room = pending_entry; pending_entry = None'
    d='if pending_entry:\n            if i < pending_entry[3] + 1 + ENTRY_DELAY:continue\n            j, lots, limit, decision, sign, atr, room = pending_entry; pending_entry = None'
    assert source.count(a)==source.count(c)==1
    source=source.replace(a,b).replace(c,d)
    namespace={**vars(L),'ENTRY_DELAY':entry_delay,'EXIT_DELAY':exit_delay}
    exec(compile(source,'<frozen E031 delayed executor>','exec'),namespace)
    return namespace['run_day']

def with_day(runner,tapes,rule,scenario):
    saved=L.run_day
    try:
        L.run_day=runner
        return L.run(tapes,rule,scenario,True)
    finally:L.run_day=saved

def bootstrap(deltas):
    rng=np.random.default_rng(731);a=np.asarray(deltas);n=len(a)
    starts=rng.integers(0,n,size=(10000,math.ceil(n/4)))
    ids=(starts[:,:,None]+np.arange(4))%n
    totals=a[ids.reshape(10000,-1)[:,:n]].sum(axis=1)
    return dict(samples=10000,block_expiries=4,seed=731,mean=round(float(totals.mean()),2),
                ci95=[round(float(x),2) for x in np.percentile(totals,[2.5,97.5])],
                share_positive=round(float(np.mean(totals>0)),4),
                caveat='Conditional on selected rules and seen observations; excludes search-selection uncertainty')

def metrics(r):
    s=dict(r['summary']);positions=[p for d in r['days'] for p in d['positions']]
    s['position_wins']=sum(p['net']>0 for p in positions)
    s['position_losses']=sum(p['net']<0 for p in positions)
    s['exit_reasons']=dict(Counter(p['events'][-1]['reason'] for p in positions if not p.get('unresolved')))
    s['marked_drawdown_basis']='Minute close bid proxy, fees included; not intrabar broker NAV'
    # In each day marked_worst is relative to opening-day cash; closed prior days
    # and all sampled within-day points are reconstructed independently below.
    curve=peak=dd=0.
    for day in r['days']:
        realized=0.;open_marks=[]
        # Exact time-ordered close marks are audited separately in financial_audit.
        dd=max(dd,peak-(curve+day['marked_worst']))
        curve+=day['net'];peak=max(peak,curve);dd=max(dd,peak-curve)
    s['opening_peak_to_sampled_low_bound']=round(dd,2)
    return s

def fixed_friction(r):
    values=[]
    for d in r['days']:
        cost=0.
        for p in d['positions']:
            for e in p['events']:
                qty=e['lots']*L.LOT;price=e['price'];buy=e['side']=='BUY'
                changed=L.E.up(price+max(.05,price*.01)) if buy else max(.05,L.E.down(price-max(.05,price*.01)))
                cost+=abs(changed-price)*qty+L.E.fee(changed,qty,buy)-L.E.fee(price,qty,buy)
        values.append(round(d['net']-cost,2))
    return dict(net=round(sum(values),2),without_best=round(sum(values)-max(values,default=0),2),
                basis='Same original contracts, times, lots and fills; add >=1%+tick-rounded friction each side; no favourable reselection or brake rerun')

def main():
    frozen=json.loads((HERE/'finalists-freeze.json').read_text())
    for p,want in frozen['code'].items():assert L.D.sha(HERE/p)==want
    arms={'E03':L.BASE,**{k:L.Candidate(**v) for k,v in frozen['finalists'].items()}}
    S.freeze('robustness-configuration.json',dict(finalist_freeze_sha256=L.D.sha(HERE/'finalists-freeze.json'),
       robustness_source_sha256=L.D.sha(__file__),arms={k:asdict(v) for k,v in arms.items()}))
    tapes=L.tapes();all_tapes=tapes[2024]+tapes[2025]
    results={};detail={};neighbours={};native={};latency={};increments={}
    for name,rule in arms.items():
        results[name]={};detail[name]={};native[name]={};latency[name]={}
        for y,ts in tapes.items():
            for sc in ('ordinary','adverse','catastrophe'):
                r=L.run(ts,rule,sc,True);key=f'{y}|{sc}';detail[name][key]=r
                results[name][key]=dict(metrics=metrics(r),fixed_friction=fixed_friction(r))
                print('FINALIST',name,key,r['summary']['net'],flush=True)
            # Production recorder starts 12:59, enough complete consecutive bars
            # for the native signal only at 13:11 (12 bars end 13:00..13:11).
            for sc in ('ordinary','adverse'):
                native[name][f'{y}|{sc}']=metrics(L.run(ts,replace(rule,start=791),sc,True))
        for sc in ('ordinary','adverse','catastrophe'):
            r=L.run(all_tapes,rule,sc,True);detail[name][f'continuous|{sc}']=r
            results[name][f'continuous|{sc}']=dict(metrics=metrics(r),fixed_friction=fixed_friction(r))
        for ed,xd in ((0,1),(1,1)):
            runner=delayed_runner(ed,xd)
            for y,ts in tapes.items():
                for sc in ('ordinary','adverse'):
                    r=with_day(runner,ts,rule,sc)
                    latency[name][f'entry+{ed}|exit+{xd}|{y}|{sc}']=metrics(r)
    for name in frozen['finalists']:
        increments[name]={}
        for sc in ('ordinary','adverse','catastrophe'):
            a=detail[name][f'continuous|{sc}'];b=detail['E03'][f'continuous|{sc}']
            deltas=[round(x['net']-y['net'],2) for x,y in zip(a['days'],b['days'])]
            increments[name][sc]=dict(net=round(sum(deltas),2),without_best=round(sum(deltas)-max(deltas),2),
               without_two_best=round(sum(deltas)-sum(sorted(deltas,reverse=True)[:2]),2),bootstrap=bootstrap(deltas),
               changed=[dict(day=d['day'],delta=z,old=o['net'],new=d['net']) for d,o,z in zip(a['days'],b['days'],deltas) if abs(z)>.01])
        r=arms[name]
        space={'stop':(.3,.4),'arm':(.3,.5),'keep':(.5,.7),'hold':(6,10),'runner_keep':(.4,.6),
               'lock_arm':(0.,.4,.6),'lock_floor':(1.,1.05,1.15)} if name=='DEFENSIVE' else {
                   'stop':(.3,.4),'keep':(.6,.8),'extend_minutes':(2,6,8),'extend_gain':(.1,.25),'hold':(6,10)}
        neighbours[name]=[]
        for k,vs in space.items():
            for v in vs:
                neighbour=replace(r,**{k:v});n=S.evaluate(tapes,neighbour,json.loads((HERE/'baseline.json').read_text()))
                neighbours[name].append(dict(parameter=k,value=v,**n))
    # Honest selection-decay diagnosis. All rules/windows were seen by prior studies;
    # each selector uses only its stated earlier/training rows, then reports later rows.
    trials=json.loads((HERE/'sweep.json').read_text())['trials']
    trials+= [json.loads(s) for s in (HERE/'genome-trials.jsonl').read_text().splitlines()]
    rules={x['key']:L.Candidate(**x['rule']) for x in trials};rules[L.BASE.key]=L.BASE
    day_cache={}
    for key,rule in rules.items():
        for y,ts in tapes.items():day_cache[key,y]=L.run(ts,rule,'adverse',True)['days']
    def train_score(days):
        s=L.E.summary(days)
        return s['without_best']-.5*s['drawdown']-max(0,5-s['trades'])*300
    selections=[]
    for train,test in ((2024,2025),(2025,2024)):
        key=max(rules,key=lambda k:train_score(day_cache[k,train]))
        selections.append(dict(train=str(train),test=str(test),chosen=asdict(rules[key]),
            training_score=train_score(day_cache[key,train]),test_metrics=L.E.summary(day_cache[key,test]),
            baseline_test=L.E.summary(day_cache[L.BASE.key,test])))
    # Expanding blocks: start with 2024 H1, choose on earlier dates, score each next quarter.
    for boundary,end in (('2024-07-01','2024-10-01'),('2024-10-01','2025-01-01'),('2025-01-01','2025-04-01'),
                         ('2025-04-01','2025-07-01'),('2025-07-01','2025-10-01'),('2025-10-01','2026-01-01')):
        earlier=lambda k:[d for y in tapes for d in day_cache[k,y] if d['day']<boundary]
        later=lambda k:[d for y in tapes for d in day_cache[k,y] if boundary<=d['day']<end]
        key=max(rules,key=lambda k:train_score(earlier(k)))
        selections.append(dict(train='before '+boundary,test=boundary+'..'+end,chosen=asdict(rules[key]),
            training_score=train_score(earlier(key)),test_metrics=L.E.summary(later(key)),baseline_test=L.E.summary(later(L.BASE.key)),
            limitation='independent segment replay uses original continuous yearly brake path, not a dynamically switched live book'))
    save=dict(results=results,detail=detail,increments=increments,neighbours=neighbours,native_warmup=native,latency=latency,
              selection_decay=selections,classification='FITTED_ROBUSTNESS_ONLY; NO_UNTOUCHED_EXAM; NO_FINANCIAL_QUALIFICATION')
    S.save('robustness.json',save)
    fields=('arm','scenario','day','net','trades','spent','fees','unresolved','cash_after','scale')
    with (HERE/'daily-results.csv').open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for name,ds in detail.items():
            for sc in ('ordinary','adverse','catastrophe'):
                for d in ds[f'continuous|{sc}']['days']:w.writerow(dict(arm=name,scenario=sc,**{k:d[k] for k in fields[2:]}))
    print('ROBUSTNESS_COMPLETE', {name:{sc:results[name][f'continuous|{sc}']['metrics']['net'] for sc in ('ordinary','adverse','catastrophe')} for name in arms},flush=True)

if __name__=='__main__':main()
