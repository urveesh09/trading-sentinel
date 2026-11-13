"""SN95 - remaining movement against the option price (PLAN.md).
Buy the ATM straddle when options look cheap against the movement (ratio in the causal top q); sell a defined-risk
iron fly (short ATM straddle, long +-200 wings) when they look rich (bottom q). Ratios: R_today (today's realised
1-minute sigma / the straddle's implied per-minute sigma) and R_atr (yesterday's daily ATR% scaled / implied).
Admission by an expanding quantile of all earlier sessions at the same clock (>= 60). Controls: the same structure
every day, and random admission at rate q. Wallets A / B / C; stress Rs 100 per leg-lot (house) and Rs 205 (strict).
Fly margin = its maximum loss (a proxy; not broker-verified)."""
from __future__ import annotations

import itertools
import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402

M = C.M
CLOCKS = {"10:00": 45, "11:00": 105, "12:30": 195}
QS = (0.20, 0.33)
EXITS = {"hold": None, "60m": 60}
WING = 200
WALLETS = {"A 15k 1 lot": (15000.0, "one"), "B 20k 1 lot": (20000.0, "one"), "C 30k sized": (30000.0, "sized")}


def bid_at(rec, j):
    v = rec[4][j] if rec[6][j] else rec[5][j]
    return None if np.isnan(v) else float(v)


def ask_at(rec, j):
    a = rec[0][3]
    col = a[: j + 1]
    ok = np.flatnonzero(~np.isnan(col))
    return None if not len(ok) else M.ask_of(float(col[ok[-1]]))


def legs(S, i, side):
    c = S.F["c"][i]
    K = int(round(c / M.STEP) * M.STEP)
    want = [(K, "CE", +1), (K, "PE", +1)] if side == "buy" else [(K, "CE", -1), (K, "PE", -1), (K + WING, "CE", +1), (K - WING, "PE", +1)]
    out = []
    for k, opt, q in want:
        rec = S.option(k, opt)
        if rec is None or not rec[6][i]:
            return None
        px = M.ask_of(float(rec[0][3][i])) if q > 0 else float(rec[4][i])
        out.append((rec, q, px))
    return out


def play(S, i, side, hold, lots, room, leg_stress, wallet):
    L_ = legs(S, i, side)
    if L_ is None:
        return None
    qty = lots * M.LOT
    credit = sum(-q * px for _r, q, px in L_)          # > 0 for the fly
    if side == "sell":
        max_loss = (WING - credit) * qty if credit > 0 else None
        if max_loss is None or max_loss <= 0 or max_loss > wallet:
            return None
    elif -credit * qty > wallet:                         # the straddle's premium must fit the wallet
        return None
    end = min(C.FLAT, i + hold) if hold else C.FLAT
    n_legs = len(L_)

    def value(j):
        tot = 0.0
        fees = 0.0
        for rec, q, px in L_:
            if q > 0:
                x = bid_at(rec, j)
                if x is None:
                    return None
                tot += (x - px) * qty
                fees += M.charges(px, x, qty)
            else:
                x = ask_at(rec, j)
                if x is None:
                    return None
                tot += (px - x) * qty
                fees += M.charges(x, px, qty)
        return tot - fees - leg_stress * lots * n_legs
    last = None
    for j in range(i + 1, end + 1):
        v = value(j)
        if v is None:
            continue
        last = v
        if v <= -room:
            return v, j
    return (last if last is not None else -leg_stress * lots * n_legs), end


def features():
    """(day, clock) -> {R_today, R_atr} and causal admission flags per (feature, q, top/bottom)."""
    Ys = C.years()
    rows = []
    for y in C.YEARS:
        for S in Ys[y].ordered():
            for cn, i in CLOCKS.items():
                rows.append((S.day, cn, C.r_today(S, i), C.r_atr(S, i)))
    hist = {(cn, f): [] for cn in CLOCKS for f in ("R_today", "R_atr")}
    adm = {}
    for day, cn, rt, ra in rows:
        for f, x in (("R_today", rt), ("R_atr", ra)):
            h = hist[(cn, f)]
            if x is not None and len(h) >= 60:
                for q in QS:
                    adm[(day, cn, f, q, "top")] = x >= np.quantile(h, 1 - q)
                    adm[(day, cn, f, q, "bottom")] = x <= np.quantile(h, q)
            if x is not None:
                h.append(x)
    return rows, adm


def table(admit, side, cn, hold, wallet, kind, leg_stress, day_ok):
    Ys = C.years()
    per = {}
    for y in C.YEARS:
        nets, trades = [], 0
        for S in Ys[y].ordered():
            if not day_ok(S.day):
                continue
            x = 0.0
            if admit(S.day):
                lots = 2 if (kind == "sized" and C.L.vday_of(S.day, {})) else 1
                got = play(S, CLOCKS[cn], side, hold, lots, 0.2 * wallet, leg_stress, wallet)
                if got is not None:
                    x = got[0]
                    trades += 1
            nets.append(x)
        per[y] = {"net": round(sum(nets)), "green": sum(v > 0 for v in nets), "red": sum(v < 0 for v in nets),
                  "none": sum(v == 0 for v in nets), "refilled": round(sum(-v for v in nets if v < 0)), "days": len(nets),
                  "trades": trades}
    return per


if __name__ == "__main__":
    out_path = HERE / "results-sn95.json"
    if out_path.exists():
        raise SystemExit("SN95 is scored once")
    rows, adm = features()
    res = {"admission_counts": {}, "sides": {}}
    for day_name, day_ok in (("gold-free", C.gold_free), ("all days", lambda d: C.adx(d) is not None)):
        for side, where in (("buy", "top"), ("sell", "bottom")):
            real, uncond, rnd = {}, {}, {}
            for f, cn, q, (en, hold) in itertools.product(("R_today", "R_atr"), CLOCKS, QS, EXITS.items()):
                k = f"{side} {f} {cn} q{q} {en}"
                real[k] = (lambda d, f=f, cn=cn, q=q: adm.get((d, cn, f, q, where), False), cn, hold)
                rng = random.Random(f"95|{k}")
                draws = {}
                rnd[k] = (lambda d, q=q, draws=draws, rng=rng: draws.setdefault(d, rng.random() < q), cn, hold)
            for cn, (en, hold) in itertools.product(CLOCKS, EXITS.items()):
                uncond[f"{side} every day {cn} {en}"] = (lambda d: True, cn, hold)
            out = {}
            for stress_name, ls in (("house 100/leg", 100.0), ("strict 205/leg", 205.0)):
                T = {g: {k: table(a, side, cn, hold, 15000.0, "one", ls, day_ok) for k, (a, cn, hold) in grp.items()}
                     for g, grp in (("real", real), ("random admission", rnd), ("every day", uncond))}
                Ls = {g: C.loyo(t, "profit") for g, t in T.items()}
                pick_w = {}
                for wname, (W, kind) in WALLETS.items():
                    pick_w[wname] = sum(table(real[Ls["real"][y]["pick"]][0], side, real[Ls["real"][y]["pick"]][1],
                                              real[Ls["real"][y]["pick"]][2], W, kind, ls, day_ok)[y]["net"] for y in C.YEARS)
                out[stress_name] = {"tables": T, "loyo": Ls, "heldout_picks_by_wallet": pick_w}
                print(f"=== SN95 {day_name} {side} [{stress_name}]")
                for k, per in sorted(T["real"].items(), key=lambda kv: -C.tot(kv[1]))[:5]:
                    print(f"  {k:36s} {[per[y]['net'] for y in C.YEARS]} sum {C.tot(per):>8} trades {sum(per[y]['trades'] for y in C.YEARS)}")
                for g, L_ in Ls.items():
                    print(f"  LOYO {g:18s} sum {L_['sum']['net']:>8}", {y: (L_[y]['pick'][-22:], L_[y]['net']) for y in C.YEARS})
                print("  held-out picks by wallet", pick_w, flush=True)
            h = out["house 100/leg"]["loyo"]
            held = [h["real"][y]["net"] for y in C.YEARS]
            out["verdict"] = {"held_out_sum": h["real"]["sum"]["net"], "years": held,
                              "beats_random": h["real"]["sum"]["net"] > h["random admission"]["sum"]["net"],
                              "beats_every_day": h["real"]["sum"]["net"] > h["every day"]["sum"]["net"],
                              "strict_sum": out["strict 205/leg"]["loyo"]["real"]["sum"]["net"]}
            out["verdict"]["PASS"] = (out["verdict"]["held_out_sum"] > 0 and sum(x > 0 for x in held) >= 3 and
                                      out["verdict"]["beats_random"] and out["verdict"]["beats_every_day"] and out["verdict"]["strict_sum"] > 0)
            print("  VERDICT", out["verdict"], flush=True)
            res["sides"][f"{day_name} | {side}"] = out
    out_path.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
