"""SN102 - forecast the straddle's remaining executable value at 10:00 (PLAN.md): one ridge model on 11 fixed
features vs B1 (R_today alone) and B2 (days-to-expiry + premium alone), leave-one-year-out (primary) and walk-forward
(secondary); trade when the forecast > Rs 300 (primary) / Rs 0; random admission control; stress / delay checks."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pa  # noqa: E402

C, M = pa.C, pa.M
LAMBDA = 10.0
FULL = ("rs_pos", "rs_neg", "jump", "eff", "vratio", "r_today", "log_prem", "dte", "atr_prev", "gap", "range45")
B1 = ("r_today",)
B2 = ("dte", "log_prem")
BUFFERS = (300.0, 0.0)
CELLS = {"15k/3k": (15000.0, 3000.0), "30k/6k": (30000.0, 6000.0)}


def features(S, asks):
    c, h, l = S.F["c"], S.F["h"], S.F["l"]
    r = np.diff(np.log(c[5: pa.I10 + 1]))
    pos, neg = float((r[r > 0] ** 2).sum()), float((r[r < 0] ** 2).sum())
    tot = pos + neg
    if tot <= 0:
        return None
    rt = C.r_today(S, pa.I10)
    a = C.L.VOLT.get(S.day, (None, None))[0]
    if rt is None or not a:
        return None
    F = float(S.s["future"][3][pa.I10])
    return {"rs_pos": math.log(pos + 1e-12), "rs_neg": math.log(neg + 1e-12), "jump": float((r ** 2).max() / tot),
            "eff": float(abs(r.sum()) / np.abs(r).sum()), "vratio": float(np.var(r[-15:]) / max(np.var(r[:25]), 1e-12)),
            "r_today": rt, "log_prem": math.log(sum(asks) / F), "dte": float(C.sessions_until(S.day, S.s["expiry"])),
            "atr_prev": float(a), "gap": float(abs(S.F["gap"])), "range45": float((h[: pa.I10 + 1].max() - l[: pa.I10 + 1].min()) / c[pa.I10])}


def build():
    Ys = C.years()
    rows = []
    for y in C.YEARS:
        for S in Ys[y].ordered():
            got = pa.path(S, pa.I10)
            if got is None:
                continue
            asks, prem, vals = got
            x = features(S, asks)
            if x is None:
                continue
            late = pa.path(S, pa.I10 + 1)
            rows.append({"day": S.day, "year": y, "gold_free": C.gold_free(S.day), "x": x, "prem": prem,
                         "y": pa.settle(vals, pa.I10)[0], "vals": vals,
                         "late": None if late is None else (late[1], late[2])})
    return rows


def ridge_fit(X, Y):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    ym = Y.mean()
    beta = np.linalg.solve(Z.T @ Z + LAMBDA * np.eye(Z.shape[1]), Z.T @ (Y - ym))
    return mu, sd, ym, beta


def ridge_pred(model, X):
    mu, sd, ym, beta = model
    return ((X - mu) / sd) @ beta + ym


def predictions(rows, feats, scheme):
    X = np.array([[r["x"][f] for f in feats] for r in rows])
    Y = np.array([r["y"] for r in rows])
    yrs = np.array([r["year"] for r in rows])
    pred = np.full(len(rows), np.nan)
    for y in C.YEARS:
        if scheme == "loyo":
            tr = yrs != y
        else:
            if y == "2023":
                continue
            tr = yrs < y
        model = ridge_fit(X[tr], Y[tr])
        te = yrs == y
        pred[te] = ridge_pred(model, X[te])
    return pred


def trade_net(r, cell, stress=205.0, late=False):
    ceil, room = CELLS[cell]
    if late:
        if r["late"] is None:
            return 0.0
        prem, vals = r["late"]
        i = pa.I10 + 1
    else:
        prem, vals, i = r["prem"], r["vals"], pa.I10
    if prem > ceil:
        return 0.0
    v = vals if stress == 205.0 else pa.shift(vals, 205.0, stress)
    return pa.settle(v, i, room, fallback=-2 * stress)[0]


def score(rows, pred, buf, cell, sel=lambda r: True, **kw):
    nets = {r["day"]: (trade_net(r, cell, **kw) if (not np.isnan(p) and p > buf and sel(r)) else 0.0) for r, p in zip(rows, pred)}
    return pa.year_table(nets)


def random_control(rows, pred, buf, cell, sel, n=2000, seed=102):
    """Same number of admissions per year, drawn at random among that year's affordable eligible sessions."""
    rng = np.random.default_rng(seed)
    ceil = CELLS[cell][0]
    per_year = {}
    for y in C.YEARS:
        idx = [k for k, r in enumerate(rows) if r["year"] == y and sel(r)]
        k_adm = sum(1 for k in idx if not np.isnan(pred[k]) and pred[k] > buf)
        cand = [trade_net(rows[k], cell) for k in idx if rows[k]["prem"] <= ceil]
        per_year[y] = (k_adm, np.array(cand))
    tots = []
    for _ in range(n):
        s = 0.0
        for y, (k_adm, cand) in per_year.items():
            if k_adm and len(cand):
                s += cand[rng.choice(len(cand), min(k_adm, len(cand)), replace=False)].sum()
        tots.append(s)
    return float(np.percentile(tots, 95)), float(np.mean(tots))


if __name__ == "__main__":
    out_path = HERE / "results-sn102.json"
    if out_path.exists():
        raise SystemExit("SN102 is scored once")
    rows = build()
    print("rows", len(rows), flush=True)
    res = {"n_rows": len(rows), "models": {}}
    for scheme in ("loyo", "walk"):
        for mname, feats in (("FULL", FULL), ("B1 R_today", B1), ("B2 dte+premium", B2)):
            pred = predictions(rows, feats, scheme)
            ok = ~np.isnan(pred)
            ic = float(np.corrcoef(pred[ok], np.array([r["y"] for r in rows])[ok])[0, 1])
            entry = {"ic_pred_vs_net": ic, "admitted_days": {}}
            for dname, sel in (("all days", lambda r: True), ("gold-free", lambda r: r["gold_free"])):
                for buf in BUFFERS:
                    for cell in CELLS:
                        k = f"{dname} | buf {int(buf)} | {cell}"
                        t = score(rows, pred, buf, cell, sel)
                        if mname == "FULL" and buf == 300.0 and cell == "15k/3k":
                            t["stress_400"] = score(rows, pred, buf, cell, sel, stress=400.0)["total"]
                            t["late_1min"] = score(rows, pred, buf, cell, sel, late=True)["total"]
                            t["random_95th"], t["random_mean"] = random_control(rows, pred, buf, cell, sel)
                            entry["admitted_days"][dname] = [r["day"] for r, p in zip(rows, pred) if not np.isnan(p) and p > buf and sel(r)]
                        entry[k] = t
            res["models"][f"{scheme} | {mname}"] = entry
            print(f"--- {scheme} {mname}  IC {ic:+.3f}", flush=True)
            for k, t in entry.items():
                if isinstance(t, dict) and "total" in t:
                    print(f"   {k:30s} {[t[y]['net'] for y in C.YEARS]} total {t['total']:>8} w/o best5 {t['without_best_5']:>8} "
                          f"trades {sum(t[y]['trades'] for y in C.YEARS)}" +
                          (f" | 400/leg {t['stress_400']} late {t['late_1min']} random95 {round(t['random_95th'])}" if "stress_400" in t else ""), flush=True)
    # coefficients of the full model on all four years (description)
    X = np.array([[r["x"][f] for f in FULL] for r in rows]); Y = np.array([r["y"] for r in rows])
    res["full_model_all_years_std_coef"] = dict(zip(FULL, map(float, ridge_fit(X, Y)[3])))
    print("standardised coefficients (all years)", {k: round(v) for k, v in res["full_model_all_years_std_coef"].items()})
    verdict = {}
    for dname in ("all days", "gold-free"):
        f = res["models"]["loyo | FULL"][f"{dname} | buf 300 | 15k/3k"]
        b1 = res["models"]["loyo | B1 R_today"][f"{dname} | buf 300 | 15k/3k"]["total"]
        b2 = res["models"]["loyo | B2 dte+premium"][f"{dname} | buf 300 | 15k/3k"]["total"]
        ok = (f["total"] > 0 and f["positive_years"] >= 3 and f["total"] > b1 and f["total"] > b2 and f["total"] > f["random_95th"]
              and f["without_best_5"] > 0 and f["stress_400"] > 0 and f["late_1min"] > 0)
        verdict[dname] = {"total": f["total"], "years": [f[y]["net"] for y in C.YEARS], "B1": b1, "B2": b2,
                          "random_95th": round(f["random_95th"]), "without_best_5": f["without_best_5"],
                          "stress_400": f["stress_400"], "late_1min": f["late_1min"], "PASS": ok}
    res["verdict"] = verdict
    print("VERDICT", verdict, flush=True)
    for r in rows:
        r.pop("vals"); r.pop("late")
    res["rows"] = rows
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
