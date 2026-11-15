"""SN213 - breach exit (PLAN.md): exit when the index is beyond a short strike by b*Q, b in {-0.25, 0, 0.25, 0.5},
checked every minute; both bases; LOYO."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fam  # noqa: E402

if __name__ == "__main__":
    out_path = HERE / "results-sn213.json"
    if out_path.exists():
        raise SystemExit("SN213 is run once")
    rules = {f"breach {b:g}": {"breach": b} for b in fam.GRID["breach"]}
    res = fam.score(fam.run(rules), rules)
    fam.show("SN213", res)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
