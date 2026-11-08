"""Forward-only candle-book challengers on previously studied NIFTY years."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import hashlib
import json
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"2026-11-02-fno-n11-tolerance"))
import n11t_final as f
from regular_rules import Trend, trend_params
import fno_exit_rules as exits

LOCAL=HERE/"_local"/"annual"
OLD=f.Q.HERE/"_local"
Y=f.Y
Y.EVALS=LOCAL/f"evals-{f.YEAR}"
f.X.LOCAL=f.B.LOCAL=f.T.LOCAL=f.L.U.LOCAL=LOCAL/f.YEAR

def books():
    baseline=f.book("FINAL")
    trend=f.book("R1_TREND_LOCK")
    trend["followup"]="TREND"
    bank=f.book("R1_BANK_TARGET")
    bank["followup"]="BANK"
    continuation=f.book("R2_CONFIRMED_ADD")
    continuation["followup"]="ADD"
    continuation["n11"]["add_any"]=True
    return {"N11T":baseline,"TREND":trend,"BANK":bank,"ADD":continuation}

manage_native=Y.BookReplay._manage
decision_native=exits.evaluate_single_leg_exit
add_native=f.T.maybe_add

def manage(self, book, obs, now):
    mode=self.book.get("followup")
    if not mode:
        return manage_native(self,book,obs,now)
    for leg in book.open.values():
        if not hasattr(leg,"followup_trend"):
            leg.followup_trend=Trend()
        leg.followup_regime=leg.followup_trend.update(now,obs.future.ltp,leg.direction)
    policies=self.policies
    def evaluate(position, *, params, **kwargs):
        chosen=trend_params(params,position,getattr(position,"followup_regime","UNKNOWN"))
        return decision_native(position,params=chosen,**kwargs)
    try:
        if mode=="BANK":
            self.policies=[replace(p,partial_at_target=True) for p in policies]
        if mode=="TREND":
            exits.evaluate_single_leg_exit=evaluate
        return manage_native(self,book,obs,now)
    finally:
        self.policies=policies
        exits.evaluate_single_leg_exit=decision_native


def add(self, book, leg, obs, now):
    if self.book.get("followup")=="ADD" and leg.lots==1:
        if getattr(leg,"followup_regime","UNKNOWN")!="SUPPORT" or not f.L.vol_up(now):
            return
        if not f.T.R.trail_locked(leg.direction,leg.entry_underlying,leg.trail_active,leg.trail_stop_underlying):
            return
    return add_native(self,book,leg,obs,now)


Y.BookReplay._manage=manage
f.T.maybe_add=add
Y.KEEP=tuple(dict.fromkeys((*Y.KEEP,"fills")))

def metrics(r):
    peak=equity=250000.
    fall=0.
    days={}
    closed=[t for t in r["trades"] if t["status"]=="CLOSED"]
    for t in sorted(closed,key=lambda t:t["exit_time"]):
        net=t["net_pnl"]
        day=t["exit_time"][:10]
        days[day]=days.get(day,0)+net
        equity+=net
        peak=max(peak,equity)
        fall=max(fall,peak-equity)
    return {"closed":len(closed),"unresolved":len(r["trades"])-len(closed),
            "net":round(equity-250000,2),"closed_drawdown":round(fall,2),
            "worst_day":round(min([0.]+list(days.values())),2),
            "net_ex_best":round(equity-250000-max([0.]+[t["net_pnl"] for t in closed]),2),
            "daily":days,"notes":r["notes"]}


def main():
    spec=HERE/"regular-freeze.json"
    rel=spec.relative_to(HERE.parents[3]).as_posix()
    frozen=json.loads(spec.read_bytes())
    assert frozen==json.loads(subprocess.check_output(["git","show",f"HEAD:{rel}"]))
    assert all(hashlib.sha256((HERE/k).read_bytes()).hexdigest()==v for k,v in frozen["files"].items())
    chosen=books()
    saved_key=json.loads((OLD/f"keys-fpanel-{f.YEAR}.json").read_bytes())["FINAL"]
    baseline=json.loads((OLD/"evals"/f"{saved_key}.json").read_bytes())
    assert Y.task_key(chosen["N11T"],"year",f.B.C.WINDOW)==saved_key
    f.Z.N.run_books(chosen,3)
    out={}
    for name,book in chosen.items():
        key=Y.task_key(book,"year",f.B.C.WINDOW)
        raw=json.loads((Y.EVALS/f"{key}.json").read_bytes())
        if name=="N11T":
            keys=("tradingsymbol","entry_time","entry_premium","exit_time","exit_premium","exit_reason","net_pnl","status")
            money=lambda r:[tuple(t.get(k) for k in keys) for t in r["trades"]]
            assert money(raw)==money(baseline), "Baseline differs from frozen reference"
        out[name]=metrics(raw)
        print(f.YEAR,name,out[name]["net"],out[name]["closed"],out[name]["notes"].get("n10_added",0),flush=True)
    with (HERE/f"regular-annual-{f.YEAR}.json").open("x",encoding="utf-8") as file:
        json.dump(out,file,indent=2,sort_keys=True)
        file.write("\n")


if __name__=="__main__":
    main()
