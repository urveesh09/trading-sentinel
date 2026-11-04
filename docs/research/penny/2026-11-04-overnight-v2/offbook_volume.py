"""Volume outside the 09:15-15:29 minute bars = daily volume - sum(minute volumes).

That residual is the pre-open auction (if not inside the 09:15 bar) plus the
15:40-16:00 post-close session at the official close. Dev minute data only.
Also splits it by whether the 09:15 bar open equalled the official open.
"""
import sqlite3, statistics as st
from collections import defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SRC = [ROOT / "docs/research/penny/2026-11-04-strategy-search/_local/production-cash.sqlite",
       ROOT / "docs/research/2026-10-03-current-system/_local/stopped-production/cache.db"]
mv = defaultdict(float); mn = defaultdict(int); last = {}; first_vol = {}
daily = {}
for p in SRC:
    c = sqlite3.connect(p.as_uri() + "?mode=ro", uri=True)
    seen = set()
    for t, dt, v in c.execute("SELECT ticker, datetime, volume FROM intraday_cache WHERE interval='minute' AND datetime >= '2026-07-30'"):
        k = (t, dt[:10])
        if (k, dt) in seen or k in daily and False:
            continue
        seen.add((k, dt))
        if k in last and p != last[k][0]:
            continue
        last[k] = (p, dt)
        mv[k] += v or 0; mn[k] += 1
        if dt[11:16] == "09:15": first_vol[k] = v or 0
    for t, d, cl, v in c.execute("SELECT ticker,date,close,volume FROM ohlcv_cache WHERE date >= '2026-07-30'"):
        daily.setdefault((t, d), (cl, v))
res, tvres = [], []
for k, n in mn.items():
    if n < 370 or k not in daily or not daily[k][1]:
        continue
    cl, dv = daily[k]
    r = (dv - mv[k]) / dv
    res.append(r); tvres.append((dv - mv[k]) * cl)
q = sorted(res); qt = sorted(tvres)
print(f"full-minute days n={len(res)}  residual share of daily volume: mean={100*st.mean(res):.2f}% med={100*st.median(res):.2f}% "
      f"p10={100*q[len(q)//10]:.2f}% p25={100*q[len(q)//4]:.2f}% p75={100*q[3*len(q)//4]:.2f}% p90={100*q[9*len(q)//10]:.2f}%")
print(f"residual traded value Rs: med={st.median(tvres):,.0f} p25={qt[len(qt)//4]:,.0f} p75={qt[3*len(qt)//4]:,.0f} p90={qt[9*len(qt)//10]:,.0f}")
print("share of days with residual > 0.5% of volume:", f"{100*sum(r>0.005 for r in res)/len(res):.0f}%", "negative:", f"{100*sum(r<-0.001 for r in res)/len(res):.0f}%")
