"""O30m analysis: the kind-of-day router chosen by slicing the library's own trades, its cross-year check, the
routers to replay exactly (routers.json), and the exact report (results.json). Frozen before any library replay.

    analyze_m.py select   -> routers.json   (slicing; cross-year check; the declared rule decides)
    analyze_m.py report   -> results.json   (exact replays of the routers in routers.json)
"""
from __future__ import annotations

import itertools
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab_m as M  # noqa: E402

C, Y = M.C, M.Y
sys.path.insert(0, str(C.ROOT / "docs/research/fno/2026-10-30-case-study"))
sys.path.insert(0, str(C.ROOT / "docs/research/fno/2026-10-29-why-study"))
import analyze_c as A  # noqa: E402
import analyze_g as AG  # noqa: E402

YEARS = ("2025", "2026")


def load(what: str) -> dict:
    out = {}
    for y in YEARS:
        raw = json.loads((M.LOCAL / f"results-raw-{what}-{y}.json").read_text(encoding="utf-8"))
        out[y] = {n: raw["trades"][k] for n, k in raw["books"].items()}
    return out


def per_lot(t: dict) -> float:
    return float(t["net_pnl"]) / max(1, int(t.get("lots_at_exit") or 1))


class Slices:
    """day -> (pnl, trades) of each (strategy, direction mode) in each year, and each day's sides."""

    def __init__(self, trades: dict, days: dict):
        self.days = days
        self.sides = {y: {d: (r.get("side") or {}) for d, r in json.loads(
            (M.LOCAL / f"table-{y}.json").read_text(encoding="utf-8")).items()} for y in YEARS}
        self.names = [n for n in trades["2025"] if not n.startswith(("NULL", "REF"))]
        self.daily = {}
        for y in YEARS:
            for n in trades[y]:
                acc = {mode: defaultdict(lambda: [0.0, 0]) for mode in M.MODES}
                for t in trades[y][n]:
                    if t.get("net_pnl") is None:
                        continue
                    d = t["entry_time"][:10]
                    trend = self.sides[y].get(d, {}).get("dmi_dir")
                    with_trend = trend is not None and (t["direction"] == "LONG") == (trend == "UP")
                    for mode in M.MODES:
                        if mode == "any" or (trend is not None and (mode == "with") == with_trend):
                            acc[mode][d][0] += per_lot(t)
                            acc[mode][d][1] += 1
                for mode in M.MODES:
                    self.daily[(n, mode, y)] = dict(acc[mode])

    def cell(self, y: str, d: str, features: tuple):
        s = self.sides[y].get(d, {})
        values = tuple(s.get(f) for f in features)
        return None if any(v is None for v in values) else values

    def value(self, n: str, mode: str, y: str, span: tuple, features: tuple, cell: tuple) -> tuple[float, int]:
        net, k = 0.0, 0
        for d, (v, c) in self.daily[(n, mode, y)].items():
            if span[0] <= d <= span[1] and self.cell(y, d, features) == cell:
                net, k = net + v, k + c
        return net, k


def cells_of(features: tuple) -> list[tuple]:
    values = {"dmi_dir": ("UP", "DOWN"), "ema_dir": ("UP", "DOWN")}
    return list(itertools.product(*[values.get(f, ("HIGH", "LOW")) for f in features]))


def select(sl: Slices, features: tuple, train: list[tuple], min_trades: int) -> list[dict]:
    out = []
    for cell in cells_of(features):
        best = None
        for n in sl.names:
            for mode in M.MODES:
                parts = [sl.value(n, mode, y, span, features, cell) for y, span in train]
                if min(k for _v, k in parts) < min_trades:
                    continue
                score, total = min(v for v, _k in parts), sum(v for v, _k in parts)
                if score > 0 and (best is None or (score, total, n, mode) > best[:4]):
                    best = (score, total, n, mode)
        if best:
            out.append({"cell": dict(zip(features, cell)), "pick": best[2], "mode": best[3],
                        "worst_half": round(best[0]), "train_total": round(best[1])})
    return out


def apply(sl: Slices, cells: list[dict], y: str) -> dict:
    daily = {d: 0.0 for d in sl.days[y]}
    trades = 0
    for c in cells:
        features, cell = tuple(c["cell"]), tuple(c["cell"].values())
        for d, (v, k) in sl.daily[(c["pick"], c["mode"], y)].items():
            if d in daily and sl.cell(y, d, features) == cell:
                daily[d] += v
                trades += k
    return {"daily": daily, "trades": trades}


def summary(daily: dict, trades: int | None = None) -> dict:
    months, run, peak, dd = defaultdict(float), 0.0, 0.0, 0.0
    for d in sorted(daily):
        months[d[:7]] += daily[d]
        run += daily[d]
        peak, dd = max(peak, run), max(dd, peak - run)
    return {"net": round(sum(daily.values())), "trades": trades, "worst_day": round(min([0.0, *daily.values()])),
            "dd": round(dd), "green_months": sum(v > 0 for v in months.values()),
            "red_months": sum(v < 0 for v in months.values())}


def random_median(sl: Slices, cells: list[dict], y: str, seed: str) -> float:
    """The chosen router's kinds of day, each given a random library strategy and direction mode instead."""
    rng = random.Random(seed)
    nets = []
    for _ in range(M.RANDOM_ROUTERS):
        fake = [{**c, "pick": rng.choice(sl.names), "mode": rng.choice(M.MODES)} for c in cells]
        nets.append(sum(apply(sl, fake, y)["daily"].values()))
    return round(statistics.median(nets)) if nets else 0


def select_main() -> None:
    lib = load("library")
    days = A.sessions()
    sl = Slices(lib, days)
    halves = {y: list(zip((y, y), C.HALVES[y])) for y in YEARS}
    ref = {name: {y: AG.per_lot(lib[y][name], C.WINDOWS[y], days[y])["net"] for y in YEARS}
           for name in ("REF|LIVE", "REF|LIVE+tpb_all_days")}
    cv = {}
    for p, features in M.PARTITIONS.items():
        row = {}
        for train, test in (("2025", "2026"), ("2026", "2025")):
            cells = select(sl, features, halves[train], M.SELECT["cv_min_trades_per_half"])
            res = apply(sl, cells, test)
            s = summary(res["daily"], res["trades"])
            rnd = random_median(sl, cells, test, f"o30m|{p}|{train}")
            row[f"{train}_to_{test}"] = {"cells": cells, "test": s, "random_median": rnd,
                                         "beats": s["net"] > ref["REF|LIVE"][test] and
                                         s["net"] > ref["REF|LIVE+tpb_all_days"][test] and s["net"] > rnd}
        row["passes"] = all(v["beats"] for k, v in row.items() if "_to_" in k)
        row["worse_direction_vs_candidate"] = min(row[f"{a}_to_{b}"]["test"]["net"] - ref["REF|LIVE+tpb_all_days"][b]
                                                  for a, b in (("2025", "2026"), ("2026", "2025")))
        cv[p] = row
    passing = [p for p in cv if cv[p]["passes"]]
    chosen = max(passing, key=lambda p: (cv[p]["worse_direction_vs_candidate"], p)) if passing else None
    best_any = max(cv, key=lambda p: (cv[p]["worse_direction_vs_candidate"], p))
    show = chosen or best_any
    final = select(sl, M.PARTITIONS[show], halves["2025"] + halves["2026"], M.SELECT["final_min_trades_per_half"])
    in_sample = {y: summary(apply(sl, final, y)["daily"], apply(sl, final, y)["trades"]) for y in YEARS}
    routers = {f"CV_2025_to_2026|{show}": {"cells": cv[show]["2025_to_2026"]["cells"]},
               f"CV_2026_to_2025|{show}": {"cells": cv[show]["2026_to_2025"]["cells"]},
               f"FINAL|{show}": {"cells": final, "candidate_for_2024": chosen is not None}}
    Y.write_new(HERE / "routers.json", {"schema": "o30m_routers_v1", "references": ref, "cv": cv,
                                        "chosen_partition": chosen, "shown_partition": show,
                                        "final_in_sample_estimate": in_sample, "routers": routers})
    print("references (exact, per lot):", ref)
    for p, row in cv.items():
        a, b = row["2025_to_2026"], row["2026_to_2025"]
        print(f"{p:22} chosen on 2025 -> 2026 {a['test']['net']:8} (random {a['random_median']:7}, {len(a['cells'])} kinds "
              f"traded) | chosen on 2026 -> 2025 {b['test']['net']:8} (random {b['random_median']:7}, {len(b['cells'])}) "
              f"| passes {row['passes']}")
    print("chosen partition:", chosen, "| shown:", show)
    for c in final:
        print("   FINAL", c)
    print("final router, in-sample estimate:", in_sample)


def report_main() -> None:
    routers = json.loads((HERE / "routers.json").read_text(encoding="utf-8"))
    exact = load("routers")
    lib = load("library")
    days = A.sessions()
    names = list(exact["2025"])
    m = {}
    for n in [*names, "REF|LIVE", "REF|LIVE+tpb_all_days", "B|UNION"]:
        src = exact if n in exact["2025"] else lib
        m[n] = {y: AG.per_lot(src[y][n], C.WINDOWS[y], days[y]) for y in YEARS}
        m[n]["both"] = AG.per_lot(src["2025"][n] + src["2026"][n], A.BOTH, days["2025"] + days["2026"])
        m[n]["weeks"] = AG.one_lot_weeks(src["2025"][n] + src["2026"][n], days["2025"] + days["2026"])
    Y.write_new(HERE / "results.json", {"schema": "o30m_results_v1", "rule": M.RULE, "routers": routers,
                                        "exact_per_lot": m})
    print(f"{'book (exact, per lot)':40} {'2025':>7} {'2026':>7} {'both':>7} {'t':>4} {'worst':>6} {'dd':>6} mo g/r  weeks")
    for n, v in m.items():
        b = v["both"]
        print(f"{n:40} {v['2025']['net']:7} {v['2026']['net']:7} {b['net']:7} {b['trades']:4} {b['worst_day']:6} "
              f"{b['dd']:6} {b['green_months']:2}/{b['red_months']:<2} {v['weeks']}")


if __name__ == "__main__":
    {"select": select_main, "report": report_main}[sys.argv[1]]()
