"""Skill-format receipts for the completed, explicitly partial experiments."""
from collections import defaultdict
from datetime import date,timedelta
import json
import shutil
import study as S


def main():
    folder=S.HERE/"evidence"
    req=json.loads((folder/"request.json").read_text())
    cov=json.loads((S.HERE/"coverage.json").read_text())
    results=[json.loads((S.HERE/f"results-{g}.json").read_text()) for g in ("development-candidates","validation","test2025")]
    minute=json.loads((S.HERE/"results-minute2025.json").read_text())
    for n in ("daily-results.csv","coverage.json"):
        shutil.copyfile(S.HERE/n,folder/n)
    for module,u,isminute in (("expiry_nifty_exit_panel","NIFTY",False),("expiry_sensex_exit_panel","SENSEX",False),
                              ("expiry_nifty_minute_proxy","NIFTY",True)):
        allp=minute["positions"]["E011"]["ordinary"] if isminute else [p for r in results for p in r["positions"]["E011"]["ordinary"] if p["underlying"]==u]
        by=defaultdict(list)
        for p in allp:by[p["day"]].append(p)
        known={a["day"]:a for a in minute["availability"]} if isminute else {a["day"]:a for r in results for a in r["availability"] if a["book"]==u}
        metrics=lambda p:dict(closed_trades=sum(x["status"]=="CLOSED" for x in p),unresolved=sum(x["status"]!="CLOSED" for x in p),
                              filled_fee_pnl=round(sum(x["net_pnl"] for x in p),2),assumed_pnl=round(sum(x.get("assumed_pnl") or 0 for x in p),2),modeled_net=S.L.net(p))
        daily=[]
        day=date.fromisoformat(req["start"]);end=date.fromisoformat(req["end"])
        while day<=end:
            d=day.isoformat()
            k=known.get(d)
            available=k is not None and k.get("status","PARTIAL")!="UNAVAILABLE"
            daily.append(dict(date=d,status="PARTIAL" if available else "UNAVAILABLE",
                reason=("Completed declared proxy/panel, independent pockets; native whole-book behavior unavailable" if available
                        else "No eligible evidence in this experiment; excluded/unacquired date is unknown, not a zero trade result or a verified non-expiry"),
                metrics=metrics(by[d]) if available else {k:None for k in ("closed_trades","unresolved","filled_fee_pnl","assumed_pnl","modeled_net")}))
            day+=timedelta(days=1)
        row=dict(module=module,start=req["start"],end=req["end"],status="PARTIAL",fidelity="BAR_LIFECYCLE",population="SHADOW",coverage="PARTIAL",
                 reason="Completed the declared research experiment, with insufficient evidence for exact native expiry-book performance",
                 metrics=metrics(allp),daily_results=daily,
                 inputs=["inputs/configuration.json","inputs/coverage.json","inputs/minute-coverage.json","inputs/freeze.json","inputs/parity.json","inputs/hash-tree-verification.json"],
                 artifacts=["ANALYSIS.md","analysis.json","daily-results.csv","coverage.json"],
                 assumptions=["Fresh independent Rs2500 pockets, current normalized lots/fees, completed bars and next-bar modelled fills", "No opening exposure or historical bankroll continuity claim"],
                 limitations=["No observed bid/ask/depth, execution or native auction tail", "Ten-second panel admissions are not the main C entries and may overlap; minute C has coarse confirmations and partial recorded chain", "Unknown dates/coverage remain null; pre-2025 prices excluded", "No unified system-profit assertion; code freeze preceded scoring, this wrapper was prepared afterward"])
        assert abs(sum(x["net_pnl"] for x in allp)-row["metrics"]["filled_fee_pnl"])<.01
        S.dump(folder/"modules"/(module+".json"),row)
    print("Three partial receipts populated with every requested date and no invented non-expiry classifications")


if __name__=="__main__":main()
