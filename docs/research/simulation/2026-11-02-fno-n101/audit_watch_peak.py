"""Independent actual cash-peak versus decision-observed WATCH tracker audit."""
import argparse
import bisect
import itertools
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
LOCAL=HERE/"_local"
YEARS=("2023","2024","2025","2026")


def main(output):
    target=HERE/output
    assert not target.exists(),"retain earlier audit attempts"
    issues=[]; terminal=[]; bound=[]; checks=0; windows=0
    for phase in ("controls","annual","carry"):
        for year in YEARS:
            path=LOCAL/f"keys-{phase}-{year}.json"
            if not path.exists():
                continue
            for name,key in json.loads(path.read_text()).items():
                watch=json.loads((LOCAL/"decisions"/f"{key}.json").read_text())["watch_terminal"]
                if watch is None:
                    continue
                keys=[key]
                if phase=="carry":
                    keys=[json.loads((LOCAL/f"keys-carry-{y}.json").read_text())[name] for y in YEARS[:YEARS.index(year)+1]]
                flows=[]
                for k in keys:
                    for t in json.loads((LOCAL/"evals"/f"{k}.json").read_text())["trades"]:
                        kids=t.get("n10_children") or []
                        flows.extend((c["exit_at"],c["net"]) for c in kids)
                        flows.append((t["exit_time"],t["net_pnl"]-sum(c["net"] for c in kids)))
                cash=high=250000.; stamps=[]; peaks=[]
                for at,group in itertools.groupby(sorted(flows,key=lambda f:f[0]),key=lambda f:f[0]):
                    cash+=sum(v for _,v in group)
                    high=max(high,cash); stamps.append(at); peaks.append(high)
                for s in watch["slices"]:
                    upto=bisect.bisect_right(stamps,s["at"])
                    actual=peaks[upto-1] if upto else 250000.
                    if s["best"]<actual-.02:
                        issues.append({"phase":phase,"year":year,"book":name,"at":s["at"],"declared":s["best"],"actual":actual})
                    if s["to"]<.75*actual-.02:
                        bound.append({"phase":phase,"year":year,"book":name,"at":s["at"],"floor":s["to"],"actual_peak":actual})
                    checks+=1
                if watch["best"]<high-.02:
                    terminal.append({"phase":phase,"year":year,"book":name,"decision_observed_best":watch["best"],
                                     "actual_closed_cash_peak":high,"difference":high-watch["best"]})
                windows+=1
    result={"windows":windows,"release_checks_including_carried_history":checks,"release_tracker_lags":issues,
            "release_deepest_floor_violations":bound,"terminal_tracker_lags":terminal,
            "passed_decision_bound":not issues and not bound,
            "basis":"Closed cash after all settlements at each observation; terminal tracker may miss a last close because it updates only during planning. No price/fee or P&L is changed."}
    target.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in ("terminal_tracker_lags",)},default=str))
    print("terminal_lags",len(terminal))


if __name__=="__main__":
    cli=argparse.ArgumentParser(); cli.add_argument("--out",default="watch-peak-audit.json")
    main(cli.parse_args().out)
