"""N11's verdict, by PLAN.md's checks, from saved replays only. Writes results.json. Nothing here changes a book or a threshold."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import screen_view as V  # noqa: E402

LOCAL = HERE / "_local"
SIM = HERE.parent
YEARS = V.YEARS
BEST = {"sum": 233275, "worst_day": -6127, "fall": 13.13, "worst_trade": -4559, "2023": -32684, "double": 168672, "without_top5": 106281}
# Published by each study. N09 is its size-by-volatility book; N10.1's PREMIUM_LOCK is its other arm.
FIVE = {"N08": {"2023": -37581, "2024": 76294, "2025": 58647, "2026": 104924, "worst_day": -9720, "fall": 15.08, "worst_trade": -5107, "double": 163688, "account": 212419},
        "N09": {"2023": -37974, "2024": 70317, "2025": 50442, "2026": 108643, "worst_day": -6127, "fall": 15.24, "double": 143250, "account": 212026, "account_with_its_restart": 410542},
        "N09.1": {"2023": -32684, "2024": 76294, "2025": 46738, "2026": 99870, "worst_day": -6127, "fall": 13.13, "worst_trade": -4559, "double": 152165, "account": 384310},
        "N10 retry": {"2023": -32898, "2024": 88805, "2025": 51583, "2026": 125786, "worst_day": -6127, "fall": 13.21, "worst_trade": -4559, "double": 168672, "account": 427440},
        "N10.1 WATCH_FLAT": {"2023": -32898, "2024": 88805, "2025": 51583, "2026": 125786, "worst_day": -6127, "fall": 13.21, "double": 165934, "account": 427452},
        "N10.1 PREMIUM_LOCK": {"2023": -32684, "2024": 80030, "2025": 54122, "2026": 100120, "worst_day": -6127, "fall": 13.13, "double": 128938, "account": 401475}}
N10_ACCOUNT = {"195": 472207, "198": 448743, "199": 427689, "200": 427440, "201": 427191, "202": 427127, "205": 470145, "180": 435812, "220": 433823, "400": 410161}


def book(phase: str, name: str) -> dict:
    return {y: V.load(LOCAL, phase, y, name)["trades"] for y in YEARS}


def summary(rows: dict) -> dict:
    per = {y: V.stats(rows[y]) for y in YEARS}
    nets = sorted((float(t["net_pnl"]) for y in YEARS for t in rows[y]), reverse=True)
    return {"years": {y: round(per[y]["net"]) for y in YEARS}, "sum": round(sum(per[y]["net"] for y in YEARS)), "worst_day": round(min(per[y]["worst_day"] for y in YEARS)), "worst_trade": round(min(per[y]["worst_trade"] for y in YEARS)),
            "fall": round(max(per[y]["fall"] for y in YEARS), 2), "falls": {y: round(per[y]["fall"], 2) for y in YEARS}, "without_top5": round(sum(nets[5:])), "trades": sum(per[y]["n"] for y in YEARS), "wins": sum(n > 0 for n in nets)}


def account(tag: str) -> dict:
    eq = pk = 250000.0
    fall, low = 0.0, eq
    by = {}
    for y in YEARS:
        rows = sorted(V.load(LOCAL, "carry", y, tag)["trades"], key=lambda r: r["exit_time"])
        start = eq
        for t in rows:
            eq += float(t["net_pnl"])
            pk = max(pk, eq)
            low = min(low, eq)
            fall = max(fall, (pk - eq) / pk)
        by[y] = round(eq - start)
    return {"end": round(eq), "by_year": by, "fall": round(fall * 100, 2), "lowest": round(low)}


def weekly(rows: dict) -> dict:
    out = defaultdict(float)
    for y in YEARS:
        for t in rows[y]:
            d = date.fromisoformat(t["exit_time"][:10])
            out[(d - timedelta(days=d.weekday())).isoformat()] += float(t["net_pnl"])
    return out


def paired(a: dict, b: dict, seed: int = 9, blocks: int = 4, draws: int = 20000) -> dict:
    wa, wb = weekly(a), weekly(b)
    weeks = sorted(set(wa) | set(wb))
    d = np.array([wa.get(w, 0.0) - wb.get(w, 0.0) for w in weeks])
    t = float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))) if d.std(ddof=1) > 0 else 0.0
    rng = np.random.default_rng(seed)
    n = len(d)
    starts = rng.integers(0, n - blocks + 1, size=(draws, n // blocks + 1))
    means = np.empty(draws)
    for i in range(draws):
        sample = np.concatenate([d[s:s + blocks] for s in starts[i]])[:n]
        means[i] = sample.sum()
    return {"weeks": n, "weeks_better": int((d > 0).sum()), "weeks_worse": int((d < 0).sum()), "total": round(float(d.sum())), "t": round(t, 2), "bootstrap_95": [round(float(np.percentile(means, 2.5))), round(float(np.percentile(means, 97.5)))]}


def add_stats(rows: dict) -> dict:
    kids = [(y, c) for y in YEARS for t in rows[y] for c in t.get("n10_children") or []]
    nets = sorted((c["net"] for _, c in kids), reverse=True)
    return {"lots": len(kids), "wins": sum(n > 0 for n in nets), "net": round(sum(nets)), "by_year": {y: round(sum(c["net"] for yy, c in kids if yy == y)) for y in YEARS}, "top_three": round(sum(nets[:3])), "worst": round(min(nets, default=0.0))}


def main() -> None:
    n11 = book("panel", "N11")
    me = summary(n11)
    n10 = {y: V.load(LOCAL, "controls", y, "N10")["trades"] for y in YEARS}
    n08 = {y: V.load(LOCAL, "controls", y, "N08")["trades"] for y in YEARS}
    double = summary(book("panel", "DOUBLE"))
    neighbours = {n: summary(book("panel", n)) for n in ("R0.85", "R0.95", "N15", "N25", "X0.75", "X1.25")}
    parts = {n: summary(book("panel", n)) for n in ("NO_STAND", "NO_LOSS", "NO_ADD", "NO_VOL")}
    accounts = {tag: account(tag) for tag in N10_ACCOUNT}
    near = [accounts[t]["end"] for t in ("195", "198", "199", "200", "201", "202", "205")]
    stress = json.loads((HERE / "stress.json").read_text(encoding="utf-8"))
    audits = {y: json.loads((HERE / f"audit-{y}.json").read_text(encoding="utf-8")) for y in YEARS}
    over = json.loads((HERE / "overfit.json").read_text(encoding="utf-8"))
    pbo = json.loads((HERE / "pbo.json").read_text(encoding="utf-8"))
    checks = {
        "1_sum_above_2_33_275": me["sum"] > BEST["sum"],
        "2_worst_day_no_larger_than_6_127": me["worst_day"] >= BEST["worst_day"],
        "3_fall_no_larger_than_13_13": me["fall"] <= BEST["fall"],
        "4_worst_trade_no_larger_than_4_559": me["worst_trade"] >= BEST["worst_trade"],
        "5_2023_no_worse_than_32_684": me["years"]["2023"] >= BEST["2023"],
        "6_double_cost_above_1_68_672": double["sum"] > BEST["double"],
        "7_without_top_five_above_1_06_281": me["without_top5"] > BEST["without_top5"],
        "8_later_years_positive_two_at_or_above_n10": all(me["years"][y] > 0 for y in YEARS[1:]) and sum(me["years"][y] >= FIVE["N10 retry"][y] for y in YEARS[1:]) >= 2,
        "9_plateau": all(s["sum"] > BEST["sum"] and s["worst_day"] >= BEST["worst_day"] for s in neighbours.values()),
        "10_account_every_cost": all(accounts[t]["end"] >= N10_ACCOUNT[t] for t in N10_ACCOUNT) and (max(near) - min(near)) / min(near) <= 0.05 and all(accounts[t]["lowest"] >= 212500 for t in accounts),
        "11_stress": all(stress["check_11"].values()),
        "12_held_lots_untouched": all(a["passed"] and a["checks"].get("held_lots_identical", 0) > 0 for a in audits.values()),
    }
    honest = {"13_rotated_placebo_at_most_0_10": over["placebos"]["check_13_rotated_p_at_most_0_10"], "17_family_overfitting_at_most_0_5": bool(pbo["check_17_family_at_most_0_5"])}
    result = {"schema": "n11_results_v1", "all_data_seen": True, "books_tried_in_n11": sum(len(json.loads((LOCAL / f"keys-{p}-2024.json").read_text(encoding="utf-8"))) for p in ("screen", "screen2", "screen3", "screen4", "screen5", "panel")), "n11": me, "five": FIVE, "double": double, "neighbours": neighbours, "parts": parts, "accounts": accounts,
              "n10_account": N10_ACCOUNT, "near_cost_spread_pct": round((max(near) - min(near)) / min(near) * 100, 2), "checks_a_and_b": checks, "meets_the_owners_bar_on_seen_years": all(checks.values()), "checks_c": honest,
              "earned": add_stats(n11), "paired": {"against_n10_retry": paired(n11, n10), "against_n08": paired(n11, n08)},
              "without_2023": {"n11": sum(me["years"][y] for y in YEARS[1:]), "n10_retry": sum(FIVE["N10 retry"][y] for y in YEARS[1:]), "n08": sum(FIVE["N08"][y] for y in YEARS[1:])},
              "stood_aside": {y: V.load(LOCAL, "panel", y, "N11")["notes"].get("n11_stood_aside", 0) for y in YEARS},
              "audit": {y: audits[y]["checks"] for y in YEARS}}
    (HERE / "results.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("n11", "checks_a_and_b", "meets_the_owners_bar_on_seen_years", "checks_c", "earned", "paired", "without_2023", "stood_aside", "near_cost_spread_pct")}, indent=1))
    print("double", double["sum"], double["worst_day"], "| neighbours", {k: (v["sum"], v["worst_day"], v["fall"]) for k, v in neighbours.items()})


if __name__ == "__main__":
    main()
