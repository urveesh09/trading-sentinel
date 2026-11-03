"""GENERATED from r8_lab.py by r8_diag.py (adds `flat`, the sell-everything minute). Round 8 lab: E03.1's own day loop (2026-11-03-expiry-e031/lab.py) with three hooks, all off by default:

  put_mult / call_mult    ticket reserve and lot cap multiplied by side (X1)
  align / align_mode      'WEEK' or 'DAY' direction: 'filter' drops the other side, 'size' scales aligned tickets (X2)
  delta_target            the strike whose Black-Scholes delta at the ATM implied volatility is nearest this (X3)

Everything a decision reads is the completed bar and earlier bars (the week's sign uses closes before the day).
With every hook off this is E03.1 day by day at all three fill levels (check()).
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, replace
from pathlib import Path
import hashlib, json, math, sqlite3, sys
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-03-expiry-e031"))
import lab as L  # noqa: E402
X, E = L.X, L.E
LOT, ORDER, PARTIAL = L.LOT, L.ORDER, L.PARTIAL
BREEZE = Path.home() / "sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite"


@dataclass(frozen=True)
class Rule(L.Candidate):
    put_mult: float = 1.
    call_mult: float = 1.
    align: str = ""
    align_mode: str = "filter"
    align_mult: float = 2.
    delta_target: float = 0.
    flat: int = 928              # minute (from midnight, bar end) from which everything is sold

    @property
    def key(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:16]


E031 = Rule(**{**asdict(L.BASE), "stop": .35, "lock_arm": .5, "lock_floor": 1.1})
WEEK = {}


def load_week(days):
    """Sign of the previous completed close against the close five sessions before it (no same-day data)."""
    c = sqlite3.connect(BREEZE.resolve().as_uri() + "?mode=ro", uri=True)
    rows = sorted((dt[:10], close) for dt, close in c.execute(
        "SELECT datetime, close FROM candles WHERE kind='daily' AND underlying='NIFTY' AND datetime >= '2023-11-01' AND datetime < '2026-01-01'"))
    c.close()
    dates = [d for d, _ in rows]; closes = dict(rows)
    for day in days:
        prior = [d for d in dates if d < day]
        if len(prior) >= 6:
            WEEK[day] = int(np.sign(closes[prior[-1]] - closes[prior[-6]]))
    return WEEK


def bias(t, rule, i):
    if rule.align == "WEEK":
        return WEEK.get(t.day, 0)
    if rule.align == "DAY":
        o = t.x[0, 0]
        return int(np.sign(t.close[i] - o)) if np.isfinite(o) and np.isfinite(t.close[i]) else 0
    return 0


def ncdf(z):
    return .5 * (1 + math.erf(z / math.sqrt(2)))


def atm_iv(t, i, d):
    s = float(t.close[i]); T = (930 - t.minute[i]) / X.YEAR_MIN
    js = [j for j in range(len(t.strikes)) if t.kinds[j] == d and np.isfinite(t.q[i, j, 3])]
    if not js or T <= 0:
        return None
    j = min(js, key=lambda j: abs(t.strikes[j] - s))
    iv = X.implied(float(t.q[i, j, 3]), s, float(t.strikes[j]), T, d == 1)
    return iv if np.isfinite(iv) and iv > 0 else None


def delta_pick(t, i, d, rule, room, cash, cap):
    iv = atm_iv(t, i, d)
    if iv is None:
        return None
    s = float(t.close[i]); T = (930 - t.minute[i]) / X.YEAR_MIN; sd = iv * math.sqrt(T)
    best = None
    for j in range(len(t.strikes)):
        k = float(t.strikes[j])
        if t.kinds[j] != d or not 0 < d * (k - s) <= 200 or not np.isfinite(t.q[i, j]).all() or t.q[i, j, 3] < 2:
            continue
        d1 = (math.log(s / k) + .5 * sd * sd) / sd
        delta = ncdf(d1) if d == 1 else 1 - ncdf(d1)
        if best is None or abs(delta - rule.delta_target) < abs(best[0] - rule.delta_target):
            best = (delta, j)
    if best is None:
        return None
    j = best[1]; raw = float(t.q[i, j, 3]); ask = E.up(raw + E.half(raw))
    top = min(cap, int(t.q[i, j, 4] * .2) // LOT)
    money = min(room, cash)
    for lots in range(top, 0, -1):
        limit = E.down(min(ask * 1.10, (money - ORDER - lots * ORDER) / (lots * LOT * (1 + E.BUY_RATE))))
        if limit >= ask and E.reserve(limit, lots) <= money + .01:
            return j, lots, limit
    return None


def day_scale(rule):
    return max(rule.put_mult, rule.call_mult, rule.align_mult if rule.align and rule.align_mode == "size" else 1.)


def run_day(t, rule, scenario="ordinary", cash=E.START_CASH, budget=E.BUDGET, details=False):
    dirs = L.directions(t, rule)
    spent = 0.0; positions = []; next_i = 0; pending_entry = None; pending_exit = None; pos = None; rejected = 0
    for i in range(int(np.searchsorted(t.minute, rule.start)), t.n):
        if pending_exit:
            qty, reason, decided = pending_exit
            filled, price = E.executable(t, i, pos["j"], "SELL", scenario, min(qty, pos["open"]))
            if filled:
                cost = E.fee(price, filled * LOT, False); gross = round((price - pos["entry"]) * filled * LOT, 2)
                pos["net"] = round(pos["net"] + gross - cost, 2); pos["fees"] = round(pos["fees"] + cost, 2); pos["open"] -= filled
                pos["events"].append(dict(i=i, decision_i=decided, side="SELL", reason=reason, lots=filled, price=price, fees=cost))
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
            if t.minute[i] >= rule.flat:
                reason = "FLAT_TIME"
            elif bid is not None and bid > 0 and pos.get("runner") and rule.split:
                pos["peak"] = max(pos["peak"], bid)
                pos["stop"] = max(pos["stop"], round(pos["entry"] * rule.runner_floor, 2), round(pos["peak"] * rule.runner_keep, 2))
                if bid <= pos["stop"]:
                    reason = "RUNNER_TRAIL"
                elif rule.hero_target and bid >= pos["entry"] * (1 + rule.hero_target):
                    reason = "HERO_TARGET"
            elif bid is not None and bid > 0:
                pos["peak"] = max(pos["peak"], bid)
                gain = pos["peak"] / pos["entry"] - 1
                if gain >= rule.arm:
                    pos["stop"] = max(pos["stop"], round(pos["peak"] * rule.keep, 2))
                if rule.lock_arm and gain >= rule.lock_arm:
                    pos["stop"] = max(pos["stop"], round(pos["entry"] * rule.lock_floor, 2))
                if bid <= pos["stop"]:
                    reason = "TRAIL" if pos["stop"] >= pos["entry"] else "STOP"
                elif np.isfinite(t.close[i]) and rule.underlying_stop > 0 and not pos.get("runner") \
                        and pos["direction"] * (t.close[i] - pos["underlying_stop"]) < 0:
                    reason = "STRUCTURE"
                elif bid >= pos["entry"] * (1 + rule.target):
                    reason = "TARGET"
                    if rule.split and pos["open"] >= 2:
                        reason, qty = "TARGET_BASE", pos["open"] - pos["open"] // 2
                elif L.stalled(rule, i, pos, bid):
                    reason = "STALL"
                elif L.timed_out(t, rule, i, pos, bid, gain):
                    reason = "TIME"
            if reason and i < t.n - 1:
                pending_exit = (qty, reason, i)
            continue
        if pending_exit or pending_entry or i < next_i or i >= t.n - 1 or len(positions) >= rule.slots:
            continue
        sign = int(dirs[i])
        if not sign:
            continue
        b = bias(t, rule, i)
        if rule.align and rule.align_mode == "filter" and b != sign:
            continue
        mult = (rule.put_mult if sign < 0 else rule.call_mult) * (rule.align_mult if rule.align and rule.align_mode == "size" and b == sign else 1.)
        room = min(E.BUDGET / rule.slots * mult, budget - spent, cash)
        if room <= 0:
            continue
        cap = int(round(rule.max_lots * mult))
        if rule.delta_target:
            pick = delta_pick(t, i, sign, rule, room, cash, cap)
        else:
            pick = L.choose(t, i, sign, replace(rule, max_lots=cap) if cap != rule.max_lots else rule, room, cash)
        if pick:
            j, lots, limit = pick
            pending_entry = (j, lots, limit, i, sign, t.features[rule.look][i, 4], room)
    unresolved = 0
    if pos:
        unresolved = 1
        pos["net"] = round(pos["net"] - pos["entry"] * pos["open"] * LOT, 2); pos["unresolved"] = True; positions.append(pos)
    net = round(sum(p["net"] for p in positions), 2)
    assert spent <= budget + .02 and net >= -spent - .03
    return dict(day=t.day, net=net, trades=len(positions), spent=round(spent, 2), fees=round(sum(p["fees"] for p in positions), 2),
                unresolved=unresolved, rejected=rejected, positions=positions if details else [], marked_worst=0.)


def run(tapes, rule, scenario="ordinary", details=False):
    cash = peak = E.START_CASH; days = []; full = E.BUDGET * day_scale(rule)
    for t in tapes:
        dd = peak - cash
        scale = 0. if dd >= 4000 else .25 if dd >= 3000 else .5 if dd >= 1500 else 1.
        row = run_day(t, rule, scenario, cash, min(full * scale, cash), details)
        cash = round(cash + row["net"], 2); peak = max(peak, cash); assert cash >= -.01
        row.update(cash_after=cash, scale=scale); days.append(row)
    return dict(rule=asdict(rule), scenario=scenario, summary=E.summary(days), days=days)


def check():
    T = L.tapes(); base = replace(L.BASE, stop=.35, lock_arm=.5, lock_floor=1.1)
    for y in (2024, 2025):
        for sc in ("ordinary", "adverse", "catastrophe"):
            a, b = run(T[y], E031, sc), L.run(T[y], base, sc)
            assert [d["net"] for d in a["days"]] == [d["net"] for d in b["days"]], (y, sc)
    assert abs(run(T[2024] + T[2025], E031)["summary"]["net"] - 12426.71) < .01
    print("CHECK_OK E03.1 reproduces day by day at all three fill levels")


if __name__ == "__main__":
    check()
