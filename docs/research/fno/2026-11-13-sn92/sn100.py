"""SN100 - one shared account (PLAN.md): Gold v5 with each companion's per-year held-out picks (SN93 drift calls,
SN94 failed breakouts) in one chronological ledger.
Gold has priority: a companion position is sold at the bid the minute a Gold signal arrives, then Gold enters; the
companion's losses use the shared 20% day room; one position at a time. Every wallet, Gold alone vs combined; the
companion's own net on the days Gold did not trade (attribution only)."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402
import sn93  # noqa: E402
import sn94  # noqa: E402


def sn94_grid():
    real = {}
    for buf, W, retest, target in itertools.product((0.0, 0.5), (15, 30), (True, False), ("mid", "far")):
        real[f"buf{buf} W{W} {'retest' if retest else 'direct'} {target}"] = (sn94.rule(buf, W, retest, target), sn94.EX)
    return real


def picks(name, grid, last):
    r = json.loads((HERE / f"results-{name}.json").read_text(encoding="utf-8"))
    out = {}
    for y in C.YEARS:
        k = r["loyo_real"][y]["pick"]
        f, ex = grid[k]
        out[y] = {"sig": (lambda S, f=f: f(S) if C.gold_free(S.day) else None), "ex": ex, "max_trades": 1,
                  "last_entry": last, "size": "gold", "pick": k}
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn100.json"
    if out_path.exists():
        raise SystemExit("SN100 is scored once")
    C.years()
    p93 = picks("sn93", sn93.grid(), sn93.LAST)
    p94 = picks("sn94", sn94_grid(), sn94.LAST)
    res = {"picks": {"SN93": {y: p93[y]["pick"] for y in C.YEARS}, "SN94": {y: p94[y]["pick"] for y in C.YEARS}}}
    gold = C.panel(C.run(C.V5, C.BIG_WALLETS))
    res["Gold v5 alone"] = gold
    combos = {"Gold + SN93": p93, "Gold + SN94": p94}
    for name, cfg in combos.items():
        res[name] = C.panel(C.run({**C.V5, "mode": "combo", "comp_by_year": cfg}, C.BIG_WALLETS))
    for name in ("Gold v5 alone",) + tuple(combos):
        print(f"--- {name}")
        for w, p in res[name].items():
            d = p["net"] - gold[w]["net"]
            print(f"   {w:18s} net {p['net']:>9} ({'+' if d >= 0 else ''}{d}) by year {p['by_year']} refilled {p['refilled']:>8} "
                  f"w/l/none {p['w/l/none']} worst {p['worst']}", flush=True)
    labels = {r["day"]: r for r in json.loads((C.FNO / "2026-11-13-sn76" / "_local" / "days.json").read_text(encoding="utf-8"))}
    attrib = {}
    for name, cfg in combos.items():
        C.RECORD[0] = True
        C.TRADES.clear()
        C.run({**C.V5, "mode": "combo", "comp_by_year": cfg}, (("30k fixed", 30000.0, "grow", 0),))
        C.RECORD[0] = False
        comp = [t for t in C.TRADES if t["who"] == "comp"]
        empty = [t for t in comp if not labels.get(t["day"], {}).get("trades")]
        attrib[name] = {"companion_trades": len(comp), "companion_net": round(sum(t["net"] for t in comp)),
                        "forced_out_by_gold": sum(t["forced"] for t in comp),
                        "on_gold_empty_days": {"trades": len(empty), "net": round(sum(t["net"] for t in empty)),
                                               "won": sum(t["net"] > 0 for t in empty), "lost": sum(t["net"] < 0 for t in empty)}}
    res["attribution_30k_fixed"] = attrib
    print("ATTRIBUTION (Rs 30k fixed)", attrib, flush=True)
    verdict = {}
    for name in combos:
        verdict[name] = {w: res[name][w]["net"] - gold[w]["net"] for w in ("30k fixed", "30k grow stop 3")}
        verdict[name]["PASS"] = all(x > 0 for x in verdict[name].values()) and \
            res[name]["30k grow stop 3"]["worst"] >= -0.2 * 30000 * 1.5 ** 3 * 1.02
    res["verdict"] = verdict
    print("VERDICT", verdict, flush=True)
    out_path.write_text(json.dumps(C.jsonable(res), indent=1), encoding="utf-8")
