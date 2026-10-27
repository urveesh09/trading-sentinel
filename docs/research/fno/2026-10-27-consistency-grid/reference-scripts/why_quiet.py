"""Read-only, inside python-engine: for each recent NIFTY session, the live F&O decisions around the opening-range
break (first bars that were not inside the range / not 'no break') and how far the future went afterwards."""
import sqlite3
import sys
from collections import Counter

from config import settings

c = sqlite3.connect(f"file:{settings.DB_PATH}?mode=ro", uri=True)
c.row_factory = sqlite3.Row
for day in sys.argv[1:]:
    rows = [dict(r) for r in c.execute(
        "SELECT bar_ts, evaluated_at, direction, accepted, reject_reason, fut_price, or_high, or_low, atr, rvol, "
        "ema_fast, ema_slow FROM fno_signals WHERE underlying='NIFTY' AND bar_ts LIKE ? AND (leg IS NULL OR "
        "leg IN ('','SINGLE','single','single_leg','SINGLE_LEG')) ORDER BY evaluated_at", (day + "%",))]
    if not rows:
        rows = [dict(r) for r in c.execute(
            "SELECT bar_ts, evaluated_at, direction, accepted, reject_reason, fut_price, or_high, or_low, atr, rvol, "
            "ema_fast, ema_slow FROM fno_signals WHERE underlying='NIFTY' AND bar_ts LIKE ? ORDER BY evaluated_at",
            (day + "%",))]
    seen, shown = set(), 0
    print(f"=== {day}: {len(rows)} evaluations; reasons {dict(Counter(r['reject_reason'] for r in rows))}")
    if rows:
        r0 = rows[0]
        print(f"  OR {r0['or_low']} - {r0['or_high']}  ATR {r0['atr']}")
    for r in rows:
        if r["bar_ts"] in seen:
            continue
        seen.add(r["bar_ts"])
        if r["reject_reason"] in ("inside_opening_range_window", "no_or_break") and shown == 0:
            continue
        if shown < 6:
            print(f"  {r['bar_ts'][11:16]} {r['direction']} acc={r['accepted']} {r['reject_reason']} fut={r['fut_price']} "
                  f"rvol={r['rvol'] and round(r['rvol'], 2)} ema={r['ema_fast'] and round(r['ema_fast'])}/"
                  f"{r['ema_slow'] and round(r['ema_slow'])}")
            shown += 1
    prices = [r["fut_price"] for r in rows if r["fut_price"]]
    if prices and rows[0]["or_high"]:
        print(f"  future: first {prices[0]}, high {max(prices)}, low {min(prices)}, last {prices[-1]}; "
              f"above OR high by up to {round(max(prices) - rows[0]['or_high'])} pts, below OR low by up to "
              f"{round(rows[0]['or_low'] - min(prices))} pts")
