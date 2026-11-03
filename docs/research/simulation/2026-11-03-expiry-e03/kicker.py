"""Hero kicker estimate: a small further-OTM ticket tied to each E03 entry.

Bought on the same execution bar as the main ticket, two strikes further out, at most
Rs 250 including fees. Sold with the main ticket unless the main ticket reached its 2x
sale; then it runs with a floor at its own cost, a 50% trail and a 20x target, flat 15:28.
Same fills/fees as the lab. An estimate beside the book (its cash is not in the book).
"""
import sys
import numpy as np
import e03_lab as X
E = X.E

E03 = dict(max_lots=3, split=True, runner_floor=1.0, runner_keep=0.5, hero_target=9.0)


def kicker(t, p, steps=2, budget=250.0, scenario="ordinary"):
    strike = t.strikes[p["j"]] + p["direction"] * 50 * steps
    js = [j for j in range(len(t.strikes)) if t.strikes[j] == strike and t.kinds[j] == p["direction"]]
    if not js:
        return None
    j = js[0]; i = p["entry_i"]
    filled, price = E.executable(t, i, j, "BUY", scenario, 10)
    if not filled or price < 0.5:
        return None
    lots = int((budget - 2 * E.ORDER) // (price * X.LOT * (1 + E.BUY_RATE)))
    lots = min(lots, filled)
    if lots < 1:
        return None
    net = -E.fee(price, lots * X.LOT, True) - 0.0
    based = next((e for e in p["events"] if e.get("reason") == "TARGET_BASE"), None)
    end_i = None
    if based is None:
        end_i = p["events"][-1]["i"]           # sold with the main ticket, same bar
    peak = price; stop = 0.0; sale_i = None
    flat = int(np.searchsorted(t.minute, 928))
    for k in range(i + 1, t.n):
        if end_i is not None and k >= end_i:
            sale_i = k; break
        if based is not None and k > based["i"]:
            row = t.q[k - 1, j, 3]
            if np.isfinite(row):
                bid = E.down(float(row) - E.half(float(row)))
                peak = max(peak, bid); stop = max(stop, price, peak * 0.5)
                if bid <= stop or bid >= price * 20 or k - 1 >= flat:
                    sale_i = k; break
    if sale_i is None:
        sale_i = t.n - 1
    got, sale = E.executable(t, sale_i, j, "SELL", scenario, lots)
    if not got:
        return dict(day=t.day, net=round(net - price * lots * X.LOT, 2), cost=price * lots * X.LOT, ran=based is not None, unsold=True)
    net += (sale - price) * lots * X.LOT - E.fee(sale, lots * X.LOT, False)
    return dict(day=t.day, net=round(net, 2), cost=round(price * lots * X.LOT, 2), ran=based is not None, mult=round(sale / price, 2))


if __name__ == "__main__":
    rule = X.Hero(**{**X.R3, **E03})
    for steps in (1, 2, 3):
        for y in (2024, 2025):
            for sc in ("ordinary", "adverse"):
                r = X.run_year(X.tapes(y), rule, sc, details=True)
                rows = []
                for t, d in zip(X.tapes(y), r["days"]):
                    for p in d["positions"]:
                        k = kicker(t, p, steps, scenario=sc)
                        if k:
                            rows.append(k)
                nets = [k["net"] for k in rows]
                by_day = {}
                for k in rows:
                    by_day[k["day"]] = by_day.get(k["day"], 0) + k["net"]
                best = max(by_day.values(), default=0)
                print(f"steps {steps} {y} {sc:<8} kickers {len(rows):>2} net {sum(nets):>8.0f} xb {sum(nets)-best:>8.0f} "
                      f"ran {sum(k['ran'] for k in rows)} best_mult {max((k.get('mult',0) for k in rows), default=0)}  book {r['summary']['net']:.0f}", flush=True)
