"""SN449: achievable frequency and how long a verdict needs (PLAN.md section 1, frozen at f56f5807; details fixed here before
any number). Arithmetic on this round's receipts; no new data.

Arms with a positive development mean at Rs 205 this round (direction arms, not execution comparisons):
  SN451 MOM      expiry-afternoon momentum (every NIFTY expiry day, 13:00 -> 15:00, expiring ATM): rows of results-sn451
  SN447 BANK     the bank-results NIFTY mapping (reaction sessions only): rows of results-sn447
Execution comparisons (SN442 WAIT-5, SN444 CONFIRM-5) are listed apart; they change fills on another signal's decisions.
For each arm and stress: f = signal sessions / eligible sessions (SN451: expiry sessions among Gold-empty dates, 251 of 263;
SN447: reaction sessions / Jan-Jul 2026 sessions), q = priced fills / signals, m and sd = mean and SD of net per fill.
  per empty-session gain = f q m against the targets Rs 154 (Rs 205) / Rs 498 (Rs 400) per empty session
  per-session contribution SD: s^2 = f q (sd^2 + m^2) - (f q m)^2
  sessions needed n = ((1.645 + 0.842) s / 154)^2 to tell a Rs 154 contribution from zero (80% power, one-sided 5%)
  SN455 shrinkage: the expected unseen rate = development x median ratio (results-sn455.json)
  90% date-block bootstrap CI of the development per-session contribution (2,000 resamples, seed 449)
Stopping rule published for any forward test: stop PASS when the 90% block CI of the per-empty-session contribution lies
wholly above Rs 154, FAIL when wholly below, else EVIDENCE_INSUFFICIENT at N_max = 3 n.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "results-sn449.json"
TARGET = {205: 154.0, 400: 498.0}


def arm(per_session):
    """per_session: list of per-eligible-session contributions (0 where no signal or no fill)."""
    xs = np.array(per_session, dtype=float)
    return float(xs.mean()), float(xs.std(ddof=1))


def boot(xs, n=2000, seed=449):
    rng = random.Random(seed)
    bs = [np.mean([xs[rng.randrange(len(xs))] for _ in xs]) for _ in range(n)]
    return [round(float(np.percentile(bs, 5)), 1), round(float(np.percentile(bs, 95)), 1)]


def main():
    if OUT.exists():
        raise SystemExit("SN449 is run once")
    shrink = json.loads((HERE / "results-sn455.json").read_text(encoding="utf-8"))["ratio_median"]
    s451 = json.loads((HERE / "results-sn451.json").read_text(encoding="utf-8"))
    s447 = json.loads((HERE / "results-sn447.json").read_text(encoding="utf-8"))
    res = {"shrinkage_median_ratio": shrink, "arms": {}}
    # SN451 MOM: one signal per expiry day with a 13:00 reading; empty dates = 263, of which 251 are expiries (SN426)
    rows = [r["13:00"] for r in s451["rows"] if "13:00" in r]
    for st in (205, 400):
        fills = [b.get(f"MOM_net@{st}") for b in rows]
        per = [x if x is not None else 0.0 for x in fills]
        f, q = len(rows) / len(s451["rows"]), sum(x is not None for x in fills) / len(rows)
        m, sd = float(np.mean([x for x in fills if x is not None])), float(np.std([x for x in fills if x is not None], ddof=1))
        share_expiry = 251 / 263
        mu, s = arm(per)
        n = ((1.645 + 0.842) * s / TARGET[205]) ** 2
        res["arms"][f"SN451 MOM @{st}"] = {"signal_share_of_expiry_sessions": round(f, 3), "expiry_share_of_empty": round(share_expiry, 3),
                                           "fill_share": round(q, 3), "mean_per_fill": round(m), "sd_per_fill": round(sd),
                                           "per_empty_session_gain": round(mu * share_expiry, 1), "target": TARGET[st],
                                           "dev_per_session_ci90": boot(per), "sessions_needed_for_154": int(np.ceil(n)),
                                           "years_of_expiries_needed": round(n / 52, 1), "expected_unseen_per_session_after_shrinkage": round(mu * share_expiry * shrink, 1)}
    # SN447 BANK: reaction sessions among Jan-Jul 2026 regular sessions (~140); the per-session contributions
    nm = s447["nifty_mapping"]
    n_sess = 140
    for st in (205, 400):
        fills = [r.get(f"net@{st}") for r in nm]
        got = [x for x in fills if x is not None]
        per = got + [0.0] * (n_sess - len(got))
        f, q = len(nm) / n_sess, len(got) / len(nm)
        mu, s = arm(per)
        n = ((1.645 + 0.842) * s / TARGET[205]) ** 2
        res["arms"][f"SN447 BANK @{st}"] = {"signal_share_of_sessions": round(f, 3), "fill_share": round(q, 3), "mean_per_fill": round(float(np.mean(got))),
                                            "sd_per_fill": round(float(np.std(got, ddof=1))), "mean_without_best": round((sum(got) - max(got)) / (len(got) - 1)),
                                            "per_session_gain": round(mu, 1), "target": TARGET[st], "dev_per_session_ci90": boot(per),
                                            "sessions_needed_for_154": int(np.ceil(n)), "years_needed": round(n / 250, 1),
                                            "independent_catalysts": len(nm), "same_date_clusters": sum(1 for r in s447["sessions"].values() if len(r) > 1)}
    res["execution_comparisons"] = {
        "SN442 WAIT-5 (paired vs NOW, Rs 205, all decisions)": json.loads((HERE / "results-sn442.json").read_text(encoding="utf-8"))["ALL @205"]["WAIT-5|A"]["paired_vs_NOW"],
        "SN444 CONFIRM-5 mechanics (per decision, Rs 205)": json.loads((HERE / "results-sn444-mechanics.json").read_text(encoding="utf-8"))["CONFIRM-5"]["per_decision@205"],
        "note": "execution companions change fills on another signal; they are judged by fx5's frozen prospective rule, not here"}
    res["BANKNIFTY last-week cluster"] = "no development net: F1 is pre-registered for recorder data after the deploy (SN420)"
    res["stopping_rule"] = "PASS when the 90% date-block CI of the per-empty-session contribution is wholly above Rs 154 (Rs 205); FAIL when wholly below; else EVIDENCE_INSUFFICIENT at N_max = 3 x sessions_needed"
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
