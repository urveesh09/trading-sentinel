"""Independent post-run cash/fee/quote/clock/recovery checks. Does not score or alter books."""
from __future__ import annotations

import bisect
import json
import math
from datetime import datetime
from pathlib import Path

import n101_lab as L

HERE, LOCAL, YEAR = L.HERE, L.LOCAL, L.YEAR
CONFIG = json.loads((HERE / "configuration.json").read_text())
RATES = CONFIG["fees"]["rates"]


def fees(buy, sell, qty):
    buy_value, sell_value = buy*qty, sell*qty
    brokerage = RATES["brokerage_flat_per_order"]*2
    exchange = RATES["exchange_pct"]*(buy_value+sell_value)
    sebi = RATES["sebi_pct"]*(buy_value+sell_value)
    ipft = RATES.get("ipft_pct", 0)*(buy_value+sell_value)
    return brokerage + RATES["stt_sell_pct"]*sell_value + exchange + sebi + ipft + RATES["stamp_duty_buy_pct"]*buy_value + RATES["gst_pct"]*(brokerage+exchange+sebi+ipft)


def full(premium, qty, lots, cost):
    return premium*qty+fees(premium,premium,qty)+(cost[0]+cost[1]*lots)*lots


def net(buy, sell, qty, extra):
    return (sell-buy)*qty-fees(buy,sell,qty)-extra


def near(a, b, context, tolerance=.011):
    assert math.isfinite(a) and math.isfinite(b) and abs(a-b) <= tolerance, (context, a, b)


def stamp(value):
    return datetime.fromisoformat(value)


def main():
    L.verify()
    L.Z.B.L._init()
    data = L.Y.dataset("year")
    packets = {}
    counts = {"books":0,"money":0,"modeled_prices":0,"native_admissions":0,"funded_adds":0,
              "watch_attempts":0,"watch_releases":0,"states":0,"cash_identities":0,"premium_stop_lifecycles":0}
    cash_drawdowns = {}

    def session(day):
        if day not in packets:
            packets[day] = sorted(data.observations(day)[0], key=lambda o:o.at)
        return packets[day]

    def quote(at, symbol):
        matches = [q for o in session(at[:10]) if o.at.isoformat()==at for q in o.options.values() if q.contract.tradingsymbol==symbol]
        assert len(matches)==1, ("missing/duplicate quote", at, symbol)
        return matches[0]

    paper = list(L.paper_rows())
    paper_times = [r[0] for r in paper]
    phases = ("controls","annual","carry")
    for phase in phases:
        keys = json.loads((LOCAL / f"keys-{phase}-{YEAR}.json").read_text())
        for name, key in keys.items():
            obj = json.loads((L.Y.EVALS/f"{key}.json").read_text())
            bookcfg, trades = obj["book"], obj["trades"]
            cost = bookcfg.get("cost") or [200,5]
            flows = []
            for t in trades:
                assert t["status"]=="CLOSED" and t["net_pnl"] is not None
                assert t["entry_qty"] in (65,130)
                assert stamp(t["entry_time"]) < stamp(t["exit_time"])
                assert stamp(t["entry_time"]).hour*60+stamp(t["entry_time"]).minute < 14*60+45
                children = t.get("n10_children") or []
                assert len(children)<=1
                parent = net(t["entry_premium"],t["exit_premium"],t["entry_qty"],float(t.get("extra_cost") or 0))
                cash_children = 0
                for c in children:
                    assert c["exit_at"] is not None
                    expected_extra=cost[0]+cost[1]
                    near(c["extra"],expected_extra,("child stress",name))
                    expected=net(c["ask"],c["bid"],c["qty"],expected_extra)
                    near(expected,c["net"],("child money",name))
                    cash_children+=c["net"]
                    flows.append((c["exit_at"],c["net"]))
                    q=quote(c["at"],t["tradingsymbol"])
                    near(q.ask,c["ask"],"child ask",.001)
                    near(quote(c["exit_at"],t["tradingsymbol"]).bid,c["bid"],"child bid",.001)
                    counts["modeled_prices"]+=2
                    assert t["entry_qty"]==130 and stamp(t["entry_time"])<stamp(c["at"])<=stamp(c["exit_at"])<=stamp(t["exit_time"])
                    assert stamp(c["at"]).hour*60+stamp(c["at"]).minute<14*60+45
                    if "n101_parent_stop" in c:
                        actual_loss=-net(c["ask"],c["premium_stop"],65,expected_extra)
                        parent_net=net(t["entry_premium"],c["n101_parent_stop"],130,(cost[0]+cost[1]*2)*2)
                        near(actual_loss,c["risk"],"actual option-stop loss")
                        near(parent_net,c["n101_parent_stop_net"],"parent stop proceeds")
                        assert parent_net>=actual_loss-1e-6 and c["planned_total"]<=c["limit"]<=5000
                        assert c["n101_parent_stop_before"]<=c["n101_parent_stop"]<q.bid
                        assert abs(c["n101_parent_stop"]/.05-round(c["n101_parent_stop"]/.05))<1e-7
                        side=1 if t["direction"]=="LONG" else -1
                        progress=side*(c["future"]-t["entry_underlying"])/abs(t["entry_underlying"]-t["initial_stop_underlying"])
                        assert progress>=1-1e-8
                        for o in session(t["entry_time"][:10]):
                            if c["at"]<o.at.isoformat()<t["exit_time"]:
                                q0=next(q for q in o.options.values() if q.contract.tradingsymbol==t["tradingsymbol"])
                                assert q0.bid<=0 or q0.bid>c["n101_parent_stop"], ("parent missed option stop",name,o.at)
                            if c["at"]<o.at.isoformat()<c["exit_at"]:
                                q0=next(q for q in o.options.values() if q.contract.tradingsymbol==t["tradingsymbol"])
                                assert q0.bid<=0 or (q0.bid>c["premium_stop"] and side*(o.future.ltp-c["level"])>0), ("child missed stop",name,o.at)
                        counts["premium_stop_lifecycles"]+=1
                near(parent+cash_children,t["net_pnl"],("total money",name,t["entry_time"]),.02)
                flows.append((t["exit_time"],parent))
                near(quote(t["entry_time"],t["tradingsymbol"]).ask,t["entry_premium"],"entry ask",.001)
                near(quote(t["exit_time"],t["tradingsymbol"]).bid,t["exit_premium"],"exit bid",.001)
                counts["modeled_prices"]+=2
                counts["money"]+=1
            opening=float(obj["notes"]["start_equity"])
            cash=opening
            high=cash
            maxdd=0
            for at, amount in sorted(flows):
                cash+=amount
                high=max(high,cash)
                maxdd=max(maxdd,(high-cash)/high)
            near(cash,opening+sum(t["net_pnl"] for t in trades),"terminal cash",.04)
            cash_drawdowns[key]=maxdd*100
            receipt=json.loads((LOCAL/"receipts"/f"{key}.json").read_text())
            for a in receipt["admissions"]:
                expected_cash=opening+sum(p for at,p in flows if at<=a["at"])
                near(a["pool"],expected_cash,("admission cash",name,a["at"]),.04)
                counts["cash_identities"]+=1
                if a["accepted"]:
                    lot=a["final_lots"]
                    reserve=full(a["ask"],65*lot,lot,cost)
                    near(reserve,a["full_reserves"][str(lot)],"entry full reserve",.001)
                    if a["floor"] is not None:
                        assert a["floor"]+a["open_reserve"]+reserve<=a["pool"]+1e-6
                    counts["native_admissions"]+=1
            decisions=json.loads((LOCAL/"decisions"/f"{key}.json").read_text())
            accepted=[]
            for e in decisions["events"]:
                if e["kind"]=="add" and e["accepted"]:
                    assert e["floor"]+e["open_reserve"]+e["child_reserve"]<=e["equity"]+1e-6
                    reserve=0
                    for t in trades:
                        if t["entry_time"]<=e["at"]<t["exit_time"]:
                            reserve+=full(t["entry_premium"],t["entry_qty"],t["entry_qty"]//65,cost)
                            for c in t.get("n10_children") or []:
                                ident=(t["entry_time"],t["tradingsymbol"],c["at"])
                                if c["at"]<=e["at"]<c["exit_at"] and (c["at"]<e["at"] or ident in accepted):
                                    reserve+=full(c["ask"],65,1,cost)
                    near(reserve,e["open_reserve"],"independent open full premium",.01)
                    near(full(e["ask"],65,1,cost),e["child_reserve"],"independent child full premium",.001)
                    accepted.append((e["parent_at"],e["symbol"],e["at"]))
                    counts["funded_adds"]+=1
                if e["kind"]!="watch":
                    continue
                counts["watch_attempts"]+=1
                cutoff=bisect.bisect_left(paper_times,stamp(e["at"]))
                assert cutoff==e["prior_closed"]
                prior=paper[:cutoff][-20:]
                if e["typical_reserve"] is not None:
                    reserves=sorted(full(t["entry_premium"],65,1,cost) for _,t in prior)
                    near((reserves[9]+reserves[10])/2,e["typical_reserve"],"typical closed reserve",.001)
                if e["released"]:
                    assert e["eligible"] and e["open_count"]==0
                    assert e["equity"]-e["floor_before"]<e["current_reserve"]<=e["typical_reserve"]
                    assert e["latest_evidence_exit"]<e["at"] and e["floor_after"]<e["floor_before"]
                    assert not any(t["entry_time"]<e["at"]<t["exit_time"] for t in trades),"released while actually exposed"
                    counts["watch_releases"]+=1
            if (bookcfg.get("n101") or {}).get("mode")=="PREMIUM_LOCK":
                actual=[(t["entry_time"],t["tradingsymbol"],c["at"]) for t in trades for c in t.get("n10_children") or []]
                assert sorted(accepted)==sorted(actual),"add identity mismatch"
            if bookcfg.get("n091"):
                terminal=json.loads((LOCAL/"states"/f"{key}.json").read_text())
                near(cash,terminal["end_equity"],"saved terminal cash",.05)
                assert terminal["window"]==obj["window"]
                counts["states"]+=1
            watch=decisions["watch_terminal"]
            if watch is not None:
                last_count=0
                best=250000
                for s in watch["slices"]:
                    upto=bisect.bisect_left(paper_times,stamp(s["at"]))
                    assert upto-last_count>=20
                    nets=[t["net_pnl"] for _,t in paper[:upto][-20:]]
                    near(sum(nets),s["evidence"],"paper pnl evidence",.02)
                    assert sum(nets)>0 and s["to"]>=.75*s["best"]-.011 and s["to"]<s["from"]
                    assert s["best"]>=best-.011
                    best=s["best"]
                    last_count=bisect.bisect_right(paper_times,stamp(s["at"]))
                if phase=="carry" and YEAR!="2023":
                    prev=L.YEARS[L.YEARS.index(YEAR)-1]
                    oldkey=json.loads((LOCAL/f"keys-carry-{prev}.json").read_text())[name]
                    prior=json.loads((LOCAL/"states"/f"{oldkey}.json").read_text())
                    near(opening,prior["end_equity"],"continuous cash",.05)
                    oldwatch=json.loads((LOCAL/"states"/f"watch-window-{oldkey}.json").read_text())
                    assert watch["slices"][:len(oldwatch["slices"])]==oldwatch["slices"]
                    assert watch["best"]>=oldwatch["best"]-1e-8
            counts["books"]+=1
    L.X.write(HERE/f"audit-{YEAR}.json",{"year":YEAR,"passed":True,"checks":counts,"cash_event_drawdown_pct":cash_drawdowns,
             "limits":["archived modeled bid/ask, not depth or broker fills","planned stops can gap; full premium still reserved","all four years seen"]})
    print(json.dumps({"year":YEAR,"passed":True,"checks":counts}),flush=True)


if __name__=="__main__":
    main()
