"""Re-run SN Gold v5 from its frozen harness and fail if any wallet's four-year total differs."""
import hashlib, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
assert hashlib.sha256((HERE / "gold_v5.py").read_bytes()).hexdigest() == "81956864837c7b897f2f43b95bdcf546c89376d4a868ab032704dbb29d87b27f", "gold_v5.py changed"
sys.path.insert(0, str(HERE))
import gold_v5 as Gd
cfg = json.loads((HERE / "SN_GOLD_V5.json").read_text(encoding="utf-8"))
v = {**cfg["variant_dict"], "itm_auto": tuple(cfg["variant_dict"]["itm_auto"]), "books": tuple(cfg["variant_dict"]["books"])}
Gd.VOLT.update(Gd.vol_table())
r = Gd.run({y: Gd.B.Year(y) for y in Gd.YEARS}, None, v)
bad = {w: (sum(r[w][y]["net"] for y in Gd.YEARS), e) for w, e in cfg["expected_totals_2023_to_2026_10"].items()
       if sum(r[w][y]["net"] for y in Gd.YEARS) != e}
print("SN Gold v5 reproduces" if not bad else f"MISMATCH {bad}")
sys.exit(1 if bad else 0)
