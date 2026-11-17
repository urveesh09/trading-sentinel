"""SN461: decision-time capacity under Gold's priority (PLAN.md section 1, frozen at 83e1b444; details fixed here before any
number). No candidate P&L; later Gold activity is attribution only, never an input.

Sessions: every NIFTY futures session 2022-01-03 .. 2026-10-28 (feat456's calendar). Gold: its replay path, DEPLOYED at Rs 205
(gold.Y22 and gold.Y2326 runs); a replay day = a row of the run's day log. Gold trade i = fill bar index, j = exit index.
At clock m (45 = 10:00, 105 = 11:00, 225 = 13:00):
  OUTSIDE  the session is not a Gold replay day (NIFTY expiry days, specials, data holes)
  OPEN     a Gold trade with i <= m - 1 < j
  PENDING  a Gold trade with i == m (its 5-minute bar closed at the clock; the fill lands 59 s later)
  CLEAR    otherwise
Attribution over the candidate's 60-minute interval [m, m + 59] (main: m = 45):
  DURING        a Gold entry with m <= i <= m + 59
  AFTER_ONLY    Gold entries only with i >= m + 60
  BEFORE_ONLY   Gold entries only before m, all closed by m (j < m)
  NONE          no Gold entry all day (the hindsight gap day)
Reported by year: state counts, CLEAR share (decision-time capacity), CLEAR x attribution (collision rate = DURING share of
CLEAR), hindsight gap days (replay days with no Gold entry) against CLEAR, OUTSIDE split into NIFTY expiry days and the rest,
and for 2023-26 the ledger10 coverage of CLEAR 10:00 sessions (at least one side ENTERED at Rs 205).
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FNO / "2026-11-17-sn411"))
import feat456 as F  # noqa: E402
import gold  # noqa: E402
import ledger10  # noqa: E402

OUT = HERE / "results-sn461.json"
CLOCKS = {"10:00": 45, "11:00": 105, "13:00": 225}


def main():
    if OUT.exists():
        raise SystemExit("SN461 is scored once")
    _days, sess = F.futures()
    cal = sorted(d for d in sess if "2022-01-01" <= d <= "2026-10-28")
    weekly = F.option_expiries()
    rep_days, trades = set(), collections.defaultdict(list)
    for years in (gold.Y22, gold.Y2326):
        days, log, _ = gold.run(years, gold.DEPLOYED, 205.0)
        if years == gold.Y2326:
            assert gold.summary(days, log)["net"] in (850882, 850883)
        rep_days |= {r[0] for r in days}
        for x in log:
            trades[x["day"]].append((x["i"], x["j"]))
    L = ledger10.build()
    res = {"sessions": len(cal), "replay_days": len([d for d in cal if d in rep_days]), "by_clock": {}}
    for cname, m in CLOCKS.items():
        by = collections.defaultdict(collections.Counter)
        for d in cal:
            y = d[:4]
            if d not in rep_days:
                by[y]["OUTSIDE_expiry" if d in weekly else "OUTSIDE_other"] += 1
                continue
            ts = trades.get(d, [])
            if any(i <= m - 1 < j for i, j in ts):
                st = "OPEN"
            elif any(i == m for i, _j in ts):
                st = "PENDING"
            else:
                st = "CLEAR"
            by[y][st] += 1
            if st == "CLEAR":
                if any(m <= i <= m + 59 for i, _j in ts):
                    a = "DURING"
                elif ts and all(i >= m + 60 for i, _j in ts):
                    a = "AFTER_ONLY"
                elif ts:
                    a = "BEFORE_ONLY"
                else:
                    a = "NONE"
                by[y]["CLEAR_" + a] += 1
                if cname == "10:00" and d in L and any(L[d][s]["state"] == "ENTERED" for s in ("CE", "PE")):
                    by[y]["CLEAR_ledger10_priced"] += 1
            if not ts:
                by[y]["hindsight_gap_day"] += 1
        tot = collections.Counter()
        for c in by.values():
            tot.update(c)
        out = {y: dict(c) for y, c in sorted(by.items())}
        out["ALL"] = dict(tot)
        inrep = tot["OPEN"] + tot["PENDING"] + tot["CLEAR"]
        out["summary"] = {"clear_share_of_replay_days": round(tot["CLEAR"] / max(1, inrep), 4),
                          "clear_share_of_all_sessions": round(tot["CLEAR"] / len(cal), 4),
                          "collision_rate_during_given_clear": round(tot["CLEAR_DURING"] / max(1, tot["CLEAR"]), 4),
                          "clear_and_gold_never_enters": tot["CLEAR_NONE"], "hindsight_gap_days": tot["hindsight_gap_day"],
                          "outside_expiry": tot["OUTSIDE_expiry"], "outside_other": tot["OUTSIDE_other"]}
        res["by_clock"][cname] = out
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: (v if k != "by_clock" else {c: v[c]["summary"] for c in v}) for k, v in res.items()}, indent=1))
    print(json.dumps(res["by_clock"]["10:00"]["ALL"], indent=1))


if __name__ == "__main__":
    main()
