"""'Gamma blast' test: the index breaking through the strike with the most open interest.

Call wall = the call strike with the largest open interest on the last completed bar; put
wall likewise. An UP event is the first completed close above the call wall (the previous
close at or below it) with the future also rising, between 13:00 and 15:00; DOWN mirrors it
on the put wall. At each event one ticket: the nearest OTM option of that side, within four
strikes, whose ask is in a band (Rs 2-20, and Rs 5-20 as E02's band). Fixed exits judged on
later closes less the half spread: hold to 15:28, and 5x / 10x targets with a 50% stop.
Fees in, one ticket of about Rs 1,000. Seen 2024/2025 only; 2023 is never opened.
"""
import sqlite3, sys
from collections import defaultdict
import numpy as np
import e03_lab as X
E = X.E
SRC = X.HERE.parent / "2026-11-03-expiry-e02/_local"


def oi_table(year, day):
    c = sqlite3.connect((SRC / f"{year}.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
    rows = c.execute("SELECT strike, opt, datetime, oi FROM candles WHERE kind='option' AND datetime BETWEEN ? AND ?",
                     (day + " 12:00:00", day + " 15:29:00")).fetchall()
    c.close()
    oi = defaultdict(dict)
    for strike, opt, stamp, v in rows:
        if v is not None and v >= 0:
            k = (int(stamp[11:13]) - 9) * 60 + int(stamp[14:16]) - 15
            oi[k][(float(strike), 1 if opt == "CE" else -1)] = v
    return oi


def walls(oi, k):
    """The latest completed bar's walls; carries each contract's last known OI forward only within the bar set."""
    snap = oi.get(k, {})
    ce = [(v, s) for (s, d), v in snap.items() if d == 1]
    pe = [(v, s) for (s, d), v in snap.items() if d == -1]
    return (max(ce)[1] if ce else None), (max(pe)[1] if pe else None)


def ticket(t, i, d, low, flat):
    c = t.close[i]
    best = None
    for j in range(len(t.strikes)):
        dist = d * (t.strikes[j] - c)
        if t.kinds[j] != d or dist <= 0 or dist > 200:
            continue
        a = t.q[i, j, 3]
        if np.isfinite(a) and low <= a <= 20 and (best is None or dist < best[0]):
            best = (dist, j)
    if best is None:
        return None
    j = best[1]
    o = t.q[i + 1, j, 0]
    if not np.isfinite(o):
        return None
    entry = E.up(o + E.half(o))
    lots = max(1, min(10, int(1000 // (entry * 65))))
    qty = lots * 65
    path = [E.down(x - E.half(x)) if np.isfinite(x) else np.nan for x in t.q[i + 1:flat + 1, j, 3]]
    out = {}
    for name, stop, k in (("hold", None, None), ("t5_s50", .5, 5), ("t10_s50", .5, 10)):
        sale = next((x for x in reversed(path) if np.isfinite(x)), 0.0)
        for x in path:
            if not np.isfinite(x):
                continue
            if stop and x <= entry * (1 - stop):
                sale = x; break
            if k and x >= entry * k:
                sale = x; break
        out[name] = round((sale - entry) * qty - E.fee(entry, qty, True) - (E.fee(sale, qty, False) if sale > 0 else 0), 2)
    out["best"] = round(max((x for x in path if np.isfinite(x)), default=0) / entry, 2)
    return out


def main():
    for low in (2.0, 5.0):
        for y in (2024, 2025):
            days = defaultdict(lambda: defaultdict(float)); events = 0; mults = []
            for t in X.tapes(y):
                oi = oi_table(y, t.day)
                flat = int(np.searchsorted(t.minute, 928))
                done = set()
                for i in range(int(np.searchsorted(t.minute, 780)), int(np.searchsorted(t.minute, 900))):
                    k = i                      # tape row i is the bar starting 09:15 + i minutes
                    cw, pw = walls(oi, k)
                    pcw, ppw = walls(oi, k - 1)
                    c, p = t.close[i], t.close[i - 1]
                    if not (np.isfinite(c) and np.isfinite(p) and np.isfinite(t.f[i, 3]) and np.isfinite(t.f[i - 1, 3])):
                        continue
                    for d, wall, prev_wall in ((1, cw, pcw), (-1, pw, ppw)):
                        if d in done or wall is None or prev_wall is None:
                            continue
                        if d * (c - wall) > 0 and d * (p - prev_wall) <= 0 and d * (t.f[i, 3] - t.f[i - 1, 3]) > 0:
                            done.add(d)
                            r = ticket(t, i, d, low, flat)
                            if r:
                                events += 1; mults.append(r["best"])
                                for x in ("hold", "t5_s50", "t10_s50"):
                                    days[t.day][x] += r[x]
            tot = {x: sum(v[x] for v in days.values()) for x in ("hold", "t5_s50", "t10_s50")}
            xb = {x: tot[x] - max((v[x] for v in days.values()), default=0) for x in tot}
            pos = {x: sum(v[x] > 0 for v in days.values()) for x in tot}
            print(f"band {low:>4}-20 {y} events {events:>3} days {len(days):>2} " +
                  "  ".join(f"{x} {tot[x]:>8.0f} (xb {xb[x]:>8.0f}, +days {pos[x]})" for x in tot) +
                  f"  reached5x {sum(m >= 5 for m in mults)} reached10x {sum(m >= 10 for m in mults)}", flush=True)


if __name__ == "__main__":
    main()
