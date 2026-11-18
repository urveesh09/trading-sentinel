"""Round8 one-shot development score. Freeze committed rules before any result is shown."""
from pathlib import Path
from dataclasses import asdict
from collections import defaultdict
import hashlib,json,os,platform,subprocess,sys,time
import numpy as np
import offline8
import data8,lab8,signals8,payoff8,information8,stats8

HERE=Path(__file__).resolve().parent
FILES=('PLAN8.md','data8.py','lab8.py','signals8.py','payoff8.py','execution8.py','information8.py','forward8.py','stats8.py','score8.py','test8.py','render8.py','verify8.py','runner8.py','offline8.py')
FREEZE=HERE/'freeze8.json'

def clean(x):
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [clean(v) for v in x]
    if isinstance(x,np.ndarray):return clean(x.tolist())
    if isinstance(x,np.generic):return clean(x.item())
    if isinstance(x,float) and not np.isfinite(x):return None
    return x

def write(path,x):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp')
    with open(tmp,'w',encoding='utf-8') as f:
        json.dump(clean(x),f,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

def git(*args):return subprocess.check_output(['git',*args],cwd=HERE,text=True).strip()

def source_paths():
    import score7
    old,_=score7._paths()
    return {**{f:HERE/f for f in FILES},'proposal':HERE.parents[2]/'EXPIRY_RESEARCH_EN86_EN95.md',
            **{'round7/'+k:p for k,p in old.items()}}

def array_manifest(B):
    out={}
    for u,book in B.items():
        h=hashlib.sha256()
        for t in book:
            h.update(t.day.encode())
            for a in (t.x,t.f,t.q,t.strikes,t.kinds,t.minute,t.oi8,*[t.features[k] for k in sorted(t.features)]):
                h.update(str(a.shape).encode());h.update(str(a.dtype).encode());h.update(np.ascontiguousarray(a).tobytes())
        out[u]=h.hexdigest()
    return out

def freeze():
    if FREEZE.exists():raise RuntimeError('freeze already exists')
    for name in ('unit8.json','parity8.json','causal8.json','model-causal8.json','smoke8.json'):
        assert json.loads((HERE/name).read_text())['status']=='PASS',name
    B,bindings=data8.historical_books();cal=json.loads((HERE/'calibration8.json').read_text())
    assert cal['inference_validated']
    import scipy
    f=dict(head_before_freeze=git('rev-parse','HEAD'),created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
           files={k:data8.sha(p) for k,p in source_paths().items()},
           data=data8.sealed_manifest(B,bindings),arrays=array_manifest(B),
           calibration_sha256=data8.sha(HERE/'calibration8.json'),
           packet_binding=json.loads((HERE/'packet-binding8.json').read_text()),
           environment=dict(python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__),
           evaluation='development only; all historical sessions already studied',
           family=[f'{s}|{u}' for s in lab8.PRIMARY for u in ('NIFTY','SENSEX')],
           rules={k:asdict(v) for k,v in lab8.ARMS.items()},
           source_gate='UNVALIDATED until >=20 synchronized covered packet expiries; no promotion',
           first_forward='after this committed freeze and verification, independent cohort; no backdating')
    reg=HERE/'registration';reg.mkdir(exist_ok=True)
    for i in range(86,96):
        slot=f'EN{i}';write(reg/(slot+'.json'),dict(slot=slot,arms={k:v for k,v in f['rules'].items() if k==slot or k.startswith(slot+'_')},
            indices=['NIFTY','SENSEX'],plan_sha256=f['files']['PLAN8.md'],source_gate=f['source_gate'],
            prospective_review=dict(first_mechanism=20,financial=40,max_eligible=100,min_parents=20,min_traded_expiries=10),
            forward_cohort=f['first_forward']))
    write(FREEZE,f);print('FROZEN',len(f['files']),'files',flush=True)

def verify_freeze(check_data=True):
    f=json.loads(FREEZE.read_text());bad=[k for k,p in source_paths().items() if data8.sha(p)!=f['files'].get(k)]
    if bad:raise RuntimeError('changed frozen files: '+str(bad))
    if data8.sha(HERE/'calibration8.json')!=f['calibration_sha256']:raise RuntimeError('calibration changed')
    packet=f['packet_binding']
    assert data8.sha(Path(packet['cache_path']))==packet['cache_sha256'],'packet cache changed'
    B,bindings=data8.historical_books()
    if check_data:
        assert bindings==f['data']['files'],'sealed source data changed'
        assert array_manifest(B)==f['arrays'],'tape/cache inputs changed'
    return f,B

def metrics(days):
    vals=np.array([d['net'] for d in days]);top=sorted(vals,reverse=True)+[0.,0.]
    years=defaultdict(float)
    for d in days:years[d['day'][:4]]+=d['net']
    positions=[p for d in days for p in d.get('positions',[])]
    assumed=sum(-p['entry']*p['open']*lab8.L4.SPECS[d.get('und','NIFTY')].lot for d in days for p in d.get('positions',[]) if p.get('unresolved'))
    # Details are present in scorer runs; no imaginary realized liquidation.
    return dict(net=round(float(vals.sum()),2),without_best=round(float(vals.sum()-max(top[0],0)),2),
                without_top2=round(float(vals.sum()-max(top[0],0)-max(top[1],0)),2),
                sessions=len(days),trades=sum(d['trades'] for d in days),traded_expiries=sum(d['trades']>0 for d in days),
                worst=round(float(min(vals,default=0)),2),worst_marked=round(min([d['marked_worst'] for d in days],default=0),2),
                fees=round(sum(d['fees'] for d in days),2),winners=sum(p['net']>0 for p in positions),
                unresolved=sum(d['unresolved'] for d in days),modeled_filled_fee_pnl=round(float(vals.sum())-assumed,2),
                assumed_unresolved_loss=round(assumed,2),by_year={k:round(v,2) for k,v in years.items()})

def paired(candidate,base):
    assert [d['day'] for d in candidate]==[d['day'] for d in base]
    days=[d['day'] for d in candidate];diff=[a['net']-b['net'] for a,b in zip(candidate,base)]
    cash=[a['net'] for a in candidate]
    p=stats8.infer(days,diff);c=stats8.infer(days,cash)
    sens={}
    x,n=stats8.weeks(days,diff)
    for block in (4,8):sens[str(block)]=stats8.infer_arrays(x,n,4999,block,8600+block)
    return dict(vs_control=p,vs_cash=c,cell_p=max(p['p'],c['p']),bootstrap_sensitivity=sens)

def anatomy(days,book):
    tickets=[];by={t.day:t for t in book}
    for d in days:
        t=by[d['day']]
        for p in d['positions']:
            sells=[e for e in p['events'] if e['side']=='SELL']
            tickets.append(dict(day=t.day,minute=int(t.minute[p['decision_i']]),direction=p['direction'],strike=float(t.strikes[p['j']]),
                decision_i=p['decision_i'],entry_i=p['entry_i'],exit_i=p.get('exit_i'),lots=p['lots'],reserve=p['reserve'],room=p['room'],
                net=p['net'],fees=p['fees'],open_lots=p['open'],unresolved=bool(p.get('unresolved')),
                first_exit=sells[0].get('reason') if sells else 'UNRESOLVED',events=p['events']))
    return tickets

def compare_tickets(xs,ys):
    key=lambda x:(x['day'],x['minute'],x['direction'])
    a={key(x):x for x in xs};b={key(x):x for x in ys};common=a.keys()&b.keys()
    changed=[k for k in a.keys()|b.keys() if k not in common or abs(a[k]['net']-b[k]['net'])>.011]
    return dict(matched=len(common),candidate_only=len(a.keys()-b.keys()),control_only=len(b.keys()-a.keys()),
                matched_net_delta=round(sum(a[k]['net']-b[k]['net'] for k in common),2),
                candidate_only_net=round(sum(a[k]['net'] for k in a.keys()-b.keys()),2),
                forgone_control_net=round(sum(b[k]['net'] for k in b.keys()-a.keys()),2),
                changed_opportunities=len(changed),changed_expiries=len({k[0] for k in changed}))

def classify(out,base,stats,affected,holm):
    m=out['ordinary'];a=out['adverse'];b=base['ordinary']
    support=m['trades']>=20 and m['traded_expiries']>=10 and affected['changed_opportunities']>=20 and affected['changed_expiries']>=10
    if not support:return 'INCONCLUSIVE — support'
    if m['unresolved'] or a['unresolved']:return 'INCONCLUSIVE — unresolved execution'
    v=stats['vs_control'];c=stats['vs_cash']
    if m['net']>0 and a['net']>0 and m['without_top2']>0 and v['lo'] is not None and v['lo']>0 and c['lo']>0 and holm<=.05:
        return 'INCOME SCREEN — SOURCE UNVALIDATED'
    tails=out['tail_days']
    if m['net']>0 and a['net']>0 and v['mean']>0 and tails>=3:return 'TAIL SCREEN — SOURCE UNVALIDATED'
    cost=(b['net']-m['net'])/m['sessions']
    if m['worst']>=b['worst'] and out['wallet|ordinary']['liq_dd']<base['wallet|ordinary']['liq_dd'] and cost<=25:
        return 'PROTECTION-LIKE — development only'
    return 'FAIL'

def pipeline(B,packet=True,verbose=True):
    start=time.time();log=lambda *x:print(f'[{time.time()-start:.0f}s]',*x,flush=True) if verbose else None
    prep={u:signals8.prepare(book) for u,book in B.items()};log('signals prepared; no P&L printed')
    ml=payoff8.prepare(B['NIFTY']);log('chronological net labels/model prepared')
    results=dict(arms={},hypotheses={},evaluation='DEVELOPMENT ONLY',qualified=False,preparation=prep,
                 EN93=ml,data_limits={'SENSEX':'OI unavailable; all new strategy cells DATA UNAVAILABLE'},
                 source_validation='UNVALIDATED: one recorded expiry; historical quote spreads modeled')
    anat=dict(days={},tickets={},events={u:{t.day:t.events8 for t in book} for u,book in B.items()})
    cache={}
    for name,rule in lab8.ARMS.items():
        for u,book in B.items():
            if u=='SENSEX' and rule.setup8:continue
            key=name+'|'+u;out={};by_scenario={}
            for sc in ('ordinary','adverse','catastrophe'):
                days=lab8.run_fixed(book,rule,sc,True)
                for d in days:d['und']=u
                by_scenario[sc]=days;out[sc]=metrics(days)
            for sc in ('ordinary','adverse'):
                w=lab8.wallet(book,rule,sc);out['wallet|'+sc]={k:v for k,v in w.items() if k!='days'}
                out['wallet|'+sc]['days']=[{k:d[k] for k in ('day','net','P','W','scale','cash_after')} for d in w['days']]
            ordinary=by_scenario['ordinary'];out['tail_days']=sum(d['net']>=2500 for d in ordinary)
            results['arms'][key]=out;cache[key]=by_scenario
            anat['days'][key]=[{k:v for k,v in d.items() if k not in ('positions','missed')} for d in ordinary]
            anat['tickets'][key]=anatomy(ordinary,book)
        log('arm completed',name)
    ps={}
    for slot in lab8.PRIMARY:
        for u in ('NIFTY','SENSEX'):
            key=slot+'|'+u
            if key not in results['arms']:
                results['hypotheses'][key]=dict(status='DATA UNAVAILABLE',reason='SENSEX OI not supplied',metrics=None);ps[key]=1.;continue
            p=paired(cache[key]['ordinary'],cache['E03_env|'+u]['ordinary'])
            affected=compare_tickets(anat['tickets'][key],anat['tickets']['E03_env|'+u])
            results['hypotheses'][key]=dict(statistics=p,affected=affected,qualified=False);ps[key]=p['cell_p']
    adj=stats8.holm(ps)
    for key,h in results['hypotheses'].items():
        h['holm']=adj[key]
        if key in results['arms']:
            h['status']=classify(results['arms'][key],results['arms']['E03_env|'+key.split('|')[1]],h['statistics'],h['affected'],adj[key])
    results['EN86']=information8.diagnostics(B['NIFTY']);log('canonical information diagnostics done')
    if packet:results['EN86']['packet_pilot']=information8.packet_pilot();log('synchronized packet pilot done')
    return results,anat

def score():
    for p in (HERE/'results8.json',HERE/'results8-started.json'):
        if p.exists():raise RuntimeError('one-shot score already started; preserve existing evidence')
    f,B=verify_freeze()
    status=git('status','--porcelain','--',*[str(HERE/name) for name in FILES],str(FREEZE))
    if status:raise RuntimeError('commit frozen code first: '+status)
    fd=os.open(HERE/'results8-started.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL)
    with os.fdopen(fd,'w',encoding='utf-8') as h:
        json.dump(dict(head=git('rev-parse','HEAD'),freeze_sha256=data8.sha(FREEZE),utc=time.time()),h);h.flush();os.fsync(h.fileno())
    try:
        r,a=pipeline(B);r['head']=git('rev-parse','HEAD');r['freeze_sha256']=data8.sha(FREEZE)
        write(HERE/'results8.json',r);write(HERE/'anatomy8.json',a)
    except BaseException as e:
        write(HERE/'failure8.json',dict(type=type(e).__name__,error=str(e)));raise
    print('SCORE COMPLETE',flush=True)

if __name__=='__main__':
    {'freeze':freeze,'score':score}[sys.argv[1]]()
