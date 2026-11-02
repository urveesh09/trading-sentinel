"""O30s Tier 2 report -> report-t2.json, written after results-t2.json: one-lot weeks with the rule, and what it passes over.
Descriptive; it cannot change the Tier 2 verdict."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_s2 as B  # noqa: E402
import lab_s as S  # noqa: E402
import analyze_s as A  # noqa: E402

sys.path.insert(0, str(A.ROOT / "docs/research/fno/2026-10-29-why-study"))
import analyze_g as AG  # noqa: E402


def main() -> None:
    days26 = json.loads((S.C.ROOT / "docs/research/fno/2026-10-29-year-genome/freeze.json").read_text(encoding="utf-8"))["bindings"]["year_sessions"]
    days25 = json.loads((S.C.O30 / "freeze.json").read_text(encoding="utf-8"))["bindings"]["sessions"]
    days = days25 + days26
    shipped = B.load("shipped")
    weeks = {}
    for n in ("LIVE", "LIVE|skip", "BEST", "BEST|skip", "TPB", "TPB|skip"):
        both = shipped["2025"][n] + shipped["2026"][n]
        weeks[n] = {str(int(s)): AG.one_lot_weeks(both, days, start=s) for s in (12500.0, 15000.0)}
    missed = {}
    for n in ("LIVE", "BEST", "TPB"):
        rows = []
        for y in A.YEARS:
            kept = {(t["entry_time"][:16], t["tradingsymbol"]) for t in shipped[y][f"{n}|skip"]}
            rows += [t for t in B.closed(shipped[y][n]) if (t["entry_time"][:16], t["tradingsymbol"]) not in kept]
        per = [(float(t["net_pnl"]) / max(1, int(t.get("lots_at_exit") or 1)), t["entry_time"][:16]) for t in rows]
        per.sort()
        missed[n] = {"trades_not_taken": len(per), "their_net_per_lot": round(sum(v for v, _ in per)),
                     "share_losing": round(sum(v < 0 for v, _ in per) / max(1, len(per)), 3),
                     "best_given_up": [(d, round(v)) for v, d in per[-4:]][::-1], "worst_avoided": [(d, round(v)) for v, d in per[:4]]}
    out = {"schema": "o30s_tier2_report_v1", "status": "descriptive, written after results-t2.json", "one_lot_weeks": weeks,
           "trades_the_rule_changes": missed}
    (HERE / "report-t2.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=0))


if __name__ == "__main__":
    main()
