import sys; sys.path.insert(0, r"C:/Users/Urveesh/Desktop/trading-sentinel/docs/research/penny/2026-11-04-overnight-v3")
import v3sim as v
P = v.load_days()
for name in ("1518", "2326"):
    days, s, e = P[name]
    for f in (1., .5):
        r = v.simulate(days, v.Policy("V2"), v.FillModel(win_fill=f), start=s, end=e)
        print(name, f, r["summary"]["net"], r["summary"]["dd"], r["open_at_end"])
