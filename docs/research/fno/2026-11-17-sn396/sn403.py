"""SN403: N10 against N11 inside the same Gold portfolio (PLAN.md section 1, frozen at 00693405). Learning only; no Gold
rule changes from this slot.

Gold v5 unchanged (sn392.one's wiring: sizing, scale-in, extension, ITM choice, growth from Rs 30,000) fed by six arms:
  with R0.85:    DEPLOYED = N11 + R0.85, NO_STAND + R0.85, N10 + R0.85
  without R0.85: N11, NO_STAND, N10
Paths 2022, 2023-2026, 2022-2026 at Rs 205 / 400 (36 runs; DEPLOYED 2023-2026 @205 must be Rs 8,50,882 / 883).
Disagreement log per path at Rs 205 (signal keys = (entry minute, strike, call)):
  STAND = keys in NO_STAND not in N11 (the stand-aside's suppressions); RETRY = keys in N10 not in NO_STAND (the retry's
  extra entries); LOST = keys in NO_STAND not in N10. For each set, the Gold trades it produced in the arm that took them
  (log rows matched by day and entry minute): count, winners, net.
Runs are cached one by one in _local/sn403-runs.json so a slice can resume; results-sn403.json is written once at the end.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn381"))
import sn392 as P  # noqa: E402

Q, C, L, B, D, G = P.Q, P.C, P.L, P.B, P.D, P.G
OUT = HERE / "results-sn403.json"
CACHE = HERE / "_local" / "sn403-runs.json"
ARMS = {"DEPLOYED": ("N11", "R0.85"), "NO_STAND+R0.85": ("NO_STAND", "R0.85"), "N10+R0.85": ("N10", "R0.85"),
        "N11": ("N11",), "NO_STAND": ("NO_STAND",), "N10": ("N10",)}
PATHS = {"2022": ("2022",), "2023-2026": ("2023", "2024", "2025", "2026"), "2022-2026": ("2022", "2023", "2024", "2025", "2026")}


def one(years, books, stress):
    """sn392.one, also returning Gold's trade log."""
    B.stream = P.stream
    D.DATASETS["2022"] = P.SN366L / "dataset-nifty-2022"
    D.load_year = G.load_2022
    for mod in (B, L, C):
        mod.YEARS = years
    C._YEARS = None
    L.VOLT.clear()
    C.panel = lambda r: {w: {} for w in r}
    old = C.V5["books"]
    C.V5["books"] = books
    try:
        row, days, log = Q.run(stress)
    finally:
        C.V5["books"] = old
    nets = [n for _d, _w, n, _t, _l in days]
    by_m, by_y = collections.defaultdict(float), collections.defaultdict(float)
    for d, _w, n, _t, _l in days:
        by_m[d[:7]] += n
        by_y[d[:4]] += n
    trades = [{"day": x["day"], "i": x["i"], "net": round(float(x["net"]), 2), "expert": x.get("expert"), "opt": x.get("opt"), "lots0": x.get("lots0")} for x in log]
    return {"net": round(sum(nets)), "by_year": {y: round(v) for y, v in sorted(by_y.items())}, "months_positive": sum(v > 0 for v in by_m.values()),
            "months": len(by_m), "worst_month": round(min(by_m.values())), "worst_day": round(min(nets)), "refilled": round(sum(-n for n in nets if n < 0)),
            "trades": len(log), "final_wallet": round(days[-1][1]) if days else None, "log": trades}


def keys(years, book):
    out = set()
    for y in years:
        for s in P.stream(y, book):
            out.add((s["sig_key"][0], s["sig_key"][1], s["sig_key"][2]))
    return out


def produced(log, ks):
    want = {(k[0][:10], B.minute_of(k[0] + ":59")) for k in ks}
    xs = [t for t in log if (t["day"], t["i"]) in want]
    return {"signals": len(ks), "gold_trades": len(xs), "winners": sum(t["net"] > 0 for t in xs), "net": round(sum(t["net"] for t in xs))}


def main():
    if OUT.exists():
        raise SystemExit("SN403 is run once")
    Q.install()
    CACHE.parent.mkdir(exist_ok=True)
    runs = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    for pname, years in PATHS.items():
        for aname, books in ARMS.items():
            for st in (205.0, 400.0):
                k = f"{pname} {aname} @{int(st)}"
                if k in runs:
                    continue
                runs[k] = one(years, books, st)
                CACHE.write_text(json.dumps(runs), encoding="utf-8")
                r = runs[k]
                print(k, json.dumps({x: r[x] for x in ("net", "by_year", "months_positive", "months", "worst_month", "refilled", "trades")}), flush=True)
    assert runs["2023-2026 DEPLOYED @205"]["net"] in (850882, 850883), runs["2023-2026 DEPLOYED @205"]["net"]
    res = {k: {x: v[x] for x in v if x != "log"} for k, v in runs.items()}
    dis = {}
    for pname, years in PATHS.items():
        kn11, kns, kn10 = keys(years, "N11"), keys(years, "NO_STAND"), keys(years, "N10")
        stand, retry, lost = kns - kn11, kn10 - kns, kns - kn10
        dis[pname] = {"N11_signals": len(kn11), "NO_STAND_signals": len(kns), "N10_signals": len(kn10),
                      "STAND (in NO_STAND+R0.85)": produced(runs[f"{pname} NO_STAND+R0.85 @205"]["log"], stand),
                      "STAND (in NO_STAND alone)": produced(runs[f"{pname} NO_STAND @205"]["log"], stand),
                      "RETRY (in N10+R0.85)": produced(runs[f"{pname} N10+R0.85 @205"]["log"], retry),
                      "LOST (in NO_STAND+R0.85)": produced(runs[f"{pname} NO_STAND+R0.85 @205"]["log"], lost),
                      "stand_by_year": {y: len([k for k in stand if k[0][:4] == y]) for y in years}}
    res["disagreements"] = dis
    for pname in PATHS:
        for st in (205, 400):
            base = runs[f"{pname} DEPLOYED @{st}"]["net"]
            res[f"{pname} increments vs DEPLOYED @{st}"] = {a: runs[f"{pname} {a} @{st}"]["net"] - base for a in ARMS}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(dis, indent=1))


if __name__ == "__main__":
    main()
