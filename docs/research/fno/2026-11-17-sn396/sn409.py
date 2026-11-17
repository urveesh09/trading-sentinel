"""SN409 (own): Gold's clocks (PLAN.md section 2, frozen at 00693405; details fixed here before any SN409 number).

N11's stream minute i is the decision bar's close (entry_time hh:mm:59): Gold fills there, the instant of the decision with
zero latency. Here every stream entry minute i and N11 exit minute j is shifted by k minutes through the stream only
(Gold's files untouched; sn403.one's wiring):
  k = -1  a fill one minute BEFORE the decision (lookahead: a diagnostic of how steep prices are around Gold's entries)
  k =  0  as deployed (must reproduce DEPLOYED 2023-26 @205 = Rs 8,50,882 / 883)
  k = +1, +2  one / two minutes of latency on entries and on N11's exits
Arms DEPLOYED (N11 + R0.85) and N10 + R0.85; paths 2023-2026 and 2022 (Rs 30k each); Rs 205 / 400. Reported: net,
by year, months positive, worst month, refills, trades; the change per minute of latency.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn403 as T  # noqa: E402

P, B = T.P, T.B
OUT = HERE / "results-sn409.json"
SHIFTS = (-1, 0, 1, 2)
ARMS = {"DEPLOYED": ("N11", "R0.85"), "N10+R0.85": ("N10", "R0.85")}
PATHS = {"2023-2026": ("2023", "2024", "2025", "2026"), "2022": ("2022",)}


def shifted(k, base):
    def stream(year, book="N11"):
        out = []
        for s in base(year, book):
            i, j = s["i"] + k, s["j"] + k
            if not 0 <= i < j <= 374:
                continue
            out.append({**s, "i": i, "j": j})
        return out
    return stream


def main():
    if OUT.exists():
        raise SystemExit("SN409 is run once")
    T.Q.install()
    res = {}
    orig = P.stream
    for k in SHIFTS:
        for pname, years in PATHS.items():
            for aname, books in ARMS.items():
                for st in (205.0, 400.0):
                    P.stream = shifted(k, orig)
                    try:
                        r = T.one(years, books, st)
                    finally:
                        P.stream = orig
                    r.pop("log", None)
                    key = f"shift {k:+d} {pname} {aname} @{int(st)}"
                    res[key] = r
                    print(key, json.dumps({x: r[x] for x in ("net", "by_year", "months_positive", "worst_month", "refilled", "trades")}), flush=True)
    assert res["shift +0 2023-2026 DEPLOYED @205"]["net"] in (850882, 850883), res["shift +0 2023-2026 DEPLOYED @205"]["net"]
    for pname in PATHS:
        for aname in ARMS:
            for st in (205, 400):
                base = res[f"shift +0 {pname} {aname} @{st}"]["net"]
                res[f"delta vs shift 0 {pname} {aname} @{st}"] = {f"{k:+d}": res[f"shift {k:+d} {pname} {aname} @{st}"]["net"] - base for k in SHIFTS}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    for k, v in res.items():
        if k.startswith("delta"):
            print(k, v)


if __name__ == "__main__":
    main()
