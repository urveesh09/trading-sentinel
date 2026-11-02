"""O31e analysis -> results.json. Frozen with lab_w.py before any of its replays; never changed after seeing a result."""
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
sys.path[:0] = [str(ROOT / "python-engine"), str(FNO / "2026-10-30-risk-spectrum")]
import analyze_r as A  # noqa: E402

YEARS = ("2024", "2025", "2026")
DATA = {"2024": FNO / "2026-10-30-day-router/_local/dataset-nifty-2024", "2025": FNO / "2026-10-30-nifty-2025-test/_local/dataset-nifty-2025",
        "2026": FNO / "2026-10-29-year-genome/_local/dataset-nifty"}
LAST = {"2024": "2024-12-31", "2025": "2025-12-31", "2026": "2026-10-28"}
PER_TRADE = 200.0
PARITY_EXACT = (16371, 5710, 30540)
PARITY_RAW_TOTAL = 43170
MIN_TRADES_CHANGE = 15
MIN_TRADES_E_YEAR = 8
MIN_TRADES_E_ALL = 40
FALL_ROOM = 0.01
BALANCE_MONEY = 1.2
BALANCE_FALL = 0.12
BALANCE_T = 1.5
MAX_FALL = 0.25


def one_lot(t: dict) -> float:
    return float(t["net_pnl"]) / max(1, int(t.get("lots_at_exit") or 1))


def closed(rows: list) -> list:
    return [t for t in rows if t.get("net_pnl") is not None]


def weeks_of(daily: dict, sessions: list) -> list:
    out: dict = defaultdict(float)
    for d in sessions:
        iso = date.fromisoformat(d).isocalendar()
        out[(iso[0], iso[1])] += daily.get(d, 0.0)
    return [out[k] for k in sorted(out)]


def paired_t(a: list, b: list) -> float:
    diff = [x - y for x, y in zip(a, b)]
    if len(diff) < 2:
        return 0.0
    sd = statistics.stdev(diff)
    return round(statistics.fmean(diff) / (sd / len(diff) ** 0.5), 2) if sd else 0.0


def plain_t(a: list) -> float:
    return paired_t(a, [0.0] * len(a))


def judge_change(row: dict, base: dict) -> dict:
    """row / base: {"years": {year: path}, "weekly": [...]}"""
    y, b = row["years"], base["years"]
    delta = {k: y[k]["net"] - b[k]["net"] for k in YEARS}
    t = paired_t(row["weekly"], base["weekly"])
    total, base_total = sum(y[k]["net"] for k in YEARS), sum(b[k]["net"] for k in YEARS)
    falls_ok = all(y[k]["fall_pct"] <= b[k]["fall_pct"] + FALL_ROOM for k in YEARS)
    trades_ok = all(y[k]["trades"] >= MIN_TRADES_CHANGE for k in YEARS)
    return {"delta": delta, "total": total, "t": t, "every_year_better": all(v > 0 for v in delta.values()), "falls_ok": falls_ok, "trades_ok": trades_ok,
            "improves": all(v > 0 for v in delta.values()) and falls_ok and trades_ok and t >= 2.0,
            "better_balance": total >= BALANCE_MONEY * base_total and all(y[k]["net"] > 0 for k in YEARS) and max(y[k]["fall_pct"] for k in YEARS) <= BALANCE_FALL and t >= BALANCE_T}


def per_lot(by_year: dict, sessions: dict) -> dict:
    years, daily = {}, {}
    for y in YEARS:
        rows = closed(by_year[y])
        years[y] = {"net": round(sum(one_lot(t) - PER_TRADE for t in rows)), "trades": len(rows)}
        for t in rows:
            d = t["entry_time"][:10]
            daily[d] = daily.get(d, 0.0) + one_lot(t) - PER_TRADE
    every = [d for y in YEARS for d in sessions[y]]
    run = peak = fall = 0.0
    for d in sorted(every):
        run += daily.get(d, 0.0)
        peak, fall = max(peak, run), max(fall, peak - run)
    return {"years": years, "total": sum(years[y]["net"] for y in YEARS), "worst_year": min(years[y]["net"] for y in YEARS), "fall": round(fall),
            "weekly": weeks_of(daily, every), "worst_day": round(min([0.0, *daily.values()])), "best_day": round(max([0.0, *daily.values()]))}


def judge_specialist(row: dict, random_best: float) -> dict:
    n = [row["years"][y]["trades"] for y in YEARS]
    t = plain_t(row["weekly"])
    positive = all(row["years"][y]["net"] > 0 for y in YEARS)
    trades_ok = min(n) >= MIN_TRADES_E_YEAR and sum(n) >= MIN_TRADES_E_ALL
    return {"positive_every_year": positive, "trades_ok": trades_ok, "t": t, "beats_random_best": row["total"] > random_best,
            "passes": positive and trades_ok and t >= 2.0 and row["total"] > random_best}


def held_out_changes(rows: dict) -> dict:
    out = {}
    for hold in YEARS:
        rest = [y for y in YEARS if y != hold]
        fit = {n: r for n, r in rows.items() if all(r["years"][y]["fall_pct"] <= MAX_FALL and r["years"][y]["trades"] >= MIN_TRADES_CHANGE for y in rest)}
        pick = max(fit, key=lambda n: min(fit[n]["years"][y]["net"] for y in rest))
        out[hold] = {"pick": pick, "net_on_held_out": rows[pick]["years"][hold]["net"], "main_on_held_out": rows["MAIN"]["years"][hold]["net"],
                     "beat_main": rows[pick]["years"][hold]["net"] > rows["MAIN"]["years"][hold]["net"]}
    return out


def held_out_specialists(rows: dict) -> dict:
    out = {}
    for hold in YEARS:
        rest = [y for y in YEARS if y != hold]
        fit = {n: r for n, r in rows.items() if all(r["years"][y]["trades"] >= MIN_TRADES_E_YEAR for y in rest)}
        pick = max(fit, key=lambda n: min(fit[n]["years"][y]["net"] for y in rest))
        out[hold] = {"pick": pick, "net_on_held_out": rows[pick]["years"][hold]["net"], "earned": rows[pick]["years"][hold]["net"] > 0}
    return out


def direction_split(books: list) -> dict:
    """Median per-lot total of puts and of calls over several random books, each year: the put-call gap with no skill in the entry."""
    out = {}
    for label, want in (("puts", "SHORT"), ("calls", "LONG")):
        by_year = {y: statistics.median(sum(one_lot(t) - PER_TRADE for t in closed(b[y]) if t["direction"] == want) for b in books) for y in YEARS}
        out[label] = {"years": {y: round(v) for y, v in by_year.items()}, "total": round(sum(by_year.values()))}
    return out


def main() -> None:
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    keys = {y: json.loads((HERE / f"_local/keys-{y}.json").read_text(encoding="utf-8")) for y in YEARS}
    sessions = {y: [d for d in json.loads((DATA[y] / "manifest.json").read_text(encoding="utf-8"))["sessions"] if d <= LAST[y]] for y in YEARS}
    every = [d for y in YEARS for d in sessions[y]]

    def load(key: str) -> dict:
        return json.loads((HERE / f"_local/evals/{key}.json").read_text(encoding="utf-8"))

    problems, cache = {}, {}
    for name, book in frozen["books"].items():
        cap = int(book["cfg"].get("FNO_MAX_TRADES_PER_DAY", 3))
        cache[name] = {}
        for y in YEARS:
            d = load(keys[y][name])
            cache[name][y] = d["trades"]
            bad = A.check_book(d["trades"], {"cfg": book["cfg"]}, A.CAPITAL, book.get("cost"), cap)
            bad.pop("unresolved", None)
            if bad:
                problems[f"{name}|{y}"] = bad
            memo = {k: v for k, v in d["notes"].items() if "conflict" in k or k == "named_memo_miss"}
            if memo:
                problems[f"{name}|{y}|notes"] = memo

    def exact(name: str) -> dict:
        years, daily = {}, {}
        for y in YEARS:
            years[y] = A.path(cache[name][y])
            daily.update(years[y]["daily"])
        return {"years": years, "weekly": weeks_of(daily, every)}

    main_exact = exact("EX|MAIN")
    got = tuple(main_exact["years"][y]["net"] for y in YEARS)
    assert got == PARITY_EXACT, f"exact parity failed: {got}"
    main_raw = per_lot(cache["RAW|MAIN"], sessions)
    assert main_raw["total"] == PARITY_RAW_TOTAL, f"surface parity failed: {main_raw['total']}"
    changes = {n[3:]: exact(n) for n in frozen["books"] if n.startswith("EX|") and n != "EX|MAIN"}
    verdicts = {}
    for n, row in changes.items():
        raw = per_lot(cache[f"RAW|{n}"], sessions)
        verdicts[n] = {**judge_change(row, main_exact), "years": {y: {k: row["years"][y][k] for k in ("net", "fall_pct", "worst_day", "trades", "days", "green_months", "red_months", "last_trade")} for y in YEARS},
                       "raw_after_200": {k: raw[k] for k in ("years", "total", "worst_year", "fall", "worst_day")}, "raw_weekly_t": plain_t(raw["weekly"]),
                       "no_effect": all(json.dumps(cache[f"EX|{n}"][y], sort_keys=True) == json.dumps(cache["EX|MAIN"][y], sort_keys=True) for y in YEARS)}
    random_rows = [per_lot(cache[f"RANDOM|{i:02d}|closed"], sessions) for i in range(20)]
    random_best = max(r["total"] for r in random_rows)
    specialists = {n[4:]: per_lot(cache[n], sessions) for n in frozen["books"] if n.startswith("RAW|E|")}
    judged = {n: {**judge_specialist(r, random_best), **{k: r[k] for k in ("years", "total", "worst_year", "fall", "worst_day", "best_day")}} for n, r in specialists.items()}
    picks = {"MAIN": main_exact, **changes}
    random_a30 = []
    final = FNO / "2026-10-31-final-book/_local"
    keys_c = {y: json.loads((final / f"keys-c-{y}.json").read_text(encoding="utf-8")) for y in YEARS}
    for i in range(20):
        random_a30.append({y: json.loads((final / "evals" / f"{keys_c[y][f'RANDOM|{i:02d}|A30']}.json").read_text(encoding="utf-8"))["trades"] for y in YEARS})
    out = {"schema": "o31e_results_v1", "rule": frozen["rule"], "correctness": {"replays": sum(len(k) for k in keys.values()), "problems": problems, "parity": "exact"},
           "main": {y: A.pub(main_exact["years"][y]) for y in YEARS}, "main_raw_after_200": {k: main_raw[k] for k in ("years", "total", "worst_year", "fall", "worst_day")},
           "changes": verdicts, "improves": [n for n, v in verdicts.items() if v["improves"]], "better_balance": [n for n, v in verdicts.items() if v["better_balance"]],
           "every_year_better": [n for n, v in verdicts.items() if v["every_year_better"]], "no_effect": [n for n, v in verdicts.items() if v["no_effect"]],
           "selection_luck_changes": held_out_changes(picks), "specialists": judged, "specialists_passing": [n for n, v in judged.items() if v["passes"]],
           "selection_luck_specialists": held_out_specialists(specialists),
           "random_closed": {"median_total": statistics.median(r["total"] for r in random_rows), "best_total": random_best, "positive_every_year": sum(r["worst_year"] > 0 for r in random_rows),
                             "median_by_year": {y: statistics.median(r["years"][y]["net"] for r in random_rows) for y in YEARS}},
           "direction_control": {"random_closed_days": direction_split([cache[f"RANDOM|{i:02d}|closed"] for i in range(20)]), "random_adx30_days": direction_split(random_a30)},
           "qualification": "NOT_ASSESSED", "can_place_orders": False}
    tmp = HERE / "results.json.part"
    tmp.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8", newline="\n")
    tmp.replace(HERE / "results.json")
    print(json.dumps({k: out[k] for k in ("improves", "better_balance", "every_year_better", "no_effect", "specialists_passing", "selection_luck_changes", "selection_luck_specialists", "random_closed", "direction_control")}, indent=0))
    print("problems", str(problems)[:800])


if __name__ == "__main__":
    main()
