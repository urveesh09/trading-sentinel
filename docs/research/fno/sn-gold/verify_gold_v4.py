"""Re-run SN Gold v4 from its frozen harness and fail if any wallet's four-year total differs."""
import hashlib, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
assert hashlib.sha256((HERE / "gold_v4.py").read_bytes()).hexdigest() == "fe167576e751d9f67921e3d3644dfd472617c1e7109d280bb090b7980ee8136f", "gold_v4.py changed"
sys.path.insert(0, str(HERE))
import gold_v4 as Gd
cfg = json.loads((HERE / "SN_GOLD_V4.json").read_text(encoding="utf-8"))
v = {**cfg["variant_dict"], "itm_auto": tuple(cfg["variant_dict"]["itm_auto"])}
Gd.VOLT.update(Gd.vol_table())
r = Gd.run({y: Gd.B.Year(y) for y in Gd.YEARS}, None, v)
bad = {w: (sum(r[w][y]["net"] for y in Gd.YEARS), e) for w, e in cfg["expected_totals_2023_to_2026_10"].items()
       if sum(r[w][y]["net"] for y in Gd.YEARS) != e}
print("SN Gold v4 reproduces" if not bad else f"MISMATCH {bad}")
sys.exit(1 if bad else 0)
