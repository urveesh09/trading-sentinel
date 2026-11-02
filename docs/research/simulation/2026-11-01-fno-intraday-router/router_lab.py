"""N01 offline intraday router using the shipped entry/cash/exit lifecycle."""
from __future__ import annotations
import argparse,copy,hashlib,json,os,subprocess,sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime,timedelta
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent;ROOT=next(p for p in HERE.parents if (p/'python-engine').is_dir())
PREVIOUS=HERE.parent/'2026-10-31-fno-broad-search'
sys.path[:0]=[str(HERE),str(PREVIOUS),str(PREVIOUS/'calendar')]
import regime_policy as R
import calendar_lab as CAL
B=CAL.B;Y,G,C,L,S=B.Y,B.G,B.C,B.L,B.S
LOCAL=HERE/'_local';Y.EVALS=LOCAL/'evals'
_STATES={};_HITS={};_MODELS=None


def native(x):
    if isinstance(x,dict):return {str(k):native(v) for k,v in x.items()}
    if isinstance(x,(tuple,list)):return [native(v) for v in x]
    if isinstance(x,np.generic):return native(x.item())
    if isinstance(x,np.ndarray):return native(x.tolist())
    if isinstance(x,Path):return str(x)
    return x


def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(native(x),indent=2,allow_nan=False)+'\n',encoding='utf-8')


def states(frame,day):
    f=B.O27F.day_features(frame,day)
    if not f:return {},None
    key=(B.YEAR,str(day),f['stamps'][-1],len(frame),str(frame.index[0]))
    if key not in _STATES:_STATES[key]=R.describe(f['t'],B.P.dmi(frame))
    return _STATES[key],f


def state_at(frame,now):
    state,f=states(frame,now.replace(tzinfo=None).date())
    bar=B.O27F.last_closed_bar(f,now) if f else None
    return state.get(bar,{'state':'UNAVAILABLE'}),bar,state


def all_triggers(m,f):
    t=f['t'];n=m['n'];out={}
    if m['family']=='BOLL_REENTRY':
        c=t['close'];mean=c.rolling(n).mean();sd=c.rolling(n).std(ddof=1)
    for i in range(n+1,len(t)):
        w=t.iloc[i-n:i+1];r=t.iloc[i]
        if not 585<=r['minute']+5<=840 or np.any(np.diff(w['minute'])!=5):continue
        if not np.isfinite(w[['close','high','low','volume','atr']].to_numpy()).all() or (w['volume']<0).any() or r['atr']<=0:continue
        d=None
        if m['family']=='DONCHIAN':
            d=1 if r['close']>t['high'].iloc[i-n:i].max() else (-1 if r['close']<t['low'].iloc[i-n:i].min() else None)
        elif m['family']=='BOLL_REENTRY':
            d=1 if c.iloc[i-1]<mean.iloc[i-1]-2*sd.iloc[i-1] and c.iloc[i]>=mean.iloc[i]-2*sd.iloc[i] else (-1 if c.iloc[i-1]>mean.iloc[i-1]+2*sd.iloc[i-1] and c.iloc[i]<=mean.iloc[i]+2*sd.iloc[i] else None)
        else:raise ValueError(m['family'])
        if d:out[f['stamps'][i]]=(d,float(r['close']-d*m['stop_atr']*r['atr']),float(r['close']+d*m['target_r']*m['stop_atr']*r['atr']))
    return out


_previous_signal=G.new_signal
def new_signal(m,frame,regime,now):
    if not m.get('n01_all_triggers'):return _previous_signal(m,frame,regime,now)
    f=B.O27F.day_features(frame,now.replace(tzinfo=None).date());bar=B.O27F.last_closed_bar(f,now) if f else None
    if not f or not f['complete_open']:return G.MomSignal(bar_ts=bar or '',reject_reason='n01:no_features')
    key=(G.digest(m),str(f['day']),f['stamps'][-1],len(frame))
    if key not in _HITS:_HITS[key]=all_triggers(m,f)
    hit=_HITS[key].get(bar);sig=G._signal(frame,regime,now,m,hit[0] if hit else None,bar,f)
    if hit and sig.direction is not None:sig.stop_underlying,sig.target_underlying=hit[1:]
    return sig
G.new_signal=new_signal


def model_file():return LOCAL/f'models-{B.YEAR}.json'


def models():
    global _MODELS
    if _MODELS is None:_MODELS=json.loads(model_file().read_text())
    return _MODELS


def cell_of(self,now,state):
    row=self.table.get(now.date().isoformat())
    if row is None:return None
    macro='HIGH' if Y.ROUTER.allowed('adx_abs30:HIGH',row) else 'LOW'
    return state+'|'+macro


_previous_route=Y.BookReplay.route
def route(self,frame,regime,now):
    policy=self.book.get('n01_policy')
    if not policy:return _previous_route(self,frame,regime,now)
    observed,bar,_=state_at(frame,now);state=observed['state'];cell=cell_of(self,now,state)
    self._n01_decision={'router_state':state,'router_cell':cell,'router_policy':policy,'router_model_asof':None,'router_fallback':False}
    if getattr(self,'_n01_counted',None)!=bar:
        self.notes['router_state:'+state]+=1;self._n01_counted=bar
    if policy=='STATIC':allowed=list(R.EXPERTS)
    elif not cell:allowed=[]
    elif policy=='LEARN':
        data=models();month=now.date().isoformat()[:7]+'-01';day=now.date().isoformat()
        if data['session_index'][day]<90:
            allowed=R.rule_experts(state);self._n01_decision['router_fallback']=True
        else:
            model=data['models'][month];assert model['asof']<=day
            assert model['latest_label_exit'] is None or model['latest_label_exit'][:10]<month
            allowed=[r['expert'] for r in model['choices'].get(cell,[])] if state not in ('SHOCK','UNAVAILABLE') else []
            self._n01_decision['router_model_asof']=month
    else:allowed=R.rule_experts(state)
    by={expert:i for i,expert in enumerate(self.book['n01_experts'])}
    for expert in allowed:
        if expert not in by:continue
        i=by[expert];sig=self._signal(i,frame,regime,now,bar)
        if sig.direction is None:continue
        if policy!='STATIC' and not R.direction_allowed(state,sig.direction.value):continue
        if self.members[i]['kind']=='NAMED':
            stretch=S.stretch_at(frame,now,sig.direction.value)
            if stretch is not None and stretch>=.5:continue
        self._fired=i;self._n01_decision['router_expert']=expert
        return sig
    return G.MomSignal(bar_ts=bar or '',reject_reason='n01:no_eligible_expert')
Y.BookReplay.route=route


_previous_entry=Y.BookReplay._entry
def entry(self,book,obs,frame,day,now):
    before=book.next_id;_previous_entry(self,book,obs,frame,day,now)
    if self.book.get('n01_policy') and book.next_id!=before:
        if not hasattr(self,'_n01_admissions'):self._n01_admissions={}
        leg=book.open[before]
        metadata={**self._n01_decision,'initial_stop_underlying':leg.stop_underlying,'initial_target_underlying':leg.target_underlying,
                  'initial_quantity':leg.initial_qty,'initial_entry_premium':leg.entry_premium,'initial_entry_time':leg.entry_time,
                  'router_admission_id':f'N01/{B.YEAR}/{Y.digest(self.book)}/{before}'}
        self._n01_admissions[before]=metadata
        leg._n01_metadata=copy.deepcopy(metadata)
Y.BookReplay._entry=entry


_previous_close=Y.replay._close_record
def close_record(leg,*args,**kwargs):
    record,net=_previous_close(leg,*args,**kwargs)
    if hasattr(leg,'_n01_metadata'):record.update(copy.deepcopy(leg._n01_metadata))
    return record,net
Y.replay._close_record=close_record


_previous_manage=Y.BookReplay._manage
def manage(self,book,obs,now):
    _previous_manage(self,book,obs,now)
    if not self.book.get('n01_policy'):return
    admissions=getattr(self,'_n01_admissions',{})
    if self.book.get('n01_policy')!='RULE_EXIT' or self._frame is None:return
    observed,bar,history=state_at(self._frame,now)
    tail=[r['state'] for stamp,r in history.items() if bar and stamp<=bar][-3:]
    from fno_adaptive_risk import Close
    for leg_id,leg in list(book.open.items()):
        saved=admissions[leg_id]
        if now-datetime.fromisoformat(leg.entry_time)<timedelta(minutes=15):continue
        if not R.invalidates(saved['router_state'],tail,leg.direction):continue
        q=obs.options.get(leg.token);basis=q.bid if q and q.bid>0 else 0.
        if basis<=0:self.notes['router_exit_unpriced']+=1;continue
        record,net=Y.replay._close_record(leg,now,basis,'router_state_invalidated',obs.future.ltp)
        record.update(member=self.leg_member[leg_id],entry_qty=leg.initial_qty,exit_router_state=observed['state'])
        record.update({k:v for k,v in saved.items() if not k.startswith('_')})
        book.trades.append(record);book.equity+=net;book.closes.append((now,net,'SINGLE_LEG'));book.completed.append(Close(now,record['net_pnl'],True));del book.open[leg_id]
        self.notes['router_state_exits']+=1
Y.BookReplay._manage=manage

Y.KEEP=tuple(dict.fromkeys((*Y.KEEP,'router_state','router_cell','router_expert','router_policy','router_model_asof','router_fallback','router_admission_id','initial_stop_underlying','initial_target_underlying','initial_quantity','initial_entry_premium','initial_entry_time','exit_router_state')))


def experts():
    out={n:Y.named(n,'ALWAYS') for n in ('SHIPPED','OR20','EFF','TPB')}
    out.update({n:G.new_member(n,'ALWAYS',n=10,stop_atr=1.5,target_r=3.,exit='RUN',n01_all_triggers=True) for n in ('DONCHIAN','BOLL_REENTRY')})
    return out


def book(name,policy,raw=False,names=None):
    names=names or list(R.EXPERTS);members=[experts()[n] for n in names]
    return B.P.X.book('N01|'+name,members=members,cfg=dict(S.RAW) if raw else {},skip=None,cost=not raw,n01_policy=policy,n01_experts=names)


def books(phase):
    if phase=='base':
        prior=B.books('screen');out={'MAIN':prior['EX|MAIN'],'OLD_BREAKOUT_LOW':prior['RAW|DONCHIAN|g2']}
        out.update({'LIB|'+e:book('LIB|'+e,'STATIC',True,[e]) for e in R.EXPERTS})
        out['STATIC_UNION']=book('STATIC_UNION','STATIC')
    else:
        out={prefix+'|'+p:book(prefix+'|'+p,p,prefix=='RAW') for p in ('RULE','RULE_EXIT','LEARN') for prefix in ('RAW','EX')}
    return {n:{**b,'n01_contract':'v1'} for n,b in out.items()}


def bindings():
    out=B.bindings()
    for p in [*HERE.glob('*.py'),HERE/'PLAN.md',HERE/'SOURCES.md',HERE/'configuration.json',PREVIOUS/'calendar/calendar_lab.py',PREVIOUS/'calendar/freeze.json']:
        out['sources'][p.relative_to(ROOT).as_posix()]=B.P.sha(p)
    out['2023_exam_sha256']=B.P.sha(ROOT/'docs/research/fno/2026-10-31-weak-spots/freeze-2023.json')
    return out


def freeze():
    parts={};clean={k:v for k,v in os.environ.items() if k not in ('O30F_YEAR','O30C_YEAR')}
    for y in ('2024','2025','2026'):
        env={**clean,**({'O30F_YEAR':y} if y=='2024' else {'O30C_YEAR':y})}
        parts[y]=json.loads(subprocess.check_output([sys.executable,__file__,'bindings'],cwd=ROOT,env=env).decode().strip().splitlines()[-1])
    assert not (HERE/'freeze.json').exists()
    write(HERE/'freeze.json',{'schema':'n01_intraday_router_v1','bindings':parts,'base_books':books('base'),'candidate_books':books('candidate'),'configuration':json.loads((HERE/'configuration.json').read_text()),'all_years_seen':True,'qualified':False,'can_place_orders':False})


def verify(phase):
    f=json.loads((HERE/'freeze.json').read_text());assert f['bindings'][B.YEAR]==native(bindings()),'frozen input/source changed'
    for p in [HERE/'freeze.json']+([HERE/'training-manifest.json'] if phase=='candidate' else []):
        assert json.loads(subprocess.check_output(['git','show','HEAD:'+p.relative_to(ROOT).as_posix()],cwd=ROOT))==json.loads(p.read_text()),'uncommitted '+p.name
    if phase=='candidate':
        manifest=json.loads((HERE/'training-manifest.json').read_text())
        assert B.P.sha(model_file())==manifest['models'][B.YEAR]['sha256']
        assert all(B.P.sha(ROOT/p)==h for p,h in manifest['library_sha256'].items())


def init():L._init()


def run(jobs,phase):
    B.O27F.deny_network();verify(phase);C.table('year')
    with ProcessPoolExecutor(max_workers=jobs,initializer=init) as pool:
        worker=Y.Runner(pool,jobs);worker.run(list(books(phase).values()),source='year',window=C.WINDOW)
    verify(phase);write(LOCAL/f'keys-{phase}-{B.YEAR}.json',{n:Y.task_key(b,'year',C.WINDOW) for n,b in books(phase).items()})
    print('DONE',phase,B.YEAR,len(books(phase)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['bindings','freeze','run']);p.add_argument('--phase',choices=['base','candidate'],default='base');p.add_argument('--jobs',type=int,default=3);a=p.parse_args()
    if a.action=='bindings':print(json.dumps(native(bindings())))
    elif a.action=='freeze':freeze()
    else:run(a.jobs,a.phase)
