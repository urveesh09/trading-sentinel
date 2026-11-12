"""SN01 analysis - applies the frozen rule (PLAN.md) and writes results.json once (research only).

  1. Leave-one-year-out: for each year, the REAL search's pick and the NULL (random-entry) search's pick are chosen on
     the other three years only, then scored on the held-out year at +Rs 0 / 100 / 200 per lot per trade.
  2. The verdict on the search procedure (RULE below).
  3. The final pick (chosen on all four years) per year and stress, and the owner's wallet ledger Jan 2023 - Oct 2026.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sn01_search as SR  # noqa: E402

RULE = {
    "stress_for_verdict": 100.0,
    "heldout_positive_years_min": 3,          # of 4
    "heldout_sum_positive": True,
    "heldout_sum_beats_null": True,
    "robust_stress": 200.0,                   # the final pick must also be positive over four years at +200
    "final_every_year_positive_at_100": True,
    "min_trades_per_session": SR.MIN_TRADES_PER_SESSION,
}


def pick(evals: dict, fold: str, null: bool, top: int = 1) -> list[dict]:
    train = SR.folds()[fold]
    tag = f"ga:{fold}:{'null' if null else 'real'}:"
    cands = [r for r in evals.values() if r["genome"]["null"] == null and
             (r["origin"] == "pool" or r["origin"].startswith(tag))]
    cands.sort(key=lambda r: SR.fitness(r, train), reverse=True)
    return cands[:top]


def main() -> None:
    out_path = HERE / "results.json"
    if out_path.exists():
        raise SystemExit("results.json exists: the frozen rule is applied once")
    evals = SR.load_evals()
    pool = SR.Pool()
    res = {"rule": RULE, "evaluations": len(evals), "loyo": {}, "final": {}}
    try:
        for fold in SR.YEARS:
            row = {}
            for null in (False, True):
                best = pick(evals, fold, null, top=10)
                g = best[0]["genome"]
                stresses = {}
                for stress in (0.0, 100.0, 200.0):
                    stresses[str(int(stress))] = pool.evaluate([g], stress)[0][fold]
                top10 = [r["years"][fold]["net"] for r in best]
                row["null" if null else "real"] = {
                    "genome": g, "training_fitness": round(SR.fitness(best[0], SR.folds()[fold]), 2),
                    "heldout": stresses, "top10_heldout_net_at_100": [round(x) for x in top10],
                    "top10_mean_at_100": round(sum(top10) / len(top10))}
            res["loyo"][fold] = row
        real = [res["loyo"][y]["real"]["heldout"]["100"]["net"] for y in SR.YEARS]
        null = [res["loyo"][y]["null"]["heldout"]["100"]["net"] for y in SR.YEARS]
        final = pick(evals, "ALL", False, top=1)[0]
        g = final["genome"]
        per_stress = {str(int(s)): pool.evaluate([g], s)[0] for s in (0.0, 100.0, 200.0)}
        res["final"] = {"genome": g, "per_year": per_stress}
        checks = {
            "heldout_positive_years": sum(1 for x in real if x > 0),
            "heldout_sum_real": round(sum(real)), "heldout_sum_null": round(sum(null)),
            "final_four_year_net_at_200": round(sum(per_stress["200"][y]["net"] for y in SR.YEARS)),
            "final_years_positive_at_100": sum(1 for y in SR.YEARS if per_stress["100"][y]["net"] > 0),
        }
        checks["search_generalises"] = (checks["heldout_positive_years"] >= RULE["heldout_positive_years_min"]
                                        and checks["heldout_sum_real"] > 0
                                        and checks["heldout_sum_real"] > checks["heldout_sum_null"])
        checks["final_robust"] = (checks["final_four_year_net_at_200"] > 0
                                  and checks["final_years_positive_at_100"] == len(SR.YEARS))
        checks["verdict"] = "PROMISING (paper shadow only)" if checks["search_generalises"] and checks["final_robust"] \
            else "NOT PROVEN"
        res["checks"] = checks
    finally:
        pool.close()
    # the wallet ledger for the final pick, one continuous account Jan 2023 - Oct 2026
    import sn01_data as D
    import sn01_ledger as LG
    import sn01_sim as M
    sessions = []
    for y in SR.YEARS:
        sessions += [M.Session(s) for s in D.load_year(y)["sessions"].values()]
    ledgers = {}
    for mode in ("every2", "every3", "prop", "flat"):
        for stress in (0.0, 100.0, 200.0):
            for counting in ("net", "gross"):
                r = LG.play(sessions, g, mode, stress, counting)
                r.pop("days")
                ledgers[f"{mode}|{int(stress)}|{counting}"] = r
    res["ledger"] = ledgers
    tmp = out_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    tmp.replace(out_path)
    print(json.dumps(res["checks"], indent=1))


if __name__ == "__main__":
    main()
