"""SN47 v4 robustness (stress, late entries); SN48 the owner's growth levers on v4; per-year v4 tables."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab as L
V3 = {"extend": True, "ext_x": 0.25, "ext_k": 3.0, "itm_if_fits": True, "in_x": 0.10}
V4 = {**V3, "itm_auto": (17500, 20000)}
if __name__ == "__main__":
    L.VOLT.update(L.vol_table())
    years = {y: L.B.Year(y) for y in L.YEARS}
    out = {}
    for stress in (205.0, 300.0, 400.0):
        L.STRESS = stress
        for name, v in (("v3", V3), ("v4", V4)):
            out[f"{name} +{int(stress)}"] = r = L.run(years, None, v)
            print(L.line(f"{name} at +Rs {int(stress)}", r), flush=True)
    L.STRESS = 205.0
    for y, Y in years.items():
        Y.streams["N11_ontime"] = Y.sigs("N11")
        Y.streams["N11"] = {d: [{**s, "i": s["i"] + 1} for s in v] for d, v in Y.streams["N11_ontime"].items()}
    out["v4 1 min late"] = r = L.run(years, None, V4)
    print(L.line("v4 entries 1 minute late", r), flush=True)
    for y, Y in years.items():
        Y.streams["N11"] = Y.streams["N11_ontime"]
    for name, extra in (("v4 step x2.0", {"g_mult": 2.0}), ("v4 step after 50% profit", {"g_trig": 0.5})):
        out[name] = r = L.run(years, None, {**V4, **extra})
        print(L.line(name, r), "worst G3", min(r["G3 (Gold)"][y]["worst"] for y in L.YEARS), "G5", min(r["G5"][y]["worst"] for y in L.YEARS), flush=True)
    r = out["v4 +205"]
    for w, per in r.items():
        print(f"v4 {w:12s}", " | ".join(f"{per[y]['net']:>8}/{per[y]['refilled']:<7}" for y in L.YEARS), "| total", sum(per[y]['net'] for y in L.YEARS),
              "refill", sum(per[y]['refilled'] for y in L.YEARS), "W/L/N", sum(per[y]['won'] for y in L.YEARS), sum(per[y]['lost'] for y in L.YEARS),
              sum(per[y]['none'] for y in L.YEARS), "worst", min(per[y]['worst'] for y in L.YEARS))
    (HERE / "results-sn47-48.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
