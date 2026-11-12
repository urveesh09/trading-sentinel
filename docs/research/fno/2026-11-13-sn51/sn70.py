"""SN70 v5 with the owner's start amounts and growth triggers (net at the end); SN73 v5 under harsh reality."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab as L
V4 = {"extend": True, "ext_x": 0.25, "ext_k": 3.0, "itm_if_fits": True, "in_x": 0.10, "itm_auto": (17500, 20000)}
V5 = {**V4, "books": ("N11", "R0.85"), "in_x": None, "in_atr": 1.0, "in_full": True}
if __name__ == "__main__":
    L.VOLT.update(L.vol_table())
    years = {y: L.B.Year(y) for y in L.YEARS}
    out = {"sn70": {}, "sn73": {}}
    base = L.WALLETS
    for W0 in (15000.0, 20000.0, 30000.0):
        for trig in (1.0, 0.5):
            L.WALLETS = tuple((f"start {int(W0/1000)}k, step after {int(trig*100)}%, stop after {cap}", W0, "grow", cap) for cap in (3, 5))
            r = L.run(years, None, {**V5, "g_trig": trig})
            for w, per in r.items():
                won = sum(per[y]["net"] + per[y]["refilled"] for y in L.YEARS); ref = sum(per[y]["refilled"] for y in L.YEARS)
                out["sn70"][w] = {"won": won, "refilled": ref, "net": won - ref, "worst": min(per[y]["worst"] for y in L.YEARS), "by_year": [per[y]["net"] for y in L.YEARS]}
                print(f"SN70 {w:40s} won {won:>9} refilled {ref:>9} NET {won-ref:>9} worst {out['sn70'][w]['worst']:>8} by year {out['sn70'][w]['by_year']}", flush=True)
    L.WALLETS = base
    for label, setup in (("+Rs 400 per lot", (400.0, 0.0)), ("1% of premium per side", (0.0, 0.01)), ("+Rs 205 and 1%", (205.0, 0.01))):
        L.STRESS, L.STRESS_PCT = setup
        out["sn73"][label] = r = L.run(years, None, V5)
        print(L.line(f"SN73 v5 at {label}", r), flush=True)
    L.STRESS, L.STRESS_PCT = 205.0, 0.0
    for y, Y in years.items():
        for b in ("N11", "R0.85"):
            Y.sigs(b)
            Y.streams[b + "_ontime"] = Y.streams[b]
            Y.streams[b] = {d: [{**s, "i": s["i"] + 2} for s in v] for d, v in Y.streams[b + "_ontime"].items()}
    out["sn73"]["2 min late"] = r = L.run(years, None, V5)
    print(L.line("SN73 v5 entries 2 minutes late", r), flush=True)
    for y, Y in years.items():
        for b in ("N11", "R0.85"):
            Y.streams[b] = Y.streams[b + "_ontime"]
    out["sn73"]["partial 50%"] = r = L.run(years, None, {**V5, "partial": 0.5})
    print(L.line("SN73 v5 one lot only on 50% of multi-lot trades", r), flush=True)
    (HERE / "results-sn70-73.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
