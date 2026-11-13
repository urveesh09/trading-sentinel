"""SN105 - banks when NIFTY cancels them (information only; PLAN.md). A BANKNIFTY proxy from 12 bank stocks (fixed
approximate weights; no BANKNIFTY index or option history exists in the repo), the rest of NIFTY from SN96's fitted
non-financial weights. Does the bank move continue over the next 30 / 60 minutes, beyond what the bank proxy's own
recent move says, when it is cancelled inside NIFTY? Development Feb-Apr 2026, test May-Oct, day bootstrap."""
from __future__ import annotations

import csv
import gzip
import json
import sys
from pathlib import Path
from urllib.parse import quote

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn92"))
import pa  # noqa: E402
import sn96  # noqa: E402

C = pa.C
BANKS = {"HDFCBANK": .28, "ICICIBANK": .25, "SBIN": .09, "KOTAKBANK": .08, "AXISBANK": .08, "INDUSINDBK": .03,
         "BANKBARODA": .03, "FEDERALBNK": .03, "IDFCFIRSTB": .03, "AUBANK": .025, "PNB": .025, "CANBK": .025}
KS = range(2, 18)


def load(names):
    bars = {s: {} for s in names}
    for s in names:
        for part in ("2026-01-01_2026-07-19", "2026-07-20_2026-07-31"):
            p = sn96.RAW / f"{quote(s, safe='-')}_15minute_{part}.json"
            if p.exists():
                for st, o, h, l, c, v in json.loads(p.read_text(encoding="utf-8"))["data"]["candles"]:
                    k = sn96._k(st)
                    if 0 <= k < sn96.NB:
                        bars[s].setdefault(st[:10], np.full(sn96.NB, np.nan))[k] = c
    with gzip.open(sn96.PROD, "rt", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["kind"] == "I" and r["ticker"] in bars:
                k = sn96._k(r["stamp"])
                if 0 <= k < sn96.NB:
                    bars[r["ticker"]].setdefault(r["stamp"][:10], np.full(sn96.NB, np.nan))[k] = float(r["close"])
    return bars


def basket(bars, w, d, k0, k1):
    num = den = 0.0
    for s, ws in w.items():
        b = bars.get(s, {}).get(d)
        if b is None or np.isnan(b[k0]) or np.isnan(b[k1]):
            continue
        num += ws * (b[k1] / b[k0] - 1)
        den += ws
    return (num / den, den) if den > 0 else (None, 0.0)


def rows_for(bars, W_rest, sess):
    out = []
    for d in sorted(sess):
        if d < "2026-02-01":
            continue
        c = sess[d].F["c"]
        for k in KS:
            B, cov = basket(bars, BANKS, d, k - 2, k)
            Rr, cov_r = basket(bars, W_rest, d, k - 2, k)
            B15, _ = basket(bars, BANKS, d, k - 1, k)
            f2, _ = basket(bars, BANKS, d, k, k + 2)
            f4, _ = basket(bars, BANKS, d, k, k + 4) if k + 4 <= 21 else (None, 0)
            if B is None or Rr is None or cov < 0.8 or B == 0:
                continue
            agree = np.mean([np.sign(bars[s][d][k] / bars[s][d][k - 2] - 1) == np.sign(B) for s in BANKS
                             if d in bars[s] and not np.isnan(bars[s][d][k]) and not np.isnan(bars[s][d][k - 2])])
            m = 15 * k + 14
            sg = float(np.sign(B))
            out.append({"day": d, "k": k, "B": B, "absB": abs(B), "B15s": (B15 or 0.0) * sg, "Rs": Rr * sg, "agree": float(agree),
                        "absN": float(abs(c[m] / c[m - 30] - 1)), "y30": None if f2 is None else f2 * sg,
                        "y60": None if f4 is None else f4 * sg})
    return out


def ols(X, y):
    X1 = np.column_stack([np.ones(len(X)), X])
    return np.linalg.lstsq(X1, y, rcond=None)[0]


def pr(b, X):
    return np.column_stack([np.ones(len(X)), X]) @ b


if __name__ == "__main__":
    out_path = HERE / "results-sn105.json"
    if out_path.exists():
        raise SystemExit("SN105 is scored once")
    _rows, W, names = sn96.build()
    W_rest = {s: x for s, x in W.items() if s not in sn96.FIN}
    bars = load(list(BANKS) + list(W_rest))
    print("bank names with data", {s: len(bars[s]) for s in BANKS}, flush=True)
    sess = C.years()["2026"].sessions
    rows = rows_for(bars, W_rest, sess)
    dev = [r for r in rows if r["day"] <= "2026-04-30"]
    test = [r for r in rows if r["day"] >= "2026-05-01"]
    q80, nmed = np.quantile([r["absB"] for r in dev], 0.8), np.median([r["absN"] for r in dev])
    for r in rows:
        r["cancel"] = float(r["absB"] >= q80 and r["Rs"] < 0 and r["absN"] <= nmed)
    BASE, FULL = ("absB", "B15s"), ("absB", "B15s", "Rs", "agree", "cancel", "absN")
    res = {"rows": len(rows), "dev": len(dev), "test": len(test), "q80_absB": float(q80), "median_absN": float(nmed)}
    rng = np.random.default_rng(105)
    for tgt in ("y30", "y60"):
        d = [r for r in dev if r[tgt] is not None]
        t = [r for r in test if r[tgt] is not None]
        yd, yt = np.array([r[tgt] for r in d]), np.array([r[tgt] for r in t])
        bb = ols(np.array([[r[f] for f in BASE] for r in d]), yd)
        bf = ols(np.array([[r[f] for f in FULL] for r in d]), yd)
        pb = pr(bb, np.array([[r[f] for f in BASE] for r in t]))
        pf = pr(bf, np.array([[r[f] for f in FULL] for r in t]))
        days = sorted({r["day"] for r in t})
        idx = {dd: [k for k, r in enumerate(t) if r["day"] == dd] for dd in days}
        canc = {dd: [yt[k] for k in idx[dd] if t[k]["cancel"]] for dd in days}
        canc = {dd: v for dd, v in canc.items() if v}
        gains, cm = [], []
        for _ in range(2000):
            pick = np.concatenate([idx[days[k]] for k in rng.choice(len(days), len(days))])
            gains.append(np.corrcoef(pf[pick], yt[pick])[0, 1] - np.corrcoef(pb[pick], yt[pick])[0, 1])
            if canc:
                ck = list(canc)
                cm.append(np.mean(np.concatenate([canc[ck[j]] for j in rng.choice(len(ck), len(ck))])))
        res[tgt] = {"test_corr_bank_only": float(np.corrcoef(pb, yt)[0, 1]), "test_corr_with_cancellation": float(np.corrcoef(pf, yt)[0, 1]),
                    "gain_95ci": [float(np.percentile(gains, 2.5)), float(np.percentile(gains, 97.5))],
                    "continuation_all_test_mean_bp": float(1e4 * yt.mean()),
                    "continuation_in_cancel_state_mean_bp": float(1e4 * np.mean(np.concatenate(list(canc.values())))) if canc else None,
                    "cancel_obs_test": int(sum(len(v) for v in canc.values())), "cancel_days_test": len(canc),
                    "continuation_cancel_95ci_bp": [float(1e4 * np.percentile(cm, 2.5)), float(1e4 * np.percentile(cm, 97.5))] if cm else None,
                    "coef_full": dict(zip(("const",) + FULL, map(float, bf)))}
        print(tgt, json.dumps(res[tgt], indent=0)[:1100], flush=True)
    res["INFORMATION_PASS"] = any(res[t]["gain_95ci"][0] > 0 or (res[t]["continuation_cancel_95ci_bp"] and res[t]["continuation_cancel_95ci_bp"][0] > 0)
                                  for t in ("y30", "y60"))
    print("INFORMATION PASS:", res["INFORMATION_PASS"])
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
