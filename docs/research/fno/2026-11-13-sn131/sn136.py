"""SN136 - the order-book learner on real quotes (PLAN.md). Production's quote archive, 40 sealed days (hash-checked by
qa.load): every minute 09:20-15:00, NIFTY nearest expiry, ATM by the smallest |call mid - put mid|. Features from real
bid / ask and 5-level depth of the option pair and the future; labels: real ask in, real bid out after 1 / 3 / 5 / 10
minutes, charges + Rs 100 (the measured latency allowance; Rs 205 reported). Train the first 25 days (theta from days
19-25 with a model on days 1-18), test the last 15 once."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn101"))
import gen  # noqa: E402
import qa  # noqa: E402
import sm  # noqa: E402

M = sm.M
HZ = (1, 3, 5, 10)
FEAT = ("f1", "f3", "f5", "f15", "f_spread", "f_imb1", "f_imb5", "ce1", "ce3", "ce5", "pe1", "pe3", "pe5", "ce_spread",
        "pe_spread", "ce_imb1", "ce_imb5", "pe_imb1", "pe_imb5", "ce_vol5", "pe_vol5", "minute", "dte")


def mid(r, i):
    if r is None or not (0 <= i < qa.NM) or not r["usable"][i] or np.isnan(r["bid"][i]) or np.isnan(r["ask"][i]):
        return np.nan
    return float((r["bid"][i] + r["ask"][i]) / 2)


def imb(r, i, levels):
    if r is None or not r["usable"][i]:
        return np.nan
    b, a = np.nansum(r["bidq"][:levels, i]), np.nansum(r["askq"][:levels, i])
    return float((b - a) / (b + a)) if b + a > 0 else np.nan


def chg(r, i, k, pct=True):
    a, b = mid(r, i - k), mid(r, i)
    if np.isnan(a) or np.isnan(b) or a <= 0:
        return np.nan
    return (b / a - 1) * (100 if pct else 1e4)


def volchg(r, i):
    if r is None or i < 5 or np.isnan(r["vol"][i]) or np.isnan(r["vol"][i - 5]):
        return np.nan
    return float(r["vol"][i] - r["vol"][i - 5])


def day_rows(day, near, dte):
    q = qa.load(day)
    fut = qa.front_fut(q, "NIFTY")
    strikes = sorted({k[2] for k in q["opt"] if k[0] == "NIFTY" and k[1] == near})
    X, L, T = [], {f"{o}{h}": [] for o in ("CE", "PE") for h in HZ}, []
    for m in range(5, 346):
        best = None
        for s in strikes:
            ce, pe = q["opt"].get(("NIFTY", near, s, "CE")), q["opt"].get(("NIFTY", near, s, "PE"))
            a, b = mid(ce, m), mid(pe, m)
            if np.isnan(a) or np.isnan(b):
                continue
            if best is None or abs(a - b) < best[0]:
                best = (abs(a - b), s, ce, pe)
        if best is None:
            continue
        _g, K, ce, pe = best
        fm = mid(fut, m)
        f = {"f1": chg(fut, m, 1, False), "f3": chg(fut, m, 3, False), "f5": chg(fut, m, 5, False), "f15": chg(fut, m, 15, False),
             "f_spread": (float(fut["ask"][m] - fut["bid"][m]) / fm * 1e4) if fm == fm else np.nan,
             "f_imb1": imb(fut, m, 1), "f_imb5": imb(fut, m, 5), "minute": float(m), "dte": float(dte)}
        for o, r in (("ce", ce), ("pe", pe)):
            f[f"{o}1"], f[f"{o}3"], f[f"{o}5"] = chg(r, m, 1), chg(r, m, 3), chg(r, m, 5)
            f[f"{o}_spread"] = float(r["ask"][m] - r["bid"][m])
            f[f"{o}_imb1"], f[f"{o}_imb5"] = imb(r, m, 1), imb(r, m, 5)
            f[f"{o}_vol5"] = volchg(r, m)
        X.append([f[k] for k in FEAT])
        T.append(m)
        for o, r in (("CE", ce), ("PE", pe)):
            ask = float(r["ask"][m])
            for h in HZ:
                j = qa.last_before(r, min(m + h, 370), m + h - 1)
                y = np.nan
                if j is not None:
                    b = float(r["bid"][j])
                    y = (b - ask) * M.LOT - M.charges(ask, b, M.LOT) - 100.0
                L[f"{o}{h}"].append(y)
    return np.array(X, dtype=np.float32), {k: np.array(v, dtype=np.float32) for k, v in L.items()}, np.array(T)


if __name__ == "__main__":
    out_path = HERE / "results-sn136.json"
    if out_path.exists():
        raise SystemExit("SN136 is scored once")
    sm.C.years()
    exps = sorted(qa.manifest()["option_expiries"]["NIFTY"])
    Xs, Ls, Ts, Ds = [], {f"{o}{h}": [] for o in ("CE", "PE") for h in HZ}, [], []
    days = [d for d in qa.days() if d not in exps]
    for d in days:
        near = [e for e in exps if e > d][0]
        dte = len([x for x in qa.days() if d < x <= near])
        x, l_, t = day_rows(d, near, dte)
        if not len(t):
            continue
        Xs.append(x)
        Ts.append(t)
        Ds += [d] * len(t)
        for k in Ls:
            Ls[k].append(l_[k])
    X, T, D = np.vstack(Xs), np.concatenate(Ts), np.array(Ds)
    Y = {k: np.concatenate(v) for k, v in Ls.items()}
    ud = sorted(set(D))
    inner, val, train = np.isin(D, ud[:18]), np.isin(D, ud[18:25]), np.isin(D, ud[:25])
    test = ~train
    print("rows", len(D), "days", len(ud), "test days", len(ud) - 25, flush=True)
    hz_of = lambda k: int(k[2:])  # noqa: E731
    pt, th, vv = gen.learn(X, Y, D, T, inner, val, train, test, hz_of, 1)
    nets, trades = gen.simulate(D, T, pt, Y, test, th, hz_of, 1)
    n205, t205 = gen.simulate(D, T, pt, Y, test, th, hz_of, 1, stress_shift=105.0)
    rm, r95 = gen.random_null(D, T, Y, test, trades)
    s = gen.summary(nets, trades)
    unseen = {d: v for d, v in nets.items() if d > "2026-10-28"}
    res = {"theta": th, "validation_net": round(vv), "test_at_100": s, "test_at_205": gen.summary(n205, t205), "random_mean": rm,
           "random_95th": r95, "unseen_oct29_nov11": {"days": len(unseen), "net": round(sum(unseen.values()))}}
    res["PASS"] = bool(s["net"] > 0 and res["test_at_205"]["net"] > 0 and s["net"] > r95)
    print("SN136", json.dumps(res), flush=True)
    out_path.write_text(json.dumps({**res, "trades": trades}, indent=1, default=float), encoding="utf-8")
