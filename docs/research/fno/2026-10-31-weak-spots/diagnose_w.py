"""O31e diagnosis - where does the main book lose, and what happens on the days it sits out? Research only. Written before the new
test is frozen, and it shapes that test: everything it finds is found by looking at three seen years.

    run_diag.py first, for each year; then python diagnose_w.py    # -> diagnosis.json
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
FNO = ROOT / "docs/research/fno"
BOOK_DIR = FNO / "2026-10-31-final-book"
PER_TRADE = 200.0
YEARS = ("2024", "2025", "2026")
DATA = {"2024": FNO / "2026-10-30-day-router/_local/dataset-nifty-2024", "2025": FNO / "2026-10-30-nifty-2025-test/_local/dataset-nifty-2025",
        "2026": FNO / "2026-10-29-year-genome/_local/dataset-nifty"}
LAST = {"2024": "2024-12-31", "2025": "2025-12-31", "2026": "2026-10-28"}
LOCAL = HERE / "_local"
NAMES = ("SHIPPED", "OR20", "EFF", "TPB")


def one_lot(t: dict) -> float:
    return float(t["net_pnl"]) / max(1, int(t.get("lots_at_exit") or 1)) - PER_TRADE


def closed(rows: list) -> list:
    return [t for t in rows if t.get("net_pnl") is not None]


def features_for(year: str) -> dict:
    sys.path.insert(0, str(HERE))
    import sides_w as W
    import sqlite3
    import pandas as pd
    root = DATA[year]
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    sessions = [d for d in manifest["sessions"] if d <= LAST[year]]
    source = {"2024": FNO / "2026-10-30-day-router/_local/mirror-2024.sqlite", "2025": FNO / "2026-10-30-nifty-2025-test/_local/mirror.sqlite",
              "2026": Path.home() / "sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite"}[year]
    con = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    rows = con.execute("SELECT datetime, open, high, low, close FROM candles WHERE kind='daily' AND underlying='NIFTY' ORDER BY datetime").fetchall()
    con.close()
    daily = pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close"])
    daily.index = pd.to_datetime(daily.pop("datetime")).dt.normalize()
    out = {d: {} for d in sessions}
    iv = W.iv_readings(root / "breeze.sqlite", sessions, manifest["option_expiries"], manifest["future_expiries"])
    for part in (W.daily_sides(daily, sessions), W.dte_sides(sessions, manifest["option_expiries"]), W.iv_sides(iv, daily, sessions),
                 json.loads((LOCAL / f"table-{year}.json").read_text(encoding="utf-8"))):
        for d, row in part.items():
            if d in out:
                out[d].update(row)
    return out


def hindsight(year: str) -> dict:
    """Known only after the day (never tradable): trend or two-way, wide or narrow, from the index, as verdict_r did."""
    import sqlite3
    con = sqlite3.connect(f"file:{(DATA[year] / 'breeze.sqlite').as_posix()}?mode=ro", uri=True)
    rows = con.execute("SELECT substr(datetime,1,10), open, high, low, close, datetime FROM candles WHERE kind='index' AND substr(datetime,12,5)>='09:15' "
                       "AND substr(datetime,12,5)<='15:30' ORDER BY datetime").fetchall()
    con.close()
    days = defaultdict(list)
    for r in rows:
        days[r[0]].append(r)
    ranges, out = [], {}
    for d in sorted(days):
        v = days[d]
        rng = max(x[2] for x in v) - min(x[3] for x in v)
        eff = abs(v[-1][4] - v[0][1]) / rng if rng > 0 else 0.0
        usual = sorted(ranges[-20:])[len(ranges[-20:]) // 2] if len(ranges) >= 10 else None
        out[d] = (("BIG" if rng >= usual else "QUIET") + ("_TREND" if eff >= 0.5 else "_TWOWAY")) if usual else None
        ranges.append(rng)
    return out


def table(rows: list, label) -> dict:
    """label(trade) -> bucket: per-lot after Rs 200 by year."""
    out: dict = defaultdict(lambda: {"2024": 0.0, "2025": 0.0, "2026": 0.0, "trades": 0, "wins": 0})
    for y, t in rows:
        b = out[str(label(y, t))]
        v = one_lot(t)
        b[y] += v
        b["trades"] += 1
        b["wins"] += v > 0
    return {k: {**{y: round(v[y]) for y in YEARS}, "total": round(sum(v[y] for y in YEARS)), "trades": v["trades"], "win_pct": round(100 * v["wins"] / v["trades"])}
            for k, v in sorted(out.items())}


def report() -> None:
    feats = {y: features_for(y) for y in YEARS}
    hind = {y: hindsight(y) for y in YEARS}

    def evals(folder: Path, key: str) -> list:
        return json.loads((folder / f"{key}.json").read_text(encoding="utf-8"))["trades"]

    keys_c = {y: json.loads((BOOK_DIR / f"_local/keys-c-{y}.json").read_text(encoding="utf-8")) for y in YEARS}
    keys_d = {y: json.loads((LOCAL / f"keys-diag-{y}.json").read_text(encoding="utf-8")) for y in YEARS}
    main = [(y, t) for y in YEARS for t in closed(evals(BOOK_DIR / "_local/evals", keys_c[y]["SURFACE|A30|S50"]))]
    every = [(y, t) for y in YEARS for t in closed(evals(LOCAL / "evals-diag", keys_d[y]["DIAG|rule"]))]

    def f(y, t, k):
        return feats[y].get(t["entry_time"][:10], {}).get(k)

    def minute(t):
        return int(t["entry_time"][11:13]) * 60 + int(t["entry_time"][14:16])

    def clock(y, t):
        m = minute(t)
        return "09:45-10:30" if m < 630 else "10:30-12:00" if m < 720 else "12:00-13:30" if m < 810 else "13:30-14:45"

    def dmi_align(y, t):
        d = f(y, t, "dmi_dir")
        return "with_dmi" if (d == "UP") == (t["direction"] == "LONG") else "against_dmi"

    def gap_align(y, t):
        d = f(y, t, "gap_dir")
        return "with_gap" if (d == "UP") == (t["direction"] == "LONG") else "against_gap"

    def stretch(y, t):
        s = t.get("stretch")
        if s is None:
            return "none"
        return "behind_vwap" if s < 0 else "0_to_0.25" if s < 0.25 else "0.25_to_0.5" if s < 0.5 else "over_0.5"

    labels = {"strategy": lambda y, t: NAMES[int(t["member"])] if str(t.get("member")).isdigit() else t.get("member"),
              "time_of_day": clock, "with_or_against_daily_trend": dmi_align, "with_or_against_gap": gap_align, "call_or_put": lambda y, t: t["direction"],
              "sessions_to_expiry": lambda y, t: f(y, t, "dte_band"), "adx_band": lambda y, t: f(y, t, "adx_band"), "adx_rising": lambda y, t: f(y, t, "adx_rising"),
              "opening_drive": lambda y, t: f(y, t, "open_drive"), "opening_width": lambda y, t: f(y, t, "or_width"), "vol20": lambda y, t: f(y, t, "rv20"),
              "iv_cheap": lambda y, t: f(y, t, "iv_cheap"), "rv_over_iv": lambda y, t: f(y, t, "rv_over_iv"), "gap_big": lambda y, t: f(y, t, "gap_big"),
              "stretch": stretch, "exit": lambda y, t: t.get("exit_reason"), "kind_of_day_hindsight": lambda y, t: hind[y].get(t["entry_time"][:10]),
              "event": lambda y, t: f(y, t, "event")}
    out = {"main_book_per_lot_after_200": {k: table(main, fn) for k, fn in labels.items()}}
    closed_rows = [(y, t) for y, t in every if (f(y, t, "adx_value") or 0) < 30]
    situations = dict(labels)
    situations.update({"nr7": lambda y, t: f(y, t, "nr7"), "inside": lambda y, t: f(y, t, "inside"), "cpr_narrow": lambda y, t: f(y, t, "cpr_narrow"),
                       "don20_aligned": lambda y, t: "none" if f(y, t, "don20") == "NONE" else ("with" if (f(y, t, "don20") == "UP") == (t["direction"] == "LONG") else "against"),
                       "di_cross_aligned": lambda y, t: "none" if f(y, t, "di_cross") == "NONE" else ("with" if (f(y, t, "di_cross") == "UP") == (t["direction"] == "LONG") else "against")})
    out["closed_days_four_plus_rule_per_lot_after_200"] = {k: table(closed_rows, fn) for k, fn in situations.items()}
    out["sessions"] = {}
    for y in YEARS:
        days = list(feats[y])
        kinds = defaultdict(lambda: defaultdict(int))
        for d in days:
            row = feats[y][d]
            gate = "open" if (row.get("adx_value") or 0) >= 30 else "closed"
            kinds[gate][str(hind[y].get(d))] += 1
        out["sessions"][y] = {"sessions": len(days), "gate_open": sum(kinds["open"].values()), "gate_closed": sum(kinds["closed"].values()),
                              "kinds_on_open_days": dict(kinds["open"]), "kinds_on_closed_days": dict(kinds["closed"])}
    months = defaultdict(float)
    for y, t in main:
        months[t["entry_time"][:7]] += one_lot(t)
    out["main_worst_months"] = {k: round(v) for k, v in sorted(months.items(), key=lambda kv: kv[1])[:6]}
    tmp = HERE / "diagnosis.json.part"
    tmp.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8", newline="\n")
    tmp.replace(HERE / "diagnosis.json")
    print("written")


if __name__ == "__main__":
    report()
