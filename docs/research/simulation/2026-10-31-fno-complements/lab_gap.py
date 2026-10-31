"""O31g: two frozen complementary hypotheses. Offline research, no runtime imports.

Use freeze before run; choose O30F_YEAR=2024 OR O30C_YEAR=2025/2026.
"""
from __future__ import annotations

import argparse
import hashlib
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
sys.path.insert(0, str(ROOT / "docs/research/fno/2026-10-31-weak-spots"))
import lab_w as W  # noqa: E402

X, Y, G, C, L, F, S, O27F = W.X, W.Y, W.G, W.C, W.L, W.F, W.S, W.O27F
YEAR, LOCAL = W.YEAR, HERE / "_local"
Y.EVALS = LOCAL / "evals"
FAMILIES = ("INTRADAY_DMI", "SHOCK_RECOVERY")
_CACHE = {}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


_original_daily = F.daily_bars
DAILY = LOCAL / f"daily-{YEAR}.json"


def daily_bars():
    raw = json.loads(DAILY.read_text(encoding="utf-8"))
    f = pd.DataFrame(raw["rows"], columns=["date", "open", "high", "low", "close"])
    f.index = pd.to_datetime(f.pop("date"))
    return f


if DAILY.exists():
    F.daily_bars = daily_bars


def dmi(frame, n=14):
    """Causal Wilder-style exponential smoothing, continuous across sessions.

    Initial exponential seed transients are reduced by 60 bars of warmup.
    This is not a session-reset ADX or a daily indicator.
    """
    h, l, c = frame["high"], frame["low"], frame["close"]
    up, down = h.diff(), -l.diff()
    plus = up.where((up > down) & (up > 0), 0.0)
    minus = down.where((down > up) & (down > 0), 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    smooth = lambda a: a.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    atr = smooth(tr).replace(0, np.nan)
    p, m = 100 * smooth(plus) / atr, 100 * smooth(minus) / atr
    adx = smooth(100 * (p - m).abs() / (p + m).replace(0, np.nan))
    return pd.DataFrame({"pdi": p, "mdi": m, "adx": adx}, index=frame.index)


def entries(m, f, trend=None):
    """Return bar-start -> (direction, stop, target), consuming only closed data.

    No cache here: direct prefix/mutated-tail tests exercise the true calculation.
    Cache is applied only at the immutable dataset's signal boundary.
    """
    t = f["t"]
    c, h, l, a, v, mins = [t[k].to_numpy() for k in ("close", "high", "low", "atr", "vwap", "minute")]
    stamps, out, done = f["stamps"], {}, set()
    for i in range(6, len(t)):
        if not 585 <= mins[i] + 5 <= 810 or not np.isfinite(a[i]) or a[i] <= 0:
            continue
        hit = None
        if m["family"] == "INTRADAY_DMI":
            if trend is None or i < 6 or any(mins[j] - mins[j - 1] != 5 for j in range(i - 5, i + 1)):
                continue
            row, before = trend.iloc[i], trend.iloc[i - 3]
            if not (row.adx >= 25 and row.adx > before.adx):
                continue
            if c[i] > max(h[i - 6:i]) and c[i] > v[i] and row.pdi >= 1.5 * row.mdi:
                hit = 1
            elif c[i] < min(l[i - 6:i]) and c[i] < v[i] and row.mdi >= 1.5 * row.pdi:
                hit = -1
            if hit:
                risk = 1.5 * a[i]
                stop, target = c[i] - hit * risk, c[i] + hit * 2 * risk
        elif m["family"] == "SHOCK_RECOVERY":
            # Most recent qualifying shock within six bars. No future extrema.
            for j in range(i - 2, max(11, i - 7), -1):
                if any(mins[k] - mins[k - 1] != 5 for k in range(j - 11, i + 1)):
                    continue
                width = h[j] - l[j]
                usual = float(np.median(h[j - 12:j] - l[j - 12:j]))
                body = c[j] - float(t["open"].iloc[j])
                if not usual > 0 or width < 2 * usual or abs(body) < 0.6 * width:
                    continue
                shock = 1 if body > 0 else -1
                if (shock > 0 and c[j] < h[j] - 0.2 * width) or (shock < 0 and c[j] > l[j] + 0.2 * width):
                    continue
                d = -shock
                if not (d * (c[i] - c[i - 1]) > 0 and d * (c[i - 1] - c[i - 2]) > 0
                        and d * (c[i] - (h[j] + l[j]) / 2) > 0
                        and d * (c[i] - (h[i - 1] if d > 0 else l[i - 1])) > 0):
                    continue
                extreme = min(l[j:i + 1]) if d > 0 else max(h[j:i + 1])
                risk = max(d * (c[i] - extreme) + 0.1 * a[i], 0.5 * a[i])
                if risk > 2 * a[i]:
                    continue
                hit, stop, target = d, c[i] - d * risk, c[i] + d * 1.5 * risk
                break
        else:
            raise ValueError(m["family"])
        if hit and hit not in done:
            out[stamps[i]] = (hit, float(stop), float(target))
            done.add(hit)
    return out


def signal(m, frame, regime, now):
    day = now.replace(tzinfo=None).date()
    f = O27F.day_features(frame, day)
    bar = O27F.last_closed_bar(f, now) if f else None
    if not f or not bar or not f["complete_open"]:
        return G.MomSignal(bar_ts=bar or "", reject_reason="o31g:no_features")
    key = (G.digest(m), day.isoformat(), f["stamps"][-1], len(frame))
    if key not in _CACHE:
        trend = None
        if m["family"] == "INTRADAY_DMI":
            clean = frame[~frame.index.duplicated(keep="last")].sort_index()
            trend = dmi(clean).reindex(f["t"].index)
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
    return G.new_member(family, W.CLOSED, stop_atr=1.5, target_r=2.0,
                        exit="RUN" if family == "INTRADAY_DMI" else "LIVE")


def books():
    base = W.books()
    out = {"EX|MAIN": base["EX|MAIN"], "RAW|MAIN": base["RAW|MAIN"],
           "EX|TPB_PUT_CONTROL": base["EX|D|tpb_puts_closed"],
           "RAW|TPB_PUT_CONTROL": base["RAW|E|tpb_puts"]}
    for fam in FAMILIES:
        out[f"RAW|{fam}"] = X.book(f"O31g|RAW|{fam}", members=[member(fam)], cfg=dict(S.RAW), cost=False)
        out[f"EX|{fam}"] = X.book(f"O31g|EX|{fam}", members=[*W.gated(W.OPEN), member(fam)])
    return out


RULE = {"standalone": "positive every year after Rs200/lot/trade; >=8/year and >=40 total; >=5/6 halves nonnegative; "
        "positive after removing each year's best day; weekly t>=2; total exceeds best stored random closed-day book",
        "combined": "improves main every year; paired weekly t>=2; yearly drawdown <=main+0.01; no unresolved positions",
        "decision": "both standalone and combined must pass; otherwise reject; all years seen, a pass only permits prospective paper research",
        "sensitivity": "Rs300/lot/trade standalone; calls/puts; main losing dates versus whole eligible population; no retuning",
        "exam": "2023 frozen exam remains unchanged and is not opened or extended"}


def bindings():
    manifest = json.loads((Y.YEAR / "manifest.json").read_text(encoding="utf-8"))
    data = {rel: sha(Y.YEAR / rel) for rel in manifest["files_sha256"]}
    assert data == manifest["files_sha256"], "sealed data changed"
    sources = (list((ROOT / "python-engine").glob("*.py")) + list((ROOT / "docs/research/fno").rglob("*.py"))
               + list(HERE.glob("*.py")) + [HERE / n for n in ("PLAN.md", "SOURCES.md", "configuration.json")])
    controls = {}
    for year in ("2024", "2025", "2026"):
        keys_file = W.LOCAL / f"keys-{year}.json"
        keys = json.loads(keys_file.read_text(encoding="utf-8"))
        controls[keys_file.relative_to(ROOT).as_posix()] = sha(keys_file)
        for name, key in keys.items():
            if name.startswith("RANDOM|"):
                p = W.LOCAL / "evals" / f"{key}.json"
                controls[p.relative_to(ROOT).as_posix()] = sha(p)
    return {"sources": {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(sources) if "_local" not in p.parts},
            "dataset": str(Y.YEAR.relative_to(ROOT)), "manifest": sha(Y.YEAR / "manifest.json"), "data": data,
            "daily": sha(DAILY), "memo": sha(Y.memo_file("year")),
            "settings": Y.grid._settings_check(), "reused_random_controls": controls}


def freeze():
    clean = {k: v for k, v in os.environ.items() if k not in ("O30F_YEAR", "O30C_YEAR")}
    parts = {}
    for year in ("2024", "2025", "2026"):
        env = {**clean, **({"O30F_YEAR": year} if year == "2024" else {"O30C_YEAR": year})}
        subprocess.check_call([sys.executable, __file__, "snapshot-daily"], cwd=ROOT, env=env)
        raw = subprocess.check_output([sys.executable, __file__, "bindings"], cwd=ROOT, env=env)
        parts[year] = json.loads(raw.decode().strip().splitlines()[-1])
    Y.write_new(HERE / "freeze.json", {"schema": "o31g_complements_v1", "books": books(), "bindings": parts,
                                       "rule": RULE, "qualification": "NOT_ASSESSED", "can_place_orders": False})


def verify_freeze():
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    assert frozen["bindings"][YEAR] == json.loads(json.dumps(bindings(), default=str)), "bound inputs changed"
    assert frozen["books"] == json.loads(json.dumps(books())), "books changed"
    rel = (HERE / "freeze.json").relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)) == frozen, "freeze not committed"
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
    write(LOCAL / f"keys-{YEAR}.json", {n: Y.task_key(b, "year", C.WINDOW) for n, b in books().items()})
    print("DONE", YEAR, len(books()), flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["snapshot-daily", "bindings", "freeze", "run"])
    cli.add_argument("--jobs", type=int, default=3)
    args = cli.parse_args()
    if args.action == "snapshot-daily":
        if not DAILY.exists():
            f = _original_daily()
            write(DAILY, {"rows": [[str(idx.date()), *map(float, row)] for idx, row in f.iterrows()]})
    elif args.action == "bindings":
        print(json.dumps(bindings(), default=str))
    elif args.action == "freeze":
        freeze()
    else:
        run(args.jobs)
