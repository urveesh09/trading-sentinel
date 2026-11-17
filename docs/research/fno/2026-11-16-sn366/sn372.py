"""SN372: expiry-morning pressure, traded in next week's contract (PLAN.md section 1, frozen at 3740b461; details fixed
here before any SN372 number).

Real-quote archive Sep 10 - Nov 13, 2026. On NIFTY expiry days (an option expiry equals the day): b(i) = the EXPIRING ATM
pair's synthetic forward (chainlib.tenor_row on the expiring chain) - the front future's mid; d10(i) = b(i) - b(i-10);
calibration from EARLIER expiry days only (>= 2): s = the std of their d10. Event, i from 09:30 to 12:30: |d10| >= 2 s,
the future moved < 0.05% over i-10 .. i, >= 30 minutes after the day's previous event. Prediction: the future moves toward
the synthetic (d10 > 0 -> up). Trade: next week's ATM option (chainlib.tenor_row K0 on the next expiry) on that side at
minute i+1's walked ask, held 15 / 30 minutes, flat by 13:30 (i <= 255), Rs 3,000 stop, stress 0 / 205 / 400.
Controls: the same mechanism on non-expiry mornings (front expiry pair, its own earlier-day calibration, front ATM
option), and coin flips at every 30th quiet minute of the expiry mornings.
Close if: fewer than 20 expiry-day events, or the 30-minute follow-through < 1 bp.
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
OUT = HERE / "results-sn372.json"
LO_I, HI_I, FLAT_I = 15, 195, 255


def series(day, expiring):
    q = qa.load(day)
    fr = qa.front_fut(q, "NIFTY")
    exps = sorted({k[1] for k in q["opt"] if k[0] == "NIFTY" and k[1] >= day})
    if fr is None or len(exps) < 2:
        return None
    e_sig = exps[0] if expiring else next((e for e in exps if e > day), None)
    later = [e for e in exps if e > e_sig]
    e_trade = later[0] if expiring and later else e_sig
    out = {"day": day, "e_sig": e_sig, "e_trade": e_trade, "b": {}, "fut": {}, "k_trade": {}}
    for i in range(LO_I - 10, FLAT_I + 31):
        f = CL.mid(fr, i)
        if f is None:
            continue
        out["fut"][i] = f
        if i <= HI_I:
            r = CL.tenor_row(q, day, e_sig, i, f)
            if r is not None:
                out["b"][i] = r["syn"] - f
            rt = r if e_trade == e_sig else CL.tenor_row(q, day, e_trade, i, f)
            if rt is not None:
                out["k_trade"][i] = rt["K0"]
    return out


def follow(x, i, sgn, h):
    f0, f1 = x["fut"].get(i), x["fut"].get(i + h)
    return None if f0 is None or f1 is None else 1e4 * (f1 / f0 - 1.0) * sgn


def trade(x, i, sgn):
    q = qa.load(x["day"])
    k = x["k_trade"].get(i)
    if k is None:
        return None
    side = "CE" if sgn > 0 else "PE"
    return {f"{h}m@{st}": CL.option_trade(q, x["e_trade"], k, side, i + 1, min(h, FLAT_I - i - 1), float(st)) for h in (15, 30) for st in (0, 205, 400)}


def scan(xs, tag, coin=False):
    ev, evq, hist = [], [], []
    for x in xs:
        d10 = {i: x["b"][i] - x["b"][i - 10] for i in x["b"] if i - 10 in x["b"] and LO_I <= i <= HI_I}
        if len(hist) >= 2:
            s = float(np.std([v for h in hist for v in h]))
            last = -999
            for i in sorted(d10):
                f0, f1 = x["fut"].get(i - 10), x["fut"].get(i)
                if f0 is None or f1 is None or abs(f1 / f0 - 1.0) >= S.QUIET:
                    continue
                if s > 0 and abs(d10[i]) >= 2.0 * s and i - last >= 30:
                    last = i
                    sgn = 1 if d10[i] > 0 else -1
                    ev.append({"day": x["day"], "i": i, "dir": sgn, "f15": follow(x, i, sgn, 15), "f30": follow(x, i, sgn, 30), "opt": trade(x, i, sgn)})
                if coin and i % 30 == 0:
                    sgn = random.Random(f"sn372-{x['day']}-{i}").choice((-1, 1))
                    evq.append({"day": x["day"], "i": i, "dir": sgn, "f15": follow(x, i, sgn, 15), "f30": follow(x, i, sgn, 30), "opt": trade(x, i, sgn)})
        hist.append(list(d10.values()))
    return ev, evq


def main():
    if OUT.exists():
        raise SystemExit("SN372 is run once")
    days = S.days_list()
    exp_days, other = [], []
    for d in days:
        q = qa.load(d)
        (exp_days if any(k[0] == "NIFTY" and k[1] == d for k in q["opt"]) else other).append(d)
    xe = [x for d in exp_days if (x := series(d, True)) is not None]
    xo = [x for d in other if (x := series(d, False)) is not None]
    ev_e, ev_q = scan(xe, "EXPIRY", coin=True)
    ev_o, _ = scan(xo, "NON_EXPIRY")
    res = {"expiry_days": [x["day"] for x in xe], "EXPIRY": S.summarize(ev_e), "NON_EXPIRY": S.summarize(ev_o), "EXPIRY_COIN": S.summarize(ev_q)}
    r = res["EXPIRY"]
    res["close"] = bool(r["events"] < 20 or (r["follow_30m_bp"]["mean"] or 0) < 1.0)
    res["events"] = ev_e
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "events"}, indent=1))


if __name__ == "__main__":
    main()
