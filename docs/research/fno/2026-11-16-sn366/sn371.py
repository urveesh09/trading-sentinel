"""SN371: does the opening forecast outlive the premium reset? (PLAN.md section 1, frozen at 3740b461 before any number.)

Samples (seen, development): GAP = gl DEV + TEST NIFTY sessions Apr 2022 - Oct 28, 2026 (non-expiry), direction = sign of
the index's 09:15 open / previous session close - 1 when |gap| >= 0.10%; AUCTION = the same sessions Dec 8, 2025 - Oct 28,
2026 with SN353's auction gap g (sn353b.auctions), direction = sign(g).
Decision at 10:15 (minute 60). Traveled T = index(10:15) / index(09:16) - 1, signed by the direction; buckets < -0.2%,
-0.2..+0.2%, +0.2..+0.4%; abstain when T >= +0.4% (the cap). IV state: NORMALIZED when the ATM straddle's Black-76 IV at
10:15 <= its IV at 09:16 (each at its own ATM strike, synthetic forward, sn361's functions), else NOT.
Trade: one lot of the front-weekly ATM option on the direction's side at 10:15 (gl model), Rs 3,000 stop, held 60 minutes
(primary), 20 minutes and to 14:30 (diagnostics), at stress 0 / 205 / 400.
Controls on the same sessions: COIN (seeded side at 10:15), OPP (the other side at 10:15), EARLY (the direction's side
at 09:16 held to 11:15).
Decomposition (60 minutes, stress 0): index points moved after 10:15 in the direction; delta part = Black-76 delta at
10:15 x index change x lot; residual = gross - delta part (theta, IV, spread, charges).
Archive (real quotes, Sep 10 - Oct 28 sessions in the sample): walked ask at the 10:15 snapshot, walked bid in the exit
minute or the one before, the stop on each minute's walked bid.
Advance (forward freeze only): 60-minute net at Rs 205 > 0 on GAP (>= 200 trades, >= 3 of 5 years positive) and on
AUCTION (>= 60 trades), both above COIN, and the archive the same sign.
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
for p in ("2026-11-16-sn251", "2026-11-13-sn101", "2026-11-16-sn351"):
    sys.path.insert(0, str(FNO / p))
import gl  # noqa: E402
import qa  # noqa: E402
import sn353b  # noqa: E402
import sn361  # noqa: E402

qa.EXPORT = sn353b.qa.EXPORT
OUT = HERE / "results-sn371.json"
I16, I10, STOP, LOT = 1, 60, 3000.0, 65
HOLDS = {"20m": 80, "60m": 120, "to1430": 315}
STRESSES = (0.0, 205.0, 400.0)


def bucket(T):
    return "lt-0.2" if T < -0.002 else "-0.2..0.2" if T < 0.002 else "0.2..0.4" if T < 0.004 else "capped"


def atm_iv(smp, s, i):
    k = gl.atm(smp, s, i)
    c, p = gl.opx(s, k, "CE", i, look=1), gl.opx(s, k, "PE", i, look=1)
    if c is None or p is None:
        return None
    hh = f"{(555 + i) // 60:02d}:{(555 + i) % 60:02d}"
    F = k + c - p
    if F <= 0:
        return None
    return sn361.iv(c + p, F, k, sn361.years_to(s["day"], s["expiry"], hh))


def trade(smp, s, side, i, exits):
    k = gl.atm(smp, s, i)
    out = {"strike": k}
    for st in STRESSES:
        pos = gl.Pos(smp, s, [(k, side, +1)], i, lots=1, stress=st)
        if not pos.ok:
            return None
        out[int(st)] = {}
        for name, j in exits.items():
            net, jj, why = gl.walk(pos, s, i, min(j, gl.NM - 1), room=STOP)
            out[int(st)][name] = None if net is None else round(net, 2)
    return out


def decompose(smp, s, side, sgn):
    k = gl.atm(smp, s, I10)
    p0, p1 = gl.opx(s, k, side, I10, look=1), gl.opx(s, k, side, 120, look=10)
    sig = atm_iv(smp, s, I10)
    i0, i1 = float(s["index"][3][I10]), float(s["index"][3][120])
    if p0 is None or p1 is None or sig is None or np.isnan(i0) or np.isnan(i1):
        return None
    T = sn361.years_to(s["day"], s["expiry"], "10:15")
    v = sig * math.sqrt(T)
    d1 = (math.log(i0 / k) + 0.5 * v * v) / v
    delta = sn361.N(d1) if side == "CE" else sn361.N(d1) - 1.0
    return {"points_in_dir": round((i1 - i0) * sgn, 2), "delta_part": round(delta * (i1 - i0) * LOT, 1), "mid_change": round((p1 - p0) * LOT, 1)}


def arch_trade(q, expiry, strike, side, i0, exit_j, stress):
    rec = q["opt"].get(("NIFTY", expiry, strike, side))
    if rec is None or not rec["usable"][i0]:
        return None
    e = qa.walk_cost(rec["askp"][:, i0], rec["askq"][:, i0], LOT)
    if e is None:
        return None
    last = None
    for j in range(i0 + 1, exit_j + 1):
        if not rec["usable"][j]:
            continue
        b = qa.walk_cost(rec["bidp"][:, j], rec["bidq"][:, j], LOT)
        if b is None:
            continue
        v = (b - e) * LOT - gl.wk.charges(e, b, LOT, "NFO") - stress
        if v <= -STOP:
            return round(v, 2)
        if j >= exit_j - 1:
            last = round(v, 2)
    return last


def run_sample(smp, days, dirs, arch):
    rows = []
    for d in days:
        if d not in dirs:
            continue
        s = smp.s[d]
        sgn = dirs[d]
        idx = s["index"][3]
        if np.isnan(idx[I16]) or np.isnan(idx[I10]):
            continue
        T = (float(idx[I10]) / float(idx[I16]) - 1.0) * sgn
        b = bucket(T)
        side = "CE" if sgn > 0 else "PE"
        opp = "PE" if side == "CE" else "CE"
        iv16, iv10 = atm_iv(smp, s, I16), atm_iv(smp, s, I10)
        state = None if iv16 is None or iv10 is None else ("NORMALIZED" if iv10 <= iv16 else "NOT")
        r = {"day": d, "dir": sgn, "T": round(T, 5), "bucket": b, "iv_state": state, "year": d[:4]}
        if b != "capped":
            r["MAIN"] = trade(smp, s, side, I10, HOLDS)
            r["OPP"] = trade(smp, s, opp, I10, HOLDS)
            r["COIN"] = trade(smp, s, random.Random(f"sn371-{d}").choice(("CE", "PE")), I10, HOLDS)
            r["EARLY"] = trade(smp, s, side, I16, {"to1115": 120})
            r["decomp"] = decompose(smp, s, side, sgn)
            if d in arch:
                q = qa.load(d)
                k = gl.atm(smp, s, I10)
                r["ARCH"] = {int(st): arch_trade(q, s["expiry"], k, side, I10, 120, st) for st in STRESSES}
                r["ARCH_COIN"] = {int(st): arch_trade(q, s["expiry"], k, random.Random(f"sn371-{d}").choice(("CE", "PE")), I10, 120, st) for st in STRESSES}
        rows.append(r)
    return rows


def mean_of(rows, arm, st, h):
    xs = [r[arm][st][h] for r in rows if r.get(arm) and r[arm][st].get(h) is not None]
    return (round(float(np.mean(xs)), 1), len(xs)) if xs else (None, 0)


def summarize(rows):
    out = {"sessions": len(rows), "capped": sum(r["bucket"] == "capped" for r in rows)}
    groups = {"ALL": [r for r in rows if r.get("MAIN")]}
    for b in ("lt-0.2", "-0.2..0.2", "0.2..0.4"):
        groups[f"T {b}"] = [r for r in groups["ALL"] if r["bucket"] == b]
    for st_ in ("NORMALIZED", "NOT"):
        groups[f"IV {st_}"] = [r for r in groups["ALL"] if r["iv_state"] == st_]
    for g, rs in groups.items():
        row = {}
        for arm in ("MAIN", "OPP", "COIN"):
            for st in (0, 205, 400):
                for h in HOLDS:
                    m, n = mean_of(rs, arm, st, h)
                    row[f"{arm} {h}@{st}"] = m
        row["n"] = len(rs)
        e = [r["EARLY"][205]["to1115"] for r in rs if r.get("EARLY") and r["EARLY"][205]["to1115"] is not None]
        row["EARLY to1115@205"] = round(float(np.mean(e)), 1) if e else None
        dc = [r["decomp"] for r in rs if r.get("decomp")]
        if dc:
            row["decomp"] = {k: round(float(np.mean([x[k] for x in dc])), 1) for k in ("points_in_dir", "delta_part", "mid_change")}
        out[g] = row
    years = {}
    for r in groups["ALL"]:
        x = r["MAIN"][205]["60m"]
        if x is not None:
            years.setdefault(r["year"], []).append(x)
    out["by_year_60m@205"] = {y: {"n": len(v), "per_trade": round(float(np.mean(v)), 1), "total": round(float(np.sum(v)))} for y, v in sorted(years.items())}
    ar = [r for r in groups["ALL"] if r.get("ARCH")]
    for st in (0, 205, 400):
        xs = [r["ARCH"][st] for r in ar if r["ARCH"][st] is not None]
        cs = [r["ARCH_COIN"][st] for r in ar if r["ARCH_COIN"][st] is not None]
        out[f"ARCH 60m@{st}"] = {"n": len(xs), "per_trade": round(float(np.mean(xs)), 1) if xs else None,
                                 "coin_per_trade": round(float(np.mean(cs)), 1) if cs else None}
    return out


def main():
    if OUT.exists():
        raise SystemExit("SN371 is run once")
    raw = gl._cache("devall", gl.build_dev)
    smp = gl.Sample("ALL", raw, gl.DEV_LO, gl.TEST_HI)
    days = [d for d in smp.days if smp.s[d]["day"] != smp.s[d]["expiry"]]
    arch = {d for d in qa.days() if d <= "2026-10-28"}
    gap = {}
    for d in days:
        pb = smp.prev_bar(d)
        o = smp.s[d]["index"][0][0]
        if pb is None or np.isnan(o):
            continue
        g = float(o) / float(pb[3]) - 1.0
        if abs(g) >= 0.001:
            gap[d] = 1 if g > 0 else -1
    au = sn353b.auctions([d for d in days if sn353b.LO <= d < sn353b.HI])
    auc = {d: (1 if a["g"] > 0 else -1) for d, a in au.items() if a["g"] != 0}
    res = {"GAP": summarize(run_sample(smp, days, gap, arch)), "AUCTION": summarize(run_sample(smp, days, auc, arch))}
    g, a = res["GAP"]["ALL"], res["AUCTION"]["ALL"]
    yrs = res["GAP"]["by_year_60m@205"]
    adv = (g["MAIN 60m@205"] is not None and g["MAIN 60m@205"] > 0 and g["n"] >= 200 and sum(v["per_trade"] > 0 for v in yrs.values()) >= 3
           and a["MAIN 60m@205"] is not None and a["MAIN 60m@205"] > 0 and a["n"] >= 60
           and g["MAIN 60m@205"] > (g["COIN 60m@205"] or -1e9) and a["MAIN 60m@205"] > (a["COIN 60m@205"] or -1e9)
           and (res["GAP"]["ARCH 60m@205"]["per_trade"] or -1) > 0)
    res["advance"] = bool(adv)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    for k in ("GAP", "AUCTION"):
        for grp, row in res[k].items():
            if isinstance(row, dict) and "n" in row:
                print(k, grp, json.dumps({x: row.get(x) for x in ("n", "MAIN 60m@0", "MAIN 60m@205", "COIN 60m@205", "OPP 60m@205", "MAIN 20m@0", "MAIN to1430@205", "EARLY to1115@205", "decomp")}), flush=True)
        print(k, "years", json.dumps(res[k]["by_year_60m@205"]), "arch", json.dumps(res[k]["ARCH 60m@205"]), flush=True)
    print("advance", res["advance"])


if __name__ == "__main__":
    main()
