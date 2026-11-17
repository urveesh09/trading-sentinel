"""SN397: what does "cheap" detect? (PLAN.md section 1, frozen at 00693405; details fixed here before any SN397 number.)

Cohort: the HONEST AUCTION sessions (op.py; g != 0) with a jump reading. CHEAP = fw9's frozen cutoff on the HONEST jump
(SN396: the moving tercile is reported beside it). Legs at 09:16:00 (HONEST fill = the 09:15 close), ITM 2 then 1 under the
cash rule, 60 minutes, Rs 3,000 stop, Rs 205 / 400, skips 0:
  four cells  CHEAP / OTHER x SAME (the auction side) / OPP (the other side, same depth rule)
  separation  (a) direction: signed index move 09:16 -> 10:16 (points, close 0 -> close 60) in the auction direction;
              (b) repricing: each filled leg's mid change at stress 0 split into delta x dF + vega x dIV + theta + residual
                  (sn383's Black-76 on the synthetic forward, entry 09:16 / exit 10:16) and the costs paid;
              (c) affordability: the admissible (filled) share;
              plus the ATM straddle IV at entry and the time-value share of the bought leg.
  strata      sessions to expiry 1-2 vs >= 3; after a weekend / holiday vs not; auction source; |g| below / above the
              cohort median. Per stratum: CHEAP - OTHER (SAME side), and the size-weighted average over strata.
  regression  per-session SAME net (filled; skips excluded) on CHEAP + the four strata dummies (+ intercept), OLS with
              HC1 standard errors, at Rs 205 and Rs 400; and with the continuous jump in place of CHEAP.
White reality check (the opening family as it was searched, SN376 - SN394, ORIGINAL clock, Rs 400): each rule's
per-session series over all 171 AUCTION sessions (net where the rule trades and fills, else 0); V = max mean;
stationary bootstrap (2,000 draws, mean block 5 sessions, seed 397) of V* = max (mean* - mean); p = share V* >= V. The
same family on the HONEST clock. Rules (24): all; match / fallback; pre / post; match-pre / match-post; CHEAP / MID /
RICH / skip-RICH (moving); CHEAP fixed; gap < / >= 0.2%; HIGH / LOW match volume (SN393); BUILDING / FADING (SN391);
20-minute hold; the ATM leg; CHEAP x {pre, post, match, fallback} (SN394b). Not reconstructed: SN384's exit (-14 vs the
hold, near-identical) and SN385 (closed on coverage, never scored) - so the family is a lower bound.
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import math
import sqlite3
import statistics
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import op  # noqa: E402
import sn396  # noqa: E402

sys.path.insert(0, str(op.FNO / "2026-11-16-sn381"))
import sn383_394 as X  # noqa: E402

gl, V = op.gl, op.V
OUT = HERE / "results-sn397.json"
HIST = op.sn353b.HIST


def leg_row(smp, s, side, stress):
    pos, dep, state, jf = op.leg(smp, s, side, 1, "HONEST", stress)
    if pos is None:
        return {"state": state}
    net, _j, _w = gl.walk(pos, s, jf, jf + 60, room=op.STOP)
    return {"state": state, "net": None if net is None else round(net, 2), "pos": pos, "depth": dep}


def decompose(smp, s, pos, side):
    F0, F1 = X.synthetic(smp, s, 0), X.synthetic(smp, s, 60)
    if F0 is None or F1 is None:
        return None
    T0, T1 = op.sn361.years_to(s["day"], s["expiry"], "09:16"), op.sn361.years_to(s["day"], s["expiry"], "10:16")
    k = pos.legs[0][0]
    m0, m1 = gl.opx(s, k, side, 0, look=1), gl.opx(s, k, side, 60, look=10)
    if m0 is None or m1 is None:
        return None
    s0, s1 = X.leg_iv(m0, F0, k, T0, side), X.leg_iv(m1, F1, k, T1, side)
    if s0 is None or s1 is None:
        return None
    dl, vg, th = X.greeks(F0, k, T0, s0, side)
    dmid = (m1 - m0) * op.LOT
    dp, vp, tp = dl * (F1 - F0) * op.LOT, vg * (s1 - s0) * op.LOT, -abs(th) * (T0 - T1) * op.LOT
    intrinsic = max(0.0, (F0 - k) if side == "CE" else (k - F0))
    return {"dmid": dmid, "delta": dp, "vega": vp, "theta": tp, "resid": dmid - dp - vp - tp, "iv0": s0, "div": s1 - s0,
            "cost": (pos.fills[0] - m0) * op.LOT + op.wk.charges(pos.fills[0], 0.0, op.LOT, "NFO"), "tv_share": (m0 - intrinsic) / m0 if m0 > 0 else None,
            "entry_delta": dl}


def cell_summary(rows, key):
    out = {"n": len(rows), "fills": sum(r[key]["state"] == "FILLED" for r in rows)}
    out["admissible_share"] = round(out["fills"] / len(rows), 3) if rows else None
    for st in (205, 400):
        xs = [(r[key].get(f"net{st}") or 0.0) if r[key]["state"] == "FILLED" else 0.0 for r in rows]
        out[f"per_session@{st}"] = op.per_session(xs)
        out[f"without_best@{st}"] = op.without_best(xs) if xs else None
    dec = [r[key]["dec"] for r in rows if r[key].get("dec")]
    if dec:
        out["decomposition_mean"] = {k: round(float(np.mean([d[k] for d in dec if d[k] is not None])), 2 if k in ("iv0", "div", "tv_share", "entry_delta") else 1)
                                     for k in ("dmid", "delta", "vega", "theta", "resid", "cost", "iv0", "div", "tv_share", "entry_delta")}
        out["decomposition_n"] = len(dec)
    out["follow_through_pts_mean"] = round(float(np.mean([r["follow"] for r in rows if r["follow"] is not None])), 1) if rows else None
    out["entry_straddle_iv_mean"] = round(float(np.mean([r["iv_open"] for r in rows if r["iv_open"] is not None])), 4) if rows else None
    return out


def ols(y, X_, names):
    y, X_ = np.asarray(y, float), np.column_stack([np.ones(len(y))] + [np.asarray(c, float) for c in X_])
    b, *_ = np.linalg.lstsq(X_, y, rcond=None)
    e = y - X_ @ b
    n, k = X_.shape
    XtX = np.linalg.inv(X_.T @ X_)
    cov = XtX @ (X_.T * (e ** 2)) @ X_ @ XtX * n / (n - k)
    se = np.sqrt(np.diag(cov))
    return {nm: {"coef": round(float(b[i]), 1), "se": round(float(se[i]), 1), "t": round(float(b[i] / se[i]), 2) if se[i] > 0 else None}
            for i, nm in enumerate(["intercept"] + names)} | {"n": n}


def white_rc(series, draws=2000, block=5, seed=397):
    names = list(series)
    M = np.array([series[k] for k in names])            # rules x sessions
    n = M.shape[1]
    means = M.mean(1)
    Vobs = float(means.max())
    rng = np.random.default_rng(seed)
    p = 1.0 / block
    hits = 0
    for _ in range(draws):
        idx = np.empty(n, int)
        idx[0] = rng.integers(n)
        for t in range(1, n):
            idx[t] = rng.integers(n) if rng.random() < p else (idx[t - 1] + 1) % n
        Vb = float((M[:, idx].mean(1) - means).max())
        hits += Vb >= Vobs
    best = names[int(means.argmax())]
    return {"rules": len(names), "best": best, "best_per_session": round(Vobs, 1), "p_white": round(hits / draws, 4),
            "means": {k: round(float(m), 1) for k, m in zip(names, means)}}


def family(smp, au, rows, jm_clock):
    """The searched opening family on the given clock's sn396.score rows: per-session series over all sessions."""
    con = sqlite3.connect(f"file:{HIST.as_posix()}?mode=ro", uri=True, timeout=60)
    L = op.labels(jm_clock, False)
    Lf = op.labels(jm_clock, True)
    vols, hist = {}, []
    for r in sorted(rows, key=lambda r: r["day"]):
        a = au[r["day"]]
        if a["how"] != "match_row":
            continue
        v = con.execute("SELECT volume FROM candles WHERE kind='future' AND underlying='NIFTY' AND expiry=? AND strike=0 AND opt='' AND interval='1minute' "
                        "AND datetime>=? AND datetime<? AND oi>0 ORDER BY datetime LIMIT 1", (a["expiry"], r["day"] + " 09:00", r["day"] + " 09:15")).fetchone()
        mv = float(v[0]) if v and v[0] is not None else None
        if mv is not None and len(hist) >= 20:
            vols[r["day"]] = "HIGH" if mv > statistics.median(hist[-20:]) else "LOW"
        if mv is not None:
            hist.append(mv)
    drift = {}
    for r in rows:
        a = au[r["day"]]
        if r["period"] == "post" and a["how"] == "match_row":
            x = con.execute("SELECT close FROM candles WHERE kind='future' AND underlying='NIFTY' AND expiry=? AND strike=0 AND opt='' AND interval='1minute' AND datetime=?",
                            (a["expiry"], r["day"] + " 09:05:00")).fetchone()
            if x:
                drift[r["day"]] = (a["A"] - float(x[0])) * (1 if a["g"] > 0 else -1)
    v400 = lambda r, k="60m@400", arm="ITM": (r[arm].get(k) or 0.0) if r[arm]["state"] == "FILLED" else 0.0  # noqa: E731
    rules = {
        "all": lambda r: True, "match": lambda r: r["src"] == "match_row", "fallback": lambda r: r["src"] == "fallback_0915_open",
        "pre": lambda r: r["period"] == "pre", "post": lambda r: r["period"] == "post",
        "match-pre": lambda r: r["src"] == "match_row" and r["period"] == "pre", "match-post": lambda r: r["src"] == "match_row" and r["period"] == "post",
        "CHEAP": lambda r: L.get(r["day"]) == "CHEAP", "MID": lambda r: L.get(r["day"]) == "MID", "RICH": lambda r: L.get(r["day"]) == "RICH",
        "skip-RICH": lambda r: L.get(r["day"]) in ("CHEAP", "MID"), "CHEAP-fixed": lambda r: Lf.get(r["day"]) == "CHEAP",
        "gap<0.2%": lambda r: abs(au[r["day"]]["g"]) < 0.002, "gap>=0.2%": lambda r: abs(au[r["day"]]["g"]) >= 0.002,
        "HIGH-volume": lambda r: vols.get(r["day"]) == "HIGH", "LOW-volume": lambda r: vols.get(r["day"]) == "LOW",
        "BUILDING": lambda r: drift.get(r["day"], 0) > 0 and r["day"] in drift, "FADING": lambda r: r["day"] in drift and drift[r["day"]] <= 0,
        "CHEAP-pre": lambda r: L.get(r["day"]) == "CHEAP" and r["period"] == "pre", "CHEAP-post": lambda r: L.get(r["day"]) == "CHEAP" and r["period"] == "post",
        "CHEAP-match": lambda r: L.get(r["day"]) == "CHEAP" and r["src"] == "match_row", "CHEAP-fallback": lambda r: L.get(r["day"]) == "CHEAP" and r["src"] != "match_row",
    }
    ser = {k: [v400(r) if f(r) else 0.0 for r in rows] for k, f in rules.items()}
    ser["20-minute hold"] = [v400(r, "20m@400") for r in rows]
    ser["ATM leg"] = [v400(r, "60m@400", "ATM") for r in rows]
    return ser


def main():
    if OUT.exists():
        raise SystemExit("SN397 is run once")
    smp, days, au = op.setup()
    jm = op.jumps(smp, "HONEST")
    Lfix, Lmov = op.labels(jm, True), op.labels(jm, False)
    cal = smp.cal
    rows = []
    for d, a in sorted(au.items()):
        if a["g"] == 0 or d not in jm:
            continue
        s = smp.s[d]
        same = "CE" if a["g"] > 0 else "PE"
        opp = "PE" if same == "CE" else "CE"
        k = bisect.bisect_left(cal, d) - 1
        r = {"day": d, "cheap": Lfix[d] == "CHEAP", "cheap_moving": Lmov.get(d) == "CHEAP", "jump": jm[d], "g": a["g"], "src": a["how"],
             "period": "post" if d >= op.SPLIT else "pre", "dte": smp.sessions_until(d, s["expiry"]),
             "after_break": (dt.date.fromisoformat(d) - dt.date.fromisoformat(cal[k])).days > 1 if k >= 0 else False,
             "follow": None, "iv_open": V.straddle_iv(smp, s, 0)}
        c0, c60 = s["index"][3][0], s["index"][3][60]
        if not (np.isnan(c0) or np.isnan(c60)):
            r["follow"] = float(c60 - c0) * (1 if a["g"] > 0 else -1)
        for key, side in (("SAME", same), ("OPP", opp)):
            x = {}
            for st in (205.0, 400.0):
                lr = leg_row(smp, s, side, st)
                x["state"] = lr["state"]
                if lr["state"] == "FILLED":
                    x[f"net{int(st)}"] = lr["net"]
                    x["depth"] = lr["depth"]
                    if st == 205.0:
                        p0, _d, _s, _j = op.leg(smp, s, side, 1, "HONEST", 0.0)
                        x["dec"] = decompose(smp, s, p0, side) if p0 is not None else None
            r[key] = x
        rows.append(r)
    med_g = float(np.median([abs(r["g"]) for r in rows]))
    res = {"cohort": len(rows), "cheap_fixed": sum(r["cheap"] for r in rows), "cheap_moving": sum(r["cheap_moving"] for r in rows), "median_abs_gap": med_g}
    for lab, f in (("CHEAP", lambda r: r["cheap"]), ("OTHER", lambda r: not r["cheap"])):
        for key in ("SAME", "OPP"):
            res[f"{lab} {key}"] = cell_summary([r for r in rows if f(r)], key)
    strata = {"dte 1-2": lambda r: r["dte"] <= 2, "dte >=3": lambda r: r["dte"] >= 3, "after break": lambda r: r["after_break"], "no break": lambda r: not r["after_break"],
              "match": lambda r: r["src"] == "match_row", "fallback": lambda r: r["src"] != "match_row",
              "small gap": lambda r: abs(r["g"]) < med_g, "large gap": lambda r: abs(r["g"]) >= med_g}
    st_out = {}
    for pair in (("dte 1-2", "dte >=3"), ("after break", "no break"), ("match", "fallback"), ("small gap", "large gap")):
        acc = {205: 0.0, 400: 0.0}
        wsum = 0
        for nm in pair:
            sub = [r for r in rows if strata[nm](r)]
            ch, ot = [r for r in sub if r["cheap"]], [r for r in sub if not r["cheap"]]
            e = {"n": len(sub), "cheap_n": len(ch), "other_n": len(ot), "cheap_share": round(len(ch) / len(sub), 3) if sub else None}
            for st in (205, 400):
                pc = op.per_session([(r["SAME"].get(f"net{st}") or 0.0) if r["SAME"]["state"] == "FILLED" else 0.0 for r in ch])
                po = op.per_session([(r["SAME"].get(f"net{st}") or 0.0) if r["SAME"]["state"] == "FILLED" else 0.0 for r in ot])
                e[f"cheap@{st}"], e[f"other@{st}"] = pc, po
                if pc is not None and po is not None:
                    e[f"diff@{st}"] = round(pc - po, 1)
                    acc[st] += (pc - po) * len(sub)
            if ch and ot:
                wsum += len(sub)
            st_out[nm] = e
        st_out[f"weighted CHEAP-OTHER over {pair}"] = {st: round(acc[st] / wsum, 1) if wsum else None for st in (205, 400)}
    res["strata"] = st_out
    filled = [r for r in rows if r["SAME"]["state"] == "FILLED"]
    for st in (205, 400):
        y = [r["SAME"][f"net{st}"] for r in filled]
        dums = [[r["dte"] <= 2 for r in filled], [r["after_break"] for r in filled], [r["src"] == "match_row" for r in filled], [abs(r["g"]) >= med_g for r in filled]]
        res[f"ols CHEAP @{st}"] = ols(y, [[r["cheap"] for r in filled]] + dums, ["CHEAP", "dte<=2", "after_break", "match", "large_gap"])
        res[f"ols jump @{st}"] = ols(y, [[r["jump"] for r in filled]] + dums, ["jump", "dte<=2", "after_break", "match", "large_gap"])
    # the reality check
    o_rows = sn396.score(smp, au, "ORIGINAL")
    h_rows = sn396.score(smp, au, "HONEST")
    res["white ORIGINAL @400"] = white_rc(family(smp, au, o_rows, op.jumps(smp, "ORIGINAL")))
    res["white HONEST @400"] = white_rc(family(smp, au, h_rows, jm))
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if not k.startswith("white")}, indent=1, default=float)[:9000])
    for k in ("white ORIGINAL @400", "white HONEST @400"):
        print(k, json.dumps({x: res[k][x] for x in ("rules", "best", "best_per_session", "p_white")}))


if __name__ == "__main__":
    main()
