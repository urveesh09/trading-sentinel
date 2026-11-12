"""SN52b - the real account (no refill): keeps 1 lot while equity >= Rs 7,500; sizing equity capped like Gold."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab as L
V4 = {"extend": True, "ext_x": 0.25, "ext_k": 3.0, "itm_if_fits": True, "in_x": 0.10, "itm_auto": (17500, 20000)}
if __name__ == "__main__":
    L.VOLT.update(L.vol_table())
    years = {y: L.B.Year(y) for y in L.YEARS}
    out = {}
    for W0 in (15000.0, 20000.0, 30000.0):
        for cap in (50625.0, 113906.0):
            L.WALLETS = ((f"real account from {int(W0/1000)}k, sizing capped at {int(cap)}", W0, "float", None),)
            r = L.run(years, None, {**V4, "float_cap": cap})
            w = list(r)[0]; per = r[w]
            out[w] = per
            print(f"SN52b {w:46s} ends with {per['final_equity']['net']:>9} (gain {per['final_equity']['net'] - int(W0):>9}) by year {[per[y]['net'] for y in L.YEARS]} worst {min(per[y]['worst'] for y in L.YEARS)} days won/lost/none {sum(per[y]['won'] for y in L.YEARS)}/{sum(per[y]['lost'] for y in L.YEARS)}/{sum(per[y]['none'] for y in L.YEARS)}", flush=True)
    (HERE / "results-sn52b.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
