"""Compare native E03.2 and a matched-risk legacy A breakout on sampled expiry quotes."""
from __future__ import annotations

from collections import Counter
from contextlib import closing
from datetime import date, datetime, time
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "_local"
sys.path.insert(0, str(HERE.parents[3] / "python-engine"))
import expiry_e02 as e
import expiry_paper as p
from fno_instruments import Contract

TODAY = "2026-11-05"
START = 25000.0
FLAT = time(15, 14)


def master(entries, underlying, day):
    if not entries:
        raise ValueError(f"No dated master for {day}")
    by_symbol = {}
    for entry in entries:
        for raw in entry["contracts"]:
            assert raw["expiry"] == day and raw["underlying"] == underlying
            con = Contract(int(raw["instrument_token"]), raw["tradingsymbol"], underlying,
                           date.fromisoformat(day), float(raw["strike"]), raw["instrument_type"],
                           int(raw["lot_size"]), float(raw["tick_size"]))
            previous = by_symbol.setdefault(con.tradingsymbol, con)
            if previous != con:
                raise ValueError(f"Conflicting same-day contract: {con.tradingsymbol}")
    return SimpleNamespace(by_symbol=by_symbol)


def e032(ticks, book, day, work):
    base = work / "replay"
    source = Path(str(base) + ".expiry-paper.db")
    source.unlink(missing_ok=True)
    target = Path(e.path_for(base, e.E032))
    target.unlink(missing_ok=True)
    with closing(sqlite3.connect(source)) as c:
        c.execute("create table expiry_paper_ticks(day text,underlying text,ts text,spot real,fut real,quotes text, primary key(day,underlying,ts))")
        c.executemany("insert into expiry_paper_ticks values(?,?,?,?,?,?)", [tuple(r) for r in ticks])
        c.commit()
    result = {}
    for row in ticks:
        now = datetime.fromisoformat(row["ts"])
        result = e.run_tick(base, enabled=True, now=now, book=book, variant=e.E032)
    return e.positions(base,e.E032), result.get("decision_counts",{}), result.get("day",{})


def legacy(ticks, book, day, underlying, *, matched, delay):
    """A's own break and exit rules with risk-limited later-packet entry."""
    state = dict(box_status="BUILDING", box_samples=[], box=None, pending=None,
                 armed={"UP": True, "DOWN": True})
    exchange = e.UNDERLYINGS[underlying]["exchange"]
    step = 100 if underlying=="SENSEX" else 50
    schedule = p.fee_schedule(exchange)
    positions, signals = [], []
    active = pending = None
    checks = Counter()
    spent = 0.
    for i,row in enumerate(ticks):
        now = datetime.fromisoformat(row["ts"])
        raw = json.loads(row["quotes"])
        legs = raw.get("legs",{})
        spot, fut = row["spot"],row["fut"]
        if active:
            quote = e.logged_quote(legs.get(active["symbol"]))
            if active["exit_pending"]:
                p._try_exit(active,quote,active["lots_open"],active["exit_pending"],now)
            elif matched and now.time()>=FLAT:
                p._try_exit(active,quote,active["lots_open"],"FLAT_TIME",now)
            elif quote and quote.fresh(now) and quote.bid is not None:
                action = p.manage_position(active,p.POLICIES["A"],quote.bid,now,
                    structure_broken=p.failed_break(state,active["opt_type"],spot))
                if action:
                    p._try_exit(active,quote,*action,now)
            elif now.time()>=p.POLICIES["A"].flat_at:
                p._try_exit(active,None,active["lots_open"],"FLAT_TIME",now)
            if active["status"]=="CLOSED":
                active=None

        p.update_box(state,now.time(),spot,fut)
        direction=p.breakout_signal(state,now,spot,fut)
        if direction:
            signals.append({"at":now.isoformat(),"side":direction})
            if not active and len(positions)<p.A_MAX_TRADES and (not matched or now.time()<time(15)):
                side=1 if direction=="UP" else -1
                atm=round(spot/step)*step
                budget=min(1250*e.ticket_scale(e.E032,side),5000-spent) if matched else 2500+min(0.,sum(x["net_pnl"] for x in positions))
                cap=min(p.A_MAX_LOTS,int(e.E032.max_lots*e.ticket_scale(e.E032,side))) if matched else p.A_MAX_LOTS
                kind="CE" if side==1 else "PE"
                for strike in (atm,atm+side*step):
                    con=next((c for c in book.by_symbol.values() if c.strike==strike and c.instrument_type==kind),None)
                    q=e.logged_quote(legs.get(con.tradingsymbol)) if con else None
                    reason=p._quote_refusal((con,q) if con and q else None,now,p.A_MAX_SPREAD)
                    if reason:
                        checks[reason]+=1
                        continue
                    if matched:
                        lots,limit=e._lots(q,budget,cap,schedule,e.E032.chase,con.lot_size)
                    else:
                        lots,prices=p.affordable_fill([(q,con.lot_size)],budget,cap,schedule)
                        limit=prices[0] if lots else None
                    if lots:
                        pending=(i+delay,con,lots,limit,budget,now)
                        break
                    checks["decision_budget_or_depth"]+=1
        if pending and not active and i>=pending[0]:
            _,con,lots,limit,budget,decided=pending
            if (now-decided).total_seconds()>60 or (matched and now.time()>=time(15)):
                checks["expired"]+=1
                pending=None
                continue
            q=e.logged_quote(legs.get(con.tradingsymbol))
            if p._quote_refusal((con,q) if q else None,now,p.A_MAX_SPREAD):
                checks["fill_quote"]+=1
                continue
            filled,price=p.walk(q.asks,lots,con.lot_size)
            if not filled:
                checks["fill_depth"]+=1
                continue
            if price>limit+1e-9:
                checks["fill_price_chase"]+=1
                continue
            risk=p.worst_case_loss(price,filled,con.lot_size,schedule)
            if risk>budget+.001:
                checks["fill_budget"]+=1
                continue
            active=p._new_position(day,underlying,"A",exchange,con,price,filled,now,schedule)
            active["id"]=len(positions)+1
            positions.append(active)
            spent+=risk
            pending=None
    return positions, dict(checks), signals


def summary(positions):
    closed=[p for p in positions if p["status"]=="CLOSED"]
    return {"net":round(sum(p["net_pnl"] for p in closed),2),"closed":len(closed),
            "unresolved":len(positions)-len(closed),
            "trades":[{k:x[k] for k in ("symbol","entry_ts","entry_price","lots","net_pnl","status","max_loss","_events")}
                      for x in positions]}


def main():
    marks=json.loads((LOCAL/"expiry-masters.json").read_bytes())
    src=sqlite3.connect((LOCAL/"expiry-input.sqlite").as_uri()+"?mode=ro",uri=True)
    src.row_factory=sqlite3.Row
    work=LOCAL/"expiry-replay"
    work.mkdir(exist_ok=True)
    out={}
    for day,underlying,s in src.execute("select day,underlying,state from expiry_paper_days order by day"):
        ticks=src.execute("select day,underlying,ts,spot,fut,quotes from expiry_paper_ticks where day=? and underlying=? order by ts",
                          (day,underlying)).fetchall()
        if not ticks:continue
        first=json.loads(ticks[0]["quotes"])
        # The old compact schema does not establish executable whole-lot depth.
        if not isinstance(next(iter(first.get("legs",{}).values()),None),dict):
            out[day]={"underlying":underlying,"coverage":"NO_FIVE_LEVEL_PACKET"}
            continue
        book=master(marks[day],underlying,day)
        native,counts,risk=e032(ticks,book,day,work)
        a,checks,signals=legacy(ticks,book,day,underlying,matched=False,delay=0)
        later,late_checks,_=legacy(ticks,book,day,underlying,matched=True,delay=1)
        stress,stress_checks,_=legacy(ticks,book,day,underlying,matched=True,delay=2)
        out[day]={"underlying":underlying,"ticks":len(ticks),"coverage":"SAMPLED",
                  "E032":{**summary(native),"checks":counts,"risk":risk},
                  "A_NATIVE":{**summary(a),"signals":signals,"checks":checks},
                  "A_MATCHED":{**summary(later),"checks":late_checks},
                  "A_MATCHED_DELAY":{**summary(stress),"checks":stress_checks},
                  "recorded_A":[dict(r) for r in src.execute("select symbol,entry_ts,entry_price,lots,status,net_pnl from expiry_paper_positions where day=? and play='A'",(day,))]}
        print(day,underlying,*(out[day][k]["net"] for k in ("E032","A_NATIVE","A_MATCHED","A_MATCHED_DELAY")),
              counts.get("signal",{}),flush=True)
    current=out[TODAY]
    assert current["E032"]["closed"]==current["E032"]["unresolved"]==0
    a=current["A_NATIVE"]
    recorded=current["recorded_A"]
    assert a["closed"]==len(recorded)==1 and a["trades"][0]["symbol"]==recorded[0]["symbol"]
    assert a["trades"][0]["entry_ts"]==recorded[0]["entry_ts"] and abs(a["net"]-recorded[0]["net_pnl"])<.01
    with (HERE/"expiry-results.json").open("x",encoding="utf-8") as f:json.dump(out,f,indent=2,sort_keys=True)


if __name__=="__main__":
    main()
