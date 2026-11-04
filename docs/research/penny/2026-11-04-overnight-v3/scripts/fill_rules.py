import sys, pickle, statistics as st
from collections import defaultdict
sys.path.insert(0, r"C:/Users/Urveesh/Desktop/trading-sentinel/docs/research/penny/2026-11-04-overnight-v2")
import lab
V2 = r"C:/Users/Urveesh/Desktop/trading-sentinel/docs/research/penny/2026-11-04-overnight-v2/_local/"
def netp(close, on):
    ex = close * (1 + on) * (1 - 5e-4); q = int(12500 // (close * 1.002))
    if q < 1: return None
    return ((ex - close) * q - lab.cnc_costs(close, ex, q)) / (q * close)
rules = {
  "all": lambda f: True,
  "F1 nm>=.5% & at20hi & ret>=0": lambda f: f["night_mean"] >= .005 and f["near_hi20"] > -.01 and f["ret"] >= 0,
  "F2 nm>=.8%": lambda f: f["night_mean"] >= .008,
  "F3 ret>=5% clv>=.5 rvol>=2 nm>=.1%": lambda f: f["ret"] >= .05 and f["clv"] >= .5 and f["rvol"] >= 2 and f["night_mean"] >= .001,
  "F4 at20hi rvol>=1.5 nm>=.2%": lambda f: f["near_hi20"] > -.01 and f["rvol"] >= 1.5 and f["night_mean"] >= .002,
  "F5 nm>=.5% & ret>=2%": lambda f: f["night_mean"] >= .005 and f["ret"] >= .02,
}
for src in ("yahoo", "kite"):
    rows = pickle.load(open(V2 + f"allrows-{src}.pkl", "rb"))
    print("\n##", src, len(rows))
    for name, rule in rules.items():
        per = defaultdict(list); nights = defaultdict(set)
        for t, d, f, on, oc, ph in rows:
            if f["from_high"] >= -.001 and f["ret"] >= .019: continue      # realism refusal
            if not rule(f): continue
            n = netp(f["price"], max(-.5, min(.5, on)))
            if n is None: continue
            per_key = "2019-22" if d < "2023" else "2023-26"
            if src == "kite": per_key = "kite"
            liq = "dv<1.25cr" if f["tv"] < 1.25e7 else "dv>=1.25cr"
            per[(per_key, "all")].append(n); per[(per_key, liq)].append(n); nights[per_key].add(d)
        print(f"{name:38s}", "  ".join(f"{k[0]}/{k[1]}:{100*st.mean(v):+.2f}%({len(v)})" for k, v in sorted(per.items())),
              " nights:", {k: len(v) for k, v in nights.items()})
