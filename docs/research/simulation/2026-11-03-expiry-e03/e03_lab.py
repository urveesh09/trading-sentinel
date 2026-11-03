"""E02's tape, fills, fees, cash book and brakes, with exits that let a winner run.

Everything that decides a trade reads the completed bar and earlier bars; fills are the next
bar's open (ordinary), with a wider spread and a tick/1% (adverse), or the next bar's worst
high/low (catastrophe), exactly as E02. Exit additions, all off by default (= E02):

  bank_mult    at this multiple of entry, sell the fewest whole lots whose proceeds return the
               ticket's whole cost (needs two or more lots); the rest is a free runner
  runner_keep  once the ticket is banked, or has gained runner_arm, its stop is this share of
               the peak (a wider floor than E02's keep, so a runner is not shaken out)
  hold_armed   E02's idle time exit only while the ticket's peak gain is below ``arm``
  ivrv_max     entry only when the option's implied volatility over the index's realized
               volatility of the last 60 minutes is at most this (both read at the decision)
  max_lots     lots per ticket inside the same reserve (E02 R3: one)
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-03-expiry-e02"))
import data as D          # noqa: E402
import e02_lab as E       # noqa: E402

LOT, ORDER = E.LOT, E.ORDER
YEAR_MIN = 375 * 252
OI_SOURCE = HERE.parent / "2026-11-03-expiry-e02/_local"
PARTIAL = ("BANK", "TARGET_BASE")     # one-shot partial sales: an unfilled one is dropped, not chased


@dataclass(frozen=True)
class Hero(E.Rule):
    max_lots: int = 1
    bank_mult: float = 0.0
    runner_keep: float = 0.0
    runner_arm: float = 1.0
    hold_armed: bool = False
    ivrv_max: float = 0.0
    split: bool = False         # at E02's target sell half the lots; the rest become a runner
    runner_floor: float = 1.0   # the runner's stop never below this multiple of entry
    hero_target: float = 0.0    # >0: the runner is sold at this gain (9 = 10x)
    solo_runner: bool = False   # a one-lot ticket at E02's target is not sold: it becomes the runner itself


R3 = dict(setup="PULLBACK", look=10, efficiency=0.7, stretch=4.0, premium_low=5.0, premium_high=20.0, option_rise=0.0,
          stop=0.4, arm=0.4, keep=0.6, target=1.0, hold=8, start=780, end=900, slots=2, underlying_stop=2.0, reach=1.0)


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs(S, K, T, v, call):
    sd = v * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    return S * ncdf(d1) - K * ncdf(d2) if call else K * ncdf(-d2) - S * ncdf(-d1)


def implied(price, S, K, T, call):
    if T <= 0 or price <= 0:
        return float("nan")
    lo, hi = 1e-3, 5.0
    if bs(S, K, T, hi, call) < price:
        return float("nan")
    for _ in range(50):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if bs(S, K, T, mid, call) < price else (lo, mid)
    return (lo + hi) / 2


def rv60(t, i):
    w = t.close[max(0, i - 60):i + 1]
    if len(w) < 61 or not np.isfinite(w).all():
        return float("nan")
    return float(np.std(np.diff(np.log(w))) * math.sqrt(YEAR_MIN))


def ivrv(t, i, j):
    r = rv60(t, i)
    ask = t.q[i, j, 3]
    if not (np.isfinite(r) and r > 0 and np.isfinite(ask)):
        return float("nan")
    return implied(float(ask), float(t.close[i]), float(t.strikes[j]), (930 - t.minute[i]) / YEAR_MIN, t.kinds[j] == 1) / r


def oi_snapshots(t, year):
    """Open interest of every contract on each completed bar (rows as the tape's), read once per tape."""
    if getattr(t, "oi", None) is not None:
        return t.oi
    import sqlite3
    c = sqlite3.connect((OI_SOURCE / f"{year}.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
    rows = c.execute("SELECT strike, opt, datetime, oi FROM candles WHERE kind='option' AND datetime BETWEEN ? AND ?",
                     (t.day + " 09:15:00", t.day + " 15:29:00")).fetchall()
    c.close()
    index = {(float(s), 1 if o == 1 else -1): j for j, (s, o) in enumerate(zip(t.strikes, t.kinds))}
    oi = np.full((t.n, len(t.strikes)), np.nan)
    for strike, opt, stamp, v in rows:
        j = index.get((float(strike), 1 if opt == "CE" else -1))
        k = (int(stamp[11:13]) - 9) * 60 + int(stamp[14:16]) - 15
        if j is not None and 0 <= k < t.n and v is not None and v >= 0:
            oi[k, j] = v
    t.oi = oi
    return oi


def wall_directions(t, rule):
    """First completed close through the largest-OI call (UP) or put (DOWN) strike, future agreeing; once a side a day."""
    oi = t.oi
    out = np.zeros(t.n, dtype=np.int8)
    done = set()
    def wall(k, d):
        m = (t.kinds == d) & np.isfinite(oi[k])
        return float(t.strikes[m][np.argmax(oi[k][m])]) if m.any() else None
    for i in range(int(np.searchsorted(t.minute, rule.start)), int(np.searchsorted(t.minute, rule.end))):
        c, p, fc, fp = t.close[i], t.close[i - 1], t.f[i, 3], t.f[i - 1, 3]
        if not np.isfinite([c, p, fc, fp]).all():
            continue
        for d in (1, -1):
            if d in done:
                continue
            now_wall, prev_wall = wall(i, d), wall(i - 1, d)
            if now_wall is None or prev_wall is None:
                continue
            if d * (c - now_wall) > 0 and d * (p - prev_wall) <= 0 and d * (fc - fp) > 0:
                done.add(d); out[i] = d
                break
    return out


def directions(t, rule):
    return wall_directions(t, rule) if rule.setup == "WALL" else E.directions(t, rule)


def choose(t, i, d, rule, budget, cash):
    """E02's pick (nearest eligible OTM in the band and reach, fee-inclusive limit), lots capped at max_lots.

    Never beyond four strikes: the download holds every strike within four of the day's range, so a farther
    strike would exist only on days that later moved there."""
    picked = E.choose(t, i, d, rule, budget, cash)
    if picked is None:
        return None
    j, lots, limit = picked
    if d * (t.strikes[j] - t.close[i]) > 200:
        return None
    if rule.ivrv_max:
        x = ivrv(t, i, j)
        if not np.isfinite(x) or x > rule.ivrv_max:
            return None
    lots = min(lots, rule.max_lots)
    ask = E.up(float(t.q[i, j, 3]) + E.half(float(t.q[i, j, 3])))
    room = min(budget, cash)
    while lots:
        limit = E.down(min(ask * 1.1, (room - ORDER - lots * ORDER) / (lots * LOT * (1 + E.BUY_RATE))))
        if limit >= ask and E.reserve(limit, lots) <= room + .01:
            return j, lots, limit
        lots -= 1
    return None


def recover_lots(pos, bid):
    paid = pos["entry"] * pos["lots"] * LOT + E.fee(pos["entry"], pos["lots"] * LOT, True)
    for take in range(1, pos["open"]):
        if bid * take * LOT - E.fee(bid, take * LOT, False) - (pos["open"] - take) * ORDER >= paid:
            return take
    return 0


def run_day(t, rule, scenario="ordinary", cash=E.START_CASH, budget=E.BUDGET, details=False):
    dirs = directions(t, rule)
    spent = 0.0; positions = []; next_i = 0; pending_entry = None; pending_exit = None; pos = None
    rejected = 0; marks = []
    for i in range(int(np.searchsorted(t.minute, rule.start)), t.n):
        if pending_exit:
            qty, reason, decided = pending_exit
            filled, price = E.executable(t, i, pos["j"], "SELL", scenario, min(qty, pos["open"]))
            if filled:
                cost = E.fee(price, filled * LOT, False); gross = round((price - pos["entry"]) * filled * LOT, 2)
                pos["net"] = round(pos["net"] + gross - cost, 2); pos["fees"] = round(pos["fees"] + cost, 2); pos["open"] -= filled
                pos["events"].append(dict(i=i, decision_i=decided, side="SELL", reason=reason, lots=filled, price=price, fees=cost))
                if reason == "BANK":
                    pos["banked"] = True
                if reason == "TARGET_BASE":
                    pos["runner"] = True
                    pos["stop"] = max(round(pos["entry"] * rule.runner_floor, 2), round(pos["peak"] * rule.runner_keep, 2))
                if not pos["open"]:
                    cash = round(cash + pos["net"], 2); pos["exit_i"] = i; positions.append(pos); pos = None; pending_exit = None; next_i = i + 5
                else:
                    pending_exit = (pos["open"], reason, decided) if reason not in PARTIAL else None
            elif reason in PARTIAL:
                pending_exit = None
            if pending_exit:
                continue
        if pending_entry:
            j, lots, limit, decision, sign, atr, room = pending_entry; pending_entry = None
            filled, price = E.executable(t, i, j, "BUY", scenario, lots)
            if filled < max(1, math.ceil(lots * .25)) or price is None or price > limit:
                rejected += 1; continue
            risk = E.reserve(price, filled); assert risk <= room + .01
            spent += risk
            pos = dict(day=t.day, j=j, symbol=t.symbols[j], direction=sign, entry_i=i, decision_i=decision, entry=price, lots=filled,
                       open=filled, reserve=round(risk, 2), peak=price, stop=round(price * (1 - rule.stop), 2), banked=False,
                       net=-E.fee(price, filled * LOT, True), fees=E.fee(price, filled * LOT, True),
                       underlying_stop=float(t.close[decision] - sign * atr * rule.underlying_stop),
                       events=[dict(i=i, decision_i=decision, side="BUY", lots=filled, price=price, fees=E.fee(price, filled * LOT, True))])
        if pos:
            row = t.q[i, pos["j"]]
            bid = E.down(float(row[3]) - E.half(float(row[3]))) if np.isfinite(row[3]) and np.isfinite(row[4]) and row[4] * .2 >= LOT else None
            reason = None; qty = pos["open"]
            if t.minute[i] >= 928:
                reason = "FLAT_TIME"
            elif bid is not None and bid > 0 and pos.get("runner") and rule.split:
                # The free runner: no idle or index stop, a floor at runner_floor x entry, a wide trail.
                pos["peak"] = max(pos["peak"], bid)
                pos["stop"] = max(pos["stop"], round(pos["entry"] * rule.runner_floor, 2), round(pos["peak"] * rule.runner_keep, 2))
                if bid <= pos["stop"]:
                    reason = "RUNNER_TRAIL"
                elif rule.hero_target and bid >= pos["entry"] * (1 + rule.hero_target):
                    reason = "HERO_TARGET"
                mark = pos["net"] + (bid - pos["entry"]) * pos["open"] * LOT - E.fee(bid, pos["open"] * LOT, False)
                marks.append(mark + sum(p["net"] for p in positions))
            elif bid is not None and bid > 0:
                pos["peak"] = max(pos["peak"], bid)
                gain = pos["peak"] / pos["entry"] - 1
                if gain >= rule.arm:
                    pos["stop"] = max(pos["stop"], round(pos["peak"] * rule.keep, 2))
                if rule.runner_keep and not rule.split and (pos["banked"] or gain >= rule.runner_arm):
                    # A runner's floor is its own, wider share of the peak, and only rises from there.
                    pos["runner"] = True
                    pos["runner_stop"] = max(pos.get("runner_stop", 0.0), round(pos["peak"] * rule.runner_keep, 2))
                    pos["stop"] = pos["runner_stop"]
                if bid <= pos["stop"]:
                    reason = "TRAIL" if pos["stop"] >= pos["entry"] else "STOP"
                elif np.isfinite(t.close[i]) and rule.underlying_stop > 0 and not pos.get("runner") \
                        and pos["direction"] * (t.close[i] - pos["underlying_stop"]) < 0:
                    reason = "STRUCTURE"
                elif bid >= pos["entry"] * (1 + rule.target):
                    reason = "TARGET"
                    if rule.split and pos["open"] >= 2:
                        reason, qty = "TARGET_BASE", pos["open"] - pos["open"] // 2
                    elif rule.split and rule.solo_runner:
                        # Decided on this bar's bid, like the sale it replaces; nothing is sold.
                        reason = None
                        pos["runner"] = True
                        pos["stop"] = max(round(pos["entry"] * rule.runner_floor, 2), round(pos["peak"] * rule.runner_keep, 2))
                elif rule.bank_mult and not pos["banked"] and pos["open"] >= 2 and bid >= pos["entry"] * rule.bank_mult:
                    take = recover_lots(pos, bid)
                    if take:
                        reason, qty = "BANK", take
                elif i - pos["entry_i"] >= rule.hold and not (rule.hold_armed and gain >= rule.arm):
                    reason = "TIME"
                mark = pos["net"] + (bid - pos["entry"]) * pos["open"] * LOT - E.fee(bid, pos["open"] * LOT, False)
                marks.append(mark + sum(p["net"] for p in positions))
            if reason and i < t.n - 1:
                pending_exit = (qty, reason, i)
            continue
        if pending_exit or pending_entry or i < next_i or i >= t.n - 1 or len(positions) >= rule.slots:
            continue
        sign = int(dirs[i])
        if not sign:
            continue
        room = min(E.BUDGET / rule.slots, budget - spent, cash)
        if room <= 0:
            continue
        pick = choose(t, i, sign, rule, room, cash)
        if pick:
            j, lots, limit = pick
            pending_entry = (j, lots, limit, i, sign, t.features[rule.look][i, 4], room)
    unresolved = 0
    if pos:
        unresolved = 1
        pos["net"] = round(pos["net"] - pos["entry"] * pos["open"] * LOT, 2)
        pos["unresolved"] = True; positions.append(pos)
    net = round(sum(p["net"] for p in positions), 2)
    assert spent <= budget + .02 and net >= -spent - .03
    return dict(day=t.day, net=net, trades=len(positions), spent=round(spent, 2), fees=round(sum(p["fees"] for p in positions), 2),
                unresolved=unresolved, rejected=rejected, positions=positions if details else [], marked_worst=min(marks, default=0.))


def run_year(tapes, rule, scenario="ordinary", details=False, brakes=True):
    saved = E.run_day
    try:
        E.run_day = run_day
        return E.run_year(tapes, rule, scenario, details, brakes)
    finally:
        E.run_day = saved


TAPES = {}


def tapes(year):
    if year not in TAPES:
        TAPES[year] = D.load_year(year, exam=year == 2024)
        for t in TAPES[year]:
            oi_snapshots(t, year)
    return TAPES[year]


def brief(s):
    return {k: s[k] for k in ("net", "without_best", "worst", "drawdown", "trades", "profit_factor", "wins", "loss_days", "quarters")}
