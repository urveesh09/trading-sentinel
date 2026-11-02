"""Independent price/depth/fee/loss-ceiling/money/stop audit of recorded expiry runs."""
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import replay as R


def fee(price,qty,schedule,buy):
    r=schedule["rates"];value=price*qty
    fixed=r["brokerage_flat_per_order"]*(1+r["gst_pct"])
    common=(r["exchange_pct"]+r["sebi_pct"]+r.get("ipft_pct",0))*(1+r["gst_pct"])
    return fixed+value*(common+(r["stamp_duty_buy_pct"] if buy else r["stt_sell_pct"]))


def near(a,b,kind,tol=.021):
    assert math.isfinite(a) and math.isfinite(b) and abs(a-b)<=tol,(kind,a,b)


def levels(q,buy,adverse):
    if isinstance(q,list):
        rows=[[q[2],q[3]]] if buy else [[q[0],q[1]]]
        stamp=q[5]
    else:
        rows=q["a"] if buy else q["b"];stamp=q["ts"]
    out=[]
    for price,qty in rows:
        if price is None:continue
        price=round(price+(.05 if buy else -.05),8) if adverse else price
        if price>0:out.append((price,qty))
    return out,stamp


def walk(rows,qty):
    assert sum(n for _,n in rows)>=qty,"insufficient recorded depth"
    value=0.;left=qty
    for price,n in rows:
        take=min(left,n);left-=take;value+=take*price
        if not left:break
    return round(value/qty,4)


def main():
    totals=defaultdict(int);source={}
    config=json.loads((R.HERE/"configuration.json").read_text())
    cases=sorted((R.LOCAL/"evals").glob("*.json"))
    for path in cases:
        c=json.loads(path.read_text())
        if c["historical"]:continue
        key=(c["day"],c["underlying"])
        if key not in source:source[key]={t["ts"]:t for t in R.load_session(*key)[0]}
        ticks=source[key];grouped=defaultdict(list)
        for p in c["positions"]:
            if p["play"] not in ("A","B","C"):continue
            schedule=json.loads(p["fee_snapshot"])
            assert schedule==config["runtime"]["fees"][p["exchange"]],"fee snapshot changed"
            qty=p["lots"]*p["lot_size"];cost=gross=0.;left=p["lots"];assumed=0.
            fixed=schedule["rates"]["brokerage_flat_per_order"]*(1+schedule["rates"]["gst_pct"])
            bound=p["entry_price"]*qty+fee(p["entry_price"],qty,schedule,True)+p["lots"]*fixed
            near(bound,p["max_loss"],"full-premium bound",.006)
            grouped[(p["play"],p["entry_ts"])].append(p)
            for i,e in enumerate(p["events"]):
                n=e["lots"];units=n*p["lot_size"]
                assert n>0 and isinstance(n,int)
                if i==0:
                    assert e["action"]=="BUY" and n==p["lots"]
                    cost=round(fee(e["price"],units,schedule,True),2)
                elif "price" in e:
                    left-=n;assert left>=0
                    expected=fee(e["price"],units,schedule,False)
                    near(expected,e["charges"],"sell fee",.006)
                    delta=(e["price"]-p["entry_price"])*units
                    near(delta,e["gross"],"sell gross",.006)
                    near(delta-expected,e["net"],"sell net",.006)
                    gross=round(gross+delta,2);cost=round(cost+expected,2)
                else:
                    assert e["action"] in ("SETTLED_ASSUMED","UNRESOLVED"),e
                    assert n==left
                    if e["action"]=="SETTLED_ASSUMED":
                        assert e["settlement_source"]=="SAMPLED_INDEX_QUOTE"
                        spot=e["settlement_spot"];intrinsic=max(spot-p["strike"],0) if p["opt_type"]=="CE" else max(p["strike"]-spot,0)
                        expected=(intrinsic-p["entry_price"])*units-intrinsic*units*.0015
                        near(expected,e["assumed_pnl"],"assumed settlement",.006)
                    assumed+=e["assumed_pnl"];left-=n
                if "price" in e:
                    t=ticks[e["ts"]];q=t["quotes"]["legs"].get(p["symbol"]);assert q is not None
                    depth,at=levels(q,i==0,c["adverse"])
                    age=(datetime.fromisoformat(e["ts"])-datetime.fromisoformat(at)).total_seconds()
                    assert -5<=age<=20,("stale fill",age)
                    near(walk(depth,units),e["price"],"actual visible VWAP",.00011)
                    h=datetime.fromisoformat(e["ts"]).time()
                    auction=(h.hour,h.minute)>=(15,15)
                    assert e["fill_model"]==("AUCTION_WINDOW" if auction else "CONTINUOUS")
                    totals["auction_fills_unverified" if auction else "continuous_fills"]+=1
                    totals["price_depth_checks"]+=1
            near(gross,p["gross"],"position gross",.006);near(cost,p["costs"],"position costs",.006)
            near(gross-cost,p["net_pnl"],"filled-event cash",.011)
            near(assumed,p.get("assumed_pnl") or 0,"assumed money",.006)
            assert p["status"]!="OPEN" and not left
            assert p["net_pnl"]+(p.get("assumed_pnl") or 0)>=-p["max_loss"]-.03,"full loss ceiling breached"
            totals["positions"]+=1
        for (play,at),ps in grouped.items():
            bound=sum(p["max_loss"] for p in ps)
            remaining=2500.
            if play=="A":
                prior=[p for p in c["positions"] if p["play"]=="A" and p["entry_ts"]<at]
                assert all(p["status"]=="CLOSED" and p["events"][-1]["ts"]<=at for p in prior),"overlapping A"
                remaining+=min(0,sum(p["net_pnl"] for p in prior))
            assert bound<=remaining+.02,("entry budget",play,bound,remaining)
            totals["entry_budget_checks"]+=1
            if play=="B":
                assert len(ps)==2
                stop_events=[e for p in ps for e in p["events"] if e["action"]=="E01_PAIR_LOSS"]
                if stop_events:
                    assert len(stop_events)==2 and len({e["ts"] for e in stop_events})==1
                    fraction=int(c["policy"].rsplit("_",1)[-1])/100
                    paid=sum(p["entry_price"]*p["lots"]*p["lot_size"] for p in ps)
                    mark=sum(p["net_pnl"] for p in ps)
                    assert mark<=-fraction*paid+.04,"pair stop labelled at the wrong net"
                    totals["pair_loss_exits"]+=1
        main=c["primary"]
        ps=[p for p in c["positions"] if p["play"] in ("A","B","C")]
        near(sum(p["net_pnl"] for p in ps),main["filled_event_net"],"main filled-event reconciliation")
        near(sum(p.get("assumed_pnl") or 0 for p in ps),main["assumed_net"],"main assumed reconciliation")
        near(main["filled_event_net"]+main["assumed_net"],main["modeled_net"],"main modeled reconciliation")
        totals["cases"]+=1
    result=dict(passed=True,checks=dict(totals),limits=["audit of paper-native replay, not broker fills","auction fills and sampled-index settlement remain unverified/assumed"])
    (R.HERE/"audit-results.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result))


if __name__=="__main__":main()
