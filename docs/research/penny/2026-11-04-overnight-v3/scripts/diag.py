"""Per-candidate overnight outcomes (PC entry at official close, exit next open -5bp, Rs 12.5k ticket costs)
for the eligible V2 pool (top-10 then night screen, realism refusals) and the full candidate list, by feature bucket."""
import sys, pickle, statistics as st, datetime as dt
from collections import defaultdict
from pathlib import Path
ROOT = Path(r"C:/Users/Urveesh/Desktop/trading-sentinel")
sys.path.insert(0, str(ROOT / "python-engine"))
from overnight_enrichment import Policy, legacy_lab, eligible
lab = legacy_lab()
V2 = ROOT / "docs/research/penny/2026-11-04-overnight-v2/_local"
OLD = ROOT / "docs/research/penny/2026-11-04-overnight-enrichment/_local/older/days.pkl"
panels = {"1518": (OLD, "2015-01-01", "2018-12-31"), "1922": (V2 / "days-yahoo.pkl", "2019-04-01", "2022-12-30"),
          "2326": (V2 / "days-yahoo.pkl", "2023-01-01", "2026-10-30"), "kite": (V2 / "days-kite.pkl", "2025-07-01", "2026-09-30")}
rows = []
cache = {}
for name, (path, s, e) in panels.items():
    if path not in cache: cache[path] = lab.load(path)
    days = cache[path]
    p = Policy("V2_NATIVE")
    for d in days:
        if not (s <= d.date <= e): continue
        pool = eligible(d, p)
        top = {c.ticker for c in pool[:2]}
        for rank, c in enumerate(pool):
            nx = d.nxt.get(c.ticker)
            if not nx: continue
            entry = c.close; ex = nx["open"] * (1 - 5e-4)
            q = int(12500 // (entry * 1.002))
            if q < 1: continue
            fee = lab.cnc_costs(entry, ex, q)
            gap = (dt.date.fromisoformat(nx["date"]) - dt.date.fromisoformat(d.date)).days
            rows.append(dict(panel=name, date=d.date, t=c.ticker, kind=c.kind, rank=rank, top2=c.ticker in top,
                             gross=ex / entry - 1, gapdays=0, net=(ex - entry) * q - fee, netp=((ex - entry) * q - fee) / (q * entry),
                             wd=dt.date.fromisoformat(d.date).weekday(), npool=len(pool), regime=d.regime, **c.f)); rows[-1]["gapdays"] = gap
pickle.dump(rows, open(ROOT / "docs/research/penny/2026-11-04-overnight-v3/_local/pool-rows.pkl", "wb"))
print(len(rows))
def table(label, key):
    print(f"\n== {label}")
    for name in panels:
        R = [r for r in rows if r["panel"] == name]
        g = defaultdict(list)
        for r in R: g[key(r)].append(r["netp"])
        cells = "  ".join(f"{k}:{100*st.mean(v):+.2f}%({len(v)})" for k, v in sorted(g.items(), key=lambda kv: str(kv[0])))
        print(f"{name}: {cells}")
table("all pool", lambda r: "all")
table("top2 vs rest", lambda r: r["top2"])
table("kind", lambda r: r["kind"])
table("gap days", lambda r: min(r["gapdays"], 4))
table("weekday", lambda r: r["wd"])
table("day ret", lambda r: "<0" if r["ret"] < 0 else "0-5" if r["ret"] < .05 else "5-8" if r["ret"] < .08 else "8-12" if r["ret"] < .12 else "12+")
table("clv", lambda r: round(min(r["clv"], .99) * 4) / 4)
table("from_high", lambda r: "<-6%" if r["from_high"] < -.06 else "-6..-3" if r["from_high"] < -.03 else "-3..-1" if r["from_high"] < -.01 else ">-1%")
table("tv20 (Rs cr)", lambda r: "<0.25" if r["tv20"] < 2.5e6 else "0.25-1" if r["tv20"] < 1e7 else "1-5" if r["tv20"] < 5e7 else "5+")
table("price", lambda r: "<10" if r["price"] < 10 else "10-25" if r["price"] < 25 else "25-60" if r["price"] < 60 else "60+")
table("night_mean", lambda r: "<0.2%" if r["night_mean"] < .002 else "0.2-0.5" if r["night_mean"] < .005 else "0.5-1" if r["night_mean"] < .01 else "1+")
table("rvol", lambda r: "<1.5" if r["rvol"] < 1.5 else "1.5-3" if r["rvol"] < 3 else "3-6" if r["rvol"] < 6 else "6+")
table("ph_rate", lambda r: "<5%" if r["ph_rate"] < .05 else "5-15" if r["ph_rate"] < .15 else "15+")
table("atrp", lambda r: "<4%" if r["atrp"] < .04 else "4-6" if r["atrp"] < .06 else "6-9" if r["atrp"] < .09 else "9+")
table("pool size", lambda r: "1-2" if r["npool"] <= 2 else "3-5" if r["npool"] <= 5 else "6+")
table("ret5", lambda r: "<0" if r["ret5"] < 0 else "0-10" if r["ret5"] < .1 else "10-25" if r["ret5"] < .25 else "25+")
table("prev_ret", lambda r: "<-2" if r["prev_ret"] < -.02 else "-2..2" if r["prev_ret"] < .02 else "2-5" if r["prev_ret"] < .05 else "5+")
table("near_hi20", lambda r: "<-15%" if r["near_hi20"] < -.15 else "-15..-5" if r["near_hi20"] < -.05 else "-5..-1" if r["near_hi20"] < -.01 else ">-1")
table("trend", lambda r: r["regime"][2])
