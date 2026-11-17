"""SN362: Gold's signal through SENSEX options (PLAN.md section 2; amendment A5 in this docstring, before any SN362 number).

A5:
  - Window: gl's EXAMS SENSEX sample (Oct 1, 2024 - Apr 30, 2026; seen for buyers since SN251-SN272), not May 2024: the
    mirror on this PC starts in October 2024. Opening that sample is allowed here (gl.SEALED["EXAMS"] = True in this
    script only).
  - Pairing on Gold's INITIAL entry only (adds are Gold's own NIFTY mechanics): NIFTY leg = Gold's first piece (ask0 x
    lots0 at minute i) sold at Gold's exit price px at minute j, cost L.cost (charges + stress per lot). SENSEX leg = the
    front-weekly SENSEX option on Gold's side, the same number of strike steps in the money as Gold's NIFTY strike (NIFTY
    step 50, SENSEX step 100, both from their own index at minute i), bought at gl's model ask at minute i, sold at gl's
    model bid at minute j (the last price within 10 minutes), lots = max(1, floor(NIFTY premium / SENSEX premium per lot)).
  - SENSEX stress per lot = NIFTY's stress x (median quoted spread cost per lot of SENSEX / of NIFTY), front-weekly ATM CE
    and PE, every usable real-quote archive snapshot 09:30 - 14:15 (Sep 10 - Nov 13, 2026).
  - Pass (routing candidate): mean paired difference (SENSEX - NIFTY) > 0 at Rs 205 and Rs 400, in both halves of the
    window (split at the median trade date), and > 0 without the best paired trade.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn251"))
sys.path.insert(0, str(FNO / "2026-11-13-sn101"))
sys.path.insert(0, str(FNO / "2026-11-16-sn331"))
import gl  # noqa: E402
import qa  # noqa: E402
import sn339_350 as Q  # noqa: E402

qa.EXPORT = Path(r"C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\docs\research\fno\2026-10-28-forward-panel"
                 r"\_local\exports\20261116T103002Z")
OUT = HERE / "results-sn362.json"


def spread_ratio():
    per = {"NIFTY": [], "SENSEX": []}
    for d in qa.days():
        q = qa.load(d)
        for und, step in (("NIFTY", 50), ("SENSEX", 100)):
            exps = sorted({k[1] for k in q["opt"] if k[0] == und and k[1] >= d})
            fut = qa.front_fut(q, und)
            if not exps or fut is None:
                continue
            e, lot = exps[0], q["lot"][und]
            for i in range(15, 301):
                if not fut["usable"][i]:
                    continue
                k = int(round(0.5 * (fut["bid"][i] + fut["ask"][i]) / step) * step)
                for o in ("CE", "PE"):
                    rec = q["opt"].get((und, e, k, o))
                    if rec is not None and rec["usable"][i]:
                        per[und].append((rec["ask"][i] - rec["bid"][i]) * lot)
    mn, ms = float(np.median(per["NIFTY"])), float(np.median(per["SENSEX"]))
    return {"nifty_spread_per_lot": mn, "sensex_spread_per_lot": ms, "ratio": ms / mn, "n_nifty": len(per["NIFTY"]), "n_sensex": len(per["SENSEX"])}


def main():
    if OUT.exists():
        raise SystemExit("SN362 is run once")
    sr = spread_ratio()
    print("spread", json.dumps(sr), flush=True)
    gl.SEALED["EXAMS"] = True
    sx = gl.sample("EXAMS")
    raw_n = gl._cache("devall", gl.build_dev)
    nx = gl.Sample("N", raw_n, gl.DEV_LO, gl.TEST_HI)
    Q.install()
    C, L, M = Q.C, Q.L, Q.L.M
    orig = C.gold_one

    def capture(S, sg, *a, **kw):
        res = orig(S, sg, *a, **kw)
        if res is not None and Q.gw.LOG:
            Q.gw.LOG[-1]["strike"] = res[5]
        return res
    C.gold_one = capture
    res = {"spread": sr}
    for st in (205.0, 400.0):
        row, days, log = Q.run(st)
        assert (st != 205.0) or row["net"] == 850882
        sst = st * sr["ratio"]
        pairs = []
        for x in log:
            d = x["day"]
            if d not in sx.s or d not in nx.s or "strike" not in x:
                continue
            sn, ss = nx.s[d], sx.s[d]
            i, j = x["i"], x["j"]
            idx_n = float(sn["index"][3][i])
            atm_n = int(round(idx_n / 50.0) * 50)
            steps = int(round((atm_n - x["strike"]) / 50.0)) if x["opt"] == "CE" else int(round((x["strike"] - atm_n) / 50.0))
            idx_s = ss["index"][3][i]
            if np.isnan(idx_s):
                continue
            atm_s = int(round(float(idx_s) / 100.0) * 100)
            k_s = atm_s - steps * 100 if x["opt"] == "CE" else atm_s + steps * 100
            prem_n = x["ask0"] * x["lots0"] * M.LOT
            probe = gl.Pos(sx, ss, [(k_s, x["opt"], +1)], i, lots=1, stress=sst)
            if not probe.ok or probe.premium <= 0:
                pairs.append({"day": d, "missed": "no_sensex_price"})
                continue
            lots_s = max(1, int(prem_n // probe.premium))
            pos = gl.Pos(sx, ss, [(k_s, x["opt"], +1)], i, lots=lots_s, stress=sst)
            v = None
            for jj in range(j, max(i, j - 10), -1):
                v = pos.value(ss, jj)
                if v is not None:
                    break
            if v is None:
                pairs.append({"day": d, "missed": "no_sensex_exit"})
                continue
            q_n = x["lots0"] * M.LOT
            # L.cost reads the module stress, which Q.run has restored by now: the same formula with this run's stress
            net_n = ((x["px"] - x["ask0"]) * q_n - M.charges(x["ask0"], x["px"], q_n) - st * x["lots0"]
                     - L.STRESS_PCT * (x["ask0"] + x["px"]) * q_n)
            pairs.append({"day": d, "opt": x["opt"], "steps": steps, "lots_n": x["lots0"], "lots_s": lots_s, "prem_n": round(prem_n),
                          "prem_s": round(pos.premium), "net_n": round(net_n, 1), "net_s": round(v, 1), "diff": round(v - net_n, 1),
                          "sensex_dte": (np.datetime64(ss["expiry"]) - np.datetime64(d)).astype(int), "reason": x["reason"]})
        ok = [p for p in pairs if "diff" in p]
        dif = np.array([p["diff"] for p in ok])
        mid = sorted(p["day"] for p in ok)[len(ok) // 2] if ok else None
        h1 = np.array([p["diff"] for p in ok if p["day"] < mid]) if ok else np.array([])
        h2 = np.array([p["diff"] for p in ok if p["day"] >= mid]) if ok else np.array([])
        r = {"pairs": len(ok), "missed": len(pairs) - len(ok), "sensex_stress_per_lot": round(sst, 1),
             "mean_diff": round(float(dif.mean()), 1) if len(dif) else None,
             "sum_net_nifty": round(sum(p["net_n"] for p in ok)), "sum_net_sensex": round(sum(p["net_s"] for p in ok)),
             "half1_mean": round(float(h1.mean()), 1) if len(h1) else None, "half2_mean": round(float(h2.mean()), 1) if len(h2) else None,
             "without_best_mean": round(float((dif.sum() - dif.max()) / max(1, len(dif) - 1)), 1) if len(dif) else None,
             "share_sensex_better": round(float((dif > 0).mean()), 3) if len(dif) else None}
        for b, f in (("dte<=1", lambda p: p["sensex_dte"] <= 1), ("dte 2-3", lambda p: 2 <= p["sensex_dte"] <= 3), ("dte 4+", lambda p: p["sensex_dte"] >= 4)):
            xs = [p["diff"] for p in ok if f(p)]
            r[b] = {"n": len(xs), "mean_diff": round(float(np.mean(xs)), 1) if xs else None}
        res[f"@{int(st)}"] = r
        res[f"pairs@{int(st)}"] = pairs
        print(int(st), json.dumps(r), flush=True)
    a, b = res["@205"], res["@400"]
    res["pass"] = bool(all(z["mean_diff"] is not None and z["mean_diff"] > 0 and z["half1_mean"] > 0 and z["half2_mean"] > 0 and z["without_best_mean"] > 0 for z in (a, b)))
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print("pass", res["pass"])


if __name__ == "__main__":
    main()
