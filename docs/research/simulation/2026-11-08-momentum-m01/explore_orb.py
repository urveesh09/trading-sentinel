"""DEV only: stocks-in-play opening-range breakout, a few arms and the first-bar volume distribution."""
import sys, time
import numpy as np, pandas as pd
import lab, lab_data

if __name__ == "__main__":
    data = lab_data.load_dev()
    days = sorted({d for (_, d) in data["bars"]})
    t = time.time()
    rel = [u[2] for d in days for u in lab.day_universe(data, d)]
    print("universe/day", round(len(rel) / len(days)), "rel quantiles", np.round(np.quantile(rel, [.5, .8, .95, .99]), 3), round(time.time() - t), "s")
    for arm in [lab.Orb("top5"), lab.Orb("top5_atr50", stop="atr:0.5"), lab.Orb("top10", top=10),
                lab.Orb("top5_mkt", market=True), lab.Orb("top5_vwap", exit=lab.Exit("vwap", vwap_exit=True)),
                lab.Orb("top3", top=3), lab.Orb("top5_0945", last_entry="09:45")]:
        trades = [x for d in days for x in lab.orb_day(data, d, arm, 600.0, lab.POOL / arm.top)]
        print(arm.name, lab.summary(trades))
    rng = np.random.default_rng(1)
    null = [x for d in days for x in lab.orb_day(data, d, lab.Orb("null5"), 600.0, lab.POOL / 5, rng=rng)]
    print("NULL5", lab.summary(null))
