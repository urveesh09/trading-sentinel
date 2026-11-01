"""Fixed N10.1 comparisons and exact prior-study controls; no trading logic."""
from __future__ import annotations

import argparse
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "_local"
YEARS = ("2023", "2024", "2025", "2026")
NAMES = ("WATCH_FLAT", "PREMIUM_LOCK")
OLD = HERE.parent / "2026-11-01-fno-n10"
spec = importlib.util.spec_from_file_location("n10_frozen_score", OLD / "score.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


def load(phase, year, name, local=LOCAL):
    keys = json.loads((local / f"keys-{phase}-{year}.json").read_text())
    return json.loads((local / "evals" / f"{keys[name]}.json").read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def parity():
    rows = []
    fields = ("entry_time", "tradingsymbol", "direction", "entry_premium", "entry_qty", "exit_time", "exit_premium", "exit_reason", "net_pnl", "n10_children")
    for year in YEARS:
        prior = {"N08": S.n08_trades(year), "CUSHION": S.n091_trades("primary", year, "CUSHION"),
                 "N10": S.trades_of("panel2", year, "R2_THIRD_CW"), "STRICT": S.trades_of("strict-annual", year, "STRICT")}
        for name, expected in prior.items():
            actual = load("controls", year, name)["trades"]
            select = lambda ts: [{k: t.get(k) for k in fields} for t in ts]
            assert select(actual) == select(expected), ("exact control failed", year, name)
            rows.append({"year": year, "book": name, "trades": len(actual), "net": sum(t["net_pnl"] for t in actual), "exact": True})
    write(HERE / "control-parity.json", {"passed": True, "checks": rows})
    print("EXACT_CONTROLS", len(rows), sum(r["trades"] for r in rows), flush=True)


def match(rows, baseline):
    key = lambda t: (t["entry_time"], t["tradingsymbol"])
    a, b = {key(t): t for t in rows}, {key(t): t for t in baseline}
    assert len(a) == len(rows) and len(b) == len(baseline)
    shared = a.keys() & b.keys()
    return {"matched": len(shared), "changed_exits": sum((a[k]["exit_time"], a[k]["exit_premium"]) != (b[k]["exit_time"], b[k]["exit_premium"]) for k in shared),
            "matched_net_delta": sum(a[k]["net_pnl"] - b[k]["net_pnl"] for k in shared),
            "added_count": len(a.keys()-b.keys()), "added_net": sum(a[k]["net_pnl"] for k in a.keys()-b.keys()),
            "missed_count": len(b.keys()-a.keys()), "missed_net": sum(b[k]["net_pnl"] for k in b.keys()-a.keys())}


def superiority(a, b):
    return {"annual_net_above_n10": a["total"]["net"] > b["total"]["net"],
            "2023_no_worse": a["annual"]["2023"]["net"] >= b["annual"]["2023"]["net"]-0.01,
            "positive_2024_to_2026": all(a["annual"][y]["net"] > 0 for y in YEARS[1:]),
            "worst_day_no_worse": a["total"]["worst_day"] >= b["total"]["worst_day"]-0.01,
            "annual_drawdown_no_worse": a["total"]["fall_pct"] <= b["total"]["fall_pct"]+1e-7,
            "double_cost_no_worse": a["double_net"] >= b["double_net"]-0.01,
            "without_own_top5_no_worse": a["without_top5"] >= b["without_top5"]-0.01,
            "every_continuous_cost_no_worse": all(a["accounts"][k]["end"] >= b["accounts"][k]["end"]-0.01 for k in b["accounts"])}


def report():
    result = {"schema": "n101_results_v1", "all_years_seen": True, "coverage": "PARTIAL", "fidelity": "BAR_LIFECYCLE", "planned_annuals": 80, "books": {}}
    for name in ("N08", "CUSHION", "STRICT", "N10", *NAMES):
        by_year = {y: load("controls", y, name)["trades"] if name not in NAMES else load("annual", y, f"{name}|200")["trades"] for y in YEARS}
        yearly = {y: S.stats(ts) for y, ts in by_year.items()}
        book = {"annual": yearly, "total": S.whole(yearly), "without_top5": S.without_best(by_year),
                "children": S.add_stats([t for ts in by_year.values() for t in ts]), "accounts": {}}
        if name in ("N10", *NAMES):
            for extra in (199, 200, 202, 400):
                ts = [t for y in YEARS for t in load("carry", y, f"{name}|{extra}")["trades"]]
                book["accounts"][str(extra)] = {**S.stats(ts), "net_by_year": {y: sum(t["net_pnl"] for t in load("carry", y, f"{name}|{extra}")["trades"]) for y in YEARS}}
            book["double_net"] = sum(t["net_pnl"] for y in YEARS for t in load("annual", y, f"{name}|400")["trades"]) if name in NAMES else sum(t["net_pnl"] for y in YEARS for t in S.trades_of("panel2", y, "R2_THIRD_CW|double"))
        result["books"][name] = book
    baseline = result["books"]["N10"]
    for name in NAMES:
        book = result["books"][name]
        book["superiority_checks"] = superiority(book, baseline)
        book["economically_superior"] = all(book["superiority_checks"].values())
        a = {y: load("annual", y, f"{name}|200")["trades"] for y in YEARS}
        b = {y: load("controls", y, "N10")["trades"] for y in YEARS}
        book["opportunity_cost"] = {y: match(a[y], b[y]) for y in YEARS}
        book["paired_weekly_descriptive"] = S.paired([t for ts in a.values() for t in ts], [t for ts in b.values() for t in ts], S.all_weeks())
    write(HERE / "results.json", result)
    print(json.dumps({n: {"net": b["total"]["net"], "annual": {y: s["net"] for y, s in b["annual"].items()}, "accounts": {k: s["end"] for k, s in b["accounts"].items()}, "superior": b.get("economically_superior")} for n, b in result["books"].items()}), flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=("parity", "report"))
    {"parity": parity, "report": report}[cli.parse_args().action]()
