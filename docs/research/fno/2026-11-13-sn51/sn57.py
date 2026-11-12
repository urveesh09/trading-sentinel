"""SN57-SN64 on SN Gold v4, every wallet: day limit 30%; day profit lock (no new trade after a big day); sizing by the
book's own equity curve; the deepest affordable strike; scale-in by index move; pyramid to the full wallet; a hybrid
extension trail; holding extended winners to 15:20."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab as L
V4 = {"extend": True, "ext_x": 0.25, "ext_k": 3.0, "itm_if_fits": True, "in_x": 0.10, "itm_auto": (17500, 20000)}
V = {"SN Gold v4": dict(V4), "SN57 day limit 30%": {**V4, "loss_share": 0.30}}
for lock in (0.10, 0.20, 0.40):
    V[f"SN58 no new trade once the day is up {int(lock*100)}%"] = {**V4, "day_lock": lock}
for n in (10, 20, 40):
    V[f"SN59 2nd lot: vol AND last {n} days positive"] = {**V4, "size": "equity", "eq_n": n}
for mx, sh in ((3, 1.0), (4, 1.0), (4, 0.9)):
    V[f"SN60 deepest ITM up to {mx} within {int(sh*100)}% of wallet"] = {**V4, "itm_auto": None, "itm_max": mx, "itm_share": sh}
for k in (1.0, 2.0):
    V[f"SN61 scale-in when the index moves {k} ATR"] = {**V4, "in_x": None, "in_atr": k}
for x in (0.10, 0.20):
    V[f"SN62 pyramid to the full wallet at +{int(x*100)}%"] = {**V4, "in_x": x, "in_full": True}
for g in (0.3, 0.5):
    V[f"SN63 extension: ATR trail or give back {g}"] = {**V4, "ext_give": g}
V["SN64 extended winners held to 15:20"] = {**V4, "ext_end": 365}
if __name__ == "__main__":
    L.study("sn57-64", V, HERE)
