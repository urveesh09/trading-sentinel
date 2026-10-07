"""Profit-lock / re-entry grid over every archived session (development evidence)."""
import json, sys, time
sys.path.insert(0, r"C:/Users/Urveesh/Desktop/trading-sentinel/python-engine")
from fno_policy_replay import ReplayData, ReplayPolicy, SingleLegReplay, parity_report

root, start, end, out = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
data = ReplayData(root)
_cache = {}
_orig = data.observations
def cached(day):
    if day not in _cache:
        _cache[day] = _orig(day)
    return _cache[day]
data.observations = cached

OFF = (("FNO_PROFIT_LOCK_ENABLED", False),)
arms = {"BASELINE_NO_LOCK": ReplayPolicy(name="BASELINE_NO_LOCK", exit_overrides=OFF, reentry_confirmation=False)}
for arm in (0.2, 0.25, 0.3, 0.4, 0.5):
    for floor in (0.05, 0.1, 0.15):
        if floor >= arm:
            continue
        for keep in (0.0, 0.5):
            name = f"LOCK_a{arm}_f{floor}_k{keep}"
            arms[name] = ReplayPolicy(name=name, reentry_confirmation=False, exit_overrides=(
                ("FNO_PROFIT_LOCK_ENABLED", True), ("FNO_PROFIT_LOCK_ARM_R", arm),
                ("FNO_PROFIT_LOCK_FLOOR_R", floor), ("FNO_PROFIT_LOCK_KEEP_FRACTION", keep)))
BEST = (("FNO_PROFIT_LOCK_ENABLED", True), ("FNO_PROFIT_LOCK_ARM_R", 0.4),
        ("FNO_PROFIT_LOCK_FLOOR_R", 0.1), ("FNO_PROFIT_LOCK_KEEP_FRACTION", 0.5))
EARLY = (("FNO_PROFIT_LOCK_ENABLED", True), ("FNO_PROFIT_LOCK_ARM_R", 0.2),
         ("FNO_PROFIT_LOCK_FLOOR_R", 0.1), ("FNO_PROFIT_LOCK_KEEP_FRACTION", 0.5))
arms["LOCK_PLUS_REENTRY"] = ReplayPolicy(name="LOCK_PLUS_REENTRY", exit_overrides=BEST, reentry_confirmation=True)
arms["FAST_NO_LOCK"] = ReplayPolicy(name="FAST_NO_LOCK", exit_overrides=OFF, reentry_confirmation=False, manage_every_observation=True)
arms["FAST_EARLY_LOCK"] = ReplayPolicy(name="FAST_EARLY_LOCK", exit_overrides=EARLY, reentry_confirmation=False, manage_every_observation=True)
arms["FAST_BEST_LOCK"] = ReplayPolicy(name="FAST_BEST_LOCK", exit_overrides=BEST, reentry_confirmation=False, manage_every_observation=True)
arms["REENTRY_ONLY"] = ReplayPolicy(name="REENTRY_ONLY", exit_overrides=OFF, reentry_confirmation=True)
if len(sys.argv) > 5:
    arms = {k: v for k, v in arms.items() if k in sys.argv[5].split(",") or k == "BASELINE_NO_LOCK"}
results = {}
for name, pol in arms.items():
    t = time.time()
    r = SingleLegReplay(data, pol).run(start, end)
    s = r["summary"]
    results[name] = {"summary": s, "trades": [{k: t_.get(k) for k in ("entry_time", "exit_time", "exit_reason", "net_pnl", "direction")} for t_ in r["trades"]]}
    if name == "BASELINE_NO_LOCK":
        results[name]["parity"] = parity_report(r["trades"], data.live_single_leg(start, end))
    print(f"{name:28s} n={s['closed']:3d} net={s['net_pnl']:10.0f} exbest={s['net_excluding_best_winner']:10.0f} "
          f"dd={s['max_drawdown']:8.0f} win={s['win_rate_pct']} pf={s['profit_factor']} {s['exit_reasons']} ({time.time()-t:.0f}s)",
          flush=True)
json.dump(results, open(out, "w"), indent=1, default=str)
