import pickle, statistics as st
from collections import defaultdict
rows = pickle.load(open(r"C:/Users/Urveesh/Desktop/trading-sentinel/docs/research/penny/2026-11-04-overnight-v3/_local/pool-rows.pkl", "rb"))
def liq(r): return "thin<0.5cr" if r["tv20"] < 5e6 else "mid0.5-2cr" if r["tv20"] < 2e7 else "liq2cr+"
def pr(r): return "<15" if r["price"] < 15 else "15-30" if r["price"] < 30 else "30+"
def nm(r): return "nm<0.4" if r["night_mean"] < .004 else "nm0.4-0.8" if r["night_mean"] < .008 else "nm0.8+"
for label, f in [("liq x price", lambda r: (liq(r), pr(r))), ("liq x night", lambda r: (liq(r), nm(r))), ("liq x at20high", lambda r: (liq(r), r["near_hi20"] > -.01)),
                 ("liq x weekend", lambda r: (liq(r), r["gapdays"] >= 3))]:
    print("\n==", label)
    keys = sorted({f(r) for r in rows})
    for k in keys:
        cells = []
        for p in ("1518", "1922", "2326", "kite"):
            v = [r["netp"] for r in rows if r["panel"] == p and f(r) == k]
            cells.append(f"{p}:{100*st.mean(v):+.2f}%({len(v)})" if v else f"{p}:-")
        print(k, "  ".join(cells))
# fraction of the pool by liquidity
for p in ("1518", "1922", "2326", "kite"):
    R = [r for r in rows if r["panel"] == p]
    print(p, {k: round(sum(liq(r) == k for r in R) / len(R), 3) for k in ("thin<0.5cr", "mid0.5-2cr", "liq2cr+")},
          "median tv20 Rs lakh", round(st.median(r["tv20"] for r in R) / 1e5, 1), "median day value Rs lakh", round(st.median(r["tv"] for r in R) / 1e5, 1))
