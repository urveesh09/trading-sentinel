"""Final fixed-SHA skill packet, post-run consistency only; not a replacement preregistration."""
import importlib.util
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import date,timedelta
from pathlib import Path

import n101_lab as L

HERE,ROOT,LOCAL=L.HERE,L.ROOT,L.LOCAL


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main(expected):
    L.verify()
    helper=Path("C:/Users/Urveesh/.codex/skills/sentinel-trading-simulation/scripts/simulation_evidence.py")
    spec=importlib.util.spec_from_file_location("n101_evidence",helper)
    H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H)
    assert H.git(ROOT,"rev-parse","HEAD")==expected
    out=LOCAL/"evidence-report-final"
    modules={"n10_retry_continuous":"N10","watch_flat_continuous":"WATCH_FLAT","premium_lock_continuous":"PREMIUM_LOCK"}
    H.initialize(ROOT,ROOT.parent/"Production_Trading-sentinel",out,"2023-01-01","2026-10-28","2026-11-02",list(modules))
    tracked=H.git(ROOT,"ls-files",HERE.relative_to(ROOT).as_posix()).splitlines()
    for name in tracked:
        path=ROOT/name;target=out/"study"/path.relative_to(HERE)
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    for folder in ("evals","receipts","decisions","states"):
        for path in (LOCAL/folder).glob("*.json"):
            target=out/("private-"+folder)/path.name
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    for path in LOCAL.iterdir():
        if path.is_file() and path.name.startswith(("keys-","binding-","command-","audit-command-")):
            target=out/"private-commands"/path.name
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    shutil.copy2(HERE/"README.md",out/"ANALYSIS.md")
    shutil.copy2(HERE/"configuration.json",out/"configuration.json")
    freeze=read(HERE/"freeze.json")
    (out/"input-verification.json").write_text(json.dumps({"passed":True,"source_files":len(freeze["sources"]),"input_files":len(freeze["inputs"]),
      "original_pre_score_source":"c567f8e","post_run_packaging":True,"not_preregistration":True,
      "raw_cache_paths_retained_in_dev":True,"full_manifest":freeze["inputs"]},indent=2)+"\n",encoding="utf-8")
    sealed=H.seal(out,[p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()
             and p.name not in ("request.json","policy-freeze.json") and "modules" not in p.relative_to(out).parts])
    available=set()
    for y in L.YEARS:
        binding=read(LOCAL/f"binding-{y}.json")
        available.update(p.stem for p in (ROOT/binding["cache"]).glob("*.pkl"))
    for module,name in modules.items():
        trades=[]
        for y in L.YEARS:
            key=read(LOCAL/f"keys-carry-{y}.json")[f"{name}|200"]
            trades+=read(LOCAL/"evals"/f"{key}.json")["trades"]
        assert all(t["status"]=="CLOSED" for t in trades)
        daily=defaultdict(float);counts=defaultdict(int)
        for t in trades:
            day=t["exit_time"][:10];assert day in available
            daily[day]+=t["net_pnl"];counts[day]+=1
        total=sum(t["net_pnl"] for t in trades)
        row=read(out/"modules"/f"{module}.json")
        row.update(status="PARTIAL",coverage="PARTIAL",fidelity="BAR_LIFECYCLE",population="SHADOW",
          reason="Finished bounded continuous research replay; historical quotes are candle-derived, with retained gaps and modeled execution.",
          inputs=list(sealed),artifacts=["ANALYSIS.md","study/results.json","study/VERIFICATION.md","study/control-parity.json",
            "study/watch-peak-audit.json","input-verification.json",*[f"study/audit-{y}.json" for y in L.YEARS]],
          metrics=dict(closed_trades=len(trades),signals=None,filled_fee_pnl=0.,assumed_pnl=total,modeled_net=total,unresolved=0),
          assumptions=["One continuous Rs250000 account Jan2023 to Oct28,2026; no annual deposits or reset.",
             "Normalized65-unit lots/current fees/modeled bid-ask/declared extra stress; cash is entirely simulated.",
             "Original source/config/input freeze c567f8e precedes all scores; this final packet is post-run consistency only.",
             "Native risk/exit clocks retained. WATCH may spend bounded additional lifetime loss budget; not live authority."],
          limitations=["All four years seen; no profitability proof, no pristine holdout.","Prior gaps/clipped candles retained; no actual depth or broker execution proof.",
             "Independent annual/cost experiments are separate artifacts and cannot be summed into this account.",
             "Rs15000 one-lot live trial not represented; Production and real-money settings unchanged."])
        row["daily_results"]=[]
        d=date(2023,1,1)
        while d<=date(2026,10,28):
            label=d.isoformat();yes=label in available
            row["daily_results"].append(dict(date=label,status="PARTIAL" if yes else "UNAVAILABLE",
              reason="Frozen cached session, original gaps retained; modeled booked cash." if yes else "No archived session in this replay scope; not assumed zero return.",
              metrics=dict(closed_trades=counts[label] if yes else None,filled_fee_pnl=0. if yes else None,
                           assumed_pnl=daily[label] if yes else None,modeled_net=daily[label] if yes else None)))
            d+=timedelta(days=1)
        (out/"modules"/f"{module}.json").write_text(json.dumps(row,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    report=H.render(out);errors=H.verify(out)
    proof=dict(validation=report["validation"],verification_errors=errors,git_sha=expected,post_run_packaging=True,
               not_preregistration=True,whole_system_profit_available=False,modules=len(modules),sealed_files=len(sealed))
    (out/"VERIFIED.json").write_text(json.dumps(proof,indent=2)+"\n",encoding="utf-8")
    assert report["validation"]=="EVIDENCE_CHECKS_PASSED" and not errors,errors
    print(json.dumps(proof),flush=True)


if __name__=="__main__":
    main(sys.argv[1])
