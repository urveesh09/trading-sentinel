"""Lab-to-paper parity for E03.2 (puts at twice the reserve, 8% buy limit, sold from 15:14). -> paper-parity.json

1. Sizing: at every lab entry, the engine's ``expiry_e02._lots`` on a quote built from the lab's decision bar (ask =
   close + the frozen half spread, depth = the lab's 20% volume capacity) must give the lab chooser's lots and limit,
   with the lab's own room (ticket x side multiple, day reserve after brakes and earlier tickets, cash).
2. Exits: every lab position is opened natively at the lab's price and lots and each completed bar's bid goes to
   ``expiry_e02.action`` (policy frozen by ``policy_for(E032)``); partial sales booked as ``sell_base`` books them,
   other exits latched and retried; the lab's 15:14 sale mirrored. Same decisions, clocks, lots, prices and money.
"""
from __future__ import annotations
import json, sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import r8b_lab as R

HERE = Path(__file__).resolve().parent
L, E, X = R.L, R.E, R.X
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "python-engine").is_dir()) / "python-engine"))
import expiry_e02 as P  # noqa: E402
EP = P.EP
RULE = replace(R.E031, put_mult=2., chase=.08, flat=914)


def replay(t, p, scenario):
    con = SimpleNamespace(tradingsymbol=p["symbol"], token=p["j"] + 1, strike=float(t.strikes[p["j"]]),
                          instrument_type="CE" if p["direction"] == 1 else "PE", lot_size=65)
    n = EP._new_position(t.day, "NIFTY", "E032", "NFO", con, p["entry"], p["lots"], t.now[p["entry_i"]], E.FEE)
    n.update(stop=round(p["entry"] * (1 - P.E032.initial_stop), 2), direction=p["direction"], underlying_stop=p["underlying_stop"],
             e02_policy=P.policy_for(P.E032))
    pending = None; events = []
    for i in range(p["entry_i"], t.n):
        if pending:
            lots, why, di = pending
            filled, price = E.executable(t, i, p["j"], "SELL", scenario, min(lots, n["lots_open"]))
            if filled:
                EP._sell(n, filled, price, why, t.now[i]); events.append((i, di, filled, price, why))
                if why == "TARGET_BASE":
                    fz = n["e02_policy"]; n["runner"] = True
                    n["stop"] = round(max(n["entry_price"] * fz["runner_floor"], n["peak"] * fz["runner_keep"]), 2)
            if not n["lots_open"]:
                break
            pending = None if why == "TARGET_BASE" else (n["lots_open"], why, di)
            if pending:
                continue
        r = t.q[i, p["j"]]
        bid = E.down(float(r[3]) - E.half(float(r[3]))) if np.isfinite(r[3]) and np.isfinite(r[4]) and r[4] * .2 >= 65 else None
        if t.minute[i] >= 914:
            pending = (n["lots_open"], "FLAT_TIME", i); continue
        if bid is None or bid <= 0:
            continue
        a = P.action(n, bid, float(t.close[i]) if np.isfinite(t.close[i]) else None, t.now[i])
        if a and i < t.n - 1:
            pending = (a[0], a[1], i)
    return n, events


def sizing(t, p, room, cash):
    i, d = p["decision_i"], p["direction"]; mult = 2. if d < 0 else 1.; cap = int(round(3 * mult))
    lab = L.choose(t, i, d, replace(RULE, max_lots=cap), room, cash)
    raw = float(t.q[i, p["j"], 3]); ask = E.up(raw + E.half(raw)); depth = int(t.q[i, p["j"], 4] * .2) // 65 * 65
    q = EP.Quote(((E.down(raw - E.half(raw)), depth),), ((ask, depth),), raw, t.now[i])
    lots, limit = P._lots(q, min(room, cash), int(round(P.E032.max_lots * P.ticket_scale(P.E032, d))), EP.fee_schedule("NFO"), P.E032.chase)
    return (lab[1], round(lab[2], 2)) if lab else None, (lots, limit) if lots else None


def main():
    T = L.tapes(); count = 0; sized = 0; bad = []
    for y in (2024, 2025):
        for sc in ("ordinary", "adverse"):
            r = R.run(T[y], RULE, sc, details=True)
            cash_before = R.E.START_CASH
            for t, d in zip(T[y], r["days"]):
                budget = min(R.E.BUDGET * 2. * d["scale"], cash_before); spent = 0.
                for p in d["positions"]:
                    room = min(R.E.BUDGET / RULE.slots * (2. if p["direction"] < 0 else 1.), budget - spent, cash_before)
                    lab_pick, paper_pick = sizing(t, p, room, cash_before); sized += 1
                    if lab_pick != paper_pick:
                        bad.append(dict(kind="sizing", year=y, scenario=sc, day=t.day, lab=lab_pick, paper=paper_pick, room=round(room, 2)))
                    n, events = replay(t, p, sc); count += 1
                    lab = [(e["i"], e["decision_i"], e["lots"], e["price"], e["reason"]) for e in p["events"][1:]]
                    if events != lab or abs(n["net_pnl"] - p["net"]) > .03 or n["lots_open"] != p["open"]:
                        bad.append(dict(kind="exit", year=y, scenario=sc, day=t.day, paper=events, lab=lab, paper_net=n["net_pnl"], lab_net=p["net"]))
                    spent += p["reserve"]
                cash_before = d["cash_after"]
            print(y, sc, r["summary"]["net"], flush=True)
    (HERE / "paper-parity.json").write_text(json.dumps(dict(positions=count, sizing_checks=sized, mismatches=bad), indent=2, default=str) + "\n", encoding="utf-8")
    print("PAPER_PARITY", count, "positions", sized, "sizing checks", len(bad), "mismatches")
    for b in bad[:8]:
        print(b)


if __name__ == "__main__":
    main()
