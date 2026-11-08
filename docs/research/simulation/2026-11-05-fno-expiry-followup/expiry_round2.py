"""Round two: enter a confirmed box breakout only after a same-direction retest."""
from datetime import datetime,timedelta,time
import json
from pathlib import Path
import sqlite3

import expiry_study as study

HERE=Path(__file__).resolve().parent
MAX_WAIT=timedelta(minutes=5)
PULLBACK=.15
native=study.p.breakout_signal


def retest(state, now, spot, future):
    direction=native(state,now,spot,future)
    waiting=state.get("followup_retest")
    if direction:
        state["followup_retest"]={"direction":direction,"until":now+MAX_WAIT,
                                  "peak":spot,"last_future":future,"pullback":False}
        return None
    if waiting is None:
        return None
    if spot is None or future is None or now>waiting["until"] or now.time()>=time(15):
        state.pop("followup_retest",None)
        return None
    box=state["box"]
    sign=1 if waiting["direction"]=="UP" else -1
    edge=box["hi"] if sign==1 else box["lo"]
    if sign*(spot-edge)<=0:
        state.pop("followup_retest",None)
        return None
    mark=sign*spot
    peak=sign*waiting["peak"]
    if mark>peak:
        waiting["peak"]=spot
    if peak-mark>=PULLBACK*(box["hi"]-box["lo"]):
        waiting["pullback"]=True
    resumed=waiting["pullback"] and mark>peak and sign*(future-waiting["last_future"])>0
    waiting["last_future"]=future
    if resumed:
        state.pop("followup_retest",None)
        return waiting["direction"]
    return None


def main():
    base=json.loads((HERE/"expiry-results.json").read_bytes())
    masters=json.loads((study.LOCAL/"expiry-masters.json").read_bytes())
    con=sqlite3.connect((study.LOCAL/"expiry-input.sqlite").as_uri()+"?mode=ro",uri=True)
    con.row_factory=sqlite3.Row
    out={}
    for day,row in base.items():
        if row["coverage"]!="SAMPLED":
            continue
        u=row["underlying"]
        ticks=con.execute("select day,underlying,ts,spot,fut,quotes from expiry_paper_ticks where day=? and underlying=? order by ts",(day,u)).fetchall()
        book=study.master(masters[day],u,day)
        study.p.breakout_signal=retest
        try:
            results={}
            for delay in (1,2):
                positions,checks,signals=study.legacy(ticks,book,day,u,matched=True,delay=delay)
                results[str(delay)]={**study.summary(positions),"checks":checks,"signals":signals}
            out[day]=results
        finally:
            study.p.breakout_signal=native
        print(day,u,*(r["net"] for r in results.values()),flush=True)
    with (HERE/"expiry-retest-results.json").open("x",encoding="utf-8") as f:
        json.dump(out,f,indent=2,sort_keys=True)
        f.write("\n")


if __name__=="__main__":
    main()
