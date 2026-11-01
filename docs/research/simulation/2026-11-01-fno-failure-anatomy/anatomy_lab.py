"""N07 isolated exit experiment; no application module imports this file."""
import argparse,copy,json,os,subprocess,sys
from pathlib import Path
from dataclasses import replace
from concurrent.futures import ProcessPoolExecutor
HERE=Path(__file__).resolve().parent;ROOT=next(p for p in HERE.parents if (p/'python-engine').is_dir());PARENT=HERE.parent/'2026-11-01-fno-stall-refinement'
sys.path[:0]=[str(HERE),str(PARENT)]
import refine_lab as P
import anatomy_rules as R
Y,B,C,X=P.Y,P.B,P.C,P.X;OLD=P.LOCAL;LOCAL=HERE/'_local';P.LOCAL=LOCAL;P.P.LOCAL=LOCAL;P.P.E.LOCAL=LOCAL;X.LOCAL=LOCAL;Y.EVALS=LOCAL/'evals'

_entry=Y.BookReplay._entry
def entry(self,book,*args):
    before=book.next_id;_entry(self,book,*args)
    if self.book.get('n07_mode') and book.next_id!=before:
        book.open[before]._n02_metadata.update(admission_id=f'N07/{B.YEAR}/{Y.digest(self.book)}/{before}',n07_mode=self.book['n07_mode'])
Y.BookReplay._entry=entry


def review(leg,obs,now,frame,mode):
    parent,ctx=P.P.E.liquidation(leg,obs,now,frame);eligible=parent==30.;setup=getattr(leg,'_n02_metadata',{}).get('n03_entry_context') or {};level=setup.get('broken_level')
    structure=P.P.E.context(frame,now) if mode=='STRUCT_OR_PREMIUM' and eligible else None
    minute,action=R.choose(mode,eligible,ctx['age_minutes'],ctx['bid'],leg.entry_premium,structure,level,leg.direction)
    return minute,{**copy.deepcopy(ctx),'review_mode':mode,'action':action,'parent_stall_eligible':eligible,'entry_premium':leg.entry_premium,'gross_at_bid':(ctx['bid']-leg.entry_premium)*leg.qty if ctx['bid'] is not None else None,'original_retest_level':level,'structure':copy.deepcopy(structure)}


_manage=Y.BookReplay._manage
def manage(self,book,obs,now):
    mode=self.book.get('n07_mode')
    if mode not in ('PREMIUM_STALL','STRUCT_OR_PREMIUM'):return _manage(self,book,obs,now)
    full,policies=book.open,self.policies
    try:
        for ident in sorted(full):
            leg=full[ident];i=self.leg_member[ident];book.open={ident:leg};self.policies=list(policies)
            if self.members[i]['name']=='EFF':
                minute,ctx=review(leg,obs,now,self._frame,mode);leg._n07_exit_context=ctx
                params={**dict(policies[i].exit_overrides),'FNO_TIME_STOP_MIN':minute};self.policies[i]=replace(policies[i],exit_overrides=tuple(sorted(params.items())))
            _manage(self,book,obs,now)
            if ident not in book.open:del full[ident]
    finally:book.open=full;self.policies=policies
Y.BookReplay._manage=manage

_close=Y.replay._close_record
def close(leg,*a,**k):
    row,net=_close(leg,*a,**k)
    if hasattr(leg,'_n07_exit_context'):row['n07_exit_context']=copy.deepcopy(leg._n07_exit_context)
    return row,net
Y.replay._close_record=close;Y.KEEP=tuple(dict.fromkeys((*Y.KEEP,'n07_mode','n07_exit_context')))


def books(phase='all'):
    out={};parents=P.books()
    modes=('BASE','STALL30','STRUCT30') if phase=='reference' else ('PREMIUM_STALL','STRUCT_OR_PREMIUM') if phase=='candidate' else ('BASE','STALL30','STRUCT30','PREMIUM_STALL','STRUCT_OR_PREMIUM')
    for sizing in ('NORMAL','ONE'):
        for mode in modes:
            b=copy.deepcopy(parents[f'{sizing}|BALANCED_RETEST|{mode if mode in ("BASE","STALL30","STRUCT30") else "BASE"}']);b.update(n07_mode=mode,n07_contract='v1');b['label']=f'N07|{sizing}|{mode}';out[sizing+'|'+mode]=b
    if phase!='reference':
        for mode in ('BASE','STALL30','STRUCT30','PREMIUM_STALL','STRUCT_OR_PREMIUM'):
            source=parents[f'NORMAL|BALANCED_RETEST|{mode if mode in ("BASE","STALL30","STRUCT30") else "BASE"}'];b=copy.deepcopy(source)
            b.update(n07_mode=mode,n07_contract='v1',cost=[0.,0.],label=f'N07|NO_EXTRA_STRESS|{mode}');out['NO_EXTRA_STRESS|'+mode]=b
    return out


def reference_files():
    out={}
    for y in ('2024','2025','2026'):
        keys=json.loads((OLD/f'keys-{y}.json').read_text());out[y]={s+'|'+m:OLD/'evals'/f'{keys[s+"|BALANCED_RETEST|"+m]}.json' for s in ('NORMAL','ONE') for m in ('BASE','STALL30','STRUCT30')}
    return out


def bindings():
    out=P.bindings()
    for p in [*HERE.glob('*.py'),HERE/'PLAN.md',HERE/'SOURCES.md',HERE/'configuration.json',HERE/'diagnosis.json',*[HERE/f'path-anatomy-{y}.json' for y in ('2024','2025','2026')]]:
        out['sources'][p.relative_to(ROOT).as_posix()]=B.P.sha(p)
    out['n05_freeze']=B.P.sha(PARENT/'freeze.json');out['n06_manifest']=B.P.sha(HERE.parent/'2026-11-01-fno-variant-selector/decision-manifest.json')
    out['controls']={p.relative_to(ROOT).as_posix():B.P.sha(p) for fs in reference_files().values() for p in fs.values()}
    out['saved_records']={p.name:B.P.sha(p) for stem in ('FNO_RESEARCH_REFERENCE','FNO_RESEARCH_CHALLENGERS','FNO_RESEARCH_PROGRESS','FNO_RESEARCH_SELECTOR_N06') for p in (ROOT/'docs').glob(stem+'.*')}
    return out


def freeze():
    clean={k:v for k,v in os.environ.items() if k not in ('O30F_YEAR','O30C_YEAR')};out={}
    for y in ('2024','2025','2026'):
        env={**clean,**({'O30F_YEAR':y} if y=='2024' else {'O30C_YEAR':y})};out[y]=json.loads(subprocess.check_output([sys.executable,__file__,'bindings'],cwd=ROOT,env=env).decode().strip().splitlines()[-1])
    assert not (HERE/'freeze.json').exists();X.write(HERE/'freeze.json',dict(schema='n07_anatomy_v1',bindings=out,books=books(),configuration=json.loads((HERE/'configuration.json').read_text()),qualified=False,can_place_orders=False,all_years_seen=True))


def verify():
    f=json.loads((HERE/'freeze.json').read_text());assert f['bindings'][B.YEAR]==X.native(bindings()),'source/input/reference changed'
    assert json.loads(subprocess.check_output(['git','show','HEAD:'+(HERE/'freeze.json').relative_to(ROOT).as_posix()],cwd=ROOT))==f,'freeze uncommitted'


def run(jobs,phase):
    assert 1<=jobs<=3;B.O27F.deny_network();verify();C.table('year')
    if phase=='candidate':
        import build_controls
        assert len(build_controls.controls())==18,'all18 exact controls required before scoring'
    with ProcessPoolExecutor(max_workers=jobs,initializer=B.L._init) as pool:Y.Runner(pool,jobs).run(list(books(phase).values()),source='year',window=C.WINDOW)
    verify();X.write(LOCAL/f'keys-{phase}-{B.YEAR}.json',{n:Y.task_key(b,'year',C.WINDOW) for n,b in books(phase).items()});print('DONE',phase,B.YEAR,len(books(phase)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['bindings','freeze','run']);p.add_argument('--phase',choices=['reference','candidate'],default='reference');p.add_argument('--jobs',type=int,default=3);a=p.parse_args()
    if a.action=='bindings':print(json.dumps(X.native(bindings())))
    elif a.action=='freeze':freeze()
    else:run(a.jobs,a.phase)
