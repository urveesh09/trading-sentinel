"""SN276 - the pooled dataset (PLAN.md): every session of DEV, TEST, EXAM-N and EXAM-S; features known at 10:00; the
outcomes of the ATM straddle (S), ATM call (C) and ATM put (P) bought at 10:00 and held to 15:10 with the Rs 3,000 stop,
at Rs 205, Rs 400 and one minute late; the index direction 10:00 -> 15:10. Built with sn251's gl / legs, unchanged."""
from __future__ import annotations

import datetime as dt
import json
import math
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SN251 = HERE.parent / "2026-11-16-sn251"
sys.path.insert(0, str(SN251))
import gl  # noqa: E402
import legs as LG  # noqa: E402
import sn259  # noqa: E402
import sn262  # noqa: E402

LOCAL = HERE / "_local"
I0, FL = gl.I["10:00"], gl.FLAT
SAMPLES = ("EXAMN", "DEV", "TEST", "EXAMS")
FEATURES = ("r_today", "or30", "gap", "abs_gap", "move_to_10", "vwap_dev_atr", "y_range", "y_ret", "rv5", "breakout10", "adx",
            "dmi_dir", "dte", "weekday", "pre_holiday", "turn_of_month", "rbi", "straddle_pct", "basis_change", "fut_vol_ratio",
            "is_sensex")
RBI = set(json.loads((SN251 / "events.json").read_text(encoding="utf-8"))["RBI"])


def atr14(smp, d):
    bars = [smp.prev_bar(d, k) for k in range(1, 16)]
    if any(b is None for b in bars):
        return None
    return float(np.mean([max(b[1] - b[2], abs(b[1] - p[3]), abs(b[2] - p[3])) for b, p in zip(bars[:14], bars[1:15])]))


def features(smp, d, prev_sessions):
    s = smp.s[d]
    ix, fu = s["index"], s["future"]
    o = float(ix[0][0])
    c10 = float(ix[3][I0])
    pb, pb2 = smp.prev_bar(d, 1), smp.prev_bar(d, 2)
    bars = [smp.prev_bar(d, k) for k in range(1, 12)]
    if pb is None or pb2 is None or any(b is None for b in bars):
        return None
    rt = sn262.r_today(smp, s)
    a = atr14(smp, d)
    K = gl.atm(smp, s, I0)
    ce, pe = gl.opx(s, K, "CE", I0), gl.opx(s, K, "PE", I0)
    if rt is None or not a or ce is None or pe is None:
        return None
    v = fu[4][: I0 + 1]
    tp = (fu[1][: I0 + 1] + fu[2][: I0 + 1] + fu[3][: I0 + 1]) / 3.0
    vwap = float(np.sum(tp * v) / np.sum(v)) - (float(fu[3][I0]) - c10) if np.sum(v) > 0 else np.nan
    closes = [b[3] for b in bars[:6]][::-1]
    rv5 = float(np.std(np.diff(np.log(closes))))
    prior10 = bars[1:11]
    y = pb[3]
    br = 1 if y > max(b[1] for b in prior10) else (-1 if y < min(b[2] for b in prior10) else 0)
    adx_r = (smp._adx or {}).get(d) if smp._adx is not None else None
    if smp._adx is None:
        smp.adx(d)
        adx_r = smp._adx.get(d)
    basis_now = float(fu[3][I0]) - c10
    if prev_sessions:
        ps = smp.s[prev_sessions[-1]]
        basis_prev = float(ps["future"][3][-1]) - float(ps["index"][3][-1])
        vols = [float(np.sum(smp.s[x]["future"][4][: I0 + 1])) for x in prev_sessions[-5:]]
        fvr = float(np.sum(v)) / np.mean(vols) if np.mean(vols) > 0 and np.sum(v) > 0 else np.nan
    else:
        basis_prev, fvr = np.nan, np.nan
    return [rt, (float(np.max(ix[1][:30])) - float(np.min(ix[2][:30]))) / o, o / y - 1.0, abs(o / y - 1.0), c10 / o - 1.0,
            (c10 - vwap) / a if not np.isnan(vwap) else np.nan, (pb[1] - pb[2]) / pb[3], pb[3] / pb2[3] - 1.0, rv5, br,
            adx_r["adx"] if adx_r else np.nan, adx_r["dir"] if adx_r else np.nan, smp.sessions_until(d, s["expiry"]),
            dt.date.fromisoformat(d).weekday(), float(sn259.pre_holiday(smp, d)), float(sn259.turn_of_month(smp, d)),
            float(d in RBI), (ce + pe) / c10, (basis_now - basis_prev) / c10 if not np.isnan(basis_prev) else np.nan, fvr,
            float(smp.inst == "SENSEX")]


def outcomes(smp, d):
    s = smp.s[d]
    out = {}
    for tag, kw in (("205", {}), ("400", {"stress": 400.0}), ("late", {"late": 1})):
        for a, lg in (("S", LG.straddle(smp, s, I0)), ("C", LG.side_legs(smp, s, I0, 1)), ("P", LG.side_legs(smp, s, I0, -1))):
            t = LG.intraday(smp, d, lg, I0, FL, **kw)
            out[f"{a}{tag}"] = None if t is None else t["net"]
            if tag == "205":
                out[f"{a}prem"] = None if t is None else t["premium"]
    return out


def build():
    rows = []
    for n in SAMPLES:
        if n in gl.SEALED:
            gl.SEALED[n] = True
        smp = gl.sample(n)
        prev = []
        for d in smp.days:
            f = features(smp, d, prev)
            prev.append(d)
            if f is None:
                continue
            o = outcomes(smp, d)
            if any(o[k] is None for k in ("S205", "C205", "P205")):
                continue
            ix = smp.s[d]["index"][3]
            rows.append({"day": d, "sample": n, "inst": smp.inst, "x": f, "up": float(ix[FL] > ix[I0]), **o})
        print("SN276", n, "rows", sum(r["sample"] == n for r in rows), flush=True)
    return rows


def load():
    p = LOCAL / "ds.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    LOCAL.mkdir(exist_ok=True)
    rows = build()
    p.write_bytes(pickle.dumps(rows))
    return rows


if __name__ == "__main__":
    out = HERE / "results-sn276.json"
    if out.exists():
        raise SystemExit("SN276 is run once")
    rows = load()
    res = {"rows": len(rows), "features": FEATURES, "base_rates": {}}
    for n in SAMPLES:
        rs = [r for r in rows if r["sample"] == n]
        res["base_rates"][n] = {"sessions": len(rs), "first": rs[0]["day"], "last": rs[-1]["day"],
                                **{a: {"mean_net": round(float(np.mean([r[f"{a}205"] for r in rs]))),
                                       "win_pct": round(100 * float(np.mean([r[f"{a}205"] > 0 for r in rs])), 1)} for a in "SCP"},
                                "up_share": round(float(np.mean([r["up"] for r in rs])), 3),
                                "missing_share": {f: round(float(np.mean([np.isnan(r["x"][k]) for r in rs])), 3) for k, f in enumerate(FEATURES)
                                                  if np.mean([np.isnan(r["x"][k]) for r in rs]) > 0}}
        print("SN276", n, json.dumps(res["base_rates"][n]), flush=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
