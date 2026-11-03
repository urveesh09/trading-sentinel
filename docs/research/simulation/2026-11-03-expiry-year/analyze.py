"""Post-score audit/report only. Does not select or modify any trading rule."""
from collections import Counter,defaultdict
from datetime import datetime,timedelta
import csv
import json
import random
import statistics

import study as S
from minutes import Minute


def combined(results,arm,scenario):
    return [p for r in results for p in r["positions"][arm][scenario]]


def relative(a,b,strict=True):
    return dict(higher_net=a["net"]>b["net"]+.01 if strict else a["net"]>=b["net"]-.01,
                worst=a["worst"]>=b["worst"]-.01,
                without_best=a["without_best"]>=b["without_best"]-.01)


def novel(a,b):
    return dict(**relative(a,b),positive=a["net"]>0,positive_without_best=a["without_best"]>0,
                drawdown=a["drawdown"]<=b["drawdown"]+.01,
                unresolved=a["unresolved"]==0)


def audit(results,minute):
    """Reconstruct cash flows, source bar execution prices and participation caps."""
    cache={};checked=events=0
    coverage=json.loads((S.HERE/"coverage.json").read_text())
    infos={(x["book"],x["day"]):x for x in coverage["sessions"]}
    failures=[]
    for r,is_minute in [(r,False) for r in results]+[(minute,True)]:
        for arm,scenarios in r["positions"].items():
            for scenario,positions in scenarios.items():
                for p in positions:
                    S.audit_position(p)
                    # Cash is reconstructed from raw order amounts, independently
                    # of the stored gross/net accumulator.
                    cash=-p["entry_price"]*p["lots"]*p["lot_size"]-p["_events"][0]["charges"]
                    for e in p["_events"][1:]:cash+=e["price"]*e["lots"]*p["lot_size"]-e["charges"]
                    if p["lots_open"]==0:assert abs(round(cash,2)-p["net_pnl"])<=.03
                    key=(is_minute,p["underlying"],p["day"])
                    if key not in cache:
                        cache[key]=Minute(p["day"]) if is_minute else S.Session(infos[p["underlying"],p["day"]])
                    x=cache[key]
                    idx={t.isoformat():i for i,t in enumerate(x.now)}
                    for j,e in enumerate(p["_events"]):
                        k=idx[e["ts"]]
                        side="BUY" if j==0 else "SELL"
                        filled,price=x.fill(k,p["symbol"],side,e["lots"],scenario=="adverse")
                        assert filled==e["lots"] and abs(price-e["price"])<=.0001,(arm,scenario,e)
                        assert k>0
                        assert x.now[k]-x.now[k-1]==timedelta(seconds=x.seconds if is_minute else 10)
                        events+=1
                    checked+=1
    return dict(positions_checked=checked,execution_events_checked=events,cashflow_errors=0,
                source_price_errors=0,lot_or_budget_errors=0,paired_exit_entry_mismatches=0,
                qualification="Confirms the declared OHLC model, not executable bid/ask or real-market profit")


def bootstrap_delta(a,b):
    """Descriptive session-cluster CI, no selection threshold or IID ticket claim."""
    da=S.stats(a)["daily"];db=S.stats(b)["daily"]
    vals=[da.get(k,0)-db.get(k,0) for k in sorted(da.keys()|db.keys())]
    rng=random.Random(20261103)
    samples=sorted(sum(rng.choice(vals) for _ in vals) for j in range(5000))
    return dict(sessions=len(vals),paired_net_delta=round(sum(vals),2),
                percentile95_total_delta=[round(samples[124],2),round(samples[4874],2)],
                note="Descriptive only; time/regime dependence and limited SENSEX 2025 remain")


def main():
    S.no_network();S.verify_freeze()
    results=[json.loads((S.HERE/f"results-{g}.json").read_text()) for g in ("development-candidates","validation","test2025")]
    minute=json.loads((S.HERE/"results-minute2025.json").read_text())
    report=dict(aggregate={},windows={},fixed_exam={},novel={},diagnosis={},audit=audit(results,minute),
                strict_book_status="UNAVAILABLE on ten-second data; minute C is a separate partial proxy")
    for arm in results[0]["positions"]:
        if arm in ("E011_BOX35","E011_BAND50"):continue
        report["aggregate"][arm]={}
        for sc in ("ordinary","adverse"):
            p=combined(results,arm,sc)
            report["aggregate"][arm][sc]={"all":S.stats(p)}
            for u in S.LOT:report["aggregate"][arm][sc][u]=S.stats([x for x in p if x["underlying"]==u])
            for year in ("2025","2026"):report["aggregate"][arm][sc][year]=S.stats([x for x in p if x["day"].startswith(year)])
    for r in results:
        report["windows"][r["group"]]={n:{sc:row["all"] for sc,row in scenarios.items()} for n,scenarios in r["summaries"].items()}
    A=report["aggregate"]
    for name,base,strict in (("E011","E01",True),("E011R","E011",False),("E011_S20","E011",False)):
        checks={sc:relative(A[name][sc]["all"],A[base][sc]["all"],strict) for sc in ("ordinary","adverse")}
        report["fixed_exam"][name]=dict(checks=checks,relative_panel_pass=all(all(v.values()) for v in checks.values()),
            scope="Original relative exit screen, not full-book or profit qualification",
            per_index_checks={u:{sc:relative(A[name][sc][u],A[base][sc][u],strict) for sc in ("ordinary","adverse")} for u in S.LOT})
    for name in ("E012_IDLE8","E012_LOCK40"):
        checks={}
        for r in results[1:]:
            for sc in ("ordinary","adverse"):
                checks[r["group"]+"|"+sc]=novel(r["summaries"][name][sc]["all"],r["summaries"]["E011"][sc]["all"])
                for u in S.LOT:
                    checks[r["group"]+"|"+sc+"|"+u]=novel(r["summaries"][name][sc][u],r["summaries"]["E011"][sc][u])
        for sc in ("ordinary","adverse"):
            checks["minute2025|"+sc]=novel(minute["summaries"][name][sc],minute["summaries"]["E011"][sc])
        report["novel"][name]=dict(passed=all(all(c.values()) for c in checks.values()),checks=checks)
    for sc in ("ordinary","adverse"):
        p=combined(results,"E011",sc)
        loss=[x for x in p if S.L.net([x])<0]
        report["diagnosis"][sc]=dict(
            tickets=len(p),losses=len(loss),loser_median_peak_multiple=statistics.median(x["peak"]/x["entry_price"] for x in loss),
            losers_reached40pct=sum(x["peak"]>=1.4*x["entry_price"] for x in loss),
            losses_then_later_high3x=sum(x["mfe_multiple_after_exit"]>=3 for x in loss),
            reached3x=[{k:x[k] for k in ("day","underlying","symbol","entry_price","peak","net_pnl","admission_rule")} for x in p if x["peak"]>=3*x["entry_price"]],
            top_tickets=[{k:x[k] for k in ("day","underlying","entry_price","net_pnl","admission_rule")} for x in sorted(p,key=lambda x:S.L.net([x]),reverse=True)[:8]],
            E011_vs_E01=bootstrap_delta(p,combined(results,"E01",sc)),
            S20_vs_E011=bootstrap_delta(combined(results,"E011_S20",sc),p))
    report["minutes"]=minute["summaries"]
    report["entry_readings"]={}
    base={p["day"]:p for p in minute["positions"]["E011"]["ordinary"] if p["net_pnl"]>=1000}
    for name in ("E011_BOX35","E011_BAND50"):
        byday={p["day"]:p for p in minute["positions"][name]["ordinary"]}
        kept=sum(d in byday and byday[d]["net_pnl"]>=1000 for d in base)
        checks={sc:relative(minute["summaries"][name][sc],minute["summaries"]["E011"][sc],False) for sc in ("ordinary","adverse")}
        report["entry_readings"][name]=dict(minute_relative_checks=checks,baseline_1000_winners=len(base),
            retained_1000_winner_days=kept,winner_day_retention=kept/len(base) if base else None,
            ten_second_status="UNAVAILABLE: opening-strike panel is not an entry test",
            full_exam_verdict="INCONCLUSIVE; minute proxy cannot substitute for the frozen full-book exam")
    S.dump(S.HERE/"analysis.json",report)
    with open(S.HERE/"daily-results.csv","w",newline="",encoding="utf-8") as f:
        w=csv.writer(f);w.writerow(["model","window","arm","scenario","underlying","date","tickets","filled_fee_pnl","assumed_pnl","net","fees"])
        for r,isminute in [(r,False) for r in results]+[(minute,True)]:
            for name,scenarios in r["positions"].items():
                for sc,p in scenarios.items():
                    buckets=defaultdict(list)
                    for x in p:buckets[x["underlying"],x["day"]].append(x)
                    for (u,d),q in sorted(buckets.items()):
                        st=S.stats(q);w.writerow([r["model"],"test2025" if isminute else r["group"],name,sc,u,d,len(q),st["filled_fee_pnl"],st["assumed_pnl"],st["net"],st["fees"]])
    print("AUDIT",report["audit"])
    print("FIXED",{k:v["relative_panel_pass"] for k,v in report["fixed_exam"].items()})
    print("NOVEL",{k:v["passed"] for k,v in report["novel"].items()})


if __name__=="__main__":main()
