"""Bounded E03.1 experiments. Every scored rule is recorded; no holdout claim."""
from dataclasses import asdict,replace
from pathlib import Path
import argparse,csv,json,random,time,hashlib
import numpy as np
import lab as L

HERE=L.HERE
SCENARIOS=('ordinary','adverse')

def save(name,obj):
    path=HERE/name
    assert not path.exists(),f'Immutable result exists: {path}'
    L.D.dump(path,obj)

def freeze(name,extra):
    paths=[HERE/'lab.py',HERE/'study.py',HERE/'PLAN.md']
    save(name,dict(classification='IN_SAMPLE_SEEN_2024_2025',year2023_read=False,api_calls=0,
                  code={p.name:L.D.sha(p) for p in paths},**extra))

def baseline():
    freeze('baseline-configuration.json',dict(rule=asdict(L.BASE)))
    tapes=L.tapes();out={};count=0;diagnosis=[]
    archive=json.loads((HERE.parent/'2026-11-03-expiry-e03/final-results.json').read_text())
    for y,ts in tapes.items():
        for sc in (*SCENARIOS,'catastrophe'):
            old=L.X.run_year(ts,L.X.Hero(**L.R3),sc,details=True)
            new=L.run(ts,L.BASE,sc,details=True)
            assert old['summary']==new['summary']
            assert old['days']==new['days']
            assert old['summary']==archive['rules'][f'E03|{y}|{sc}']['summary']
            out[f'{y}|{sc}']=new
            count+=sum(d['trades'] for d in new['days'])
            if sc!='ordinary':continue
            for t,d in zip(ts,new['days']):
                for p in d['positions']:
                    a,b=p['entry_i'],p['exit_i'];j=p['j']
                    values=t.q[a:b+1,j,3]
                    after=t.q[b+1:,j,3]
                    diagnosis.append(dict(day=t.day,symbol=p['symbol'],entry=p['entry'],lots=p['lots'],net=p['net'],fees=p['fees'],
                       age=b-a,reason=p['events'][-1]['reason'],peak_before_exit=float(np.nanmax(values))/p['entry'],
                       low_before_exit=float(np.nanmin(values))/p['entry'],
                       later_peak=float(np.nanmax(after))/p['entry'] if np.isfinite(after).any() else None,
                       events=p['events']))
    save('baseline.json',dict(parity_positions=count,mismatches=0,runs=out,diagnosis=diagnosis))
    print('BASELINE_EXACT',count,'position histories, all summaries and day/event records',flush=True)
    for k,v in out.items():print(k,L.X.brief(v['summary']),flush=True)
    print('LOSER_REASONS', {k:dict(count=sum(p['net']<0 and p['reason']==k for p in diagnosis),
         net=round(sum(p['net'] for p in diagnosis if p['reason']==k),2)) for k in sorted({p['reason'] for p in diagnosis})},flush=True)

def evaluate(ts,rule,baseline):
    rows={};scores=[];passes=[]
    for y,tapes in ts.items():
        rows[str(y)]={}
        for sc in SCENARIOS:
            r=L.run(tapes,rule,sc);s=r['summary'];rows[str(y)][sc]=s
            b=baseline['runs'][f'{y}|{sc}']
            deltas=[d['net']-o['net'] for d,o in zip(r['days'],b['days'])]
            # Distributed improvement gets priority over the single biggest extra winner.
            increment=sum(deltas);without=max(deltas,default=0)
            s['increment']=round(increment,2);s['increment_ex_best']=round(increment-without,2)
            s['increment_ex_top2']=round(increment-sum(sorted(deltas,reverse=True)[:2]),2)
            s['improved_days']=sum(x>.01 for x in deltas);s['worsened_days']=sum(x<-.01 for x in deltas)
            passes.append(s['net']>b['summary']['net']+.01 and s['without_best']>0 and
                          s['worst']>=b['summary']['worst']*1.05 and s['drawdown']<=1500 and s['unresolved']==0)
            scores.append(s['increment_ex_best']-.25*max(0,s['drawdown']-b['summary']['drawdown'])+
                          min(0,s['worst']-b['summary']['worst'])*2)
    return dict(key=rule.key,rule=asdict(rule),years=rows,passes=all(passes),score=round(min(scores),2))

def sweep():
    arms={}
    for v in (0.,.01,.025,.05):arms[f'chase_{v}']=replace(L.BASE,chase=v)
    for n in (2,3,4,5):
        for gain in (-.1,0.,.1,.2):arms[f'stall_{n}_{gain}']=replace(L.BASE,stall_minutes=n,stall_gain=gain)
    for n in (4,8,16):
        for gain in (0.,.1,.25):arms[f'extend_{n}_{gain}']=replace(L.BASE,extend_minutes=n,extend_gain=gain)
    for k,vs in dict(stop=(.2,.25,.3,.35),arm=(.2,.3,.5,.6),keep=(.5,.7,.8),hold=(4,6,10,12),confirmation=('trend20','future2')).items():
        for v in vs:arms[f'{k}_{v}']=replace(L.BASE,**{k:v})
    for arm in (.25,.5,1.):
        for floor in (1.,1.1,1.25):arms[f'lock_{arm}_{floor}']=replace(L.BASE,lock_arm=arm,lock_floor=floor)
    freeze('sweep-configuration.json',dict(arms={k:asdict(v) for k,v in arms.items()}))
    ts=L.tapes();base=json.loads((HERE/'baseline.json').read_text());out=[]
    for name,r in arms.items():
        result=evaluate(ts,r,base);result['name']=name;out.append(result)
        print('SWEEP',name,result['passes'],result['score'],
              [result['years'][str(y)]['adverse']['net'] for y in (2024,2025)],flush=True)
    save('sweep.json',dict(trials=out,unique_rules=len({x['key'] for x in out})))

SPACE=dict(chase=(0.,.01,.025,.05,.10),stop=(.25,.3,.35,.4),arm=(.3,.4,.5),keep=(.5,.6,.7),hold=(6,8,10),
           stall_minutes=(0,3,4,5),stall_gain=(-.1,0.,.1),extend_minutes=(0,4,8),extend_gain=(0.,.1,.25),
           lock_arm=(0.,.5,1.),lock_floor=(1.,1.1),confirmation=('none','trend20','future2'))

def genome():
    # Seeded evolution of mechanisms rather than a giant threshold/cartesian search.
    freeze('genome-configuration.json',dict(space=SPACE,seeds=[31,137],max_new_unique=400,population=32,generations=7,
           objective='worst seen-year/scenario incremental ex-best, penalized for worse DD/day'))
    ts=L.tapes();base=json.loads((HERE/'baseline.json').read_text());sweep=json.loads((HERE/'sweep.json').read_text())['trials']
    cache={v['key']:v for v in sweep};cache[L.BASE.key]=evaluate(ts,L.BASE,base)
    leaders=sorted(sweep,key=lambda v:(v['passes'],v['score']),reverse=True)[:8]
    new=0;history=[]
    with (HERE/'genome-trials.jsonl').open('x',encoding='utf-8') as f:
        for seed in (31,137):
            rng=random.Random(seed);pop=[L.BASE]+[L.Candidate(**x['rule']) for x in leaders]
            def mutate(parent):
                args=asdict(parent)
                for k in rng.sample(list(SPACE),rng.choice((1,2,3))):args[k]=rng.choice(SPACE[k])
                if not args['stall_minutes']:args['stall_gain']=0.
                if not args['extend_minutes']:args['extend_gain']=.2
                if not args['lock_arm']:args['lock_floor']=1.
                return L.Candidate(**args)
            pop+= [mutate(rng.choice(pop)) for _ in range(32-len(pop))]
            for generation in range(7):
                for r in pop:
                    if r.key not in cache and new<400:
                        row=evaluate(ts,r,base);cache[r.key]=row;new+=1
                        f.write(json.dumps(row)+'\n');f.flush()
                ranked=sorted([r for r in pop if r.key in cache],key=lambda r:(cache[r.key]['passes'],cache[r.key]['score']),reverse=True)
                elite=ranked[:8];best=cache[elite[0].key]
                history.append(dict(seed=seed,generation=generation,leader=best['key'],new_unique=new))
                print('GENOME',seed,generation,new,best['passes'],best['score'],flush=True)
                pop=elite+[mutate(rng.choice(elite)) for _ in range(24)]
    save('genome.json',dict(new_unique=new,leaders=sorted(cache.values(),key=lambda r:(r['passes'],r['score']),reverse=True)[:30],history=history))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('baseline','sweep','genome'))
    args=parser.parse_args();globals()[args.mode]()
