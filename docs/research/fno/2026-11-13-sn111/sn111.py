"""SN111 - where the straddle's money comes from (description; PLAN.md): by R_today decile at 10:00, the straddle and
each leg (pure hold, strict), volatility persistence (realised 10:00-15:10 / implied at 10:00), implied catch-up
(implied at 15:10 / at 10:00), move / premium, and trend continuation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pb  # noqa: E402

C, M, pa = pb.C, pb.M, pb.pa


if __name__ == "__main__":
    out_path = HERE / "results-sn111.json"
    if out_path.exists():
        raise SystemExit("SN111 is scored once")
    adm = pa.admission()
    Ys = C.years()
    rows = []
    for y in C.YEARS:
        for S in Ys[y].ordered():
            i = pb.I10
            K = pb.atm(S, i)
            st = pb.struct_path(S, i, [(K, "CE"), (K, "PE")])
            if st is None:
                continue
            ref = pa.path(S, i)
            assert ref is not None and np.allclose(np.nan_to_num(ref[2]), np.nan_to_num(st[2])), S.day
            ce, pe = pb.struct_path(S, i, [(K, "CE")]), pb.struct_path(S, i, [(K, "PE")])
            rt, si10, si1510 = C.r_today(S, i), C.sigma_imp(S, i), C.sigma_imp(S, pb.FLAT)
            c, o = S.F["c"], S.F["o"]
            if rt is None or si10 is None:
                continue
            rv = float(np.std(np.diff(np.log(c[i: pb.FLAT + 1]))))
            rows.append({"day": S.day, "year": y, "r_today": rt, "flag": adm.get((S.day, "10:00", "R_today", 0.2, "top")),
                         "straddle": pa.settle(st[2], i)[0],
                         "call": pa.settle(ce[2], i, fallback=-205.0)[0] if ce else None,
                         "put": pa.settle(pe[2], i, fallback=-205.0)[0] if pe else None,
                         "persist": rv / si10, "catch_up": (si1510 / si10) if si1510 else None,
                         "move_over_premium": float(abs(c[pb.FLAT] - c[i]) / sum(st[0])),
                         "continued": bool(np.sign(c[pb.FLAT] - c[i]) == np.sign(c[i] - o[0])),
                         "dte": C.sessions_until(S.day, S.s["expiry"])})
    edges = np.quantile([r["r_today"] for r in rows], np.linspace(0, 1, 11))
    dec = {}
    for d in range(10):
        g = [r for r in rows if edges[d] <= r["r_today"] <= edges[d + 1]]
        m = lambda k: round(float(np.mean([r[k] for r in g if r[k] is not None])), 3)  # noqa: E731
        dec[d + 1] = {"n": len(g), "straddle": round(m("straddle")), "call": round(m("call")), "put": round(m("put")),
                      "persist": m("persist"), "catch_up": m("catch_up"), "move_over_premium": m("move_over_premium"),
                      "continued_share": m("continued")}
    top = [r for r in rows if r["r_today"] >= edges[9]]
    by_dte = {}
    for d in sorted({r["dte"] for r in top}):
        g = [r for r in top if r["dte"] == d]
        by_dte[d] = {"n": len(g), "straddle_mean": round(float(np.mean([r["straddle"] for r in g])))}
    best_leg = {"top decile: call won more": sum(1 for r in top if (r["call"] or 0) > (r["put"] or 0)), "n": len(top),
                "top decile: winning leg follows the morning trend": round(float(np.mean([
                    ((r["call"] or 0) > (r["put"] or 0)) == r["continued"] for r in top])), 3)}
    res = {"rows": len(rows), "deciles": dec, "top_decile_by_dte": by_dte, "legs": best_leg,
           "corr_r_today_persist": float(np.corrcoef([r["r_today"] for r in rows], [r["persist"] for r in rows])[0, 1]),
           "corr_r_today_catch_up": float(np.corrcoef([r["r_today"] for r in rows if r["catch_up"]], [r["catch_up"] for r in rows if r["catch_up"]])[0, 1])}
    for d, v in dec.items():
        print(f"decile {d:2d}", v, flush=True)
    print("top decile by days to expiry", by_dte)
    print("legs", best_leg)
    print("corr(R_today, later realised/implied)", round(res["corr_r_today_persist"], 3), "| corr(R_today, implied catch-up)", round(res["corr_r_today_catch_up"], 3))
    res["table"] = rows
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
