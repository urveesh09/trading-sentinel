"""Offline multi-session expiry replay on recorded packets, native clocks/fees/depth."""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import importlib.util
import inspect
import json
import logging
import re
import socket
import sqlite3
import sys
import time
from collections import Counter
from datetime import date,datetime,timedelta
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/"python-engine").is_dir())
LOCAL=HERE/"_local"
sys.path[:0]=[str(HERE),str(ROOT/"python-engine")]
from fno_instruments import FnoInstruments
from fno_models import Contract


def denied(*args,**kwargs):
    raise RuntimeError("network is disabled in the expiry study")


def disable_network():
    # Windows asyncio creates its loopback self-pipe BEFORE entering async main.
    socket.socket.connect=denied
    socket.create_connection=denied
logging.disable(logging.CRITICAL)
SOURCE=LOCAL/"export/expiry.sqlite"


def read_db():
    c=sqlite3.connect(SOURCE.resolve().as_uri()+"?mode=ro",uri=True)
    c.row_factory=sqlite3.Row
    return c


def sessions():
    with read_db() as c:
        return [tuple(r) for r in c.execute("select distinct day,underlying from expiry_paper_ticks order by day")]


def module_for(day, historical=False):
    path=LOCAL/"source"/f"expiry-{day}.py" if historical else ROOT/"python-engine/expiry_paper.py"
    name="expiry_e01_"+day.replace("-","")+('_old' if historical else '_current')
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module


def load_session(day,underlying):
    with read_db() as c:
        ticks=[dict(r) for r in c.execute("select * from expiry_paper_ticks where day=? and underlying=? order by ts",(day,underlying))]
        observed=[dict(r) for r in c.execute("select * from expiry_paper_positions where day=? and underlying=? order by id",(day,underlying))]
    for t in ticks:t["quotes"]=json.loads(t["quotes"])
    for p in observed:p["events"]=json.loads(p["events"])
    return ticks,observed


class RecordedMarket:
    def __init__(self,module,adverse=False):
        self.module=module;self.adverse=adverse;self.tick=None;self.calls=0;self.missing=Counter();self.legacy=False

    async def get_quote_by_instruments(self,request):
        self.calls+=1;out={};raw=self.tick["quotes"]
        for token,name in request.items():
            if token<0:
                kind="index" if token==self.module.SPOT_KEY else "future"
                q=raw.get(kind)
                if q is None:  # legacy logged OBSERVED values, not raw index timestamps
                    self.legacy=True;value=self.tick["spot" if kind=="index" else "fut"]
                    if value is not None:out[token]={"last_price":value,"timestamp":self.tick["ts"]}
                elif q.get("status")!="MISSING":
                    out[token]={"last_price":q.get("ltp"),"timestamp":q.get("ts"),"oi":q.get("oi")}
                continue
            symbol=name.split(":",1)[1];q=raw["legs"].get(symbol)
            if q is None:self.missing[symbol]+=1;continue
            if isinstance(q,list):
                bid,bn,ask,an,ltp,stamp=q
                bids,asks=[[bid,bn]],[[ask,an]];oi=None
            else:
                bids,asks,ltp,stamp,oi=q["b"],q["a"],q["ltp"],q["ts"],q.get("oi")
            def levels(rows,buy):
                result=[]
                for price,qty in rows:
                    if price is None:continue
                    new=round(float(price)+(.05 if not buy else -.05),8) if self.adverse else price
                    if new>0:result.append({"price":new,"quantity":qty})
                return result
            out[token]={"last_price":ltp,"timestamp":stamp,"oi":oi,"depth":{"buy":levels(bids,True),"sell":levels(asks,False)}}
        return out


def catalogue(day,u,ticks,observed):
    # Eligibility is limited to the independently recorded instrument-resolved sessions.
    assert (day,u) in sessions()
    sizes={p["lot_size"] for p in observed}
    assert len(sizes)==1, "missing dated lot evidence"
    lot=sizes.pop();tokens={p["symbol"]:p["token"] for p in observed}
    assert lot==({"NIFTY":65,"SENSEX":20}[u])
    contracts=[];names=sorted({n for t in ticks for n in t["quotes"]["legs"]})
    for i,name in enumerate(names):
        match=re.search(r"(\d{5})(CE|PE)$",name)
        assert match and name.startswith(u),(day,name)
        contracts.append(Contract(tokens.get(name,100000000+i),name,u,date.fromisoformat(day),float(match[1]),match[2],lot))
    contracts.append(Contract(99999999,f"{u}_ARCHIVED_FUTURE",u,date(2026,11,30),0,"FUT",lot,.1))
    exchange="NFO" if u=="NIFTY" else "BFO"
    book=FnoInstruments(underlying=u,segment=exchange,json_path=str(LOCAL/"unused.json"))
    book._load_contracts(contracts);book.refreshed_on=date.fromisoformat(day)
    return book,exchange


def totals(rows):
    result={}
    for p in rows:
        item=result.setdefault(p["play"],dict(entries=set(),legs=0,filled_event_net=0.,assumed_net=0.,unresolved=0,open=0))
        item["entries"].add(p["entry_ts"]);item["legs"]+=1;item["filled_event_net"]+=p["net_pnl"]
        item["assumed_net"]+=p.get("assumed_pnl") or 0.;item["unresolved"]+=p["status"]=="UNRESOLVED";item["open"]+=p["status"]=="OPEN"
    for r in result.values():
        r["entries"]=len(r["entries"]);r["modeled_net"]=round(r["filled_event_net"]+r["assumed_net"],2)
        r["filled_event_net"]=round(r["filled_event_net"],2);r["assumed_net"]=round(r["assumed_net"],2)
    return result


async def run_one(day,u,policy="BASE",historical=False,adverse=False,patch=None):
    label=f"{day}-{u}-{'HISTORY-v3' if historical else policy}-{'adverse' if adverse else 'ordinary'}"
    target=LOCAL/"evals"/f"{label}.json"
    assert not target.exists(),f"preserve earlier run {target}"
    target.parent.mkdir(exist_ok=True)
    module=module_for(day,historical)
    if patch:patch(module,policy)
    ticks,observed=load_session(day,u);market=RecordedMarket(module,adverse)
    book,exchange=catalogue(day,u,ticks,observed)
    base=LOCAL/"books"/label;base.parent.mkdir(exist_ok=True)
    path=module.expiry_db_path(str(base));assert not Path(path).exists()
    started=time.monotonic()
    has_clock="clock" in inspect.signature(module._tick_underlying).parameters
    # One scratch transaction is faster than opening/fsyncing the same private DB every tick.
    # It does not model crash durability; native persistence tests cover that independently.
    with module._store(path) as c:
        for t in ticks:
            market.tick=t;now=datetime.fromisoformat(t["ts"])
            begin=datetime.fromisoformat(t["quotes"].get("started",t["ts"]))
            if has_clock:
                await module._tick_underlying(market,c,book,u,exchange,begin,lambda now=now:now)
            else:
                await module._tick_underlying(market,c,book,u,exchange,now)
    settlements=[e["ts"] for p in observed for e in p["events"] if e.get("action") in ("SETTLED_ASSUMED","UNRESOLVED")]
    reconcile_at=datetime.fromisoformat(max(settlements) if settlements else day+"T15:45:00+05:30")
    module.reconcile(str(base),reconcile_at)
    with sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro",uri=True) as c:
        c.row_factory=sqlite3.Row
        positions=[dict(r) for r in c.execute("select * from expiry_paper_positions order by id")]
        state=json.loads(c.execute("select state from expiry_paper_days where day=? and underlying=?",(day,u)).fetchone()[0])
    for p in positions:p["events"]=json.loads(p["events"])
    byplay=totals(positions)
    primary={k:round(sum(byplay.get(p,{}).get(k,0) for p in ("A","B","C")),2) for k in ("filled_event_net","assumed_net","modeled_net","unresolved","open")}
    result=dict(day=day,underlying=u,policy=policy,historical=historical,adverse=adverse,primary=primary,by_play=byplay,
                positions=positions,state=state,ticks=len(ticks),provider_calls=market.calls,legacy_index_clock=market.legacy,
                missing_requested=dict(market.missing),seconds=round(time.monotonic()-started,3),external_network=False,orders=0,
                raw_source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),rules=module.RULES_VERSION,
                execution=getattr(module,"EXECUTION_VERSION","legacy-unversioned"),limitations=["recorded catalogue only; synthetic IDs for untraded contracts",
                 "auction-window fills unverified; residual values assumed, never broker cash","eight already-seen sessions, not profitability proof"])
    if historical:
        key=lambda p:(p["play"],p["symbol"],p["entry_ts"],p.get("side","LONG"))
        a,b={key(p):p for p in positions},{key(p):p for p in observed}
        fields=("lots","lots_open","entry_price","max_loss","peak","stop","banked","exit_pending","status","gross","costs","net_pnl","assumed_pnl","bank_pending","events")
        mismatch=[dict(key=k,field=f,replay=a.get(k,{}).get(f),observed=b.get(k,{}).get(f)) for k in a.keys()|b.keys() for f in fields if a.get(k,{}).get(f)!=b.get(k,{}).get(f)]
        result["historical_parity"]={"passed":not mismatch,"mismatches":mismatch,"observed_positions":len(observed)}
    target.write_text(json.dumps(result,indent=1,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("day","underlying","policy","historical","primary","seconds")}|{"parity":result.get("historical_parity",{}).get("passed")}),flush=True)
    return result


async def main():
    disable_network()
    cli=argparse.ArgumentParser();cli.add_argument("phase",choices=("history","controls"));cli.add_argument("--day")
    args=cli.parse_args()
    for day,u in sessions():
        if args.day and day!=args.day:continue
        await run_one(day,u,historical=args.phase=="history")


if __name__=="__main__":
    asyncio.run(main())
