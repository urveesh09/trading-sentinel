"""SN129 - the gap-day sleeve from survivors (PLAN.md). Reads SN123-SN128's saved held-out day nets; a component
joins only if its frozen verdict PASSED; SN95-L joins as the frozen watch. One separate Rs 25k sleeve beside Gold
(day nets summed, 20% day limit applied to the sum); compared with the same Rs 25k added to Gold. If nothing passed,
the sleeve is not formed and the all-candidates sum is shown as a labelled description."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn116"))
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn111"))
import pg  # noqa: E402
import pc  # noqa: E402
import pb  # noqa: E402

C, pa = pg.C, pg.pa


def load(name):
    return json.loads((HERE / f"results-{name}.json").read_text(encoding="utf-8"))


def components():
    out = {}
    r = load("sn123"); out["SN123 burst scalper + lock"] = (r["PASS"], r["heldout_day_nets"])
    r = load("sn124"); out["SN124 overnight short fly/condor"] = (r["verdict"]["PASS"], r["heldout_day_nets"])
    r = load("sn125")["gold-free"]; out["SN125 last half-hour"] = (r["verdict"]["PASS"], r["heldout_day_nets"])
    r = load("sn126"); out["SN126 hot-day scalping"] = (r["PASS"], r["heldout_day_nets"])
    r = load("sn128")["gold-free"]; out["SN128 morning crush (Gold-free)"] = (r["verdict"]["PASS"], r["heldout_day_nets"])
    adm = pa.admission()
    out["SN95-L straddle (frozen watch)"] = (True, {S.day: pb.net(pa.path(S, pb.I10)) for S in pb.signal_days(adm, True)})
    return out


def sleeve(parts, room=5000.0):
    days = sorted({d for p in parts for d in p})
    nets = [(d, max(-room * 1.0, sum(p.get(d, 0.0) for p in parts))) for d in days]
    nets = [(d, n) for d, n in nets if n != 0]
    xs = sorted((n for _d, n in nets), reverse=True)
    return {"days": len(nets), "net": round(sum(xs)), "by_year": pc.by_year(nets), "without_best_5": round(sum(xs[5:])),
            **pc.series_stats(nets), "refilled": round(sum(-n for n in xs if n < 0))}, nets


if __name__ == "__main__":
    out_path = HERE / "results-sn129.json"
    if out_path.exists():
        raise SystemExit("SN129 is scored once")
    comp = components()
    res = {"components": {k: {"passed": ok, **sleeve([v])[0]} for k, (ok, v) in comp.items()}}
    for k, v in res["components"].items():
        print(f"  {k:36s}", v, flush=True)
    passed = [v for k, (ok, v) in comp.items() if ok and not k.startswith("SN95-L")]
    res["formed"] = bool(passed)
    chosen = passed + [comp["SN95-L straddle (frozen watch)"][1]]
    label = "sleeve of survivors + SN95-L" if passed else "NOT FORMED - description only: every candidate + SN95-L summed"
    if not passed:
        chosen = [v for _k, (_ok, v) in comp.items()]
    s, nets = sleeve(chosen)
    res["sleeve"] = {"label": label, **s}
    print("SLEEVE", res["sleeve"], flush=True)
    cmp = {}
    for mname, cap in (("fixed", 0), ("grow stop 3", 3)):
        g30, d30 = pc.gold_days(C.V5, (f"30k {mname}", 30000.0, "grow", cap))
        g55, d55 = pc.gold_days(C.V5, (f"55k {mname}", 55000.0, "grow", cap))
        both = pc.merge(d30, nets)
        cmp[mname] = {"Gold 30k + 25k sleeve": {"net": round(g30["net"] + s["net"]), **pc.series_stats(both), "by_year": pc.by_year(both)},
                      "Gold 55k alone": {"net": round(g55["net"]), **pc.series_stats(d55), "by_year": pc.by_year(d55)},
                      "Gold 30k alone": {"net": round(g30["net"]), **pc.series_stats(d30)}}
        print(f"=== Rs 55k total | {mname}", cmp[mname], flush=True)
    res["vs_gold"] = cmp
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
