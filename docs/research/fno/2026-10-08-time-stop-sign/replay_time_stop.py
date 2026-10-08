import sys, json
sys.path.insert(0, r"C:/Users/Urveesh/Desktop/trading-sentinel/python-engine")
root, start, end, out, dd = sys.argv[1:6]
from config import settings
settings.FNO_MAX_DRAWDOWN_PCT = float(dd)
from fno_policy_replay import ReplayData, ReplayPolicy, SingleLegReplay
data = ReplayData(root)
BEST = (("FNO_PROFIT_LOCK_ENABLED", True), ("FNO_PROFIT_LOCK_ARM_R", 0.4),
        ("FNO_PROFIT_LOCK_FLOOR_R", 0.1), ("FNO_PROFIT_LOCK_KEEP_FRACTION", 0.5))
arms = {"DEFER": BEST, "NO_DEFER": BEST + (("FNO_TIME_STOP_RESPECTS_PREMIUM", False),),
        "DEFER_NEEDS_LOCK": BEST + (("FNO_TIME_STOP_DEFER_NEEDS_LOCK", True),)}
res = {}
for name, ov in arms.items():
    r = SingleLegReplay(data, ReplayPolicy(name=name, exit_overrides=ov, reentry_confirmation=True)).run(start, end)
    s = r["summary"]; res[name] = {"summary": s, "trades": r["trades"]}
    print(f"dd{dd}", name, s["closed"], round(s["net_pnl"]), "exbest", round(s["net_excluding_best_winner"]), "maxdd", round(s["max_drawdown"]), "pf", s["profit_factor"], "win", s["win_rate_pct"], flush=True)
json.dump(res, open(out, "w"), indent=1, default=str)
