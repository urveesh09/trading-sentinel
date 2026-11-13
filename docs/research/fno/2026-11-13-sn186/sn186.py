"""SN186 - the commonality of Gold's empty days (PLAN.md). Development sessions. Causal 09:45 features (yesterday's
ADX, gap %, OR30 width %, R_today at 09:45, VIX ratio, weekday, sessions to expiry) and what the day then did (range %,
trend efficiency, open-to-close %, biggest move after 10:00 %), Gold days against empty days. k-means (k = 4, seed
186) on the empty days' standardised causal features: each cluster's outcomes and the average net of four simple
plays (10:00 ATM straddle held, Rs 30k; 09:45-10:00 range break ATM +/- Rs 1,500 one lot; 09:45 open fade ATM +/- Rs
1,500; 10:00 1-OTM strangle held, Rs 15k) - where money existed in hindsight - and a cluster router chosen by LOYO.
Gold day vs empty day from 09:45 features: logistic regression, LOYO AUC."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pe  # noqa: E402

pw, p3, C = pe.pw, pe.p3, pe.C
FEAT = ("adx", "gap_pct", "or30_pct", "r_today_0945", "vix_ratio", "weekday", "dte")
PLAYS = ("straddle 10:00", "range break", "open fade", "strangle 10:00")


def causal(S):
    c, h, l = S.F["c"], S.F["h"], S.F["l"]
    adx = C.adx(S.day)
    vl, vm = C.vix_prev(S.day)
    rt = C.r_today(S, 30)
    wd = int(np.datetime64(S.day, "D").astype("datetime64[D]").view("int64") + 3) % 7
    return [adx if adx is not None else np.nan, S.F["gap"] * 100, (float(h[:31].max()) - float(l[:31].min())) / c[30] * 100,
            rt if rt is not None else np.nan, (vl / vm) if vl else np.nan, float(wd), float(C.sessions_until(S.day, S.s["expiry"]))]


def outcome(S):
    c, h, l, o = S.F["c"], S.F["h"], S.F["l"], S.F["o"]
    e = pw.FLAT
    path = float(np.sum(np.abs(np.diff(c[: e + 1]))))
    return {"range_pct": (float(h[: e + 1].max()) - float(l[: e + 1].min())) / o[0] * 100,
            "efficiency": abs(c[e] - o[0]) / path if path > 0 else 0.0, "open_close_pct": (c[e] / o[0] - 1) * 100,
            "max_move_after_10_pct": float(np.max(np.abs(c[46: e + 1] - c[45]))) / c[45] * 100}


def plays(S):
    out = []
    K = pw.atm(S, 45)
    got = pb.struct_path(S, 45, [(K, "CE"), (K, "PE")])
    out.append(p3.settle_target(got[2], 45, 6000.0)[0] if got is not None and got[1] <= 30000 else None)
    hi, lo = float(np.max(S.F["h"][30:45])), float(np.min(S.F["l"][30:45]))
    c = S.F["c"]
    rb = None
    for i in range(45, pw.I_MAX + 1):
        d = 1 if (c[i] > hi and c[i - 1] <= hi) else (-1 if (c[i] < lo and c[i - 1] >= lo) else 0)
        if d:
            r = pw.trade(S, i, "CE" if d > 0 else "PE", pw.atm(S, i), 1e9, target=1500.0, stop=-1500.0, max_lots=1)
            rb = None if r is None else r["net"]
            break
    out.append(rb)
    d = -1 if c[30] > S.F["o"][0] else 1
    r = pw.trade(S, 30, "CE" if d > 0 else "PE", pw.atm(S, 30), 1e9, target=1500.0, stop=-1500.0, max_lots=1)
    out.append(None if r is None else r["net"])
    out.append(p3.structure(S, 45, "strangle1", 15000.0, 3000.0))
    return out


pb = pe.pb

if __name__ == "__main__":
    out_path = HERE / "results-sn186.json"
    if out_path.exists():
        raise SystemExit("SN186 is scored once")
    from sklearn.cluster import KMeans
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    ss = pw.dev_sessions()
    gold = pe.gold_trade_days()
    rows = []
    for S in ss:
        rows.append({"day": S.day, "gold": S.day in gold, "x": causal(S), **outcome(S), "plays": plays(S)})
    res = {"sessions": len(rows), "gold_days": sum(r["gold"] for r in rows), "empty_days": sum(not r["gold"] for r in rows)}
    cmp_ = {}
    for name, idx in [(f, k) for k, f in enumerate(FEAT)]:
        g = [r["x"][idx] for r in rows if r["gold"] and r["x"][idx] == r["x"][idx]]
        e = [r["x"][idx] for r in rows if not r["gold"] and r["x"][idx] == r["x"][idx]]
        cmp_[name] = {"gold_median": round(float(np.median(g)), 3), "empty_median": round(float(np.median(e)), 3)}
    for k in ("range_pct", "efficiency", "open_close_pct", "max_move_after_10_pct"):
        cmp_[k] = {"gold_median": round(float(np.median([r[k] for r in rows if r["gold"]])), 3),
                   "empty_median": round(float(np.median([r[k] for r in rows if not r["gold"]])), 3)}
    res["gold_vs_empty"] = cmp_
    emp = [r for r in rows if not r["gold"]]
    X = np.array([r["x"] for r in emp], dtype=float)
    med = np.nanmedian(X, axis=0)
    X = np.where(np.isnan(X), med, X)
    mu, sd = X.mean(axis=0), X.std(axis=0) + 1e-9
    km = KMeans(n_clusters=4, n_init=10, random_state=186).fit((X - mu) / sd)
    clusters = {}
    for c_ in range(4):
        m = [r for r, lab in zip(emp, km.labels_) if lab == c_]
        clusters[str(c_)] = {"days": len(m), "centre": {f: round(float(v), 3) for f, v in zip(FEAT, km.cluster_centers_[c_] * sd + mu)},
                             "outcomes": {k: round(float(np.median([r[k] for r in m])), 3) for k in ("range_pct", "efficiency", "open_close_pct", "max_move_after_10_pct")},
                             "plays_mean_net": {p: round(float(np.mean([r["plays"][q] for r in m if r["plays"][q] is not None])), 1)
                                                if any(r["plays"][q] is not None for r in m) else None for q, p in enumerate(PLAYS)}}
    res["clusters"] = clusters
    lab = dict(zip([r["day"] for r in emp], km.labels_))
    router = {}
    for y in pe.YEARS:
        best = {}
        for c_ in range(4):
            def tot(q, held):
                return sum((r["plays"][q] or 0.0) for r in emp if lab[r["day"]] == c_ and ((r["day"][:4] == y) == held))
            q = max(range(len(PLAYS)), key=lambda q: tot(q, False))
            best[str(c_)] = PLAYS[q] if tot(q, False) > 0 else "none"
        net = sum((r["plays"][PLAYS.index(best[str(lab[r["day"]])])] or 0.0) for r in emp
                  if r["day"][:4] == y and best[str(lab[r["day"]])] != "none")
        router[y] = {"rule": best, "net": round(net)}
    res["cluster_router_loyo"] = router
    res["cluster_router_total"] = sum(v["net"] for v in router.values())
    XA = np.array([r["x"] for r in rows], dtype=float)
    XA = np.where(np.isnan(XA), np.nanmedian(XA, axis=0), XA)
    yA = np.array([r["gold"] for r in rows])
    aucs = {}
    for y in pe.YEARS:
        tr = np.array([r["day"][:4] != y for r in rows])
        m = LogisticRegression(max_iter=1000).fit((XA[tr] - mu) / sd, yA[tr])
        aucs[y] = round(float(roc_auc_score(yA[~tr], m.predict_proba((XA[~tr] - mu) / sd)[:, 1])), 3)
    res["gold_day_auc_loyo"] = aucs
    print("SN186", json.dumps(res), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
