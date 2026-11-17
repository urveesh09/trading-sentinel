"""SN484b (supplementary, PLAN.md A4): the 2010-2026 window of SN484 without the one bad Yahoo print (2019-12-19 close 13.02 between
129.25 and 129.93, a 90% one-day gap that is not a split: no split event exists); every rule as in sn484.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn484 as E  # noqa: E402

OUT = HERE / "results-sn484b.json"


def main():
    if OUT.exists():
        raise SystemExit("SN484b is scored once")
    rows, divs, sha = E.load()
    bad = [r for r in rows if r[0] == "2019-12-19"]
    assert len(bad) == 1 and bad[0][1] < 20, bad
    rows = [r for r in rows if r[0] != "2019-12-19"]
    cell = {}
    for y in (0.0, 0.05):
        for kind in ("TREND", "BUY_HOLD", "CASH"):
            r = E.sim(rows, divs, kind, "2010-01-01", yield_pa=y)
            r["cagr_pct"] = E.cagr(r)
            cell[f"{kind} cash@{int(y * 100)}%"] = r
    t, b, c = cell["TREND cash@0%"], cell["BUY_HOLD cash@0%"], cell["CASH cash@0%"]
    ratio = lambda r: (r["cagr_pct"] or 0) / max(r["max_drawdown_pct"], 1e-9)  # noqa: E731
    cell["verdict_primary"] = "PASS" if ((t["cagr_pct"] or -99) > (c["cagr_pct"] or 0) and ratio(t) > ratio(b)) else "FAIL"
    cell["return_per_drawdown"] = {"TREND": round(ratio(t), 3), "BUY_HOLD": round(ratio(b), 3)}
    OUT.write_text(json.dumps({"dropped_row": bad[0], "source_sha256": sha, "2010-2026": cell}, indent=1), encoding="utf-8")
    print(cell["verdict_primary"], cell["return_per_drawdown"])
    for k, r in cell.items():
        if isinstance(r, dict) and "final" in r:
            print(f"   {k:20s} final {r['final']:>9} cagr {r['cagr_pct']} mdd {r['max_drawdown_pct']}% invested {r['share_of_sessions_invested']} trades {r['trades']}")


if __name__ == "__main__":
    main()
