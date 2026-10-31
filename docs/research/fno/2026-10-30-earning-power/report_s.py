"""O30s report -> report.json: descriptive views of the frozen run, written AFTER seeing results.json.

Nothing here can change the frozen verdict or the pick (analyze_s.py). Anything found here counts as found by looking.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_s as A  # noqa: E402

ROOT = A.ROOT
PLANS = {
    "Today's live rules (LIVE, shipped size and brakes)": ("LIVE", ("shipped",), "SHIPPED", False),
    "TPB, shipped size and brakes": ("TPB", ("shipped",), "SHIPPED", False),
    "BEST, shipped size and brakes": ("BEST", ("shipped",), "SHIPPED", False),
    "TPB, 1 lot, no brakes": ("TPB", ("fixed", 1), "NONE", False),
    "TPB, 2 lots, half when stretched": ("TPB", ("fixed", 2), "NONE", True),
    "TPB, 3 lots, half when stretched": ("TPB", ("fixed", 3), "NONE", True),
    "PICK: TPB + engine add, 3 lots, half when stretched": ("TPB|HOUSE", ("fixed", 3), "NONE", True),
    "TPB + engine add, 5 lots, throttle + day stop, half when stretched": ("TPB|HOUSE", ("fixed", 5), "THROTTLE+DAY", True),
    "TPB, 5 lots, no brakes": ("TPB", ("fixed", 5), "NONE", False),
    "TPB, 8 lots, no brakes": ("TPB", ("fixed", 8), "NONE", False),
    "TPB, 10 lots, no brakes": ("TPB", ("fixed", 10), "NONE", False),
    "LIVE, 3 lots, no brakes": ("LIVE", ("fixed", 3), "NONE", False),
    "BEST, 3 lots, no brakes": ("BEST", ("fixed", 3), "NONE", False),
    "BIG-DAY EXAMPLE: LIVE + add at +1R, 6 lots, half when stretched": ("LIVE|ADD1", ("fixed", 6), "NONE", True),
}


def reserve(name: str) -> int:
    return 3 if "ADD2" in name else 2 if ("ADD1" in name or "HOUSE" in name) else 1


def view(s: dict) -> dict:
    return {k: s[k] for k in ("net", "end", "fall_pct", "fall_rs", "trades", "days", "avg_lots", "max_lots", "avg_outlay",
                              "max_outlay", "worst_day", "best_day", "worst_week", "worst_month", "green_months",
                              "red_months", "no_cash", "halted")}


def stretch_split(rows: list, stress: float) -> dict:
    out = {}
    for label, (y, first, last) in A.HALVES.items():
        inside = [r for r in rows[y] if first <= r[6] <= last and r[5] is not None]
        far = [r[3] - stress * r[4] for r in inside if r[5] >= A.GRID["stretch_limit"]]
        near = [r[3] - stress * r[4] for r in inside if r[5] < A.GRID["stretch_limit"]]
        out[label] = {"stretched_trades": len(far), "stretched_net": round(sum(far)), "other_trades": len(near),
                      "other_net": round(sum(near)), "stretched_loss_rate": round(sum(v < 0 for v in far) / len(far), 3) if far else None,
                      "other_loss_rate": round(sum(v < 0 for v in near) / len(near), 3) if near else None}
    out["all"] = {k: sum(v[k] for v in out.values()) for k in ("stretched_trades", "stretched_net", "other_trades", "other_net")}
    return out


def main() -> None:
    trades, _sha = A.load()
    combos = json.loads((HERE / "_local/all-combos.json").read_text(encoding="utf-8"))
    results = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
    out: dict = {"schema": "o30s_report_v1", "status": "descriptive, written after results.json; cannot change the verdict"}

    # how much of the money the shipped book actually uses
    stored = ROOT / "docs/research/fno/2026-10-30-micro-adaptation/_local"
    use = {}
    for y in A.YEARS:
        raw = json.loads((stored / f"results-raw-{y}.json").read_text(encoding="utf-8"))
        for name, ref in (("LIVE", "REF|LIVE"), ("BEST", "REF|BEST"), ("TPB", "REF|TPB")):
            tr = [t for t in raw["trades"][raw["books"][ref]] if t.get("net_pnl") is not None]
            outlay = [float(t["entry_premium"]) * int(t["entry_qty"]) for t in tr]
            use[f"{name}_{y}"] = {"trades": len(tr), "days_traded": len({t["entry_time"][:10] for t in tr}),
                                  "avg_outlay": round(statistics.fmean(outlay)), "max_outlay": round(max(outlay)),
                                  "avg_share_of_money": round(statistics.fmean(outlay) / A.CAPITAL, 3),
                                  "avg_lots": round(statistics.fmean(int(t.get("lots_at_exit") or 1) for t in tr), 2),
                                  "rupee_net": round(sum(float(t["net_pnl"]) for t in tr))}
    out["money_in_use_shipped"] = use

    # the plans, with and without the extra cost
    plans = {}
    for label, (name, rule, brakes, half) in PLANS.items():
        row = {"book": name, "rule": list(rule), "brakes": brakes, "half": half}
        for tag, stress in (("as_replayed", 0.0), ("plus_200", A.STRESS)):
            years = {y: A.sim(trades[y][name], rule, brakes, stress, half, reserve=reserve(name)) for y in A.YEARS}
            joined = sorted(trades["2025"][name] + trades["2026"][name])
            both = A.sim(joined, rule, brakes, stress, half, reserve=reserve(name))
            row[tag] = {"y2025": view(years["2025"]), "y2026": view(years["2026"]), "both": view(both),
                        "negative_halves": A.halves_negative(years)}
        plans[label] = row
    out["plans"] = plans

    # chance tables, Kelly and the lots for 2 lakh without the extra cost
    no_stress = {}
    for name in ("LIVE", "BEST", "TPB"):
        by_year = {y: trades[y][name] for y in A.YEARS}
        goal = {}
        for y in A.YEARS:
            for n in range(1, 41):
                s = A.sim(trades[y][name], ("fixed", n))
                if s["net"] >= A.GOAL:
                    goal[y] = {"lots": n, "fall_pct": s["fall_pct"], "fall_rs": s["fall_rs"], "worst_day": s["worst_day"]}
                    break
            else:
                goal[y] = None
        no_stress[name] = {"chance": A.boot(by_year, [1, 2, 3, 5, 8, 10], stress=0.0), "kelly_lots": A.kelly(by_year, stress=0.0),
                           "lots_for_2_lakh": goal}
    out["without_extra_cost"] = no_stress

    # the O30q clue, on books it was not found on, and on the random books
    split = {}
    for name in ("TPB", "LIVE", "BEST", "TPB|HOLD"):
        split[name] = {"as_replayed": stretch_split({y: trades[y][name] for y in A.YEARS}, 0.0),
                       "plus_200": stretch_split({y: trades[y][name] for y in A.YEARS}, A.STRESS)}
    nulls = [n for n in trades["2025"] if n.startswith("NULL")]
    null_rows = {y: [r for n in nulls for r in trades[y][n]] for y in A.YEARS}
    split["random_books_pooled"] = {"as_replayed": stretch_split(null_rows, 0.0)}
    out["stretch"] = split
    lift = {}
    for rule in (("fixed", 2), ("fixed", 3), ("fixed", 5)):
        for name in ("TPB", "LIVE", "BEST"):
            row = {}
            for half in (False, True):
                row[str(half)] = {y: A.sim(trades[y][name], rule, "NONE", A.STRESS, half)["net"] for y in A.YEARS}
            lift[f"{name}|{rule[1]}"] = row
        lift[f"random_median|{rule[1]}"] = {
            str(half): {y: statistics.median(A.sim(trades[y][n], rule, "NONE", A.STRESS, half)["net"] for n in nulls)
                        for y in A.YEARS} for half in (False, True)}
    out["half_when_stretched_lift_at_plus_200"] = lift

    # the biggest days
    days = {}
    for name in ("LIVE", "BEST", "TPB", "LIVE|ADD1", "LIVE|ADD2"):
        daily: dict = defaultdict(float)
        for y in A.YEARS:
            for r in trades[y][name]:
                daily[r[6]] += r[3]
        ranked = sorted(daily.items(), key=lambda kv: -kv[1])
        worst = sorted(daily.items(), key=lambda kv: kv[1])
        days[name] = {"best_days_one_unit": [(d, round(v)) for d, v in ranked[:5]],
                      "worst_days_one_unit": [(d, round(v)) for d, v in worst[:5]],
                      "share_of_net_from_best_5_days": round(sum(v for _, v in ranked[:5]) / max(1.0, sum(daily.values())), 2),
                      "net": round(sum(daily.values())), "days": len(daily)}
    out["single_days"] = days

    # how the 71 passes split and the ones outside TPB
    passes = [r for r in combos if r["pass"]]
    def short(r):
        return {k: r[k] for k in ("book", "rule", "brakes", "half", "negative_halves")} | {
            "y2025": r["y2025"]["net"], "y2026": r["y2026"]["net"], "both": r["both"]["net"], "fall": r["both"]["fall_pct"],
            "fall_rs": r["both"]["fall_rs"], "worst_day": r["both"]["worst_day"], "avg_lots": r["both"]["avg_lots"]}
    out["passes_outside_TPB_alone"] = [short(r) for r in passes if not r["book"].startswith("TPB")]
    out["pass_counts"] = {"by_book": {b: sum(r["book"] == b for r in passes) for b in sorted({r["book"] for r in passes})},
                          "total_combos": len(combos), "total_passes": len(passes)}

    # how far a size picked on one year understates the fall on the other: TPB, half when stretched, at the extra cost
    size_check = {}
    for n in A.GRID["fixed_lots"]:
        years = {y: A.sim(trades[y]["TPB"], ("fixed", n), "NONE", A.STRESS, True) for y in A.YEARS}
        both = A.sim(sorted(trades["2025"]["TPB"] + trades["2026"]["TPB"]), ("fixed", n), "NONE", A.STRESS, True)
        size_check[str(n)] = {"y2025": years["2025"]["net"], "y2026": years["2026"]["net"], "fall_2025": years["2025"]["fall_pct"],
                              "fall_2026": years["2026"]["fall_pct"], "fall_both": both["fall_pct"], "worst_day": both["worst_day"]}
    out["tpb_half_size_ladder_plus_200"] = size_check
    out["frozen_pick"] = {k: results["pick"][k] for k in ("book", "rule", "brakes", "half")} if results["pick"] else None
    (HERE / "report.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("money_in_use_shipped", "stretch", "half_when_stretched_lift_at_plus_200", "single_days",
                                          "passes_outside_TPB_alone", "pass_counts", "tpb_half_size_ladder_plus_200",
                                          "without_extra_cost")}, indent=0)[:14000])


if __name__ == "__main__":
    main()
