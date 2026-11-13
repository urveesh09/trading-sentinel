"""SN156 - leg out of a winning straddle (PLAN.md): on SN95-L days (and all signal days), once a leg's bid reaches +X%
of its ask, sell that leg and hold the other to 15:10 (Rs 3k stop on the whole position: realised + open leg at its
bid); X in {50%, 100%}; against holding both. Strict costs per leg; preference rule."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ph  # noqa: E402

C, M, pa, pb = ph.C, ph.M, ph.pa, ph.pb
XS = (0.5, 1.0)


def leg_out(S, x, stress=205.0, room=3000.0):
    i = pa.I10
    K = pb.atm(S, i)
    legs = {}
    for o in ("CE", "PE"):
        rec = S.option(K, o)
        if rec is None or not rec[6][i]:
            return None
        legs[o] = [rec, M.ask_of(float(rec[0][3][i])), True]       # rec, ask, still open
    if sum(v[1] for v in legs.values()) * M.LOT > 15000:
        return None
    realized, last_bid = 0.0, {o: None for o in legs}

    def close(o, b):
        return (b - legs[o][1]) * M.LOT - M.charges(legs[o][1], b, M.LOT) - stress
    for j in range(i + 1, C.FLAT + 1):
        for o, (rec, ask, op) in legs.items():
            b = pa.sn95.bid_at(rec, j)
            if b is not None:
                last_bid[o] = b
        if any(v is None for v in last_bid.values()):
            continue
        for o in legs:
            rec, ask, op = legs[o]
            if op and last_bid[o] >= (1 + x) * ask and all(legs[p][2] for p in legs):
                realized += close(o, last_bid[o])
                legs[o][2] = False
        open_val = sum(close(o, last_bid[o]) for o in legs if legs[o][2])
        if realized + open_val <= -room:
            return realized + open_val
    return realized + sum(close(o, last_bid[o]) for o in legs if legs[o][2] and last_bid[o] is not None)


if __name__ == "__main__":
    out_path = HERE / "results-sn156.json"
    if out_path.exists():
        raise SystemExit("SN156 is scored once")
    adm = pa.admission()
    res = {}
    for dname, gf in (("SN95-L days", True), ("all signal days", False)):
        days = pb.signal_days(adm, gf)
        hold = {S.day: pb.net(pa.path(S, pa.I10)) for S in days}
        out, raw = {"hold both": ph.table(hold)}, {"hold both": hold}
        for x in XS:
            v = {S.day: leg_out(S, x) for S in days}
            raw[f"leg out at +{int(x * 100)}%"] = {d: n for d, n in v.items() if n is not None}
            out[f"leg out at +{int(x * 100)}%"] = ph.table(raw[f"leg out at +{int(x * 100)}%"])
        base = out["hold both"]

        def wob5(d):
            xs_ = sorted(d.values(), reverse=True)
            return round(sum(xs_[5:]))
        pref = {}
        for k, t in out.items():
            if k == "hold both":
                continue
            yrs = sum(t[y]["net"] > base[y]["net"] for y in ph.YEARS)
            pref[k] = {"total": ph.tot(t), "years_better": yrs, "without_best_5": wob5(raw[k]), "hold_without_best_5": wob5(hold),
                       "preferred": bool(ph.tot(t) > ph.tot(base) and yrs >= 3 and wob5(raw[k]) > wob5(hold))}
        res[dname] = {"tables": out, "preference": pref}
        print(f"=== SN156 {dname}: hold {[base[y]['net'] for y in ph.YEARS]} {ph.tot(base)} | " +
              " | ".join(f"{k} {[t[y]['net'] for y in ph.YEARS]} {ph.tot(t)}" for k, t in out.items() if k != "hold both"), flush=True)
        print("   preference", pref, flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
