"""Attribute saved N11 controls to signal, option and underlying economics."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
DOCS = HERE.parents[2]
PREV = HERE.parent / "2026-11-05-fno-expiry-followup"
OLD = HERE.parent / "2026-11-02-fno-n11-tolerance" / "_local"
FNO = DOCS / "research/fno"
DATASETS = {
    "2022": PREV / "_local/nifty-2022/dataset",
    "2023": HERE.parent / "2026-11-01-fno-n08/_local/dataset-nifty-2023",
    "2024": FNO / "2026-10-30-day-router/_local/dataset-nifty-2024",
    "2025": FNO / "2026-10-30-nifty-2025-test/_local/dataset-nifty-2025",
    "2026": FNO / "2026-10-29-year-genome/_local/dataset-nifty",
}


def read(path):
    return json.loads(path.read_bytes())


def trades(year, label):
    if year == "2022":
        aliases = {"N11": "N11|T|BASE", "N11T": "N11T|F|FINAL", "DIAG": "N09|DIAG|N08_ONE_NOBRAKE"}
        for path in (PREV / "_local/nifty-2022/evals").glob("*.json"):
            data = read(path)
            if data["book"]["label"] == aliases[label]:
                return path, data
        raise FileNotFoundError(label)
    keys = read(OLD / f"keys-fpanel-{year}.json")
    path = OLD / "evals" / f"{keys['FINAL' if label=='N11T' else 'N11']}.json"
    return path, read(path)


def window(con, kind, expiry, day, strike=0.0, opt=""):
    return con.execute("""select datetime,open,high,low,close,volume from candles
        where kind=? and expiry=? and strike=? and opt=? and datetime>=? and datetime<?
        order by datetime""", (kind,expiry,strike,opt,day,day+"z")).fetchall()


def describe(t, fut, opt):
    ent=t["entry_time"][:16].replace("T"," ")+":00"
    end=t["exit_time"][:16].replace("T"," ")+":00"
    sign=1 if t["direction"]=="LONG" else -1
    future=float(t["entry_underlying"])
    risk=abs(future-t["stop_underlying"])
    prior=[r for r in fut if r[0]<=ent]
    held=[r for r in fut if ent<=r[0]<=end]
    after=[r for r in fut if ent<r[0]<=t["entry_time"][:10]+" 15:10:00"]
    opts=[r for r in opt if ent<=r[0]<=end and r[4]>0]
    # Minute closes, rather than OHLC extremes, avoid assigning an intra-minute sequence.
    closed=[r for r in prior if r[0][:16] < ent[:16]]
    recent=closed[-30:]
    weight=sum(max(r[5] or 0,0) for r in closed)
    vwap=sum(max(r[5] or 0,0)*(r[2]+r[3]+r[4])/3 for r in closed)/weight if weight else None
    path=[sign*(r[4]-future)/risk for r in held] if risk else []
    after_path=[sign*(r[4]-future)/risk for r in after] if risk else []
    last_close=closed[-1][4] if closed else None
    first=[r for r in closed if r[0][11:16]<"09:45"]
    travel=sum(abs(b[4]-a[4]) for a,b in zip(recent,recent[1:]))
    er=sign*(recent[-1][4]-recent[0][4])/travel if travel else None
    open_reach=sign*(last_close-first[0][1])/risk if first and risk else None
    relative=sign*(last_close-vwap)/risk if vwap is not None and risk else None
    return dict(entry=t["entry_time"],exit=t["exit_time"],member=t.get("entry_expert"),
                gate=t.get("entry_gate"),side=t["direction"],quantity=t["entry_qty"],symbol=t["tradingsymbol"],
                gross=t["gross_pnl"],net=t["net_pnl"],charges_and_stress=round(t["gross_pnl"]-t["net_pnl"],4),
                exit_reason=t["exit_reason"],risk=risk,
                favorable_r=round(max([0.]+path),4),adverse_r=round(min([0.]+path),4),
                favorable_through_flat_r=round(max([0.]+after_path),4),
                favorable_option_close=round(max([0.]+[r[4]-t["entry_premium"] for r in opts]),4),
                delta=t.get("delta_at_entry"),option_price=t["entry_premium"],
                entry_vwap_r=None if relative is None else round(relative,4),
                entry_30m_signed_efficiency=None if er is None else round(er,4),
                from_open_r=None if open_reach is None else round(open_reach,4),
                minute_future_samples=len(held),minute_option_samples=len(opts),
                risk_notes=t.get("n11_entry",{}))


def attribution(rows, axis):
    groups=defaultdict(list)
    for row in rows:
        groups[axis(row)].append(row)
    return {key: {"n":len(group),"gross":round(sum(r["gross"] for r in group),2),
                  "net":round(sum(r["net"] for r in group),2),
                  "wins":sum(r["net"]>0 for r in group),
                  "median_favorable_r":round(median([r["favorable_r"] for r in group if r["favorable_r"] is not None] or [0]),3),
                  "never_half_r":sum(r["favorable_r"] is not None and r["favorable_r"]<.5 for r in group)}
            for key,group in sorted(groups.items())}


def run(year,label):
    src,raw=trades(year,label)
    db=DATASETS[year]/"breeze.sqlite"
    manifest=read(DATASETS[year]/"manifest.json")
    future_exp=manifest["future_expiries"]
    rows=[]
    with sqlite3.connect(db.resolve().as_uri()+"?mode=ro",uri=True) as c:
        for t in raw["trades"]:
            if t["status"]!="CLOSED":
                continue
            day=t["entry_time"][:10]
            expiry=next(x for x in future_exp if x>=day)
            m=re.fullmatch(r"NIFTY(\d{6})(\d+)(CE|PE)",t["tradingsymbol"])
            assert m,t["tradingsymbol"]
            series=datetime.strptime(m[1],"%y%m%d").date().isoformat()
            rows.append(describe(t,window(c,"future",expiry,day),
                                 window(c,"option",series,day,float(m[2]),m[3])))
    for row in rows:
        if not row["minute_future_samples"]:
            row["favorable_r"]=row["adverse_r"]=None
        if not row["minute_option_samples"]:
            row["favorable_option_close"]=None
    missing=[r["entry"]+" "+r["symbol"] for r in rows if not r["minute_future_samples"] or not r["minute_option_samples"]]
    if missing:
        print(year,label,"unavailable paths",missing,flush=True)
    summary={
      "member":attribution(rows,lambda r:str(r["gate"])+" "+str(r["member"])),
      "reason":attribution(rows,lambda r:r["exit_reason"]),
      "month":attribution(rows,lambda r:r["entry"][:7]),
      "side":attribution(rows,lambda r:r["side"]),
      "vwap":attribution(rows,lambda r:"UNKNOWN" if r["entry_vwap_r"] is None else "WITH" if r["entry_vwap_r"]>=0 else "AGAINST"),
      "opening":attribution(rows,lambda r:"UNKNOWN" if r["from_open_r"] is None else "WITH" if r["from_open_r"]>=0 else "AGAINST"),
      "efficiency":attribution(rows,lambda r:"UNKNOWN" if r["entry_30m_signed_efficiency"] is None else "WITH" if r["entry_30m_signed_efficiency"]>=0 else "AGAINST"),
    }
    return dict(source=str(src.relative_to(DOCS)),sha256=hashlib.sha256(src.read_bytes()).hexdigest(),
                rows=rows,summary=summary)


if __name__=="__main__":
    out={f"{year}-{label}":run(year,label) for year in DATASETS
         for label in (("N11","DIAG") if year=="2022" else ("N11T",))}
    with (HERE/"anatomy.json").open("x",encoding="utf-8") as f:
        json.dump(out,f,indent=2,sort_keys=True)
        f.write("\n")
    for label,r in out.items():
        print(label,len(r["rows"]),round(sum(x["net"] for x in r["rows"]),2),r["summary"]["reason"],flush=True)
