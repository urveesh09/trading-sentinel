"""N012 round four. Independent signals compete for idle N11T capacity."""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import subprocess

import pandas as pd

import round1 as r
from config import settings
from fno_engine_mom import FnoDirection,MomSignal

HERE=Path(__file__).resolve().parent
Y=r.Y
ENTRY=Y.BookReplay._entry
ROUTE=Y.BookReplay.route


def books():
    base=r.books()["N11T"]
    out={}
    for name in ("OPEN_FLIP","MIDDAY_COIL"):
        b=copy.deepcopy(base)
        b["label"]="N12|"+name
        b["n12"]=name
        # Own immutable TPB-style management, same execution and admission.
        b["members"].append(copy.deepcopy(b["members"][3]))
        out[name]=b
    return out


def extract(frame,now):
    ts=Y.replay._last_closed_bar(frame,now)
    if ts is None:
        return None,None,None
    t=pd.Timestamp(ts)
    prefix=frame.loc[:t]
    today=prefix.loc[t.normalize():t]
    if len(today)<6 or today.index[0]!=t.normalize()+pd.Timedelta(hours=9,minutes=15):
        return ts,None,None
    if not all(y-x==pd.Timedelta(minutes=5) for x,y in zip(today.index,today.index[1:])):
        return ts,None,None
    return ts,today,prefix


def signal_for(mode,frame,now):
    m=now.hour*60+now.minute
    if mode=="OPEN_FLIP" and not 590<=m<660:
        return None
    if mode=="MIDDAY_COIL" and not 660<=m<830:
        return None
    bar,today,prefix=extract(frame,now)
    if today is None:
        return None
    current=today.iloc[-1]
    close=float(current.close)
    highs=today.high.to_list()
    lows=today.low.to_list()
    closes=today.close.to_list()
    atr=sum(max(h-l,abs(h-prev),abs(l-prev)) for h,l,prev in
            zip(highs[-6:],lows[-6:],closes[-7:-1]))/6
    if atr<=0:
        return None
    if mode=="OPEN_FLIP":
        earlier=prefix.loc[prefix.index<pd.Timestamp(bar).normalize()]
        if earlier.empty or len(today)<7:
            return None
        prev_day=earlier.index[-1].normalize()
        prev=earlier.loc[prev_day:]
        if len(prev)<50:
            return None
        opening=float(today.open.iloc[0])
        prev_close=float(prev.close.iloc[-1])
        prior_range=float(prev.high.max()-prev.low.min())
        final=prev.tail(12)
        if prior_range<=0 or abs(opening-prev_close)<.25*prior_range:
            return None
        side=-1 if opening>prev_close else 1
        edge=float(final.high.max() if side==-1 else final.low.min())
        if side*(edge-opening)<=0 or side*(closes[-3]-edge)>=0:
            return None
        if not all(side*(z-edge)>0 for z in closes[-2:]):
            return None
        volume=today.volume.clip(lower=0)
        if volume.sum()<=0:
            return None
        vwap=float((((today.high+today.low+today.close)/3)*volume).sum()/volume.sum())
        if side*(close-vwap)<=0:
            return None
        extreme=max(highs[-3:]) if side==-1 else min(lows[-3:])
        distance=side*(close-extreme)+.1*atr
        if not .5*atr<=distance<=1.5*atr or side*(prev_close-close)<1.8*distance:
            return None
        target=prev_close
    else:
        early=today.iloc[:6]
        opening=float(early.open.iloc[0])
        initial=float(early.close.iloc[-1])-opening
        opening_width=float(early.high.max()-early.low.min())
        if opening_width<=0 or abs(initial)<.60*opening_width or len(today)<10:
            return None
        side=1 if initial>0 else -1
        coil=today.iloc[-5:-1]
        coil_hi=float(coil.high.max())
        coil_lo=float(coil.low.min())
        width=coil_hi-coil_lo
        edge=coil_hi if side==1 else coil_lo
        floor=coil_lo if side==1 else coil_hi
        if width<=0 or width>.45*opening_width or side*(floor-opening)<.65*abs(initial):
            return None
        if not 0<side*(close-edge)<=.35*opening_width:
            return None
        distance=side*(close-floor)+.1*atr
        if not .5*atr<=distance<=1.5*atr:
            return None
        target=close+side*2*distance
    return MomSignal(bar_ts=bar,direction=FnoDirection.LONG if side==1 else FnoDirection.SHORT,
                     close=close,atr=atr,stop_underlying=close-side*distance,
                     target_underlying=target,strategy="N12_"+mode)


def entry(self,book,obs,frame,day,now):
    mode=self.book.get("n12")
    if mode not in ("OPEN_FLIP","MIDDAY_COIL"):
        return ENTRY(self,book,obs,frame,day,now)
    self.n12_book=book
    before=book.next_id
    try:
        result=ENTRY(self,book,obs,frame,day,now)
        if book.next_id!=before and self.leg_member.get(before)==5:
            self.n12_executed=now.date()
            self.notes["n12_new_entry"]+=1
        return result
    finally:
        self.n12_book=None


def route(self,frame,regime,now):
    sig=ROUTE(self,frame,regime,now)
    mode=self.book.get("n12")
    if mode not in ("OPEN_FLIP","MIDDAY_COIL") or sig.direction is not None:
        return sig
    if self.n12_book.open or getattr(self,"n12_executed",None)==now.date():
        return sig
    if r.f.L.R.stand_aside(r.f.L.vol_at(now,.9),r.f.L.paper_before(now),20):
        return sig
    extra=signal_for(mode,frame,now)
    if extra is None:
        return sig
    self._fired=5
    self._n02_decision={"selected_profile":"N12","selector_policy":"STATIC","selection_asof":None,
                        "signal_bar":extra.bar_ts,"selection_latest_label_exit":None,
                        "origin":"N12_NEW","entry_expert":mode,"entry_gate":"FLAT"}
    settings.FNO_MAX_LOTS=min(settings.FNO_MAX_LOTS,1)
    settings.FNO_MAX_LOTS_PROVEN=min(settings.FNO_MAX_LOTS_PROVEN,1)
    self.notes["n12_new_signal_ticks"]+=1
    return extra


Y.BookReplay._entry=entry
Y.BookReplay.route=route


def main():
    spec=HERE/"round4-freeze.json"
    rel=spec.relative_to(r.ROOT).as_posix()
    cfg=json.loads(spec.read_bytes())
    assert cfg==json.loads(subprocess.check_output(["git","show",f"HEAD:{rel}"],cwd=r.ROOT))
    assert all(hashlib.sha256((HERE/name).read_bytes()).hexdigest()==sha for name,sha in cfg["files"].items())
    r.verify_freeze()
    variants=books()
    r.f.Z.N.run_books(variants,2)
    out={k:r.metrics(r.raw_for(b)) for k,b in variants.items()}
    for k,v in out.items():
        print(r.YEAR,k,v["net"],v["closed"],v["worst_day"],v["drawdown_pct"],v["notes"].get("n12_new_entry",0),flush=True)
    with (HERE/f"round4-{r.YEAR}.json").open("x",encoding="utf-8") as f:
        json.dump(out,f,indent=2,sort_keys=True)
        f.write("\n")


if __name__=="__main__":
    main()
