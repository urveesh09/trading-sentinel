"""N09 supplement: the runs PLAN_SUPPLEMENT.md fixes. It imports the frozen n09_lab.py unchanged.

    N08_YEAR=<year> python n09_supp.py run --jobs 4                (brakes off, cost, the 2023 complements)
    N08_YEAR=<year> N09_CARRY=1 python n09_supp.py carry --jobs 3  (one account, 2023 first)
    python n09_supp.py score                                       (writes results-supplement.json and pbo-corrected.json)
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
YEARS = ("2023", "2024", "2025", "2026")
LOCAL = HERE / "_local"


def lab():
    import n09_lab as Z
    return Z


if __name__ != "__main__" and "N08_YEAR" in __import__("os").environ:
    import n09_lab  # noqa: F401  pool workers need the patches


def s_vol(Z) -> dict:
    return Z.cash_books()["CASH|S_VOL"]


def run_books(Z) -> dict:
    out = {}
    for name, book in (("N08", Z.n08()), ("S_VOL", s_vol(Z))):
        b = copy.deepcopy(book)
        b["cfg"] = {**b.get("cfg", {}), **Z.L.BRAKES_OFF}
        b["label"] = f"N09|SUPP|NOBRAKE|{name}"
        out[f"NOBRAKE|{name}"] = b
    for name, cost in (("none", [0.0, 0.0]), ("double", [400.0, 10.0])):
        b = copy.deepcopy(s_vol(Z))
        b.update(cost=cost, label=f"N09|SUPP|COST|S_VOL|{name}")
        out[f"COST|S_VOL|{name}"] = b
    return out


def complement_books(Z) -> dict:
    B = Z.B
    out = {n: b for n, b in B.books("screen").items() if n.startswith("RAW|") and n not in ("RAW|MAIN", "RAW|E|tpb_puts")}
    gap = sys.modules["lab_gap"]
    for fam in gap.FAMILIES:
        out[f"RAW|{fam}"] = gap.books()[f"RAW|{fam}"]
    return out


def carry_books(Z) -> dict:
    earlier = YEARS[:YEARS.index(Z.YEAR)]
    shadow = [f"evals-{y}/{json.loads((LOCAL / f'keys-diag-{y}.json').read_text())['DIAG']}.json" for y in YEARS]
    base = s_vol(Z)
    extra = base.get("n09") or {}
    arms = {"S_VOL": base, "S_VOL|ANNUAL": Z.with_n09(base, "N09|SUPP|CARRY|S_VOL|ANNUAL", **extra, rearm="ANNUAL"), "S_VOL|SHADOW": Z.with_n09(base, "N09|SUPP|CARRY|S_VOL|SHADOW", **extra, rearm="SHADOW", shadow=shadow)}
    out = {}
    for name, book in arms.items():
        b = copy.deepcopy(book)
        if earlier:
            saved = [json.loads((LOCAL / f"keys-supp-carry-{y}.json").read_text(encoding="utf-8"))[name] for y in earlier]
            b["carry"] = saved
            if b.get("n09", {}).get("rearm"):
                b["n09"]["floor_from"] = saved[-1].rsplit("_", 1)[-1]
        out[name] = b
    return out


# ---- scoring ---------------------------------------------------------------------------------------------------------


def reshuffle(seed: int = 9, paths: int = 10000, months: int = 46) -> dict:
    """N08 at one lot: whole calendar months drawn at random with replacement. An account starts at Rs 2.5 lakh with the fixed floor.
    Same draws for each rule. Shadow reads the same stream, last 20 closed trades. Rough: it says nothing the 46 months don't contain."""
    from analyze_panel import keys, load
    streams = defaultdict(list)
    for y in YEARS:
        for t in load(y, keys("diag", y)["DIAG"]):
            streams[t["exit_time"][:7]].append(float(t["net_pnl"]))
    labels = sorted(streams)
    # Months with no trades count too: they are part of what the months contain. List every month in the windows.
    every = [f"{y}-{m:02d}" for y in YEARS for m in range(1, 13) if not (y == "2026" and m > 10)]
    bank = [streams.get(m, []) for m in every]
    rng = np.random.default_rng(seed)
    out = {"NONE": [], "ANNUAL": [], "SHADOW": []}
    restarts = {"ANNUAL": [], "SHADOW": []}
    lows = {"NONE": [], "ANNUAL": [], "SHADOW": []}
    for _ in range(paths):
        draw = rng.integers(0, len(bank), months)
        for rule in out:
            equity = low = 250000.0
            floor = 212500.0
            halted, halted_month, paper, count = False, None, [], 0
            for i, m in enumerate(draw):
                # ANNUAL: every 12th month of the path counts as a new calendar year.
                if rule == "ANNUAL" and halted and i // 12 > halted_month // 12:
                    halted, floor, count = False, equity * 0.85, count + 1
                for net in bank[m]:
                    paper.append(net)
                    if rule == "SHADOW" and halted and len(paper) >= 20 and sum(paper[-20:]) > 0:
                        halted, floor, count = False, equity * 0.85, count + 1
                    if not halted:
                        equity += net
                        low = min(low, equity)
                        if equity < floor:
                            halted, halted_month = True, i
            out[rule].append(equity)
            lows[rule].append(low)
            if rule != "NONE":
                restarts[rule].append(count)
    table = {}
    for rule, ends in out.items():
        a = np.array(ends)
        table[rule] = {"median_end": round(float(np.median(a))), "p5_end": round(float(np.percentile(a, 5))), "p25_end": round(float(np.percentile(a, 25))), "p75_end": round(float(np.percentile(a, 75))), "share_below_start": round(float((a < 250000).mean()), 3),
                       "lowest_equity_p5": round(float(np.percentile(lows[rule], 5))), "mean_restarts": round(float(np.mean(restarts[rule])), 2) if rule in restarts else 0}
    return {"paths": paths, "months": months, "month_bank": len(bank), "months_with_trades": len(labels), "rules": table}


def corrected_pbo() -> dict:
    from analyze_panel import all_weeks, cscv, keys, load, weekly, N08_LOCAL
    weeks = all_weeks()
    index = {w: i for i, w in enumerate(weeks)}
    series = {}

    def add(name, trades):
        row = np.zeros(len(weeks))
        for w, v in weekly(trades).items():
            row[index[w]] += v
        series[name] = row

    k23 = keys("screens", "2023")
    screens = {}
    for y in ("2024", "2025", "2026"):
        merged = {}
        for phase in ("screen", "screen2", "screen3", "screen4"):
            merged.update(json.loads((N08_LOCAL / f"keys-{phase}-{y}.json").read_text(encoding="utf-8")))
        screens[y] = merged
    removed = []
    for name in sorted(k23):
        if "COST|" in name:
            removed.append(name)
            continue
        rows = load("2023", k23[name])
        for y in ("2024", "2025", "2026"):
            rows = rows + load(y, screens[y][name], N08_LOCAL / "evals")
        add("SCREEN|" + name, rows)
    p = {y: keys("panel", y) for y in YEARS}
    for name in ("CASH|NO_E", "CASH|S_VOL"):
        add(name, [t for y in YEARS for t in load(y, p[y][name])])
    add("N08", [t for y in YEARS for t in load(y, keys("diag", y)["N08"])])
    # Exact duplicates add ties and no information. Keep the first of each, and N08 by name.
    seen, ordered = {}, []
    for name in sorted(series, key=lambda n: (n != "N08", n)):
        fingerprint = tuple(np.round(series[name], 2))
        if fingerprint in seen:
            continue
        seen[fingerprint] = name
        ordered.append(name)
    matrix = np.array([series[k] for k in ordered]).T
    full = cscv(matrix)
    picks = full.pop("picks")
    labelled = {ordered[int(k)]: v for k, v in sorted(picks.items(), key=lambda kv: -kv[1])[:10]}
    totals = matrix.sum(axis=0)
    i = ordered.index("N08")
    out = {**full, "removed_cost_books": removed, "duplicates_removed": len(series) - len(ordered), "most_often_chosen": labelled, "n08_total": round(float(totals[i])), "n08_rank_by_total": int((totals > totals[i]).sum()) + 1, "median_total": round(float(np.median(totals)))}
    (HERE / "pbo-corrected.json").write_text(json.dumps({**out, "books_named": ordered}, indent=1), encoding="utf-8")
    return out


def complements() -> dict:
    from analyze_panel import load, keys
    k23 = keys("supp", "2023")
    broad = {y: json.loads((HERE.parent / f"2026-10-31-fno-broad-search/_local/keys-screen-{y}.json").read_text(encoding="utf-8")) for y in ("2024", "2025", "2026")}
    gap = {y: json.loads((HERE.parent / f"2026-10-31-fno-complements/_local/keys-{y}.json").read_text(encoding="utf-8")) for y in ("2024", "2025", "2026")}
    table = {}
    for name in k23:
        if not name.startswith("RAW|"):
            continue
        row = {"2023": sum(t["net_pnl"] - 200 for t in load("2023", k23[name])), "trades_2023": len(load("2023", k23[name]))}
        for y in ("2024", "2025", "2026"):
            source, folder = (broad[y], HERE.parent / "2026-10-31-fno-broad-search/_local/evals") if name in broad[y] else (gap[y], HERE.parent / "2026-10-31-fno-complements/_local/evals")
            row[y] = sum(t["net_pnl"] - 200 for t in load(y, source[name], folder)) if name in source else None
        table[name] = {k: (round(v) if v is not None else None) for k, v in row.items()}
    return table


def score() -> None:
    from analyze_panel import POOL, YEARS as Y, account, keys, load, stats
    k = {y: keys("supp", y) for y in Y}
    p = {y: keys("panel", y) for y in Y}
    d = {y: keys("diag", y) for y in Y}
    table = {}
    for name in ("NOBRAKE|N08", "NOBRAKE|S_VOL", "COST|S_VOL|none", "COST|S_VOL|double"):
        table[name] = {y: stats(load(y, k[y][name])) for y in Y}
        print(f"{name:<20}", " ".join(f"{table[name][y]['net']:>9,}" for y in Y), "total", sum(table[name][y]["net"] for y in Y), "falls", [table[name][y]["fall_pct"] for y in Y], "worst day", min(table[name][y]["worst_day"] for y in Y), "trades", [table[name][y]["trades"] for y in Y], flush=True)
    accounts = {}
    carry = {y: json.loads((LOCAL / f"keys-supp-carry-{y}.json").read_text(encoding="utf-8")) for y in Y}
    n08_carry = {y: json.loads((LOCAL / f"keys-carry-{y}.json").read_text(encoding="utf-8")) for y in Y}
    for name in carry["2023"]:
        accounts[name] = account(name, {y: load(y, carry[y][name], LOCAL / "evals-carry") for y in Y})
    for name in ("N08", "N08|ANNUAL", "N08|SHADOW"):
        accounts[name] = account(name, {y: load(y, n08_carry[y][name], LOCAL / "evals-carry") for y in Y})
    for name, row in accounts.items():
        flat = None
        print(f"account {name:<14} end {row['end_equity']:>9,} by year {row['by_year']} trades {row['trades_by_year']} fall {row['fall_pct']}% worst day {row['worst_day']} worst trade {row['worst_trade']} last {row['last']}", flush=True)
    total = lambda rows: sum(rows[y]["net"] for y in Y)  # noqa: E731
    fresh_n08 = {y: stats(load(y, d[y]["N08"])) for y in Y}
    fresh_vol = {y: stats(load(y, p[y]["CASH|S_VOL"])) for y in Y}
    b_checks = {
        "1_account_95pct": accounts["S_VOL|SHADOW"]["end_equity"] >= 0.95 * accounts["N08|SHADOW"]["end_equity"],
        "2_account_fall_and_worst_day": accounts["S_VOL|SHADOW"]["fall_pct"] <= accounts["N08|SHADOW"]["fall_pct"] and accounts["S_VOL|SHADOW"]["worst_day"] >= accounts["N08|SHADOW"]["worst_day"],
        "3_nobrake_2023_10pct": table["NOBRAKE|S_VOL"]["2023"]["net"] >= 0.9 * table["NOBRAKE|N08"]["2023"]["net"],
        "4_fresh_total_90pct": total(fresh_vol) >= 0.9 * total(fresh_n08),
        "5_double_cost": total(table["COST|S_VOL|double"]) > 0,
    }
    print("\nN09B checks:", {a: ("pass" if v else "FAIL") for a, v in b_checks.items()}, "LEAD" if all(b_checks.values()) else "not the lead", flush=True)
    shuffle = reshuffle()
    print("reshuffle", json.dumps(shuffle["rules"], indent=0), flush=True)
    r = shuffle["rules"]
    restart_checks = {"1_real_account": accounts["N08|SHADOW"]["end_equity"] > accounts["N08"]["end_equity"], "2_median": r["SHADOW"]["median_end"] > r["NONE"]["median_end"], "3_p5_within_10pct": r["SHADOW"]["p5_end"] >= 0.9 * r["NONE"]["p5_end"]}
    print("restart checks:", {a: ("pass" if v else "FAIL") for a, v in restart_checks.items()}, flush=True)
    pbo = corrected_pbo()
    print("corrected PBO", round(pbo["pbo"], 3), "books", pbo["books"], "removed", pbo["removed_cost_books"], "duplicates", pbo["duplicates_removed"], "median out-of-sample percentile", round(pbo["median_out_of_sample_percentile"], 3), "N08 rank", pbo["n08_rank_by_total"], flush=True)
    print("chosen in sample:", pbo["most_often_chosen"], flush=True)
    comp = complements()
    ok = {n: r for n, r in comp.items() if r["2023"] > 0}
    print(f"\ncomplements, net after Rs 200: {len(comp)} books; positive on 2023: {len(ok)}", flush=True)
    for n, r in sorted(comp.items(), key=lambda kv: -kv[1]["2023"])[:12]:
        print(f"{n:<34}", r, flush=True)
    full = {n: r for n, r in comp.items() if None not in (r["2024"], r["2025"], r["2026"])}
    passing = [n for n, r in full.items() if r["2023"] > 0 and sum(r[y] > 0 for y in Y) >= 3 and sum(r[y] for y in Y) > 0]
    print("positive 2023, at least 3 of 4 years, four-year net above zero:", passing, flush=True)
    (HERE / "results-supplement.json").write_text(json.dumps({"runs": table, "accounts": accounts, "fresh_s_vol": fresh_vol, "fresh_n08": fresh_n08, "n09b_checks": b_checks, "n09b_lead": all(b_checks.values()), "restart_checks": restart_checks, "reshuffle": shuffle, "complements": comp, "complements_passing_first_tests": passing, "qualified": False, "can_place_orders": False}, indent=1), encoding="utf-8")


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=("run", "carry", "score"))
    cli.add_argument("--jobs", type=int, default=3)
    a = cli.parse_args()
    if a.action == "score":
        score()
        return
    Z = lab()
    if a.action == "carry":
        assert Z.CARRY
        Z.run_year_books("supp-carry", carry_books(Z), a.jobs)
    else:
        books = run_books(Z)
        if Z.YEAR == "2023":
            books.update(complement_books(Z))
        Z.run_year_books("supp", books, a.jobs)


if __name__ == "__main__":
    main()
