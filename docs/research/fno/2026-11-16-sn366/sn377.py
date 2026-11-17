"""SN377: is the opening premium always rich? (PLAN.md section 2, frozen at 3740b461; details below fixed before any
SN377 number.)

gl DEV + TEST NIFTY sessions Apr 2022 - Oct 28, 2026, non-expiry. For each session d with the same front-weekly expiry as
the previous session (else skipped and counted; a different expiry would mix term structure):
  IV_open = Black-76 IV of the ATM straddle at 09:16 (synthetic forward, sn361's functions, ATM at 09:16);
  IV_prev = the same on the previous session at 15:00 (its own ATM at 15:00, the same expiry);
  jump = IV_open - IV_prev (vol points).
Terciles of jump from EARLIER sessions only (expanding window, >= 60 earlier values): CHEAP (below the lower tercile),
MID, RICH (above the upper).
Measured per tercile:
  R = the 09:16 ATM straddle's residual by 10:15 (sn361's measure, rupees per lot) and the 11:00 control's residual;
  the gap side's single ATM leg at 09:16 (GAP sample: |index gap| >= 0.10%), 60-minute net at stress 0 / 205 / 400,
  Rs 3,000 stop; and a seeded coin-flip leg at the same clock.
Advance (forward freeze only): CHEAP's gap-leg 60-minute net at Rs 205 > 0 with >= 100 trades, >= 3 of 5 years positive,
and above its coin flip.
"""
from __future__ import annotations

import bisect
import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn371 as S  # noqa: E402

gl, sn361 = S.gl, S.sn361
OUT = HERE / "results-sn377.json"


def straddle_iv(smp, s, i, k=None):
    k = gl.atm(smp, s, i) if k is None else k
    c, p = gl.opx(s, k, "CE", i, look=1), gl.opx(s, k, "PE", i, look=1)
    if c is None or p is None:
        return None
    hh = f"{(555 + i) // 60:02d}:{(555 + i) % 60:02d}"
    F = k + c - p
    return None if F <= 0 else sn361.iv(c + p, F, k, sn361.years_to(s["day"], s["expiry"], hh))


def residual(smp, s, t0, t1):
    k = gl.atm(smp, s, S.I16 if t0 == "09:16" else 105)

    def mids(hh, k=k):
        i = sn361.minute(hh)
        c, p = gl.opx(s, k, "CE", i, look=1), gl.opx(s, k, "PE", i, look=1)
        return None if c is None or p is None else (c, p)
    m = sn361.measure(s["day"], s["expiry"], k, mids, t0, t1)
    return None if m is None else m["R"]


def leg(smp, s, side, stress):
    k = gl.atm(smp, s, S.I16)
    pos = gl.Pos(smp, s, [(k, side, +1)], S.I16, lots=1, stress=stress)
    if not pos.ok:
        return None
    net, _j, _w = gl.walk(pos, s, S.I16, S.I16 + 60, room=S.STOP)
    return None if net is None else round(net, 2)


def main():
    if OUT.exists():
        raise SystemExit("SN377 is run once")
    raw = gl._cache("devall", gl.build_dev)
    smp = gl.Sample("ALL", raw, gl.DEV_LO, gl.TEST_HI)
    days = smp.days
    rows, skipped, hist = [], {"expiry_day": 0, "expiry_changed": 0, "no_iv": 0}, []
    for a, d in zip(days, days[1:]):
        s, sp = smp.s[d], smp.s[a]
        if s["day"] == s["expiry"]:
            skipped["expiry_day"] += 1
            continue
        if sp["expiry"] != s["expiry"]:
            skipped["expiry_changed"] += 1
            continue
        io, ip = straddle_iv(smp, s, S.I16), straddle_iv(smp, sp, 345)          # 345 = 15:00
        if io is None or ip is None:
            skipped["no_iv"] += 1
            continue
        jump = 100.0 * (io - ip)
        if len(hist) >= 60:
            srt = sorted(hist)
            lo, hi = srt[len(srt) // 3], srt[(2 * len(srt)) // 3]
            terc = "CHEAP" if jump < lo else "RICH" if jump > hi else "MID"
        else:
            terc = None
        hist.append(jump)
        if terc is None:
            continue
        pb = smp.prev_bar(d)
        o = s["index"][0][0]
        g = None if pb is None or np.isnan(o) else float(o) / float(pb[3]) - 1.0
        r = {"day": d, "year": d[:4], "jump": round(jump, 3), "terc": terc, "R_open": residual(smp, s, "09:16", "10:15"),
             "R_ctrl": residual(smp, s, "11:00", "11:59")}
        if g is not None and abs(g) >= 0.001:
            side = "CE" if g > 0 else "PE"
            coin = random.Random(f"sn377-{d}").choice(("CE", "PE"))
            r["GAP"] = {st: leg(smp, s, side, float(st)) for st in (0, 205, 400)}
            r["COIN"] = {st: leg(smp, s, coin, float(st)) for st in (0, 205, 400)}
        rows.append(r)
    res = {"sessions": len(rows), "skipped": skipped}
    for t in ("CHEAP", "MID", "RICH"):
        rs = [r for r in rows if r["terc"] == t]
        ro = [r["R_open"] for r in rs if r["R_open"] is not None]
        rc = [r["R_ctrl"] for r in rs if r["R_ctrl"] is not None]
        g = {"n": len(rs), "jump_mean": round(float(np.mean([r["jump"] for r in rs])), 3),
             "R_open_mean": round(float(np.mean(ro)), 1) if ro else None, "R_ctrl_mean": round(float(np.mean(rc)), 1) if rc else None}
        for arm in ("GAP", "COIN"):
            for st in (0, 205, 400):
                xs = [r[arm][st] for r in rs if r.get(arm) and r[arm][st] is not None]
                g[f"{arm}@{st}"] = {"n": len(xs), "per_trade": round(float(np.mean(xs)), 1) if xs else None}
        yrs = {}
        for r in rs:
            if r.get("GAP") and r["GAP"][205] is not None:
                yrs.setdefault(r["year"], []).append(r["GAP"][205])
        g["GAP@205 by year"] = {y: round(float(np.mean(v)), 1) for y, v in sorted(yrs.items())}
        res[t] = g
    c = res["CHEAP"]
    res["advance"] = bool(c["GAP@205"]["per_trade"] is not None and c["GAP@205"]["per_trade"] > 0 and c["GAP@205"]["n"] >= 100
                          and sum(v > 0 for v in c["GAP@205 by year"].values()) >= 3 and c["GAP@205"]["per_trade"] > (c["COIN@205"]["per_trade"] or -1e9))
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    for t in ("CHEAP", "MID", "RICH"):
        print(t, json.dumps(res[t]), flush=True)
    print("skipped", skipped, "advance", res["advance"])


if __name__ == "__main__":
    main()
