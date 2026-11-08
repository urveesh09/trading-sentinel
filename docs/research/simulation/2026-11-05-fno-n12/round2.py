"""N012 round two. Recover proven impulses and contain overlapping directional exposure."""
from __future__ import annotations

from collections import Counter
from datetime import timedelta
import copy
import hashlib
import json
from pathlib import Path
import subprocess

import round1 as r
from config import settings
from fno_costs import calc_fno_costs
from fno_engine_mom import MomSignal
from fno_n11 import extra_cost
import pandas as pd

HERE=Path(__file__).resolve().parent
Y=r.Y
route_previous=Y.BookReplay.route
entry_previous=Y.BookReplay._entry


def books():
    base=r.books()["N11T"]
    recovery=copy.deepcopy(base)
    recovery["label"]="N12|RECOVERY"
    recovery["n12"]="RECOVERY"
    recovery["n11"].pop("stand")
    cluster=copy.deepcopy(base)
    cluster["label"]="N12|CLUSTER"
    cluster["n12"]="CLUSTER"
    return {"RECOVERY":recovery,"CLUSTER":cluster}


def impulse(frame,now,side):
    """Range and efficiency read only bars with all five minutes already over."""
    bar=Y.replay._last_closed_bar(frame,now)
    if bar is None:
        return False
    stamp=pd.Timestamp(bar)
    opening=stamp.normalize()+pd.Timedelta(hours=9,minutes=15)
    first_end=opening+pd.Timedelta(minutes=25)
    if stamp<first_end+pd.Timedelta(minutes=10):
        return False
    early=frame.loc[opening:first_end]
    recent=frame.loc[stamp-pd.Timedelta(minutes=25):stamp]
    if len(early)!=6 or len(recent)!=6:
        return False
    width=float(early.high.max()-early.low.min())
    closes=recent.close.to_list()
    total=sum(abs(b-a) for a,b in zip(closes,closes[1:]))
    if width<=0 or total<=0:
        return False
    edge=float(early.high.max() if side==1 else early.low.min())
    return (side*(closes[-1]-closes[0])>=.35*total
            and side*(closes[-1]-float(early.open.iloc[0]))>=.5*width
            and all(side*(c-edge)>0 for c in closes[-2:]))


def enough_space(leg,obs,now):
    side=1 if leg.direction=="LONG" else -1
    distance=abs(leg.entry_underlying-leg.stop_underlying)
    future=obs.future.ltp
    if distance<=0 or future<=0 or side*(future-leg.entry_underlying)<.5*distance:
        return False
    quote=obs.options.get(leg.token)
    if quote is None or quote.bid<=0 or quote.last_trade_time is None:
        return False
    age=(now-quote.last_trade_time).total_seconds()
    if not 0<=age<=settings.FNO_MAX_QUOTE_AGE_SEC:
        return False
    fees=calc_fno_costs(leg.entry_premium,quote.bid,leg.qty)+extra_cost(leg.lots)
    return (quote.bid-leg.entry_premium)*leg.qty>fees


def entry(self,book,obs,frame,day,now):
    if self.book.get("n12")=="CLUSTER":
        self.n12_cluster=(book,obs)
    try:
        return entry_previous(self,book,obs,frame,day,now)
    finally:
        self.n12_cluster=None


def route(self,frame,regime,now):
    sig=route_previous(self,frame,regime,now)
    if sig.direction is None:
        return sig
    mode=self.book.get("n12")
    if mode=="RECOVERY" and r.f.L.R.stand_aside(r.f.L.vol_at(now,.9),r.f.L.paper_before(now),20):
        side=1 if sig.direction.value=="LONG" else -1
        if not impulse(frame,now,side):
            return MomSignal(bar_ts=sig.bar_ts,reject_reason="n11:stand_aside")
        settings.FNO_MAX_LOTS=min(settings.FNO_MAX_LOTS,1)
        settings.FNO_MAX_LOTS_PROVEN=min(settings.FNO_MAX_LOTS_PROVEN,1)
        self.notes["n12_recovery_signal_ticks"]+=1
    if mode=="CLUSTER":
        book,obs=self.n12_cluster
        parents=[leg for leg in book.open.values() if leg.direction==sig.direction.value]
        if any(not enough_space(leg,obs,now) for leg in parents):
            return MomSignal(bar_ts=sig.bar_ts,reject_reason="n12:unpaid_directional_cluster")
    return sig


Y.BookReplay._entry=entry
Y.BookReplay.route=route


def main():
    freeze=HERE/"round2-freeze.json"
    rel=freeze.relative_to(r.ROOT).as_posix()
    spec=json.loads(freeze.read_bytes())
    assert spec==json.loads(subprocess.check_output(["git","show",f"HEAD:{rel}"],cwd=r.ROOT))
    for name,expected in spec["files"].items():
        assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==expected
    r.verify_freeze()
    selected=books()
    r.f.Z.N.run_books(selected,2)
    out={k:r.metrics(r.raw_for(b)) for k,b in selected.items()}
    for k,v in out.items():
        print(r.YEAR,k,v["net"],v["closed"],v["worst_day"],v["drawdown_pct"],flush=True)
    with (HERE/f"round2-{r.YEAR}.json").open("x",encoding="utf-8") as file:
        json.dump(out,file,indent=2,sort_keys=True)
        file.write("\n")

if __name__=="__main__":
    main()
