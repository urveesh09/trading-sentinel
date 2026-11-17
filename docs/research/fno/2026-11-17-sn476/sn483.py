"""SN483: oil and the rupee as Gold's risk input (PLAN.md SN483, frozen at bf895633; details fixed here before any number).

Data: FRED DCOILBRENTEU (Brent, USD) and DEXINUS (INR per USD), fetched once with a generic client (fredgraph.csv; hashes recorded).
ALFRED first-release dates were not fetched (one vintage file per week would be needed), so the plan's conservative lags apply:
Brent observed on d is usable from the first IST session after the Thursday following d; DEXINUS observed on d is usable from the
first session after the Tuesday following d's Monday-Friday week. At a Gold trade's session t: the latest usable observation of each
series and its change from the previous observation, dlog; |dlog| as a z-score against that series' previous 60 |dlog| values;
JOINT = z(Brent) + z(USD/INR).
Trades: Gold v5's GOLD_30K @205 trade log, 2022 and 2023-26 (186 trades). Targets: MAE60 = the index's largest move against the trade
over the 60 minutes after entry, in entry-ATR units (session index minutes, the replay's own c and atr); STOP = the trade left by its
stop; ADD_NET = the added pieces' net (trades with an add). Baseline: the session's opening gap, Gold's volatility ratio (VOLT
atr / median), expert dummies, side. Leave-one-year-out (2022, 2023, 2024, 2025, 2026): ridge (alpha 1, standardized on training)
for MAE60 and ADD_NET, logistic (L2 1.0, 200 Newton steps) for STOP; per held-out year the MSE (or Brier) change from adding JOINT
(negative = better) and the correlation of JOINT with the target. Information = a better held-out score in >= 4 of 5 years for a
target. Only then: the reduction "skip the add when JOINT >= 1.0" as a Gold variant (goldx skip_add), GOLD_30K / ONE_15K, both paths,
both stresses, with sn480.compare.
"""
from __future__ import annotations

import bisect
import csv
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn480 as A  # noqa: E402

goldx, g = A.goldx, A.g
OUT = HERE / "results-sn483.json"
FRED = Path(r"C:\Users\Urveesh\AppData\Local\Temp\claude\f191b6166a36c84a\b7c0aa9b-c954-4f08-9df8-57422081ea0c\scratchpad\dl\fred")
YEARS5 = ("2022", "2023", "2024", "2025", "2026")


def series(name):
    p = FRED / f"{name}.csv"
    rows = []
    with open(p, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            v = r[name].strip()
            if v and v != ".":
                rows.append((r["observation_date"], float(v)))
    return rows, hashlib.sha256(p.read_bytes()).hexdigest()


def usable_from(d, kind):
    x = dt.date.fromisoformat(d)
    if kind == "brent":
        thu = x + dt.timedelta(days=(3 - x.weekday()) % 7 or 7)
        return (thu + dt.timedelta(days=1)).isoformat()
    mon_next = x + dt.timedelta(days=7 - x.weekday())
    return (mon_next + dt.timedelta(days=2)).isoformat()


def build(rows, kind):
    out = []
    absd = []
    for k in range(1, len(rows)):
        d, v = rows[k]
        dl = float(np.log(v / rows[k - 1][1]))
        hist = absd[-60:]
        z = (abs(dl) - np.mean(hist)) / np.std(hist) if len(hist) >= 60 and np.std(hist) > 0 else None
        out.append((usable_from(d, kind), d, dl, z))
        absd.append(abs(dl))
    out.sort()
    return out


def latest(tab, day):
    k = bisect.bisect_right([r[0] for r in tab], day) - 1
    return tab[k] if k >= 0 else None


CAPT = {}
_gold_one = None


def capture(S, sg, v, wallet, full_lots, ctx, vol_day, realized, loss):
    res = _gold_one(S, sg, v, wallet, full_lots, ctx, vol_day, realized, loss)
    if res is not None:
        i, d = sg["i"], (1 if sg["opt"] == "CE" else -1)
        c, atr = S.F["c"], S.F["atr"]
        win = c[i + 1:min(len(c), i + 61)]
        mae = float(np.max(-d * (win - c[i])) / atr[i]) if len(win) else 0.0
        a, med = goldx.L.VOLT.get(S.day, (None, None))
        CAPT[(S.day, i)] = {"mae60": max(0.0, mae), "gap": float(S.F.get("gap", 0.0)) if hasattr(S.F, "get") else 0.0,
                            "volratio": (a / med) if a and med else 1.0, "d": d, "expert": sg.get("expert")}
    return res


def ridge(X, y, alpha=1.0):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1
    Z = (X - mu) / sd
    w = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ (y - y.mean()))
    return lambda Xn: ((Xn - mu) / sd) @ w + y.mean()


def logit(X, y, lam=1.0, steps=200):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1
    Z = np.c_[np.ones(len(X)), (X - mu) / sd]
    w = np.zeros(Z.shape[1])
    for _ in range(steps):
        p = 1 / (1 + np.exp(-Z @ w))
        H = Z.T @ (Z * (p * (1 - p))[:, None]) + lam * np.eye(len(w))
        w -= np.linalg.solve(H, Z.T @ (p - y) + lam * w)
    return lambda Xn: 1 / (1 + np.exp(-(np.c_[np.ones(len(Xn)), (Xn - mu) / sd] @ w)))


def main():
    global _gold_one
    if OUT.exists():
        raise SystemExit("SN483 is scored once")
    (brent, hb), (fx, hf) = series("DCOILBRENTEU"), series("DEXINUS")
    tb, tf = build(brent, "brent"), build(fx, "fx")
    goldx.install()
    _gold_one = g.C.gold_one
    g.C.gold_one = capture
    trades = []
    for pname, years in A.PATHS:
        CAPT.clear()
        _s, _d, log = A.run(years, 205.0, goldx.GOLD_30K)
        for t in log:
            c = CAPT.get((t["day"], t["i"]))
            lb, lf = latest(tb, t["day"]), latest(tf, t["day"])
            if c is None or lb is None or lf is None or lb[3] is None or lf[3] is None:
                continue
            trades.append({"day": t["day"], "year": t["day"][:4], "joint": lb[3] + lf[3], "brent_obs": lb[1], "fx_obs": lf[1], **c,
                           "stop": 1.0 if t["reason"] == "stop" else 0.0, "add_net": sum(p[2] for p in t["pieces"][1:]) if len(t["pieces"]) > 1 else None,
                           "staleness_days": [(dt.date.fromisoformat(t["day"]) - dt.date.fromisoformat(lb[1])).days,
                                              (dt.date.fromisoformat(t["day"]) - dt.date.fromisoformat(lf[1])).days]})
    g.C.gold_one = _gold_one
    experts = sorted({t["expert"] for t in trades})

    def X(rows, with_joint):
        cols = [[r["gap"], r["volratio"], r["d"]] + [1.0 if r["expert"] == e else 0.0 for e in experts[1:]] + ([r["joint"]] if with_joint else []) for r in rows]
        return np.asarray(cols, float)
    res = {"sources": {"DCOILBRENTEU": hb, "DEXINUS": hf}, "trades": len(trades), "stops": int(sum(t["stop"] for t in trades)),
           "adds": sum(1 for t in trades if t["add_net"] is not None),
           "median_staleness_days": [float(np.median([t["staleness_days"][0] for t in trades])), float(np.median([t["staleness_days"][1] for t in trades]))],
           "targets": {}}
    for target in ("mae60", "stop", "add_net"):
        rows = [t for t in trades if t[target] is not None]
        per = {}
        for Y in YEARS5:
            tr = [r for r in rows if r["year"] != Y]
            te = [r for r in rows if r["year"] == Y]
            if len(te) < 3 or len(tr) < 20 or (target == "stop" and sum(r["stop"] for r in tr) < 2):
                per[Y] = {"n_test": len(te), "skipped": True}
                continue
            y_tr = np.asarray([r[target] for r in tr], float)
            y_te = np.asarray([r[target] for r in te], float)
            out = {}
            for wj in (False, True):
                f = (logit if target == "stop" else ridge)(X(tr, wj), y_tr)
                out[wj] = float(np.mean((f(X(te, wj)) - y_te) ** 2))
            j = np.asarray([r["joint"] for r in te])
            per[Y] = {"n_test": len(te), "score_base": round(out[False], 4), "score_with_joint": round(out[True], 4), "change": round(out[True] - out[False], 5),
                      "corr_joint_target": round(float(np.corrcoef(j, y_te)[0, 1]), 3) if np.std(y_te) > 0 and np.std(j) > 0 else None}
        better = sum(1 for v in per.values() if not v.get("skipped") and v["change"] < 0)
        res["targets"][target] = {"by_year": per, "years_better": better, "information": better >= 4}
    res["reduction_tested"] = any(v["information"] for v in res["targets"].values())
    if res["reduction_tested"]:
        jmap = {t["day"]: t["joint"] for t in trades}
        skip = lambda day, sg: jmap.get(day, -9) >= 1.0  # noqa: E731
        cells = {}
        for lname, wallet in (("GOLD_30K", goldx.GOLD_30K), ("ONE_15K", goldx.ONE_15K)):
            for pname, years in A.PATHS:
                for st in A.STRESSES:
                    sb, db, lb = A.run(years, st, wallet)
                    sc, dc, lc = A.run(years, st, wallet, skip_add=skip)
                    c = A.compare(sb, db, lb, sc, dc, lc)
                    c.pop("fail_events", None)
                    cells[f"{lname} {pname} @{int(st)}"] = c
        res["reduction"] = cells
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1)[:6000])


if __name__ == "__main__":
    main()
