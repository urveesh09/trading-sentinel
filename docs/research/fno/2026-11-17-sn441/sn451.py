"""SN451 (own): expiry-afternoon hedging flows on NIFTY - pin (toward the largest open interest; Ni, Pearson & Poteshman
2005; Golez & Jackwerth 2012) against momentum (the day's move continues while dealers are short gamma; Baltussen, Da,
Lammers & Martens 2021) (PLAN.md section 2, frozen at f56f5807; details fixed here before any number).

Sample: NIFTY weekly expiry days in 2024 and 2025 only (2023 is the protected expiry exam and is never queried) whose
expiring chain has >= 9 strikes of 1-minute bars with OI on the day. Bars are labelled by start; a decision at hh:mm:00 uses
closes through the bar labelled hh:mm - 1.
At the decision (13:00 main; 12:00 and 14:00 sensitivity):
  S0      the index close of the bar before the decision; prev = the previous session's last index close
  K_OI    the strike with the largest CE + PE OI (each leg's last OI at or before the decision bar)
  K_pain  the strike minimising the holders' payout sum_K OI_CE(K) max(0, X-K) + OI_PE(K) max(0, K-X) over present strikes
  PIN     side = sign(K_OI - S0) when |K_OI - S0| >= 25 points, else no call (PIN_PAIN the same with K_pain)
  MOM     side = sign(S0 - prev)
Outcome: the index move from S0 to the close of the bar before 15:00 and before 15:25. Hit = the sign agrees.
Placebo: the session before each expiry, the same expiry's chain where it has >= 5 strikes with OI.
Uncertainty: 2,000 day-bootstrap resamples (seed 451) of the hit share.
Priced (13:00 only): the expiring ATM option (strike nearest S0) on each rule's side, bought at wk.ask of the 12:59 bar's
close, out at wk.bid of the 14:59 close or at the first minute whose bid mark <= -Rs 3,000; one lot (65), Zerodha charges,
Rs 205 / 400. Outside Gold's 13:30 expiring-contract cutoff (marked).
A development pass (hit >= 58% and a positive priced mean at both stresses) only nominates the rule for the protected 2023
expiry exam, on the owner's word.
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
sys.path.insert(0, str(FNO / "2026-11-14-sn201"))
import wk  # noqa: E402

OUT = HERE / "results-sn451.json"
DB = "file:C:/Users/Urveesh/sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite?mode=ro"
MK, LOT, STOP = wk.NIFTY, 65, 3000.0
CLOCKS = {"12:00": 165, "13:00": 225, "14:00": 285}
OUTC = {"15:00": 345, "15:25": 370}


def mi(t):
    return int(t[11:13]) * 60 + int(t[14:16]) - 555


def chain(c, e, day):
    out = {}
    for k, o, t, cl, oi in c.execute("SELECT strike, opt, datetime, close, oi FROM candles WHERE kind='option' AND underlying='NIFTY' AND expiry=? "
                                     "AND interval='1minute' AND datetime>=? AND datetime<?", (e, day + " 09:15", day + " 15:31")):
        i = mi(t)
        if not 0 <= i < 376:
            continue
        r = out.setdefault((int(round(k)), o), {"close": np.full(376, np.nan), "oi": np.full(376, np.nan)})
        r["close"][i] = cl
        r["oi"][i] = oi if oi is not None else np.nan
    return out


def index_day(c, day):
    a = np.full(376, np.nan)
    for t, cl in c.execute("SELECT datetime, close FROM candles WHERE kind='index' AND underlying='NIFTY' AND expiry='' AND strike=0 AND opt='' "
                           "AND interval='1minute' AND datetime>=? AND datetime<?", (day + " 09:15", day + " 15:31")):
        i = mi(t)
        if 0 <= i < 376:
            a[i] = cl
    return a


def last_le(arr, i):
    v = arr[: i + 1]
    v = v[np.isfinite(v)]
    return float(v[-1]) if len(v) else np.nan


def calls(ch, S0, i):
    oi = {}
    for (k, o), r in ch.items():
        x = last_le(r["oi"], i)
        if np.isfinite(x):
            oi.setdefault(k, {"CE": 0.0, "PE": 0.0})[o] += x
    if len(oi) < 5:
        return None
    ks = sorted(oi)
    k_oi = max(ks, key=lambda k: (oi[k]["CE"] + oi[k]["PE"], -abs(k - S0)))
    pain = {X: sum(oi[k]["CE"] * max(0.0, X - k) + oi[k]["PE"] * max(0.0, k - X) for k in ks) for X in ks}
    k_pain = min(ks, key=lambda X: (pain[X], abs(X - S0)))
    return k_oi, k_pain, len(ks)


def price(ch, side, S0, i, j_end, stress):
    k = int(round(S0 / 50.0) * 50)
    r = ch.get((k, side))
    if r is None or not np.isfinite(r["close"][i]):
        return None, "NO_PRICE"
    a = wk.ask(MK, float(r["close"][i]))
    last = None
    for j in range(i + 1, j_end + 1):
        p = r["close"][j]
        if not np.isfinite(p):
            continue
        b = wk.bid(MK, float(p))
        n = (b - a) * LOT - wk.charges(a, b, LOT, "NFO") - stress
        last = n
        if n <= -STOP:
            return n, "stop"
    return (last, "time") if last is not None else (None, "NO_EXIT")


def main():
    if OUT.exists():
        raise SystemExit("SN451 is run once")
    c = sqlite3.connect(DB, uri=True)
    exps = [r[0] for r in c.execute("SELECT DISTINCT expiry FROM candles WHERE kind='option' AND underlying='NIFTY' AND expiry>='2024-01-01' AND expiry<='2025-12-31'")]
    days_idx = sorted({r[0][:10] for r in c.execute("SELECT datetime FROM candles WHERE kind='index' AND underlying='NIFTY' AND expiry='' AND strike=0 AND opt='' "
                                                    "AND interval='1minute' AND datetime>='2023-12-20' AND datetime<'2026-01-01' AND datetime LIKE '% 15:29:00'")})
    rows, plac = [], []
    for e in sorted(exps):
        assert e[:4] in ("2024", "2025")
        ch = chain(c, e, e)
        if len({k for k, _o in ch}) < 9:
            continue
        idx = index_day(c, e)
        prevs = [d for d in days_idx if d < e]
        if not prevs:
            continue
        pidx = index_day(c, prevs[-1])
        prev = last_le(pidx, 375)
        row = {"day": e, "strikes": len({k for k, _o in ch})}
        for cn, i in CLOCKS.items():
            S0 = last_le(idx, i - 1)
            cl = calls(ch, S0, i - 1)
            if cl is None or not np.isfinite(S0 + prev):
                continue
            k_oi, k_pain, _n = cl
            blk = {"S0": S0, "K_OI": k_oi, "K_pain": k_pain, "dist_OI": k_oi - S0, "day_move": S0 - prev,
                   "PIN": int(np.sign(k_oi - S0)) if abs(k_oi - S0) >= 25 else 0,
                   "PIN_PAIN": int(np.sign(k_pain - S0)) if abs(k_pain - S0) >= 25 else 0,
                   "MOM": int(np.sign(S0 - prev))}
            for on, j in OUTC.items():
                Sx = last_le(idx, j - 1)
                blk[f"move_{on}"] = Sx - S0
                blk[f"closer_OI_{on}"] = bool(abs(Sx - k_oi) < abs(S0 - k_oi))
            if cn == "13:00":
                for rule in ("PIN", "PIN_PAIN", "MOM"):
                    if blk[rule] == 0:
                        continue
                    side = "CE" if blk[rule] > 0 else "PE"
                    for st in (205.0, 400.0):
                        n, why = price(ch, side, S0, i - 1, OUTC["15:00"] - 1, st)
                        blk[f"{rule}_net@{int(st)}"] = None if n is None else round(n, 1)
                        blk[f"{rule}_exit"] = why
                    for st in (205.0, 400.0):
                        n, _w = price(ch, "PE" if side == "CE" else "CE", S0, i - 1, OUTC["15:00"] - 1, st)
                        blk[f"{rule}_opposite_net@{int(st)}"] = None if n is None else round(n, 1)
            row[cn] = blk
        rows.append(row)
        # placebo: the session before expiry, same chain
        pd_ = prevs[-1]
        chp = chain(c, e, pd_)
        if len({k for k, _o in chp}) >= 5:
            pp = [d for d in days_idx if d < pd_]
            if pp:
                S0 = last_le(pidx, 224)
                prev2 = last_le(index_day(c, pp[-1]), 375)
                cl = calls(chp, S0, 224)
                if cl is not None and np.isfinite(S0 + prev2):
                    Sx = last_le(pidx, 344)
                    plac.append({"day": pd_, "expiry": e, "PIN": int(np.sign(cl[0] - S0)) if abs(cl[0] - S0) >= 25 else 0,
                                 "MOM": int(np.sign(S0 - prev2)), "move_15:00": Sx - S0})

    def hits(sel, rule, on):
        xs = [(np.sign(b[f"move_{on}"]) == b[rule]) for b in sel if b.get(rule) and b.get(f"move_{on}") is not None and b[f"move_{on}"] != 0]
        return xs

    def boot(xs, n=2000, seed=451):
        rng = random.Random(seed)
        bs = [np.mean([xs[rng.randrange(len(xs))] for _k in xs]) for _ in range(n)]
        return [round(float(np.percentile(bs, 5)), 3), round(float(np.percentile(bs, 95)), 3)]
    res = {"expiry_days": len(rows), "years": {y: sum(1 for r in rows if r["day"][:4] == y) for y in ("2024", "2025")}}
    for cn in CLOCKS:
        sel = [r[cn] for r in rows if cn in r]
        blk = {"days": len(sel)}
        for rule in ("PIN", "PIN_PAIN", "MOM"):
            for on in OUTC:
                xs = hits(sel, rule, on)
                blk[f"{rule} hit {on}"] = {"n": len(xs), "hit": round(float(np.mean(xs)), 3) if xs else None, "ci90": boot(xs) if len(xs) > 5 else None,
                                           "mean_signed_pts": round(float(np.mean([b[f"move_{on}"] * b[rule] for b in sel if b.get(rule)])), 1) if xs else None}
        both = [b for b in sel if b["PIN"] and b["MOM"]]
        blk["PIN_and_MOM_agree_share"] = round(float(np.mean([b["PIN"] == b["MOM"] for b in both])), 3) if both else None
        blk["closer_to_K_OI_15:25"] = round(float(np.mean([b["closer_OI_15:25"] for b in sel])), 3) if sel else None
        blk["median_abs_dist_OI"] = round(float(np.median([abs(b["dist_OI"]) for b in sel])), 1) if sel else None
        res[f"clock {cn}"] = blk
    sel = [r["13:00"] for r in rows if "13:00" in r]
    for rule in ("PIN", "PIN_PAIN", "MOM"):
        for st in (205, 400):
            xs = [b[f"{rule}_net@{st}"] for b in sel if b.get(f"{rule}_net@{st}") is not None]
            op = [b[f"{rule}_opposite_net@{st}"] for b in sel if b.get(f"{rule}_opposite_net@{st}") is not None]
            res[f"priced {rule} @{st}"] = {"n": len(xs), "mean": round(float(np.mean(xs))) if xs else None, "median": round(float(np.median(xs))) if xs else None,
                                           "sum": round(sum(xs)) if xs else None, "without_best": round((sum(xs) - max(xs)) / (len(xs) - 1)) if len(xs) > 1 else None,
                                           "opposite_side_mean": round(float(np.mean(op))) if op else None,
                                           "stops": sum(1 for b in sel if b.get(f"{rule}_exit") == "stop" and b.get(f"{rule}_net@{st}") is not None)}
    for rule in ("PIN", "MOM"):
        xs = [(np.sign(p["move_15:00"]) == p[rule]) for p in plac if p[rule] and p["move_15:00"] != 0]
        res[f"placebo {rule} hit 15:00 (day before expiry)"] = {"n": len(xs), "hit": round(float(np.mean(xs)), 3) if xs else None}
    p13 = res["clock 13:00"]
    res["development_pass"] = {r: bool((p13[f"{r} hit 15:00"]["hit"] or 0) >= 0.58 and (res[f"priced {r} @205"]["mean"] or -1) > 0 and (res[f"priced {r} @400"]["mean"] or -1) > 0)
                               for r in ("PIN", "PIN_PAIN", "MOM")}
    res["rows"] = rows
    res["placebo_rows"] = plac
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("rows", "placebo_rows")}, indent=1, default=float))


if __name__ == "__main__":
    main()
