"""N03 isolated EFF entry/exit experiment; never imported by the application."""
import argparse,copy,json,math,os,subprocess,sys
from dataclasses import replace
from datetime import datetime,timedelta
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=next(p for p in HERE.parents if (p/'python-engine').is_dir());PARENT=HERE.parent/'2026-11-01-fno-core-selector'
sys.path[:0]=[str(HERE),str(PARENT)]
import core_lab as X
import eff_rules as R
from fno_book import _features
from fno_costs import calc_fno_costs
Y,B,C,G=X.Y,X.B,X.C,X.G;LOCAL=HERE/'_local';PARENT_LOCAL=X.LOCAL
X.LOCAL=LOCAL;Y.EVALS=LOCAL/'evals';X.INDEX['EFF_ONLY']=(2,)

@lru_cache(None)
def parent_decisions():return json.loads((PARENT_LOCAL/f'decisions-{B.YEAR}.json').read_text())
X.decisions=parent_decisions

def context(frame,now):
    if frame is None or frame.empty:return None
    f=_features(frame);end=f.index.searchsorted(now.replace(tzinfo=None)-timedelta(minutes=5),side='right');closed=f.iloc[:end]
    today=closed[closed.index.date==now.date()]
    if len(today)<5:return None
    last=today.iloc[-1];previous=today.iloc[-2];stamp=today.index[-1];start=stamp
    for t in reversed(today.index[:-1]):
        if (start-t).total_seconds()!=300:break
        start=t
    fresh=timedelta(0)<=now.replace(tzinfo=None)-(stamp.to_pydatetime()+timedelta(minutes=5))<timedelta(minutes=5)
    valid_volume=bool((today.volume>=0).all())
    vwap=float(last.vwap)
    if not math.isfinite(vwap):vwap=float(((today.high+today.low+today.close)/3).mean())
    values={'bar':stamp.strftime('%Y-%m-%d %H:%M:%S'),'close':float(last.close),'open':float(last.open),'high':float(last.high),'low':float(last.low),
        'previous_close':float(previous.close),'atr':float(last.atr),'rvol':float(last.rvol) if math.isfinite(last.rvol) else 0.,'vwap':vwap,
        'prior4high':float(today.iloc[-5:-1].high.max()),'prior4low':float(today.iloc[-5:-1].low.min()),'fresh':bool(fresh),'valid_volume':valid_volume,'consecutive_from':start.strftime('%Y-%m-%d %H:%M:%S')}
    return values if all(math.isfinite(values[k]) for k in ('close','open','high','low','previous_close','atr','vwap','prior4high','prior4low')) and values['atr']>0 else None

_signal=Y.BookReplay._signal
def signal(self,i,frame,regime,now,bar):
    original=_signal(self,i,frame,regime,now,bar)
    if self.book.get('n03_variant')!='RETEST' or self.members[i]['name']!='EFF':return original
    if not hasattr(self,'_n03_retest'):self._n03_retest=R.RetestState()
    cache=getattr(self,'_n03_context',None)
    if cache is None or cache[0]!=bar:
        cache=(bar,context(frame,now));self._n03_context=cache
    # Freshness is checked against this tick, including repeated evaluations.
    ctx=copy.copy(cache[1]) if cache[1] else None
    if ctx:ctx['fresh']=timedelta(0)<=now.replace(tzinfo=None)-(datetime.fromisoformat(ctx['bar'])+timedelta(minutes=5))<timedelta(minutes=5)
    answer,info=self._n03_retest.step(original,ctx,regime);self._n03_entry_context=info
    return answer if answer is not None else G.MomSignal(bar_ts=bar or '',reject_reason='n03:'+info['reason'])
Y.BookReplay._signal=signal

_entry=Y.BookReplay._entry
def entry(self,book,obs,frame,day,now):
    before=book.next_id;self._n03_entry_context=None
    _entry(self,book,obs,frame,day,now)
    if self.book.get('n03_variant') and book.next_id!=before:
        leg=book.open[before];leg._n02_metadata.update(admission_id=f'N03/{B.YEAR}/{Y.digest(self.book)}/{before}',n03_variant=self.book['n03_variant'],
            n03_entry_context=copy.deepcopy(self._n03_entry_context) if self.members[self._fired]['name']=='EFF' else None)
Y.BookReplay._entry=entry

def liquidation(leg,obs,now,frame):
    quote=obs.options.get(leg.token);bid=quote.bid if quote and quote.bid>0 else None
    stress=(B.P.L._COST[0]+B.P.L._COST[1]*leg.lots)*leg.lots
    net=(bid-leg.entry_premium)*leg.qty-calc_fno_costs(leg.entry_premium,bid,leg.qty)-stress if bid is not None else None
    initial=getattr(leg,'_n02_metadata',{});stop=initial.get('initial_stop_underlying',leg.stop_underlying);risk=abs(leg.entry_underlying-stop)
    assert risk>0
    progress=(1 if leg.direction=='LONG' else -1)*(obs.future.ltp-leg.entry_underlying)/risk;age=(now-datetime.fromisoformat(leg.entry_time)).total_seconds()/60
    ctx=context(frame,now) if 60<=age<90 else None
    minute,action=R.horizon(age,bool(leg.trail_active),net,progress,ctx,leg.direction)
    return minute,{'action':action,'age_minutes':age,'net_at_bid_after_cost':net,'progress_r':progress,'bid':bid,'context':ctx}

_manage=Y.BookReplay._manage
def manage(self,book,obs,now):
    if self.book.get('n03_variant')!='HORIZON':return _manage(self,book,obs,now)
    full,policies=book.open,self.policies
    try:
        for ident in sorted(full):
            leg=full[ident];i=self.leg_member[ident];self.policies=list(policies);book.open={ident:leg}
            if self.members[i]['name']=='EFF':
                minute,ctx=liquidation(leg,obs,now,self._frame);leg._n03_exit_context=ctx
                leg._n03_ever_extended=getattr(leg,'_n03_ever_extended',False) or ctx['action']=='CONTINUE90'
                params={**dict(policies[i].exit_overrides),'FNO_TIME_STOP_MIN':minute}
                self.policies[i]=replace(policies[i],exit_overrides=tuple(sorted(params.items())))
            _manage(self,book,obs,now)
            if ident not in book.open:del full[ident]
    finally:book.open=full;self.policies=policies
Y.BookReplay._manage=manage

_close=Y.replay._close_record
def close(leg,*args,**kwargs):
    record,net=_close(leg,*args,**kwargs)
    if hasattr(leg,'_n03_exit_context'):record.update(n03_exit_context=copy.deepcopy(leg._n03_exit_context),n03_ever_extended=bool(leg._n03_ever_extended))
    return record,net
Y.replay._close_record=close
Y.KEEP=tuple(dict.fromkeys((*Y.KEEP,'n03_variant','n03_entry_context','n03_exit_context','n03_ever_extended')))

def books():
    out={}
    for sizing,contexts in [('NORMAL',('EFF_ONLY','MAIN','TPB_ONE','CORE_SELECT')),('ONE',('EFF_ONLY','MAIN'))]:
        for ctx in contexts:
            for variant in ('BASE','RETEST','HORIZON'):
                name=f'{sizing}|{ctx}|{variant}';b=X.book('N03|'+name,'CORE_SELECT' if ctx=='CORE_SELECT' else 'STATIC',None if ctx=='CORE_SELECT' else ctx)
                b.update(n03_variant=variant,n03_context=ctx,n03_sizing=sizing,n03_contract='v1')
                if sizing=='ONE':b['cfg']={**b.get('cfg',{}),'FNO_MAX_LOTS':1,'FNO_MAX_LOTS_PROVEN':1}
                out[name]=b
    b=X.book('N03|NORMAL|TPB_FULL|BASE','STATIC','TPB_FULL');b.update(n03_variant='BASE',n03_context='TPB_FULL',n03_sizing='NORMAL',n03_contract='v1');out['NORMAL|TPB_FULL|BASE']=b
    return out

def bindings():
    out=X.bindings()
    for p in [*HERE.glob('*.py'),HERE/'PLAN.md',HERE/'SOURCES.md',HERE/'configuration.json']:
        out['sources'][p.relative_to(ROOT).as_posix()]=B.P.sha(p)
    out['parent_freeze_sha256']=B.P.sha(PARENT/'freeze.json');out['parent_decisions_manifest_sha256']=B.P.sha(PARENT/'decision-manifest.json')
    out['decision_file_sha256']=B.P.sha(PARENT_LOCAL/f'decisions-{B.YEAR}.json');out['feature_audit_sha256']=B.P.sha(HERE/'feature-audit.json')
    return out

def freeze():
    clean={k:v for k,v in os.environ.items() if k not in ('O30F_YEAR','O30C_YEAR')};out={}
    for y in ('2024','2025','2026'):
        env={**clean,**({'O30F_YEAR':y} if y=='2024' else {'O30C_YEAR':y})}
        out[y]=json.loads(subprocess.check_output([sys.executable,__file__,'bindings'],cwd=ROOT,env=env).decode().strip().splitlines()[-1])
    assert not (HERE/'freeze.json').exists();X.write(HERE/'freeze.json',{'schema':'n03_eff_v1','bindings':out,'books':books(),'configuration':json.loads((HERE/'configuration.json').read_text()),'qualified':False,'can_place_orders':False,'all_years_seen':True})

def verify():
    frozen=json.loads((HERE/'freeze.json').read_text());assert frozen['bindings'][B.YEAR]==X.native(bindings()),'source/input changed'
    assert json.loads(subprocess.check_output(['git','show','HEAD:'+(HERE/'freeze.json').relative_to(ROOT).as_posix()],cwd=ROOT))==frozen,'freeze uncommitted'
    manifest=json.loads((PARENT/'decision-manifest.json').read_text());assert manifest['decisions'][B.YEAR]['sha256']==B.P.sha(PARENT_LOCAL/f'decisions-{B.YEAR}.json')

def run(jobs):
    assert 1<=jobs<=3;B.O27F.deny_network();verify();C.table('year')
    with ProcessPoolExecutor(max_workers=jobs,initializer=B.L._init) as pool:Y.Runner(pool,jobs).run(list(books().values()),source='year',window=C.WINDOW)
    verify();X.write(LOCAL/f'keys-{B.YEAR}.json',{n:Y.task_key(b,'year',C.WINDOW) for n,b in books().items()});print('DONE',B.YEAR,len(books()),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['bindings','freeze','run']);p.add_argument('--jobs',type=int,default=3);a=p.parse_args()
    if a.action=='bindings':print(json.dumps(X.native(bindings())))
    elif a.action=='freeze':freeze()
    else:run(a.jobs)
