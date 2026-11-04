"""Iteration 1: re-price v2 and the cost route with the forward Production evidence."""
import sys, json, time
from pathlib import Path
ROOT = Path(r"C:/Users/Urveesh/Desktop/trading-sentinel")
sys.path.insert(0, str(ROOT / "python-engine"))
from overnight_enrichment import Policy, legacy_lab, risk_history, simulate
lab = legacy_lab()
V2 = ROOT / "docs/research/penny/2026-11-04-overnight-v2/_local"
OLD = ROOT / "docs/research/penny/2026-11-04-overnight-enrichment/_local/older/days.pkl"
panels = {"older": (OLD, "2015-01-01", "2018-12-31"), "yahoo1922": (V2 / "days-yahoo.pkl", "2019-04-01", "2022-12-30"),
          "yahoo2326": (V2 / "days-yahoo.pkl", "2023-01-01", "2026-10-30")}
pols = [Policy("V2_NATIVE"), Policy("V3_COST_ROUTE", regular_fraction=.5, route_rule="positive_net")]
out = {}
cache = {}
for name, (path, s, e) in panels.items():
    if path not in cache:
        days = lab.load(path); cache[path] = (days, risk_history(days))
    days, hist = cache[path]
    for rb, xb, f in [(36, 5, 1.), (36, 5, .5), (100, 5, 1.), (100, 5, .5), (135, 5, 1.), (135, 5, .5), (36, 110, 1.)]:
        for p in pols:
            if p.name == "V2_NATIVE" and rb != 36: continue
            r = simulate(days, p, start=s, end=e, regular_bps=rb, exit_bps=xb, winning_close_fill=f, keep=False, histories=hist)
            sm = r["summary"]
            key = f"{name} {p.name} reg{rb} exit{xb} fill{f}"
            out[key] = {k: sm.get(k) for k in ("closes", "net", "dd", "pf", "win_rate")}
            print(key, out[key], flush=True)
json.dump(out, open(ROOT / "docs/research/penny/2026-11-04-overnight-v3/_local/i1.json", "w"), indent=1)
