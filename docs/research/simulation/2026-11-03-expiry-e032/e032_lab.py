"""E03.2 lab: E03.1's book, unchanged, plus two money ideas that never touch the original stake.

1. House-money roll (``roll_share`` > 0). When a ticket's 2x sale (TARGET, or E03's TARGET_BASE) fills,
   ``roll_share`` of that sale's realized profit buys a cheaper, further out-of-the-money option in the
   same direction, decided on the bar the sale filled and bought on the next bar. The roll is a separate
   side position: it never changes E03.1's own tickets, slots, reserves or exits, and it can only lose
   what it cost, which is a share of profit already banked that day.
2. Earned ticket (``earn_share`` > 0). The day's reserve grows by ``earn_share`` of the book's profit
   above its starting cash (and shrinks back as that profit is lost), capped at ``earn_cap`` times
   E03's Rs 2,500; the lot cap grows with it. A losing book trades E03.1's own size.

Every decision reads the completed bar and earlier bars; fills, fees, volume caps and the three fill
scenarios are E02's. With both ideas off this is E03.1's ``run_day`` exactly (checked in ``check()``).
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, replace
from pathlib import Path
import hashlib, json, math, sys
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-03-expiry-e031"))
import lab as L  # noqa: E402
X, E, D = L.X, L.E, L.D
LOT, ORDER, PARTIAL = L.LOT, L.ORDER, L.PARTIAL


@dataclass(frozen=True)
class Rule(L.Candidate):
    roll_share: float = 0.0      # share of the 2x sale's realized profit spent on the roll (0 = off)
    roll_on: str = "both"        # 'target' (one-lot full sale), 'base' (E03's partial sale) or 'both'
    roll_min: float = 1.0        # cheapest option the roll may buy (Rs)
    roll_stop: float = 0.5       # roll sold when its bid falls this share below its cost
    roll_hold: int = 10          # roll sold after this many minutes unless it has reached roll_arm
    roll_arm: float = 1.0        # from this gain the roll trails at roll_keep of its peak, no clock
    roll_keep: float = 0.5
    roll_target: float = 9.0     # roll sold at this gain (9 = 10x); 0 = none
    roll_lots: int = 6           # most lots one roll may buy
    earn_share: float = 0.0      # share of the book's profit above its start added to the day's reserve
    earn_cap: float = 2.0        # the day's reserve never above this multiple of Rs 2,500
    instrument: str = "otm"      # 'otm' = E03's pick; 'atm' = the nearest strike at or just out of the money, one lot
    ticket_room: float = 0.0     # 'atm' only: the ticket's full-premium reserve (the day's is twice this)
    prefer_lots: int = 0         # >=2: first look for the nearest strike where this many lots fit the same reserve
    prefer_only: bool = False    # with prefer_lots: no fallback to E03's one-lot pick

    @property
    def key(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:16]


E031 = Rule(**{**asdict(L.BASE), "stop": .35, "lock_arm": .5, "lock_floor": 1.1})
E03 = Rule(**asdict(L.BASE))


def roll_pick(t, i, d, rule, money, strike_from):
    """The nearest OTM strike beyond ``strike_from`` (same side, within four strikes of spot) that the money buys."""
    if not np.isfinite(t.close[i]) or money <= 0:
        return None
    spot = float(t.close[i])
    cands = [j for j in range(len(t.strikes)) if t.kinds[j] == d and d * (t.strikes[j] - strike_from) > 0
             and 0 < d * (t.strikes[j] - spot) <= 200 and np.isfinite(t.q[i, j]).all()]
    for j in sorted(cands, key=lambda j: d * t.strikes[j]):
        raw = float(t.q[i, j, 3])
        if raw < rule.roll_min:
            continue
        ask = E.up(raw + E.half(raw))
        cap = min(rule.roll_lots, int(t.q[i, j, 4] * .2) // LOT)
        for lots in range(cap, 0, -1):
            limit = E.down(min(ask * 1.10, (money - ORDER - lots * ORDER) / (lots * LOT * (1 + E.BUY_RATE))))
            if limit >= ask and E.reserve(limit, lots) <= money + .01:
                return j, lots, limit
    return None


def atm_pick(t, i, d, rule, room, cash):
    """The nearest strike at or out of the money on the signal's side (within one step), one lot, if the room buys it."""
    if not np.isfinite(t.close[i]):
        return None
    spot = float(t.close[i])
    cands = [j for j in range(len(t.strikes)) if t.kinds[j] == d and -25 <= d * (t.strikes[j] - spot) <= 50
             and np.isfinite(t.q[i, j]).all() and rule.premium_low <= t.q[i, j, 3] <= rule.premium_high]
    for j in sorted(cands, key=lambda j: abs(t.strikes[j] - spot)):
        raw = float(t.q[i, j, 3]); ask = E.up(raw + E.half(raw))
        if int(t.q[i, j, 4] * .2) // LOT < 1:
            continue
        money = min(room, cash)
        limit = E.down(min(ask * 1.10, (money - 2 * ORDER) / (LOT * (1 + E.BUY_RATE))))
        if limit >= ask and E.reserve(limit, 1) <= money + .01:
            return j, 1, limit
        return None
    return None


def manage_roll(t, i, roll, rule, scenario):
    """One bar of the roll: fill a pending sale, else decide one. Returns True when the roll is closed."""
    if roll.get("pending"):
        filled, price = E.executable(t, i, roll["j"], "SELL", scenario, roll["open"])
        if filled:
            cost = E.fee(price, filled * LOT, False)
            roll["net"] = round(roll["net"] + (price - roll["entry"]) * filled * LOT - cost, 2)
            roll["fees"] = round(roll["fees"] + cost, 2); roll["open"] -= filled
            roll["events"].append(dict(i=i, side="SELL", reason=roll["pending"], lots=filled, price=price))
            if not roll["open"]:
                return True
        return False
    row = t.q[i, roll["j"]]
    bid = E.down(float(row[3]) - E.half(float(row[3]))) if np.isfinite(row[3]) and np.isfinite(row[4]) and row[4] * .2 >= LOT else None
    reason = None
    if t.minute[i] >= 928:
        reason = "ROLL_FLAT"
    elif bid is not None and bid > 0:
        roll["peak"] = max(roll["peak"], bid)
        gain = roll["peak"] / roll["entry"] - 1
        if gain >= rule.roll_arm:
            roll["stop"] = max(roll["stop"], round(roll["peak"] * rule.roll_keep, 2))
        if bid <= roll["stop"]:
            reason = "ROLL_TRAIL" if roll["stop"] >= roll["entry"] else "ROLL_STOP"
        elif rule.roll_target and bid >= roll["entry"] * (1 + rule.roll_target):
            reason = "ROLL_TARGET"
        elif i - roll["entry_i"] >= rule.roll_hold and gain < rule.roll_arm:
            reason = "ROLL_TIME"
    if reason and i < t.n - 1:
        roll["pending"] = reason
    return False


def run_day(t, rule, scenario="ordinary", cash=E.START_CASH, budget=E.BUDGET, details=False, day_budget=None):
    dirs = L.directions(t, rule)
    full = E.BUDGET if day_budget is None else day_budget          # the day's unbraked reserve (E03: Rs 2,500)
    if rule.instrument == "atm":
        full = 2 * rule.ticket_room
    lot_cap = rule.max_lots if day_budget is None else max(rule.max_lots, int(rule.max_lots * day_budget / E.BUDGET))
    spent = 0.0; positions = []; next_i = 0; pending_entry = None; pending_exit = None; pos = None
    rejected = 0; marks = []; rolls = []; roll = None; roll_entry = None
    for i in range(int(np.searchsorted(t.minute, rule.start)), t.n):
        # --- the house-money roll, a side position (never changes the ticket below) ---
        if roll_entry:
            j, lots, limit, paid_from = roll_entry; roll_entry = None
            filled, price = E.executable(t, i, j, "BUY", scenario, lots)
            if filled and price is not None and price <= limit:
                fee = E.fee(price, filled * LOT, True)
                roll = dict(day=t.day, j=j, symbol=t.symbols[j], entry_i=i, entry=price, lots=filled, open=filled, peak=price,
                            stop=round(price * (1 - rule.roll_stop), 2), net=-fee, fees=fee, funded_by=paid_from, pending=None,
                            events=[dict(i=i, side="BUY", lots=filled, price=price)])
        if roll:
            if manage_roll(t, i, roll, rule, scenario):
                rolls.append(roll); cash = round(cash + roll["net"], 2); roll = None
        if pending_exit:
            qty, reason, decided = pending_exit
            filled, price = E.executable(t, i, pos["j"], "SELL", scenario, min(qty, pos["open"]))
            if filled:
                cost = E.fee(price, filled * LOT, False); gross = round((price - pos["entry"]) * filled * LOT, 2)
                pos["net"] = round(pos["net"] + gross - cost, 2); pos["fees"] = round(pos["fees"] + cost, 2); pos["open"] -= filled
                pos["events"].append(dict(i=i, decision_i=decided, side="SELL", reason=reason, lots=filled, price=price, fees=cost))
                if reason in ("TARGET", "TARGET_BASE") and rule.roll_share and roll is None and roll_entry is None \
                        and (rule.roll_on == "both" or (rule.roll_on == "target") == (reason == "TARGET")) and t.minute[i] < 920:
                    # Realized profit of the lots just sold (their share of the entry fee included).
                    banked = gross - cost - pos["fees_in"] * filled / pos["lots"]
                    pick = roll_pick(t, i, pos["direction"], rule, rule.roll_share * banked, float(t.strikes[pos["j"]]))
                    if pick and i < t.n - 1:
                        roll_entry = (*pick, pos["symbol"])
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
            fee_in = E.fee(price, filled * LOT, True)
            pos = dict(day=t.day, j=j, symbol=t.symbols[j], direction=sign, entry_i=i, decision_i=decision, entry=price, lots=filled,
                       open=filled, reserve=round(risk, 2), peak=price, stop=round(price * (1 - rule.stop), 2), banked=False,
                       net=-fee_in, fees=fee_in, fees_in=fee_in,
                       underlying_stop=float(t.close[decision] - sign * atr * rule.underlying_stop),
                       events=[dict(i=i, decision_i=decision, side="BUY", lots=filled, price=price, fees=fee_in)])
        if pos:
            row = t.q[i, pos["j"]]
            bid = E.down(float(row[3]) - E.half(float(row[3]))) if np.isfinite(row[3]) and np.isfinite(row[4]) and row[4] * .2 >= LOT else None
            reason = None; qty = pos["open"]
            if t.minute[i] >= 928:
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
        room = min(full / rule.slots, budget - spent, cash)
        if room <= 0:
            continue
        if rule.instrument == "atm":
            pick = atm_pick(t, i, sign, rule, room, cash)
        elif rule.prefer_lots >= 2:
            cheap = E.down((min(room, cash) - (1 + rule.prefer_lots) * ORDER) / (rule.prefer_lots * LOT * (1 + E.BUY_RATE)) / 1.1)
            pick = L.choose(t, i, sign, replace(rule, premium_high=min(rule.premium_high, cheap)), room, cash) if cheap >= rule.premium_low else None
            if pick and pick[1] < rule.prefer_lots:
                pick = None
            if pick is None and not rule.prefer_only:
                pick = L.choose(t, i, sign, rule, room, cash)
        else:
            pick = L.choose(t, i, sign, replace(rule, max_lots=lot_cap) if lot_cap != rule.max_lots else rule, room, cash)
        if pick:
            j, lots, limit = pick
            pending_entry = (j, lots, limit, i, sign, t.features[rule.look][i, 4], room)
    unresolved = 0
    if pos:
        unresolved = 1
        pos["net"] = round(pos["net"] - pos["entry"] * pos["open"] * LOT, 2)
        pos["unresolved"] = True; positions.append(pos)
    if roll:
        unresolved += 1
        roll["net"] = round(roll["net"] - roll["entry"] * roll["open"] * LOT, 2); roll["unresolved"] = True; rolls.append(roll)
    base = round(sum(p["net"] for p in positions), 2)
    side = round(sum(r["net"] for r in rolls), 2)
    assert spent <= budget + .02 and base >= -spent - .03
    return dict(day=t.day, net=round(base + side, 2), base=base, roll=side, rolls=len(rolls), trades=len(positions), spent=round(spent, 2),
                fees=round(sum(p["fees"] for p in positions) + sum(r["fees"] for r in rolls), 2), unresolved=unresolved,
                rejected=rejected, positions=positions if details else [], roll_positions=rolls if details else [], marked_worst=0.)


def run(tapes, rule, scenario="ordinary", details=False, brakes=True):
    cash = peak = E.START_CASH; days = []
    for t in tapes:
        dd = peak - cash
        scale = 0. if brakes and dd >= 4000 else .25 if brakes and dd >= 3000 else .5 if brakes and dd >= 1500 else 1.
        day_budget = None
        if rule.earn_share:
            day_budget = min(E.BUDGET * rule.earn_cap, E.BUDGET + rule.earn_share * max(0., cash - E.START_CASH))
        full = 2 * rule.ticket_room if rule.instrument == "atm" else (day_budget or E.BUDGET)
        row = run_day(t, rule, scenario, cash, min(full * scale, cash), details, day_budget)
        cash = round(cash + row["net"], 2); peak = max(peak, cash); assert cash >= -.01
        row.update(cash_after=cash, scale=scale, day_budget=day_budget or E.BUDGET); days.append(row)
    s = E.summary(days)
    s.update(roll=round(sum(d["roll"] for d in days), 2), rolls=sum(d["rolls"] for d in days),
             roll_wins=sum(1 for d in days for r in d["roll_positions"] if r["net"] > 0) if details else None)
    return dict(rule=asdict(rule), scenario=scenario, summary=s, days=days)


def check():
    """With both ideas off, every day of every scenario equals E03.1's own lab."""
    T = L.tapes()
    for y in (2024, 2025):
        for sc in ("ordinary", "adverse", "catastrophe"):
            for mine, theirs in ((E031, replace(L.BASE, stop=.35, lock_arm=.5, lock_floor=1.1)), (E03, L.BASE)):
                a, b = run(T[y], mine, sc), L.run(T[y], theirs, sc)
                assert [d["net"] for d in a["days"]] == [d["net"] for d in b["days"]], (y, sc)
    both = T[2024] + T[2025]
    assert abs(run(both, E031)["summary"]["net"] - 12426.71) < .01
    print("CHECK_OK E03 and E03.1 reproduce day by day, all scenarios")


if __name__ == "__main__":
    check()
