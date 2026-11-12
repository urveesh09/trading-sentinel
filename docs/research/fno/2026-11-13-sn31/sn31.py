"""SN31-SN37: tune and extend each kept part of SN Gold v3 (every wallet, held out per wallet)."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab as L
V3 = {"extend": True, "ext_x": 0.25, "ext_k": 3.0, "itm_if_fits": True, "in_x": 0.10}
V = {"SN Gold": {"extend": True, "ext_x": 0.25, "ext_k": 3.0}, "SN Gold v3": dict(V3)}
for x in (0.0, 0.5):                                     # SN31 extension threshold
    V[f"SN31 extend at +{int(x*100)}%"] = {**V3, "ext_x": x}
for k in (2.0, 4.0):                                     # SN32 extension trail width
    V[f"SN32 extension trail {k} ATR"] = {**V3, "ext_k": k}
V["SN33 ITM two strikes when it fits"] = {**V3, "itm_depth": 2}
for n, x in ((2, 0.10), (2, 0.20), (3, 0.10)):           # SN34 more scale-ins
    V[f"SN34 up to {n} adds every +{int(x*100)}%"] = {**V3, "in_x": x, "in_max": n}
V["SN35 scale-in on high-vol days only"] = {**V3, "in_vol_only": True}
V["SN35 scale-in before 14:00 only"] = {**V3, "in_before": 285}
V["SN35 scale-in puts only"] = {**V3, "in_puts_only": True}
for r in (0.8, 0.9, 1.1, 1.25):                          # SN36 volatility threshold for the second lot
    V[f"SN36 high-vol line x{r}"] = {**V3, "vol_ratio": r}
for t in (0.8, 1.0, 1.3):                                # SN37 intraday volatility sizing
    V[f"SN37 size by today's range >= {t}"] = {**V3, "size": "iv", "iv_thr": t}
V["SN37 size by today's range AND yesterday's vol"] = {**V3, "size": "iv&vol", "iv_thr": 1.0}
if __name__ == "__main__":
    L.study("sn31-37", V, HERE)
