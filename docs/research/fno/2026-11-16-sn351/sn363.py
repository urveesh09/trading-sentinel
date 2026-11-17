"""SN363: the owner's fixed salary on SN352's corrected ledger (PLAN.md section 2; amendment A1 below, committed before
any SN363 number).

Amendment A1 (Nov 16, before SN363 runs; SN352's numbers are known, SN363's are not):
  - The salary SAL(S) is paid in full at every month end from the spare cash P, whatever P's level (that is what makes it
    fixed; the V1-G keep in the plan's text is not applied to it).
  - A run FAILS if: paying S would leave P below 20% of the wallet (Gold could not cover its next day stop), or P < S;
    any session start finds P < 20% of the wallet (Gold would pause); a growth step stays deferred > 21 sessions.
  - S* = the largest S in Rs 500 steps that does not fail (binary search, then S* passes and S* + 500 fails, both run).
  - "Capital preserved" = final funds (trading + spare) >= opening funds. A salary that only survives by spending the
    owner's opening money is reported as such: S*_kept = the largest S that does not fail AND preserves capital.
  - Capital for the wage: the smallest spare P0 (Rs 10,000 steps) at which Rs 15,750 a month does not fail AND
    preserves capital.
  - "Months below S*" = months whose own Gold net was below S* (the reserve paid the difference).
"""
from __future__ import annotations

import collections
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn352  # noqa: E402

STEP = 500.0
WAGE = 15750.0


class Fail(Exception):
    pass


class Salary(sn352.Journal):
    def __init__(self, W0, P0, S):
        super().__init__(W0, P0, policy="NONE", funding="PAUSE", model="new")
        self.S = float(S)
        self.month_net = collections.Counter()
        self.defer_run = 0

    def _withdraw(self):
        if self.P < self.S or self.P - self.S < 0.2 * self.W:
            raise Fail(f"salary {self.month}")
        self.P -= self.S
        self.X += self.S
        self.paid.append((self.month, self.S))

    def gate(self, day, has_signals):
        if self.P < 0.2 * self.W:
            raise Fail(f"pause {day}")
        return super().gate(day, has_signals)

    def settle(self, day, x):
        self.month_net[day[:7]] += x
        before = self.deferred_sessions
        super().settle(day, x)
        self.defer_run = self.defer_run + 1 if self.deferred_sessions > before else 0
        if self.defer_run > 21:
            raise Fail(f"growth deferred {day}")


def trial(Q, stress, P0, S, from_day=None):
    j = Salary(30000.0, P0, S)
    v_old = dict(Q.C.V5)
    if from_day:
        Q.C.V5["from_day"] = from_day
    try:
        sn352.run_gold(Q, stress, j)
        ok, why = True, None
    except Fail as e:
        ok, why = False, str(e)
    finally:
        Q.C.V5.clear()
        Q.C.V5.update(v_old)
    final = j.T + j.P
    return {"ok": ok, "why": why, "kept": ok and final >= j.E0, "paid": round(j.X), "final_funds": round(final),
            "opening": round(j.E0), "min_spare": round(j.minP) if j.minP != float("inf") else None,
            "months_below_S": sum(1 for m, _a in j.paid if j.month_net[m] < S), "months": len(j.paid),
            "gold_net": round(j.cum), "steps": j.step_days}


def s_star(Q, stress, P0, from_day=None, need_kept=False):
    key = "kept" if need_kept else "ok"
    lo, hi = 0, 120                       # in STEPs: 0 .. Rs 60,000
    assert trial(Q, stress, P0, 0.0, from_day)["ok"]
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if trial(Q, stress, P0, mid * STEP, from_day)[key]:
            lo = mid
        else:
            hi = mid
    at = trial(Q, stress, P0, lo * STEP, from_day)
    above = trial(Q, stress, P0, (lo + 1) * STEP, from_day)
    assert at[key] and not above[key], (at, above)
    return {"S_star": lo * STEP, "per_session": round(lo * STEP / 21.0), "at": at, "above": above}


def capital(Q, stress):
    lo, hi = 0, 300                       # in Rs 10,000 steps: 0 .. Rs 30 lakh
    if not trial(Q, stress, hi * 10000.0, WAGE)["kept"]:
        return {"P0": None, "why": "not sustainable with Rs 30 lakh spare"}
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if trial(Q, stress, mid * 10000.0, WAGE)["kept"]:
            hi = mid
        else:
            lo = mid
    at = trial(Q, stress, hi * 10000.0, WAGE)
    below = trial(Q, stress, (hi - 1) * 10000.0, WAGE)
    assert at["kept"] and not below["kept"]
    return {"P0": hi * 10000.0, "owner_total": 30000.0 + hi * 10000.0, "at": at, "below": below}


def main():
    out_path = HERE / "results-sn363.json"
    if out_path.exists():
        raise SystemExit("SN363 is run once")
    Q = sn352.gold_setup()
    t = time.time()
    res = {}
    for st in (205.0, 400.0):
        for P0 in (30000.0, 60000.0, 90000.0):
            for need_kept in (False, True):
                k = f"S* P0={int(P0)}{' kept' if need_kept else ''} @{int(st)}"
                res[k] = s_star(Q, st, P0, need_kept=need_kept)
                print(k, res[k]["S_star"], json.dumps({x: res[k]["at"][x] for x in ("paid", "final_funds", "months_below_S", "min_spare")}),
                      round(time.time() - t), flush=True)
        for start in ("2024-01-01", "2025-01-01"):
            k = f"S* start={start} P0=30000 @{int(st)}"
            res[k] = s_star(Q, st, 30000.0, from_day=start)
            print(k, res[k]["S_star"], json.dumps({x: res[k]["at"][x] for x in ("paid", "final_funds", "months_below_S")}), flush=True)
        k = f"capital for Rs 15,750 @{int(st)}"
        res[k] = capital(Q, st)
        print(k, json.dumps({x: res[k].get(x) for x in ("P0", "owner_total")}), round(time.time() - t), flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
