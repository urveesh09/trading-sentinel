"""SN254 - the old gap-day buyers, frozen, on both exams, once (PLAN.md). Exactly SN196's conventions:
  SN95-L - the 10:00 ATM straddle when R_today at 10:00 >= the development 80th percentile (a fixed number from 2023 -
           Aug 2026, recomputed here and checked against SN196's stored value), premium <= Rs 15k, held inside Rs 3,000
           to 15:10; on proxy-empty days (yesterday's daily ADX(14) < 30) and on all days;
  SN171  - HAR beta from all development (SN171's saved fit); forecast / implied >= 1.1 -> the 1-OTM strangle (Rs 15k,
           room Rs 3,000) and the ATM straddle (Rs 30k, room Rs 6,000), held to 15:10. EXAM-N only (NIFTY code).
EXAM-N runs the original NIFTY code on SN01-format sessions. EXAM-S runs an instrument-aware port of SN95-L whose parity
with the original is checked on every EXAM-N session first (the port must match to the rupee, or EXAM-S is not scored).
Matched null (SN196): as many random scope days with the same structure, 2,000 draws; Rs 400 per leg; 1 minute late.
SN126-L is not portable (its own burst engine) and is recorded as such."""
from __future__ import annotations

import bisect
import json
import math
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FNO / "2026-11-13-sn186"))
import gl  # noqa: E402
import pe  # noqa: E402

pw, p3, pa, pb, C, M = pe.pw, pe.p3, pe.pa, pe.pb, pe.C, pe.M
SN196 = json.loads((FNO / "2026-11-13-sn186/results-sn196.json").read_text(encoding="utf-8"))
F171 = pickle.loads((FNO / "2026-11-13-sn161/_local/sn171_final.pkl").read_bytes())


def null(pool, k, draws=2000, seed=254):
    rng = np.random.default_rng(seed)
    if not pool or not k:
        return 0, 0
    t = [float(np.sum(rng.choice(pool, min(k, len(pool)), replace=False))) for _ in range(draws)]
    return round(float(np.mean(t))), round(float(np.percentile(t, 95)))


# ---- the instrument-aware port of SN95-L (sigma_imp, r_today, pa.path, pb.net) ---------------------------------
def _mark(s, k, o, i, stale=5):
    a = s["options"].get((k, o))
    if a is None:
        return None
    col = a[3][: i + 1]
    ok = np.flatnonzero(~np.isnan(col))
    if not len(ok) or i - ok[-1] > stale:
        return None
    return float(col[ok[-1]])


def p_sigma(smp, s, i):
    st = smp.mk["step"]
    c = float(s["index"][3][i])
    K = int(round(c / st) * st)
    ce, pe_ = _mark(s, K, "CE", i), _mark(s, K, "PE", i)
    if ce is None or pe_ is None:
        return None
    F = float(s["future"][3][i])
    n = smp.sessions_until(s["day"], s["expiry"])
    tau = (375 - (i + 1)) + 375.0 * n + C.OVERNIGHT_MIN * n
    if tau <= 0:
        return None
    return (ce + pe_) / (0.7979 * F * math.sqrt(tau))


def p_rtoday(smp, s, i):
    si = p_sigma(smp, s, i)
    if si is None or i < 20:
        return None
    c = np.asarray(s["index"][3][5: i + 1], dtype=np.float64)
    r = np.diff(np.log(c))
    return float(np.std(r)) / si if len(r) > 5 else None


def p_path(smp, s, i, stress=205.0, end=C.FLAT):
    mk, st = smp.mk, smp.mk["step"]
    K = int(round(float(s["index"][3][i]) / st) * st)
    legs = []
    for o in ("CE", "PE"):
        a = s["options"].get((K, o))
        if a is None or np.isnan(a[3][i]):
            return None
        legs.append((a, gl.wk.ask(mk, float(a[3][i]))))
    qty = mk["lot"]
    vals = np.full(end + 1, np.nan)
    marks = []
    for a, _px in legs:
        m = a[3].astype(np.float64).copy()
        last = np.nan
        for j in range(len(m)):
            if np.isnan(m[j]):
                m[j] = last
            else:
                last = m[j]
        marks.append(m)
    for j in range(i + 1, end + 1):
        tot = fees = 0.0
        ok = True
        for (a, px), m in zip(legs, marks):
            x = float(m[j])
            if np.isnan(x):
                ok = False
                break
            b = gl.wk.bid(mk, x)
            tot += (b - px) * qty
            fees += gl.wk.charges(px, b, qty, mk["exch"])
        if ok:
            vals[j] = tot - fees - stress * 2
    return [px for _a, px in legs], sum(px for _a, px in legs) * qty, vals


def p_net(got, i=45, room=3000.0, ceiling=15000.0):
    if got is None or got[1] > ceiling:
        return 0.0
    return pa.settle(got[2], i, room, fallback=-205.0 * 2)[0]


def run_scope(name, days_all, empty, fn, pool_fn):
    row = {}
    for scope, days in (("proxy-empty days", empty), ("all days", set(days_all))):
        dn = {d: fn(d) for d in days_all if d in days}
        dn = {d: n for d, n in dn.items() if n is not None and n != 0}
        pool = [n for n in (pool_fn(d) for d in days_all if d in days) if n is not None and n != 0]
        nm, n95 = null(pool, len(dn))
        s400 = sum((fn(d, stress=400.0) or 0.0) for d in dn)
        late = sum((fn(d, late=1) or 0.0) for d in dn)
        r = {"net": round(sum(dn.values())), "trades": len(dn), "wins": sum(v > 0 for v in dn.values()),
             "worst": round(min(dn.values())) if dn else 0, "null_mean": nm, "null_p95": n95, "stress_400": round(s400),
             "late_1": round(late), "by_year": {}, "days": sorted(dn)}
        for d, v in dn.items():
            r["by_year"][d[:4]] = r["by_year"].get(d[:4], 0) + round(v)
        r["PASS"] = bool(r["net"] > 0 and r["net"] > n95 and s400 > 0 and late > 0)
        row[scope] = r
        print("SN254", name, scope, {k: v for k, v in r.items() if k != "days"}, flush=True)
    return row


if __name__ == "__main__":
    out_path = HERE / "results-sn254.json"
    if out_path.exists():
        raise SystemExit("SN254 is scored once")
    devS = pw.dev_sessions()
    rt_dev = [r for r in (C.r_today(S, 45) for S in devS) if r is not None]
    thr = float(np.quantile(rt_dev, 0.8))
    assert abs(round(thr, 4) - SN196["sn95l_threshold_dev_p80"]) < 1e-9, (thr, SN196["sn95l_threshold_dev_p80"])
    res = {"sn95l_threshold_dev_p80": round(thr, 4), "exams": {}, "not_portable": ["SN126-L (its own burst engine)",
                                                                                  "SN171 on SENSEX (p3.structure is NIFTY-only; not ported)"]}
    # ---- EXAM-N: the original code
    gl.SEALED["EXAMN"] = True
    smp = gl.sample("EXAMN")
    for d in smp.cal:
        if d not in C._CAL:
            bisect.insort(C._CAL, d)
    SS = {d: M.Session(smp.s[d]) for d in smp.days}
    empty = {d for d in smp.days if smp.adx(d) is not None and smp.adx(d) < 30}

    def o95(d, stress=205.0, late=0):
        S = SS[d]
        r = C.r_today(S, 45)
        if r is None or r < thr:
            return None
        got = pa.path(S, 45 + late, leg_stress=stress)
        return None if got is None else pb.net(got, i=45 + late, room=3000.0, ceiling=15000.0)

    def o95_pool(d):
        g = pa.path(SS[d], 45)
        return None if g is None else pb.net(g, i=45, room=3000.0, ceiling=15000.0)

    # port parity on EXAM-N before anything is scored
    mism = 0
    for d in smp.days:
        s = smp.s[d]
        a = o95(d)
        rp = p_rtoday(smp, s, 45)
        b = None if (rp is None or rp < thr) else p_net(p_path(smp, s, 45), 45)
        g1, g2 = pa.path(SS[d], 45), p_path(smp, s, 45)
        pool_a = None if g1 is None else pb.net(g1, i=45, room=3000.0, ceiling=15000.0)
        pool_b = None if g2 is None else p_net(g2, 45)
        if (a is None) != (b is None) or (a is not None and abs(a - b) > 0.01) or (pool_a is None) != (pool_b is None) or \
                (pool_a is not None and abs(pool_a - pool_b) > 0.01):
            mism += 1
    res["port_parity_examn"] = {"sessions": len(smp.days), "mismatches": mism}
    print("SN254 port parity on EXAM-N", res["port_parity_examn"], flush=True)
    rowN = {"sessions": len(smp.days), "proxy_empty_days": len(empty),
            "SN95-L (Rs 15k)": run_scope("EXAM-N SN95-L", smp.days, empty, o95, o95_pool)}
    har = p3.HAR([SS[d] for d in smp.days])
    rho = {}
    for d in smp.days:
        fs, si = har.sigma(d, F171["beta"], F171["s2"]), C.sigma_imp(SS[d], p3.I1000)
        if fs and si:
            rho[d] = fs / si
    for nm, (wallet, kind, room) in (("SN171 Rs 15k strangle", (15000.0, "strangle1", 3000.0)),
                                      ("SN171 Rs 30k straddle", (30000.0, "straddle", 6000.0))):
        def f171(d, stress=205.0, late=0, wallet=wallet, kind=kind, room=room):
            if rho.get(d, 0) < 1.1:
                return None
            return p3.structure(SS[d], p3.I1000 + late, kind, wallet, room, None, stress)
        rowN[nm] = run_scope("EXAM-N " + nm, smp.days, empty, f171,
                             lambda d, wallet=wallet, kind=kind, room=room: p3.structure(SS[d], p3.I1000, kind, wallet, room))
    res["exams"]["EXAM-N"] = rowN
    # ---- EXAM-S: the port, only if parity held
    if mism == 0:
        gl.SEALED["EXAMS"] = True
        sm2 = gl.sample("EXAMS")
        empty2 = {d for d in sm2.days if sm2.adx(d) is not None and sm2.adx(d) < 30}

        def s95(d, stress=205.0, late=0):
            s = sm2.s[d]
            r = p_rtoday(sm2, s, 45)
            if r is None or r < thr:
                return None
            got = p_path(sm2, s, 45 + late, stress)
            return None if got is None else p_net(got, 45 + late)

        def s95_pool(d):
            g = p_path(sm2, sm2.s[d], 45)
            return None if g is None else p_net(g, 45)

        res["exams"]["EXAM-S"] = {"sessions": len(sm2.days), "proxy_empty_days": len(empty2),
                                  "SN95-L (Rs 15k)": run_scope("EXAM-S SN95-L", sm2.days, empty2, s95, s95_pool)}
    else:
        res["exams"]["EXAM-S"] = "not scored: the port did not match the original on EXAM-N"
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
