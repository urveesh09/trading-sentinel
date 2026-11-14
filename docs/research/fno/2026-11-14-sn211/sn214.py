"""SN214 - minute loss stop and profit take (PLAN.md): exit when the value <= -L x credit, L in {0.5, 1, 1.5, 2},
checked every minute; separately exit when the value >= p x credit, p in {0.5, 0.7}; both bases; LOYO per family."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fam  # noqa: E402

if __name__ == "__main__":
    out_path = HERE / "results-sn214.json"
    if out_path.exists():
        raise SystemExit("SN214 is run once")
    res = {}
    for famname in ("loss", "profit"):
        rules = {f"{famname} {x:g}": {famname: x} for x in fam.GRID[famname]}
        res[famname] = fam.score(fam.run(rules), rules)
        fam.show(f"SN214 {famname}", res[famname])
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
