"""SN433: the research adapter's back-fill (PLAN.md section 1, frozen at 123301ac; details fixed here before any number).
Gold's live clock cannot be audited yet: its Production ledger had no trade (auditor's check: Nov 13 and 16 closed with
zero trades; Nov 17 is an expiry day with entries blocked). This part checks the replay side.

sn01_data._ffill back-fills a session's leading missing minutes from the first later candle. In Gold's own sessions
(sn01 format, 2022-26; `index_traded` / `future_traded` mark real candles), list the sessions whose first real index or
futures minute is after 09:15, the length of the back-filled stretch, and whether any Gold trade (DEPLOYED 2022-26, Rs 205)
falls on that session with its entry minute inside the stretch or within 30 minutes after it (an opening-range input).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-17-sn411"))
import gold  # noqa: E402

OUT = HERE / "results-sn433.json"


def main():
    if OUT.exists():
        raise SystemExit("SN433 is run once")
    days, log, _ = gold.run(gold.Y2226, gold.DEPLOYED, 205.0)
    by_day = {}
    for x in log:
        by_day.setdefault(x["day"], []).append(x["i"])
    rows = []
    for y in gold.Y2226:
        for d, s in gold.D.load_year(y)["sessions"].items():
            for kind in ("index", "future"):
                tr = s.get(f"{kind}_traded")
                if tr is None:
                    continue
                first = int(np.flatnonzero(tr)[0]) if np.any(tr) else None
                if first is None or first > 0:
                    ent = by_day.get(d, [])
                    rows.append({"day": d, "kind": kind, "first_real_minute": first, "gold_entries": ent,
                                 "entry_in_or_near_stretch": any(first is not None and i <= first + 30 for i in ent) if ent else False})
    res = {"gold_ledger_trades_in_production": "none yet (auditor's morning check Nov 17: sessions Nov 13 and 16 closed with zero trades)",
           "sessions_checked": sum(len(gold.D.load_year(y)["sessions"]) for y in gold.Y2226), "late_first_minute": rows,
           "affected_gold_decisions": sum(1 for r in rows if r["entry_in_or_near_stretch"])}
    OUT.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
