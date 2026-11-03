"""Selected expiry OHLC only. 2024 prices are inaccessible to development code."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timedelta
from pathlib import Path
import hashlib,json,sqlite3,sys,pickle
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'python-engine').is_dir())
LOCAL=HERE/'_local'
SOURCE=HERE.parent/'2026-11-02-expiry-e02/_local/data.sqlite'
sys.path.insert(0,str(ROOT/'python-engine'))
import expiry_paper as EP


def dump(path,obj):
    path.write_text(json.dumps(obj,indent=2,default=str,allow_nan=False)+'\n',encoding='utf-8')


def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        while chunk:=f.read(1024*1024):h.update(chunk)
    return h.hexdigest()


def snapshot():
    LOCAL.mkdir(exist_ok=True)
    assert not (HERE/'dataset.json').exists()
    manifest={}
    for year in (2025,2024):
        dst=LOCAL/f'{year}.sqlite';assert not dst.exists()
        a=sqlite3.connect(SOURCE.resolve().as_uri()+'?mode=ro',uri=True)
        b=sqlite3.connect(dst)
        b.execute('CREATE TABLE candles(kind TEXT,expiry TEXT,strike REAL,opt TEXT,datetime TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,oi REAL)')
        cursor=a.execute('SELECT * FROM candles WHERE datetime>=? AND datetime<?',(f'{year}-01-01',f'{year+1}-01-01'))
        while rows:=cursor.fetchmany(5000):b.executemany('INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?)',rows)
        b.execute('CREATE INDEX stamp ON candles(datetime)');b.commit()
        counts=b.execute('SELECT kind,count(*),count(distinct substr(datetime,1,10)),min(datetime),max(datetime) FROM candles GROUP BY kind').fetchall()
        assert b.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        b.close();a.close()
        manifest[str(year)]=dict(rows=counts,sha256=sha(dst),role='development_seen' if year==2025 else 'reserved_expiry_path_exam',prices_printed=False)
        print('SNAPSHOT_METADATA',year,counts,flush=True)
    dump(HERE/'dataset.json',dict(years=manifest,source=str(SOURCE),source_writes=0,api_calls=0,year2023_read=False))


@dataclass
class Tape:
    day:str
    x:np.ndarray                 # index O/H/L/C
    f:np.ndarray                 # independent future O/H/L/C
    q:np.ndarray                 # [minute, contract, O/H/L/C/volume]
    strikes:np.ndarray
    kinds:np.ndarray             # +1 CE, -1 PE
    symbols:list
    now:list
    minute:np.ndarray
    invalid:int

    def __post_init__(self):
        self.n=len(self.x)
        self.close=self.x[:,3]
        self.features={}
        for look in (5,10,20,30):
            out=np.full((self.n,8),np.nan)
            for i in range(look,self.n):
                prev=self.x[i-look:i];fv=self.f[i-look:i]
                closes=self.close[i-look:i+1]
                if not np.isfinite(prev).all() or not np.isfinite(fv).all() or not np.isfinite(closes).all():continue
                path=np.abs(np.diff(closes)).sum()
                tr=np.maximum(prev[:,1]-prev[:,2],np.maximum(np.abs(prev[:,1]-self.close[i-look-1:i-1]) if i>look else prev[:,1]-prev[:,2],np.abs(prev[:,2]-self.close[i-look-1:i-1]) if i>look else prev[:,1]-prev[:,2]))
                atr=float(np.mean(tr))
                if atr<=0:continue
                out[i]=[np.max(prev[:,1]),np.min(prev[:,2]),(closes[-1]-closes[0])/path if path else 0.,
                        np.mean(prev[:,3]),atr,np.std(prev[:,3]),np.max(fv[:,1]),np.min(fv[:,2])]
            self.features[look]=out
        # Frozen native sampled-close 13:00-13:30 box, minute proxy.
        mask=(self.minute>=780)&(self.minute<810)
        self.box=(float(np.max(self.close[mask])),float(np.min(self.close[mask])),float(np.max(self.f[mask,3])),float(np.min(self.f[mask,3]))) if np.isfinite(self.close[mask]).all() and np.isfinite(self.f[mask,3]).all() else None


def load_year(year,*,exam=False):
    if year!=2025:
        assert year==2024 and exam,'Reserved 2024 is only opened by the frozen final exam'
        from search import verify_freeze
        verify_freeze()
    cache=LOCAL/f'tapes-{year}-{sha(Path(__file__))[:12]}.pkl'
    if cache.exists():return pickle.loads(cache.read_bytes())
    c=sqlite3.connect((LOCAL/f'{year}.sqlite').as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    days=[r[0] for r in c.execute('SELECT DISTINCT substr(datetime,1,10) FROM candles ORDER BY 1')]
    tapes=[];coverage=[]
    for day in days:
        rows=c.execute('SELECT * FROM candles WHERE datetime BETWEEN ? AND ? ORDER BY datetime',(day+' 09:15:00',day+' 15:29:00')).fetchall()
        opts=sorted({(r['strike'],r['opt']) for r in rows if r['kind']=='option'})
        lookup={v:j for j,v in enumerate(opts)}
        x=np.full((375,4),np.nan);f=x.copy();q=np.full((375,len(opts),5),np.nan);bad=0
        for r in rows:
            k=(int(r['datetime'][11:13])-9)*60+int(r['datetime'][14:16])-15
            if not 0<=k<375:continue
            vals=[r[n] for n in ('open','high','low','close')]
            if not all(v is not None and np.isfinite(v) and v>0 for v in vals) or not vals[2]<=min(vals[0],vals[3])<=max(vals[0],vals[3])<=vals[1]:bad+=1;continue
            if r['kind']=='index':x[k]=vals
            elif r['kind']=='future':f[k]=vals
            elif r['kind']=='option':
                assert r['expiry']==day
                if r['volume'] is None or r['volume']<0:bad+=1;continue
                q[k,lookup[r['strike'],r['opt']]]=vals+[r['volume']]
        now=[datetime.fromisoformat(day+'T09:15:00').replace(tzinfo=EP.IST)+timedelta(minutes=i+1) for i in range(375)]
        tapes.append(Tape(day,x,f,q,np.array([k for k,o in opts]),np.array([1 if o=='CE' else -1 for k,o in opts]),[f'NIFTY-{day}-{k:g}-{o}' for k,o in opts],now,np.arange(556,931),bad))
        coverage.append(dict(day=day,contracts=len(opts),invalid_rows=bad,index_points=int(np.isfinite(x[:,3]).sum()),future_points=int(np.isfinite(f[:,3]).sum())))
    c.close();cache.write_bytes(pickle.dumps(tapes))
    dump(HERE/f'coverage-{year}.json',coverage)
    return tapes


if __name__=='__main__':snapshot()
