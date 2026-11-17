"""SN398: weekly-roll days with the same contract (PLAN.md section 1, frozen at 00693405; details fixed here before any
SN398 number).

1. History: for every NIFTY weekly expiry E in Breeze's request keys (2026), the first option request date against the
   previous expiry: if no expiry's options start on or before the previous expiry day, the next-week chain does not exist
   on expiry days in this history (the slot's history part closes).
2. Real-quote archive (sealed Sep 10 - Nov 13): roll day d = a session whose previous exchange session p was a NIFTY
   expiry (p == the front expiry on p). Today's front E2 was p's second expiry. Readings (decision-safe snapshots):
     today  the snapshot in [09:15:00, 09:16:00) (about 09:15:27);  p  the snapshot in [14:59:00, 15:00:00);
     ATM strike nearest the front future's last price at that snapshot; IV = Black-76 straddle IV on the synthetic forward
     K + C - P with time to E2 at 09:16 / 15:00 (sn361); jump = 100 x (IV_d - IV_p) on the SAME contract (E2), and the
     total-variance change d(IV^2 T). CHEAP = jump < 1.2684 (fw9's frozen cutoff, no recalibration). The same readings on
     ordinary archive days (same front on both days) as the reference distribution.
   Trade on roll days (all, and CHEAP only): direction = sign(today's [09:15, 09:16) future - p's last future snapshot)
   (the archive has no pre-open match; a gap proxy known by 09:16:00); 2-ITM then 1-ITM on E2, admissible if the walked
   one-lot ask + entry charges <= Rs 15,000 at the first snapshot in [09:16:00, 09:17:00); exit at the walked bid of the
   snapshot in [10:16:00, 10:17:00); the Rs 3,000 stop checked on every minute snapshot between (walked bid); Rs 205 /
   400. Reported: roll days, readings, CHEAP labels, affordable lots, nets, and the coverable share of roll days.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import pickle
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import op  # noqa: E402
import fw9a  # noqa: E402
import sn396  # noqa: E402

OUT = HERE / "results-sn398.json"
LOCAL = HERE / "_local"


def history_keys():
    con = sqlite3.connect(f"file:{op.sn353b.HIST.as_posix()}?mode=ro", uri=True, timeout=60)
    first = {}
    for (k,) in con.execute("SELECT key FROM requests WHERE key LIKE 'option|NIFTY|2026-%' AND status='ok'"):
        p = k.split("|")
        e, a = p[2], p[-2]
        first[e] = min(first.get(e, a), a)
    exps = sorted(first)
    rows = [{"expiry": e, "prev_expiry": pe, "first_request": first[e], "covers_prev_expiry_day": first[e] <= pe} for pe, e in zip(exps, exps[1:])]
    return {"expiries": len(rows), "covering_prev_expiry_day": sum(r["covers_prev_expiry_day"] for r in rows), "rows": rows}


def load(day):
    LOCAL.mkdir(exist_ok=True)
    p = LOCAL / f"arch398-{day}.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    man = json.loads((sn396.EXPORT / "manifest.json").read_text(encoding="utf-8"))["files_sha256"]
    out = {}
    for k in sorted(x for x in man if x.startswith(f"quotes/{day}/") and x.endswith(".jsonl.gz")):
        b = (sn396.EXPORT / k).read_bytes()
        assert hashlib.sha256(b).hexdigest() == man[k], k
        for line in gzip.decompress(b).decode("utf-8").splitlines():
            r = json.loads(line)
            t = (r.get("provider_timestamp_raw") or "")[11:19]
            if not ("09:15:00" <= t < "10:17:00" or "14:59:00" <= t < "15:31:00"):
                continue
            c = r["contract"]
            if c["underlying"] != "NIFTY":
                continue
            ok = r.get("depth_state") == "USABLE" and not r.get("crossed_depth") and not r.get("locked_depth")
            key = ("FUT", c["expiry"]) if c["instrument_type"] == "FUT" else (c["instrument_type"], c["expiry"], int(round(float(c["strike"]))))
            out.setdefault(key, []).append({"t": t, "ok": ok, "ltp": r.get("ltp"),
                                            "bids": [(x["price"], x["quantity"]) for x in (r.get("buy_depth") or []) if x.get("price") and x.get("quantity")],
                                            "asks": [(x["price"], x["quantity"]) for x in (r.get("sell_depth") or []) if x.get("price") and x.get("quantity")]})
    for v in out.values():
        v.sort(key=lambda x: x["t"])
    p.write_bytes(pickle.dumps(out))
    return out


def front_fut(A):
    fs = sorted(k for k in A if k[0] == "FUT")
    return A[fs[0]] if fs else None


def reading(A, day, expiry, lo, hi, hhmm):
    f = sn396.snap(front_fut(A), lo, hi)
    if f is None or not f.get("ltp"):
        return None
    k = int(round(float(f["ltp"]) / 50.0) * 50)
    c, p = sn396.snap(A.get(("CE", expiry, k)), lo, hi), sn396.snap(A.get(("PE", expiry, k)), lo, hi)
    if c is None or p is None:
        return None
    mc, mp = 0.5 * (c["bids"][0][0] + c["asks"][0][0]), 0.5 * (p["bids"][0][0] + p["asks"][0][0])
    F = k + mc - mp
    T = op.sn361.years_to(day, expiry, hhmm)
    iv = op.sn361.iv(mc + mp, F, k, T)
    return None if iv is None else {"iv": iv, "T": T, "k": k}


def last_fut(A):
    fs = front_fut(A)
    xs = [r for r in fs or [] if r.get("ltp")]
    return float(xs[-1]["ltp"]) if xs else None


def trade(A, expiry, side, F0, stress):
    sgn = -1 if side == "CE" else 1
    atm = int(round(F0 / 50.0) * 50)
    for dep in (2, 1):
        recs = A.get((side, expiry, atm + sgn * dep * 50))
        e = sn396.snap(recs, "09:16:00", "09:17:00")
        if e is None:
            continue
        px = sn396.walk(e["asks"], op.LOT)
        if px is None or op.entry_cost(px) > op.ROOM:
            continue
        for r in recs:
            if not (e["t"] < r["t"] < "10:17:00") or not r["ok"] or not r["bids"]:
                continue
            b = sn396.walk(r["bids"], op.LOT)
            if b is None:
                continue
            net = (b - px) * op.LOT - op.wk.charges(px, b, op.LOT, "NFO") - stress
            if net <= -op.STOP or r["t"] >= "10:16:00":
                return {"depth": dep, "net": round(net, 2), "exit_t": r["t"], "why": "stop" if net <= -op.STOP else "time", "debit": round(op.entry_cost(px), 2)}
        return {"depth": dep, "net": None, "why": "no exit quote"}
    return {"depth": None, "net": None, "why": "INADMISSIBLE"}


def main():
    if OUT.exists():
        raise SystemExit("SN398 is run once")
    res = {"history": history_keys()}
    man = json.loads((sn396.EXPORT / "manifest.json").read_text(encoding="utf-8"))
    sealed = [d for d in man["quote_days"] if d not in set(man["unsealed_days"])]
    roll, ordinary = [], []
    for d in sealed:
        p = fw9a.prev_exchange_session(d)
        if p not in sealed:
            continue
        A, Ap = load(d), load(p)
        exps_p = sorted({k[1] for k in Ap if k[0] != "FUT" and k[1] >= p})
        exps_d = sorted({k[1] for k in A if k[0] != "FUT" and k[1] >= d})
        if not exps_p or not exps_d or exps_d[0] == d:
            continue
        E2 = exps_d[0]
        is_roll = exps_p[0] == p
        a = reading(A, d, E2, "09:15:00", "09:16:00", "09:16")
        b = reading(Ap, p, E2, "14:59:00", "15:00:00", "15:00")
        r = {"day": d, "prev": p, "front": E2, "roll": is_roll, "reading": a is not None and b is not None}
        if r["reading"]:
            r["jump"] = 100.0 * (a["iv"] - b["iv"])
            r["d_total_variance"] = a["iv"] ** 2 * a["T"] - b["iv"] ** 2 * b["T"]
            r["cheap"] = r["jump"] < op.CUT_LO
        if is_roll:
            f0, fp = sn396.snap(front_fut(A), "09:15:00", "09:16:00"), last_fut(Ap)
            if f0 and fp and f0.get("ltp"):
                gap = float(f0["ltp"]) - fp
                r["gap_proxy_pts"] = gap
                if gap != 0:
                    side = "CE" if gap > 0 else "PE"
                    for st in (205.0, 400.0):
                        r[f"trade@{int(st)}"] = trade(A, E2, side, float(f0["ltp"]), st)
            roll.append(r)
        else:
            ordinary.append(r)
    res["roll_days"] = roll
    res["roll_summary"] = {"roll_days": len(roll), "with_reading": sum(r["reading"] for r in roll), "cheap": sum(bool(r.get("cheap")) for r in roll),
                           "affordable_trades": sum(1 for r in roll if (r.get("trade@205") or {}).get("net") is not None)}
    for st in (205, 400):
        xs = [(r.get(f"trade@{st}") or {}).get("net") for r in roll]
        res["roll_summary"][f"all_roll per_session@{st}"] = op.per_session([x or 0.0 for x in xs]) if roll else None
        res["roll_summary"][f"cheap_roll per_session@{st}"] = op.per_session([(r.get(f"trade@{st}") or {}).get("net") or 0.0 for r in roll if r.get("cheap")]) if any(r.get("cheap") for r in roll) else None
    oj = [r["jump"] for r in ordinary if r["reading"]]
    rj = [r["jump"] for r in roll if r["reading"]]
    res["jump_distribution"] = {"ordinary_n": len(oj), "ordinary_median": round(float(np.median(oj)), 3) if oj else None,
                                "ordinary_share_cheap": round(float(np.mean([j < op.CUT_LO for j in oj])), 3) if oj else None,
                                "roll_n": len(rj), "roll_jumps": [round(j, 3) for j in rj]}
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "history"} | {"history": {k: v for k, v in res["history"].items() if k != "rows"}}, indent=1, default=float))


if __name__ == "__main__":
    main()
