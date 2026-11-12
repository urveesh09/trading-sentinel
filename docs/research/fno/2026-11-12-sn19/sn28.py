"""SN28 rerun with the day-limit fix: scale-in only when the whole position still fits the day's loss room."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gold as Gd
G2 = {**Gd.GOLD, "itm_if_fits": True}
V = {"SN Gold": dict(Gd.GOLD), "SN Gold v2": dict(G2)}
for x in (0.05, 0.10, 0.20, 0.40):
    V[f"SN28 scale-in 1 lot at +{int(x*100)}%"] = {**G2, "in_x": x}
if __name__ == "__main__":
    import json
    res = Gd.study("sn28-fixed", V, HERE)
    for n, r in res.items():
        print(n, "worst", {w: min(r[w][y]["worst"] for y in Gd.YEARS) for w in ("A 15k 1 lot", "B 20k 1 lot", "C 30k sized", "G3 (Gold)", "G5")})
