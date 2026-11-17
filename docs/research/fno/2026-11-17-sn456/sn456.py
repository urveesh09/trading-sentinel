"""SN456: does prior-session participant positioning add information beyond the opening move? (PLAN.md section 1, frozen at
83e1b444; the definitions live in feat456.py and are the plan's). Forecast stage only; the option stage runs only if the
improvement holds (a separate script, committed before it runs).

Usable date: y, every baseline feature and z (primary: report t-1 ON_TIME or ASSUMED, report t-2 valid, 60 earlier x values).
BASE = gap, opening return, range, previous return, monthly expiry, roll window, weekly expiry, vol20; AUG = BASE + z.
Ridge (alpha 10) on training-standardised features (a constant column keeps sd 1), intercept unpenalised.
Anchored: the first 250 usable dates train; out-of-sample blocks of 125 usable dates, refit at each block start.
CW f_t = (y - yB)^2 - [(y - yA)^2 - (yB - yA)^2]; p = share of 2,000 circular block-bootstrap (block 20, seed 456) means of
the centred f at or above the observed mean. Permutation: z shuffled within calendar quarters (500, seed 4560), full refit.
Holds iff CW p < 0.05, p_perm < 0.05, CW mean > 0 in >= 2/3 of blocks, CW mean > 0 outside the roll window.
Writes results-sn456.json and _local/sn456_forecasts.json (out-of-sample forecasts, each block's in-sample 70th percentile and
quintile edges of |fitted|, for SN462 / SN475 / the option stage).
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import feat456 as F  # noqa: E402

OUT = HERE / "results-sn456.json"
FC = HERE / "_local" / "sn456_forecasts.json"
BASE = ["gap", "openret", "range", "prevret", "monthly_expiry", "roll", "weekly_expiry", "vol20"]
ALPHA, TRAIN0, BLOCK = 10.0, 250, 125


def ridge(Xtr, ytr, Xte, alpha):
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd[sd == 0] = 1.0
    A, Bm = (Xtr - mu) / sd, (Xte - mu) / sd
    ym = ytr.mean()
    beta = np.linalg.solve(A.T @ A + alpha * np.eye(A.shape[1]), A.T @ (ytr - ym))
    return ym + Bm @ beta, ym + A @ beta


def oos(X, y, alpha):
    n = len(y)
    pred, blk, p70, qed = np.full(n, np.nan), np.full(n, -1), {}, {}
    b = 0
    for s in range(TRAIN0, n, BLOCK):
        e = min(n, s + BLOCK)
        pt, pin = ridge(X[:s], y[:s], X[s:e], alpha)
        pred[s:e], blk[s:e] = pt, b
        p70[b] = float(np.percentile(np.abs(pin), 70))
        qed[b] = [float(np.percentile(np.abs(pin), q)) for q in (20, 40, 60, 80)]
        b += 1
    return pred, blk, p70, qed


def cw(y, yb, ya):
    return (y - yb) ** 2 - ((y - ya) ** 2 - (yb - ya) ** 2)


def cbb_p(f, seed=456, n=2000, block=20):
    rng = np.random.default_rng(seed)
    m = len(f)
    k = int(np.ceil(m / block))
    starts = rng.integers(0, m, (n, k))
    idx = ((starts[:, :, None] + np.arange(block)) % m).reshape(n, -1)[:, :m]
    fc = f - f.mean()
    bm = fc[idx].mean(1)
    return float(np.mean(bm >= f.mean())), [float(np.percentile(f[idx].mean(1), q)) for q in (5, 95)]


def design(rows, dates, zkey):
    Xb = np.array([[rows[d][k] for k in BASE] for d in dates], float)
    z = np.array([rows[d][zkey] for d in dates], float)
    y = np.array([rows[d]["y"] for d in dates], float)
    return Xb, z, y


def run(rows, dates, zkey, alpha, perm=0):
    Xb, z, y = design(rows, dates, zkey)
    yb, blk, p70b, qb = oos(Xb, y, alpha)
    ya, _blk, p70a, qa = oos(np.column_stack([Xb, z]), y, alpha)
    o = blk >= 0
    f = cw(y[o], yb[o], ya[o])
    res = {"oos_dates": int(o.sum()), "blocks": int(blk.max() + 1), "cw_mean": round(float(f.mean()), 3)}
    res["cw_p"], ci = cbb_p(f)
    res["cw_ci90"] = [round(c, 3) for c in ci]
    res["mspe_base"], res["mspe_aug"] = round(float(np.mean((y[o] - yb[o]) ** 2)), 2), round(float(np.mean((y[o] - ya[o]) ** 2)), 2)
    nz = y[o] != 0
    res["hit_base"] = round(float(np.mean(np.sign(yb[o][nz]) == np.sign(y[o][nz]))), 4)
    res["hit_aug"] = round(float(np.mean(np.sign(ya[o][nz]) == np.sign(y[o][nz]))), 4)
    bm = [float(f[blk[o] == b].mean()) for b in range(res["blocks"])]
    res["blocks_cw_positive"] = sum(m > 0 for m in bm)
    res["block_cw_means"] = [round(m, 2) for m in bm]
    dd = [d for d, ok in zip(dates, o) if ok]
    roll = np.array([rows[d]["roll"] > 0 for d in dd])
    res["cw_mean_outside_roll"] = round(float(f[~roll].mean()), 3)
    res["cw_mean_roll_only"] = round(float(f[roll].mean()), 3) if roll.any() else None
    me = np.array([rows[d]["month_end"] for d in dd])
    mx = np.array([bool(rows[d].get("mix_break")) for d in dd])
    keep = ~me & ~mx
    res["cw_without_month_end_and_mix_breaks"] = {"dates": int(keep.sum()), "cw_mean": round(float(f[keep].mean()), 3),
                                                  "cw_p": cbb_p(f[keep])[0]}
    # partial correlation of z with y beyond gap and opening return (out-of-sample dates)
    G = np.column_stack([np.ones(o.sum()), Xb[o][:, 0], Xb[o][:, 1]])
    ry = y[o] - G @ np.linalg.lstsq(G, y[o], rcond=None)[0]
    rz = z[o] - G @ np.linalg.lstsq(G, z[o], rcond=None)[0]
    res["partial_corr_z_y"] = round(float(np.corrcoef(ry, rz)[0, 1]), 4)
    res["raw_corr_z_y"] = round(float(np.corrcoef(z[o], y[o])[0, 1]), 4)
    if perm:
        rng = np.random.default_rng(4560)
        q = collections.defaultdict(list)
        for i, d in enumerate(dates):
            q[(d[:4], (int(d[5:7]) - 1) // 3)].append(i)
        ms = []
        for _ in range(perm):
            zp = z.copy()
            for ix in q.values():
                zp[ix] = z[rng.permutation(ix)]
            yp, *_ = oos(np.column_stack([Xb, zp]), y, alpha)
            ms.append(float(cw(y[o], yb[o], yp[o]).mean()))
        res["perm_p"] = round(float((1 + sum(m >= f.mean() for m in ms)) / (perm + 1)), 4)
        res["perm_mean_p95"] = round(float(np.percentile(ms, 95)), 3)
    keep_fc = {"dates": dd, "y": y[o].tolist(), "yb": yb[o].tolist(), "ya": ya[o].tolist(), "block": blk[o].tolist(),
               "p70_a": p70a, "p70_b": p70b, "q_a": qa, "q_b": qb}
    return res, keep_fc


def main():
    if OUT.exists():
        raise SystemExit("SN456 is scored once")
    cal, rows, rep = F.features()
    res = {"reports": {"files": len(rep), "valid": sum(r["valid"] for r in rep.values()),
                       "invalid_by_reason": dict(collections.Counter(r["why"] for r in rep.values() if not r["valid"]))},
           "futures_sessions": len(cal)}
    res["availability_of_report_t_minus_1"] = dict(collections.Counter(rows[d]["avail"] for d in cal))
    base_ok = [d for d in cal if "y" in rows[d] and all(rows[d].get(k) is not None for k in BASE)]
    prim = [d for d in base_ok if rows[d].get("z") is not None]
    lag = [d for d in base_ok if rows[d].get("z2") is not None]
    res["dates"] = {"with_y_and_baseline": len(base_ok), "primary_matched": len(prim), "extra_lag_matched": len(lag),
                    "missing_pair_or_late": len(base_ok) - len(prim), "first": prim[0], "last": prim[-1]}
    main_r, fc = run(rows, prim, "z", ALPHA, perm=500)
    res["PRIMARY"] = main_r
    holds = (main_r["cw_p"] < 0.05 and main_r["perm_p"] < 0.05 and main_r["blocks_cw_positive"] >= np.ceil(2 * main_r["blocks"] / 3)
             and main_r["cw_mean_outside_roll"] > 0)
    res["improvement_holds"] = bool(holds)
    res["EXTRA_LAG"] = run(rows, lag, "z2", ALPHA)[0]
    res["ALPHA_1"] = run(rows, prim, "z", 1.0)[0]
    res["ALPHA_100"] = run(rows, prim, "z", 100.0)[0]
    res["verdict"] = "IMPROVEMENT_HOLDS (option stage next)" if holds else "CLOSED (no forecast value beyond the opening move)"
    FC.write_text(json.dumps(fc), encoding="utf-8")
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
