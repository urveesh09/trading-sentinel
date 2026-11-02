"""N09 step 1 tables, from the saved features. Equal size: one lot, brakes off.

Every feature is a split at a threshold fixed from the OTHER years' trades (terciles), so a year is never scored on a cut it helped choose.
A max-t permutation test across all features, shuffling net within each year, says what a search this size finds by luck.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "_local"
YEARS = ("2023", "2024", "2025", "2026")
T = {y: json.loads((LOCAL / f"features-{y}.json").read_text(encoding="utf-8")) for y in YEARS}
S = {y: json.loads((LOCAL / f"sessions-{y}.json").read_text(encoding="utf-8")) for y in YEARS}
ALL = [t for y in YEARS for t in T[y]]
FEATURES = ("minute", "er_today", "vwap_cross", "vol_ratio", "range_atr", "with_day_atr", "gap_with_atr", "risk_atr", "ret5_with", "ret20_with", "close_loc", "bar_atr5", "push2_atr5",
            "stretch", "iv", "iv_rv20", "dte", "extrinsic_pct", "premium", "premium_per_atr", "premium_per_target", "cost_share", "response", "delta", "adx", "atr_pct", "rv10", "rv20",
            "prev_range_atr", "stops_before_today")


def line(*a):
    print(*a, flush=True)


def by_label():
    line("\n== Why trades lost, one lot, brakes off (net Rs, trades) ==")
    labels = ("WIN", "COST", "OPTION", "FAILED_MOVE", "WRONG_DIRECTION")
    line("year  " + "  ".join(f"{k:>20}" for k in labels) + "        total")
    for y in YEARS:
        cells = []
        for k in labels:
            rows = [t for t in T[y] if t["label"] == k]
            cells.append(f"{sum(t['net'] for t in rows):>13,.0f} ({len(rows):>3})")
        line(y, "  ".join(cells), f"{sum(t['net'] for t in T[y]):>10,.0f} n={len(T[y])}")
    line("\nLosers that would stand above entry premium at the close of the day (exit timing):")
    for y in YEARS:
        losers = [t for t in T[y] if t["net"] <= 0 and t.get("after_close_option") is not None]
        ok = [t for t in losers if t["after_close_option"] > 0]
        line(y, f"{len(ok)} of {len(losers)} losers", f"cost of those losses {sum(t['net'] for t in ok):,.0f}")


def by_group(key, name):
    line(f"\n== By {name} ==")
    groups = sorted({t.get(key) for t in ALL}, key=str)
    for g in groups:
        cells = []
        for y in YEARS:
            rows = [t for t in T[y] if t.get(key) == g]
            wins = sum(t["net"] > 0 for t in rows)
            cells.append(f"{sum(t['net'] for t in rows):>9,.0f} {wins:>2}/{len(rows):<3}")
        line(f"{str(g):<22}", "  ".join(cells))


def year_table():
    line("\n== The year, from the market and the option chain (not from any trade) ==")
    line("year  sessions  IV09:45  rv/iv  realised/implied move  straddle 09:45-15:10   er_day  big days(|o-c|>0.6ATR)")
    for y in YEARS:
        rows = [s for s in S[y] if not s["expiry_day"]]
        iv = np.nanmedian([s.get("iv_0945") or np.nan for s in rows])
        ri = np.nanmedian([s.get("rv_iv") or np.nan for s in rows])
        mv = np.nansum([s.get("realised_move") or 0 for s in rows]) / np.nansum([s.get("implied_move") or 0 for s in rows if s.get("realised_move") is not None])
        st = np.nanmean([s.get("straddle_change_pct") if s.get("straddle_change_pct") is not None else np.nan for s in rows])
        er = np.nanmedian([s.get("er_day") or np.nan for s in rows])
        big = sum(1 for s in rows if s.get("atr") and abs(s["close"] - s["open"]) > 0.6 * s["atr"])
        line(y, len(rows), f"{iv:7.3f} {ri:6.3f} {mv:10.3f} {st * 100:15.2f}% {er:12.3f} {big:8d}")


def rotations():
    """Terciles from the other three years; scored on the year left out."""
    results = {}
    for name in FEATURES:
        rows = {}
        for y in YEARS:
            train = [t[name] for o in YEARS if o != y for t in T[o] if t.get(name) is not None]
            if len(train) < 30:
                continue
            lo, hi = np.percentile(train, [33.34, 66.67])
            cell = {"low": [], "mid": [], "high": []}
            for t in T[y]:
                v = t.get(name)
                if v is None:
                    continue
                cell["low" if v <= lo else ("high" if v > hi else "mid")].append(t["net"])
            rows[y] = {k: (sum(v), len(v)) for k, v in cell.items()}
        results[name] = rows
    return results


def perm(n=4000, seed=9):
    """Max |t| of (high tercile minus low tercile) across features, net shuffled within each year."""
    rng = np.random.default_rng(seed)
    X = {}
    for name in FEATURES:
        v, r, yrs = [], [], []
        for i, y in enumerate(YEARS):
            train = [t[name] for o in YEARS if o != y for t in T[o] if t.get(name) is not None]
            if len(train) < 30:
                continue
            lo, hi = np.percentile(train, [33.34, 66.67])
            for j, t in enumerate(T[y]):
                x = t.get(name)
                if x is None:
                    continue
                v.append(1 if x > hi else (-1 if x <= lo else 0))
                r.append((i, j))
        X[name] = (np.array(v), np.array(r))
    nets = [np.array([t["net"] for t in T[y]], float) for y in YEARS]

    def stat(nets_now):
        out = {}
        for name, (v, r) in X.items():
            if len(v) < 40:
                continue
            y = np.array([nets_now[i][j] for i, j in r])
            a, b = y[v == 1], y[v == -1]
            if len(a) < 10 or len(b) < 10:
                continue
            out[name] = (a.mean() - b.mean()) / np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
        return out

    real = stat(nets)
    worst = np.zeros(n)
    for k in range(n):
        worst[k] = max(abs(v) for v in stat([rng.permutation(a) for a in nets]).values())
    return {name: (float(t), float((worst >= abs(t)).mean())) for name, t in real.items()}


def main():
    year_table()
    by_label()
    by_group("expert", "strategy")
    by_group("direction", "direction")
    by_group("origin", "main or low-day")
    by_group("dte", "days to expiry")
    results = rotations()
    p = perm()
    line("\n== Feature splits at terciles from the other three years: net Rs low / mid / high per year ==")
    line("A feature counts only if high-minus-low has the same sign in all four years. adj_p: chance of a |t| this big anywhere in the search.")
    table = []
    for name, rows in results.items():
        if len(rows) < 4:
            continue
        gaps = [rows[y]["high"][0] / max(rows[y]["high"][1], 1) - rows[y]["low"][0] / max(rows[y]["low"][1], 1) for y in YEARS]
        same = all(g > 0 for g in gaps) or all(g < 0 for g in gaps)
        t, ap = p.get(name, (float("nan"), float("nan")))
        table.append((abs(t) if t == t else 0, name, t, ap, same, rows, gaps))
    table.sort(reverse=True, key=lambda r: r[0])
    for _, name, t, ap, same, rows, gaps in table:
        cells = " | ".join(f"{rows[y]['low'][0]:>8,.0f}/{rows[y]['mid'][0]:>8,.0f}/{rows[y]['high'][0]:>8,.0f}" for y in YEARS)
        line(f"{name:<20} t={t:>5.2f} adj_p={ap:.3f} same_sign={'YES' if same else 'no ':3} {cells}")
    (HERE / "diagnosis.json").write_text(json.dumps({"features": [{"name": n, "t": t, "adj_p": a, "same_sign_all_years": s, "rows": r} for _, n, t, a, s, r, _g in table]}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
