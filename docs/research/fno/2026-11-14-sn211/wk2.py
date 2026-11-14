"""SN211-SN220 minute-level exit engine (PLAN.md), built on SN201's wk.py.

simulate() replays one weekly position minute by minute from 15:16 on the entry day to the last session before
expiry. It keeps the base rules of wk.trade exactly (the 15:15-mark stop on the lean data, the pre-expiry 15:15 exit,
settlement), so a rule that never fires returns wk.trade's result. Smart rules (any combination):
  breach b  - the index beyond a short strike by b*Q;           loss L   - value <= -L x credit (every minute);
  profit p  - value >= p x credit;                               speed z  - |index move over 30 minutes| >= z*Q;
  protect b - at a breach by b*Q buy the wing 0.5*Q beyond that short strike instead of exiting (once per side);
  calendar  - skip a week whose holding window holds a scheduled shock day;
  gate c    - (settle base) at the 15:15 mark before expiry, close unless the index is >= c*Q inside both short strikes.
A trigger at minute j executes at the first minute >= j + delay where every short leg printed within FRESH minutes;
exits / hedges before 09:20 pay OPEN_PEN per leg-lot extra; a trigger late in the day executes next morning."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-14-sn201"))
import wk  # noqa: E402

LOCAL = HERE / "_local"
EXAM_FULL = {"NIFTY": LOCAL / "mirror-nifty-exam-full.sqlite", "SENSEX": LOCAL / "mirror-sensex-exam-full.sqlite"}
FRESH = 3
OPEN_PEN = 100.0
OPEN_MIN = 5                 # 09:15 .. 09:19
SPEED_WIN = 30
WK_S = ("STRANGLE 0.5", 3, "settle", 1.0)
WK_S_PRE = ("STRANGLE 0.5", 3, "pre", 1.0)
BASES = {"settle": WK_S, "pre": WK_S_PRE}

RBI = ["2021-12-08", "2022-02-10", "2022-04-08", "2022-06-08", "2022-08-05", "2022-09-30", "2022-12-07", "2023-02-08",
       "2023-04-06", "2023-06-08", "2023-08-10", "2023-10-06", "2023-12-08", "2024-02-08", "2024-04-05", "2024-06-07",
       "2024-08-08", "2024-10-09", "2024-12-06", "2025-02-07", "2025-04-09", "2025-06-06", "2025-08-06", "2025-10-01",
       "2025-12-05", "2026-02-06", "2026-04-08", "2026-06-05", "2026-08-05", "2026-10-07"]
BUDGET = ["2022-02-01", "2023-02-01", "2024-02-01", "2024-07-23", "2025-02-01", "2026-02-01"]
ELECTION = ["2024-06-04"]
EVENTS = set(RBI + BUDGET + ELECTION)


class Minutes:
    """Option minute closes on demand, {day: array(375)} per (expiry, strike, opt), sessions before expiry."""

    def __init__(self, source):
        self.source = source
        self.cache, self._cons = {}, {}
        self.paths = list(wk.DEV_SOURCES.values()) if source == "dev" else [EXAM_FULL[source]]

    def _con(self, p):
        if p not in self._cons:
            self._cons[p] = sqlite3.connect(f"file:{Path(p).as_posix()}?mode=ro", uri=True)
        return self._cons[p]

    def leg(self, e, k, o):
        key = (e, int(k), o)
        if key in self.cache:
            return self.cache[key]
        order = self.paths
        if self.source == "dev" and e[:4] in wk.DEV_SOURCES:
            first = wk.DEV_SOURCES[e[:4]]
            order = [first] + [p for p in self.paths if p != first]
        out = {}
        for p in order:
            if self.source == "dev":
                rows = self._con(p).execute("SELECT datetime, close FROM candles WHERE kind='option' AND expiry=? AND strike=? AND opt=?",
                                            (e, float(k), o)).fetchall()
            else:
                rows = self._con(p).execute("SELECT datetime, close FROM candles WHERE kind='option' AND underlying=? AND expiry=? "
                                            "AND strike=? AND opt=? AND interval='1minute'", (self.source, e, float(k), o)).fetchall()
            for dt, c in rows:
                d = dt[:10]
                m = wk._minute(dt)
                if d < e and c is not None and 0 <= m < wk.NM:
                    out.setdefault(d, np.full(wk.NM, np.nan))[m] = float(c)
            if out:
                break
        self.cache[key] = out
        return out


def _lean_mark(mk, data, e, d, legs, fills):
    """wk.trade's 15:15 mark (lean data, 10-minute lookback, intrinsic + 0.5 when a leg is missing); None if no index."""
    s = wk.idx_px(data, d)
    raws = []
    for kk, o, _s in legs:
        r = wk.opt_px(data, e, d, kk, o)
        if r is None:
            if s is None:
                return None
            r = (max(0.0, s - kk) if o == "CE" else max(0.0, kk - s)) + 0.5
        raws.append(r)
    return raws


def simulate(mk, data, mins, e, days, base, rule=None, stress=wk.SCORE_STRESS, delay=1, open_pen=OPEN_PEN, record=False):
    s_, k_, ex, st = base
    t = wk.trade(mk, data, e, days, k_, s_, ex, st, stress)
    if not t or "net" not in t or t["net"] is None:
        return None
    rule = rule or {}
    d0 = t["entry"]
    if rule.get("calendar") and any(d0 <= d <= e for d in EVENTS):
        return {"skip": "calendar", "entry": d0, "expiry": e}
    if not rule and not record:
        return t
    legs = list(t["legs"])
    raws0 = [wk.opt_px(data, e, d0, kk, o) for kk, o, _s in legs]
    fills = [wk.bid(mk, r) if sg < 0 else wk.ask(mk, r) for (kk, o, sg), r in zip(legs, raws0)]
    lot = mk["lot"]
    credit_rs = t["credit_pts"] * lot
    Q = t["Q"]
    Kc, Kp = legs[0][0], legs[1][0]
    shorts = [(kk, o) for kk, o, sg in legs if sg < 0]
    px = {(kk, o): r for (kk, o, _s), r in zip(legs, raws0)}
    seen = {(kk, o): None for kk, o, _s in legs}
    ser = {(kk, o): mins.leg(e, kk, o) for kk, o, _s in legs}
    need_value = record or "loss" in rule or "profit" in rule
    pb = rule.get("protect")
    protected = set()
    adj = 0.0
    pending = None
    S_list = []
    g = 0
    out = dict(t)
    out.update(marks={d0: t["marks"][d0]}, reason=None, rule_fired=None, hedges=0)
    rec = {"mae": 0.0, "close": {}, "open": {}, "first_breach": None} if record else None
    hold = [d for d in days if d >= d0]

    def value(raws):
        return wk._value(mk, legs, fills, raws, stress)

    def finish(net, d, j, reason):
        out.update(net=net + adj, exit_day=d, exit_minute=j, reason=reason)
        out["marks"][d] = net + adj
        if record:
            out["record"] = rec
        return out

    for d in hold:
        a = data["idx"].get(d)
        j0 = wk.I_ENTRY + 1 if d == d0 else 0
        first_fresh = None
        for j in range(j0, wk.NM):
            for key in px:
                sr = ser.get(key)
                if sr is None:
                    sr = ser[key] = mins.leg(e, key[0], key[1])
                v = sr.get(d)
                if v is not None and v[j] == v[j]:
                    px[key], seen[key] = float(v[j]), (d, j)
            fresh = all(seen[sk] is not None and seen[sk][0] == d and j - seen[sk][1] < FRESH for sk in shorts)
            S = float(a[j]) if a is not None and a[j] == a[j] else None
            if S is not None:
                S_list.append(S)
            raws = [px[(kk, o)] for kk, o, _s in legs]
            # --- base: the 15:15 mark on the lean data (exactly wk.trade) ---
            if j == wk.I_ENTRY and d > d0:
                lr = _lean_mark(mk, data, e, d, legs, fills)
                if lr is not None:
                    v = value(lr)
                    out["marks"][d] = v + adj
                    if st is not None and v <= -st * credit_rs:
                        return finish(v, d, j, "stop")
                    if "gate" in rule and ex == "settle" and d == days[-1]:       # SN217: hold into expiry only when safe
                        sg = wk.idx_px(data, d)
                        if sg is not None and min(Kc - sg, sg - Kp) < rule["gate"] * Q:
                            out["rule_fired"] = "gate"
                            return finish(v, d, j, "gate")
                    if ex == "pre" and d == days[-1]:
                        return finish(v, d, j, "pre")
                elif ex == "pre" and d == days[-1]:
                    return None
            if ex == "pre" and d == days[-1] and j >= wk.I_ENTRY:
                break
            # --- execute a pending action ---
            if pending is not None and g >= pending[1] and fresh:
                pen = open_pen * len(legs) if j < OPEN_MIN else 0.0
                if pending[0] == "exit":
                    return finish(value(raws) - pen, d, j, "rule:" + pending[2])
                side = pending[2]
                kw = (Kc + wk.dist(mk, 0.5 * Q), "CE") if side == "CE" else (Kp - wk.dist(mk, 0.5 * Q), "PE")
                wv = mins.leg(e, kw[0], kw[1]).get(d)
                wp = None
                if wv is not None:
                    for jj in range(j, max(-1, j - 5), -1):
                        if wv[jj] == wv[jj]:
                            wp = float(wv[jj])
                            break
                if wp is None:
                    out["hedge_failed"] = True
                    return finish(value(raws) - pen, d, j, "rule:protect-fallback")
                legs.append((kw[0], kw[1], 1))
                fills.append(wk.ask(mk, wp))
                px[kw], seen[kw], ser[kw] = wp, (d, j), mins.leg(e, kw[0], kw[1])
                protected.add(side)
                adj -= open_pen if j < OPEN_MIN else 0.0
                out["hedges"] += 1
                pending = None
                raws = [px[(kk, o)] for kk, o, _s in legs]
            v_now = value(raws) if need_value else None
            if record:
                rec["mae"] = min(rec["mae"], v_now)
                if fresh and first_fresh is None:
                    first_fresh = v_now
                    rec["open"][d] = v_now
                rec["close"][d] = v_now
                if rec["first_breach"] is None and S is not None and (S >= Kc or S <= Kp):
                    rec["first_breach"] = {"day": d, "minute": j, "value": v_now}
            # --- smart triggers ---
            if pending is None and S is not None:
                why = None
                if "breach" in rule and (S >= Kc + rule["breach"] * Q or S <= Kp - rule["breach"] * Q):
                    why = "breach"
                elif "loss" in rule and v_now <= -rule["loss"] * credit_rs:
                    why = "loss"
                elif "profit" in rule and v_now >= rule["profit"] * credit_rs:
                    why = "profit"
                elif "speed" in rule and len(S_list) > SPEED_WIN and abs(S - S_list[-1 - SPEED_WIN]) >= rule["speed"] * Q:
                    why = "speed"
                if why:
                    pending = ("exit", g + delay, why)
                    out["rule_fired"] = why
                elif pb is not None:
                    if S >= Kc + pb * Q and "CE" not in protected:
                        pending = ("protect", g + delay, "CE")
                    elif S <= Kp - pb * Q and "PE" not in protected:
                        pending = ("protect", g + delay, "PE")
            g += 1
    if ex == "pre":
        return None
    S_T = wk.settle_px(data, e)
    return finish(wk._settle_value(mk, legs, fills, S_T, stress), e, None, "settle")


def book2(mk, data, mins, weeks, base, rule=None, **kw):
    out = []
    for e, days in weeks:
        r = simulate(mk, data, mins, e, days, base, rule, **kw)
        if r and "net" in r and r["net"] is not None:
            out.append(r)
    return out


def summary(trades):
    s = wk.stats(trades)
    mo = {}
    for t in trades:
        mo[t["exit_day"][:7]] = mo.get(t["exit_day"][:7], 0.0) + t["net"]
    x = np.sort([t["net"] for t in trades])
    s.update(worst_month=round(min(mo.values())) if mo else 0, months_positive=f"{sum(v > 0 for v in mo.values())} of {len(mo)}",
             cvar5=round(float(x[:max(1, len(x) // 20)].mean())) if len(x) else 0,
             fired=sum(1 for t in trades if t.get("rule_fired")), hedges=sum(t.get("hedges", 0) for t in trades))
    for key in ("max_loss_median", "max_loss_max"):
        s.pop(key, None)
    return s


def name(rule):
    return " + ".join(f"{k} {v}" if v is not True else k for k, v in rule.items()) if rule else "none"
