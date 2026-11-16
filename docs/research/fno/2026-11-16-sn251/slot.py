"""Block C slot runner (PLAN.md section 3), fixed before any Block C score.

A variant is a dict:
  name, signal(smp, d) -> +1 / -1 (a side), True (no side) or None/0 (no trade);
  trade(smp, d, side, stress=205, late=0) -> trade dict or None;
  null: "side" (random side on the same signal days), "day" (the same trade on as many random eligible days, with a
        random side when the trade has one), or "none" (no selection: the rule trades every eligible day, so G2 is n/a);
  eligible(smp, d) -> bool (the days a "day" null may draw).
DEV years 2022-2026 (2022 from April). Pick = the best worst DEV year (max-min), ties by DEV net. G2's null: each draw
replaces every variant by its random version and takes the max-min pick among them (200 draws); one position at a time
is kept for the real books (gl.book) and ignored inside null draws (a disclosed approximation). Only the pick is run on
TEST, EXAM-N and EXAM-S, once."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gl  # noqa: E402

YEARS = ("2022", "2023", "2024", "2025", "2026")
EXAMS = ("TEST", "EXAMN", "EXAMS")


def _rule(v, stress=gl.STRESS, late=0):
    def f(smp, d):
        sg = v["signal"](smp, d)
        if not sg:
            return None
        return v["trade"](smp, d, sg if sg is not True else True, stress=stress, late=late)
    return f


def _years(trades, years=YEARS):
    by = {y: 0.0 for y in years}
    for t in trades:
        y = t["exit_day"][:4]
        if y in by:
            by[y] += t["net"]
    return by


def _null_years(v, smp, real, rng_seed, draws, years=YEARS):
    """[draw] -> {year: net} of the variant's random version."""
    kind = v["null"]
    if kind == "none":
        by = _years(real, years)
        return [by] * draws
    rng = np.random.default_rng(rng_seed)
    out = []
    if kind == "side":
        days = [t["day"] for t in real]
        pool = {}
        for t in real:
            sg = v["signal"](smp, t["day"])
            o = v["trade"](smp, t["day"], -sg)
            pool[t["day"]] = (t["net"], None if o is None else o["net"], t["exit_day"], None if o is None else o["exit_day"])
        for _ in range(draws):
            by = {y: 0.0 for y in years}
            for d in days:
                a, b, xa, xb = pool[d]
                if b is not None and rng.random() < 0.5:
                    a, xa = b, xb
                if xa[:4] in by:
                    by[xa[:4]] += a
            out.append(by)
        return out
    # "day"
    elig = [d for d in smp.days if v["eligible"](smp, d)]
    k = len(real)
    cache = {}

    def get(d, sg):
        key = (d, sg)
        if key not in cache:
            t = v["trade"](smp, d, sg)
            cache[key] = None if t is None else (t["net"], t["exit_day"])
        return cache[key]

    sided = v.get("sided", False)
    for _ in range(draws):
        by = {y: 0.0 for y in years}
        pick = rng.choice(len(elig), size=min(k, len(elig)), replace=False) if k else []
        for n in pick:
            d = elig[int(n)]
            sg = (1 if rng.random() < 0.5 else -1) if sided else True
            r = get(d, sg)
            if r is not None and r[1][:4] in by:
                by[r[1][:4]] += r[0]
        out.append(by)
    return out


def evaluate(tag, variants, draws=200, seed=251, notes=None, years=YEARS):
    dev = gl.sample("DEV")
    rows, books = {}, {}
    for v in variants:
        tr = gl.book(dev, _rule(v))
        st = gl.stats(tr)
        st["maxmin"] = round(gl.maxmin(st, years))
        rows[v["name"]], books[v["name"]] = st, tr
        print(tag, f"{v['name']:58s}", f"trades {st['trades']:4d} net {st['net']:>9} maxmin {st['maxmin']:>8} years+ {st['years_positive']}/{st['years']} "
              f"win {st['win_pct']}% worst {st['worst']}", json.dumps(st["by_year"]), flush=True)
    order = sorted(variants, key=lambda v: (rows[v["name"]]["maxmin"], rows[v["name"]]["net"]), reverse=True)
    pick = order[0]
    pst = rows[pick["name"]]
    # G2: the same-budget null
    nulls = [_null_years(v, dev, books[v["name"]], seed + n, draws, years) for n, v in enumerate(variants)]
    sel = []
    for k in range(draws):
        sel.append(max(min(nulls[n][k][y] for y in years) for n in range(len(variants))))
    p95 = float(np.percentile(sel, 95))
    g2_na = pick["null"] == "none"
    # G4 on DEV
    s400 = gl.stats(gl.book(dev, _rule(pick, stress=400.0)))
    late = gl.stats(gl.book(dev, _rule(pick, late=1)))
    G1 = pst["net"] > 0 and sum(pst["by_year"].get(y, 0) > 0 for y in years) >= (3 if len(years) == 5 else len(years) - 1)
    G2 = True if g2_na else pst["maxmin"] > p95
    G4 = s400["net"] > 0 and late["net"] > 0
    # the exams, once, for the pick only
    ex = {}
    for n in EXAMS:
        if n in gl.SEALED:
            gl.SEALED[n] = True
        smp = gl.sample(n)
        tr = gl.book(smp, _rule(pick))
        ex[n] = gl.stats(tr)
        ex[n]["stress_400"] = gl.stats(gl.book(smp, _rule(pick, stress=400.0)))["net"]
        if n in gl.SEALED:
            gl.SEALED[n] = False
        print(tag, "PICK", pick["name"], n, json.dumps({k: ex[n][k] for k in ("trades", "net", "per_trade", "win_pct", "worst", "by_year",
                                                                               "months_positive", "months", "stress_400")}), flush=True)
    G3 = ex["EXAMN"]["net"] > 0 and ex["EXAMS"]["net"] > 0
    verdict = "PASS" if (G1 and G2 and G3 and G4) else ("WATCH" if (G1 and G2 and G3) else "FAIL")
    res = {"variants": rows, "pick": pick["name"], "pick_dev": pst, "null": {"kind": pick["null"], "selected_maxmin_p95": round(p95),
                                                                             "selected_maxmin_mean": round(float(np.mean(sel)))},
           "dev_stress_400": s400["net"], "dev_late_1": late["net"], "exams": ex,
           "gates": {"G1": G1, "G2": G2 if not g2_na else "n/a (no selection)", "G3": G3, "G4": G4}, "verdict": verdict,
           "notes": notes or []}
    print(tag, "VERDICT", verdict, json.dumps(res["gates"]), "null p95", round(p95), "pick maxmin", pst["maxmin"],
          "DEV 400", s400["net"], "late", late["net"], flush=True)
    return res


def save(path, res):
    if path.exists():
        raise SystemExit(f"{path.name} exists: a slot is run once")
    path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
