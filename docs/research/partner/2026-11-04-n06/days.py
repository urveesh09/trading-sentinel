"""Read-only: the partner's result per day next to the Sentinel's own paper books on the same days."""
import sqlite3
from collections import defaultdict

db = sqlite3.connect("file:/data/cache.db?mode=ro", uri=True)
part = defaultdict(lambda: [0, 0, 0.0])
for day, realised in db.execute(
        "SELECT session_date, realised FROM partner_watch_trips WHERE closed_at IS NOT NULL AND carried=0"):
    p = part[day]
    p[0] += 1
    p[1] += 1 if (realised or 0) > 0 else 0
    p[2] += realised or 0
acct = {r[0]: r[1:] for r in db.execute("SELECT session_date, opening_balance, live_balance FROM partner_account_days")}

fno = defaultdict(lambda: [0, 0.0, set()])
for day, src, pnl, strat, und in db.execute(
        "SELECT exit_date, source, pnl, strategy, underlying FROM fno_positions WHERE status='CLOSED' AND exit_date>='2026-10-20'"):
    f = fno[(day, src)]
    f[0] += 1
    f[1] += pnl or 0
    f[2].add(f"{strat}/{und}")

e = sqlite3.connect("file:/data/cache.db.expiry-paper.db?mode=ro", uri=True)
cols = [r[1] for r in e.execute("PRAGMA table_info(expiry_paper_positions)")]
print("expiry cols", cols)
exp = defaultdict(float)
expn = defaultdict(int)
dcol = "session_date" if "session_date" in cols else ("day" if "day" in cols else None)
pcol = "pnl" if "pnl" in cols else None
if dcol and pcol:
    q = f"SELECT {dcol}, play, underlying, {pcol} FROM expiry_paper_positions" if {"play", "underlying"} <= set(cols) else f"SELECT {dcol}, '', '', {pcol} FROM expiry_paper_positions"
    for day, play, und, pnl in e.execute(q):
        exp[(day, play, und)] += pnl or 0
        expn[(day, play, und)] += 1

days = sorted(set(part) | {d for d, _ in fno})
for d in days:
    if d < "2026-10-26":
        continue
    p = part.get(d)
    a = acct.get(d)
    line = f"{d} partner " + (f"{p[0]} trades {p[1]} won {p[2]:+,.0f}" if p else "-")
    if a:
        line += f" (cash {a[0]:,.0f} -> {a[1] if a[1] is None else round(a[1]):,})"
    for (dd, src), f in sorted(fno.items()):
        if dd == d:
            line += f" | {src} {f[0]} {f[1]:+,.0f} {sorted(f[2])}"
    print(line)
print("--- expiry book")
for k in sorted(exp):
    if k[0] >= "2026-10-20":
        print(k, expn[k], round(exp[k]))
