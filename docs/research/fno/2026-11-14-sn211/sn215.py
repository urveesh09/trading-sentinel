"""SN215 - speed exit, the crash detector (PLAN.md): exit when the index moves >= z*Q within 30 minutes (the opening
gap counts), z in {0.3, 0.5, 0.7}; both bases; LOYO."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fam  # noqa: E402

if __name__ == "__main__":
    out_path = HERE / "results-sn215.json"
    if out_path.exists():
        raise SystemExit("SN215 is run once")
    rules = {f"speed {z:g}": {"speed": z} for z in fam.GRID["speed"]}
    res = fam.score(fam.run(rules), rules)
    fam.show("SN215", res)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
