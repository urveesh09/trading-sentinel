"""O31i frozen broad hypothesis population; offline research only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'python-engine/fno_policy_replay.py').is_file())
PRIOR=HERE.parent/'2026-10-31-fno-complements'
sys.path.insert(0,str(PRIOR))
import lab_gap as P  # noqa:E402

Y,G,C,L,S,W,O27F=P.Y,P.G,P.C,P.L,P.S,P.W,P.O27F
YEAR,LOCAL=P.YEAR,HERE/'_local'
Y.EVALS=LOCAL/'evals'
FAMILIES=('EMA_CROSS','KAMA_TURN','DONCHIAN','BOLL_REENTRY','CCI_REENTRY','RSI_DIVERGENCE',
          'REGRESSION_REVERT','PDL_RECLAIM','GAP_REPAIR','RANGE_RELEASE','OBV_BREAK','CLOCK_MOMO')
GENES=((10,1.,2.,'LIVE'),(20,1.5,2.,'LIVE'),(10,1.5,3.,'RUN'),(20,1.,3.,'RUN'))
_CACHE={}


def kama(close,n):
    a=close.to_numpy(dtype=float);out=np.full(len(a),np.nan)
    if len(a)<=n:return pd.Series(out,index=close.index)
    out[n]=float(np.mean(a[:n+1]))
    for i in range(n+1,len(a)):
        path=float(np.abs(np.diff(a[i-n:i+1])).sum())
        er=abs(a[i]-a[i-n])/path if path>0 else 0.
        speed=(er*(2/3-2/31)+2/31)**2
        out[i]=out[i-1]+speed*(a[i]-out[i-1])
    return pd.Series(out,index=close.index)


def readings(t,n):
    c,h,l=t['close'],t['high'],t['low']
    ema=c.ewm(span=n,adjust=False).mean();slow=c.ewm(span=2*n,adjust=False).mean()
    mean=c.rolling(n).mean();sd=c.rolling(n).std(ddof=1)
    tp=(h+l+c)/3
    mad=tp.rolling(n).apply(lambda v:np.mean(np.abs(v-np.mean(v))),raw=True)
    cci=(tp-tp.rolling(n).mean())/(.015*mad.replace(0,np.nan))
    diff=c.diff();up=diff.clip(lower=0).ewm(alpha=1/14,adjust=False).mean();down=(-diff.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
    rsi=100-100/(1+up/down.replace(0,np.nan));rsi=rsi.where(down>0,100.).where((up+down)>0,50.)
    slope=np.full(len(t),np.nan);resid=np.full(len(t),np.nan);res_sd=np.full(len(t),np.nan)
    x=np.arange(n,dtype=float);xx=x-x.mean();den=float((xx*xx).sum())
    vals=c.to_numpy()
    for i in range(n,len(t)):
        past=vals[i-n:i];b=float((xx*(past-past.mean())).sum()/den)
        fit=past.mean()+b*xx
        slope[i]=b;resid[i]=vals[i]-(past.mean()+b*(n-x.mean()));res_sd[i]=float(np.std(past-fit,ddof=1))
    vol=t['volume'].to_numpy();signed=np.sign(c.diff().fillna(0).to_numpy())
    obv=np.cumsum(signed*np.where(np.isfinite(vol)&(vol>=0),vol,0))
    return {'ema':ema.to_numpy(),'slow':slow.to_numpy(),'mean':mean.to_numpy(),'sd':sd.to_numpy(),
            'kama':kama(c,n).to_numpy(),'cci':cci.to_numpy(),'rsi':rsi.to_numpy(),
            'resid':resid,'res_sd':res_sd,'slope':slope,'obv':obv}


def clock_votes(frame,day,n):
    """Previous sessions' SAME slot returns only; never today's later prices."""
    prior=frame[frame.index.date<day].copy()
    out={}
    for _d,t in prior.groupby(prior.index.date):
        c=t['close'].to_numpy();mins=t.index.hour*60+t.index.minute
        for i in range(len(t)-3):
            if int(mins[i+3]-mins[i])!=15:continue
            out.setdefault(int(mins[i]),[]).append(float(c[i+3]/c[i]-1))
    votes={}
    for minute,values in out.items():
        v=values[-(n//2):]
        if len(v)<5:continue
        sd=float(np.std(v,ddof=1));mean=float(np.mean(v))
        if sd>0 and abs(mean)>sd/np.sqrt(len(v)):votes[minute]=1 if mean>0 else -1
    return votes


def entries(m,f,history=None):
    t,stamps=f['t'],f['stamps'];n=int(m['n']);fam=m['family']
    c,h,l,a,mins=[t[k].to_numpy() for k in ('close','high','low','atr','minute')]
    z=readings(t,n);out={};done=set()
    votes=clock_votes(history,f['day'],n) if fam=='CLOCK_MOMO' and history is not None else {}
    for i in range(max(6,n+1),len(t)):
        end=int(mins[i])+5
        if not 585<=end<=840 or not np.isfinite([a[i],c[i],h[i],l[i]]).all() or a[i]<=0:continue
        # Missing slots/session breaks cannot become an uninterrupted pattern.
        if any(mins[j]-mins[j-1]!=5 for j in range(i-n+1,i+1)):continue
        d=None;stop=target=None
        if fam=='EMA_CROSS':
            v=z['ema']-z['slow'];d=1 if v[i]>0>=v[i-1] else (-1 if v[i]<0<=v[i-1] else None)
        elif fam=='KAMA_TURN':
            k=z['kama'];d=1 if c[i]>k[i] and c[i-1]<=k[i-1] and k[i]>k[i-1] else (-1 if c[i]<k[i] and c[i-1]>=k[i-1] and k[i]<k[i-1] else None)
        elif fam=='DONCHIAN':
            d=1 if c[i]>max(h[i-n:i]) else (-1 if c[i]<min(l[i-n:i]) else None)
        elif fam=='BOLL_REENTRY':
            mean,sd=z['mean'],z['sd']
            d=1 if c[i-1]<mean[i-1]-2*sd[i-1] and c[i]>=mean[i]-2*sd[i] else (-1 if c[i-1]>mean[i-1]+2*sd[i-1] and c[i]<=mean[i]+2*sd[i] else None)
        elif fam=='CCI_REENTRY':
            q=z['cci'];d=1 if q[i-1]<-100<=q[i] else (-1 if q[i-1]>100>=q[i] else None)
        elif fam=='RSI_DIVERGENCE':
            q=z['rsi'];old_low=i-n-1+int(np.argmin(l[i-n-1:i-1]));old_high=i-n-1+int(np.argmax(h[i-n-1:i-1]))
            d=1 if l[i-1]<l[old_low] and q[i-1]>q[old_low] and c[i]>h[i-1] else (-1 if h[i-1]>h[old_high] and q[i-1]<q[old_high] and c[i]<l[i-1] else None)
        elif fam=='REGRESSION_REVERT':
            q,sd=z['resid'],z['res_sd']
            d=1 if q[i-1]<-2*sd[i-1] and q[i]>q[i-1] and c[i]>h[i-1] else (-1 if q[i-1]>2*sd[i-1] and q[i]<q[i-1] and c[i]<l[i-1] else None)
        elif fam=='PDL_RECLAIM':
            d=1 if l[i-1]<f['pdl'] and c[i-1]>f['pdl'] and c[i]>h[i-1] else (-1 if h[i-1]>f['pdh'] and c[i-1]<f['pdh'] and c[i]<l[i-1] else None)
        elif fam=='GAP_REPAIR':
            gap=f['day_open']-f['pdc']
            # Gap has filled, then price resumes the original gap direction.
            d=1 if gap>0 and min(l[:i])<=f['pdc'] and c[i]>f['day_open']>=c[i-1] else (-1 if gap<0 and max(h[:i])>=f['pdc'] and c[i]<f['day_open']<=c[i-1] else None)
        elif fam=='RANGE_RELEASE':
            mean,sd=z['mean'],z['sd'];width=4*sd/np.maximum(abs(mean),1e-9)
            past=width[max(n-1,i-2*n):i]
            finite=past[np.isfinite(past)]
            if len(finite)>=n and width[i-1]<=np.quantile(finite,.25) and width[i]>width[i-1]:
                d=1 if c[i]>max(h[i-n:i]) else (-1 if c[i]<min(l[i-n:i]) else None)
        elif fam=='OBV_BREAK':
            vol=t['volume'].to_numpy();q=z['obv']
            if np.isfinite(vol[i-n:i+1]).all() and min(vol[i-n:i+1])>=0:
                d=1 if c[i]>max(h[i-n:i]) and q[i]>max(q[i-n:i]) else (-1 if c[i]<min(l[i-n:i]) and q[i]<min(q[i-n:i]) else None)
        elif fam=='CLOCK_MOMO':
            d=votes.get(int(mins[i])) if end%30==0 else None
        elif fam=='NULL_ENTRY':
            digest=hashlib.sha256(f"{m['seed']}|{f['day']}|{stamps[i]}".encode()).digest()
            if int.from_bytes(digest[:4],'big')/2**32<.04:d=1 if digest[4]%2 else -1
        else:raise ValueError(fam)
        if d and d not in done:
            risk=m['stop_atr']*a[i]
            out[stamps[i]]=(d,float(c[i]-d*risk),float(c[i]+d*m['target_r']*risk));done.add(d)
    return out


def signal(m,frame,regime,now):
    f=O27F.day_features(frame,now.replace(tzinfo=None).date());bar=O27F.last_closed_bar(f,now) if f else None
    if not f or not bar or not f['complete_open']:return G.MomSignal(bar_ts=bar or '',reject_reason='broad:no_features')
    key=(G.digest(m),f['day'].isoformat(),f['stamps'][-1],len(frame))
    if key not in _CACHE:
        _CACHE[key]=entries(m,f,frame)
        while len(_CACHE)>2000:_CACHE.pop(next(iter(_CACHE)))
    hit=_CACHE[key].get(bar);out=G._signal(frame,regime,now,m,hit[0] if hit else None,bar,f)
    if hit and out.direction is not None:out.stop_underlying,out.target_underlying=hit[1:]
    return out


_previous_signal=G.new_signal
def new_signal(m,frame,regime,now):
    return signal(m,frame,regime,now) if m['family'] in (*FAMILIES,'NULL_ENTRY') else _previous_signal(m,frame,regime,now)
G.new_signal=new_signal

# Main's fitted location rule stays on MAIN members; new families are tested
# on their own entry logic. No application function is changed.
_previous_route=Y.BookReplay.route
def route(self,frame,regime,now):
    if not self.book.get('broad_member_skip'):return _previous_route(self,frame,regime,now)
    limit=self.book.pop('skip',None)
    try:sig=_previous_route(self,frame,regime,now)
    finally:
        if limit is not None:self.book['skip']=limit
    if sig.direction is None:return sig
    m=self.members[self._fired]
    if m.get('kind')=='NAMED' and limit is not None:
        stretch=S.stretch_at(frame,now,sig.direction.value)
        if stretch is not None and stretch>=limit:return G.MomSignal(bar_ts=sig.bar_ts,reject_reason='broad:main_stretched')
    only=self.book.get('broad_direction')
    if m.get('family') in FAMILIES and only and sig.direction.value!=only:return G.MomSignal(bar_ts=sig.bar_ts,reject_reason='broad:direction')
    return sig
Y.BookReplay.route=route


def genomes():
    return {f'{fam}|g{k}':G.new_member(fam,W.CLOSED,n=n,stop_atr=stop,target_r=target,exit=ex)
            for fam in FAMILIES for k,(n,stop,target,ex) in enumerate(GENES)}


def books(phase='screen'):
    if phase=='screen':
        old=W.books()
        out={n:old[n] for n in ('EX|MAIN','RAW|MAIN','RAW|E|tpb_puts')}
        out.update({f'RAW|{n}':P.X.book('O31i|'+n,members=[m],cfg=dict(S.RAW),skip=None,cost=False) for n,m in genomes().items()})
        for seed in range(8):
            m=G.new_member('NULL_ENTRY',W.CLOSED,n=10,seed=seed,stop_atr=1.5,target_r=2.,exit='RUN')
            out[f'NULL|{seed:02d}']=P.X.book(f'O31i|null|{seed}',members=[m],cfg=dict(S.RAW),skip=None,cost=False)
        return out
    chosen=json.loads((HERE/'selection.json').read_text())['selected']
    out={}
    for pick in chosen:
        n,m,d=pick['name'],pick['member'],pick['direction']
        tag={'broad_member_skip':True,'broad_direction':d}
        out['RAW|'+n]=P.X.book('O31i|selected|'+n,members=[m],cfg=dict(S.RAW),skip=None,cost=False,**tag)
        out['EX|'+n]=P.X.book('O31i|combined|'+n,members=[*W.gated(W.OPEN),m],**tag)
    return out


RULE={'screen':'48 predeclared genomes; LOW dailyADX, no inherited stretch on new members; all outcomes retained',
      'selection':'2024+2025 only; BOTH/LONG/SHORT proposals; positive and>=12 trades EACH fitting year; rank minimum annual net/trade; at most6 and1/family; ties lexicographic',
      'raw_pass':'positive every year;>=8/year,>=40total;>=5/6 nonnegative halves; positive without each year best day; weekly t>=2; max-t four-week signflip p<=.05',
      'exact_pass':'better than MAIN every year; paired weekly t>=2; annual fall<=MAIN+.01; zero unresolved',
      'honesty':'all three years seen; folds/subsets only exploratory; no fresh qualification or changes to2023 exam',
      'signflip':{'samples':4096,'block_weeks':4,'seed':310126}}


def bindings():
    b=P.bindings()
    for p in [*HERE.glob('*.py'),*[HERE/n for n in ('PLAN.md','SOURCES.md','configuration.json')]]:b['sources'][p.relative_to(ROOT).as_posix()]=P.sha(p)
    b['prior_results']=P.sha(PRIOR/'results.json')
    return b


def freeze():
    parts={};clean={k:v for k,v in os.environ.items() if k not in ('O30F_YEAR','O30C_YEAR')}
    for y in ('2024','2025','2026'):
        env={**clean,**({'O30F_YEAR':y} if y=='2024' else {'O30C_YEAR':y})}
        raw=subprocess.check_output([sys.executable,__file__,'bindings'],cwd=ROOT,env=env)
        parts[y]=json.loads(raw.decode().strip().splitlines()[-1])
    Y.write_new(HERE/'freeze.json',{'schema':'o31i_broad_v1','bindings':parts,'genomes':genomes(),'books':books(),'rule':RULE,'qualification':'NOT_ASSESSED','can_place_orders':False})


def verify(phase):
    f=json.loads((HERE/'freeze.json').read_text())
    assert f['bindings'][YEAR]==json.loads(json.dumps(bindings(),default=str)),'inputs changed'
    rel=(HERE/'freeze.json').relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(['git','show','HEAD:'+rel],cwd=ROOT))==f,'freeze uncommitted'
    if phase=='selected':
        p=HERE/'selection.json';rel=p.relative_to(ROOT).as_posix()
        assert json.loads(subprocess.check_output(['git','show','HEAD:'+rel],cwd=ROOT))==json.loads(p.read_text()),'selection uncommitted'


def run(jobs,phase):
    assert 1<=jobs<=4
    O27F.deny_network();verify(phase);C.table('year')
    with ProcessPoolExecutor(max_workers=jobs,initializer=L._init) as pool:
        runner=Y.Runner(pool,jobs);runner.run(list(books(phase).values()),source='year',window=C.WINDOW)
    verify(phase)
    P.write(LOCAL/f'keys-{phase}-{YEAR}.json',{n:Y.task_key(b,'year',C.WINDOW) for n,b in books(phase).items()})
    print('DONE',phase,YEAR,len(books(phase)),flush=True)


if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('action',choices=['bindings','freeze','run']);cli.add_argument('--jobs',type=int,default=3);cli.add_argument('--phase',choices=['screen','selected'],default='screen');a=cli.parse_args()
    if a.action=='bindings':print(json.dumps(bindings(),default=str))
    elif a.action=='freeze':freeze()
    else:run(a.jobs,a.phase)
