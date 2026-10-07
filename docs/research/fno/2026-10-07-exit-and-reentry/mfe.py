"""Max favourable excursion of every archived FNO_PAPER single-leg trade."""
import sqlite3, sys, json
from datetime import datetime
sys.path.insert(0, r"C:/Users/Urveesh/Desktop/trading-sentinel/python-engine")
import pytz
from fno_policy_replay import ReplayData
from fno_costs import calc_fno_costs

IST = pytz.timezone("Asia/Kolkata")
root = sys.argv[1]
data = ReplayData(root)
con = sqlite3.connect(f"{root}/fno-replay.sqlite")
con.row_factory = sqlite3.Row
rows = con.execute("SELECT * FROM fno_positions WHERE source='FNO_PAPER' AND status='CLOSED' ORDER BY entry_time").fetchall()
cache = {}
out = []
for r in rows:
    day = r["entry_date"]
    if day not in data.days or r["underlying"] not in (None, "NIFTY"):
        continue
    if day not in cache:
        cache[day] = data.observations(day)[0]
    et = datetime.fromisoformat(r["entry_time"]); et = et if et.tzinfo else IST.localize(et)
    xt = datetime.fromisoformat(r["exit_time"]); xt = xt if xt.tzinfo else IST.localize(xt)
    tok = int(r["token"])
    long_view = r["direction"] == "LONG"
    rpts = abs(r["entry_underlying"] - r["stop_underlying"])
    path = []
    for o in cache[day]:
        if o.at <= et or o.at > xt:
            continue
        q = o.options.get(tok)
        if q is None:
            continue
        bid = q.bid if q.bid and q.bid > 0 else q.ltp
        prog = (o.future.ltp - r["entry_underlying"]) if long_view else (r["entry_underlying"] - o.future.ltp)
        path.append((o.at, bid, prog / rpts if rpts else 0))
    if not path:
        out.append({"id": r["id"], "day": day, "pnl": r["pnl"], "note": "no path"}); continue
    best = max(path, key=lambda p: p[1])
    qty = r["qty"]; ep = r["entry_premium"]
    best_net = (best[1] - ep) * qty - calc_fno_costs(ep, best[1], qty)
    out.append({"id": r["id"], "day": day, "reason": r["exit_reason"], "pnl": round(r["pnl"], 0),
                "entry": ep, "best_bid": best[1], "best_net": round(best_net, 0),
                "best_at_min": round((best[0] - et).total_seconds() / 60, 1),
                "max_prog_R": round(max(p[2] for p in path), 2), "n": len(path)})
for x in out:
    print(json.dumps(x))
