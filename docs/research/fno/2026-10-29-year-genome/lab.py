"""O29f year genome - research only. No runtime module imports this file.

Owner (Oct 29): with the older months now downloaded, run the genome search again on almost a year of data - mix
the best components of the winners, sometimes with a little randomness and sometimes without - and report the best
strategy. Production RAM must not be hindered.

What is new against O27f (genome round 3) and O28 (router):
  * data: NIFTY Jan 1 - Oct 28 2026 from ICICI Breeze 1-minute candles (``yeardata.py``: declared candle model);
    Jan 1 - Sep 9 has never been used by any F&O study;
  * a genome is a BOOK: 1-4 members in priority order, each member a named component exactly as studied
    (SHIPPED, OR20, EFF, TPB) or an O27f lab family with its genes, each with its own day gate (ALWAYS or one
    09:45 condition from O28, e.g. open_drive:HIGH) and its own exits - the shape of the live UNION_DRIVE book;
  * recombination takes members from both parents (and mixes genes inside same-family members); a declared
    share of children get no mutation at all, the rest get mutations and structural changes (add, drop, reorder);
  * an anchored walk-forward of the whole search over four test blocks (Apr-May, Jun-Jul, Aug-Sep, Oct: 143
    sessions, each traded by a pick that never saw it) and a random-entry NULL track with the same budget;
  * a memory guard: no new replay starts while free RAM is under the declared floor, and at most 4 replays run
    during market hours (09:00-15:45 IST).

Every book is replayed once over the full year through the shipped single-leg book (planner, sizing, brakes,
exit ladder, costs, bid/ask fills; fno_policy_replay unchanged). Window metrics are slices of that one path.
"""
from __future__ import annotations

import argparse
import copy
import ctypes
import hashlib
import importlib.util
import json
import math
import os
import random
import statistics
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
sys.path[:0] = [str(ROOT / "python-engine"), str(ROOT / "scripts"), str(HERE)]

import fno_policy_replay as replay  # noqa: E402
import yeardata  # noqa: E402
from fno_engine_mom import MomSignal  # noqa: E402


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ROUTER_PY = ROOT / "docs/research/fno/2026-10-28-regime-router/router.py"
ROUTER = _load(ROUTER_PY, "o28_router")
O27F, O27E, grid = ROUTER.O27F, ROUTER.O27E, ROUTER.grid

YEAR = HERE / "_local/dataset-nifty"
ARCHIVE = ROUTER.DATA
LOCAL = HERE / "_local"
EVALS = LOCAL / "evals"
CACHES = {"year": LOCAL / "observations-year", "archive": LOCAL / "observations-archive"}
IST = timezone(timedelta(hours=5, minutes=30))

FULL = ("2026-01-01", "2026-10-28")
UNSEEN = ("2026-01-01", "2026-09-09")       # no F&O study had used these sessions before O29f
SEEN = ("2026-09-10", "2026-10-26")          # the archive window every earlier study used (fidelity check)
FOLDS = (
    {"name": "F1", "train": ("2026-01-01", "2026-03-31"), "test": ("2026-04-01", "2026-05-31")},
    {"name": "F2", "train": ("2026-01-01", "2026-05-31"), "test": ("2026-06-01", "2026-07-31")},
    {"name": "F3", "train": ("2026-01-01", "2026-07-31"), "test": ("2026-08-01", "2026-09-30")},
    {"name": "F4", "train": ("2026-01-01", "2026-09-30"), "test": ("2026-10-01", "2026-10-28")},
    {"name": "FINAL", "train": FULL, "test": None},
)

NAMED = ROUTER.COMPONENTS                    # SHIPPED, OR20, EFF, TPB
LAB_FAMILIES = ("TREND_PULLBACK", "PDL_BREAK", "VWAP_BAND", "MOMO_BURST")
GATES = tuple(o for o in ROUTER.OPTIONS if o != "NEVER")
NAMED_EXITS = ("OWN", "LIVE", "LATE", "LOOSE", "RUN")
FIXED_SHARED = {"xidx": "OFF", "delta": 0.55, "expiry": "NEAR"}   # SENSEX confirmation, depth and next week are
YEAR_SHARED = {k: v for k, v in O27F.SHARED_GENES.items() if k not in FIXED_SHARED}  # not in the year data
MAX_MEMBERS = 4

POOL = {"REAL": 160, "NULL": 80, "seed": 2026102901, "p_named": 0.4, "p_always": 0.4}
GA = {"population": 24, "parents_from_pool": 18, "generations": 6, "elites": 4, "immigrants": 2, "tournament": 3,
      "p_no_mutation": 0.4, "gene_mutation": 0.2, "adjacent": 0.7, "p_add": 0.15, "p_drop": 0.15, "p_swap": 0.1,
      "p_member_gene_mix": 0.5, "plateau_top": 3, "plateau_neighbours": 12, "seed": 2026102902}
GUARD = {"min_free_gb_market": 2.0, "min_free_gb_after": 1.5, "market_jobs": 4, "market_hours_ist": ("09:00", "15:45")}
RULE = {
    "path": "each book replayed once over FULL (Jan 1 - Oct 28) through the shipped book; a window = its slice",
    "min_trades": "max(10, ceil(0.30 * sessions in the slice))",
    "fitness": "(net - best day) / max(closed-trade drawdown, 2000) + (green weeks - red weeks) / weeks "
               "+ (green months - red months) / months - 1 if stressed net <= 0 - 1 if worst day < -5000; "
               "below min trades: -5 + trades / min",
    "stress": "net - Rs 1 per option unit per side - 25% extra recorded charges (trade list held fixed)",
    "plateau": "median training fitness of the book and 12 of its one-step neighbours (lowest digests)",
    "pick": "the highest plateau among the 3 best training-fitness books the fold itself evaluated, ties by "
            "fitness then digest",
    "walk_forward_verdict": "the search works only if REAL out-of-sample (F1-F4 tests, Apr 1 - Oct 28) is > 0, "
                            "beats UNION_DRIVE (the live book) on the same sessions, beats the NULL track, has "
                            ">= 3 of 4 folds > 0 and an out-of-sample worst day >= -5000",
    "final": "the FINAL fold's REAL pick is a forward-test candidate only; nothing is promoted on a replay",
    "unseen_check": "the fixed books (live UNION_DRIVE, its parts, UNION, the O28 theories) are frozen here and "
                    "scored on Jan 1 - Sep 9, sessions no F&O study had used",
}


# ---- helpers -----------------------------------------------------------------------------------------------------

def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


def write_new(path: Path, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, indent=1, allow_nan=False, default=str)


class _Mem(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def free_gb() -> float:
    m = _Mem()
    m.dwLength = ctypes.sizeof(_Mem)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 2 ** 30


def market_hours(now: datetime | None = None) -> bool:
    now = now or datetime.now(IST)
    clock = now.strftime("%H:%M")
    return now.weekday() < 5 and GUARD["market_hours_ist"][0] <= clock < GUARD["market_hours_ist"][1]


def allowed_inflight(jobs: int) -> int:
    return min(jobs, GUARD["market_jobs"]) if market_hours() else jobs


def memory_ok() -> bool:
    floor = GUARD["min_free_gb_market"] if market_hours() else GUARD["min_free_gb_after"]
    return free_gb() >= floor


# ---- members and books -------------------------------------------------------------------------------------------

def lab_genome(g: dict) -> dict:
    return O27F.canonical({**g, **FIXED_SHARED})


def named(name: str, gate: str = "ALWAYS", exit_: str = "OWN", vwap: str = "OFF") -> dict:
    return {"kind": "NAMED", "name": name, "gate": gate, "exit": exit_, "vwap_exit": vwap}


def lab(genome: dict, gate: str = "ALWAYS") -> dict:
    return {"kind": "LAB", "gate": gate, "genome": lab_genome(genome)}


def canonical_member(m: dict) -> dict:
    if m["kind"] == "NAMED":
        return named(m["name"], m["gate"], m["exit"], m["vwap_exit"])
    return lab(m["genome"], m["gate"])


def book_of(members) -> dict:
    out, seen = [], set()
    for m in members:
        m = canonical_member(m)
        key = digest(m)
        if key not in seen:
            seen.add(key)
            out.append(m)
    return {"members": out[:MAX_MEMBERS]}


def signal_id(m: dict) -> str:
    """Identity of a member's entry signal (exits and gates do not change it)."""
    if m["kind"] == "NAMED":
        return m["name"]
    return digest({k: v for k, v in m["genome"].items() if k not in ("exit", "vwap_exit")})


def member_policy(m: dict) -> replay.ReplayPolicy:
    if m["kind"] == "NAMED":
        if m["exit"] == "OWN":
            return ROUTER._POLICIES[m["name"]]
        return replay.ReplayPolicy(name=f"O29F_{m['name']}_{m['exit']}", manage_every_observation=True,
                                   exit_overrides=tuple(sorted(O27F.EXITS[m["exit"]].items())))
    return O27F.policy_for(m["genome"])


def member_vwap(m: dict) -> bool:
    return (m["vwap_exit"] if m["kind"] == "NAMED" else m["genome"]["vwap_exit"]) == "ON"


def member_signal(m: dict, frame, regime: str, now) -> MomSignal:
    if m["kind"] == "NAMED":
        return ROUTER.component_signal(m["name"], frame, regime, now)
    return O27F.lab_signal(frame, regime, now, m["genome"])


# Fixed books (frozen): the live book, its parts, UNION and the O28 theories, in O28's member order.
BREAKOUTS = ("SHIPPED", "OR20", "EFF")
FIXED = {
    "UNION_DRIVE": book_of([named(c, "open_drive:HIGH") for c in BREAKOUTS] + [named("TPB")]),
    "UNION": book_of([named(c) for c in NAMED]),
    "THEORY_IB": book_of([named(c, "or_width:LOW") for c in BREAKOUTS] + [named("TPB")]),
    "THEORY_NR": book_of([named(c, "nr:LOW") for c in BREAKOUTS] + [named("TPB")]),
    **{c: book_of([named(c)]) for c in NAMED},
    **{f"{c}_DRIVE": book_of([named(c, "open_drive:HIGH")]) for c in BREAKOUTS},
}
NULL_FIXED = 20   # random-entry books scored beside the fixed books (luck yardstick)


# ---- the book inside the shipped replay --------------------------------------------------------------------------

_NAMED_MEMO: dict = {"year": {}, "archive": {}}   # source -> (component, bar_ts, regime) -> MomSignal
_SHIPPED_LAST_CLOSED_BAR = replay._last_closed_bar


def fast_last_closed_bar(frame, now):
    """fno_policy_replay._last_closed_bar by binary search (same answer: the newest bar that closed by ``now`` on
    today's date); the archive parity gate re-proves it on every run."""
    import pandas as pd
    naive = now.replace(tzinfo=None)
    pos = int(frame.index.searchsorted(pd.Timestamp(naive) - pd.Timedelta(minutes=5), side="right"))
    if not pos:
        return None
    stamp = frame.index[pos - 1]
    return stamp.strftime("%Y-%m-%d %H:%M:%S") if stamp.date() == naive.date() else None


def _remember_more(key, value) -> None:
    O27F._FEATURES[key] = value
    while len(O27F._FEATURES) > 600:      # every session of the year stays cached in a worker
        O27F._FEATURES.popitem(last=False)


def speedups() -> None:
    replay._last_closed_bar = fast_last_closed_bar
    O27F._remember = _remember_more


class BookReplay(replay.SingleLegReplay):
    """The shipped book with a member-routed signal: the first member whose gate is open today and whose signal
    fires on the closed bar wins; each leg is managed with its own member's exits (and VWAP-lost exit).
    warm=True computes every named member's signal at every entry tick and enters nothing (the shared memo)."""

    def __init__(self, data, book: dict, table: dict, source: str, warm: bool = False):
        name = "O29F_" + digest(book)
        super().__init__(data, replay.ReplayPolicy(name=name, manage_every_observation=True,
                                                   signal_variant=ROUTER.RouterSignal(name)))
        self.book, self.table, self.source, self.warm = book, table, source, warm
        self.members = book["members"]
        self.policies = [member_policy(m) for m in self.members]
        self.vwap = [member_vwap(m) for m in self.members]
        self.ids = [signal_id(m) for m in self.members]
        self.leg_member: dict[int, int] = {}
        self._fired = None
        self._frame = None
        self._memo: dict = {}
        ROUTER._ACTIVE[name] = self

    def _signal(self, i: int, frame, regime, now, bar_ts) -> MomSignal:
        key = (self.ids[i], bar_ts, regime)
        memo = _NAMED_MEMO[self.source] if self.members[i]["kind"] == "NAMED" else self._memo
        hit = memo.get(key)
        if hit is None or self.warm:
            sig = member_signal(self.members[i], frame, regime, now)
            if hit is not None and repr(hit) != repr(sig):
                self.notes["memo_conflict"] += 1   # the same closed bar answered differently at another tick
            if hit is None:
                memo[key] = sig
                if not self.warm:
                    self.notes["named_memo_miss" if self.members[i]["kind"] == "NAMED" else "lab_memo_miss"] += 1
            hit = sig if hit is None else hit
        return copy.copy(hit)

    def route(self, frame, regime, now) -> MomSignal:
        bar_ts = replay._last_closed_bar(frame, now)
        row = self.table.get(now.date().isoformat())
        if self.warm:
            for i in range(len(self.members)):
                self._signal(i, frame, regime, now, bar_ts)
            return MomSignal(bar_ts=bar_ts or "", reject_reason="book:warm")
        for i, m in enumerate(self.members):
            if not ROUTER.allowed(m["gate"], row):
                continue
            sig = self._signal(i, frame, regime, now, bar_ts)
            if sig.direction is not None:
                self._fired = i
                return sig
        return MomSignal(bar_ts=bar_ts or "", reject_reason="book:no_member")

    def _entry(self, book, obs, frame, day, now):
        self._fired, self._frame = None, frame
        before = book.next_id
        super()._entry(book, obs, frame, day, now)
        if book.next_id != before:
            assert self._fired is not None and book.next_id == before + 1
            self.leg_member[before] = self._fired

    def _manage(self, book, obs, now):
        base, full = self.policy, book.open
        try:
            for leg_id in sorted(full):
                leg, i = full[leg_id], self.leg_member[leg_id]
                before = len(book.trades)
                book.open = {leg_id: leg}
                if self.vwap[i] and self._frame is not None:
                    O27F.LabReplay._vwap_exit(self, book, obs, now)
                if leg_id in book.open:
                    self.policy = self.policies[i]
                    super()._manage(book, obs, now)
                    self.policy = base
                for trade in book.trades[before:]:
                    trade["member"], trade["entry_qty"] = i, leg.initial_qty
                if leg_id not in book.open:
                    del full[leg_id]
        finally:
            book.open, self.policy = full, base


# ---- evaluation ----------------------------------------------------------------------------------------------------

KEEP = (*O27F.KEEP, "member")
_DATA: dict = {}
_TABLES: dict = {}


def year_bars(data: yeardata.YearData) -> tuple[dict, dict]:
    """Every NIFTY monthly future's own 5-minute bars (pre-roll days included, as live reads the front contract),
    and token -> expiry, for the O28 09:45 condition table."""
    bars, expiries = {}, {}
    for expiry in data._futures:
        contract = data.future_contract(expiry)
        frame = _full_frame(data, expiry)
        if not frame.empty:
            bars[contract.token], expiries[contract.token] = frame[["open", "high", "low", "close"]], expiry.isoformat()
    return bars, expiries


def _full_frame(data, expiry):
    import pandas as pd
    with data._connect() as con:
        rows = con.execute("SELECT datetime, open, high, low, close, volume FROM candles WHERE kind='future' AND "
                           "expiry=? ORDER BY datetime", (expiry.isoformat(),)).fetchall()
    frame = pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close", "volume"])
    frame.index = pd.to_datetime(frame.pop("datetime"))
    return frame.resample("5min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["open"])


def condition_table(source: str) -> dict:
    if source == "archive":
        return ROUTER.condition_table()
    data = dataset("year")
    bars, expiries = year_bars(data)
    saved = dict(ROUTER.NIFTY_FUTURES)
    ROUTER.NIFTY_FUTURES.clear()
    ROUTER.NIFTY_FUTURES.update(expiries)
    try:
        return ROUTER.condition_table(bars)
    finally:
        ROUTER.NIFTY_FUTURES.clear()
        ROUTER.NIFTY_FUTURES.update(saved)


def dataset(source: str):
    if source not in _DATA:
        _DATA[source] = (yeardata.YearData(YEAR, CACHES["year"]) if source == "year"
                         else grid.CachedReplayData(ARCHIVE, CACHES["archive"]))
    return _DATA[source]


def table(source: str) -> dict:
    if source not in _TABLES:
        _TABLES[source] = condition_table(source)
    return _TABLES[source]


def memo_file(source: str) -> Path:
    return LOCAL / f"named-signals-{source}.pkl"


def _worker_init() -> None:
    import pickle
    O27F.deny_network()
    speedups()
    for source in _NAMED_MEMO:
        if memo_file(source).is_file():
            _NAMED_MEMO[source] = pickle.loads(memo_file(source).read_bytes())


def warm_day(task: tuple) -> tuple[str, str, dict, int]:
    """Every named component's signal at every entry tick of one session (signals never read the book)."""
    source, day = task
    O27F.deny_network()
    speedups()
    _NAMED_MEMO[source] = {}
    with ROUTER.dispatch():
        engine = BookReplay(dataset(source), FIXED["UNION"], table(source), source, warm=True)
        engine.run(day, day)
    return source, day, dict(_NAMED_MEMO[source]), int(engine.notes.get("memo_conflict", 0))


def warm(ex: ProcessPoolExecutor, source: str, days: list[str]) -> int:
    import pickle
    if memo_file(source).is_file():
        return 0
    memo, conflicts = {}, 0
    for _src, day, part, bad in ex.map(warm_day, [(source, d) for d in days]):
        memo.update(part)
        conflicts += bad
    assert conflicts == 0, f"{conflicts} named signal(s) changed within a closed bar; the memo is unsafe"
    memo_file(source).write_bytes(pickle.dumps(memo, protocol=pickle.HIGHEST_PROTOCOL))
    print(f"warm {source}: {len(memo)} named signals over {len(days)} sessions", flush=True)
    return conflicts


def task_key(book: dict, source: str, window: tuple) -> str:
    return f"{source}_{window[0]}_{window[1]}_{digest(book)}"


def evaluate(task: tuple) -> tuple[str, list]:
    book, source, window = task
    key = task_key(book, source, window)
    target = EVALS / f"{key}.json"
    if target.is_file():
        return key, json.loads(target.read_text(encoding="utf-8"))["trades"]
    started = time.time()
    with ROUTER.dispatch():
        engine = BookReplay(dataset(source), book, table(source), source)
        result = engine.run(*window)
    trades = [{k: t.get(k) for k in KEEP if k in t} for t in result["trades"]]
    for t in trades:
        t.setdefault("status", "CLOSED" if "net_pnl" in t else "UNRESOLVED")
    halted = sorted({d["at"][:10] for d in engine.decisions if any(h.startswith("drawdown_halt") for h in d["halts"])})
    tmp = target.with_name(f"{key}.{os.getpid()}.part")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps({"book": book, "source": source, "window": window, "trades": trades,
                               "funnel": result["funnel"], "notes": result["notes"],
                               "drawdown_halt_days": halted[:1] + halted[-1:],
                               "seconds": round(time.time() - started, 1)}, default=str), encoding="utf-8")
    os.replace(tmp, target)
    return key, trades


class Runner:
    """Runs replays in a process pool under the memory guard; every result is also on disk (a crash resumes)."""

    def __init__(self, ex: ProcessPoolExecutor, jobs: int):
        self.ex, self.jobs = ex, jobs
        self.trades: dict[str, list] = {}
        self.books: dict[str, dict] = {}
        self.paused = 0

    def run(self, books: list[dict], source: str = "year", window: tuple = FULL) -> None:
        todo = []
        for b in books:
            key = task_key(b, source, window)
            self.books[key] = b
            if key not in self.trades and key not in {task_key(x, source, window) for x in todo}:
                todo.append(b)
        pending = set()
        for b in todo:
            while len(pending) >= allowed_inflight(self.jobs) or (pending and not memory_ok()):
                if pending and not memory_ok():
                    self.paused += 1
                done, pending = wait(pending, timeout=15, return_when=FIRST_COMPLETED)
                self._collect(done)
            while not memory_ok() and not pending:
                self.paused += 1
                time.sleep(15)
            pending.add(self.ex.submit(evaluate, (b, source, window)))
        done, _ = wait(pending)
        self._collect(done)

    def _collect(self, done) -> None:
        for f in done:
            key, trades = f.result()
            self.trades[key] = trades

    def m(self, book: dict, window, days: list[str]) -> dict:
        return metrics(self.trades[task_key(book, "year", FULL)], O27F.sessions_in(window, days))

    def fit(self, book: dict, window, days: list[str]) -> float:
        return fitness(self.m(book, window, days))


# ---- metrics -----------------------------------------------------------------------------------------------------

def metrics(trades: list, days: list[str]) -> dict:
    m = O27F.metrics(trades, days)
    months: dict = {}
    for d, v in m["daily"].items():
        months[d[:7]] = months.get(d[:7], 0.0) + v
    m.update({"months": len(months), "green_months": sum(v > 0 for v in months.values()),
              "red_months": sum(v < 0 for v in months.values()), "monthly": {k: round(v, 2) for k, v in months.items()}})
    return m


def fitness(m: dict) -> float:
    need = max(10, math.ceil(0.30 * m["sessions"]))
    if m["trades"] < need:
        return round(-5 + m["trades"] / need, 6)
    cs = m["net_without_best_day"] / max(m["dd"], 2000.0)
    weekly = (m["green_weeks"] - m["red_weeks"]) / max(1, m["weeks"])
    monthly = (m["green_months"] - m["red_months"]) / max(1, m["months"])
    penalty = (1.0 if m["stressed"] <= 0 else 0.0) + (1.0 if m["worst_day"] < -5000 else 0.0)
    return round(cs + weekly + monthly - penalty, 6)


# ---- generation, recombination, mutation -------------------------------------------------------------------------

def random_gate(rng: random.Random) -> str:
    return "ALWAYS" if rng.random() < POOL["p_always"] else rng.choice(GATES[1:])


def random_lab_genome(family: str, rng: random.Random) -> dict:
    g = {"family": family}
    for k, alleles in O27F.FAMILY_GENES[family].items():
        g[k] = rng.choice(alleles)
    for k, alleles in YEAR_SHARED.items():
        g[k] = rng.choice(alleles)
    return lab_genome(g)


def random_member(track: str, rng: random.Random) -> dict:
    if track == "NULL":
        return lab(random_lab_genome("NULL_RANDOM", rng), random_gate(rng))
    if rng.random() < POOL["p_named"]:
        return named(rng.choice(NAMED), random_gate(rng), rng.choice(NAMED_EXITS), rng.choice(("OFF", "ON")))
    return lab(random_lab_genome(rng.choice(LAB_FAMILIES), rng), random_gate(rng))


def random_book(track: str, rng: random.Random) -> dict:
    return book_of([random_member(track, rng) for _ in range(rng.randint(1, MAX_MEMBERS))])


def seeds() -> list[dict]:
    """Declared starting points: the fixed books and the O27f trend-pullback genome as a member."""
    tpb = {"family": "TREND_PULLBACK", "tp_trend": 1.5, "tp_side": 0.75, "tp_anchor": "VWAP", "tp_touch": 0.5,
           "tp_from": 690, "rvol": 0.0, "htf": "OFF", "window": "ALL", "stop_atr": 1.5, "target_r": 3.0,
           "exit": "RUN", "vwap_exit": "OFF"}
    return [*FIXED.values(), book_of([lab(tpb)]), book_of([named("OR20", "open_drive:HIGH"), lab(tpb)])]


def pool(track: str) -> list[dict]:
    rng = random.Random(f"{POOL['seed']}|{track}")
    out = {digest(b): b for b in (seeds() if track == "REAL" else [])}
    while len(out) < POOL[track] + (len(seeds()) if track == "REAL" else 0):
        b = random_book(track, rng)
        out.setdefault(digest(b), b)
    return list(out.values())


def null_fixed() -> list[dict]:
    rng = random.Random(f"{POOL['seed']}|NULL_FIXED")
    return [random_book("NULL", rng) for _ in range(NULL_FIXED)]


def _mutate_member(m: dict, track: str, rng: random.Random) -> dict:
    m = copy.deepcopy(m)
    if rng.random() < GA["gene_mutation"]:
        if m["gate"] == "ALWAYS" or rng.random() >= GA["adjacent"]:
            m["gate"] = rng.choice(GATES)
        else:
            feature, side = m["gate"].split(":")
            m["gate"] = rng.choice(("ALWAYS", f"{feature}:{'LOW' if side == 'HIGH' else 'HIGH'}"))
    if m["kind"] == "NAMED":
        if rng.random() < GA["gene_mutation"]:
            m["exit"] = rng.choice(NAMED_EXITS)
        if rng.random() < GA["gene_mutation"]:
            m["vwap_exit"] = "ON" if m["vwap_exit"] == "OFF" else "OFF"
        if rng.random() < GA["gene_mutation"] / 2:
            m["name"] = rng.choice(NAMED)
        return canonical_member(m)
    g = dict(m["genome"])
    for k in [*O27F.FAMILY_GENES[g["family"]], *YEAR_SHARED]:
        if rng.random() >= GA["gene_mutation"]:
            continue
        alleles = O27F.FAMILY_GENES[g["family"]].get(k) or YEAR_SHARED[k]
        i = alleles.index(g[k])
        if rng.random() < GA["adjacent"]:
            j = i + rng.choice((-1, 1))
            if 0 <= j < len(alleles):
                g[k] = alleles[j]
        else:
            g[k] = rng.choice(alleles)
    m["genome"] = g
    return canonical_member(m)


def mutate(b: dict, track: str, rng: random.Random) -> dict:
    members = [_mutate_member(m, track, rng) for m in b["members"]]
    if len(members) < MAX_MEMBERS and rng.random() < GA["p_add"]:
        members.insert(rng.randint(0, len(members)), random_member(track, rng))
    if len(members) > 1 and rng.random() < GA["p_drop"]:
        members.pop(rng.randrange(len(members)))
    if len(members) > 1 and rng.random() < GA["p_swap"]:
        i, j = rng.sample(range(len(members)), 2)
        members[i], members[j] = members[j], members[i]
    return book_of(members)


def crossover(a: dict, b: dict, rng: random.Random) -> dict:
    """Slot by slot, take the member from either parent; two same-family lab members mix their genes."""
    out = []
    for i in range(max(len(a["members"]), len(b["members"]))):
        options = [p["members"][i] for p in (a, b) if i < len(p["members"])]
        m = copy.deepcopy(rng.choice(options))
        if (len(options) == 2 and all(o["kind"] == "LAB" for o in options)
                and options[0]["genome"]["family"] == options[1]["genome"]["family"]
                and rng.random() < GA["p_member_gene_mix"]):
            g = {k: rng.choice((options[0]["genome"][k], options[1]["genome"][k])) for k in options[0]["genome"]}
            m = lab(g, rng.choice((options[0]["gate"], options[1]["gate"])))
        out.append(m)
    keep = [m for m in out if rng.random() < 0.85] or out[:1]
    return book_of(keep)


def neighbours(b: dict) -> list[dict]:
    out = []
    members = b["members"]
    for i, m in enumerate(members):
        def swap(new_member):
            return book_of([*members[:i], new_member, *members[i + 1:]])
        if m["gate"] != "ALWAYS":
            out.append(swap({**m, "gate": "ALWAYS"}))
            feature, side = m["gate"].split(":")
            out.append(swap({**m, "gate": f"{feature}:{'LOW' if side == 'HIGH' else 'HIGH'}"}))
        if m["kind"] == "NAMED":
            out += [swap({**m, "exit": e}) for e in NAMED_EXITS if e != m["exit"]]
            out.append(swap({**m, "vwap_exit": "ON" if m["vwap_exit"] == "OFF" else "OFF"}))
        else:
            for n in O27F.neighbours(m["genome"]):
                if all(n.get(k) == v for k, v in FIXED_SHARED.items()):
                    out.append(swap(lab(n, m["gate"])))
        if len(members) > 1:
            out.append(book_of([*members[:i], *members[i + 1:]]))
    unique = {digest(n): n for n in out if digest(n) != digest(b)}
    return [unique[k] for k in sorted(unique)][:GA["plateau_neighbours"]]


# ---- search --------------------------------------------------------------------------------------------------------

def evolve(runner: Runner, track: str, fold: dict, days: list[str], rng: random.Random, history: list) -> dict:
    train = fold["train"]
    seen = {digest(b): b for b in pool(track)}

    def fit(b):
        return runner.fit(b, train, days)
    ranked = sorted(seen.values(), key=lambda b: (fit(b), digest(b)), reverse=True)
    population = ranked[:GA["parents_from_pool"]]
    while len(population) < GA["population"]:
        population.append(random_book(track, rng))
    for generation in range(GA["generations"]):
        runner.run(population)
        seen.update({digest(b): b for b in population})
        population = sorted({digest(b): b for b in population}.values(), key=lambda b: (fit(b), digest(b)),
                            reverse=True)
        best = population[0]
        history.append({"track": track, "fold": fold["name"], "generation": generation, "best": digest(best),
                        "fitness": fit(best), "net": runner.m(best, train, days)["net"], "seen": len(seen),
                        "members": [m.get("name") or m["genome"]["family"] for m in best["members"]]})
        print(f"{track} {fold['name']} gen {generation}: fit={fit(best):.3f} "
              f"net={runner.m(best, train, days)['net']:.0f} members={history[-1]['members']} seen={len(seen)} "
              f"free={free_gb():.1f}GB", flush=True)
        nxt = population[:GA["elites"]]
        nxt += [random_book(track, rng) for _ in range(GA["immigrants"])]

        def pick():
            return max(rng.sample(population, GA["tournament"]), key=lambda b: (fit(b), digest(b)))
        guard = 0
        while len(nxt) < GA["population"] and guard < 500:
            guard += 1
            child = crossover(pick(), pick(), rng)
            if rng.random() >= GA["p_no_mutation"]:
                child = mutate(child, track, rng)
            if digest(child) not in {digest(x) for x in nxt}:
                nxt.append(child)
        population = nxt
    runner.run(population)
    seen.update({digest(b): b for b in population})
    top = sorted(seen.values(), key=lambda b: (fit(b), digest(b)), reverse=True)[:GA["plateau_top"]]
    rows = []
    for b in top:
        near = neighbours(b)
        runner.run(near)
        seen.update({digest(n): n for n in near})
        plateau = statistics.median([fit(b), *[fit(n) for n in near]])
        rows.append({"book": b, "digest": digest(b), "fitness": fit(b), "plateau": round(plateau, 6),
                     "neighbours": len(near)})
    chosen = max(rows, key=lambda r: (r["plateau"], r["fitness"], r["digest"]))
    return {"pick": chosen, "top": rows, "seen": sorted(seen)}


# ---- freeze and run ------------------------------------------------------------------------------------------------

def bindings() -> dict:
    files = {p.relative_to(ROOT).as_posix(): grid._sha(p) for p in sorted((ROOT / "python-engine").glob("*.py"))}
    for p in (Path(grid.__file__), ROUTER_PY, ROUTER.O27F_LAB, ROUTER.O27E_LAB, HERE / "lab.py", HERE / "yeardata.py",
              HERE / "test_lab.py"):
        files[p.relative_to(ROOT).as_posix()] = grid._sha(p)
    manifest = json.loads((YEAR / "manifest.json").read_text(encoding="utf-8"))
    for rel, sha in manifest["files_sha256"].items():
        if grid._sha(YEAR / rel) != sha:
            raise SystemExit(f"year dataset file changed: {rel}")
    return {"sources": files, "year_manifest_sha256": grid._sha(YEAR / "manifest.json"),
            "year_sessions": manifest["sessions"], "archive": grid._verify_dataset(ARCHIVE),
            "settings": grid._settings_check(),
            "references": {c: grid._sha(ROOT / rel) for c, rel in ROUTER.REFERENCES.items()}}


def freeze() -> None:
    O27F.deny_network()
    write_new(HERE / "freeze.json", {
        "schema": "o29f_year_genome_v1", "bindings": bindings(), "full": FULL, "unseen": UNSEEN, "seen": SEEN,
        "folds": FOLDS, "named": NAMED, "lab_families": LAB_FAMILIES, "family_genes": O27F.FAMILY_GENES,
        "year_shared_genes": YEAR_SHARED, "fixed_shared": FIXED_SHARED, "gates": GATES, "named_exits": NAMED_EXITS,
        "exits": O27F.EXITS, "fixed_books": FIXED, "null_fixed": null_fixed(), "seeds": seeds(), "pool": POOL,
        "ga": GA, "guard": GUARD, "rule": RULE, "qualification": "NOT_ASSESSED", "can_place_orders": False})
    print("frozen", HERE / "freeze.json")


def _parity(runner: Runner) -> dict:
    """On the archive (Sep 10 - Oct 26): each named member alone and the live UNION_DRIVE book must trade exactly as
    their stored O28 paths; the O27f trend-pullback genome as a lab member exactly as its O27f path."""
    keys = ROUTER.PARITY_KEYS
    checks = {c: (book_of([named(c)]), ROUTER._reference(rel)) for c, rel in ROUTER.REFERENCES.items()}
    drive_ref = ROOT / "docs/research/fno/2026-10-28-regime-router/_local/evals/e04ff62bc8c6ce2c.json"
    checks["UNION_DRIVE"] = (FIXED["UNION_DRIVE"],
                             [{k: t.get(k) for k in keys} for t in json.loads(drive_ref.read_text())["trades"]])
    tpb_ref = ROOT / "docs/research/fno/2026-10-27-genome-round3/_local/evals/a6d7762768c82811.json"
    tpb = json.loads(tpb_ref.read_text())
    checks["LAB_TPB"] = (book_of([lab(tpb["genome"])]), [{k: t.get(k) for k in keys} for t in tpb["trades"]])
    books = [b for b, _ in checks.values()]
    runner.run(books, source="archive", window=O27F.FULL)
    out = {}
    for name, (b, ref) in checks.items():
        mine = [{k: t.get(k) for k in keys} for t in runner.trades[task_key(b, "archive", O27F.FULL)]]
        assert mine == ref, f"{name}: the book path differs from its stored study path; abort"
        out[name] = {"trades": len(mine), "net": round(sum(t["net_pnl"] or 0 for t in mine), 2)}
        print("PARITY PASS", name, out[name], flush=True)
    return out


def run(jobs: int) -> None:
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    assert frozen["bindings"] == bindings(), "bound inputs changed since the freeze"
    rel = (HERE / "freeze.json").relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)) == frozen, \
        "freeze not committed"
    assert 1 <= jobs <= 10
    O27F.deny_network()
    days = [d for d in frozen["bindings"]["year_sessions"] if FULL[0] <= d <= FULL[1]]
    for p in (EVALS, *CACHES.values()):
        p.mkdir(parents=True, exist_ok=True)
    archive_days = [d for d in frozen["bindings"]["archive"]["quote_days"] if O27F.FULL[0] <= d <= O27F.FULL[1]]
    with ProcessPoolExecutor(max_workers=allowed_inflight(jobs)) as ex:      # shared named-signal memos first
        warm(ex, "archive", archive_days)
        warm(ex, "year", days)
    with ProcessPoolExecutor(max_workers=jobs, initializer=_worker_init) as ex:
        runner = Runner(ex, jobs)
        parity = _parity(runner)
        fixed = list(FIXED.values())
        runner.run(fixed, source="archive", window=SEEN)          # fidelity: the same books on both data sets
        runner.run(fixed, source="year", window=SEEN)
        print("fidelity books done", flush=True)
        runner.run([*fixed, *null_fixed()])
        print("fixed books done (year)", flush=True)
        for track in ("REAL", "NULL"):
            runner.run(pool(track))
            print(f"pool {track}: {len(pool(track))} books, paused {runner.paused}x for memory", flush=True)
        history, folds = [], {}
        for track in ("REAL", "NULL"):
            for fold in FOLDS:
                rng = random.Random(f"{GA['seed']}|{track}|{fold['name']}")
                folds[f"{track}|{fold['name']}"] = evolve(runner, track, fold, days, rng, history)
        final = folds["REAL|FINAL"]["pick"]["book"]
    assert frozen["bindings"] == bindings(), "bound inputs changed during scoring"
    write_new(LOCAL / "results-raw.json", {
        "freeze_sha256": grid._sha(HERE / "freeze.json"), "days": days, "parity": parity,
        "trades": runner.trades, "books": runner.books, "folds": folds, "history": history,
        "final_pick": final, "memory_pauses": runner.paused, "table": table("year")})
    print("DONE", len(runner.trades), "replays", flush=True)


def smoke(jobs: int) -> None:
    """Pre-freeze timing check on three books over the year (disclosed; scores nothing that is selected on)."""
    O27F.deny_network()
    books = [FIXED["UNION_DRIVE"], random_book("REAL", random.Random(1)), random_book("NULL", random.Random(2))]
    started = time.time()
    with ProcessPoolExecutor(max_workers=jobs, initializer=_worker_init) as ex:
        for key, trades in ex.map(evaluate, [(b, "year", ("2026-01-01", "2026-01-31")) for b in books]):
            print("smoke", key, len(trades), "trades", flush=True)
    print(f"smoke: {time.time() - started:.0f}s for {len(books)} books x January, free {free_gb():.1f} GB")


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["freeze", "run", "smoke"])
    cli.add_argument("--jobs", type=int, default=6)
    args = cli.parse_args()
    {"freeze": freeze, "run": lambda: run(args.jobs), "smoke": lambda: smoke(args.jobs)}[args.action]()
