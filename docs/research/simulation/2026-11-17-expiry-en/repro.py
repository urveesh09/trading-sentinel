import json, time
import en_base as B
t0=time.time(); T=B.tapes(); both=T[2024]+T[2025]
out={}
for sc in ("ordinary","adverse","catastrophe"):
    r=B.R.run(both,B.E032,sc,details=True); s=r["summary"]
    out[sc]=dict(net=s["net"],worst=s["worst"],dd=s["drawdown"],trades=s["trades"])
    if sc=="ordinary":
        tick=[]
        for d in r["days"]:
            for p in d["positions"]:
                t=[x for x in both if x.day==d["day"]][0]
                tick.append(dict(day=d["day"],dir=p["direction"],decision_min=int(t.minute[p["decision_i"]]),entry_min=int(t.minute[p["entry_i"]]),lots=p["lots"],entry=p["entry"],net=p["net"],
                                 exits=[(e["reason"],e["lots"],e["price"],int(t.minute[e["i"]])) for e in p["events"][1:]]))
        json.dump(tick,open("e032-tickets-insample.json","w"),indent=1)
print(out, round(time.time()-t0,1))
