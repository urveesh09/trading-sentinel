"""SN286 - the corrected holiday replay (PLAN.md; a diagnosis on seen data). Pre-holiday session = a Monday-Friday regular
session with index prints through 15:10, and at least one Monday-Friday market holiday between it and the next trading
day (derived from the calendar, printed, checked against the engine's 2026 NSE list). ITM call (one strike) at 09:20,
exit at 15:10 with an executable 15:10 price (else "unresolved", excluded from the net); Rs 3,000 stop; ATM reference.
Old (SN259) vs corrected admissions; matched ordinary-session control (same sample, weekday, sessions to expiry); without
the best day; the corrected call in Gold's one wallet (ow.py)."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SN251 = HERE.parent / "2026-11-16-sn251"
sys.path.insert(0, str(SN251))
sys.path.insert(0, str(HERE.parent.parent.parent.parent / "python-engine"))
import gl  # noqa: E402
import sn259  # noqa: E402

I920 = gl.I["09:20"]
ENGINE_2026 = {"2026-01-15", "2026-01-26", "2026-03-03", "2026-03-26", "2026-03-31", "2026-04-03", "2026-04-14", "2026-05-01",
               "2026-05-28", "2026-06-26", "2026-09-14", "2026-10-02", "2026-10-20", "2026-11-10", "2026-11-24", "2026-12-25"}


def full_session(s):
    tr = s.get("index_traded")
    if tr is None:
        return False
    ok = np.flatnonzero(tr)
    return len(ok) > 0 and int(ok[-1]) >= gl.FLAT


def holidays_between(smp, d):
    nd = smp.next_day(d)
    if nd is None:
        return []
    a, b = dt.date.fromisoformat(d), dt.date.fromisoformat(nd)
    out, x = [], a + dt.timedelta(days=1)
    while x < b:
        if x.weekday() < 5:
            out.append(x.isoformat())
        x += dt.timedelta(days=1)
    return out


def pre_holiday(smp, d):
    return dt.date.fromisoformat(d).weekday() < 5 and full_session(smp.s[d]) and bool(holidays_between(smp, d))


def call(smp, d, off=1, stress=gl.STRESS):
    s = smp.s[d]
    K = gl.atm(smp, s, I920) - off * smp.mk["step"]
    p = gl.Pos(smp, s, [(K, "CE", 1)], I920, 1, stress)
    if not p.ok:
        return None
    net, j, why = gl.walk(p, s, I920, gl.FLAT, room=3000.0)
    if net is None:
        return {"day": d, "exit_day": d, "net": None, "why": "unresolved"}
    if why == "time" and (j != gl.FLAT or gl.opx(s, K, "CE", gl.FLAT) is None):
        return {"day": d, "exit_day": d, "net": None, "why": "unresolved", "last_minute": j}
    return {"day": d, "exit_day": d, "net": net, "why": why}


def ledger(smp, days, off=1):
    tr = [call(smp, d, off) for d in days]
    return [t for t in tr if t is not None]


if __name__ == "__main__":
    out = HERE / "results-sn286.json"
    if out.exists():
        raise SystemExit("SN286 is run once")
    for n in ("EXAMN", "EXAMS"):
        gl.SEALED[n] = True
    res = {"samples": {}, "derived_weekday_holidays": {}}
    for n in ("DEV", "TEST", "EXAMN", "EXAMS"):
        smp = gl.sample(n)
        old = [d for d in smp.days if sn259.pre_holiday(smp, d)]
        new = [d for d in smp.days if pre_holiday(smp, d)]
        hol = sorted({h for d in new for h in holidays_between(smp, d)})
        res["derived_weekday_holidays"][n] = hol
        rows = {}
        for tag, off in (("ITM", 1), ("ATM", 0)):
            tr = ledger(smp, new, off)
            ok = [t for t in tr if t["net"] is not None]
            nets = sorted([t["net"] for t in ok], reverse=True)
            # matched control: same weekday and sessions-to-expiry, ordinary sessions
            ctl, nm = 0.0, []
            for t in ok:
                d = t["day"]
                wd, k = dt.date.fromisoformat(d).weekday(), smp.sessions_until(d, smp.s[d]["expiry"])
                m = [x for x in smp.days if x not in set(new) and dt.date.fromisoformat(x).weekday() == wd
                     and smp.sessions_until(x, smp.s[x]["expiry"]) == k]
                vals = [r["net"] for r in (call(smp, x, off) for x in m) if r and r["net"] is not None]
                nm.append(len(vals))
                ctl += float(np.mean(vals)) if vals else 0.0
            rows[tag] = {"trades": len(ok), "unresolved": [t["day"] for t in tr if t["net"] is None], "net": round(sum(nets)),
                         "wins": sum(x > 0 for x in nets), "best": round(nets[0]) if nets else 0,
                         "without_best": round(sum(nets[1:])), "without_best3": round(sum(nets[3:])),
                         "matched_control": round(ctl), "matched_sessions_median": int(np.median(nm)) if nm else 0,
                         "by_day": {t["day"]: round(t["net"]) for t in ok}}
        res["samples"][n] = {"old_admitted": len(old), "corrected_admitted": len(new), "dropped": sorted(set(old) - set(new)),
                             "added": sorted(set(new) - set(old)), **rows}
        print("SN286", n, json.dumps({k: (v if k not in ("ITM", "ATM") else {kk: vv for kk, vv in v.items() if kk != "by_day"})
                                      for k, v in res["samples"][n].items()}), flush=True)
        print("SN286", n, "derived weekday holidays", hol, flush=True)
    d26 = [h for h in res["derived_weekday_holidays"]["DEV"] + res["derived_weekday_holidays"]["TEST"] if h.startswith("2026")]
    res["check_2026"] = {"derived_not_in_engine_list": sorted(set(d26) - ENGINE_2026)}
    print("SN286 2026 check", res["check_2026"], flush=True)
    # the corrected call inside Gold's one wallet
    import ow  # noqa: E402

    class Corrected:
        def intraday(self, smp, d, i_from, budget, room, stop_at):
            if d not in smp.s or not pre_holiday(smp, d) or i_from > I920 or (stop_at is not None and stop_at <= I920):
                return None
            s = smp.s[d]
            K = gl.atm(smp, s, I920) - smp.mk["step"]
            p = gl.Pos(smp, s, [(K, "CE", 1)], I920)
            if not p.ok or p.premium > budget:
                return None
            end = gl.FLAT if stop_at is None else min(gl.FLAT, stop_at)
            net, j, why = gl.walk(p, s, I920, end, room=room)
            if net is None:
                return None
            if stop_at is not None and j >= stop_at and why == "time":
                why = "forced"
            return net, j, why

    _r0, d0, _ = ow.run_wallet(ow.C.V5, ow.GOLD_30K, None)
    _r1, d1, l1 = ow.run_wallet(ow.C.V5, ow.GOLD_30K, Corrected())

    def acct(days):
        x = {d: n for d, _w, n, _t, _l in days}
        mo = {}
        for d, v in x.items():
            mo[d[:7]] = mo.get(d[:7], 0.0) + v
        mv = np.array(list(mo.values()))
        return {"net": round(sum(x.values())), "months_positive": int((mv > 0).sum()), "worst_month": round(float(mv.min())),
                "worst_day": round(min(x.values()))}
    legs = sorted([t["net"] for t in l1], reverse=True)
    res["one_wallet"] = {"gold_alone": acct(d0), "gold_plus_corrected_call": acct(d1), "leg_trades": len(l1), "leg_net": round(sum(legs)),
                         "leg_without_best": round(sum(legs[1:])), "leg_best": round(legs[0]) if legs else 0}
    print("SN286 one wallet", json.dumps(res["one_wallet"]), flush=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
