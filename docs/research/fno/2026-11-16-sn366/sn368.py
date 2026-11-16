"""SN368: do the option wings move before the future? (PLAN.md section 1, frozen at 3740b461; details fixed here before
any SN368 number.) Real-quote archive (Sep 10 - Nov 13, 2026, seen; non-expiry days), chain features from chainlib.

Per minute i (09:30 .. 14:30): dRR_t = rr_t(i) - rr_t(i-10) for t = front, next; dA_t = atm_iv_t(i) - atm_iv_t(i-10);
r10 = fut(i) / fut(i-10) - 1.
Calibration from EARLIER sessions only (>= 5): per tenor, OLS dRR_t ~ 1 + dA_t + r10 over all earlier minutes; residual
e_t; s_t = the std of earlier residuals.
Event: e_front and e_next the same sign, |e_t| >= 1.5 s_t for both, |r10| < 0.05%, and >= 30 minutes after the day's
previous event. Prediction: e > 0 (puts richer than calls) -> the future falls.
Measured: the future's mid return over i -> i+15 and i -> i+30 in the predicted direction (basis points); the front ATM
option on that side bought at minute i+1's walked ask, held 15 / 30 minutes, Rs 3,000 stop, stress 0 / 205 / 400.
Controls: ATM-only events (OLS dA_front ~ 1 + r10 on earlier sessions, |residual| >= 1.5 std, quiet future, predicted
fall when the ATM IV rose) and QUIET = every 30th quiet minute with a seeded coin-flip direction.
Close if: fewer than 30 events, or the 30-minute follow-through < 1 bp, or the option is negative at zero stress.
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import chainlib as CL  # noqa: E402

qa = CL.qa
OUT = HERE / "results-sn368.json"
QUIET = 0.0005


def days_list():
    return [d for d in qa.days() if d <= "2026-11-13"]


def get(feat, i, tenor, key):
    r = feat["rows"].get(i)
    if r is None or r.get(tenor) is None:
        return None
    v = r[tenor][key]
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else v


def fut(feat, i):
    r = feat["rows"].get(i)
    return None if r is None else r["fut"]


def raw(feat, i):
    f0, f1 = fut(feat, i - 10), fut(feat, i)
    if f0 is None or f1 is None:
        return None
    out = {"r10": f1 / f0 - 1.0}
    for t in ("front", "next"):
        a0, a1 = get(feat, i - 10, t, "rr"), get(feat, i, t, "rr")
        b0, b1 = get(feat, i - 10, t, "atm_iv"), get(feat, i, t, "atm_iv")
        if None in (a0, a1, b0, b1):
            return None
        out[f"dRR_{t}"], out[f"dA_{t}"] = a1 - a0, b1 - b0
    return out


def ols(X, y):
    X, y = np.asarray(X, float), np.asarray(y, float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ beta
    return beta, float(np.std(res, ddof=X.shape[1]))


def follow(feat, i, sgn, h):
    f0, f1 = fut(feat, i), fut(feat, i + h)
    return None if f0 is None or f1 is None else 1e4 * (f1 / f0 - 1.0) * sgn


def trade(day, feat, i, sgn):
    q = qa.load(day)
    k = get(feat, i, "front", "K0")
    if k is None:
        return None
    side = "CE" if sgn > 0 else "PE"
    return {f"{h}m@{st}": CL.option_trade(q, feat["front"], k, side, i + 1, h, float(st)) for h in (15, 30) for st in (0, 205, 400)}


def summarize(evs):
    out = {"events": len(evs)}
    for h in (15, 30):
        xs = [e[f"f{h}"] for e in evs if e.get(f"f{h}") is not None]
        out[f"follow_{h}m_bp"] = {"n": len(xs), "mean": round(float(np.mean(xs)), 2) if xs else None,
                                  "se": round(float(np.std(xs, ddof=1) / math.sqrt(len(xs))), 2) if len(xs) > 1 else None,
                                  "hit": round(float(np.mean([x > 0 for x in xs])), 3) if xs else None}
    for k in ("15m@0", "15m@205", "15m@400", "30m@0", "30m@205", "30m@400"):
        xs = [e["opt"][k] for e in evs if e.get("opt") and e["opt"].get(k) is not None]
        out[f"option_{k}"] = {"n": len(xs), "per_trade": round(float(np.mean(xs)), 1) if xs else None}
    return out


def main():
    if OUT.exists():
        raise SystemExit("SN368 is run once")
    days = [d for d in days_list()]
    feats = {}
    for d in days:
        f = CL.day_features(d)
        if f["front"] is not None and not f.get("expiry_day"):
            feats[d] = f
    days = sorted(feats)
    samples = {}                                     # day -> list of (i, raw)
    for d in days:
        samples[d] = [(i, x) for i in range(CL.I0, CL.I1 + 1) if (x := raw(feats[d], i)) is not None]
    coverage = {"days": len(days), "minutes_with_both_wings": sum(len(v) for v in samples.values()),
                "minutes_possible": len(days) * (CL.I1 - CL.I0 + 1)}
    ev_rr, ev_atm, ev_q = [], [], []
    for k, d in enumerate(days):
        prior = [x for dd in days[:k] for _i, x in samples[dd]]
        if k < 5 or len(prior) < 200:
            continue
        cal = {}
        for t in ("front", "next"):
            X = [[1.0, x[f"dA_{t}"], x["r10"]] for x in prior]
            y = [x[f"dRR_{t}"] for x in prior]
            cal[t] = ols(X, y)
        ba, sa = ols([[1.0, x["r10"]] for x in prior], [x["dA_front"] for x in prior])
        last_rr = last_atm = -999
        for i, x in samples[d]:
            if abs(x["r10"]) >= QUIET:
                continue
            e = {t: x[f"dRR_{t}"] - float(np.dot([1.0, x[f"dA_{t}"], x["r10"]], cal[t][0])) for t in ("front", "next")}
            if (np.sign(e["front"]) == np.sign(e["next"]) != 0 and all(abs(e[t]) >= 1.5 * cal[t][1] for t in e) and i - last_rr >= 30):
                last_rr = i
                sgn = -1 if e["front"] > 0 else 1
                ev_rr.append({"day": d, "i": i, "dir": sgn, "f15": follow(feats[d], i, sgn, 15), "f30": follow(feats[d], i, sgn, 30), "opt": trade(d, feats[d], i, sgn)})
            ra = x["dA_front"] - float(np.dot([1.0, x["r10"]], ba))
            if abs(ra) >= 1.5 * sa and i - last_atm >= 30:
                last_atm = i
                sgn = -1 if ra > 0 else 1
                ev_atm.append({"day": d, "i": i, "dir": sgn, "f15": follow(feats[d], i, sgn, 15), "f30": follow(feats[d], i, sgn, 30), "opt": trade(d, feats[d], i, sgn)})
        quiet = [i for i, x in samples[d] if abs(x["r10"]) < QUIET][::30]
        for i in quiet:
            sgn = random.Random(f"sn368-{d}-{i}").choice((-1, 1))
            ev_q.append({"day": d, "i": i, "dir": sgn, "f15": follow(feats[d], i, sgn, 15), "f30": follow(feats[d], i, sgn, 30), "opt": trade(d, feats[d], i, sgn)})
    res = {"coverage": coverage, "RR": summarize(ev_rr), "ATM_ONLY": summarize(ev_atm), "QUIET_COIN": summarize(ev_q),
           "abs_move_30m_bp_quiet": round(float(np.mean([abs(e["f30"]) for e in ev_q if e["f30"] is not None])), 2) if ev_q else None}
    r = res["RR"]
    res["close"] = bool(r["events"] < 30 or (r["follow_30m_bp"]["mean"] or 0) < 1.0 or (r["option_30m@0"]["per_trade"] or -1) < 0)
    res["events_rr"] = ev_rr
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "events_rr"}, indent=1))


if __name__ == "__main__":
    main()
