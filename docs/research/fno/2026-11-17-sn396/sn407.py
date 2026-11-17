"""SN407 (own): fw9's frozen rule before the auction existed (PLAN.md section 2, frozen at 00693405; details fixed here
before any SN407 number).

Sessions: gl DEV, Apr 1, 2022 - Dec 5, 2025 (no Breeze pre-open rows), non-expiry, with an index gap |gap| >= 0.10%
(09:15 open against the previous close, as SN376 / SN382's GAP sample; known at 09:15:00). The trade is fw9's on the HONEST
clock: the gap's side, 2-ITM then 1-ITM under the cash rule at the label quote, filled at the 09:15 close, 60 minutes,
Rs 3,000 stop, Rs 205 / 400. CHEAP = the HONEST 09:16 jump below fw9's frozen 1.2684; also the causal tercile.
Prior (stated before running): SN377's CHEAP gap-side ATM leg (ORIGINAL clock, 2022 - 2026) made -148 a trade at Rs 205.
Reported: CHEAP and OTHER per cheap / other session (skips 0) and over all sessions with a reading; without the best
day; by year; fills. Supports fw9 if CHEAP > 0 at Rs 205 and Rs 400, > 0 without the best day, >= 3 of 4 years positive
(2022 - 2025) and CHEAP > OTHER.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import op  # noqa: E402

gl = op.gl
OUT = HERE / "results-sn407.json"
HI = "2025-12-06"


def block(rows, pick):
    rs = [r for r in rows if pick(r)]
    out = {"n": len(rs), "fills": sum(r["state"] == "FILLED" for r in rs)}
    for st in (205, 400):
        xs = [r[f"net{st}"] for r in rs]
        out[f"per_session@{st}"] = op.per_session(xs)
        out[f"without_best@{st}"] = op.without_best(xs)
        out[f"by_year@{st}"] = {y: op.per_session([r[f"net{st}"] for r in rs if r["day"][:4] == y]) for y in ("2022", "2023", "2024", "2025")}
        out[f"years_positive@{st}"] = sum(1 for v in out[f"by_year@{st}"].values() if v is not None and v > 0)
    return out


def main():
    if OUT.exists():
        raise SystemExit("SN407 is run once")
    smp, days, _au = op.setup()
    jm = op.jumps(smp, "HONEST")
    fixed, moving = op.labels(jm, True), op.labels(jm, False)
    rows = []
    for d in days:
        if d >= HI or d not in jm:
            continue
        s, pb = smp.s[d], smp.prev_bar(d)
        o = s["index"][0][0]
        if pb is None or np.isnan(o):
            continue
        g = float(o) / float(pb[3]) - 1.0
        if abs(g) < 0.001:
            continue
        side = "CE" if g > 0 else "PE"
        r = {"day": d, "g": g, "jump": jm[d], "cheap": fixed[d] == "CHEAP", "cheap_moving": moving.get(d) == "CHEAP", "has_moving": d in moving}
        for st in (205.0, 400.0):
            pos, dep, state, jf = op.leg(smp, s, side, 1, "HONEST", st)
            r["state"] = state
            net = gl.walk(pos, s, jf, jf + 60, room=op.STOP)[0] if pos is not None else None
            r[f"net{int(st)}"] = net if (state == "FILLED" and net is not None) else 0.0
        rows.append(r)
    res = {"sessions_with_reading": len(rows), "cheap_fixed": sum(r["cheap"] for r in rows), "prior_SN377_cheap_ATM_gap@205": -147.8}
    res["CHEAP fixed"] = block(rows, lambda r: r["cheap"])
    res["OTHER fixed"] = block(rows, lambda r: not r["cheap"])
    res["CHEAP moving"] = block(rows, lambda r: r["has_moving"] and r["cheap_moving"])
    res["OTHER moving"] = block(rows, lambda r: r["has_moving"] and not r["cheap_moving"])
    res["ALL"] = block(rows, lambda r: True)
    for st in (205, 400):
        res[f"fw9 rule per session over all readings@{st}"] = op.per_session([r[f"net{st}"] if r["cheap"] else 0.0 for r in rows])
    c, o = res["CHEAP fixed"], res["OTHER fixed"]
    res["supports_fw9"] = bool(c["per_session@205"] > 0 and c["per_session@400"] > 0 and (c["without_best@205"] or -1) > 0
                               and c["years_positive@205"] >= 3 and c["per_session@205"] > o["per_session@205"])
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
