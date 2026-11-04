"""Can the next 30-60 minutes of NIFTY be predicted from what is known now? (Nov 4, 2026, owner's question.)

Read-only on the sealed research datasets (NIFTY index 1-minute candles, Dec 2023 - Oct 2026). Every feature
uses only candles up to the decision minute. Train on 2024, test on 2025 and on Jan-Oct 2026, never refit.

Models: logistic regression (numpy, Newton steps) on standardized features; a binned look-up table on the run
of the last 15 and 60 minutes and the time of day. Measured against the base rate (always say the commoner
side). Also descriptive base rates: after a strong opening run, and Gao et al.'s first-half-hour -> last
half-hour intraday momentum.

    python -I predictability.py <out.json>
"""
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(r"C:\Users\Urveesh\Desktop\trading-sentinel\docs\research\fno")
SETS = ["2026-10-30-day-router/_local/dataset-nifty-2024", "2026-10-30-nifty-2025-test/_local/dataset-nifty-2025",
        "2026-10-29-year-genome/_local/dataset-nifty"]
HORIZON = 30
BIG = 0.005          # a 0.5% index move (about 120 NIFTY points): what turns an at-the-money option bought into a big loss


def load():
    rows = {}
    for rel in SETS:
        path = (ROOT / rel / "breeze.sqlite").as_posix()
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        for dt, o, h, l, c in con.execute("SELECT datetime, open, high, low, close FROM candles WHERE kind='index' "
                                          "ORDER BY datetime"):
            hhmm = dt[11:16]
            if "09:15" <= hhmm <= "15:29":
                rows[dt] = (float(o), float(h), float(l), float(c))
        con.close()
    days = defaultdict(list)
    for dt in sorted(rows):
        days[dt[:10]].append((int(dt[11:13]) * 60 + int(dt[14:16]) - 555, *rows[dt]))
    # a session needs most of its minutes
    return {d: v for d, v in days.items() if len(v) >= 360 and v[0][0] == 0}


def features(days):
    out = []
    prev_close = None
    for day in sorted(days):
        bars = days[day]
        closes = np.array([b[4] for b in bars])
        highs = np.array([b[2] for b in bars])
        lows = np.array([b[3] for b in bars])
        mins = [b[0] for b in bars]
        if mins != list(range(len(bars))):
            idx = {m: i for i, m in enumerate(mins)}
            if any(m not in idx for m in range(0, 375, 1) if m < len(bars)):
                prev_close = closes[-1]
                continue
        open_ = bars[0][1]
        gap = open_ / prev_close - 1 if prev_close else 0.0
        rets = np.diff(np.log(closes))
        for t in range(15, 345 - HORIZON + 30, 5):          # 09:30 .. 14:59
            if t + HORIZON >= len(closes):
                break
            c = closes[t]

            def back(k):
                return c / closes[max(0, t - k)] - 1

            hi, lo = highs[:t + 1].max(), lows[:t + 1].min()
            pos = (c - lo) / (hi - lo) if hi > lo else 0.5
            rv = float(np.std(rets[max(0, t - 30):t])) if t > 5 else 0.0
            fut = closes[t + HORIZON] / c - 1
            path_hi = highs[t + 1:t + HORIZON + 1].max() / c - 1
            path_lo = lows[t + 1:t + HORIZON + 1].min() / c - 1
            out.append(dict(day=day, t=t, r5=back(5), r15=back(15), r30=back(30), r60=back(60), ropen=c / open_ - 1,
                            gap=gap, pos=pos, rv=rv, tod=t / 375.0, fut=fut, big_fall=path_lo <= -BIG,
                            big_rise=path_hi >= BIG))
        prev_close = closes[-1]
    return out


COLS = ["r5", "r15", "r30", "r60", "ropen", "gap", "pos", "rv", "tod"]


def matrix(rows, mu=None, sd=None):
    x = np.array([[r[c] for c in COLS] for r in rows], dtype=float)
    if mu is None:
        mu, sd = x.mean(0), x.std(0) + 1e-12
    x = (x - mu) / sd
    return np.hstack([np.ones((len(x), 1)), x]), mu, sd


def logit_fit(x, y, l2=1.0, steps=25):
    w = np.zeros(x.shape[1])
    for _ in range(steps):
        p = 1 / (1 + np.exp(-x @ w))
        g = x.T @ (p - y) + l2 * np.r_[0, w[1:]]
        h = (x.T * (p * (1 - p))) @ x + l2 * np.diag(np.r_[0, np.ones(len(w) - 1)])
        w -= np.linalg.solve(h, g)
    return w


def auc(p, y):
    order = np.argsort(p)
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    pos = y == 1
    n1, n0 = pos.sum(), (~pos).sum()
    return float((ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else float("nan")


def judge(p, y, name):
    pred = p >= 0.5
    acc = float((pred == (y == 1)).mean())
    base = float(max(y.mean(), 1 - y.mean()))
    top = p >= np.quantile(p, 0.9)
    bottom = p <= np.quantile(p, 0.1)
    return {"model": name, "n": int(len(y)), "accuracy": round(acc, 4), "base_rate": round(base, 4),
            "auc": round(auc(p, y), 4), "event_rate": round(float(y.mean()), 4),
            "top_decile_event_rate": round(float(y[top].mean()), 4),
            "bottom_decile_event_rate": round(float(y[bottom].mean()), 4)}


def binned(train, test, target):
    def key(r):
        return (int(np.clip(np.floor(r["r15"] / 0.001), -4, 4)), int(np.clip(np.floor(r["r60"] / 0.002), -4, 4)),
                int(r["tod"] * 6))
    counts = defaultdict(lambda: [0, 0])
    for r in train:
        counts[key(r)][0] += 1
        counts[key(r)][1] += bool(target(r))
    prior = sum(bool(target(r)) for r in train) / len(train)
    p = np.array([(counts[key(r)][1] + 20 * prior) / (counts[key(r)][0] + 20) for r in test])
    return p


def main(out_path):
    days = load()
    rows = features(days)
    years = {"train_2024": [r for r in rows if r["day"].startswith("2024")],
             "test_2025": [r for r in rows if r["day"].startswith("2025")],
             "test_2026": [r for r in rows if r["day"].startswith("2026")]}
    result = {"sessions": {k: len({r["day"] for r in v}) for k, v in years.items()},
              "decisions": {k: len(v) for k, v in years.items()}, "horizon_min": HORIZON, "big_move": BIG,
              "tests": {}}
    targets = {"up_next_30m": lambda r: r["fut"] > 0, "big_fall_30m": lambda r: r["big_fall"],
               "big_rise_30m": lambda r: r["big_rise"]}
    xtr, mu, sd = matrix(years["train_2024"])
    for tname, target in targets.items():
        ytr = np.array([1.0 if target(r) else 0.0 for r in years["train_2024"]])
        w = logit_fit(xtr, ytr)
        for split in ("train_2024", "test_2025", "test_2026"):
            xs, _, _ = matrix(years[split], mu, sd)
            ys = np.array([1.0 if target(r) else 0.0 for r in years[split]])
            ps = 1 / (1 + np.exp(-xs @ w))
            pb = binned(years["train_2024"], years[split], target)
            result["tests"].setdefault(tname, {})[split] = [judge(ps, ys, "logistic"), judge(pb, ys, "binned")]
        result["tests"][tname]["logistic_weights"] = dict(zip(["const"] + COLS, [round(float(v), 4) for v in w]))
    # Descriptive: after a strong opening run (09:15 -> 09:45 at least +/-0.5%), what came next?
    after = {}
    for split, rs in years.items():
        sel = [r for r in rs if r["t"] == 30]
        for sign, name in ((1, "up_run"), (-1, "down_run")):
            strong = [r for r in sel if sign * r["ropen"] >= 0.005]
            if strong:
                after.setdefault(name, {})[split] = {
                    "days": len(strong),
                    "next30_same_direction": round(sum(sign * r["fut"] > 0 for r in strong) / len(strong), 3),
                    "big_move_against_within_30m": round(sum((r["big_fall"] if sign > 0 else r["big_rise"])
                                                             for r in strong) / len(strong), 3)}
    result["after_strong_opening_run"] = after
    # Gao et al.: first half-hour (prev close -> 09:45) sign against the last half-hour (15:00 -> 15:29).
    hits, n = defaultdict(int), defaultdict(int)
    prev = None
    for day in sorted(days):
        bars = days[day]
        c = {b[0]: b[4] for b in bars}
        if prev and 30 in c and 345 in c and 374 in c:
            first = c[30] / prev - 1
            last = c[374] / c[345] - 1
            split = "2024" if day.startswith("2024") else "2025" if day.startswith("2025") else "2026"
            n[split] += 1
            hits[split] += (first > 0) == (last > 0)
        prev = bars[-1][4]
    result["intraday_momentum_first_vs_last_half_hour"] = {k: {"days": n[k], "same_sign": round(hits[k] / n[k], 3)}
                                                           for k in sorted(n) if n[k]}
    Path(out_path).write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
