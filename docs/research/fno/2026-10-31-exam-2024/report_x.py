"""O31 - what the three scored 2024 sheets say together. Research only; descriptive, written after they were scored.

It reads stored replays and the scored sheets. It chooses nothing, changes no frozen verdict and finds no new rule. The
half-day sections re-apply each sheet's own frozen rule with those two sessions removed, as data-binding-2024.json said
would be done. Run with the research interpreter: python report_x.py -> report.json.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

os.environ["O30F_YEAR"] = "2024"
HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
FNO = ROOT / "docs/research/fno"
ROUTER, EARN, RISK = FNO / "2026-10-30-day-router", FNO / "2026-10-30-earning-power", FNO / "2026-10-30-risk-spectrum"
sys.path[:0] = [str(RISK), str(EARN), str(ROUTER)]
import exam_s as ES  # noqa: E402
import exam_r as ER  # noqa: E402
from fno_costs import calc_fno_costs  # noqa: E402

Y = ES.Y
YEARS = ("2024", "2025", "2026")
DATA = {"2024": ROUTER / "_local/dataset-nifty-2024", "2025": FNO / "2026-10-30-nifty-2025-test/_local/dataset-nifty-2025",
        "2026": FNO / "2026-10-29-year-genome/_local/dataset-nifty"}
LAST = {"2024": "2024-12-31", "2025": "2025-12-31", "2026": "2026-10-28"}
SESSIONS = {y: [d for d in json.loads((DATA[y] / "manifest.json").read_text(encoding="utf-8"))["sessions"] if d <= LAST[y]]
            for y in YEARS}
HALF_DAYS = ("2024-03-02", "2024-05-18")
PER_TRADE = 200.0
LOT = 65
START_CASH = (12500.0, 15000.0)
FLOOR = 7000.0


def read(p: Path) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def named(raw: dict) -> dict:
    return {n: raw["trades"][k] for n, k in raw["books"].items()}


def closed(trades: list) -> list:
    return [t for t in trades if t.get("net_pnl") is not None]


def one_lot(t: dict) -> float:
    return float(t["net_pnl"]) / max(1, int(t.get("lots_at_exit") or 1))


def per_lot_days(trades: list, stress: float = 0.0) -> dict:
    out: dict = defaultdict(float)
    for t in closed(trades):
        out[t["entry_time"][:10]] += one_lot(t) - stress
    return dict(out)


def fall_of(daily: dict, sessions: list) -> int:
    run = peak = fall = 0.0
    for d in sorted(sessions):
        run += daily.get(d, 0.0)
        peak = max(peak, run)
        fall = max(fall, peak - run)
    return round(fall)


def consistency(by_year: dict, stress: float = 0.0) -> dict:
    """verdict_r's measures, over all three years."""
    daily: dict = {}
    for y in YEARS:
        daily.update(per_lot_days(by_year[y], stress))
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
    se = statistics.pstdev(w) / len(w) ** 0.5 if w else 0.0
    best = max([0.0, *daily.values()])
    return {"net": round(sum(daily.values())), "months": len(series), "green_months": sum(v > 0 for v in series),
            "red_months": sum(v < 0 for v in series), "worst_month": round(min(series)), "rolling_3m": len(roll),
            "rolling_3m_green": sum(v > 0 for v in roll), "weeks": len(w), "weeks_up": sum(v > 0 for v in w),
            "weeks_down": sum(v < 0 for v in w), "weeks_flat": sum(v == 0 for v in w), "fall": fall_of(daily, sessions),
            "worst_day": round(min([0.0, *daily.values()])), "best_day": round(best),
            "without_best_day": round(sum(daily.values()) - best),
            "weekly_t": round(statistics.fmean(w) / se, 2) if se else 0.0}


def spearman(a: list, b: list) -> float:
    def ranks(x: list) -> list:
        order = sorted(range(len(x)), key=lambda i: x[i])
        r = [0.0] * len(x)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and x[order[j + 1]] == x[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    ra, rb = ranks(a), ranks(b)
    return round(statistics.correlation(ra, rb), 3)


# ---- sheet rules, re-applied ------------------------------------------------------------------------------------------

def sheet1(trades: dict, frozen: dict) -> dict:
    """analyze_f.py's verdict, from per-lot nets."""
    def net(t: list, first: str = "2024-01-01", last: str = "2024-12-31") -> float:
        return sum(one_lot(x) for x in closed(t) if first <= x["entry_time"][:10] <= last)
    nets = {n: round(net(t)) for n, t in trades.items()}
    halves = {n: {"H1": round(net(t, last="2024-06-30")), "H2": round(net(t, first="2024-07-01"))} for n, t in trades.items()}
    live, cand = "REF|LIVE", "REF|LIVE+tpb_all_days"
    alone = [f"ALONE|{n}" for n in frozen["positive_both"]]
    others = [n for n in trades if not n.startswith(("NULL", "REF", "ALONE", "ROUTER", "ROBUST", "UNION_DRIVE"))
              and n not in frozen["positive_both"]]
    return {"candidate_confirmed": nets[cand] > nets[live] and all(halves[cand][h] >= halves[live][h] for h in ("H1", "H2")),
            "robust_core_candidate": nets["ROBUST_CORE"] > 0 and nets["ROBUST_CORE"] > nets[live],
            "positive_both_carries": sum(nets[n] > 0 for n in alone) >= 9 and
            statistics.median(nets[n] for n in alone) > statistics.median(nets[n] for n in others),
            "positive_both_count": f"{sum(nets[n] > 0 for n in alone)} of {len(alone)}",
            "medians": {"positive_both": round(statistics.median(nets[n] for n in alone)),
                        "other_library": round(statistics.median(nets[n] for n in others)), "others": len(others)},
            "random_books_median": round(statistics.median(nets[n] for n in trades if n.startswith("NULL"))),
            "nets": {n: nets[n] for n in frozen["books"]}}


def without_half_days(trades: list) -> list:
    return [t for t in trades if t["entry_time"][:10] not in HALF_DAYS]


def last_bid_value(leg: dict, con: sqlite3.Connection) -> float:
    """What one lot of an open leg was worth at its session's last bar: the last close, at the model's bid, after charges."""
    expiry, strike, opt = re.fullmatch(r"NIFTY(\d{6})(\d+)(CE|PE)", leg["tradingsymbol"]).groups()
    iso = f"20{expiry[:2]}-{expiry[2:4]}-{expiry[4:]}"
    close = con.execute("SELECT close FROM candles WHERE kind='option' AND expiry=? AND strike=? AND opt=? AND datetime LIKE ? "
                        "ORDER BY datetime DESC LIMIT 1", (iso, float(strike), opt, leg["entry_time"][:10] + "%")).fetchone()[0]
    bid = Y.yeardata.bid_ask(float(close))[0]
    entry = float(leg["entry_premium"])
    return round((bid - entry) * LOT - calc_fno_costs(entry, bid, LOT), 2)


# ---- one lot on Monday's terms ----------------------------------------------------------------------------------------

def _runs(groups: list, length: int, start: float, stress: float) -> dict:
    ends, none, hit_floor, refused, wanted = [], 0, 0, 0, 0
    for trades, days in groups:
        rows = sorted(closed(trades), key=lambda t: t["entry_time"])
        by_day = defaultdict(list)
        for t in rows:
            by_day[t["entry_time"][:10]].append(t)
        for i in range(len(days) - length + 1):
            cash, held_until, took, short, any_signal = start, "", 0, False, False
            for d in days[i:i + length]:
                done = 0
                for t in by_day.get(d, ()):
                    any_signal = True
                    if t["entry_time"] < held_until or done >= 3:
                        continue
                    if cash < FLOOR:
                        short = True
                        continue
                    prem = float(t["entry_premium"])
                    if prem * LOT + calc_fno_costs(prem, prem, LOT) > cash:
                        short = True
                        continue
                    cash += one_lot(t) - stress
                    held_until, took, done = t["exit_time"], took + 1, done + 1
            ends.append(cash)
            none += took == 0
            hit_floor += cash < FLOOR
            refused += short
            wanted += any_signal
    n = len(ends)
    return {"runs": n, "paper_book_traded": round(wanted / n, 3), "no_trade": round(none / n, 3), "up": round(sum(e > start for e in ends) / n, 3),
            "down": round(sum(e < start for e in ends) / n, 3), "median_end": round(statistics.median(ends)),
            "worst_end": round(min(ends)), "best_end": round(max(ends)), "ended_below_floor": round(hit_floor / n, 3),
            "a_trade_was_refused_for_cash": round(refused / n, 3)}


def one_lot_runs(by_year: dict, length: int, start: float, stress: float) -> dict:
    """Every possible start session, one lot, the live test's cash floor: enter only with the money to pay for the lot."""
    return _runs([(by_year[y], SESSIONS[y]) for y in YEARS], length, start, stress)


def one_lot_runs_year(trades: list, days: list, length: int, start: float, stress: float) -> dict:
    return _runs([(trades, days)], length, start, stress)


# ---- main ---------------------------------------------------------------------------------------------------------------

def main() -> None:
    binding = read(ROUTER / "data-binding-2024.json")
    integrity = {
        "dataset_unchanged": sha(DATA["2024"] / "breeze.sqlite") == binding["dataset_breeze_sqlite_sha256"],
        "manifest_unchanged": sha(DATA["2024"] / "manifest.json") == binding["dataset_manifest_sha256"],
        "mirror_unchanged": sha(ROUTER / "_local/mirror-2024.sqlite") == binding["mirror"]["sha256"]}

    frozen1 = read(ROUTER / "freeze-2024.json")
    raw1 = {y: read(sorted(glob.glob(str(ROUTER / f"_local/results-raw-2024test-{y}-*.json")))[-1]) for y in YEARS}
    trades1 = named(raw1["2024"])
    shipped = {"2024": named(read(EARN / "_local/results-2024-shipped.json")),
               "2025": named(read(EARN / "_local/results-t2-shipped-2025.json")),
               "2026": named(read(EARN / "_local/results-t2-shipped-2026.json"))}
    raw2 = named(read(EARN / "_local/results-2024-raw.json"))
    raw3 = named(read(RISK / "_local/results-2024.json"))
    scored = {"1": read(ROUTER / "results-2024.json")["verdict"], "2": read(EARN / "results-2024.json")["verdict"],
              "3": read(RISK / "results-2024.json")["verdict"]}

    # every replay is of 2024, and the sheets reproduce each other (they ran separately, with no shared files)
    same = {}
    for a, b in (("REF|LIVE", "LIVE"), ("REF|LIVE+tpb_all_days", "BEST"), ("N|TPB|OWN", "TPB")):
        key = lambda t: (t["entry_time"], t.get("exit_time"), t.get("net_pnl"))  # noqa: E731
        same[f"{a} = {b}"] = sorted(map(key, closed(trades1[a]))) == sorted(map(key, closed(shipped["2024"][b])))
    integrity["sheets_reproduce_each_other"] = same
    every = [t for group in (trades1, shipped["2024"], raw2, raw3) for ts in group.values() for t in ts]
    integrity["trades_read"] = len(every)
    integrity["entries_outside_2024"] = sum(not t["entry_time"].startswith("2024") for t in every)
    integrity["entries_on_expiry_days"] = sum(t["entry_time"][:10] in set(read(DATA["2024"] / "manifest.json")["option_expiries"]) for t in closed(every))

    # the re-applied rules must reproduce the scored sheets before they are used on anything else
    again1 = sheet1(trades1, frozen1)
    assert {k: again1[k] for k in scored["1"]} == scored["1"], "sheet 1 rule not reproduced"
    assert json.loads(json.dumps(ES.verdict(shipped["2024"], raw2))) == scored["2"], "sheet 2 rule not reproduced"
    assert json.loads(json.dumps(ER.verdict(raw3))) == scored["3"], "sheet 3 rule not reproduced"

    # ---- half-days
    half = {"trades_on_half_days_by_frozen_book": {}, "open_at_session_end_by_frozen_book": {}}
    con = sqlite3.connect(f"file:{(DATA['2024'] / 'breeze.sqlite').as_posix()}?mode=ro", uri=True)
    closed_at_last = {}
    for n in frozen1["books"]:
        on = [t for t in trades1[n] if t["entry_time"][:10] in HALF_DAYS]
        if on:
            half["trades_on_half_days_by_frozen_book"][n] = [
                {"day": t["entry_time"][:10], "per_lot": round(one_lot(t)) if t.get("net_pnl") is not None else None} for t in on]
        legs = [t for t in on if t.get("net_pnl") is None]
        if legs:
            values = [last_bid_value(t, con) for t in legs]
            half["open_at_session_end_by_frozen_book"][n] = [
                {"day": t["entry_time"][:10], "symbol": t["tradingsymbol"], "per_lot_at_last_bid": v} for t, v in zip(legs, values)]
        closed_at_last[n] = [{**t, "net_pnl": last_bid_value(t, con), "lots_at_exit": 1} if t.get("net_pnl") is None else t for t in trades1[n]]
    con.close()
    half["sheet_1_without_half_days"] = sheet1({n: without_half_days(t) for n, t in trades1.items()}, frozen1)
    half["sheet_1_open_legs_closed_at_last_bid"] = sheet1({**trades1, **closed_at_last}, frozen1)
    half["sheet_2_without_half_days"] = {k: v for k, v in ES.verdict({n: without_half_days(t) for n, t in shipped["2024"].items()},
                                                                      {n: without_half_days(t) for n, t in raw2.items()}).items()
                                         if k != "halves_per_lot"}
    half["sheet_3_without_half_days"] = ER.verdict({n: without_half_days(t) for n, t in raw3.items()})
    half["open_legs_in_sheet_2_shipped"] = {n: sum(t.get("net_pnl") is None for t in ts) for n, ts in shipped["2024"].items()}
    half["open_legs_in_sheet_2_raw"] = sum(t.get("net_pnl") is None for ts in raw2.values() for t in ts)
    half["open_legs_in_sheet_3"] = sum(t.get("net_pnl") is None for ts in raw3.values() for t in ts)

    # ---- three years, one lot, shipped size and brakes
    def row(by_year: dict) -> dict:
        years = {}
        for y in YEARS:
            days = per_lot_days(by_year[y])
            n = len(closed(by_year[y]))
            years[y] = {"net": round(sum(days.values())), "plus_200": round(sum(days.values()) - PER_TRADE * n), "trades": n,
                        "days": len(days), "fall": fall_of(days, SESSIONS[y]), "worst_day": round(min([0.0, *days.values()])),
                        "best_day": round(max([0.0, *days.values()])), "last_trade": max((t["entry_time"][:10] for t in closed(by_year[y])), default=None)}
        return {"years": years, "together": consistency(by_year), "together_plus_200": consistency(by_year, PER_TRADE)}

    three = {b: row({y: shipped[y][b] for y in YEARS}) for b in ("LIVE", "LIVE|skip", "BEST", "BEST|skip", "TPB", "TPB|skip")}
    for b in ("UNION_DRIVE", "B|UNION", "ROBUST_CORE"):
        three[b] = row({y: named(raw1[y])[b] for y in YEARS})

    # ---- rupees from Rs 2.5 lakh, each year on its own, with the extra cost in the money path
    rows25 = {r["name"]: r for r in read(RISK / "results.json")["rows"]}
    rupees = {}
    for n, x in scored["3"]["books"].items():
        r = rows25[n]
        rupees[n] = {"2024": {k: x[k] for k in ("net", "fall_pct", "fall_rs", "worst_day", "trades", "avg_lots", "max_lots", "last_trade")},
                     "2025": {k: r["y2025"][k] for k in ("net", "fall_pct", "worst_day", "trades", "last_trade")},
                     "2026": {k: r["y2026"][k] for k in ("net", "fall_pct", "worst_day", "trades", "last_trade")},
                     "sum_of_years": x["net"] + r["y2025"]["net"] + r["y2026"]["net"]}
    as_replayed = {b: {y: round(sum(float(t["net_pnl"]) for t in closed(shipped[y][b]))) for y in YEARS}
                   for b in ("LIVE", "LIVE|skip", "BEST", "BEST|skip", "TPB", "TPB|skip")}

    # ---- does a strategy's past say anything about its next year?
    lib = {"2024": named(raw1["2024"]), "2025": named(read(ROUTER / "_local/results-raw-library-2025.json")),
           "2026": named(read(ROUTER / "_local/results-raw-library-2026.json"))}
    names = [n for n in sorted(set(lib["2025"]) & set(lib["2026"]) & set(lib["2024"]))]
    nets = {y: {n: sum(one_lot(t) for t in closed(lib[y][n])) for n in names} for y in YEARS}
    real = [n for n in names if not n.startswith("NULL")]
    rand = [n for n in names if n.startswith("NULL")]
    past = [nets["2025"][n] + nets["2026"][n] for n in real]
    now = [nets["2024"][n] for n in real]
    all_three = sorted((n for n in real if all(nets[y][n] > 0 for y in YEARS)), key=lambda n: -min(nets[y][n] for y in YEARS))
    rand_all_three = [n for n in rand if all(nets[y][n] > 0 for y in YEARS)]
    persistence = {
        "strategies": len(real), "random_books": len(rand),
        "positive_on_2024": sum(v > 0 for v in now),
        "median_2024": round(statistics.median(now)), "best_2024": round(max(now)),
        "random_positive_on_2024": sum(nets["2024"][n] > 0 for n in rand),
        "random_median_2024": round(statistics.median(nets["2024"][n] for n in rand)),
        "random_best_2024": round(max(nets["2024"][n] for n in rand)),
        "rank_correlation_2025_plus_2026_vs_2024": spearman(past, now),
        "rank_correlation_2025_vs_2024": spearman([nets["2025"][n] for n in real], now),
        "rank_correlation_2026_vs_2024": spearman([nets["2026"][n] for n in real], now),
        "live_rank_on_2024_among_strategies": 1 + sum(v > nets["2024"]["REF|LIVE"] for v in now) if "REF|LIVE" in nets["2024"] else None,
        "positive_in_all_three": {n: {y: round(nets[y][n]) for y in YEARS} for n in all_three},
        "random_positive_in_all_three": len(rand_all_three)}

    # ---- one lot, on Monday's terms: every possible start, over the three years
    monday = {}
    for b in ("LIVE", "LIVE|skip"):
        by_year = {y: shipped[y][b] for y in YEARS}
        monday[b] = {f"from_{int(s)}": {f"{n}_sessions": {"as_replayed": one_lot_runs(by_year, n, s, 0.0), "plus_200": one_lot_runs(by_year, n, s, PER_TRADE)}
                                        for n in (5, 20, 60)} for s in START_CASH}

    # ---- how much rests on a few days: each year's single best day, with and without it
    big_days = {}
    for b in ("LIVE", "LIVE|skip", "TPB|skip", "BEST|skip"):
        rows = {}
        for y in YEARS:
            days = per_lot_days(shipped[y][b])
            after = per_lot_days(shipped[y][b], PER_TRADE)
            best = max(days, key=days.get)
            rows[y] = {"best_day": best, "best_day_net": round(days[best]), "net": round(sum(days.values())),
                       "net_plus_200": round(sum(after.values())), "plus_200_without_best_day": round(sum(after.values()) - after[best])}
        big_days[b] = {**rows, "sum_of_best_days": sum(r["best_day_net"] for r in rows.values()),
                       "net": sum(r["net"] for r in rows.values()), "net_plus_200": sum(r["net_plus_200"] for r in rows.values()),
                       "plus_200_without_each_years_best_day": sum(r["plus_200_without_best_day"] for r in rows.values())}

    # ---- could one lot be paid for at all, and how often does a five-session run trade, by year
    afford = {}
    for b in ("LIVE", "LIVE|skip"):
        afford[b] = {}
        for y in YEARS:
            rows = closed(shipped[y][b])
            cost = [float(t["entry_premium"]) * LOT + calc_fno_costs(float(t["entry_premium"]), float(t["entry_premium"]), LOT) for t in rows]
            weeks = {f"from_{int(s)}": one_lot_runs_year(shipped[y][b], SESSIONS[y], 5, s, PER_TRADE) for s in START_CASH}
            afford[b][y] = {"trades": len(rows), "median_lot_cost": round(statistics.median(cost)),
                            "over_12500": round(sum(c > 12500 for c in cost) / len(cost), 3),
                            "over_15000": round(sum(c > 15000 for c in cost) / len(cost), 3),
                            "over_20000": round(sum(c > 20000 for c in cost) / len(cost), 3), "five_sessions_plus_200": weeks}

    # ---- the top of 2024, to look at it, not to use it: where did the money come from?
    top = {}
    for n in sorted(real, key=lambda n: -nets["2024"][n])[:6]:
        days = per_lot_days(lib["2024"][n])
        rows = closed(lib["2024"][n])
        worst = sorted(days.items(), key=lambda kv: -kv[1])[:3]
        top[n] = {"2024": round(nets["2024"][n]), "2025": round(nets["2025"][n]), "2026": round(nets["2026"][n]), "trades": len(rows),
                  "best_days": {d: round(v) for d, v in worst}}

    months_2024 = {b: {m: round(sum(v for d, v in per_lot_days(shipped["2024"][b]).items() if d[:7] == m))
                       for m in sorted({d[:7] for d in SESSIONS["2024"]})} for b in ("LIVE", "LIVE|skip")}

    out = {"schema": "o31_exam_2024_report_v1", "integrity": integrity, "sheets": scored, "half_days": half, "three_years_per_lot": three,
           "rupees_with_cost_each_year_from_2_5_lakh": rupees, "rupees_as_replayed_shipped": as_replayed,
           "persistence": persistence, "one_lot_on_monday_terms": monday, "big_days": big_days, "one_lot_affordability": afford,
           "top_of_2024_not_for_use": top, "months_2024_per_lot": months_2024, "qualification": "NOT_ASSESSED", "can_place_orders": False}
    tmp = HERE / "report.json.part"
    tmp.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8", newline="\n")
    os.replace(tmp, HERE / "report.json")
    print(json.dumps(integrity, indent=1))


if __name__ == "__main__":
    main()
