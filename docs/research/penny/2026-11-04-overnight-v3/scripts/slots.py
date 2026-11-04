import sys; sys.path.insert(0, r"C:/Users/Urveesh/Desktop/trading-sentinel/docs/research/penny/2026-11-04-overnight-v3")
import v3sim as v
from collections import Counter
P = v.load_days()
for name, (days, s, e) in P.items():
    r = v.simulate(days, v.Policy("V2"), v.FillModel(), start=s, end=e, keep=True)
    per = Counter(t["entry_date"] for t in r["trades"])
    nights = [d.date for d in days if s <= d.date <= e]
    dist = Counter(min(per.get(n, 0), 2) for n in nights)
    poolsz = Counter(min(len(v.pool(d, v.Policy("V2"))), 3) for d in days if s <= d.date <= e)
    print(name, "nights", len(nights), "positions/night", dict(sorted(dist.items())), "pool size", dict(sorted(poolsz.items())),
          "capital use %", round(100 * sum(t["notional"] for t in r["trades"]) / (25000 * len(nights)), 1))
