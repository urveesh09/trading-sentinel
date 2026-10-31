"""Frozen analysis for O31g; report every rejected candidate, never tune here."""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
sys.path.insert(0, str(ROOT / "docs/research/fno/2026-10-31-weak-spots"))
import analyze_w as A  # noqa: E402

YEARS = ("2024", "2025", "2026")
FAMILIES = ("INTRADAY_DMI", "SHOCK_RECOVERY")
HALVES = {"2024": (("2024-01-01", "2024-06-30"), ("2024-07-01", "2024-12-31")),
          "2025": (("2025-01-01", "2025-06-30"), ("2025-07-01", "2025-12-31")),
          "2026": (("2026-01-01", "2026-05-31"), ("2026-06-01", "2026-10-28"))}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def raw_summary(by_year, sessions, cost=200):
    daily, years, halves, directions, reasons = {}, {}, {}, {}, Counter()
    unresolved = 0
    for year in YEARS:
        rows = by_year[year]
        unresolved += sum(t.get("net_pnl") is None for t in rows)
        closed = A.closed(rows)
        days = defaultdict(float)
        for t in closed:
            days[t["exit_time"][:10]] += A.one_lot(t) - cost
            reasons[t.get("exit_reason", "UNKNOWN")] += 1
        daily.update(days)
        net = sum(days.values())
        years[year] = {"net": round(net, 2), "trades": len(closed), "unresolved": len(rows) - len(closed),
                       "without_best_day": round(net - max([0.0, *days.values()]), 2),
                       "wins": sum(A.one_lot(t) - cost > 0 for t in closed)}
        halves[year] = [round(sum(v for d, v in days.items() if start <= d <= end), 2) for start, end in HALVES[year]]
        directions[year] = {d: {"net": round(sum(A.one_lot(t) - cost for t in closed if t["direction"] == d), 2),
                                "trades": sum(t["direction"] == d for t in closed)} for d in ("LONG", "SHORT")}
    every = [d for y in YEARS for d in sessions[y]]
    weekly = A.weeks_of(daily, every)
    total = sum(y["net"] for y in years.values())
    curve = peak = dd = 0.0
    for day in sorted(every):
        curve += daily.get(day, 0.0)
        peak = max(peak, curve)
        dd = max(dd, peak - curve)
    return {"years": years, "total": round(total, 2), "halves": halves, "directions": directions,
            "weekly": weekly, "weekly_t": A.plain_t(weekly), "daily": daily,
            "without_each_year_best_day": round(sum(y["without_best_day"] for y in years.values()), 2),
            "drawdown_rs": round(dd, 2), "unresolved": unresolved, "exit_reasons": dict(reasons)}


def judge(raw, exact, main, random_best):
    flags = {"positive_each_year": all(raw["years"][y]["net"] > 0 for y in YEARS),
             "enough_trades": min(raw["years"][y]["trades"] for y in YEARS) >= 8
             and sum(raw["years"][y]["trades"] for y in YEARS) >= 40,
             "five_nonnegative_halves": sum(v >= 0 for halves in raw["halves"].values() for v in halves) >= 5,
             "positive_without_year_best": all(raw["years"][y]["without_best_day"] > 0 for y in YEARS),
             "weekly_t": raw["weekly_t"] >= 2, "beats_random": raw["total"] > random_best,
             "combined_better_each_year": all(exact["years"][y]["net"] > main["years"][y]["net"] for y in YEARS),
             "combined_fall": all(exact["years"][y]["fall_pct"] <= main["years"][y]["fall_pct"] + 0.01 for y in YEARS),
             "combined_t": A.paired_t(exact["weekly"], main["weekly"]) >= 2,
             "resolved": not raw["unresolved"] and not exact["unresolved"]}
    return {"passes": all(flags.values()), "checks": flags,
            "combined_paired_t": A.paired_t(exact["weekly"], main["weekly"])}


def main():
    import lab_gap as X
    frozen = load(HERE / "freeze.json")
    keys = {y: load(HERE / f"_local/keys-{y}.json") for y in YEARS}
    sessions = {y: [d for d in load(ROOT / frozen["bindings"][y]["dataset"] / "manifest.json")["sessions"]
                    if d <= A.LAST[y]] for y in YEARS}
    every = [d for y in YEARS for d in sessions[y]]
    cache, issues = {}, {}
    for name, book in frozen["books"].items():
        cache[name] = {}
        for year in YEARS:
            data = load(HERE / "_local/evals" / f"{keys[year][name]}.json")
            rows = data["trades"]
            assert data["book"] == book
            cache[name][year] = rows
            bad = A.A.check_book(rows, {"cfg": book["cfg"]}, A.A.CAPITAL, book.get("cost"), book["cfg"].get("FNO_MAX_TRADES_PER_DAY", 3))
            memo = {k: v for k, v in data["notes"].items() if "conflict" in k or k == "named_memo_miss"}
            if bad or memo:
                issues[f"{name}|{year}"] = {"financial": bad, "memo": memo}

    def exact(name):
        years, days = {}, {}
        for y in YEARS:
            years[y] = A.A.path(cache[name][y])
            days.update(years[y]["daily"])
        return {"years": years, "weekly": A.weeks_of(days, every),
                "unresolved": sum(t.get("net_pnl") is None for y in YEARS for t in cache[name][y])}

    base = exact("EX|MAIN")
    assert tuple(base["years"][y]["net"] for y in YEARS) == A.PARITY_EXACT, "main parity failed"
    raw_main = raw_summary(cache["RAW|MAIN"], sessions)
    assert round(raw_main["total"]) == A.PARITY_RAW_TOTAL, "raw main parity failed"
    control = exact("EX|TPB_PUT_CONTROL")
    assert tuple(control["years"][y]["net"] for y in YEARS) == (15337, 47892, 77233), "TPB control parity failed"
    assert not issues, f"invalid or unresolved books: {issues}"
    random_totals = []
    for i in range(20):
        rows = {}
        for y in YEARS:
            old = ROOT / "docs/research/fno/2026-10-31-weak-spots/_local"
            key = load(old / f"keys-{y}.json")[f"RANDOM|{i:02d}|closed"]
            rows[y] = load(old / "evals" / f"{key}.json")["trades"]
        random_totals.append(raw_summary(rows, sessions)["total"])
    random_best = max(random_totals)
    output = {"schema": "o31g_complements_results_v1", "qualification": "NOT_ASSESSED", "can_place_orders": False,
              "correctness": {"fresh_replays": 24, "reused_random_replays": 60, "problems": issues, "main_and_tpb_parity": True},
              "sessions": {y: len(sessions[y]) for y in YEARS}, "rule": frozen["rule"],
              "main": {y: A.A.pub(base["years"][y]) for y in YEARS}, "main_raw": raw_main,
              "random_closed": {"best": random_best, "median": statistics.median(random_totals)},
              "tpb_control": {"exact": {y: A.A.pub(control["years"][y]) for y in YEARS},
                              "standalone": raw_summary(cache["RAW|TPB_PUT_CONTROL"], sessions)}, "candidates": {}}
    for family in FAMILIES:
        raw = raw_summary(cache[f"RAW|{family}"], sessions)
        ex = exact(f"EX|{family}")
        losses = {d for y in YEARS for d, v in base["years"][y]["daily"].items() if v < 0}
        output["candidates"][family] = {**judge(raw, ex, base, random_best), "standalone": raw,
            "stress_300": raw_summary(cache[f"RAW|{family}"], sessions, 300),
            "combined": {y: A.A.pub(ex["years"][y]) for y in YEARS},
            "increment_vs_main": {y: ex["years"][y]["net"] - base["years"][y]["net"] for y in YEARS},
            "hindsight_main_losing_dates_only": {"dates": len(losses), "net": round(sum(v for d, v in raw["daily"].items() if d in losses), 2),
                "note": "Complement operates only below daily ADX30, while main operates above it; no same-day hedge is expected"}}
    output["passing"] = [k for k, v in output["candidates"].items() if v["passes"]]
    X.write(HERE / "results.json", output)
    X.write(HERE / "_local/daily-results.json", {"sessions": sessions, "trades": cache})
    print(json.dumps({"passing": output["passing"], "candidates": {k: {"years": v["standalone"]["years"],
        "combined": v["combined"], "checks": v["checks"]} for k, v in output["candidates"].items()}}, indent=2))


if __name__ == "__main__":
    main()
