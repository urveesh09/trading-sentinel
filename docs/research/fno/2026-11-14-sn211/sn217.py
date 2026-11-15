"""SN217 - calendar fail-safe and the expiry-day gate (PLAN.md + amendment): (a) skip weeks whose holding window holds
a Budget, election-result or RBI decision day, both bases, alone and with the best single exit of SN213-SN216 (by
development total, from their results); (b) the gate: at the 15:15 mark before expiry hold into expiry only when the
index is >= c*Q inside both short strikes, c in {-0.25, 0, 0.25, 0.5} (settle base); LOYO per part."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fam  # noqa: E402

if __name__ == "__main__":
    out_path = HERE / "results-sn217.json"
    if out_path.exists():
        raise SystemExit("SN217 is run once")
    best = None
    for sn in ("213", "214", "215", "216"):
        r = json.loads((HERE / f"results-sn{sn}.json").read_text(encoding="utf-8"))
        for part in ([r] if "rows" in r else list(r.values())):
            k = part["best"]
            if best is None or part["rows"][k]["net"] > best[2]:
                best = (k.split(" | ")[0], part["best_rule"], part["rows"][k]["net"])
    res = {"best_single_exit": {"base": best[0], "rule": best[1], "net": best[2]}}
    rules = {"calendar": {"calendar": True}}
    res["calendar"] = fam.score(fam.run(rules), rules)
    fam.show("SN217 calendar", res["calendar"])
    combo = {"calendar": True, **best[1]}
    nm = "calendar + " + " + ".join(f"{k} {v:g}" for k, v in best[1].items())
    res["calendar + best exit"] = fam.score(fam.run({nm: combo}, bases=(best[0],)), {nm: combo})
    fam.show("SN217 calendar+best", res["calendar + best exit"])
    rules = {f"gate {c:g}": {"gate": c} for c in fam.GRID["gate"]}
    res["gate"] = fam.score(fam.run(rules, bases=("settle",)), rules)
    fam.show("SN217 gate", res["gate"])
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
