"""SN354 / SN355 / SN356: availability and affordability checks (PLAN.md section 1). Nothing is fetched or bought for
these hypotheses; the facts below were read on Nov 16, 2026 (17:10 IST):
  - PC search: no file named *gift*; Production's cache has no GIFT / SGX / rates / sector / constituent table; the
    Breeze history holds NIFTY and SENSEX (index, futures, options) and only daily bars of BANKNIFTY.
  - RBI's monetary-policy page (rbi.org.in/Scripts/Annualpolicy.aspx): 2026-27 MPC decisions Apr 8, Jun 5, Aug 5 and
    Oct 7, 2026; scheduled Dec 4, 2026 and Feb 5, 2027. Earlier years sit behind the page's year selector (not fetched).
  - NSE's lot file (nsearchives.nseindia.com/content/fo/fo_mktlots.csv): BANKNIFTY lot 30 for Nov 2026 - Sep 2027.
SN355's calendar-only description: on the 2026 decision days inside gl's sample (Apr 8, Jun 5, Aug 5, Oct 7), one lot
each of the front-weekly ATM CE and PE bought at 10:15 and held 60 minutes (Rs 3,000 stop), against the same clock on
every other 2026 non-expiry session. A description, never a signal (no surprise measure exists here).
SN356's arithmetic: Black-76 ATM call premium per lot (30) at BANKNIFTY 54,267.4 (the PC's last close, Oct 28, 2026),
volatility 15% and 18%, 7 / 14 / 21 / 28 calendar days to the monthly expiry, against the Rs 15,000 debit room of a
Rs 30,000 wallet.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn251"))
import gl  # noqa: E402

OUT = HERE / "results-sn354-356.json"
MPC_2026 = ["2026-04-08", "2026-06-05", "2026-08-05", "2026-10-07"]


def N(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def atm_call(F, T, s):
    v = s * math.sqrt(T)
    return F * (N(0.5 * v) - N(-0.5 * v))


def rbi_description():
    raw = gl._cache("devall", gl.build_dev)
    smp = gl.Sample("ALL", raw, "2026-01-01", gl.TEST_HI)
    ev, ctl = [], []
    for d in smp.days:
        s = smp.s[d]
        if s["day"] == s["expiry"]:
            continue
        i = 60                                   # 10:15
        k = gl.atm(smp, s, i)
        for side in ("CE", "PE"):
            out = {}
            for st in (0.0, 205.0):
                pos = gl.Pos(smp, s, [(k, side, +1)], i, lots=1, stress=st)
                if not pos.ok:
                    break
                net, _j, _w = gl.walk(pos, s, i, i + 60, room=3000.0)
                out[int(st)] = net
            if len(out) == 2 and None not in out.values():
                (ev if d in MPC_2026 else ctl).append(out)
    f = lambda xs, st: round(float(np.mean([x[st] for x in xs])), 1) if xs else None  # noqa: E731
    return {"event_positions": len(ev), "event_net0": f(ev, 0), "event_net205": f(ev, 205),
            "control_positions": len(ctl), "control_net0": f(ctl, 0), "control_net205": f(ctl, 205),
            "event_days_in_sample": [d for d in MPC_2026 if d in smp.s]}


def main():
    if OUT.exists():
        raise SystemExit("SN354-SN356 are recorded once")
    S = 54267.4
    afford = {}
    for vol in (0.15, 0.18):
        for days in (7, 14, 21, 28):
            p = atm_call(S, days / 365.0, vol)
            afford[f"vol {int(vol * 100)}% {days}d"] = {"premium_per_unit": round(p, 1), "per_lot": round(p * 30), "fits_15000": p * 30 <= 15000}
    res = {
        "SN354": {"verdict": "BLOCKED", "found": "no timestamped GIFT NIFTY data on this PC or in Production's cache",
                  "needed": "per-minute NSE IX GIFT NIFTY futures (contract month, exchange timestamps) from 15:30 the previous day to 09:15, from a licensed, reproducible source"},
        "SN355": {"verdict": "UNTESTABLE HERE (feasibility only)", "mpc_2026": MPC_2026, "scheduled": ["2026-12-04", "2027-02-05"],
                  "events_per_year": "about 6 scheduled decisions (RBI's 2026-27 schedule lists 6)",
                  "missing": ["pre-event expectations (survey or OIS-implied)", "intraday OIS / G-sec reaction", "release timestamps beyond the 10:00 statement"],
                  "calendar_only_description": rbi_description()},
        "SN356": {"verdict": "BLOCKED (data) and mostly UNAFFORDABLE at ATM", "lot": 30, "banknifty_last_close_on_pc": {"date": "2026-10-28", "close": S},
                  "atm_call_per_lot": afford,
                  "missing": ["BANKNIFTY option quotes or minutes", "bank-constituent 1-minute bars", "timestamped bank disclosures"],
                  "download_needs_owner": True},
        "SN357": {"verdict": "NOT TRIGGERED", "why": "no candidate reached a trade rule: SN353 (b) closed, SN353 (c) is forward-only, SN354-SN356 blocked"},
        "SN360": {"verdict": "NOT TRIGGERED", "why": "no survivor; SN352's journal (sn352.Journal) is the harness left for a later candidate"},
    }
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
