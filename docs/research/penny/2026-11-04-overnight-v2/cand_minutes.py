"""Minute paths for shipped candidates (dev minute data Jul 30 - Oct 1 2026, Kite days panel).
Entry side: price at 15:00/15:10/15:20/15:25/15:29 vs official close.
Exit side: next morning 09:15 open (auction) vs 09:16..09:45 closes."""
import sqlite3, statistics as st, sys
from collections import defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab
from microstructure import SRC
minute = defaultdict(dict)
for p in SRC:
    c = sqlite3.connect(p.as_uri() + "?mode=ro", uri=True)
    for t, dt, o, h, l, cl, v in c.execute("SELECT ticker, datetime, open, high, low, close, volume FROM intraday_cache WHERE interval='minute' AND datetime >= '2026-07-30'"):
        minute[(t, dt[:10])].setdefault(dt[11:16], (o, h, l, cl, v))
days = lab.load(HERE / "_local/days-kite.pkl")
ent = defaultdict(list); ex = defaultdict(list); n_c = 0
for d in days:
    if d.date < "2026-07-30":
        continue
    for c in d.cands[:10]:
        b, pc, nx = d.bar[c.ticker], d.prev_close.get(c.ticker), d.nxt.get(c.ticker)
        if c.kind == "MR_mid" or c.ticker.endswith(("-SM", "-ST")) or nx is None:
            continue
        if pc and b["close"] >= b["high"] * 0.999 and b["close"] / pc - 1 >= .019:
            continue
        m, n = minute.get((c.ticker, d.date)), minute.get((c.ticker, nx["date"]))
        if m:
            for k in ("15:00", "15:10", "15:15", "15:20", "15:25", "15:29"):
                if k in m: ent[k].append(m[k][3] / b["close"] - 1)
        if n and "09:15" in n:
            n_c += 1
            o = nx["open"]
            ex["auction_vs_close"].append(o / b["close"] - 1)
            for k in ("09:15", "09:16", "09:17", "09:20", "09:25", "09:30", "09:45", "10:30"):
                if k in n: ex[k].append(n[k][3] / o - 1)
print("candidates with next-morning minutes:", n_c)
for k, v in ent.items(): print(f"entry {k} close / official close - 1: n={len(v)} mean={100*st.mean(v):+.3f}% med={100*st.median(v):+.3f}%")
for k, v in ex.items(): print(f"exit  {k:16s} vs auction open: n={len(v)} mean={100*st.mean(v):+.3f}% med={100*st.median(v):+.3f}%")
