"""SN91 - how many rupees of wallet behind each lot (Gold v5 sizing leverage), from the deployed Rs 30k start.
lots = floor(W / X), halved on low-volatility days; X in 10k / 12.5k / 15k (deployed) / 20k. Wallets: fixed Rs 30k and
growth stopped after 3 steps. In-sample description; the per-lot edge is the same in every row, only size changes."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn51"))
import lab as L
V5 = {"extend": True, "ext_x": 0.25, "ext_k": 3.0, "itm_if_fits": True, "in_x": None, "in_atr": 1.0, "in_full": True,
      "itm_auto": (17500, 20000), "books": ("N11", "R0.85")}
src = Path(L.__file__).read_text(encoding="utf-8")
assert src.count("max(1, int(W // 15000))") == 1
if __name__ == "__main__":
    L.VOLT.update(L.vol_table())
    years = {y: L.B.Year(y) for y in L.YEARS}
    out = {}
    for X in (10000, 12500, 15000, 20000):
        code = compile(src.replace("max(1, int(W // 15000))", f"max(1, int(W // {X}))"), L.__file__, "exec")
        ns = {"__name__": "lab_x", "__file__": L.__file__}
        exec(code, ns)
        ns["VOLT"].update(L.VOLT)
        ns["WALLETS"] = (("fixed 30k", 30000.0, "grow", 0), ("grow from 30k, stop after 3", 30000.0, "grow", 3))
        r = ns["run"](years, None, V5)
        for w, per in r.items():
            won = sum(per[y]["net"] + per[y]["refilled"] for y in L.YEARS); ref = sum(per[y]["refilled"] for y in L.YEARS)
            row = {"by_year": [per[y]["net"] for y in L.YEARS], "net": won - ref, "refilled": ref, "worst": min(per[y]["worst"] for y in L.YEARS),
                   "losing_years": sum(per[y]["net"] < 0 for y in L.YEARS)}
            out[f"Rs {X} per lot | {w}"] = row
            print(f"Rs {X:>5} per lot | {w:28s} net {row['net']:>9} by year {row['by_year']} refilled {ref:>9} worst {row['worst']:>8} losing years {row['losing_years']}", flush=True)
    (HERE / "results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
