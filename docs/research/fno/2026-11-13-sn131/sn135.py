"""SN135 - the 1-second learner (PLAN.md). Archive A (Apr 6 - Jul 27 2026) trains; archive B (Jul 28 - Nov 12)
tests once. Decisions every 10 s 09:20-15:00 while the opening-ATM strike is within 100 points; LightGBM predicts
the executable net of buying the opening-ATM call / put and selling 30 / 60 / 120 / 300 s later (house spread from
the print, charges, Rs 205); theta from A's last 17 days with a model on A's first 60; one position at a time."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn78"))
import gen  # noqa: E402
import sm  # noqa: E402
import sec_data as SD  # noqa: E402

M = sm.M
HZ = (30, 60, 120, 300)
S0, S1, STEP = 300, 20700, 10
FEAT = ("i5", "i10", "i30", "i60", "i120", "i300", "i600", "vol60", "vol600", "vol_open", "ret_open", "range_pos",
        "dist_k", "ce10", "ce30", "ce60", "ce300", "pe10", "pe30", "pe60", "pe300", "ce_stale", "pe_stale", "minute")


def ffill(a):
    out = a.copy()
    last = np.nan
    for k in range(len(out)):
        if np.isnan(out[k]):
            out[k] = last
        else:
            last = out[k]
    return out


def lastprint(a):
    out = np.full(len(a), -10 ** 6)
    last = -10 ** 6
    for k in range(len(a)):
        if not np.isnan(a[k]):
            last = k
        out[k] = last
    return out


def day_rows(day, rec, stress):
    ser = rec["series"]
    if not all(k in ser for k in ("INDEX", "CE", "PE")):
        return None
    K = rec["meta"]["CE"][0]
    ic = ffill(ser["INDEX"][3].astype(np.float64))
    if np.isnan(ic[S0]):
        return None
    oc = {o: ser[o][3].astype(np.float64) for o in ("CE", "PE")}
    om = {o: ffill(oc[o]) for o in oc}
    lp = {o: lastprint(oc[o]) for o in oc}
    d1 = np.concatenate([[0.0], np.diff(np.log(ic))])
    d1 = np.nan_to_num(d1)
    first = int(np.flatnonzero(~np.isnan(ic))[0])
    X, L, T = [], {f"{o}{h}": [] for o in ("CE", "PE") for h in HZ}, []
    hi, lo = np.fmax.accumulate(np.nan_to_num(ic, nan=-np.inf)), np.fmin.accumulate(np.nan_to_num(ic, nan=np.inf))
    for s in range(S0, S1 + 1, STEP):
        if abs(ic[s] - K) > 100:
            continue
        f = {f"i{k}": ((ic[s] / ic[s - k] - 1) * 1e4 if s - k >= first else np.nan) for k in (5, 10, 30, 60, 120, 300, 600)}
        f.update({"vol60": float(np.std(d1[max(first + 1, s - 59): s + 1])) * 1e4, "vol600": float(np.std(d1[max(first + 1, s - 599): s + 1])) * 1e4,
                  "vol_open": float(np.std(d1[first + 1: s + 1])) * 1e4, "ret_open": (ic[s] / ic[first] - 1) * 1e4,
                  "range_pos": (ic[s] - lo[s]) / (hi[s] - lo[s]) if hi[s] > lo[s] else 0.5, "dist_k": (ic[s] - K) / ic[s] * 1e4,
                  "minute": s / 60.0})
        for o in ("CE", "PE"):
            for k in (10, 30, 60, 300):
                a, b = (om[o][s - k] if s - k >= 0 else np.nan), om[o][s]
                f[f"{o.lower()}{k}"] = (b / a - 1) * 100 if a and a == a and b == b else np.nan
            f[f"{o.lower()}_stale"] = float(s - lp[o][s])
        X.append([f[k] for k in FEAT])
        T.append(s)
        for o in ("CE", "PE"):
            ok = not np.isnan(oc[o][s])
            ask = M.ask_of(float(oc[o][s])) if ok else None
            for h in HZ:
                j = min(s + h, 22499)
                y = np.nan
                if ok and j - lp[o][j] <= 10:
                    b = M.bid_of(float(oc[o][lp[o][j]]))
                    y = (b - ask) * M.LOT - M.charges(ask, b, M.LOT) - stress
                L[f"{o}{h}"].append(y)
    return np.array(X, dtype=np.float32), {k: np.array(v, dtype=np.float32) for k, v in L.items()}, np.array(T)


def dataset(days_dict, keep, stress=205.0):
    Xs, Ls, Ts, Ds = [], {f"{o}{h}": [] for o in ("CE", "PE") for h in HZ}, [], []
    for d in sorted(days_dict):
        if not keep(d):
            continue
        got = day_rows(d, days_dict[d], stress)
        if got is None or not len(got[2]):
            continue
        Xs.append(got[0])
        Ts.append(got[2])
        Ds += [d] * len(got[2])
        for k in Ls:
            Ls[k].append(got[1][k])
    return np.vstack(Xs), {k: np.concatenate(v) for k, v in Ls.items()}, np.concatenate(Ts), np.array(Ds)


if __name__ == "__main__":
    out_path = HERE / "results-sn135.json"
    if out_path.exists():
        raise SystemExit("SN135 is scored once")
    A = SD.load()["days"]
    SD.CACHE = HERE.parent / "2026-11-13-sn78" / "_local" / "seconds-1112.pkl"
    Bd = SD.load()["days"]
    XA, YA, TA, DA = dataset(A, lambda d: True)
    XB, YB, TB, DB = dataset(Bd, lambda d: d > "2026-07-27")
    print("A rows", len(DA), "days", len(set(DA)), "| B rows", len(DB), "days", len(set(DB)), flush=True)
    X = np.vstack([XA, XB])
    Y = {k: np.concatenate([YA[k], YB[k]]) for k in YA}
    T = np.concatenate([TA, TB])
    D = np.concatenate([DA, DB])
    adays = sorted(set(DA))
    inner = np.isin(D, adays[:60])
    val = np.isin(D, adays[60:])
    train = np.isin(D, adays)
    test = ~train
    hz_of = lambda k: int(k[2:])  # noqa: E731
    pt, th, vv = gen.learn(X, Y, D, T, inner, val, train, test, hz_of, STEP)
    nets, trades = gen.simulate(D, T, pt, Y, test, th, hz_of, STEP)
    n100, t100 = gen.simulate(D, T, pt, Y, test, th, hz_of, STEP, stress_shift=-105.0)
    rm, r95 = gen.random_null(D, T, Y, test, trades)
    s = gen.summary(nets, trades)
    res = {"theta": th, "validation_net": round(vv), "test": s, "test_at_100": gen.summary(n100, t100), "random_mean": rm, "random_95th": r95,
           "by_choice": {k: sum(1 for t_ in trades if t_[2] == k) for k in Y}}
    res["PASS"] = bool(s["net"] > 0 and s["net"] > r95 and s["without_best_5_days"] > 0)
    print("SN135", json.dumps(res), flush=True)
    out_path.write_text(json.dumps({**res, "trades": trades}, indent=1, default=float), encoding="utf-8")
