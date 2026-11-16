"""SN361: opening premium richness (PLAN.md section 2; amendment A3 in this docstring, committed before any SN361 number).

A3: the forward is the synthetic forward of the ATM pair (F = K + C - P on mids), not the monthly future (the weekly
option's own forward); the rupee measure is the fixed-strike residual R = actual mid change of the straddle bought at the
first clock minus its Black-76 change at the first clock's implied volatility (the same strikes, the new forward and the
shorter time). R ~ vega x the IV change, so R is the rupee cost (or gain) of the volatility change; vega x dIV is reported
beside it. Calendar time to 15:30 on expiry day; the control window (11:00 -> 11:29 / 11:59) carries the same time-
convention bias, so the open-minus-control difference is the result.

Windows: OPEN 09:16 -> 09:45 and 09:16 -> 10:15; CONTROL 11:00 -> 11:29 and 11:00 -> 11:59 (same lengths).
Samples: the real-quote archive (Sep 10 - Nov 13, mids of usable quotes, non-expiry days) and gl's DEV + TEST minute closes
(Apr 2022 - Oct 28, 2026, non-expiry). The ATM strike is fixed at the window's first clock. By DTE (calendar days to
expiry): 1, 2-3, 4+.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn251"))
sys.path.insert(0, str(FNO / "2026-11-13-sn101"))
import gl  # noqa: E402
import qa  # noqa: E402

qa.EXPORT = Path(r"C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\docs\research\fno\2026-10-28-forward-panel"
                 r"\_local\exports\20261116T103002Z")
OUT = HERE / "results-sn361.json"
LOT = 65
WINDOWS = {"open_29": ("09:16", "09:45"), "open_59": ("09:16", "10:15"), "ctrl_29": ("11:00", "11:29"), "ctrl_59": ("11:00", "11:59")}


def minute(hhmm):
    return int(hhmm[:2]) * 60 + int(hhmm[3:]) - 555


def N(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def b76(F, K, T, s, cp):
    if T <= 0 or s <= 0:
        return max(0.0, (F - K) if cp == "CE" else (K - F))
    v = s * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * v * v) / v
    d2 = d1 - v
    return F * N(d1) - K * N(d2) if cp == "CE" else K * N(-d2) - F * N(-d1)


def straddle(F, K, T, s):
    return b76(F, K, T, s, "CE") + b76(F, K, T, s, "PE")


def iv(price, F, K, T):
    lo, hi = 1e-4, 5.0
    if not (straddle(F, K, T, lo) < price < straddle(F, K, T, hi)):
        return None
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if straddle(F, K, T, mid) < price:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def years_to(day, expiry, hhmm):
    a = dt.datetime.fromisoformat(f"{day}T{hhmm}:00")
    b = dt.datetime.fromisoformat(f"{expiry}T15:30:00")
    return (b - a).total_seconds() / (365.0 * 86400.0)


def measure(day, expiry, K, mids_at, t0, t1):
    """mids_at(hhmm) -> (C, P) mids of strike K or None."""
    a, b = mids_at(t0), mids_at(t1)
    if a is None or b is None:
        return None
    (c0, p0), (c1, p1) = a, b
    F0, F1 = K + c0 - p0, K + c1 - p1
    T0, T1 = years_to(day, expiry, t0), years_to(day, expiry, t1)
    s0 = iv(c0 + p0, F0, K, T0)
    s1 = iv(c1 + p1, F1, K, T1)
    if s0 is None or s1 is None:
        return None
    model = straddle(F1, K, T1, s0) - straddle(F0, K, T0, s0)
    actual = (c1 + p1) - (c0 + p0)
    h = 1e-4
    vega = (straddle(F0, K, T0, s0 + h) - straddle(F0, K, T0, s0 - h)) / (2 * h)
    return {"R": (actual - model) * LOT, "vega_dIV": vega * (s1 - s0) * LOT, "iv0": s0, "iv1": s1, "actual": actual * LOT,
            "model": model * LOT, "dF_pct": 100 * (F1 / F0 - 1)}


def dte_bucket(day, expiry):
    n = (dt.date.fromisoformat(expiry) - dt.date.fromisoformat(day)).days
    return "1" if n <= 1 else "2-3" if n <= 3 else "4+"


def summarize(rows):
    out = {}
    for w in WINDOWS:
        xs = [r[w] for r in rows if r.get(w)]
        if not xs:
            continue
        R = np.array([x["R"] for x in xs])
        out[w] = {"n": len(xs), "R_mean": round(float(R.mean()), 1), "R_median": round(float(np.median(R)), 1),
                  "R_se": round(float(R.std(ddof=1) / math.sqrt(len(R))), 1) if len(R) > 1 else None,
                  "vega_dIV_mean": round(float(np.mean([x["vega_dIV"] for x in xs])), 1),
                  "iv0_mean_pct": round(100 * float(np.mean([x["iv0"] for x in xs])), 2),
                  "dIV_mean_pts": round(100 * float(np.mean([x["iv1"] - x["iv0"] for x in xs])), 3),
                  "actual_mean": round(float(np.mean([x["actual"] for x in xs])), 1)}
    for a, c in (("open_29", "ctrl_29"), ("open_59", "ctrl_59")):
        pa = {r["day"]: r[a]["R"] for r in rows if r.get(a)}
        pc = {r["day"]: r[c]["R"] for r in rows if r.get(c)}
        both = sorted(set(pa) & set(pc))
        if len(both) > 1:
            d = np.array([pa[x] - pc[x] for x in both])
            out[f"{a}_minus_{c}"] = {"n": len(d), "mean": round(float(d.mean()), 1), "se": round(float(d.std(ddof=1) / math.sqrt(len(d))), 1),
                                     "share_negative": round(float((d < 0).mean()), 3)}
    return out


def archive_rows():
    rows = []
    for d in qa.days():
        q = qa.load(d)
        exps = sorted({k[1] for k in q["opt"] if k[0] == "NIFTY" and k[1] >= d})
        if not exps or exps[0] == d:
            continue
        e = exps[0]

        def mids(K, hhmm, q=q, e=e):
            i = minute(hhmm)
            out = []
            for o in ("CE", "PE"):
                rec = q["opt"].get(("NIFTY", e, K, o))
                j = None if rec is None else qa.last_before(rec, i, i - 1)
                if j is None:
                    return None
                out.append(0.5 * (rec["bid"][j] + rec["ask"][j]))
            return tuple(out)
        r = {"day": d, "expiry": e, "dte": dte_bucket(d, e)}
        for w, (t0, t1) in WINDOWS.items():
            fut = qa.front_fut(q, "NIFTY")
            i0 = minute(t0)
            j = None if fut is None else qa.last_before(fut, i0, i0 - 1)
            if j is None:
                continue
            K = int(round(0.5 * (fut["bid"][j] + fut["ask"][j]) / 50.0) * 50)
            # the pair nearest the synthetic forward: re-centre once using parity at t0
            m = mids(K, t0)
            if m is not None:
                K2 = int(round((K + m[0] - m[1]) / 50.0) * 50)
                if K2 != K and mids(K2, t0) is not None:
                    K = K2
            r[w] = measure(d, e, K, lambda hh, K=K: mids(K, hh), t0, t1)
        rows.append(r)
    return rows


def gl_rows():
    raw = gl._cache("devall", gl.build_dev)
    smp = gl.Sample("ALL", raw, gl.DEV_LO, gl.TEST_HI)
    rows = []
    for d in smp.days:
        s = smp.s[d]
        if s["day"] == s["expiry"]:
            continue
        r = {"day": d, "expiry": s["expiry"], "dte": dte_bucket(d, s["expiry"])}
        for w, (t0, t1) in WINDOWS.items():
            i0 = minute(t0)
            K = gl.atm(smp, s, i0)

            def mids(hh, K=K, s=s):
                i = minute(hh)
                c, p = gl.opx(s, K, "CE", i, look=1), gl.opx(s, K, "PE", i, look=1)
                return None if c is None or p is None else (c, p)
            r[w] = measure(d, s["expiry"], K, mids, t0, t1)
        rows.append(r)
    return rows


def main():
    if OUT.exists():
        raise SystemExit("SN361 is run once")
    res = {}
    for name, rows in (("archive", archive_rows()), ("gl", gl_rows())):
        res[name] = {"all": summarize(rows)}
        for b in ("1", "2-3", "4+"):
            res[name][f"dte {b}"] = summarize([r for r in rows if r["dte"] == b])
        if name == "gl":
            for y in ("2022", "2023", "2024", "2025", "2026"):
                res[name][y] = summarize([r for r in rows if r["day"][:4] == y])
        print(name, json.dumps(res[name]["all"]), flush=True)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
