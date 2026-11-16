"""SN290 - the executable hurdle (PLAN.md), on the sealed per-minute real-quote archive (SN101's 41 days, Sep 10 -
Nov 12 2026). NIFTY front-weekly ATM CE, ATM PE and the straddle (strike nearest the front future's mid), one lot, bought
at 09:20 / 10:00 / 11:00 / 13:00 / 14:00 and sold 15 or 60 minutes later:
  real   = buy at the real ask (walking the 5 levels for one lot), sell at the real bid (walking the levels);
  model  = the research engine's rule on the same minutes: ask/bid = mid +/- half the P75 spread table (gl / wk);
  delay  = the real round trip with entry and exit one minute later, minus the on-time one (signed and absolute);
all with Zerodha charges. (Fix before any score: the day list comes from SN101's sealed per-minute caches; the
export manifest qa.days() read was replaced on Nov 13.) Reports per lot: real spread cost, model spread cost, the gap, the delay movement, and
the total hurdle against the Rs 205 house stress."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn251"))
sys.path.insert(0, str(FNO / "2026-11-13-sn101"))
import gl  # noqa: E402
import qa  # noqa: E402

CLOCKS = {"09:20": 5, "10:00": 45, "11:00": 105, "13:00": 225, "14:00": 285}
HOLDS = (15, 60)


def walk(prices, qtys, need):
    got, cost = 0, 0.0
    for p, q in zip(prices, qtys):
        if np.isnan(p) or np.isnan(q) or q <= 0:
            continue
        take = min(q, need - got)
        cost += take * p
        got += take
        if got >= need:
            return cost / need
    return None


def real_px(rec, i, side, lot):
    if i >= qa.NM or not rec["usable"][i]:
        return None
    if side == "buy":
        return walk(rec["askp"][:, i], rec["askq"][:, i], lot)
    return walk(rec["bidp"][:, i], rec["bidq"][:, i], lot)


def mid(rec, i):
    if i >= qa.NM or not rec["usable"][i] or np.isnan(rec["bid"][i]) or np.isnan(rec["ask"][i]):
        return None
    return (rec["bid"][i] + rec["ask"][i]) / 2.0


def front(q, day):
    exps = sorted({k[1] for k in q["opt"] if k[0] == "NIFTY" and k[1] > day})
    return exps[0] if exps else None


if __name__ == "__main__":
    out = HERE / "results-sn290.json"
    if out.exists():
        raise SystemExit("SN290 is run once")
    mk = gl.INST["NIFTY"]
    rows = []
    days = sorted(x.stem.replace("quotes-", "") for x in qa.LOCAL.glob("quotes-*.pkl"))   # the sealed per-minute caches
    for day in days:
        try:
            q = qa.load(day)
        except Exception:
            continue
        e = front(q, day)
        fk = sorted(k for k in q["fut"] if k[0] == "NIFTY")
        if e is None or not fk:
            continue
        fut = q["fut"][fk[0]]
        lot = q["lot"]["NIFTY"]
        for cn, i in CLOCKS.items():
            fm = mid(fut, i)
            if fm is None:
                continue
            K = int(round(fm / 50.0) * 50)
            for name, legs in (("CE", [(K, "CE")]), ("PE", [(K, "PE")]), ("straddle", [(K, "CE"), (K, "PE")])):
                recs = [q["opt"].get(("NIFTY", e, k, o)) for k, o in legs]
                if any(r is None for r in recs):
                    continue
                for h in HOLDS:
                    j = i + h
                    vals = {}
                    for tag, (a, b) in (("ontime", (i, j)), ("late", (i + 1, j + 1))):
                        rb = [real_px(r, a, "buy", lot) for r in recs]
                        rs = [real_px(r, b, "sell", lot) for r in recs]
                        ma = [mid(r, a) for r in recs]
                        mb = [mid(r, b) for r in recs]
                        if any(x is None for x in rb + rs + ma + mb):
                            vals = None
                            break
                        real = sum((s - bb) * lot - gl.wk.charges(bb, s, lot, "NFO") for bb, s in zip(rb, rs))
                        model = sum((gl.wk.bid(mk, y) - gl.wk.ask(mk, x)) * lot - gl.wk.charges(gl.wk.ask(mk, x), gl.wk.bid(mk, y), lot, "NFO")
                                    for x, y in zip(ma, mb))
                        midmove = sum((y - x) * lot for x, y in zip(ma, mb))
                        vals[tag] = (real, model, midmove, sum(ma))
                    if not vals:
                        continue
                    r0, m0, mm0, prem = vals["ontime"]
                    r1 = vals["late"][0]
                    rows.append({"day": day, "clock": cn, "kind": name, "hold": h, "premium_pts": prem,
                                 "real_cost": mm0 - r0, "model_cost": mm0 - m0, "delay": r1 - r0, "legs": len(legs)})
    res = {"days": len({r["day"] for r in rows}), "rows": len(rows), "by": {}}
    for kind in ("CE", "PE", "straddle"):
        for h in HOLDS:
            rs = [r for r in rows if r["kind"] == kind and r["hold"] == h]
            if not rs:
                continue
            real, model, dly = (np.array([r[k] for r in rs]) for k in ("real_cost", "model_cost", "delay"))
            legs = rs[0]["legs"]
            res["by"][f"{kind} hold {h}"] = {"n": len(rs), "real_cost_per_lot_mean": round(float(real.mean())),
                                             "model_cost_per_lot_mean": round(float(model.mean())),
                                             "real_minus_model": round(float((real - model).mean())),
                                             "delay_1min_mean": round(float(dly.mean())), "delay_1min_abs_mean": round(float(np.abs(dly).mean())),
                                             "house_stress": 205 * legs,
                                             "hurdle_real_plus_abs_delay": round(float(real.mean() + np.abs(dly).mean())),
                                             "by_clock_real_cost": {c: round(float(np.mean([r["real_cost"] for r in rs if r["clock"] == c])))
                                                                    for c in CLOCKS if any(r["clock"] == c for r in rs)}}
            print("SN290", kind, h, json.dumps(res["by"][f"{kind} hold {h}"]), flush=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
