"""N10B's verdict, by PLAN2.md's checks, from saved replays only. Writes results-2.json. Round one's results.json stays as it was."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import score as S  # noqa: E402

YEARS = S.YEARS
CAPITAL = S.CAPITAL
R = S.REFERENCE
N08_2023, N08_FALL = -37581, 15.08
NEIGHBOURS = ("need10", "need30", "slice2.5", "slice10")


def account_end(name: str) -> float:
    return CAPITAL + sum(float(t["net_pnl"]) for y in YEARS for t in S.trades_of("carry2", y, name))


def checks(fresh: dict, trades: dict, accounts: dict, double_sum: float, x_sums: dict, ref_without5: float, stress: dict) -> dict:
    """PLAN2.md's ten checks, each a bare true or false."""
    w = S.whole(fresh)
    years = {y: fresh[y]["net"] for y in ("2024", "2025", "2026")}
    return {
        "1_sum_above_n08": w["net"] > R["n08_sum"],
        "2_worst_day_no_larger": w["worst_day"] >= R["cushion_worst_day"],
        "3_fall_no_larger_than_n08": round(w["fall_pct"], 2) <= N08_FALL,
        "4_2023_no_worse_than_n08": fresh["2023"]["net"] >= N08_2023,
        "5_years_positive_two_at_or_above": all(v > 0 for v in years.values()) and sum(years[y] >= R["cushion_years"][y] for y in years) >= 2,
        "6_account_all_costs": all(accounts[k] >= R["cushion_account"] for k in ("base", "low", "high")),
        "7_double_cost_at_or_above": double_sum >= R["cushion_double"],
        "8_plateau": all(v > R["cushion_sum"] for v in x_sums.values()) and all(accounts[k] >= R["cushion_account"] for k in NEIGHBOURS),
        "9_without_top_five": S.without_best(trades) >= ref_without5,
        "10_stress": stress["WATCH"]["worst_end"] >= 187500 and stress["WATCH"]["median_end"] >= stress["CUSHION"]["median_end"],
    }


def removes_the_cliff(ends: dict, ref_ends: dict, stress: dict) -> dict:
    """R2_CW's own question: stable across the cost shifts where N09.1 CUSHION is not, and the stress check holds."""
    spread = lambda e: max(abs(e["low"] - e["base"]), abs(e["high"] - e["base"])) / e["base"]  # noqa: E731
    out = {"spread_with_watch": spread(ends), "spread_cushion": spread(ref_ends), "stress_holds": stress["WATCH"]["worst_end"] >= 187500 and stress["WATCH"]["median_end"] >= stress["CUSHION"]["median_end"]}
    out["passes"] = out["spread_with_watch"] <= 0.05 and out["spread_cushion"] > 0.05 and out["stress_holds"]
    return out


def main() -> None:
    from analyze_panel import cscv
    import stress_watch as W
    weeks = S.all_weeks()
    names = ("R2_CW", "R2_THIRD_C", "R2_THIRD_CW")
    rows = {n: {y: S.trades_of("panel2", y, n) for y in YEARS} for n in names}
    rows["N08"] = {y: S.n08_trades(y) for y in YEARS}
    rows["CUSHION"] = {y: S.n091_trades("primary", y, "CUSHION") for y in YEARS}
    fresh = {n: {y: S.stats(rows[n][y]) for y in YEARS} for n in rows}
    assert round(S.whole(fresh["N08"])["net"]) == R["n08_sum"] and round(S.whole(fresh["CUSHION"])["net"]) == R["cushion_sum"]
    ref_without5 = S.without_best(rows["CUSHION"])
    stress = W.table(W.load_streams())
    (HERE / "stress-watch.json").write_text(json.dumps(stress, indent=1) + "\n", encoding="utf-8")

    accounts = {n: {"base": account_end(n), **{t: account_end(f"{n}|{t}") for t in ("low", "high")}} for n in ("CUSHION", "R2_CW", "R2_THIRD_CW")}
    assert round(accounts["CUSHION"]["base"]) == R["cushion_account"], "the base CUSHION account must reproduce N09.1's"
    third_accounts = {**accounts["R2_THIRD_CW"], **{t: account_end(f"R2_THIRD_CW|{t}") for t in NEIGHBOURS}}
    x_sums = {x: sum(float(t["net_pnl"]) for y in YEARS for t in S.trades_of("panel2", y, f"R2_THIRD_CW@{x}")) for x in ("0.75", "1.25")}
    double = sum(float(t["net_pnl"]) for y in YEARS for t in S.trades_of("panel2", y, "R2_THIRD_CW|double"))
    verdict = checks(fresh["R2_THIRD_CW"], rows["R2_THIRD_CW"], third_accounts, double, x_sums, ref_without5, stress)

    slices = {n: [s for s in json.loads((S.LOCAL / "states" / f"watch-{S.keys('carry2', '2026')[n].rsplit('_', 1)[-1]}.json").read_text(encoding="utf-8"))["slices"]] for n in ("R2_CW", "R2_THIRD_CW")}
    children = [c for y in YEARS for t in rows["R2_THIRD_CW"][y] for c in t.get("n10_children") or []]
    flat = {n: [t for y in YEARS for t in rows[n][y]] for n in rows}
    round_one = [*("EARN_N", "EARN_W", "EARN_WV", "EARN_WC", "EARN_WVC", "LADDER_WC", "HYBRID_C"), *(f"{n}@{x}" for n in S.CUSHION_BOOKS for x in ("0.75", "1.25"))]
    panel = {n: [t for y in YEARS for t in S.trades_of("panel", y, n)] for n in round_one}
    panel.update({n: flat[n] for n in ("R2_CW", "R2_THIRD_C", "R2_THIRD_CW", "N08", "CUSHION")})
    panel.update({f"R2_THIRD_CW@{x}": [t for y in YEARS for t in S.trades_of("panel2", y, f"R2_THIRD_CW@{x}")] for x in ("0.75", "1.25")})
    book_names = list(panel)
    pbo = cscv(np.column_stack([S.weekly_vector(panel[n], weeks) for n in book_names]), blocks=16)
    pbo["picks"] = {book_names[int(k)]: v for k, v in pbo["picks"].items()}
    result = {
        "schema": "n10b_results_v1", "all_data_seen": True, "books_tried_in_n10": len(book_names) - 2,
        "fresh": fresh, "aggregates": {n: S.whole(v) for n, v in fresh.items()},
        "checks": verdict, "n10b_passes": all(verdict.values()), "x_sums": x_sums, "double": double, "without_top_five": {"n10b": S.without_best(rows["R2_THIRD_CW"]), "cushion": ref_without5},
        "accounts": accounts, "third_accounts": third_accounts, "removes_the_cliff": removes_the_cliff(accounts["R2_CW"], accounts["CUSHION"], stress),
        "account_by_year": {n: {y: round(S.stats(S.trades_of("carry2", y, n))["net"]) for y in YEARS} for n in ("CUSHION", "R2_CW", "R2_THIRD_C", "R2_THIRD_CW")},
        "account_fall": {n: round(S.stats([t for y in YEARS for t in S.trades_of("carry2", y, n)])["fall_pct"], 2) for n in ("CUSHION", "R2_CW", "R2_THIRD_C", "R2_THIRD_CW")},
        "slices": slices, "earned": S.add_stats([t for y in YEARS for t in rows["R2_THIRD_CW"][y]]), "earned_by_year": {y: S.add_stats(rows["R2_THIRD_CW"][y]) for y in YEARS},
        "paired": {n: {"against_n08": S.paired(flat[n], flat["N08"], weeks), "against_cushion": S.paired(flat[n], flat["CUSHION"], weeks)} for n in names},
        "pbo": {**pbo, "book_names": book_names}, "stress_256_orderings": stress,
    }
    (HERE / "results-2.json").write_text(json.dumps(result, indent=1, allow_nan=False, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("aggregates", "checks", "n10b_passes", "x_sums", "double", "without_top_five", "accounts", "third_accounts", "removes_the_cliff", "account_by_year", "account_fall", "slices", "earned", "paired")}, indent=1, default=str))
    print("PBO", pbo["pbo"], "median percentile", pbo["median_out_of_sample_percentile"], "picks", pbo["picks"])
    print("STRESS", json.dumps(stress))


if __name__ == "__main__":
    main()
