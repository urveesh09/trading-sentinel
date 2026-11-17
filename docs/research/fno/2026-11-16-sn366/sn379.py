"""SN379: signed option flow before the future moves (PLAN.md section 2, frozen at 3740b461; chain features from chainlib,
measures and controls from sn368, fixed here before any SN379 number.)

Real-quote archive Sep 10 - Nov 13, 2026, non-expiry days. flow(i) = the minute's volume increments of the front
expiry's CE and PE at K0 - 100 .. K0 + 100, signed by the snapshot's last price against the previous snapshot's mid
(Lee-Ready), call-buys minus put-buys, in lots (chainlib). F10(i) = flow summed over i-9 .. i.
Calibration from EARLIER sessions only (>= 5 sessions): s = the std of F10 over all their minutes.
Event: |F10| >= 1.5 s, the future moved < 0.05% over i-10 .. i, >= 30 minutes after the day's previous event.
Prediction: net call-buying (F10 > 0) -> the future rises.
Measured and controls exactly as sn368. Close as sn368's rule. Diagnostic: the share of minutes whose flow is 0 (unsigned
or no volume), reported.
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
OUT = HERE / "results-sn379.json"


def f10(feat, i):
    xs = [feat["rows"].get(j, {}).get("flow") for j in range(i - 9, i + 1)]
    return None if any(x is None for x in xs) else float(sum(xs))


def main():
    if OUT.exists():
        raise SystemExit("SN379 is run once")
    feats = {d: f for d in S.days_list() if (f := CL.day_features(d))["front"] is not None and not f.get("expiry_day")}
    days = sorted(feats)
    vals = {d: [(i, x) for i in range(CL.I0, CL.I1 + 1) if (x := f10(feats[d], i)) is not None] for d in days}
    zero = [feats[d]["rows"][i].get("flow") == 0 for d in days for i in range(CL.I0, CL.I1 + 1) if i in feats[d]["rows"] and "flow" in feats[d]["rows"][i]]
    ev, evq = [], []
    for k, d in enumerate(days):
        prior = [x for dd in days[:k] for _i, x in vals[dd]]
        if k < 5 or len(prior) < 200:
            continue
        s = float(np.std(prior))
        f = feats[d]
        last = -999
        for i, x in vals[d]:
            f0, f1 = S.fut(f, i - 10), S.fut(f, i)
            if f0 is None or f1 is None or abs(f1 / f0 - 1.0) >= S.QUIET:
                continue
            if s > 0 and abs(x) >= 1.5 * s and i - last >= 30:
                last = i
                sgn = 1 if x > 0 else -1
                ev.append({"day": d, "i": i, "F10": round(x, 1), "dir": sgn, "f15": S.follow(f, i, sgn, 15), "f30": S.follow(f, i, sgn, 30),
                           "opt": S.trade(d, f, i, sgn)})
            if i % 30 == 0:
                sgn = random.Random(f"sn379-{d}-{i}").choice((-1, 1))
                evq.append({"day": d, "i": i, "dir": sgn, "f15": S.follow(f, i, sgn, 15), "f30": S.follow(f, i, sgn, 30), "opt": S.trade(d, f, i, sgn)})
    res = {"days": len(days), "flow_zero_share": round(float(np.mean(zero)), 3) if zero else None, "FLOW": S.summarize(ev), "QUIET_COIN": S.summarize(evq)}
    r = res["FLOW"]
    res["close"] = bool(r["events"] < 30 or (r["follow_30m_bp"]["mean"] or 0) < 1.0 or (r["option_30m@0"]["per_trade"] or -1) < 0)
    res["events"] = ev
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "events"}, indent=1))


if __name__ == "__main__":
    main()
