"""SN24-SN28 on top of SN Gold v2 (SN Gold + ITM when it fits), every wallet: an insurance option, a debit spread,
scale-out (sell one lot at +x, the rest stays) and scale-in (add a lot at +x while the wallet allows)."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gold as Gd
G2 = {**Gd.GOLD, "itm_if_fits": True}
V = {"SN Gold": dict(Gd.GOLD), "SN Gold v2": dict(G2)}
for k in (2, 4):
    V[f"SN24 hedge: buy opposite OTM{k}"] = {**G2, "hedge_k": k}
for k in (2, 4, 6):
    V[f"SN25 debit spread: sell same-side +{k}"] = {**G2, "short_k": k}
for x in (0.10, 0.20, 0.40):
    V[f"SN27 scale-out 1 lot at +{int(x*100)}%"] = {**G2, "out_x": x}
for x in (0.10, 0.20, 0.40):
    V[f"SN28 scale-in 1 lot at +{int(x*100)}%"] = {**G2, "in_x": x}
if __name__ == "__main__":
    Gd.study("sn24-28", V, HERE)
