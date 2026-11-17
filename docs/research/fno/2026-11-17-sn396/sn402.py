"""SN402: late price discovery after a verified RBI release (PLAN.md section 1, frozen at 00693405; details fixed here
before any SN402 number).

Event list (RBI MPC decision days, Apr 2022 - Oct 2026), fixed before any price is read: RBI's own pages confirmed Apr 8,
Jun 5, Aug 5 and Oct 7, 2026 (AnnualPolicy.aspx / the resolutions); RBI's published schedules (2023-24, 2024-25,
2025-26) and RBI-sourced reports give the rest; Aug 6, 2025 is the rescheduled date (Aug 4-6). Release time 10:00 IST
(the Governor's statement; press reports, not stated on the RBI pages read), except the May 4, 2022 off-cycle statement
at 14:00 IST (press reports). Events on NIFTY expiry days have no gl session (expiry days flat) and are counted.
Rule (HONEST clock): decision at release + 6 min using bars to release + 5; direction = sign(index close at release + 5
- close at release - 1), |move| >= 0.15%; FILTERED also needs the ATM straddle IV at release + 5 <= its value at release
- 1 (the event premium released). Trade: ITM 2 then 1 under the cash rule, filled at the release + 5 close, held 30 / 60
minutes, Rs 3,000 stop, Rs 205 / 400. UNFILTERED = without the IV condition. ORDINARY = every other non-expiry gl session
at the same clock (10:06) with the same move threshold, same trade (per-trade comparison). Fewer than 20 qualifying events
= INSUFFICIENT. Bank-futures agreement: no intraday BANKNIFTY history on this PC (SN401), so not tested.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import op  # noqa: E402

gl, V = op.gl, op.V
OUT = HERE / "results-sn402.json"
EVENTS = {  # day: release HH:MM IST
    "2022-04-08": "10:00", "2022-05-04": "14:00", "2022-06-08": "10:00", "2022-08-05": "10:00", "2022-09-30": "10:00", "2022-12-07": "10:00",
    "2023-02-08": "10:00", "2023-04-06": "10:00", "2023-06-08": "10:00", "2023-08-10": "10:00", "2023-10-06": "10:00", "2023-12-08": "10:00",
    "2024-02-08": "10:00", "2024-04-05": "10:00", "2024-06-07": "10:00", "2024-08-08": "10:00", "2024-10-09": "10:00", "2024-12-06": "10:00",
    "2025-02-07": "10:00", "2025-04-09": "10:00", "2025-06-06": "10:00", "2025-08-06": "10:00", "2025-10-01": "10:00", "2025-12-05": "10:00",
    "2026-02-06": "10:00", "2026-04-08": "10:00", "2026-06-05": "10:00", "2026-08-05": "10:00", "2026-10-07": "10:00",
}
MOVE = 0.0015


def idx(hhmm):
    return int(hhmm[:2]) * 60 + int(hhmm[3:]) - 555


def one(smp, s, r, filtered):
    c = s["index"][3]
    a, b = c[r - 1], c[r + 5]
    if np.isnan(a) or np.isnan(b) or abs(b / a - 1.0) < MOVE:
        return None, "no_move"
    if filtered:
        i0, i1 = V.straddle_iv(smp, s, r - 1), V.straddle_iv(smp, s, r + 5)
        if i0 is None or i1 is None:
            return None, "no_iv"
        if i1 > i0:
            return None, "iv_not_released"
    side = "CE" if b > a else "PE"
    out = {}
    for st in (205.0, 400.0):
        pos, _dep, state, jf = op.leg(smp, s, side, r + 6, "HONEST", st)
        if pos is None:
            return None, state
        for h in (30, 60):
            net = gl.walk(pos, s, jf, jf + h, room=op.STOP)[0]
            out[f"{h}m@{int(st)}"] = None if net is None else round(net, 2)
    return out, "traded"


def summ(xs):
    keys = ("30m@205", "60m@205", "30m@400", "60m@400")
    return {"trades": len(xs), **{k: op.per_session([x[k] for x in xs if x.get(k) is not None]) for k in keys},
            "winners_60m@205": sum(1 for x in xs if (x.get("60m@205") or 0) > 0)}


def main():
    if OUT.exists():
        raise SystemExit("SN402 is run once")
    smp, days, _au = op.setup()
    ev = {"events": len(EVENTS), "in_gl": 0, "expiry_or_missing": [], "rows": []}
    filt, unf = [], []
    for d, hhmm in EVENTS.items():
        if d not in smp.s or d not in days:
            ev["expiry_or_missing"].append(d)
            continue
        ev["in_gl"] += 1
        s, r = smp.s[d], idx(hhmm)
        f, wf = one(smp, s, r, True)
        u, wu = one(smp, s, r, False)
        ev["rows"].append({"day": d, "filtered": wf, "unfiltered": wu, "f": f, "u": u})
        if f:
            filt.append(f)
        if u:
            unf.append(u)
    ordinary = []
    for d in days:
        if d in EVENTS:
            continue
        x, _w = one(smp, smp.s[d], idx("10:00"), False)
        if x:
            ordinary.append(x)
    res = {**{k: v for k, v in ev.items() if k != "rows"}, "FILTERED": summ(filt), "UNFILTERED": summ(unf), "ORDINARY_same_clock": summ(ordinary),
           "verdict": "INSUFFICIENT" if len(filt) < 20 else "SCORED", "rows": ev["rows"]}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))
    for r in ev["rows"]:
        print(r["day"], r["filtered"], r["unfiltered"], (r["u"] or {}).get("60m@205"))


if __name__ == "__main__":
    main()
