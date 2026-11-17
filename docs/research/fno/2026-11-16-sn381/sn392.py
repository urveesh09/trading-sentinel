"""SN392: Gold's signal source across five years (PLAN.md section 2, frozen at c6e99cee; details fixed here before any
SN392 number). Learning only: 2022 is seen now and no Gold rule changes from this slot.

Gold v5 unchanged (sizing, scale-in, extension, ITM choice, growth from Rs 30,000 = ow.GOLD_30K) fed by:
  DEPLOYED   N11 + R0.85 panel books (C.V5["books"], as Production runs it)
  NO_STAND   N11's panel NO_STAND book (N11 without the stand-aside)
  N10        N10 retry (N11's control book "N10", = R2_THIRD_CW, which equals the stored N10 trade for trade)
Streams: 2023 - 2026 from N11's own saved panel / controls evals; 2022 from SN366's exam evals (panel|N11, panel|R0.85,
panel|NO_STAND, ctrl|N10), all converted by sn03.stream's code.
Paths: 2022 alone (Rs 30k), 2023 - 2026 (Rs 30k, the development path; DEPLOYED must give Rs 8,50,882 at Rs 205), and
2022 - 2026 (Rs 30k from Jan 2022). Stress Rs 205 / 400. Per path: net, per-year net, months positive, worst month,
worst day, refills.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn366"))
_argv = sys.argv[:]
sys.argv = [_argv[0], "parity"]                     # sn366_gold checks its own command line at import
import sn366_gold as G  # noqa: E402  (its patches: 2022 sessions build in SN366's folder, the 2022 dataset)
sys.argv = _argv

Q, ow, C, L, B, D = G.Q, G.ow, G.C, G.L, G.B, G.D
N11L = FNO.parent / "simulation" / "2026-11-02-fno-n11" / "_local"
SN366L = FNO / "2026-11-16-sn366" / "_local"
OUT = HERE / "results-sn392.json"
SRC = {"N11": ("panel", "N11", "panel|N11"), "R0.85": ("panel", "R0.85", "panel|R0.85"), "NO_STAND": ("panel", "NO_STAND", "panel|NO_STAND"),
       "N10": ("controls", "N10", "ctrl|N10")}
_orig_load = D.load_year


def stream(year, book="N11"):
    phase, name, exam = SRC[book]
    if year == "2022":
        key = json.loads((SN366L / "keys-exam-2022.json").read_text(encoding="utf-8"))[exam]
        data = json.loads((SN366L / "exam-evals-2022" / f"{key}.json").read_text(encoding="utf-8"))
    else:
        key = json.loads((N11L / f"keys-{phase}-{year}.json").read_text(encoding="utf-8"))[name]
        data = json.loads((N11L / "evals" / f"{key}.json").read_text(encoding="utf-8"))
    out = []
    for t in data["trades"]:
        ctx = t["n091_entry"]["native_gate_context"]
        sym = t["tradingsymbol"]
        out.append({"day": t["entry_time"][:10], "i": B.minute_of(t["entry_time"]), "j": B.minute_of(t["exit_time"]),
                    "strike": int(round(ctx["strike"])), "opt": "CE" if ctx["is_call"] else "PE",
                    "expiry": f"20{sym[5:7]}-{sym[7:9]}-{sym[9:11]}", "reason": t["exit_reason"],
                    "expert": t["entry_expert"], "gate": t.get("entry_gate") or "", "book": book,
                    "sig_key": (t["entry_time"][:16], int(round(ctx["strike"])), ctx["is_call"])})
    return out


def one(years, books, stress):
    B.stream = stream
    D.DATASETS["2022"] = SN366L / "dataset-nifty-2022"
    D.load_year = G.load_2022
    for mod in (B, L, C):
        mod.YEARS = years
    C._YEARS = None                                  # rebuild the year objects for this path
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
    return {"net": round(sum(nets)), "by_year": {y: round(v) for y, v in sorted(by_y.items())}, "months_positive": sum(v > 0 for v in by_m.values()),
            "months": len(by_m), "worst_month": round(min(by_m.values())), "worst_day": round(min(nets)), "refilled": round(sum(-n for n in nets if n < 0)),
            "trades": len(log), "final_wallet": round(days[-1][1]) if days else None}


def main():
    if OUT.exists():
        raise SystemExit("SN392 is run once")
    Q.install()
    res = {}
    paths = {"2022": ("2022",), "2023-2026": ("2023", "2024", "2025", "2026"), "2022-2026": ("2022", "2023", "2024", "2025", "2026")}
    for pname, years in paths.items():
        for sname, books in (("DEPLOYED", ("N11", "R0.85")), ("NO_STAND", ("NO_STAND",)), ("N10", ("N10",))):
            for st in (205.0, 400.0):
                r = one(years, books, st)
                res[f"{pname} {sname} @{int(st)}"] = r
                print(pname, sname, int(st), json.dumps({k: r[k] for k in ("net", "by_year", "months_positive", "months", "worst_month", "refilled", "trades")}), flush=True)
    assert res["2023-2026 DEPLOYED @205"]["net"] in (850882, 850883), res["2023-2026 DEPLOYED @205"]["net"]
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
