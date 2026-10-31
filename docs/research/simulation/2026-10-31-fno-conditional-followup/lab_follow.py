"""O31h: causal stateful entries following a failed initial break or shock fade.

Research only. Freeze before scoring. Year via O30F_YEAR=2024 or O30C_YEAR.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
PRIOR = HERE.parent / "2026-10-31-fno-complements"
sys.path.insert(0, str(PRIOR))
import lab_gap as P  # noqa: E402

Y, G, C, L, S, W, O27F = P.Y, P.G, P.C, P.L, P.S, P.W, P.O27F
YEAR, LOCAL = P.YEAR, HERE / "_local"
Y.EVALS = LOCAL / "evals"
FAMILIES = ("DMI_VWAP_RETEST", "SHOCK_FLAG")
_CACHE = {}


def entries(m, f, trend=None):
    t, stamps = f["t"], f["stamps"]
    c, h, l, a, v, mins = [t[k].to_numpy() for k in ("close", "high", "low", "atr", "vwap", "minute")]
    out = {}
    if m["family"] == "DMI_VWAP_RETEST":
        arms = P.entries({"family": "INTRADAY_DMI"}, f, trend)
        for stamp, arm in arms.items():
            start, (d, _, _) = stamps.index(stamp), arm
            touch, extreme = None, None
            for i in range(start + 1, min(len(t), start + 7)):
                if mins[i] - mins[i - 1] != 5 or mins[i] + 5 > 810:
                    break
                if not np.isfinite(a[i]) or not np.isfinite(v[i]) or a[i] <= 0 or d * (c[i] - v[i]) <= 0:
                    break
                edge = l[i] if d > 0 else h[i]
                if touch is None:
                    if d * (edge - v[i]) <= .25 * a[i]:
                        touch, extreme = i, edge
                    continue  # touch and confirmation must be different bars
                extreme = min(extreme, l[i]) if d > 0 else max(extreme, h[i])
                row = trend.iloc[i]
                if not np.isfinite([row.adx, row.pdi, row.mdi]).all():
                    continue
                aligned = row.pdi >= 1.5 * row.mdi if d > 0 else row.mdi >= 1.5 * row.pdi
                if row.adx < 25 or not aligned or not d * (c[i] - (h[i - 1] if d > 0 else l[i - 1])) > 0:
                    continue
                risk = max(d * (c[i] - extreme) + .1 * a[i], .5 * a[i])
                if risk <= 2 * a[i]:
                    out[stamps[i]] = (d, float(c[i] - d * risk), float(c[i] + d * 2 * risk))
                    break
    elif m["family"] == "SHOCK_FLAG":
        done = set()
        for j in range(12, len(t) - 3):
            width, usual = h[j] - l[j], float(np.median(h[j - 12:j] - l[j - 12:j]))
            body = c[j] - float(t["open"].iloc[j])
            if not usual > 0 or width < 2 * usual or abs(body) < .6 * width:
                continue
            d = 1 if body > 0 else -1
            if d in done or (d > 0 and c[j] < h[j] - .2 * width) or (d < 0 and c[j] > l[j] + .2 * width):
                continue
            if any(mins[k] - mins[k - 1] != 5 for k in range(j - 11, j + 1)):
                continue
            mid = (h[j] + l[j]) / 2
            for i in range(j + 1, min(len(t), j + 7)):
                if mins[i] - mins[i - 1] != 5 or mins[i] + 5 > 810:
                    break
                if not np.isfinite(a[i]) or not np.isfinite(v[i]) or a[i] <= 0 or d * (c[i] - mid) <= 0:
                    break
                # At least TWO completed inside bars before the breakout.
                if i < j + 3:
                    if h[i] > h[j] or l[i] < l[j]:
                        break
                    continue
                prior = slice(j + 1, i)
                level = max(h[prior]) if d > 0 else min(l[prior])
                if d * (c[i] - level) > 0 and d * (c[i] - v[i]) > 0:
                    extreme = min(l[prior]) if d > 0 else max(h[prior])
                    risk = max(d * (c[i] - extreme) + .1 * a[i], .5 * a[i])
                    if risk <= 2 * a[i]:
                        out[stamps[i]] = (d, float(c[i] - d * risk), float(c[i] + d * 2 * risk))
                        done.add(d)
                        break
                # A bar which left the shock's range invalidates a later flag.
                if h[i] > h[j] or l[i] < l[j]:
                    break
    else:
        raise ValueError(m["family"])
    return out


def signal(m, frame, regime, now):
    f = O27F.day_features(frame, now.replace(tzinfo=None).date())
    bar = O27F.last_closed_bar(f, now) if f else None
    if not f or not bar or not f["complete_open"]:
        return G.MomSignal(bar_ts=bar or "", reject_reason="o31h:no_features")
    key = (G.digest(m), f["day"].isoformat(), f["stamps"][-1], len(frame))
    if key not in _CACHE:
        trend = None
        if m["family"] == "DMI_VWAP_RETEST":
            clean = frame[~frame.index.duplicated(keep="last")].sort_index()
            trend = P.dmi(clean).reindex(f["t"].index)
            counts = pd.Series(np.arange(len(clean)), index=clean.index).reindex(f["t"].index)
            trend.loc[counts < 60, :] = np.nan
        _CACHE[key] = entries(m, f, trend)
        while len(_CACHE) > 1500:
            _CACHE.pop(next(iter(_CACHE)))
    hit = _CACHE[key].get(bar)
    out = G._signal(frame, regime, now, m, hit[0] if hit else None, bar, f)
    if hit and out.direction is not None:
        out.stop_underlying, out.target_underlying = hit[1:]
    return out


_previous_signal = G.new_signal


def new_signal(m, frame, regime, now):
    return signal(m, frame, regime, now) if m["family"] in FAMILIES else _previous_signal(m, frame, regime, now)


G.new_signal = new_signal


def member(family):
    return G.new_member(family, W.CLOSED, stop_atr=1.5, target_r=2., exit="RUN")


def books():
    old = P.books()
    out = {n: old[n] for n in ("EX|MAIN", "RAW|INTRADAY_DMI", "RAW|SHOCK_RECOVERY")}
    for fam in FAMILIES:
        out[f"RAW|{fam}"] = P.X.book(f"O31h|RAW|{fam}", members=[member(fam)], cfg=dict(S.RAW), cost=False)
        out[f"EX|{fam}"] = P.X.book(f"O31h|EX|{fam}", members=[*W.gated(W.OPEN), member(fam)])
    return out


RULE = {"standalone": "positive every year after Rs200/lot/trade; >=8/year and >=40 total; >=5/6 nonnegative halves; "
        "positive without each year's best day; weekly t>=2; above best frozen random closed-day control",
        "combined": "net above MAIN every year; paired weekly t>=2; yearly realized-equity fall <=MAIN+0.01; no unresolved positions",
        "decision": "both sets required; all three years seen, pass permits fresh paper research only; no automatic live change",
        "parity": "fresh MAIN annual net16,371/5,710/30,540; original DMI and recovery RAW trades identical to O31g",
        "search": "EXPLORATORY_FOUND_BY_LOOKING; no threshold grids, direction selection or alteration of 2023 exam"}


def bindings():
    out = P.bindings()
    for path in [*HERE.glob("*.py"), *[HERE / n for n in ("PLAN.md", "SOURCES.md", "configuration.json", "diagnosis.json", "conditional-stability.json")]]:
        out["sources"][path.relative_to(ROOT).as_posix()] = P.sha(path)
    out["prior_freeze"] = P.sha(PRIOR / "freeze.json")
    out["prior_results"] = P.sha(PRIOR / "results.json")
    return out


def freeze():
    clean = {k: v for k, v in os.environ.items() if k not in ("O30F_YEAR", "O30C_YEAR")}
    parts = {}
    for year in ("2024", "2025", "2026"):
        env = {**clean, **({"O30F_YEAR": year} if year == "2024" else {"O30C_YEAR": year})}
        raw = subprocess.check_output([sys.executable, __file__, "bindings"], cwd=ROOT, env=env)
        parts[year] = json.loads(raw.decode().strip().splitlines()[-1])
    Y.write_new(HERE / "freeze.json", {"schema": "o31h_followup_v1", "bindings": parts, "books": books(), "rule": RULE,
                                      "qualification": "NOT_ASSESSED", "can_place_orders": False})


def verify_freeze():
    frozen = json.loads((HERE / "freeze.json").read_text())
    assert frozen["bindings"][YEAR] == json.loads(json.dumps(bindings(), default=str)), "bound inputs changed"
    assert frozen["books"] == json.loads(json.dumps(books()))
    rel = (HERE / "freeze.json").relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)) == frozen, "not committed"
    return frozen


def run(jobs):
    assert 1 <= jobs <= 4
    O27F.deny_network()
    verify_freeze()
    C.table("year")
    with ProcessPoolExecutor(max_workers=jobs, initializer=L._init) as pool:
        runner = Y.Runner(pool, jobs)
        runner.run(list(books().values()), source="year", window=C.WINDOW)
    verify_freeze()
    P.write(LOCAL / f"keys-{YEAR}.json", {n: Y.task_key(b, "year", C.WINDOW) for n, b in books().items()})
    print("DONE", YEAR, len(books()), flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["bindings", "freeze", "run"])
    cli.add_argument("--jobs", type=int, default=3)
    args = cli.parse_args()
    if args.action == "bindings":
        print(json.dumps(bindings(), default=str))
    elif args.action == "freeze":
        freeze()
    else:
        run(args.jobs)
