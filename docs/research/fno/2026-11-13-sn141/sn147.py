"""SN147 - the 1-second learner swapped (PLAN.md): train on archive B (Jul 28 - Nov 12; theta from its last days with a
model on its first 55), test on archive A (Apr 6 - Jul 27). Same features, labels and policy as SN135."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn131"))
import gen  # noqa: E402
import sn135  # noqa: E402

if __name__ == "__main__":
    out_path = HERE / "results-sn147.json"
    if out_path.exists():
        raise SystemExit("SN147 is scored once")
    A = sn135.SD.load()["days"]
    sn135.SD.CACHE = HERE.parent / "2026-11-13-sn78" / "_local" / "seconds-1112.pkl"
    Bd = sn135.SD.load()["days"]
    XA, YA, TA, DA = sn135.dataset(A, lambda d: True)
    XB, YB, TB, DB = sn135.dataset(Bd, lambda d: d > "2026-07-27")
    X = np.vstack([XB, XA])
    Y = {k: np.concatenate([YB[k], YA[k]]) for k in YA}
    T, D = np.concatenate([TB, TA]), np.concatenate([DB, DA])
    order = np.lexsort((T, D))
    X, T, D = X[order], T[order], D[order]
    Y = {k: v[order] for k, v in Y.items()}
    bdays = sorted(set(DB))
    inner, val, train = np.isin(D, bdays[:55]), np.isin(D, bdays[55:]), np.isin(D, bdays)
    test = ~train
    hz_of = lambda k: int(k[2:])  # noqa: E731
    pt, th, vv = gen.learn(X, Y, D, T, inner, val, train, test, hz_of, sn135.STEP)
    nets, trades = gen.simulate(D, T, pt, Y, test, th, hz_of, sn135.STEP)
    rm, r95 = gen.random_null(D, T, Y, test, trades)
    res = {"theta": th, "validation_net": round(vv), "test_on_A": gen.summary(nets, trades), "random_mean": rm, "random_95th": r95}
    print("SN147", json.dumps(res), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
