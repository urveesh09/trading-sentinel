"""SN374: withdrawals that survive bad starts (PLAN.md section 1, frozen at 3740b461; details fixed here before any
SN374 number). sn352.Journal (cash-funded growth, daily identity), Gold v5 unchanged, Rs 30k trading + Rs 30k spare,
PAUSE funding, starting on the first session of every month Jan 2023 .. Apr 2026 (Gold's own from_day knob), each run to
Oct 28, 2026, at Rs 205 and Rs 400.
Policies (month end, as sn352):
  FIXED_500 / FIXED_2000  pay min(S, spare - 20% of the wallet), never below Gold's next-day cover (a short month is
                          counted; the shortfall is not carried)
  PROFIT_ONLY             everything above one wallet (sn352 V1W)
  BASE_VAR                min(1,000, spare - 20% of the wallet) + 50% of what is then above one wallet
Reported per policy and stress, over start months: median of the median monthly payout; median share of months paying
nothing; share of starts with any payment that leaves total funds below the opening Rs 60k (paid from principal);
median deferred growth sessions; worst start (lowest total paid).
The gap to Rs 750 a session (from the Jan 2023 start, PROFIT_ONLY): (750 x sessions - withdrawn) / Gold's no-trade
sessions = the extra after-cost net each empty-Gold session would have to earn.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn351"))
import sn352  # noqa: E402

OUT = HERE / "results-sn374.json"


class Policy(sn352.Journal):
    def __init__(self, kind, S=0.0):
        super().__init__(30000.0, 30000.0, policy="V1W" if kind == "PROFIT_ONLY" else "NONE", funding="PAUSE", model="new")
        self.kind, self.S = kind, float(S)
        self.from_principal = False

    def _withdraw(self):
        if self.kind == "PROFIT_ONLY":
            super()._withdraw()
        else:
            room = max(0.0, self.P - 0.2 * self.W)
            if self.kind.startswith("FIXED"):
                amt = min(self.S, room)
            else:
                base = min(1000.0, room)
                amt = base + 0.5 * max(0.0, self.P - base - self.W)
            self.P -= amt
            self.X += amt
            self.paid.append((self.month, amt))
        if self.T + self.P < self.E0 - 0.01 and self.paid and self.paid[-1][1] > 0:
            self.from_principal = True


def run(Q, stress, kind, S, start):
    j = Policy(kind, S)
    old = dict(Q.C.V5)
    Q.C.V5["from_day"] = start
    Q.ow.DAYLOG.clear()
    try:
        sn352.run_gold(Q, stress, j)
    finally:
        Q.C.V5.clear()
        Q.C.V5.update(old)
    pays = [a for _m, a in j.paid]
    flat = sum(1 for _d, _w, _n, ntr, _l in Q.ow.DAYLOG if ntr == 0)
    return {"paid": round(j.X), "months": len(pays), "median_month": round(statistics.median(pays)) if pays else 0,
            "zero_share": round(sum(a <= 0 for a in pays) / max(1, len(pays)), 3), "from_principal": j.from_principal,
            "deferred": j.deferred_sessions, "paused": j.paused, "sessions": j.sessions, "flat_sessions": flat, "final_funds": round(j.T + j.P)}


def main():
    if OUT.exists():
        raise SystemExit("SN374 is run once")
    Q = sn352.gold_setup()
    starts = [f"{y}-{m:02d}-01" for y in (2023, 2024, 2025, 2026) for m in range(1, 13) if f"{y}-{m:02d}" <= "2026-04"]
    res = {"starts": len(starts)}
    for st in (205.0, 400.0):
        for kind, S in (("FIXED_500", 500), ("FIXED_2000", 2000), ("PROFIT_ONLY", 0), ("BASE_VAR", 0)):
            rows = {s: run(Q, st, kind, S, s) for s in starts}
            worst = min(rows, key=lambda s: rows[s]["paid"])
            res[f"{kind} @{int(st)}"] = {
                "median_of_median_month": statistics.median(r["median_month"] for r in rows.values()),
                "median_zero_share": statistics.median(r["zero_share"] for r in rows.values()),
                "share_of_starts_paying_from_principal": round(sum(r["from_principal"] for r in rows.values()) / len(rows), 3),
                "median_deferred": statistics.median(r["deferred"] for r in rows.values()),
                "starts_with_pauses": sum(r["paused"] > 0 for r in rows.values()),
                "worst_start": {"start": worst, **rows[worst]}, "by_start": rows}
            print(kind, int(st), json.dumps({k: v for k, v in res[f"{kind} @{int(st)}"].items() if k != "by_start"}), flush=True)
        j = res[f"PROFIT_ONLY @{int(st)}"]["by_start"]["2023-01-01"]
        need = 750.0 * j["sessions"] - j["paid"]
        res[f"gap_to_750 @{int(st)}"] = {"sessions": j["sessions"], "withdrawn": j["paid"], "shortfall": round(need), "flat_sessions": j["flat_sessions"],
                                         "extra_net_per_flat_session": round(need / max(1, j["flat_sessions"]))}
        print("gap", int(st), json.dumps(res[f"gap_to_750 @{int(st)}"]), flush=True)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
