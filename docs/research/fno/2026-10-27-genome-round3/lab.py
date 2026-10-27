"""O27f genome round 3 - research only. No runtime module imports this file.

What is new against O27 (OR grid), O27b (17 ORB genes) and O27e (efficiency / compression / failed-auction):
  * entry families: trend-day pullback, prior-day level break, VWAP sigma-band break, momentum burst, and an
    ensemble that votes across six sub-signals (k=1 is a union of signals);
  * genes: SENSEX cross-index confirmation, multi-day trend alignment, AM/PM windows, a VWAP-lost exit, the option
    strike depth (target delta 0.55/0.65, never OTM; 0.75 was dropped before the freeze because a timing
    smoke test showed the shipped per-trade risk cap leaves it almost always unaffordable) and the expiry week (nearest or next);
  * crossover across families (shared genes mix between families, entry genes stay with their family);
  * an anchored walk-forward of the whole search procedure (pool -> evolution -> plateau pick, re-run per fold
    using only that fold's training sessions) and a random-entry NULL family searched with the same budget.

Every genome is replayed once over the full archive through the shipped single-leg book (planner, sizing, brakes,
exit ladder, costs, ask/bid fills; fno_policy_replay unchanged). Window metrics are slices of that one causal path.
Production is read-only: the dataset is the existing read-only export. No broker calls, no orders.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import socket
import statistics
import subprocess
import sys
from collections import Counter, OrderedDict
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
sys.path[:0] = [str(ROOT / "python-engine"), str(ROOT / "scripts")]
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import fno_policy_replay as replay  # noqa: E402
import run_fno_consistency_grid as grid  # noqa: E402
from config import settings  # noqa: E402
from fno_engine_mom import MomSignal  # noqa: E402
from fno_models import FnoDirection  # noqa: E402

DATA = ROOT / "docs/research/fno/2026-10-27-consistency-grid/_local/dataset"
LOCAL = HERE / "_local"
CACHE = LOCAL / "observations"
EVALS = LOCAL / "evals"
GRID_ARMS = ROOT / "docs/research/fno/2026-10-27-consistency-grid/_local/arms"
O27E = ROOT / "docs/research/simulation/2026-10-27-fno-novel-families"
SENSEX_TOKENS = (216221445, 221330181)

FULL = ("2026-09-10", "2026-10-26")
A = ("2026-09-10", "2026-10-09")
B = ("2026-10-12", "2026-10-26")
FOLDS = (  # anchored walk-forward: each fold searches only sessions before its test block
    {"name": "F1", "train": ("2026-09-10", "2026-09-30"), "test": ("2026-10-01", "2026-10-09")},
    {"name": "F2", "train": ("2026-09-10", "2026-10-09"), "test": ("2026-10-12", "2026-10-16")},
    {"name": "F3", "train": ("2026-09-10", "2026-10-16"), "test": ("2026-10-19", "2026-10-26")},
    {"name": "FINAL", "train": ("2026-09-10", "2026-10-26"), "test": None},
)

SUBS = ("ORB20", "EFF", "PDL", "VWB", "TPB", "MOMO")
FAMILY_GENES = {
    "TREND_PULLBACK": {"tp_trend": (1.0, 1.5, 2.5), "tp_side": (0.6, 0.75, 0.9), "tp_anchor": ("VWAP", "EMA20"),
                       "tp_touch": (0.25, 0.5, 1.0), "tp_from": (630, 690, 750)},
    "PDL_BREAK": {"pd_buffer": (0.0, 0.1, 0.25), "pd_first": (True, False)},
    "VWAP_BAND": {"vb_k": (0.75, 1.0, 1.5, 2.0), "vb_slope": (3, 6)},
    "MOMO_BURST": {"mb_bars": (2, 3), "mb_move": (1.0, 1.5, 2.0)},
    "ENSEMBLE": {"en_members": tuple(SUBS), "en_k": (1, 2), "en_window": (1, 3)},
    "NULL_RANDOM": {"nr_p": (0.02, 0.04, 0.08), "nr_seed": tuple(range(16))},
}
REAL_FAMILIES = ("TREND_PULLBACK", "PDL_BREAK", "VWAP_BAND", "MOMO_BURST", "ENSEMBLE")
SHARED_GENES = {
    "rvol": (0.0, 0.8, 1.0, 1.2),
    "htf": ("OFF", "WITH"),
    "xidx": ("OFF", "ON"),
    "window": ("ALL", "AM", "PM"),
    "stop_atr": (1.0, 1.5, 2.0),
    "target_r": (1.5, 1.8, 2.4, 3.0),
    "exit": ("LIVE", "LATE", "LOOSE", "RUN"),
    "vwap_exit": ("OFF", "ON"),
    "delta": (0.55, 0.65),
    "expiry": ("NEAR", "NEXT"),
}
SHIPPED_SHARED = {"rvol": 0.0, "htf": "OFF", "xidx": "OFF", "window": "ALL", "stop_atr": 1.5, "target_r": 1.8,
                  "exit": "LIVE", "vwap_exit": "OFF", "delta": 0.55, "expiry": "NEAR"}
EXITS = {
    "LIVE": {},
    "LATE": {"FNO_TIME_STOP_MIN": 75.0, "FNO_TRAIL_ATR_MULT": 1.5, "FNO_PROFIT_LOCK_ARM_R": 0.8},
    "LOOSE": {"FNO_TIME_STOP_MIN": 60.0, "FNO_TRAIL_ATR_MULT": 1.5, "FNO_PROFIT_LOCK_ENABLED": False},
    "RUN": {"FNO_TIME_STOP_MIN": 120.0, "FNO_TRAIL_ATR_MULT": 2.0, "FNO_PROFIT_LOCK_ENABLED": False},
}
# Fixed sub-signal parameters when a family is used inside the ENSEMBLE (declared, never searched there).
SUB_DEFAULTS = {"orb_buffer": 0.1, "eff": {"n": 4, "er": 0.35, "buffer": 0.2, "body": 0.55},
                "tp_trend": 1.5, "tp_side": 0.75, "tp_anchor": "VWAP", "tp_touch": 0.5, "tp_from": 690,
                "pd_buffer": 0.1, "pd_first": True, "vb_k": 1.0, "vb_slope": 6, "mb_bars": 3, "mb_move": 1.5}
POOL = {"per_family": 120, "seed": 2026102706}
GA = {"population": 20, "parents_from_pool": 16, "generations": 6, "elites": 4, "immigrants": 2,
      "tournament": 3, "mutation": 0.15, "adjacent": 0.7, "seed": 2026102707, "plateau_top": 5}
RULE = {
    "all_dates_seen": True,
    "path": "each genome replayed once over FULL through the shipped book; a window = the slice of that path",
    "min_trades": "max(6, ceil(0.35 * sessions in the slice))",
    "fitness": "(net - best day) / max(closed-trade drawdown, 1000) + (green weeks - red weeks) / weeks "
               "- 1 if fixed-trade stressed net <= 0; below min trades: -5 + trades / min",
    "stress": "net - Rs 1 per option unit per side - 25% extra recorded charges (trade list held fixed)",
    "plateau": "median training fitness of the genome and all its one-step neighbours",
    "pick": "the highest plateau among the 5 best training-fitness genomes the fold itself evaluated "
            "(pool + its own evolution + its own neighbours), ties by fitness then digest",
    "tracks": "REAL (5 new families, cross-family crossover) and NULL (random entries, same budget)",
    "walk_forward_verdict": "the search works only if REAL out-of-sample (F1+F2+F3 tests, 16 sessions) is > 0, "
                            "beats SHIPPED on the same sessions, beats the NULL track, and >= 2 of 3 folds are > 0",
    "final": "the FINAL fold's REAL pick is a forward-test candidate only; nothing is promoted on seen data",
}


# ---- helpers ---------------------------------------------------------------------------------------------------

def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


def write_new(path: Path, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, indent=1, allow_nan=False, default=str)


def deny_network() -> None:
    def denied(*_a, **_k):
        raise RuntimeError("O27f offline research: network prohibited")
    socket.socket.connect = denied
    socket.socket.connect_ex = denied
    socket.create_connection = denied
    socket.getaddrinfo = denied


def _minute(ts) -> int:
    return ts.hour * 60 + ts.minute


# ---- causal features ---------------------------------------------------------------------------------------------

_FEATURES: "OrderedDict[tuple, dict]" = OrderedDict()
_SENSEX: dict = {}


def _key(frame: pd.DataFrame, day: date) -> tuple:
    return (day.isoformat(), len(frame), str(frame.index[0]), str(frame.index[-1]), round(float(frame["close"].sum()), 4))


def day_features(frame: pd.DataFrame, day: date) -> dict | None:
    """Today's 5-minute bars with causal features (each row reads only itself, earlier rows and prior sessions)."""
    if frame is None or frame.empty:
        return None
    key = _key(frame, day)
    if key in _FEATURES:
        return _FEATURES[key]
    x = frame[~frame.index.duplicated(keep="last")].sort_index().copy()
    session = pd.Series(x.index.date, index=x.index)
    prev = x["close"].shift(1)
    tr = pd.concat([x["high"] - x["low"], (x["high"] - prev).abs(), (x["low"] - prev).abs()], axis=1).max(axis=1)
    x["atr"] = tr.ewm(alpha=1 / settings.FNO_ATR_LEN, adjust=False).mean()
    x["ema20"] = x["close"].ewm(span=20, adjust=False).mean()
    tp = (x["high"] + x["low"] + x["close"]) / 3
    vol = x["volume"].astype(float)
    cv = vol.groupby(session).cumsum()
    cpv = (tp * vol).groupby(session).cumsum()
    cp2v = (tp * tp * vol).groupby(session).cumsum()
    vwap = cpv / cv.replace(0, np.nan)
    x["vwap"] = vwap.fillna(tp.groupby(session).transform(lambda s: s.expanding().mean()))
    x["vsd"] = np.sqrt((cp2v / cv.replace(0, np.nan) - vwap ** 2).clip(lower=0)).fillna(0.0)
    slot = x.index.hour * 60 + x.index.minute
    x["rvol"] = np.nan
    for _, idx in x.groupby(slot).groups.items():
        s = vol.loc[idx]
        base = s.shift(1).rolling(10, min_periods=3).mean()
        x.loc[idx, "rvol"] = (s / base.replace(0, np.nan)).values
    t = x[session == day].copy()
    prior = x[session < day]
    if t.empty or prior.empty:
        _remember(key, None)
        return None
    sessions = prior.groupby(prior.index.date).agg(high=("high", "max"), low=("low", "min"), close=("close", "last"))
    feats = {"day": day, "pdh": float(sessions["high"].iloc[-1]), "pdl": float(sessions["low"].iloc[-1]),
             "pdc": float(sessions["close"].iloc[-1]),
             "htf_up": (bool(sessions["close"].iloc[-1] > sessions["close"].iloc[-6:-1].mean())
                        if len(sessions) >= 6 else None)}
    mins = np.array([_minute(s) for s in t.index])
    t["minute"] = mins
    feats["complete_open"] = bool(len(t) and mins[0] == 555)
    day_open = float(t["open"].iloc[0])
    feats["day_open"] = day_open
    orb = t[mins < 575]
    feats["orh"], feats["orl"] = (float(orb["high"].max()), float(orb["low"].min())) if len(orb) == 4 else (None, None)
    n = SUB_DEFAULTS["eff"]["n"]
    t["hi4"] = t["high"].shift(1).rolling(n).max()
    t["lo4"] = t["low"].shift(1).rolling(n).min()
    path = t["close"].diff().abs().rolling(n).sum()
    t["er4"] = (t["close"] - t["close"].shift(n)).abs() / path.replace(0, np.nan)
    t["body"] = (t["close"] - t["open"]).abs() / (t["high"] - t["low"]).replace(0, np.nan)
    count = np.arange(1, len(t) + 1)
    t["above"] = (t["close"] > t["vwap"]).cumsum() / count
    t["below"] = (t["close"] < t["vwap"]).cumsum() / count
    t["green"] = (t["close"] > t["open"]).astype(int)
    t["red"] = (t["close"] < t["open"]).astype(int)
    feats["t"] = t
    feats["stamps"] = list(t.index.strftime("%Y-%m-%d %H:%M:%S"))
    _remember(key, feats)
    return feats


def _remember(key, value) -> None:
    _FEATURES[key] = value
    while len(_FEATURES) > 40:
        _FEATURES.popitem(last=False)


def sensex_confirm(day: date) -> dict:
    """bar_ts -> +1 / -1 / 0: the SENSEX front future above (below) its day open and its close 3 bars earlier."""
    if day in _SENSEX:
        return _SENSEX[day]
    import sqlite3
    con = sqlite3.connect(f"file:{(DATA / 'fno-replay.sqlite').resolve().as_posix()}?mode=ro", uri=True)
    try:
        last = {tok: con.execute("SELECT MAX(datetime) FROM fut_candles WHERE instrument_token=? AND interval='5minute'",
                                 (tok,)).fetchone()[0] for tok in SENSEX_TOKENS}
        live = [tok for tok in SENSEX_TOKENS if last[tok] and last[tok][:10] >= day.isoformat()]
        out: dict = {}
        if live:
            front = min(live, key=lambda tok: last[tok])
            rows = con.execute("SELECT datetime, open, close FROM fut_candles WHERE instrument_token=? AND "
                               "interval='5minute' AND datetime>=? AND datetime<? ORDER BY datetime",
                               (front, day.isoformat(), (day + timedelta(days=1)).isoformat())).fetchall()
            seen = OrderedDict((r[0], (float(r[1]), float(r[2]))) for r in rows)
            stamps = list(seen)
            if stamps and stamps[0].endswith("09:15:00"):
                day_open = seen[stamps[0]][0]
                for i, stamp in enumerate(stamps):
                    close = seen[stamp][1]
                    back = seen[stamps[i - 3]][1] if i >= 3 else day_open
                    out[stamp] = 1 if (close > day_open and close > back) else -1 if (close < day_open and close < back) else 0
    finally:
        con.close()
    _SENSEX[day] = out
    return out


# ---- signals -----------------------------------------------------------------------------------------------------

def _cross_up(level, prev_level, close, prev_close):
    return (close > level) & (prev_close <= prev_level)


def sub_signal(name: str, f: dict, p: dict) -> np.ndarray:
    """Direction per today's bar (+1 long, -1 short, 0 none) for one sub-signal with parameters ``p``."""
    t = f["t"]
    c, o, h, l = t["close"], t["open"], t["high"], t["low"]
    pc = c.shift(1)
    atr, patr = t["atr"], t["atr"].shift(1)
    m = t["minute"].values
    z = np.zeros(len(t), dtype=int)
    if name == "ORB20":
        if f["orh"] is None:
            return z
        b = p["orb_buffer"]
        up = _cross_up(f["orh"] + b * atr, f["orh"] + b * patr, c, pc)
        dn = _cross_up(-(f["orl"] - b * atr), -(f["orl"] - b * patr), -c, -pc)
        ok = m >= 575
    elif name == "EFF":
        e = p["eff"]
        up = _cross_up(t["hi4"] + e["buffer"] * atr, t["hi4"].shift(1) + e["buffer"] * patr, c, pc)
        dn = _cross_up(-(t["lo4"] - e["buffer"] * atr), -(t["lo4"].shift(1) - e["buffer"] * patr), -c, -pc)
        ok = ((t["er4"] >= e["er"]) & (t["body"] >= e["body"])).values
    elif name == "PDL":
        b = p["pd_buffer"]
        up = _cross_up(f["pdh"] + b * atr, f["pdh"] + b * patr, c, pc)
        dn = _cross_up(-(f["pdl"] - b * atr), -(f["pdl"] - b * patr), -c, -pc)
        if p["pd_first"]:
            up = up & ~((c > f["pdh"] + b * atr).cumsum().shift(1, fill_value=0) > 0)
            dn = dn & ~((c < f["pdl"] - b * atr).cumsum().shift(1, fill_value=0) > 0)
        ok = np.ones(len(t), dtype=bool)
    elif name == "VWB":
        k, s = p["vb_k"], p["vb_slope"]
        upper, lower = t["vwap"] + k * t["vsd"], t["vwap"] - k * t["vsd"]
        up = _cross_up(upper, upper.shift(1), c, pc) & (t["vwap"] - t["vwap"].shift(s) > 0)
        dn = _cross_up(-lower, -lower.shift(1), -c, -pc) & (t["vwap"] - t["vwap"].shift(s) < 0)
        ok = (t["vsd"] > 0).values
    elif name == "TPB":
        anchor = t["vwap"] if p["tp_anchor"] == "VWAP" else t["ema20"]
        trend_up = ((c - f["day_open"]) >= p["tp_trend"] * atr) & (t["above"] >= p["tp_side"])
        trend_dn = ((f["day_open"] - c) >= p["tp_trend"] * atr) & (t["below"] >= p["tp_side"])
        touched_up = l.rolling(3, min_periods=1).min() <= anchor + p["tp_touch"] * atr
        touched_dn = h.rolling(3, min_periods=1).max() >= anchor - p["tp_touch"] * atr
        up = trend_up & touched_up & (c > o) & (c > h.shift(1)) & (c > anchor)
        dn = trend_dn & touched_dn & (c < o) & (c < l.shift(1)) & (c < anchor)
        ok = m >= p["tp_from"] - 5
    elif name == "MOMO":
        k = p["mb_bars"]
        move = (c - c.shift(k)) / atr
        greens = t["green"].rolling(k).sum() == k
        reds = t["red"].rolling(k).sum() == k
        up_now = (move >= p["mb_move"]) & greens
        dn_now = (move <= -p["mb_move"]) & reds
        up = up_now & ~up_now.shift(1, fill_value=False)
        dn = dn_now & ~dn_now.shift(1, fill_value=False)
        ok = np.ones(len(t), dtype=bool)
    else:
        raise ValueError(name)
    up = np.asarray(up.fillna(False) if hasattr(up, "fillna") else up, dtype=bool) & np.asarray(ok, dtype=bool)
    dn = np.asarray(dn.fillna(False) if hasattr(dn, "fillna") else dn, dtype=bool) & np.asarray(ok, dtype=bool)
    z[up] = 1
    z[dn & ~up] = -1
    return z


def _null_uniform(seed: int, stamp: str, salt: str) -> float:
    return int(hashlib.sha256(f"{seed}|{stamp}|{salt}".encode()).hexdigest()[:12], 16) / float(16 ** 12)


def family_directions(g: dict, f: dict) -> np.ndarray:
    family = g["family"]
    t = f["t"]
    if family == "NULL_RANDOM":
        out = np.zeros(len(t), dtype=int)
        for i, stamp in enumerate(t.index.strftime("%Y-%m-%d %H:%M:%S")):
            if _null_uniform(g["nr_seed"], stamp, "fire") < g["nr_p"]:
                out[i] = 1 if _null_uniform(g["nr_seed"], stamp, "side") < 0.5 else -1
        return out
    if family == "ENSEMBLE":
        members = [s for s in SUBS if s in g["en_members"]]
        votes = np.array([sub_signal(s, f, SUB_DEFAULTS) for s in members])
        w = g["en_window"]
        out = np.zeros(len(t), dtype=int)
        for i in range(len(t)):
            now = votes[:, i]
            if not now.any():
                continue
            recent = votes[:, max(0, i - w + 1): i + 1]
            last = [next((v for v in row[::-1] if v), 0) for row in recent]
            signs = {v for v in last if v}
            if len(signs) == 1 and sum(1 for v in last if v) >= g["en_k"]:
                out[i] = signs.pop()
        return out
    name = {"TREND_PULLBACK": "TPB", "PDL_BREAK": "PDL", "VWAP_BAND": "VWB", "MOMO_BURST": "MOMO"}[family]
    return sub_signal(name, f, {**SUB_DEFAULTS, **{k: g[k] for k in FAMILY_GENES[family]}})


_SIGNALS: "OrderedDict[tuple, dict]" = OrderedDict()


def day_signals(g: dict, f: dict) -> dict:
    """bar_ts -> (direction, close, atr, rvol) for the genome on this session, after the shared entry genes."""
    key = (digest(g), f["day"].isoformat(), id(f))
    if key in _SIGNALS:
        return _SIGNALS[key]
    t = f["t"]
    dirs = family_directions(g, f)
    if g.get("flip"):
        dirs = -dirs
    stamps = t.index.strftime("%Y-%m-%d %H:%M:%S")
    xidx = sensex_confirm(f["day"]) if g["xidx"] == "ON" else None
    out = {}
    for i in np.flatnonzero(dirs):
        d = int(dirs[i])
        r = t.iloc[i]
        end = int(r["minute"]) + 5
        if g["window"] == "AM" and end > 12 * 60 + 30:
            continue
        if g["window"] == "PM" and end < 11 * 60 + 30:
            continue
        if g["rvol"] > 0 and not (pd.notna(r["rvol"]) and r["rvol"] >= g["rvol"]):
            continue
        if g["htf"] == "WITH" and (f["htf_up"] is None or f["htf_up"] != (d > 0)):
            continue
        if xidx is not None and xidx.get(stamps[i], 0) != d:
            continue
        if not (pd.notna(r["atr"]) and r["atr"] > 0):
            continue
        out[stamps[i]] = (d, float(r["close"]), float(r["atr"]), float(r["rvol"]) if pd.notna(r["rvol"]) else 0.0)
    _SIGNALS[key] = out
    while len(_SIGNALS) > 80:
        _SIGNALS.popitem(last=False)
    return out


def last_closed_bar(f: dict, now: datetime) -> str | None:
    """Same answer as fno_policy_replay._last_closed_bar on today's bars, by binary search."""
    naive = pd.Timestamp(now.replace(tzinfo=None)) - pd.Timedelta(minutes=5)
    pos = int(f["t"].index.searchsorted(naive, side="right"))
    return f["stamps"][pos - 1] if pos else None


def lab_signal(frame: pd.DataFrame, regime: str, now: datetime, g: dict) -> MomSignal:
    out = MomSignal()
    naive = now.replace(tzinfo=None)
    f = day_features(frame, naive.date())
    bar_ts = last_closed_bar(f, now) if f is not None else replay._last_closed_bar(frame, now)
    if bar_ts is None:
        out.reject_reason = "lab:no_closed_bar"
        return out
    out.bar_ts = bar_ts
    if f is None or not f["complete_open"]:
        out.reject_reason = "lab:no_features"
        return out
    out.or_high, out.or_low = f["orh"] or 0.0, f["orl"] or 0.0
    hit = day_signals(g, f).get(bar_ts)
    if hit is None:
        out.reject_reason = "lab:no_trigger"
        return out
    if regime == "REGIME_3_CRISIS":
        out.reject_reason = "lab:crisis"
        return out
    d, close, atr, rvol = hit
    out.close, out.atr, out.rvol = close, atr, rvol
    risk = g["stop_atr"] * atr
    out.direction = FnoDirection.LONG if d > 0 else FnoDirection.SHORT
    out.stop_underlying = close - d * risk
    out.target_underlying = close + d * g["target_r"] * risk
    return out


# ---- the book: shipped replay, two entry axes and one exit added -------------------------------------------------

class LabReplay(replay.SingleLegReplay):
    """SingleLegReplay with the lab signal, the expiry-week and strike-depth genes and the VWAP-lost exit.

    genome=None is the passthrough used by the parity gate: the shipped evaluator, nearest expiry, live delta.
    """

    def __init__(self, data, policy, genome: dict | None):
        super().__init__(data, policy)
        self.genome = genome
        self._frame = None

    def _manage(self, book, obs, now):
        before = len(book.trades)
        held = {leg.tradingsymbol: leg for leg in book.open.values()}
        if self.genome and self.genome["vwap_exit"] == "ON" and book.open and self._frame is not None:
            self._vwap_exit(book, obs, now)
        super()._manage(book, obs, now)
        for trade in book.trades[before:]:
            leg = held.get(trade["tradingsymbol"])
            if leg is not None:
                trade["entry_qty"] = leg.initial_qty

    def _vwap_exit(self, book, obs, now):
        from fno_adaptive_risk import Close
        f = day_features(self._frame, now.date())
        if f is None:
            return
        naive = now.replace(tzinfo=None)
        t = f["t"]
        closed = t[t.index + timedelta(minutes=5) <= naive]
        if closed.empty:
            return
        last = closed.iloc[-1]
        bar_end = closed.index[-1] + timedelta(minutes=5)
        for leg_id in sorted(book.open):
            leg = book.open[leg_id]
            entered = replay._aware(leg.entry_time).replace(tzinfo=None)
            if bar_end <= entered:
                continue
            lost = last["close"] < last["vwap"] if leg.direction == "LONG" else last["close"] > last["vwap"]
            if not lost:
                continue
            quote = obs.options.get(leg.token)
            basis = (quote.bid if quote and quote.bid > 0 else quote.ltp if quote else 0.0)
            if basis <= 0:
                self.notes["vwap_exit_unpriced"] += 1
                continue
            record, final_net = replay._close_record(leg, now, basis, "VWAP_LOST", obs.future.ltp)
            record["entry_qty"] = leg.initial_qty
            book.trades.append(record)
            book.equity += final_net
            book.closes.append((now, final_net, "SINGLE_LEG"))
            book.completed.append(Close(now, record["net_pnl"], True))
            del book.open[leg_id]

    def _entry(self, book, obs, frame, day, now):
        # Copy of SingleLegReplay._entry; the only changes are marked [LAB].
        from fno_chain import ChainSnapshot, years_to_expiry, _parity_forward
        from fno_engine_mom import evaluate_fno_mom
        from fno_entry_plan import EntryState, plan_single_leg_entry
        self._frame = frame  # [LAB] the VWAP-lost exit reads the same session frame
        minute = now.hour * 60 + now.minute
        if not (settings.FNO_ENTRY_START_MIN <= minute < settings.FNO_ENTRY_END_MIN):
            return
        today = now.date()
        g = self.genome
        f = day_features(frame, today) if g else None  # [LAB] binary-search bar lookup, same answer
        bar_ts = last_closed_bar(f, now) if f is not None else replay._last_closed_bar(frame, now)
        if bar_ts is None:
            return
        regime, regime_source = self.data.regime(bar_ts, day)
        self.notes[f"regime_{regime_source}"] += 1
        sig = lab_signal(frame, regime, now, g) if g else evaluate_fno_mom(frame, regime, now)  # [LAB]
        if sig.direction is None:
            self.funnel[f"engine:{sig.reject_reason}"] += 1
            return
        if sig.bar_ts in book.entered_bars:
            return
        calendar, _ = self.data.option_expiries()
        upcoming = [e for e in calendar if e >= today]  # [LAB] expiry-week gene; the expiry-day gate is unchanged
        if not upcoming:
            self.funnel["chain_unavailable"] += 1
            return
        expiry = upcoming[1] if (g and g["expiry"] == "NEXT" and len(upcoming) > 1) else upcoming[0]
        quotes = {(q.contract.strike, q.contract.instrument_type): q
                  for q in obs.options.values() if q.contract.expiry == expiry}
        if not quotes:
            self.funnel["chain_unavailable:calendar_expiry_not_archived"] += 1
            return
        forward = obs.future.ltp
        strikes = sorted({k for k, _ in quotes})
        atm = min(strikes, key=lambda k: abs(k - forward)) if strikes else forward
        snap = ChainSnapshot(taken_at=obs.at, expiry=expiry, forward=forward,
                             parity_forward=_parity_forward(quotes, atm, years_to_expiry(expiry, obs.at)),
                             lot_size=obs.future.contract.lot_size, fut_quote=obs.future, quotes=quotes)
        held = frozenset(leg.tradingsymbol for leg in book.open.values())
        open_premium = sum(leg.entry_premium * leg.qty for leg in book.open.values())
        stance = self._stance(book, now)
        halts = self._halts(book, now)
        if stance.single_leg_halted_today:
            halts = (*halts, f"two_strike_day_halt losses={stance.single_leg_losses_today}")
        from fno_entry_plan import REENTRY_STOP_REASONS, reentry_level
        confirm = (settings.FNO_REENTRY_REQUIRES_CONFIRMATION if self.policy.reentry_confirmation is None
                   else self.policy.reentry_confirmation)
        levels = {}
        if confirm:
            for t in sorted((t for t in book.trades if "net_pnl" in t), key=lambda t: t["exit_time"]):
                if t["exit_time"][:10] == today.isoformat() and t["exit_reason"] in REENTRY_STOP_REASONS:
                    levels[t["direction"]] = reentry_level(t["direction"], t["entry_underlying"],
                                                           t["stop_underlying"], settings.FNO_REENTRY_MARGIN_R)
        state = EntryState(pool=book.equity, open_premium=open_premium, open_positions=len(book.open),
                           trades_today=book.entries_today[today], active_kill_switches=halts,
                           held_symbols=held, is_trading_day=True, is_expiry_day=today in calendar,
                           risk_multiplier=stance.multiplier, reentry_levels=levels)
        shipped_delta = settings.FNO_TARGET_DELTA
        settings.FNO_TARGET_DELTA = g["delta"] if g else shipped_delta  # [LAB] strike-depth gene
        try:
            plan = plan_single_leg_entry(sig, snap, regime, now, state)
        finally:
            settings.FNO_TARGET_DELTA = shipped_delta
        self.decisions.append({"at": now.isoformat(), "bar_ts": sig.bar_ts, "direction": sig.direction.value,
                               "outcome": "accepted" if plan.accepted else plan.reject_reason,
                               "halts": list(state.active_kill_switches), "pool": round(state.pool, 2),
                               "risk_multiplier": stance.multiplier, "risk_reason": stance.reason})
        if not plan.accepted:
            self.funnel[plan.reject_reason] += 1
            return
        self.funnel["accepted"] += 1
        fill = plan.quote.ask
        leg = replay.OpenLeg(
            initial_qty=plan.lots * plan.lot_size, id=book.next_id, tradingsymbol=plan.quote.contract.tradingsymbol,
            token=plan.quote.contract.token,
            direction=sig.direction.value, lots=plan.lots, lot_size=plan.lot_size, entry_time=now.isoformat(),
            entry_premium=fill, entry_underlying=snap.forward, stop_underlying=sig.stop_underlying,
            target_underlying=sig.target_underlying,
            premium_stop=round((1.0 - settings.FNO_STOP_PREMIUM_PCT) * fill, 2),
            atr_at_entry=sig.atr, delta_at_entry=plan.delta, bar_ts=sig.bar_ts, best_underlying=snap.forward)
        book.next_id += 1
        book.open[leg.id] = leg
        book.entered_bars.add(sig.bar_ts)
        book.entries_today[today] += 1


# ---- evaluation ----------------------------------------------------------------------------------------------------

_DATA = None
KEEP = ("tradingsymbol", "direction", "bar_ts", "entry_time", "entry_premium", "lots_at_exit", "exit_time",
        "exit_premium", "exit_reason", "gross_pnl", "net_pnl", "entry_qty", "status")


def _worker_init() -> None:
    global _DATA
    deny_network()
    _DATA = grid.CachedReplayData(DATA, CACHE)


def policy_for(g: dict) -> replay.ReplayPolicy:
    return replay.ReplayPolicy(name="O27F_" + digest(g), manage_every_observation=True,
                               exit_overrides=tuple(sorted(EXITS[g["exit"]].items())))


def evaluate(g: dict | None) -> tuple[str, list]:
    """Replay one genome over FULL (genome None = the passthrough parity arm). Returns (digest, compact trades)."""
    data = _DATA or grid.CachedReplayData(DATA, CACHE)
    name = "PASSTHROUGH" if g is None else digest(g)
    target = EVALS / f"{name}.json"
    if target.is_file():
        return name, json.loads(target.read_text(encoding="utf-8"))["trades"]
    pol = (replay.ReplayPolicy(name="PASSTHROUGH", manage_every_observation=bool(settings.FNO_FAST_EXIT_ENABLED))
           if g is None else policy_for(g))
    result = LabReplay(data, pol, g).run(*FULL)
    trades = [{k: t.get(k) for k in KEEP if k in t} for t in result["trades"]]
    for t in trades:
        t.setdefault("status", "CLOSED" if "net_pnl" in t else "UNRESOLVED")
    tmp = target.with_name(f"{name}.{os.getpid()}.part")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps({"genome": g, "trades": trades, "funnel": result["funnel"], "notes": result["notes"]},
                              default=str), encoding="utf-8")
    os.replace(tmp, target)
    return name, trades


def _warm(day: str) -> str:
    deny_network()
    grid.CachedReplayData(DATA, CACHE).observations(day)
    return day


# ---- metrics -----------------------------------------------------------------------------------------------------

def sessions_in(window, days) -> list[str]:
    return [d for d in days if window[0] <= d <= window[1]]


def metrics(trades: list, days: list[str]) -> dict:
    inside = set(days)
    closed = sorted((t for t in trades if t.get("net_pnl") is not None and t["entry_time"][:10] in inside),
                    key=lambda t: t["exit_time"])
    unresolved = sum(1 for t in trades if t.get("net_pnl") is None and t["entry_time"][:10] in inside)
    daily = {d: 0.0 for d in days}
    running = peak = dd = charges = stress = 0.0
    for t in closed:
        net = float(t["net_pnl"])
        daily[t["entry_time"][:10]] += net
        running += net
        peak = max(peak, running)
        dd = max(dd, peak - running)
        fee = float(t["gross_pnl"]) - net
        charges += fee
        stress += net - 2 * int(t.get("entry_qty") or 0) - 0.25 * fee
    weeks: dict = {}
    for d in days:
        weeks.setdefault(date.fromisoformat(d).isocalendar()[:2], 0.0)
        weeks[date.fromisoformat(d).isocalendar()[:2]] += daily[d]
    vals = [float(t["net_pnl"]) for t in closed]
    wins, losses = sum(v for v in vals if v > 0), -sum(v for v in vals if v < 0)
    best_day = max([0.0, *daily.values()])
    return {"sessions": len(days), "trades": len(closed), "unresolved": unresolved, "net": round(running, 2),
            "best_day": round(best_day, 2), "net_without_best_day": round(running - best_day, 2),
            "dd": round(dd, 2), "charges": round(charges, 2), "stressed": round(stress, 2),
            "win_rate": round(sum(v > 0 for v in vals) / len(vals), 4) if vals else None,
            "profit_factor": round(wins / losses, 3) if losses else None,
            "green_days": sum(v > 0 for v in daily.values()), "red_days": sum(v < 0 for v in daily.values()),
            "weeks": len(weeks), "green_weeks": sum(v > 0 for v in weeks.values()),
            "red_weeks": sum(v < 0 for v in weeks.values()), "worst_day": round(min([0.0, *daily.values()]), 2),
            "daily": {k: round(v, 2) for k, v in daily.items()},
            "exit_reasons": dict(Counter(t["exit_reason"] for t in closed))}


def fitness(m: dict) -> float:
    need = max(6, math.ceil(0.35 * m["sessions"]))
    if m["trades"] < need:
        return round(-5 + m["trades"] / need, 6)
    cs = m["net_without_best_day"] / max(m["dd"], 1000.0)
    weekly = (m["green_weeks"] - m["red_weeks"]) / max(1, m["weeks"])
    return round(cs + weekly - (1.0 if m["stressed"] <= 0 else 0.0), 6)


# ---- genomes -----------------------------------------------------------------------------------------------------

def canonical(g: dict) -> dict:
    out = {"family": g["family"]}
    for k in FAMILY_GENES[g["family"]]:
        out[k] = g[k]
    if g["family"] == "ENSEMBLE":
        members = sorted(set(out["en_members"]), key=SUBS.index)
        out["en_members"] = members
        out["en_k"] = min(out["en_k"], len(members))
    for k in SHARED_GENES:
        out[k] = g[k]
    if g.get("flip"):
        out["flip"] = True
    return out


def random_genome(family: str, rng: random.Random) -> dict:
    g = {"family": family}
    for k, alleles in FAMILY_GENES[family].items():
        if k == "en_members":
            g[k] = rng.sample(list(SUBS), rng.choice((2, 3, 4)))
        else:
            g[k] = rng.choice(alleles)
    for k, alleles in SHARED_GENES.items():
        g[k] = rng.choice(alleles)
    return canonical(g)


def seeds() -> list[dict]:
    """Declared starting points: each family with the shipped shared genes and with a let-it-run variant."""
    base = {"TREND_PULLBACK": {k: SUB_DEFAULTS[k] for k in FAMILY_GENES["TREND_PULLBACK"]},
            "PDL_BREAK": {"pd_buffer": 0.1, "pd_first": True},
            "VWAP_BAND": {"vb_k": 1.0, "vb_slope": 6},
            "MOMO_BURST": {"mb_bars": 3, "mb_move": 1.5},
            "ENSEMBLE": {"en_members": ["ORB20", "EFF"], "en_k": 1, "en_window": 1}}
    run = {**SHIPPED_SHARED, "exit": "LATE", "target_r": 2.4}
    out = []
    for family, genes in base.items():
        for shared in (SHIPPED_SHARED, run):
            out.append(canonical({"family": family, **genes, **shared}))
    out.append(canonical({"family": "ENSEMBLE", "en_members": ["ORB20", "EFF", "PDL", "VWB", "TPB"], "en_k": 2,
                          "en_window": 3, **SHIPPED_SHARED}))
    return out


def pool(track: str) -> list[dict]:
    rng = random.Random(f"{POOL['seed']}|{track}")
    families = REAL_FAMILIES if track == "REAL" else ("NULL_RANDOM",)
    out = {digest(g): g for g in (seeds() if track == "REAL" else [])}
    for family in families:
        made = 0
        while made < POOL["per_family"]:
            g = random_genome(family, rng)
            if digest(g) not in out:
                out[digest(g)] = g
                made += 1
    return list(out.values())


def _alleles(g: dict, k: str):
    return FAMILY_GENES[g["family"]][k] if k in FAMILY_GENES[g["family"]] else SHARED_GENES[k]


def mutate(g: dict, rng: random.Random) -> dict:
    g = dict(g)
    for k in [*FAMILY_GENES[g["family"]], *SHARED_GENES]:
        if rng.random() >= GA["mutation"]:
            continue
        if k == "en_members":
            members = set(g[k])
            flip = rng.choice(SUBS)
            members ^= {flip}
            if len(members) >= 2:
                g[k] = sorted(members, key=SUBS.index)
            continue
        alleles = _alleles(g, k)
        i = alleles.index(g[k])
        if rng.random() < GA["adjacent"]:
            j = i + rng.choice((-1, 1))
            if 0 <= j < len(alleles):
                g[k] = alleles[j]
        else:
            g[k] = rng.choice(alleles)
    return canonical(g)


def crossover(a: dict, b: dict, rng: random.Random) -> dict:
    """Entry genes stay with parent a's family (mixed with b only if b is the same family); shared genes mix."""
    child = {"family": a["family"]}
    for k in FAMILY_GENES[a["family"]]:
        child[k] = rng.choice((a[k], b[k])) if b["family"] == a["family"] else a[k]
    for k in SHARED_GENES:
        child[k] = rng.choice((a[k], b[k]))
    return canonical(child)


def neighbours(g: dict) -> list[dict]:
    out = []
    for k in [*FAMILY_GENES[g["family"]], *SHARED_GENES]:
        if k == "en_members":
            for s in SUBS:
                members = set(g[k]) ^ {s}
                if len(members) >= 2:
                    out.append(canonical({**g, k: sorted(members, key=SUBS.index)}))
            continue
        alleles = _alleles(g, k)
        if isinstance(alleles[0], str):
            out += [canonical({**g, k: v}) for v in alleles if v != g[k]]
        else:
            i = alleles.index(g[k])
            out += [canonical({**g, k: alleles[j]}) for j in (i - 1, i + 1) if 0 <= j < len(alleles)]
    unique = {digest(n): n for n in out if digest(n) != digest(g)}
    return list(unique.values())


# ---- search --------------------------------------------------------------------------------------------------------

class Lab:
    def __init__(self, pool_executor, days: list[str]):
        self.ex = pool_executor
        self.days = days
        self.trades: dict[str, list] = {}
        self.genomes: dict[str, dict] = {}

    def run(self, genomes: list[dict]) -> None:
        fresh = {digest(g): g for g in genomes if digest(g) not in self.trades}
        for name, trades in self.ex.map(evaluate, list(fresh.values()), chunksize=1):
            self.trades[name] = trades
        self.genomes.update(fresh)

    def m(self, name: str, window) -> dict:
        return metrics(self.trades[name], sessions_in(window, self.days))

    def fit(self, g: dict, window) -> float:
        return fitness(self.m(digest(g), window))


def evolve(lab: Lab, track: str, fold: dict, rng: random.Random, history: list) -> dict:
    """One fold's search on its training sessions only. Returns the pick and the genomes this fold saw."""
    train = fold["train"]
    seen = {digest(g): g for g in pool(track)}
    ranked = sorted(seen.values(), key=lambda g: (lab.fit(g, train), digest(g)), reverse=True)
    population = ranked[:GA["parents_from_pool"]]
    families = REAL_FAMILIES if track == "REAL" else ("NULL_RANDOM",)
    while len(population) < GA["population"]:
        population.append(random_genome(rng.choice(families), rng))
    for generation in range(GA["generations"]):
        lab.run(population)
        seen.update({digest(g): g for g in population})
        population = sorted({digest(g): g for g in population}.values(),
                            key=lambda g: (lab.fit(g, train), digest(g)), reverse=True)
        best = population[0]
        history.append({"track": track, "fold": fold["name"], "generation": generation, "best": digest(best),
                        "family": best["family"], "fitness": lab.fit(best, train),
                        "net": lab.m(digest(best), train)["net"], "evaluated_by_fold": len(seen)})
        print(f"{track} {fold['name']} gen {generation}: best {best['family']} fit={lab.fit(best, train):.3f} "
              f"net={lab.m(digest(best), train)['net']:.0f} seen={len(seen)}", flush=True)
        nxt = population[:GA["elites"]]
        nxt += [random_genome(rng.choice(families), rng) for _ in range(GA["immigrants"])]

        def pick():
            return max(rng.sample(population, GA["tournament"]), key=lambda g: (lab.fit(g, train), digest(g)))
        guard = 0
        while len(nxt) < GA["population"] and guard < 500:
            guard += 1
            child = mutate(crossover(pick(), pick(), rng), rng)
            if digest(child) not in {digest(x) for x in nxt}:
                nxt.append(child)
        population = nxt
    lab.run(population)
    seen.update({digest(g): g for g in population})
    top = sorted(seen.values(), key=lambda g: (lab.fit(g, train), digest(g)), reverse=True)[:GA["plateau_top"]]
    rows = []
    for g in top:
        near = neighbours(g)
        lab.run(near)
        seen.update({digest(n): n for n in near})
        plateau = statistics.median([lab.fit(g, train), *[lab.fit(n, train) for n in near]])
        rows.append({"genome": g, "digest": digest(g), "fitness": lab.fit(g, train), "plateau": round(plateau, 6),
                     "neighbours": len(near)})
    chosen = max(rows, key=lambda r: (r["plateau"], r["fitness"], r["digest"]))
    return {"pick": chosen, "top": rows, "seen": sorted(seen)}


def bindings() -> dict:
    files = {p.relative_to(ROOT).as_posix(): grid._sha(p) for p in sorted((ROOT / "python-engine").glob("*.py"))}
    for p in (Path(grid.__file__), HERE / "lab.py", HERE / "test_lab.py"):
        files[p.relative_to(ROOT).as_posix()] = grid._sha(p)
    return {"sources": files, "dataset": grid._verify_dataset(DATA), "settings": grid._settings_check()}


def freeze() -> None:
    deny_network()
    write_new(HERE / "freeze.json", {
        "schema": "o27f_genome_round3_v1", "bindings": bindings(), "windows": {"FULL": FULL, "A": A, "B": B},
        "folds": FOLDS, "family_genes": FAMILY_GENES, "shared_genes": SHARED_GENES, "exits": EXITS,
        "sub_defaults": SUB_DEFAULTS, "seeds": seeds(), "pool": POOL, "ga": GA, "rule": RULE,
        "qualification": "NOT_ASSESSED", "can_place_orders": False})
    print("frozen", HERE / "freeze.json")


def _reference(path: Path) -> list:
    return [{k: t.get(k) for k in KEEP if k in t} | {"entry_qty": t.get("entry_qty") or t.get("initial_qty")}
            for t in json.loads(path.read_text(encoding="utf-8"))["trades"]]


def run(jobs: int) -> None:
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    assert frozen["bindings"] == bindings(), "bound inputs changed since the freeze"
    rel = (HERE / "freeze.json").relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)) == frozen, "freeze not committed"
    assert 1 <= jobs <= 10
    deny_network()
    days = frozen["bindings"]["dataset"]["quote_days"]
    for p in (CACHE, EVALS):
        p.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(max_workers=jobs, initializer=_worker_init) as ex:
        list(ex.map(_warm, days))
        lab = Lab(ex, days)
        gate = ex.submit(evaluate, None)
        for track in ("REAL", "NULL"):
            lab.run(pool(track))
            print(f"pool {track}: {len(pool(track))} genomes", flush=True)
        # Gate: the copied entry path with genome=None must trade exactly as the shipped book (O27 CURRENT arm).
        name, trades = gate.result()
        shipped = json.loads((GRID_ARMS / "OR30__LOCK_LIVE__T45__TR1.0.json").read_text(encoding="utf-8"))["trades"]
        keys = ("bar_ts", "tradingsymbol", "entry_time", "entry_premium", "exit_time", "exit_premium", "exit_reason",
                "net_pnl")
        assert [{k: t.get(k) for k in keys} for t in trades] == [{k: t.get(k) for k in keys} for t in shipped], \
            "passthrough differs from the shipped book; abort"
        print("PARITY PASS", len(trades), round(sum(t["net_pnl"] for t in trades if "net_pnl" in t), 2), flush=True)
        history, folds = [], {}
        for track in ("REAL", "NULL"):
            for fold in FOLDS:
                rng = random.Random(f"{GA['seed']}|{track}|{fold['name']}")
                folds[f"{track}|{fold['name']}"] = evolve(lab, track, fold, rng, history)
        final_pick = folds["REAL|FINAL"]["pick"]["genome"]
        diagnostics = [canonical({**final_pick, "flip": True})]
        lab.run(diagnostics)
    assert frozen["bindings"] == bindings(), "bound inputs changed during scoring"
    references = {
        "SHIPPED": _reference(GRID_ARMS / "OR30__LOCK_LIVE__T45__TR1.0.json"),
        "O27_OR20_NOEMA_LATE_T75_TR1.5": _reference(GRID_ARMS / "OR20_NOEMA__LOCK_LATE__T75__TR1.5.json"),
    }
    o27e = O27E / "_local/FULL/ed0d136bdd80ee89.json"
    if o27e.is_file():
        references["O27E_EFFICIENCY_BREAK"] = _reference(o27e)
    write_new(LOCAL / "results-raw.json", {
        "freeze_sha256": grid._sha(HERE / "freeze.json"), "days": days, "trades": lab.trades,
        "genomes": lab.genomes, "folds": folds, "history": history, "references": references,
        "flip_digest": digest(diagnostics[0])})
    print("DONE", len(lab.trades), "replays", flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["freeze", "run"])
    cli.add_argument("--jobs", type=int, default=8)
    args = cli.parse_args()
    freeze() if args.action == "freeze" else run(args.jobs)
