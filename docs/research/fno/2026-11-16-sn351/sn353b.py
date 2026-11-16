"""SN353 (b): the price-only auction arm (PLAN.md section 1 + amendment A2, frozen before any SN353 outcome).

Sessions Dec 8, 2025 - Oct 28, 2026 (gl's DEV + TEST NIFTY sessions, seen data), non-expiry (day != front weekly expiry).
Auction price A: close of the first pre-09:15 Breeze 1-minute row with OI > 0 of the nearest futures contract with such a
row (fallback: that contract's 09:15 open, counted). Previous close C0: that contract's last close of the previous session.
g = A / C0 - 1; buckets |g| < 0.2%, 0.2-0.5%, > 0.5%.
Entry at 09:16 (minute 1), one lot of the front-weekly ATM option (gl.atm on the index), gl's executable model.
Arms: CONT (CE if g > 0 else PE), FADE (the other side), COIN (seeded coin flip per session). Held 5 / 20 / 60 minutes,
Rs 3,000 stop on minute closes (gl.walk). Net at stress Rs 0 / 205 / 400 (charges always).
Archive check (Sep 10 - Oct 28 sessions): walked ask at the first usable snapshot >= 09:16 (no later than 09:18, else
missed), walked bid at a usable snapshot
in the exit minute or the one before, the stop checked on each minute's walked bid.
Advance (frozen): an arm's 20-minute net per trade at Rs 205 > 0 on Breeze with >= 60 trades, above COIN, and the same
sign on the archive.
"""
from __future__ import annotations

import json
import random
import sqlite3
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
HIST = Path(r"C:/Users/Urveesh/sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite")
LO, HI = "2025-12-08", "2026-10-29"
HOLDS = (5, 20, 60)
STRESSES = (0.0, 205.0, 400.0)
STOP = 3000.0
OUT = HERE / "results-sn353b.json"


def bucket(g):
    a = abs(g)
    return "lt0.2" if a < 0.002 else "0.2-0.5" if a <= 0.005 else "gt0.5"


def auctions(days):
    con = sqlite3.connect(f"file:{HIST.as_posix()}?mode=ro", uri=True, timeout=60)
    keys = [r[0] for r in con.execute("select key from requests where key like 'future|NIFTY|%' and status='ok'")]
    spans = [(k.split("|")[2], k.split("|")[3], k.split("|")[4]) for k in keys]
    out = {}
    q = ("select datetime, open, close, oi from candles where kind='future' and underlying='NIFTY' and expiry=? and strike=0 "
         "and opt='' and interval='1minute' and datetime>=? and datetime<? order by datetime")
    for d in days:
        exps = sorted({e for e, a, b in spans if a <= d <= b and e >= d})
        got = None
        for e in exps:
            rows = con.execute(q, (e, d + " 09:00", d + " 09:15")).fetchall()
            hit = next((r for r in rows if (r[3] or 0) > 0), None)
            if hit is not None:
                got = (e, float(hit[2]), "match_row", hit[0][11:16])
                break
        if got is None and exps:
            e = exps[0]
            r = con.execute(q, (e, d + " 09:15", d + " 09:16")).fetchone()
            if r is not None:
                got = (e, float(r[1]), "fallback_0915_open", "09:15")
        if got is None:
            continue
        e, A, how, at = got
        prev = con.execute("select datetime, close from candles where kind='future' and underlying='NIFTY' and expiry=? and strike=0 "
                           "and opt='' and interval='1minute' and datetime<? order by datetime desc limit 1", (e, d + " 00:00")).fetchone()
        f16 = con.execute(q, (e, d + " 09:16", d + " 09:17")).fetchone()
        if prev is None:
            continue
        out[d] = {"expiry": e, "A": A, "how": how, "at": at, "C0": float(prev[1]), "prev_day": prev[0][:10],
                  "g": A / float(prev[1]) - 1.0, "f0916": None if f16 is None else float(f16[2])}
    return out


def gl_trade(smp, s, side, stress):
    k = gl.atm(smp, s, 1)
    pos = gl.Pos(smp, s, [(k, side, +1)], 1, lots=1, stress=stress)
    if not pos.ok:
        return None
    res = {"strike": k, "premium": round(pos.premium, 2)}
    for H in HOLDS:
        net, j, why = gl.walk(pos, s, 1, 1 + H, room=STOP)
        res[H] = None if net is None else {"net": round(net, 2), "why": why, "j": j}
    return res


def arch_trade(q, expiry, strike, side, stress, lot):
    rec = q["opt"].get(("NIFTY", expiry, strike, side))
    if rec is None:
        return None
    i0 = qa.first_at(rec, 1)
    if i0 is None or i0 > 3:
        return None
    entry = qa.walk_cost(rec["askp"][:, i0], rec["askq"][:, i0], lot)
    if entry is None:
        return None
    res = {"i0": i0, "entry": entry}
    for H in HOLDS:
        out = None
        for j in range(i0 + 1, i0 + H + 1):
            if not rec["usable"][j]:
                continue
            b = qa.walk_cost(rec["bidp"][:, j], rec["bidq"][:, j], lot)
            if b is None:
                continue
            v = (b - entry) * lot - gl.wk.charges(entry, b, lot, "NFO") - stress
            if v <= -STOP:
                out = {"net": round(v, 2), "why": "stop", "j": j}
                break
            if j >= i0 + H - 1:
                out = {"net": round(v, 2), "why": "time", "j": j}
        res[H] = out
    return res


def summarize(rows, key):
    out = {}
    for H in HOLDS:
        for st in STRESSES:
            xs = [r[key][str(int(st))][H]["net"] for r in rows if r[key] and r[key].get(str(int(st))) and r[key][str(int(st))].get(H)]
            if xs:
                a = np.array(xs)
                out[f"{H}m@{int(st)}"] = {"n": len(a), "per_trade": round(float(a.mean()), 1), "median": round(float(np.median(a)), 1),
                                          "win_pct": round(100 * float((a > 0).mean()), 1), "total": round(float(a.sum()))}
    return out


def main():
    if OUT.exists():
        raise SystemExit("SN353 (b) is run once")
    raw = gl._cache("devall", gl.build_dev)
    smp = gl.Sample("AUCTION", raw, LO, HI)
    days = [d for d in smp.days if smp.s[d]["day"] != smp.s[d]["expiry"]]
    auc = auctions(days)
    print("sessions", len(days), "with auction", len(auc), flush=True)
    arch_days = set(d for d in qa.days() if LO <= d < HI)
    rows = []
    for d in days:
        a = auc.get(d)
        if a is None:
            continue
        s = smp.s[d]
        g = a["g"]
        cont = "CE" if g > 0 else "PE"
        fade = "PE" if cont == "CE" else "CE"
        coin = random.Random(f"sn353-{d}").choice(("CE", "PE"))
        r = {"day": d, **a, "bucket": bucket(g), "sides": {"CONT": cont, "FADE": fade, "COIN": coin},
             "idx0916": float(s["index"][3][1]), "idx_prev": None}
        pb = smp.prev_bar(d)
        if pb is not None:
            r["idx_prev"] = float(pb[3])
        for arm, side in r["sides"].items():
            r[arm] = {str(int(st)): gl_trade(smp, s, side, st) for st in STRESSES}
            r[f"{arm}_arch"] = None
        if d in arch_days:
            q = qa.load(d)
            k = gl.atm(smp, s, 1)
            for arm, side in r["sides"].items():
                r[f"{arm}_arch"] = {str(int(st)): arch_trade(q, s["expiry"], k, side, st, 65) for st in STRESSES}
        rows.append(r)
    res = {"sessions": len(days), "with_auction": len(auc), "how": {h: sum(1 for x in auc.values() if x["how"] == h) for h in ("match_row", "fallback_0915_open")},
           "match_minutes": sorted({x["at"] for x in auc.values()}), "buckets": {b: sum(1 for r in rows if r["bucket"] == b) for b in ("lt0.2", "0.2-0.5", "gt0.5")}}
    pri = [(r["f0916"] - r["A"]) / r["A"] * np.sign(r["g"]) for r in rows if r["f0916"] is not None and r["g"] != 0]
    res["first_minute_move_in_gap_direction_pct"] = {"mean": round(100 * float(np.mean(pri)), 4), "median": round(100 * float(np.median(pri)), 4), "n": len(pri)}
    for arm in ("CONT", "FADE", "COIN"):
        res[arm] = {"all": summarize(rows, arm)}
        for b in ("lt0.2", "0.2-0.5", "gt0.5"):
            res[arm][b] = summarize([r for r in rows if r["bucket"] == b], arm)
        res[f"{arm}_arch"] = summarize([r for r in rows if r.get(f"{arm}_arch")], f"{arm}_arch")
    adv = {}
    for arm in ("CONT", "FADE"):
        x = res[arm]["all"].get("20m@205", {})
        c = res["COIN"]["all"].get("20m@205", {})
        z = res[f"{arm}_arch"].get("20m@205", {})
        adv[arm] = bool(x and x["n"] >= 60 and x["per_trade"] > 0 and x["per_trade"] > c.get("per_trade", -1e9) and z and z["per_trade"] > 0)
    res["advance"] = adv
    res["rows"] = rows
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    for arm in ("CONT", "FADE", "COIN"):
        print(arm, json.dumps(res[arm]["all"]), flush=True)
        print(arm, "arch", json.dumps(res[f"{arm}_arch"]), flush=True)
    print("advance", adv, "buckets", res["buckets"], "first minute", res["first_minute_move_in_gap_direction_pct"], res["how"], res["match_minutes"])


if __name__ == "__main__":
    main()
