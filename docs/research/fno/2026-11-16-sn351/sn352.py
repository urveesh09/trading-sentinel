"""SN352: the cash-funded wage and refill ledger (PLAN.md section 1, frozen at cbdbc54c before any number).

Gold v5's day is unchanged (sn301/gw.py through sn331/sn339_350.install(), the pool switched off, so every hook passes
through). Only the money around it changes. Journal (one class, used by the fixture and by every Gold run):
  T trading cash (= Gold's sizing wallet W at each session start), P spare cash, D owner deposits, X withdrawals.
  model "old": SN342's equations (growth raises W without paying for it; P gets every day's net).
  model "new": a growth step moves 0.5 W from P to T, only if P - 0.5 W >= 20% of the new wallet; otherwise deferred.
  Daily identity (new): opening funds + sum(net) + D - X == T + P, asserted to Rs 0.01 every session.
Policies (month end, applied at the first session of the next month, like SN342):
  V1G  keep one wallet, plus the pending step's 0.5 W when a step is deferred      (growth first)
  V1W  keep one wallet                                                                (wage first)
  V2   keep Rs 60,000
  F10 / F15  pay Rs 10,000 / 15,000 from P above one wallet (partial when short, never carried)
  NONE no withdrawal (parity)
Funding: PAUSE (Gold sits out a session when P < 20% of W) or DEPOSIT (the owner tops P up to 20% of W).
python sn352.py test   -> the auditor's fixture on both models
python sn352.py        -> reproduction, parity and the frozen grid; results-sn352.json written once
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FNO = HERE.parent


class Journal:
    def __init__(self, W0, P0, policy="V1G", funding="PAUSE", model="new", cap=3, trig=1.0, mult=1.5):
        self.W = self.T = float(W0)
        self.P = float(P0)
        self.E0 = self.W + self.P
        self.policy, self.funding, self.model = policy, funding, model
        self.cap, self.trig, self.mult = cap, trig, mult
        self.D = self.X = self.cum = self.prog = 0.0
        self.steps = 0
        self.step_days = []
        self.deferred_sessions = 0
        self.phantom = 0.0                    # old model: growth cash never debited
        self.month = None
        self.paid = []                        # (month, amount)
        self.dep_month = collections.Counter()
        self.paused = self.paused_sig = self.sessions = 0
        self.minP = float("inf")

    # --- month end ------------------------------------------------------------------------------------------------
    def pending_step(self):
        return self.prog >= self.trig * self.W and self.steps < self.cap

    def _withdraw(self):
        W, P, pol = self.W, self.P, self.policy
        if pol == "NONE":
            amt = 0.0
        elif pol in ("V1G", "V1W"):
            keep = W + ((self.mult - 1) * W if pol == "V1G" and self.model == "new" and self.pending_step() else 0.0)
            amt = max(0.0, P - keep)
        elif pol == "V2":
            amt = max(0.0, P - 60000.0)
        elif pol in ("F10", "F15"):
            amt = min(10000.0 if pol == "F10" else 15000.0, max(0.0, P - W))
        else:
            raise ValueError(pol)
        self.P -= amt
        self.X += amt
        self.paid.append((self.month, amt))

    def month_tick(self, month):
        if self.month is not None and month != self.month:
            self._withdraw()
        self.month = month

    # --- a session ------------------------------------------------------------------------------------------------
    def gate(self, day, has_signals):
        """True if Gold may play this session."""
        self.sessions += 1
        need = 0.2 * self.W
        if self.P < need:
            if self.funding == "PAUSE":
                self.paused += 1
                self.paused_sig += bool(has_signals)
                return False
            dep = need - self.P
            self.D += dep
            self.P += dep
            self.dep_month[day[:7]] += dep
        return True

    def settle(self, day, x):
        self.P += x
        self.cum += x
        self.prog += x
        deferred = False
        while self.prog >= self.trig * self.W and self.steps < self.cap:
            dW = (self.mult - 1) * self.W
            if self.model == "new" and self.P - dW < 0.2 * self.W * self.mult:
                deferred = True
                break
            if self.model == "new":
                self.P -= dW
            else:
                self.phantom += dW
            self.prog -= self.trig * self.W
            self.W *= self.mult
            self.steps += 1
            self.step_days.append(day)
        self.deferred_sessions += deferred
        self.T = self.W
        self.minP = min(self.minP, self.P)
        if self.model == "new":
            gap = self.E0 + self.cum + self.D - self.X - (self.T + self.P)
            assert abs(gap) < 0.01, (day, gap)

    def summary(self, n_days=None):
        w = [a for _m, a in self.paid]
        run = cur = 0
        for a in w:
            cur = cur + 1 if a <= 0 else 0
            run = max(run, cur)
        full = None
        if self.policy in ("F10", "F15"):
            s = 10000.0 if self.policy == "F10" else 15000.0
            full = sum(a >= s - 0.005 for a in w)
        final = self.T + self.P
        return {"withdrawn_total": round(self.X), "per_session_wage": round(self.X / max(1, self.sessions)),
                "avg_month": round(self.X / max(1, len(w))), "months": len(w), "months_paid": sum(a > 0 for a in w),
                "months_paid_in_full": full, "longest_dry_months": run,
                "last_12_months_avg": round(sum(w[-12:]) / max(1, len(w[-12:]))),
                "growth_steps": self.steps, "step_days": self.step_days, "deferred_sessions": self.deferred_sessions,
                "paused_sessions": self.paused, "paused_with_signals": self.paused_sig,
                "deposits_total": round(self.D), "deposits_worst_month": round(max(self.dep_month.values(), default=0.0)),
                "min_spare": round(self.minP), "final_wallet": round(self.W), "final_funds": round(final),
                "opening_funds": round(self.E0), "gold_net": round(self.cum),
                "identity_gap": round(self.X + final - self.E0 - self.D - self.cum, 2) if self.model == "new" else None,
                "phantom_growth_cash": round(self.phantom), "sessions": self.sessions,
                "monthly": [(m, round(a)) for m, a in self.paid]}


# ---- the auditor's fixture ----------------------------------------------------------------------------------------
def fixture():
    out = {}
    for model in ("old", "new"):
        j = Journal(30000.0, 30000.0, policy="V1W", model=model)
        j.month_tick("2026-01")
        assert j.gate("2026-01-05", True)
        j.settle("2026-01-05", 30000.0)
        j.month_tick("2026-02")               # month end: withdraw
        out[model] = {"trading": j.W, "spare": j.P, "paid": j.X, "accounted": j.W + j.P + j.X}
    assert out["old"] == {"trading": 45000.0, "spare": 45000.0, "paid": 15000.0, "accounted": 105000.0}, out["old"]
    assert out["new"] == {"trading": 45000.0, "spare": 45000.0, "paid": 0.0, "accounted": 90000.0}, out["new"]
    return out


# ---- Gold's day loop (lab.run's growth branch, the money moved into the Journal) ------------------------------------
def gold_setup():
    sys.path.insert(0, str(FNO / "2026-11-16-sn331"))
    import sn339_350 as Q  # noqa: E402
    Q.install()
    return Q


def run_gold(Q, stress, journal):
    ow, C, L, gw = Q.ow, Q.C, Q.L, Q.gw
    v = {**C.V5}
    old_s = L.STRESS
    L.STRESS = stress
    L.play_day, L.size = ow.play_day, C.size_ext
    ow.DAYLOG.clear()
    ow.STATE["leg"], ow.STATE["carry"] = None, None
    gw.LOG.clear()
    nets = []
    try:
        years = C.years()
        ctx = L.Ctx()
        for y in L.YEARS:
            Y = years[y]
            for S in Y.ordered():
                if v.get("from_day") and S.day < v["from_day"]:
                    continue
                sigs = L.sig_of(Y, S.day, v)
                journal.month_tick(S.day[:7])
                if not journal.gate(S.day, sigs):
                    x = 0.0
                else:
                    W = journal.W
                    full, vday = max(1, int(W // 15000)), L.vday_of(S.day, v)
                    x = L.play_day(S, sigs, v, W, full, ctx, vday)
                ctx.day_nets.append(x)
                journal.settle(S.day, x)
                nets.append((S.day, round(x, 2)))
    finally:
        L.STRESS = old_s
    return nets


def main():
    out_path = HERE / "results-sn352.json"
    if out_path.exists():
        raise SystemExit("SN352 is run once")
    res = {"fixture": fixture()}
    Q = gold_setup()
    # 1. reproduce SN342 with its own code, then with the Journal's old model
    for st in (205.0, 400.0):
        old = Q.pooled(st, R_is_wallet=True)
        res[f"repro_sn342_code @{int(st)}"] = old
        j = Journal(30000.0, 30000.0, policy="V1W", model="old")
        run_gold(Q, st, j)
        s = j.summary()
        res[f"repro_journal_old @{int(st)}"] = s
        assert s["withdrawn_total"] == old["withdrawn_total"], (s["withdrawn_total"], old["withdrawn_total"])
        assert s["paused_sessions"] == old["paused_sessions"]
        print("repro", int(st), old["withdrawn_total"], s["withdrawn_total"], "phantom", s["phantom_growth_cash"], flush=True)
    assert res["repro_sn342_code @205"]["withdrawn_total"] == 654004
    # 2. parity: unlimited spare cash, no withdrawal
    j = Journal(30000.0, 1e12, policy="NONE", model="new")
    nets = run_gold(Q, 205.0, j)
    row, days, _log = Q.run(205.0)
    ref = [(d, round(n, 2)) for d, _w, n, _t, _l in days]
    # disclosed fix (before any grid number): the panel row is a sum of per-year rounded nets (850,882); the journal's
    # unrounded total is 850,882.78, so the check is to Rs 1; the day-by-day comparison below is exact
    assert abs(j.cum - 850882) < 1 and row["net"] == 850882, (j.cum, row["net"])
    assert nets == ref, "day nets differ from ow.run_wallet"
    res["parity"] = {"gold_net": round(j.cum), "steps": j.steps, "step_days": j.step_days, "days_identical": True}
    print("parity ok", round(j.cum), j.step_days, flush=True)
    # 3. the frozen grid
    for st in (205.0, 400.0):
        for P0 in (30000.0, 60000.0):
            for funding in ("PAUSE", "DEPOSIT"):
                for pol in ("V1G", "V1W", "V2", "F10", "F15"):
                    j = Journal(30000.0, P0, policy=pol, funding=funding, model="new")
                    run_gold(Q, st, j)
                    s = j.summary()
                    assert abs(s["identity_gap"]) < 1, s["identity_gap"]
                    key = f"{pol} P0={int(P0)} {funding} @{int(st)}"
                    res[key] = s
                    print(key, json.dumps({k: s[k] for k in ("withdrawn_total", "per_session_wage", "months_paid", "longest_dry_months",
                                                            "growth_steps", "deferred_sessions", "paused_sessions", "deposits_total",
                                                            "final_funds", "gold_net")}), flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print(json.dumps(fixture()))
    else:
        main()
