"""SN16-SN18 - three new ideas on N11's own days, each scored at EVERY wallet (research only).

  SN16 extend: N11 sells many winners on a clock (45-minute time stop, trail, lock). If the trade is in profit by `x` at
       N11's exit, keep it with a trail (premium give-back or index ATR trail) until 15:10.
  SN17 reenter: after a winning N11 trade, buy again in the same direction when the index makes a new extreme beyond
       the exit level + b x ATR within `win` minutes; that leg leaves at an index trail, a 45-minute clock or 15:10.
  SN18 dte sizing: the second lot by days to expiry (cheap, high-gamma options near expiry) instead of / with volatility.
Wallets (every variant): A Rs 15k 1 lot; B Rs 20k 1 lot; C Rs 30k second lot by the sizing rule; G growth from Rs 15k
(+50% after net profit = wallet), stopped after 0-5 steps, lots floor(W / 15k) halved on a low day of the sizing rule.
One position at a time, 20% day loss limit, the strike one step out of the money when a lot costs more than the
wallet, current Zerodha charges + Rs 205 per lot per trade. Choose on three years, score the fourth, per wallet.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "2026-11-12-sn03"), str(HERE.parent / "2026-11-12-sn13")]
import sn03 as B  # noqa: E402
import sn13 as V  # noqa: E402
from sn03_run import loyo  # noqa: E402

M = B.M
YEARS = B.YEARS
STRESS = 205.0


def buy(S, i, strike, opt, wallet, lots_cap):
    for attempt in range(2):
        rec = S.option(strike, opt)
        if rec is None or not rec[6][i]:
            return None
        ask = M.ask_of(float(rec[0][3][i]))
        lots = int(min(lots_cap, math.floor(wallet / (ask * M.LOT))))
        if lots >= 1:
            return rec, ask, lots, strike
        if attempt:
            return None
        strike += M.STEP if opt == "CE" else -M.STEP


def leg(S, rec, ask, lots, i, j_n11, d, v, room, mode):
    """Walk one position. mode 'n11': N11's exit at j_n11, optionally extended (SN16). mode 'reentry': SN17's own exit."""
    a, bo, bh, bl, bc, bm, tr = rec
    qty = lots * M.LOT
    c, atr = S.F["c"], S.F["atr"]
    stop = M._ceil_tick(ask - (room - M.charges(ask, ask, qty) - STRESS * lots) / qty)
    ext, peak_b, best_u, px, j = False, ask, c[i], None, i
    for j in range(i + 1, M.EXIT_MIN + 1):
        if tr[j] and bl[j] <= stop:
            px = min(stop, bo[j])
            break
        bid = bc[j] if tr[j] else bm[j]
        best_u = max(best_u, c[j]) if d > 0 else min(best_u, c[j])
        if ext:
            if v["ext_mode"] == "give" and bid <= peak_b - v["ext_give"] * (peak_b - ask):
                px = bid
                break
            if v["ext_mode"] == "atr" and (c[j] - (best_u - d * v["ext_k"] * atr[j])) * d <= 0:
                px = bid
                break
            if j >= 355:
                px = bid
                break
        elif mode == "n11" and j >= j_n11:
            if v.get("extend") and bid >= ask * (1 + v["ext_x"]) and j < 355:
                ext = True
            else:
                px = bid
                break
        elif mode == "reentry":
            if (c[j] - (best_u - d * v["re_k"] * atr[j])) * d <= 0 or j - i >= v["re_hold"] or j >= 355:
                px = bid
                break
        peak_b = max(peak_b, bid)
    if px is None or np.isnan(px):
        px = float(bm[j]) if not np.isnan(bm[j]) else ask
    px = float(px)
    return (px - ask) * qty - M.charges(ask, px, qty) - STRESS * lots, j


def play_day(S, sigs, v, wallet, lots_cap):
    loss = 0.2 * wallet
    realized, free = 0.0, 0
    c, atr = S.F["c"], S.F["atr"]
    for sg in sorted(sigs, key=lambda x: x["i"]):
        i = sg["i"]
        if i < free or i >= M.EXIT_MIN or sg["expiry"] != S.s["expiry"]:
            continue
        got = buy(S, i, sg["strike"], sg["opt"], wallet, lots_cap)
        if got is None:
            continue
        rec, ask, lots, strike = got
        d = 1 if sg["opt"] == "CE" else -1
        net, j = leg(S, rec, ask, lots, i, min(max(sg["j"], i + 1), M.EXIT_MIN), d, v, loss + realized, "n11")
        realized += net
        free = j + 1
        if loss + realized < loss * 0.05:
            break
        if v.get("reenter") and net > 0:
            level = c[j]
            for k in range(j + 1, min(M.EXIT_MIN - 30, j + 1 + v["re_win"])):
                if (c[k] - (level + d * v["re_b"] * atr[k])) * d > 0:
                    got = buy(S, k, int(round(c[k] / M.STEP) * M.STEP), sg["opt"], wallet, lots_cap)
                    if got is None:
                        break
                    rec2, ask2, lots2, _ = got
                    net2, j2 = leg(S, rec2, ask2, lots2, k, k, d, v, loss + realized, "reentry")
                    realized += net2
                    free = j2 + 1
                    break
            if loss + realized < loss * 0.05:
                break
    return realized


def sizing_flags(vol: dict) -> dict:
    return {"vol": lambda S: bool(vol.get(S.day)),
            "dte<=2": lambda S: (date.fromisoformat(S.s["expiry"]) - date.fromisoformat(S.day)).days <= 2,
            "dte>=3": lambda S: (date.fromisoformat(S.s["expiry"]) - date.fromisoformat(S.day)).days >= 3,
            "vol&dte<=2": lambda S: bool(vol.get(S.day)) and (date.fromisoformat(S.s["expiry"]) - date.fromisoformat(S.day)).days <= 2,
            "vol|dte<=2": lambda S: bool(vol.get(S.day)) or (date.fromisoformat(S.s["expiry"]) - date.fromisoformat(S.day)).days <= 2}


def wallets(years, v, flag) -> dict:
    """Every wallet for one variant: per-year net / refilled / won / lost / none, and growth caps 0-5."""
    out = {}
    for name, W, rule in (("A 15k 1 lot", 15000.0, "one"), ("B 20k 1 lot", 20000.0, "one"), ("C 30k sized", 30000.0, "sized")):
        per = {}
        for y in YEARS:
            Y = years[y]
            n11 = Y.sigs("N11")
            nets = [play_day(S, n11.get(S.day, []), v, W, 1 if rule == "one" else (2 if flag(S) else 1)) for S in Y.ordered()]
            per[y] = {"net": round(sum(nets)), "refilled": round(sum(-x for x in nets if x < 0)), "green": sum(x > 0 for x in nets),
                      "red": sum(x < 0 for x in nets), "none": sum(x == 0 for x in nets), "worst": round(min(nets))}
        out[name] = per
    for cap in range(0, 6):
        W, steps, prog = 15000.0, 0, 0.0
        per = {y: {"net": 0.0, "refilled": 0.0, "green": 0, "red": 0, "none": 0, "worst": 0.0} for y in YEARS}
        for y in YEARS:
            Y = years[y]
            n11 = Y.sigs("N11")
            for S in Y.ordered():
                full = max(1, int(W // 15000))
                x = play_day(S, n11.get(S.day, []), v, W, full if flag(S) else max(1, full // 2))
                p = per[y]
                p["net"] += x
                p["refilled"] += max(0.0, -x)
                p["green" if x > 0 else "red" if x < 0 else "none"] += 1
                p["worst"] = min(p["worst"], x)
                prog += x
                while prog >= W and steps < cap:
                    prog -= W
                    W *= 1.5
                    steps += 1
        out[f"G grow from 15k, stop after {cap}"] = {y: {k: round(val) for k, val in per[y].items()} for y in YEARS}
    return out


def variants() -> dict:
    out = {"benchmark": {}}
    for x in (0.0, 0.10, 0.25):
        for give in (0.3, 0.5):
            out[f"SN16 extend >= +{int(x*100)}% give {give}"] = {"extend": True, "ext_x": x, "ext_mode": "give", "ext_give": give}
        for k in (3.0, 6.0):
            out[f"SN16 extend >= +{int(x*100)}% ATR trail {k}"] = {"extend": True, "ext_x": x, "ext_mode": "atr", "ext_k": k}
    for win in (30, 90):
        for b in (0.5, 1.5):
            for k, hold in ((3.0, 45), (6.0, 400)):
                out[f"SN17 reenter win {win} b {b} trail {k} hold {hold}"] = {"reenter": True, "re_win": win, "re_b": b, "re_k": k, "re_hold": hold}
    return out


if __name__ == "__main__":
    vol = V.vol_days()
    flags = sizing_flags(vol)
    years = {y: B.Year(y) for y in YEARS}
    res = {}
    for name, v in variants().items():
        res[name] = wallets(years, v, flags["vol"])
        r = res[name]
        print(f"{name:42s}", " | ".join(f"{w[:1]} {sum(r[w][y]['net'] for y in YEARS):>8}" for w in ("A 15k 1 lot", "B 20k 1 lot", "C 30k sized")),
              "| G3", sum(r["G grow from 15k, stop after 3"][y]["net"] for y in YEARS), flush=True)
    for sname in ("dte<=2", "dte>=3", "vol&dte<=2", "vol|dte<=2"):
        res[f"SN18 size by {sname}"] = wallets(years, {}, flags[sname])
        r = res[f"SN18 size by {sname}"]
        print(f"{'SN18 size by ' + sname:42s}", "C", sum(r["C 30k sized"][y]["net"] for y in YEARS), "| G3", sum(r["G grow from 15k, stop after 3"][y]["net"] for y in YEARS), flush=True)
    summary = {}
    for w in ("A 15k 1 lot", "B 20k 1 lot", "C 30k sized", "G grow from 15k, stop after 3"):
        table = {k: r[w] for k, r in res.items() if w in r and (not k.startswith("SN18") or w.startswith(("C", "G")))}
        L = loyo(table, "profit")
        summary[w] = {"loyo": L}
        print("LOYO", w, {y: (L[y]["pick"][:30], L[y]["net"]) for y in YEARS}, "sum", L["sum"]["net"], "benchmark", sum(res["benchmark"][w][y]["net"] for y in YEARS), flush=True)
    (HERE / "results.json").write_text(json.dumps({"variants": res, "loyo": summary}, indent=1), encoding="utf-8")
