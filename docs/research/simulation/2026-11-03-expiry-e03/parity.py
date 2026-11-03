"""Paper-module parity: every lab E03 position's exits replayed through expiry_e02.action/sell_base.

For each position the lab bought (2024 and 2025, ordinary and adverse), a native position is opened
at the same price and lots, then each completed bar's bid goes to the paper module's ``action``.
A planned partial sale is booked the way ``sell_base`` books it; other exits latch and retry, as
the paper module's ``_try_exit`` does. Fills use the lab's execution model, so the comparison is
of decisions, clocks, lots, prices and money. Any difference fails.
"""
import sys
from types import SimpleNamespace
import numpy as np
import e03_lab as X
E, D = X.E, X.D
sys.path.insert(0, str(X.HERE.parents[3] / "python-engine"))
import expiry_e02 as P   # noqa: E402
EP = D.EP

E03 = dict(max_lots=3, split=True, runner_floor=1.0, runner_keep=0.5, hero_target=9.0)


def replay(t, p, scenario):
    con = SimpleNamespace(tradingsymbol=p["symbol"], token=p["j"] + 1, strike=float(t.strikes[p["j"]]),
                          instrument_type="CE" if p["direction"] == 1 else "PE", lot_size=65)
    n = EP._new_position(t.day, "NIFTY", "E03", "NFO", con, p["entry"], p["lots"], t.now[p["entry_i"]], E.FEE)
    n.update(stop=round(p["entry"] * .6, 2), direction=p["direction"], underlying_stop=p["underlying_stop"],
             e02_policy=P.policy_for(P.E03))
    pending = None; events = []
    for i in range(p["entry_i"], t.n):
        if pending:
            lots, why, di = pending
            filled, price = E.executable(t, i, p["j"], "SELL", scenario, min(lots, n["lots_open"]))
            if filled:
                EP._sell(n, filled, price, why, t.now[i]); events.append((i, di, filled, price, why))
                if why == "TARGET_BASE":
                    frozen = n["e02_policy"]; n["runner"] = True
                    n["stop"] = round(max(n["entry_price"] * frozen["runner_floor"], n["peak"] * frozen["runner_keep"]), 2)
            if not n["lots_open"]:
                break
            pending = None if why == "TARGET_BASE" else (n["lots_open"], why, di)
            if pending:
                continue
        r = t.q[i, p["j"]]
        bid = E.down(float(r[3]) - E.half(float(r[3]))) if np.isfinite(r[3]) and np.isfinite(r[4]) and r[4] * .2 >= 65 else None
        if t.minute[i] >= 928:
            pending = (n["lots_open"], "FLAT_TIME", i); continue
        if bid is None or bid <= 0:
            continue
        spot = float(t.close[i]) if np.isfinite(t.close[i]) else None
        a = P.action(n, bid, spot, t.now[i])
        if a and i < t.n - 1:
            pending = (a[0], a[1], i)
    return n, events


def main():
    count = 0; bad = []
    for y in (2024, 2025):
        for sc in ("ordinary", "adverse"):
            r = X.run_year(X.tapes(y), X.Hero(**{**X.R3, **E03}), sc, details=True)
            print(y, sc, X.brief(r["summary"])["net"], flush=True)
            for t, d in zip(X.tapes(y), r["days"]):
                for p in d["positions"]:
                    n, events = replay(t, p, sc)
                    lab = [(e["i"], e["decision_i"], e["lots"], e["price"], e["reason"]) for e in p["events"][1:]]
                    count += 1
                    if events != lab or abs(n["net_pnl"] - p["net"]) > .03 or n["lots_open"] != p["open"]:
                        bad.append(dict(year=y, scenario=sc, day=t.day, paper=events, lab=lab, paper_net=n["net_pnl"], lab_net=p["net"]))
    X.D.dump(X.HERE / "paper-parity.json", dict(positions=count, mismatches=bad))
    print("PAPER_PARITY", count, "positions", len(bad), "mismatches")


if __name__ == "__main__":
    main()
