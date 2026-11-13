"""Phase E helpers: hold-to-the-close labels (CE999 / PE999 / ST999 = buy now, sell at 15:10) for every phase-D row,
and SN95's causal hot-day flag per row. Imports phase D's frozen engine (sm, run); edits nothing."""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn131"))
import run  # noqa: E402
import sm  # noqa: E402

C, M, pa = sm.C, sm.M, sm.pa
LOCAL = HERE / "_local"


def close_labels(data):
    LOCAL.mkdir(exist_ok=True)
    p = LOCAL / "close_labels.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    C.years()
    sess = {S.day: S for y in C.YEARS for S in C.years()[y].ordered()}
    n = len(data["day"])
    out = {k: np.full(n, np.nan, dtype=np.float32) for k in ("CE999", "PE999")}
    start = {}
    for k, d in enumerate(data["day"]):
        start.setdefault(d, k)
    for d, k0 in start.items():
        S = sess[d]
        c = S.F["c"]
        for i in range(sm.I0, sm.I1 + 1):
            K = int(round(c[i] / M.STEP) * M.STEP)
            for opt in ("CE", "PE"):
                rec = S.option(K, opt)
                if rec is None or not rec[6][i]:
                    continue
                ask = M.ask_of(float(rec[0][3][i]))
                j = C.FLAT
                col = rec[0][3][: j + 1]
                ok = np.flatnonzero(~np.isnan(col))
                if not len(ok) or j - ok[-1] > 5:
                    continue
                b = float(rec[4][j] if rec[6][j] else rec[5][j])
                out[f"{opt}999"][k0 + i - sm.I0] = (b - ask) * M.LOT - M.charges(ask, b, M.LOT) - sm.STRESS
    out["ST999"] = (out["CE999"] + out["PE999"]).astype(np.float32)
    p.write_bytes(pickle.dumps(out))
    return out


def hot_rows(data):
    adm = pa.admission()
    hot_day = {d: bool(adm.get((d, "10:00", "R_today", 0.2, "top"), False)) for d in np.unique(data["day"])}
    return np.array([hot_day[d] for d in data["day"]]) & (data["minute"] >= pa.I10)


def with_labels(data, extra):
    return {**data, "Y": {**data["Y"], **extra}}
