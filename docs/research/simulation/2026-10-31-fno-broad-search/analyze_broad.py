"""Frozen O31i selection, multiplicity sensitivity and full trial ledger."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'python-engine/fno_policy_replay.py').is_file())
PRIOR=HERE.parent/'2026-10-31-fno-complements'
sys.path[:0]=[str(HERE),str(PRIOR)]
import analyze_gap as A  # noqa:E402

YEARS=('2024','2025','2026')
FIN=A.A.A


def load(p):return json.loads(p.read_text(encoding='utf-8'))


def arrays(phase):
    f=load(HERE/'freeze.json');keys={y:load(HERE/f'_local/keys-{phase}-{y}.json') for y in YEARS}
    sessions={y:[d for d in load(ROOT/f['bindings'][y]['dataset']/'manifest.json')['sessions'] if d<=A.A.LAST[y]] for y in YEARS}
    cache={};issues={}
    for name in keys['2024']:
        cache[name]={}
        for y in YEARS:
            obj=load(HERE/'_local/evals'/f'{keys[y][name]}.json');book=obj['book'];rows=obj['trades'];cache[name][y]=rows
            bad=FIN.check_book(rows,{'cfg':book['cfg']},FIN.CAPITAL,book.get('cost'),book['cfg'].get('FNO_MAX_TRADES_PER_DAY',3))
            notes={k:v for k,v in obj['notes'].items() if 'conflict' in k or k=='named_memo_miss'}
            if bad or notes:issues[f'{y}|{name}']={'financial':bad,'memo':notes}
    return f,keys,sessions,cache,issues


def select_proposals(summaries,members):
    proposed=[]
    for name,m in members.items():
        for direction in ('BOTH','LONG','SHORT'):
            values=summaries[name][direction]
            if all(values[y]['net']>0 and values[y]['trades']>=12 for y in ('2024','2025')):
                score=min(values[y]['net']/values[y]['trades'] for y in ('2024','2025'))
                proposed.append({'name':name+'|'+direction,'parent':name,'member':m,'direction':None if direction=='BOTH' else direction,'fit_score':score,'fitting':values})
    proposed.sort(key=lambda p:(-p['fit_score'],p['name']))
    out=[];seen=set()
    for p in proposed:
        if p['member']['family'] in seen:continue
        out.append(p);seen.add(p['member']['family'])
        if len(out)==6:break
    return out


def max_t_adjusted(weekly,samples=4096,seed=310126):
    """Exploratory shared sign flips by contiguous4-week blocks; keeps arm correlation."""
    if not weekly:return [],[]
    x=np.asarray(weekly,dtype=float);n=x.shape[1]
    denom=x.std(axis=1,ddof=1)/np.sqrt(n)
    observed=np.divide(x.mean(axis=1),denom,out=np.zeros(len(x)),where=denom>0)
    rng=np.random.default_rng(seed);maxima=[]
    for _ in range(samples):
        signs=np.repeat(rng.choice([-1.,1.],size=(n+3)//4),4)[:n]
        z=x*signs;sd=z.std(axis=1,ddof=1)/np.sqrt(n)
        ts=np.divide(z.mean(axis=1),sd,out=np.zeros(len(x)),where=sd>0)
        maxima.append(float(max(ts)))
    return observed.tolist(),[(1+sum(v>=t for v in maxima))/(samples+1) for t in observed]


def screen():
    import lab_broad as X
    f,keys,sessions,cache,issues=arrays('screen')
    controls={y:FIN.pub(FIN.path(cache['EX|MAIN'][y])) for y in YEARS}
    assert tuple(controls[y]['net'] for y in YEARS)==(16371,5710,30540)
    assert round(A.raw_summary(cache['RAW|MAIN'],sessions)['total'])==43170
    tpb=A.raw_summary(cache['RAW|E|tpb_puts'],sessions)
    assert tpb['years']==load(PRIOR/'results.json')['tpb_control']['standalone']['years'],'TPB control parity'
    nulls={n:A.raw_summary(v,sessions) for n,v in cache.items() if n.startswith('NULL|')}
    valid_null=[v['total'] for n,v in nulls.items() if not any(k.endswith('|'+n) for k in issues)]
    random_best=max(valid_null) if valid_null else None
    candidates={};fitting={}
    for name,m in X.genomes().items():
        rows=cache['RAW|'+name];r=A.raw_summary(rows,sessions)
        candidates[name]={'member':m,'standalone':r,'stress300':A.raw_summary(rows,sessions,300)}
        fitting[name]={}
        for d in ('BOTH','LONG','SHORT'):
            fitting[name][d]={}
            for y in ('2024','2025'):
                chosen=[t for t in rows[y] if t.get('net_pnl') is not None and (d=='BOTH' or t['direction']==d)]
                fitting[name][d][y]={'net':round(sum(A.A.one_lot(t)-200 for t in chosen),4),'trades':len(chosen)}
    invalid={n for n in candidates if any(k.endswith('|RAW|'+n) for k in issues)}
    names=[n for n in candidates if n not in invalid]
    ts,p=max_t_adjusted([candidates[n]['standalone']['weekly'] for n in names])
    for n,t,v in zip(names,ts,p):
        candidates[n]['weekly_t_unrounded']=t;candidates[n]['max_t_p']=v
        r=candidates[n]['standalone'];ys=r['years']
        checks={'positive_each_year':all(ys[y]['net']>0 for y in YEARS),'sample':min(ys[y]['trades'] for y in YEARS)>=8 and sum(ys[y]['trades'] for y in YEARS)>=40,
                'five_halves':sum(z>=0 for h in r['halves'].values() for z in h)>=5,'without_year_best':all(ys[y]['without_best_day']>0 for y in YEARS),
                't_ge2':t>=2,'max_t_p_le05':v<=.05,'beats_random':random_best is not None and r['total']>random_best,'resolved':r['unresolved']==0}
        candidates[n]['checks']=checks;candidates[n]['screen_pass']=all(checks.values())
    # Keep invalid candidates visible; never count unresolved as zero P&L.
    for n in candidates:
        candidates[n]['invalid_replay']=n in invalid
        if n in invalid:
            candidates[n].update(screen_pass=False,max_t_p=None,checks={'invalid_replay':False,'positive_each_year':False})
    selected=select_proposals(fitting,{n:m for n,m in X.genomes().items() if n not in invalid})
    selection={'schema':'o31i_selection_v1','rule':f['rule']['selection'],'selected':selected,'parent_freeze_sha256':X.P.sha(HERE/'freeze.json'),
               'fitting_years':['2024','2025'],'all_years_seen':True,'note':'direction subsets only propose candidates; actual direction/shared-cash replays required'}
    X.Y.write_new(HERE/'selection.json',selection)
    out={'schema':'o31i_screen_results_v1','qualification':'NOT_ASSESSED','can_place_orders':False,'correctness':{'fresh_replays':sum(len(k) for k in keys.values()),'issues':issues,'main_parity':True},
         'controls':controls,'random_controls':nulls,'random_best_valid':random_best,'valid_random_controls':len(valid_null),'candidates':candidates,'screen_passing':[n for n,v in candidates.items() if v['screen_pass']],
         'positive_every_year':[n for n,v in candidates.items() if v['checks']['positive_each_year'] and not v['invalid_replay']],
         'selected':[p['name'] for p in selected],'rule':f['rule']}
    X.P.write(HERE/'screen-results.json',out)
    print('SCREEN',len(candidates),'positive all years',out['positive_every_year'],'passing',out['screen_passing'],'selected',out['selected'],'invalid',len(issues),flush=True)


def selected():
    import lab_broad as X
    f,keys,sessions,cache,issues=arrays('selected');prior=load(HERE/'screen-results.json')
    _,_,_,base_cache,_=arrays('screen')
    every=[d for y in YEARS for d in sessions[y]]
    def exact(rows):
        ys={y:FIN.path(rows[y]) for y in YEARS};days={d:v for r in ys.values() for d,v in r['daily'].items()}
        return {'years':ys,'weekly':A.A.weeks_of(days,every),'unresolved':sum(t.get('net_pnl') is None for y in YEARS for t in rows[y])}
    base=exact(base_cache['EX|MAIN']);out={}
    picks=load(HERE/'selection.json')['selected']
    parent_series=[v['standalone']['weekly'] for v in prior['candidates'].values() if not v['invalid_replay']]
    child_rows=[A.raw_summary(cache['RAW|'+p['name']],sessions) for p in picks]
    _,ps=max_t_adjusted(parent_series+[r['weekly'] for r in child_rows]) if child_rows else ([],[])
    child_ps=ps[len(parent_series):]
    for pick,p_value in zip(picks,child_ps):
        n=pick['name'];raw=A.raw_summary(cache['RAW|'+n],sessions);ex=exact(cache['EX|'+n]);parent=prior['candidates'][pick['parent']]
        judge=A.judge(raw,ex,base,prior['random_best_valid'] if prior['random_best_valid'] is not None else float('inf'))
        judge['checks']['selected_max_t']=p_value<=.05
        judge['passes']=all(judge['checks'].values()) and not any(k.endswith('|RAW|'+n) or k.endswith('|EX|'+n) for k in issues)
        out[n]={**judge,'standalone':raw,'stress300':A.raw_summary(cache['RAW|'+n],sessions,300),'combined':{y:FIN.pub(ex['years'][y]) for y in YEARS},'parent_max_t_p':parent['max_t_p'],'selected_max_t_p':p_value}
    X.P.write(HERE/'selected-results.json',{'schema':'o31i_selected_results_v1','candidates':out,'passing':[n for n,v in out.items() if v['passes']],
        'correctness':{'fresh_replays':sum(len(k) for k in keys.values()),'issues':issues},'qualification':'NOT_ASSESSED','can_place_orders':False})
    print('SELECTED passes',[n for n,v in out.items() if v['passes']],'issues',issues,flush=True)


if __name__=='__main__':
    {'screen':screen,'selected':selected}[sys.argv[1]]()
