"""Frozen routes and honest money separation for the small expiry study."""
import json
from pathlib import Path
from collections import defaultdict

HERE=Path(__file__).resolve().parent
LOCAL=HERE/"_local"


def rows(policy,adverse=False):
    suffix="adverse" if adverse else "ordinary"
    paths=sorted((LOCAL/"evals").glob(f"*-{policy}-{suffix}.json"))
    assert len(paths)==8,(policy,suffix,len(paths))
    return [json.loads(p.read_text()) for p in paths]


def stats(cases,full_only=False):
    cases=[c for c in cases if not full_only or not c["legacy_index_clock"]]
    total=peak=dd=0.;by_u=defaultdict(float);daily=[]
    for c in cases:
        value=c["primary"]["modeled_net"];daily.append(value);total+=value;peak=max(peak,total);dd=max(dd,peak-total);by_u[c["underlying"]]+=value
    return dict(sessions=len(cases),net=round(total,2),worst_day=min(daily),drawdown_rupees=round(dd,2),
                without_best=round(total-max(daily),2),by_underlying=dict(by_u),
                filled_event_net=round(sum(c["primary"]["filled_event_net"] for c in cases),2),
                assumed_net=round(sum(c["primary"]["assumed_net"] for c in cases),2),
                unresolved=sum(c["primary"]["unresolved"]+c["primary"]["open"] for c in cases),
                positive_sessions=sum(v>0 for v in daily),negative_sessions=sum(v<0 for v in daily))


def routes(a,b):
    common=dict(no_unresolved=a["unresolved"]==b["unresolved"]==0,without_best_no_worse=a["without_best"]>=b["without_best"]-.01,
                underlyings_no_worse=all(a["by_underlying"][u]>=v-.01 for u,v in b["by_underlying"].items()))
    profit={**common,"higher_net":a["net"]>b["net"]+.01,"worst_day_no_worse":a["worst_day"]>=b["worst_day"]-.01,
            "drawdown_no_worse":a["drawdown_rupees"]<=b["drawdown_rupees"]+.01}
    loss={**common,"net_retained":a["net"]>=.9*b["net"] if b["net"]>0 else a["net"]>b["net"],
          "worst_day_smaller":a["worst_day"]>b["worst_day"]+.01,"drawdown_smaller":a["drawdown_rupees"]<b["drawdown_rupees"]-.01}
    return dict(profit=profit,loss=loss,profit_pass=all(profit.values()),loss_pass=all(loss.values()))


def main():
    from policies import PRIMARY,NEIGHBOURS
    names=("BASE",*PRIMARY,*NEIGHBOURS)
    result={"all_seen":True,"new_primary":list(PRIMARY),"evaluations":{},"checks":{}}
    for name in names:
        result["evaluations"][name]={}
        for adverse in ((False,True) if name in ("BASE",*PRIMARY) else (False,)):
            result["evaluations"][name]["adverse" if adverse else "ordinary"]={
                "all8":stats(rows(name,adverse)),"raw_clock7":stats(rows(name,adverse),True)}
    for name in PRIMARY:
        checks={}
        for scenario in ("ordinary","adverse"):
            for group in ("all8","raw_clock7"):
                checks[f"{scenario}|{group}"]=routes(result["evaluations"][name][scenario][group],result["evaluations"]["BASE"][scenario][group])
        profit=all(c["profit_pass"] for c in checks.values());loss=all(c["loss_pass"] for c in checks.values())
        plateau={}
        for near in (name.replace("30","20"),name.replace("30","40")):
            a,b=result["evaluations"][near]["ordinary"]["all8"],result["evaluations"]["BASE"]["ordinary"]["all8"]
            plateau[near]=a["net"]>=b["net"]-.01 and a["worst_day"]>=b["worst_day"]-.01 if profit else routes(a,b)["loss_pass"] if loss else False
        result["checks"][name]={"routes":checks,"profit_route":profit,"loss_route":loss,"plateau":plateau,"accepted_screen":(profit or loss) and all(plateau.values())}
    (HERE/"results-round1.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({n:result["evaluations"][n]["ordinary"]["all8"]|{"accepted":result["checks"].get(n,{}).get("accepted_screen")} for n in names}))


if __name__=="__main__":main()
