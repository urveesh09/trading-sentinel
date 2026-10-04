"""Run the single-leg F&O replay for one rule-set / bankroll scenario (research driver)."""
import json
import os
import sys
from collections import defaultdict

engine, label, bankroll, mode, out = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4], sys.argv[5]
sys.path.insert(0, engine)
os.chdir(engine)

from config import settings  # noqa: E402
import fno_policy_replay as rp  # noqa: E402

DATA = r"C:\Users\Urveesh\Desktop\trading-sentinel\docs\research\fno\2026-10-04-archive\_local"
START, END = "2026-09-17", "2026-10-01"

settings.FNO_PAPER_BANKROLL = bankroll
if mode == "fresh":
    # A brand-new live account: no earlier paper history, no capped-loss book closes.
    rp.ReplayData.paper_closes = lambda self: []

result = rp.run_replay(DATA, start=START, end=END)
trades = [t for t in result["trades"] if "net_pnl" in t]
daily = defaultdict(float)
for t in trades:
    daily[t["exit_time"][:10]] += t["net_pnl"]
report = {
    "label": label, "bankroll": bankroll, "mode": mode, "window": result["window"],
    "sessions": result["sessions"], "start_equity": result["start_equity"],
    "summary": result["summary"],
    "daily": {d: round(v, 2) for d, v in sorted(daily.items())},
    "trades": [{k: t.get(k) for k in ("entry_time", "tradingsymbol", "direction", "lots_at_exit",
                                       "entry_premium", "exit_premium", "exit_reason", "net_pnl")}
               for t in trades],
    "unresolved": [t for t in result["trades"] if t.get("status") == "UNRESOLVED"],
    "funnel": result["funnel"],
    "decisions": result["decisions"],
    "parity_vs_live": {k: result["parity_vs_live"][k] for k in ("live_trades", "replayed_trades")},
    "notes": result["notes"],
}
with open(out, "w", encoding="utf-8") as fh:
    json.dump(report, fh, indent=2, default=str)
s = report["summary"]
print(f"{label:28s} trades={s['closed']:2d} net={s['net_pnl']:>10.0f} exBest={s['net_excluding_best_winner']:>9.0f} "
      f"maxDD={s['max_drawdown']:>7.0f} win%={s['win_rate_pct']} PF={s['profit_factor']}")
