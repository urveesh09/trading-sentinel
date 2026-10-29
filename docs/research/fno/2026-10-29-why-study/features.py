"""O29g "why" study - day features known before a trade, and each strategy's daily result per lot (research only).

Features use only bars before the decision: the daily ones read sessions up to yesterday, the morning ones read
today's 09:15-09:44 bars. Hindsight columns (today's whole-session shape) are for explanation only and are never
used as a gate.
"""
from __future__ import annotations

import json
import math
import sqlite3
import statistics
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
YEAR_STUDY = ROOT / "docs/research/fno/2026-10-29-year-genome"
sys.path[:0] = [str(ROOT / "python-engine"), str(YEAR_STUDY)]
import pandas as pd  # noqa: E402

DOWNLOAD = Path.home() / "sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite"
DATASET = YEAR_STUDY / "_local/dataset-nifty"


def _con(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)


def daily_bars() -> pd.DataFrame:
    with _con(DOWNLOAD) as con:
        rows = con.execute("SELECT datetime, open, high, low, close FROM candles WHERE kind='daily' AND "
                           "underlying='NIFTY' ORDER BY datetime").fetchall()
    frame = pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close"])
    frame.index = pd.to_datetime(frame.pop("datetime")).dt.normalize()
    return frame[~frame.index.duplicated(keep="last")]


def index_minutes() -> pd.DataFrame:
    with _con(DATASET / "breeze.sqlite") as con:
        rows = con.execute("SELECT datetime, open, high, low, close FROM candles WHERE kind='index' "
                           "ORDER BY datetime").fetchall()
    frame = pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close"])
    frame.index = pd.to_datetime(frame.pop("datetime"))
    return frame[~frame.index.duplicated(keep="last")]


def adx(frame: pd.DataFrame, n: int = 14) -> pd.Series:
    high, low, close = frame["high"], frame["low"], frame["close"]
    up, down = high.diff(), -low.diff()
    plus = ((up > down) & (up > 0)) * up
    minus = ((down > up) & (down > 0)) * down
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * plus.ewm(alpha=1 / n, adjust=False).mean() / atr
    mdi = 100 * minus.ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, math.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def day_features(sessions: list[str], drive_table: dict, weekly: list[str]) -> dict:
    d = daily_bars()
    tr = pd.concat([d["high"] - d["low"], (d["high"] - d["close"].shift()).abs(),
                    (d["low"] - d["close"].shift()).abs()], axis=1).max(axis=1)
    atr14 = tr.ewm(alpha=1 / 14, adjust=False).mean()
    atr50 = tr.rolling(50).mean()
    logret = (d["close"] / d["close"].shift()).apply(math.log)
    rv20 = logret.rolling(20).std() * math.sqrt(252)
    ema20 = d["close"].ewm(span=20, adjust=False).mean()
    a14 = adx(d)
    rng = d["high"] - d["low"]
    minutes = index_minutes()
    out = {}
    for s in sessions:
        day = pd.Timestamp(s)
        prior = d[d.index < day]
        if len(prior) < 60:
            continue
        y = prior.index[-1]
        closes = prior["close"]
        moves = closes.diff().abs().iloc[-5:].sum()
        today = minutes[minutes.index.normalize() == day]
        morning = today[(today.index.hour * 60 + today.index.minute) < 9 * 60 + 45]
        row = {
            "adx14": float(a14.loc[y]),
            "rv20": float(rv20.loc[y]),
            "atr_ratio": float(atr14.loc[y] / atr50.loc[y]) if atr50.loc[y] > 0 else None,
            "ret20_abs": abs(float(closes.iloc[-1] / closes.iloc[-21] - 1)),
            "trend5": abs(float(closes.iloc[-1] - closes.iloc[-6])) / moves if moves > 0 else 0.0,
            "ema20_dist": abs(float(closes.iloc[-1] - ema20.loc[y])) / float(atr14.loc[y]),
            "nr7": bool(rng.loc[y] <= rng[rng.index <= y].iloc[-7:].min() + 1e-9),
            "prev_range_rel": float(rng.loc[y] / rng[rng.index <= y].iloc[-20:].mean()),
            "prev_body": abs(float(prior["close"].iloc[-1] - prior["open"].iloc[-1])) / float(rng.loc[y])
            if rng.loc[y] > 0 else 0.0,
        }
        if not morning.empty:
            o = float(morning["open"].iloc[0])
            row["gap_abs"] = abs(o - float(closes.iloc[-1])) / float(atr14.loc[y])
            row["fhh_abs"] = abs(float(morning["close"].iloc[-1]) - float(closes.iloc[-1])) / float(atr14.loc[y])
        t = drive_table.get(s) or {}
        for k in ("open_drive", "or_width"):
            if t.get(k) is not None:
                row[k] = float(t[k])
        nxt = next((e for e in weekly if e >= s), None)
        row["days_to_expiry"] = sum(1 for x in sessions if s <= x < nxt) if nxt else None
        if not today.empty:
            hi, lo = float(today["high"].max()), float(today["low"].min())
            op, cl = float(today["open"].iloc[0]), float(today["close"].iloc[-1])
            row["h_trend_day"] = hi > lo and abs(cl - op) >= 0.5 * (hi - lo)
            row["h_range_rel"] = (hi - lo) / float(rng[rng.index <= y].iloc[-20:].mean())
        out[s] = row
    return out


def daily_per_lot(trades: list, sessions: list[str]) -> dict:
    out = {s: 0.0 for s in sessions}
    for t in trades:
        if t.get("net_pnl") is None:
            continue
        s = t["entry_time"][:10]
        if s in out:
            out[s] += float(t["net_pnl"]) / max(1, int(t.get("lots_at_exit") or 1))
    return out


def split_table(features: dict, pnl: dict, sessions: list[str], halves: tuple) -> dict:
    """Per feature: mean daily per-lot result above / below its trailing median (previous 60 sessions), in each
    half of the year. A feature whose sign holds in both halves is a candidate; anything else is noise."""
    keys = sorted({k for r in features.values() for k in r if not k.startswith("h_") and k != "days_to_expiry"})
    out = {}
    order = [s for s in sessions if s in features]
    for k in keys:
        res = {}
        for name, (lo, hi) in halves.items():
            above, below = [], []
            for i, s in enumerate(order):
                if not (lo <= s <= hi):
                    continue
                v = features[s].get(k)
                hist = [features[x][k] for x in order[max(0, i - 60):i] if features[x].get(k) is not None]
                if v is None or len(hist) < 20:
                    continue
                v = float(v)
                (above if v > statistics.median(float(h) for h in hist) else below).append(pnl[s])
            res[name] = {"above_mean": round(statistics.fmean(above), 1) if above else None, "n_above": len(above),
                         "below_mean": round(statistics.fmean(below), 1) if below else None, "n_below": len(below)}
        signs = [(r["above_mean"] or 0) - (r["below_mean"] or 0) for r in res.values()]
        res["stable"] = all(x > 0 for x in signs) or all(x < 0 for x in signs)
        res["better_side"] = "HIGH" if signs and statistics.fmean(signs) > 0 else "LOW"
        out[k] = res
    return out


if __name__ == "__main__":
    import lab
    frozen = json.loads((YEAR_STUDY / "freeze.json").read_text())
    sessions = frozen["bindings"]["year_sessions"]
    manifest = json.loads((DATASET / "manifest.json").read_text())
    table = {d: {"open_drive": r.get("open_drive"), "or_width": r.get("or_width")} for d, r in lab.table("year").items()}
    feats = day_features(sessions, table, manifest["weekly_expiry_calendar"])
    (HERE / "_local").mkdir(exist_ok=True)
    (HERE / "_local/features.json").write_text(json.dumps(feats, indent=1, default=str))
    raw = json.loads((lab.LOCAL / "results-raw.json").read_text())
    halves = {"H1_jan_may": ("2026-01-01", "2026-05-31"), "H2_jun_oct": ("2026-06-01", "2026-10-28")}
    report = {}
    for name in ("SHIPPED", "OR20", "EFF", "TPB", "UNION_DRIVE"):
        pnl = daily_per_lot(raw["trades"][lab.task_key(lab.FIXED[name], "year", lab.FULL)], sessions)
        report[name] = split_table(feats, pnl, sessions, halves)
        trend = [pnl[s] for s in sessions if feats.get(s, {}).get("h_trend_day")]
        other = [pnl[s] for s in sessions if s in feats and feats[s].get("h_trend_day") is False]
        report[name]["_hindsight"] = {"trend_days": len(trend), "trend_day_mean": round(statistics.fmean(trend), 1),
                                      "trend_day_total": round(sum(trend)), "other_days": len(other),
                                      "other_mean": round(statistics.fmean(other), 1), "other_total": round(sum(other))}
        dte = {}
        for s in sessions:
            k = feats.get(s, {}).get("days_to_expiry")
            if k is not None:
                dte.setdefault(k, []).append(pnl[s])
        report[name]["_days_to_expiry"] = {k: (len(v), round(sum(v))) for k, v in sorted(dte.items())}
    (HERE / "_local/why.json").write_text(json.dumps(report, indent=1))
    for name, r in report.items():
        print("=" * 80, "\n", name, "hindsight:", r["_hindsight"], "\n  by days to expiry (n, total per lot):",
              r["_days_to_expiry"])
        for k, v in r.items():
            if k.startswith("_"):
                continue
            h1, h2 = v["H1_jan_may"], v["H2_jun_oct"]
            flag = "STABLE" if v["stable"] else ""
            print(f"  {k:15} H1 hi {h1['above_mean']!s:>8} lo {h1['below_mean']!s:>8} | H2 hi {h2['above_mean']!s:>8} "
                  f"lo {h2['below_mean']!s:>8} {flag} better={v['better_side']}")
