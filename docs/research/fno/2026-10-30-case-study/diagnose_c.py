"""O30c investigation -> diagnosis.json: why the live book broke even on 2025, read from replays already made.

Descriptive only, per lot. Everything here was looked at after both years were seen, so a pattern found here is a
Tier 2 idea for the unseen checks, never proof. Written and frozen before it was run.
  D1 the live book (UNION_ADX) by strategy, direction, month and exit, each year;
  D2 each strategy (always on) on trend days (yesterday's ADX >= 25) against other days, each year;
  D3 each strategy (always on) with the daily trend direction (DMI, 20-day EMA) against it, each year;
  D4 what each year's market was like;
  D5 which day features split good from bad days the same way in all four half-years (features.split_table);
  D6 the four strategies together (UNION, always on) by entry hour, days to expiry and exit, each year.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_c as A  # noqa: E402

C, Y, F = A.C, A.Y, A.C.F
STORED = {"2025": [C.LOCAL / "evals", C.O30 / "_local/evals"],
          "2026": [C.LOCAL / "evals"] + [C.ROOT / f"docs/research/fno/{s}/_local/evals" for s in
                                         ("2026-10-29-sideways-study", "2026-10-29-why-study", "2026-10-29-year-genome")]}


def stored(book: dict, year: str) -> list:
    w = C.WINDOWS[year]
    name = f"year_{w[0]}_{w[1]}_{Y.digest(book)}.json"
    for folder in STORED[year]:
        if (folder / name).is_file():
            return json.loads((folder / name).read_text(encoding="utf-8"))["trades"]
    raise SystemExit(f"no stored {year} replay for {book}")


def per_lot(t: dict) -> float:
    return float(t["net_pnl"]) / max(1, int(t.get("lots_at_exit") or 1))


def closed(trades: list) -> list:
    return [t for t in trades if t.get("net_pnl") is not None]


def group(trades: list, key) -> dict:
    out = defaultdict(lambda: [0, 0.0])
    for t in closed(trades):
        k = key(t)
        out[k][0] += 1
        out[k][1] += per_lot(t)
    return {str(k): {"trades": n, "net": round(v), "per_trade": round(v / n)} for k, (n, v) in sorted(out.items())}


def side(tables: dict, year: str, day: str, key: str):
    return ((tables[year].get(day) or {}).get("side") or {}).get(key)


def main() -> None:
    _trades, days = A.load()
    tables = {y: json.loads((C.LOCAL / f"table-{y}.json").read_text(encoding="utf-8")) for y in A.YEARS}
    live = C.books()["BASE|UNION_ADX"]
    names = [m["name"] for m in live["members"]]
    comp = {y: {c: {g: stored(Y.book_of([Y.named(c, g)]), y) for g in ("ALWAYS", C.ADX)} for c in Y.NAMED}
            for y in A.YEARS}
    union = {y: stored(C.books()["BASE|UNION"], y) for y in A.YEARS}
    live_t = {y: stored(live, y) for y in A.YEARS}
    out = {}

    out["D1_live_book"] = {y: {
        "by_strategy": group(live_t[y], lambda t: names[t["member"]]),
        "by_direction": group(live_t[y], lambda t: t["direction"]),
        "by_month": group(live_t[y], lambda t: t["entry_time"][:7]),
        "by_exit": group(live_t[y], lambda t: t["exit_reason"]),
        "by_trend_direction": group(live_t[y], lambda t: "with" if side(tables, y, t["entry_time"][:10], "dmi_dir") ==
                                    ("UP" if t["direction"] == "LONG" else "DOWN") else "against")} for y in A.YEARS}

    d2 = {}
    for y in A.YEARS:
        for c in Y.NAMED:
            daily = defaultdict(float)
            for t in closed(comp[y][c]["ALWAYS"]):
                daily[t["entry_time"][:10]] += per_lot(t)
            rows = {"HIGH": [], "LOW": []}
            for d in days[y]:
                s = side(tables, y, d, "adx_abs25")
                if s in rows:
                    rows[s].append(daily.get(d, 0.0))
            d2.setdefault(c, {})[y] = {k: {"days": len(v), "net": round(sum(v)),
                                           "per_day": round(statistics.fmean(v)) if v else None} for k, v in rows.items()}
    out["D2_trend_days_vs_other_days"] = d2

    d3 = {}
    for y in A.YEARS:
        for c in Y.NAMED:
            for key in ("dmi_dir", "ema_dir"):
                d3.setdefault(c, {}).setdefault(key, {})[y] = group(
                    comp[y][c]["ALWAYS"], lambda t, key=key: "with" if side(tables, y, t["entry_time"][:10], key) ==
                    ("UP" if t["direction"] == "LONG" else "DOWN") else "against")
    out["D3_with_or_against_the_trend"] = d3

    d4 = {}
    for y in A.YEARS:
        feats = [(tables[y].get(d) or {}).get("features") or {} for d in days[y]]
        sides = [(tables[y].get(d) or {}).get("side") or {} for d in days[y]]
        d4[y] = {"sessions": len(days[y]),
                 "adx25_high_share": round(sum(s.get("adx_abs25") == "HIGH" for s in sides) / len(days[y]), 3),
                 "uptrend_share_dmi": round(sum(s.get("dmi_dir") == "UP" for s in sides) / len(days[y]), 3),
                 "trend_day_share": round(sum(bool(f.get("h_trend_day")) for f in feats) / len(days[y]), 3),
                 "median_adx14": round(statistics.median(f["adx14"] for f in feats if f.get("adx14") is not None), 1),
                 "median_rv20": round(statistics.median(f["rv20"] for f in feats if f.get("rv20") is not None), 3),
                 "median_range_vs_20d": round(statistics.median(f["h_range_rel"] for f in feats
                                                                 if f.get("h_range_rel") is not None), 2)}
    out["D4_market"] = d4

    features = {d: (tables[y].get(d) or {}).get("features") for y in A.YEARS for d in days[y]}
    features = {d: f for d, f in features.items() if f}
    pnl = {}
    for y in A.YEARS:
        pnl.update(F.daily_per_lot(union[y], days[y]))
    halves = {f"{y}_{h}": span for y in A.YEARS for h, span in zip(("H1", "H2"), C.HALVES[y])}
    split = F.split_table(features, pnl, days["2025"] + days["2026"], halves)
    out["D5_stable_day_features"] = {k: v for k, v in split.items()}

    out["D6_four_strategies"] = {y: {
        "by_entry_hour": group(union[y], lambda t: t["entry_time"][11:13]),
        "by_days_to_expiry": group(union[y], lambda t: ((tables[y].get(t["entry_time"][:10]) or {}).get("features")
                                                        or {}).get("days_to_expiry")),
        "by_exit": group(union[y], lambda t: t["exit_reason"])} for y in A.YEARS}

    Y.write_new(HERE / "diagnosis.json", out)
    for y in A.YEARS:
        print(f"== {y} market:", d4[y])
        for k, v in out["D1_live_book"][y].items():
            print(f"   live book {k}:", {a: (b["trades"], b["net"]) for a, b in v.items()})
    print("== D2 trend days (ADX>=25) vs other days, per lot (days, net):")
    for c, v in d2.items():
        print(f"   {c:8}", {y: {k: (r['days'], r['net']) for k, r in v[y].items()} for y in A.YEARS})
    print("== D3 with / against the daily trend (trades, net):")
    for c, v in d3.items():
        for key, by in v.items():
            print(f"   {c:8} {key}", {y: {k: (r['trades'], r['net']) for k, r in by[y].items()} for y in A.YEARS})
    print("== D5 features with the same better side in all four half-years:",
          {k: v["better_side"] for k, v in split.items() if v["stable"]})
    for y in A.YEARS:
        print(f"== D6 {y} four strategies:", {k: {a: (b["trades"], b["net"]) for a, b in v.items()}
                                              for k, v in out["D6_four_strategies"][y].items()})


if __name__ == "__main__":
    main()
