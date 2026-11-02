"""O31e - the main book's weak spots, and what could do better there. Research only. No runtime module imports this file.

Owner (Oct 31): "situations where the strategy didn't perform the best. You identify those situations and in those situations,
what better strategy we can put in that you search you implement a new test".

FOUND BY LOOKING. diagnose_w.py and the library slice shaped this list, on three seen years (per lot after Rs 200):
  * inside the main book: calls lose in all three years and puts earn in all three; EFF makes most trades and loses; TPB earns
    most; entries behind VWAP and on big-gap days lose;
  * on the 80-90% of days it sits out: 0 of 116 stored strategies earn in all three years, and calls earn in none. Puts earn in 3,
    led by the four on ADX 25-30. Entries in the gap's direction lose in all three years; afternoon entries lose in all three;
  * the web offered little evidence: narrow-CPR, NR7 and similar setups are trader lore without published results. The first half
    hour predicting the last (Gao, Han, Li and Zhou, JFE 2018) is the one peer-reviewed intraday effect, so it is tested.

GROUP C (change the main book) and GROUP D (widen it, puts only below ADX 30): exact at today's limits with the cost in the path,
and one lot with brakes off. GROUP E (a specialist for the days it sits out): one lot, brakes off, against sitting out, which earns
exactly zero. 20 random-entry books on the same closed days are the luck yardstick. Every setting is one textbook or round value.

    python lab_w.py freeze                                                     # commit and push freeze.json alone
    python ../run_slice.py --env O30F_YEAR=2024 -- <folder>/lab_w.py run --jobs 6   # repeat until DONE, then 2025 and 2026
    python analyze_w.py
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
sys.path[:0] = [str(HERE), str(ROOT / "docs/research/fno/2026-10-31-final-book")]
import lab_o2 as O  # noqa: E402
import sides_w as W  # noqa: E402

X, L, T, S, C, Y, G, F, O27F = O.X, O.L, O.T, O.S, O.C, O.Y, O.G, O.F, O.O27F
YEAR = O.YEAR
LOCAL = HERE / "_local"
Y.EVALS = LOCAL / "evals"
CLOSED = "adx_abs30:LOW"
OPEN = "adx_abs30:HIGH"
FAMILIES = ("GAP_FADE", "LAST_HOUR", "CPR_BREAK", "IB_BREAK", "SUPERTREND_VWAP")
LATE_CFG = {"FNO_HARD_FLAT_MIN": 925, "FNO_ENTRY_END_MIN": 905}      # LAST_HOUR alone: enter by 15:05, flat by 15:25
EXPANSION = 0.6
_TABLE: dict = {}
_prev_table = C.table
_sides_done: set = set()


# ---- the new sides --------------------------------------------------------------------------------------------------

def table(source: str) -> dict:
    rows = _prev_table(source)
    if source not in _sides_done:
        manifest = json.loads((Y.YEAR / "manifest.json").read_text(encoding="utf-8"))
        parts = (W.daily_sides(F.daily_bars(), sorted(rows)), W.dte_sides(manifest["sessions"], manifest["option_expiries"]))
        for part in parts:
            for day, values in part.items():
                if day in rows:
                    rows[day].setdefault("side", {}).update(values)
        _sides_done.add(source)
    return rows


C.table = table
Y.table = table


# ---- the new entries (causal: the answer for bar i reads only bars <= i and earlier sessions) ----------------------------

def entries(m: dict, f: dict) -> dict:
    """bar_ts -> +1 (buy calls) / -1 (buy puts)."""
    key = (G.digest(m), f["day"].isoformat(), f["stamps"][-1], len(f["stamps"]))
    if key in _TABLE:
        return _TABLE[key]
    t, stamps, fam = f["t"], f["stamps"], m["family"]
    c, h, l, atr, vwap, mins = (t["close"].values, t["high"].values, t["low"].values, t["atr"].values, t["vwap"].values, t["minute"].values)
    n, out = len(t), {}
    day_open, pdc, pdh, pdl = f["day_open"], f["pdc"], f["pdh"], f["pdl"]
    if fam == "GAP_FADE":
        # After a gap, the first close back through today's open on the far side of VWAP, 09:45 to 11:00: trade towards the gap's fill.
        gap = day_open - pdc
        for i in range(n):
            if not (585 <= mins[i] + 5 <= 660) or gap == 0:
                continue
            if (gap > 0 and c[i] < day_open and c[i] < vwap[i]) or (gap < 0 and c[i] > day_open and c[i] > vwap[i]):
                out[stamps[i]] = -1 if gap > 0 else 1
                break
    elif fam == "LAST_HOUR":
        # Gao et al.: the first half hour's return (from yesterday's close) and the penultimate half hour's, when they agree.
        at = {int(v): i for i, v in enumerate(mins)}
        if all(k in at for k in (580, 865, 895)):
            first, late = c[at[580]] - pdc, c[at[895]] - c[at[865]]
            if first * late > 0:
                out[stamps[at[895]]] = 1 if first > 0 else -1
    elif fam == "CPR_BREAK":
        # The central pivot range from yesterday's high, low and close: the first close through it, on VWAP's side, one per side.
        pivot = (pdh + pdl + pdc) / 3
        base = (pdh + pdl) / 2
        top, bottom = max(base, 2 * pivot - base), min(base, 2 * pivot - base)
        done = set()
        for i in range(1, n):
            if not (585 <= mins[i] + 5 <= 810):
                continue
            if 1 not in done and c[i] > top and c[i - 1] <= top and c[i] > vwap[i]:
                out[stamps[i]] = 1
                done.add(1)
            elif -1 not in done and c[i] < bottom and c[i - 1] >= bottom and c[i] < vwap[i]:
                out[stamps[i]] = -1
                done.add(-1)
    elif fam == "IB_BREAK":
        # The first hour's range (the initial balance): the first close through it by 0.1 ATR, 10:15 to 13:30, one per side.
        ib = np.where(mins < 615)[0]
        if len(ib) == 12 and mins[0] == 555:
            top, bottom, done = float(h[ib].max()), float(l[ib].min()), set()
            for i in range(12, n):
                if not (atr[i] > 0) or mins[i] + 5 > 810:
                    continue
                if 1 not in done and c[i] > top + 0.1 * atr[i] and c[i - 1] <= top + 0.1 * atr[i - 1]:
                    out[stamps[i]] = 1
                    done.add(1)
                elif -1 not in done and c[i] < bottom - 0.1 * atr[i] and c[i - 1] >= bottom - 0.1 * atr[i - 1]:
                    out[stamps[i]] = -1
                    done.add(-1)
    elif fam == "SUPERTREND_VWAP":
        # Supertrend (3 x ATR, restarted each morning): a flip with the close on VWAP's side, 09:45 to 13:30.
        trend, upper, lower = 0, float("inf"), float("-inf")
        for i in range(n):
            if not (atr[i] > 0):
                continue
            mid = (h[i] + l[i]) / 2
            up, low = mid + 3 * atr[i], mid - 3 * atr[i]
            before = c[i - 1] if i else c[i]
            upper = up if up < upper or before > upper else upper
            lower = low if low > lower or before < lower else lower
            flip = 1 if c[i] > upper else -1 if c[i] < lower else trend
            if trend != 0 and flip != trend and 585 <= mins[i] + 5 <= 810 and ((flip > 0) == (c[i] > vwap[i])):
                out[stamps[i]] = flip
            trend = flip
    else:
        raise ValueError(fam)
    _TABLE[key] = out
    while len(_TABLE) > 6000:
        _TABLE.pop(next(iter(_TABLE)))
    return out


def family_signal(m: dict, frame, regime: str, now):
    naive = now.replace(tzinfo=None)
    f = O27F.day_features(frame, naive.date())
    bar_ts = O27F.last_closed_bar(f, now) if f is not None else Y.replay._last_closed_bar(frame, now)
    if bar_ts is None or f is None or not f["complete_open"]:
        return G.MomSignal(bar_ts=bar_ts or "", reject_reason="o31e:no_features")
    return G._signal(frame, regime, now, m, entries(m, f).get(bar_ts), bar_ts, f)


_prev_signal = G.new_signal


def new_signal(m, frame, regime, now):
    return family_signal(m, frame, regime, now) if m["family"] in FAMILIES else _prev_signal(m, frame, regime, now)


G.new_signal = new_signal


def member(family: str, gate: str, **genes) -> dict:
    return G.new_member(family, gate, **{"stop_atr": 1.0, "target_r": 2.0, "exit": "LATE", **genes})


# ---- the filters on a fired signal ------------------------------------------------------------------------------------

def expansion_at(frame, now) -> float | None:
    """Today's range so far as a share of the average daily range of the earlier sessions in the frame (at least 5)."""
    naive = now.replace(tzinfo=None)
    f = O27F.day_features(frame, naive.date())
    if f is None:
        return None
    bar_ts = O27F.last_closed_bar(f, now)
    if bar_ts is None:
        return None
    t = f["t"]
    upto = t[t.index <= pd.Timestamp(bar_ts)]
    x = frame[~frame.index.duplicated(keep="last")]
    prior = x[x.index.date < naive.date()]
    if prior.empty:
        return None
    by_day = prior.groupby(prior.index.date).agg(high=("high", "max"), low=("low", "min"))
    if len(by_day) < 5:
        return None
    usual = float((by_day["high"] - by_day["low"]).mean())
    return float(upto["high"].max() - upto["low"].min()) / usual if usual > 0 else None


def filter_reason(book: dict, side: dict, direction: str, frame, now) -> str | None:
    """Why a fired signal is passed over, or None. The first signal of a tick decides, as with the stretched-entry rule."""
    long = direction == "LONG"
    if book.get("only_dir") and direction != book["only_dir"]:
        return "only_dir"
    if "calls_min_adx" in book and long and (side.get("adx_value") or 0) < book["calls_min_adx"]:
        return "calls_min_adx"
    if "min_stretch" in book:
        s = S.stretch_at(frame, now, direction)
        if s is not None and s < book["min_stretch"]:
            return "behind_vwap"
    if "gap" in book:
        if side.get("gap_dir") is None or ((side["gap_dir"] == "UP") == long) != (book["gap"] == "with"):
            return "gap"
    if "clock" in book:
        minute = now.hour * 60 + now.minute
        if not book["clock"][0] <= minute < book["clock"][1]:
            return "clock"
    if "expansion" in book:
        ratio = expansion_at(frame, now)
        if ratio is None or ratio < book["expansion"]:
            return "expansion"
    return None


_prev_route = Y.BookReplay.route


def route(self, frame, regime, now):
    sig = _prev_route(self, frame, regime, now)
    if self.warm or sig.direction is None or "o31e" not in self.book:
        return sig
    row = self.table.get(now.date().isoformat()) or {}
    reason = filter_reason(self.book, row.get("side") or {}, sig.direction.value, frame, now)
    if reason:
        self.notes[f"o31e_{reason}"] += 1
        return G.MomSignal(bar_ts=sig.bar_ts, reject_reason=f"o31e:{reason}")
    return sig


Y.BookReplay.route = route


# ---- the books -----------------------------------------------------------------------------------------------------

def gated(gate: str) -> list:
    return X.gated(gate)


def compound(side: str) -> dict:
    return {"members": gated(f"{OPEN}&{side}"), "router": "o30m"}


CHANGES = {
    # group C: inside the main book's days
    "C|puts_only": {"members": gated(OPEN), "only_dir": "SHORT"},
    "C|no_eff": {"members": [m for m in gated(OPEN) if m["name"] != "EFF"]},
    "C|no_behind_vwap": {"members": gated(OPEN), "min_stretch": 0.0},
    "C|no_big_gap": compound("gap_big:LOW"),
    "C|with_gap_only": {"members": gated(OPEN), "gap": "with"},
    "C|adx_rising": compound("adx_rising:HIGH"),
    "C|narrow_open": compound("or_width:LOW"),
    "C|calls_need_35": {"members": gated(OPEN), "calls_min_adx": 35},
    # group D: more days, puts only below ADX 30
    "D|puts_from_25": {"members": gated("adx_abs25:HIGH"), "calls_min_adx": 30},
    "D|puts_from_20": {"members": gated("adx_abs20:HIGH"), "calls_min_adx": 30},
    "D|puts_every_day": {"members": gated("ALWAYS"), "calls_min_adx": 30},
    "D|only_puts_from_25": {"members": gated("adx_abs25:HIGH"), "only_dir": "SHORT"},
    "D|only_puts_from_20": {"members": gated("adx_abs20:HIGH"), "only_dir": "SHORT"},
    "D|only_puts_every_day": {"members": gated("ALWAYS"), "only_dir": "SHORT"},
    "D|tpb_puts_closed": {"members": [*gated(OPEN), Y.named("TPB", CLOSED)], "calls_min_adx": 30},
}


def closed_compound(side: str) -> dict:
    return {"members": gated(f"{CLOSED}&{side}"), "router": "o30m"}


def pdl_member() -> dict:
    return {**X.lab_m.library()["L|PDL_BREAK|4"]["members"][0], "gate": CLOSED}


SPECIALISTS = {
    "E|four_10_30_to_12": {"members": gated(CLOSED), "clock": [630, 720]},
    "E|four_against_gap": {"members": gated(CLOSED), "gap": "against"},
    "E|four_against_gap_10_30_to_12": {"members": gated(CLOSED), "gap": "against", "clock": [630, 720]},
    "E|four_range_expansion": {"members": gated(CLOSED), "expansion": EXPANSION},
    "E|four_on_events": closed_compound("event:HIGH"),
    "E|four_adx_25_30_rising": {"members": gated(f"adx_abs25:HIGH&{CLOSED}&adx_rising:HIGH"), "router": "o30m"},
    "E|four_puts": {"members": gated(CLOSED), "only_dir": "SHORT"},
    "E|tpb_puts": {"members": [Y.named("TPB", CLOSED)], "only_dir": "SHORT"},
    "E|gap_fade": {"members": [member("GAP_FADE", f"{CLOSED}&gap_big:HIGH")], "router": "o30m"},
    "E|cpr_break": {"members": [member("CPR_BREAK", f"{CLOSED}&cpr_narrow:HIGH")], "router": "o30m"},
    "E|ib_break": {"members": [member("IB_BREAK", f"{CLOSED}&or_width:LOW", exit="RUN")], "router": "o30m"},
    "E|supertrend_vwap": {"members": [member("SUPERTREND_VWAP", CLOSED, stop_atr=1.5, exit="RUN")]},
    "E|last_hour_closed": {"members": [member("LAST_HOUR", CLOSED, stop_atr=1.5, target_r=3.0, exit="RUN")], "skip": None, "cfg": LATE_CFG},
    "E|last_hour_every_day": {"members": [member("LAST_HOUR", "ALWAYS", stop_atr=1.5, target_r=3.0, exit="RUN")], "skip": None, "cfg": LATE_CFG},
    "E|pdl_break_4": {"members": [pdl_member()]},
}


def _exact(name: str, v: dict) -> dict:
    return X.book(f"EX|{name}", **v, o31e=1)


def _raw(name: str, v: dict) -> dict:
    v = dict(v)
    extra = v.pop("cfg", {})
    return X.book(f"RAW|{name}", cfg={**S.RAW, **extra}, cost=False, **v, o31e=1)


def books() -> dict:
    main = {"members": gated(OPEN)}
    out = {"EX|MAIN": X.book("EX|MAIN", **main), "RAW|MAIN": X.book("RAW|MAIN", cfg=dict(S.RAW), cost=False, **main)}
    for name, v in CHANGES.items():
        out[f"EX|{name}"] = _exact(name, v)
        out[f"RAW|{name}"] = _raw(name, v)
    for name, v in SPECIALISTS.items():
        out[f"RAW|{name}"] = _raw(name, v)
    for i, b in enumerate(Y.null_fixed()):
        out[f"RANDOM|{i:02d}|closed"] = X.book(f"RANDOM|{i:02d}|closed", members=[{**m, "gate": CLOSED} for m in b["members"]],
                                                cfg=dict(S.RAW), cost=False)
    return out


RULE = {
    "status": "Found by looking at NIFTY 2024, 2025 and Jan - Oct 2026, all seen. A pass here is a candidate for an unseen check (NIFTY 2023 if "
              "Breeze serves it, forward sessions, real fills), never proof. Nothing in the system changes on this; the owner decides.",
    "parity": "EX|MAIN must reproduce +16,371 / +5,710 / +30,540, and RAW|MAIN the stored surface cell, or nothing here counts",
    "change_improves": "Groups C and D, exact at today's limits with the cost in the path: nets more than MAIN in EVERY year, fall at most 1 point "
                       "above MAIN's in every year, at least 15 trades in every year, paired weekly t against MAIN >= 2",
    "better_balance": "Groups C and D, also reported: three-year net at least 20% above MAIN's, positive in every year, worst yearly fall <= 12% (the ADX "
                      "25 book's), paired weekly t >= 1.5. It can move money between years, so it is a weaker claim than change_improves",
    "specialist_passes": "Group E, one lot, brakes off, after Rs 200 a trade, against sitting out: above zero in EVERY year, at least 8 trades every year "
                         "and 40 in all, weekly t >= 2, and above the best of the 20 random closed-day books over the three years",
    "selection_luck": "Choose among groups C and D on two years (highest worse-of-two net with falls <= 25% and 15+ trades a year) and score on the third "
                      "against MAIN, all three ways. Choose among group E the same way and score the third against zero",
    "direction_control": "Puts against calls on the 20 random closed-day books and on the 20 random ADX 30 books: if random entries show the same gap, the "
                         "put edge is a market effect rather than a skill of these strategies",
    "no_change": "Nothing changes on this result; the owner decides. A one-sided book carries a risk these three years cannot measure: a long calm rise.",
}


# ---- freeze and run -----------------------------------------------------------------------------------------------------

def sources() -> dict:
    final = ROOT / "docs/research/fno/2026-10-31-final-book"
    return {p.relative_to(ROOT).as_posix(): Y.grid._sha(p) for p in
            [*sorted((ROOT / "python-engine").glob("*.py")), HERE / "lab_w.py", HERE / "sides_w.py", HERE / "analyze_w.py", HERE / "test_lab_w.py",
             final / "lab_o.py", final / "lab_o2.py"]}


def freeze() -> None:
    Y.write_new(HERE / "freeze.json", {"schema": "o31e_weak_spots_v1", "books": json.loads(json.dumps(books())), "rule": RULE, "sources": sources(),
                                       "qualification": "NOT_ASSESSED", "can_place_orders": False})
    print("frozen", len(books()), "books per year")


def run(jobs: int) -> None:
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    rel = (HERE / "freeze.json").relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)) == frozen, "not committed"
    changed = [k for k, v in frozen["sources"].items() if Y.grid._sha(ROOT / k) != v]
    assert not changed, f"files changed since the freeze: {changed}"
    all_books = books()
    assert {n: Y.digest(b) for n, b in frozen["books"].items()} == {n: Y.digest(b) for n, b in all_books.items()}
    assert 1 <= jobs <= 7
    O27F.deny_network()
    C.table("year")
    with ProcessPoolExecutor(max_workers=jobs, initializer=L._init) as ex:
        runner = Y.Runner(ex, jobs)
        runner.run(list(all_books.values()), source="year", window=C.WINDOW)
    L._atomic(LOCAL / f"keys-{YEAR}.json", {n: Y.task_key(b, "year", C.WINDOW) for n, b in all_books.items()})
    print("DONE", YEAR, len(all_books), flush=True)


def smoke() -> None:
    """Every new kind over January of the chosen year: proves the plumbing, scores nothing."""
    O27F.deny_network()
    Y.speedups()
    Y.EVALS = LOCAL / "smoke"
    window = (f"{YEAR}-01-01", f"{YEAR}-01-31")
    C.table("year")
    Y._worker_init()
    all_books = books()
    for name in ("RAW|C|puts_only", "RAW|C|no_behind_vwap", "RAW|C|with_gap_only", "RAW|C|calls_need_35", "RAW|D|puts_every_day", "RAW|D|tpb_puts_closed", "RAW|E|four_range_expansion",
                 "RAW|E|four_10_30_to_12", "RAW|E|four_on_events", "RAW|E|gap_fade", "RAW|E|cpr_break", "RAW|E|ib_break", "RAW|E|supertrend_vwap", "RAW|E|last_hour_every_day", "RAW|E|pdl_break_4"):
        _key, trades = Y.evaluate((all_books[name], "year", window))
        print(f"smoke {YEAR} {name}: {len(trades)} trades, {sorted({t.get('direction') for t in trades})}, last exit {max((t.get('exit_time') or '')[11:16] for t in trades) if trades else '-'} (plumbing only)", flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["freeze", "run", "smoke"])
    cli.add_argument("--jobs", type=int, default=6)
    a = cli.parse_args()
    {"freeze": freeze, "run": lambda: run(a.jobs), "smoke": smoke}[a.action]()
