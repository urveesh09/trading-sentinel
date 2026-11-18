"""Explicit read-only OI panels. No year inference for forward sessions, no network."""
from pathlib import Path
from dataclasses import dataclass
import hashlib, json, sqlite3, sys
import numpy as np

HERE=Path(__file__).resolve().parent
R7=HERE.parent/'2026-11-18-expiry-en71'
sys.path.insert(0,str(R7))
import en_lab7 as L7

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

@dataclass(frozen=True)
class Source:
    path: Path
    oi_available: bool
    identity: str

def read_panel(t,source):
    """A supplied snapshot, any year; zero is valid only for an OI-capable source."""
    out=np.full((t.n,len(t.strikes)),np.nan)
    if not source.oi_available: return out
    con=sqlite3.connect(source.path.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        cols={r[1] for r in con.execute('PRAGMA table_info(candles)')}
        sql="SELECT strike,opt,datetime,oi FROM candles WHERE kind='option' AND expiry=? AND datetime BETWEEN ? AND ?"
        args=[t.day,t.day+' 09:15:00',t.day+' 15:29:00']
        if 'underlying' in cols: sql+=' AND underlying=?'; args.append(getattr(t,'und','NIFTY'))
        if 'interval' in cols: sql+=" AND interval='1minute'"
        sql+=' ORDER BY datetime,strike,opt'
        lookup={(float(k),'CE' if d==1 else 'PE'):j for j,(k,d) in enumerate(zip(t.strikes,t.kinds))}
        for K,side,dt,value in con.execute(sql,args):
            j=lookup.get((float(K),side)); i=(int(dt[11:13])-9)*60+int(dt[14:16])-15
            if j is None or not 0<=i<t.n or value is None or not np.isfinite(value) or value<0: continue
            if np.isfinite(out[i,j]) and out[i,j]!=value: raise ValueError('conflicting OI observations')
            out[i,j]=value
    finally: con.close()
    out.flags.writeable=False
    return out

def attach(t,source):
    t.oi8=read_panel(t,source); t.oi_source8=dict(path=str(source.path),identity=source.identity,available=source.oi_available)
    return t

def historical_books():
    import prep7
    L7.L5.install(); B=L7.L6.books(); bindings={}
    for und,book in B.items():
        for t in book:
            p=prep7.SEALED[t.day[:4]]
            key=str(p.resolve())
            if key not in bindings: bindings[key]=sha(p)
            attach(t,Source(p,und=='NIFTY',bindings[key]))
    return B,bindings

def basket(t,i,anchor=None):
    k=i if anchor is None else anchor
    if k<0 or not np.isfinite(t.close[k]): return []
    sp=L7.L4.spec_of(t); atm=round(float(t.close[k])/sp.step)*sp.step
    lookup={(float(K),int(d)):j for j,(K,d) in enumerate(zip(t.strikes,t.kinds))}
    return [(lookup[(atm+off*sp.step,1)],lookup[(atm+off*sp.step,-1)])
            for off in (-2,-1,0,1,2) if (atm+off*sp.step,1) in lookup and (atm+off*sp.step,-1) in lookup]

def components(t,i,pairs=None):
    if i<15: return (np.nan,np.nan,np.nan,0)
    oi=t.oi8; pairs=basket(t,i) if pairs is None else pairs
    den=up=dn=0.; valid=0
    for c,p in pairs:
        c0,ct,p0,pt=oi[i-15,c],oi[i,c],oi[i-15,p],oi[i,p]
        if not np.isfinite([c0,ct,p0,pt]).all(): continue
        den+=c0+p0; up+=max(c0-ct,0)-max(p0-pt,0); dn+=max(pt-p0,0)-max(ct-c0,0); valid+=1
    if valid<3 or den<=0: return (np.nan,np.nan,np.nan,valid)
    u,d=up/den,dn/den
    return (u+d,u,d,valid)

def oi_series(t,lag_anchor=False):
    a=np.full((t.n,4),np.nan)
    for i in range(15,t.n): a[i]=components(t,i,basket(t,i,i-15) if lag_anchor else None)
    return a

def sealed_manifest(B,bindings):
    return dict(files=bindings,sessions={u:[t.day for t in b] for u,b in B.items()},
                oi_capability={'NIFTY':True,'SENSEX':False},
                interval='1minute',fidelity='BAR_LIFECYCLE',lots='present-policy normalization')
