"""SN216 - protect instead of exit (PLAN.md): at a breach by b*Q (b in {0, 0.25}) buy the wing 0.5*Q beyond the
threatened short strike and hold to the base exit (each side at most once); no wing price -> exit (counted); both
bases; LOYO."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fam  # noqa: E402

if __name__ == "__main__":
    out_path = HERE / "results-sn216.json"
    if out_path.exists():
        raise SystemExit("SN216 is run once")
    rules = {f"protect {b:g}": {"protect": b} for b in fam.GRID["protect"]}
    books = fam.run(rules)
    res = fam.score(books, rules)
    res["hedge_fallbacks"] = {k: sum(1 for t in tr if t.get("hedge_failed")) for k, tr in books.items()}
    fam.show("SN216", res)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
