"""N012 round one. Exact N11/T controls and two causal low-day TPB changes."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from anatomy import DATASETS, trades

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
PREV=HERE.parent/"2026-11-05-fno-expiry-followup"
YEAR=os.environ.get("N12_YEAR","2024")
sys.path[:0]=[str(PREV),str(HERE.parent/"2026-11-02-fno-n11-tolerance")]
if YEAR=="2022":
    import nifty_2022 as prior
    f=prior.final
    _,diag=trades("2022","DIAG")
    f.L.U.paper_rows=lambda:tuple(sorted(
        ((datetime.fromisoformat(t["exit_time"]),t) for t in diag["trades"] if t["status"]=="CLOSED"),
        key=lambda r:(r[0],r[1]["entry_time"])))
else:
    os.environ["N08_YEAR"]=YEAR
    os.environ.pop("N09_CARRY",None)
    import n11t_final as f

import fno_exit_rules as exits
from config import settings
from fno_engine_mom import MomSignal

Y=f.Y
LOCAL=HERE/"_local"
YEAR_LOCAL=LOCAL/YEAR
Y.EVALS=YEAR_LOCAL/"evals"
f.X.LOCAL=f.B.LOCAL=f.T.LOCAL=f.L.U.LOCAL=YEAR_LOCAL
WINDOW=f.B.C.WINDOW
ENTER_NATIVE=Y.BookReplay._entry
ROUTE_NATIVE=Y.BookReplay.route
MANAGE_NATIVE=Y.BookReplay._manage
EXIT_NATIVE=exits.evaluate_single_leg_exit


def books():
    n11=f.L.n11_book("T|BASE")
    n11t=f.book("FINAL")
    return {
        "N11":n11, "N11T":n11t,
        "PRICE_WAIT":{**copy.deepcopy(n11t),"label":"N12|PRICE_WAIT","n12":"PRICE_WAIT"},
        "PROTECT":{**copy.deepcopy(n11t),"label":"N12|PROTECT","n12":"PROTECT"},
    }


def low_member(self):
    return self._fired==4 and self.members[4]["name"]=="TPB"


def entry(self,book,obs,frame,day,now):
    if self.book.get("n12")=="PRICE_WAIT":
        self.n12_now_future=obs.future.ltp
    return ENTER_NATIVE(self,book,obs,frame,day,now)


def route(self,frame,regime,now):
    if self.book.get("n12")!="PRICE_WAIT":
        return ROUTE_NATIVE(self,frame,regime,now)
    pending=getattr(self,"n12_wait",None)
    future=self.n12_now_future
    if pending and pending["at"].date()!=now.date():
        pending=self.n12_wait=None
    if pending:
        sig=pending["sig"]
        side=1 if sig.direction.value=="LONG" else -1
        initial=pending["future"]
        risk=abs(initial-sig.stop_underlying)
        signed_move=side*(future-initial)
        minute=now.hour*60+now.minute
        rejected=(now-pending["at"]>timedelta(minutes=6) or minute>=840 or signed_move<-.40*risk or
                  f.L.R.stand_aside(f.L.vol_at(now,.9),f.L.paper_before(now),20))
        if rejected:
            self.notes["n12_wait_cancelled"]+=1
            self.n12_wait=None
        elif now>pending["at"] and signed_move<=-.20*risk:
            self.n12_wait=None
            self._fired=4
            self._n02_decision=pending["decision"]
            settings.FNO_MAX_LOTS=min(settings.FNO_MAX_LOTS,pending["ceiling"])
            settings.FNO_MAX_LOTS_PROVEN=min(settings.FNO_MAX_LOTS_PROVEN,pending["proven"])
            self.notes["n12_wait_price_reached"]+=1
            return copy.copy(sig)
        else:
            return MomSignal(bar_ts=sig.bar_ts,reject_reason="n12:waiting")
    sig=ROUTE_NATIVE(self,frame,regime,now)
    if sig.direction is None or not low_member(self):
        return sig
    if sig.bar_ts==getattr(self,"n12_waited_bar",None):
        return MomSignal(bar_ts=sig.bar_ts,reject_reason="n12:already_considered")
    self.n12_waited_bar=sig.bar_ts
    self.n12_wait={"sig":copy.copy(sig),"at":now,"future":future,"decision":copy.deepcopy(self._n02_decision),
                   "ceiling":settings.FNO_MAX_LOTS,"proven":settings.FNO_MAX_LOTS_PROVEN}
    self.notes["n12_wait_created"]+=1
    self._fired=None
    return MomSignal(bar_ts=sig.bar_ts,reject_reason="n12:waiting")


def manage(self,book,obs,now):
    if self.book.get("n12")!="PROTECT" or not book.open:
        return MANAGE_NATIVE(self,book,obs,now)
    frame=getattr(self,"_frame",None)
    if frame is None:
        return MANAGE_NATIVE(self,book,obs,now)
    bar=Y.replay._last_closed_bar(frame,now)
    close=float(frame.loc[bar].close) if bar and bar in frame.index else None
    low_ids={k for k in book.open if self.leg_member.get(k)==4}

    def decide(position, *, fut_price, exit_px_basis, **kwargs):
        native=EXIT_NATIVE(position,fut_price=fut_price,exit_px_basis=exit_px_basis,**kwargs)
        if (position.id not in low_ids or native.exit_reason or native.trail_active
                or close is None or fut_price is None or exit_px_basis<=0):
            return native
        side=1 if position.direction=="LONG" else -1
        risk=abs(position.entry_underlying-position.stop_underlying)
        best=native.best_underlying
        if risk<=0 or best is None:
            return native
        earned=side*(best-position.entry_underlying)>=risk
        lost=side*(close-position.entry_underlying)<=.10*risk and side*(fut_price-position.entry_underlying)<=.10*risk
        if earned and lost:
            self.notes["n12_protected"]+=1
            return replace(native,exit_reason="n12_earned_progress_lost",persist_trail=False)
        return native

    exits.evaluate_single_leg_exit=decide
    try:
        return MANAGE_NATIVE(self,book,obs,now)
    finally:
        exits.evaluate_single_leg_exit=EXIT_NATIVE


Y.BookReplay._entry=entry
Y.BookReplay.route=route
Y.BookReplay._manage=manage


def money(raw):
    keys=("tradingsymbol","entry_time","entry_premium","entry_qty","exit_time",
          "exit_premium","exit_reason","net_pnl","status")
    return [tuple(t.get(k) for k in keys) for t in raw["trades"]]


def metrics(raw):
    closed=[t for t in raw["trades"] if t["status"]=="CLOSED"]
    cash=peak=250000.
    dd=fall=0.
    daily={}
    for t in sorted(closed,key=lambda t:t["exit_time"]):
        d=t["exit_time"][:10]
        daily[d]=daily.get(d,0.)+t["net_pnl"]
        cash+=t["net_pnl"]
        peak=max(peak,cash)
        dd=max(dd,peak-cash)
        fall=max(fall,(peak-cash)/peak)
    return {"net":round(cash-250000.,2),"closed":len(closed),"unresolved":len(raw["trades"])-len(closed),
            "closed_drawdown":round(dd,2),"drawdown_pct":round(fall*100,5),
            "worst_day":round(min([0.]+list(daily.values())),2),
            "worst_trade":round(min([0.]+[t["net_pnl"] for t in closed]),2),
            "daily":daily,"notes":raw["notes"],"funnel":raw["funnel"]}


def raw_for(book):
    key=Y.task_key(book,"year",WINDOW)
    return json.loads((Y.EVALS/f"{key}.json").read_bytes())


def verify_freeze():
    freeze=HERE/"round1-freeze.json"
    path=freeze.relative_to(ROOT).as_posix()
    data=json.loads(freeze.read_bytes())
    assert data==json.loads(subprocess.check_output(["git","show",f"HEAD:{path}"],cwd=ROOT))
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==data["runner_sha256"]
    manifest=DATASETS[YEAR]/"manifest.json"
    assert hashlib.sha256(manifest.read_bytes()).hexdigest()==data["data_manifest_sha256"][YEAR]
    for label in ("N11","N11T"):
        source,_=trades(YEAR,label)
        assert hashlib.sha256(source.read_bytes()).hexdigest()==data["controls_sha256"][YEAR][label]


def main():
    verify_freeze()
    models=books()
    controls={k:models[k] for k in ("N11","N11T")}
    f.Z.N.run_books(controls,2)
    for label,model in controls.items():
        _,reference=trades(YEAR,label)
        assert money(raw_for(model))==money(reference),(YEAR,label,"baseline mismatch")
    print(YEAR,"both controls exact",flush=True)
    f.Z.N.run_books({k:v for k,v in models.items() if k not in controls},2)
    out={label:metrics(raw_for(model)) for label,model in models.items()}
    path=HERE/f"round1-{YEAR}.json"
    with path.open("x",encoding="utf-8") as file:
        json.dump(out,file,indent=2,sort_keys=True)
        file.write("\n")
    for label,v in out.items():
        print(YEAR,label,v["net"],v["closed"],v["worst_day"],v["drawdown_pct"],flush=True)


if __name__=="__main__":
    main()
