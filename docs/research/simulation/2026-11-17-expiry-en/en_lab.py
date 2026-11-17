"""EN lab: the round-8 day loop (r8b_lab.run_day) with three put-side hooks, all off by default.

  put_eff      put signals need |efficiency| >= put_eff instead of the rule's 0.70 (calls unchanged)     EN03
  put_mult     (existing) put ticket reserve / lot cap multiple; day reserve = 2,500 x max(put, call)  EN04
  put_runner   >0: a put ticket of >= 2 lots whose TIME exit comes with bid >= put_runner x entry sells
               half (rounded up) and the rest becomes the E03 runner (floor at cost, half the peak kept,
               10x target, sold from `flat`)                                                         EN05

With every hook off this is E03.2 exactly (check()). Every decision reads the completed bar and earlier bars.
NIFTY 2024 + 2025 only (both SEEN); 2023 is never read.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, replace
import hashlib, json, math
import numpy as np
import en_base as B

R, L, X, E = B.R, B.L, B.X, B.E
LOT, PARTIAL = R.LOT, R.PARTIAL


@dataclass(frozen=True)
class Rule(R.Rule):
    put_eff: float = 0.
    put_runner: float = 0.

    @property
    def key(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:16]


E032 = Rule(**asdict(B.E032))
_DIR = {}


def directions(t, rule):
    """E03.2's signal; with put_eff < efficiency, put signals between put_eff and efficiency are added."""
    base = L.directions(t, rule)
    if not rule.put_eff or rule.put_eff >= rule.efficiency:
        return base
    key = (id(t), rule.put_eff, rule.look, rule.stretch, rule.start, rule.end, rule.efficiency)
    if key not in _DIR:
        loose = L.directions(t, replace(rule, efficiency=rule.put_eff))
        out = base.copy()
        add = (loose < 0) & (base == 0)
        out[add] = -1
        _DIR[key] = out
    return _DIR[key]


def run_day(t, rule, scenario="ordinary", cash=E.START_CASH, budget=E.BUDGET, details=False):
    dirs = directions(t, rule)
    spent = 0.0; positions = []; next_i = 0; pending_entry = None; pending_exit = None; pos = None; rejected = 0
    for i in range(int(np.searchsorted(t.minute, rule.start)), t.n):
        if pending_exit:
            qty, reason, decided = pending_exit
            filled, price = E.executable(t, i, pos["j"], "SELL", scenario, min(qty, pos["open"]))
            if filled:
                cost = E.fee(price, filled * LOT, False); gross = round((price - pos["entry"]) * filled * LOT, 2)
                pos["net"] = round(pos["net"] + gross - cost, 2); pos["fees"] = round(pos["fees"] + cost, 2); pos["open"] -= filled
                pos["events"].append(dict(i=i, decision_i=decided, side="SELL", reason=reason, lots=filled, price=price, fees=cost))
                if reason in ("TARGET_BASE", "PUT_RUNNER"):
                    pos["runner"] = True
                    pos["stop"] = max(round(pos["entry"] * rule.runner_floor, 2), round(pos["peak"] * rule.runner_keep, 2))
                if not pos["open"]:
                    cash = round(cash + pos["net"], 2); pos["exit_i"] = i; positions.append(pos); pos = None; pending_exit = None; next_i = i + 5
                else:
                    pending_exit = (pos["open"], reason, decided) if reason not in PARTIAL + ("PUT_RUNNER",) else None
            elif reason in PARTIAL + ("PUT_RUNNER",):
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
                    if rule.put_runner and pos["direction"] < 0 and pos["open"] >= 2 and bid >= pos["entry"] * rule.put_runner:
                        reason, qty = "PUT_RUNNER", pos["open"] - pos["open"] // 2
            if reason and i < t.n - 1:
                pending_exit = (qty, reason, i)
            continue
        if pending_exit or pending_entry or i < next_i or i >= t.n - 1 or len(positions) >= rule.slots:
            continue
        sign = int(dirs[i])
        if not sign:
            continue
        mult = rule.put_mult if sign < 0 else rule.call_mult
        room = min(E.BUDGET / rule.slots * mult, budget - spent, cash)
        if room <= 0:
            continue
        cap = int(round(rule.max_lots * mult))
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
    cash = peak = E.START_CASH; days = []; full = E.BUDGET * R.day_scale(rule)
    for t in tapes:
        dd = peak - cash
        scale = 0. if dd >= 4000 else .25 if dd >= 3000 else .5 if dd >= 1500 else 1.
        row = run_day(t, rule, scenario, cash, min(full * scale, cash), details)
        cash = round(cash + row["net"], 2); peak = max(peak, cash); assert cash >= -.01
        row.update(cash_after=cash, scale=scale); days.append(row)
    return dict(rule=asdict(rule), scenario=scenario, summary=E.summary(days), days=days)


def check():
    T = B.tapes()
    for y in (2024, 2025):
        for sc in ("ordinary", "adverse", "catastrophe"):
            a, b = run(T[y], E032, sc), R.run(T[y], B.E032, sc)
            assert [d["net"] for d in a["days"]] == [d["net"] for d in b["days"]], (y, sc)
    assert abs(run(T[2024] + T[2025], E032)["summary"]["net"] - 21517.55) < .01
    print("CHECK_OK EN lab reproduces E03.2 day by day at all three fill levels (+21,517.55)")


if __name__ == "__main__":
    check()
