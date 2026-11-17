"""SN383 / SN384 / SN385 / SN391 / SN393 / SN394: the opening family on SN382's honest AUCTION rows (PLAN.md sections 1-2,
frozen at c6e99cee; the details below are fixed here before any of these numbers). gl DEV + TEST, Dec 8, 2025 - Oct
28, 2026, non-expiry; the 09:16 decision; SN382's cash rule; per-session net = the ITM leg's net when FILLED, else 0;
everything reported at Rs 205 and Rs 400 and split before / from Sep 7, 2026.

SN383 (what the ITM option buys): sessions where ATM, 1-ITM and 2-ITM are ALL admissible; each leg held to 10:16 (or its
Rs 3,000 stop at stress 0). Black-76 on the synthetic forward of the ATM pair (minute closes): mid change = delta x dF +
vega x dIV + theta x dt + residual (Greeks and IV at entry, each leg's own IV at entry and exit); plus spread + charges
paid; time value paid as a share of the debit. Means per leg, rupees per lot. Next-week legs: not in gl's data (front
weekly only) - recorded as not available.
SN384 (cut a failed thesis): on the ITM fills, at 09:36 exit if the auction contract's 09:36 futures close (Breeze) has
given back >= half of the move from the previous close C0 to the auction price A (i.e. (f - C0) <= 0.5 (A - C0) for an
up gap, mirrored), at minute 22's model bid (the next minute); else the 60-minute hold. Paired vs the hold on the same
fills: (a) exits fixed at stress 0 then the stress subtracted; (b) gl's own stress-triggered walks. Winners cut short =
exited trades whose hold was > 0.
SN385 (cash support): the NIFTY 50 index's last pre-09:15 Breeze row (the cash-auction basket, published before the
open) vs the previous session's index close: cash gap. AGREE = same sign as the futures g. Coverage required: >= 100
sessions with both. Per-session net AGREE vs DISAGREE (all, by |g| bucket < 0.2% / >= 0.2%, by period). Roll dates (two
contracts with pre-open match rows): front / next gap sign agreement logged. Advance: AGREE > 0 at Rs 205 and Rs 400,
above DISAGREE and the unconditional arm, in both periods.
SN391 (indicative path): from Sep 7, 2026 only (Breeze's pre-open rows carry the indicative price): drift = A - the
09:05 row's close, signed by g; BUILDING (drift with the gap) vs FADING. Development only (small sample).
SN393 (conviction): MATCH-source sessions; the match row's volume vs the median of the previous 20 MATCH sessions'
match volumes (causal): HIGH / LOW.
SN394 (non-rich opens): SN377's causal tercile of the overnight IV jump (IV(09:16) - IV(previous 15:00), same expiry,
terciles from earlier sessions over the whole 2022 - 2026 history, >= 60 earlier); per-session net by tercile and with
RICH skipped.
"""
from __future__ import annotations

import json
import math
import sqlite3
import statistics
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FNO / "2026-11-16-sn366"))
import sn382 as R  # noqa: E402
import sn377 as V  # noqa: E402

gl, S, sn353b, sn361 = R.gl, R.S, R.sn353b, V.sn361
OUT = HERE / "results-sn383-394.json"
HIST = sn353b.HIST
LOT = 65


def q(con, sql, args):
    return con.execute(sql, args).fetchall()


def per_session(rows, key="60m", st=205, pick=None):
    rs = [r for r in rows if pick is None or pick(r)]
    xs = [(r["ITM"].get(f"{key}@{st}") or 0.0) if r["ITM"]["state"] == "FILLED" else 0.0 for r in rs]
    return {"n": len(rs), "fills": sum(r["ITM"]["state"] == "FILLED" for r in rs), "per_session": round(float(np.mean(xs)), 1) if xs else None}


def split(rows, pick):
    return {f"{k}@{st}": per_session(rows, k, st, pick) for k in ("20m", "60m") for st in (205, 400)}


def greeks(F, K, T, s, cp):
    v = s * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * v * v) / v
    n1 = math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
    delta = sn361.N(d1) if cp == "CE" else sn361.N(d1) - 1.0
    vega = F * n1 * math.sqrt(T)
    theta = -F * n1 * s / (2 * math.sqrt(T))            # per year
    return delta, vega, theta


def leg_iv(p, F, K, T, cp):
    lo, hi = 1e-3, 5.0
    if not (sn361.b76(F, K, T, lo, cp) < p < sn361.b76(F, K, T, hi, cp)):
        return None
    for _ in range(60):
        m = 0.5 * (lo + hi)
        lo, hi = (m, hi) if sn361.b76(F, K, T, m, cp) < p else (lo, m)
    return 0.5 * (lo + hi)


def synthetic(smp, s, i):
    k = gl.atm(smp, s, i)
    c, p = gl.opx(s, k, "CE", i, look=1), gl.opx(s, k, "PE", i, look=1)
    return None if c is None or p is None else k + c - p


def sn383(smp, rows):
    out = {}
    legs = {"ATM": (0,), "ITM1": (1,), "ITM2": (2,)}
    acc = {n: [] for n in legs}
    common = 0
    for r in rows:
        s = smp.s[r["day"]]
        side = "CE" if r["dir"] > 0 else "PE"
        got = {}
        for n, dep in legs.items():
            pos, d = R.leg(smp, s, side, 1, 0.0, dep)
            if pos is None:
                break
            got[n] = pos
        if len(got) < 3:
            continue
        common += 1
        F0, F1 = synthetic(smp, s, 1), synthetic(smp, s, 61)
        if F0 is None or F1 is None:
            continue
        T0 = sn361.years_to(s["day"], s["expiry"], "09:16")
        T1 = sn361.years_to(s["day"], s["expiry"], "10:16")
        for n, pos in got.items():
            k = pos.legs[0][0]
            m0, m1 = gl.opx(s, k, side, 1, look=1), gl.opx(s, k, side, 61, look=10)
            if m0 is None or m1 is None:
                continue
            s0, s1 = leg_iv(m0, F0, k, T0, side), leg_iv(m1, F1, k, T1, side)
            if s0 is None or s1 is None:
                continue
            dl, vg, th = greeks(F0, k, T0, s0, side)
            dmid = (m1 - m0) * LOT
            dpart, vpart = dl * (F1 - F0) * LOT, vg * (s1 - s0) * LOT
            tpart = -abs(th) * (T0 - T1) * LOT              # theta (per year) x the elapsed years: decay
            intrinsic = max(0.0, (F0 - k) if side == "CE" else (k - F0))
            net0, _j, _w = gl.walk(pos, s, 1, 61, room=S.STOP)
            acc[n].append({"dmid": dmid, "delta": dpart, "vega": vpart, "theta": tpart, "resid": dmid - dpart - vpart - tpart,
                           "cost": (pos.fills[0] - m0) * LOT + gl.wk.charges(pos.fills[0], 0.0, LOT, "NFO"),
                           "tv_share": (m0 - intrinsic) / m0 if m0 > 0 else None, "net0": net0, "entry_delta": dl, "debit": pos.fills[0] * LOT})
    out["common_sessions"] = common
    for n, xs in acc.items():
        if xs:
            out[n] = {k: round(float(np.nanmean([x[k] for x in xs if x[k] is not None])), 3 if k in ("tv_share", "entry_delta") else 1)
                      for k in ("dmid", "delta", "vega", "theta", "resid", "cost", "tv_share", "net0", "entry_delta", "debit")}
            out[n]["n"] = len(xs)
    out["next_week"] = "not available (gl holds the front weekly only)"
    return out


def main():
    if OUT.exists():
        raise SystemExit("SN383-SN394 are run once")
    raw = gl._cache("devall", gl.build_dev)
    smp = gl.Sample("ALL", raw, gl.DEV_LO, gl.TEST_HI)
    days = [d for d in smp.days if smp.s[d]["day"] != smp.s[d]["expiry"]]
    au = sn353b.auctions([d for d in days if sn353b.LO <= d < sn353b.HI])
    auc = {d: (1 if a["g"] > 0 else -1) for d, a in au.items() if a["g"] != 0}
    rows = R.run(smp, days, auc, {d: a["how"] for d, a in au.items()})
    for r in rows:
        r["dir"] = auc[r["day"]]
        r.update({k: au[r["day"]][k] for k in ("A", "C0", "expiry", "g", "how", "at")})
    con = sqlite3.connect(f"file:{HIST.as_posix()}?mode=ro", uri=True, timeout=60)
    res = {"rows": len(rows), "unconditional": split(rows, None)}
    # SN383
    res["SN383"] = sn383(smp, rows)
    # SN384
    fq = ("SELECT close FROM candles WHERE kind='future' AND underlying='NIFTY' AND expiry=? AND strike=0 AND opt='' AND interval='1minute' AND datetime=?")
    a_fix, a_nat, h_fix, h_nat, cut, native = [], [], [], [], {"exited": 0, "winners_cut": 0}, {}
    for r in rows:
        if r["ITM"]["state"] != "FILLED":
            continue
        s = smp.s[r["day"]]
        f = q(con, fq, (r["expiry"], r["day"] + " 09:36:00"))
        side = "CE" if r["dir"] > 0 else "PE"
        pos0, _d = R.leg(smp, s, side, 1, 0.0, (2, 1))
        hold0, _j, _w = gl.walk(pos0, s, 1, 61, room=S.STOP)
        if not f or hold0 is None:
            continue
        gave = ((float(f[0][0]) - r["C0"]) <= 0.5 * (r["A"] - r["C0"])) if r["dir"] > 0 else ((float(f[0][0]) - r["C0"]) >= 0.5 * (r["A"] - r["C0"]))
        stopped_before = gl.walk(pos0, s, 1, 21, room=S.STOP)[2] == "stop"
        exit0 = pos0.value(s, 22) if gave and not stopped_before else None
        rule0 = exit0 if exit0 is not None else hold0
        if exit0 is not None:
            cut["exited"] += 1
            cut["winners_cut"] += hold0 > 0
        for st, af, hf in ((205, a_fix, h_fix), (400, a_nat, h_nat)):
            af.append(rule0 - st)
            hf.append(hold0 - st)
            pst, _d = R.leg(smp, s, side, 1, float(st), (2, 1))      # gl's own stress-triggered stop
            hn, _j, _w = gl.walk(pst, s, 1, 61, room=S.STOP)
            sn_ = gl.walk(pst, s, 1, 21, room=S.STOP)[2] == "stop"
            en = pst.value(s, 22) if gave and not sn_ else None
            if hn is not None:
                native.setdefault(st, []).append(((en if en is not None else hn), hn))
    res["SN384"] = {"fills": len(h_fix), **cut,
                    "rule_fixed@205": round(float(np.mean(a_fix)), 1) if a_fix else None, "hold_fixed@205": round(float(np.mean(h_fix)), 1) if h_fix else None,
                    "rule_fixed@400": round(float(np.mean(a_nat)), 1) if a_nat else None, "hold_fixed@400": round(float(np.mean(h_nat)), 1) if h_nat else None,
                    "paired_diff@205": round(float(np.mean(np.array(a_fix) - np.array(h_fix))), 1) if a_fix else None,
                    "paired_se": round(float(np.std(np.array(a_fix) - np.array(h_fix), ddof=1) / math.sqrt(len(a_fix))), 1) if len(a_fix) > 1 else None,
                    "native": {str(st): {"rule": round(float(np.mean([a for a, _h in v])), 1), "hold": round(float(np.mean([h for _a, h in v])), 1), "n": len(v)} for st, v in native.items()}}
    # SN385
    iq = ("SELECT datetime, close FROM candles WHERE kind='index' AND underlying='NIFTY' AND expiry='' AND strike=0 AND opt='' AND interval='1minute' "
          "AND datetime>=? AND datetime<? ORDER BY datetime")
    cov = 0
    for r in rows:
        pre = q(con, iq, (r["day"] + " 09:00", r["day"] + " 09:15"))
        pb = smp.prev_bar(r["day"])
        r["cash_gap"] = None if not pre or pb is None else float(pre[-1][1]) / float(pb[3]) - 1.0
        cov += r["cash_gap"] is not None
    res["SN385"] = {"coverage": cov}
    if cov >= 100:
        ag = lambda r: r.get("cash_gap") is not None and np.sign(r["cash_gap"]) == r["dir"]  # noqa: E731
        dg = lambda r: r.get("cash_gap") is not None and np.sign(r["cash_gap"]) != r["dir"]  # noqa: E731
        res["SN385"].update(AGREE=split(rows, ag), DISAGREE=split(rows, dg))
        for b, f in (("small", lambda r: abs(r["g"]) < 0.002), ("large", lambda r: abs(r["g"]) >= 0.002)):
            res["SN385"][f"AGREE {b}"] = split(rows, lambda r, f=f: ag(r) and f(r))
            res["SN385"][f"DISAGREE {b}"] = split(rows, lambda r, f=f: dg(r) and f(r))
        for per in ("pre", "post"):
            res["SN385"][f"AGREE {per}"] = split(rows, lambda r, per=per: ag(r) and r["period"] == per)
            res["SN385"][f"DISAGREE {per}"] = split(rows, lambda r, per=per: dg(r) and r["period"] == per)
    else:
        res["SN385"]["closed"] = "coverage below 100"
    # roll dates
    keys = [k for (k,) in con.execute("SELECT key FROM requests WHERE key LIKE 'future|NIFTY|%' AND status='ok'")]
    spans = [(k.split("|")[2], k.split("|")[3], k.split("|")[4]) for k in keys]
    roll = []
    for r in rows:
        exps = sorted({e for e, a, b in spans if a <= r["day"] <= b and e >= r["day"]})
        gs = []
        for e in exps[:2]:
            m = q(con, "SELECT close FROM candles WHERE kind='future' AND underlying='NIFTY' AND expiry=? AND strike=0 AND opt='' AND interval='1minute' "
                  "AND datetime>=? AND datetime<? AND oi>0 ORDER BY datetime LIMIT 1", (e, r["day"] + " 09:00", r["day"] + " 09:15"))
            p = q(con, "SELECT close FROM candles WHERE kind='future' AND underlying='NIFTY' AND expiry=? AND strike=0 AND opt='' AND interval='1minute' "
                  "AND datetime<? ORDER BY datetime DESC LIMIT 1", (e, r["day"] + " 00:00"))
            if m and p:
                gs.append(float(m[0][0]) / float(p[0][0]) - 1.0)
        if len(gs) == 2:
            roll.append({"day": r["day"], "agree": bool(np.sign(gs[0]) == np.sign(gs[1])), "net60@205": r["ITM"].get("60m@205") if r["ITM"]["state"] == "FILLED" else 0.0})
    res["SN385"]["roll_dates"] = {"n": len(roll), "agree": sum(x["agree"] for x in roll),
                                  "per_session_agree": round(float(np.mean([x["net60@205"] or 0 for x in roll if x["agree"]])), 1) if any(x["agree"] for x in roll) else None,
                                  "per_session_disagree": round(float(np.mean([x["net60@205"] or 0 for x in roll if not x["agree"]])), 1) if any(not x["agree"] for x in roll) else None}
    # SN391
    for r in rows:
        r["drift"] = None
        if r["period"] == "post" and r["how"] == "match_row":
            row = q(con, "SELECT close FROM candles WHERE kind='future' AND underlying='NIFTY' AND expiry=? AND strike=0 AND opt='' AND interval='1minute' AND datetime=?",
                    (r["expiry"], r["day"] + " 09:05:00"))
            if row:
                r["drift"] = (r["A"] - float(row[0][0])) * r["dir"]
    res["SN391"] = {"sessions": sum(r["drift"] is not None for r in rows),
                    "BUILDING": split(rows, lambda r: r["drift"] is not None and r["drift"] > 0),
                    "FADING": split(rows, lambda r: r["drift"] is not None and r["drift"] <= 0)}
    # SN393
    vols, hist = {}, []
    for r in sorted(rows, key=lambda r: r["day"]):
        if r["how"] != "match_row":
            continue
        v = q(con, "SELECT volume FROM candles WHERE kind='future' AND underlying='NIFTY' AND expiry=? AND strike=0 AND opt='' AND interval='1minute' AND datetime>=? "
              "AND datetime<? AND oi>0 ORDER BY datetime LIMIT 1", (r["expiry"], r["day"] + " 09:00", r["day"] + " 09:15"))
        mv = float(v[0][0]) if v and v[0][0] is not None else None
        if mv is not None and len(hist) >= 20:
            vols[r["day"]] = "HIGH" if mv > statistics.median(hist[-20:]) else "LOW"
        if mv is not None:
            hist.append(mv)
    res["SN393"] = {"sessions": len(vols), "HIGH": split(rows, lambda r: vols.get(r["day"]) == "HIGH"), "LOW": split(rows, lambda r: vols.get(r["day"]) == "LOW")}
    # SN394
    jump, histj = {}, []
    alld = smp.days
    for a, d in zip(alld, alld[1:]):
        s, sp = smp.s[d], smp.s[a]
        if s["day"] == s["expiry"] or sp["expiry"] != s["expiry"]:
            continue
        io, ip = V.straddle_iv(smp, s, 1), V.straddle_iv(smp, sp, 345)
        if io is None or ip is None:
            continue
        j = 100.0 * (io - ip)
        if len(histj) >= 60:
            srt = sorted(histj)
            lo, hi = srt[len(srt) // 3], srt[(2 * len(srt)) // 3]
            jump[d] = "CHEAP" if j < lo else "RICH" if j > hi else "MID"
        histj.append(j)
    res["SN394"] = {t: split(rows, lambda r, t=t: jump.get(r["day"]) == t) for t in ("CHEAP", "MID", "RICH")}
    res["SN394"]["skip_RICH"] = split(rows, lambda r: jump.get(r["day"]) in ("CHEAP", "MID"))
    res["SN394"]["unconditional_with_reading"] = split(rows, lambda r: r["day"] in jump)
    res["by_period"] = {p: split(rows, lambda r, p=p: r["period"] == p) for p in ("pre", "post")}
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
