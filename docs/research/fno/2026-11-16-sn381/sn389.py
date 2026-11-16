"""SN389: the cash needed to live through a bad start (PLAN.md section 1, frozen at c6e99cee; details fixed here before
any SN389 number). sn352.Journal (cash-funded growth, daily identity), Gold v5 unchanged on the 2022 - 2026 path (2022 =
SN366's exam stream, SN392's wiring), Rs 30,000 trading + Rs 30,000 spare, DEPOSIT funding: when a session would start
with spare cash below 20% of the wallet, the owner deposits the shortfall from outside (counted). Rs 205 and Rs 400.
Policies at each month end:
  PROFIT_ONLY      everything above one wallet (sn352 V1W)
  SALARY_15750     Rs 15,750 (Rs 750 x 21 sessions) paid in full every month from spare cash, whatever its level; any
                   shortfall that follows is the owner's outside deposit
Starts: Jan 2022 and Jan 2023 (full ledgers), and every month start Jan 2022 - Apr 2026 (SALARY_15750: the distribution of
outside cash needed).
Reported: outside deposits (total, worst month), gross internal transfers (losing days refilled from spare), maximum
reserve depletion (opening spare - lowest spare), withdrawn total and per session, the share of months paying >= Rs
15,750, the longest run of months paying nothing, final funds, Gold's net.
"""
from __future__ import annotations

import collections
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FNO / "2026-11-16-sn351"))
import sn352  # noqa: E402
import sn392 as P  # noqa: E402

Q, C, L, B, D, G = P.Q, P.C, P.L, P.B, P.D, P.G
OUT = HERE / "results-sn389.json"
YEARS = ("2022", "2023", "2024", "2025", "2026")


class Ledger(sn352.Journal):
    def __init__(self, policy):
        super().__init__(30000.0, 30000.0, policy="V1W" if policy == "PROFIT_ONLY" else "NONE", funding="DEPOSIT", model="new")
        self.kind = policy
        self.internal = 0.0

    def _withdraw(self):
        if self.kind == "PROFIT_ONLY":
            return super()._withdraw()
        self.P -= 15750.0
        self.X += 15750.0
        self.paid.append((self.month, 15750.0))

    def settle(self, day, x):
        if x < 0:
            self.internal += -x
        super().settle(day, x)


def setup():
    B.stream = P.stream
    D.DATASETS["2022"] = P.SN366L / "dataset-nifty-2022"
    D.load_year = G.load_2022
    for mod in (B, L, C):
        mod.YEARS = YEARS
    C._YEARS = None
    L.VOLT.clear()
    C.panel = lambda r: {w: {} for w in r}


def run(stress, policy, start):
    j = Ledger(policy)
    old = dict(C.V5)
    C.V5["from_day"] = start
    try:
        sn352.run_gold(Q, stress, j)
    finally:
        C.V5.clear()
        C.V5.update(old)
    pays = [a for _m, a in j.paid]
    run_, cur = 0, 0
    for a in pays:
        cur = cur + 1 if a <= 0 else 0
        run_ = max(run_, cur)
    return {"outside_deposits": round(j.D), "worst_month_deposit": round(max(j.dep_month.values(), default=0.0)), "internal_transfers": round(j.internal),
            "max_reserve_depletion": round(30000.0 - min(j.minP, 30000.0)), "withdrawn": round(j.X), "per_session": round(j.X / max(1, j.sessions)),
            "months": len(pays), "months_paying_15750": sum(a >= 15750.0 for a in pays), "longest_months_paying_nothing": run_,
            "final_funds": round(j.T + j.P), "gold_net": round(j.cum), "sessions": j.sessions}


def main():
    if OUT.exists():
        raise SystemExit("SN389 is run once")
    Q.install()
    setup()
    res = {}
    for st in (205.0, 400.0):
        for start in ("2022-01-01", "2023-01-01"):
            for pol in ("PROFIT_ONLY", "SALARY_15750"):
                r = run(st, pol, start)
                res[f"{pol} from {start[:7]} @{int(st)}"] = r
                print(pol, start[:7], int(st), json.dumps(r), flush=True)
        starts = [f"{y}-{m:02d}-01" for y in (2022, 2023, 2024, 2025, 2026) for m in range(1, 13) if f"{y}-{m:02d}" <= "2026-04"]
        rows = {s: run(st, "SALARY_15750", s) for s in starts}
        dep = [r["outside_deposits"] for r in rows.values()]
        res[f"SALARY_15750 every start @{int(st)}"] = {"starts": len(rows), "median_outside": statistics.median(dep), "max_outside": max(dep),
                                                       "worst_start": max(rows, key=lambda s: rows[s]["outside_deposits"]),
                                                       "starts_needing_no_outside_cash": sum(d == 0 for d in dep),
                                                       "by_start": {s: r["outside_deposits"] for s, r in rows.items()}}
        print("every start", int(st), json.dumps({k: v for k, v in res[f"SALARY_15750 every start @{int(st)}"].items() if k != "by_start"}), flush=True)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
