"""SN108 - order-book absorption on the NIFTY future (quote archive; PLAN.md). Information test only: do top-5 depth
imbalance, a signed volume proxy and absorption (volume that fails to move the price) add to the last 5- / 15-minute
return in predicting the next 5 / 15 / 30 minutes? Development Sep 10 - Oct 12, test Oct 13 - Nov 11; day bootstrap."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pa  # noqa: E402
import qa  # noqa: E402

DEV_END = "2026-10-12"
HZ = (5, 15, 30)
BASE = ("r5", "r15")
FULL = BASE + ("imb", "flow", "absorb")


def day_rows(day):
    q = qa.load(day)
    f = qa.front_fut(q, "NIFTY")
    if f is None:
        return []
    ok = f["usable"] & ~np.isnan(f["bid"]) & ~np.isnan(f["ask"])
    mid = np.where(ok, (f["bid"] + f["ask"]) / 2, np.nan)
    vol = f["vol"].copy()
    # carry the cumulative volume forward over gaps
    last = np.nan
    for i in range(len(vol)):
        if np.isnan(vol[i]):
            vol[i] = last
        else:
            last = vol[i]
    dv = np.concatenate([[np.nan], np.diff(vol)])
    rows = []
    for i in range(20, 345):
        if not ok[i] or np.isnan(mid[i - 5]) or np.isnan(mid[i - 15]):
            continue
        hist_dv = dv[1:i][~np.isnan(dv[1:i])]
        moves = np.abs(np.diff(mid[:i + 1]))
        moves = moves[~np.isnan(moves)]
        if len(hist_dv) < 10 or len(moves) < 10:
            continue
        med_dv = max(float(np.median(hist_dv)), 1.0)
        med_mv = max(float(np.median(moves)), 0.05)
        bq, aq = np.nansum(f["bidq"][:, i]), np.nansum(f["askq"][:, i])
        signs = np.sign(np.diff(mid[i - 5: i + 1]))
        flow = float(np.nansum(signs * dv[i - 4: i + 1]) / (5 * med_dv))
        v5 = float(np.nansum(dv[i - 4: i + 1]) / (5 * med_dv))
        m5 = abs(mid[i] - mid[i - 5]) / (5 * med_mv)
        absorb = float(np.sign(mid[i] - mid[i - 5]) * np.log((v5 + 0.1) / (m5 + 0.1)))
        r = {"day": day, "i": i, "r5": float(mid[i] / mid[i - 5] - 1), "r15": float(mid[i] / mid[i - 15] - 1),
             "imb": float((bq - aq) / (bq + aq)) if bq + aq > 0 else 0.0, "flow": flow, "absorb": absorb}
        for h in HZ:
            j = min(i + h, 374)
            r[f"y{h}"] = float(mid[j] / mid[i] - 1) if not np.isnan(mid[j]) else None
        rows.append(r)
    return rows


def ols(X, y):
    X1 = np.column_stack([np.ones(len(X)), X])
    return np.linalg.lstsq(X1, y, rcond=None)[0]


def pred(b, X):
    return np.column_stack([np.ones(len(X)), X]) @ b


if __name__ == "__main__":
    out_path = HERE / "results-sn108.json"
    if out_path.exists():
        raise SystemExit("SN108 is scored once")
    rows = [r for d in qa.days() for r in day_rows(d)]
    dev = [r for r in rows if r["day"] <= DEV_END]
    test = [r for r in rows if r["day"] > DEV_END]
    res = {"rows": len(rows), "dev_days": len({r['day'] for r in dev}), "test_days": len({r['day'] for r in test})}
    rng = np.random.default_rng(108)
    for h in HZ:
        d = [r for r in dev if r[f"y{h}"] is not None]
        t = [r for r in test if r[f"y{h}"] is not None]
        Xb, Xf = np.array([[r[k] for k in BASE] for r in d]), np.array([[r[k] for k in FULL] for r in d])
        yd = np.array([r[f"y{h}"] for r in d])
        bb, bf = ols(Xb, yd), ols(Xf, yd)
        Tb, Tf = np.array([[r[k] for k in BASE] for r in t]), np.array([[r[k] for k in FULL] for r in t])
        yt = np.array([r[f"y{h}"] for r in t])
        pb, pf = pred(bb, Tb), pred(bf, Tf)
        days = sorted({r["day"] for r in t})
        idx = {dd: [k for k, r in enumerate(t) if r["day"] == dd] for dd in days}
        gains = []
        for _ in range(2000):
            pick = np.concatenate([idx[days[k]] for k in rng.choice(len(days), len(days))])
            gains.append(np.corrcoef(pf[pick], yt[pick])[0, 1] - np.corrcoef(pb[pick], yt[pick])[0, 1])
        uni = {k: float(np.corrcoef(np.array([r[k] for r in t]), yt)[0, 1]) for k in FULL}
        res[f"h{h}"] = {"test_corr_base": float(np.corrcoef(pb, yt)[0, 1]), "test_corr_full": float(np.corrcoef(pf, yt)[0, 1]),
                        "gain_95ci": [float(np.percentile(gains, 2.5)), float(np.percentile(gains, 97.5))],
                        "test_mse_gain_pct": float(100 * (1 - ((pf - yt) ** 2).mean() / ((pb - yt) ** 2).mean())),
                        "single_feature_test_corr": uni, "coef_full": dict(zip(("const",) + FULL, map(float, bf)))}
        print(f"h{h}", json.dumps(res[f'h{h}'], indent=0)[:900], flush=True)
    res["INFORMATION_PASS"] = any(res[f"h{h}"]["gain_95ci"][0] > 0 for h in HZ)
    print("INFORMATION PASS:", res["INFORMATION_PASS"])
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
