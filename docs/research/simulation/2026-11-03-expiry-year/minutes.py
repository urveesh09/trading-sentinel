"""Separate NIFTY 2025 C book proxy on the wider minute archive.

Two completed minute observations replace two ten-second confirmations. This
cannot establish native timing. Independent index/front future are available.
No pre-2025 rows or price outcomes are read, including from the source snapshot.
"""
import argparse
from collections import defaultdict
from datetime import datetime,time,timedelta,date
import json
from pathlib import Path
import sqlite3

import study as S
from candidates import CANDIDATES,MANAGERS


def snapshot():
    src=S.HERE.parent/"2026-11-02-expiry-e02/_local/data.sqlite"
    dst=S.LOCAL/"minutes.sqlite"
    assert not dst.exists()
    a=sqlite3.connect(src.resolve().as_uri()+"?mode=ro",uri=True)
    b=sqlite3.connect(dst)
    b.execute("CREATE TABLE candles(kind TEXT,expiry TEXT,strike REAL,opt TEXT,datetime TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,oi REAL)")
    # The bounds apply in SQL, so 2023/2024 evidence is never read into this job.
    cursor=a.execute("SELECT * FROM candles WHERE datetime>='2025-01-01' AND datetime<'2026-01-01'")
    while batch:=cursor.fetchmany(5000):
        b.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?)",batch)
    b.execute("CREATE INDEX by_day ON candles(datetime)")
    b.commit()
    counts=b.execute("SELECT kind,count(*),count(distinct substr(datetime,1,10)),min(datetime),max(datetime) FROM candles GROUP BY kind").fetchall()
    assert b.execute("PRAGMA quick_check").fetchone()[0]=="ok"
    b.close();a.close()
    S.dump(S.HERE/"minute-coverage.json",dict(counts=counts,sha256=S.sha(dst),source=str(src),
        scope="NIFTY 2025 only; current normalized lot65/fees; recorded chain, minute timing proxy; A/B not scored"))
    print("MINUTE_METADATA",counts)


class Minute(S.Session):
    seconds=60
    flat=time(15,28)

    def __init__(self,day):
        self.day=day;self.underlying="NIFTY";self.date=date.fromisoformat(day)
        self.info={"window":"test2025-minute-proxy"}
        self.exchange="NFO";self.schedule=S.EP.fee_schedule("NFO");self.step=50.;self.lot=65
        self.p75=json.loads((S.OLD/"spreads.json").read_text())["p75"]
        c=sqlite3.connect((S.LOCAL/"minutes.sqlite").as_uri()+"?mode=ro",uri=True)
        c.row_factory=sqlite3.Row
        rows=c.execute("SELECT * FROM candles WHERE datetime BETWEEN ? AND ? ORDER BY datetime",(day+" 12:59:00",day+" 15:29:00")).fetchall()
        c.close()
        by_stamp=defaultdict(dict);index={};future={};contracts={};self.invalid_rows=0
        for r in rows:
            stamp=r["datetime"]
            vals=[r[k] for k in ("open","high","low","close")]
            valid=all(v is not None and v>0 for v in vals) and r["low"]<=min(r["open"],r["close"])<=max(r["open"],r["close"])<=r["high"]
            if not valid or (r["kind"]=="option" and (r["volume"] is None or r["volume"]<0)):
                self.invalid_rows+=1;continue
            if r["kind"]=="index":index[stamp]=r["close"]
            elif r["kind"]=="future":future[stamp]=r["close"]
            elif r["kind"]=="option":
                assert r["expiry"]==day
                name=f"NIFTY-{day}-{r['strike']:g}-{r['opt']}"
                if name not in contracts:
                    contracts[name]=S.L.Contract(300000000+len(contracts),name,"NIFTY",self.date,r["strike"],r["opt"],65)
                by_stamp[stamp][name]=dict(r)
        stamps=[(datetime.fromisoformat(day+" 12:59:00")+timedelta(minutes=i)).isoformat(sep=" ") for i in range(151)]
        self.now=[datetime.fromisoformat(t).replace(tzinfo=S.EP.IST)+timedelta(minutes=1) for t in stamps]
        self.clock=[t.time() for t in self.now];self.n=len(stamps)
        self.spot=[index.get(t) for t in stamps];self.fut=[future.get(t) for t in stamps]
        self.anchor=[self.spot[max(0,i-1)] for i in range(self.n)]
        self._bars=[by_stamp[t] for t in stamps];self.names=sorted(contracts)
        self._contract=contracts;self.kinds={n:n for n in self.names}
        self._signals={}

    def contracts_near(self,i):
        anchor=self.anchor[i]
        if anchor is None:return {}
        atm=self.atm(anchor)
        return {(c.strike,c.instrument_type):c for c in self._contract.values() if abs(c.strike-atm)<=8*self.step}

    def quoted_chain(self,i):
        return {k:(c,self.quote(i,c.tradingsymbol)) for k,c in self.contracts_near(i).items() if self.quote(i,c.tradingsymbol) is not None}


def signals(x):
    saved=S.EP.CONFIRM_MAX_GAP_SEC
    try:
        S.EP.CONFIRM_MAX_GAP_SEC=65.
        return S.L.signal_stream(x)
    finally:
        S.EP.CONFIRM_MAX_GAP_SEC=saved


def run():
    S.no_network();S.verify_freeze()
    target=S.HERE/"results-minute2025.json"
    assert not target.exists()
    c=sqlite3.connect((S.LOCAL/"minutes.sqlite").as_uri()+"?mode=ro",uri=True)
    days=[r[0] for r in c.execute("SELECT DISTINCT substr(datetime,1,10) FROM candles ORDER BY 1")];c.close()
    arms={**S.FIXED,**CANDIDATES}
    out={n:{s:[] for s in ("ordinary","adverse")} for n in arms}
    availability=[]
    for day in days:
        x=Minute(day);state,fire=signals(x)
        audit=dict(day=day,box_status=state["box_status"],signals=len(fire),invalid_rows=x.invalid_rows,
                   minute_index_points=sum(v is not None for v in x.spot),minute_future_points=sum(v is not None for v in x.fut),
                   symbol_count=len(x.names),recorded_chain_entry="PARTIAL",arms={})
        for name,ticket in arms.items():
            for scenario,adverse in (("ordinary",False),("adverse",True)):
                attempts=0;filled=None
                for i,d in fire:
                    box=state["box"]
                    if ticket.box_max_bp is not None and (box["hi"]-box["lo"])/box["hi"]*1e4>ticket.box_max_bp:continue
                    strike=S.L._pick(x,i,d,ticket)
                    if strike is None:continue
                    kind="CE" if d=="UP" else "PE"
                    contract,q=x.quoted_chain(i)[(strike,kind)]
                    attempts+=1
                    filled=S.simulate(x,(i,contract.tradingsymbol,"RECORDED_CHAIN_BREAK"),ticket,adverse,
                                      failed_back=True,manager_override=MANAGERS.get(name))
                    if filled:
                        S.audit_position(filled);out[name][scenario].append(filled);break
                audit["arms"][f"{name}|{scenario}"]=dict(attempts=attempts,filled=filled is not None,
                    status="FILLED_PROXY" if filled else "NO_RECORDED_CHAIN_FILL_OR_FILTERED")
        availability.append(audit)
        print("MINUTE2025",day,"breaks",len(fire),"E011",audit["arms"]["E011|ordinary"]["status"],flush=True)
    summary={n:{s:S.stats(p) for s,p in scenarios.items()} for n,scenarios in out.items()}
    # Exit-only arms must remain matched to E011 even with different stop rules.
    for name in ("C","E01","E011R","E011_S20",*CANDIDATES):
        for scenario in ("ordinary","adverse"):
            sig=lambda p:(p["day"],p["symbol"],p["entry_ts"],p["entry_price"],p["lots"],p["max_loss"])
            assert [sig(p) for p in out[name][scenario]]==[sig(p) for p in out["E011"][scenario]]
    S.dump(target,dict(model="RECORDED_CHAIN_MINUTE_C_PROXY_v1",summaries=summary,availability=availability,positions=out))
    print(json.dumps({n:summary[n] for n in ("E01","E011",*CANDIDATES)},indent=1))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("command",choices=("snapshot","run"));a=p.parse_args()
    snapshot() if a.command=="snapshot" else run()
