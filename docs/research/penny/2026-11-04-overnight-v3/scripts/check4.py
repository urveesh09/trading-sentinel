import sys, statistics as st
from collections import defaultdict
sys.path.insert(0, r"C:/Users/Urveesh/Desktop/trading-sentinel/docs/research/penny/2026-11-04-overnight-v3")
import v3sim as v
P = v.load_days()
arms = [v.Policy("V2"), v.Policy("V2_HI_F3N", rank="strength_hi20", filler="F3", filler_order="night"),
        v.Policy("V2_HI_F3L", rank="strength_hi20", filler="F3", filler_order="value")]
for name, (days, s, e) in P.items():
    for p in arms:
        r = v.simulate(days, p, v.FillModel(), start=s, end=e, keep=True)
        k = defaultdict(list)
        for t in r["trades"]: k["FILL" if t["kind"] == "FILL" else "EDGE"].append(t["net"])
        print(name, f"{p.name:10s}", "trades", len(r["trades"]), {a: (len(b), round(sum(b)), round(st.mean(b), 1)) for a, b in k.items()},
              "years", v.by_year(r["trades"]), "ex_best", r["summary"]["ex_best"], "open_end", r["open_at_end"])
