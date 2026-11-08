"""Reconcile held paper entries, then compare exits at recorded bid and future observations."""
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
import json
import sys

HERE=Path(__file__).resolve().parent
LOCAL=HERE/"_local"
sys.path.insert(0,str(HERE.parents[3]/"python-engine"))
from fno_costs import calc_fno_costs
from fno_exit_rules import evaluate_single_leg_exit
from fno_n11 import ADD_AT_R, budget, child_full_loss, extra_cost, parent_loss_at_stop
from regular_rules import Trend, trend_params

DAY="2026-11-05"
IST=timezone(timedelta(hours=5,minutes=30))

def stamp(raw):
    return datetime.fromisoformat(raw.replace("Z","+00:00")).astimezone(IST)

def observed_tails():
    batches=defaultdict(dict)
    for line in (LOCAL/"nifty-quote-tail.jsonl").open(encoding="utf-8"):
        r=json.loads(line)
        at=stamp(r["received_at_utc"])
        pt=r.get("provider_timestamp_utc")
        if pt and -1<=(at-stamp(pt)).total_seconds()<=10:
            batches[at][r["contract"]["tradingsymbol"]]=r
    by_symbol=defaultdict(list)
    for at, rows in sorted(batches.items()):
        f=rows.get("NIFTY26NOVFUT")
        if not f or not f["ltp"]:
            continue
        for symbol,r in rows.items():
            if r is f or r["depth_state"]!="USABLE":
                continue
            bids=r["buy_depth"]
            asks=r["sell_depth"]
            if bids and asks:
                by_symbol[symbol].append(dict(at=at.isoformat(),bid=bids[0]["price"],ask=asks[0]["price"],
                    bid_qty=bids[0]["quantity"],ask_qty=asks[0]["quantity"],fut=f["ltp"],
                    archived=True))
    return by_symbol

def outcome(row, held, tail, mode, positions, opening_equity):
    q=row["initial_qty"]
    lots=row["initial_lots"]
    lot=row["lot_size"]
    pos=SimpleNamespace(**row)
    pos.trail_active=0
    pos.trail_stop_underlying=None
    pos.best_underlying=row["entry_underlying"]
    pos.best_premium=None
    params=held[0]["params"]
    equity=opening_equity
    regime=Trend()
    breach_since=None
    banked=None
    child=None
    child_exit=None
    intent=None
    exchange="NFO" if row["underlying"]=="NIFTY" else "BFO"
    fees=lambda a,b,n: calc_fno_costs(a,b,n,exchange=exchange)
    sign=1 if row["direction"]=="LONG" else -1
    path=held if mode=="N11T" else held+tail
    for snap in path:
        at=stamp(snap["at"])
        bid=snap.get("bid") or 0.
        ask=snap.get("ask") or 0.
        future=snap.get("fut")
        status=regime.update(at,future,row["direction"])
        selected=trend_params(params,pos,status) if mode=="TREND" else params
        basis=bid if bid>0 else snap.get("ltp") or 0.
        decision=evaluate_single_leg_exit(pos,now_ist=at,fut_price=future,exit_px_basis=basis,
            hard_flat=at.hour*60+at.minute>=params["FNO_HARD_FLAT_MIN"],params=selected,
            lock_breach_since=breach_since)
        breach_since=decision.lock_breach_since
        pos.best_premium=decision.best_premium
        if decision.persist_trail:
            pos.best_underlying=decision.best_underlying
            pos.trail_stop_underlying=decision.trail_stop
            pos.trail_active=decision.trail_active
        if mode=="BANK" and decision.trail_newly_armed and not decision.exit_reason and lots>=2 and banked is None and bid>0:
            banked={"at":at.isoformat(),"bid":bid,"qty":(lots//2)*lot}
        if mode=="ADD" and not snap.get("archived") and lots==1 and future and bid>0 and ask>0:
            if child and not child_exit:
                if bid<=child["stop"] or sign*(future-row["entry_underlying"])<=0:
                    child_exit={"at":at.isoformat(),"bid":bid}
            if not child:
                progress=sign*(future-row["entry_underlying"])/abs(row["entry_underlying"]-row["stop_underlying"])
                locked=pos.trail_active and sign*(pos.trail_stop_underlying-row["entry_underlying"])>0
                eligible=(not decision.exit_reason and at.hour*60+at.minute<885 and
                          progress>=ADD_AT_R and locked and status=="SUPPORT")
                realised=sum(p["pnl"] for p in positions if stamp(p["exit_time"])<at)
                equity=opening_equity+realised
                open_premium=sum(p["entry_premium"]*p["initial_qty"] for p in positions
                                 if stamp(p["entry_time"])<=at<stamp(p["exit_time"]))
                if eligible:
                    held_risk=parent_loss_at_stop(row["direction"],future,bid,row["delta_at_entry"],
                        pos.trail_stop_underlying,row["entry_premium"],row["premium_stop"],q,extra_cost(lots),fees)
                    risk=held_risk+child_full_loss(ask,.25,lot,extra_cost(1),fees)
                    if risk<=budget(equity,1.) and open_premium+ask*lot<=.15*equity:
                        if intent and at-intent[0]<=timedelta(seconds=30) and ask<=intent[1]*1.01:
                            child={"at":at.isoformat(),"ask":ask,"stop":round(ask*.75,2),"risk":risk}
                        intent=(at,ask)
                    else:
                        intent=None
                else:
                    intent=None
        if decision.exit_reason and basis>0:
            remainder=q-(banked["qty"] if banked else 0)
            if snap.get("archived") and snap["bid_qty"]<remainder:
                continue
            net=(basis-row["entry_premium"])*remainder-fees(row["entry_premium"],basis,remainder)
            if banked:
                net+=(banked["bid"]-row["entry_premium"])*banked["qty"]-fees(row["entry_premium"],banked["bid"],banked["qty"])
            if child:
                child_exit=child_exit or {"at":at.isoformat(),"bid":bid}
                child["exit"]=child_exit
                child["net"]=(child_exit["bid"]-child["ask"])*lot-fees(child["ask"],child_exit["bid"],lot)
                net+=child["net"]
            return {"status":"CLOSED","exit_time":at.isoformat(),"exit":basis,"net":round(net,4),
                    "reason":decision.exit_reason,"banked":banked,"add":child,
                    "tail":bool(snap.get("archived"))}
    return {"status":"UNRESOLVED","net":None,"banked":banked,"add":child}

def main():
    rows=json.loads((LOCAL/"regular.json").read_bytes())
    quotes=defaultdict(list)
    for line in (LOCAL/"exit-paths.jsonl").open(encoding="utf-8"):
        r=json.loads(line)
        quotes[r["position_id"]].append(r)
    tails=observed_tails()
    result={}
    history={}
    opening=rows["ledger"][0]["bankroll_before"]
    for row in rows["historical_positions"]:
        held=sorted(quotes[row["id"]],key=lambda x:stamp(x["at"]))
        if not held or "params" not in held[0] or held[-1]["exit_reason"]!=row["exit_reason"]:
            continue
        path_tail=[r for r in tails[row["tradingsymbol"]] if stamp(r["at"])>stamp(held[-1]["at"])] if row["entry_date"]==DAY else []
        base=outcome(row,held,[],"N11T",rows["positions"],opening)
        reconciled=(base.get("reason")==row["exit_reason"] and base.get("exit")==row["exit_premium"]
                    and base.get("exit_time")==row["exit_time"] and abs(base["net"]-row["pnl"])<.01)
        record={"symbol":row["tradingsymbol"],"day":row["entry_date"],"samples":len(held),
                "tail_samples":len(path_tail),"parity":reconciled,"N11T":base}
        if reconciled:
            for mode in ("TREND","BANK","ADD"):
                if mode=="ADD" and row["entry_date"]!=DAY:
                    continue
                record[mode]=outcome(row,held,path_tail,mode,rows["positions"],opening)
        target=result if row["entry_date"]==DAY else history
        target[row["id"]]=record
    assert len(result)==3 and all(r["parity"] for r in result.values()),result
    with (HERE/"regular-today-results.json").open("x",encoding="utf-8") as f:
        json.dump({"today":result,"diagnostic_held_paths":history,"unchanged_defined_risk_net":rows["spreads"][0]["pnl"]},f,indent=2)
        f.write("\n")
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
