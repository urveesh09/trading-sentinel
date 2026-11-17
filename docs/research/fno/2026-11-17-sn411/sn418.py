"""SN418: does Gold's stand-aside help across starting points? (PLAN.md section 1, frozen at e5cc95b7; details fixed here
before any number.) Learning only; the current source is retained unless the matched comparison shows value.

A. One lot, no growth (wallet kind "one": one lot every trade, no volatility halving, no growth steps), Rs 30,000:
   DEPLOYED (N11 + R0.85) vs NO_STAND + R0.85, and N11 vs NO_STAND; paths 2022, 2023-26, 2022-26; Rs 205 / 400.
   The stand-aside's blocked signals (NO_STAND keys not in N11) priced at one lot in the NO_STAND + R0.85 run.
B. Quarterly starts: Gold's Rs 30k growth wallet (GOLD_30K) from each quarter start Jan 2022 - Jul 2026 (from_day), the
   2022-26 path; DEPLOYED vs NO_STAND + R0.85 at Rs 205 / 400: net over the next four quarters (to the end of data if
   shorter) and to the end; the dates the wallet first reached 45k / 67.5k / 1.0125 lakh (growth steps).
   Reported: starts where DEPLOYED leads, the median difference. Runs cached in _local/sn418-runs.json (slices).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gold  # noqa: E402

OUT = HERE / "results-sn418.json"
CACHE = HERE / "_local" / "sn418-runs.json"
ONE = ("1 lot", 30000.0, "one", None)
STARTS = [f"{y}-{m:02d}-01" for y in range(2022, 2027) for m in (1, 4, 7, 10) if f"{y}-{m:02d}-01" <= "2026-07-01"]
ARMS_A = {"DEPLOYED": gold.DEPLOYED, "NO_STAND+R0.85": gold.NO_STAND_R, "N11": ("N11",), "NO_STAND": ("NO_STAND",)}
PATHS = {"2022": gold.Y22, "2023-2026": gold.Y2326, "2022-2026": gold.Y2226}


def keys(years, book):
    return {x["sig_key"] for y in years for x in gold.P.stream(y, book)}


def main():
    if OUT.exists():
        raise SystemExit("SN418 is run once")
    CACHE.parent.mkdir(exist_ok=True)
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    if "parity" not in cache:
        cache["parity"] = gold.parity()
    res = {"parity_deployed_2023_26_205": cache["parity"]}
    for pname, years in PATHS.items():
        for aname, books in ARMS_A.items():
            for st in (205.0, 400.0):
                k = f"A {pname} {aname} @{int(st)}"
                if k not in cache:
                    days, log, _ = gold.run(years, books, st, wallet=ONE)
                    cache[k] = {**gold.summary(days, log), "log": [{"day": x["day"], "i": x["i"], "net": round(float(x["net"]), 2)} for x in log]}
                    CACHE.write_text(json.dumps(cache), encoding="utf-8")
                    print(k, cache[k]["net"], flush=True)
                res[k] = {x: v for x, v in cache[k].items() if x != "log"}
    for pname, years in PATHS.items():
        stand = keys(years, "NO_STAND") - keys(years, "N11")
        want = {(k[0][:10], gold.B.minute_of(k[0] + ":59")) for k in stand}
        for st in (205, 400):
            xs = [t["net"] for t in cache[f"A {pname} NO_STAND+R0.85 @{st}"]["log"] if (t["day"], t["i"]) in want]
            res[f"A {pname} blocked signals at one lot @{st}"] = {"signals": len(stand), "gold_trades": len(xs), "winners": sum(x > 0 for x in xs), "net": round(sum(xs))}
            res[f"A {pname} stand-aside effect at one lot @{st}"] = {"with_R0.85": res[f"A {pname} DEPLOYED @{st}"]["net"] - res[f"A {pname} NO_STAND+R0.85 @{st}"]["net"],
                                                                    "without_R0.85": res[f"A {pname} N11 @{st}"]["net"] - res[f"A {pname} NO_STAND @{st}"]["net"]}
    for s in STARTS:
        for aname, books in (("DEPLOYED", gold.DEPLOYED), ("NO_STAND+R0.85", gold.NO_STAND_R)):
            for st in (205.0, 400.0):
                k = f"B {s} {aname} @{int(st)}"
                if k in cache:
                    continue
                days, log, _ = gold.run(gold.Y2226, books, st, from_day=s)
                d1 = (dt.date.fromisoformat(s) + dt.timedelta(days=365)).isoformat()
                steps = {}
                for d, w, *_r in days:
                    for lvl in (45000, 67500, 101250):
                        if w >= lvl - 1 and lvl not in steps:
                            steps[lvl] = d
                cache[k] = {"net_4q": round(sum(n for d, _w, n, *_r in days if s <= d < d1)), "net_to_end": round(sum(n for d, _w, n, *_r in days if d >= s)),
                            "steps": {str(a): b for a, b in steps.items()}, "sessions": sum(1 for d, *_r in days if d >= s)}
                CACHE.write_text(json.dumps(cache), encoding="utf-8")
                print(k, cache[k]["net_4q"], cache[k]["net_to_end"], flush=True)
    for st in (205, 400):
        d4 = [cache[f"B {s} DEPLOYED @{st}"]["net_4q"] - cache[f"B {s} NO_STAND+R0.85 @{st}"]["net_4q"] for s in STARTS]
        de = [cache[f"B {s} DEPLOYED @{st}"]["net_to_end"] - cache[f"B {s} NO_STAND+R0.85 @{st}"]["net_to_end"] for s in STARTS]
        res[f"B quarterly starts @{st}"] = {"starts": len(STARTS), "deployed_leads_4q": sum(x > 0 for x in d4), "ties_4q": sum(x == 0 for x in d4),
                                           "median_diff_4q": round(float(np.median(d4))), "deployed_leads_to_end": sum(x > 0 for x in de),
                                           "median_diff_to_end": round(float(np.median(de))), "diff_4q_by_start": dict(zip(STARTS, d4)),
                                           "diff_to_end_by_start": dict(zip(STARTS, de))}
    res["B runs"] = {k: v for k, v in cache.items() if k.startswith("B ")}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "B runs"}, indent=1))


if __name__ == "__main__":
    main()
