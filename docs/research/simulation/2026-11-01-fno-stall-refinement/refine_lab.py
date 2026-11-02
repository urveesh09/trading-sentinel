"""N05 offline balanced-entry exit refinement; no runtime imports this file."""
import argparse,copy,json,os,subprocess,sys
from dataclasses import replace
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=next(p for p in HERE.parents if (p/'python-engine').is_dir());PARENT=HERE.parent/'2026-11-01-fno-exit-ablation'
sys.path[:0]=[str(HERE),str(PARENT)]
import exit_lab as P
import refine_rules as R
Y,B,C,X=P.Y,P.B,P.C,P.X;OLD=P.LOCAL;LOCAL=HERE/'_local';P.LOCAL=LOCAL;P.E.LOCAL=LOCAL;X.LOCAL=LOCAL;Y.EVALS=LOCAL/'evals'

_entry=Y.BookReplay._entry
def entry(self,book,*args):
    before=book.next_id;_entry(self,book,*args)
    if self.book.get('n05_mode') and book.next_id!=before:
        book.open[before]._n02_metadata.update(admission_id=f'N05/{B.YEAR}/{Y.digest(self.book)}/{before}',n05_mode=self.book['n05_mode'],n05_context=self.book['n05_context'])
Y.BookReplay._entry=entry

def review(leg,obs,now,frame,mode):
    parent,ctx=P.E.liquidation(leg,obs,now,frame);eligible=parent==30.;admission=getattr(leg,'_n02_metadata',{});setup=admission.get('n03_entry_context') or {};level=setup.get('broken_level')
    structure=P.E.context(frame,now) if mode=='STRUCT30' and eligible else None
    minute,action=R.choose(mode,eligible,ctx['age_minutes'],structure,level,leg.direction)
    return minute,{**copy.deepcopy(ctx),'action':action,'review_mode':mode,'parent_stall_eligible':eligible,'original_retest_level':level,'structure':copy.deepcopy(structure)}

_manage=Y.BookReplay._manage
def manage(self,book,obs,now):
    mode=self.book.get('n05_mode')
    if not mode or mode=='BASE':return _manage(self,book,obs,now)
    full,policies=book.open,self.policies
    try:
        for ident in sorted(full):
            leg=full[ident];i=self.leg_member[ident];book.open={ident:leg};self.policies=list(policies)
            if self.members[i]['name']=='EFF':
                minute,ctx=review(leg,obs,now,self._frame,mode);leg._n05_exit_context=ctx
                params={**dict(policies[i].exit_overrides),'FNO_TIME_STOP_MIN':minute};self.policies[i]=replace(policies[i],exit_overrides=tuple(sorted(params.items())))
            _manage(self,book,obs,now)
            if ident not in book.open:del full[ident]
    finally:book.open=full;self.policies=policies
Y.BookReplay._manage=manage

_close=Y.replay._close_record
def close(leg,*args,**kwargs):
    record,net=_close(leg,*args,**kwargs)
    if hasattr(leg,'_n05_exit_context'):record['n05_exit_context']=copy.deepcopy(leg._n05_exit_context)
    return record,net
Y.replay._close_record=close;Y.KEEP=tuple(dict.fromkeys((*Y.KEEP,'n05_mode','n05_context','n05_exit_context')))

def books():
    out={}
    for sizing in ('NORMAL','ONE'):
        for mode in ('BASE','STALL30','DELAY45','STRUCT30'):
            name=f'{sizing}|BALANCED_RETEST|{mode}';b=X.book('N05|'+name,'STATIC','TPB_ONE')
            b.update(n03_variant='RETEST',n03_context='TPB_ONE',n03_sizing=sizing,n03_contract='v1',n04_mode='BASE',n04_context='BALANCED_RETEST',n04_contract='v1',n05_mode=mode,n05_context='BALANCED_RETEST',n05_contract='v1')
            if sizing=='ONE':b['cfg']={**b.get('cfg',{}),'FNO_MAX_LOTS':1,'FNO_MAX_LOTS_PROVEN':1}
            out[name]=b
    name='NORMAL|MAIN|BASE';b=X.book('N05|'+name,'STATIC','MAIN');b.update(n03_variant='BASE',n03_context='MAIN',n03_sizing='NORMAL',n03_contract='v1',n04_mode='BASE',n04_context='MAIN',n04_contract='v1',n05_mode='BASE',n05_context='MAIN',n05_contract='v1');out[name]=b
    return out

def bindings():
    out=P.bindings()
    for p in [*HERE.glob('*.py'),HERE/'PLAN.md',HERE/'SOURCES.md',HERE/'configuration.json',ROOT/'docs/FNO_RESEARCH_CHALLENGERS.md',ROOT/'docs/FNO_RESEARCH_CHALLENGERS.json']:
        out['sources'][p.relative_to(ROOT).as_posix()]=B.P.sha(p)
    out['n04_freeze_sha256']=B.P.sha(PARENT/'freeze.json');out['n04_results_sha256']=B.P.sha(PARENT/'results.json');out['early_feature_audit_sha256']=B.P.sha(HERE/'early-feature-audit.json');out['n04_controls']={}
    for y in ('2024','2025','2026'):
        keys=json.loads((OLD/f'keys-{y}.json').read_text())
        for n in ('NORMAL|MAIN|BASE',*[f'{s}|BALANCED_RETEST|{m}' for s in ('NORMAL','ONE') for m in ('BASE','STALL_ONLY')]):
            p=OLD/'evals'/f'{keys[n]}.json';out['n04_controls'][p.relative_to(ROOT).as_posix()]=B.P.sha(p)
    return out

def freeze():
    clean={k:v for k,v in os.environ.items() if k not in ('O30F_YEAR','O30C_YEAR')};out={}
    for y in ('2024','2025','2026'):
        env={**clean,**({'O30F_YEAR':y} if y=='2024' else {'O30C_YEAR':y})};out[y]=json.loads(subprocess.check_output([sys.executable,__file__,'bindings'],cwd=ROOT,env=env).decode().strip().splitlines()[-1])
    assert not (HERE/'freeze.json').exists();X.write(HERE/'freeze.json',{'schema':'n05_refine_v1','bindings':out,'books':books(),'configuration':json.loads((HERE/'configuration.json').read_text()),'qualified':False,'can_place_orders':False,'all_years_seen':True})

def verify():
    f=json.loads((HERE/'freeze.json').read_text());assert f['bindings'][B.YEAR]==X.native(bindings()),'source/input/reference changed'
    assert json.loads(subprocess.check_output(['git','show','HEAD:'+(HERE/'freeze.json').relative_to(ROOT).as_posix()],cwd=ROOT))==f,'freeze uncommitted'

def run(jobs):
    assert 1<=jobs<=3;B.O27F.deny_network();verify();C.table('year')
    with ProcessPoolExecutor(max_workers=jobs,initializer=B.L._init) as pool:Y.Runner(pool,jobs).run(list(books().values()),source='year',window=C.WINDOW)
    verify();X.write(LOCAL/f'keys-{B.YEAR}.json',{n:Y.task_key(b,'year',C.WINDOW) for n,b in books().items()});print('DONE',B.YEAR,len(books()),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['bindings','freeze','run']);p.add_argument('--jobs',type=int,default=3);a=p.parse_args()
    if a.action=='bindings':print(json.dumps(X.native(bindings())))
    elif a.action=='freeze':freeze()
    else:run(a.jobs)
