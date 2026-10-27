"""Exploration on SEEN sessions: the shipped book (CURRENT) vs the same book whose entry does not require the
multi-day EMA trend agreement at the opening-range break (FNO_NO_EMA, Dev working tree). Full replay: live entry plan,
sizing, brakes, exit ladder at fast-exit cadence, bid/ask, costs. Development only."""
import json
import sys

sys.path.insert(0, r"C:\Users\Urveesh\Desktop\trading-sentinel\python-engine")
import fno_policy_replay as R  # noqa: E402
import fno_shadow as S  # noqa: E402
from config import settings  # noqa: E402

ROOT = sys.argv[4] if len(sys.argv) > 4 else \
    r"C:\Users\Urveesh\Desktop\trading-sentinel\docs\research\fno\2026-10-24-entry-arms\_local"
START, END, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
S.VARIANTS = {**S.VARIANTS, "FNO_NO_EMA": S.FnoShadowVariant("FNO_NO_EMA", int(settings.FNO_OR_MINUTES), "crossing",
                                                            ema_filter=False)}
R.POLICIES["FNO_SIG_NO_EMA"] = R.ReplayPolicy(name="FNO_SIG_NO_EMA", manage_every_observation=True,
                                              signal_variant="FNO_NO_EMA")
out = {}
for policy in ("CURRENT", "FNO_SIG_NO_EMA"):
    res = R.run_replay(ROOT, start=START, end=END, policy=policy)
    out[policy] = res
    print(policy, json.dumps(res["summary"]), flush=True)
    for t in res["trades"]:
        if "net_pnl" in t:
            print("   ", t["entry_time"][:16], t["direction"], t["tradingsymbol"], t["exit_reason"], round(t["net_pnl"]))
    print("   funnel:", {k: v for k, v in res["funnel"].items() if v})
    print("   notes:", res["notes"])
json.dump(out, open(OUT, "w"), indent=1, default=str)
