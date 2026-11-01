"""N02 whole-policy research selector. No runtime module imports this file."""
import argparse,copy,json,os,subprocess,sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime,timedelta
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=next(p for p in HERE.parents if (p/'python-engine').is_dir())
BROAD=HERE.parent/'2026-10-31-fno-broad-search'
sys.path[:0]=[str(HERE),str(BROAD),str(BROAD/'calendar')]
import core_policy as P
import calendar_lab as CAL
B=CAL.B;Y,G,C,S=B.Y,B.G,B.C,B.S
from config import settings
LOCAL=HERE/'_local';Y.EVALS=LOCAL/'evals';_DECISIONS=None
INDEX={'MAIN':(0,1,2,3),'NO_EFF':(0,1,3),'TPB_FULL':(0,1,2,3,4),'TPB_ONE':(0,1,2,3,4)}


def native(x):
    if isinstance(x,dict):return {str(k):native(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [native(v) for v in x]
    if isinstance(x,np.generic):return x.item()
    return str(x) if isinstance(x,Path) else x


def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(native(x),indent=2,allow_nan=False)+'\n',encoding='utf-8')


def decisions():
    global _DECISIONS
    if _DECISIONS is None:_DECISIONS=json.loads((LOCAL/f'decisions-{B.YEAR}.json').read_text())
    return _DECISIONS


_old_route=Y.BookReplay.route
def route(self,frame,regime,now):
    policy=self.book.get('n02_policy')
    if not policy:return _old_route(self,frame,regime,now)
    bar=Y.replay._last_closed_bar(frame,now);day=now.date().isoformat()
    if policy=='STATIC':decision={'profile':self.book['n02_profile'],'asof':None,'latest_label_exit':None}
    else:
        if bar is None or now-(datetime.fromisoformat(bar).replace(tzinfo=now.tzinfo)+timedelta(minutes=5))>=timedelta(minutes=5):
            return G.MomSignal(bar_ts=bar or '',reject_reason='n02:stale_or_missing_bar')
        decision=decisions()[policy][day]
        assert decision['asof']<=day and (decision['latest_label_exit'] is None or decision['latest_label_exit'][:10]<day)
    profile=decision['profile'];row=self.table.get(day)
    for i in INDEX[profile]:
        m=self.members[i]
        if not Y.ROUTER.allowed(m['gate'],row):continue
        sig=self._signal(i,frame,regime,now,bar)
        if sig.direction is None:continue
        # Preserve MAIN's first-firing-member semantics: a stretched first
        # signal is rejected, not replaced by a later member on that bar.
        stretch=S.stretch_at(frame,now,sig.direction.value)
        if stretch is not None and stretch>=.5:return G.MomSignal(bar_ts=sig.bar_ts,reject_reason='n02:stretched')
        if i==4 and sig.direction.value!='SHORT':return G.MomSignal(bar_ts=sig.bar_ts,reject_reason='n02:low_tpb_puts_only')
        self._fired=i
        self._n02_decision={'selected_profile':profile,'selector_policy':policy,'selection_asof':decision['asof'],'signal_bar':sig.bar_ts,
                            'selection_latest_label_exit':decision['latest_label_exit'],'origin':'TPB_LOW' if i==4 else 'MAIN',
                            'entry_expert':m['name'],'entry_gate':m['gate']}
        if i==4 and profile=='TPB_ONE':
            settings.FNO_MAX_LOTS=min(settings.FNO_MAX_LOTS,1)
            settings.FNO_MAX_LOTS_PROVEN=min(settings.FNO_MAX_LOTS_PROVEN,1)
        return sig
    return G.MomSignal(bar_ts=bar or '',reject_reason='n02:no_member')
Y.BookReplay.route=route


_old_entry=Y.BookReplay._entry
def entry(self,book,obs,frame,day,now):
    if not self.book.get('n02_policy'):return _old_entry(self,book,obs,frame,day,now)
    before=(settings.FNO_MAX_LOTS,settings.FNO_MAX_LOTS_PROVEN);identifier=book.next_id;decision_start=len(getattr(self,'decisions',[]));self._n02_decision=None
    try:
        _old_entry(self,book,obs,frame,day,now)
        if self._n02_decision:
            for trace in getattr(self,'decisions',[])[decision_start:]:trace.update(copy.deepcopy(self._n02_decision))
        if book.next_id!=identifier:
            leg=book.open[identifier]
            leg._n02_metadata={**copy.deepcopy(self._n02_decision),'admission_id':f'N02/{B.YEAR}/{Y.digest(self.book)}/{identifier}',
                'initial_entry_time':leg.entry_time,'initial_entry_premium':leg.entry_premium,'initial_quantity':leg.initial_qty,
                'initial_stop_underlying':leg.stop_underlying,'initial_target_underlying':leg.target_underlying}
    finally:settings.FNO_MAX_LOTS,settings.FNO_MAX_LOTS_PROVEN=before
Y.BookReplay._entry=entry


_old_close=Y.replay._close_record
def close_record(leg,*a,**k):
    record,net=_old_close(leg,*a,**k)
    if hasattr(leg,'_n02_metadata'):record.update(copy.deepcopy(leg._n02_metadata))
    return record,net
Y.replay._close_record=close_record
META=('selected_profile','selector_policy','selection_asof','selection_latest_label_exit','signal_bar','origin','entry_expert','entry_gate','admission_id','initial_entry_time','initial_entry_premium','initial_quantity','initial_stop_underlying','initial_target_underlying')
Y.KEEP=tuple(dict.fromkeys((*Y.KEEP,*META)))


_old_run=Y.BookReplay.run
def run_book(self,start,end):
    result=_old_run(self,start,end)
    if self.book.get('n02_policy'):
        key=Y.task_key(self.book,self.source,(start,end));target=LOCAL/'traces'/f'{key}.json';part=target.with_suffix(f'.{os.getpid()}.part')
        write(part,{'book':self.book,'window':[start,end],'decisions':self.decisions});os.replace(part,target)
    return result
Y.BookReplay.run=run_book


def members():return [*B.W.gated(B.W.OPEN),Y.named('TPB',B.W.CLOSED)]


def book(name,policy,profile=None):
    return B.P.X.book('N02|'+name,members=members(),skip=None,n02_policy=policy,n02_profile=profile,n02_contract='v1')


def books(phase):
    if phase=='reference':return {p:book(p,'STATIC',p) for p in INDEX}
    return {p:book(p,p) for p in ('CORE_ADD','CORE_SELECT')}


def bindings():
    out=B.bindings()
    for p in [*HERE.glob('*.py'),HERE/'PLAN.md',HERE/'SOURCES.md',HERE/'configuration.json',BROAD/'calendar/calendar_lab.py']:
        out['sources'][p.relative_to(ROOT).as_posix()]=B.P.sha(p)
    out['2023_exam_sha256']=B.P.sha(ROOT/'docs/research/fno/2026-10-31-weak-spots/freeze-2023.json')
    out['diagnosis_sha256']=B.P.sha(HERE/'diagnosis.json')
    out['legacy_references']={}
    for y in ('2024','2025','2026'):
        keys=json.loads((B.W.LOCAL/f'keys-{y}.json').read_text())
        for n in ('EX|MAIN','EX|C|no_eff','EX|D|tpb_puts_closed'):
            p=B.W.LOCAL/'evals'/f'{keys[n]}.json';out['legacy_references'][p.relative_to(ROOT).as_posix()]=B.P.sha(p)
    return out


def freeze():
    clean={k:v for k,v in os.environ.items() if k not in ('O30F_YEAR','O30C_YEAR')};out={}
    for y in ('2024','2025','2026'):
        env={**clean,**({'O30F_YEAR':y} if y=='2024' else {'O30C_YEAR':y})}
        out[y]=json.loads(subprocess.check_output([sys.executable,__file__,'bindings'],cwd=ROOT,env=env).decode().strip().splitlines()[-1])
    assert not (HERE/'freeze.json').exists();write(HERE/'freeze.json',{'schema':'n02_core_selector_v1','bindings':out,'reference_books':books('reference'),'candidate_books':books('candidate'),
            'configuration':json.loads((HERE/'configuration.json').read_text()),'all_years_seen':True,'qualified':False,'can_place_orders':False})


def verify(phase):
    f=json.loads((HERE/'freeze.json').read_text());assert f['bindings'][B.YEAR]==native(bindings()),'frozen source/input changed'
    for name in ['freeze.json']+(['decision-manifest.json'] if phase=='candidate' else []):
        p=HERE/name;assert json.loads(subprocess.check_output(['git','show','HEAD:'+p.relative_to(ROOT).as_posix()],cwd=ROOT))==json.loads(p.read_text()),'uncommitted '+name
    if phase=='candidate':
        m=json.loads((HERE/'decision-manifest.json').read_text());assert B.P.sha(LOCAL/f'decisions-{B.YEAR}.json')==m['decisions'][B.YEAR]['sha256']
        assert all(B.P.sha(ROOT/p)==h for p,h in m['reference_files'].items())


def run(jobs,phase):
    B.O27F.deny_network();verify(phase);C.table('year')
    with ProcessPoolExecutor(max_workers=jobs,initializer=B.L._init) as pool:
        worker=Y.Runner(pool,jobs);worker.run(list(books(phase).values()),source='year',window=C.WINDOW)
    verify(phase);write(LOCAL/f'keys-{phase}-{B.YEAR}.json',{n:Y.task_key(b,'year',C.WINDOW) for n,b in books(phase).items()})
    print('DONE',phase,B.YEAR,len(books(phase)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['bindings','freeze','run']);p.add_argument('--phase',choices=['reference','candidate'],default='reference');p.add_argument('--jobs',type=int,default=3);a=p.parse_args()
    if a.action=='bindings':print(json.dumps(native(bindings())))
    elif a.action=='freeze':freeze()
    else:run(a.jobs,a.phase)
