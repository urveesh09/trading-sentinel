"""Minute-bar facts around the overnight trade (dev minute data only: Jul 30 - Nov 3 2026).

Sources: Production cash export (Nov 3) and the stopped-Production copy (Oct 3); the
reserved Jan-Jul 2026 penny-h1 archive is NOT read. For each (ticker, day) with both a
daily bar and minute bars: official close vs the 15:20 minute close and the 15:00-15:30
VWAP; official open vs the 09:15 minute open; and on the following morning, what a
seller got in 09:15-09:20 when the daily open equalled the previous close (placeholder).
"""
import sqlite3, statistics as st, sys
from collections import defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SRC = [ROOT / "docs/research/penny/2026-11-04-strategy-search/_local/production-cash.sqlite",
       ROOT / "docs/research/2026-10-03-current-system/_local/stopped-production/cache.db"]

def load():
    minute = defaultdict(dict)   # (t, day) -> {hhmm: (o,h,l,c,v)}
    daily = {}
    for p in SRC:
        c = sqlite3.connect(p.as_uri() + "?mode=ro", uri=True)
        for t, dt, o, h, l, cl, v in c.execute(
                "SELECT ticker, datetime, open, high, low, close, volume FROM intraday_cache "
                "WHERE interval='minute' AND datetime >= '2026-07-30'"):
            minute[(t, dt[:10])].setdefault(dt[11:16], (o, h, l, cl, v))
        for t, d, o, h, l, cl, v in c.execute("SELECT ticker,date,open,high,low,close,volume FROM ohlcv_cache WHERE date >= '2026-07-29'"):
            daily.setdefault((t, d), (o, h, l, cl, v))
    return minute, daily

def main():
    minute, daily = load()
    by_t = defaultdict(list)
    for (t, d) in daily:
        by_t[t].append(d)
    close_vs_1520, close_vs_vwap, open_vs_0915, ph = [], [], [], []
    for t, ds in by_t.items():
        ds.sort()
        for a, b in zip(ds, ds[1:]):
            m = minute.get((t, a)); n = minute.get((t, b))
            o, h, l, c, v = daily[(t, a)]
            if m and "15:20" in m and c:
                close_vs_1520.append(c / m["15:20"][3] - 1)
                w = [(x[3], x[4]) for k, x in m.items() if "15:00" <= k <= "15:29" and x[4]]
                if w and sum(q for _, q in w) > 0:
                    close_vs_vwap.append(c / (sum(p * q for p, q in w) / sum(q for _, q in w)) - 1)
            ob = daily[(t, b)][0]
            if n and "09:15" in n:
                open_vs_0915.append(ob / n["09:15"][0] - 1)
                if ob == c:
                    first = [n[k] for k in sorted(n) if k <= "09:20"]
                    if first:
                        vw = sum(x[3] * x[4] for x in first) / max(1e-9, sum(x[4] for x in first))
                        ph.append({"t": t, "day": b, "o915": n["09:15"][0] / c - 1, "c917": (n.get("09:17") or first[-1])[3] / c - 1,
                                   "vwap0920": vw / c - 1 if sum(x[4] for x in first) > 0 else None,
                                   "minutes": len(first)})
    def d(name, xs):
        xs = [x for x in xs if x is not None]
        q = sorted(xs)
        print(f"{name:34s} n={len(xs):6d} mean={100*st.mean(xs):+.3f}% med={100*st.median(xs):+.3f}% "
              f"p10={100*q[len(q)//10]:+.2f}% p90={100*q[9*len(q)//10]:+.2f}% exact0={100*sum(abs(x)<1e-9 for x in xs)/len(xs):.0f}%")
    d("official close / 15:20 close - 1", close_vs_1520)
    d("official close / 15:00-15:29 vwap - 1", close_vs_vwap)
    d("official open / 09:15 open - 1", open_vs_0915)
    print("placeholder mornings (daily open == prior close):", len(ph))
    d("  09:15 first trade vs prior close", [x["o915"] for x in ph])
    d("  09:17 close vs prior close", [x["c917"] for x in ph])
    d("  09:15-09:20 vwap vs prior close", [x["vwap0920"] for x in ph])

if __name__ == "__main__":
    main()
