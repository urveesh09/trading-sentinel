"""Offline E01.1 exam. Immutable exports, native money, causal next-bar orders.

Ten-second opening-strike evidence is a CONDITIONAL EXIT PANEL, not a book.
No SDK/client/scheduler is run. All nonlocal files are opened read-only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date, datetime, time, timedelta
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
OLD = HERE.parent / "2026-11-02-expiry-e011"
SOURCE = Path.home() / "sentinel-operations/breeze-history-20261029/data/expiry-10second-20261103"
LOCAL = HERE / "_local"
sys.path.insert(0, str(OLD))
import e011_lab as L
import arms as M
import panel as P
import sept as Z
EP = L.EP

SEEN = {("NIFTY", d) for d in Z.DAYS}
LOT = {"NIFTY": 65, "SENSEX": 20}  # current-size normalization, NOT dated lot history
FIXED = {k: M.ARMS[k] for k in ("C", "E01", "E011", "E011R", "E011_S20")}
FIXED.update({k: M.ENTRY_READINGS[k] for k in ("E011_BOX35", "E011_BAND50")})
FLAT = time(15, 29, 30)  # decide before the final two fully requested bars


def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2, default=str, allow_nan=False) + "\n", encoding="utf-8")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def no_network():
    def refused(*args, **kwargs):
        raise RuntimeError("Offline research: network is disabled")
    socket.socket.connect = refused
    socket.create_connection = refused


def window(book, day):
    if (book, day) in SEEN:
        return "seen"
    if day[:4] == "2025":
        return "test2025"
    return "development" if day < "2026-07-01" else "validation"


def snapshot():
    assert not (HERE / "coverage.json").exists(), "Do not overwrite an evidence binding"
    LOCAL.mkdir(exist_ok=True)
    (LOCAL / "initial-owner-diff.patch").write_bytes(subprocess.check_output(
        ["git", "diff", "--", ".gitignore", "docs/SYSTEM_GUIDE.md", "docs/NEXT_AGENT_PLAN.md", "docs/HANDOVER_CHECKLIST.md"], cwd=ROOT))
    data = LOCAL / "data"
    data.mkdir()
    sessions, hashes = [], {}
    verified = json.loads((SOURCE / "verification.json").read_text())
    for book in ("NIFTY", "SENSEX"):
        coverage = json.loads((SOURCE / book.lower() / "coverage.json").read_text())
        for item in sorted(coverage["sessions"], key=lambda s: s["date"]):
            day = item["date"]
            assert "2025-01-01" <= day <= "2026-10-01"
            src = SOURCE / book.lower() / Path(item["csv"]).name
            dst = data / src.name
            shutil.copyfile(src, dst)
            assert sha(dst) == sha(src)
            hashes[str(dst.relative_to(HERE))] = sha(dst)
            invalid, missing, counts, stamps, strikes = 0, 0, Counter(), defaultdict(set), set()
            with open(dst, newline="") as f:
                for row in csv.DictReader(f):
                    assert row["underlying"] == book and row["expiry"] == day
                    o, h, lo, c, v = [float(row[k]) for k in ("open", "high", "low", "close", "volume")]
                    invalid += not (all(math.isfinite(x) for x in (o, h, lo, c, v)) and 0 < lo <= min(o, c)
                                    <= max(o, c) <= h and v >= 0 and int(row["invalid_volume_source_seconds"]) == 0)
                    stamp = row["datetime_ist"]
                    assert stamp[:10] == day and stamp not in stamps[row["opt"]]
                    stamps[row["opt"]].add(stamp)
                    counts[row["opt"]] += 1
                    missing += int(row["missing_source_seconds"])
                    strikes.add(row["strike"])
            assert len(strikes) == 1 and sum(counts.values()) == item["rows"]
            paired = stamps["CE"] & stamps["PE"]
            needed = {f"{day} {(datetime(2000,1,1,12,58,50)+timedelta(seconds=10*k)).strftime('%H:%M:%S')}"
                      for k in range(907)}  # 12:58:50 through 15:29:50
            absent = len(needed - paired)
            sessions.append(dict(book=book, day=day, window=window(book, day), csv=dst.name,
                                 rows=sum(counts.values()), grid=item["full_10second_grid"],
                                 missing_pairs_research_window=absent, invalid_rows=invalid,
                                 missing_source_seconds=missing,
                                 eligible=absent == 0 and invalid == 0,
                                 reason="COMPLETE_GRID_WITH_SOURCE_HOLES" if not absent and not invalid
                                 else "INCOMPLETE_WINDOW_OR_INVALID_ROWS"))
    dump(HERE / "coverage.json", dict(sessions=sessions, hashes=hashes,
        source_verification_sha256=sha(SOURCE / "verification.json"),
        source_totals={b: {k:v for k,v in d.items() if k != "details"} for b,d in verified["books"].items()},
        minute_inventory={"NIFTY2025": "53 expiry sessions, 624156 option minute rows; separate model required",
                          "NIFTY2026": "no same-day-expiry one-minute option rows in current source",
                          "SENSEX": "same-day option evidence is one-second/derived ten-second"}))
    print(Counter((s["book"], s["window"], s["eligible"]) for s in sessions))


class Session:
    """Completed ten-second prices; no future prices/volumes in decision quotes."""
    partial = True

    def __init__(self, info, truncate=None):
        self.info = info
        self.day, self.underlying = info["day"], info["book"]
        self.date = date.fromisoformat(self.day)
        self.exchange = "NFO" if self.underlying == "NIFTY" else "BFO"
        self.schedule = EP.fee_schedule(self.exchange)
        self.step = 50.0 if self.underlying == "NIFTY" else 100.0
        self.lot = LOT[self.underlying]
        self.p75 = json.loads((OLD / "spreads.json").read_text())["p75"]
        bars = defaultdict(dict)
        with open(LOCAL / "data" / info["csv"], newline="") as f:
            for row in csv.DictReader(f):
                self.strike = float(row["strike"])
                if row["datetime_ist"][11:] >= "12:58:50":
                    bars[row["datetime_ist"]][row["opt"]] = row
        stamps = sorted(bars)
        if truncate is not None:
            stamps = stamps[:truncate]
        self.now = [datetime.fromisoformat(t).replace(tzinfo=EP.IST) + timedelta(seconds=10) for t in stamps]
        self.clock = [t.time() for t in self.now]
        self._bars = [bars[t] for t in stamps]
        self.n = len(stamps)
        self.names = [f"{self.underlying}-{self.day}-{self.strike:g}-{k}" for k in ("CE", "PE")]
        self.kinds = dict(zip(self.names, ("CE", "PE")))
        self._contract = {n: L.Contract(200000000+j, n, self.underlying, self.date, self.strike, k, self.lot)
                          for j,(n,k) in enumerate(self.kinds.items())}
        raw, self.spot = [], []
        for i, b in enumerate(self._bars):
            x = self.strike + float(b["CE"]["close"]) - float(b["PE"]["close"]) if len(b) == 2 else None
            raw.append(x)
            recent = raw[max(0, i-2):i+1]
            self.spot.append(statistics.median(recent) if all(x is not None for x in recent) else None)
        self.fut = list(self.spot)  # parity proxy, explicitly not independent confirmation
        self.anchor = [self.spot[max(0, i-1)] for i in range(self.n)]
        self._signals = {}

    def half(self, price):
        return (self.p75[Z._bucket(price)] or .05) / 2

    def quote(self, i, symbol):
        b = self._bars[i].get(self.kinds.get(symbol))
        if b is None:
            return None
        price = float(b["close"])
        bid, ask = Z._down(price-self.half(price)), Z._up(price+self.half(price))
        depth = int(float(b["volume"]) * Z.DEPTH_SHARE)
        return EP.Quote(bids=((bid, depth),) if bid > 0 and depth >= self.lot else (),
                        asks=((ask, depth),) if depth >= self.lot else (), ltp=price, ts=self.now[i])

    def fill(self, i, symbol, side, lots, adverse=False, max_price=None):
        """The pending market order uses only this NEXT bar; never an entry signal."""
        b = self._bars[i].get(self.kinds.get(symbol))
        if b is None:
            return 0, None
        price = float(b["high" if side == "BUY" else "low"] if adverse else b["open"])
        # Stress doubles spread AND uses the worst price of the execution bar.
        half = self.half(price) * (2 if adverse else 1)
        price = Z._up(price+half) if side == "BUY" else Z._down(price-half)
        depth = int(float(b["volume"]) * Z.DEPTH_SHARE) // self.lot
        if price <= 0 or (max_price is not None and price > max_price):
            return 0, None
        return min(lots, depth), price

    def contracts_near(self, i):
        return {(self.strike, self.kinds[n]): self._contract[n] for n in self.names}

    def quoted_chain(self, i):
        return {(self.strike, self.kinds[n]): (self._contract[n], self.quote(i,n)) for n in self.names
                if self.quote(i,n) is not None}

    def atm(self, spot):
        return float(round(spot/self.step)*self.step)

    def contract(self, symbol):
        return self._contract[symbol]


def simulate(S, admission, ticket, adverse=False, *, failed_back=False, manager_override=None):
    """Single independent pocket; decisions on completed bars, fills one bar later.

    Entry order quantity and cap come from the decision quote; future execution
    never increases quantity. A higher ask may reduce affordable whole lots.
    Exit orders latch; unfilled banks retry only while the trigger still holds.
    """
    i, symbol, rule = admission
    if i+1 >= S.n or S.now[i+1]-S.now[i] != timedelta(seconds=getattr(S,"seconds",10)):
        return None
    q = S.quote(i, symbol)
    planned, prices = EP.affordable_fill([(q,S.lot)],2500,EP.C_MAX_LOTS,S.schedule)
    if not planned:
        return None
    # Market order is sized before submission, with the original risk ceiling.
    lots, price = S.fill(i+1,symbol,"BUY",planned,adverse)
    while lots and EP.worst_case_loss(price,lots,S.lot,S.schedule) > 2500:
        lots -= 1
    if not lots:
        return None
    flat = getattr(S,"flat",FLAT)
    policy = replace(ticket.policy, flat_at=flat)
    pos = L._open(S,i+1,"X",S.contract(symbol),price,lots,policy)
    pos["decision_ts"] = S.now[i].isoformat()
    pos["admission_rule"] = rule
    pos["window"] = S.info["window"]
    pos["missed_exit_bars"] = 0
    pos["max_liquidation_net"] = -pos["max_loss"]
    pos["min_liquidation_net"] = 0.0
    pos["mfe_multiple_after_exit"] = 1.0
    manager = manager_override or L._bank_manager(ticket) or EP.manage_position
    state, _ = L.signal_stream(S)
    pending = None
    closed_at = None
    for k in range(i+1,S.n):
        if pending is not None:
            qty, why = pending
            qty, sale = S.fill(k,symbol,"SELL",min(qty,pos["lots_open"]),adverse)
            if qty:
                EP._sell(pos,qty,sale,why,S.now[k])
            else:
                pos["missed_exit_bars"] += 1
            if pos["status"] != "OPEN":
                closed_at = k
                break
            pending = (pos["lots_open"],why) if why != "BANK_HALF" else None
        quote = S.quote(k,symbol)
        if quote is not None and quote.bid is not None:
            qty = pos["lots_open"]*S.lot
            mark = pos["net_pnl"] + (quote.bid-price)*qty - EP.sell_charges(quote.bid,qty,S.schedule)
            pos["max_liquidation_net"] = max(pos["max_liquidation_net"],mark)
            pos["min_liquidation_net"] = min(pos["min_liquidation_net"],mark)
        if pending is not None:
            continue
        if k == S.n-1:
            continue  # no later execution bar, so no invented terminal sale
        if quote is None or quote.bid is None:
            if S.clock[k] >= flat:
                pending = (pos["lots_open"],"FLAT_TIME")
            continue
        broken = failed_back and EP.failed_break(state,pos["opt_type"],S.spot[k],ticket.back)
        action = manager(pos,policy,quote.bid,S.now[k],structure_broken=broken)
        if action:
            pending = action
    if pos["status"] == "OPEN":
        pos["status"] = "UNRESOLVED_AT_DATA_END"
        pos["assumed_pnl"] = round(-price*pos["lots_open"]*S.lot,2)
    if closed_at is not None:
        highs = [float(b[S.kinds[symbol]]["high"]) for b in S._bars[closed_at+1:] if S.kinds[symbol] in b]
        pos["mfe_multiple_after_exit"] = max(highs,default=price)/price
    return pos


def audit_position(pos):
    ev = pos["_events"]
    sold = [e for e in ev if e["action"] != "BUY"]
    assert pos["lots"] == sum(e["lots"] for e in sold)+pos["lots_open"]
    gross = round(sum((e["price"]-pos["entry_price"])*e["lots"]*pos["lot_size"] for e in sold),2)
    costs = round(sum(e["charges"] for e in ev),2)
    assert abs(gross-pos["gross"]) <= .02 and abs(costs-pos["costs"]) <= .02
    assert abs(pos["net_pnl"]-(gross-costs)) <= .02
    assert pos["max_loss"] <= 2500.01 and L.net([pos]) >= -pos["max_loss"]-.02
    assert datetime.fromisoformat(pos["decision_ts"]) < datetime.fromisoformat(pos["entry_ts"])
    assert all(e["ts"] > pos["entry_ts"] for e in sold)


def stats(positions):
    if not positions:
        return dict(tickets=0,net=None,without_best=None,worst=None,drawdown=None)
    daily = defaultdict(float)
    for p in positions:
        daily[p["day"]] += L.net([p])
    total=peak=dd=0.0
    for day in sorted(daily):
        total += daily[day]
        peak=max(peak,total)
        dd=max(dd,peak-total)
    vals=[L.net([p]) for p in positions]
    wins=sum(v>0 for v in vals)
    pos_sum=sum(v for v in vals if v>0)
    neg_sum=-sum(v for v in vals if v<0)
    return dict(tickets=len(vals),sessions=len(daily),net=round(total,2),
        without_best=round(total-max(daily.values()),2),worst=round(min(daily.values()),2),drawdown=round(dd,2),
        wins=wins,losses=len(vals)-wins,win_rate=round(wins/len(vals),4),
        profit_factor=round(pos_sum/neg_sum,4) if neg_sum else None,
        fees=round(sum(p["costs"] for p in positions),2),
        filled_fee_pnl=round(sum(p["net_pnl"] for p in positions),2),
        assumed_pnl=round(sum(p.get("assumed_pnl") or 0 for p in positions),2),
        unresolved=sum(p["status"] != "CLOSED" for p in positions),
        reached3x=sum(p["peak"] >= 3*p["entry_price"] for p in positions),
        exits=dict(Counter(p["_events"][-1]["action"] if p["status"] == "CLOSED" else p["status"] for p in positions)),
        daily={d:round(v,2) for d,v in sorted(daily.items())})


def native_parity():
    """Archived source controls, no rewriting an older receipt."""
    bad=[]; n=0
    fields=("entry_price","lots","peak","stop","banked","gross","costs","net_pnl","status","lots_open","max_loss")
    for adverse in (False,True):
        for day,u in L.recorded_keys():
            suffix="adverse" if adverse else "ordinary"
            stored=json.loads((OLD/"_local/evals"/f"{day}-{u}-NATIVE_E011-{suffix}.json").read_text())
            S=L.Recorded(day,u,adverse)
            for arm,play in (("E01","CE01"),("E011","CE011"),("E011R","CE011R")):
                expected=[p for p in stored["positions"] if p["play"] == play]
                mine=L.run_c(S,FIXED[arm],"X")
                if len(mine)!=len(expected): bad.append((day,arm,"count")); continue
                for x,y in zip(mine,expected):
                    n+=1
                    for f in fields:
                        if x[f]!=y[f]: bad.append((day,arm,f,x[f],y[f]))
                    # Recorded failed-break events also contain index/line context;
                    # the fast lab omits record-only annotations. Compare every
                    # clock, fill and money field explicitly, as the old parity did.
                    economic=lambda rows:[tuple(e.get(k) for k in ("ts","action","lots","price","gross","charges","net","fill_model")) for e in rows]
                    left=economic(x["_events"])
                    right=economic(y["events"])
                    if left!=right: bad.append((day,arm,"events"))
    dump(HERE/"parity.json",dict(legs=n,mismatches=bad))
    print("ARCHIVE_PARITY",n,"legs",len(bad),"mismatches")
    assert not bad


def bindings():
    paths=[HERE/"study.py",HERE/"minutes.py",HERE/"candidates.py",HERE/"test_study.py",HERE/"PLAN.md",HERE/"configuration.json",HERE/"coverage.json",HERE/"minute-coverage.json",
           OLD/"e011_lab.py",OLD/"panel.py",OLD/"sept.py",OLD/"arms.py",OLD/"spreads.json",
           ROOT/"python-engine/expiry_paper.py",ROOT/"python-engine/fno_costs.py",ROOT/"python-engine/cost_schedules.py"]
    return {str(p.relative_to(ROOT)):sha(p) for p in paths}


def freeze():
    assert not (HERE/"freeze.json").exists()
    data=dict(json.loads((HERE/"coverage.json").read_text())["hashes"])
    data["_local/minutes.sqlite"]=sha(LOCAL/"minutes.sqlite")
    dump(HERE/"freeze.json",dict(source=bindings(),data=data,
         fees={x:EP.fee_schedule(x) for x in ("NFO","BFO")},python=sys.version,
         head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
         note="Commit this file before exam. Development only was inspected before freeze."))


def verify_freeze():
    f=json.loads((HERE/"freeze.json").read_text())
    assert f["source"]==bindings(),"Source/configuration changed since freeze"
    assert f["fees"]=={x:EP.fee_schedule(x) for x in ("NFO","BFO")},"Effective fees changed"
    for p,h in f["data"].items(): assert sha(HERE/p)==h,p
    subprocess.run(["git","ls-files","--error-unmatch",str((HERE/"freeze.json").relative_to(ROOT))],cwd=ROOT,check=True,capture_output=True)


def run(group, include_candidates=False):
    no_network()
    if group != "development": verify_freeze()
    suffix="-candidates" if group=="development" and include_candidates else ""
    target=HERE/f"results-{group}{suffix}.json"
    assert not target.exists(),"Results are immutable; retain a failed/corrected run separately"
    arms=dict(FIXED)
    if include_candidates:
        from candidates import CANDIDATES, MANAGERS
        arms.update(CANDIDATES)
    else:
        MANAGERS={}
    manifest=json.loads((HERE/"coverage.json").read_text())
    selected=[s for s in manifest["sessions"] if s["window"]==group]
    by_arm={n:{x:[] for x in ("ordinary","adverse")} for n in arms}
    availability=[]
    for info in selected:
        if not info["eligible"]:
            availability.append(dict(book=info["book"],day=info["day"],status="UNAVAILABLE",reason=info["reason"]))
            continue
        S=Session(info)
        state,signals=L.signal_stream(S)
        available=[]
        for i,d in signals:
            available.append(dict(at=S.clock[i].isoformat(),direction=d,
                                  recorded_strike_eligible=L._pick(S,i,d,FIXED["E011"]) is not None))
        admissions=P.admissions(S)
        availability.append(dict(book=info["book"],day=info["day"],status="PARTIAL",box=state["box"],
            signals=available,panel_admissions=len(admissions),
            full_chain_entries="UNAVAILABLE: opening strike is not a complete afternoon chain"))
        for a in admissions:
            for scenario,adverse in (("ordinary",False),("adverse",True)):
                for name,ticket in arms.items():
                    # Entry arms cannot be scored on the expanded-band, non-book panel.
                    if name in ("E011_BOX35","E011_BAND50"):
                        continue
                    p=simulate(S,a,ticket,adverse,manager_override=MANAGERS.get(name))
                    if p is not None:
                        audit_position(p)
                        by_arm[name][scenario].append(p)
        print(group,info["book"],info["day"],"breaks",len(signals),"panel",len(admissions),flush=True)
    summaries={}
    for name,scenarios in by_arm.items():
        summaries[name]={}
        for scenario,positions in scenarios.items():
            summaries[name][scenario]={"all":stats(positions)}
            for book in LOT:
                summaries[name][scenario][book]=stats([p for p in positions if p["underlying"]==book])
            for kind in ("CE","PE"):
                summaries[name][scenario][kind]=stats([p for p in positions if p["opt_type"]==kind])
    paired=[]
    for name in arms:
        if name in ("E011_BOX35","E011_BAND50"): continue
        for scenario in ("ordinary","adverse"):
            key=lambda p:(p["day"],p["underlying"],p["decision_ts"],p["symbol"],p["admission_rule"])
            base={key(p):p for p in by_arm["E011"][scenario]}
            cand={key(p):p for p in by_arm[name][scenario]}
            assert base.keys()==cand.keys()
            for k in base:
                assert all(base[k][f]==cand[k][f] for f in ("entry_ts","entry_price","lots","max_loss"))
            paired.append(dict(arm=name,scenario=scenario,tickets=len(base),entry_mismatches=0))
    dump(target,dict(group=group,model="CAUSAL_NEXT_BAR_CONDITIONAL_PANEL_v1",summaries=summaries,
                     availability=availability,paired=paired,positions=by_arm))
    print(json.dumps({n:{s:x["all"] for s,x in v.items()} for n,v in summaries.items() if n in ("E01","E011")},indent=1))


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("snapshot","parity","freeze","verify","run"))
    p.add_argument("--group",choices=("development","validation","test2025","seen"))
    p.add_argument("--candidates",action="store_true")
    a=p.parse_args()
    if a.command=="snapshot": snapshot()
    elif a.command=="parity": native_parity()
    elif a.command=="freeze": freeze()
    elif a.command=="verify": verify_freeze()
    else: run(a.group,a.candidates)
