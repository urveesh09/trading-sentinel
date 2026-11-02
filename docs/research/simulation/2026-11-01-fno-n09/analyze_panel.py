"""N09 scoring: the frozen rules of PLAN.md, from saved replays. It chooses by rule and prints everything, failures included.

    python analyze_panel.py panel     # challengers against N08; writes results-panel.json and composition.json
    python analyze_panel.py final     # N09 against N08; needs the final and carry runs; writes results-final.json
    python analyze_panel.py pbo       # the overfitting estimate; writes pbo.json
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "_local"
N08_LOCAL = HERE.parent / "2026-11-01-fno-n08" / "_local"
YEARS = ("2023", "2024", "2025", "2026")
POOL = 250000.0
LOT = 65
PARTS = ("ONE|CONFIRM", "ONE|STRUCTURE", "ONE|D65", "ONE|D75", "ONE|N08+NOISE")


def load(year: str, key: str, folder: Path | None = None) -> list:
    data = json.loads(((folder or LOCAL / f"evals-{year}") / f"{key}.json").read_text(encoding="utf-8"))
    return sorted((t for t in data["trades"] if t.get("net_pnl") is not None), key=lambda t: t["exit_time"])


def keys(name: str, year: str) -> dict:
    return json.loads((LOCAL / f"keys-{name}-{year}.json").read_text(encoding="utf-8"))


def r_of(t: dict) -> float:
    risk = abs(t["entry_underlying"] - t["initial_stop_underlying"])
    delta = abs(t.get("delta_at_entry") or 0.0)
    qty = t.get("entry_qty") or t.get("initial_quantity") or LOT
    return t["net_pnl"] / (delta * risk * qty) if delta > 0 and risk > 0 else 0.0


def stats(trades: list, pool: float = POOL) -> dict:
    equity = peak = pool
    fall = 0.0
    days = defaultdict(float)
    for t in trades:
        equity += t["net_pnl"]
        peak = max(peak, equity)
        fall = max(fall, (peak - equity) / peak)
        days[t["exit_time"][:10]] += t["net_pnl"]
    nets = sorted((t["net_pnl"] for t in trades), reverse=True)
    return {"net": round(sum(nets)), "r": round(sum(r_of(t) for t in trades), 2), "trades": len(trades), "wins": sum(n > 0 for n in nets), "fall_pct": round(fall * 100, 2),
            "worst_trade": round(min(nets, default=0)), "worst_day": round(min(days.values(), default=0)), "best_trade": round(nets[0] if nets else 0), "last": trades[-1]["exit_time"][:10] if trades else None,
            "without_best_5": round(sum(nets[5:]))}


def daily(trades: list) -> dict:
    out = defaultdict(float)
    for t in trades:
        out[t["exit_time"][:10]] += t["net_pnl"]
    return out


def weekly(trades: list) -> dict:
    out = defaultdict(float)
    for t in trades:
        iso = date.fromisoformat(t["exit_time"][:10]).isocalendar()
        out[(iso[0], iso[1])] += t["net_pnl"]
    return out


def paired_t(a: list, b: list, weeks: list) -> float:
    wa, wb = weekly(a), weekly(b)
    d = np.array([wa.get(w, 0.0) - wb.get(w, 0.0) for w in weeks])
    s = d.std(ddof=1)
    return float(d.mean() / (s / math.sqrt(len(d)))) if s > 0 else 0.0


def all_weeks() -> list:
    """Every ISO week in the four windows."""
    out = []
    for y, last in (("2023", "2023-12-31"), ("2024", "2024-12-31"), ("2025", "2025-12-31"), ("2026", "2026-10-28")):
        d = date.fromisoformat(f"{y}-01-01")
        end = date.fromisoformat(last)
        while d <= end:
            iso = d.isocalendar()
            if (iso[0], iso[1]) not in out:
                out.append((iso[0], iso[1]))
            d = date.fromordinal(d.toordinal() + 1)
    return out


def part_gates(book: dict, base: dict, weeks: list) -> dict:
    """The six frozen gates, against N08 at one lot. book and base: year -> trades."""
    b = {y: stats(book[y]) for y in YEARS}
    r = {y: stats(base[y]) for y in YEARS}
    flat_b, flat_r = [t for y in YEARS for t in book[y]], [t for y in YEARS for t in base[y]]
    db, dr = daily(flat_b), daily(flat_r)
    gain_days = sorted((db.get(d, 0.0) - dr.get(d, 0.0) for d in set(db) | set(dr)), reverse=True)
    gain = sum(gain_days)
    worst_b, worst_r = min(db.values()), min(dr.values())
    out = {
        "g1_2023": b["2023"]["net"] >= r["2023"]["net"],
        "g2_net_and_r": sum(b[y]["net"] for y in YEARS) > sum(r[y]["net"] for y in YEARS) and sum(b[y]["r"] for y in YEARS) > sum(r[y]["r"] for y in YEARS),
        "g3_years": sum(b[y]["net"] > r[y]["net"] for y in YEARS) >= 3,
        "g4_worst_day": worst_b >= worst_r * 1.10,
        "g5_not_five_days": gain - sum(gain_days[:5]) > 0,
        "g6_t": paired_t(flat_b, flat_r, weeks) >= 1.0,
    }
    return {"gates": out, "passes": all(out.values()), "t": round(paired_t(flat_b, flat_r, weeks), 2), "gain": round(gain), "gain_without_best_5_days": round(gain - sum(gain_days[:5])),
            "worst_day": round(worst_b), "by_year": b, "net_total": sum(b[y]["net"] for y in YEARS), "r_total": round(sum(b[y]["r"] for y in YEARS), 2)}


def pairing(book: dict, base: dict) -> dict:
    """New winners, missed winners, avoided losses, against N08: same day and direction, entered within 11 minutes after N08's entry."""
    out = {"kept": 0, "kept_change": 0.0, "missed_winners": 0, "missed_winners_rs": 0.0, "avoided_losers": 0, "avoided_losers_rs": 0.0, "new_winners": 0, "new_winners_rs": 0.0, "new_losers": 0, "new_losers_rs": 0.0}
    for y in YEARS:
        used = set()
        for t in base[y]:
            match = None
            for i, c in enumerate(book[y]):
                if i in used or c["entry_time"][:10] != t["entry_time"][:10] or c["direction"] != t["direction"]:
                    continue
                gap = (np.datetime64(c["entry_time"][:19]) - np.datetime64(t["entry_time"][:19])) / np.timedelta64(1, "m")
                if 0 <= gap <= 11:
                    match = i
                    break
            if match is None:
                if t["net_pnl"] > 0:
                    out["missed_winners"] += 1
                    out["missed_winners_rs"] += t["net_pnl"]
                else:
                    out["avoided_losers"] += 1
                    out["avoided_losers_rs"] += t["net_pnl"]
            else:
                used.add(match)
                out["kept"] += 1
                out["kept_change"] += book[y][match]["net_pnl"] - t["net_pnl"]
        for i, c in enumerate(book[y]):
            if i not in used:
                k = "new_winners" if c["net_pnl"] > 0 else "new_losers"
                out[k] += 1
                out[k + "_rs"] += c["net_pnl"]
    return {k: round(v) for k, v in out.items()}


def show(name: str, row: dict) -> None:
    cells = " ".join(f"{row['by_year'][y]['net']:>9,}" for y in YEARS)
    gates = "".join("Y" if v else "n" for v in row["gates"].values())
    print(f"{name:<20} {cells} total {row['net_total']:>9,} R {row['r_total']:>7.1f} t {row['t']:>5.2f} gain-5d {row['gain_without_best_5_days']:>8,} worst day {row['worst_day']:>7,} gates {gates} {'PASS' if row['passes'] else 'fail'}", flush=True)


def panel() -> None:
    weeks = all_weeks()
    base, books = {}, defaultdict(dict)
    cash = defaultdict(dict)
    for y in YEARS:
        d, p = keys("diag", y), keys("panel", y)
        base[y] = load(y, d["DIAG"])
        cash["CASH|N08"][y] = load(y, d["N08"])
        for name, key in p.items():
            (cash if name.startswith("CASH|") else books)[name][y] = load(y, key)
    base_stats = {y: stats(base[y]) for y in YEARS}
    print("N08 one lot          ", " ".join(f"{base_stats[y]['net']:>9,}" for y in YEARS), "total", sum(base_stats[y]["net"] for y in YEARS), "R", round(sum(base_stats[y]["r"] for y in YEARS), 1), flush=True)
    results = {}
    for name, book in books.items():
        results[name] = part_gates(book, base, weeks)
        results[name]["pairing"] = pairing(book, base)
        show(name, results[name])
        print("    ", results[name]["pairing"], "trades", [results[name]["by_year"][y]["trades"] for y in YEARS], "win", [results[name]["by_year"][y]["wins"] for y in YEARS], "falls", [results[name]["by_year"][y]["fall_pct"] for y in YEARS], flush=True)
    print("\nFull cash path, fresh Rs 2.5 lakh a year, today's brakes", flush=True)
    cash_stats = {}
    for name, book in cash.items():
        cash_stats[name] = {y: stats(book[y]) for y in YEARS}
        row = cash_stats[name]
        print(f"{name:<20}", " ".join(f"{row[y]['net']:>9,}" for y in YEARS), "total", sum(row[y]["net"] for y in YEARS), "falls", [row[y]["fall_pct"] for y in YEARS], "worst trade", min(row[y]["worst_trade"] for y in YEARS), "worst day", min(row[y]["worst_day"] for y in YEARS), "last 2023", row["2023"]["last"], flush=True)
    s, e, n = cash_stats["CASH|S_VOL"], cash_stats["CASH|NO_E"], cash_stats["CASH|N08"]
    total = lambda row: sum(row[y]["net"] for y in YEARS)  # noqa: E731
    fall = lambda row: max(row[y]["fall_pct"] for y in ("2024", "2025", "2026"))  # noqa: E731
    sizing_checks = {"2023_at_or_above_n08": s["2023"]["net"] >= n["2023"]["net"], "total_at_or_above_no_e": total(s) >= total(e), "fall_within_1pp_of_n08": fall(s) <= fall(n) + 1.0}
    deltas = [(results[k]["r_total"], d) for k, d in (("ONE|D65", 0.65), ("ONE|D75", 0.75)) if results[k]["passes"]]
    noise_alone_2023 = results["ONE|NOISE_HOUSE"]["by_year"]["2023"]["net"]
    composition = {"schema": "n09_composition_v1", "confirm": results["ONE|CONFIRM"]["passes"], "structure": results["ONE|STRUCTURE"]["passes"], "delta": max(deltas)[1] if deltas else None,
                   "noise": results["ONE|N08+NOISE"]["passes"] and noise_alone_2023 > 0, "noise_alone_2023": noise_alone_2023, "sizing": "S_VOL" if all(sizing_checks.values()) else "NO_E", "sizing_checks": sizing_checks}
    print("\nComposition by the frozen rule:", composition, flush=True)
    (HERE / "results-panel.json").write_text(json.dumps({"n08_one_lot": base_stats, "challengers": results, "cash": cash_stats}, indent=1), encoding="utf-8")
    (HERE / "composition.json").write_text(json.dumps(composition, indent=1) + "\n", encoding="utf-8")


def account(name: str, trades_by_year: dict) -> dict:
    flat = [t for y in YEARS for t in trades_by_year[y]]
    row = stats(flat)
    row["end_equity"] = round(POOL + sum(t["net_pnl"] for t in flat))
    row["by_year"] = {y: round(sum(t["net_pnl"] for t in trades_by_year[y])) for y in YEARS}
    row["trades_by_year"] = {y: len(trades_by_year[y]) for y in YEARS}
    return row


def final() -> None:
    weeks = all_weeks()
    f = {y: keys("final", y) for y in YEARS}
    d = {y: keys("diag", y) for y in YEARS}
    pick = lambda table, name: {y: load(y, table[y][name]) for y in YEARS}  # noqa: E731
    n09, n08 = pick(f, "N09"), pick(d, "N08")
    n09_one, n08_one = pick(f, "N09|ONE"), pick(d, "DIAG")
    t = lambda trades: {y: stats(trades[y]) for y in YEARS}  # noqa: E731
    total = lambda row: sum(row[y]["net"] for y in YEARS)  # noqa: E731
    a, b, ao, bo = t(n09), t(n08), t(n09_one), t(n08_one)
    print("           ", " ".join(f"{y:>9}" for y in YEARS), "    total", flush=True)
    for name, row in (("N09", a), ("N08", b), ("N09 one", ao), ("N08 one", bo)):
        print(f"{name:<11}", " ".join(f"{row[y]['net']:>9,}" for y in YEARS), f"{total(row):>9,}", "falls", [row[y]["fall_pct"] for y in YEARS], "trades", [row[y]["trades"] for y in YEARS], "wins", [row[y]["wins"] for y in YEARS], "worst trade", min(row[y]["worst_trade"] for y in YEARS), "worst day", min(row[y]["worst_day"] for y in YEARS), flush=True)
    costs = {}
    for name in ("COST|N09|none", "COST|N08|none", "COST|N09|double", "COST|N08|double"):
        costs[name] = {y: stats(load(y, f[y][name]))["net"] for y in YEARS}
        print(name, costs[name], sum(costs[name].values()), flush=True)
    accounts = {}
    carry = {y: json.loads((LOCAL / f"keys-carry-{y}.json").read_text(encoding="utf-8")) for y in YEARS}
    for name in carry["2023"]:
        rows = {y: load(y, carry[y][name], LOCAL / "evals-carry") for y in YEARS}
        accounts[name] = account(name, rows)
        print(f"account {name:<12} end {accounts[name]['end_equity']:>9,} by year {accounts[name]['by_year']} trades {accounts[name]['trades_by_year']} fall {accounts[name]['fall_pct']}% last {accounts[name]['last']}", flush=True)
    flat = [x for y in YEARS for x in n09[y]]
    pbo_value = json.loads((HERE / "pbo.json").read_text(encoding="utf-8"))["pbo"] if (HERE / "pbo.json").exists() else None
    checks = {
        "1_one_lot": total(ao) > total(bo) and ao["2023"]["net"] >= bo["2023"]["net"],
        "2_total_85pct": total(a) >= 0.85 * total(b),
        "3_2023": a["2023"]["net"] >= b["2023"]["net"],
        "4_worst_trade_and_day": min(a[y]["worst_trade"] for y in YEARS) >= min(b[y]["worst_trade"] for y in YEARS) and min(a[y]["worst_day"] for y in YEARS) >= min(b[y]["worst_day"] for y in YEARS),
        "5_account": accounts["N09|SHADOW"]["end_equity"] > accounts["N08"]["end_equity"],
        "6_double_cost": sum(costs["COST|N09|double"].values()) > 0,
        "7_pbo": pbo_value is not None and pbo_value < 0.5,
        "8_without_best_five": sum(sorted((x["net_pnl"] for x in flat), reverse=True)[5:]) > 0,
    }
    print("\nVerdict:", {k: ("pass" if v else "FAIL") for k, v in checks.items()}, "LEAD" if all(checks.values()) else "stays a seen-year lead", flush=True)
    print("paired weekly t, N09 against N08, four years, cash:", round(paired_t(flat, [x for y in YEARS for x in n08[y]], weeks), 2), "one lot:", round(paired_t([x for y in YEARS for x in n09_one[y]], [x for y in YEARS for x in n08_one[y]], weeks), 2), flush=True)
    (HERE / "results-final.json").write_text(json.dumps({"n09": a, "n08": b, "n09_one": ao, "n08_one": bo, "costs": costs, "accounts": accounts, "checks": checks, "lead": all(checks.values()), "qualified": False, "can_place_orders": False}, indent=1), encoding="utf-8")


def cscv(matrix: np.ndarray, blocks: int = 16) -> dict:
    """Bailey et al.: weeks in blocks, every half as in-sample, the best in-sample book's rank out of sample. PBO: how often it lands below the median."""
    t, n = matrix.shape
    edges = np.array_split(np.arange(t), blocks)
    logits, ranks, picks = [], [], defaultdict(int)
    for chosen in itertools.combinations(range(blocks), blocks // 2):
        inside = np.concatenate([edges[i] for i in chosen])
        outside = np.concatenate([edges[i] for i in range(blocks) if i not in chosen])
        sharpe = lambda idx: matrix[idx].mean(axis=0) / np.where(matrix[idx].std(axis=0, ddof=1) > 0, matrix[idx].std(axis=0, ddof=1), np.inf)  # noqa: E731
        s_in, s_out = sharpe(inside), sharpe(outside)
        best = int(np.argmax(s_in))
        picks[best] += 1
        rank = (s_out < s_out[best]).sum() + 0.5 * ((s_out == s_out[best]).sum() + 1)
        omega = rank / (n + 1)
        ranks.append(omega)
        logits.append(math.log(omega / (1 - omega)))
    logits = np.array(logits)
    return {"pbo": float((logits <= 0).mean()), "combinations": len(logits), "median_out_of_sample_percentile": float(np.median(ranks)), "picks": dict(picks), "books": n, "weeks": t}


def pbo() -> None:
    weeks = all_weeks()
    index = {w: i for i, w in enumerate(weeks)}
    series = {}

    def add(name: str, trades: list) -> None:
        row = np.zeros(len(weeks))
        for w, v in weekly(trades).items():
            row[index[w]] += v
        series[name] = row

    names = set(keys("screens", "2023"))
    screens = {}
    for y in ("2024", "2025", "2026"):
        merged = {}
        for phase in ("screen", "screen2", "screen3", "screen4"):
            merged.update(json.loads((N08_LOCAL / f"keys-{phase}-{y}.json").read_text(encoding="utf-8")))
        screens[y] = merged
    for name in sorted(names):
        rows = load("2023", keys("screens", "2023")[name])
        for y in ("2024", "2025", "2026"):
            rows = rows + load(y, screens[y][name], N08_LOCAL / "evals")
        add("SCREEN|" + name, rows)
    panel_keys = {y: keys("panel", y) for y in YEARS}
    for name in ("CASH|NO_E", "CASH|S_VOL"):
        add(name, [t for y in YEARS for t in load(y, panel_keys[y][name])])
    d = {y: keys("diag", y) for y in YEARS}
    add("N08", [t for y in YEARS for t in load(y, d[y]["N08"])])
    ordered = list(series)
    full = cscv(np.array([series[k] for k in ordered]).T)
    labelled = {ordered[int(k)]: v for k, v in sorted(full.pop("picks").items(), key=lambda kv: -kv[1])[:10]}
    n08_position = ordered.index("N08")
    matrix = np.array([series[k] for k in ordered]).T
    totals = matrix.sum(axis=0)
    print("PBO", round(full["pbo"], 3), "books", full["books"], "weeks", full["weeks"], "combinations", full["combinations"], "median out-of-sample percentile of the in-sample best", round(full["median_out_of_sample_percentile"], 3), flush=True)
    print("most often chosen in sample:", labelled, flush=True)
    print("N08 total rank", int((totals > totals[n08_position]).sum()) + 1, "of", len(totals), "total", round(totals[n08_position]), "median book", round(float(np.median(totals))), flush=True)
    (HERE / "pbo.json").write_text(json.dumps({**full, "most_often_chosen": labelled, "n08_total": round(float(totals[n08_position])), "median_total": round(float(np.median(totals))), "books_named": ordered}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=("panel", "final", "pbo"))
    {"panel": panel, "final": final, "pbo": pbo}[cli.parse_args().action]()
    sys.exit(0)
