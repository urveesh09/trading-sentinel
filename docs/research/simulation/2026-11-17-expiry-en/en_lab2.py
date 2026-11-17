"""EN08-EN10 lab: en_lab.run_day with three more hooks, all off by default (check() proves E03.2 unchanged on
NIFTY 2023, 2024 and 2025 day by day at all three fill levels). Every decision reads the completed bar and
earlier bars only; the regime metric is fixed at 13:00 from 09:15-13:00 bars.

  regime_min    EN08: no new entry on a day whose 09:15-13:00 index range / 13:00 index is below this (percent)
  squeeze       EN09: 'add' = E03.2's signals plus the compression-breakout signals on minutes where E03.2 has
                none; 'only' = the breakout signals alone. At most one breakout signal per day.
  bank_r        EN10: a ONE-lot ticket (it cannot sell half) is sold whole before its 8-minute clock when the bid
                reaches entry x (1 + bank_r x stop) plus the round-trip charges per unit (bank_r = 1: one initial
                risk unit). Multi-lot tickets, the 2x rule and the clock are unchanged.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, replace
import hashlib, json, math, random
import numpy as np
import en_lab as N

R, L, X, E = N.R, N.L, N.X, N.E
LOT, PARTIAL = N.LOT, N.PARTIAL
# EN09 frozen parameters (PLAN2.md)
SQ_LOOK, SQ_REF_FROM, SQ_CUT, SQ_START, SQ_END = 20, 30, .6, 780, 885


@dataclass(frozen=True)
class Rule(N.Rule):
    regime_min: float = 0.
    squeeze: str = ""
    bank_r: float = 0.

    @property
    def key(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:16]


E032 = Rule(**asdict(N.E032))
_REG = {}; _SQ = {}
AVAIL = None          # set by the scorer to the exam's decision-minute coverage rule (exam2023b.available_at)


def morning_range(t):
    """(max high - min low) of the index 09:15-13:00 over the 13:00 close, percent; NaN if incomplete."""
    if id(t) not in _REG:
        m = t.minute <= 780
        x = t.x[m]
        ok = np.isfinite(x).all() and len(x) >= 200
        _REG[id(t)] = float((np.max(x[:, 1]) - np.min(x[:, 2])) / x[-1, 3] * 100) if ok else float("nan")
    return _REG[id(t)]


def squeeze_signals(t):
    """Compression then breakout, once a day. At bar i (13:00 <= end < 14:45):
    compression: the 20-bar index range ending at i-1 <= 0.6 x the median 20-bar range of bars ending 09:45..i-21;
    breakout: index close[i] beyond the high/low of bars i-20..i-1 AND future close[i] beyond its own high/low."""
    if id(t) in _SQ:
        return _SQ[id(t)]
    out = np.zeros(t.n, dtype=np.int8); hi, lo = t.x[:, 1], t.x[:, 2]; fh, fl = t.f[:, 1], t.f[:, 2]
    rng = np.full(t.n, np.nan)
    for i in range(SQ_LOOK - 1, t.n):
        w = slice(i - SQ_LOOK + 1, i + 1)
        if np.isfinite(hi[w]).all() and np.isfinite(lo[w]).all():
            rng[i] = np.max(hi[w]) - np.min(lo[w])
    for i in range(t.n):
        if not SQ_START <= t.minute[i] < SQ_END or i < 2 * SQ_LOOK + SQ_REF_FROM:
            continue
        ref = rng[SQ_REF_FROM:i - SQ_LOOK]
        ref = ref[np.isfinite(ref)]
        prev = slice(i - SQ_LOOK, i)
        if len(ref) < 30 or not np.isfinite(rng[i - 1]) or not np.isfinite([t.close[i], t.f[i, 3]]).all():
            continue
        if not np.isfinite(hi[prev]).all() or not np.isfinite(fh[prev]).all() or not np.isfinite(fl[prev]).all():
            continue
        if rng[i - 1] > SQ_CUT * float(np.median(ref)):
            continue
        d = 1 if t.close[i] > np.max(hi[prev]) and t.f[i, 3] > np.max(fh[prev]) else -1 if t.close[i] < np.min(lo[prev]) and t.f[i, 3] < np.min(fl[prev]) else 0
        if d:
            if AVAIL is None or AVAIL(t, i, d):
                out[i] = d
            break                                   # one breakout a day, taken or not
    _SQ[id(t)] = out
    return out


def directions(t, rule):
    base = N.directions(t, rule)
    if rule.squeeze == "only":
        return squeeze_signals(t)
    if rule.squeeze == "add":
        out = base.copy(); sq = squeeze_signals(t); add = (sq != 0) & (base == 0); out[add] = sq[add]
        return out
    return base


def _bank_price(pos, rule):
    per_unit_fees = (E.fee(pos["entry"], LOT, True) + E.fee(pos["entry"] * (1 + rule.bank_r * rule.stop), LOT, False)) / LOT
    return pos["entry"] * (1 + rule.bank_r * rule.stop) + per_unit_fees


def run_day(t, rule, scenario="ordinary", cash=E.START_CASH, budget=E.BUDGET, details=False):
    dirs = directions(t, rule)
    calm = bool(rule.regime_min) and not (morning_range(t) >= rule.regime_min)
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
            j, lots, limit, decision, sign, atr, room, origin = pending_entry; pending_entry = None
            filled, price = E.executable(t, i, j, "BUY", scenario, lots)
            if filled < max(1, math.ceil(lots * .25)) or price is None or price > limit:
                rejected += 1; continue
            risk = E.reserve(price, filled); assert risk <= room + .01
            spent += risk
            pos = dict(day=t.day, j=j, symbol=t.symbols[j], direction=sign, entry_i=i, decision_i=decision, entry=price, lots=filled,
                       open=filled, reserve=round(risk, 2), peak=price, stop=round(price * (1 - rule.stop), 2), banked=False, origin=origin,
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
                elif rule.bank_r and pos["lots"] == 1 and i - pos["entry_i"] < rule.hold and bid >= _bank_price(pos, rule):
                    reason = "ONE_LOT_BANK"
                elif L.stalled(rule, i, pos, bid):
                    reason = "STALL"
                elif L.timed_out(t, rule, i, pos, bid, gain):
                    reason = "TIME"
                    if rule.put_runner and pos["direction"] < 0 and pos["open"] >= 2 and bid >= pos["entry"] * rule.put_runner:
                        reason, qty = "PUT_RUNNER", pos["open"] - pos["open"] // 2
            if reason and i < t.n - 1:
                pending_exit = (qty, reason, i)
            continue
        if calm or pending_exit or pending_entry or i < next_i or i >= t.n - 1 or len(positions) >= rule.slots:
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
            origin = "SQUEEZE" if rule.squeeze and squeeze_signals(t)[i] == sign and N.directions(t, rule)[i] != sign else "E032"
            pending_entry = (j, lots, limit, i, sign, t.features[rule.look][i, 4], room, origin)
    unresolved = 0
    if pos:
        unresolved = 1
        pos["net"] = round(pos["net"] - pos["entry"] * pos["open"] * LOT, 2); pos["unresolved"] = True; positions.append(pos)
    net = round(sum(p["net"] for p in positions), 2)
    assert spent <= budget + .02 and net >= -spent - .03
    return dict(day=t.day, net=net, trades=len(positions), spent=round(spent, 2), fees=round(sum(p["fees"] for p in positions), 2),
                unresolved=unresolved, rejected=rejected, positions=positions if details else [], marked_worst=0., calm=calm)


def run(tapes, rule, scenario="ordinary", details=False):
    cash = peak = E.START_CASH; days = []; full = E.BUDGET * R.day_scale(rule)
    for t in tapes:
        dd = peak - cash
        scale = 0. if dd >= 4000 else .25 if dd >= 3000 else .5 if dd >= 1500 else 1.
        row = run_day(t, rule, scenario, cash, min(full * scale, cash), details)
        cash = round(cash + row["net"], 2); peak = max(peak, cash); assert cash >= -.01
        row.update(cash_after=cash, scale=scale); days.append(row)
    return dict(rule=asdict(rule), scenario=scenario, summary=E.summary(days), days=days)


_TAPES = {}


def tapes():
    """NIFTY 2023 (opened on the owner's word, Nov 17; now seen), 2024 and 2025 (seen)."""
    if not _TAPES:
        import exam2023 as A
        _TAPES[2023] = A.build_tapes(2023)[0]
        T = N.B.tapes(); _TAPES[2024] = T[2024]; _TAPES[2025] = T[2025]
        for y, ts in _TAPES.items():
            assert all(t.day.startswith(str(y)) for t in ts)
    return _TAPES


def check():
    T = tapes()
    for y in (2023, 2024, 2025):
        for sc in ("ordinary", "adverse", "catastrophe"):
            a, b = run(T[y], E032, sc), N.run(T[y], N.E032, sc)
            assert [d["net"] for d in a["days"]] == [d["net"] for d in b["days"]], (y, sc)
    print("CHECK_OK en_lab2 reproduces E03.2 day by day on 2023, 2024 and 2025 at all three fill levels")


if __name__ == "__main__":
    check()
