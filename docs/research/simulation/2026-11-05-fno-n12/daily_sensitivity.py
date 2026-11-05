"""Sensitivity to 2022 daily index prices. The derivative data and controls are unchanged."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import json
import os
import subprocess

os.environ["N12_YEAR"]="2022"
import round1 as r

HERE=Path(__file__).resolve().parent
LOCAL=HERE/"_local"/"2022-public-daily"
PRIOR=r.PREV/"_local/nifty-2022/daily.json"
PUBLIC=HERE/"_local/yahoo-nifty-2022-daily-audit.json"
DAILY=LOCAL/"daily.json"
F=r.f
r.Y.EVALS=LOCAL/"evals"
F.X.LOCAL=F.B.LOCAL=F.T.LOCAL=F.L.U.LOCAL=LOCAL
F.Z.N.GAP.DAILY=DAILY
F.Z.DAILY_SOURCES=(DAILY,)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def prepare():
    LOCAL.mkdir(parents=True,exist_ok=True)
    original=json.loads(PRIOR.read_bytes())["rows"]
    source=json.loads(PUBLIC.read_bytes())["chart"]["result"][0]
    q=source["indicators"]["quote"][0]
    ist=timezone(timedelta(hours=5,minutes=30))
    ohlc={datetime.fromtimestamp(t,ist).date().isoformat():[round(q[k][i],2) for k in ("open","high","low","close")]
          for i,t in enumerate(source["timestamp"]) if all(q[k][i] is not None for k in ("open","high","low","close"))}
    old_dates={d for d,*_ in original if d.startswith("2022-")}
    assert set(ohlc)==old_dates and len(old_dates)==248
    new=[row for row in original if row[0]<"2022"]+[[d,*ohlc[d]] for d in sorted(ohlc)]
    with DAILY.open("x",encoding="utf-8") as f:json.dump({"rows":new},f)
    freeze={"source_sha256":sha(PUBLIC),"original_daily_sha256":sha(PRIOR),
            "alternate_daily_sha256":sha(DAILY),"source_code_sha256":sha(Path(__file__)),
            "controls":["N11","N11T"],"design":"Replay on identical derivative data with independently sourced daily 2022 OHLC only. Rebuild the causal one-lot evidence."}
    with (HERE/"daily-sensitivity-freeze.json").open("x",encoding="utf-8") as f:
        json.dump(freeze,f,indent=2)
        f.write("\n")

def raw_diag():
    raw=r.raw_for(F.Z.diag_books()["DIAG"])
    rows=[t for t in raw["trades"] if t["status"]=="CLOSED"]
    return tuple(sorted(((datetime.fromisoformat(t["exit_time"]),t) for t in rows),
                        key=lambda z:(z[0],z[1]["entry_time"])))

F.L.U.paper_rows=raw_diag

def main():
    spec=HERE/"daily-sensitivity-freeze.json"
    cfg=json.loads(spec.read_bytes())
    rel=spec.relative_to(r.ROOT).as_posix()
    assert cfg==json.loads(subprocess.check_output(["git","show",f"HEAD:{rel}"],cwd=r.ROOT))
    for path,k in ((PUBLIC,"source_sha256"),(PRIOR,"original_daily_sha256"),(DAILY,"alternate_daily_sha256"),(Path(__file__),"source_code_sha256")):
        assert sha(path)==cfg[k]
    F.Z.N.run_books({"DIAG":F.Z.diag_books()["DIAG"]},1)
    arms=r.books()
    chosen={k:arms[k] for k in cfg["controls"]}
    F.Z.N.run_books(chosen,2)
    results={k:r.metrics(r.raw_for(b)) for k,b in chosen.items()}
    results["diagnostic"]=r.metrics(r.raw_for(F.Z.diag_books()["DIAG"]))
    for k,v in results.items():
        print(k,v["net"],v["closed"],v["worst_day"],v["notes"].get("n11t_second_lots",0),flush=True)
    with (HERE/"daily-sensitivity-results.json").open("x",encoding="utf-8") as f:
        json.dump(results,f,indent=2,sort_keys=True)
        f.write("\n")

if __name__=="__main__":
    import sys
    (prepare if sys.argv[1]=="prepare" else main)()
