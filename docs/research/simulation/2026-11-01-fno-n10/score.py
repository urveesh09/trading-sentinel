"""N10's verdict, by PLAN.md's checks, from saved replays only. Writes results.json. Nothing here changes a book or a threshold."""
from __future__ import annotations

import itertools
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "2026-11-01-fno-n091"), str(HERE.parent / "2026-11-01-fno-n09")]
LOCAL = HERE / "_local"
N09 = HERE.parent / "2026-11-01-fno-n09" / "_local"
N091 = HERE.parent / "2026-11-01-fno-n091" / "_local"
YEARS = ("2023", "2024", "2025", "2026")
CAPITAL = 250000.0
CUSHION_BOOKS = ("EARN_WC", "EARN_WVC", "LADDER_WC", "HYBRID_C")
# Published by N08 and N09.1; the score asserts these figures come back from their saved trades.
REFERENCE = {"n08_sum": 202284, "cushion_sum": 190218, "cushion_worst_day": -6127, "cushion_fall": 13.13, "cushion_2023": -32684, "cushion_years": {"2024": 76294, "2025": 46738, "2026": 99870},
             "cushion_account": 384310, "cushion_double": 152165}


def stats(trades: list, capital: float = CAPITAL) -> dict:
    equity = peak = capital
    fall = 0.0
    daily = defaultdict(float)
    for t in sorted(trades, key=lambda r: r["exit_time"]):
        net = float(t["net_pnl"])
        equity += net
        peak = max(peak, equity)
        fall = max(fall, (peak - equity) / peak)
        daily[t["exit_time"][:10]] += net
    nets = sorted((float(t["net_pnl"]) for t in trades), reverse=True)
    return {"net": equity - capital, "end": equity, "trades": len(trades), "wins": sum(n > 0 for n in nets), "fall_pct": fall * 100, "worst_trade": min(nets, default=0.0),
            "worst_day": min(daily.values(), default=0.0), "best_trade": max(nets, default=0.0)}


def whole(by_year: dict) -> dict:
    return {"net": sum(s["net"] for s in by_year.values()), "worst_day": min(s["worst_day"] for s in by_year.values()), "worst_trade": min(s["worst_trade"] for s in by_year.values()),
            "fall_pct": max(s["fall_pct"] for s in by_year.values()), "trades": sum(s["trades"] for s in by_year.values())}


def without_best(by_year_trades: dict, count: int = 5) -> float:
    nets = sorted((float(t["net_pnl"]) for rows in by_year_trades.values() for t in rows), reverse=True)
    return sum(nets[count:])


def add_stats(trades: list) -> dict:
    """What the earned lots themselves made, and how many trades earned one."""
    children = [c for t in trades for c in t.get("n10_children") or []]
    by_reason = defaultdict(lambda: [0, 0.0])
    for c in children:
        key = "with_first" if c["reason"].startswith("with_first") else c["reason"]
        by_reason[key][0] += 1
        by_reason[key][1] += c["net"]
    return {"lots_earned": len(children), "trades_with_an_earned_lot": sum(bool(t.get("n10_children")) for t in trades), "of_trades": len(trades), "earned_net": round(sum(c["net"] for c in children), 2),
            "earned_wins": sum(c["net"] > 0 for c in children), "by_exit": {k: [v[0], round(v[1], 2)] for k, v in sorted(by_reason.items())}}


def checks(name: str, fresh: dict, trades: dict, account: float, double_sum: float, neighbours: dict, ref_without5: float) -> dict:
    """PLAN.md's nine checks. Each entry is a bare true or false, so that no reading can soften one afterwards."""
    w = whole(fresh)
    r = REFERENCE
    years = {y: fresh[y]["net"] for y in ("2024", "2025", "2026")}
    out = {
        "1_sum_above_n08": w["net"] > r["n08_sum"],
        "2_worst_day_no_larger": w["worst_day"] >= r["cushion_worst_day"],
        "3_fall_no_larger": round(w["fall_pct"], 2) <= r["cushion_fall"],
        "4_2023_no_worse": fresh["2023"]["net"] >= r["cushion_2023"],
        "5_years_positive_two_at_or_above": all(v > 0 for v in years.values()) and sum(years[y] >= r["cushion_years"][y] for y in years) >= 2,
        "6_account_at_or_above": account >= r["cushion_account"],
        "7_double_cost_at_or_above": double_sum >= r["cushion_double"],
        "8_plateau": all(neighbours[x] > r["cushion_sum"] for x in ("0.75", "1.25")),
        "9_without_top_five": without_best(trades) >= ref_without5,
    }
    return {"book": name, "checks": out, "passes": all(out.values()), "sum": w["net"], "worst_day": w["worst_day"], "fall_pct": w["fall_pct"], "account": account, "double": double_sum,
            "neighbours": neighbours, "without_top_five": without_best(trades)}


# ---- saved replays ----------------------------------------------------------------------------------------------------


def keys(phase: str, year: str) -> dict:
    return json.loads((LOCAL / f"keys-{phase}-{year}.json").read_text(encoding="utf-8"))


def trades_of(phase: str, year: str, name: str) -> list:
    return json.loads((LOCAL / "evals" / f"{keys(phase, year)[name]}.json").read_text(encoding="utf-8"))["trades"]


def eval_of(phase: str, year: str, name: str) -> dict:
    return json.loads((LOCAL / "evals" / f"{keys(phase, year)[name]}.json").read_text(encoding="utf-8"))


def n08_trades(year: str) -> list:
    key = json.loads((N09 / f"keys-diag-{year}.json").read_text(encoding="utf-8"))["N08"]
    return json.loads((N09 / f"evals-{year}" / f"{key}.json").read_text(encoding="utf-8"))["trades"]


def n091_trades(phase: str, year: str, name: str) -> list:
    key = json.loads((N091 / f"keys-{phase}-{year}.json").read_text(encoding="utf-8"))[name]
    return json.loads((N091 / "evals" / f"{key}.json").read_text(encoding="utf-8"))["trades"]


# ---- reported, not gates ----------------------------------------------------------------------------------------------


def all_weeks() -> list:
    weeks = []
    for y in YEARS:
        day, end = date(int(y), 1, 1), date(int(y), 10, 28) if y == "2026" else date(int(y), 12, 31)
        while day <= end:
            iso = tuple(day.isocalendar()[:2])
            if iso not in weeks:
                weeks.append(iso)
            day += timedelta(days=1)
    return weeks


def weekly_vector(trades: list, weeks: list) -> np.ndarray:
    net = defaultdict(float)
    for t in trades:
        net[tuple(date.fromisoformat(t["exit_time"][:10]).isocalendar()[:2])] += float(t["net_pnl"])
    return np.array([net[w] for w in weeks])


def paired(candidate: list, baseline: list, weeks: list) -> dict:
    delta = weekly_vector(candidate, weeks) - weekly_vector(baseline, weeks)
    rng = np.random.default_rng(110901)
    drawn = [float(delta[np.concatenate([(np.arange(4) + i) % len(delta) for i in rng.integers(0, len(delta), math.ceil(len(delta) / 4))])[:len(delta)]].sum()) for _ in range(4096)]
    se = float(delta.std(ddof=1) / math.sqrt(len(delta)))
    return {"total_delta": round(float(delta.sum()), 2), "paired_t": round(float(delta.mean() / se), 3) if se else None, "bootstrap_95": [round(float(v)) for v in np.percentile(drawn, [2.5, 97.5])]}


def first_lot_same(earn: list, one: list) -> dict:
    """Wherever a trade is in both books, its first lot must have lived the same life."""
    def key(t):
        return (t["entry_time"], t["tradingsymbol"])
    a, b = {key(t): t for t in earn}, {key(t): t for t in one}
    shared = a.keys() & b.keys()
    same = [k for k in shared if (a[k]["exit_time"], a[k]["exit_premium"], a[k]["exit_reason"]) == (b[k]["exit_time"], b[k]["exit_premium"], b[k]["exit_reason"])]
    return {"shared": len(shared), "same_exit": len(same), "only_in_earn": len(a.keys() - b.keys()), "only_in_one": len(b.keys() - a.keys())}


def stress(streams: dict) -> dict:
    """All 256 orderings of whole years, on N09.1's causal proxy, brakes-off trades. A proxy: fixed admissions, no regenerated market decisions."""
    import n091_lab_free as S
    out = {}
    for name, stream in streams.items():
        rows = {}
        for rule in ("NONE", "CUSHION"):
            ends = sorted(S.simulate(seq, stream, rule)["end"] for seq in itertools.product(YEARS, repeat=4))
            rows[rule] = {"worst_end": round(ends[0]), "median_end": round((ends[127] + ends[128]) / 2), "best_end": round(ends[-1]), "below_start": sum(e < CAPITAL for e in ends)}
        out[name] = rows
    return out


def reserve_stream(trades: list) -> list:
    """Each trade with the full premium it could lose, first lot and earned lots."""
    from fno_costs import calc_fno_costs

    def reserve(premium, qty, lots):
        return premium * qty + calc_fno_costs(premium, premium, qty) + (200.0 + 5.0 * lots) * lots

    rows = []
    for t in trades:
        lots = t["entry_qty"] // 65
        need = reserve(t["entry_premium"], t["entry_qty"], lots) + sum(reserve(c["ask"], c["qty"], 1) for c in t.get("n10_children") or [])
        rows.append({**t, "full_reserve": need})
    return rows


def main() -> None:
    from analyze_panel import cscv
    weeks = all_weeks()
    primary = ("EARN_N", "EARN_W", "EARN_WV", *CUSHION_BOOKS)
    rows = {name: {y: trades_of("panel", y, name) for y in YEARS} for name in primary}
    rows["ONE"] = {y: trades_of("controls", y, "ONE") for y in YEARS}
    rows["N08"] = {y: n08_trades(y) for y in YEARS}
    rows["CUSHION"] = {y: n091_trades("primary", y, "CUSHION") for y in YEARS}
    fresh = {name: {y: stats(rows[name][y]) for y in YEARS} for name in rows}

    # The two reference books must come back as published, or nothing below means anything.
    assert round(whole(fresh["N08"])["net"]) == REFERENCE["n08_sum"]
    c = whole(fresh["CUSHION"])
    assert round(c["net"]) == REFERENCE["cushion_sum"] and round(c["worst_day"]) == REFERENCE["cushion_worst_day"] and round(c["fall_pct"], 2) == REFERENCE["cushion_fall"]
    assert round(fresh["CUSHION"]["2023"]["net"]) == REFERENCE["cushion_2023"]
    account_ref = CAPITAL + sum(float(t["net_pnl"]) for y in YEARS for t in n091_trades("carry", y, "CUSHION"))
    assert round(account_ref) == REFERENCE["cushion_account"]
    double_ref = sum(float(t["net_pnl"]) for y in YEARS for t in n091_trades("costs", y, "CUSHION|double"))
    assert round(double_ref) == REFERENCE["cushion_double"]
    ref_without5 = without_best(rows["CUSHION"])

    verdicts = {}
    for name in CUSHION_BOOKS:
        account = CAPITAL + sum(float(t["net_pnl"]) for y in YEARS for t in trades_of("carry", y, name))
        double = sum(float(t["net_pnl"]) for y in YEARS for t in trades_of("costs", y, f"COST|{name}|double"))
        near = {x: sum(float(t["net_pnl"]) for y in YEARS for t in trades_of("panel", y, f"{name}@{x}")) for x in ("0.75", "1.25")}
        verdicts[name] = checks(name, fresh[name], rows[name], account, double, near, ref_without5)
    passing = [v for v in verdicts.values() if v["passes"]]
    pick = max(passing, key=lambda v: v["sum"])["book"] if passing else None

    # Reported, not gates.
    flat = {n: [t for y in YEARS for t in rows[n][y]] for n in rows}
    panel_names = [*primary, *(f"{n}@{x}" for n in CUSHION_BOOKS for x in ("0.75", "1.25"))]
    panel_flat = {n: flat[n] if n in flat else [t for y in YEARS for t in trades_of("panel", y, n)] for n in panel_names}
    matrix = np.column_stack([weekly_vector(v, weeks) for v in (*panel_flat.values(), flat["N08"], flat["CUSHION"], flat["ONE"])])
    names = [*panel_flat, "N08", "CUSHION", "ONE"]
    pbo = cscv(matrix, blocks=16)
    pbo["picks"] = {names[int(k)]: v for k, v in pbo["picks"].items()}
    nobrake = {n: {y: stats(trades_of("panel", y, f"NOBRAKE|{n}")) for y in YEARS} for n in ("N08", "ONE", "EARN_W", "EARN_WV")}
    random_delta = {}
    for y in YEARS:
        base = [sum(float(t["net_pnl"]) for t in trades_of("random", y, f"RANDOM|{i:02d}|BASE")) for i in range(10)]
        earned = [sum(float(t["net_pnl"]) for t in trades_of("random", y, f"RANDOM|{i:02d}|EARN")) for i in range(10)]
        random_delta[y] = {"base_median": round(statistics.median(base)), "earn_median": round(statistics.median(earned)), "helped": sum(e > b for b, e in zip(base, earned)), "books": 10,
                           "median_change": round(statistics.median(e - b for b, e in zip(base, earned)))}
    streams = {n: {y: reserve_stream(trades_of("panel", y, f"NOBRAKE|{n}")) for y in YEARS} for n in ("N08", "ONE", "EARN_W", "EARN_WV")}
    result = {
        "schema": "n10_results_v1", "all_data_seen": True, "reference": REFERENCE,
        "fresh": fresh, "aggregates": {n: whole(v) for n, v in fresh.items()}, "verdicts": verdicts, "pick": pick,
        "earned_lots": {n: {y: add_stats(rows[n][y]) for y in YEARS} for n in primary},
        "refusals": {n: {y: {k: v for k, v in eval_of("panel", y, n)["notes"].items() if k.startswith("n10_")} for y in YEARS} for n in primary},
        "account": {n: {"end": verdicts[n]["account"], "by_year": {y: round(stats(trades_of("carry", y, n))["net"]) for y in YEARS}, "fall_pct": round(stats([t for y in YEARS for t in trades_of("carry", y, n)])["fall_pct"], 2)} for n in CUSHION_BOOKS},
        "costs": {n: {tag: {y: round(sum(float(t["net_pnl"]) for t in trades_of("costs", y, f"COST|{n}|{tag}"))) for y in YEARS} for tag in ("none", "double")} for n in CUSHION_BOOKS},
        "neighbours": {n: {x: {y: round(sum(float(t["net_pnl"]) for t in trades_of("panel", y, f"{n}@{x}"))) for y in YEARS} for x in ("0.75", "1.25")} for n in CUSHION_BOOKS},
        "nobrake": nobrake, "random_control": random_delta,
        "paired": {n: {"against_n08": paired(flat[n], flat["N08"], weeks), "against_cushion": paired(flat[n], flat["CUSHION"], weeks)} for n in primary},
        "first_lot_same": {y: first_lot_same(rows["EARN_W"][y], rows["ONE"][y]) for y in YEARS},
        "pbo": {**pbo, "book_names": names}, "stress_256_orderings": stress(streams),
    }
    (HERE / "results.json").write_text(json.dumps(result, indent=1, allow_nan=False, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"pick": pick, "aggregates": result["aggregates"], "verdicts": verdicts, "pbo": pbo["pbo"], "random": random_delta}, indent=1, default=str))


if __name__ == "__main__":
    main()
