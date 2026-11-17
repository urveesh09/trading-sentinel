"""SN399: a maximum price from the move the forecast can still deliver (PLAN.md section 1, frozen at 00693405; details
fixed here before any SN399 number).

HONEST 09:16:00 decision (labels and fill at the 09:15 close), AUCTION sessions with g != 0. Candidates: the auction-side
ATM, 1-ITM and 2-ITM, each admissible under the cash rule at its label ask. For each candidate at entry:
  m0 = model mid (the 09:15 close), a0 = gl's modelled ask, F0 / T0 / IV / delta / vega / theta by Black-76 on the synthetic
  forward (sn383's functions), and the hurdle in index points
    H = [ (a0 - m0) + half the modelled spread at m0 (the exit allowance) + round-trip charges / lot + stress / lot
          + |theta| x (T0 - T1)  - vega x E(dIV) ] / |delta|                        (T1 = 10:16; per unit of option)
  E(dIV) = the mean change of the ATM straddle IV from 09:16 to 10:16 (HONEST: index 0 -> 60) over EARLIER sessions with
  the same fixed CHEAP / OTHER label (>= 30 earlier, else no trade).
Forecast F = the mean signed index move from 09:16 to 10:16 (close 0 -> 60) in the gap's direction over EARLIER sessions in
the same |gap| half (the causal median of earlier |gap|): the GAP history first (Apr 2022 - Dec 5, 2025, index gap
|gap| >= 0.10%), then the earlier AUCTION sessions (>= 30 earlier sessions in the half, else no trade).
Rule: take the admissible candidate with the lowest H; trade it if F >= H (60 minutes, Rs 3,000 stop), else SKIP. The
Rs 400 run uses H with the Rs 400 stress. Compared on the same sessions with the fixed ITM rule (2 then 1, all
sessions) and fixed ITM on CHEAP (fw9's rule on the HONEST clock): per-session net, trades, missed winners (sessions SN399
skips where fixed ITM made money), incremental net vs fixed ITM; and the distribution of H and F.
"""
from __future__ import annotations

import bisect
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import op  # noqa: E402

sys.path.insert(0, str(op.FNO / "2026-11-16-sn381"))
import sn383_394 as X  # noqa: E402

gl, V, wk = op.gl, op.V, op.wk
OUT = HERE / "results-sn399.json"
GAP_HI = "2025-12-06"


def follow(s, direction):
    c0, c60 = s["index"][3][0], s["index"][3][60]
    return None if (np.isnan(c0) or np.isnan(c60)) else float(c60 - c0) * direction


def hurdle(smp, s, side, dep, stress, e_div):
    atm = gl.atm(smp, s, 0)
    k = atm + (-1 if side == "CE" else 1) * dep * 50
    m0 = gl.opx(s, k, side, 0)
    if m0 is None:
        return None
    a0 = wk.ask(smp.mk, m0)
    if op.entry_cost(a0) > op.ROOM:
        return None
    F0 = X.synthetic(smp, s, 0)
    if F0 is None:
        return None
    T0, T1 = op.sn361.years_to(s["day"], s["expiry"], "09:16"), op.sn361.years_to(s["day"], s["expiry"], "10:16")
    iv = X.leg_iv(m0, F0, k, T0, side)
    if iv is None:
        return None
    dl, vg, th = X.greeks(F0, k, T0, iv, side)
    if abs(dl) < 0.05:
        return None
    half = 0.5 * (wk.ask(smp.mk, m0) - wk.bid(smp.mk, m0))
    fees = wk.charges(a0, a0, op.LOT, "NFO") / op.LOT
    per_unit = (a0 - m0) + half + fees + stress / op.LOT + abs(th) * (T0 - T1) - vg * e_div
    return {"dep": dep, "k": k, "H": per_unit / abs(dl), "delta": abs(dl), "per_unit": per_unit, "m0": m0}


def main():
    if OUT.exists():
        raise SystemExit("SN399 is run once")
    smp, days, au = op.setup()
    jm = op.jumps(smp, "HONEST")
    lab = op.labels(jm, True)
    # the IV-change history by label (every labelled session, chronological)
    div_hist = []
    for d in sorted(lab):
        s = smp.s[d]
        a, b = V.straddle_iv(smp, s, 0), V.straddle_iv(smp, s, 60)
        if a is not None and b is not None:
            div_hist.append((d, lab[d] == "CHEAP", b - a))
    div_days = [x[0] for x in div_hist]
    # the forecast history: GAP sessions before the auction era, then auction sessions
    fh = []
    for d in days:
        if d >= GAP_HI:
            break
        s, pb = smp.s[d], smp.prev_bar(d)
        o = s["index"][0][0]
        if pb is None or np.isnan(o):
            continue
        g = float(o) / float(pb[3]) - 1.0
        if abs(g) < 0.001:
            continue
        f = follow(s, 1 if g > 0 else -1)
        if f is not None:
            fh.append((d, abs(g), f))
    auc_days = sorted(d for d, a in au.items() if a["g"] != 0)
    rows = []
    for d in auc_days:
        s, a = smp.s[d], au[d]
        side = "CE" if a["g"] > 0 else "PE"
        direction = 1 if a["g"] > 0 else -1
        r = {"day": d, "period": "post" if d >= op.SPLIT else "pre", "src": a["how"], "cheap": lab.get(d) == "CHEAP", "has_label": d in lab}
        # fixed ITM on the HONEST clock
        for st in (205.0, 400.0):
            pos, dep, state, jf = op.leg(smp, s, side, 1, "HONEST", st)
            r[f"fixed@{int(st)}"] = (gl.walk(pos, s, jf, jf + 60, room=op.STOP)[0] or 0.0) if pos is not None else 0.0
            r["fixed_state"] = state
        # forecast and hurdle (causal)
        prior = [x for x in fh if x[0] < d]
        medg = float(np.median([x[1] for x in prior])) if prior else None
        half = [x[2] for x in prior if (x[1] >= medg) == (abs(a["g"]) >= medg)] if prior else []
        F = float(np.mean(half)) if len(half) >= 30 else None
        k = bisect.bisect_left(div_days, d)
        same = [x[2] for x in div_hist[:k] if x[1] == (lab.get(d) == "CHEAP")]
        e_div = float(np.mean(same)) if len(same) >= 30 and d in lab else None
        r["F"], r["E_dIV"] = F, e_div
        for st in (205.0, 400.0):
            r[f"sn399@{int(st)}"] = 0.0
            if F is None or e_div is None:
                r[f"sn399_state@{int(st)}"] = "NO_FORECAST"
                continue
            cands = [h for h in (hurdle(smp, s, side, dep, st, e_div) for dep in (0, 1, 2)) if h is not None]
            if not cands:
                r[f"sn399_state@{int(st)}"] = "INADMISSIBLE"
                continue
            best = min(cands, key=lambda h: h["H"])
            r[f"H@{int(st)}"], r[f"dep@{int(st)}"] = best["H"], best["dep"]
            if F < best["H"]:
                r[f"sn399_state@{int(st)}"] = "SKIP"
                continue
            pos = gl.Pos(smp, s, [(best["k"], side, +1)], 0, lots=1, stress=st)
            net = gl.walk(pos, s, 0, 60, room=op.STOP)[0] if pos.ok else None
            r[f"sn399@{int(st)}"] = net or 0.0
            r[f"sn399_state@{int(st)}"] = "TRADED"
        rows.append(r)
    res = {"sessions": len(rows), "with_forecast": sum(r["F"] is not None for r in rows), "with_E_dIV": sum(r["E_dIV"] is not None for r in rows)}
    for st in (205, 400):
        ok = [r for r in rows if r[f"sn399_state@{st}"] != "NO_FORECAST"]
        traded = [r for r in ok if r[f"sn399_state@{st}"] == "TRADED"]
        skipped = [r for r in ok if r[f"sn399_state@{st}"] == "SKIP"]
        res[f"@{st}"] = {
            "eligible_sessions": len(ok), "traded": len(traded), "skipped": len(skipped),
            "states": {x: sum(r[f"sn399_state@{st}"] == x for r in ok) for x in ("TRADED", "SKIP", "INADMISSIBLE")},
            "sn399_per_session": op.per_session([r[f"sn399@{st}"] for r in ok]),
            "fixed_ITM_per_session": op.per_session([r[f"fixed@{st}"] for r in ok]),
            "fixed_ITM_CHEAP_per_session": op.per_session([r[f"fixed@{st}"] if r["cheap"] else 0.0 for r in ok]),
            "incremental_vs_fixed": round(sum(r[f"sn399@{st}"] - r[f"fixed@{st}"] for r in ok)),
            "missed_winners": sum(1 for r in skipped if r[f"fixed@{st}"] > 0), "missed_winner_net": round(sum(r[f"fixed@{st}"] for r in skipped if r[f"fixed@{st}"] > 0)),
            "avoided_losers": sum(1 for r in skipped if r[f"fixed@{st}"] < 0), "avoided_loser_net": round(sum(r[f"fixed@{st}"] for r in skipped if r[f"fixed@{st}"] < 0)),
            "traded_per_trade": op.per_session([r[f"sn399@{st}"] for r in traded]),
            "H_median": round(float(np.median([r[f"H@{st}"] for r in ok if f"H@{st}" in r])), 1) if any(f"H@{st}" in r for r in ok) else None,
            "H_p10_p90": [round(float(np.percentile([r[f"H@{st}"] for r in ok if f"H@{st}" in r], q)), 1) for q in (10, 90)] if any(f"H@{st}" in r for r in ok) else None,
            "depth_chosen": {str(dp): sum(1 for r in ok if r.get(f"dep@{st}") == dp) for dp in (0, 1, 2)},
            "by_period": {p: op.per_session([r[f"sn399@{st}"] for r in ok if r["period"] == p]) for p in ("pre", "post")},
        }
    res["F_median"] = round(float(np.median([r["F"] for r in rows if r["F"] is not None])), 2)
    res["F_range"] = [round(float(min(r["F"] for r in rows if r["F"] is not None)), 2), round(float(max(r["F"] for r in rows if r["F"] is not None)), 2)]
    res["E_dIV_by_label_last"] = {lb: round(float(np.mean([x[2] for x in div_hist if x[1] == (lb == "CHEAP")])), 4) for lb in ("CHEAP", "OTHER")}
    res["realized_follow_median_auction"] = round(float(np.median([f for f in (follow(smp.s[d], 1 if au[d]["g"] > 0 else -1) for d in auc_days) if f is not None])), 2)
    res["rows"] = rows
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1, default=float))


if __name__ == "__main__":
    main()
