"""SN473 (own): where the participant-positioning information goes, and the popular "FII long ratio" rule (PLAN.md section 3,
frozen at 83e1b444; details fixed here before any number). A mechanism check, not a trade.

z_t = SN456's primary feature (feat456). Correlations of z_t with, on every futures session that has both:
  gap      previous close -> today's open (the first price after the report is published)
  open10   today's open -> 10:00 (F44)
  y        10:00 -> 11:00 (SN456's target)
  late     11:00 -> 15:15 (F104 -> F359)
90% CI: 2,000 circular block-bootstrap resamples (block 20, seed 473) of the paired series.
The popular rule: L = FII Future Index Long / (Long + Short) in report t-1 (ON_TIME or ASSUMED); its percentile among every
earlier valid report, once >= 250 exist; LONG when <= 10%, SHORT when >= 90%. Outcomes: today's open -> close (near contract)
and the 5-session open -> close (today's open-to-close plus the next four sessions' close-to-close on each day's near
contract). Hit (sign agrees) and the mean signed return (bp) with a 90% block CI over signal days (block 5, seed 4731).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import feat456 as F  # noqa: E402

OUT = HERE / "results-sn473.json"


def cbb(n, rng, B=2000, block=20):
    k = int(np.ceil(n / block))
    return ((rng.integers(0, n, (B, k))[:, :, None] + np.arange(block)) % n).reshape(B, -1)[:, :n]


def corr_ci(a, b, seed):
    rng = np.random.default_rng(seed)
    idx = cbb(len(a), rng)
    cs = [np.corrcoef(a[i], b[i])[0, 1] for i in idx]
    return round(float(np.corrcoef(a, b)[0, 1]), 4), [round(float(np.percentile(cs, 5)), 4), round(float(np.percentile(cs, 95)), 4)]


def main():
    if OUT.exists():
        raise SystemExit("SN473 is scored once")
    cal, rows, rep = F.features()
    res = {"correlations_with_z": {}}
    for k in ("gap", "openret", "y", "late"):
        ds = [d for d in cal if rows[d].get("z") is not None and rows[d].get(k) is not None]
        a = np.array([rows[d]["z"] for d in ds])
        b = np.array([rows[d][k] for d in ds])
        r, ci = corr_ci(a, b, 473)
        res["correlations_with_z"][k] = {"dates": len(ds), "corr": r, "ci90": ci,
                                         "mean_bp_when_z_gt_1": round(float(b[a > 1].mean()), 2), "mean_bp_when_z_lt_-1": round(float(b[a < -1].mean()), 2)}
    # the popular rule
    valid = sorted(d for d, r in rep.items() if r["valid"])
    hist, pct = [], {}
    for d in valid:
        L = rep[d]["long_ratio"]
        if len(hist) >= 250:
            pct[d] = float(np.mean(np.array(hist) < L))
        hist.append(L)
    exch = sorted(set(cal) | set(valid))
    pos = {d: i for i, d in enumerate(exch)}
    ci_cal = {d: i for i, d in enumerate(cal)}
    sig = []
    for d in cal:
        r = rows[d]
        k = pos[d]
        p1 = exch[k - 1] if k >= 1 else None
        if p1 not in pct or r["avail"] not in ("ON_TIME", "ASSUMED") or r.get("day_oc") is None:
            continue
        side = 1 if pct[p1] <= 0.10 else (-1 if pct[p1] >= 0.90 else 0)
        if side == 0:
            continue
        t = ci_cal[d]
        five = r["day_oc"]
        ok = True
        for j in range(1, 5):
            if t + j >= len(cal):
                ok = False
                break
            five_j = None
            sess = SESS[cal[t + j]]
            if sess["close"] and sess["prev_close"]:
                five_j = 1e4 * np.log(sess["close"] / sess["prev_close"])
            if five_j is None:
                ok = False
                break
            five += five_j
        sig.append({"day": d, "side": side, "pct": pct[p1], "oc": r["day_oc"], "five": five if ok else None})
    out = {}
    for name, sd in (("LONG", 1), ("SHORT", -1), ("BOTH", 0)):
        xs = [s for s in sig if sd == 0 or s["side"] == sd]
        blk = {}
        for h in ("oc", "five"):
            v = np.array([s["side"] * s[h] for s in xs if s[h] is not None])
            if len(v) < 5:
                blk[h] = {"n": len(v)}
                continue
            rng = np.random.default_rng(4731)
            idx = cbb(len(v), rng, block=5)
            bm = v[idx].mean(1)
            blk[h] = {"n": len(v), "hit": round(float(np.mean(v > 0)), 4), "mean_signed_bp": round(float(v.mean()), 2),
                      "ci90": [round(float(np.percentile(bm, 5)), 2), round(float(np.percentile(bm, 95)), 2)]}
        out[name] = blk
    res["fii_long_ratio_rule"] = out
    res["signal_days"] = len(sig)
    res["signal_years"] = {y: sum(s["day"][:4] == y for s in sig) for y in sorted({s["day"][:4] for s in sig})}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


SESS = None
if __name__ == "__main__":
    SESS = F.futures()[1]
    main()
