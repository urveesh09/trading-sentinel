"""SN404: were the stand-aside's blocked recovery entries priced differently? (PLAN.md section 1, frozen at 00693405;
details fixed here before any SN404 number). SN399 found no usable price criterion (the forecast never clears the
hurdle), so by the plan no prospective arm is specified; this slot measures and closes.

Cohorts (2022-26 path, Rs 205, from SN403's cached Gold logs; gl range Apr 2022 on):
  BLOCKED   the stand-aside's suppressions (NO_STAND signals absent from N11) that produced a Gold trade in NO_STAND+R0.85
  ACCEPTED  Gold's DEPLOYED trades from TPB signals
Measured at the signal bar (stream minute i, the bar close where N11 decided and Gold filled; zero latency), for the
signal's own strike and side: model mid / ask; time-value share (intrinsic on the index close); the ATM straddle IV at i,
minus the same session's 09:16 IV (index 1), minus the previous session's 15:00 IV (index 345, same expiry, else none);
sessions to expiry; the 60-minute hurdle in points H = [(ask - mid) + half spread + round-trip charges / lot + 205 / lot
+ |theta| x 60 min] / |delta| and H / ATR14 (daily). Outcome: Gold's net per lot at entry (net / lots0).
Reported: medians per cohort split winners / losers, and Spearman correlations of each measure with the per-lot net
inside BLOCKED and inside ACCEPTED.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import op  # noqa: E402

sys.path.insert(0, str(op.FNO / "2026-11-16-sn381"))
import sn383_394 as X  # noqa: E402
import sn392 as P  # noqa: E402

gl, V, wk = op.gl, op.V, op.wk
OUT = HERE / "results-sn404.json"
RUNS = HERE / "_local" / "sn403-runs.json"
YEARS = ("2022", "2023", "2024", "2025", "2026")


def spearman(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = ~(np.isnan(x) | np.isnan(y))
    x, y = x[ok], y[ok]
    if len(x) < 8:
        return {"n": int(len(x)), "rho": None}
    rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y))
    rho = float(np.corrcoef(rx, ry)[0, 1])
    t = rho * np.sqrt((len(x) - 2) / max(1e-12, 1 - rho * rho))
    return {"n": int(len(x)), "rho": round(rho, 3), "t": round(float(t), 2)}


def atr14(smp, d):
    k = smp.cal.index(d) if d in smp.cal else None
    if k is None or k < 15:
        return None
    trs = []
    for j in range(k - 14, k):
        _o, h, l, _c = smp.daily[smp.cal[j]][:4]
        pc = smp.daily[smp.cal[j - 1]][3]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return float(np.mean(trs))


def measure(smp, sg):
    d, i = sg["day"], sg["i"]
    if d not in smp.s or not 1 <= i < gl.NM:
        return None
    s = smp.s[d]
    if s["expiry"] != sg["expiry"]:
        return None
    k, o = sg["strike"], sg["opt"]
    m = gl.opx(s, k, o, i)
    if m is None:
        return None
    a = wk.ask(smp.mk, m)
    F = X.synthetic(smp, s, i)
    hh = f"{(555 + i) // 60:02d}:{(555 + i) % 60:02d}"
    T0 = op.sn361.years_to(d, s["expiry"], hh)
    if F is None or T0 <= 0:
        return None
    iv = X.leg_iv(m, F, k, T0, o)
    out = {"ask": a, "mid": m, "tv_share": (m - max(0.0, (F - k) if o == "CE" else (k - F))) / m if m > 0 else None,
           "dte": smp.sessions_until(d, s["expiry"]), "atm_iv": V.straddle_iv(smp, s, i)}
    iv16 = V.straddle_iv(smp, s, 1)
    out["iv_vs_0916"] = None if (out["atm_iv"] is None or iv16 is None) else 100.0 * (out["atm_iv"] - iv16)
    k0 = smp.days.index(d)
    prev = smp.s[smp.days[k0 - 1]] if k0 > 0 else None
    ivp = V.straddle_iv(smp, prev, 345) if prev is not None and prev["expiry"] == s["expiry"] else None
    out["iv_vs_prev1500"] = None if (out["atm_iv"] is None or ivp is None) else 100.0 * (out["atm_iv"] - ivp)
    if iv is not None:
        dl, _vg, th = X.greeks(F, k, T0, iv, o)
        T1 = max(1e-6, T0 - 60.0 / (375.0 * 252.0))
        half = 0.5 * (wk.ask(smp.mk, m) - wk.bid(smp.mk, m))
        per_unit = (a - m) + half + wk.charges(a, a, op.LOT, "NFO") / op.LOT + 205.0 / op.LOT + abs(th) * (T0 - T1)
        out["H_pts"] = per_unit / abs(dl) if abs(dl) > 0.05 else None
        at = atr14(smp, d)
        out["H_over_ATR"] = None if (out["H_pts"] is None or not at) else out["H_pts"] / at
    return out


def main():
    if OUT.exists():
        raise SystemExit("SN404 is run once")
    runs = json.loads(RUNS.read_text(encoding="utf-8"))
    smp, _days, _au = op.setup()
    sigs = {b: [x for y in YEARS for x in P.stream(y, b)] for b in ("N11", "NO_STAND")}
    k11 = {x["sig_key"] for x in sigs["N11"]}
    blocked = [x for x in sigs["NO_STAND"] if x["sig_key"] not in k11]
    logs = {a: {(t["day"], t["i"]): t for t in runs[f"2022-2026 {a} @205"]["log"]} for a in ("NO_STAND+R0.85", "DEPLOYED")}
    rows = []
    for sg in blocked:
        t = logs["NO_STAND+R0.85"].get((sg["day"], sg["i"]))
        if t is None:
            continue
        m = measure(smp, sg)
        if m is not None:
            rows.append({"cohort": "BLOCKED", "day": sg["day"], "expert": sg["expert"], "net_per_lot": t["net"] / max(1, t["lots0"] or 1), **m})
    for sg in sigs["N11"]:
        if sg["expert"] != "TPB":
            continue
        t = logs["DEPLOYED"].get((sg["day"], sg["i"]))
        if t is None:
            continue
        m = measure(smp, sg)
        if m is not None:
            rows.append({"cohort": "ACCEPTED_TPB", "day": sg["day"], "expert": sg["expert"], "net_per_lot": t["net"] / max(1, t["lots0"] or 1), **m})
    feats = ("ask", "tv_share", "dte", "atm_iv", "iv_vs_0916", "iv_vs_prev1500", "H_pts", "H_over_ATR")
    res = {"blocked_signals": len(blocked), "measured": {c: sum(r["cohort"] == c for r in rows) for c in ("BLOCKED", "ACCEPTED_TPB")}}
    for c in ("BLOCKED", "ACCEPTED_TPB"):
        rs = [r for r in rows if r["cohort"] == c]
        for wl, f in (("winners", lambda r: r["net_per_lot"] > 0), ("losers", lambda r: r["net_per_lot"] <= 0)):
            sub = [r for r in rs if f(r)]
            res[f"{c} {wl}"] = {"n": len(sub), "net_per_lot_mean": op.per_session([r["net_per_lot"] for r in sub]),
                                **{x: round(float(np.median([r[x] for r in sub if r.get(x) is not None])), 3) if any(r.get(x) is not None for r in sub) else None for x in feats}}
        res[f"{c} spearman with net per lot"] = {x: spearman([r.get(x) if r.get(x) is not None else np.nan for r in rs], [r["net_per_lot"] for r in rs]) for x in feats}
        res[f"{c} by expert"] = {e: sum(1 for r in rs if r["expert"] == e) for e in sorted({r["expert"] for r in rs})}
    res["rows"] = rows
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1, default=float))


if __name__ == "__main__":
    main()
