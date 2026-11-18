"""Versioned local forward infrastructure. No acquisition, scheduler, broker or old ledger writes."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import json,hashlib,sqlite3
from contextlib import contextmanager
from data8 import L7,Source,attach

IST=timezone(timedelta(hours=5,minutes=30))

def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(x):return hashlib.sha256(canonical(x).encode()).hexdigest()

class Ledger:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS receipts(
                policy TEXT NOT NULL, underlying TEXT NOT NULL, day TEXT NOT NULL,
                status TEXT NOT NULL, body TEXT NOT NULL, hash TEXT NOT NULL,
                PRIMARY KEY(policy,underlying,day));
                CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY,policy TEXT,underlying TEXT,
                day TEXT,status TEXT,body TEXT);
                CREATE TABLE IF NOT EXISTS leases(policy TEXT,underlying TEXT,day TEXT,
                owner TEXT,until REAL,PRIMARY KEY(policy,underlying,day));''')
    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.path,timeout=30,isolation_level=None)
        try:
            c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA synchronous=FULL')
            yield c
        finally:c.close()
    def claim(self,key,owner,now,ttl=600):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT 1 FROM receipts WHERE policy=? AND underlying=? AND day=?',key).fetchone():c.rollback();return False
            row=c.execute('SELECT until FROM leases WHERE policy=? AND underlying=? AND day=?',key).fetchone()
            if row and row[0]>now:c.rollback();return False
            c.execute('INSERT OR REPLACE INTO leases VALUES (?,?,?,?,?)',(*key,owner,now+ttl));c.commit();return True
    def record(self,key,status,body,owner=None):
        assert status in ('PENDING','MISSING','ELIGIBLE','SENSITIVITY')
        text=canonical(body);h=digest(body)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if status in ('PENDING','SENSITIVITY'):
                c.execute('INSERT INTO attempts(policy,underlying,day,status,body) VALUES(?,?,?,?,?)',(*key,status,text));c.commit();return 'ATTEMPT'
            old=c.execute('SELECT status,hash FROM receipts WHERE policy=? AND underlying=? AND day=?',key).fetchone()
            if old:
                c.rollback()
                if old!=(status,h):raise ValueError('immutable receipt conflict; append a sensitivity instead')
                return 'EXISTS'
            lease=c.execute('SELECT owner FROM leases WHERE policy=? AND underlying=? AND day=?',key).fetchone()
            if owner is not None and (lease is None or lease[0]!=owner):c.rollback();raise ValueError('lease owner mismatch')
            c.execute('INSERT INTO receipts VALUES(?,?,?,?,?,?)',(*key,status,text,h))
            c.execute('DELETE FROM leases WHERE policy=? AND underlying=? AND day=?',key);c.commit();return 'INSERTED'
    def rows(self):
        with self.connect() as c:return [dict(policy=p,underlying=u,day=d,status=s,body=json.loads(b),hash=h)
            for p,u,d,s,b,h in c.execute('SELECT * FROM receipts ORDER BY day,underlying,policy')]

def due(calendar,now,cohort_start):
    """Explicit dated entries with source and close, not expiries inferred from options present."""
    if not calendar.get('source') or not calendar.get('verified_through'):raise ValueError('dated calendar proof required')
    if now.tzinfo is None:raise ValueError('timezone-aware now required')
    return [x for x in calendar['sessions'] if cohort_start[x['underlying']]<=x['day']<=calendar['verified_through']
            and datetime.fromisoformat(x['day']+'T'+x.get('close','15:30:00')).replace(tzinfo=IST)<=now]

def coverage(snapshot,underlying,day,need_oi=False):
    """Strict required window sets on the actual nearest dated contract, not summed series."""
    c=sqlite3.connect(Path(snapshot).resolve().as_uri()+'?mode=ro',uri=True)
    try:
        front=c.execute("SELECT MIN(expiry) FROM candles WHERE kind='future' AND underlying=? AND expiry>=? AND interval='1minute' AND datetime BETWEEN ? AND ?",
                        (underlying,day,day+' 09:15:00',day+' 15:29:00')).fetchone()[0]
        required={f'{m//60:02d}:{m%60:02d}:00' for m in range(720,915)} # noon warmup through flat/retry window
        missing=[]
        for kind,exp in [('index',None),('future',front)]:
            if kind=='future' and front is None:missing.append('front contract absent');continue
            sql="SELECT datetime,open,high,low,close FROM candles WHERE kind=? AND underlying=? AND interval='1minute' AND datetime BETWEEN ? AND ?"
            args=[kind,underlying,day+' 12:00:00',day+' 15:14:00']
            if exp:sql+=' AND expiry=?';args.append(exp)
            good={dt[11:] for dt,o,h,l,cl in c.execute(sql,args) if all(v is not None and v>0 for v in (o,h,l,cl)) and l<=min(o,cl)<=max(o,cl)<=h}
            gap=sorted(required-good)
            if gap:missing.append(dict(kind=kind,missing=len(gap),first=gap[:3]))
        # Build actual tape: it carries warmup and the chain; enforce both option sides at each decision.
        tape=build_tape(snapshot,underlying,day,front)
        available=[]
        for i in range(tape.n):
            if 780<=tape.minute[i]<870:
                import numpy as np
                ok=np.isfinite(tape.close[i]) and all(L7.L4.available(tape,i,d) for d in (-1,1))
                available.append(ok)
        if len(available)!=90 or not all(available):missing.append('option strike-side decision coverage incomplete')
        if need_oi:
            from data8 import oi_series
            import numpy as np
            valid=oi_series(tape)[:,0];win=(tape.minute>=780)&(tape.minute<870)
            if not np.isfinite(valid[win]).all():missing.append('OI decision endpoints incomplete')
        return dict(eligible=not missing,missing=missing,front=front,tape=tape)
    finally:c.close()

def build_tape(snapshot,underlying,day,front=None):
    c=sqlite3.connect(Path(snapshot).resolve().as_uri()+'?mode=ro',uri=True)
    m=sqlite3.connect(':memory:');m.row_factory=sqlite3.Row
    try:
        if front is None:front=c.execute("SELECT MIN(expiry) FROM candles WHERE kind='future' AND underlying=? AND expiry>=? AND interval='1minute' AND datetime BETWEEN ? AND ?",
            (underlying,day,day+' 09:15:00',day+' 15:29:00')).fetchone()[0]
        m.execute('CREATE TABLE candles(kind TEXT,underlying TEXT,expiry TEXT,strike REAL,opt TEXT,datetime TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,oi REAL)')
        rows=c.execute("SELECT kind,underlying,expiry,strike,opt,datetime,open,high,low,close,volume,oi FROM candles WHERE underlying=? AND interval='1minute' AND datetime BETWEEN ? AND ? AND (kind='index' OR (kind='future' AND expiry=?) OR (kind='option' AND expiry=?))",
                       (underlying,day+' 09:15:00',day+' 15:29:00',front,day)).fetchall()
        m.executemany('INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',rows)
        t=L7.D4.build(m,underlying,day,L7.D4._D())
        from data8 import sha
        return attach(t,Source(Path(snapshot),underlying=='NIFTY',sha(snapshot)))
    finally:c.close();m.close()

def record_availability(ledger,key,coverage_result,now,body):
    close=datetime.fromisoformat(key[2]+'T15:30:00').replace(tzinfo=IST)
    if now<close:raise ValueError('unfinished session')
    status='PENDING' if now<close+timedelta(hours=48) else 'MISSING'
    if coverage_result['eligible']:return 'READY'
    ledger.record(key,status,dict(body,missing=coverage_result['missing']))
    return status

def review(ledger,policies,baseline='E03_env'):
    import stats8
    out={}
    rows=ledger.rows()
    for und in ('NIFTY','SENSEX'):
        for policy in policies:
            use=[r for r in rows if r['underlying']==und and r['policy']==policy and r['status']=='ELIGIBLE']
            base={r['day']:r for r in rows if r['underlying']==und and r['policy']==baseline and r['status']=='ELIGIBLE'}
            paired=[r for r in use if r['day'] in base]
            item=dict(eligible=len(use),missing=sum(r['underlying']==und and r['policy']==policy and r['status']=='MISSING' for r in rows),
                      review_due=len(use)>=40,support=sum(r['body']['ordinary']['trades'] for r in use),
                      net={sc:round(sum(r['body'][sc]['net'] for r in use),2) for sc in ('ordinary','adverse')})
            if paired:
                item['paired']=stats8.infer([r['day'] for r in paired],[r['body']['ordinary']['net']-base[r['day']]['body']['ordinary']['net'] for r in paired])
            item['verdict']='REVIEW REQUIRED; no automatic promotion'
            out[policy+'|'+und]=item
    return out
