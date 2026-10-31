"""O30r analysis -> results.json. Freeze with lab_r.py before any replay; never change it after seeing a result.

Every figure is read from the shipped code's replays at that level. check_book proves each replay before it counts.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
sys.path[:0] = [str(ROOT / "python-engine"), str(ROOT / "docs/research/fno/2026-10-30-earning-power")]

CAPITAL = 250000.0
LOT = 65
MAX_FALL = 0.25
WIPE_OUT = 10000.0
YEARS = ("2025", "2026")
HALVES = {"2025_H1": ("2025", "2025-01-01", "2025-06-30"), "2025_H2": ("2025", "2025-07-01", "2025-12-31"),
          "2026_H1": ("2026", "2026-01-01", "2026-05-31"), "2026_H2": ("2026", "2026-06-01", "2026-10-28")}
STORED = {"LIVE": (-7738, 68176), "BEST": (1343, 92002), "TPB": (34435, 36965), "LIVE+rule": (26230, 79247),
          "BEST+rule": (36068, 57776), "TPB+rule": (82124, 45796)}


def closed(trades: list) -> list:
    return [t for t in trades if t.get("net_pnl") is not None]


def path(trades: list, start: float = CAPITAL) -> dict:
    """The money along one list of trades (equity moves when a trade closes, as the replay's own book does)."""
    rows = sorted(closed(trades), key=lambda t: (t["exit_time"], t["entry_time"]))
    equity = peak = start
    fall = fall_rs = 0.0
    worst_trade = worst_trade_pct = 0.0
    daily: dict = defaultdict(float)
    day_start: dict = {}
    for t in rows:
        d = t["exit_time"][:10]
        day_start.setdefault(d, equity)
        net = float(t["net_pnl"])
        if net < worst_trade:
            worst_trade = net
        if equity > 0:
            worst_trade_pct = min(worst_trade_pct, net / equity)
        equity += net
        daily[d] += net
        peak = max(peak, equity)
        if peak > 0:
            fall = max(fall, (peak - equity) / peak)
        fall_rs = max(fall_rs, peak - equity)
    months: dict = defaultdict(float)
    for d, v in daily.items():
        months[d[:7]] += v
    worst_day = min(daily, key=daily.get) if daily else None
    lots = [int(t.get("entry_qty") or LOT) // LOT for t in rows]
    outlay = [float(t["entry_premium"]) * int(t.get("entry_qty") or LOT) for t in rows]
    return {"net": round(equity - start), "end": round(equity), "fall_pct": round(fall, 4), "fall_rs": round(fall_rs),
            "trades": len(rows), "days": len(daily), "avg_lots": round(statistics.fmean(lots), 2) if lots else 0.0,
            "max_lots": max(lots, default=0), "avg_outlay": round(statistics.fmean(outlay)) if outlay else 0,
            "max_outlay": round(max(outlay, default=0.0)), "worst_trade": round(worst_trade),
            "worst_trade_pct": round(worst_trade_pct, 4), "worst_day": round(daily[worst_day]) if worst_day else 0,
            "worst_day_date": worst_day, "worst_day_pct": round(daily[worst_day] / day_start[worst_day], 4) if worst_day and day_start[worst_day] > 0 else 0.0,
            "best_day": round(max([0.0, *daily.values()])), "green_months": sum(v > 0 for v in months.values()),
            "red_months": sum(v < 0 for v in months.values()), "last_trade": rows[-1]["exit_time"][:10] if rows else None,
            "wiped_out": equity < WIPE_OUT, "daily": dict(daily)}


def pub(s: dict) -> dict:
    return {k: v for k, v in s.items() if k != "daily"}


def negative_halves(alone: dict) -> int:
    n = 0
    for y, first, last in HALVES.values():
        n += sum(v for d, v in alone[y]["daily"].items() if first <= d <= last) < 0
    return n


def check_book(trades: list, level: dict | None, start: float, cost: list | None, cap_per_day: int) -> dict:
    """Recompute what the replay claims. Returns counts of anything that does not hold."""
    from fno_costs import calc_fno_costs
    cfg = (level or {}).get("cfg") or {}
    bad: Counter = Counter()
    bad["unresolved"] = sum(t.get("net_pnl") is None for t in trades)
    rows = sorted(closed(trades), key=lambda t: t["entry_time"])
    per_day: Counter = Counter()
    closes = sorted(((t["exit_time"], float(t["net_pnl"])) for t in rows))
    open_: list = []
    brakes_off = cfg.get("FNO_TWO_STRIKE_LOSSES") == 1_000_000
    risk, stop = cfg.get("FNO_MAX_RISK_PCT"), cfg.get("FNO_STOP_PREMIUM_PCT")
    i = 0
    equity = start
    for t in rows:
        per_day[t["entry_time"][:10]] += 1
        if per_day[t["entry_time"][:10]] > cap_per_day:
            bad["over_day_cap"] += 1
        while i < len(closes) and closes[i][0] <= t["entry_time"]:
            equity += closes[i][1]
            i += 1
        open_ = [o for o in open_ if o[0] > t["entry_time"]]
        qty, prem = int(t["entry_qty"]), float(t["entry_premium"])
        lots = qty // LOT
        if t.get("lots_at_exit") != lots or qty % LOT:
            bad["lots_changed"] += 1
        outlay = qty * prem
        held = sum(o[1] for o in open_)
        if held + outlay > equity + 1.0:
            bad["over_own_cash"] += 1
        extra = float(t.get("extra_cost") or 0.0)
        if cost and abs(extra - (cost[0] + cost[1] * lots) * lots) > 0.02:
            bad["extra_cost_wrong"] += 1
        if not cost and extra:
            bad["extra_cost_wrong"] += 1
        expected = (float(t["exit_premium"]) - prem) * qty - calc_fno_costs(prem, float(t["exit_premium"]), qty) - extra
        if abs(expected - float(t["net_pnl"])) > 1.0:
            bad["net_wrong"] += 1
        if brakes_off and risk and stop:
            want = int(min(equity * risk, 1e12) // (prem * LOT * stop))
            while want > 0 and held + want * prem * LOT > equity:
                want -= 1
            if abs(want - lots) > (1 if abs(equity * risk / (prem * LOT * stop) - round(equity * risk / (prem * LOT * stop))) < 1e-3 else 0):
                bad["lots_not_the_formula"] += 1
        open_.append((t["exit_time"], outlay))
    return {k: v for k, v in bad.items() if v}


def boxes(names: list, by: dict) -> list:
    return [by[n] for n in names if n in by]


def balanced_ok(r: dict) -> bool:
    return (r["y2025"]["net"] > 0 and r["y2026"]["net"] > 0 and r["negative_halves"] <= 1
            and min(r["y2025"]["trades"], r["y2026"]["trades"]) >= 40 and r["carried"]["fall_pct"] <= MAX_FALL
            and not r["carried"]["wiped_out"])


def share_of(level: str) -> float | None:
    head = level.split("|")[0]
    return float(head[1:]) if head.startswith("R") else None


def peak_level(rows: list, year: str) -> tuple:
    r = max(rows, key=lambda x: x[f"y{year}"]["net"])
    return r["level"], r[f"y{year}"]["net"]


def main() -> None:
    import lab_r as L
    Y = L.Y
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    keys = {y: json.loads((HERE / f"_local/keys-{y}.json").read_text(encoding="utf-8")) for y in YEARS}
    evals = HERE / "_local/evals"

    def trades_of(y: str, name: str) -> tuple:
        d = json.loads((evals / f"{keys[y][name]}.json").read_text(encoding="utf-8"))
        return d["trades"], d["notes"]

    levels = {**frozen["levels"], **{f"SENS|{k}": v for k, v in frozen["sensitivities"].items()}}
    rows, checks, starts = [], {}, {}
    for name in frozen["books"]:
        base, rest = name.split("|", 1)
        level, tag = rest.rsplit("|", 1)
        book = frozen["books"][name]
        alone, problems = {}, {}
        cap = int(book["cfg"].get("FNO_MAX_TRADES_PER_DAY", 3))
        for y in YEARS:
            tr, notes = trades_of(y, name)
            alone[y] = path(tr)
            problems[y] = check_book(tr, levels[level], CAPITAL, book.get("cost"), cap)
            starts[f"{name}|{y}"] = notes.get("start_equity")
        row = {"name": name, "base": base, "level": level, "cost": tag, "y2025": pub(alone["2025"]), "y2026": pub(alone["2026"]),
               "negative_halves": negative_halves(alone)}
        if "|SENS|" not in name:
            t26, notes26 = trades_of("2026", f"{name}|carry")
            t25, _ = trades_of("2025", name)
            joined = path(t25 + t26)
            row["carried"] = pub(joined)
            row["carried_y2026"] = pub(path(t26, start=alone["2025"]["end"]))
            problems["2026_carried"] = check_book(t26, levels[level], alone["2025"]["end"], book.get("cost"), cap)
            if abs(float(notes26.get("start_equity", 0.0)) - alone["2025"]["end"]) > 1.0:
                problems["carry_start"] = {"start": notes26.get("start_equity"), "end_2025": alone["2025"]["end"]}
        rows.append(row)
        checks[name] = {k: v for k, v in problems.items() if v}
    by = {r["name"]: r for r in rows}
    main_rows = [r for r in rows if r["cost"] == "COST"]

    # --- correctness ---------------------------------------------------------------------------------------------
    parity = {b: {"stored": STORED[b], "now": (by[f"{b}|SHIPPED|AS"]["y2025"]["net"], by[f"{b}|SHIPPED|AS"]["y2026"]["net"])}
              for b in L.AS_BASES}
    import analyze_s as A
    base_raw, _ = A.load()
    t2 = {}
    for y in YEARS:
        raw = json.loads((ROOT / f"docs/research/fno/2026-10-30-earning-power/_local/results-t2-raw-{y}.json").read_text(encoding="utf-8"))
        t2[y] = {n: A.prep(raw["trades"][k]) for n, k in raw["books"].items()}
    sim_check = {}
    for r in L.SHARES:
        lv = f"{L.share_name(r)}|OFF"
        for b, source in (("LIVE", lambda y: base_raw[y]["LIVE"]), ("BEST+rule", lambda y: t2[y]["BEST|skip"]), ("TPB+rule", lambda y: t2[y]["TPB|skip"])):
            for y in YEARS:
                s = A.sim(source(y), ("risk", r))
                e = by[f"{b}|{lv}|AS"][f"y{y}"]
                sim_check[f"{b}|{lv}|{y}"] = {"exact": e["net"], "simulator": s["net"], "exact_trades": e["trades"], "sim_trades": s["trades"]}

    # --- the frozen answers ----------------------------------------------------------------------------------------
    spectrum = [r for r in main_rows if "|SENS|" not in r["name"]]
    balanced = sorted((r for r in spectrum if balanced_ok(r)), key=lambda r: -min(r["y2025"]["net"], r["y2026"]["net"]))
    most = max(spectrum, key=lambda r: r["carried"]["end"])
    earning = [r for r in spectrum if r["y2025"]["net"] > 0 and r["y2026"]["net"] > 0]
    lowest = min(earning, key=lambda r: r["carried"]["fall_pct"]) if earning else None
    peaks = {}
    for b in L.BASES:
        off = [r for r in spectrum if r["base"] == b and r["level"].endswith("|OFF")]
        p25, p26 = peak_level(off, "2025"), peak_level(off, "2026")
        s25, s26 = share_of(p25[0]), share_of(p26[0])
        peaks[b] = {"peak_2025": p25, "peak_2026": p26, "margin_share": min(s25, s26) / 2}
    pick = balanced[0] if balanced else None
    if pick and share_of(pick["level"]) is not None:
        pick_share = share_of(pick["level"])
    else:
        pick_share = None
    cross = {}
    for a, b in (("2025", "2026"), ("2026", "2025")):
        ok = [r for r in spectrum if r[f"y{a}"]["net"] > 0 and r[f"y{a}"]["trades"] >= 40 and r[f"y{a}"]["fall_pct"] <= MAX_FALL]
        chosen = max(ok, key=lambda r: r[f"y{a}"]["net"]) if ok else None
        if chosen:
            cross[f"chosen_on_{a}"] = {"name": chosen["name"], f"on_{a}": chosen[f"y{a}"], f"on_{b}": chosen[f"y{b}"],
                                       "pick_on_other_year": by[pick["name"]][f"y{b}"] if pick else None}

    # --- random books under the same shares (simulator, as O30s; brakes off, Rs 200 per lot) -------------------------
    nulls = [n for n in base_raw["2025"] if n.startswith("NULL")]
    control = {}
    for r in L.SHARES:
        sims = {y: [A.sim(base_raw[y][n], ("risk", r), stress=200.0) for n in nulls] for y in YEARS}
        control[L.share_name(r)] = {y: {"median_net": round(statistics.median(s["net"] for s in sims[y])),
                                        "positive": sum(s["net"] > 0 for s in sims[y]),
                                        "end_under_10k": sum(s["end"] < WIPE_OUT for s in sims[y])} for y in YEARS}

    bad = {k: v for k, v in checks.items() if v}
    out = {"schema": "o30r_results_v1", "freeze_sha256": A.hashlib_sha(HERE / "freeze.json"), "rule": frozen["rule"],
           "correctness": {"replays_checked": sum(2 + ("|SENS|" not in n) for n in frozen["books"]), "problems": bad,
                           "shipped_parity": parity, "simulator_vs_exact": sim_check},
           "pick_balanced": pick, "balanced_top": balanced[:15], "balanced_count": len(balanced), "most_money": most,
           "lowest_risk": lowest, "peaks": peaks, "pick_share": pick_share, "cross_year": cross, "random_control": control,
           "rows": rows, "qualification": "NOT_ASSESSED", "can_place_orders": False}
    tmp = HERE / "results.json.part"
    tmp.write_text(json.dumps(out, indent=1), encoding="utf-8")
    tmp.replace(HERE / "results.json")
    print("checked", out["correctness"]["replays_checked"], "replays; with problems:", len(bad))
    print("parity", parity)
    print("balanced", len(balanced), "pick", pick["name"] if pick else None, {k: pick[k]["net"] for k in ("y2025", "y2026", "carried")} if pick else None)
    print("most", most["name"], most["carried"]["end"], most["carried"]["fall_pct"])
    print("lowest", lowest["name"] if lowest else None)
    print("peaks", peaks)


if __name__ == "__main__":
    main()
