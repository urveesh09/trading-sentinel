"""SN85: Gold v5's second lot by the 09:45 opening-range width (SN80: wide OR -> big day), every wallet. Before 09:45
the opening range is not known yet, so an earlier entry keeps v5's volatility rule."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn51"))
sys.path.insert(0, str(HERE))
import lab as L
import sn80 as Z
OR_RANK = {}
_orig = L.size
def size(S, sg, v, full, ctx, vol_day):
    rule = v.get("size", "vol")
    if rule.startswith("or") and full > 1:
        small = max(1, full // 2)
        if sg["i"] < 30 or OR_RANK.get(S.day) is None:
            return full if vol_day else small
        wide = OR_RANK[S.day] >= 0.67
        if rule == "or_wide":
            return full if wide else small
        if rule == "or_wide|vol":
            return full if (wide or vol_day) else small
        if rule == "or_wide&vol":
            return full if (wide and vol_day) else small
        if rule == "or_not_tight":
            return full if OR_RANK[S.day] > 0.33 else small
    return _orig(S, sg, v, full, ctx, vol_day)
L.size = size
V5 = {"extend": True, "ext_x": 0.25, "ext_k": 3.0, "itm_if_fits": True, "in_x": None, "in_atr": 1.0, "in_full": True,
      "itm_auto": (17500, 20000), "books": ("N11", "R0.85")}
if __name__ == "__main__":
    OR_RANK.update({d: r["or_rank"] for d, r in Z.day_table().items()})
    V = {"SN Gold v4": {**V5, "books": ("N11",), "in_x": 0.10, "in_atr": None, "in_full": False}, "SN Gold v5": dict(V5)}
    for rule in ("or_wide", "or_wide|vol", "or_wide&vol", "or_not_tight"):
        V[f"SN85 v5 + 2nd lot {rule}"] = {**V5, "size": rule}
    import json
    res = L.study("sn85", V, HERE)
    for n, r in res.items():
        print(f"{n:34s} worst", {w.split()[0]: min(r[w][y]["worst"] for y in L.YEARS) for w in ("C 30k sized", "G3 (Gold)", "G5")})
