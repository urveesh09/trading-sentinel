"""O30s Tier 2 analysis -> results-t2.json. Freeze with lab_s2.py before any replay; never change it after a result."""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_s as A  # noqa: E402

BUDGET_DAY = "2026-02-01"
EXPECTED = {"LIVE": (271, 80912), "BEST": (34517, 80232), "TPB": (36694, 42056)}
PER_TRADE_STRESS = 200.0


def closed(trades: list) -> list:
    return [t for t in trades if t.get("net_pnl") is not None]


def per_lot(trades: list, stress: float = 0.0) -> dict:
    daily: dict = defaultdict(float)
    for t in closed(trades):
        daily[t["entry_time"][:10]] += float(t["net_pnl"]) / max(1, int(t.get("lots_at_exit") or 1)) - stress
    run = peak = dd = 0.0
    for d in sorted(daily):
        run += daily[d]
        peak, dd = max(peak, run), max(dd, max(peak, run) - run)
    months: dict = defaultdict(float)
    for d, v in daily.items():
        months[d[:7]] += v
    return {"net": round(sum(daily.values())), "trades": len(closed(trades)), "days": len(daily), "fall": round(dd),
            "worst_day": round(min([0.0, *daily.values()])), "best_day": round(max([0.0, *daily.values()])),
            "without_best_day": round(sum(daily.values()) - max([0.0, *daily.values()])),
            "without_budget_day": round(sum(v for d, v in daily.items() if d != BUDGET_DAY)),
            "green_months": sum(v > 0 for v in months.values()), "red_months": sum(v < 0 for v in months.values()),
            "rupees": round(sum(float(t["net_pnl"]) for t in closed(trades)))}


def half_nets(trades: dict) -> dict:
    out = {}
    for label, (y, first, last) in A.HALVES.items():
        out[label] = round(sum(float(t["net_pnl"]) / max(1, int(t.get("lots_at_exit") or 1)) for t in closed(trades[y])
                               if first <= t["entry_time"][:10] <= last))
    return out


def load(mode: str) -> dict:
    sha = A.hashlib_sha(HERE / "freeze-t2.json")
    out = {}
    for y in A.YEARS:
        raw = json.loads((HERE / f"_local/results-t2-{mode}-{y}.json").read_text(encoding="utf-8"))
        assert raw["freeze_sha256"] == sha, "replays are not from this freeze"
        out[y] = {n: raw["trades"][k] for n, k in raw["books"].items()}
    return out


def main() -> None:
    shipped = load("shipped")
    table, verdict = {}, {}
    for n in shipped["2025"]:
        by_year = {y: shipped[y][n] for y in A.YEARS}
        table[n] = {"y2025": per_lot(by_year["2025"]), "y2026": per_lot(by_year["2026"]),
                    "y2025_stress": per_lot(by_year["2025"], PER_TRADE_STRESS)["net"],
                    "y2026_stress": per_lot(by_year["2026"], PER_TRADE_STRESS)["net"], "halves": half_nets(by_year)}
    parity = {n: (table[n]["y2025"]["net"], table[n]["y2026"]["net"]) == e for n, e in EXPECTED.items()}
    for n in ("LIVE", "BEST", "TPB", "UNION", "DRIVE"):
        a, b = table[f"{n}|skip"], table[n]
        verdict[n] = {"beats_both_years": a["y2025"]["net"] > b["y2025"]["net"] and a["y2026"]["net"] > b["y2026"]["net"],
                      "halves_not_worse": sum(a["halves"][k] >= b["halves"][k] for k in A.HALVES),
                      "trades_ok": min(a["y2025"]["trades"], a["y2026"]["trades"]) >= 40,
                      "positive_after_stress": a["y2025_stress"] > 0 and a["y2026_stress"] > 0}
        verdict[n]["helps"] = (verdict[n]["beats_both_years"] and verdict[n]["halves_not_worse"] >= 3
                               and verdict[n]["trades_ok"] and verdict[n]["positive_after_stress"])

    raw = load("raw")
    base_raw, _ = A.load()
    prepped = {y: {n: A.prep(t) for n, t in raw[y].items()} for y in A.YEARS}
    nulls = [n for n in prepped["2025"] if n.startswith("NULL")]
    control = {y: {"random_median_without": statistics.median(
                       A.sim(base_raw[y][n[:6]], ("fixed", 1), "NONE", 0.0)["net"] for n in nulls),
                   "random_median_with": statistics.median(A.sim(prepped[y][n], ("fixed", 1), "NONE", 0.0)["net"] for n in nulls)}
               for y in A.YEARS}
    ladder = {}
    for n in ("LIVE|skip", "BEST|skip", "TPB|skip"):
        ladder[n] = {}
        joined = sorted(prepped["2025"][n] + prepped["2026"][n])
        for lots in (1, 2, 3, 4, 5, 8):
            for brakes in ("NONE", "THROTTLE+DAY"):
                row = {}
                for tag, stress in (("as_replayed", 0.0), ("plus_200", A.STRESS)):
                    years = {y: A.sim(prepped[y][n], ("fixed", lots), brakes, stress) for y in A.YEARS}
                    both = A.sim(joined, ("fixed", lots), brakes, stress)
                    row[tag] = {"y2025": years["2025"]["net"], "y2026": years["2026"]["net"], "fall_pct": both["fall_pct"],
                                "fall_rs": both["fall_rs"], "worst_day": both["worst_day"], "worst_month": both["worst_month"],
                                "negative_halves": A.halves_negative(years), "trades": both["trades"]}
                ladder[n][f"{lots}|{brakes}"] = row
        ladder[n]["chance_plus_200"] = A.boot({y: prepped[y][n] for y in A.YEARS}, [1, 2, 3, 5, 8, 10])
        ladder[n]["chance_as_replayed"] = A.boot({y: prepped[y][n] for y in A.YEARS}, [1, 2, 3, 5, 8, 10], stress=0.0)
        ladder[n]["kelly_plus_200"] = A.kelly({y: prepped[y][n] for y in A.YEARS})
        ladder[n]["kelly_as_replayed"] = A.kelly({y: prepped[y][n] for y in A.YEARS}, stress=0.0)
    out = {"schema": "o30s_tier2_results_v1", "freeze_sha256": A.hashlib_sha(HERE / "freeze-t2.json"), "parity": parity,
           "verdict": verdict, "per_lot": table, "random_control": control, "ladder": ladder,
           "qualification": "NOT_ASSESSED", "can_place_orders": False}
    (HERE / "results-t2.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("parity", parity)
    print("verdict", json.dumps(verdict))
    for n, r in table.items():
        print(f'{n:14} 2025 {r["y2025"]["net"]:7} 2026 {r["y2026"]["net"]:7} no-budget {r["y2026"]["without_budget_day"]:7} | '
              f'+200: {r["y2025_stress"]:7} {r["y2026_stress"]:7} | trades {r["y2025"]["trades"]:4} {r["y2026"]["trades"]:4} | '
              f'fall {r["y2025"]["fall"]:6} {r["y2026"]["fall"]:6} | rupees {r["y2025"]["rupees"]:7} {r["y2026"]["rupees"]:7} | halves {r["halves"]}')
    print("control", control)


if __name__ == "__main__":
    main()
