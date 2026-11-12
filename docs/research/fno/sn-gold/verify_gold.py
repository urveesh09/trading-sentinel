"""Re-run SN Gold v3 from its frozen harness and fail loudly if any wallet's four-year total differs (rollback check)."""
import hashlib, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
assert hashlib.sha256((HERE / "gold_v3.py").read_bytes()).hexdigest() == "91ccabd551e873ebfb599c92d214f84e2fd3a34cdb1abe27437fa1b4d03b80e1", "gold_v3.py changed"
sys.path.insert(0, str(HERE))
import gold_v3 as Gd
cfg = json.loads((HERE / "SN_GOLD_V3.json").read_text(encoding="utf-8"))
r = Gd.run({y: Gd.B.Year(y) for y in Gd.YEARS}, Gd.V.vol_days(), cfg["variant_dict"])
bad = {w: (sum(r[w][y]["net"] for y in Gd.YEARS), e) for w, e in cfg["expected_totals_2023_to_2026_10"].items()
       if sum(r[w][y]["net"] for y in Gd.YEARS) != e}
print("SN Gold v3 reproduces" if not bad else f"MISMATCH {bad}")
sys.exit(1 if bad else 0)
