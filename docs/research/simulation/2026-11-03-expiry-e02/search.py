"""Reproducible development genomes; 2024 opened only after a committed freeze."""
from dataclasses import asdict,replace
import argparse,csv,json,random,subprocess,sys,time
import data as D
import e02_lab as E

SPACE={
 'setup':('BOX','BREAK','RETEST','PULLBACK','FADE'),
 'look':(5,10,20,30),'efficiency':(0.,.3,.5,.7),'stretch':(1.5,2.5,4.),
 'premium_low':(2.,5.,10.),'premium_high':(10.,20.,35.),'option_rise':(0.,1.,1.2),
 'stop':(.2,.3,.4),'arm':(.4,1.,2.),'keep':(.5,.6,.75),'target':(1.,2.,4.,9.),
 'hold':(8,15,30,60),'start':(780,810),'end':(870,900),'slots':(1,2),'underlying_stop':(.5,1.,2.),'reach':(0.,1.,2.,3.)}


def random_rule(rng):
    while True:
        r=E.Rule(**{k:rng.choice(v) for k,v in SPACE.items()})
        if r.premium_low<r.premium_high:return r


def mutate(r,rng,n=2):
    d=asdict(r)
    for k in rng.sample(list(SPACE),n):d[k]=rng.choice(SPACE[k])
    if d['premium_low']>=d['premium_high']:d['premium_low']=2.
    return E.Rule(**d)


def evaluate(tapes,r):
    a=E.run_year(tapes,r,'ordinary');b=E.run_year(tapes,r,'adverse')
    return dict(key=r.key,rule=asdict(r),score=E.score(a,b),ordinary=a['summary'],adverse=b['summary'])


def genome(label,population=48,generations=5,seeds=(11,37,101),through=12):
    tapes=[t for t in D.load_year(2025) if int(t.day[5:7])<=through]
    out=D.HERE/f'round-{label}.json';assert not out.exists()
    ledger_path=D.HERE/f'trials-{label}.csv';assert not ledger_path.exists()
    cache={};runs=[]
    # Every round records its exact family before scoring starts.
    D.dump(D.HERE/f'round-{label}-configuration.json',dict(space=SPACE,seeds=seeds,population=population,generations=generations,
           execution=dict(ordinary='next-open + p75 half spread',adverse='next-open + double half spread + max(one tick,1% premium)',catastrophe='next bar worst high/low, double spread; separately reported'),
           source_sha={p.name:D.sha(p) for p in (D.HERE/'data.py',D.HERE/'e02_lab.py',D.HERE/'search.py')},through_month=through,year2024_opened=False))
    with ledger_path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.writer(f);writer.writerow(['id','score','ordinary_net','adverse_net','ordinary_ex_best','adverse_ex_best','ordinary_trades','adverse_trades','rule_json'])
        for seed in seeds:
            rng=random.Random(seed)
            pop=[random_rule(rng) for _ in range(population)]
            if label in ('02','03'):
                previous=json.loads((D.HERE/'round-01.json').read_text())
                parents=[E.Rule(**x['rule']) for x in previous['leaders'][:8]]
                pop=parents+[mutate(rng.choice(parents),rng,3) for _ in range(population-len(parents))]
            for generation in range(generations):
                for rule in pop:
                    if rule.key not in cache:
                        row=evaluate(tapes,rule);cache[rule.key]=row
                        writer.writerow([rule.key,row['score'],row['ordinary']['net'],row['adverse']['net'],row['ordinary']['without_best'],row['adverse']['without_best'],row['ordinary']['trades'],row['adverse']['trades'],json.dumps(row['rule'],sort_keys=True)])
                f.flush()
                ranked=sorted(pop,key=lambda r:cache[r.key]['score'],reverse=True)
                elite=ranked[:max(4,population//6)]
                top=cache[elite[0].key]
                trace=dict(seed=seed,generation=generation,unique_trials=len(cache),leader=top)
                runs.append(trace)
                print('ROUND',label,'seed',seed,'generation',generation,'trials',len(cache),'score',top['score'],'net',top['ordinary']['net'],top['adverse']['net'],flush=True)
                pop=elite+[mutate(rng.choice(elite),rng,rng.choice((1,2,3))) if rng.random()<.85 else random_rule(rng) for _ in range(population-len(elite))]
    leaders=sorted(cache.values(),key=lambda x:x['score'],reverse=True)[:30]
    D.dump(out,dict(label=label,unique_trials=len(cache),leaders=leaders,history=runs,
                   fitting_status='2025 development already seen; no untouched claim',year2024_opened=False))
    return leaders


def bindings():
    files=[p for p in D.HERE.glob('*.py')]+[D.HERE/'PLAN.md',D.HERE/'dataset.json',D.HERE/'finalists.json']
    return {str(p.relative_to(D.ROOT)):D.sha(p) for p in files}


def freeze():
    target=D.HERE/'freeze-final.json';assert not target.exists()
    D.dump(target,dict(source=bindings(),data={str(y):D.sha(D.LOCAL/f'{y}.sqlite') for y in (2025,2024)},fees=E.FEE,
           head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=D.ROOT,text=True).strip(),year2024_scored=False,
           acceptance='PLAN.md profit/ex-best/PF/activity/worst/DD/quarter/unresolved tests; same-cash E011 comparison; ordinary and adverse; no later retuning can reuse 2024 as untouched'))


def verify_freeze():
    f=json.loads((D.HERE/'freeze-final.json').read_text())
    assert bindings()==f['source'],'Final strategy/source changed'
    assert f['fees']==E.FEE
    for year,h in f['data'].items():assert D.sha(D.LOCAL/f'{year}.sqlite')==h
    subprocess.run(['git','ls-files','--error-unmatch',str((D.HERE/'freeze-final.json').relative_to(D.ROOT))],cwd=D.ROOT,check=True,capture_output=True)


def exam():
    verify_freeze();out=D.HERE/'exam-2024.json';assert not out.exists()
    rules=json.loads((D.HERE/'finalists.json').read_text())
    tapes=D.load_year(2024,exam=True)
    from audit import evaluate_finalist
    results={};audits={};stress={}
    baseline={s:E.run_year(tapes,E.Rule(setup='E011'),s,True) for s in ('ordinary','adverse')}
    for name,params in rules.items():
        r=E.Rule(**params)
        checked=evaluate_finalist(tapes,r)
        results[name]=checked['results'];audits[name]={k:v for k,v in checked.items() if k!='results'}
        stress[name]={}
        saved=E.LOT
        try:
            for lot in (25,50,75):
                E.LOT=lot
                stress[name][str(lot)]={s:E.run_year(tapes,r,s)['summary'] for s in ('ordinary','adverse')}
        finally:E.LOT=saved
        print('FINAL_EXAM',name,{s:v['summary'] for s,v in results[name].items()},flush=True)
    verdict={}
    for name,row in results.items():
        checks={s:E.qualifies(v['summary']) for s,v in row.items() if s in ('ordinary','adverse')}
        for s in ('ordinary','adverse'):
            a=row[s]['summary'];b=baseline[s]['summary']
            checks[s]['beats_same_cash_E011']=a['net']>b['net']+.01
            checks[s]['worst_vs_same_cash_E011']=a['worst']>=b['worst']-.01
            checks[s]['drawdown_vs_same_cash_E011']=a['drawdown']<=b['drawdown']+.01
        checks['fixed_entry_stress']={'positive':row['fixed_entry_stress']['summary']['net']>0,'without_best_positive':row['fixed_entry_stress']['summary']['without_best']>0}
        verdict[name]=dict(checks=checks,passed=all(all(c.values()) for c in checks.values()))
    D.dump(out,dict(results=results,verdict=verdict,native_audit=audits,lot_sensitivity=stress,baseline=baseline,
                   source_freeze='freeze-final.json',no_retuning=True))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=('genome','freeze','verify','exam'));p.add_argument('--round',default='01');p.add_argument('--population',type=int,default=48);p.add_argument('--generations',type=int,default=5);p.add_argument('--through-month',type=int,default=12)
    a=p.parse_args()
    if a.command=='genome':genome(a.round,a.population,a.generations,through=a.through_month)
    elif a.command=='freeze':freeze()
    elif a.command=='verify':verify_freeze()
    else:exam()
