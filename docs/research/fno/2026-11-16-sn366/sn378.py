"""SN378: does the option pair lead the future? (PLAN.md section 2, frozen at 3740b461; chain features from chainlib,
measures and controls from sn368, fixed here before any SN378 number.)

Real-quote archive Sep 10 - Nov 13, 2026, non-expiry days. b(i) = the front ATM pair's synthetic forward - the front
future's mid (the weekly-vs-monthly carry is in b's level; only its change is used). z(i) = (b(i) - mean of b over
i-30 .. i-1) / std of b over i-30 .. i-1 (>= 20 of those minutes present).
Event: |z| >= 2, the future moved < 0.05% over i-10 .. i, >= 30 minutes after the day's previous event.
Prediction: the future moves toward the synthetic (z > 0 -> up).
Measured and controls exactly as sn368 (15 / 30-minute follow-through in basis points; the front ATM option on the
predicted side at minute i+1's walked ask; QUIET coin flips). Close as sn368's rule.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn368 as S  # noqa: E402

CL, qa = S.CL, S.qa
OUT = HERE / "results-sn378.json"


def b_of(feat, i):
    r = feat["rows"].get(i)
    if r is None or r.get("front") is None:
        return None
    return r["front"]["syn"] - r["fut"]


def main():
    if OUT.exists():
        raise SystemExit("SN378 is run once")
    feats = {d: f for d in S.days_list() if (f := CL.day_features(d))["front"] is not None and not f.get("expiry_day")}
    ev, evq = [], []
    for d in sorted(feats):
        f = feats[d]
        last = -999
        for i in range(CL.I0, CL.I1 + 1):
            f0, f1, b = S.fut(f, i - 10), S.fut(f, i), b_of(f, i)
            if None in (f0, f1, b) or abs(f1 / f0 - 1.0) >= S.QUIET:
                continue
            win = [x for j in range(i - 30, i) if (x := b_of(f, j)) is not None]
            if len(win) < 20 or np.std(win) <= 0:
                continue
            z = (b - np.mean(win)) / np.std(win)
            if abs(z) >= 2.0 and i - last >= 30:
                last = i
                sgn = 1 if z > 0 else -1
                ev.append({"day": d, "i": i, "z": round(float(z), 2), "dir": sgn, "f15": S.follow(f, i, sgn, 15), "f30": S.follow(f, i, sgn, 30),
                           "opt": S.trade(d, f, i, sgn)})
            if i % 30 == 0:
                sgn = random.Random(f"sn378-{d}-{i}").choice((-1, 1))
                evq.append({"day": d, "i": i, "dir": sgn, "f15": S.follow(f, i, sgn, 15), "f30": S.follow(f, i, sgn, 30), "opt": S.trade(d, f, i, sgn)})
    res = {"days": len(feats), "SYN_LEAD": S.summarize(ev), "QUIET_COIN": S.summarize(evq)}
    r = res["SYN_LEAD"]
    res["close"] = bool(r["events"] < 30 or (r["follow_30m_bp"]["mean"] or 0) < 1.0 or (r["option_30m@0"]["per_trade"] or -1) < 0)
    res["events"] = ev
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "events"}, indent=1))


if __name__ == "__main__":
    main()
