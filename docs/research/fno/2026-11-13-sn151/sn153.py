"""SN153 - the expiry-day hot straddle (PLAN.md; development evidence). SN10's 56 NIFTY expiry days (10-second
opening-ATM legs, minute index / future from the sealed datasets). R_today at 10:00 = sigma of 1-minute index returns
since 09:20 / the opening-ATM straddle's implied sigma over the minutes left today (0 days to expiry). Hot = causal
quantile over earlier expiry days (>= 10). Buy both legs at 10:00, exit 12:00 or 13:00, Rs 3k stop on the combined
mark. Choose on the first 28 days, score the last 28 once."""
from __future__ import annotations

import itertools
import json
import math
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ph  # noqa: E402

M = ph.M
EXP = ph.C.FNO / "2026-11-12-sn10" / "_local" / "expiry10.pkl"
EXITS = {"12:00": 165 * 6 - 1, "13:00": 225 * 6 - 1}
QS = (0.20, 0.33)


def ffill(a):
    out, last = a.copy(), np.nan
    for k in range(len(out)):
        if np.isnan(out[k]):
            out[k] = last
        else:
            last = out[k]
    return out


def last_print(col, k, back):
    for j in range(k, max(-1, k - back - 1), -1):
        if not np.isnan(col[j]):
            return float(col[j])
    return None


def day_feature(rec):
    c = ffill(rec["s"]["index"][3].astype(np.float64))
    fc = ffill(rec["s"]["future"][3].astype(np.float64))
    r = np.diff(np.log(c[5:46]))
    ce, pe = last_print(rec["legs"]["CE"][3], 269, 3), last_print(rec["legs"]["PE"][3], 269, 3)
    if ce is None or pe is None or np.isnan(fc[45]) or len(r) < 10:
        return None
    return float(np.std(r)) / ((ce + pe) / (0.7979 * fc[45] * math.sqrt(375 - 46)))


def trade(rec, end_k, stress=205.0, late=0, room=3000.0):
    k0 = 269 + 6 * late
    legs = {}
    for o in ("CE", "PE"):
        px = last_print(rec["legs"][o][3], k0, 3)
        if px is None:
            return None
        legs[o] = M.ask_of(px)
    if sum(legs.values()) * M.LOT > 15000:
        return None
    last = None
    for k in range(k0 + 1, end_k + 1):
        bids = {}
        for o in legs:
            px = last_print(rec["legs"][o][3], k, 6)
            if px is None:
                break
            bids[o] = M.bid_of(px)
        if len(bids) < 2:
            continue
        v = sum((bids[o] - legs[o]) * M.LOT - M.charges(legs[o], bids[o], M.LOT) for o in legs) - 2 * stress
        last = v
        if v <= -room:
            return v
    return last if last is not None else -2 * stress


if __name__ == "__main__":
    out_path = HERE / "results-sn153.json"
    if out_path.exists():
        raise SystemExit("SN153 is scored once")
    days = pickle.loads(EXP.read_bytes())
    ds = sorted(days)
    feats, flag, hist = {}, {}, []
    for d in ds:
        x = day_feature(days[d])
        feats[d] = x
        flag[d] = {q: (x is not None and len(hist) >= 10 and x >= float(np.quantile(hist, 1 - q))) for q in QS}
        if x is not None:
            hist.append(x)
    choose, score = ds[:28], ds[28:]
    variants = {f"top{int(q * 100)} exit {e}": (q, k) for q, (e, k) in itertools.product(QS, EXITS.items())}
    res = {"days": len(ds), "choose": [choose[0], choose[-1]], "score": [score[0], score[-1]], "variants": {}}
    for name, (q, k) in variants.items():
        part = {}
        for half, dd in (("choose", choose), ("score", score)):
            xs = [trade(days[d], k) for d in dd if flag[d][q]]
            xs = [x for x in xs if x is not None]
            part[half] = {"trades": len(xs), "net": round(sum(xs)), "won": sum(x > 0 for x in xs)}
        res["variants"][name] = part
        print(f"   {name:20s} choose {part['choose']} score {part['score']}", flush=True)
    pick = max(variants, key=lambda n: res["variants"][n]["choose"]["net"])
    q, k = variants[pick]
    sc = res["variants"][pick]["score"]
    pool = [x for x in (trade(days[d], k) for d in score) if x is not None]
    rng = np.random.default_rng(153)
    draws = [float(np.sum(rng.choice(pool, min(sc["trades"], len(pool)), replace=False))) for _ in range(2000)] if sc["trades"] else [0.0]
    s400 = sum(x for x in (trade(days[d], k, stress=400.0) for d in score if flag[d][q]) if x is not None)
    late = sum(x for x in (trade(days[d], k, late=1) for d in score if flag[d][q]) if x is not None)
    res["pick"] = pick
    res["verdict"] = {"score_net": sc["net"], "trades": sc["trades"], "random_95th": round(float(np.percentile(draws, 95))),
                      "stress_400_per_leg": round(s400), "late_1min": round(late),
                      "PASS_development": bool(sc["net"] > 0 and sc["net"] > np.percentile(draws, 95) and s400 > 0 and late > 0)}
    print("SN153 pick", pick, "VERDICT", res["verdict"], flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
