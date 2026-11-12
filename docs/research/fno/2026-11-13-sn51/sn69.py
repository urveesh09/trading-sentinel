"""SN69 - a small, fair contest to build v5 from the parts that helped (fewer candidates -> less selection luck)."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab as L
V4 = {"extend": True, "ext_x": 0.25, "ext_k": 3.0, "itm_if_fits": True, "in_x": 0.10, "itm_auto": (17500, 20000)}
R = {"books": ("N11", "R0.85")}
ATR1 = {"in_x": None, "in_atr": 1.0}
V = {"SN Gold v4": dict(V4),
     "v4 + R0.85 entries": {**V4, **R},
     "v4 + scale-in at 1 ATR": {**V4, **ATR1},
     "v4 + R0.85 + scale-in at 1 ATR": {**V4, **R, **ATR1},
     "v4 + R0.85 + 1 ATR + pyramid to full": {**V4, **R, **ATR1, "in_full": True},
     "v4 + R0.85 + 1 ATR + day limit 30%": {**V4, **R, **ATR1, "loss_share": 0.30}}
if __name__ == "__main__":
    res = L.study("sn69", V, HERE)
    for n, r in res.items():
        print(f"{n:42s} worst", {w.split()[0]: min(r[w][y]["worst"] for y in L.YEARS) for w in ("A 15k 1 lot", "B 20k 1 lot", "C 30k sized", "G3 (Gold)", "G5")},
              "G3 won/refilled", sum(r["G3 (Gold)"][y]["net"] + r["G3 (Gold)"][y]["refilled"] for y in L.YEARS), sum(r["G3 (Gold)"][y]["refilled"] for y in L.YEARS))
