"""SN38-SN42 (every wallet): deepest-ITM cascade; growth step size and trigger; day limit; trades a day; start wallet."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab as L
V3 = {"extend": True, "ext_x": 0.25, "ext_k": 3.0, "itm_if_fits": True, "in_x": 0.10}
V = {"SN Gold v3": dict(V3)}
for n in (2, 3):
    V[f"SN38 deepest ITM that fits (up to {n})"] = {**V3, "itm_cascade": n}
for mult in (1.25, 2.0):
    V[f"SN39 growth step x{mult}"] = {**V3, "g_mult": mult}
for trig in (0.5, 1.5):
    V[f"SN39 step after {int(trig*100)}% of wallet in profit"] = {**V3, "g_trig": trig}
for ls in (0.15, 0.25, 0.30):
    V[f"SN40 day limit {int(ls*100)}%"] = {**V3, "loss_share": ls}
for mt in (1, 2):
    V[f"SN41 max {mt} trade(s) a day"] = {**V3, "max_trades": mt}
if __name__ == "__main__":
    L.study("sn38-41", V, HERE)
    # SN42: start the growing wallet higher (the owner's wallet question, with v3)
    import copy
    years = {y: L.B.Year(y) for y in L.YEARS}
    for W0 in (20000.0, 25000.0, 30000.0):
        L.WALLETS = tuple((n.replace("G", "S"), W0, "grow", cap) for n, _w, kind, cap in L.WALLETS if kind == "grow")
        r = L.run(years, None, V3)
        print(f"SN42 start Rs {int(W0)}:", " ".join(f"{w} {sum(r[w][y]['net'] for y in L.YEARS)} (worst {min(r[w][y]['worst'] for y in L.YEARS)}, refill {sum(r[w][y]['refilled'] for y in L.YEARS)})" for w in r), flush=True)
