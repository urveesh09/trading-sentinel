"""SN19 - the strike by setup: deeper in the money for trend pullbacks (more delta, less decay), further out for
breakouts (more gamma per rupee), per N11 strategy. Every wallet; held out per wallet."""
import itertools, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gold as Gd
V = {"benchmark (no extension)": {}, "SN Gold": dict(Gd.GOLD)}
for tpb, other in itertools.product((-1, 0, 1), (-1, 0, 1)):
    if (tpb, other) != (0, 0):
        V[f"SN19 TPB {tpb:+d} others {other:+d}"] = {**Gd.GOLD, "offset": {"TPB": tpb, "OR20": other, "EFF": other, "SHIPPED": other}}
if __name__ == "__main__":
    Gd.study("sn19", V, HERE)
