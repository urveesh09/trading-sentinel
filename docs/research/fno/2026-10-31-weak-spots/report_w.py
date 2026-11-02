"""O31e - a descriptive report on the leading candidates, written after scoring. It chooses nothing and changes no frozen verdict. One
lot, brakes off, after Rs 200 a trade: consistency, dependence on a few days, and one lot on the real-money test's terms. -> report.json

Also writes freeze-2023.json once: the exam for a year no rule here has seen, fixed before any NIFTY 2023 data exists.
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
import analyze_w as A  # noqa: E402
from fno_costs import calc_fno_costs  # noqa: E402

YEARS = A.YEARS
LOT = 65
FLOOR = 7000.0
SESSIONS = {y: [d for d in json.loads((A.DATA[y] / "manifest.json").read_text(encoding="utf-8"))["sessions"] if d <= A.LAST[y]] for y in YEARS}
KEYS = {y: json.loads((HERE / f"_local/keys-{y}.json").read_text(encoding="utf-8")) for y in YEARS}
CANDIDATES = {"main": "RAW|MAIN", "puts_only_from_25": "RAW|D|only_puts_from_25", "puts_from_25_calls_from_30": "RAW|D|puts_from_25",
              "main_plus_tpb_puts_on_closed_days": "RAW|D|tpb_puts_closed", "main_without_eff": "RAW|C|no_eff", "main_puts_only": "RAW|C|puts_only"}
EXAM_BOOKS = ("EX|MAIN", "EX|D|only_puts_from_25", "EX|D|puts_from_25", "EX|D|tpb_puts_closed", "EX|C|puts_only", "EX|C|no_eff")


def trades(name: str) -> dict:
    return {y: json.loads((HERE / f"_local/evals/{KEYS[y][name]}.json").read_text(encoding="utf-8"))["trades"] for y in YEARS}


def one(t: dict) -> float:
    return A.one_lot(t) - A.PER_TRADE


def consistency(by_year: dict) -> dict:
    daily: dict = {}
    for y in YEARS:
        for t in A.closed(by_year[y]):
            d = t["entry_time"][:10]
            daily[d] = daily.get(d, 0.0) + one(t)
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
    best = {y: max((v, d) for d, v in daily.items() if d[:4] == y) for y in YEARS}
    total = sum(daily.values())
    rows = [t for y in YEARS for t in A.closed(by_year[y])]
    run = peak = fall = 0.0
    for d in sorted(sessions):
        run += daily.get(d, 0.0)
        peak, fall = max(peak, run), max(fall, peak - run)
    return {"net": round(total), "years": {y: round(sum(one(t) for t in A.closed(by_year[y]))) for y in YEARS}, "trades": len(rows),
            "win_pct": round(100 * sum(one(t) > 0 for t in rows) / len(rows)), "months_up": sum(v > 0 for v in series), "months_down": sum(v < 0 for v in series),
            "worst_month": round(min(series)), "three_months_up": sum(v > 0 for v in roll), "three_months_down": sum(v < 0 for v in roll), "weeks_up": sum(v > 0 for v in w),
            "weeks_down": sum(v < 0 for v in w), "weeks_flat": sum(v == 0 for v in w), "weeks": len(w), "weekly_t": A.plain_t(w), "fall": round(fall), "worst_day": round(min(daily.values())),
            "without_each_years_best_day": round(total - sum(v for v, _d in best.values())), "best_days": {y: {"day": best[y][1], "net": round(best[y][0])} for y in YEARS}}


def one_lot_runs(by_year: dict, length: int, start: float) -> dict:
    ends, none, refused = [], 0, 0
    for y in YEARS:
        by_day = defaultdict(list)
        for t in sorted(A.closed(by_year[y]), key=lambda t: t["entry_time"]):
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
                    cash += one(t)
                    held, took, done = t["exit_time"], took + 1, done + 1
            ends.append(cash)
            none += took == 0
            refused += short
    n = len(ends)
    return {"no_trade": round(none / n, 3), "up": round(sum(e > start for e in ends) / n, 3), "down": round(sum(e < start for e in ends) / n, 3),
            "worst_end": round(min(ends)), "below_floor": round(sum(e < FLOOR for e in ends) / n, 3), "refused_for_cash": round(refused / n, 3)}


def freeze_2023() -> None:
    target = HERE / "freeze-2023.json"
    if target.exists():
        return
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    out = {"schema": "o31e_nifty_2023_exam_v1", "status": "Fixed before any NIFTY 2023 data exists here. Breeze has not been asked whether it serves 2023.",
           "books": {n: frozen["books"][n] for n in EXAM_BOOKS},
           "why_2023": "NIFTY rose about 20% that year: a long calm rise, the hardest kind of year for a book that buys only puts, and one these three years do not hold.",
           "rule": {"once": "NIFTY 2023 is scored once with these books unchanged, nothing is tuned on it, and the data is sealed and fingerprinted before any replay",
                    "measure": "from Rs 2.5 lakh at today's limits, with the O30r extra cost in the money path; lot 65",
                    "main_holds": "EX|MAIN holds if net > 0 and its largest fall is <= 15% of the running peak",
                    "candidate_holds": "A candidate holds if its net is above EX|MAIN's on 2023 and its largest fall is <= 15% of the running peak",
                    "recommendation": "If EX|D|only_puts_from_25 or EX|D|tpb_puts_closed holds, the higher three-year net of those that hold is recommended as the main book. If neither does, the main book stays",
                    "no_change": "Nothing changes on this by itself; the owner decides"},
           "qualification": "NOT_ASSESSED", "can_place_orders": False}
    with target.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1)


def main() -> None:
    detail, monday = {}, {}
    for name, book in CANDIDATES.items():
        by = trades(book)
        detail[name] = consistency(by)
        monday[name] = {f"from_{int(s)}": {f"{n}_sessions": one_lot_runs(by, n, s) for n in (5, 20, 60)} for s in (12500.0, 15000.0)}
    out = {"schema": "o31e_report_v1", "one_lot_after_200": detail, "one_lot_on_monday_terms": monday, "qualification": "NOT_ASSESSED", "can_place_orders": False}
    tmp = HERE / "report.json.part"
    tmp.write_text(json.dumps(out, indent=1), encoding="utf-8", newline="\n")
    tmp.replace(HERE / "report.json")
    freeze_2023()
    for name, v in detail.items():
        print(f"{name:34} net {v['net']:>7} years {v['years']} trades {v['trades']} win {v['win_pct']}% months {v['months_up']}/{v['months_down']} 3m {v['three_months_up']}/{v['three_months_down']} weeks {v['weeks_up']}/{v['weeks_down']}/{v['weeks_flat']} t {v['weekly_t']} fall {v['fall']} worstday {v['worst_day']} worstmonth {v['worst_month']} noBest {v['without_each_years_best_day']} best {[(x['day'], x['net']) for x in v['best_days'].values()]}")
    for name, v in monday.items():
        print(name, {s: {k: (x["below_floor"], x["no_trade"], x["up"], x["down"], x["worst_end"]) for k, x in y.items()} for s, y in v.items()})


if __name__ == "__main__":
    main()
