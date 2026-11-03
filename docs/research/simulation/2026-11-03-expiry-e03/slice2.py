"""Day-level view of cheap-vs-realized tickets: one Rs ~1,000 ticket per day = the day's mean ticket."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-03-expiry-e02"))
import e02_lab as E
df = pd.read_csv(HERE / "_local/surface.csv")
lots = np.clip(np.floor(1000 / (df.entry * 65)), 1, 10); qty = lots * 65
for x in ["hold", "t5", "t10", "hold_s50", "t5_s50", "t10_s50", "t3_s50"]:
    sale = df[x] * df.entry
    df["rs_" + x] = (sale - df.entry) * qty - np.array([E.fee(p, q, True) + (E.fee(s, q, False) if s > 0 else 0) for p, s, q in zip(df.entry, sale, qty)])
def day_view(mask, label):
    g = df[mask].groupby(["year", "day"]).agg(**{x: ("rs_" + x, "mean") for x in ["hold", "hold_s50", "t5_s50", "t10_s50", "t3_s50"]})
    for y in (2024, 2025):
        d = g.loc[y] if y in g.index.get_level_values(0) else None
        if d is None: print(label, y, "none"); continue
        s = d.sum(); best = d.max()
        print(f"{label:<34} {y} days {len(d):>2}  " + "  ".join(f"{k} {s[k]:>8.0f} (xb {s[k]-best[k]:>7.0f}, +days {int((d[k]>0).sum())})" for k in d.columns))
for lim in (0.8, 1.0, 1.2, 1.5):
    day_view(df.ivrv <= lim, f"ivrv<={lim}")
    day_view((df.ivrv <= lim) & (df.entry >= 4), f"ivrv<={lim} & price>=4")
day_view(df.ivrv > 0, "all")
# is low ivrv just distance? correlation
print(df[["ivrv", "dist", "reach", "entry", "rv60", "minute"]].corr().round(2).ivrv)
