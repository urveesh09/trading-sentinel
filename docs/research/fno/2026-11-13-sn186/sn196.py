"""SN196 - the NIFTY 2022 exam (PLAN.md), scored once on the sealed SN195 dataset (Apr 1 - Dec 30 2022; 145 lab
sessions). No 2022 number was read before this script was frozen. Gold v5 cannot be replayed on 2022 (no N11 replay
exists), so an empty day is the causal proxy: yesterday's daily ADX(14) < 30 (Wilder, SN06's formula, on the sealed
mirror's NIFTY daily bars).
Frozen candidates (as the forward watches run them; nothing chosen here):
  SN95-L - 10:00 ATM straddle when R_today at 10:00 >= the development 80th percentile (a fixed number from 2023 -
           Aug 2026: 2022 precedes them, so no causal history exists), premium <= Rs 15k, held inside Rs 3,000;
  SN171  - HAR beta from all development (saved by SN171); forecast / implied >= 1.1 -> 1-OTM strangle Rs 15k (room
           Rs 3,000) and ATM straddle Rs 30k (room Rs 6,000), held to 15:10.
Each on proxy-empty days and on all days; matched null = as many random proxy-empty days with the same structure
(2,000 draws); Rs 400 per leg and 1 minute late. Reference: the coin-flip wage trader (Rs 1,000 / -Rs 1,000, 1 lot)
on 2022. Also every SN187-SN193 final variant on proxy-empty days, for the record (all failed development)."""
from __future__ import annotations

import bisect
import json
import pickle
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pe  # noqa: E402
import sn187  # noqa: E402
import sn188  # noqa: E402
import sn189  # noqa: E402
import sn195  # noqa: E402

pw, p3, pa, pb, C, M = pe.pw, pe.p3, pe.pa, pe.pb, pe.C, pe.M
SN161_LOCAL = HERE.parent / "2026-11-13-sn161" / "_local"


def daily_adx_2022():
    con = sqlite3.connect(f"file:{sn195.MIRROR.as_posix()}?mode=ro", uri=True)
    bars = con.execute("SELECT substr(datetime,1,10), open, high, low, close FROM candles WHERE kind='daily' AND "
                       "underlying='NIFTY' ORDER BY datetime").fetchall()
    con.close()
    out, n = {}, 14
    tr_s = pdm_s = mdm_s = adx = None
    dx = []
    for k in range(1, len(bars)):
        _, _, h, l, c = bars[k]
        _, _, ph, pl, pc = bars[k - 1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        up, dn = h - ph, pl - l
        pdm = up if up > dn and up > 0 else 0.0
        mdm = dn if dn > up and dn > 0 else 0.0
        if tr_s is None:
            tr_s, pdm_s, mdm_s = tr, pdm, mdm
        else:
            tr_s, pdm_s, mdm_s = tr_s - tr_s / n + tr, pdm_s - pdm_s / n + pdm, mdm_s - mdm_s / n + mdm
        pdi, mdi = 100 * pdm_s / tr_s, 100 * mdm_s / tr_s
        dx.append(100 * abs(pdi - mdi) / max(pdi + mdi, 1e-9))
        if len(dx) == n:
            adx = sum(dx) / n
        elif adx is not None:
            adx = (adx * (n - 1) + dx[-1]) / n
        if k + 1 < len(bars) and k >= 2 * n:
            out[bars[k + 1][0]] = adx
    return out


def sessions_2022():
    C.years()                                       # the lab's years and calendar first
    sys.path.insert(0, str(pe.HERE.parent / "2026-11-12-sn01"))
    import sn01_data as D
    D.DATASETS["2022"] = sn195.DATASET
    built = D.build_year("2022")["sessions"]
    con = sqlite3.connect(f"file:{(sn195.DATASET / 'breeze.sqlite').as_posix()}?mode=ro", uri=True)
    days = {r[0] for r in con.execute("SELECT DISTINCT substr(datetime,1,10) FROM candles WHERE kind='index'")}
    con.close()
    for d in sorted(days):
        if d not in C._CAL:
            bisect.insort(C._CAL, d)
    return [M.Session(built[d]) for d in sorted(built)]


def null(pool, k, draws=2000, seed=196):
    rng = np.random.default_rng(seed)
    if not pool or not k:
        return 0, 0
    t = [float(np.sum(rng.choice(pool, min(k, len(pool)), replace=False))) for _ in range(draws)]
    return round(float(np.mean(t))), round(float(np.percentile(t, 95)))


if __name__ == "__main__":
    out_path = HERE / "results-sn196.json"
    if out_path.exists():
        raise SystemExit("SN196 is scored once")
    devS = pw.dev_sessions()
    rt_dev = [r for r in (C.r_today(S, 45) for S in devS) if r is not None]
    thr95 = float(np.quantile(rt_dev, 0.8))
    f171 = pickle.loads((SN161_LOCAL / "sn171_final.pkl").read_bytes())
    ss = sessions_2022()
    adx = daily_adx_2022()
    empty = {S.day for S in ss if adx.get(S.day) is not None and adx[S.day] < 30}
    har = p3.HAR(ss)
    rho = {}
    for S in ss:
        fs, si = har.sigma(S.day, f171["beta"], f171["s2"]), C.sigma_imp(S, p3.I1000)
        if fs and si:
            rho[S.day] = fs / si
    res = {"sessions": len(ss), "proxy_empty_days": len(empty), "adx_days": len(adx), "sn95l_threshold_dev_p80": round(thr95, 4),
           "har_days": len(har.rows), "candidates": {}}

    def sn95l(S, stress=205.0, late=0):
        r = C.r_today(S, 45)
        if r is None or r < thr95:
            return None
        got = pa.path(S, 45 + late, leg_stress=stress)
        return None if got is None else pb.net(got, i=45 + late, room=3000.0, ceiling=15000.0)

    def sn171(S, wallet, kind, room, stress=205.0, late=0):
        if rho.get(S.day, 0) < 1.1:
            return None
        return p3.structure(S, p3.I1000 + late, kind, wallet, room, None, stress)

    cands = {"SN95-L (Rs 15k)": lambda S, **k: sn95l(S, **k),
             "SN171 Rs 15k strangle": lambda S, **k: sn171(S, 15000.0, "strangle1", 3000.0, **k),
             "SN171 Rs 30k straddle": lambda S, **k: sn171(S, 30000.0, "straddle", 6000.0, **k)}
    pools = {"SN95-L (Rs 15k)": lambda S: (lambda g: None if g is None else pb.net(g, i=45, room=3000.0, ceiling=15000.0))(pa.path(S, 45)),
             "SN171 Rs 15k strangle": lambda S: p3.structure(S, p3.I1000, "strangle1", 15000.0, 3000.0),
             "SN171 Rs 30k straddle": lambda S: p3.structure(S, p3.I1000, "straddle", 30000.0, 6000.0)}
    for name, fn in cands.items():
        row = {}
        for scope, days in (("proxy-empty days", empty), ("all days", {S.day for S in ss})):
            dn = {S.day: fn(S) for S in ss if S.day in days}
            dn = {d: n for d, n in dn.items() if n is not None and n != 0}
            pool = [n for n in (pools[name](S) for S in ss if S.day in days) if n is not None and n != 0]
            nm, n95 = null(pool, len(dn))
            s400 = sum((fn(S, stress=400.0) or 0.0) for S in ss if S.day in dn)
            late = sum((fn(S, late=1) or 0.0) for S in ss if S.day in dn)
            row[scope] = {"net": round(sum(dn.values())), "trades": len(dn), "wins": sum(v > 0 for v in dn.values()),
                          "worst": round(min(dn.values())) if dn else 0, "null_mean": nm, "null_p95": n95,
                          "stress_400": round(s400), "late_1": round(late), "days": sorted(dn)}
            row[scope]["PASS"] = bool(row[scope]["net"] > 0 and row[scope]["net"] > n95 and s400 > 0 and late > 0)
        res["candidates"][name] = row
        print(f"SN196 {name}: " + json.dumps({k: {x: y for x, y in v.items() if x != 'days'} for k, v in row.items()}, default=float), flush=True)
    coin = []
    for k in range(50):
        dn = {}
        for S in ss:
            n, tr = pw.play(S, pw.random_picker(pw.seed_of(S.day, k, 196)), 1e9, 1000.0, 1000.0, 1, day_limit=2000.0, max_lots=1)
            if tr:
                dn[S.day] = n
        coin.append(sum(dn.values()))
    res["coin_flip_rs1000_1lot_2022"] = {"mean": round(float(np.mean(coin))), "p5": round(float(np.percentile(coin, 5))),
                                         "p95": round(float(np.percentile(coin, 95)))}
    rec = {}
    E = [S for S in ss if S.day in empty]
    rec["SN187 pair 10:00 goal 1500 stop 2000"] = round(sum((sn187.play(S, 45, ("pair", 1500.0, 2000.0)) or 0.0) for S in E))
    rec["SN188 goal 1000 stop 1000 (all proxy-empty days, no hot filter)"] = round(sum((sn188.day(S, 1000.0, 1000.0) or 0.0) for S in E))
    rec["SN189 fly goal 1500 stop 3000 (rho < 0.75)"] = round(sum((sn189.fly(S, 1500.0, 3000.0) or 0.0) for S in E if rho.get(S.day, 9) < 0.75))
    res["record_failed_development"] = rec
    print("SN196 reference", json.dumps({"coin": res["coin_flip_rs1000_1lot_2022"], "record": rec}, default=float), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
