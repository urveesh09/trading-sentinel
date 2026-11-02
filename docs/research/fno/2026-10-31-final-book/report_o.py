"""O31b/c - a descriptive report over the stored replays, written after both were scored. It chooses nothing and changes no
frozen decision. Three things: how stretched entries did by how stretched they were (is the rule's limit a real slope or a
spike?), how often the rule helped across the whole surface, and the candidate books in detail, including one lot on the
real-money test's terms. -> report.json
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
FNO = ROOT / "docs/research/fno"
sys.path[:0] = [str(HERE), str(ROOT / "python-engine"), str(FNO / "2026-10-30-risk-spectrum")]
import analyze_o as AO  # noqa: E402
import analyze_r as A  # noqa: E402
from fno_costs import calc_fno_costs  # noqa: E402

YEARS = AO.YEARS
PER_TRADE = 200.0
LOT = 65
FLOOR = 7000.0
BUCKETS = ((-9.0, 0.0), (0.0, 0.25), (0.25, 0.35), (0.35, 0.5), (0.5, 0.65), (0.65, 0.75), (0.75, 1.0), (1.0, 99.0))
SESSIONS = {y: [d for d in json.loads((AO.DATA[y] / "manifest.json").read_text(encoding="utf-8"))["sessions"] if d <= AO.LAST[y]] for y in YEARS}
KEYS_B = {y: json.loads((HERE / f"_local/keys-{y}.json").read_text(encoding="utf-8")) for y in YEARS}
KEYS_C = {y: json.loads((HERE / f"_local/keys-c-{y}.json").read_text(encoding="utf-8")) for y in YEARS}


def load(key: str) -> dict:
    return json.loads((HERE / f"_local/evals/{key}.json").read_text(encoding="utf-8"))


def trades(name: str, keys: dict) -> dict:
    return {y: load(keys[y][name])["trades"] for y in YEARS}


def closed(rows: list) -> list:
    return [t for t in rows if t.get("net_pnl") is not None]


def one_lot(t: dict) -> float:
    return float(t["net_pnl"]) / max(1, int(t.get("lots_at_exit") or 1))


def by_stretch(by_year: dict) -> dict:
    out = {}
    for lo, hi in BUCKETS:
        row = {}
        for y in YEARS:
            rows = [t for t in closed(by_year[y]) if t.get("stretch") is not None and lo <= float(t["stretch"]) < hi]
            row[y] = {"trades": len(rows), "after_200": round(sum(one_lot(t) - PER_TRADE for t in rows))}
        n = sum(row[y]["trades"] for y in YEARS)
        total = sum(row[y]["after_200"] for y in YEARS)
        out[f"{lo:g} to {hi:g}"] = {**row, "trades": n, "after_200": total, "per_trade": round(total / n) if n else 0}
    return out


def consistency(by_year: dict, stress: float) -> dict:
    daily: dict = {}
    for y in YEARS:
        for t in closed(by_year[y]):
            d = t["entry_time"][:10]
            daily[d] = daily.get(d, 0.0) + one_lot(t) - stress
    sessions = [d for y in YEARS for d in SESSIONS[y]]
    months, weeks = defaultdict(float), defaultdict(float)
    for d in sessions:
        v = daily.get(d, 0.0)
        months[d[:7]] += v
        iso = date.fromisoformat(d).isocalendar()
        weeks[(iso[0], iso[1])] += v
    series = [months[m] for m in sorted(months)]
    roll = [sum(series[i:i + 3]) for i in range(len(series) - 2)]
    w = list(weeks.values())
    se = statistics.pstdev(w) / len(w) ** 0.5
    best_each_year = {}
    for y in YEARS:
        inside = {d: v for d, v in daily.items() if d[:4] == y}
        best = max(inside, key=inside.get)
        best_each_year[y] = {"day": best, "net": round(inside[best])}
    total = sum(daily.values())
    run = peak = fall = 0.0
    for d in sorted(sessions):
        run += daily.get(d, 0.0)
        peak = max(peak, run)
        fall = max(fall, peak - run)
    return {"net": round(total), "months": len(series), "green_months": sum(v > 0 for v in series), "red_months": sum(v < 0 for v in series),
            "rolling_3m": len(roll), "rolling_3m_green": sum(v > 0 for v in roll), "rolling_3m_red": sum(v < 0 for v in roll), "weeks": len(w),
            "weeks_up": sum(v > 0 for v in w), "weeks_down": sum(v < 0 for v in w), "weeks_flat": sum(v == 0 for v in w), "weekly_t": round(statistics.fmean(w) / se, 2),
            "fall": round(fall), "worst_day": round(min(daily.values())), "worst_month": round(min(series)), "best_each_year": best_each_year,
            "without_each_years_best_day": round(total - sum(v["net"] for v in best_each_year.values()))}


def one_lot_runs(by_year: dict, length: int, start: float, stress: float) -> dict:
    ends, none, refused = [], 0, 0
    for y in YEARS:
        by_day = defaultdict(list)
        for t in sorted(closed(by_year[y]), key=lambda t: t["entry_time"]):
            by_day[t["entry_time"][:10]].append(t)
        days = SESSIONS[y]
        for i in range(len(days) - length + 1):
            cash, held, took, short = start, "", 0, False
            for d in days[i:i + length]:
                done = 0
                for t in by_day.get(d, ()):
                    if t["entry_time"] < held or done >= 3:
                        continue
                    prem = float(t["entry_premium"])
                    if cash < FLOOR or prem * LOT + calc_fno_costs(prem, prem, LOT) > cash:
                        short = True
                        continue
                    cash += one_lot(t) - stress
                    held, took, done = t["exit_time"], took + 1, done + 1
            ends.append(cash)
            none += took == 0
            refused += short
    n = len(ends)
    return {"runs": n, "no_trade": round(none / n, 3), "up": round(sum(e > start for e in ends) / n, 3), "down": round(sum(e < start for e in ends) / n, 3),
            "worst_end": round(min(ends)), "below_floor": round(sum(e < FLOOR for e in ends) / n, 3), "refused_for_cash": round(refused / n, 3)}


def main() -> None:
    results = json.loads((HERE / "results-c.json").read_text(encoding="utf-8"))
    surface = results["surface_per_lot_after_200"]
    wins, cells = {}, 0
    for a in (20, 25, 27, 30, 32, 35):
        none = surface[f"A{a}|Snone"]["total"]
        wins[f"A{a}"] = {s: surface[f"A{a}|S{s}"]["total"] > none for s in ("25", "35", "50", "65", "75")}
    win_count = sum(v for row in wins.values() for v in row.values())
    strict = [(a, s) for a in (30, 32, 35) for s in ("35", "50", "65", "75")]
    books = {"LIVE (today)": ("SKIP|none", KEYS_B, 0.0), "four + rule, ADX 25": ("BASE|AS", KEYS_B, PER_TRADE), "four + rule, ADX 30": ("EXACT|A30|AS", KEYS_C, PER_TRADE)}
    detail, monday = {}, {}
    for name, (book, keys, stress) in books.items():
        by = trades(book, keys)
        detail[name] = {"as_replayed": consistency(by, 0.0) if stress else None, "after_200": consistency(by, stress)}
    live_as = {y: None for y in YEARS}
    earn = FNO / "2026-10-30-earning-power/_local"
    shipped = {"2024": json.loads((earn / "results-2024-shipped.json").read_text(encoding="utf-8")),
               "2025": json.loads((earn / "results-t2-shipped-2025.json").read_text(encoding="utf-8")),
               "2026": json.loads((earn / "results-t2-shipped-2026.json").read_text(encoding="utf-8"))}
    live_as = {y: shipped[y]["trades"][shipped[y]["books"]["LIVE"]] for y in YEARS}
    detail["LIVE (today)"] = {"as_replayed": consistency(live_as, 0.0), "after_200": consistency(live_as, PER_TRADE)}
    for name, by in (("LIVE (today)", live_as), ("four + rule, ADX 25", trades("BASE|AS", KEYS_B)), ("four + rule, ADX 30", trades("EXACT|A30|AS", KEYS_C))):
        monday[name] = {f"from_{int(s)}": {f"{n}_sessions": one_lot_runs(by, n, s, PER_TRADE) for n in (5, 20, 60)} for s in (12500.0, 15000.0)}
    out = {"schema": "o31_final_book_report_v1",
           "stretch_buckets_four_strategies_one_lot_no_rule_adx25": by_stretch(trades("SURFACE|A25|Snone", KEYS_C)),
           "stretch_buckets_four_strategies_one_lot_no_rule_adx30": by_stretch(trades("SURFACE|A30|Snone", KEYS_C)),
           "rule_beats_no_rule_by_cell": wins, "rule_beats_no_rule_cells": f"{win_count} of 30",
           "strict_block_adx30_35_limits35_75": {f"A{a}|S{s}": {"total": surface[f"A{a}|S{s}"]["total"], "worst_year": surface[f"A{a}|S{s}"]["worst_year"], "fall": surface[f"A{a}|S{s}"]["fall"]} for a, s in strict},
           "adx25_row_limits35_75": {f"A25|S{s}": {"total": surface[f"A25|S{s}"]["total"], "worst_year": surface[f"A25|S{s}"]["worst_year"], "fall": surface[f"A25|S{s}"]["fall"]} for s in ("35", "50", "65", "75")},
           "detail_per_lot": detail, "one_lot_on_monday_terms_after_200": monday, "qualification": "NOT_ASSESSED", "can_place_orders": False}
    tmp = HERE / "report.json.part"
    tmp.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8", newline="\n")
    tmp.replace(HERE / "report.json")
    print(json.dumps({k: out[k] for k in ("stretch_buckets_four_strategies_one_lot_no_rule_adx25", "stretch_buckets_four_strategies_one_lot_no_rule_adx30")}, indent=0)[:3800])
    print(out["rule_beats_no_rule_cells"], wins)
    print(json.dumps(out["strict_block_adx30_35_limits35_75"]))
    print(json.dumps(out["adx25_row_limits35_75"]))
    print(json.dumps(detail, indent=0)[:4600])
    print(json.dumps(monday)[:3200])


if __name__ == "__main__":
    main()
