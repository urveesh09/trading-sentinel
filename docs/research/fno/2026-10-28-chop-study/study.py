"""O29b chop study - research only. No runtime module imports this file.

Oct 28 2026 was a two-way day: NIFTY broke above its opening range, fell back through it, broke below it, and rallied
back to a new high. Every breakout strategy lost; "all four together" (O28b panel C, UNION) lost Rs 5,955.

The owner asked (Oct 28 evening): why did it go so bad, on what kind of days should these strategies not be used, how
do we find that out in time, and is there a strategy that makes money on such days. This study answers with three
tracks, all through the shipped single-leg book (planner, sizing, brakes, exit ladder, costs, ask/bid fills;
fno_policy_replay unchanged), over every archived session Sep 10 - Oct 28:

  G  the four studied strategies (SHIPPED, OR20, EFF, TPB) behind intraday "day-state" filters, read at the signal
     bar only from bars already closed: the 09:45 opening drive (O28), a failed opening-range break so far, the
     session's efficiency so far, VWAP crosses so far, the share of the usual daily range already used;
  F  fades: buy the option against a failed opening-range break (FADE), or back toward VWAP after a band rejection
     on a low-efficiency session (VWAP_REVERT); a random-entry NULL track with the same budget is the control;
  S  "smart" books: the breakouts behind one filter, TPB always on, plus one fade (or none).

Selection is an anchored walk-forward: each fold picks on its training sessions only, and is scored on the sessions
after them. The last fold's test block is Oct 27-28 (Oct 27 is the NIFTY expiry: the shipped book takes no entry).
Every session was seen by earlier studies and Oct 28 is the day that prompted this one: a pick is a forward-test
candidate, never a promotion. Production is read-only: the dataset is the forward panel's read-only export.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import itertools
import json
import math
import os
import pickle
import shutil
import socket
import sqlite3
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
sys.path[:0] = [str(ROOT / "python-engine"), str(ROOT / "scripts")]
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


router = _load(ROOT / "docs/research/fno/2026-10-28-regime-router/router.py", "o28_router")
O27F, replay, grid = router.O27F, router.replay, router.grid
from config import settings  # noqa: E402
from fno_engine_mom import MomSignal  # noqa: E402
from fno_models import FnoDirection  # noqa: E402

LOCAL = HERE / "_local"
DATA = LOCAL / "dataset"
CACHE = LOCAL / "observations"
EVALS = LOCAL / "evals"
SIGNALS = LOCAL / "signals.pkl"
O28_CACHE = ROOT / "docs/research/fno/2026-10-28-regime-router/_local/observations"
NOV_FUTURE = {15736578: "2026-11-23"}  # NIFTY26NOVFUT, the front future from Oct 28 (checked in prepare)

FULL = ("2026-09-10", "2026-10-28")
TODAY = "2026-10-28"
FOLDS = (
    {"name": "F1", "train": ("2026-09-10", "2026-09-30"), "test": ("2026-10-01", "2026-10-09")},
    {"name": "F2", "train": ("2026-09-10", "2026-10-09"), "test": ("2026-10-12", "2026-10-16")},
    {"name": "F3", "train": ("2026-09-10", "2026-10-16"), "test": ("2026-10-19", "2026-10-26")},
    {"name": "F4", "train": ("2026-09-10", "2026-10-26"), "test": ("2026-10-27", "2026-10-28")},
    {"name": "FINAL", "train": ("2026-09-10", "2026-10-28"), "test": None},
)
BASE = ("SHIPPED", "OR20", "EFF", "TPB")
BREAKOUTS = ("SHIPPED", "OR20", "EFF")
# Filters read at the signal bar from closed bars only. "+" joins two that must both hold.
GATES = ("ALWAYS", "drive:HIGH", "nofail", "er:0.2", "er:0.3", "vx:3", "used:0.8", "nofail+er:0.2")
FADE_GENES = {"level": ("OR30", "OR20"), "within": (1, 2, 3), "buffer": (0.0, 0.1),
              "stop": ("STRUCT", 1.0, 1.5), "target_r": (1.8, 2.4), "exit": ("LIVE", "LATE"), "window": ("ALL", "AM")}
VR_GENES = {"k": (1.0, 1.5, 2.0), "er_below": (0.2, 0.3, 1.0), "stop": (1.0, 1.5), "target_r": (1.8, 2.4),
            "exit": ("LIVE", "LATE")}
NULL_GENES = {"p": (0.02, 0.04, 0.08), "seed": tuple(range(16))}
FADE_TOP = 3  # each fold's best fades (training fitness) tried inside the smart books
EXTREME_DAY = -5000.0  # 2% of the Rs 2,50,000 paper bankroll (the panel C bound)
RULE = {
    "metrics": "trades by entry day; net after recorded charges; drawdown over closed trades in exit order",
    "min_trades": "max(4, ceil(0.25 * sessions in the slice))",
    "fitness": "(net - best day) / max(max drawdown, 1000); below min trades: -5 + trades / min; ties: net, then key",
    "G_verdict": "a strategy's filter helps only if its walk-forward picks' out-of-sample net (F1-F4 tests) beats the "
                 "unfiltered strategy on the same sessions and its worst out-of-sample day is no worse",
    "F_verdict": "fades work only if the walk-forward fade picks' out-of-sample net is > 0, at least 2 of the 3 "
                 "multi-session folds (F1-F3) are > 0, and it beats the NULL track's picks out of sample",
    "S_verdict": "a smart book helps only if its walk-forward picks' out-of-sample net beats both SHIPPED and UNION on "
                 "the same sessions with no out-of-sample day worse than Rs -5,000",
    "candidate": "the FINAL fold's picks are forward-test candidates only (panel D); nothing is promoted on seen data, "
                 "and nothing changes the paper or live books in the proving week",
}


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


def deny_network() -> None:
    def denied(*_a, **_k):
        raise RuntimeError("O29b offline research: network prohibited")
    socket.socket.connect = denied
    socket.socket.connect_ex = denied
    socket.create_connection = denied
    socket.getaddrinfo = denied


router.NIFTY_FUTURES.update(NOV_FUTURE)


# ---- the day state at each closed bar -----------------------------------------------------------------------------

def futures_bars(db: Path = DATA / "fno-replay.sqlite") -> dict[int, pd.DataFrame]:
    con = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
    try:
        out = {}
        for token in router.NIFTY_FUTURES:
            rows = con.execute("SELECT datetime, open, high, low, close, volume FROM fut_candles WHERE "
                               "instrument_token=? AND interval='5minute' ORDER BY datetime", (token,)).fetchall()
            frame = pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close", "volume"])
            frame.index = pd.to_datetime(frame.pop("datetime"))
            out[token] = frame[~frame.index.duplicated(keep="last")].sort_index()
        return out
    finally:
        con.close()


def bar_states(bars: dict[int, pd.DataFrame] | None = None) -> dict[str, dict[str, dict]]:
    """day -> bar_ts -> the day so far at that bar's close (reads that bar, earlier bars and prior sessions only):
      er     |close - day open| / (path of closes from the open): 1 = one-way, near 0 = back and forth;
      failed a close beyond the 30-minute opening range after 09:45, then a close back inside it;
      vx     how often the close crossed the session VWAP;
      used   (high - low so far) / the average range of the 5 sessions before;
      drive  the O28 09:45 opening-drive side (HIGH / LOW / None), the same on every bar of the day."""
    bars = futures_bars() if bars is None else bars
    sides = router.with_sides(router.day_rows({t: f[["open", "high", "low", "close"]] for t, f in bars.items()}))
    out: dict = {}
    for token, frame in bars.items():
        days = sorted(set(frame.index.date))
        ranges = {d: float(frame[frame.index.date == d]["high"].max() - frame[frame.index.date == d]["low"].min())
                  for d in days}
        for n, day in enumerate(days):
            if router.front_token(day) != token:
                continue
            b = frame[frame.index.date == day]
            mins = b.index.hour * 60 + b.index.minute
            if not len(b) or mins[0] != 555:
                continue
            adr5 = statistics.fmean(ranges[d] for d in days[n - 5:n]) if n >= 5 else None
            orb = b[mins < 585]
            orh, orl = (float(orb["high"].max()), float(orb["low"].min())) if len(orb) == 6 else (None, None)
            day_open = float(b["open"].iloc[0])
            drive = (sides.get(day.isoformat()) or {}).get("side", {}).get("open_drive")
            path, prev, hi, lo = 0.0, day_open, -math.inf, math.inf
            cpv = cv = 0.0
            sign, crosses, outside, failed = 0, 0, False, False
            states = {}
            for ts, row in b.iterrows():
                c = float(row["close"])
                path += abs(c - prev)
                prev = c
                hi, lo = max(hi, float(row["high"])), min(lo, float(row["low"]))
                tp, vol = (row["high"] + row["low"] + c) / 3, float(row["volume"] or 0.0)
                cpv, cv = cpv + tp * vol, cv + vol
                vwap = cpv / cv if cv > 0 else tp
                s = 1 if c > vwap else -1 if c < vwap else 0
                if s and sign and s != sign:
                    crosses += 1
                sign = s or sign
                minute = ts.hour * 60 + ts.minute
                if orh is not None and minute >= 585:
                    beyond = c > orh or c < orl
                    if outside and not beyond:
                        failed = True
                    outside = outside or beyond
                states[ts.strftime("%Y-%m-%d %H:%M:%S")] = {
                    "er": abs(c - day_open) / path if path > 0 else 0.0, "failed": failed, "vx": crosses,
                    "used": (hi - lo) / adr5 if adr5 else None, "drive": drive}
            out[day.isoformat()] = states
    return out


def gate_ok(rule: str, state: dict | None) -> bool:
    if rule == "ALWAYS":
        return True
    if rule == "NEVER" or state is None:
        return False
    for part in rule.split("+"):
        kind, _, arg = part.partition(":")
        if kind == "drive":
            ok = state["drive"] == arg
        elif kind == "nofail":
            ok = not state["failed"]
        elif kind == "er":
            ok = state["er"] >= float(arg)
        elif kind == "erlt":
            ok = state["er"] < float(arg)
        elif kind == "vx":
            ok = state["vx"] < int(arg)
        elif kind == "used":
            ok = state["used"] is not None and state["used"] <= float(arg)
        else:
            raise ValueError(rule)
        if not ok:
            return False
    return True


# ---- fades and the random control ----------------------------------------------------------------------------------

def fade_genomes() -> list[dict]:
    out = [{"family": "FADE", **dict(zip(FADE_GENES, v))} for v in itertools.product(*FADE_GENES.values())]
    out += [{"family": "VWAP_REVERT", **dict(zip(VR_GENES, v))} for v in itertools.product(*VR_GENES.values())]
    return out


def null_genomes() -> list[dict]:
    return [{"family": "NULL", "p": p, "seed": s, "stop": 1.5, "target_r": 1.8, "exit": "LIVE"}
            for p in NULL_GENES["p"] for s in NULL_GENES["seed"]]


_TABLES: dict = {}


def fade_table(g: dict, f: dict) -> dict:
    """bar_ts -> (direction, close, atr, rvol, stop, target) for one genome on one session (causal per bar)."""
    key = (digest(g), f["day"].isoformat(), f["stamps"][-1], len(f["stamps"]))
    if key in _TABLES:
        return _TABLES[key]
    t = f["t"]
    c, h, l = t["close"].values, t["high"].values, t["low"].values
    atr, m = t["atr"].values, t["minute"].values
    vwap, vsd = t["vwap"].values, t["vsd"].values
    rvol = t["rvol"].fillna(0.0).values
    day_open = f["day_open"]
    path = np.cumsum(np.abs(np.diff(np.concatenate([[day_open], c]))))
    er = np.where(path > 0, np.abs(c - day_open) / np.where(path > 0, path, 1.0), 0.0)
    out: dict = {}
    done = set()

    def put(i, d, stop):
        risk = abs(c[i] - stop)
        if risk <= 0 or not atr[i] > 0:
            return
        out[f["stamps"][i]] = (d, float(c[i]), float(atr[i]), float(rvol[i]), float(stop),
                               float(c[i] + d * g["target_r"] * risk))
        done.add(d)

    fam = g["family"]
    if fam == "FADE":
        n = 6 if g["level"] == "OR30" else 4
        if len(t) < n or m[n - 1] != 555 + 5 * (n - 1):
            _TABLES[key] = out
            return out
        orh, orl = float(h[:n].max()), float(l[:n].min())
        for i in range(n + 1, len(t)):
            if g["window"] == "AM" and m[i] + 5 > 12 * 60 + 30:
                break
            lo_j = max(n, i - g["within"])
            for d, level in ((-1, orh), (1, orl)):
                if d in done:
                    continue
                broke = [j for j in range(lo_j, i) if (c[j] - level) * -d > g["buffer"] * atr[j]]
                if not broke or (c[i] - level) * -d >= 0 or (c[i - 1] - level) * -d < 0:
                    continue
                j0 = broke[0]
                if g["stop"] == "STRUCT":
                    stop = (h[j0:i + 1].max() + 0.25 * atr[i]) if d < 0 else (l[j0:i + 1].min() - 0.25 * atr[i])
                else:
                    stop = c[i] - d * g["stop"] * atr[i]
                put(i, d, stop)
    elif fam == "VWAP_REVERT":
        for i in range(1, len(t)):
            if m[i] < 585 or not vsd[i] > 0:
                continue
            for d, upper in ((-1, True), (1, False)):
                if d in done or er[i] >= g["er_below"]:
                    continue
                band, prev_band = (vwap[i] + g["k"] * vsd[i], vwap[i - 1] + g["k"] * vsd[i - 1]) if upper else (
                    vwap[i] - g["k"] * vsd[i], vwap[i - 1] - g["k"] * vsd[i - 1])
                if (c[i - 1] - prev_band) * -d > 0 and (c[i] - band) * -d < 0:
                    put(i, d, c[i] - d * g["stop"] * atr[i])
    elif fam == "NULL":
        for i, stamp in enumerate(f["stamps"]):
            if m[i] >= 585 and O27F._null_uniform(g["seed"], stamp, "fire") < g["p"]:
                d = 1 if O27F._null_uniform(g["seed"], stamp, "side") < 0.5 else -1
                put(i, d, c[i] - d * g["stop"] * atr[i])
                done.clear()
    else:
        raise ValueError(fam)
    _TABLES[key] = out
    if len(_TABLES) > 4000:
        _TABLES.pop(next(iter(_TABLES)))
    return out


def fade_signal(g: dict, frame: pd.DataFrame, regime: str, now, bar_ts: str | None) -> MomSignal:
    out = MomSignal()
    out.bar_ts = bar_ts or ""
    f = O27F.day_features(frame, now.replace(tzinfo=None).date())
    if bar_ts is None or f is None or not f["complete_open"]:
        out.reject_reason = "o29b:no_features"
        return out
    hit = fade_table(g, f).get(bar_ts)
    if hit is None:
        out.reject_reason = "o29b:no_trigger"
        return out
    if regime == "REGIME_3_CRISIS":
        out.reject_reason = "o29b:crisis"
        return out
    d, out.close, out.atr, out.rvol, out.stop_underlying, out.target_underlying = hit
    out.or_high, out.or_low = f["orh"] or 0.0, f["orl"] or 0.0
    out.direction = FnoDirection.LONG if d > 0 else FnoDirection.SHORT
    return out


def fade_policy(g: dict) -> replay.ReplayPolicy:
    return replay.ReplayPolicy(name="O29B_" + digest(g), manage_every_observation=True,
                               exit_overrides=tuple(sorted(O27F.EXITS[g["exit"]].items())))


# ---- the book -----------------------------------------------------------------------------------------------------

def comp_name(entry: list) -> str:
    return entry[0] if entry[0] != "F" else "F:" + digest(entry[2])


class ChopReplay(router.RouterReplay):
    """The O28 router's book (the shipped _entry and _manage unchanged; each leg managed with its own strategy's
    exits) with components in a declared order, each behind its own filter read from ``states`` at the signal bar."""

    def __init__(self, data, config: dict, states: dict, memo: dict, warm: bool = False):
        self.comps = [(comp_name(e), e[1], e[2] if e[0] == "F" else None) for e in config["comps"]]
        for name, _rule, g in self.comps:
            if g is not None:
                router._POLICIES[name] = fade_policy(g)
        super().__init__(data, config, {}, memo, warm=warm)
        self.states = states

    def route(self, frame, regime, now) -> MomSignal:
        bar_ts = replay._last_closed_bar(frame, now)
        state = self.states.get(now.date().isoformat(), {}).get(bar_ts) if bar_ts else None
        for name, rule, g in self.comps:
            if not (gate_ok(rule, state) or self.warm):
                continue
            sig = (self._signal(name, frame, regime, now, bar_ts) if g is None
                   else fade_signal(g, frame, regime, now, bar_ts))
            if sig.direction is not None and not self.warm:
                self._fired = name
                return sig
        return MomSignal(bar_ts=bar_ts or "", reject_reason="router:no_component")


def single(comp, rule: str = "ALWAYS") -> dict:
    return {"comps": [["F", rule, comp]] if isinstance(comp, dict) else [[comp, rule, None]]}


def smart(gate: str, fade: dict | None, tpb: bool = True) -> dict:
    comps = [[c, gate, None] for c in BREAKOUTS] + ([["TPB", "ALWAYS", None]] if tpb else [])
    return {"comps": comps + ([["F", "ALWAYS", fade]] if fade else [])}


UNION = smart("ALWAYS", None)
UNION_DRIVE = smart("drive:HIGH", None)


# ---- running -------------------------------------------------------------------------------------------------------

KEEP = (*O27F.KEEP, "component")
_DATA = _STATES = _MEMO = None


def _worker_init() -> None:
    global _DATA, _STATES, _MEMO
    deny_network()
    _DATA = grid.CachedReplayData(DATA, CACHE)
    _STATES = bar_states()
    _MEMO = pickle.loads(SIGNALS.read_bytes()) if SIGNALS.is_file() else {}


def warm_day(day: str) -> tuple[str, dict, int]:
    """The four studied strategies' signals at every entry tick of one session (signals never read the book)."""
    deny_network()
    memo: dict = {}
    with router.dispatch():
        book = ChopReplay(grid.CachedReplayData(DATA, CACHE), {"comps": [[c, "ALWAYS", None] for c in BASE]}, {},
                          memo, warm=True)
        book.run(day, day)
    return day, memo, int(book.notes.get("memo_conflict", 0))


def evaluate(config: dict) -> tuple[str, list]:
    name = digest(config)
    target = EVALS / f"{name}.json"
    if target.is_file():
        return name, json.loads(target.read_text(encoding="utf-8"))["trades"]
    with router.dispatch():
        book = ChopReplay(_DATA, config, _STATES, _MEMO)
        result = book.run(*FULL)
    trades = [{k: t.get(k) for k in KEEP if k in t} for t in result["trades"]]
    for t in trades:
        t.setdefault("status", "CLOSED" if "net_pnl" in t else "UNRESOLVED")
    tmp = target.with_name(f"{name}.{os.getpid()}.part")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps({"config": config, "trades": trades, "funnel": result["funnel"],
                               "notes": result["notes"], "memo_miss": book.notes.get("memo_miss", 0)},
                              default=str), encoding="utf-8")
    os.replace(tmp, target)
    return name, trades


def sessions() -> list[str]:
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    return sorted(d for d in manifest["quote_days"] if FULL[0] <= d <= FULL[1])


def in_window(window, days) -> list[str]:
    return [d for d in days if window[0] <= d <= window[1]]


def metrics(trades: list, days: list[str]) -> dict:
    keep = set(days)
    closed = [t for t in trades if t.get("status") == "CLOSED" and t["bar_ts"][:10] in keep]
    by_day = {d: 0.0 for d in days}
    for t in closed:
        by_day[t["bar_ts"][:10]] += t["net_pnl"]
    equity = peak = dd = 0.0
    for t in sorted(closed, key=lambda t: t["exit_time"]):
        equity += t["net_pnl"]
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
    net = round(sum(by_day.values()), 2)
    best = max([0.0, *by_day.values()])
    worst = min([0.0, *by_day.values()])
    return {"trades": len(closed), "net": net, "net_ex_best": round(net - best, 2), "worst_day": round(worst, 2),
            "max_dd": round(dd, 2), "green": sum(v > 0 for v in by_day.values()),
            "red": sum(v < 0 for v in by_day.values()), "by_day": {d: round(v, 2) for d, v in by_day.items() if v},
            "unresolved": sum(1 for t in trades if t.get("status") != "CLOSED" and t["bar_ts"][:10] in keep)}


def fitness(m: dict, n_sessions: int) -> float:
    need = max(4, math.ceil(0.25 * n_sessions))
    if m["trades"] < need:
        return -5 + m["trades"] / need
    return m["net_ex_best"] / max(m["max_dd"], 1000.0)


def pick(keys: list[str], trades: dict, train: list[str]) -> str:
    scored = [(fitness(metrics(trades[k], train), len(train)), metrics(trades[k], train)["net"], k) for k in keys]
    return max(scored, key=lambda s: (s[0], s[1], s[2]))[2]


def freeze() -> dict:
    gates = {c: [single(c, g) for g in GATES] for c in BASE}
    frozen = {"study": "O29b", "rule": RULE, "folds": FOLDS, "gates": GATES, "fade_genes": FADE_GENES,
              "vr_genes": VR_GENES, "null_genes": NULL_GENES, "fade_top": FADE_TOP,
              "counts": {"gated": sum(len(v) for v in gates.values()), "fades": len(fade_genomes()),
                         "nulls": len(null_genomes())},
              "baselines": {"UNION": UNION, "UNION_DRIVE": UNION_DRIVE},
              "sources_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (Path(__file__), router.HERE / "router.py", Path(O27F.__file__))},
              "seen": "every session was seen by O27-O28; Oct 28 prompted this study"}
    return frozen


def _parallel(fn, items, jobs, init=_worker_init):
    with ProcessPoolExecutor(max_workers=jobs, initializer=init) as pool:
        return list(pool.map(fn, items, chunksize=1))


def prepare(source: Path, jobs: int) -> None:
    """Copy the forward panel's read-only export, reuse O28's parsed sessions for the sealed days it parsed, parse
    the rest, check the November contract, and warm the four strategies' signals."""
    if not DATA.exists():
        shutil.copytree(source, DATA)
    CACHE.mkdir(parents=True, exist_ok=True)
    for pkl in O28_CACHE.glob("*.pkl"):
        if not (CACHE / pkl.name).exists():
            shutil.copyfile(pkl, CACHE / pkl.name)
    days = sessions()
    _parallel(grid._warm, [(str(DATA), str(CACHE), d) for d in days if not (CACHE / f"{d}.pkl").exists()], jobs,
              init=deny_network)
    obs, _ = grid.CachedReplayData(DATA, CACHE).observations(TODAY)
    contract = obs[0].future.contract
    assert {contract.token: str(contract.expiry)} == {k: v for k, v in NOV_FUTURE.items()}, contract
    if not SIGNALS.exists():
        memo, conflicts = {}, 0
        for _day, part, bad in _parallel(warm_day, days, jobs, init=deny_network):
            memo.update(part)
            conflicts += bad
        assert conflicts == 0, conflicts
        SIGNALS.write_bytes(pickle.dumps(memo, protocol=pickle.HIGHEST_PROTOCOL))
    print("prepared", len(days), "sessions")


def run(jobs: int) -> dict:
    deny_network()
    days = sessions()
    states = bar_states()
    configs = {}
    for c in BASE:
        for g in GATES:
            configs[digest(single(c, g))] = single(c, g)
    for g in fade_genomes() + null_genomes():
        configs[digest(single(g))] = single(g)
    for cfg in (UNION, UNION_DRIVE):
        configs[digest(cfg)] = cfg
    trades = dict(_parallel(evaluate, list(configs.values()), jobs))
    fades = [digest(single(g)) for g in fade_genomes()]
    nulls = [digest(single(g)) for g in null_genomes()]
    folds = []
    smart_configs = {}
    for fold in FOLDS:
        train = in_window(fold["train"], days)
        top = sorted(fades, key=lambda k: (fitness(metrics(trades[k], train), len(train)),
                                           metrics(trades[k], train)["net"], k), reverse=True)[:FADE_TOP]
        cands = [smart(g, None) for g in GATES] + [smart(g, configs[k]["comps"][0][2]) for g in GATES for k in top]
        for cfg in cands:
            smart_configs[digest(cfg)] = cfg
        folds.append({"fold": fold, "train": train, "top_fades": top, "smart": [digest(c) for c in cands]})
    trades.update(dict(_parallel(evaluate, [c for k, c in smart_configs.items() if k not in trades], jobs)))
    configs.update(smart_configs)
    out = {"sessions": days, "folds": []}
    for f in folds:
        fold, train = f["fold"], f["train"]
        test = in_window(fold["test"], days) if fold["test"] else []
        row = {"name": fold["name"], "train": fold["train"], "test": fold["test"], "picks": {}}
        for c in BASE:
            row["picks"][f"G:{c}"] = pick([digest(single(c, g)) for g in GATES], trades, train)
        row["picks"]["F"] = pick(fades, trades, train)
        row["picks"]["NULL"] = pick(nulls, trades, train)
        row["picks"]["S"] = pick(f["smart"], trades, train)
        row["top_fades"] = f["top_fades"]
        if test:
            row["test_metrics"] = {k: metrics(trades[v], test) for k, v in row["picks"].items()}
            row["baselines"] = {name: metrics(trades[digest(cfg)], test) for name, cfg in
                                (("SHIPPED", single("SHIPPED")), ("UNION", UNION), ("UNION_DRIVE", UNION_DRIVE),
                                 *((f"ungated:{c}", single(c)) for c in BASE))}
        out["folds"].append(row)
    out["configs"] = configs
    out["full"] = {k: metrics(v, days) for k, v in trades.items()}
    out["today"] = {k: metrics(v, [TODAY]) for k, v in trades.items()}
    (LOCAL / "results-raw.json").write_text(json.dumps({"trades": trades, **out}, default=str), encoding="utf-8")
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("freeze", "prepare", "run"))
    p.add_argument("--source", type=Path)
    p.add_argument("--jobs", type=int, default=8)
    a = p.parse_args()
    if a.command == "freeze":
        target = HERE / "freeze.json"
        if target.exists():
            raise SystemExit("freeze.json exists")
        target.write_text(json.dumps(freeze(), indent=1, default=str), encoding="utf-8", newline="\n")
    elif a.command == "prepare":
        prepare(a.source, a.jobs)
    else:
        frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
        assert frozen["sources_sha256"] == freeze()["sources_sha256"], "study code changed since the freeze"
        run(a.jobs)


if __name__ == "__main__":
    main()
