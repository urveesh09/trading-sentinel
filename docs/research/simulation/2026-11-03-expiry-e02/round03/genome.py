"""Joint seen-year search. Never labelled as an untouched exam."""
from dataclasses import asdict
import csv,json,random,sys,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import iterate as I
import data as D
import e02_lab as E
import search as G


def evaluate(tapes,rule):
    rows={};scores=[]
    for y,t in tapes.items():
        a=I.run(t,rule);b=I.run(t,rule,'adverse')
        rows[str(y)]=dict(ordinary=a['summary'],adverse=b['summary'])
        scores.append(E.score(a,b))
    return dict(rule=asdict(rule),key=rule.key,score=min(scores),years=rows)


def main(phase=1):
    suffix='' if phase==1 else '-phase2'
    out=I.HERE/f'joint-genome{suffix}.json';assert not out.exists()
    tapes={y:D.load_year(y,exam=y==2024) for y in (2024,2025)}
    population,generations=(48,6) if phase==1 else (64,7)
    parents=[] if phase==1 else [E.Rule(**x['rule']) for x in json.loads((I.HERE/'joint-genome.json').read_text())['leaders'][:10]]
    D.dump(I.HERE/f'joint-configuration{suffix}.json',dict(population=population,generations=generations,seeds=(23,71,193),space=G.SPACE,
        risk='One lot, unchanged own cash/reserve/brakes; no refills or year-specific rules',
        year2024_status='NOW SEEN after failed f2b95cd exam',source_sha={p.name:D.sha(p) for p in (I.HERE/'iterate.py',Path(__file__))}))
    cache={};history=[]
    with (I.HERE/f'trials{suffix}.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['key','min_score','2024_ordinary','2024_adverse','2025_ordinary','2025_adverse','rule_json'])
        for seed in (23,71,193):
            rng=random.Random(seed);pop=[G.random_rule(rng) for _ in range(population)] if not parents else parents+[G.mutate(rng.choice(parents),rng,rng.choice((1,2,3))) for _ in range(population-len(parents))]
            for generation in range(generations):
                for r in pop:
                    if r.key not in cache:
                        v=evaluate(tapes,r);cache[r.key]=v
                        w.writerow([r.key,v['score'],*[v['years'][str(y)][s]['net'] for y in (2024,2025) for s in ('ordinary','adverse')],json.dumps(v['rule'],sort_keys=True)])
                f.flush();ranked=sorted(pop,key=lambda r:cache[r.key]['score'],reverse=True);elite=ranked[:8]
                top=cache[elite[0].key];history.append(dict(seed=seed,generation=generation,leader=top,unique=len(cache)))
                print('JOINT_SEEN_YEAR_GENOME',seed,generation,len(cache),top['score'],{y:{s:x['net'] for s,x in row.items()} for y,row in top['years'].items()},flush=True)
                pop=elite+[G.mutate(rng.choice(elite),rng,rng.choice((1,2,3))) if rng.random()<.8 else G.random_rule(rng) for _ in range(population-len(elite))]
    D.dump(out,dict(unique_trials=len(cache),leaders=sorted(cache.values(),key=lambda x:x['score'],reverse=True)[:30],history=history,
                   selection_status='JOINT IN-SAMPLE; prior failed exam preserved; no untouched claim'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--phase',type=int,choices=(1,2),default=1);a=p.parse_args();main(a.phase)
