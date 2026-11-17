"""ledger10: the two-sided 10:00 ledger on Breeze minutes (PLAN.md shared helper, frozen at 83e1b444; details fixed here before
any number). Development data (gl's sealed ALL sample), non-expiry sessions 2023-01-01 .. 2026-10-28 (op.setup's days; no
expiry-day chain is read, so the protected 2023 expiry exam is untouched).

Per date and side (CE / PE): the strike is 1-ITM of gl.atm at index 44 (the 09:59 bar's close), else ATM when 1-ITM is
unaffordable or unprinted; the entry is wk.ask of that minute's own print (gl.opx look 0) and must cost <= Rs 15,000 with
entry charges (op.entry_cost). Legal exit: a stop at the first minute 45..103 whose own print gives a net mark <= -Rs 3,000
(wk.bid, Zerodha charges, stress), else the first printed minute 104..109 (11:00:00 close + 5), else UNRESOLVED.
States ENTERED / UNRESOLVED / UNAFFORDABLE / NO_QUOTE; nets at Rs 205 and 400. Cached to _local/ledger10.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-17-sn396"))
import op  # noqa: E402

gl, wk = op.gl, op.wk
CACHE = HERE / "_local" / "ledger10.json"
LO, HI = "2023-01-01", "2026-10-28"
E, X, GRACE, STOP, ROOM = 44, 104, 5, 3000.0, 15000.0


def side_trade(smp, s, side, stress):
    mk = smp.mk
    lot = mk["lot"]
    atm = gl.atm(smp, s, E)
    for dep in (1, 0):
        k = atm + (-50 if side == "CE" else 50) * dep
        p = gl.opx(s, k, side, E, look=0)
        if p is None:
            continue
        a = wk.ask(mk, p)
        if op.entry_cost(a) > ROOM:
            continue
        def net(px):
            b = wk.bid(mk, px)
            return (b - a) * lot - wk.charges(a, b, lot, mk["exch"]) - stress
        for j in range(E + 1, X):
            q = gl.opx(s, k, side, j, look=0)
            if q is not None and net(q) <= -STOP:
                return {"state": "ENTERED", "k": k, "dep": dep, "ask": a, "net": round(net(q), 2), "x": j, "why": "stop"}
        for j in range(X, X + GRACE + 1):
            q = gl.opx(s, k, side, j, look=0)
            if q is not None:
                return {"state": "ENTERED", "k": k, "dep": dep, "ask": a, "net": round(net(q), 2), "x": j, "why": "time"}
        return {"state": "UNRESOLVED", "k": k, "dep": dep, "ask": a}
    return {"state": "NO_QUOTE_OR_UNAFFORDABLE"}


def build():
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    smp, days, _au = op.setup()
    out = {}
    for d in days:
        if not (LO <= d <= HI):
            continue
        s = smp.s[d]
        row = {"expiry": s["expiry"]}
        for side in ("CE", "PE"):
            r205, r400 = side_trade(smp, s, side, 205.0), side_trade(smp, s, side, 400.0)
            row[side] = {**r205, "net205": r205.get("net"), "net400": r400.get("net"), "state400": r400["state"]}
            row[side].pop("net", None)
            p = gl.opx(s, row[side]["k"], side, E, look=0) if "k" in row[side] else None
            row[side]["spread_share"] = None if p is None else round((wk.ask(smp.mk, p) - wk.bid(smp.mk, p)) / p, 5)
        out[d] = row
    CACHE.write_text(json.dumps(out), encoding="utf-8")
    return out


if __name__ == "__main__":
    L = build()
    print(len(L), "dates")
