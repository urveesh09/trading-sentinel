"""SN235-SN243 engine (DIAGNOSIS.md amendment), on SN221's wk3 (not edited).

hedge_path4 re-implements wk3.hedge_path with options (defaults = wk3 exactly, checked in SN235):
  band / every / lots    as wk3;
  freeze_j               expiry day: no new orders from this minute index (wk3: 315 = 14:30; 361 = checks through 15:15);
  flatten_j              expiry day: close every futures lot at this minute and trade no more (None = never);
  late_every / late_from expiry day: check every late_every minutes from minute late_from (None = no change);
  instrument "fut"       NIFTY / SENSEX futures (wk3);
             "synth"     a weekly synthetic forward (ATM call bought + put sold, or the reverse), priced at the index plus
                         carry (6.5% a year over the calendar days left), each lot-order charged as two option legs
                         (model spread at the leg premium Q_now / 2, Rs 100 stress per leg-lot, option charges with STT on
                         the sold leg), remaining lots settled at intrinsic (one sold leg at Q0 / 2 charged).
trade4 is wk3.trade3 with hedge_path4; daily4 is the daily hedged straddle (SN237): a 1-session position from each 15:15
that the next calendar day's session follows, closed at the next 15:15 or settled when that session is the expiry."""
from __future__ import annotations

import datetime as dt
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-15-sn221"))
import wk3  # noqa: E402

wk = wk3.wk
CARRY = 0.065
_OPT = {}


def opt_side(p, qty, side, exch):
    """One option order's charges (Zerodha, from the engine's options schedule)."""
    if exch not in _OPT:
        from cost_schedules import options_cost_snapshot
        _OPT[exch] = options_cost_snapshot(exch)["rates"]
    r = _OPT[exch]
    v = max(0.0, p) * qty
    brk = float(r["brokerage_flat_per_order"])
    exch_ = float(r["exchange_pct"]) * v
    sebi = float(r["sebi_pct"]) * v
    ipft = float(r.get("ipft_pct", 0.0)) * v
    stt = float(r["stt_sell_pct"]) * v if side == "sell" else 0.0
    stamp = float(r["stamp_duty_buy_pct"]) * v if side == "buy" else 0.0
    return brk + exch_ + sebi + ipft + stt + stamp + float(r["gst_pct"]) * (brk + exch_ + sebi + ipft)


DEFAULT = {"band": 0.6, "every": 15, "lots": 2, "freeze_j": wk3.FREEZE, "flatten_j": None, "late_every": None, "late_from": None,
           "instrument": "fut"}


def hedge_path4(smp, t, e, days, hp):
    hp = {**DEFAULT, **hp}
    mk, lot = smp.mk, smp.mk["lot"]
    L, band, every = hp["lots"], hp["band"], hp["every"]
    synth = hp["instrument"] == "synth"
    half = wk3.HALF[mk["name"]]
    d0 = t["entry"]
    hold = [d for d in days if d >= d0] + [e]
    n_after = {d: sum(1 for x in days if d < x) for d in hold}
    e_date = dt.date.fromisoformat(e)

    def T_of(d, j):
        if d == e:
            return max(1e-4, (360 - j) / 375.0)
        return (375 - j) / 375.0 + n_after[d] + 360 / 375.0 + wk3.NIGHT * (n_after[d] + 1)

    S0 = t["S0"] or wk.idx_px(smp.data, d0) or float(t["K0"])
    T0 = T_of(d0, wk.I_ENTRY)
    sig = t["Q"] / (0.7979 * S0 * math.sqrt(T0))
    legs = t["legs"]
    h, cash, costs, orders, fallback = 0, 0.0, 0.0, 0, 0
    basis = None
    pending = None
    marks, out = {}, {}

    def leg_p(d, j):
        return max(wk.TICK, t["Q"] / 2 * math.sqrt(max(T_of(d, j), 1e-4) / T0))

    def synth_px(S, d):
        days_left = max(0, (e_date - dt.date.fromisoformat(d)).days)
        return S * (1 + CARRY * days_left / 365.0)

    def order_cost(px, q, d, j):
        n = abs(q)
        if not synth:
            side = "buy" if q > 0 else "sell"
            return wk3.fut_charges(px, n, side, mk) + wk3.FUT_STRESS * n + (wk3.OPEN_PEN * n if j < wk2_open() else 0.0)
        p = leg_p(d, j)
        qty = n * lot
        c = opt_side(p, qty, "buy", mk["exch"]) + opt_side(p, qty, "sell", mk["exch"])
        return c + 2 * wk.SCORE_STRESS * n + (2 * wk3.OPEN_PEN * n if j < wk2_open() else 0.0)

    def spread_half(d, j):
        if not synth:
            return half
        return wk._spread(mk, leg_p(d, j))            # two legs' half-spreads

    def px_at(F, S, j, d):
        nonlocal basis
        if synth:
            return (synth_px(S, d), False) if S is not None else (None, False)
        f = F[j] if F is not None and F[j] == F[j] else None
        if f is not None and S is not None:
            basis = f - S
        if f is not None:
            return f, False
        if S is not None and basis is not None:
            return S + basis, True
        return None, False

    def close_value(f, d, j):
        if h == 0:
            return cash
        hs = spread_half(d, j)
        if h > 0:
            p = f - hs
            c = order_cost(p, -h, d, 999) - (0.0 if synth else 0.0)
            return cash + h * lot * p - c
        p = f + hs
        return cash + h * lot * p - order_cost(p, -h, d, 999)

    def execute(q, f, d, j):
        nonlocal h, cash, costs, orders
        hs = spread_half(d, j)
        p = f + hs if q > 0 else f - hs
        c = order_cost(p, q, d, j)
        cash -= q * lot * p
        cash -= c
        costs += c
        orders += 1
        h += q

    flattened = False
    for d in hold:
        a = smp.data["idx"].get(d)
        F = None if synth else smp.fut.series(e, d)
        j0 = wk.I_ENTRY + 1 if d == d0 else 0
        last_f = None
        for j in range(j0, wk.NM):
            S = float(a[j]) if a is not None and a[j] == a[j] else None
            f, fb = px_at(F, S, j, d)
            if f is not None:
                last_f = f
            if pending is not None and f is not None:
                execute(pending, f, d, j)
                fallback += int(fb)
                pending = None
            if d != d0 and d != e and j == wk.I_ENTRY:
                marks[d] = close_value(last_f, d, j) if last_f is not None else None
            if d == e and hp["flatten_j"] is not None and j >= hp["flatten_j"]:
                if not flattened and h != 0 and f is not None:
                    execute(-h, f, d, j)
                if f is not None or h == 0:
                    flattened = True
                continue
            if d == e and j >= hp["freeze_j"]:
                continue
            ev = every
            if d == e and hp["late_every"] and hp["late_from"] is not None and j >= hp["late_from"]:
                ev = hp["late_every"]
            if S is not None and pending is None and (j % ev == 0 or ev == 1):
                dl = L * wk3._delta(legs, S, T_of(d, j), sig)
                if abs(dl + h) > band:
                    target = -int(round(dl))
                    if target != h:
                        pending = target - h
        if d == e:
            if synth:
                ST = wk.settle_px(smp.data, e)
                v = cash + h * lot * ST
                if h:
                    v -= opt_side(t["Q"] / 2, abs(h) * lot, "sell", mk["exch"])
                out["settle"] = v
            else:
                w = []
                for j in range(*wk3.TWAP):
                    S = float(a[j]) if a is not None and a[j] == a[j] else None
                    f = F[j] if F is not None and F[j] == F[j] else (S + basis if S is not None and basis is not None else None)
                    if f is not None:
                        w.append(f)
                out["settle"] = close_value(sum(w) / len(w), d, 999) if w else (close_value(last_f, d, 999) if last_f is not None else cash)
    out.update(marks=marks, orders=orders, costs=round(costs, 2), fallback=fallback, end_lots=h)
    return out


def wk2_open():
    return wk3.wk2.OPEN_MIN


def hkey(hp):
    hp = {**DEFAULT, **hp}
    return tuple(sorted(hp.items()))


def trade4(smp, e, days, struct, k, exit_name, hp, flt_name="none"):
    """wk3.trade3 with hedge_path4 (hp = None: no hedge)."""
    exit_, stop, gate = wk3.EXITS[exit_name]
    flt = wk3.FILTERS[flt_name]
    t = wk3.base_trade(smp, e, days, struct, k)
    if t is None or not wk3.passes(smp, t["entry"], flt):
        return None
    if exit_ == "pre" and t["k"] == 1:
        return None
    L = hp.get("lots", 2) if hp is not None else 1
    H = None
    if hp is not None:
        cache = smp.__dict__.setdefault("hpaths4", {})
        key = (e, struct, k, hkey(hp))
        if key not in cache:
            cache[key] = hedge_path4(smp, t, e, days, hp)
        H = cache[key]
    lot = smp.mk["lot"]
    credit_rs = t["credit_pts"] * lot * L
    legs = t["legs"]
    Kc, Kp, Q = legs[0][0], legs[1][0], t["Q"]
    d0 = t["entry"]
    marks = {d0: L * t["marks"][d0]}

    def done(v, d, why):
        marks[d] = v
        return {"entry": d0, "expiry": e, "exit_day": d, "reason": why, "net": v, "Q": Q, "k": t["k"], "lots": L, "marks": marks,
                "orders": H["orders"] if H else 0, "hedge_costs": H["costs"] if H else 0.0}

    for d in [x for x in days if x > d0]:
        if d not in t["marks"]:
            if exit_ == "pre" and d == days[-1]:
                return None
            continue
        hv = (H["marks"].get(d) or 0.0) if H else 0.0
        v = L * t["marks"][d] + hv
        marks[d] = v
        if stop is not None and v <= -stop * credit_rs:
            return done(v, d, "stop")
        if gate is not None and exit_ == "settle" and d == days[-1]:
            sg = wk.idx_px(smp.data, d)
            if sg is not None and min(Kc - sg, sg - Kp) < gate * Q:
                return done(v, d, "gate")
        if exit_ == "pre" and d == days[-1]:
            return done(v, d, "pre")
    if exit_ == "pre":
        return None
    return done(L * t["marks"][e] + (H["settle"] if H else 0.0), e, "settle")


def book4(smp, struct, k, exit_name, hp, flt_name="none"):
    out = []
    for e, days in smp.weeks:
        r = trade4(smp, e, days, struct, k, exit_name, hp, flt_name)
        if r and r.get("net") is not None:
            out.append(r)
    return out


def daily4(smp, hp, struct="STRADDLE"):
    """SN237: one 1-session hedged straddle from every 15:15 followed by the next calendar day's session."""
    out = []
    for e, days in smp.weeks:
        seq = list(days) + [e]
        for i, d in enumerate(days):
            nxt = seq[i + 1]
            if (dt.date.fromisoformat(nxt) - dt.date.fromisoformat(d)).days != 1:
                continue
            k = len(days) - i
            t = wk3.base_trade(smp, e, days, struct, k)
            if t is None or t["entry"] != d:
                continue
            L = hp.get("lots", 2)
            cache = smp.__dict__.setdefault("hpaths4", {})
            key = (e, struct, k, hkey(hp))
            if key not in cache:
                cache[key] = hedge_path4(smp, t, e, days, hp)
            H = cache[key]
            if nxt == e:
                v = L * t["marks"][e] + H["settle"]
            else:
                if nxt not in t["marks"] or H["marks"].get(nxt) is None:
                    continue
                v = L * t["marks"][nxt] + H["marks"][nxt]
            out.append({"entry": d, "expiry": e, "exit_day": nxt, "net": v, "lots": L, "k": k, "Q": t["Q"],
                        "marks": {d: L * t["marks"][d], nxt: v}, "orders": H["orders"], "hedge_costs": H["costs"]})
    return out
