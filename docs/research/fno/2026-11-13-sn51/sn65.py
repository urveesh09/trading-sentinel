"""SN65-SN68 reality checks on SN Gold v4: slippage as a share of premium (instead of a flat Rs 205 per lot); entries
2 minutes late; partial fills (only one lot of two filled); start-date sensitivity (growth stopped after 3 from
Rs 15k with refills, and the real Rs 30k account without refills, started at each quarter)."""
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
    for flat, pct in ((0.0, 0.01), (0.0, 0.02), (205.0, 0.01)):
        L.STRESS, L.STRESS_PCT = flat, pct
        out[f"SN65 +Rs {int(flat)} and {pct:.0%} of premium per side"] = r = L.run(years, None, V4)
        print(L.line(f"SN65 +Rs {int(flat)} and {pct:.0%} premium/side", r), flush=True)
    L.STRESS, L.STRESS_PCT = 205.0, 0.0
    for y, Y in years.items():
        Y.streams["N11_ontime"] = Y.sigs("N11")
        Y.streams["N11"] = {d: [{**s, "i": s["i"] + 2} for s in v] for d, v in Y.streams["N11_ontime"].items()}
    out["SN66 entries 2 minutes late"] = r = L.run(years, None, V4)
    print(L.line("SN66 entries 2 minutes late", r), flush=True)
    for y, Y in years.items():
        Y.streams["N11"] = Y.streams["N11_ontime"]
    for p in (0.3, 0.6):
        out[f"SN66 partial fills {p:.0%}"] = r = L.run(years, None, {**V4, "partial": p})
        print(L.line(f"SN66 one lot only on {p:.0%} of 2-lot trades", r), flush=True)
    starts = [f"{y}-{m}-01" for y in ("2023", "2024", "2025", "2026") for m in ("01", "04", "07", "10")][:-1]
    rows = []
    for st in starts:
        L.WALLETS = (("G3 from 15k (refilled)", 15000.0, "grow", 3), ("real 30k (no refill), capped 50625", 30000.0, "float", None))
        r = L.run(years, None, {**V4, "from_day": st, "float_cap": 50625.0})
        g = sum(r["G3 from 15k (refilled)"][y]["net"] for y in L.YEARS); ref = sum(r["G3 from 15k (refilled)"][y]["refilled"] for y in L.YEARS)
        f = r["real 30k (no refill), capped 50625"]["final_equity"]["net"]
        rows.append({"start": st, "g3_net": g, "g3_refilled": ref, "real30k_end": f})
        print(f"SN68 start {st}: G3 net {g:>8} (refilled {ref:>7}) | real Rs 30k account ends {f:>8}", flush=True)
    out["SN68"] = rows
    (HERE / "results-sn65-68.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
