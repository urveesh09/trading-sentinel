"""O29g why-study lab - research only. No runtime module imports this file.

Owner (Oct 29, after O29f): understand why the strategies lost and when they won; try combinations and published
ideas that made money in such times; test them on the year; a consistent winning effort, not a win every week.

What O29f's year showed (features.py, descriptive, both halves Jan-May and Jun-Oct): every component did better
when the market had been trending before the day - daily ADX(14), 20-day realised volatility and the 20-day move
above their usual level - and lost when it had not. The opening drive the live book gates on was not stable.

This lab tests that, plus two published ideas, through the same shipped book (O29f's BookReplay, unchanged):
  * day regime gates known before the session: ADX(14) of yesterday >= 20 or >= 25 (the textbook trend
    thresholds), and ADX / 20-day realised vol / 20-day move / yesterday's range and body above or below the
    median of the previous 60 sessions, and a trend regime = at least 2 of ADX, vol and 20-day move high;
  * NOISE_BAND - Zarattini, Aziz & Barbon (2024), "Beat the Market: an effective intraday momentum strategy for
    SPY": enter when price leaves the day's noise area, open (gap-adjusted) +/- k x the average absolute move
    from the open at that time of day over the previous 14 sessions; checked every 30 minutes (or every bar);
    exit on the VWAP-lost rule (their VWAP trail) or the book's own stops and the 15:10 flat;
  * LATE_MOMO - Gao, Han, Li & Zhou (2018, JFE), "Market intraday momentum": the first half-hour's move (or
    the day's move so far) predicts the last stretch; enter at about 14:30 in its direction, hold to the flat.
Every book is replayed once over Jan 1 - Oct 28 on the sealed O29f dataset.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import statistics
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
YEAR_STUDY = ROOT / "docs/research/fno/2026-10-29-year-genome"
sys.path[:0] = [str(ROOT / "python-engine"), str(ROOT / "scripts"), str(YEAR_STUDY), str(HERE)]
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import lab as Y  # noqa: E402  (O29f)
import features as F  # noqa: E402
import fno_policy_replay as replay  # noqa: E402
from fno_engine_mom import MomSignal  # noqa: E402
from fno_models import FnoDirection  # noqa: E402

O27F, ROUTER = Y.O27F, Y.ROUTER
LOCAL = HERE / "_local"
Y.EVALS = LOCAL / "evals"
FULL, H1, H2 = Y.FULL, ("2026-01-01", "2026-05-31"), ("2026-06-01", "2026-10-28")
REL_FEATURES = ("adx14", "rv20", "ret20_abs", "prev_range_rel", "prev_body")
REL_LOOKBACK, REL_MIN = 60, 20
GATES = ("ALWAYS", "adx_abs20:HIGH", "adx_abs25:HIGH", "adx14:HIGH", "rv20:HIGH", "ret20_abs:HIGH",
         "trend_regime:HIGH", "prev_range_rel:LOW", "prev_body:HIGH")
EXITS = O27F.EXITS
NB_HISTORY = 14


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


# ---- regime table (known before the session) ---------------------------------------------------------------------

def regime_rows(sessions: list[str], base: dict, weekly: list[str]) -> dict:
    """The O28 09:45 table plus the regime sides: each relative side compares today's value (from bars up to
    yesterday) with the median of the previous 60 sessions' values (at least 20); a missing value closes the gate."""
    feats = F.day_features(sessions, {d: {"open_drive": r.get("open_drive"), "or_width": r.get("or_width")}
                                      for d, r in base.items()}, weekly)
    order = [s for s in sessions if s in feats]
    out = {}
    for d, row in base.items():
        out[d] = {**row, "side": dict(row.get("side") or {})}
    for i, s in enumerate(order):
        f = feats[s]
        side = out.setdefault(s, {"side": {}})["side"]
        adx = f.get("adx14")
        side["adx_abs20"] = None if adx is None else ("HIGH" if adx >= 20 else "LOW")
        side["adx_abs25"] = None if adx is None else ("HIGH" if adx >= 25 else "LOW")
        for k in REL_FEATURES:
            hist = [float(feats[x][k]) for x in order[max(0, i - REL_LOOKBACK):i] if feats[x].get(k) is not None]
            v = f.get(k)
            side[k] = None if v is None or len(hist) < REL_MIN else (
                "HIGH" if float(v) > statistics.median(hist) else "LOW")
        highs = [side.get(k) == "HIGH" for k in ("adx14", "rv20", "ret20_abs")]
        side["trend_regime"] = None if any(side.get(k) is None for k in ("adx14", "rv20", "ret20_abs")) else (
            "HIGH" if sum(highs) >= 2 else "LOW")
        out[s]["features"] = f
    return out


_TABLE: dict = {}


def table(source: str) -> dict:
    if source not in _TABLE:
        base = ROUTER.condition_table() if source == "archive" else Y.condition_table("year")
        if source == "year":
            frozen = json.loads((YEAR_STUDY / "freeze.json").read_text())
            manifest = json.loads((Y.YEAR / "manifest.json").read_text())
            _TABLE[source] = regime_rows(frozen["bindings"]["year_sessions"], base,
                                         manifest["weekly_expiry_calendar"])
        else:
            _TABLE[source] = base
    return _TABLE[source]


# ---- new families ------------------------------------------------------------------------------------------------

_NB: dict = {}


def noise_bands(frame: pd.DataFrame, day: date, k: float) -> dict | None:
    """bar_ts -> (close, upper, lower) for today's bars; sigma from the previous 14 complete sessions only."""
    key = (O27F._key(frame, day), k)
    if key in _NB:
        return _NB[key]
    x = frame[~frame.index.duplicated(keep="last")].sort_index()
    out = None
    by_day = {d: b for d, b in x.groupby(x.index.date)}
    prior = [d for d in sorted(by_day) if d < day]
    if day in by_day and len(prior) >= 10:
        moves: dict[int, list] = {}
        for d in prior[-NB_HISTORY:]:
            b = by_day[d]
            if b.index[0].hour * 60 + b.index[0].minute != 555:
                continue
            o = float(b["open"].iloc[0])
            for ts, c in zip(b.index, b["close"]):
                moves.setdefault(ts.hour * 60 + ts.minute, []).append(abs(float(c) / o - 1))
        t = by_day[day]
        if t.index[0].hour * 60 + t.index[0].minute == 555:
            o = float(t["open"].iloc[0])
            prev_close = float(by_day[prior[-1]]["close"].iloc[-1])
            hi_ref, lo_ref = max(o, prev_close), min(o, prev_close)
            out = {}
            for ts, c in zip(t.index, t["close"]):
                m = ts.hour * 60 + ts.minute
                hist = moves.get(m) or []
                if len(hist) < 10:
                    continue
                sigma = statistics.fmean(hist)
                out[ts.strftime("%Y-%m-%d %H:%M:%S")] = (float(c), hi_ref * (1 + k * sigma), lo_ref * (1 - k * sigma))
    _NB[key] = out
    while len(_NB) > 600:
        _NB.pop(next(iter(_NB)))
    return out


def _signal(frame, regime, now, m: dict, direction: int | None, bar_ts: str, f: dict) -> MomSignal:
    out = MomSignal(bar_ts=bar_ts)
    if direction is None:
        out.reject_reason = f"{m['family'].lower()}:no_trigger"
        return out
    if regime == "REGIME_3_CRISIS":
        out.reject_reason = f"{m['family'].lower()}:crisis"
        return out
    row = f["t"].loc[pd.Timestamp(bar_ts)]
    close, atr = float(row["close"]), float(row["atr"])
    if not (atr > 0):
        out.reject_reason = f"{m['family'].lower()}:no_atr"
        return out
    risk = m["stop_atr"] * atr
    out.close, out.atr, out.rvol = close, atr, float(row["rvol"]) if pd.notna(row["rvol"]) else 0.0
    out.or_high, out.or_low = f["orh"] or 0.0, f["orl"] or 0.0
    out.direction = FnoDirection.LONG if direction > 0 else FnoDirection.SHORT
    out.stop_underlying = close - direction * risk
    out.target_underlying = close + direction * m["target_r"] * risk
    return out


def new_signal(m: dict, frame, regime: str, now) -> MomSignal:
    naive = now.replace(tzinfo=None)
    f = O27F.day_features(frame, naive.date())
    bar_ts = O27F.last_closed_bar(f, now) if f is not None else replay._last_closed_bar(frame, now)
    if bar_ts is None or f is None or not f["complete_open"]:
        return MomSignal(bar_ts=bar_ts or "", reject_reason="new:no_features")
    bar = pd.Timestamp(bar_ts)
    end = bar.hour * 60 + bar.minute + 5
    direction = None
    if m["family"] == "NOISE_BAND":
        bands = noise_bands(frame, naive.date(), m["k"])
        hit = bands.get(bar_ts) if bands else None
        on_check = m["check"] == "5m" or end % 30 == 0
        if hit and on_check and end >= 600:
            close, upper, lower = hit
            direction = 1 if close > upper else -1 if close < lower else None
    elif m["family"] == "LATE_MOMO":
        if 14 * 60 + 30 <= end <= 14 * 60 + 40:
            t = f["t"]
            prev_close = f["pdc"]
            if m["mode"] == "FHH":
                first = t[t["minute"] == 9 * 60 + 40]
                ref = float(first["close"].iloc[0]) if len(first) else None
            else:
                ref = float(t.loc[bar, "close"])
            if ref is not None and prev_close:
                r = ref / prev_close - 1
                direction = (1 if r > 0 else -1) if abs(r) >= m["x"] else None
    else:
        raise ValueError(m["family"])
    return _signal(frame, regime, now, m, direction, bar_ts, f)


def new_member(family: str, gate: str = "ALWAYS", **params) -> dict:
    base = {"stop_atr": 1.5, "target_r": 3.0, "exit": "RUN",
            "vwap_exit": "ON" if family == "NOISE_BAND" else "OFF"}
    return {"kind": "NEW", "family": family, "gate": gate, **base, **params}


# ---- plug the new kind into the O29f book (its functions are read at call time) -------------------------------

_policy, _vwap, _id, _sig, _canon = Y.member_policy, Y.member_vwap, Y.signal_id, Y.member_signal, Y.canonical_member


def member_policy(m):
    if m["kind"] == "NEW":
        return replay.ReplayPolicy(name="O29G_" + digest(m), manage_every_observation=True,
                                   exit_overrides=tuple(sorted(EXITS[m["exit"]].items())))
    return _policy(m)


def member_vwap(m):
    return m["vwap_exit"] == "ON" if m["kind"] == "NEW" else _vwap(m)


def signal_id(m):
    if m["kind"] == "NEW":
        return digest({k: v for k, v in m.items() if k not in ("gate", "exit", "vwap_exit")})
    return _id(m)


def member_signal(m, frame, regime, now):
    return new_signal(m, frame, regime, now) if m["kind"] == "NEW" else _sig(m, frame, regime, now)


def canonical_member(m):
    return dict(m) if m["kind"] == "NEW" else _canon(m)


Y.member_policy, Y.member_vwap, Y.signal_id, Y.member_signal, Y.canonical_member = (
    member_policy, member_vwap, signal_id, member_signal, canonical_member)
Y.table = table


# ---- the frozen book list ----------------------------------------------------------------------------------------

def gated(book: dict, gate: str) -> dict:
    return Y.book_of([{**m, "gate": gate} for m in book["members"]])


def books() -> dict:
    out = {}
    for c in Y.NAMED:
        for g in GATES:
            out[f"{c}|{g}"] = Y.book_of([Y.named(c, g)])
    for g in GATES[1:]:
        out[f"UNION_ALL|{g}"] = Y.book_of([Y.named(c, g) for c in Y.NAMED])
        out[f"TPB_PLUS_BREAKOUTS|{g}"] = Y.book_of([Y.named("TPB")] + [Y.named(c, g) for c in ("SHIPPED", "OR20", "EFF")])
    out["UNION_DRIVE_LIVE"] = Y.FIXED["UNION_DRIVE"]
    for k in (1.0, 1.5):
        for check in ("30m", "5m"):
            for g in ("ALWAYS", "adx_abs20:HIGH", "trend_regime:HIGH"):
                out[f"NOISE_BAND|k{k}|{check}|{g}"] = Y.book_of([new_member("NOISE_BAND", g, k=k, check=check)])
    for mode in ("FHH", "DAY"):
        for x in (0.003, 0.006):
            for g in ("ALWAYS", "rv20:HIGH"):
                out[f"LATE_MOMO|{mode}|{x}|{g}"] = Y.book_of([new_member("LATE_MOMO", g, mode=mode, x=x)])
    nb = new_member("NOISE_BAND", "adx_abs20:HIGH", k=1.0, check="30m")
    lm = new_member("LATE_MOMO", "rv20:HIGH", mode="FHH", x=0.003)
    out["COMBO|TPB+NB"] = Y.book_of([Y.named("TPB"), new_member("NOISE_BAND", k=1.0, check="30m")])
    out["COMBO|TPB+NB_adx20"] = Y.book_of([Y.named("TPB"), nb])
    out["COMBO|TPB+LM"] = Y.book_of([Y.named("TPB"), new_member("LATE_MOMO", mode="FHH", x=0.003)])
    out["COMBO|TPB+NB_adx20+LM_rv"] = Y.book_of([Y.named("TPB"), nb, lm])
    for i, b in enumerate(Y.null_fixed()):
        out[f"NULL{i:02d}|ALWAYS"] = b
        out[f"NULL{i:02d}|adx_abs20:HIGH"] = gated(b, "adx_abs20:HIGH")
        out[f"NULL{i:02d}|trend_regime:HIGH"] = gated(b, "trend_regime:HIGH")
    return out


RULE = {
    "status": "IN-SAMPLE on Jan 1 - Oct 28: the regime idea came from looking at this year (features.py), so a good "
              "full-year result is a hypothesis, not proof",
    "selection_check": "two-fold: per component, the gate with the best H1 (Jan-May) net-without-best-day is scored "
                       "on H2 (Jun-Oct), and the H2 choice on H1; it counts only if it beats ALWAYS on the other half "
                       "in both directions for most components",
    "luck_check": "the same gates on the 20 random-entry books: a gate that also lifts random entries is capturing "
                  "the regime, not the entry",
    "clean_tests_next": "NIFTY 2025 sessions never seen (if Breeze serves them), SENSEX 2026, and the forward panel",
}


def bindings() -> dict:
    files = {p.relative_to(ROOT).as_posix(): Y.grid._sha(p) for p in sorted((ROOT / "python-engine").glob("*.py"))}
    for p in (YEAR_STUDY / "lab.py", YEAR_STUDY / "yeardata.py", HERE / "lab_g.py", HERE / "features.py",
              HERE / "test_lab_g.py", Y.ROUTER_PY, Y.ROUTER.O27F_LAB, Y.ROUTER.O27E_LAB):
        files[p.relative_to(ROOT).as_posix()] = Y.grid._sha(p)
    return {"sources": files, "year_manifest_sha256": Y.grid._sha(Y.YEAR / "manifest.json"),
            "daily_bars_sha256": hashlib.sha256(F.daily_bars().to_csv().encode()).hexdigest(),
            "settings": Y.grid._settings_check()}


def freeze() -> None:
    Y.write_new(HERE / "freeze.json", {"schema": "o29g_why_study_v1", "bindings": bindings(), "gates": GATES,
                                       "books": books(), "rule": RULE, "qualification": "NOT_ASSESSED",
                                       "can_place_orders": False})
    print("frozen", len(books()), "books")


def _init() -> None:
    Y._worker_init()


def run(jobs: int) -> None:
    frozen = json.loads((HERE / "freeze.json").read_text())
    assert frozen["bindings"] == bindings(), "bound inputs changed since the freeze"
    rel = (HERE / "freeze.json").relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)) == frozen, "freeze not committed"
    Y.EVALS.mkdir(parents=True, exist_ok=True)
    O27F.deny_network()
    all_books = books()
    with ProcessPoolExecutor(max_workers=jobs, initializer=_init) as ex:
        runner = Y.Runner(ex, jobs)
        runner.run(list(all_books.values()))
    Y.write_new(LOCAL / "results-raw.json", {"freeze_sha256": Y.grid._sha(HERE / "freeze.json"),
                                             "books": {n: Y.task_key(b, "year", FULL) for n, b in all_books.items()},
                                             "trades": runner.trades})
    print("DONE", len(runner.trades), flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["freeze", "run"])
    cli.add_argument("--jobs", type=int, default=5)
    args = cli.parse_args()
    freeze() if args.action == "freeze" else run(args.jobs)
