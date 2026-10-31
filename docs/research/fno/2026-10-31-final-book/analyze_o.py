"""O31b analysis -> results.json. Freeze with lab_o.py before any replay; never change it after seeing a result."""
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
PARITY = {"BASE": (-219, 4805, 47333), "SKIP|none": (-33726, -38681, 61674), "BASE|AS": (17358, 26230, 79247)}
MIN_TRADES = 40
FALL_ROOM = 0.01
SAFER_POINTS = 0.02
SAFER_MONEY = 0.90
LOTS_MAX_FALL = 0.15
MAX_FALL = A.MAX_FALL


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


def judge(row: dict, base: dict) -> dict:
    """row / base: {"years": {year: path}, "weekly": [...]}"""
    y, b = row["years"], base["years"]
    delta = {k: y[k]["net"] - b[k]["net"] for k in YEARS}
    t = paired_t(row["weekly"], base["weekly"])
    falls_ok = all(y[k]["fall_pct"] <= b[k]["fall_pct"] + FALL_ROOM for k in YEARS)
    trades_ok = all(y[k]["trades"] >= MIN_TRADES for k in YEARS)
    every = all(v > 0 for v in delta.values())
    total, base_total = sum(y[k]["net"] for k in YEARS), sum(b[k]["net"] for k in YEARS)
    worst_base = max(YEARS, key=lambda k: b[k]["fall_pct"])
    safer = (y[worst_base]["fall_pct"] <= b[worst_base]["fall_pct"] - SAFER_POINTS and min(y[k]["net"] for k in YEARS) >=
             min(b[k]["net"] for k in YEARS) and total >= SAFER_MONEY * base_total)
    return {"delta": delta, "total": total, "t": t, "every_year": every, "falls_ok": falls_ok, "trades_ok": trades_ok,
            "improves": every and falls_ok and trades_ok and t >= 2.0, "safer": safer}


def held_out(rows: dict, base_name: str = "BASE") -> dict:
    """The selection-luck check: choose on two years, score on the third."""
    out = {}
    for hold in YEARS:
        rest = [y for y in YEARS if y != hold]
        fit = {n: r for n, r in rows.items() if all(r["years"][y]["fall_pct"] <= MAX_FALL and r["years"][y]["trades"] >= MIN_TRADES for y in rest)}
        pick = max(fit, key=lambda n: min(fit[n]["years"][y]["net"] for y in rest))
        out[hold] = {"pick": pick, "pick_net_on_held_out": rows[pick]["years"][hold]["net"], "base_net_on_held_out": rows[base_name]["years"][hold]["net"],
                     "beat_base": rows[pick]["years"][hold]["net"] > rows[base_name]["years"][hold]["net"]}
    return out


def lots_answer(rows: dict) -> dict:
    names = [n for n in rows if n.startswith("LOTS|") or n == "BASE"]
    table = {n: {"years": {y: rows[n]["years"][y]["net"] for y in YEARS}, "total": sum(rows[n]["years"][y]["net"] for y in YEARS),
                 "falls": {y: rows[n]["years"][y]["fall_pct"] for y in YEARS}, "worst_day": min(rows[n]["years"][y]["worst_day"] for y in YEARS),
                 "max_lots": max(rows[n]["years"][y]["max_lots"] for y in YEARS)} for n in names}
    ok = [n for n in names if all(rows[n]["years"][y]["fall_pct"] <= LOTS_MAX_FALL for y in YEARS)]
    return {"table": table, "within_fall_limit": ok, "best": max(ok, key=lambda n: table[n]["total"]) if ok else None}


def main() -> None:
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    keys = {y: json.loads((HERE / f"_local/keys-{y}.json").read_text(encoding="utf-8")) for y in YEARS}
    sessions = {y: [d for d in json.loads((DATA[y] / "manifest.json").read_text(encoding="utf-8"))["sessions"] if d <= LAST[y]] for y in YEARS}
    every = [d for y in YEARS for d in sessions[y]]
    rows, problems, trades_of, funnel = {}, {}, {}, {}
    for name, book in frozen["books"].items():
        years, weekly, all_trades = {}, {}, {}
        cap = int(book["cfg"].get("FNO_MAX_TRADES_PER_DAY", 3))
        daily: dict = {}
        for y in YEARS:
            d = json.loads((HERE / f"_local/evals/{keys[y][name]}.json").read_text(encoding="utf-8"))
            all_trades[y] = d["trades"]
            years[y] = A.path(d["trades"])
            daily.update(years[y]["daily"])
            bad = A.check_book(d["trades"], {"cfg": book["cfg"]}, A.CAPITAL, book.get("cost"), cap)
            open_days = sorted({t["entry_time"][:10] for t in d["trades"] if t.get("net_pnl") is None})
            bad.pop("unresolved", None)
            if bad:
                problems[f"{name}|{y}"] = bad
            years[y]["open_at_session_end"] = open_days
            memo = {k: v for k, v in d["notes"].items() if "conflict" in k or k == "named_memo_miss"}
            if memo:
                problems[f"{name}|{y}|notes"] = memo
            funnel[f"{name}|{y}"] = d["funnel"]
        rows[name] = {"years": years, "weekly": weeks_of(daily, every)}
        trades_of[name] = all_trades
    for n, want in PARITY.items():
        got = tuple(rows[n]["years"][y]["net"] for y in YEARS)
        assert got == want, f"parity failed for {n}: {got} against {want}"
    base = rows["BASE"]
    choice = {n: r for n, r in rows.items() if n != "BASE|AS"}
    verdicts = {}
    for n, r in choice.items():
        if n == "BASE":
            continue
        verdicts[n] = {**judge(r, base), "years": {y: {k: r["years"][y][k] for k in ("net", "fall_pct", "worst_day", "trades", "days", "max_lots", "green_months", "red_months")} for y in YEARS},
                       "no_effect": all(json.dumps(trades_of[n][y], sort_keys=True) == json.dumps(trades_of["BASE"][y], sort_keys=True) for y in YEARS)}
    carried = {}
    for n in frozen["carried"]:
        t = []
        for y in YEARS:
            key = keys[y][n] if y == "2024" else keys[y][f"{n}|carry"]
            t += json.loads((HERE / f"_local/evals/{key}.json").read_text(encoding="utf-8"))["trades"]
        carried[n] = A.pub(A.path(t))
    out = {"schema": "o31b_results_v1", "rule": frozen["rule"], "correctness": {"replays": sum(len(k) for k in keys.values()), "problems": problems, "parity": "exact"},
           "base": {y: A.pub(base["years"][y]) for y in YEARS}, "base_as_replayed": {y: A.pub(rows["BASE|AS"]["years"][y]) for y in YEARS},
           "verdicts": verdicts, "improves": [n for n, v in verdicts.items() if v["improves"]], "safer": [n for n, v in verdicts.items() if v["safer"]],
           "every_year_better": [n for n, v in verdicts.items() if v["every_year"]], "no_effect": [n for n, v in verdicts.items() if v["no_effect"]],
           "selection_luck": held_out(choice), "lots": lots_answer(rows), "carried": carried, "qualification": "NOT_ASSESSED", "can_place_orders": False}
    tmp = HERE / "results.json.part"
    tmp.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8", newline="\n")
    tmp.replace(HERE / "results.json")
    print(json.dumps({k: out[k] for k in ("improves", "safer", "every_year_better", "no_effect", "selection_luck")}, indent=1))
    print("problems", problems)


if __name__ == "__main__":
    main()
