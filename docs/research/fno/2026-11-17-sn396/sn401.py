"""SN401: a second instrument for dates NIFTY cannot serve (PLAN.md section 1, frozen at 00693405; details fixed here
before any SN401 number). gl's EXAMS sample (SENSEX, Oct 2024 - Apr 2026) is already SEEN for option buyers (SN251 -
SN272); it is opened here for that reason (gl.SEALED is set in this process only).

SENSEX sessions (non-SENSEX-expiry days with the front weekly). Each is classified by what NIFTY could do that day:
  EXPIRY        a NIFTY expiry day (gl DEV sessions with day == expiry)
  INADMISSIBLE  NIFTY had a signal (the futures auction direction from Dec 8, 2025, else the index gap |gap| >= 0.10%)
                but its HONEST ITM leg (2 then 1) was not affordable under the cash rule
  NO_SIGNAL     NIFTY had no signal (reported only)
  COMMON        NIFTY trades (the comparison set)
SENSEX trade (HONEST 09:16:00: labels and fill at the 09:15 close): signal = SENSEX's own index gap (09:15 open vs the
previous close, |gap| >= 0.10%); on auction-era days also the NIFTY auction direction as an alternative; ITM 2 then 1
(100-point steps), lot 20 (gl's SENSEX lot), walked model ask + BFO entry charges <= Rs 15,000, 60 minutes, Rs 3,000
stop, Rs 205 / 400 per lot. Pass (per signal): per-session net > 0 at Rs 205 and Rs 400 on NIFTY-skip days (EXPIRY +
INADMISSIBLE), > 0 without the best day. BANKNIFTY: only daily bars on this PC (recorded).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import op  # noqa: E402

gl, wk = op.gl, op.wk
OUT = HERE / "results-sn401.json"


def leg_s(smp, s, side, stress, depths=(2, 1)):
    """SENSEX ITM leg on the HONEST clock (label and fill at index 0)."""
    mk = smp.mk
    k0 = gl.atm(smp, s, 0)
    sgn = -1 if side == "CE" else 1
    for dep in depths:
        k = k0 + sgn * dep * mk["step"]
        p = gl.opx(s, k, side, 0)
        if p is None:
            continue
        a = wk.ask(mk, p)
        if a * mk["lot"] + wk.charges(a, 0.0, mk["lot"], mk["exch"]) > op.ROOM:
            continue
        pos = gl.Pos(smp, s, [(k, side, +1)], 0, lots=1, stress=stress)
        if not pos.ok:
            return None, "NO_PRICE"
        return pos, "FILLED"
    return None, "INADMISSIBLE"


def gap_of(smp, d):
    s, pb = smp.s[d], smp.prev_bar(d)
    o = s["index"][0][0]
    if pb is None or np.isnan(o):
        return None
    return float(o) / float(pb[3]) - 1.0


def block(rows, key, st):
    xs = [r[key][f"net{st}"] for r in rows if key in r]
    return {"n": len(xs), "fills": sum(1 for r in rows if key in r and r[key]["state"] == "FILLED"), "per_session": op.per_session(xs), "without_best": op.without_best(xs),
            "by_year": {y: op.per_session([r[key][f"net{st}"] for r in rows if key in r and r["day"][:4] == y]) for y in ("2024", "2025", "2026")}}


def main():
    if OUT.exists():
        raise SystemExit("SN401 is run once")
    smpN, _daysN, au = op.setup()
    raw = gl._cache("devall", gl.build_dev)
    allN = gl.Sample("ALLN", raw)
    nifty_expiry = {d for d in allN.days if allN.s[d]["day"] == allN.s[d]["expiry"]}
    gl.SEALED["EXAMS"] = True                      # already seen for option buyers (SN251 - SN272)
    smpS = gl.sample("EXAMS")
    rows = []
    for d in smpS.days:
        r = {"day": d}
        if d in nifty_expiry:
            r["nifty"] = "EXPIRY"
        elif d in smpN.s:
            if d in au and au[d]["g"] != 0:
                sideN = "CE" if au[d]["g"] > 0 else "PE"
            else:
                gN = gap_of(smpN, d)
                sideN = None if gN is None or abs(gN) < 0.001 else ("CE" if gN > 0 else "PE")
            if sideN is None:
                r["nifty"] = "NO_SIGNAL"
            else:
                _pos, _dep, state, _jf = op.leg(smpN, smpN.s[d], sideN, 1, "HONEST", 205.0)
                r["nifty"] = "COMMON" if state == "FILLED" else "INADMISSIBLE" if state == "INADMISSIBLE" else "NO_SIGNAL"
        else:
            r["nifty"] = "NO_DATA"
        s = smpS.s[d]
        gS = gap_of(smpS, d)
        signals = {}
        if gS is not None and abs(gS) >= 0.001:
            signals["SENSEX_GAP"] = "CE" if gS > 0 else "PE"
        if d in au and au[d]["g"] != 0:
            signals["NIFTY_AUCTION"] = "CE" if au[d]["g"] > 0 else "PE"
        for name, side in signals.items():
            x = {}
            for st in (205.0, 400.0):
                pos, state = leg_s(smpS, s, side, st)
                x["state"] = state
                net = gl.walk(pos, s, 0, 60, room=op.STOP)[0] if pos is not None else None
                x[f"net{int(st)}"] = net if (state == "FILLED" and net is not None) else 0.0
            r[name] = x
        rows.append(r)
    res = {"sensex_sessions": len(rows), "classes": {c: sum(r["nifty"] == c for r in rows) for c in ("EXPIRY", "INADMISSIBLE", "NO_SIGNAL", "COMMON", "NO_DATA")},
           "banknifty": "no intraday BANKNIFTY history on this PC: the Breeze DB holds only its daily bars (1,195, Jan 3, 2022 - Oct 28, 2026); no futures / options minutes; the recorder and the archive hold none"}
    skip = [r for r in rows if r["nifty"] in ("EXPIRY", "INADMISSIBLE")]
    for sig in ("SENSEX_GAP", "NIFTY_AUCTION"):
        for st in (205, 400):
            res[f"{sig} skip-days @{st}"] = block(skip, sig, st)
            res[f"{sig} expiry-days @{st}"] = block([r for r in rows if r["nifty"] == "EXPIRY"], sig, st)
            res[f"{sig} inadmissible-days @{st}"] = block([r for r in rows if r["nifty"] == "INADMISSIBLE"], sig, st)
            res[f"{sig} common-days @{st}"] = block([r for r in rows if r["nifty"] == "COMMON"], sig, st)
        a, b = res[f"{sig} skip-days @205"], res[f"{sig} skip-days @400"]
        res[f"{sig} pass"] = bool(a["n"] and a["per_session"] > 0 and b["per_session"] > 0 and (a["without_best"] or -1) > 0)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
