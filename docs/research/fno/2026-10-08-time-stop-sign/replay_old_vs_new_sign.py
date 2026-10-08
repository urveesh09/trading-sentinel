"""Exit-rule comparison with the drawdown halt removed (identical entries)."""
import sys, json, importlib.util
sys.path.insert(0, r"C:/Users/Urveesh/Desktop/trading-sentinel/python-engine")
which, root, start, end, out = sys.argv[1:6]
if which == "old":
    spec = importlib.util.spec_from_file_location("fno_exit_rules", sys.argv[6])
    mod = importlib.util.module_from_spec(spec); sys.modules["fno_exit_rules"] = mod; spec.loader.exec_module(mod)
from config import settings
settings.FNO_MAX_DRAWDOWN_PCT = 0.9
from fno_policy_replay import ReplayData, ReplayPolicy, SingleLegReplay
data = ReplayData(root)
BEST = (("FNO_PROFIT_LOCK_ENABLED", True), ("FNO_PROFIT_LOCK_ARM_R", 0.4),
        ("FNO_PROFIT_LOCK_FLOOR_R", 0.1), ("FNO_PROFIT_LOCK_KEEP_FRACTION", 0.5))
arms = {"BASE": ReplayPolicy(name="BASE", exit_overrides=(("FNO_PROFIT_LOCK_ENABLED", False),), reentry_confirmation=False),
        "SHIPPED": ReplayPolicy(name="SHIPPED", exit_overrides=BEST, reentry_confirmation=True),
        "SHIPPED_NO_DEFER": ReplayPolicy(name="SHIPPED_NO_DEFER", exit_overrides=BEST + (("FNO_TIME_STOP_RESPECTS_PREMIUM", False),), reentry_confirmation=True)}
res = {}
for name, pol in arms.items():
    r = SingleLegReplay(data, pol).run(start, end)
    res[name] = {"summary": r["summary"], "trades": [{k: t.get(k) for k in ("entry_time", "exit_time", "exit_reason", "net_pnl", "direction")} for t in r["trades"]]}
    s = r["summary"]
    print(which, name, s["closed"], round(s["net_pnl"]), "dd", round(s["max_drawdown"]), "pf", s["profit_factor"], flush=True)
json.dump(res, open(out, "w"), indent=1, default=str)
