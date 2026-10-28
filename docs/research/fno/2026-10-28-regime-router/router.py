"""O28 regime router - research only. No runtime module imports this file.

Owner question (Oct 28): under what market condition did the best strategies win, can that condition be known in
time, and does deploying each strategy only under its condition do better than running them unconditionally?

Components, each exactly as it was studied (the run aborts unless each one, routed alone, reproduces its own stored
trades):
  SHIPPED  the shipped 30-minute opening-range break (CURRENT)
  OR20     the O27 grid's OR20 break, no EMA check, late lock, 75-minute time stop, 1.5-ATR trail
  EFF      the O27e efficiency-break finalist
  TPB      the O27f trend-day VWAP pullback (the live shadow FNO_TREND_PULLBACK and its replay arm)

Conditions: five day-level features known at 09:45 (today's 09:15-09:40 bars and earlier sessions only). Each is
split HIGH / LOW at the median of the same feature over the previous 20 sessions. A router gives every component
ALWAYS, NEVER or one condition (feature:side). Every router is replayed once over FULL through the shipped single-leg
book: one pool, one set of brakes and trade limits, and each leg keeps its own component's exits. Window metrics are
slices of that one causal path.

Production is read-only: the dataset is the existing read-only export. No broker calls, no orders.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import pickle
import random
import socket
import sqlite3
import statistics
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
sys.path[:0] = [str(ROOT / "python-engine"), str(ROOT / "scripts")]
import pandas as pd  # noqa: E402

import fno_policy_replay as replay  # noqa: E402
import fno_shadow  # noqa: E402
import run_fno_consistency_grid as grid  # noqa: E402
from fno_engine_mom import MomSignal, evaluate_fno_mom  # noqa: E402


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


O27F_LAB = ROOT / "docs/research/fno/2026-10-27-genome-round3/lab.py"
O27E_LAB = ROOT / "docs/research/simulation/2026-10-27-fno-novel-families/lab.py"
O27F = _load(O27F_LAB, "o27f_lab")
O27E = _load(O27E_LAB, "o27e_lab")
_ORIGINAL = fno_shadow._variant_signal

DATA = ROOT / "docs/research/fno/2026-10-27-consistency-grid/_local/dataset"
LOCAL = HERE / "_local"
CACHE = LOCAL / "observations"
EVALS = LOCAL / "evals"
SIGNALS = LOCAL / "signals.pkl"
FULL, FOLDS = O27F.FULL, O27F.FOLDS

COMPONENTS = ("SHIPPED", "OR20", "EFF", "TPB")  # declared priority when two signal on the same tick
OR20_ARM = "OR20_NOEMA|LOCK_LATE|T75|TR1.5"
EFF_GENOME = {"family": "EFFICIENCY_BREAK", "lookback": 4, "efficiency": 0.35, "buffer": 0.2, "body": 0.55,
              "vwap": False, "compression": 3.0, "rvol": 1.2, "stop": 2.0, "target": 1.8, "exit": "LOOSE"}
REFERENCES = {  # each component's own stored trades over FULL (the parity gate)
    "SHIPPED": "docs/research/fno/2026-10-27-consistency-grid/_local/arms/OR30__LOCK_LIVE__T45__TR1.0.json",
    "OR20": "docs/research/fno/2026-10-27-consistency-grid/_local/arms/OR20_NOEMA__LOCK_LATE__T75__TR1.5.json",
    "EFF": "docs/research/simulation/2026-10-27-fno-novel-families/_local/FULL/ed0d136bdd80ee89.json",
    "TPB": "docs/research/fno/2026-10-27-genome-round3/_local/evals/a6d7762768c82811.json",
}
PARITY_KEYS = ("bar_ts", "tradingsymbol", "entry_time", "entry_premium", "exit_time", "exit_premium", "exit_reason",
               "net_pnl")
NIFTY_FUTURES = {17512194: "2026-09-29", 12468226: "2026-10-27"}  # token -> expiry, from the archived quotes

FEATURES = ("or_width", "open_drive", "nr", "gap", "trend5")
FEATURE_TEXT = {
    "or_width": "09:15-09:45 opening range / mean range of the previous 5 sessions (narrow initial balance -> "
                "trend-day potential; Market Profile)",
    "open_drive": "efficiency of the first 30 minutes: |09:40 close - 09:15 open| / path of the six 5-minute bars "
                  "(open-drive conviction)",
    "nr": "previous session's range / mean range of the 5 sessions before it (Crabel NR: contraction -> "
          "expansion)",
    "gap": "|09:15 open - previous close| / mean range of the previous 5 sessions",
    "trend5": "5-session efficiency of daily closes: |close[d-1] - close[d-6]| / sum of the 5 daily close moves "
              "(multi-day trend vs chop)",
}
SPLIT = {"lookback": 20, "min_prior": 5,
         "rule": "HIGH if today's value > median of the previous 20 sessions' values (min 5), else LOW; "
                 "a feature without a value or a threshold allows no gated component that day"}
OPTIONS = ("ALWAYS", "NEVER", *[f"{f}:{s}" for f in FEATURES for s in ("HIGH", "LOW")])  # tie order
BREAKOUTS = ("SHIPPED", "OR20", "EFF")
THEORY = {  # declared from the literature before scoring; TPB keeps its own trend-day condition
    "THEORY_IB": {**{c: "or_width:LOW" for c in BREAKOUTS}, "TPB": "ALWAYS"},
    "THEORY_DRIVE": {**{c: "open_drive:HIGH" for c in BREAKOUTS}, "TPB": "ALWAYS"},
    "THEORY_NR": {**{c: "nr:LOW" for c in BREAKOUTS}, "TPB": "ALWAYS"},
}
UNION = {c: "ALWAYS" for c in COMPONENTS}
NULL = {"count": 200, "seed": 2026102801, "draw": "each component's option uniformly from OPTIONS"}
RULE = {
    "all_dates_seen": True,
    "path": "each router replayed once over FULL through the shipped book; a window = the slice of that path",
    "selection": "per fold and per component independently: the option with the highest training "
                 "net-without-best-day of that component routed alone (NEVER scores 0); ties go to the earlier "
                 "option in OPTIONS (ALWAYS, then NEVER, then the conditions in declared order)",
    "oos": "F1+F2+F3 test sessions (16), each fold's router sliced to its own test window",
    "verdict": "conditions add value on this test only if the walk-forward router's OOS net > UNION's OOS net, "
               "> 0, > SHIPPED's OOS net, >= UNION in >= 2 of 3 folds, and >= the 90th percentile of the random "
               "routers' OOS net",
    "descriptive": "per component and feature: daily net HIGH vs LOW over the 29 sessions, two-sided permutation "
                   "test of the mean daily difference (20,000 label shuffles), Holm-adjusted over 20 tests",
    "hindsight": "trend day = |close - open| >= 0.5 * (high - low) of the session; explanation only, never routed",
    "caveat": "every component was itself chosen on some of these sessions (TPB on all 29), so even the "
              "walk-forward is optimistic about the components; it measures only what routing adds",
}


# ---- helpers -----------------------------------------------------------------------------------------------------

def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


def write_new(path: Path, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, indent=1, allow_nan=False, default=str)


def deny_network() -> None:
    def denied(*_a, **_k):
        raise RuntimeError("O28 offline research: network prohibited")
    socket.socket.connect = denied
    socket.socket.connect_ex = denied
    socket.create_connection = denied
    socket.getaddrinfo = denied


# ---- conditions known at 09:45 -----------------------------------------------------------------------------------

def nifty_bars(db: Path = DATA / "fno-replay.sqlite") -> dict[int, pd.DataFrame]:
    con = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
    try:
        out = {}
        for token in NIFTY_FUTURES:
            rows = con.execute("SELECT datetime, open, high, low, close FROM fut_candles WHERE instrument_token=? "
                               "AND interval='5minute' ORDER BY datetime", (token,)).fetchall()
            frame = pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close"])
            frame.index = pd.to_datetime(frame.pop("datetime"))
            out[token] = frame[~frame.index.duplicated(keep="last")].sort_index()
        return out
    finally:
        con.close()


def front_token(day: date) -> int | None:
    live = [t for t, expiry in NIFTY_FUTURES.items() if expiry >= day.isoformat()]
    return min(live, key=lambda t: NIFTY_FUTURES[t]) if live else None


def _sessions(frame: pd.DataFrame) -> dict:
    out = {}
    for day, b in frame.groupby(frame.index.date):
        mins = b.index.hour * 60 + b.index.minute
        opening = b[(mins >= 555) & (mins < 585)]
        expected = pd.date_range(pd.Timestamp(day) + pd.Timedelta(minutes=555), periods=6, freq="5min")
        out[day] = {"open": float(b["open"].iloc[0]) if mins[0] == 555 else None,
                    "high": float(b["high"].max()), "low": float(b["low"].min()), "close": float(b["close"].iloc[-1]),
                    "opening": opening if opening.index.equals(expected) else None}
    return out


def day_rows(bars: dict[int, pd.DataFrame]) -> dict[str, dict]:
    """date -> the five 09:45 features (None where not computable). Row d reads only day d's 09:15-09:40 bars and
    the front contract's earlier sessions."""
    per_token = {t: _sessions(f) for t, f in bars.items()}
    days = sorted({d for s in per_token.values() for d in s})
    rows = {}
    for day in days:
        token = front_token(day)
        sessions = per_token.get(token, {})
        if day not in sessions:
            continue
        prior = [sessions[d] for d in sorted(sessions) if d < day]
        today = sessions[day]
        row = {"token": token, **{f: None for f in FEATURES}}
        if len(prior) >= 6:
            ranges = [p["high"] - p["low"] for p in prior]
            adr5 = statistics.fmean(ranges[-5:])
            closes = [p["close"] for p in prior[-6:]]
            moves = sum(abs(closes[i] - closes[i - 1]) for i in range(1, 6))
            base = statistics.fmean(ranges[-6:-1])
            row["nr"] = ranges[-1] / base if base > 0 else None
            row["trend5"] = abs(closes[-1] - closes[0]) / moves if moves > 0 else 0.0
            op = today["opening"]
            if op is not None and today["open"] is not None and adr5 > 0:
                o0 = float(op["open"].iloc[0])
                c = [float(v) for v in op["close"]]
                path = abs(c[0] - o0) + sum(abs(c[i] - c[i - 1]) for i in range(1, 6))
                row["or_width"] = (float(op["high"].max()) - float(op["low"].min())) / adr5
                row["open_drive"] = abs(c[-1] - o0) / path if path > 0 else 0.0
                row["gap"] = abs(today["open"] - prior[-1]["close"]) / adr5
        rows[day.isoformat()] = row
    return rows


def with_sides(rows: dict[str, dict]) -> dict[str, dict]:
    """Adds each feature's threshold (median of the previous 20 sessions' values) and HIGH/LOW side."""
    out = {}
    ordered = sorted(rows)
    for i, day in enumerate(ordered):
        row = dict(rows[day])
        row["threshold"], row["side"] = {}, {}
        for f in FEATURES:
            history = [rows[d][f] for d in ordered[:i] if rows[d][f] is not None][-SPLIT["lookback"]:]
            if row[f] is None or len(history) < SPLIT["min_prior"]:
                row["threshold"][f], row["side"][f] = None, None
                continue
            threshold = statistics.median(history)
            row["threshold"][f] = threshold
            row["side"][f] = "HIGH" if row[f] > threshold else "LOW"
        out[day] = row
    return out


def condition_table(bars: dict[int, pd.DataFrame] | None = None) -> dict[str, dict]:
    return with_sides(day_rows(nifty_bars() if bars is None else bars))


def hindsight(bars: dict[int, pd.DataFrame] | None = None) -> dict[str, dict]:
    """Full-session facts (explanation only; a router never reads these)."""
    bars = nifty_bars() if bars is None else bars
    per_token = {t: _sessions(f) for t, f in bars.items()}
    out = {}
    for token, sessions in per_token.items():
        ordered = sorted(sessions)
        for i, day in enumerate(ordered):
            if front_token(day) != token or sessions[day]["open"] is None or i < 5:
                continue
            s = sessions[day]
            rng = s["high"] - s["low"]
            adr5 = statistics.fmean(sessions[d]["high"] - sessions[d]["low"] for d in ordered[i - 5:i])
            out[day.isoformat()] = {"body": abs(s["close"] - s["open"]) / rng if rng > 0 else 0.0,
                                    "range_rel": rng / adr5 if adr5 > 0 else None,
                                    "direction": "UP" if s["close"] > s["open"] else "DOWN",
                                    "trend_day": rng > 0 and abs(s["close"] - s["open"]) >= 0.5 * rng}
    return out


def allowed(rule: str, row: dict | None) -> bool:
    if rule == "ALWAYS":
        return True
    if rule == "NEVER" or row is None:
        return False
    feature, side = rule.split(":")
    return row["side"].get(feature) == side


# ---- components --------------------------------------------------------------------------------------------------

def component_policies() -> dict[str, replay.ReplayPolicy]:
    arms = grid.arms()
    return {"SHIPPED": arms[grid.CURRENT_ARM], "OR20": arms[OR20_ARM], "EFF": O27E.policy(EFF_GENOME),
            "TPB": replay.POLICIES["FNO_SIG_TREND_PULLBACK"]}


_POLICIES = component_policies()


def component_signal(comp: str, frame: pd.DataFrame, regime: str, now) -> MomSignal:
    policy = _POLICIES[comp]
    if comp == "SHIPPED":
        return evaluate_fno_mom(frame, regime, now)
    if comp == "EFF":
        return O27E.signal(frame, regime, now, policy.signal_variant)
    variant = policy.signal_variant
    return _ORIGINAL(frame, regime, now, fno_shadow.VARIANTS[variant] if isinstance(variant, str) else variant)


# ---- the router inside the shipped book --------------------------------------------------------------------------

_ACTIVE: dict = {}


@dataclass(frozen=True)
class RouterSignal:
    name: str


@contextmanager
def dispatch():
    def routed(frame, regime, now, variant):
        if isinstance(variant, RouterSignal):
            return _ACTIVE[variant.name].route(frame, regime, now)
        return _ORIGINAL(frame, regime, now, variant)
    fno_shadow._variant_signal = routed
    try:
        yield
    finally:
        fno_shadow._variant_signal = _ORIGINAL


class RouterReplay(replay.SingleLegReplay):
    """The shipped book with a routed signal. The shipped _entry and _manage run unchanged: the router answers the
    variant call, and each leg is managed with its own component's exit overrides."""

    def __init__(self, data, config: dict, table: dict, memo: dict, warm: bool = False):
        name = "O28_" + digest(config)
        super().__init__(data, replay.ReplayPolicy(name=name, manage_every_observation=True,
                                                   signal_variant=RouterSignal(name)))
        self.config, self.table, self.memo, self.warm = config, table, memo, warm
        self.leg_component: dict[int, str] = {}
        self._fired = None
        _ACTIVE[name] = self

    def _signal(self, comp, frame, regime, now, bar_ts) -> MomSignal:
        key = (comp, bar_ts, regime)
        hit = self.memo.get(key)
        if hit is not None and not self.warm:
            return copy.copy(hit)
        sig = component_signal(comp, frame, regime, now)
        if hit is None:
            self.memo[key] = sig
            if not self.warm:
                self.notes["memo_miss"] += 1
        elif repr(hit) != repr(sig):
            self.notes["memo_conflict"] += 1  # the same closed bar gave a different answer at another tick
        return copy.copy(sig)

    def route(self, frame, regime, now) -> MomSignal:
        bar_ts = replay._last_closed_bar(frame, now)
        row = self.table.get(now.date().isoformat())
        chosen = None
        for comp in COMPONENTS:
            on = allowed(self.config[comp], row)
            if not (on or self.warm):
                continue
            sig = self._signal(comp, frame, regime, now, bar_ts)
            if on and chosen is None and sig.direction is not None:
                chosen = (comp, sig)
                if not self.warm:
                    break
        if chosen is None:
            return MomSignal(bar_ts=bar_ts or "", reject_reason="router:no_component")
        self._fired = chosen[0]
        return chosen[1]

    def _entry(self, book, obs, frame, day, now):
        self._fired = None
        before = book.next_id
        super()._entry(book, obs, frame, day, now)
        if book.next_id != before:
            assert self._fired is not None and book.next_id == before + 1
            self.leg_component[before] = self._fired

    def _manage(self, book, obs, now):
        base, full = self.policy, book.open
        try:
            for leg_id in sorted(full):
                leg, comp = full[leg_id], self.leg_component[leg_id]
                before = len(book.trades)
                book.open = {leg_id: leg}
                self.policy = _POLICIES[comp]
                super()._manage(book, obs, now)
                for trade in book.trades[before:]:
                    trade["component"], trade["entry_qty"] = comp, leg.initial_qty
                if leg_id not in book.open:
                    del full[leg_id]
        finally:
            book.open, self.policy = full, base

    def run(self, start: str, end: str) -> dict:
        result = super().run(start, end)
        for trade in result["trades"]:
            if "component" not in trade and "id" in trade:
                trade["component"] = self.leg_component.get(trade["id"])
        return result


# ---- evaluation ----------------------------------------------------------------------------------------------------

KEEP = (*O27F.KEEP, "component")
_DATA = _TABLE = _MEMO = None


def _worker_init() -> None:
    global _DATA, _TABLE, _MEMO
    deny_network()
    _DATA = grid.CachedReplayData(DATA, CACHE)
    _TABLE = condition_table()
    _MEMO = pickle.loads(SIGNALS.read_bytes()) if SIGNALS.is_file() else {}


def warm_day(day: str) -> tuple[str, dict, int]:
    """Every component's signal at every entry tick of one session (signals never read the book)."""
    deny_network()
    data = grid.CachedReplayData(DATA, CACHE)
    memo: dict = {}
    with dispatch():
        router = RouterReplay(data, UNION, condition_table(), memo, warm=True)
        router.run(day, day)
    return day, memo, int(router.notes.get("memo_conflict", 0))


def evaluate(config: dict) -> tuple[str, list]:
    name = digest(config)
    target = EVALS / f"{name}.json"
    if target.is_file():
        return name, json.loads(target.read_text(encoding="utf-8"))["trades"]
    with dispatch():
        router = RouterReplay(_DATA, config, _TABLE, _MEMO)
        result = router.run(*FULL)
    trades = [{k: t.get(k) for k in KEEP if k in t} for t in result["trades"]]
    for t in trades:
        t.setdefault("status", "CLOSED" if "net_pnl" in t else "UNRESOLVED")
    tmp = target.with_name(f"{name}.{os.getpid()}.part")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps({"config": config, "trades": trades, "funnel": result["funnel"],
                               "notes": result["notes"]}, default=str), encoding="utf-8")
    os.replace(tmp, target)
    return name, trades


def single(comp: str, option: str) -> dict:
    return {c: (option if c == comp else "NEVER") for c in COMPONENTS}


def null_configs() -> list[dict]:
    out = []
    for i in range(NULL["count"]):
        rng = random.Random(f"{NULL['seed']}|{i}")
        out.append({c: rng.choice(OPTIONS) for c in COMPONENTS})
    return out


def select(trades: dict, train_days: list[str]) -> dict:
    """Walk-forward choice: per component, the option whose routed-alone path earned the most on the training
    sessions after removing its best day."""
    config = {}
    for comp in COMPONENTS:
        best = None
        for order, option in enumerate(OPTIONS):
            score = 0.0 if option == "NEVER" else \
                O27F.metrics(trades[digest(single(comp, option))], train_days)["net_without_best_day"]
            key = (score, -order)
            if best is None or key > best[0]:
                best = (key, option)
        config[comp] = best[1]
    return config


def _reference(rel: str) -> list:
    return [{k: t.get(k) for k in PARITY_KEYS} for t in json.loads((ROOT / rel).read_text(encoding="utf-8"))["trades"]]


def bindings() -> dict:
    files = {p.relative_to(ROOT).as_posix(): grid._sha(p) for p in sorted((ROOT / "python-engine").glob("*.py"))}
    for p in (Path(grid.__file__), O27F_LAB, O27E_LAB, HERE / "router.py", HERE / "test_router.py"):
        files[p.relative_to(ROOT).as_posix()] = grid._sha(p)
    refs = {comp: grid._sha(ROOT / rel) for comp, rel in REFERENCES.items()}
    return {"sources": files, "references": refs, "dataset": grid._verify_dataset(DATA),
            "settings": grid._settings_check()}


def freeze() -> None:
    deny_network()
    write_new(HERE / "freeze.json", {
        "schema": "o28_regime_router_v1", "bindings": bindings(), "full": FULL, "folds": FOLDS,
        "components": COMPONENTS, "or20_arm": OR20_ARM, "eff_genome": EFF_GENOME, "features": FEATURE_TEXT,
        "split": SPLIT, "options": OPTIONS, "theory": THEORY, "null": NULL, "rule": RULE,
        "qualification": "NOT_ASSESSED", "can_place_orders": False})
    print("frozen", HERE / "freeze.json")


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
    conflicts = 0
    if not SIGNALS.is_file():
        memo: dict = {}
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            for day, part, bad in ex.map(warm_day, days):
                memo.update(part)
                conflicts += bad
                print("warm", day, len(part), "signals", bad, "conflicts", flush=True)
        assert conflicts == 0, f"{conflicts} signal(s) changed within a closed bar; the memo is unsafe"
        SIGNALS.write_bytes(pickle.dumps(memo, protocol=pickle.HIGHEST_PROTOCOL))
    with ProcessPoolExecutor(max_workers=jobs, initializer=_worker_init) as ex:
        trades: dict[str, list] = {}

        def batch(configs):
            fresh = {digest(c): c for c in configs if digest(c) not in trades}
            for name, result in ex.map(evaluate, list(fresh.values()), chunksize=1):
                trades[name] = result
        # Gate: each component routed alone must trade exactly as its own stored study path.
        batch([single(c, "ALWAYS") for c in COMPONENTS])
        parity = {}
        for comp in COMPONENTS:
            mine = [{k: t.get(k) for k in PARITY_KEYS} for t in trades[digest(single(comp, "ALWAYS"))]]
            ref = _reference(REFERENCES[comp])
            assert mine == ref, f"{comp}: routed alone differs from its stored path; abort"
            parity[comp] = {"trades": len(mine), "net": round(sum(t["net_pnl"] or 0 for t in mine), 2)}
            print("PARITY PASS", comp, parity[comp], flush=True)
        batch([single(c, o) for c in COMPONENTS for o in OPTIONS if o != "NEVER"])
        routers = {}
        for fold in FOLDS:
            routers[fold["name"]] = select(trades, O27F.sessions_in(fold["train"], days))
            print("fold", fold["name"], routers[fold["name"]], flush=True)
        batch([UNION, *THEORY.values(), *routers.values()])
        batch(null_configs())
    misses = {}
    for name in trades:
        notes = json.loads((EVALS / f"{name}.json").read_text(encoding="utf-8"))["notes"]
        if notes.get("memo_miss") or notes.get("memo_conflict"):
            misses[name] = {k: notes.get(k) for k in ("memo_miss", "memo_conflict")}
    assert not misses, f"router replays computed signals outside the warmed memo: {misses}"
    assert frozen["bindings"] == bindings(), "bound inputs changed during scoring"
    write_new(LOCAL / "results-raw.json", {
        "freeze_sha256": grid._sha(HERE / "freeze.json"), "days": days, "parity": parity, "routers": routers,
        "trades": trades, "configs": {digest(c): c for c in [*(single(x, o) for x in COMPONENTS for o in OPTIONS
                                                                 if o != "NEVER"), UNION, *THEORY.values(),
                                                               *routers.values(), *null_configs()]},
        "table": condition_table(), "hindsight": hindsight(), "warm_conflicts": conflicts})
    print("DONE", len(trades), "replays", flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["freeze", "run"])
    cli.add_argument("--jobs", type=int, default=8)
    args = cli.parse_args()
    freeze() if args.action == "freeze" else run(args.jobs)
