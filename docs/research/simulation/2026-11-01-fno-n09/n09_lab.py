"""N09: challengers beside a fixed N08, on the unchanged replay stack. Research only; no application module imports this file.

N08_YEAR chooses the year, as in n08_lab.py. All four years are seen, so nothing here is an exam. Each year has its own results folder,
because the runner reuses any saved result with the same key. Patches sit at module level: Windows workers re-import the main script.

    N08_YEAR=<year> python n09_lab.py diag --jobs 3
    N08_YEAR=<year> python n09_lab.py parity --jobs 3
    N08_YEAR=<year> python n09_lab.py panel --jobs 4      (needs the committed freeze)
    N08_YEAR=<year> python n09_lab.py screens --jobs 5    (the 81 N08 search books, for the overfitting estimate)
    N08_YEAR=<year> python n09_lab.py final --jobs 4      (needs composition.json, committed)
    N08_YEAR=<year> N09_CARRY=1 python n09_lab.py carry --jobs 3   (one account, 2023 first)
"""
from __future__ import annotations

import argparse
import bisect
import copy
import hashlib
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
sys.path[:0] = [str(HERE), str(HERE.parent / "2026-11-01-fno-n08")]
import n08_lab as N  # noqa: E402
import n09_rules as R  # noqa: E402
from config import settings  # noqa: E402
from fno_adaptive_risk import Close  # noqa: E402
from fno_book import _features  # noqa: E402
from fno_engine_mom import FnoDirection  # noqa: E402

Y, X, C, B, L, F = N.Y, N.X, N.C, N.B, N.B.L, N.F
replay, ROUTER, MomSignal = Y.replay, Y.ROUTER, X.G.MomSignal
YEAR = B.YEAR
YEARS = ("2023", "2024", "2025", "2026")
LOCAL = HERE / "_local"
CARRY = os.environ.get("N09_CARRY") == "1"
Y.EVALS = LOCAL / ("evals-carry" if CARRY else f"evals-{YEAR}")
Y.EVALS.mkdir(parents=True, exist_ok=True)
ONE_LOT = {"FNO_MAX_LOTS": 1, "FNO_MAX_LOTS_PROVEN": 1}
LOW_INDEX = 4                       # the low-day TPB member, as in N03-N08
NOISE_INDEX = 5
NOT_CONFIRMED = ("EFF", "NOISE")    # EFF already waits for its retest; the noise book has its own half-hour clock
NO_STRUCTURE = ("TPB", "NOISE")     # N08's search: cutting stalled TPB trades cost Rs 46,065, and they earn by being held
DAILY_SOURCES = (HERE.parent / "2026-11-01-fno-n08/_local/daily-2023.json", HERE.parent / "2026-10-31-fno-complements/_local/daily-2026.json")

# ---- trade records: what the option study needs. This changes no decision. ------------------------------------------

_close = replay._close_record


def close_record(leg, *args, **kwargs):
    row, net = _close(leg, *args, **kwargs)
    row.update(delta_at_entry=leg.delta_at_entry, atr_at_entry=leg.atr_at_entry)
    return row, net


replay._close_record = close_record
Y.KEEP = tuple(dict.fromkeys((*Y.KEEP, "delta_at_entry", "atr_at_entry")))

# ---- the volatility reading ------------------------------------------------------------------------------------------


@lru_cache(None)
def vol_table() -> dict:
    """day -> (yesterday's daily ATR as % of close, its median over the 250 sessions before that). Daily bars strictly before the day."""
    rows = {}
    for path in DAILY_SOURCES:
        for row in json.loads(path.read_text(encoding="utf-8"))["rows"]:
            rows[row[0]] = row
    days = sorted(rows)
    out, atr, readings, prev = {}, None, [], None
    for i, day in enumerate(days):
        if readings:
            out[day] = (readings[-1], R.trailing_median(readings[:-1]))
        _d, _o, high, low, close = rows[day]
        tr = high - low if prev is None else max(high - low, abs(high - prev), abs(low - prev))
        atr = tr if atr is None else atr + (tr - atr) / 14
        if i >= 14:
            readings.append(atr / close * 100)
        prev = close
    return out


# ---- the noise-area member -------------------------------------------------------------------------------------------

ROUTER._POLICIES["NOISE"] = replay.ReplayPolicy(
    name="N09_NOISE", manage_every_observation=True,
    exit_overrides=tuple(sorted({"FNO_TIME_STOP_MIN": 1e6, "FNO_TRAIL_ATR_MULT": 1000.0}.items())))   # only its own trail, the backstop, its stop and the 15:10 close
_NOISE: dict = {}


def noise_table(frame, day) -> dict:
    key = (day, frame.index[0], len(frame))
    hit = _NOISE.get(key)
    if hit is None:
        prior = frame[frame.index.date < day]
        moves = defaultdict(list)
        for _d, bars in list(prior.groupby(prior.index.date))[-14:]:
            first = float(bars.open.iloc[0])
            for stamp, close in bars.close.items():
                moves[stamp.hour * 60 + stamp.minute].append(abs(float(close) / first - 1))
        hit = {"sigma": {m: R.noise_sigma(v) for m, v in moves.items()}, "prev_close": float(prior.close.iloc[-1]) if len(prior) else None}
        if len(_NOISE) > 800:
            _NOISE.clear()
        _NOISE[key] = hit
    return hit


def closed_today(frame, now):
    naive = pd.Timestamp(now.replace(tzinfo=None))
    pos = int(frame.index.searchsorted(naive - pd.Timedelta(minutes=5), side="right"))
    closed = frame.iloc[:pos]
    return closed[closed.index.date == naive.date()]


def today_vwap(today) -> pd.Series:
    volume = today.volume.clip(lower=0)
    typical = (today.high + today.low + today.close) / 3
    vwap = (typical * volume).cumsum() / volume.cumsum().replace(0, np.nan)
    return vwap.fillna(typical.expanding().mean())


def noise_state(frame, now) -> dict | None:
    """At a half-hour mark: the boundaries for this time of day and where price closed. Anything else, None."""
    today = closed_today(frame, now)
    if today.empty:
        return None
    stamp = today.index[-1]
    if not R.noise_mark(stamp.hour * 60 + stamp.minute):
        return None
    if not pd.Timedelta(0) <= pd.Timestamp(now.replace(tzinfo=None)) - (stamp + pd.Timedelta(minutes=5)) < pd.Timedelta(minutes=5):
        return None
    table = noise_table(frame, now.date())
    sigma, prev = table["sigma"].get(stamp.hour * 60 + stamp.minute), table["prev_close"]
    if sigma is None or prev is None:
        return None
    upper, lower = R.noise_bounds(float(today.open.iloc[0]), prev, sigma)
    return {"bar": stamp.strftime("%Y-%m-%d %H:%M:%S"), "stamp": stamp, "close": float(today.close.iloc[-1]), "upper": upper, "lower": lower, "vwap": float(today_vwap(today).iloc[-1])}


def noise_signal(frame, regime, now) -> MomSignal:
    bar = replay._last_closed_bar(frame, now) or ""
    state = noise_state(frame, now)
    if state is None:
        return MomSignal(bar_ts=bar, reject_reason="n09:no_mark")
    side = R.noise_direction(state["close"], state["upper"], state["lower"])
    if side is None:
        return MomSignal(bar_ts=bar, reject_reason="n09:inside_noise")
    stop = state["lower"] if side == "LONG" else state["upper"]    # the opposite boundary is the hard stop; the paper's trail runs at the marks
    atr = float(_features(frame).loc[state["stamp"]].atr)
    return MomSignal(bar_ts=bar, direction=FnoDirection(side), close=state["close"], or_high=state["upper"], or_low=state["lower"], atr=atr, stop_underlying=stop,
                     target_underlying=R.target_from(side, state["close"], stop, 3.0), strategy="NOISE")


_member_signal = Y.member_signal


def member_signal(m, frame, regime, now):
    if m["kind"] == "NAMED" and m["name"] == "NOISE":
        return noise_signal(frame, regime, now)
    return _member_signal(m, frame, regime, now)


Y.member_signal = member_signal

# ---- entries: one-bar confirmation, and the size reading -------------------------------------------------------------

_route = Y.BookReplay.route


def judge(pend: dict, frame, now, bar):
    """The bar after the signal: GO with a fresh target, or the setup is gone."""
    sig, previous = pend["sig"], pd.Timestamp(pend["bar"])
    stamp = pd.Timestamp(bar) if bar else None
    if stamp is None or stamp - previous != pd.Timedelta(minutes=5) or stamp not in frame.index or previous not in frame.index:
        return None
    side = sig.direction.value
    row = frame.loc[stamp]
    if not R.confirmed(side, float(frame.loc[previous].close), float(row.close), float(row.low), float(row.high), float(sig.stop_underlying), X.S.stretch_at(frame, now, side)):
        return None
    fresh = copy.copy(sig)
    fresh.bar_ts, fresh.close = bar, float(row.close)
    fresh.target_underlying = R.target_from(side, float(row.close), float(sig.stop_underlying))
    return {**pend, "state": "GO", "go": bar, "sig": fresh}


def waiting(bar) -> MomSignal:
    return MomSignal(bar_ts=bar or "", reject_reason="n09:waiting")


def confirm_route(self, frame, regime, now):
    bar = replay._last_closed_bar(frame, now)
    pend = getattr(self, "_n09_pend", None)
    if pend and pend["day"] != now.date():
        pend = None
    if pend and pend["state"] == "WAIT" and bar != pend["bar"]:
        pend = judge(pend, frame, now, bar)
    if pend and pend["state"] == "GO" and bar != pend["go"]:
        pend = None
    self._n09_pend = pend
    if pend and pend["state"] == "GO":
        self._fired, self._n02_decision = pend["fired"], copy.deepcopy(pend["decision"])
        settings.FNO_MAX_LOTS, settings.FNO_MAX_LOTS_PROVEN = min(settings.FNO_MAX_LOTS, pend["lots"][0]), min(settings.FNO_MAX_LOTS_PROVEN, pend["lots"][1])
        return copy.copy(pend["sig"])
    if pend:
        return waiting(bar)
    sig = _route(self, frame, regime, now)
    if sig.direction is None or self.members[self._fired]["name"] in NOT_CONFIRMED:
        return sig
    self._n09_pend = {"state": "WAIT", "day": now.date(), "bar": bar, "sig": sig, "fired": self._fired, "decision": copy.deepcopy(self._n02_decision),
                      "lots": (settings.FNO_MAX_LOTS, settings.FNO_MAX_LOTS_PROVEN)}
    self._fired, self._n02_decision = None, None
    return waiting(bar)


def route(self, frame, regime, now):
    cfg = self.book.get("n09")
    if not cfg:
        return _route(self, frame, regime, now)
    saved = X.S.stretch_at
    if cfg.get("no_stretch"):
        X.S.stretch_at = lambda *_a, **_k: None
    try:
        sig = confirm_route(self, frame, regime, now) if cfg.get("confirm") else _route(self, frame, regime, now)
    finally:
        X.S.stretch_at = saved
    if cfg.get("vol_size") and sig.direction is not None:
        reading = vol_table().get(now.date().isoformat(), (None, None))
        lots = R.vol_lots(*reading)
        settings.FNO_MAX_LOTS, settings.FNO_MAX_LOTS_PROVEN = min(settings.FNO_MAX_LOTS, lots), min(settings.FNO_MAX_LOTS_PROVEN, lots)
    return sig


Y.BookReplay.route = route

# ---- exits: the structure challenger and the noise trail -------------------------------------------------------------


def close_now(self, book, leg, ident, member, obs, now, reason) -> None:
    """The same steps the shipped manager takes when it closes a leg."""
    quote = obs.options.get(leg.token)
    bid = quote.bid if quote else 0.0
    if bid <= 0:
        self.notes["n09_exit_unpriced"] += 1
        return
    record, final = replay._close_record(leg, now, bid, reason, obs.future.ltp)
    record["member"], record["entry_qty"] = member, leg.initial_qty
    book.trades.append(record)
    book.equity += final
    book.closes.append((now, final, "SINGLE_LEG"))
    book.completed.append(Close(now, record["net_pnl"], True))
    del book.open[ident]


_manage = Y.BookReplay._manage


def manage(self, book, obs, now):
    cfg = self.book.get("n09") or {}
    frame = getattr(self, "_frame", None)
    if cfg and frame is not None and now.date() == frame.index[-1].date():
        for ident in sorted(book.open):
            leg, member = book.open[ident], self.leg_member[ident]
            name = self.members[member]["name"]
            bar = replay._last_closed_bar(frame, now)
            if bar is None or bar <= leg.bar_ts or bar == getattr(leg, "_n09_bar", None):
                continue
            leg._n09_bar = bar
            if name == "NOISE":
                state = noise_state(frame, now)
                if state and R.noise_trail_hit(leg.direction, state["close"], state["upper"], state["lower"], state["vwap"]):
                    close_now(self, book, leg, ident, member, obs, now, "n09_noise_trail")
            elif cfg.get("structure") and name not in NO_STRUCTURE:
                today = closed_today(frame, now)
                if len(today) >= 2:
                    risk = abs(leg.entry_underlying - leg.stop_underlying)
                    side = 1 if leg.direction == "LONG" else -1
                    progress = side * (obs.future.ltp - leg.entry_underlying) / risk if risk > 0 else 0.0
                    age = (now - datetime.fromisoformat(leg.entry_time)).total_seconds() / 60
                    if R.structure_broken(leg.direction, today.close.tolist(), today_vwap(today).tolist(), age, bool(leg.trail_active), progress):
                        close_now(self, book, leg, ident, member, obs, now, "n09_structure")
    return _manage(self, book, obs, now)


Y.BookReplay._manage = manage

# ---- the account: starting again after the 15% stop ------------------------------------------------------------------

_SHADOW: dict = {}


def shadow_trades(names: tuple) -> tuple:
    """The same rules on paper, one lot, brakes off, closed trades only: (exit instants, nets), oldest first."""
    if names not in _SHADOW:
        rows = []
        for rel in names:
            for t in json.loads((LOCAL / rel).read_text(encoding="utf-8"))["trades"]:
                if t.get("net_pnl") is not None:
                    rows.append((datetime.fromisoformat(t["exit_time"]), float(t["net_pnl"])))
        rows.sort(key=lambda r: r[0])
        _SHADOW[names] = ([r[0] for r in rows], [r[1] for r in rows])
    return _SHADOW[names]


_halts = replay.SingleLegReplay._halts


def halts(self, book, now):
    active = _halts(self, book, now)
    mode = (self.book.get("n09") or {}).get("rearm")
    if not mode:
        return active
    active = tuple(a for a in active if not a.startswith("drawdown_halt"))
    state = self._n09_account
    if book.equity < state["floor"]:
        if state.get("halted_at") is None:
            state["halted_at"] = now.isoformat()
        go = False
        if mode == "ANNUAL":
            go = R.rearm_annual(int(state["halted_at"][:4]), now.year)
        elif mode == "SHADOW":
            at, nets = shadow_trades(tuple(self.book["n09"]["shadow"]))
            go = R.rearm_shadow(nets[:bisect.bisect_left(at, now)])
        else:
            raise ValueError(mode)
        if go:
            state["rearms"].append({"at": now.isoformat(), "equity": round(book.equity, 2), "halted_at": state["halted_at"]})
            state["floor"] = book.equity * (1.0 - float(settings.FNO_MAX_DRAWDOWN_PCT))
            state["halted_at"] = None
        else:
            active = (*active, f"drawdown_halt equity={book.equity:.0f}")
    return active


Y.BookReplay._halts = halts

_run = Y.BookReplay.run


def run_book(self, start, end):
    cfg = self.book.get("n09") or {}
    if cfg.get("rearm"):
        previous = cfg.get("floor_from")
        self._n09_account = (json.loads((LOCAL / f"account-{previous}.json").read_text(encoding="utf-8")) if previous else
                             {"floor": float(settings.FNO_PAPER_BANKROLL) * (1.0 - float(settings.FNO_MAX_DRAWDOWN_PCT)), "rearms": [], "halted_at": None})
    result = _run(self, start, end)
    if cfg.get("rearm"):
        X.write(LOCAL / f"account-{Y.digest(self.book)}.json", self._n09_account)
    return result


Y.BookReplay.run = run_book

# ---- books -----------------------------------------------------------------------------------------------------------


def n08() -> dict:
    return N.n08_book()


def one_lot(book: dict, label: str) -> dict:
    """The equal-size view: one lot, every brake off, so neither size nor the halt can hide a difference."""
    b = copy.deepcopy(book)
    b["cfg"] = {**b.get("cfg", {}), **L.BRAKES_OFF, **ONE_LOT}
    b["label"] = label
    return b


def with_n09(book: dict, label: str, **cfg) -> dict:
    b = copy.deepcopy(book)
    b["n09"] = {"contract": "v1", **cfg}
    b["label"] = label
    return b


def with_noise(book: dict, order: list) -> dict:
    b = copy.deepcopy(book)
    b["members"] = [*b["members"], Y.canonical_member(Y.named("NOISE"))]
    b["n08"] = {**b["n08"], "order": order}
    return b


def diag_books() -> dict:
    return {"N08": n08(), "DIAG": one_lot(n08(), "N09|DIAG|N08_ONE_NOBRAKE")}


def noop_book() -> dict:
    """Every N09 code path active, with nothing changed: it must equal N08 trade for trade."""
    return with_n09(n08(), "N09|NOOP")


def one_books() -> dict:
    """Against DIAG, one change at a time, at one lot, brakes off."""
    base = one_lot(n08(), "N09|ONE|BASE")
    order = [*X.INDEX["TPB_ONE"]]
    out = {
        "ONE|CONFIRM": with_n09(base, "N09|ONE|CONFIRM", confirm=True),
        "ONE|STRUCTURE": with_n09(base, "N09|ONE|STRUCTURE", structure=True),
        "ONE|NOISE_TEXTBOOK": with_n09(with_noise(base, [NOISE_INDEX]), "N09|ONE|NOISE_TEXTBOOK", no_stretch=True),
        "ONE|NOISE_HOUSE": with_n09(with_noise(base, [NOISE_INDEX]), "N09|ONE|NOISE_HOUSE"),
        "ONE|N08+NOISE": with_n09(with_noise(base, [*order, NOISE_INDEX]), "N09|ONE|N08+NOISE"),
    }
    for delta in (0.65, 0.75):
        b = copy.deepcopy(base)
        b["cfg"] = {**b["cfg"], "FNO_TARGET_DELTA": delta}
        out[f"ONE|D{int(delta * 100)}"] = with_n09(b, f"N09|ONE|D{int(delta * 100)}")
    return out


def cash_books() -> dict:
    """The full cash path, fresh Rs 2.5 lakh a year, today's brakes: sizing comes last, as the auditor asked."""
    return {
        "CASH|NO_E": with_n09(N.welc("N09|CASH|NO_E", two_before=0), "N09|CASH|NO_E"),
        "CASH|S_VOL": with_n09(N.welc("N09|CASH|S_VOL", two_before=1440), "N09|CASH|S_VOL", vol_size=True),
    }


def screen_books() -> dict:
    """N08's own search, for the overfitting estimate. Unchanged books, now on all four years."""
    return {**N.screen_books(), **N.screen2_books(), **N.screen3_books(), **N.screen4_books()}


def composition() -> dict:
    return json.loads((HERE / "composition.json").read_text(encoding="utf-8"))


def n09_book(cash: bool = True, label: str = "N09") -> dict:
    """N09, exactly as composition.json says, which analyze_panel.py derives from the frozen rule."""
    c = composition()
    cfg = {k: True for k in ("confirm", "structure") if c.get(k)}
    if c.get("sizing") == "S_VOL":
        b, cfg["vol_size"] = N.welc(label, two_before=1440), True
    else:
        b = N.welc(label, two_before=0)
    if c.get("delta"):
        b["cfg"] = {**b["cfg"], "FNO_TARGET_DELTA": c["delta"]}
    if c.get("noise"):
        b = with_noise(b, [*X.INDEX["TPB_ONE"], NOISE_INDEX])
    if not cash:
        b = one_lot(b, label + "|ONE")
    return with_n09(b, label if cash else label + "|ONE", **cfg)


def final_books() -> dict:
    n09 = n09_book()
    out = {"N09": n09, "N09|ONE": n09_book(cash=False)}
    for name, cost in (("none", [0.0, 0.0]), ("double", [400.0, 10.0])):
        for ref, book in (("N09", n09), ("N08", n08())):
            b = copy.deepcopy(book)
            b.update(cost=cost, label=f"N09|COST|{ref}|{name}")
            out[f"COST|{ref}|{name}"] = b
    return out


def carry_books() -> dict:
    """One account from January 2023: N08 as it is, N09 as it is, and each starting again by the two account rules."""
    order = list(YEARS)
    earlier = order[:order.index(YEAR)]
    shadow_n09 = [f"evals-{y}/{json.loads((LOCAL / f'keys-final-{y}.json').read_text())['N09|ONE']}.json" for y in order]
    shadow_n08 = [f"evals-{y}/{json.loads((LOCAL / f'keys-diag-{y}.json').read_text())['DIAG']}.json" for y in order]
    base = {"N08": n08(), "N09": n09_book()}
    arms = {"N08": base["N08"], "N09": base["N09"]}
    for name in ("N08", "N09"):
        shadow = shadow_n08 if name == "N08" else shadow_n09
        arms[f"{name}|ANNUAL"] = with_n09(base[name], f"N09|CARRY|{name}|ANNUAL", **(base[name].get("n09") or {}), rearm="ANNUAL")
        arms[f"{name}|SHADOW"] = with_n09(base[name], f"N09|CARRY|{name}|SHADOW", **(base[name].get("n09") or {}), rearm="SHADOW", shadow=shadow)
    out = {}
    for name, book in arms.items():
        b = copy.deepcopy(book)
        if earlier:
            saved = [json.loads((LOCAL / f"keys-carry-{y}.json").read_text(encoding="utf-8"))[name] for y in earlier]
            b["carry"] = saved
            if b.get("n09", {}).get("rearm"):
                b["n09"]["floor_from"] = saved[-1].rsplit("_", 1)[-1]
        out[name] = b
    return out


def keys(books: dict) -> dict:
    return {n: Y.task_key(b, "year", C.WINDOW) for n, b in books.items()}


# ---- the freeze ------------------------------------------------------------------------------------------------------

SOURCES = ("n09_rules.py", "n09_lab.py", "PLAN.md", "analyze_panel.py", "test_n09.py")


def sha(path: Path) -> str:
    """Line endings don't count: git may rewrite them on this machine."""
    return hashlib.sha256(path.read_bytes().replace(bytes([13, 10]), bytes([10]))).hexdigest()


def committed(path: Path) -> bytes:
    return subprocess.check_output(["git", "show", f"HEAD:{path.relative_to(ROOT).as_posix()}"], cwd=ROOT)


def freeze() -> None:
    target = HERE / "freeze.json"
    assert not target.exists(), "already frozen"
    X.write(target, {"schema": "n09_freeze_v1", "sources": {s: sha(HERE / s) for s in SOURCES}, "one_books": one_books(), "cash_books": cash_books(),
                     "note": "Written before any challenger is scored. All four years are seen, so this is discipline, not an exam."})


def require_freeze() -> None:
    target = HERE / "freeze.json"
    assert json.loads(committed(target)) == json.loads(target.read_text(encoding="utf-8")), "freeze.json is not committed"
    frozen = json.loads(target.read_text(encoding="utf-8"))
    for name, value in frozen["sources"].items():
        assert sha(HERE / name) == value, f"{name} changed after the freeze"


def require_composition() -> None:
    target = HERE / "composition.json"
    assert json.loads(committed(target)) == json.loads(target.read_text(encoding="utf-8")), "composition.json is not committed"


def run_year_books(name: str, books: dict, jobs: int) -> None:
    N.run_books(books, jobs)
    X.write(LOCAL / f"keys-{name}-{YEAR}.json", keys(books))
    print("DONE", name, YEAR, len(books), flush=True)


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=("diag", "parity", "freeze", "panel", "screens", "final", "carry"))
    cli.add_argument("--jobs", type=int, default=3)
    a = cli.parse_args()
    if a.action == "diag":
        run_year_books("diag", diag_books(), a.jobs)
    elif a.action == "parity":
        books = {"N08": n08(), "NOOP": noop_book()}
        run_year_books("parity", books, a.jobs)
        k = keys(books)
        load = lambda name: json.loads((Y.EVALS / f"{k[name]}.json").read_text(encoding="utf-8"))["trades"]  # noqa: E731
        strip = lambda t: {x: v for x, v in t.items() if x != "admission_id"}  # noqa: E731
        assert [strip(t) for t in load("N08")] == [strip(t) for t in load("NOOP")], "the N09 code paths changed N08 with nothing switched on"
        print("PARITY OK", YEAR, len(load("N08")), round(sum(t["net_pnl"] for t in load("N08"))), flush=True)
    elif a.action == "freeze":
        freeze()
        print("FROZEN", flush=True)
    elif a.action == "panel":
        require_freeze()
        run_year_books("panel", {**one_books(), **cash_books()}, a.jobs)
    elif a.action == "screens":
        run_year_books("screens", screen_books(), a.jobs)
    elif a.action == "final":
        require_composition()
        run_year_books("final", final_books(), a.jobs)
    else:
        assert CARRY
        require_composition()
        run_year_books("carry", carry_books(), a.jobs)


if __name__ == "__main__":
    main()
