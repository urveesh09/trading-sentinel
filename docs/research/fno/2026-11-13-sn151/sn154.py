"""SN154 - a learned "will today's 10:00 straddle pay?" probability (PLAN.md), and SN155 - rule and model must agree.
One row per session at 10:00 (straddle priced and <= Rs 15k): SN102's 11 features + the 30-minute opening range, ADX,
VIX ratio, previous range; label = the straddle held to 15:10 (Rs 3k room, strict) nets > 0. Logistic regression
(standardised, C = 0.5), leave one year out; admit when p >= p*, p* in {0.30 ... 0.50} chosen on the training years
by straddle net. SN155: SN95-L's hot flag AND the held-out p >= 0.5, against SN95-L alone on identical days."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn101"))
import ph  # noqa: E402
import sn102  # noqa: E402

C, pa = ph.C, ph.pa
PSTARS = (0.30, 0.35, 0.40, 0.45, 0.50)
FEATS = list(sn102.FULL) + ["or30", "adx", "vix_ratio", "prev_range"]


def rows():
    out = []
    for S in ph.sessions():
        got = pa.path(S, pa.I10)
        if got is None or got[1] > 15000:
            continue
        x = sn102.features(S, got[0])
        if x is None:
            continue
        h, l, c = S.F["h"], S.F["l"], S.F["c"]
        vl, vm = C.vix_prev(S.day)
        prev = S.s.get("prev")
        x = {**x, "or30": float((h[:30].max() - l[:30].min()) / c[29] * 100), "adx": C.adx(S.day) or np.nan,
             "vix_ratio": vl / vm if vl else np.nan, "prev_range": (prev[1] - prev[2]) / prev[3] * 100 if prev else np.nan}
        net = pa.settle(got[2], pa.I10, 3000.0)[0]
        out.append({"S": S, "day": S.day, "year": S.day[:4], "x": [x[f] for f in FEATS], "net": net, "gold_free": C.gold_free(S.day)})
    return out


def fit(X, y):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.impute import SimpleImputer
    m = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.5, max_iter=2000))
    m.fit(X, y)
    return m


if __name__ == "__main__":
    out_path = HERE / "results-sn154.json"
    if out_path.exists():
        raise SystemExit("SN154 is scored once")
    R = rows()
    X = np.array([r["x"] for r in R], dtype=float)
    y = np.array([r["net"] > 0 for r in R], dtype=int)
    net = np.array([r["net"] for r in R])
    yr = np.array([r["year"] for r in R])
    p_held = np.full(len(R), np.nan)
    pstar = {}
    for Y in ph.YEARS:
        tr, te = yr != Y, yr == Y
        m = fit(X[tr], y[tr])
        ptr = m.predict_proba(X[tr])[:, 1]
        pstar[Y] = max(PSTARS, key=lambda s: float(net[tr][ptr >= s].sum()))
        p_held[te] = m.predict_proba(X[te])[:, 1]
    adm = pa.admission()
    res = {"rows": len(R), "base_rate": round(float(y.mean()), 3), "pstar": pstar}
    for dname, sel in (("gold-free", lambda r: r["gold_free"]), ("all days", lambda r: True)):
        take = {r["day"]: r["net"] for k, r in enumerate(R) if sel(r) and p_held[k] >= pstar[r["year"]]}
        t = ph.table(take)
        pool = {}
        for r in R:
            if sel(r):
                pool.setdefault(r["year"], []).append(r["net"])
        rm, r95 = ph.random_control({Y: t[Y]["trades"] for Y in ph.YEARS}, pool, seed=154)
        s400 = sum(ph.straddle(r["S"], pa.I10, stress=400.0) or 0.0 for k, r in enumerate(R) if sel(r) and p_held[k] >= pstar[r["year"]])
        late = sum(ph.straddle(r["S"], pa.I10, late=1) or 0.0 for k, r in enumerate(R) if sel(r) and p_held[k] >= pstar[r["year"]])
        v = ph.verdict(take, [t[Y]["net"] for Y in ph.YEARS], r95, round(s400), round(late))
        # SN155: SN95-L's hot flag AND p >= 0.5
        hot = [k for k, r in enumerate(R) if sel(r) and adm.get((r["day"], "10:00", "R_today", 0.2, "top"), False)]
        alone = {R[k]["day"]: R[k]["net"] for k in hot}
        both = {R[k]["day"]: R[k]["net"] for k in hot if p_held[k] >= 0.5}
        ta, tb = ph.table(alone), ph.table(both)
        xs = sorted((x for x in both.values()), reverse=True)
        yrs_better = sum(tb[Y]["net"] > ta[Y]["net"] for Y in ph.YEARS)
        sn155 = {"sn95l_alone": {Y: ta[Y]["net"] for Y in ph.YEARS} | {"total": ph.tot(ta), "trades": len(alone)},
                 "consensus": {Y: tb[Y]["net"] for Y in ph.YEARS} | {"total": ph.tot(tb), "trades": len(both),
                                                                     "without_best_5": round(sum(xs[5:]))},
                 "years_better": yrs_better}
        sn155["PASS"] = bool(sn155["consensus"]["total"] > sn155["sn95l_alone"]["total"] and yrs_better >= 3 and sn155["consensus"]["without_best_5"] > 0)
        res[dname] = {"sn154_table": t, "sn154_random_mean": rm, "sn154_verdict": v, "sn155": sn155, "heldout_day_nets": take,
                      "consensus_day_nets": both}
        print(f"=== SN154 {dname}: {[t[Y]['net'] for Y in ph.YEARS]} | VERDICT {v} | random mean {rm}", flush=True)
        print(f"=== SN155 {dname}: {sn155}", flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
