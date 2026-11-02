"""O30s analysis -> results.json: the RAW one-lot trades of lab_s.py, sized and braked on Rs 2.5 lakh.

Freeze this file with lab_s.py before any replay; never change it after seeing a result.

The simulator walks the trades in time order. Before each entry it settles the closed trades, applies the brakes, sizes
from the money known at that moment, checks own cash (no margin: premium outlay of everything open <= the money), and
books lots x the trade's one-lot net. Shortcut: a dropped trade cannot release a later trade it had blocked inside the
replay; the shipped sizing's parity with the stored replays and the exact replay of the pick measure that.
"""
from __future__ import annotations

import heapq
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())

CAPITAL = 250000.0
LOT = 65
STOP_PCT = 0.25
STRESS = 200.0
MAX_FALL = 0.25
GOAL = 200000.0
YEARS = ("2025", "2026")
HALVES = {"2025_H1": ("2025", "2025-01-01", "2025-06-30"), "2025_H2": ("2025", "2025-07-01", "2025-12-31"),
          "2026_H1": ("2026", "2026-01-01", "2026-05-31"), "2026_H2": ("2026", "2026-06-01", "2026-10-28")}
GRID = {"fixed_lots": [1, 2, 3, 4, 5, 6, 8, 10, 12, 15], "risk_share_of_money": [0.01, 0.02, 0.03, 0.04, 0.05, 0.075, 0.10],
        "brakes": ["NONE", "SHIPPED", "THROTTLE", "THROTTLE+DAY"], "half_size_when_stretched": [False, True],
        "stretch_limit": 0.5, "day_cap": 3, "capital": CAPITAL, "stress_per_lot_per_trade": STRESS,
        "max_fall": MAX_FALL, "bootstrap": {"paths": 5000, "weeks": 52, "seed": 20261030},
        "derived_sleeves": {"S4": ["SHIPPED", "OR20", "EFF", "TPB"], "S_LIVE+TPB": ["LIVE", "TPB"]}}
SIZES = [("fixed", n) for n in GRID["fixed_lots"]] + [("risk", p) for p in GRID["risk_share_of_money"]]
SHOWN = ("LIVE", "BEST", "TPB", "UNION")


def prep(trades: list, sleeve: int = 0) -> list:
    rows = []
    for t in trades:
        if t.get("net_pnl") is None:
            continue
        d = t["entry_time"][:10]
        iso = date.fromisoformat(d).isocalendar()
        rows.append((t["entry_time"], t["exit_time"], float(t.get("first_premium") or t["entry_premium"]),
                     float(t["net_pnl"]), int(t.get("lots_at_exit") or 1), t.get("stretch"), d, (iso[0], iso[1]),
                     d[:7], sleeve))
    return sorted(rows)


def in_window(rows: list, first: str, last: str) -> list:
    return [r for r in rows if first <= r[6] <= last]


def sim(rows: list, rule: tuple, brakes: str = "NONE", stress: float = 0.0, half: bool = False,
        capital: float = CAPITAL, day_cap: int = GRID["day_cap"], reserve: int = 1) -> dict:
    """rule: ("fixed", lots) | ("risk", share of the money lost at the premium backstop) | ("shipped",)."""
    equity = peak = capital
    open_: list = []
    cash_out = 0.0
    day = week = month = None
    day_pnl = week_pnl = month_pnl = 0.0
    losses_today = consec = wins_sum = loss_sum = closed = 0
    last_loss_day = None
    per_day: Counter = Counter()
    daily: dict = defaultdict(float)
    max_dd = max_dd_rs = 0.0
    taken = lots_sum = max_lots = 0
    outlay_sum = max_outlay = 0.0
    no_cash = halted = 0
    next_day_pause = None

    def settle(until: str) -> None:
        nonlocal equity, peak, cash_out, day_pnl, week_pnl, month_pnl, losses_today, consec, last_loss_day
        nonlocal wins_sum, loss_sum, closed, max_dd, max_dd_rs
        while open_ and open_[0][0] <= until:
            _, _, pnl, outlay, d = heapq.heappop(open_)
            equity += pnl
            cash_out -= outlay
            day_pnl += pnl
            week_pnl += pnl
            month_pnl += pnl
            closed += 1
            if pnl < 0:
                losses_today += 1
                consec += 1
                last_loss_day = d
                loss_sum -= pnl
            else:
                consec = 0
                wins_sum += pnl
            peak = max(peak, equity)
            max_dd_rs = max(max_dd_rs, peak - equity)
            max_dd = max(max_dd, (peak - equity) / peak if peak > 0 else 1.0)

    for i, r in enumerate(rows):
        entry_t, exit_t, prem, net, lots_exit, stretch, d, wk, mo, sleeve = r
        settle(entry_t)
        if d != day:
            day, day_pnl, losses_today = d, 0.0, 0
        if wk != week:
            week, week_pnl = wk, 0.0
        if mo != month:
            month, month_pnl = mo, 0.0
        if per_day[(sleeve, d)] >= day_cap:
            continue
        dd_now = (peak - equity) / peak if peak > 0 else 1.0
        mult = 1.0
        if brakes == "SHIPPED":
            pool = capital
            stop = (day_pnl <= -0.03 * pool or week_pnl <= -0.06 * pool or month_pnl <= -0.10 * pool
                    or equity < 0.85 * pool or losses_today >= 2)
            if consec >= 6 and last_loss_day is not None:
                gap = (date.fromisoformat(d) - date.fromisoformat(last_loss_day)).days
                stop = stop or gap <= 1
            if stop:
                halted += 1
                continue
            pf = (wins_sum / loss_sum) if loss_sum > 0 else None
            if dd_now >= 0.08:
                mult = 0.25
            elif dd_now >= 0.04:
                mult = 0.5
            elif dd_now <= 0.02 and pf is not None and closed >= 40 and pf >= 1.5:
                mult = 1.5
            elif dd_now <= 0.02 and pf is not None and closed >= 20 and pf >= 1.3:
                mult = 1.25
        elif brakes in ("THROTTLE", "THROTTLE+DAY"):
            if brakes == "THROTTLE+DAY" and (losses_today >= 2 or day_pnl <= -0.03 * equity):
                halted += 1
                continue
            mult = 0.25 if dd_now >= 0.20 else 0.5 if dd_now >= 0.10 else 1.0
        per_lot = prem * LOT
        if rule[0] == "fixed":
            lots = rule[1]
        elif rule[0] == "risk":
            lots = int(rule[1] * equity // (per_lot * STOP_PCT))
        else:                                                   # the shipped sizing, exactly as fno_entry_plan
            ceiling = 3 if mult > 1.0 else 2
            lots = min(int(min(equity * 0.02 * mult, 6250.0 * mult) // (per_lot * STOP_PCT)), ceiling)
            if lots < 1 and 0.0 < mult < 1.0:
                lots = min(int(min(equity * 0.02, 6250.0) // (per_lot * STOP_PCT)), 1)
            while lots > 0 and cash_out + lots * per_lot > 0.15 * equity:
                lots -= 1
        if rule[0] != "shipped" and mult != 1.0 and lots >= 1:
            lots = max(1, int(lots * mult))
        if half and stretch is not None and stretch >= GRID["stretch_limit"] and lots >= 1:
            lots = max(1, lots // 2)
        room = equity - cash_out
        if lots * per_lot * reserve > room:
            lots = int(room // (per_lot * reserve))
        if lots < 1:
            no_cash += 1
            continue
        pnl = lots * net - stress * lots * lots_exit
        outlay = lots * per_lot
        per_day[(sleeve, d)] += 1
        daily[d] += pnl
        heapq.heappush(open_, (exit_t, i, pnl, outlay, d))
        cash_out += outlay
        taken += 1
        lots_sum += lots
        max_lots = max(max_lots, lots)
        outlay_sum += outlay
        max_outlay = max(max_outlay, outlay)
    settle("9999")
    weeks, months = defaultdict(float), defaultdict(float)
    for d, v in daily.items():
        iso = date.fromisoformat(d).isocalendar()
        weeks[(iso[0], iso[1])] += v
        months[d[:7]] += v
    return {"net": round(equity - capital), "end": round(equity), "fall_pct": round(max_dd, 4), "fall_rs": round(max_dd_rs),
            "trades": taken, "days": len(daily), "avg_lots": round(lots_sum / taken, 2) if taken else 0.0,
            "max_lots": max_lots, "avg_outlay": round(outlay_sum / taken) if taken else 0, "max_outlay": round(max_outlay),
            "worst_day": round(min([0.0, *daily.values()])), "best_day": round(max([0.0, *daily.values()])),
            "worst_week": round(min([0.0, *weeks.values()])), "worst_month": round(min([0.0, *months.values()])),
            "green_months": sum(v > 0 for v in months.values()), "red_months": sum(v < 0 for v in months.values()),
            "no_cash": no_cash, "halted": halted, "daily": dict(daily)}


def _pub(s: dict) -> dict:
    return {k: v for k, v in s.items() if k != "daily"}


def halves_negative(year_sims: dict) -> int:
    n = 0
    for year, first, last in HALVES.values():
        n += sum(v for d, v in year_sims[year]["daily"].items() if first <= d <= last) < 0
    return n


def boot(rows_by_year: dict, lots: list, cfg: dict = GRID["bootstrap"], stress: float = STRESS,
         capital: float = CAPITAL) -> dict:
    """One-year paths drawn week by week from both years at one lot, scaled by lots (no brakes, no cash limit)."""
    weeks = defaultdict(lambda: defaultdict(float))
    for rows in rows_by_year.values():
        for r in rows:
            weeks[r[7]][r[6]] += r[3] - stress * r[4]
    blocks = []
    for wk in sorted(weeks):
        days = [weeks[wk][d] for d in sorted(weeks[wk])]
        blocks.append((days + [0.0] * 5)[:5])
    blocks = np.array(blocks)
    rng = np.random.default_rng(cfg["seed"])
    picks = rng.integers(0, len(blocks), size=(cfg["paths"], cfg["weeks"]))
    unit = np.cumsum(blocks[picks].reshape(cfg["paths"], -1), axis=1)
    out = {}
    for n in lots:
        path = capital + n * unit
        peak = np.maximum.accumulate(np.maximum(path, capital), axis=1)
        fall = ((peak - path) / peak).max(axis=1)
        net = path[:, -1] - capital
        out[str(n)] = {"median_net": round(float(np.median(net))), "p5_net": round(float(np.percentile(net, 5))),
                       "p95_net": round(float(np.percentile(net, 95))), "chance_year_loses": round(float((net < 0).mean()), 3),
                       "chance_fall_25pct": round(float((fall >= 0.25).mean()), 3),
                       "chance_fall_50pct": round(float((fall >= 0.50).mean()), 3),
                       "chance_2_lakh": round(float((net >= GOAL).mean()), 3)}
    return out


def kelly(rows_by_year: dict, stress: float = STRESS, capital: float = CAPITAL) -> dict:
    """Lots at full Kelly from weekly one-lot P&L: money x mean / variance, per year and both (an upper limit, not a plan)."""
    out = {}
    for label, parts in {**{y: [rows_by_year[y]] for y in YEARS}, "both": list(rows_by_year.values())}.items():
        weeks: dict = defaultdict(float)
        for rows in parts:
            for r in rows:
                weeks[r[7]] += r[3] - stress * r[4]
        v = list(weeks.values())
        if len(v) >= 2 and statistics.pvariance(v) > 0:
            out[label] = round(capital * statistics.fmean(v) / statistics.pvariance(v), 1)
    return out


def load() -> tuple[dict, str]:
    sys.path.insert(0, str(HERE))
    sha = hashlib_sha(HERE / "freeze.json")
    trades: dict = {}
    for y in YEARS:
        raw = json.loads((HERE / f"_local/results-raw-{y}.json").read_text(encoding="utf-8"))
        assert raw["freeze_sha256"] == sha, "replays are not from this freeze"
        trades[y] = {n: prep(raw["trades"][k]) for n, k in raw["books"].items()}
        for name, parts in GRID["derived_sleeves"].items():
            trades[y][name] = sorted(r[:9] + (i,) for i, p in enumerate(parts) for r in trades[y][p])
    return trades, sha


def hashlib_sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parity(trades: dict) -> dict:
    """The simulator's shipped sizing and brakes against the stored shipped replays (rupees, per year)."""
    stored_dir = ROOT / "docs/research/fno/2026-10-30-micro-adaptation/_local"
    out = {}
    for name, ref in (("LIVE", "REF|LIVE"), ("BEST", "REF|BEST"), ("TPB", "REF|TPB")):
        for y in YEARS:
            path = stored_dir / f"results-raw-{y}.json"
            if not path.is_file():
                continue
            raw = json.loads(path.read_text(encoding="utf-8"))
            stored = [t for t in raw["trades"][raw["books"][ref]] if t.get("net_pnl") is not None]
            s = sim(trades[y][name], ("shipped",), "SHIPPED")
            out[f"{name}_{y}"] = {"stored_net": round(sum(float(t["net_pnl"]) for t in stored)), "simulated_net": s["net"],
                                  "stored_trades": len(stored), "simulated_trades": s["trades"]}
    return out


def main() -> None:
    trades, sha = load()
    books = [n for n in trades["2025"] if not n.startswith("NULL")]
    nulls = [n for n in trades["2025"] if n.startswith("NULL")]
    rows = []
    medians: dict = {}
    reserve_for = lambda n: 3 if "ADD2" in n else 2 if ("ADD1" in n or "HOUSE" in n) else 1   # noqa: E731
    joined = {n: sorted(trades["2025"][n] + trades["2026"][n]) for n in books}
    for rule in SIZES:
        for brakes in GRID["brakes"]:
            for half in GRID["half_size_when_stretched"]:
                key = (rule, brakes, half)
                medians[key] = {y: statistics.median(sim(trades[y][n], rule, brakes, STRESS, half)["net"] for n in nulls)
                                for y in YEARS}
                for name in books:
                    res = reserve_for(name)
                    years = {y: sim(trades[y][name], rule, brakes, STRESS, half, reserve=res) for y in YEARS}
                    both = sim(joined[name], rule, brakes, STRESS, half, reserve=res)
                    neg = halves_negative(years)
                    passed = (years["2025"]["net"] > 0 and years["2026"]["net"] > 0 and neg <= 1
                              and both["fall_pct"] <= MAX_FALL
                              and min(years[y]["trades"] for y in YEARS) >= 40
                              and all(years[y]["net"] > medians[key][y] for y in YEARS))
                    rows.append({"book": name, "rule": list(rule), "brakes": brakes, "half": half, "pass": passed,
                                 "negative_halves": neg, "y2025": _pub(years["2025"]), "y2026": _pub(years["2026"]),
                                 "both": _pub(both), "random_median": medians[key]})
    (HERE / "_local").mkdir(exist_ok=True)
    (HERE / "_local/all-combos.json").write_text(json.dumps(rows), encoding="utf-8")
    passes = sorted((r for r in rows if r["pass"]), key=lambda r: -min(r["y2025"]["net"], r["y2026"]["net"]))
    pick = passes[0] if passes else None

    # --- cross-year: choose on one year alone, score on the other -------------------------------------------------
    cross = {}
    for a, b in (("2025", "2026"), ("2026", "2025")):
        field_a, field_b = f"y{a}", f"y{b}"
        ok = [r for r in rows if r[field_a]["net"] > 0 and r[field_a]["fall_pct"] <= MAX_FALL and r[field_a]["trades"] >= 40]
        chosen = max(ok, key=lambda r: r[field_a]["net"]) if ok else None
        if chosen:
            same = {n: next(r for r in rows if r["book"] == n and r["rule"] == chosen["rule"]
                            and r["brakes"] == chosen["brakes"] and r["half"] == chosen["half"]) for n in ("TPB", "BEST")}
            cross[f"chosen_on_{a}"] = {"book": chosen["book"], "rule": chosen["rule"], "brakes": chosen["brakes"],
                                       "half": chosen["half"], "on_chosen_year": chosen[field_a], "on_other_year": chosen[field_b],
                                       "TPB_same_size_other_year": same["TPB"][field_b],
                                       "BEST_same_size_other_year": same["BEST"][field_b]}

    # --- the three entries at one lot, under the stress ------------------------------------------------------------
    one = (("fixed", 1), "NONE", False)
    def at_one(name):
        return next(r for r in rows if r["book"] == name and tuple(r["rule"]) == one[0] and r["brakes"] == one[1]
                    and r["half"] == one[2])
    entries = {}
    for fam in ("RETEST", "FAILCONF", "SQUEEZE", "ALL3"):
        added, base = at_one(f"BEST+{fam}"), at_one("BEST")
        sims = {y: (sim(trades[y][f"BEST+{fam}"], ("fixed", 1), stress=STRESS), sim(trades[y]["BEST"], ("fixed", 1), stress=STRESS))
                for y in YEARS}
        halves_ok = 0
        for y, first, last in HALVES.values():
            a_h = sum(v for d, v in sims[y][0]["daily"].items() if first <= d <= last)
            b_h = sum(v for d, v in sims[y][1]["daily"].items() if first <= d <= last)
            halves_ok += a_h >= b_h
        entries[f"BEST+{fam}"] = {"y2025": added["y2025"]["net"], "y2026": added["y2026"]["net"], "BEST_2025": base["y2025"]["net"],
                                  "BEST_2026": base["y2026"]["net"], "halves_not_worse": halves_ok,
                                  "improves": (added["y2025"]["net"] > base["y2025"]["net"]
                                               and added["y2026"]["net"] > base["y2026"]["net"] and halves_ok >= 3)}
        if fam != "ALL3":
            alone = at_one(f"{fam}|alone")
            entries[f"{fam}|alone"] = {"y2025": alone["y2025"]["net"], "y2026": alone["y2026"]["net"],
                                       "trades": [alone["y2025"]["trades"], alone["y2026"]["trades"]],
                                       "random_median": alone["random_median"], "negative_halves": alone["negative_halves"],
                                       "beats_random": all(alone[f"y{y}"]["net"] > alone["random_median"][y] for y in YEARS)}

    # --- the trade-off table, the goal, the bootstrap, Kelly, one-lot weeks -------------------------------------------
    shown = list(SHOWN) + ([pick["book"]] if pick and pick["book"] not in SHOWN else [])
    lots_list = [1, 2, 3, 5, 8, 10, 15]
    tradeoff, chance, kel, goal = {}, {}, {}, {}
    for name in shown:
        res = reserve_for(name)
        tradeoff[name] = {}
        for n in lots_list:
            years0 = {y: sim(trades[y][name], ("fixed", n), reserve=res) for y in YEARS}
            years1 = {y: sim(trades[y][name], ("fixed", n), stress=STRESS, reserve=res) for y in YEARS}
            both1 = sim(joined[name], ("fixed", n), stress=STRESS, reserve=res)
            tradeoff[name][str(n)] = {"net_2025": years0["2025"]["net"], "net_2026": years0["2026"]["net"],
                                      "net_2025_stress": years1["2025"]["net"], "net_2026_stress": years1["2026"]["net"],
                                      "both_stress": _pub(both1)}
        by_year = {y: trades[y][name] for y in YEARS}
        chance[name] = boot(by_year, lots_list)
        kel[name] = kelly(by_year)
        goal[name] = {}
        for y in YEARS:
            for n in range(1, 41):
                s = sim(trades[y][name], ("fixed", n), stress=STRESS, reserve=res)
                if s["net"] >= GOAL:
                    goal[name][y] = {"lots": n, "fall_pct": s["fall_pct"], "fall_rs": s["fall_rs"], "worst_day": s["worst_day"]}
                    break
            else:
                goal[name][y] = None
    sys.path.insert(0, str(ROOT / "docs/research/fno/2026-10-29-why-study"))
    weeks = {}
    import lab_s as S
    import analyze_g as AG
    days = json.loads((S.C.ROOT / "docs/research/fno/2026-10-29-year-genome/freeze.json").read_text(encoding="utf-8"))["bindings"]["year_sessions"]
    days25 = json.loads((S.C.O30 / "freeze.json").read_text(encoding="utf-8"))["bindings"]["sessions"]
    raw_trades = {}
    for y in YEARS:
        raw = json.loads((HERE / f"_local/results-raw-{y}.json").read_text(encoding="utf-8"))
        raw_trades[y] = {n: raw["trades"][k] for n, k in raw["books"].items()}
    for name in ("LIVE", "BEST", "TPB"):
        weeks[name] = {str(int(start)): AG.one_lot_weeks(raw_trades["2025"][name] + raw_trades["2026"][name], days25 + days, start=start)
                       for start in (12500.0, 15000.0)}

    out = {"schema": "o30s_results_v1", "freeze_sha256": sha, "grid": GRID, "combos": len(rows), "passes": len(passes),
           "pick": pick, "top_passes": passes[:12], "cross_year": cross, "entries": entries, "tradeoff": tradeoff,
           "chance": chance, "kelly_lots": kel, "lots_for_2_lakh": goal, "one_lot_weeks": weeks, "parity": parity(trades),
           "qualification": "NOT_ASSESSED", "can_place_orders": False}
    (HERE / "results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("combos", len(rows), "passes", len(passes))
    print("pick", json.dumps({k: pick[k] for k in ("book", "rule", "brakes", "half", "y2025", "y2026", "both")}) if pick else None)
    print("cross", json.dumps(cross)[:1500])
    print("entries", json.dumps(entries, indent=0)[:2500])
    print("parity", json.dumps(out["parity"]))


if __name__ == "__main__":
    main()
