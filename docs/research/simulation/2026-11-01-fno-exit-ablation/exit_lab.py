"""N04 offline exit ablations with the exact balanced N03 reference retained."""
import argparse,copy,json,os,subprocess,sys
from dataclasses import replace
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=next(p for p in HERE.parents if (p/'python-engine').is_dir());PARENT=HERE.parent/'2026-11-01-fno-eff-improvement'
sys.path[:0]=[str(HERE),str(PARENT)]
import eff_lab as E
import exit_rules as R
Y,B,C,X=E.Y,E.B,E.C,E.X;OLD=E.LOCAL;LOCAL=HERE/'_local';E.LOCAL=LOCAL;X.LOCAL=LOCAL;Y.EVALS=LOCAL/'evals'

_entry=Y.BookReplay._entry
def entry(self,book,*args):
    before=book.next_id;_entry(self,book,*args)
    if self.book.get('n04_mode') and book.next_id!=before:
        book.open[before]._n02_metadata.update(admission_id=f'N04/{B.YEAR}/{Y.digest(self.book)}/{before}',n04_mode=self.book['n04_mode'],n04_context=self.book['n04_context'])
Y.BookReplay._entry=entry

_manage=Y.BookReplay._manage
def manage(self,book,obs,now):
    mode=self.book.get('n04_mode')
    if not mode or mode=='BASE':return _manage(self,book,obs,now)
    full,policies=book.open,self.policies
    try:
        for ident in sorted(full):
            leg=full[ident];i=self.leg_member[ident];book.open={ident:leg};self.policies=list(policies)
            if self.members[i]['name']=='EFF':
                combined,ctx=E.liquidation(leg,obs,now,self._frame);minute,action=R.choose(mode,combined)
                leg._n04_exit_context={**copy.deepcopy(ctx),'action':action,'combined_would_choose':ctx['action'],'mode':mode}
                leg._n04_ever_extended=getattr(leg,'_n04_ever_extended',False) or action=='CONTINUE90'
                params={**dict(policies[i].exit_overrides),'FNO_TIME_STOP_MIN':minute};self.policies[i]=replace(policies[i],exit_overrides=tuple(sorted(params.items())))
            _manage(self,book,obs,now)
            if ident not in book.open:del full[ident]
    finally:book.open=full;self.policies=policies
Y.BookReplay._manage=manage

_close=Y.replay._close_record
def close(leg,*args,**kwargs):
    record,net=_close(leg,*args,**kwargs)
    if hasattr(leg,'_n04_exit_context'):record.update(n04_exit_context=copy.deepcopy(leg._n04_exit_context),n04_ever_extended=bool(leg._n04_ever_extended))
    return record,net
Y.replay._close_record=close;Y.KEEP=tuple(dict.fromkeys((*Y.KEEP,'n04_mode','n04_context','n04_exit_context','n04_ever_extended')))

def books():
    out={}
    for sizing,contexts in [('NORMAL',('MAIN','TPB_ONE','BALANCED_RETEST','CORE_SELECT')),('ONE',('MAIN','BALANCED_RETEST'))]:
        for ctx in contexts:
            profile='TPB_ONE' if ctx=='BALANCED_RETEST' else ctx
            for mode in ('BASE','STALL_ONLY','CONTINUE_ONLY'):
                name=f'{sizing}|{ctx}|{mode}';b=X.book('N04|'+name,'CORE_SELECT' if profile=='CORE_SELECT' else 'STATIC',None if profile=='CORE_SELECT' else profile)
                b.update(n03_variant='RETEST' if ctx=='BALANCED_RETEST' else 'BASE',n03_context=profile,n03_sizing=sizing,n03_contract='v1',n04_mode=mode,n04_context=ctx,n04_contract='v1')
                if sizing=='ONE':b['cfg']={**b.get('cfg',{}),'FNO_MAX_LOTS':1,'FNO_MAX_LOTS_PROVEN':1}
                out[name]=b
    return out

def bindings():
    out=E.bindings()
    for p in [*HERE.glob('*.py'),HERE/'PLAN.md',HERE/'configuration.json',HERE/'SOURCES.md',ROOT/'docs/FNO_RESEARCH_REFERENCE.md',ROOT/'docs/FNO_RESEARCH_REFERENCE.json']:
        out['sources'][p.relative_to(ROOT).as_posix()]=B.P.sha(p)
    out['n03_freeze_sha256']=B.P.sha(PARENT/'freeze.json');out['n03_results_sha256']=B.P.sha(PARENT/'results.json')
    out['reused_n03_evaluations']={}
    for y in ('2024','2025','2026'):
        keys=json.loads((OLD/f'keys-{y}.json').read_text())
        for name,key in keys.items():
            if name.endswith('|BASE') or name.endswith('|HORIZON') or name=='NORMAL|TPB_ONE|RETEST':
                p=OLD/'evals'/f'{key}.json';out['reused_n03_evaluations'][p.relative_to(ROOT).as_posix()]=B.P.sha(p)
    return out

def freeze():
    out={};clean={k:v for k,v in os.environ.items() if k not in ('O30F_YEAR','O30C_YEAR')}
    for y in ('2024','2025','2026'):
        env={**clean,**({'O30F_YEAR':y} if y=='2024' else {'O30C_YEAR':y})};out[y]=json.loads(subprocess.check_output([sys.executable,__file__,'bindings'],cwd=ROOT,env=env).decode().strip().splitlines()[-1])
    assert not (HERE/'freeze.json').exists();X.write(HERE/'freeze.json',{'schema':'n04_exit_ablation_v1','bindings':out,'books':books(),'configuration':json.loads((HERE/'configuration.json').read_text()),'qualified':False,'can_place_orders':False,'all_years_seen':True})

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
