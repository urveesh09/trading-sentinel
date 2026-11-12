"""SN19b-SN23 on top of SN Gold, every wallet: ITM when it fits; second chance after a loss; second lot by time of day,
by the strategy's recent form, by the opening gap."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gold as Gd
G = Gd.GOLD
V = {"SN Gold": dict(G), "SN19b ITM when it fits": {**G, "itm_if_fits": True}}
for win in (30, 90):
    for b in (0.0, 1.0):
        V[f"SN20 second chance win {win} b {b}"] = {**G, "second_chance": True, "sc_win": win, "sc_b": b}
V["SN21 2nd lot mornings (before 12:00)"] = {**G, "size": "am"}
V["SN21 2nd lot afternoons"] = {**G, "size": "pm"}
for n in (5, 10, 20):
    V[f"SN22 2nd lot if strategy hot (last {n})"] = {**G, "size": "hot", "hot_n": n}
for gap in (0.002, 0.005):
    V[f"SN23 2nd lot gap with trade >= {gap:.1%}"] = {**G, "size": "gap_with", "gap": gap}
    V[f"SN23 2nd lot gap against >= {gap:.1%}"] = {**G, "size": "gap_against", "gap": gap}
V["SN Gold all lots every day"] = {**G, "size": "all"}
if __name__ == "__main__":
    Gd.study("sn20-23", V, HERE)
