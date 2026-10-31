"""O30r verdict -> verdict.json: which strategy earned on which kind of day, and is the book generally profitable?

Owner (Oct 30): "tell me the final verdict on what days or trends what best strategy we have ... is our system atleast
generally profitable? ... most times consistent profitable?"

Descriptive, written after the earlier results. It reads stored replays of the shipped book (O30m library, O30s Tier 2) at
the shipped size and brakes, per lot. It chooses nothing and changes no frozen verdict.

Two kinds of day label, kept apart on purpose:
  KNOWN BEFORE the trade: yesterday's ADX(14) >= 25 ("trend days" as the live gate sees them) against < 25, and the
      first 30 minutes' efficiency (open_drive) at 09:45. A system can act on these.
  KNOWN ONLY AFTER the day, from the index, 09:15 to 15:30, efficiency = |close - open| / (high - low), and range against
      the median of the previous 20 sessions:
        BIG_TREND       efficiency >= 0.5, range >= usual      QUIET_TREND  efficiency >= 0.5, range < usual
        BIG_TWO_WAY     efficiency <  0.5, range >= usual      SIDEWAYS     efficiency <  0.5, range < usual
      These describe what a day turned out to be. No system can trade on them in advance.
"""
from __future__ import annotations

import json
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
FNO = ROOT / "docs/research/fno"
YEARS = ("2025", "2026")
DATA = {"2025": FNO / "2026-10-30-nifty-2025-test/_local/dataset-nifty-2025/breeze.sqlite",
        "2026": FNO / "2026-10-29-year-genome/_local/dataset-nifty/breeze.sqlite"}
SESSIONS = {"2025": json.loads((FNO / "2026-10-30-nifty-2025-test/freeze.json").read_text(encoding="utf-8"))["bindings"]["sessions"],
            "2026": json.loads((FNO / "2026-10-29-year-genome/freeze.json").read_text(encoding="utf-8"))["bindings"]["year_sessions"]}
KINDS = ("BIG_TREND", "QUIET_TREND", "BIG_TWO_WAY", "SIDEWAYS")
NAMED = {"SHIPPED alone": "N|SHIPPED|OWN", "OR20 alone": "N|OR20|OWN", "EFF alone": "N|EFF|OWN", "TPB alone": "N|TPB|OWN",
         "Four together, no gate": "B|UNION", "Four together, ADX gate (LIVE)": "REF|LIVE",
         "LIVE + TPB on closed days (BEST)": "REF|LIVE+tpb_all_days"}
PER_TRADE = 200.0


def day_kinds(year: str) -> dict:
    con = sqlite3.connect(f"file:{DATA[year]}?mode=ro", uri=True)
    rows = con.execute("SELECT substr(datetime,1,10), datetime, open, high, low, close FROM candles WHERE kind='index' "
                       "ORDER BY datetime").fetchall()
    con.close()
    days: dict = {}
    for d, stamp, o, h, l, c in rows:
        if not "09:15" <= stamp[11:16] <= "15:30":
            continue
        x = days.setdefault(d, {"open": float(o), "high": float(h), "low": float(l), "close": float(c)})
        x["high"], x["low"], x["close"] = max(x["high"], float(h)), min(x["low"], float(l)), float(c)
    order = sorted(days)
    out = {}
    for i, d in enumerate(order):
        x = days[d]
        rng = x["high"] - x["low"]
        past = [days[p]["high"] - days[p]["low"] for p in order[max(0, i - 20):i]]
        if d not in SESSIONS[year] or rng <= 0 or len(past) < 5:
            continue
        eff, big = abs(x["close"] - x["open"]) / rng, rng >= statistics.median(past)
        kind = ("BIG_TREND" if big else "QUIET_TREND") if eff >= 0.5 else ("BIG_TWO_WAY" if big else "SIDEWAYS")
        out[d] = {"kind": kind, "efficiency": round(eff, 3), "range": round(rng, 1), "up": x["close"] >= x["open"],
                  "move_pct": round(100 * (x["close"] - x["open"]) / x["open"], 3)}
    return out


def closed(trades: list) -> list:
    return [t for t in trades if t.get("net_pnl") is not None]


def per_lot_days(trades: list, stress: float = 0.0) -> dict:
    daily: dict = defaultdict(float)
    for t in closed(trades):
        daily[t["entry_time"][:10]] += float(t["net_pnl"]) / max(1, int(t.get("lots_at_exit") or 1)) - stress
    return dict(daily)


def by_label(trades: list, label) -> dict:
    out: dict = defaultdict(lambda: {"net": 0.0, "trades": 0})
    for t in closed(trades):
        k = label(t["entry_time"][:10])
        if k is None:
            continue
        out[k]["net"] += float(t["net_pnl"]) / max(1, int(t.get("lots_at_exit") or 1))
        out[k]["trades"] += 1
    return {k: {"net": round(v["net"]), "trades": v["trades"]} for k, v in out.items()}


def consistency(by_year: dict, stress: float = 0.0) -> dict:
    """Green and red months, rolling three months, weeks, and a plain t-statistic on the weekly P&L, over both years."""
    daily = {}
    for y in YEARS:
        daily.update(per_lot_days(by_year[y], stress))
    sessions = SESSIONS["2025"] + SESSIONS["2026"]
    months, weeks = defaultdict(float), defaultdict(float)
    for d in sessions:
        v = daily.get(d, 0.0)
        months[d[:7]] += v
        iso = date.fromisoformat(d).isocalendar()
        weeks[(iso[0], iso[1])] += v
    series = [months[m] for m in sorted(months)]
    roll = [sum(series[i:i + 3]) for i in range(len(series) - 2)]
    w = list(weeks.values())
    run = peak = fall = 0.0
    for d in sorted(sessions):
        run += daily.get(d, 0.0)
        peak = max(peak, run)
        fall = max(fall, peak - run)
    best = max([0.0, *daily.values()])
    se = statistics.pstdev(w) / len(w) ** 0.5 if w else 0.0
    return {"net": round(sum(daily.values())), "months": len(series), "green_months": sum(v > 0 for v in series),
            "red_months": sum(v < 0 for v in series), "worst_month": round(min(series)), "rolling_3m": len(roll),
            "rolling_3m_green": sum(v > 0 for v in roll), "weeks_up": sum(v > 0 for v in w), "weeks_down": sum(v < 0 for v in w),
            "weeks_flat": sum(v == 0 for v in w), "fall": round(fall), "worst_day": round(min([0.0, *daily.values()])),
            "best_day": round(best), "without_best_day": round(sum(daily.values()) - best),
            "weekly_t": round(statistics.fmean(w) / se, 2) if se else 0.0}


def main() -> None:
    kinds = {y: day_kinds(y) for y in YEARS}
    lib = {}
    tables = {}
    for y in YEARS:
        raw = json.loads((FNO / f"2026-10-30-day-router/_local/results-raw-library-{y}.json").read_text(encoding="utf-8"))
        lib[y] = {n: raw["trades"][k] for n, k in raw["books"].items()}
        tables[y] = json.loads((FNO / f"2026-10-30-day-router/_local/table-{y}.json").read_text(encoding="utf-8"))
    t2 = {}
    for y in YEARS:
        raw = json.loads((FNO / f"2026-10-30-earning-power/_local/results-t2-shipped-{y}.json").read_text(encoding="utf-8"))
        t2[y] = {n: raw["trades"][k] for n, k in raw["books"].items()}
    fades = sorted(n for n in lib["2025"] if n.startswith("S|FADE"))
    best_fade = "S|FADE|level=OR20|stop=EXTREME|target_r=2.4|exit=LIVE"
    if best_fade not in lib["2025"]:
        best_fade = next(n for n in fades if "level=OR20" in n and "target_r=2.4" in n and "exit=LIVE" in n)
    books = {name: {y: lib[y][key] for y in YEARS} for name, key in NAMED.items()}
    books["Failed-break FADE (sideways idea, O29i best)"] = {y: lib[y][best_fade] for y in YEARS}
    for name, key in (("LIVE + skip stretched", "LIVE|skip"), ("BEST + skip stretched", "BEST|skip"), ("TPB + skip stretched", "TPB|skip")):
        books[name] = {y: t2[y][key] for y in YEARS}

    # the kinds of day each year had
    mix = {y: dict(Counter(v["kind"] for v in kinds[y].values())) for y in YEARS}
    moves = {y: {"up_days": sum(v["up"] for v in kinds[y].values()), "sessions": len(kinds[y]),
                 "median_range": round(statistics.median(v["range"] for v in kinds[y].values()), 1),
                 "trend_days_up": sum(v["up"] for v in kinds[y].values() if "TREND" in v["kind"]),
                 "trend_days_down": sum(not v["up"] for v in kinds[y].values() if "TREND" in v["kind"])} for y in YEARS}

    # each book on each kind of day
    matrix = {}
    for name, by_year in books.items():
        row = {"after_the_day": {}, "known_before": {}, "years": {}}
        for y in YEARS:
            row["after_the_day"][y] = by_label(by_year[y], lambda d: kinds[y].get(d, {}).get("kind"))
            side = lambda d: (tables[y].get(d, {}).get("side") or {})     # noqa: E731
            row["known_before"][y] = {
                "adx": by_label(by_year[y], lambda d: side(d).get("adx_abs25")),
                "open_drive": by_label(by_year[y], lambda d: side(d).get("open_drive")),
                "direction_up_down": by_label(by_year[y], lambda d: side(d).get("dmi_dir"))}
            row["years"][y] = {"net": round(sum(per_lot_days(by_year[y]).values())),
                               "plus_200": round(sum(per_lot_days(by_year[y], PER_TRADE).values())),
                               "trades": len(closed(by_year[y]))}
        row["consistency"] = consistency(by_year)
        row["consistency_plus_200"] = consistency(by_year, PER_TRADE)
        matrix[name] = row

    # across the whole library: who earned inside each kind in BOTH years (hindsight kinds and the ADX sides)
    def scan(label_for) -> dict:
        out = {}
        for label in sorted({k for y in YEARS for k in {label_for(y, d) for d in SESSIONS[y]} if k}):
            rows = []
            for n in lib["2025"]:
                nets = []
                for y in YEARS:
                    nets.append(sum(float(t["net_pnl"]) / max(1, int(t.get("lots_at_exit") or 1)) for t in closed(lib[y][n])
                                    if label_for(y, t["entry_time"][:10]) == label))
                rows.append((min(nets), nets[0], nets[1], n))
            real = sorted((r for r in rows if not r[3].startswith("NULL")), reverse=True)
            nulls = [r for r in rows if r[3].startswith("NULL")]
            out[label] = {"positive_both_years": sum(r[0] > 0 for r in real), "of": len(real),
                          "random_positive_both_years": sum(r[0] > 0 for r in nulls), "random_of": len(nulls),
                          "top": [{"name": r[3], "y2025": round(r[1]), "y2026": round(r[2])} for r in real[:6]]}
        return out

    scan_after = scan(lambda y, d: kinds[y].get(d, {}).get("kind"))
    scan_adx = scan(lambda y, d: "ADX_HIGH" if (tables[y].get(d, {}).get("side") or {}).get("adx_abs25") == "HIGH"
                    else "ADX_LOW" if (tables[y].get(d, {}).get("side") or {}).get("adx_abs25") == "LOW" else None)

    # the random books, same stored size and brakes, for the yardstick
    nulls = [n for n in lib["2025"] if n.startswith("NULL")]
    random_two_years = sorted(sum(per_lot_days(lib[y][n]).get(d, 0.0) for y in YEARS for d in SESSIONS[y]) for n in nulls)
    yard = {"median": round(statistics.median(random_two_years)), "best": round(random_two_years[-1]), "worst": round(random_two_years[0]),
            "positive": sum(v > 0 for v in random_two_years), "of": len(random_two_years)}

    # single changes, exact, per lot
    def pair(a: str, b: str) -> dict:
        return {"before": {y: {"net": matrix[a]["years"][y]["net"], "fall": _fall(books[a][y])} for y in YEARS},
                "after": {y: {"net": matrix[b]["years"][y]["net"], "fall": _fall(books[b][y])} for y in YEARS}}

    changes = {"Add the ADX trend gate": pair("Four together, no gate", "Four together, ADX gate (LIVE)"),
               "Let TPB trade the closed days": pair("Four together, ADX gate (LIVE)", "LIVE + TPB on closed days (BEST)"),
               "Skip stretched entries, LIVE": pair("Four together, ADX gate (LIVE)", "LIVE + skip stretched"),
               "Skip stretched entries, BEST": pair("LIVE + TPB on closed days (BEST)", "BEST + skip stretched"),
               "Skip stretched entries, TPB": pair("TPB alone", "TPB + skip stretched")}
    out = {"schema": "o30r_verdict_v1", "status": "descriptive; hindsight kinds cannot be traded in advance", "best_fade": best_fade,
           "mix": mix, "moves": moves, "matrix": matrix, "scan_after_the_day": scan_after, "scan_adx": scan_adx,
           "random_books_two_years": yard, "single_changes": changes, "qualification": "NOT_ASSESSED", "can_place_orders": False}
    tmp = HERE / "verdict.json.part"
    tmp.write_text(json.dumps(out, indent=1), encoding="utf-8")
    tmp.replace(HERE / "verdict.json")
    print("mix", mix)
    print("moves", moves)
    print("random", yard)
    for name, row in matrix.items():
        c, s = row["consistency"], row["consistency_plus_200"]
        print(f'\n{name}\n  years {row["years"]["2025"]["net"]:7} {row["years"]["2026"]["net"]:7} | +200 {row["years"]["2025"]["plus_200"]:7} {row["years"]["2026"]["plus_200"]:7} | months {c["green_months"]}/{c["red_months"]} of {c["months"]} (+200: {s["green_months"]}/{s["red_months"]}) | 3m {c["rolling_3m_green"]}/{c["rolling_3m"]} (+200 {s["rolling_3m_green"]}) | t {c["weekly_t"]} (+200 {s["weekly_t"]}) | fall {c["fall"]} | no best day {c["without_best_day"]}')
        for kind in KINDS:
            a, b = row["after_the_day"]["2025"].get(kind, {"net": 0, "trades": 0}), row["after_the_day"]["2026"].get(kind, {"net": 0, "trades": 0})
            print(f'  {kind:12} {a["net"]:7} ({a["trades"]:3}) | {b["net"]:7} ({b["trades"]:3})')
        a, b = row["known_before"]["2025"]["adx"], row["known_before"]["2026"]["adx"]
        print(f'  ADX HIGH {a.get("HIGH", {}).get("net", 0):7} | {b.get("HIGH", {}).get("net", 0):7}   ADX LOW {a.get("LOW", {}).get("net", 0):7} | {b.get("LOW", {}).get("net", 0):7}')
    print("\nSCAN after the day")
    for k, v in scan_after.items():
        print(k, v["positive_both_years"], "of", v["of"], "random", v["random_positive_both_years"], "of", v["random_of"], [(t["name"][:34], t["y2025"], t["y2026"]) for t in v["top"][:4]])
    print("SCAN adx")
    for k, v in scan_adx.items():
        print(k, v["positive_both_years"], "of", v["of"], "random", v["random_positive_both_years"], "of", v["random_of"], [(t["name"][:34], t["y2025"], t["y2026"]) for t in v["top"][:4]])
    print("CHANGES", json.dumps(changes))


def _fall(trades: list) -> int:
    daily = per_lot_days(trades)
    run = peak = fall = 0.0
    for d in sorted(daily):
        run += daily[d]
        peak = max(peak, run)
        fall = max(fall, peak - run)
    return round(fall)


if __name__ == "__main__":
    main()
