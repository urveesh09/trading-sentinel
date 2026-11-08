"""The runtime momentum_orb_shadow reproduces the frozen research arm A3 trade for trade on both windows."""
import sys
import pandas as pd
import lab, lab_data
import momentum_orb_shadow as rt

if __name__ == "__main__":
    for window, loader in (("DEV", lab_data.load_dev), ("EXAM", lab_data.load_exam)):
        data = loader()
        days = sorted({d for (_, d) in data["bars"]})
        arm = lab.Orb("top5_vwap", exit=lab.Exit("VWAP", vwap_exit=True))
        bad, research_net, runtime_net, n = 0, 0.0, 0.0, 0
        for day in days:
            ours = lab.orb_day(data, day, arm, 600.0, lab.POOL / 5)
            bars = {t: b for (t, d), b in data["bars"].items() if d == day and t != lab.INDEX}
            prior = {t: p for t in bars if (p := lab.prior_daily(data, t, day, 30)) is not None}
            theirs = rt.session_trades(day, bars, prior)["trades"]
            key = lambda x: (x["ticker"], x["entry_at"], round(x["entry"], 6), x["qty"], x["reason"], round(x["net"], 6))
            bad += sorted(map(key, ours)) != sorted(map(key, theirs))
            research_net += sum(x["net"] for x in ours); runtime_net += sum(x["net"] for x in theirs); n += len(theirs)
        print(window, "days", len(days), "mismatched days", bad, "trades", n, "research net", round(research_net, 2), "runtime net", round(runtime_net, 2))
