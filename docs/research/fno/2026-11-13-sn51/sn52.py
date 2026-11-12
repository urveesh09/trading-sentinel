"""SN52-SN56 on SN Gold v4 (every wallet): a real account that keeps its losses (no refill); good parts of failed
strategies turned into SIZING signals - option writers' flow (SN09), puts (SN03), the trend regime (SN06); and N11's
sister entry streams (SN03 D) inside v4."""
import json, pickle, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab as L
V4 = {"extend": True, "ext_x": 0.25, "ext_k": 3.0, "itm_if_fits": True, "in_x": 0.10, "itm_auto": (17500, 20000)}
V = {"SN Gold v4": dict(V4)}
for k, thr in ((15, 0.0), (15, 0.01), (6, 0.0), (30, 0.0)):
    V[f"SN53 2nd lot: vol AND writers agree (k{k} thr{thr})"] = {**V4, "size": "oi", "oi_k": k, "oi_thr": thr}
V["SN53 2nd lot: vol OR writers agree"] = {**V4, "size": "oi_or_vol"}
V["SN54 2nd lot: every put, calls on vol days"] = {**V4, "size": "puts_full"}
V["SN54 2nd lot: puts on vol days only"] = {**V4, "size": "vol_puts"}
for a in (25, 30):
    V[f"SN55 2nd lot: vol AND ADX >= {a}"] = {**V4, "size": "adx_hi", "adx": a}
    V[f"SN55 2nd lot: vol AND ADX < {a}"] = {**V4, "size": "adx_lo", "adx": a}
for b in (("N11", "R0.85"), ("N11", "N15"), ("N11", "NO_STAND")):
    V[f"SN56 entries {'+'.join(b)}"] = {**V4, "books": b}
if __name__ == "__main__":
    sys.path.insert(0, str(HERE.parent / "2026-11-12-sn09"))
    import sn09_oi
    for y in L.YEARS:
        L.OI.update(sn09_oi.load(y))
    L.ADX.update(json.loads((HERE.parent / "2026-11-12-sn06" / "_local" / "daily.json").read_text(encoding="utf-8")))
    res = L.study("sn53-56", V, HERE)
    # SN52: the real account - no refill, losses stay, profits stay; lots = floor(equity / 15k) (halved on low-vol days)
    L.WALLETS = (("F float from 15k", 15000.0, "float", None), ("F float from 20k", 20000.0, "float", None), ("F float from 30k", 30000.0, "float", None))
    L.VOLT.update(L.vol_table())
    years = {y: L.B.Year(y) for y in L.YEARS}
    r = L.run(years, None, V4)
    for w, per in r.items():
        print("SN52", w, "final equity", per["final_equity"]["net"], "by year", [per[y]["net"] for y in L.YEARS], "worst", min(per[y]["worst"] for y in L.YEARS), flush=True)
    (HERE / "results-sn52.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
