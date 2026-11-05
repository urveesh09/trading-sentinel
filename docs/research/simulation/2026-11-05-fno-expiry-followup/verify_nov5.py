"""Generate and verify the November 5 per-module simulation receipt."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
LOCAL=HERE/"_local"
OUT=LOCAL/"final-nov5-receipt"
SKILL=Path.home()/".codex/skills/sentinel-trading-simulation/scripts/simulation_evidence.py"
DAY="2026-11-05"
MODULES=("fno_nifty_single","fno_sensex_single","fno_defined_risk","expiry_paper","expiry_e032")

def tool(command,*args):
    subprocess.run([sys.executable,str(SKILL),command,*map(str,args)],cwd=ROOT,check=True)

def write(path,value):
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n",encoding="utf-8")

def money(closed,net,signals=None):
    return dict(closed_trades=closed,signals=signals,filled_fee_pnl=net,assumed_pnl=0.0,modeled_net=net,unresolved=0)

def main():
    tool("init","--repo",ROOT,"--production",ROOT.parent/"Production_Trading-sentinel",
         "--date",DAY,"--as-of",DAY,"--modules",",".join(MODULES),"--out",OUT)
    # These original input hashes were recorded before the first causal replay.
    sealed=json.loads((HERE/"inputs.json").read_bytes())["files_sha256"]
    for key in ("_local/expiry-input.sqlite","_local/expiry-masters.json","_local/expiry-baseline.json",
                "_local/regular.json","_local/exit-paths.jsonl","_local/nifty-quote-tail.jsonl"):
        src=HERE/key
        with src.open("rb") as f:
            assert hashlib.file_digest(f,"sha256").hexdigest()==sealed[key],key
        (OUT/key).parent.mkdir(exist_ok=True)
        shutil.copyfile(src,OUT/key)
    for name in ("configuration.json","regular_today.py","regular_rules.py","expiry_study.py"):
        shutil.copyfile(HERE/name,OUT/name)
    tool("inspect-expiry","--run",OUT,"--source",OUT/"_local/expiry-input.sqlite")
    tool("seal","--run",OUT,"--paths","configuration.json","regular_today.py","regular_rules.py","expiry_study.py",
         "preflight/expiry.json",*[k for k in sealed if k.startswith("_local/")])

    # Re-run the three held-position exits and both expiry baselines at the finalized source.
    import regular_today as rt
    rt.HERE=OUT
    rt.main()
    import expiry_study as ex
    import sqlite3
    con=sqlite3.connect((OUT/"_local/expiry-input.sqlite").as_uri()+"?mode=ro",uri=True)
    con.row_factory=sqlite3.Row
    ticks=con.execute("select day,underlying,ts,spot,fut,quotes from expiry_paper_ticks where day=? and underlying='SENSEX' order by ts",(DAY,)).fetchall()
    masters=json.loads((OUT/"_local/expiry-masters.json").read_bytes())
    book=ex.master(masters[DAY],"SENSEX",DAY)
    work=OUT/"_local"
    e032,counts,risk=ex.e032(ticks,book,DAY,work)
    a,_,signals=ex.legacy(ticks,book,DAY,"SENSEX",matched=False,delay=0)
    assert not e032 and len(ticks)==966 and counts["signal"].get("passed",0)==0
    assert len(a)==1 and a[0]["net_pnl"]==1962.21 and len(signals)==1
    write(OUT/"expiry-day.json",{"E032":ex.summary(e032),"checks":counts,"risk":risk,"A":ex.summary(a)})
    baseline=json.loads((OUT/"regular-today-results.json").read_bytes())
    net=round(sum(v["N11T"]["net"] for v in baseline["today"].values()),2)
    assert net==4821.18

    def receipt(module,status,fidelity,coverage,reason,metrics,inputs,artifacts,limits,population="PRIMARY"):
        write(OUT/"modules"/f"{module}.json",dict(module=module,start=DAY,end=DAY,status=status,
            fidelity=fidelity,coverage=coverage,reason=reason,metrics=metrics,inputs=inputs,artifacts=artifacts,
            limitations=limits,population=population,assumptions=["Production paper economics, IST decision clocks."],
            daily_results=[dict(date=DAY,status=status,metrics=metrics)]))
    receipt("fno_nifty_single","PARTIAL","QUOTE_LIFECYCLE","PARTIAL",
            "Three baseline exits reproduced on original held positions. Full alternative admission not replayed.",
            money(3,net),["configuration.json","_local/regular.json","_local/exit-paths.jsonl","_local/nifty-quote-tail.jsonl"],
            ["regular-today-results.json"],["Paper bid basis and conditional fixed entries, with original reserves and fills."])
    evaluator=dict(closed_trades=None,signals=2,filled_fee_pnl=None,assumed_pnl=None,modeled_net=None,unresolved=None)
    receipt("fno_sensex_single","PARTIAL","EVALUATOR","PARTIAL",
            "Two distinct logged signal bars reached the same-day expiry exclusion, six checks.",
            evaluator,["configuration.json","_local/regular.json"],["_local/regular.json"],
            ["No counterfactual entry from a logged refusal."])
    receipt("fno_defined_risk","UNAVAILABLE","NONE","UNAVAILABLE",
            "Unchanged recorded close +2545.91 is reconciled separately. Spread lifecycle was not replayed.",
            {k:None for k in evaluator},["configuration.json","_local/regular.json"],["_local/regular.json"],
            ["Source record uses paper midpoint entry and bid/ask exit."])
    receipt("expiry_paper","PARTIAL","QUOTE_LIFECYCLE","PARTIAL",
            "Legacy A reconciles at its recorded expiry fill and close. C and other shadows remain outside the challenger.",
            money(1,1962.21,1),["configuration.json","preflight/expiry.json","_local/expiry-masters.json"],
            ["expiry-day.json"],["A alone. Quote snapshots do not establish queue fills."],"SHADOW")
    receipt("expiry_e032","COMPLETED","QUOTE_LIFECYCLE","COMPLETE",
            "Full recorded expiry afternoon replay for the declared sampled clock. No signal passed.",
            money(0,0.,0),["configuration.json","preflight/expiry.json","_local/expiry-masters.json","_local/expiry-baseline.json"],
            ["expiry-day.json"],["Completion is bounded to the recorded 10-second clock."])
    tool("report","--run",OUT)
    tool("verify","--run",OUT)

if __name__=="__main__":
    main()
